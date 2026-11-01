#!/usr/bin/env bash
# Renders bench/fidelity.md with glow and with tui-markdown at width 60, ANSI removed, into bench/results/.
#   bash bench/fidelity.sh /path/to/glow /path/to/tui-markdown
set -eu
cd "$(dirname "$0")"
glow=${1:?glow binary}; tmd=${2:?tui-markdown binary}
"$glow" -s dark -w 60 fidelity.md </dev/null | python3 -I strip_ansi.py > results/fidelity-glow-width60.txt
"$tmd" --cat --theme dark --width 60 fidelity.md </dev/null | python3 -I strip_ansi.py > results/fidelity-tui-markdown-width60.txt
