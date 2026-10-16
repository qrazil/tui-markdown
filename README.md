# tui-markdown

A terminal markdown viewer and light editor, written in
[m31](https://github.com/qrazil/m31), on the
[tui](https://github.com/qrazil/tui) widget library, the
[term-markdown](https://github.com/qrazil/term-markdown) parser and the
[syntax](https://github.com/qrazil/syntax) highlighter. Think `glow` with the
page of a VS Code preview: themes, an outline, link following and a back
stack, and when you want to change something, Source and Live panes with the
mouse and the keys of a desktop editor (not vim).

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

Picks the release for your OS and CPU, unpacks it under `~/.local/opt/tui-markdown/<version>` and links the programs into `~/.local/bin`. `--release v1.2.3` (or `VERSION=v1.2.3`) pins a release, `--prefix DIR` (or `PREFIX=...`) moves the install, `--libc gnu|musl` (or `LIBC=`) overrides detection, `-uninstall` removes it, `--help` lists them; piped from curl, pass them after `-s --`: `curl -fsSL <url> | sh -s -- --prefix /usr/local`. The grammar is Oro's: a mistyped option is an error naming the closest one (exit 2).

On Alpine (musl) the installer picks the `-musl` Linux asset built by `scripts/ci-musl.sh`; `LIBC=gnu|musl` overrides detection, and a release without a musl asset falls back to the glibc one.

## Command line

The grammar is Oro's `args` (`lib/args`, m31's
[`docs/cli-conventions.md`](https://github.com/qrazil/m31/blob/master/docs/cli-conventions.md)):
`--width 40` and `--width=40`; a short option is two dashes and one letter
(`--w 40`, `--c`); `-word` would be a command (there are none), so `-h` and `-w` are
refused with a message that says what to write; `--help` is the only help; a
mistyped option names the closest one; a file called `-x` is passed as `./-x`. A bad
command line, or a value that is not one of an option's words (`--theme fancy`; it
used to warn and fall back to dark), is an error on standard error with exit 2; a file
that cannot be read is exit 1.

| option | | default | |
|---|---|---|---|
| `--cat`, `--c` | switch | off; implied when stdout is not a terminal | print the rendering and exit |
| `--width N`, `--w` | integer >= 1 | the terminal's width, else 80 | columns for `--cat` and `--dump` |
| `--theme NAME` | `dark light tokyonight nightfox gruvbox-material plain` | from `COLORFGBG`; `plain` with `NO_COLOR` | |
| `--no-watch` | switch | off | do not reload when the file changes |
| `--version` | | | `tui-markdown 0.4.0` |
| `--completions SHELL` | `bash`, `zsh`, `fish` | | prints a completion script |

The page and editor options (`--dump`, `--max-width`, `--scale`, `--links`, `--colors`,
`--zebra`, `--numbers`, `--side`, `--mode`, `--edit`, `--smart`) are in `--help`.

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

## Editing

Three panes, switched from the header (click), with `F2`, or directly:

| | |
|---|---|
| **Preview** (`Alt-P`) | the rendered page; read only, with the vim-flavoured movement keys below |
| **Source** (`Alt-S`) | the markdown as written, highlighted, soft-wrapped, with a caret |
| **Live** (`Alt-L`, or `e` in Preview) | the page rendered, except the block under the caret, which is source (as Obsidian's live preview) |

It opens in Preview; `--mode source|live` (or `--edit`) opens in an editing
pane. A task box ticked in Preview or Live changes the file like any other
edit.

| Key | Does |
|---|---|
| typing, arrows, `Home` `End` `PgUp` `PgDn`, `Ctrl`+arrows (word), `Shift` to select | what they do in any editor |
| mouse | click places the caret, drag selects, double-click a word, triple-click a line, wheel scrolls; in Live a click on a rendered block turns it into source |
| `Ctrl-A` `Ctrl-X` `Ctrl-C` `Ctrl-V` | select all, cut, copy, paste (system clipboard through `pbcopy`/`wl-copy`/`xclip`/`xsel` when there is one, and OSC 52); Ctrl-C and Ctrl-X with no selection take the line |
| `Ctrl-Z` `Ctrl-Y` | undo, redo (a run of typing is one step) |
| `Ctrl-S` | save (asks for a name for standard input) |
| `Ctrl-F`, `Ctrl-R` | find, find and replace; `Enter`/`Up` next/previous, `Tab` switches fields, `Alt-A` replace all, `Alt-C` match case, `Esc` closes |
| `Ctrl-P` or `F1` | command palette: every action, with its key |
| `Ctrl-G` | go to heading |
| `Ctrl-B` `Alt-I` `Alt-D` `Ctrl-E` `Ctrl-K` `Alt-M` | bold, italic, strikethrough, code, link, image |
| `Alt-1` .. `Alt-6` | heading level (again removes it) |
| `Ctrl-Q` | quit; asks when there is unsaved work |

Markdown help while typing: `- ` `* ` `+ ` `1.` `- [ ]` start lists, and `Enter`
continues them (on an empty item it ends the list, in a quote it continues
the `>`, after an opening fence it types the closing one, at the end of a
table row it adds a row); `Tab` / `Shift-Tab` nest and un-nest items and the
ordered lists renumber themselves; `(` `[` `{` `"` `'` `` ` `` pair, typing the
closing character steps over it and Backspace on an empty pair removes both,
and `*` `_` `~` wrap a selection (`*` twice makes it bold); pasting a URL over
a selection makes a link, and a dragged file arrives as `![name](path)` or
`[name](path)`; pipe tables line up when the caret leaves a row and `Tab`
moves between cells (a new row after the last). `--smart` (or the palette)
turns on curly quotes, en dashes and ellipses.

A change on disk while there are unsaved edits asks instead of reloading.
`Ctrl-H` cannot be replace: a terminal sends the same byte for it as for
Backspace. `Ctrl-I` (Tab), `Ctrl-M` (Enter) and `Ctrl-1`..`Ctrl-6` have the same
problem, which is why italic and the headings are on `Alt`.

## Keys in Preview

| Key | Does |
|---|---|
| `j` `k`, arrows, `Enter` | scroll a line (a count works: `5j`) |
| `Ctrl-d` `Ctrl-u` | half a page down / up |
| `Ctrl-b`, `Space`, PgDn/PgUp | a page up / down |
| `gg` `G` | top / bottom; `12G` and `12gg` go to row 12 |
| `]]` `[[` | next / previous heading (a count skips that many) |
| `/` | search: type, `Enter` runs it, `Esc` cancels. Smart case: lower case matches any case, a capital makes it exact |
| `n` `N` | next / previous match (wraps; `3n` goes three on) |
| `o` | outline of the headings: `j`/`k` move, `l`/`h` open and close, `Enter` goes there |
| `b` | dock / undock the outline sidebar (click a heading to go there) |
| `t` | next theme |
| `e` | edit (Live) |
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
