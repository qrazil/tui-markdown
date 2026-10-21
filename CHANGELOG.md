# Changelog

Each version is a tag of github.com/qrazil/tui-markdown. `RENAMES.md` says what a program that imports one of
these modules has to change when an API moves; this file says what each version added, changed and fixed.
Versions up to 0.5.0 were written back from `git log`.

## 0.8.0

Screen corruption on real Macs. The viewer leaves pieces of earlier frames on a terminal that measures a cluster
differently from the library: scrolling a page that holds a text emoji (`U+26A0 U+FE0F`), a keycap, Devanagari, halfwidth
katakana with a dakuten or an emoji newer than the terminal's tables left the tail of a line or a stray word in the
next row (`tests/pty_variants.py` below, in the form that repainted by resizing, on the unchanged 0.7.0 binary: 78 of 105
comparisons wrong, 15 steps on 7 emulated terminals). The renderer is tui's; this release pins tui v0.13.0 (f67234d, see its CHANGELOG): rows with
a cluster of uncertain width are written whole from the cluster to their end, the column a narrower terminal leaves
undrawn is blanked, autowrap is off, and a full repaint clears the screen. Built and tested against m31 v0.9.0.

### Added

- `tests/pty_variants.py` (run by `tests/test.sh`, skipped when `pyte` is missing): a document full of what terminals
  disagree on, in a heading, a list, a table, a quote and a code block, scrolled by line, page and to the ends, with the
  help open and resized, replayed on seven emulated terminals (pyte, which adds code points up as Terminal.app does, and
  six more width tables). After every step each terminal's screen must equal what a from-scratch repaint gives on it.

### Changed

- CTRL-L redraws the whole screen (`Loop.should_repaint_on_ctrl_l`, listed in the help), as m3 always had.
- Pins tui v0.13.0 (f67234d). Version 0.8.0.

## 0.7.0

The program uses what tui 0.11.0 added for its 0.6.0 findings, and `auto` means what it says. With `--scale
off --links off --sync off` the bytes written for the viewer, the editor and the source pane are identical to
0.6.0 (checked on 75 scripted steps under a pty); with scale and links on the emulator screens (text, links,
scaled headings still on the screen) match 0.6.0 step for step. The goldens did not change. Built and tested
against m31 v0.6.0 and tui v0.11.0 (e156723).

### Changed

- Scaled headings (OSC 66) go through `Loop.after_frame`: `Screen` is the hook, and the bytes are in the same
  write as the frame (after the cells, before the cursor, inside the synchronized update) instead of
  `Loop.queue_output` on the next read, up to 50 ms late. The hook answers a heading only when `is_full` is true,
  when the heading is new, moved or changed, or when the frame's diff wrote a cell of its block (a popup over it,
  closing); a frame that leaves them alone answers nothing, so one that changes nothing is not written. It keeps
  a copy of the frame it last answered for to know. Headings that were not touched are no longer re-sent after
  every frame (87600 bytes of the pty script with scale on became 86750). `Screen.build_overlay` and
  `Screen.loop` are gone.
- Mouse and motion reports are asked of the loop (`should_report_raw_mouse`, `should_report_hover`) instead of
  `MOUSE_ON` and `HOVER_ON` appended by hand to `enter` and `leave`. The same bytes on the wire, in the same
  places; the reports still reach `App.handle` unrouted. `MDV_cli.make_loop` is public (tested).
- Pins tui v0.11.0 (e156723). Version 0.7.0.

### Fixed

- `--links auto` and `--scale auto` meant off (the capability was set to `mode == "on"`). `auto` is now what the
  environment says, as it was for `--sync auto`: links except on Terminal.app and dumb terminals, scaled
  headings on kitty. `on` and `off` are exact. It applies under `--cat` and `--dump` too when the flag is
  given; without a flag nothing changed.

### Added

- `tests/t_frame.m31` (the hook: first frame, identical frame, `is_full`, change elsewhere, popup over a heading
  and closing, scrolled away and back, a moved heading, scale off), `tests/t_loop.m31` (entry and exit bytes,
  the on/off/auto function), 26 `--links` and `--scale` checks in `tests/test_cli.sh` against made-up
  environments, and `--links`, `--scale` and the no-redundant-OSC 66 checks in `tests/pty_e2e.py`.

## 0.6.0

The program moves onto tui 0.10.0 and deletes its private copy of the loop. With `--links off --scale off
--sync off` the bytes written for the viewer, the editor and the source pane are identical to 0.5.0 (checked on
75 scripted steps under a pty); the goldens did not change. Built and tested against m31 v0.6.0 and tui v0.10.0
(73c226e).

