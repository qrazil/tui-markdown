#!/usr/bin/env bash
# Every check for this repo.
#
#   M31_ROOT=/path/to/m31 LANGC=/path/to/m31c bash tests/test.sh
#   BLESS=1 ... bash tests/test.sh        rewrite tests/golden/ from the program
#
# What is checked, and against what:
#
#   house style    m31c fmt --check, m31c lint
#   viewer         tests/t_viewer.m31, the state machine with no terminal
#   editing        tests/t_edit.m31 (buffer, undo, list/table/pair assists) and
#                  tests/t_editor.m31 (panes, typing, mouse, find, palette, save)
#   oracle         what the layout shows against the text of term-markdown's
#                  own HTML, for tests/oracle_cases.txt, at two widths
#   goldens        `--cat --theme plain` (and one styled) output, byte for byte
#   --cat          NO_COLOR, --width, stdin, several files, the exit codes
#   pty            tests/pty_e2e.py drives the real binary under a pty
#
# The suite runs on bash 3.2 and BSD tools (macOS): no associative arrays, no
# `mapfile`, no GNU-only flags. Where a BSD tool differs (`wc` pads its
# numbers) tests/shims has a stand-in that goes first on PATH.
set -uo pipefail
cd "$(dirname "$0")/.."

if [ -z "${M31_ROOT:-}" ]; then
    echo "M31_ROOT is not set -- point it at a checkout of github.com/qrazil/m31" \
         "(or an extracted release's runtime SDK) matching the m31c version" \
         "you're building with." >&2
    exit 1
fi
if [ ! -f "$M31_ROOT/config.sh" ] || [ ! -d "$M31_ROOT/runtime" ]; then
    echo "M31_ROOT=$M31_ROOT does not look like an m31 checkout" \
         "(expected $M31_ROOT/config.sh and $M31_ROOT/runtime/)" >&2
    exit 1
fi
. "$M31_ROOT/runtime/arch.sh"

LANGC=${LANGC:-./m31c}
export LANGC M31_ROOT
# The program reads the environment to decide colour depth, links and scaled
# text (TERM, COLORTERM, TERM_PROGRAM, KITTY_WINDOW_ID, ...). A golden must not
# depend on the machine it is made on, so every such variable is cleared here
# and TERM is pinned; a test that wants a capability asks for it with a flag.
for hostile in COLORTERM TERM_PROGRAM TERM_PROGRAM_VERSION KITTY_WINDOW_ID WEZTERM_EXECUTABLE GHOSTTY_RESOURCES_DIR LC_TERMINAL VTE_VERSION WT_SESSION KONSOLE_VERSION NO_COLOR COLORFGBG COLUMNS LINES; do
    unset "$hostile"
