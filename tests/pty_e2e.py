#!/usr/bin/env python3
"""Drive the compiled `tui-markdown` under a real pty.

    python3 tests/pty_e2e.py <tui-markdown-binary> <fixtures-dir> <scratch-dir>

Every `ok`/`FAIL` line is one check; the exit code is the number of failures.
The screen is read through a small terminal emulator (cursor addressing,
erase, wide and combining characters, OSC 52 captured) so a check asks what is
ON the screen, not what bytes the diff renderer chose to send.
"""
import base64
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

failures = 0
checks = 0


def ok(name):
    global checks
    checks += 1
    print("ok   " + name)


def fail(name, detail):
    global failures, checks
    checks += 1
    failures += 1
    print("FAIL " + name + ": " + detail)


def check(name, condition, detail=""):
    if condition:
        ok(name)
    else:
        fail(name, detail)


class Screen:
    def __init__(self, rows=24, cols=80):
        self.resize(rows, cols)
        self.clipboard = []
        self.cur_link = None
        self.linkmap = {}
        self.scaled = []
        self.leave_seen = False
        self.pending = b""

    def resize(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.cells = [[" "] * cols for _ in range(rows)]
        self.row = 0
        self.col = 0

    def put(self, ch):
        if unicodedata.combining(ch) or ch in "‍️":
            c = self.col - 1
            while c > 0 and self.cells[self.row][c] == "":
                c -= 1
            if 0 <= c < self.cols:
                self.cells[self.row][c] += ch
            return
        width = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if 0 <= self.row < self.rows and 0 <= self.col < self.cols:
            self.cells[self.row][self.col] = ch
            if self.cur_link:
                self.linkmap[(self.row, self.col)] = self.cur_link
            if width == 2 and self.col + 1 < self.cols:
                self.cells[self.row][self.col + 1] = ""
        self.col += width

    def feed(self, data):
        text = (self.pending + data).decode("utf-8", errors="replace")
        self.pending = b""
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch == "\x1b":
                if i + 1 >= n:
                    self.pending = text[i:].encode()
                    return
                nxt = text[i + 1]
                if nxt == "]":
                    j = i + 2
                    while j < n and text[j] != "\x07" and not (text[j] == "\x1b" and j + 1 < n and text[j + 1] == "\\"):
                        j += 1
                    if j >= n:
                        self.pending = text[i:].encode()
                        return
                    self.osc(text[i + 2 : j])
                    i = j + (1 if text[j] == "\x07" else 2)
                    continue
                if nxt != "[":
                    i += 2
                    continue
                j = i + 2
                while j < n and text[j] in "0123456789;?<>= !\"#$%&'()*+,-./":
                    j += 1
                if j >= n:
                    self.pending = text[i:].encode()
                    return
                self.csi(text[i + 2 : j], text[j])
                i = j + 1
                continue
            if ch == "\r":
                self.col = 0
            elif ch == "\n":
                self.row = min(self.row + 1, self.rows - 1)
            elif ch >= " ":
                self.put(ch)
            i += 1

    def osc(self, body):
        if body.startswith("8;"):
            uri = body.split(";", 2)[2] if body.count(";") >= 2 else ""
            self.cur_link = uri or None
            return
        if body.startswith("66;"):
            params, _, text = body[3:].partition(";")
            self.scaled.append((self.row, self.col, params, text))
            return
        if body.startswith("52;c;"):
            try:
                self.clipboard.append(base64.b64decode(body[5:]).decode("utf-8"))
            except Exception:
                self.clipboard.append("<bad base64>")

    def csi(self, params, final):
        if params.startswith("?"):
            if final == "l" and "1049" in params:
                self.leave_seen = True
            return
        nums = [int(x) if x.isdigit() else 0 for x in params.split(";")] if params else []
        first = nums[0] if nums and nums[0] > 0 else 1
        if final in "Hf":
            self.row = (nums[0] if len(nums) > 0 and nums[0] > 0 else 1) - 1
            self.col = (nums[1] if len(nums) > 1 and nums[1] > 0 else 1) - 1
        elif final == "C":
            self.col += first
        elif final == "D":
            self.col = max(0, self.col - first)
        elif final == "A":
            self.row = max(0, self.row - first)
        elif final == "B":
            self.row = min(self.rows - 1, self.row + first)
        elif final == "G":
            self.col = first - 1
        elif final == "K":
            mode = nums[0] if nums else 0
            if 0 <= self.row < self.rows:
                lo, hi = (self.col, self.cols) if mode == 0 else ((0, self.col + 1) if mode == 1 else (0, self.cols))
                for c in range(max(lo, 0), min(hi, self.cols)):
                    self.cells[self.row][c] = " "
        elif final == "J":
            mode = nums[0] if nums else 0
            if mode in (2, 3):
                self.cells = [[" "] * self.cols for _ in range(self.rows)]
            elif mode == 0:
                for r in range(self.row, self.rows):
                    for c in range(self.cols):
                        if r > self.row or c >= self.col:
                            self.cells[r][c] = " "

    def lines(self):
        return ["".join(row).rstrip() for row in self.cells]

    def text(self):
        return "\n".join(self.lines())


KEYS = {
    "ctrl-d": "\x04", "ctrl-u": "\x15", "ctrl-f": "\x06", "ctrl-b": "\x02",
    "ctrl-o": "\x0f", "ctrl-c": "\x03", "esc": "\x1b", "enter": "\r",
    "tab": "\t", "backtab": "\x1b[Z", "backspace": "\x7f", "space": " ",
    "down": "\x1b[B", "up": "\x1b[A", "pgdn": "\x1b[6~", "pgup": "\x1b[5~",
    "home": "\x1b[H", "end": "\x1b[F",
}


class Session:
    def __init__(self, binary, args, env=None, cwd=None, stdin_data=None, rows=24, cols=80):
        self.screen = Screen(rows, cols)
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        e = dict(os.environ)
        e["TERM"] = "xterm-256color"
        for k in ("NO_COLOR", "COLORFGBG"):
            e.pop(k, None)
        if env:
            e.update(env)
        stdin = slave
        if stdin_data is not None:
            stdin = subprocess.PIPE
        self.proc = subprocess.Popen([binary] + args, stdin=stdin, stdout=slave, stderr=slave, cwd=cwd, env=e)
        os.close(slave)
        if stdin_data is not None:
            self.proc.stdin.write(stdin_data.encode())
            self.proc.stdin.close()
        self.drain(0.4)

    def drain(self, timeout=0.3):
        got = False
        while True:
            r, _, _ = select.select([self.master], [], [], timeout)
            if not r:
                break
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                break
            if not chunk:
                break
            got = True
            self.screen.feed(chunk)
            timeout = 0.08
        return got

    def text(self):
        return self.screen.text()

    def send(self, keys):
        """`keys` is a string of literal characters; named keys go in {braces}: {ctrl-d}."""
        out = ""
        i = 0
        while i < len(keys):
            if keys[i] == "{":
                j = keys.index("}", i)
                out += KEYS[keys[i + 1 : j]]
                i = j + 1
            else:
                out += keys[i]
                i += 1
        os.write(self.master, out.encode())
        self.drain(0.25)

    def mouse(self, kind, col, row, mods=0):
        """An SGR (1006) report: kind is down, up, drag, move, wheel-up or wheel-down; col and row are 1-based."""
        code = {"down": 0, "up": 0, "drag": 32, "move": 35, "wheel-up": 64, "wheel-down": 65}[kind] + mods
        final = "m" if kind == "up" else "M"
        os.write(self.master, ("\x1b[<%d;%d;%d%s" % (code, col, row, final)).encode())
        self.drain(0.25)

    def click(self, col, row):
        self.mouse("down", col, row)
        self.mouse("up", col, row)

    def wait_for(self, needle, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if needle in self.text():
                return True
            self.drain(0.15)
        return needle in self.text()

    def resize(self, rows, cols):
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        os.kill(self.proc.pid, signal.SIGWINCH)
        self.screen.resize(rows, cols)
        self.wait_for("\u0000", 0.6)
        self.drain(0.5)

    def status(self):
        return self.screen.lines()[self.screen.rows - 1]

    def head(self):
        return self.screen.lines()[0]

    def top(self):
        """The first row of the document on screen (row 0 is the header)."""
        return self.screen.lines()[1]

    def finish(self, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                break
            self.drain(0.1)
        code = self.proc.poll()
        if code is None:
            self.proc.kill()
            self.proc.wait()
            code = -9
        self.drain(0.1)
        try:
            os.close(self.master)
        except OSError:
            pass
        return code


def main():
    binary, fixtures, scratch = sys.argv[1:4]
    binary = os.path.abspath(binary)
    fixtures = os.path.abspath(fixtures)
    shutil.rmtree(scratch, ignore_errors=True)
    os.makedirs(scratch)
    scratch = os.path.abspath(scratch)
    tour = "tour.md"
    other = "other.md"
    os.chdir(fixtures)

    # --- start up, scroll, jump ---------------------------------------------
    s = Session(binary, [tour])
    check("startup: the title is in the banner", "The Tour" in s.screen.lines()[2], s.text())
    check("startup: the header has the outline button and theme", "☰" in s.head() and "dark" in s.head(), s.head())
    check("startup: status names the file", "tour.md" in s.status() and "0%" in s.status(), s.status())
    s.send("j")
    check("j scrolls one line", "The Tour" in s.top(), s.text())
    s.send("k")
    check("k scrolls back", "The Tour" in s.screen.lines()[2])
    s.send("3j")
    check("3j scrolls three", "\u2550" in s.top(), s.top())
    s.send("gg")
    check("gg goes to the top", "The Tour" in s.screen.lines()[2])
    s.send("G")
    check("G goes to the bottom", "final paragraph" in s.text() and "100%" in s.status(), s.status())
    s.send("gg")
    s.send("{ctrl-d}")
    check("Ctrl-d moves half a page", "The Tour" not in s.screen.lines()[2], s.top())
    s.send("{ctrl-u}")
    check("Ctrl-u moves back", "The Tour" in s.screen.lines()[2])
    s.send("{ctrl-f}")
    pos_f = s.top()
    s.send("{ctrl-b}")
    check("Ctrl-f / Ctrl-b page", pos_f != s.top() and "The Tour" in s.screen.lines()[2], pos_f)
    s.send("{pgdn}")
    check("PgDn pages", "The Tour" not in s.screen.lines()[2])
    s.send("{home}")
    s.send("9G")
    check("9G goes to row 9", s.top().startswith(" ▌ First Chapter"), s.text())
    s.send("gg")
    s.send("]]")
    check("]] jumps to the next heading", s.top().startswith(" ▌ First Chapter"), s.top())
    s.send("]]")
    check("]] again", s.top().startswith(" ▌ Second Chapter"), s.top())
    s.send("[[")
    check("[[ goes back a heading", s.top().startswith(" ▌ First Chapter"), s.top())
    s.send("gg2]]")
    check("2]] skips one heading", s.top().startswith(" ▌ Second Chapter"), s.top())
    s.send("q")
    code = s.finish()
    check("q quits with status 0", code == 0, str(code))
    check("quit restores the screen", s.screen.leave_seen)

    # --- search ---------------------------------------------------------------
    s = Session(binary, [tour])
    s.send("/fox")
    check("/ shows the prompt", s.status().startswith(" /fox"), s.status())
    s.send("{backspace}x{backspace}")
    check("backspace edits the query", s.status().startswith(" /fo"), s.status())
    s.send("z{enter}")
    check("a search with no hit says so", "not found" in s.status(), s.status())
    s.send("/QUICK{enter}")
    check("an uppercase pattern is case sensitive", "not found" in s.status(), s.status())
    s.send("/quick{enter}")
    check("smart case finds a lower-case pattern", "1 match" in s.status() or "/quick 1/1" in s.status(), s.status())
    s.send("/the{enter}")
    first = s.status()
    s.send("n")
    check("n moves to the next hit", "/the 2/" in s.status(), s.status())
    s.send("N")
    check("N moves to the previous hit", "/the 1/" in s.status(), s.status())
    s.send("N")
    check("N wraps around", "BOTTOM" in s.status(), s.status())
    s.send("{esc}")
    check("Esc clears the search", "/the" not in s.status(), s.status())
    s.send("/zzzz{esc}")
    check("Esc cancels typing", "/zzzz" not in s.status())
    s.send("q")
    s.finish()

    # --- outline ----------------------------------------------------------------
    s = Session(binary, [tour])
    s.send("o")
    t = s.text()
    check("o opens the outline", "Outline" in t and "The Tour" in t and "Second Chapter" in t and "Deep Heading" in t, t)
    s.send("jj")
    s.send("{enter}")
    check("Enter in the outline jumps", s.top().startswith(" ▌ Second Chapter") or "Second Chapter" in s.top(), s.top())
    check("the outline closes", "Outline" not in s.text())
    s.send("o")
    s.send("{esc}")
    check("Esc closes the outline", "Outline" not in s.text())
    s.send("q")
    s.finish()

    # --- links, back stack, OSC 52 ----------------------------------------------
    s = Session(binary, [tour])
    s.send("{tab}")
    check("Tab focuses the first link", "#second-chapter" in s.status(), s.status())
    s.send("{enter}")
    check("Enter follows an anchor link", s.top().startswith(" ▌ Second Chapter"), s.top())
    s.send("{ctrl-o}")
    check("Ctrl-o goes back", "The Tour" in s.screen.lines()[2], s.text())
    s.send("{tab}")
    check("Tab again reaches the sibling file link", "other.md#deep-end" in s.status(), s.status())
    s.send("{enter}")
    check("Enter follows a link to another file", s.wait_for("Deep End") and "Other File" not in s.top(), s.text())
    check("the status names the new file", "other.md" in s.status() or "other.md" in s.text(), s.status())
    s.send("{backspace}")
    check("Backspace returns to the first file", s.wait_for("The Tour") and "other.md#deep-end" in s.status(), s.status())
    s.send("{tab}")
    check("Tab reaches the external link", "https://example.com/docs?a=1&b=2" in s.status(), s.status())
    s.send("{enter}")
    check("an external link is copied through OSC 52", s.screen.clipboard[-1:] == ["https://example.com/docs?a=1&b=2"], str(s.screen.clipboard))
    check("an external link is not opened", s.proc.poll() is None and "The Tour" in s.text())
    s.send("{backtab}")
    check("Shift-Tab goes to the previous link", "other.md#deep-end" in s.status(), s.status())
    s.send("y")
    check("y yanks the focused link", s.screen.clipboard[-1] == "other.md#deep-end", str(s.screen.clipboard))
    s.send("{esc}")
    check("Esc drops link focus", "other.md#deep-end" not in s.status(), s.status())
    s.send("y")
    check("y yanks the block at the top", s.screen.clipboard[-1] == "The Tour", str(s.screen.clipboard))
    s.send("q")
    s.finish()

    # --- help, reload, files ------------------------------------------------------
    s = Session(binary, [tour, other])
    check("several files: status shows the position", "[1/2]" in s.status(), s.status())
    s.send("?")
    t = s.text()
    check("? shows the key help", "Keys" in t and "next / previous heading" in t, t)
    s.send("x")
    check("any key closes help", "Keys" not in s.text())
    s.send(">")
    check("> opens the next file", s.wait_for("Other File") and "[2/2]" in s.status(), s.status())
    s.send(">")
    check("> at the last file says so", "no more files" in s.status(), s.status())
    s.send("<")
    check("< returns", s.wait_for("The Tour") and "[1/2]" in s.status(), s.status())
    s.send("r")
    check("r reloads", "reloaded" in s.status(), s.status())
    s.send("q")
    s.finish()

    # --- auto reload ----------------------------------------------------------------
    live = os.path.join(scratch, "live.md")
    with open(live, "w") as f:
        f.write("# Live\n\nfirst version\n")
    s = Session(binary, [live])
    check("auto-reload: first version", "first version" in s.text())
    time.sleep(0.05)
    with open(live, "w") as f:
        f.write("# Live\n\nsecond version, now longer\n")
    check("auto-reload: change appears with no key", s.wait_for("second version", 3.0), s.text())
    s.send("q")
    s.finish()
    s = Session(binary, ["--no-watch", live])
    with open(live, "w") as f:
        f.write("# Live\n\nthird version\n")
    time.sleep(1.2)
    s.drain(0.3)
    check("--no-watch: no reload without r", "third version" not in s.text() and "second version" in s.text(), s.text())
    s.send("r")
    check("--no-watch: r still reloads", "third version" in s.text(), s.text())
    s.send("q")
    s.finish()

    # --- resize reflow ----------------------------------------------------------------
    s = Session(binary, [tour], rows=24, cols=100)
    wide = s.text()
    s.send("]]")
    pos = s.top()
    s.resize(24, 40)
    narrow = s.text()
    longest = max(len(l) for l in s.screen.lines())
    check("resize: the text reflows to the new width", longest <= 40, str(longest))
    check("resize: the place is kept", "First Chapter" in narrow, narrow)
    s.resize(24, 100)
    check("resize: back to wide", "First Chapter" in s.text())
    s.send("q")
    s.finish()

    # --- unicode ------------------------------------------------------------------------
    s = Session(binary, [tour], cols=60)
    s.send("/日本語{enter}")
    s.send("{esc}")
    t = s.text()
    check("CJK text is shown", "日本語" in t, t)
    check("emoji and combining mark stay whole", "🎉" in t and "é" in t.replace("é", "é"), t)
    wide_ok = all(len(l) <= 60 for l in s.screen.lines())
    check("wide characters never overflow", wide_ok, t)
    s.send("q")
    s.finish()

    # --- standard input ------------------------------------------------------------------
    data = open(tour).read()
    s = Session(binary, [], stdin_data=data)
    check("stdin: the document is shown", "The Tour" in s.text(), s.text())
    check("stdin: status says <stdin>", "<stdin>" in s.status(), s.status())
    s.send("]]")
    check("stdin: keys work from the terminal", s.top().startswith(" ▌ First Chapter"), s.top())
    s.send("r")
    check("stdin: reload is refused", "cannot be reloaded" in s.status(), s.status())
    s.send("q")
    check("stdin: q quits", s.finish() == 0)

    # --- themes ------------------------------------------------------------------------------
    for theme in ("light", "plain"):
        s = Session(binary, ["--theme", theme, tour])
        check("theme %s runs" % theme, "The Tour" in s.text())
        s.send("q")
        s.finish()

    # --- counts and stray keys -----------------------------------------------------------------
    s = Session(binary, [tour])
    s.send("12j")
    a = s.top()
    s.send("{esc}")
    s.send("zzz")
    s.send("gx")
    s.send("{ctrl-d}")
    check("unknown keys do nothing harmful", s.proc.poll() is None and s.top() != a)
    s.send("0")
    s.send("{ctrl-c}")
    check("Ctrl-c quits", s.finish() == 0)

    # --- the mouse, the sidebar, the header ---------------------------------------------
    s = Session(binary, [tour])
    before = s.top()
    s.mouse("wheel-down", 20, 10)
    check("mouse: the wheel scrolls three rows", s.top() != before and "\u2550" in s.top(), s.top())
    s.mouse("wheel-up", 20, 10)
    check("mouse: the wheel scrolls back", "The Tour" in s.screen.lines()[2])
    s.send("b")
    check("b opens the outline sidebar", "Second Chapter" in s.text() and "Deep Heading" in s.text() and "\u2502" in s.screen.lines()[3], s.text())
    s.click(5, 4)
    check("mouse: a click in the sidebar jumps to the heading", "Second Chapter" in s.top(), s.top())
    s.send("b")
    check("b closes the sidebar", "\u25b8 " not in s.text())
    s.click(2, 1)
    check("mouse: the outline button in the header opens it", "\u25b8 " in s.text(), s.text())
    s.click(2, 1)
    check("mouse: and closes it", "\u25b8 " not in s.text())
    dark = s.head()
    s.click(78, 1)
    check("mouse: the theme button changes the theme", "dark" in dark and "light" in s.head(), s.head())
    s.send("t")
    check("t changes the theme too", "tokyonight" in s.head(), s.head())
    s.send("gg")
    # a click on the in-document link follows it
    row = None
    for i, line in enumerate(s.screen.lines()):
        if "link to the second chapter" in line:
            row = i
            col = line.index("link to the second chapter")
    check("the link is on screen", row is not None, s.text())
    s.mouse("move", col + 3, row + 1)
    check("mouse: hovering a link shows its target in the status line", "#second-chapter" in s.status(), s.status())
    s.click(col + 3, row + 1)
    check("mouse: clicking a link follows it", s.top().startswith(" \u258c Second Chapter"), s.top())
    s.send("{ctrl-o}")
    s.mouse("down", 80, 5)
    s.mouse("drag", 80, 15)
    s.mouse("up", 80, 15)
    check("mouse: dragging the scrollbar scrolls", "The Tour" not in s.screen.lines()[2] and "%" in s.status(), s.status())
    s.send("q")
    s.finish()

    # --- links (OSC 8) and scaled headings (OSC 66) -------------------------------------
    s = Session(binary, ["--links", "on", "--scale", "on", tour])
    urls = set(s.screen.linkmap.values())
    check("OSC 8: the external link is marked", "https://example.com/docs?a=1&b=2" in urls, str(urls))
    check("OSC 8: a relative link is not", not any("other.md" in u or u.startswith("#") for u in urls), str(urls))
    check("OSC 66: the H1 is written as scaled text", any(t == "The Tour" and "s=2" in params for (_, _, params, t) in s.screen.scaled), str(s.screen.scaled))
    s.send("q")
    s.finish()
    s = Session(binary, [tour], env={"TERM_PROGRAM": "Apple_Terminal"})
    check("no OSC 8 or OSC 66 on Terminal.app", not s.screen.linkmap and not s.screen.scaled)
    s.send("q")
    s.finish()

    # --- a missing file -------------------------------------------------------------------------
    s = Session(binary, ["nope.md"])
    code = s.finish()
    check("a missing file is an error", code == 1 and "nope.md" in s.text(), "%s %s" % (code, s.text()))

    print()
    print("%d checks, %d failed" % (checks, failures))
    return failures


if __name__ == "__main__":
    sys.exit(min(main(), 255))
