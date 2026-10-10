# tui-markdown

An interactive, vim-keyed terminal markdown viewer written in
[m31](https://github.com/qrazil/m31), on the
[tui](https://github.com/qrazil/tui) widget library and the
[term-markdown](https://github.com/qrazil/term-markdown) parser. Think `glow`
or `less`, with an outline popup, link following and a back stack.

```
tui-markdown README.md            read a file
tui-markdown a.md b.md c.md       read several; > and < step between them
cat notes.md | tui-markdown       read standard input
tui-markdown --cat README.md      print the rendering and exit
tui-markdown README.md | less -R  (a pipe on stdout is --cat automatically)
```

## What it shows

Headings, paragraphs (wrapped to the terminal, reflowed on resize), emphasis,
strong, inline code, links and images (as `[image: alt]`), block quotes
(nested), bullet, ordered and task lists (nested, tight and loose), fenced
and indented code blocks, tables (with column alignment, wrapping inside the
cells), and horizontal rules. East Asian wide characters, emoji (ZWJ
sequences, skin tones, flags) and combining marks are measured and wrapped
by grapheme cluster, never split. Text is centred in at most 100 columns.

Light and dark themes: `--theme dark|light|plain`. Without the flag it asks
`COLORFGBG`, and it uses plain when `NO_COLOR` is set to anything non-empty.

## Keys

| Key | Does |
|---|---|
| `j` `k`, arrows, `Enter` | scroll a line (a count works: `5j`) |
| `Ctrl-d` `Ctrl-u` | half a page down / up |
| `Ctrl-f` `Ctrl-b`, `Space`, PgDn/PgUp | a page down / up |
| `gg` `G` | top / bottom; `12G` and `12gg` go to row 12 |
| `]]` `[[` | next / previous heading (a count skips that many) |
| `/` | search: type, `Enter` runs it, `Esc` cancels. Smart case: lower case matches any case, a capital makes it exact |
| `n` `N` | next / previous match (wraps; `3n` goes three on) |
| `o` | outline of the headings: `j`/`k` move, `l`/`h` open and close, `Enter` goes there |
| `Tab` `Shift-Tab` | focus the next / previous link; the target shows on the status line |
| `Enter` | follow the focused link |
| `Ctrl-o`, `Backspace` | back to where you were (block, offset and link focus are restored) |
| `y` | copy the focused link's target, or else the paragraph at the top of the window |
| `r` | reload the file |
| `>` `<` | next / previous file of the set |
| `Esc` | clear the search highlight, link focus and count |
| `?` | which-key help |
| `q`, `Ctrl-c` | quit |

### Links

- `#anchor` jumps to the heading with that GitHub-style slug (`## Hello World`
  is `#hello-world`; repeated headings get `-1`, `-2`).
- A relative path to a markdown file (`.md`, `.markdown`, `.mdown`, `.txt`)
  opens it, at its `#anchor` if one is given, and pushes the place you left on
  the back stack.
- An external URL (`https://`, `mailto:`, ...) is never opened. It is copied to
  the clipboard with an OSC 52 escape sequence, and the status line says so.
  So is a relative link to anything that is not markdown.

### Copying

`y` and external links use OSC 52 (`ESC ] 52 ; c ; base64 BEL`). It needs a
terminal that allows it (kitty, iTerm2, WezTerm, foot, Alacritty, tmux with
`set-clipboard on`, ...). Anything past 60000 bytes is cut.

### Reloading

`r` re-reads the file. Unless `--no-watch` is given the file is also checked
four times a second and reloaded when its size or modification time changes;
the window stays at the same source line. Standard input cannot be reloaded.

## `--cat`

Prints the layout once and exits, at `--width N` columns (default: the
terminal's, else 80). It is the default when standard output is not a
terminal. With `NO_COLOR` or `--theme plain` there are no escape sequences;
otherwise the styles are written as SGR sequences (256 colours; 16 on
`TERM=linux`, `vt100`, `ansi` and `dumb`).

## Build

You need an m31 toolchain: `m31c` and a checkout (or release tarball) of
[m31](https://github.com/qrazil/m31) for its C runtime. Dependencies are pinned
in `deps` (`deps.lock` records what was fetched); `m31c` fetches them into
`.m31-deps/` on the first build.

```
export M31_ROOT=/path/to/m31 LANGC=/path/to/m31c
bash scripts/build.sh            # -> ./tui-markdown
bash tests/test.sh               # fmt, lint, unit, oracle, goldens, --cat, pty
```

CI (`.github/workflows/test.yml`) runs `tests/test.sh` on Linux x86-64,
Linux aarch64 and macOS arm64 against m31 v0.3.2; `release.yml` builds the
binaries for a pushed `v*` tag.

## Architecture

```
  term-markdown                         this repo
  -------------                         ---------
  MD_blocks.parse  --block tree-->  MDV_prepare   source lines, slugs, tasks
  MD_inlines.render --HTML------->  MDV_inline    HTML -> styled spans, links
                                    MDV_wrap      spans -> lines, by width
                                    MDV_layout    blocks -> rows (Layout)
                                         |
                    MDV_cat  <-----------+----------> MDV_viewer  state machine
                    (--cat)                              |  keys -> state + Requests
                                                      MDV_render  Screen widget
                                                         |
                                    MDV_loop / MDV_app   events, tick, files, OSC 52
                                    MDV_cli              flags, the exit status
```

`MDV_viewer` knows nothing about the terminal: it takes `term.Key`s and
produces state and a list of `Request`s (`Reload`, `Open(path)`,
`Copy(text)`); `MDV_app` performs them. That is what lets `tests/t_viewer.m31`
test the whole key set with no pty. `docs/design.md` has the detail and the
changes proposed to term-markdown.

## Tests

`tests/test.sh` is the one entry point (about 390 checks):

- `t_viewer.m31`: the state machine (160 checks).
- `oracle.py` + `t_oracle.m31`: the visible text of the layout equals the text
  of term-markdown's own HTML, for 69 cases at two widths.
- `golden/`: `--cat` output at several widths, wide characters included.
  `BLESS=1 bash tests/test.sh` rewrites them; read the diff.
- `pty_e2e.py`: the real binary under a pty with a small terminal emulator, 73
  checks.

## Limits

- `~~strikethrough~~` is not parsed upstream; the markers show.
- A search term that wraps across two rows is not found.
- A table narrower than its minimum (3 columns per cell plus borders) overflows
  its line; wrap-around of tables below about 13 columns is not attempted.
- Raw HTML is shown literally (`<b>x</b>` prints with its tags); markdown
  inside it is still styled.