### Changed

- `MDV_loop` is gone. The program runs on `TUI_app.Loop.run_with`: `App.handle` is the `Handler`, `App.tick`
  (every 250 ms) the `Ticker` that notices a file changing, the escape wait is the loop's `tick_ms` (50 ms), keys
  come from `Loop(input_fd: INPUT_AUTO)` and the same keys, mouse modes and one frame per event as before.
- A copy (`y`, a link that cannot be opened) is `Loop.copy` (OSC 52, `copy_limit` 60000): cut at a character
  instead of a byte count, the same bytes for text under the limit. `App.outbox`, `copy_sequence` and
  `Host.take_output` are gone.
- Hyperlinks (OSC 8) are marks on the cells (`Buffer.link`) and no longer bytes written after the frame, so
  a popup drawn over a link takes the link off (the old overlay made the popup's cells a link). Off exactly as
  before where the terminal is Terminal.app or dumb, or with `--links off`.
- Scaled headings (OSC 66) are queued with `Loop.queue_output` after each render. They reach the terminal on
  the next read, at most 50 ms after the frame (the loop has no hook after a frame).
- `docs/DESIGN.md`: the loop section, the capabilities decision for DECRQM, the gaps hit in tui.
- Pins tui v0.10.0 (73c226e).

### Added

- Synchronized output (DEC mode 2026): frames are written inside the markers once the terminal has answered
  the query, so one is never seen half drawn; one that does not answer gets the frames it got before.
  `--sync on|off|auto`; asked only of terminals that are neither Terminal.app nor dumb (`Caps.has_sync`).
- `CHANGELOG.md`.

## 0.5.0 (2026-10-16)

- The command line speaks Oro's grammar: `--version`, `--completions bash|zsh|fish`, the short forms `--c`
  and `--w`, an epilog, an integer range on `--width`; a bad value of `--theme`, `--scale`, `--links`,
  `--colors` or `--mode` is a usage error (exit 2) where `--theme` used to warn and fall back to dark.
  `install.sh` takes `--release`, `--prefix`, `--libc`, `-uninstall`, `--help`, `--version`.
- Builds against m31 v0.6.0.
- Tests: the goldens are hermetic (no environment leaks in), a double click is sent as one write, line width is
  measured in characters (BSD awk).

## 0.4.0 (2026-10-16)

- A light markdown editor: Preview, Source and Live panes, caret, selection, mouse (click, drag, double and
  triple click), undo groups, cut, copy and paste with the system clipboard and OSC 52, bracketed paste, find
  and replace (`Ctrl-R`), a command palette, a toolbar, save and save as, prompts for unsaved changes and a
  file changed on disk, checkbox toggling.
- Markdown assists: list continuation and renumbering, Tab nesting, auto pairs and wrapping, fence auto-close,
  quote continuation, heading and inline shortcuts, pipe table alignment, optional smart typography (`--smart`).
- Changed keys in Preview: `Ctrl-f` is find (`PgDn` or `Space` page down), `Ctrl-h` is no longer back.

## 0.3.0 (2026-10-15; no tag)

- The page is designed: an H1 band (OSC 66 scaled text on kitty), H2 bar and rule, bullets by depth, task
  boxes, block quotes and callouts, code cards with a language chip and syntax colours, rounded tables with
  optional zebra rows, front matter, footnotes, strikethrough, links as OSC 8, a header with breadcrumb and
  buttons, an outline sidebar, a draggable scrollbar, mouse wheel, click and hover.
- Themes (dark, light, tokyonight, nightfox, gruvbox-material, plain) in 24-bit colour that folds down.
- New options: `--dump`, `--max-width`, `--scale`, `--links`, `--colors`, `--zebra`, `--numbers`, `--side`.
- Pins tui v0.8.0 and term-markdown v0.4.1.

## 0.2.1 (2026-10-15)

- Alpine/musl release assets; `install.sh`, a one-line install of the latest release for the OS and CPU.

## 0.2.0 (2026-10-11)

- Pins tui v0.5.0, whose modules live in `core/`, `app/` and `widgets/`; tui modules are imported by folder
  path.

## 0.1.1 (2026-10-10)

- Migrated to m31 0.4.0 (grouped-module imports, standard library renames); pins tui v0.4.0 and term-markdown
  v0.4.0.

## 0.1.0 (2026-10-10)

- The viewer: parse (term-markdown), lay out, view with vim keys; search, outline, links with a back stack,
  OSC 52 yank, auto-reload, `--cat` for a pipe, a text oracle and goldens, a pty end-to-end test.
