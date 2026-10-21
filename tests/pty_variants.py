#!/usr/bin/env python3
"""tui-markdown on terminals that measure text differently (tui 0.13.0's stress harness, on this viewer).

    python3 tests/pty_variants.py <tui-markdown-binary> <scratch-dir>

A document full of what terminals disagree on (text emoji with U+FE0F, keycaps, ZWJ sequences, flags,
Devanagari, halfwidth katakana, arrows, Nerd Font glyphs, emoji newer than a terminal's tables) in
headings, a list, a table, a quote and a code block. The viewer is driven (scrolling by line, page and
to the ends, a resize), and after every step the screen of each emulated terminal must equal what a
from-scratch repaint of the same state gives on that terminal (the repaint is what a resize writes:
it begins with a screen clear; CTRL-L asks for it). The terminals: pyte (xterm pending wrap; characters measured one code
point at a time as Terminal.app does: a family is 6 columns, U+2764 U+FE0F is 1), and the same with the
width table of `pyte.screens.wcwidth` swapped: ambiguous wide, private use wide, new emoji narrow, old
pictographs narrow, jamo added up, regional indicators wide. Skips with a note when pyte is missing.

Margins: non-blocking pty writes, a dead child tolerated, waits are "until bytes are there, then quiet"
(hundreds of ms), the document is written under a directory resolved here.
"""
import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import unicodedata

try:
    import pyte
    import pyte.screens
except ImportError:
    print("skip pty_variants: pyte is not installed")
    sys.exit(0)

binpath, scratch = os.path.abspath(sys.argv[1]), os.path.realpath(sys.argv[2])
shutil.rmtree(scratch, ignore_errors=True)
os.makedirs(scratch, exist_ok=True)
ROWS, COLS = 30, 100

DOC = """# Terminals \u26a0\ufe0f disagree \u2764\ufe0f

A paragraph with a text emoji \u26a0\ufe0f, a heart \u2764\ufe0f, a keycap 1\ufe0f\u20e3, a family \U0001f468\u200d\U0001f469\u200d\U0001f467, a flag
\U0001f1e9\U0001f1ea, a skin tone \U0001f44d\U0001f3fd, Devanagari \u0915\u093f \u0928\u092e\u0938\u094d\u0924\u0947, halfwidth \uff76\uff9e, an arrow \u2192 and a
triangle \u25b8, a Nerd Font glyph \ue0b0 \uf115 and newer emoji \U0001faa8 \U0001fae8, then CJK \u4e2d\u6587 \ud55c\uae00 and some filler so that the
line wraps at the width of the window and goes on for a while.

## A list

- one \u26a0\ufe0f
- two \u2764\ufe0f \U0001f468\u200d\U0001f469\u200d\U0001f467
- three \uff76\uff9e \u0915\u093f

| name | note |
|------|------|
| warn \u26a0\ufe0f | text emoji |
| heart \u2764\ufe0f | text emoji |
| family \U0001f468\u200d\U0001f469\u200d\U0001f467 | zwj |

> a quote \u26a0\ufe0f with \u2764\ufe0f

```
code \u26a0\ufe0f \u2764\ufe0f \u2192
```

""" + "\n".join("Line %d of filler with \u26a0\ufe0f and \u2764\ufe0f and \U0001f468\u200d\U0001f469\u200d\U0001f467 and text." % i for i in range(60)) + "\n"

doc_path = os.path.join(scratch, "doc.md")
with open(doc_path, "w", encoding="utf-8") as f:
    f.write(DOC)

# --- the terminals ----------------------------------------------------------------------------

_pyte_width = pyte.screens.wcwidth


def _ambiguous(ch):
    if 0x2500 <= ord(ch) <= 0x259F:
        return False
    return unicodedata.east_asian_width(ch) == "A"


VARIANTS = [
    ("pyte (code points added up, text emoji 1 column)", _pyte_width),
    ("ambiguous-wide", lambda ch: 2 if _ambiguous(ch) else _pyte_width(ch)),
    ("private-wide", lambda ch: 2 if 0xE000 <= ord(ch) <= 0xF8FF else _pyte_width(ch)),
    ("new-emoji-narrow", lambda ch: 1 if 0x1FA70 <= ord(ch) <= 0x1FAFF else _pyte_width(ch)),
    ("astral-narrow", lambda ch: 1 if (0x1F300 <= ord(ch) <= 0x1F64F and _pyte_width(ch) == 2) else _pyte_width(ch)),
    ("jamo-added", lambda ch: 2 if 0x1100 <= ord(ch) <= 0x11FF else _pyte_width(ch)),
    ("regional-wide", lambda ch: 2 if 0x1F1E6 <= ord(ch) <= 0x1F1FF else _pyte_width(ch)),
]


