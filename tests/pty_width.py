#!/usr/bin/env python3
"""tui-markdown's start-up width probe (tui 0.14.0), end to end through the real binary, on a pty.

    python3 tests/pty_width.py <tui-markdown-binary> [scratch-dir]

The terminal is `pyte` made to answer cursor position reports (`CSI 6 n`) as a real one does: every byte the viewer writes is
fed to the emulator and the reports it produces go back to it at once (tui's `tests/width_pty.m31` plays the terminal the
same way for a bare loop). The width model is swapped as in `pty_variants.py`. Each case opens the help (`?`), a box,
which is the screen's one border; a repaint is a resize away and back (the loop clears the screen and writes every cell). Checked:

  * an answering terminal that agrees with the library: the probe is asked (`CSI 6 n`), the help keeps its line-drawing box;
  * a terminal that draws box characters two columns wide: the viewer measures it and draws the box in ASCII (no line-drawing
    character on the screen), and the screen equals the terminal's own repaint (a resize writes a full frame);
  * `TUI_BORDERS=ascii` draws ASCII anyway, `TUI_BORDERS=unicode` keeps the characters on the box-wide terminal;
  * `TUI_WIDTH_PROBE=off` asks nothing, whatever the terminal is;
  * a mute terminal (no answers): the first frame comes after the probe's budget (a lower bound only, so a slow machine
    cannot fail it), the box is the unicode one (the 0.13.0 policy), and a key typed during the wait (`?`) is not lost.

Time to the first frame of each case is printed as a note, never asserted from above. Margins: pty writes never block, a
dead child is tolerated, every wait is "until the bytes are there, then quiet" (hundreds of ms). Skips with a note when
pyte is missing.
"""
import fcntl
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time

try:
    import pyte
    import pyte.screens
except ImportError:
    print("skip pty_width: pyte is not installed")
    sys.exit(0)

binpath = os.path.abspath(sys.argv[1])
scratch = os.path.realpath(sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="mdvwidth"))
shutil.rmtree(scratch, ignore_errors=True)
os.makedirs(scratch, exist_ok=True)
ROWS, COLS = 30, 100
BOX = "\u2500\u2502\u250c\u2510\u2514\u2518\u256d\u256e\u2570\u256f"
CPR_ASK = b"\x1b[6n"
ALT_ON = b"\x1b[?1049h"
failures = 0
checks = 0
_pyte_width = pyte.screens.wcwidth
HELP = b"?"


def box_wide(ch):
    return 2 if 0x2500 <= ord(ch) <= 0x257F else _pyte_width(ch)


def check(name, condition, detail=""):
    global failures, checks
    checks += 1
    if condition:
        print("ok   " + name, flush=True)
    else:
        failures += 1
        print("FAIL " + name + ": " + detail, flush=True)


project = os.path.join(scratch, "project")
os.makedirs(project)
doc_path = os.path.join(project, "doc.md")
with open(doc_path, "w") as f:
    f.write("# hello world\n\nsecond paragraph with some words\n\n- one\n- two\n")


class Answering(pyte.Screen):
    """A pyte screen whose `CSI 6 n` reports go back to the program."""

    def __init__(self, cols, rows, master):
        super().__init__(cols, rows)
        self.master = master

    def write_process_input(self, data):
        try:
            os.write(self.master, data.encode())
        except (OSError, BlockingIOError):
            pass


class Viewer:
    def __init__(self, env_extra=None, width=_pyte_width, answers=True, keys=None):
        self.width = width
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        fcntl.fcntl(self.master, fcntl.F_SETFL, fcntl.fcntl(self.master, fcntl.F_GETFL) | os.O_NONBLOCK)
        env = dict(os.environ)
        for key in ("TERM_PROGRAM", "VISUAL", "EDITOR", "NO_COLOR", "TUI_WIDTH_PROBE", "TUI_BORDERS"):
            env.pop(key, None)
        env.update(TERM="xterm-256color", COLORTERM="truecolor", LANG="C.UTF-8", HOME=project, PWD=project,
                   XDG_CONFIG_HOME=os.path.join(project, ".config"), XDG_STATE_HOME=os.path.join(project, ".state"))
        env.update(env_extra or {})
        self.screen = Answering(COLS, ROWS, self.master) if answers else pyte.Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.raw = b""
        self.started = time.time()
        self.alt_at = None
        self.frame_at = None
        self.keys = keys
        self.is_keys_sent = False
        self.proc = subprocess.Popen([binpath, "--no-watch", doc_path], stdin=slave, stdout=slave, stderr=slave,
                                     cwd=project, env=env, start_new_session=True)
        os.close(slave)

    def feed(self, chunk):
        self.raw += chunk
        pyte.screens.wcwidth = self.width
        try:
            self.stream.feed(chunk)
        finally:
            pyte.screens.wcwidth = _pyte_width
        now = time.time()
        if self.alt_at is None and ALT_ON in self.raw:
            self.alt_at = now
            if self.keys and not self.is_keys_sent:
                self.is_keys_sent = True
                self.write(self.keys)
        if self.frame_at is None and self.alt_at is not None and any("hello" in t for t in self.text()):
            self.frame_at = now

    def write(self, data):
        try:
            os.write(self.master, data)
        except (OSError, BlockingIOError):
            pass

    def drain(self, quiet):
        while True:
            try:
                ready, _, _ = select.select([self.master], [], [], quiet)
            except (OSError, ValueError):
                return
            if not ready:
                return
            try:
                chunk = os.read(self.master, 65536)
            except BlockingIOError:
                continue
            except OSError:
                return
            if not chunk:
                return
            self.feed(chunk)

    def settle(self, quiet=0.8, timeout=20.0):
        """Read until the first frame is there (or the time is up), then until quiet."""
        end = time.time() + timeout
        while self.frame_at is None and time.time() < end and self.proc.poll() is None:
            self.drain(0.1)
        self.drain(quiet)

    def text(self):
        return ["".join(self.screen.buffer[y][x].data or " " for x in range(COLS)) for y in range(ROWS)]

    def repaint(self):
        """A resize writes a full frame: what the same terminal shows after it, from a blank screen."""
        mark = 0
        for rows in (ROWS + 1, ROWS):
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, COLS, 0, 0))
            try:
                os.killpg(os.getpgid(self.proc.pid), 28)
            except OSError:
                pass
            if rows == ROWS:
                mark = len(self.raw)
            self.drain(0.8)
        fresh = pyte.Screen(COLS, ROWS)
        pyte.screens.wcwidth = self.width
        try:
            pyte.ByteStream(fresh).feed(self.raw[mark:])
        finally:
            pyte.screens.wcwidth = _pyte_width
        return ["".join(fresh.buffer[y][x].data or " " for x in range(COLS)) for y in range(ROWS)]

    def probe_wait_ms(self):
        if self.alt_at is None or self.frame_at is None:
            return None
        return int((self.frame_at - self.alt_at) * 1000)

    def close(self):
        if self.proc.poll() is None:
            self.write(b"q")
            self.drain(0.2)
            self.write(b"q")
        end = time.time() + 3
        while self.proc.poll() is None and time.time() < end:
            self.drain(0.1)
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        try:
            os.close(self.master)
        except OSError:
            pass


