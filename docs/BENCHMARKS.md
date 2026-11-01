# Benchmarks: tui-markdown against glow

tui-markdown (m31, on the tui widget library) against [glow](https://github.com/charmbracelet/glow) 3.0.0 (Go,
Charm's markdown renderer: goldmark, glamour, chroma, lipgloss, termenv) on the same files: wall time including
start-up, peak RSS and output bytes, to a pipe and to a pty, plus the interactive first frame of tui-markdown, plus what each
renders that the other does not. The library-level comparison with ratatui is in tui's `docs/BENCHMARKS.md`.

```sh
python3 -I bench/gen_inputs.py /tmp/md-in README.md                  # readme.md, mixed-50k.md, mixed-1m.md
python3 -I bench/render.py 30 /tmp/md-in /path/to/glow /path/to/tui-markdown      # ROW lines: wall time, output bytes
BENCH_MODES=rss python3 -I bench/render.py 7 /tmp/md-in glow tui-markdown          # RSS lines: peak RSS (GNU time)
python3 -I bench/ab_first_frame.py 30 /tmp/md-in/readme.md binary-a binary-b       # interleaved first-frame A/B
bash bench/fidelity.sh /path/to/glow /path/to/tui-markdown                         # bench/results/fidelity-*.txt
```

## What was run

- **glow 3.0.0** (`glow_3.0.0_Linux_x86_64.tar.gz` from the charmbracelet/glow release, SHA-256 checked against the
  release's `checksums.txt`), run by absolute path as `glow -s dark -w 80 file`. `-s dark` is a fixed style (no terminal
  background query); `-w 80` is the width. Its stdin is `/dev/null`: with a stdin that was neither a terminal nor `/dev/null`, glow waited and did not render the file in my first try, so every run gives it `/dev/null`.
- **tui-markdown 0.10.1** built with m31 v0.9.0 (gcc -O2) against tui 0.16.0, run as `tui-markdown --cat --theme dark --width 80 file`
  (the one-shot rendering: what `tui-markdown file | less -R` does). The interactive viewer is a different thing from
  glow's one-shot; its first frame is measured separately, below.
- **Inputs** (`bench/gen_inputs.py`, deterministic): `readme.md`, this repository's README (19 KB); `mixed-50k.md` (52 KB) and
  `mixed-1m.md` (1,050 KB), synthetic: every section has headings, a paragraph with bold, italic, code, strike, a link, emoji, a ZWJ family
  and CJK/Korean text, nested lists with tasks, a block quote, a three-row table with alignments and a wide-character cell, a
  code block in one of five languages (rust, python, go, sh, json), and a rule.
- **Modes**: *pipe* (stdout a pipe, drained) and *pty* (an 80x24 pseudo-terminal, drained, which answers the background-colour,
  cursor-position and device-attribute queries a terminal answers, because a glow on a pty that nobody answers waits 10 s
  for termenv's timeout; `bench/results/render-v0.10.0-m31rel9-run1-silent-terminal.txt` is that run, kept to show it).
- **Sampling**: 30 runs (10 for the 1 MB file) after one warm-up, median and p95 of the wall time from spawn to exit,
  one command at a time. **Not pinned to a core** (glow is multi-threaded with a garbage collector; pinning it to one
  core would be unfair to it), on a machine that was **also running other work (load average 2-5)**: the spread between
  repeated runs of one command was up to 2x, so the ratios below carry about that uncertainty (the earlier runs
  in `bench/results/*silent*` and the first runs I looked at gave glow readme 72-160 ms and tui-markdown 10-17 ms).
- **Machine**: Intel Core i7-8750H, 12 threads, Linux 6.14, `powersave` governor, 16 GB.

## Results

Wall time to render and exit, milliseconds (`bench/results/render-v0.10.1-tui-0.16.0-m31-v0.9.0.txt`):

| file | mode | glow median / p95 | tui-markdown median / p95 | glow / tui-markdown |
|---|---|---:|---:|---:|
| readme 19 KB | pipe | 127 / 190 | 15.4 / 27 | 8.3x |
| readme 19 KB | pty | 135 / 184 | 23.6 / 27 | 5.7x |
| mixed 52 KB | pipe | 630 / 884 | 123 / 147 | 5.1x |
| mixed 52 KB | pty | 1065 / 1228 | 91 / 145 | 11.7x |
| mixed 1 MB | pipe | 7738 / 7922 | 1097 / 1169 | 7.1x |
| mixed 1 MB | pty | 9894 / 13970 | 1892 / 2405 | 5.2x |

(The pipe and pty rows of one tool differ by the machine's load as much as by the mode; read the ratio as 5-12x.) glow's
`pipe-color` rows (`CLICOLOR_FORCE=1`) are the same as `pipe`: with `-s dark` it writes its colours on a pipe anyway.

Output bytes (the same in every run) and peak RSS (`bench/results/rss-*.txt`, GNU time, median of 7):

| file | glow bytes | tui-markdown bytes | glow RSS | tui-markdown RSS |
|---|---:|---:|---:|---:|
| readme 19 KB | 231,721 | 54,764 | 18.8 MB | 7.2 MB |
| mixed 52 KB | 1,748,182 | 229,651 | 30.1 MB | 9.2 MB |
| mixed 1 MB | 34,995,292 | 4,635,630 | 301 MB | 56 MB |

glow writes 4.2-7.6x the bytes: it styles every character separately (5,400 SGR sequences for the 80 lines of the fidelity
sample, against 264) and pads every line with styled spaces to the margin. That is a cost to the terminal, and to a pager.

tui-markdown's interactive first frame (spawn, parse, layout, write the first screen; 150 ms of quiet after the last byte
is not counted; the width calibration is off because the harness does not answer it), interleaved A/B of tui 0.15.0 and 0.16.0 builds
(`bench/results/first-frame-ab-*.txt`): readme 15.2 / 14.7 ms, 52 KB 58.1 / 57.5 ms, 1 MB 1178 / 1124 ms. No difference: the first
frame is parse and layout, and one frame has few links. (The tui change that matters for a page with links is in the cost of
every later frame, a scroll; the viewer's scroll cost was not measured here, tui's `docs/BENCHMARKS.md` has the library numbers.)

glow's other modes were not measured: `glow -p file` hands the rendering to `$PAGER` (the time is the same one-shot render plus the
pager's start-up) and `glow` with no argument is its file-browser TUI. They are products glow has and the one-shot comparison does not cover.

## What is rendered, and what is not (`bench/fidelity.md` at width 60, `bench/results/fidelity-*.txt`)

| | glow 3.0.0 | tui-markdown 0.10.1 |
|---|---|---|
| front matter | dropped | a dim metadata card |
| headings | H1 a coloured band; H2-H6 as the literal `##` prefix in colour | H1 band with a double rule, H2 accent bar and rule, H3-H6 marker and hue each |
| inline link | the text, then the URL written after it in the text, and an OSC 8 hyperlink (22 in the sample) | the text, underlined; the target in the status line when hovered; no OSC 8 in `--cat` to a pipe (0 in the sample), OSC 8 in the viewer where the terminal has it |
| autolink, reference link | URL shown; reference link shows its URL | URL shown; reference link shown as its text |
| image | `Image: alt -> /absolute/path/pic.png` (a relative path made absolute) | `[image: alt] pic.png` |
| footnote | `[^1]` left in the text and the definition listed | superscript mark and a footnote section |
| block quote, nested | bar per level; a quote line wrapped one word early with its continuation outside the bar (in the sample) | bar per level, wrapped inside the bar |
| `> [!WARNING]` callout | printed as the literal `[!WARNING]` text in a quote | a card with icon, colour and a tint (NOTE, TIP, IMPORTANT, WARNING, CAUTION) |
| nested lists, task lists | yes (blank lines between nesting groups) | yes, with indentation guides, `☐` / `☑` |
| table | columns with `│` and a `─┼─` rule, no outer box; alignment and cell wrapping yes; a wide-character cell aligned | rounded box, tinted header, alignment, cell wrapping yes, wide-character cell aligned, optional zebra |
| code block | syntax-coloured (chroma, 18 foreground colours in the sample), no language label | syntax-coloured (the `syntax` library), a language chip, optional line numbers, framed when transparent |
| wide text, emoji | wrapped by columns; the ZWJ family, flag and VS16 heart kept whole | wrapped by grapheme cluster and never split; calibrated against the terminal at start-up in the viewer |
| long unbreakable URL | broken at a `/` | broken at the margin, mid-token |
| inline HTML | tags dropped, text kept | shown literally |
| definition list | not rendered as a list (neither supports it) | same |
| colour depth | 256-colour (`38;5`) with `-s dark` | the terminal's depth (`--colors`), 24-bit when it has it (121 `38;2` uses in the sample) |

Where glow is better in the sample: it keeps a relative image path usable (made absolute), drops raw HTML tags instead of showing
them, shows every link's target without hovering, and breaks a long URL at a slash. Where tui-markdown is: callouts, front matter,
the heading hierarchy, footnotes, tables that survive narrow widths in a box, grapheme-safe wrapping, a quarter of the bytes
and an interactive viewer (outline, search, link following, editing) that glow's one-shot does not claim to be.

## Why the gap, and what the profile says

A sampling profile of `--cat` on the 1 MB file (2 kHz SIGPROF with the emitted C, symbolised with `nm`) puts 52 % in libc
(`malloc`, `free`, `memcpy`, `memcmp`), 11 % in `rc_dec`, 3 % in `rt_stack_check`, 2 % in `rt_str_byte_at`, and the rest in a flat tail
(`str_new`, `rt_list_push`, `class_of`, `char_width`...): the renderer is allocation-bound, with about 1 µs per input byte, which
is 7x faster than glow's goldmark + chroma + lipgloss pipeline and uses a fifth of its memory, and neither is fast in absolute
terms (1 MB/s). The 56 MB of RSS for a 1 MB document is the document model: parsed nodes, one layout line per row, styled
spans as strings.

## Perf updates we should have (tui-markdown)

**Done in this review**: nothing in tui-markdown's own code (it was already 5-12x glow); it now pins tui 0.16.0, whose link, CJK-text
and hyperlink-URI changes are in tui's `docs/BENCHMARKS.md`. The benchmark, the fidelity sample and the gate are new.

**Worth doing**

1. *Lay out only what is visible, and keep the rest lazy* (or incrementally by block): a resize or a width change re-lays the whole
   document; for the 1 MB file that is up to a second (the `--cat` time is parse + layout + render, so it bounds it from above;
   not measured separately), for a README 15 ms. Cache the layout per block and re-wrap only the blocks in and near the window.
2. *Lower memory on large documents*: 56 MB for 1 MB. Store spans as offsets into the source text rather than strings.
3. *Autolinks and long tokens*: break a long URL at `/`, `-`, `?`, `&` as glow does, before falling back to the margin (a small
   `TUI_text.wrap` change, byte-visible, so it needs the goldens re-blessed).
4. *Relative images*: keep the path as written (it does), and add the resolved path to the label when `--links on`.
5. *tui*: the wide-text cluster-layout cache and the measured-class trust listed in tui's BENCHMARKS (CJK documents).

**Compiler-bound**

1. The allocation share (52 % libc, 11 % `rc_dec`): there is no arena or `str` slice type, so every node, span and line is a heap
   object (tui `docs/FRICTION.md` section 8 and items 3 and 8 of section 30).
2. Idle CPU of the interactive viewer (about 10-20 ms of CPU a second while open, a 1 kHz scheduler tick) and the 100 ms latency to
   notice a resized window (no SIGWINCH): tui's `docs/FRICTION.md` section 31, requests 1 and 2.
3. A SIGTERM or SIGHUP leaves the alternate screen, the mouse modes and the hidden cursor on (section 31, request 3): `tui-markdown`
   cannot restore them from a handler the language does not have.

## Raw data

`bench/results/`: `render-v0.10.1-tui-0.16.0-m31-v0.9.0.txt` (`ROW tool mode file runs median_ms p95_ms rss_kb_wait4 out_bytes`; the
rss column there is wait4's and is floored by the harness's own size: use `rss-*.txt`), `render-v0.10.0-m31rel9-run1-silent-terminal.txt`
(a pty that answers nothing: glow waits about 10 s on every run; the pipe rows of this first run are the same measurement as above),
`first-frame-*.txt`, `first-frame-ab-*.txt`, `rss-*.txt`, `fidelity-*-width60.txt`.
