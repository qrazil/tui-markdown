# tui-markdown 0.2.0: tui 0.5.0 and the import paths

Version 0.2.0, from master c2c6f94 (v0.1.1). **Nothing a user sees changed**:
the command line, the keys, the rendering (every golden file is byte for byte
what it was) and the exit statuses are the same. The minor bump is because the
`deps` pin of tui moves to v0.5.0 (1609d91), whose modules live in `core/`,
`widgets/` and `app/` folders, so every tui import path changed. The term-markdown
pin is unchanged (a55a55e). No `MDV_*` module, function or type was renamed.

| module | old import | new import |
|---|---|---|
| `TUI_geometry`, `TUI_style`, `TUI_buffer`, `TUI_text`, `TUI_widget` | `import tui.TUI_x;` | `import tui.core.TUI_x;` |
| `TUI_menu`, `TUI_outline` | `import tui.TUI_x;` | `import tui.widgets.TUI_x;` |
| `TUI_app`, `TUI_diff` | `import tui.TUI_x;` | `import tui.app.TUI_x;` |

Files that changed: `MDV_app`, `MDV_cat`, `MDV_cli`, `MDV_layout`, `MDV_loop`,
`MDV_render`, `MDV_theme`, `MDV_viewer`, `MDV_wrap`, `tests/t_viewer.m31` and
the build note in `scripts/build.sh`. This repository stays flat (14 `MDV_*`
files at the root next to the entry file `tui_markdown.m31`): folders are worth
adding above about 20 modules.

---

# tui-markdown -> m31 0.4.0

Version 0.1.1, from master 2f45842 (v0.1.0). **Nothing a user sees changed**:
the command line, the keys, the rendering (every golden file is byte for byte
what it was) and the exit statuses are the same. The patch bump is because the
source moved to m31 0.4.0's standard library names and now needs **m31 v0.4.0
or later** (and tui and term-markdown 0.4.0); it does not build with older
compilers. `m31c lint` reports no finding.

What changed, from m31's `CHANGELOG.md` ("Moving a program from 0.3.x"):

| where | old | new |
|---|---|---|
| import (`MDV_wrap`) | `import unicode;` | `import text.unicode;` |
| import (`MDV_app`) | `import base64;` | `import encoding.base64;` |
| `tui_markdown.m31`, `tests/t_oracle.m31` | `os.args()` | `os.arguments()` |
| `MDV_cli` | `given.flag("cat")` (`args.Parsed`) | `given.is_flag_set("cat")` |
| `MDV_cli`, `MDV_loop` | `term.Size` `.cols` | `.columns` |
| `MDV_keys` | `key.has(term.CTRL)` | `key.has_modifiers(term.CTRL)` |
| `MDV_loop` | `term.reader(fd: ..)` | `term.reader(descriptor: ..)` |

No public name of this program's own modules (`MDV_*`) changed: they already
followed `docs/naming-decision.md`. CI (`M31_REF`) and the build notes name
m31 v0.4.0. The `deps` pins of tui and term-markdown move to their 0.4.0
commits.
