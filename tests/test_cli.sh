#!/usr/bin/env bash
# tui-markdown's command line: Oro's grammar (m31's docs/cli-conventions.md):
# every option in its long and short forms (--cat, --c, --width, --w), Oro's
# refusals (-h, help-as-option, a lone --), a bad value is a usage error, the
# generated --help, --version and --completions.
#
#   M31_ROOT=/path/to/m31 LANGC=/path/to/m31c bash tests/test_cli.sh      (builds it)
#   TUI_MARKDOWN_BIN=/path/to/tui-markdown bash tests/test_cli.sh         (uses a built one)
#
# Everything here uses --cat or exits before the viewer starts, so no terminal
# is needed. macOS-safe: bash 3.2, BSD tools, mktemp, no GNU timeout.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
pass=0
fail=0
note() { printf '\033[32mok\033[0m   %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '\033[31mFAIL\033[0m %s\n' "$1"; shift; printf '%s\n' "$@" | sed 's/^/     /'; fail=$((fail + 1)); }

BIN=${TUI_MARKDOWN_BIN:-}
if [ -z "$BIN" ]; then
    BIN="$WORK/tui-markdown"
    if ! bash scripts/build.sh -o "$BIN" >"$WORK/build.log" 2>&1; then
        bad "build" "$(tail -5 "$WORK/build.log")"
        exit 1
    fi
fi

F="$ROOT/tests/fixtures"
esc=$(printf '\033')

# run ARGS... -> $out $err $code. NO_COLOR is unset and TERM fixed so the colour
# logic does not depend on the caller's terminal; standard input is /dev/null
# unless $stdin names a file.
run() {
    env -u NO_COLOR -u COLORFGBG TERM=xterm-256color "$BIN" "$@" >"$WORK/out" 2>"$WORK/err" <"${stdin:-/dev/null}"
    code=$?
    out=$(cat "$WORK/out")
    err=$(cat "$WORK/err")
}
expect() {
    local label=$1 want=$2 so=${3:-} se=${4:-}
    if [ "$code" != "$want" ]; then
        bad "$label" "exit $code, want $want" "stdout: ${out:0:300}" "stderr: ${err:0:300}"
    elif [ -n "$so" ] && [[ "$out" != *"$so"* ]]; then
        bad "$label" "stdout lacks: $so" "stdout: ${out:0:300}"
    elif [ -n "$se" ] && [[ "$err" != *"$se"* ]]; then
        bad "$label" "stderr lacks: $se" "stderr: $err"
    else
        note "$label"
    fi
}
same() {
    if [ "$2" = "$3" ]; then note "$1"; else bad "$1" "[$2]" "[$3]"; fi
}
escapes() { printf '%s\n' "$1" | grep -c "$esc"; }

# --- help, version, completions ---------------------------------------------------
run --help; expect "--help" 0 "usage: tui-markdown [options] [<FILE>...]"
for want in "--c, --cat" "--w, --width N" "--theme NAME" "--no-watch" "--version" "--help" "--completions SHELL" "exit status:"; do
    run --help
    if [[ "$out" == *"$want"* ]]; then note "--help lists: $want"; else bad "--help lacks: $want" "$out"; fi
done
run --version; expect "--version" 0 "tui-markdown 0."
run --completions bash; expect "--completions bash" 0 "complete -o filenames -F _tui_markdown_complete tui-markdown"
if printf '%s\n' "$out" | bash -n 2>"$WORK/syntax"; then note "--completions bash is valid bash"; else bad "bash completion syntax" "$(cat "$WORK/syntax")"; fi
run --completions fish; expect "--completions fish" 0 "complete -c tui-markdown -l cat"
run --completions zsh;  expect "--completions zsh" 0 "#compdef tui-markdown"

# --- --cat, --width and the theme, in every spelling -----------------------------------
cd "$F"
run --cat --width 40 --theme plain tour.md; ref=$out
expect "--cat prints the rendering" 0 "" ""
for spelling in "--c --w 40" "--cat --width=40" "--c --width 40" "--cat --w 40"; do
    # shellcheck disable=SC2086
    run $spelling --theme plain tour.md
    same "$spelling is --cat --width 40" "$ref" "$out"
done
run --cat --width 20 --theme plain tour.md
[ "$out" != "$ref" ] && note "a different --width changes the layout" || bad "--width ignored"
# characters, not bytes: BSD awk's length() counts bytes whatever the locale
wide=$(printf '%s\n' "$out" | python3 -c 'import sys; print(max([len(l.rstrip("\n")) for l in sys.stdin] or [0]))')
[ "$wide" -le 20 ] && note "--width 20: no line is wider than 20" || bad "--width 20: a line has $wide columns"
run --cat --width 40 --theme dark tour.md
[ "$(escapes "$out")" -gt 0 ] && note "--theme dark is coloured" || bad "--theme dark has no escapes"
run --cat --width 40 --theme=plain tour.md
[ "$(escapes "$out")" = 0 ] && note "--theme=plain has no escapes" || bad "--theme=plain has escapes"
NO_COLOR=1 TERM=xterm-256color "$BIN" --cat --width 40 tour.md >"$WORK/out" 2>/dev/null </dev/null
[ "$(escapes "$(cat "$WORK/out")")" = 0 ] && note "NO_COLOR still removes every escape" || bad "NO_COLOR ignored"
run --cat --width 40 --no-watch --theme plain tour.md; same "--no-watch is accepted (and changes nothing under --cat)" "$ref" "$out"

# --- operands --------------------------------------------------------------------------
stdin="$F/other.md" run --cat --width 30 --theme plain;      expect "no operand reads standard input" 0 "Other File"
stdin="$F/other.md" run --cat --width 30 --theme plain -;    expect "- reads standard input" 0 "Other File"
run --cat --width 30 --theme plain other.md other.md; [ "$(printf '%s\n' "$out" | grep -c 'Other File')" = 2 ] && note "several files are all printed" || bad "several files" "$out"
cp "$F/other.md" "$WORK/-dash.md"
(cd "$WORK" && env -u NO_COLOR "$BIN" --cat --width 30 --theme plain ./-dash.md >"$WORK/dd.out" 2>&1 </dev/null; echo $? >"$WORK/dd.rc")
[ "$(cat "$WORK/dd.rc")" = 0 ] && [[ "$(cat "$WORK/dd.out")" == *"Other File"* ]] && note "a file called -dash.md is passed as ./-dash.md" || bad "./-dash.md" "$(cat "$WORK/dd.out")"

# --- Oro's refusals and bad values: stderr, exit 2 ----------------------------------------
run -h;                  expect "-h is refused" 2 "" "write '--help'"
run -c tour.md;          expect "-c is a command, refused" 2 "" "takes no commands, and got '-c'"
run --;                  expect "a lone -- is refused" 2 "" "'--' has no meaning here"
run --h;                 expect "--h is refused" 2 "" "help has one spelling"
run --nonsense;          expect "an unknown option" 2 "" "tui-markdown: unknown option '--nonsense'"
run --ca tour.md;        expect "an abbreviation is suggested, never accepted" 2 "" "did you mean '--cat'?"
run --cw tour.md;        expect "shorts do not cluster" 2 "" "short options do not cluster -- write '--c --w'"
run --theme fancy --cat tour.md; expect "a bad theme is an error, not a warning" 2 "" "'--theme' needs one of dark, light"
run --scale maybe --cat tour.md; expect "a bad --scale" 2 "" "'--scale' needs on, off or auto, and got 'maybe'"
run --links maybe --cat tour.md; expect "a bad --links" 2 "" "'--links' needs on, off or auto"
run --colors 8 --cat tour.md;    expect "a bad --colors" 2 "" "'--colors' needs 16, 256 or 24bit, and got '8'"
run --mode vim --cat tour.md;    expect "a bad --mode" 2 "" "'--mode' needs preview, source or live"
run --width abc --cat tour.md;   expect "--width abc" 2 "" "'--width' needs a whole number, and got 'abc'"
run --width 0 --cat tour.md;     expect "--width 0 is refused, not silently replaced" 2 "" "'--width' needs a whole number of at least 1"
run --width;             expect "--width at the end" 2 "" "'--width' needs a value and is the last argument"
run --width 30 --width 40 --cat tour.md; expect "--width twice" 2 "" "was given more than once and takes a single value"
run --cat=1 tour.md;     expect "--cat takes no value" 2 "" "is a flag and takes no value"
run --cat --cat tour.md; expect "--cat twice" 2 "" "was given more than once"
[ "$(printf '%s\n' "$err" | wc -l | tr -d ' ')" -ge 2 ] && note "usage errors carry the usage line" || bad "usage error shape" "$err"
run --cat nope.md;       expect "a missing file exits 1" 1 "" "nope.md"

cd "$ROOT"

# --- install.sh ----------------------------------------------------------------
run_sh() {
    sh install.sh "$@" >"$WORK/out" 2>"$WORK/err" </dev/null
    code=$?
    out=$(cat "$WORK/out")
    err=$(cat "$WORK/err")
}
run_sh --help; expect "install.sh --help" 0 "usage: sh install.sh [options] [-uninstall]"
run_sh --version; expect "install.sh --version" 0 "installer"
run_sh -h;     expect "install.sh: -h is refused" 2 "" "write '--help'"
run_sh help;   expect "install.sh: help is refused" 2 "" "write '--help'"
run_sh --;     expect "install.sh: a lone -- is refused" 2 "" "'--' has no meaning here"
run_sh --prefx /x; expect "install.sh: typo suggests" 2 "" "did you mean '--prefix'?"
run_sh -unistall;  expect "install.sh: a mistyped command is suggested" 2 "" "did you mean '-uninstall'?"
run_sh --libc foo; expect "install.sh: bad --libc" 2 "" "needs gnu or musl, and got 'foo'"
run_sh --prefix;   expect "install.sh: --prefix at the end" 2 "" "needs a value and is the last argument"
run_sh extra;  expect "install.sh: an operand" 2 "" "unexpected argument 'extra'"
for spelling in "-uninstall --prefix $WORK/i1" "-u --prefix=$WORK/i2" "-u --p $WORK/i3"; do
    # shellcheck disable=SC2086
    run_sh $spelling
    expect "install.sh $(printf '%s' "$spelling" | sed "s#$WORK#.#g")" 0 "removed"
done
run_sh --uninstall --prefix "$WORK/i4"; expect "install.sh --uninstall (the old spelling) works and warns" 0 "removed" "deprecated"

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