done
export TERM=xterm-256color
ROOT=$(pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
pass=0
fail=0

if [ "$(echo x | wc -l)" != "1" ]; then
    PATH="$ROOT/tests/shims:$PATH"
    export PATH
fi

note() { printf '\033[32mok\033[0m   %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '\033[31mFAIL\033[0m %s\n' "$1"; shift; printf '%s\n' "$@" | sed 's/^/     /'; fail=$((fail + 1)); }

# build NAME: compile tests/NAME.m31 into $WORK/NAME
build() {
    local name=$1
    if ! "$LANGC" --emit-c "tests/$name.m31" -o "$WORK/$name.c" 2>"$WORK/$name.diag"; then
        bad "compile $name" "$(head -5 "$WORK/$name.diag")"
        return 1
    fi
    if ! cc -O2 -w -I "$M31_ROOT/runtime" -pthread -o "$WORK/$name" "$WORK/$name.c" \
           "$M31_ROOT/runtime/rt.c" "$M31_ROOT/runtime/scheduler.c" "$M31_ROOT/$RT_REACTOR_C" "$M31_ROOT/$RT_CTX_ASM" \
           2>"$WORK/$name.cc"; then
        bad "cc $name" "$(head -5 "$WORK/$name.cc")"
        return 1
    fi
    return 0
}

# tally LABEL FILE: FILE ends in "N passed, M failed" (or "N checks, M failed");
# add its counts, show its failures.
tally() {
    local label=$1 file=$2 last count failed
    last=$(tail -n 1 "$file")
    count=$(printf '%s\n' "$last" | sed -E -n 's/^([0-9]+) (passed|checks), ([0-9]+) failed.*$/\1/p')
    failed=$(printf '%s\n' "$last" | sed -E -n 's/^([0-9]+) (passed|checks), ([0-9]+) failed.*$/\3/p')
    if [ -z "$count" ]; then
        bad "$label: no summary line" "$(tail -n 5 "$file")"
        return
    fi
    if [ "$failed" = "0" ]; then
        pass=$((pass + count))
        printf '\033[32mok\033[0m   %s: %s checks\n' "$label" "$count"
    else
        pass=$((pass + count))
        fail=$((fail + failed))
        printf '\033[31mFAIL\033[0m %s: %s failed\n' "$label" "$failed"
        grep '^FAIL' "$file" | head -20 | sed 's/^/     /'
    fi
}

# --- house style -----------------------------------------------------------------

if out=$("$LANGC" fmt --check -r . 2>&1); then
    note "source is formatted"
else
    bad "source is not formatted (run: m31c fmt -r .)" "$out"
fi

if out=$("$LANGC" lint . 2>&1) && printf '%s\n' "$out" | grep -q '^0 finding(s)'; then
    note "lint: no findings"
else
    bad "lint" "$(printf '%s\n' "$out" | head -10)"
fi

# --- the program -------------------------------------------------------------------

BIN="$WORK/tui-markdown"
if ! bash scripts/build.sh -o "$BIN" >"$WORK/build.log" 2>&1; then
    bad "build tui-markdown" "$(tail -n 8 "$WORK/build.log")"
    echo
    printf '\033[31m%d of %d checks FAILED\033[0m\n' "$fail" "$((pass + fail))"
    exit 1
fi
note "tui-markdown builds"

# --- the viewer's state machine ------------------------------------------------------

if build t_viewer; then
    "$WORK/t_viewer" >"$WORK/t_viewer.out" 2>&1
    tally "viewer state machine" "$WORK/t_viewer.out"
fi

# --- editing: the buffer, the markdown assists, and the editor in the viewer ----------

if build t_edit; then
    "$WORK/t_edit" >"$WORK/t_edit.out" 2>&1
    tally "editing core and markdown assists" "$WORK/t_edit.out"
fi
if build t_editor; then
    "$WORK/t_editor" >"$WORK/t_editor.out" 2>&1
    tally "editor state machine" "$WORK/t_editor.out"
fi

# --- visible text against term-markdown's HTML ---------------------------------------

if build t_oracle; then
    python3 tests/oracle.py "$WORK/t_oracle" tests/oracle_cases.txt >"$WORK/oracle.out" 2>&1
    tally "text oracle (term-markdown HTML)" "$WORK/oracle.out"
fi

# --- layout goldens ----------------------------------------------------------------------
#
# One line per golden: NAME FIXTURE WIDTH. `--cat --theme plain` is the layout
# with no colour, so the file is the layout. NAME-dark is the same with the
# styles as escape sequences.

goldens="tour-16 tour.md 16
tour-20 tour.md 20
tour-40 tour.md 40
tour-80 tour.md 80
other-40 other.md 40
unicode-12 unicode.md 12
unicode-20 unicode.md 20
unicode-40 unicode.md 40
rich-30 rich.md 30
rich-80 rich.md 80"

mkdir -p tests/golden
golden_count=0
golden_bad=0
while read -r name fixture width; do
    golden_count=$((golden_count + 1))
    got="$WORK/golden-$name.txt"
    (cd tests/fixtures && "$BIN" --cat --theme plain --width "$width" "$fixture") >"$got" 2>"$WORK/golden.err"
    if [ -n "${BLESS:-}" ]; then
        cp "$got" "tests/golden/$name.txt"
    elif ! cmp -s "$got" "tests/golden/$name.txt"; then
        golden_bad=$((golden_bad + 1))
        bad "golden $name" "$(diff "tests/golden/$name.txt" "$got" | head -10)"
    fi
done <<EOF2
$goldens
EOF2

# The styled one: dark theme, 256 colours, no NO_COLOR.
got="$WORK/golden-tour-dark.txt"
(cd tests/fixtures && env -u NO_COLOR TERM=xterm-256color "$BIN" --cat --theme dark --colors 256 --width 40 tour.md) >"$got" 2>/dev/null
golden_count=$((golden_count + 1))
if [ -n "${BLESS:-}" ]; then
    cp "$got" tests/golden/tour-dark-40.txt
elif ! cmp -s "$got" tests/golden/tour-dark-40.txt; then
    golden_bad=$((golden_bad + 1))
    bad "golden tour-dark-40" "$(diff tests/golden/tour-dark-40.txt "$got" | head -6 | cat -v)"
fi
if [ $golden_bad -eq 0 ]; then
    note "layout goldens: $golden_count files match${BLESS:+ (rewritten)}"
fi

# The themed pages: `--dump` (what the screen shows, theme background and
# margins included) per theme, at 80 columns. These are also the files in
# docs/screenshots, so the screenshots can never go stale.
mkdir -p docs/screenshots
shot_count=0
shot_bad=0
for theme in dark light tokyonight nightfox gruvbox-material plain; do
    got="$WORK/shot-$theme.ansi"
    (cd tests/fixtures && "$BIN" --dump --theme "$theme" --width 80 --colors 24bit rich.md) >"$got" 2>/dev/null
    shot_count=$((shot_count + 1))
    if [ -n "${BLESS:-}" ]; then
        cp "$got" "docs/screenshots/$theme-80.ansi"
    elif ! cmp -s "$got" "docs/screenshots/$theme-80.ansi"; then
        shot_bad=$((shot_bad + 1))
        bad "screenshot $theme" "$(diff "docs/screenshots/$theme-80.ansi" "$got" | head -4 | cat -v | cut -c1-150)"
    fi
done
# One page with every option on: scaled headings, links, zebra rows, numbers.
got="$WORK/shot-everything.ansi"
(cd tests/fixtures && "$BIN" --dump --theme tokyonight --width 60 --colors 256 --scale on --links on --zebra --numbers rich.md) >"$got" 2>/dev/null
shot_count=$((shot_count + 1))
if [ -n "${BLESS:-}" ]; then
    cp "$got" docs/screenshots/everything-60.ansi
elif ! cmp -s "$got" docs/screenshots/everything-60.ansi; then
    shot_bad=$((shot_bad + 1))
    bad "screenshot everything" "$(diff docs/screenshots/everything-60.ansi "$got" | head -4 | cat -v | cut -c1-150)"
fi
if [ $shot_bad -eq 0 ]; then
    note "screenshots: $shot_count dumps match${BLESS:+ (rewritten)}"
fi

# Every line of every plain golden fits its width, wide characters counted as
# two columns: the layout may never overflow what it was given.
python3 - "$WORK" <<'PY'
import sys, glob, unicodedata, re, os
def cols(text):
    n = 0
    for ch in text:
        if unicodedata.combining(ch) or ch in "‍️":
            continue
        n += 2 if unicodedata.east_asian_width(ch) in "WF" or ord(ch) >= 0x1F300 and ord(ch) <= 0x1FAFF else 1
    return n
bad = 0
for path in sorted(glob.glob(sys.argv[1] + "/golden-*-[0-9]*.txt")):
    width = int(re.search(r"-(\d+)\.txt$", path).group(1))
    for number, line in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
        if "\x1b" in line:
            continue
        # a regional-indicator pair is one flag, two columns
        line = re.sub("[\U0001F1E6-\U0001F1FF]{2}", "\U0001F1EF", line)
        # a ZWJ sequence is one glyph, and a skin tone joins the one before it
        line = re.sub("\u200d.", "", line)
        line = re.sub("[\U0001F3FB-\U0001F3FF]", "", line)
        if cols(line) > width:
            print("FAIL %s:%d is %d columns wide, limit %d" % (os.path.basename(path), number, cols(line), width))
            bad += 1
print("%d goldens, %d lines too wide" % (len(glob.glob(sys.argv[1] + "/golden-*-[0-9]*.txt")), bad))
sys.exit(1 if bad else 0)
PY
if [ $? -eq 0 ]; then
    note "goldens: no line wider than its width"
else
    bad "goldens: a line is wider than its width"
fi

# --- --cat -------------------------------------------------------------------------------

cd tests/fixtures
cat_checks=0
check() {
    local name=$1 want=$2 got=$3
    if [ "$got" = "$want" ]; then
        note "cat: $name"
    else
        bad "cat: $name" "want [$want]" "got  [$got]"
    fi
    cat_checks=$((cat_checks + 1))
}

esc=$(printf '\033')
styled=$(env -u NO_COLOR TERM=xterm-256color "$BIN" --cat --theme dark --width 40 tour.md | grep -c "$esc")
check "styled output has escape sequences" yes "$([ "$styled" -gt 0 ] && echo yes || echo no)"
plain=$(NO_COLOR=1 TERM=xterm-256color "$BIN" --cat --width 40 tour.md | grep -c "$esc")
check "NO_COLOR removes every escape sequence" 0 "$plain"
plain=$(env -u NO_COLOR TERM=xterm-256color "$BIN" --cat --theme plain --width 40 tour.md | grep -c "$esc")
check "--theme plain removes every escape sequence" 0 "$plain"
empty=$(NO_COLOR= TERM=xterm-256color "$BIN" --cat --theme dark --width 40 tour.md | grep -c "$esc")
check "an empty NO_COLOR is not NO_COLOR" yes "$([ "$empty" -gt 0 ] && echo yes || echo no)"

piped=$(printf '# Piped\n\nbody text\n' | NO_COLOR=1 "$BIN" --width 30 | sed -n 2p | sed 's/ *$//')
check "standard input to a pipe prints the rendering" "  Piped" "$piped"
explicit=$(printf '# Dash\n' | NO_COLOR=1 "$BIN" --cat --width 30 - | sed -n 2p | sed 's/ *$//')
check "'-' reads standard input" "  Dash" "$explicit"
both=$(NO_COLOR=1 "$BIN" --cat --width 30 other.md other.md | grep -c 'Other File')
check "several files are all printed" 2 "$both"
piped_file=$(NO_COLOR=1 "$BIN" --width 30 other.md | sed -n 2p | sed 's/ *$//')
check "a file to a pipe prints the rendering (no terminal needed)" "  Other File" "$piped_file"

links=$(env -u NO_COLOR TERM=xterm-256color "$BIN" --cat --links on --width 60 rich.md | grep -c "${esc}]8;id=l")
check "--links on wraps links in OSC 8" yes "$([ "$links" -gt 0 ] && echo yes || echo no)"
links=$(env -u NO_COLOR TERM=xterm-256color "$BIN" --cat --width 60 rich.md | grep -c "${esc}]8;")
check "--cat has no OSC 8 unless asked" 0 "$links"
scaled=$(env -u NO_COLOR TERM=xterm-256color "$BIN" --cat --scale on --width 60 rich.md | grep -c "${esc}]66;s=2;")
check "--scale on writes the H1 as OSC 66" 1 "$scaled"
dumped=$(NO_COLOR=1 "$BIN" --dump --width 50 rich.md | grep -c "$esc")
check "--dump with NO_COLOR has no escapes" 0 "$dumped"
dumped=$(env -u NO_COLOR "$BIN" --dump --theme tokyonight --width 50 rich.md | grep -c "48;2;26;27;38")
check "--dump paints the theme's background" yes "$([ "$dumped" -gt 10 ] && echo yes || echo no)"
"$BIN" --cat nope.md >/dev/null 2>"$WORK/err.txt"
check "a missing file exits 1" 1 "$?"
check "and names the file" yes "$(grep -q 'nope.md' "$WORK/err.txt" && echo yes || echo no)"
"$BIN" --bogus >/dev/null 2>"$WORK/err.txt"
check "an unknown option exits 2" 2 "$?"
"$BIN" --help >"$WORK/help.txt" 2>&1
check "--help exits 0" 0 "$?"
check "--help names the options" yes "$(grep -q -- '--theme' "$WORK/help.txt" && grep -q -- '--no-watch' "$WORK/help.txt" && echo yes || echo no)"
printf 'not utf-8: \xe9\n' >"$WORK/latin1.md"
latin=$(NO_COLOR=1 "$BIN" --cat "$WORK/latin1.md" | head -n 1 | od -An -c | tr -d ' ' | head -c 40)
check "a Latin-1 file is shown, not refused" yes "$([ -n "$latin" ] && echo yes || echo no)"
: >"$WORK/empty.md"
check "an empty file prints and exits 0" 0 "$(NO_COLOR=1 "$BIN" --cat "$WORK/empty.md" >/dev/null 2>&1; echo $?)"
cd "$ROOT"

# --- the command line: its own suite (tests/test_cli.sh) ---------------------------------------------

TUI_MARKDOWN_BIN="$BIN" bash tests/test_cli.sh >"$WORK/cli.out" 2>&1
cli_rc=$?
cat "$WORK/cli.out"
tally "command line (tests/test_cli.sh)" "$WORK/cli.out" >/dev/null
if [ "$cli_rc" != 0 ]; then
    bad "command line suite failed" "$(grep FAIL "$WORK/cli.out" | head -10)"
fi

# --- a real terminal ----------------------------------------------------------------------------

mkdir -p "$WORK/pty"
if python3 tests/pty_e2e.py "$BIN" "$ROOT/tests/fixtures" "$WORK/pty" >"$WORK/pty.out" 2>&1; then
    :
fi
tally "pty end to end" "$WORK/pty.out"

echo
if [ $fail -eq 0 ]; then
    printf '\033[32mall %d checks passed\033[0m\n' "$pass"
else
    printf '\033[31m%d of %d checks FAILED\033[0m\n' "$fail" "$((pass + fail))"
fi
exit $fail
