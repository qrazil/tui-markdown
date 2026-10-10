#!/usr/bin/env bash
# Build tui-markdown into a real executable.
#
#   M31_ROOT=/path/to/m31 LANGC=/path/to/m31c bash scripts/build.sh
#       -> ./tui-markdown
#   M31_ROOT=/path/to/m31 LANGC=/path/to/m31c bash scripts/build.sh -o mdv
#       -> ./mdv
#
# `tui_markdown.m31` imports this repo's own MDV_ modules, github.com/qrazil/tui's
# widgets as `import tui.TUI_app;` and github.com/qrazil/term-markdown's parser as
# `import markdown.MD_blocks;`. The `deps` file at the repo root names both and
# the exact commits; the first compile fetches them into `.m31-deps/` and
# records them in `deps.lock`, so nothing is staged or copied.
#
# m31c only emits C; the executable is that C linked against the m31 runtime's
# own source files, so this needs both:
#
#   - LANGC: the m31c compiler binary (v0.3.2 or later). Default ./m31c.
#   - M31_ROOT: a directory containing config.sh and runtime/ (a checkout of
#     github.com/qrazil/m31, or an extracted release's bundled runtime SDK)
#     matching LANGC's version. No default: a missing M31_ROOT is a clear error.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${M31_ROOT:-}" ]; then
    echo "M31_ROOT is not set -- point it at a checkout of github.com/qrazil/m31" \
         "(or an extracted release's runtime SDK) matching the m31c version" \
         "you're building with. See this script's own header comment." >&2
    exit 1
fi
if [ ! -f "$M31_ROOT/config.sh" ] || [ ! -d "$M31_ROOT/runtime" ]; then
    echo "M31_ROOT=$M31_ROOT does not look like an m31 checkout" \
         "(expected $M31_ROOT/config.sh and $M31_ROOT/runtime/)" >&2
    exit 1
fi
. "$M31_ROOT/config.sh"
. "$M31_ROOT/runtime/arch.sh"

out=tui-markdown
[ "${1:-}" = "-o" ] && out=${2:?-o needs a name}

LANGC=${LANGC:-./m31c}
CC=${CC:-cc}
if [ ! -x "$LANGC" ]; then
    echo "compiler not found or not executable: $LANGC" >&2
    exit 1
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

"$LANGC" --emit-c tui_markdown.m31 -o "$tmp/out.c"
# RT_REACTOR_C/RT_CTX_ASM (from runtime/arch.sh above) are paths relative to
# M31_ROOT, not to this script's own directory -- prefix them before use.
"$CC" -O2 -pthread -I "$M31_ROOT/runtime" -o "$out" "$tmp/out.c" \
    "$M31_ROOT/runtime/rt.c" "$M31_ROOT/runtime/scheduler.c" \
    "$M31_ROOT/$RT_REACTOR_C" "$M31_ROOT/$RT_CTX_ASM"
echo "$out"
