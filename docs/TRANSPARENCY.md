# Transparency

tui-markdown can draw on a terminal with an opacity or blur setting (rio, Alacritty, kitty, Terminal.app, ...) so that the
desktop shows through the whole screen, not only the margins.

    tui-markdown --transparent on        every surface            (--transparent popups, --transparent off)
    TUI_MARKDOWN_TRANSPARENT=1|popups|0 tui-markdown FILE         the same, from the environment (also on, off)

Off by default, and then nothing changes: `--cat` and `--dump` of every theme at 16, 256 and 24 bits, and the bytes of
a scripted viewer session, are identical to 0.9.0 (`tests/default_bytes.py`, `tests/pty_transparent.py`). The flag wins
over the variable. A word that is neither is a usage error (exit 2). The option has no short form: Oro's table gives
`--x` shorts only to options used on every run, and `--theme` has none either; put the variable in your shell profile.

## Why a terminal needs this

A cell shows the desktop only when its background is the terminal's default (no SGR 40-47/48/100-107, or SGR 49 after
one). Any explicit background, even one equal to the default colour, is painted opaque. So the viewer cannot "make a
colour see-through": every cell it writes must leave the background alone. That is a rule about styles, so it is applied
where styles are made.

## The rule

`MDV_theme.transparent_style(mode, kind, style)` is the one function that decides, and every style that leaves
`MDV_theme` goes through it (`style_for`, `base_style`, `status_style`, `accent_style`, `select_style`, `quiet_style`,
`popup_style`, `side_style`, `thumb_style`, `hit_style`, `focus_style`). No renderer code builds a colour of its own, so a
new surface gets the rule for free as long as it asks the theme.

| kind | examples | `on` | `popups` |
|---|---|---|---|
| highlight | search hits, the focused link, the editor's selection, the chosen row of the outline and the palette | keeps its background; text becomes near-black or near-white, whichever reads on it | same |
| badge | mode / prompt label, open tab, theme button, current sidebar heading, match count | the block goes, its colour is the (bold) text colour | untouched |
| popup | outline, help, command palette, find / replace bar | background dropped | background dropped |
| surface | page, bars, sidebar, tints behind code, quotes, tables, headings | background dropped | untouched |

A reversed style that is not a highlight loses its reversal (reverse video paints the terminal's text colour as an opaque
block): in the plain theme the bars become dim text and the badges bold text. Text cursors stay reverse video. No colour of
the desktop is read, mixed or guessed: the only colours that ever appear are the theme's.

## What tells a surface from the page when its tint is gone

| was | now |
|---|---|
| code card, front-matter card (tinted block) | drawn framed: `╭─── rust ─╮`-style top rule with the language label, a dim `│` bar at the left of every line, `╰───` bottom rule. Same rows, same widths, same text; the frame is chrome (not searchable, not copied) |
| block quote, callout | the `▎` bar it always had, in the callout's colour (dim grey for a plain quote); the title row stays bold |
| table | its box-drawing borders; header cells bold blue; `--zebra` rows dim |
| H1 band | the `═` rule under it and its bold text; H2 keeps its `▌` bar and `─` rule |
| inline code, language chip | their text colour (orange, bold cyan) |
| status bar, header, toolbar, sidebar | text colour; badges (active tab, current heading `▸`, labels) bold and coloured |
| popups | their rounded border (outline, help, palette); the find bar by its dim labels and the underlined field |
| search hit, focused link, selection | an explicit background, on purpose |

## Per-surface behaviour (`--transparent on`; `popups` changes only the popups, as the table above says)

| surface | result |
|---|---|
| page and margins | no background; the theme's text colour |
| headings | bold text colour; the H1 band's background is gone |
| code cards, metadata card | framed (above); syntax colours as the theme |
| quotes and callouts | bar and text, no tint |
| tables | borders and text; no header or zebra shade |
| links | cyan underlined text; the focused link is a highlight (its colour as the block, readable text) |
| images | the `[image: alt]` placeholder is dim italic text (tui-markdown draws no bitmaps) |
| scaled H1 (OSC 66) | text colour, no band |
| outline sidebar | no background; `│` rule; the current heading bold accent text with `▸` |
| header, status line, prompt | text only; the mode, prompt and button labels are bold accent text |
| search bar, search hits | prompt text; hits keep their background (the current one is orange and bold) |
| help, outline popup, command palette | no background inside the rounded border; the chosen row keeps a background |
| find and replace bar (editor) | no background; the field is underlined while focused |
| editor (`--edit`, `--mode source|live`) | caret is reverse video; the selection keeps its background; toolbar is text |
| live reload | the status message is text; the page redraws the same way |
| scrollbar | glyphs only |
| `--cat`, `--dump` | the same mode: `--dump --transparent on` paints no page background at all |
| `--theme plain` | unchanged except that the status bar is dim text instead of reverse video |

## Highlights on a light or a dark desktop

A highlight must stay visible, so it keeps the explicit background its theme chose (as editors with a transparent
background do: only the main background is dropped). The colour is the theme's: a dark theme's highlight is dark, the
`light` theme's is light, so pick the theme that matches the desktop (`--theme`, or `COLORFGBG` at start). The text on a
highlight is chosen for its background, so it reads whatever the terminal's own text colour is. The limit: text drawn over a
highlight in the editor keeps its own syntax colour only where it already read; a dark theme on a light desktop is
unreadable with or without transparency, because the text colours are the theme's.

## Terminal settings

Opacity makes the *default* background translucent; blur blurs what is behind the window. Cells with an explicit
background stay opaque, which is why the viewer drops them.

* rio: `[window] opacity = 0.85`, `blur = true`.
* Alacritty: `[window] opacity = 0.85` (and `blur = true` where the compositor supports it).
* kitty: `background_opacity 0.85`, `background_blur 20`. Recent kitty also has `transparent_background_colors`, which
  makes chosen explicit backgrounds translucent too; with it the default (non-transparent) themes can look right.
* Terminal.app: Profile, Window: Background colour opacity and Blur.

Opacity near 1.0 hides the problem; around 0.7-0.9 the opaque cells of a non-transparent theme stand out. Check the exact
option names against your version.

## Tests

* `tests/t_theme.m31`: the resolver for all six themes and all three modes over every combination of span style bits (no
  background but the selection's, readable highlights, badges as text, popups mode touches only popups), the mode words,
  `next_after` keeping the mode, the card frame (same rows and widths and text).
* `tests/pty_transparent.py`: the real binary on a pty and a `pyte` screen, on a rich sample: page, scroll, help, outline,
  search, link focus, theme switch, sidebar, the editor (selection, find, replace, palette, three panes), the scaled
  heading, a reload from disk; for dark, light and plain with `on`, for dark with `popups`: after every step no cell has
  `bg != 'default'` outside the highlight, the bytes of a step with no highlight carry no SGR background, a highlight reads
  as exactly what was searched or focused. Default mode: the session's bytes equal the 0.9.0 binary's.
* `tests/default_bytes.py`: 414 `--cat` / `--dump` outputs equal 0.9.0's (every theme, depth, option); `off` spelled four ways
  is the same bytes as no option.
* `tests/test_cli.sh`: the option's grammar (refusals, no short form, twice, missing value), `--help`, the completion scripts.
