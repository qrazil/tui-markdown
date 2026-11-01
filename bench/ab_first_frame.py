#!/usr/bin/env python3
"""Interleaved first-frame A/B of two tui-markdown binaries.   python3 -I bench/ab_first_frame.py <runs> <file> <binary-a> <binary-b>"""
import os, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render

runs, path, a, b = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor", LANG="C.UTF-8", TUI_WIDTH_PROBE="off")
env.pop("NO_COLOR", None)
cmds = {"a": [a, "--theme", "dark", "--no-watch", path], "b": [b, "--theme", "dark", "--no-watch", path]}
res = {"a": [], "b": []}
render.run_pty(cmds["a"], env, True); render.run_pty(cmds["b"], env, True)
for _ in range(runs):
    for k in ("a", "b"):
        res[k].append(render.run_pty(cmds[k], env, True)[0])
for k in ("a", "b"):
    xs = sorted(res[k])
    print("FIRSTFRAME %s %s runs=%d median_ms=%.1f p95_ms=%.1f" % (k, os.path.basename(path), runs, statistics.median(xs), xs[min(len(xs) - 1, int(len(xs) * 0.95))]))
