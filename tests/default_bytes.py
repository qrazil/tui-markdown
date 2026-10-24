#!/usr/bin/env python3
"""The default output is the 0.9.0 output, byte for byte: `--cat` and `--dump` for every theme.

    python3 tests/default_bytes.py <tui-markdown-binary> [baseline-binary]

Every theme (dark, light, tokyonight, nightfox, gruvbox-material, plain) at 16, 256 and 24-bit colour, on every fixture,
with and without the switches that change the layout (--zebra, --numbers, --scale, --links), through `--cat` and
`--dump`; the explicit spellings of "off" (`--transparent off`, TUI_MARKDOWN_TRANSPARENT=0, =off) must write the same
bytes as no option. Each output is compared with the same command on `baseline-binary` (a build of the 0.9.0 tag, or
$TUI_MARKDOWN_BASELINE) or, without one, with its SHA-256 in tests/golden/default_0.9.0.txt (PY_BLESS=1 with a
baseline rewrites that file). Nothing needs a terminal.
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
GOLDEN = os.path.join(HERE, "golden", "default_0.9.0.txt")
binary = os.path.abspath(sys.argv[1])
baseline = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("TUI_MARKDOWN_BASELINE", "")
baseline = os.path.abspath(baseline) if baseline else ""
THEMES = ["dark", "light", "tokyonight", "nightfox", "gruvbox-material", "plain"]
DEPTHS = ["16", "256", "24bit"]
SWITCHES = [[], ["--zebra", "--numbers"], ["--scale", "on", "--links", "on", "--zebra", "--numbers"]]
FILES = ["tour.md", "rich.md", "unicode.md", "other.md"]
ENV_KEYS = ("NO_COLOR", "COLORFGBG", "COLORTERM", "TERM_PROGRAM", "KITTY_WINDOW_ID", "WEZTERM_EXECUTABLE",
            "GHOSTTY_RESOURCES_DIR", "LC_TERMINAL", "VTE_VERSION", "WT_SESSION", "KONSOLE_VERSION", "TUI_MARKDOWN_TRANSPARENT")


def run(program, args, extra_env=None):
    env = dict(os.environ)
    for key in ENV_KEYS:
        env.pop(key, None)
    env.update(TERM="xterm-256color", PWD=FIXTURES, GIT_CEILING_DIRECTORIES=HERE)
    env.update(extra_env or {})
    done = subprocess.run([program] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                          cwd=FIXTURES, env=env)
    return done.returncode, done.stdout


def cases():
    for theme in THEMES:
        for depth in DEPTHS:
            for switches in SWITCHES:
                for name in FILES:
                    if switches and name in ("other.md", "unicode.md"):
                        continue
                    for mode in ("--cat", "--dump"):
                        args = [mode, "--width", "60", "--theme", theme, "--colors", depth] + switches + [name]
                        yield " ".join(args), args


golden = {}
if os.path.exists(GOLDEN):
    with open(GOLDEN) as f:
        for line in f:
            digest, _, key = line.rstrip("\n").partition(" ")
            golden[key] = digest
failures = 0
total = 0
blessed = []
for key, args in cases():
    code, out = run(binary, args)
    total += 1
    digest = hashlib.sha256(out).hexdigest()
    if baseline:
        want_code, want = run(baseline, args)
        want_digest = hashlib.sha256(want).hexdigest()
        blessed.append("%s %s" % (want_digest, key))
    else:
        want_code, want_digest = 0, golden.get(key)
    if code != want_code or digest != want_digest:
        failures += 1
        print("FAIL %s: %s (exit %d, want %d)" % (key, digest[:12], code, want_code))
# the spellings of off write the same bytes as nothing
off_failures = 0
for key, args in list(cases())[:: 7]:
    _, plain = run(binary, args)
    for extra_args, extra_env in ((["--transparent", "off"], None), ([], {"TUI_MARKDOWN_TRANSPARENT": "0"}), ([], {"TUI_MARKDOWN_TRANSPARENT": "off"})):
        _, out = run(binary, extra_args + args, extra_env)
        total += 1
        if out != plain:
            off_failures += 1
            print("FAIL off spelling %r %r changes %s" % (extra_args, extra_env, key))
failures += off_failures
if os.environ.get("PY_BLESS") and baseline:
    with open(GOLDEN, "w") as f:
        f.write("\n".join(blessed) + "\n")
    print("note: wrote %s" % GOLDEN)
print("default_bytes: %d checks, %d failed" % (total, failures))
sys.exit(1 if failures else 0)
