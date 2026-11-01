#!/usr/bin/env python3
"""tui-markdown against glow: wall time, peak RSS and output bytes of rendering one markdown file.

    python3 -I bench/render.py <runs> <input-dir> <glow-binary> <tui-markdown-binary> [file ...]

Modes, per file and tool (one line each, `ROW tool mode file runs ms_med ms_p95 rss_kb_med out_bytes`):
  pipe   stdout is a pipe, stdin is /dev/null (what `tool file | less -R` does); width 80, dark theme
  pty    stdout is a pseudo-terminal of 80x24 that is drained and answers background-colour, cursor-position and
         device-attributes queries (what typing `tool file` does), same options. BENCH_MODES=pty,first-frame runs only those.
and, for tui-markdown only, `first-frame`: the interactive viewer on a pty, spawn to the moment the first screenful
has been written (the width calibration is off here: the harness answers the questions of termenv, not those) and 150 ms have passed without more output (that 150 ms is subtracted).
Wall time is from spawn to exit (EOF and wait4), so it includes the start-up of each program. The rss column of
the ROW lines is wait4's ru_maxrss, which a forked child inherits as a floor from the harness: ignore it. BENCH_MODES=rss
measures peak RSS properly (GNU time, `RSS tool file runs median max` lines). glow gets `-s dark -w 80` (no terminal background query) and, in the pipe mode, is run both
as it comes (no colour: its colour profile is read from stdout) and with CLICOLOR_FORCE=1 (`pipe-color`).
"""
import os, pty, select, statistics, subprocess, sys, time, fcntl, termios, struct, resource

def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * 0.95))]

def run_pipe(cmd, env):
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    n = 0
    while True:
        d = os.read(p.stdout.fileno(), 1 << 20)
        if not d:
            break
        n += len(d)
    _, status, ru = os.wait4(p.pid, 0)
    p.returncode = 0
    return (time.perf_counter() - t0) * 1000, ru.ru_maxrss, n

QUERIES = ((b"\x1b]11;?", b"\x1b]11;rgb:0000/0000/0000\x1b\\"), (b"\x1b]10;?", b"\x1b]10;rgb:cccc/cccc/cccc\x1b\\"),
           (b"\x1b[6n", b"\x1b[1;1R"), (b"\x1b[c", b"\x1b[?62;c"))

def answer(master, data):
    """A terminal answers the questions programs ask it (background colour, cursor position, device attributes);
    one that does not makes termenv-based programs wait for their timeout, which is not what a terminal does."""
    for q, a in QUERIES:
        if q in data:
            os.write(master, a * data.count(q))

def run_pty(cmd, env, interactive=False):
    m, s = os.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    def child():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdin=s, stdout=s, stderr=s, env=env, preexec_fn=child, close_fds=True)
    os.close(s)
    n = 0
    last = t0
    first = None
    while True:
        r, _, _ = select.select([m], [], [], 0.15 if interactive else 30)
        if not r:
            if interactive and n > 0:
                break          # quiet for 150 ms after output: the first frame is on screen
            if not interactive:
                break
            continue
        try:
            d = os.read(m, 1 << 20)
        except OSError:
            break
        if not d:
            break
        n += len(d)
        last = time.perf_counter()
        answer(m, d)
    if interactive:
        elapsed = (last - t0) * 1000
        os.write(m, b"q")
        try:
            while select.select([m], [], [], 1.0)[0]:
                if not os.read(m, 65536):
                    break
        except OSError:
            pass
    else:
        elapsed = (time.perf_counter() - t0) * 1000
    try:
        _, status, ru = os.wait4(p.pid, os.WNOHANG)
        if _ == 0:
            p.kill()
            _, status, ru = os.wait4(p.pid, 0)
    except ChildProcessError:
        ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    os.close(m)
    return elapsed, ru.ru_maxrss, n

def peak_rss_kb(cmd, env):
    """Peak RSS of one run, from GNU time (a child of a big process inherits that process's high-water mark through
    fork, so wait4's ru_maxrss of the main runs is floored at the harness's own size and is not used)."""
    import tempfile
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        subprocess.run(["/usr/bin/time", "-f", "%M", "-o", path] + cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, env=env)
        return int(open(path).read().split()[-1])
    finally:
        os.unlink(path)

def main_rss(runs, indir, glow, tmd, files):
    base = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor", LANG="C.UTF-8")
    base.pop("NO_COLOR", None)
    for f in files:
        path = os.path.join(indir, f)
        for tool, cmd in (("glow", [glow, "-s", "dark", "-w", "80", path]), ("tui-markdown", [tmd, "--cat", "--theme", "dark", "--width", "80", path])):
            xs = [peak_rss_kb(cmd, base) for _ in range(runs)]
            print("RSS %s %s %d %d %d" % (tool, f, runs, statistics.median(xs), max(xs)))
            sys.stdout.flush()

def main():
    runs, indir, glow, tmd = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
    modes = os.environ.get("BENCH_MODES", "").split(",") if os.environ.get("BENCH_MODES") else None
    files = sys.argv[5:] or sorted(f for f in os.listdir(indir) if f.endswith(".md"))
    if modes == ["rss"]:
        main_rss(runs, indir, glow, tmd, files)
        return
    base = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor", LANG="C.UTF-8")
    base.pop("NO_COLOR", None)
    for f in files:
        path = os.path.join(indir, f)
        n = runs if os.path.getsize(path) < 200000 else max(10, runs // 3)
        cases = [
            ("glow", "pipe", [glow, "-s", "dark", "-w", "80", path], base, run_pipe),
            ("glow", "pipe-color", [glow, "-s", "dark", "-w", "80", path], dict(base, CLICOLOR_FORCE="1"), run_pipe),
            ("tui-markdown", "pipe", [tmd, "--cat", "--theme", "dark", "--width", "80", path], base, run_pipe),
            ("glow", "pty", [glow, "-s", "dark", "-w", "80", path], base, run_pty),
            ("tui-markdown", "pty", [tmd, "--cat", "--theme", "dark", "--width", "80", path], base, run_pty),
            ("tui-markdown", "first-frame", [tmd, "--theme", "dark", "--no-watch", path], dict(base, TUI_WIDTH_PROBE="off"), lambda c, e: run_pty(c, e, True)),
        ]
        for tool, mode, cmd, env, fn in cases:
            if modes and mode not in modes:
                continue
            fn(cmd, env)  # warm-up
            ms, rss, out = [], [], 0
            for _ in range(n):
                a, b, c = fn(cmd, env)
                ms.append(a); rss.append(b); out = c
            print("ROW %s %s %s %d %.1f %.1f %d %d" % (tool, mode, f, n, statistics.median(ms), p95(ms), statistics.median(rss), out))
            sys.stdout.flush()

if __name__ == "__main__":
    main()
