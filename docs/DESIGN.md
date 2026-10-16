# Design

tui-markdown is a terminal Markdown viewer and, from 0.4, a light editor in
the style of a VS Code preview: mouse first, desktop keys, no modes to learn.
This file has four parts: the research the design rests on (1), the visual
design of the viewer (2), the editing design (3), and how the code is built
(4, the original design document, still accurate below the 0.3 changes).

## Part 1. Research

Surveyed 2026-10-15. Items marked (unverified) came from memory or a
secondary source; nothing in the code depends on one.

### What makes the good ones look good

| Tool | What it does well | Portable to plain ANSI? |
|---|---|---|
| glow / glamour ([dark.json](https://raw.githubusercontent.com/charmbracelet/glamour/master/styles/dark.json)) | H1 as a padded coloured badge, inline code as a padded chip on a tinted background, code blocks as one tinted slab with a margin, `│` quote bars, `•` bullets | Yes (256 colours; degrades to 16) |
| rich Markdown ([markdown.py](https://github.com/Textualize/rich/blob/master/rich/markdown.py)) | centred H1, rules under headings, code in a padded panel, `▌` quote bar with narrower content, OSC 8 for links | Layout yes; OSC 8 needs a modern terminal |
| frogmouth ([repo](https://github.com/Textualize/frogmouth)) | table-of-contents sidebar, history, mouse | Yes with mouse; truecolor nicer |
| mdcat ([repo](https://github.com/swsnr/mdcat), archived) | OSC 8 links, inline images (iTerm2/kitty), iTerm2 jump marks per heading | Styles yes; links/images modern only |
| termimad ([repo](https://github.com/Canop/termimad)) | width-aware wrapping, table column balancing, scrollable view | Yes |
| mdfried ([repo](https://github.com/benjajaja/mdfried)) | OSC 66 scaled headings where supported, image fallback otherwise | Kitty only for the big text |
| Obsidian Live Preview ([help](https://obsidian.md/help/edit-and-read)) | markup hidden except in the block under the caret | Yes: it is a layout rule, not a terminal feature |
| iA Writer ([focus mode](https://ia.net/writer/support/editor/focus-mode)) | dim everything but the sentence/paragraph in focus, typewriter scrolling | Yes (SGR faint, scroll maths) |
| GitHub alerts ([docs](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)) | `> [!NOTE]` etc.: coloured bar, icon, title | Yes |
| bat, mdv, Zed/VS Code preview, Typora, Helix+Marksman, mdbook | not researched in depth (unverified): bat is the reference for a code gutter; the GUI previews are the target look, not a technique to copy | n/a |

What they share, and what 0.3 takes from it: hierarchy comes from background
bands and rules, not from font size; code is a card with its own background;
blocks that quote or warn carry a coloured bar and a tint that fills the whole
row; links are underlined and accent-coloured; tables have real borders and a
tinted header. All of that is plain SGR colour and works everywhere.

### Terminal capabilities (what is portable)

| Feature | Facts | Where it works | Decision |
|---|---|---|---|
| Kitty text sizing, OSC 66 ([spec](https://sw.kovidgoyal.net/kitty/text-sizing-protocol/)) | `ESC ] 66 ; s=2 ; text ST`: text fills `s*w` x `s` cells. Detect by cursor-position trick (`CSI 6 n` before and after). Erasing or overwriting any cell of a block removes it | kitty >= 0.40, Contour 0.7. Ghostty parses it but does not render ([#10333](https://github.com/ghostty-org/ghostty/issues/10333)); WezTerm no ([#7814](https://github.com/wezterm/wezterm/issues/7814)); foot width only (unverified) | Used for H1 only when the environment says kitty, or with `--scale on`; otherwise the banner band. The terminfo.dev matrix that lists iTerm2/Terminal.app/Ghostty as supporting it contradicts the trackers and is not trusted |
| OSC 8 hyperlinks ([spec](https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda)) | `OSC 8 ; id=x ; URI ST ... OSC 8 ; ; ST`; explicit `id` groups a wrapped link; URI bytes 33..126 only; keep under ~2000 bytes | iTerm2, kitty, WezTerm, VTE, Windows Terminal, foot, Alacritty, Ghostty, Konsole (off by default), tmux >= 3.4 with a feature flag ([adoption table](https://github.com/Alhadis/OSC8-Adoption)). **Not Terminal.app**: its parser prints OSC payloads ([Damore, 2025](https://garrett.damore.org/2025/12/macos-terminal-still-missing-mark-apple.html)) | On except Terminal.app and dumb terminals; `--links on|off`. Clicks are also handled by the program (mouse reporting swallows the terminal's own Ctrl-click) |
| Inline images | kitty graphics `ESC _ G a=T,f=100,c=,r= ; base64 ST` (PNG straight through, 4096-byte chunks) ([spec](https://sw.kovidgoyal.net/kitty/graphics-protocol/)); iTerm2 `OSC 1337 ; File=inline=1 : base64` ([docs](https://iterm2.com/documentation-images.html)); Sixel needs a quantiser | kitty/Ghostty/Konsole: kitty protocol. iTerm2 and WezTerm: iTerm2 protocol. Sixel: foot, WezTerm, Konsole, iTerm2 ([arewesixelyet](https://www.arewesixelyet.com/)). Never Terminal.app | Chosen from the environment (`MDV_caps`); the image drawing itself is Phase C. Sixel skipped (needs an image encoder, which m31 does not have) |
| Colour | `COLORTERM=truecolor|24bit` is the signal; kitty, WezTerm, Ghostty, iTerm2, Windows Terminal, Konsole, VTE are truecolor; Terminal.app is from macOS 26 | | Palettes are 24-bit; `TUI_style.sgr` folds to 256 or 16, so no theme needs a second table |
| Probing (XTGETTCAP, DA1, XTVERSION, DECRQM) | DA1 as a sentinel works everywhere except that Terminal.app prints the payload of DCS/APC/OSC it does not know and does not answer XTVERSION/DECRQM | | **No probing.** Decisions come from `TERM`, `TERM_PROGRAM`, `COLORTERM`, `KITTY_WINDOW_ID`, `WEZTERM_EXECUTABLE`, `GHOSTTY_RESOURCES_DIR`, `LC_TERMINAL`, `VTE_VERSION`; every feature has a flag. An over-ssh kitty therefore falls back to the band, which is the safe failure |
| OSC 52 clipboard | write is allowed by kitty, WezTerm, foot, Alacritty, tmux; iTerm2 needs a preference; Terminal.app drops it | | Used (as 0.2 did); Phase B adds pbcopy / wl-copy / xclip when present |
| Keyboard | Terminal.app has no key disambiguation; the kitty keyboard protocol (`CSI ? u`) and modifyOtherKeys fix Ctrl+Shift/Ctrl+Enter elsewhere | | Every binding is a plain Ctrl+letter, Alt+letter or function key, so Terminal.app works. The enhanced protocol is not enabled |
| Mouse | SGR 1006 reports with modifier bits; 1003 for motion | all | On: press, drag, wheel, and motion (for the hover status line) |

### Palettes

Tokyonight (night) from [folke/tokyonight.nvim](https://raw.githubusercontent.com/folke/tokyonight.nvim/main/extras/lua/tokyonight_night.lua),
nightfox from [EdenEast/nightfox.nvim](https://raw.githubusercontent.com/EdenEast/nightfox.nvim/main/lua/nightfox/palette/nightfox.lua),
gruvbox-material (dark, medium) from [sainnhe/gruvbox-material](https://raw.githubusercontent.com/sainnhe/gruvbox-material/master/autoload/gruvbox_material.vim),
all hex values copied as published. The default dark and light are the GitHub
palettes; those hex values are from memory and were **not** checked against
primer (unverified) - they are plain data in `MDV_theme` if one is off.

### Decisions taken from this

1. No terminal probing: environment only, flags to override, plain fallbacks.
2. Hierarchy by bands, bars and rules; OSC 66 is an enhancement for kitty.
3. Nothing but SGR colour is required for the look to work; truecolor
   palettes fold down.
4. Links: OSC 8 with explicit ids, withheld from Terminal.app; clicking is
   done by the program as well.
5. Themes are tables of ten colours; every tint is a mix of the page
   colour and a hue (`MDV_theme.mix`).
6. Editing follows Obsidian: the block under the caret shows its source
   (Part 3).

## Part 2. The viewer's look (0.3.0)

Everything is chrome carried by span style bits (`MDV_model`), resolved to
colours by one function (`MDV_theme.style_for`), so `--dump`, `--cat` and the
screen agree byte for byte.

| Element | Look |
|---|---|
| H1 | full-width band (padding row, title, padding row) in a tint of the accent, then a double rule `═`. With OSC 66: the title at scale 2 (two rows, two columns a letter) |
| H2 | accent bar `▌`, bold accent title, thin rule below |
| H3..H6 | markers `◆ ◇ ▸ ·`, each its own hue; H5 italic |
| Lists | bullets by depth `• ◦ ▪`, numbers right-aligned, `☐`/`☑` for tasks, a dim `│` guide for nested lists |
| Block quote | `▎` bar and a tint that fills the row; nests |
| Callouts | `> [!NOTE|TIP|IMPORTANT|WARNING|CAUTION] [title]`: kind colour for bar, icon (`ⓘ ✦ ❖ ▲ ✖`) and title; tint of the kind |
| Code | a card: tinted background, language chip at the top right, syntax colours from the `syntax` library through `TUI_syntax` (twelve classes mapped to the palette), optional line numbers, long lines wrapped |
| Tables | rounded box drawing, heavy header rule, tinted header, optional zebra rows, alignment, columns shrunk to fit |
| Rules | `── ◆ ──` |
| Front matter | dim card with a "metadata" chip |
| Footnotes | `[^x]` as superscripts, definitions collected under a short rule |
| Strikethrough | `~~x~~` (the parser leaves it as text; handled in `MDV_prepare`) |
| Images | `[image: alt]` chip with the path after it; inline drawing is Phase C |
| Links | accent colour, underline, OSC 8, target shown in the status line on hover or focus |
| Chrome | header row (outline button, sticky breadcrumb of the headings above the window, theme button), optional outline sidebar with the current heading marked, a scrollbar at the right edge (draggable), a status line with position and percentage |
| Width | text capped at 100 columns (`--max-width N`, 0 for none) and centred |

Not done: figlet-style block letters for H1 (a band plus OSC 66 reads better
and costs no layout code), per-block incremental relayout (layout is whole
document per width; fast enough for the documents tried, measured in the
test run).

## Part 3. Editing (0.4.0)

Not a full text editor: a document editor in the spirit of a VS Code preview.
Mouse first, desktop keys, no modes to learn.

### Decision: its own editing core (`MDV_edit`), not m3dit's, not `TUI_textarea`

- m3dit's `MED_buffer` / `MED_editor` are the right shape (one `splice`
  mutator, `Edit` records the undo reverses) and the idea is copied, but they
  are modules of an application: the editor there is vim (modes, registers,
  an undo *tree*, marks) and `MED_editor` is 1,400 lines that assume it. Taking
  them would mean depending on the application repo for one 200-line idea, so
  they were not entangled; the core here is `MDV_edit` (about 450 lines).
- `tui`'s `TextArea` is library quality and was the other candidate. It is a
  widget (it draws itself and decodes its own keys), keeps undo as snapshots
  of the whole line list, and has no way to group an edit run or to run a
  markdown rule between a key and its effect. The assists need `splice`-level
  control; a snapshot undo of a 10,000-line file per keystroke is also the
  wrong cost.
- What `MDV_edit` has: lines and a caret on grapheme boundaries (`TUI_text`),
  a selection, one mutator (`splice`) that records `Edit(from, removed,
  inserted)`, undo groups (a run of typing is one step; every command is one;
  moving the caret seals the open group), `dirty_from` so a highlight cache
  knows where to forget, and the motions.
- `MDV_assist` is the markdown on top, each rule one function over a buffer
  and tested on `before -> command -> after` strings (`tests/t_edit.m31`).

### Panes

Preview, Source and Live all produce an ordinary `MDV_model.Layout`, so
scrolling, search, the sidebar and the mouse code are the same for all three.

- **Preview** is the 0.3 layout.
- **Source** (`MDV_live.source_layout`): every line as written, wrapped at the
  text width at a space when there is one; a row knows its source line and the
  byte offset of its text (`Row.line`, `Row.col`). Colour comes from the
  `syntax` library's markdown grammar, per line, with the end state of each
  line kept so a fence colours the lines inside it; edits forget only from the
  first changed line (`Buffer.dirty_from`).
- **Live** (`MDV_live.live_layout`): at the grain of a block (a paragraph, a
  heading, a whole list, a table, a fence), the block that holds the caret is
  Source and the rest is Preview rows from a per-document cache. Moving the
  caret only changes which block is source. Typing inside a line never
  re-parses: the old document serves until the caret leaves the block, a
  structural edit (a line added or removed, undo, paste, replace) re-parses.
  Clicking a rendered block puts the caret at its first line.

It opens in **Preview**: a file is usually opened to be read, and the pane
that cannot change it by accident is the safe default (`--mode`/`--edit`
change that).

### Keys

Desktop keys, chosen so they reach the program on every terminal: the decoder
(`lib/term.m31`) cannot tell `Ctrl-H` from Backspace, `Ctrl-I` from Tab,
`Ctrl-M` from Enter, and `Ctrl-1`..`Ctrl-6` are not sent at all, so replace
is `Ctrl-R` (`Ctrl-H` also works on a terminal speaking the CSI-u protocol),
italic and the heading levels are on `Alt`. Soft wrap is always on in the
editing panes (a wrapped row is a row; horizontal scrolling was not done).

### Measured (14,000 lines, 2,000 sections, -O1 test build, one core)

Open and lay out Preview 185 ms; switch to Source 146 ms; a keystroke in
Source 124 ms (the whole source layout is rebuilt: only the highlight is
incremental); the first switch to Live 2.7 s (every block laid out once, then
cached), a keystroke in Live 96 ms. Comfortable to about 1,500 lines; beyond
that the per-keystroke rebuild needs to become per-line. Not done.

### What is not done

- Real terminals were not available to the author: every behaviour is tested
  through a pty with an emulator and SGR 1006 mouse reports (`tests/pty_e2e.py`),
  not in kitty, iTerm2, Ghostty or Terminal.app.
- Phase C (inline images, polish) was not started.
- No incremental parse: Preview and Live re-run the whole markdown parser
  after a structural edit.
- The find bar highlights hits on rows (Source rows, rendered text), not
  source ranges inside a rendered block.

## Part 4. How the viewer is built (0.2, kept; 0.3 notes at the end of each part)

tui-markdown reads markdown, lays it out for a width, and lets you move around
in the result with vim keys. This file is how it is built, what it takes from
its two dependencies, what it had to work around, and what term-markdown could
change to make that unnecessary.

## Pipeline

```
source text
  -> MDV_prepare.prepare      MD_blocks.parse; each inline through MD_inlines.render
                              and MDV_inline.parse; slugs, source lines, task items
  -> MDV_model.Document       blocks (Para, Head, Code, Quote, Items, Table, Rule)
                              holding styled Spans; the document's Links
  -> MDV_layout.layout(width) rows of spans: wrapping, bullets, borders, padding
  -> MDV_model.Layout         rows, headings (with their row), links
  -> MDV_cat / MDV_render     ANSI text, or cells in a TUI_buffer
```

Everything up to `Layout` is pure: a string and a width in, a value out. That
is why the goldens and the oracle can be run without a terminal, and why a
resize is only `layout()` again.

### Spans and styles

A `Span` is text, a bit set (`BOLD`, `ITALIC`, `CODE`, `LINK`, `IMAGE`, `TASK`,
`HEAD_CELL`, `BLOCK`, `BREAK`, `DECO`, plus a heading level) and a link index.
`DECO` marks decoration: the bullet, the quote bar, the table borders, a code
block's padding, `[image: ` and `]`. `Row.content()` is the row without
decoration. Search, yank, and the visible-text oracle all use `content()`, so
decoration can never be found, copied or confused for text.

### Wrapping (`MDV_wrap`)

`TUI_text.wrap` wraps a `str`; a line here is many spans. The same rules are
applied to a span list: break at a run of spaces (dropped), and between two
grapheme clusters when either is two columns wide (so CJK wraps with no
spaces); a word wider than the line is cut at the last cluster that fits; a
cluster wider than the line gets a line of its own; a hard break ends the
line. Nothing splits a cluster. Plain ASCII, nearly all of any document, is
scanned by byte and never goes through `unicode.graphemes`.

### Layout (`MDV_layout`)

Each block becomes a `Part` of rows, nested blocks get a prefix (list indent,
`│ ` for a quote) that is itself DECO and is accounted for in the width given
to the children. Tables size each column to its longest cell, shrink the
widest columns until the table fits, and wrap inside the cell; the minimum is
one column per cell, so a table below about 13 columns (for 3 columns)
overflows. Every row records its leaf block's index and the 1-based source line of that
block. The block plus the row's offset inside the block (`Anchor`) keeps the
place across a resize; the line keeps it across a reload; both go into a
back-stack `Place`.

## The viewer (`MDV_viewer`)

`Viewer` is the whole state: `top` row, pending count and `g`/`]`/`[` prefix,
`Mode` (`Normal | Search | Outline | Help`), search needle and hits, focused
link, back stack, outline, message. `Viewer.key(term.Key)` is the only way it
changes, and it answers a `TUI_app.Action`. Effects outside the process are
never performed there: it queues `Request`s (`Reload`, `Open(path)`,
`Copy(text)`), and `MDV_app.App` drains and performs them after each key. A
test builds a `Viewer` from a string, types key names with `press`, and reads
fields back; nothing in `t_viewer.m31` touches a file descriptor.

- **Keeping the place.** `Anchor` (block, offset within the block's rows) is
  used for resize, because wrapping changes row numbers and not blocks. A
  reload uses the source line, because blocks may have changed; it is exact
  when the line count is unchanged and approximate otherwise. A back-stack
  `Place` holds name, block, offset and link focus; going back to another file
  asks for `Open` and applies the place when the text arrives (`pending_place`).
- **Search** is smart-case over `Row.content()`. Hits are byte ranges in a row.
  A row whose lower-cased text has a different byte length (a few Unicode
  letters) is skipped rather than risk marking the wrong bytes. A match that
  wraps across two rows is not found.
- **Links.** `Tab` cycles `layout.links`. Following one decides in order:
  `#slug` in this file; external (`scheme:` or `//`) is `Copy`; same file;
  not markdown is `Copy`; otherwise push the place and `Open`. A failed open
  (`load_failed`) pops what it pushed.
- **Outline.** Built from heading levels with a recursive cursor, so a skipped
  level (`#` then `###`) still nests. It is a `TUI_outline.Outline` in a popup.

## The loop (`MDV_loop`, `MDV_app`)

`TUI_app.Loop.run` takes a widget and a handler. This program also needs to
tick (file watch every 250 ms), write raw output (OSC 52) between frames, and
notice a lone `Esc`. `term.Reader.read` only resolves a lone ESC (as opposed to
the start of a sequence) when a read times out, so a loop that waits 250 ms for
a key makes Esc take 250 ms. `MDV_loop` is therefore a copy of the tui loop
that always reads with a 50 ms wait, counts idle waits to tick every 250 ms,
and asks a `Host` interface (`handle`, `needs_redraw`, `take_output`) for the
rest. When standard input is a pipe, keys are read from fd 1 (the terminal).

## Testing, and what each layer is checked against

| Layer | Checked against |
|---|---|
| Visible text | term-markdown's HTML rendering of the same source, text extracted by Python's `html.parser`; whitespace removed from both; tables compared as character multisets (cells wrap side by side) |
| Layout | goldens (`--cat --theme plain`), plus a Python check that no line exceeds its width in columns |
| Viewer | 160 direct checks on the state machine |
| Whole program | a pty with a screen emulator: the checks read what is on the screen, not bytes |

The oracle found a real bug during development: image alt text was entirely
decoration, so it could not be searched or copied. Only the brackets are
decoration now.

## What term-markdown gave us, and what it did not

Used as a library it works: `import markdown.MD_blocks;` gives
`MD_blocks.parse(source)` (a `MD_doc.Document` with `blocks` and `references`)
and `MD_inlines.render(raw, references)`. No change to it was needed to ship.
The gaps below are worked around here, each in one place.

1. **Inline output is HTML only.** Inlines come back as an HTML string, not a
   tree. `MDV_inline` is a small HTML reader for exactly the tags
   `MD_inlines.render` writes (`em strong code a img br`), and relies on every
   literal `<` in the source being escaped. *Proposal:* a
   `MD_inlines.parse(raw, references) -> List<MD_doc.Inline>` that the HTML
   renderer itself is built on (`Text`, `Emph`, `Strong`, `Code`, `Link{href,
   title, kids}`, `Image{src, title, alt}`, `Break`, `SoftBreak`). That makes
   `render` a fold over the tree, and every non-HTML consumer cheap.
2. **No source positions.** A block does not know which lines it came from.
   `MDV_prepare` searches forward through the source for each block's first
   line. It is exact for most input and a near miss for rewritten text (setext
   headings, tabs). The line is only used to keep the place across a reload.
   *Proposal:* `line: int` (1-based, and ideally `end_line`) on every
   `MD_doc.Block` variant's payload.
3. **No task lists.** `- [x] done` is an ordinary item whose paragraph starts
   with `[x] `; `MDV_prepare` splits those three bytes into a `TASK` span.
   *Proposal:* `is_task` and `is_checked` (or `Option<bool>`) on `MD_doc.Item`.
4. **No strikethrough.** `~~x~~` stays literal. *Proposal:* GFM `Strike` in the
   inline tree.
5. **No raw HTML** as inline or block; it is escaped and shown literally. Fine
   for a terminal; noted for completeness.
6. **Heading anchors.** `MDV_prepare.slugify` implements GitHub's slugs and the
   `-1`, `-2` suffix for repeats. *Proposal:* `MD_doc.Heading.slug`, since an
   HTML renderer wants the same `id`.

## Gaps hit in m31 and tui (none blocking)

- `TUI_app.Loop.run` has no tick hook and no way to write raw bytes between
  frames; `MDV_loop` copies the loop around a `Host`. A `Handler` with
  `tick()` and `take_output()` upstream would remove the copy.
- `term.Reader.read(timeout)` resolves a lone `Esc` only on a timeout (see
  above); a documented "escape wait" knob on `Loop` would be enough.
- There is no lossy UTF-8 decode: a file that is not UTF-8 is read as Latin-1
  (`MDV_app.text_of`), so it shows rather than failing.
- Parameters and fields with defaults are named-only, and `==` on enums needs a
  hand-written `eq`; code here uses `match` for both `Mode` and `Action`.
- `str` has no `replace`; `split(a).join(b)` stands in.

## Limits

Strikethrough, a match wrapping across rows, tables narrower than their
minimum, an open outline or help popup during a resize (it is redrawn at the
new size; its scroll position is not recomputed), and raw HTML. See the README.