class Screens:
    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.items = []
        for name, width in VARIANTS:
            screen = pyte.Screen(cols, rows)
            self.items.append((name, width, screen, pyte.ByteStream(screen)))

    def feed(self, data):
        for name, width, screen, stream in self.items:
            pyte.screens.wcwidth = width
            try:
                stream.feed(data)
            finally:
                pyte.screens.wcwidth = _pyte_width

    def resize(self, rows, cols):
        self.rows, self.cols = rows, cols
        for name, width, screen, stream in self.items:
            screen.resize(rows, cols)


def cells(screen, rows, cols):
    buf = screen.buffer
    return [[(buf[y][x].data, buf[y][x].fg, buf[y][x].bg, buf[y][x].reverse) for x in range(cols)] for y in range(rows)]


def text(screen, rows, cols):
    buf = screen.buffer
    return ["".join(buf[y][x].data or " " for x in range(cols)) for y in range(rows)]


class Viewer:
    def __init__(self, rows=ROWS, cols=COLS):
        self.rows, self.cols = rows, cols
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        fcntl.fcntl(self.master, fcntl.F_SETFL, fcntl.fcntl(self.master, fcntl.F_GETFL) | os.O_NONBLOCK)
        env = dict(os.environ)
        for key in ("TERM_PROGRAM", "VISUAL", "EDITOR", "NO_COLOR", "COLORTERM"):
            env.pop(key, None)
        env.update(TERM="xterm-256color", COLORTERM="truecolor", PWD=scratch, LANG="C.UTF-8", HOME=scratch,
                   XDG_CONFIG_HOME=os.path.join(scratch, ".config"), XDG_STATE_HOME=os.path.join(scratch, ".state"))
        self.proc = subprocess.Popen([binpath, "--no-watch", doc_path], stdin=slave, stdout=slave, stderr=slave,
                                     cwd=scratch, env=env, start_new_session=True)
        os.close(slave)
        self.raw = bytearray()
        self.fed = 0
        self.screens = Screens(rows, cols)
        self.settle(0.8)

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
            self.raw += chunk

    def take(self):
        data = bytes(self.raw[self.fed:])
        self.fed = len(self.raw)
        return data

    def settle(self, quiet=0.4):
        self.drain(quiet)
        self.screens.feed(self.take())

    def type(self, keys, quiet=0.4):
        try:
            os.write(self.master, keys)
        except (OSError, BlockingIOError):
            pass
        self.settle(quiet)

    def _resize(self, rows, cols):
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGWINCH)
        except OSError:
            pass
        self.rows, self.cols = rows, cols

    def resize(self, rows, cols):
        self._resize(rows, cols)
        self.screens.resize(rows, cols)
        self.settle(0.8)

    def repaint(self):
        """What a from-scratch repaint of the current state gives on each terminal: CTRL-L (the
        loop clears the screen and writes every cell), applied to a new screen. A resize would do
        the same but moves the scroll position."""
        rows, cols = self.rows, self.cols
        try:
            os.write(self.master, b"\x0c")
        except (OSError, BlockingIOError):
            pass
        self.drain(0.8)
        fresh = Screens(rows, cols)
        fresh.feed(self.take())
        return fresh

    def close(self):
        try:
            os.write(self.master, b"q")
        except OSError:
            pass
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


failures = []
checks = 0


def check(m, label):
    global checks
    rows, cols = m.rows, m.cols
    shown = {name: (cells(s, rows, cols), text(s, rows, cols)) for name, w, s, st in m.screens.items}
    fresh = m.repaint()
    checks += 1
    for name, width, screen, stream in fresh.items:
        got_cells, got_text = shown[name]
        want_cells = cells(screen, rows, cols)
        want_text = text(screen, rows, cols)
        if got_cells != want_cells:
            diff = []
            for y in range(rows):
                if got_text[y] != want_text[y]:
                    diff.append("row %d screen=%r repaint=%r" % (y, got_text[y].rstrip(), want_text[y].rstrip()))
                elif got_cells[y] != want_cells[y]:
                    xs = [x for x in range(cols) if got_cells[y][x] != want_cells[y][x]]
                    diff.append("row %d look differs at cols %s" % (y, xs[:6]))
            failures.append("%s [%s]: %s" % (label, name, " | ".join(diff[:2])))
    m.screens = fresh


m = Viewer()
try:
    check(m, "start")
    steps = [("j", "down"), ("j", "down"), ("j", "down"), ("k", "up"), (" ", "page down"), (" ", "page down"),
             ("b", "page up"), ("G", "end"), ("gg", "top"), ("j", "down"), ("j", "down")]
    for keys, label in steps:
        m.type(keys.encode(), 0.5)
        check(m, label)
    for rows, cols in [(30, 80), (20, 60), (30, 100)]:
        m.resize(rows, cols)
        m.type(b"j")
        check(m, "resized to %dx%d" % (rows, cols))
finally:
    m.close()

for line in failures[:30]:
    print("FAIL " + line)
print("pty_variants: %d checks on %d terminals, %d failed" % (checks, len(VARIANTS), len(failures)))
sys.exit(1 if failures else 0)
