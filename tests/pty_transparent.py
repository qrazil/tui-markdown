#!/usr/bin/env python3
"""tui-markdown on a terminal with a transparent background, through the real binary, on a pty.

    python3 tests/pty_transparent.py <tui-markdown-binary> [scratch-dir [baseline-binary]]

A terminal shows the desktop through a cell only when the cell's background is the terminal's default, so a
transparent page may not write a background (SGR 40-48, 100-107) except under a highlight: a search hit, the
focused link, a selection, a chosen row. The viewer is opened on a rich markdown sample (heading, code card, quotes,
callouts, table, links, lists, an image) and driven through the page, the help, the outline, a search, link focus,
the sidebar, the editor (selection, the find bar, the command palette, the three panes), the scaled heading and a
reload from disk. After every step the emulator (`pyte`) is asked for each cell's background and the bytes the step
wrote are parsed for SGR:

  * `--transparent on`, for the dark, light and plain themes: after each step no cell has a background (`cell.bg ==
    'default'`) and no reverse video, except where the step has a highlight; the bytes of a step without one carry no
    background SGR at all; the cells of a highlight read as exactly what was searched, focused or selected;
  * `--transparent popups`: the popups (help, outline, palette, find bar) have no background inside their box while the
    page still has one, so it is not `on`; `TUI_MARKDOWN_TRANSPARENT` says the same as the flag, and the flag wins;
  * default (off, `0`, `--transparent off`): the bytes of a scripted session equal what 0.9.0 wrote, byte for byte,
    against `baseline-binary` (a build of the 0.9.0 tag; or $TUI_MARKDOWN_BASELINE) or, without one, the hashes in
    tests/golden/pty_default_0.9.0.txt (PTY_BLESS=1 with a baseline rewrites them).

Margins: pty writes never block, a dead child is tolerated, every wait is "until the bytes are there, then quiet"
(hundreds of ms), paths are resolved here, the environment is cleared of what the program reads. Skips with a note when
pyte is missing.
"""
import concurrent.futures
import fcntl
import hashlib
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import time

try:
    import pyte
except ImportError:
    print("skip pty_transparent: pyte is not installed")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
binpath = os.path.abspath(sys.argv[1])
scratch = os.path.realpath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.environ.get("TMPDIR", "/tmp"), "mdvtransp%d" % os.getpid()))
baseline = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("TUI_MARKDOWN_BASELINE", "")
baseline = os.path.abspath(baseline) if baseline else ""
shutil.rmtree(scratch, ignore_errors=True)
os.makedirs(scratch, exist_ok=True)
ROWS, COLS = 36, 100
QUIET = 0.35
GOLDEN = os.path.join(HERE, "golden", "pty_default_0.9.0.txt")
failures = 0
checks = 0


def check(name, condition, detail=""):
    global failures, checks
    checks += 1
    if condition:
        print("ok   " + name, flush=True)
    else:
        failures += 1
        print("FAIL " + name + (": " + detail if detail else ""), flush=True)


# --- the sample ---------------------------------------------------------------------------------

with open(os.path.join(HERE, "fixtures", "rich.md"), encoding="utf-8") as f:
    SAMPLE = f.read()
SAMPLE += "\n" + "\n".join("Filler line %d about the page and the terminal." % i for i in range(1, 40)) + "\n"
PROJECT = os.path.join(scratch, "project")
os.makedirs(PROJECT)


