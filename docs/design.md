# Design

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
