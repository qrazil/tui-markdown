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

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/qrazil/tui-markdown/master/install.sh | sh
```

Picks the release for your OS and CPU, unpacks it under `~/.local/opt/tui-markdown/<version>` and links the programs into `~/.local/bin`. `VERSION=v1.2.3` pins a release, `PREFIX=...` moves the install, `sh install.sh --uninstall` removes it.

On Alpine (musl) the installer picks the `-musl` Linux asset built by `scripts/ci-musl.sh`; `LIBC=gnu|musl` overrides detection, and a release without a musl asset falls back to the glibc one.

## What it shows

A page that reads like a rendered document, not like source with colours:

- **Headings with a real hierarchy.** H1 is a full-width band with a double
  rule under it (and, on kitty, the title at twice the size through the text
  sizing protocol, OSC 66); H2 has an accent bar and a rule; H3 to H6 each
  have a marker and a hue.
- **Lists** with bullets by depth (`•` `◦` `▪`), aligned numbers, `☐` / `☑`
  task boxes and indentation guides.
- **Block quotes** with a bar and a tint, and **callouts**: `> [!NOTE]`,
  `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]` (with an optional title
  after the marker) get an icon, a colour and their own tint.
- **Code blocks as cards**: a background, a language chip, syntax colours (the
  [syntax](https://github.com/qrazil/syntax) library), optional line numbers.
- **Tables** in rounded boxes with a tinted header, alignment, wrapping inside
  cells, and optional zebra rows.
- **Links** underlined in the accent colour and written as OSC 8 hyperlinks
  where the terminal has them; hovering one shows its target in the status line.
- Front matter as a dim metadata card, footnotes, `~~strikethrough~~`, images
  as a labelled placeholder, horizontal rules.
- East Asian wide characters, emoji (ZWJ sequences, skin tones, flags) and
  combining marks are measured and wrapped by grapheme cluster, never split.
  Text is centred in at most 100 columns (`--max-width`).
- A header row with an outline button, a sticky breadcrumb of the headings
  above the window and a theme button; an optional outline sidebar; a
  scrollbar you can drag; a status line with position and percentage.

### Themes

`--theme dark|light|tokyonight|nightfox|gruvbox-material|plain`. The default
is `light` when `COLORFGBG` says so, `plain` when `NO_COLOR` is set to
anything non-empty, else `dark`. In the viewer, `t` or a click on the theme
name in the header switches to the next one. Colours are 24-bit and fold
down to 256 or 16 colours on terminals that have no more; `--colors
16|256|24bit` forces it.

### What the terminal gets

Nothing is probed; the environment decides (`TERM`, `TERM_PROGRAM`,
`COLORTERM`, `KITTY_WINDOW_ID`, ...) and a flag overrides. OSC 8 links are on
everywhere except macOS Terminal.app (which prints what it does not know) and
dumb terminals (`--links on|off`); scaled H1 is on for kitty
(`--scale on|off`). Everything else is plain colour and works anywhere. See
`docs/DESIGN.md` for the research and the reasons.

### Mouse

The wheel scrolls; a click follows a link (an external one is handed to
`xdg-open` / `open`), jumps to a heading in the sidebar, presses a header
button, or moves the scrollbar (drag it too). Moving the pointer over a link
shows where it goes.

### `--dump`

`tui-markdown --dump --width 80 --theme tokyonight FILE` writes the page as
the screen shows it (theme background, margins, padding) with no terminal, as
ANSI text. `docs/screenshots/` has one per theme; `--zebra`, `--numbers`,
`--scale on` and `--links on` apply to it as they do on screen.

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
| `b` | dock / undock the outline sidebar (click a heading to go there) |
| `t` | next theme |
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
Linux aarch64 and macOS arm64 against m31 v0.5.0; `release.yml` builds the
binaries for a pushed `v*` tag.

## Layout

```
tui_markdown.m31   entry point (imports MDV_cli)
MDV_*.m31          the program's modules, flat at the root (14 files)
deps, deps.lock    version and pins: tui (widgets), term-markdown (parser)
scripts/build.sh   builds ./tui-markdown
tests/             test.sh (the one entry point), unit, oracle, goldens, pty
docs/DESIGN.md     the design and the changes proposed to term-markdown
RENAMES.md         what changed between releases, for a user or a dependent
.github/workflows  test.yml (3 platforms), release.yml (v* tags)
```

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
test the whole key set with no pty. `docs/DESIGN.md` has the detail and the
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

## Release

Bump `version` in `deps`, add the entry to `RENAMES.md`, push to master and wait
for `test.yml` to be green on all three platforms, then tag and push:

```
git tag v0.2.0 && git push origin v0.2.0
```

`release.yml` re-runs `test.yml` as a hard precondition, builds the binary for
Linux x86-64, Linux aarch64 and macOS arm64, and publishes the three tarballs
on the GitHub release.

## Limits

- `~~strikethrough~~` is not parsed upstream; the markers show.
- A search term that wraps across two rows is not found.
- A table narrower than its minimum (3 columns per cell plus borders) overflows
  its line; wrap-around of tables below about 13 columns is not attempted.
- Raw HTML is shown literally (`<b>x</b>` prints with its tags); markdown
  inside it is still styled.