def write_doc(name, text=SAMPLE):
    path = os.path.join(PROJECT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# --- SGR in a byte stream -------------------------------------------------------------------------

CSI_SGR = re.compile(rb"\x1b\[([0-9;:]*)m")


def sgr_features(data):
    """(number of SGR that set a background, number that set reverse video) in `data`."""
    backgrounds = 0
    reverses = 0
    for match in CSI_SGR.finditer(data):
        params = match.group(1).decode().replace(":", ";").split(";")
        index = 0
        has_background = False
        while index < len(params):
            value = int(params[index] or 0)
            if value in (38, 48):
                if value == 48:
                    has_background = True
                index += 3 if index + 1 < len(params) and params[index + 1] == "5" else 5
                continue
            if 40 <= value <= 47 or 100 <= value <= 107:
                has_background = True
            if value == 7:
                reverses += 1
            index += 1
        backgrounds += 1 if has_background else 0
    return backgrounds, reverses


# --- a terminal ------------------------------------------------------------------------------------


class Answering(pyte.Screen):
    """A pyte screen whose cursor position reports go back to the program."""

    def __init__(self, cols, rows, master):
        super().__init__(cols, rows)
        self.master = master

    def write_process_input(self, data):
        try:
            os.write(self.master, data.encode())
        except (OSError, BlockingIOError):
            pass


class Step:
    def __init__(self, label, kind, raw, cells, text):
        self.label = label
        self.kind = kind
        self.raw = raw
        self.cells = cells
        self.text = text

    def marked(self):
        """The cells that carry a background or reverse video: [(row, col, char, has_background)]."""
        out = []
        for y, row in enumerate(self.cells):
            for x, cell in enumerate(row):
                if cell[1] != "default" or cell[2]:
                    out.append((y, x, cell[0], cell[1] != "default"))
        return out

    def backgrounds(self):
        return [m for m in self.marked() if m[3]]

    def runs(self):
        """The text of each run of marked cells on a row."""
        out = []
        last = None
        current = ""
        for y, x, char, _ in self.marked():
            if last is not None and last == (y, x - 1):
                current += char
            else:
                if current:
                    out.append(current)
                current = char
            last = (y, x)
        if current:
            out.append(current)
        return out


class Session:
    def __init__(self, binary, args, env_extra=None, doc="doc.md"):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        fcntl.fcntl(self.master, fcntl.F_SETFL, fcntl.fcntl(self.master, fcntl.F_GETFL) | os.O_NONBLOCK)
        env = dict(os.environ)
        for key in ("NO_COLOR", "COLORFGBG", "COLORTERM", "TERM_PROGRAM", "TERM_PROGRAM_VERSION", "KITTY_WINDOW_ID",
                    "WEZTERM_EXECUTABLE", "GHOSTTY_RESOURCES_DIR", "LC_TERMINAL", "VTE_VERSION", "WT_SESSION",
                    "KONSOLE_VERSION", "TUI_BORDERS", "TUI_MARKDOWN_TRANSPARENT", "VISUAL", "EDITOR"):
            env.pop(key, None)
        env.update(TERM="xterm-256color", COLORTERM="truecolor", LANG="C.UTF-8", HOME=PROJECT, PWD=PROJECT,
                   TUI_WIDTH_PROBE="off", GIT_CEILING_DIRECTORIES=scratch,
                   XDG_CONFIG_HOME=os.path.join(PROJECT, ".config"), XDG_STATE_HOME=os.path.join(PROJECT, ".state"))
        env.update(env_extra or {})
        self.screen = Answering(COLS, ROWS, self.master)
        self.stream = pyte.ByteStream(self.screen)
        self.raw = b""
        self.steps = []
        self.proc = subprocess.Popen([binary] + args + [doc], stdin=slave, stdout=slave, stderr=slave, cwd=PROJECT,
                                     env=env, start_new_session=True)
        os.close(slave)

    def drain(self, quiet=QUIET, first=False):
        """Read until bytes have come (`first`: up to 10 s for the first frame) and then until quiet."""
        end = time.time() + (10.0 if first else 0)
        got = False
        while True:
            try:
                ready, _, _ = select.select([self.master], [], [], 0.1 if (first and not got) else quiet)
            except (OSError, ValueError):
                return
            if not ready:
                if first and not got and time.time() < end and self.proc.poll() is None:
                    continue
                return
            try:
                chunk = os.read(self.master, 65536)
            except BlockingIOError:
                continue
            except OSError:
                return
            if not chunk:
                return
            got = True
            self.raw += chunk
            self.stream.feed(chunk)

    def snapshot(self):
        cells = []
        for y in range(ROWS):
            row = []
            for x in range(COLS):
                cell = self.screen.buffer[y][x]
                row.append((cell.data or " ", cell.bg, cell.reverse))
            cells.append(row)
        text = ["".join(c[0] for c in row) for row in cells]
        return cells, text

    def step(self, label, keys, kind="none", first=False):
        mark = len(self.raw)
        if keys:
            try:
                os.write(self.master, keys)
            except (OSError, BlockingIOError):
                pass
        self.drain(first=first)
        cells, text = self.snapshot()
        record = Step(label, kind, self.raw[mark:], cells, text)
        self.steps.append(record)
        return record

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.close(self.master)
        except OSError:
            pass


ESC = b"\x1b"
TAB = b"\t"
ENTER = b"\r"
CTRL_P = b"\x10"
CTRL_F = b"\x06"
CTRL_R = b"\x12"
CTRL_Q = b"\x11"
SHIFT_RIGHT = b"\x1b[1;2C"
ALT_S = b"\x1bs"
ALT_P = b"\x1bp"
ALT_L = b"\x1bl"


def preview_session(binary, args, env=None):
    """The page, help, outline, search, link focus, theme switch, yank: a step is (label, keys, kind)."""
    s = Session(binary, ["--no-watch"] + args, env)
    s.step("page", b"", "none", first=True)
    s.step("scroll", b"jjj", "none")
    s.step("help", b"?", "popup")
    s.step("help closed", ESC, "none")
    s.step("outline", b"o", "row")
    s.step("outline next", b"j", "row")
    s.step("outline closed", ESC, "none")
    s.step("search typing", b"/the", "cursor")
    s.step("search hits", ENTER, "hits:the")
    s.step("next hit", b"n", "hits:the")
    s.step("search cleared", ESC, "none")
    s.step("link focused", TAB, "hits:link")
    s.step("link refocused", TAB, "any")
    s.step("link unfocused", ESC, "none")
    s.step("end", b"G", "none")
    s.step("top", b"gg", "none")
    s.step("next theme", b"t", "none")
    s.step("yank", b"y", "none")
    return s


def side_session(binary, args, env=None):
    s = Session(binary, ["--no-watch", "--side"] + args, env)
    s.step("page with the sidebar", b"", "none", first=True)
    s.step("scrolled", b"15j", "none")
    s.step("end", b"G", "none")
    return s


def edit_session(binary, args, env=None):
    """Live editing: caret, typing, a selection, the find bar, the replace row, the palette, the three panes."""
    s = Session(binary, ["--no-watch", "--edit"] + args, env)
    s.step("live page", b"", "cursor", first=True)
    s.step("typed", b"abc", "cursor")
    s.step("selected", SHIFT_RIGHT * 3 + SHIFT_RIGHT * 0, "select")
    s.step("deselected", b"\x1b[C", "cursor")
    s.step("find bar", CTRL_F + b"the", "any")
    # the found text stays selected (a highlight) until the caret moves
    s.step("find closed", ESC, "any")
    s.step("find, caret moved", b"\x1b[C", "any")
    s.step("replace row", CTRL_R + b"the", "any")
    s.step("replace closed", ESC, "any")
    s.step("replace, caret moved", b"\x1b[C", "cursor")
    s.step("palette", CTRL_P, "row")
    s.step("palette typed", b"zeb", "row")
    s.step("palette closed", ESC, "cursor")
    s.step("source pane", ALT_S, "cursor")
    s.step("preview pane", ALT_P, "none")
    s.step("live pane", ALT_L, "cursor")
    return s


def scale_session(binary, args, env=None):
    s = Session(binary, ["--no-watch", "--scale", "on"] + args, env)
    s.step("scaled heading", b"", "none", first=True)
    s.step("scrolled", b"3j", "none")
    s.step("scrolled back", b"3k", "none")
    s.step("help over the heading", b"?", "popup")
    s.step("help closed", ESC, "none")
    return s


def reload_session(binary, args, env=None):
    doc = write_doc("reload.md")
    s = Session(binary, args, env, doc="reload.md")
    s.step("page", b"", "none", first=True)
    with open(doc, "a", encoding="utf-8") as f:
        f.write("\nA paragraph that arrived from disk.\n")
    later = time.time() + 3
    os.utime(doc, (later, later))
    s.step("reloaded", b"", "none")
    s.step("end", b"G", "none")
    return s


SCRIPTS = [("preview", preview_session), ("sidebar", side_session), ("editor", edit_session), ("scaled", scale_session), ("reload", reload_session)]
write_doc("doc.md")


# --- what a step must look like ---------------------------------------------------------------------


def box_of(step):
    """The rectangle (top, left, bottom, right) of the first rounded box on the screen, or None."""
    top = left = bottom = right = None
    for y, line in enumerate(step.text):
        if top is None and "╭" in line:
            top, left = y, line.index("╭")
            right = line.index("╮", left)
        if top is not None and "╰" in line:
            bottom = y
    if top is None or bottom is None:
        return None
    return top, left, bottom, right


def check_transparent(label, step, plain):
    where = "%s / %s" % (label, step.label)
    bytes_bg, bytes_rev = sgr_features(step.raw)
    backgrounds = step.backgrounds()
    marked = step.marked()
    kind = step.kind
    if kind == "none":
        check("%s: no cell has a background or reverse video" % where, not marked,
              "%d cells, first %r" % (len(marked), marked[:3]))
        check("%s: the bytes have no background SGR and no reverse" % where, bytes_bg == 0 and bytes_rev == 0,
              "%d background and %d reverse SGR" % (bytes_bg, bytes_rev))
    elif kind in ("popup", "cursor"):
        # no highlight, but a text cursor (reverse, one cell) may be there
        check("%s: no cell has a background" % where, not backgrounds, "%d cells, first %r" % (len(backgrounds), backgrounds[:3]))
        check("%s: the bytes have no background SGR" % where, bytes_bg == 0, "%d" % bytes_bg)
        check("%s: at most a few cells are reversed (the cursor)" % where, len(marked) <= 12, "%d" % len(marked))
    elif kind == "row":
        bg_rows = sorted(set(m[0] for m in backgrounds))
        reverse_only = [m for m in marked if not m[3]]
        check(
            "%s: the chosen row is the only row with a background (cursors are reverse)" % where,
            (len(bg_rows) <= 1 and len(marked) > 0 and len(reverse_only) <= 3)
            or (plain and 0 < len(set(m[0] for m in marked)) <= 3),
            "background rows %r, %d reverse cells" % (bg_rows, len(reverse_only)),
        )
        check("%s: the bytes carry no more than the chosen row's background" % where, bytes_bg <= 6, "%d" % bytes_bg)
    elif kind.startswith("hits:"):
        wanted = kind[5:]
        runs = step.runs()
        check("%s: something is marked and every marked run reads %r" % (where, wanted),
              runs and all(r.lower() == wanted for r in runs), "runs %r" % runs[:6])
        if not plain:
            check("%s: the marks are backgrounds" % where, len(backgrounds) == len(marked), "%d of %d" % (len(backgrounds), len(marked)))
    elif kind == "select":
        runs = step.runs()
        check("%s: the selection reads as the characters selected" % where, plain or (len(runs) >= 1 and all(len(r) <= 4 for r in runs)),
              "runs %r" % runs[:6])
    elif kind == "any":
        check("%s: a few cells at most are marked (highlights only)" % where, len(marked) <= 60, "%d" % len(marked))


def check_whole_stream(label, session):
    """A background SGR may only come in a step that has a highlight."""
    plain_steps = [s for s in session.steps if s.kind in ("none", "popup", "cursor")]
    leaked = [s.label for s in plain_steps if sgr_features(s.raw)[0] > 0]
    check("%s: no background SGR in any step without a highlight" % label, not leaked, "in %r" % leaked)


def check_popups(label, step):
    """popups mode: the popup's box has no background, the page around it still does."""
    box = box_of(step)
    where = "%s / %s" % (label, step.label)
    if box is None:
        check("%s: a popup box is on the screen" % where, False, "\n".join(step.text[:8]))
        return
    top, left, bottom, right = box
    inside = []
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if step.cells[y][x][1] != "default":
                inside.append((y, x))
    chosen_rows = sorted(set(y for y, _ in inside))
    check("%s: no background inside the box, except the chosen row" % where, len(chosen_rows) <= 1, "rows %r" % chosen_rows)
    outside = sum(1 for y in range(ROWS) for x in range(COLS) if (y < top or y > bottom or x < left or x > right) and step.cells[y][x][1] != "default")
    check("%s: the page around the box still has its background" % where, outside > 500, "%d cells" % outside)


# --- the checks --------------------------------------------------------------------------------------

SESSIONS = []


def run_all(label, binary, args, env=None, only=None):
    """Every script (or those in `only`) on its own pty, side by side."""
    wanted = [(n, f) for n, f in SCRIPTS if only is None or n in only]
    out = {}

    def one(item):
        name, script = item
        s = script(binary, args, env)
        s.close()
        return name, s

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        for name, s in pool.map(one, wanted):
            out[name] = s
    return out


# on, three themes
for theme in ("dark", "light", "plain"):
    label = "on/%s" % theme
    runs = run_all(label, binpath, ["--transparent", "on", "--theme", theme])
    for name, s in runs.items():
        for step in s.steps:
            check_transparent("%s %s" % (label, name), step, theme == "plain")
        check_whole_stream("%s %s" % (label, name), s)
    if theme != "plain":
        raw = b"".join(step.raw for step in runs["scaled"].steps)
        check("%s: the scaled heading (OSC 66) is on the wire" % label, b"\x1b]66;s=2;" in raw)
        check("%s: the editor's cursor, selection and palette row are drawn" % label,
              any(st.label == "selected" and st.runs() for st in runs["editor"].steps) and any(st.label == "palette" and st.marked() for st in runs["editor"].steps))
        reloaded = [st for st in runs["reload"].steps if st.label == "reloaded"][0]
        check("%s: the reload from disk showed" % label, any("reloaded" in line for line in reloaded.text) or any("from disk" in line for line in reloaded.text),
              "\n".join(reloaded.text[-3:]))
    if theme == "dark":
        outline = [st for st in runs["preview"].steps if st.label == "outline"][0]
        box = box_of(outline)
        check("on/dark: the outline keeps its rounded border (a popup is told apart by it)", box is not None)
        frame_text = "\n".join(runs["preview"].steps[0].text)
        check("on/dark: the code card is framed (rounded corner and a rule)", "╭" in frame_text and "╰" in frame_text)
        check("on/dark: the quote keeps its bar", "▎" in frame_text)
        printed = subprocess.run(
            [binpath, "--cat", "--width", "50", "--theme", "dark", "--transparent", "on", os.path.join(HERE, "fixtures", "rich.md")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, cwd=PROJECT,
        ).stdout.decode()
        printed = re.sub(r"\x1b\[[0-9;]*m", "", printed)
        check(
            "on/dark (--cat): the table keeps its borders and the card its frame",
            "│ a │ b │" in printed and "╭" in printed and "╰" in printed,
            printed[:200],
        )

# popups
runs = run_all("popups/dark", binpath, ["--transparent", "popups", "--theme", "dark"])
for name in ("preview", "scaled"):
    for step in runs[name].steps:
        if step.kind in ("popup", "row") and box_of(step):
            check_popups("popups/dark %s" % name, step)
for step in runs["editor"].steps:
    if step.label in ("palette", "palette typed"):
        check_popups("popups/dark editor", step)
page = runs["preview"].steps[0]
check("popups/dark: the page keeps its background (it is not 'on')", len(page.backgrounds()) > 1000, "%d" % len(page.backgrounds()))
find = [st for st in runs["editor"].steps if st.label == "find bar"][0]
bar_row = [y for y, line in enumerate(find.text) if "Find:" in line]
check("popups/dark: the find bar row has no background", bool(bar_row) and all(find.cells[bar_row[0]][x][1] == "default" for x in range(2, 40)),
      "rows %r" % bar_row)

# the environment variable, and the flag over it
env_run = Session(binpath, ["--no-watch", "--theme", "dark"], {"TUI_MARKDOWN_TRANSPARENT": "1"})
page = env_run.step("page", b"", "none", first=True)
env_run.close()
check("TUI_MARKDOWN_TRANSPARENT=1 is --transparent on", not page.marked() and sgr_features(page.raw) == (0, 0))
env_run = Session(binpath, ["--no-watch", "--theme", "dark"], {"TUI_MARKDOWN_TRANSPARENT": "popups"})
page = env_run.step("page", b"", "none", first=True)
env_run.close()
check("TUI_MARKDOWN_TRANSPARENT=popups is --transparent popups", len(page.backgrounds()) > 1000)
env_run = Session(binpath, ["--no-watch", "--theme", "dark", "--transparent", "off"], {"TUI_MARKDOWN_TRANSPARENT": "1"})
page = env_run.step("page", b"", "none", first=True)
env_run.close()
check("--transparent off beats TUI_MARKDOWN_TRANSPARENT=1", len(page.backgrounds()) > 1000)
env_run = Session(binpath, ["--no-watch", "--theme", "dark", "--transparent", "on"], {"TUI_MARKDOWN_TRANSPARENT": "0"})
page = env_run.step("page", b"", "none", first=True)
env_run.close()
check("--transparent on beats TUI_MARKDOWN_TRANSPARENT=0", not page.marked())

# --- default mode: the bytes of 0.9.0 ----------------------------------------------------------------

FLAVOURS = [("dark", ["--theme", "dark"], {}), ("plain", ["--theme", "plain"], {}), ("light", ["--theme", "light"], {}),
            ("dark, --transparent off", ["--theme", "dark", "--transparent", "off"], {}),
            ("dark, TUI_MARKDOWN_TRANSPARENT=0", ["--theme", "dark"], {"TUI_MARKDOWN_TRANSPARENT": "0"})]


def digest(sessions):
    lines = []
    for name, _ in SCRIPTS:
        if name not in sessions:
            continue
        for step in sessions[name].steps:
            lines.append("%s %s %s" % (name, step.label.replace(" ", "_"), hashlib.sha256(step.raw).hexdigest()))
    return lines


golden = {}
if os.path.exists(GOLDEN):
    with open(GOLDEN) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 4:
                golden[(parts[0], parts[1], parts[2])] = parts[3]
blessed = []
dark_default = None
for flavour, args, env in FLAVOURS:
    sessions = run_all("default/" + flavour, binpath, args, env)
    got = digest(sessions)
    if flavour == "dark":
        dark_default = got
    key = flavour.split(",")[0]
    if baseline and flavour in ("dark", "plain", "light"):
        old = digest(run_all("baseline/" + flavour, baseline, args, env))
        check("default (%s): every step's bytes equal the 0.9.0 binary's (%d steps)" % (flavour, len(got)), got == old,
              "first difference: %r" % next(((a, b) for a, b in zip(got, old) if a != b), None))
        if os.environ.get("PTY_BLESS"):
            blessed += ["%s %s" % (key, line) for line in old]
    elif flavour in ("dark", "plain", "light"):
        want = [l for l in (golden.get((key, *line.split()[:2])) for line in got)]
        mismatched = [line.split()[:2] for line, w in zip(got, want) if w is None or line.split()[2] != w]
        check("default (%s): every step's bytes equal the recorded 0.9.0 session (%d steps)" % (flavour, len(got)), not mismatched,
              "first %r" % mismatched[:3])
    else:
        # the explicit-off spellings write the same bytes as the default
        check("default (%s) is byte-identical to no option at all" % flavour, got == dark_default)

if blessed:
    with open(GOLDEN, "w") as f:
        f.write("\n".join(blessed) + "\n")
    print("note: wrote %s" % GOLDEN)

shutil.rmtree(scratch, ignore_errors=True)
print("pty_transparent: %d checks, %d failed" % (checks, failures))
sys.exit(1 if failures else 0)