def has_box(lines):
    return any(ch in BOX for line in lines for ch in line)


def run(env_extra=None, width=_pyte_width, answers=True, keys=None, open_help=True):
    ed = Viewer(env_extra, width, answers, keys)
    ed.settle()
    if open_help and keys is None:
        ed.write(HELP)
        ed.drain(0.8)
        ed.drain(0.5)
    return ed


def note(name, ed):
    print("note %s: first frame %s ms after the alternate screen" % (name, ed.probe_wait_ms()), flush=True)


def help_shown(ed):
    return any("redraw the whole screen" in t or "scroll a line" in t for t in ed.text())


# --- a terminal that answers and agrees with the library -------------------------------------
ed = run()
try:
    note("answering terminal", ed)
    check("the probe is asked (CSI 6 n)", CPR_ASK in ed.raw)
    check("the help is drawn", help_shown(ed), "\n".join(ed.text()[:12]))
    check("an agreeing terminal keeps line-drawing borders", has_box(ed.text()), "\n".join(ed.text()[:12]))
finally:
    ed.close()

# --- a terminal that draws box characters two columns wide ------------------------------------
ed = run(width=box_wide)
try:
    note("box-wide terminal", ed)
    check("box-wide: the probe is asked", CPR_ASK in ed.raw)
    check("box-wide: the help is drawn", help_shown(ed), "\n".join(ed.text()[:12]))
    check("box-wide: no line-drawing character on the screen (ASCII borders)", not has_box(ed.text()), "\n".join(ed.text()[:12]))
    check("box-wide: ASCII borders are there", any("+-" in t for t in ed.text()) and any("|" in t for t in ed.text()), "\n".join(ed.text()[:12]))
    shown = ed.text()
    again = ed.repaint()
    check("box-wide: the screen equals the terminal's own repaint", shown == again,
          " | ".join("row %d %r != %r" % (y, shown[y].rstrip(), again[y].rstrip()) for y in range(ROWS) if shown[y] != again[y]))
finally:
    ed.close()

ed = run({"TUI_BORDERS": "unicode"}, width=box_wide)
try:
    check("box-wide with TUI_BORDERS=unicode: the characters stay (the user asked)", has_box(ed.text()))
finally:
    ed.close()

ed = run({"TUI_BORDERS": "ascii"})
try:
    check("TUI_BORDERS=ascii on an agreeing terminal: ASCII", help_shown(ed) and not has_box(ed.text()) and any("|" in t for t in ed.text()), "\n".join(ed.text()[:12]))
finally:
    ed.close()

# --- the probe off -------------------------------------------------------------------------
ed = run({"TUI_WIDTH_PROBE": "off"}, width=box_wide)
try:
    note("TUI_WIDTH_PROBE=off (box-wide terminal)", ed)
    check("TUI_WIDTH_PROBE=off: nothing is asked", CPR_ASK not in ed.raw)
    check("TUI_WIDTH_PROBE=off: the help is drawn", help_shown(ed), "\n".join(ed.text()[:12]))
finally:
    ed.close()

# --- a terminal that never answers -------------------------------------------------------------
ed = run(answers=False, keys=HELP)
try:
    ed.drain(0.8)
    note("mute terminal", ed)
    waited = ed.probe_wait_ms()
    check("mute: the probe is asked", CPR_ASK in ed.raw)
    check("mute: the first frame waits for the budget (at least 120 ms of 150)", waited is not None and waited >= 120, str(waited))
    check("mute: a key typed during the wait is not lost (the help is drawn)", help_shown(ed), "\n".join(ed.text()[:12]))
    check("mute: the box is the unicode one (the 0.13.0 policy)", has_box(ed.text()), "\n".join(ed.text()[:12]))
finally:
    ed.close()

ed = run({"TUI_WIDTH_PROBE": "off"}, answers=False)
try:
    note("mute terminal, TUI_WIDTH_PROBE=off", ed)
    check("mute with TUI_WIDTH_PROBE=off: nothing is asked", CPR_ASK not in ed.raw)
finally:
    ed.close()

shutil.rmtree(scratch, ignore_errors=True)
print("pty_width: %d checks, %d failed" % (checks, failures))
sys.exit(1 if failures else 0)
