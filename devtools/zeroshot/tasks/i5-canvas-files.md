I5 — a project file or the last stage's diff opens as a closable read-only tab in the canvas (0.5.2,
docs/RELEASE_0.5.2_PLAN.md, run i5; owner scenario C: "files and diffs in the canvas, read-only, only when nothing runs").

Why: in 0.5.1 a diff opens only in a modal over the run screen and a file cannot be seen at all; the approved screen
(docs/ui-redesign/WORK_SCREEN.md, lab `devtools/ui-lab/work.py` `_render_view`) shows them as extra canvas tabs beside
Сейчас and План, closed with esc. The renderables exist and are tested: `terminal_planner/tui/viewer.py`
`resolve(root, name)` (raises `ViewError(id, values)` for a path outside the project or missing), `file_view(path,
max_bytes, words)`, `diff_view(text, words)`; `words` is `strings.text`.

Today (terminal_planner/tui/app.py; run s0 moved modals into modals.py, MainScreen/ZplanApp stay in app.py): the
canvas is `TabbedContent#right` with `TAB_LIVE` and `TAB_PLAN`, ←→ cycle them (`MainScreen.action_view`); a finished
stage's diff comes from `self.controller.diff(token, self.deliver(...))` and is shown by `ZplanApp.diff_shown` in a
`TextScreen(..., diff=True)` modal.

Change:
- Two methods on MainScreen, the only entry points (run i3a wires `/open FILE` and `/diff` to them; do not add slash
  wiring here): `open_file_tab(name)` and `open_diff_tab()`.
- `open_file_tab(name)`: `viewer.resolve(project root, name)`, then add a TabPane after План titled with the file name
  (elided to fit), holding a VerticalScroll with the `file_view` renderable, and make it active. A `ViewError` opens no
  tab and shows `strings.text(error.id, **error.values)` on the status line. Opening a file already open activates its
  tab. At most 3 file tabs: opening a 4th closes the oldest.
- `open_diff_tab()`: use `app.selection().token` for the selected finished attempt (refuse with the status-line text
  if there is none); capture its milestone for the callback; call the existing `controller.diff` through `deliver`;
  open/replace one tab titled «Изменения <milestone>» with `diff_view("\n".join(outcome.lines))` only when
  `outcome.kind == 'diff'`; any other outcome or an error shows its lines/text on the status line, no tab.
- Only when nothing runs (guard: current planner activity and any snapshot row with `active`, not `planner_pane()`,
  which keeps finished progress): while the planner or a stage runs, both methods open nothing and the status line says the
  `note.not_now` text; a file/diff tab already open stays.
- Escape precedence (both runs i2 and i5): hide the palette and clear its input; otherwise close the active file/diff
  canvas tab and return to the tab that was active before; otherwise the existing cancel-turn action.
- ←→ cycle over all open
  tabs; Сейчас and План never close. The run screen's diff modal stays as it is.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, docs/USER_FLOW.md (canvas tabs),
tests/test_tui_canvas_files.py (new), tests/test_tui_milestones.py (only ArrowTabTests, if the tab cycle assertion
needs the new rule). Do not edit viewer.py, strings.py, slash.py, catalog.py, modals.py, controller, engine.

Acceptance criteria:
- A1 `open_file_tab("README.md")` at 120x40 and 80x24 shows a third tab with the file's first lines numbered and
  makes it active; `open_file_tab("../x")` and a missing name open no tab and show the viewer's refusal text.
- A2 With a fixture finished stage selected, `open_diff_tab()` shows «Изменения …» with the fixture diff lines; with no finished
  stage it opens nothing and says why.
- A3 While a fixture stage runs, and separately while the planner is active, both open nothing and show the not-now text.
- A4 esc closes the active file tab and returns to the previous tab; ←→ cycle includes the open file tabs; a 4th file
  closes the oldest.
- A5 Tests per preamble: at most two whole-app tests in tests/test_tui_canvas_files.py (A1+A4 in one, A2+A3 in the
  other); viewer logic is already tested in tests/test_tui_viewer.py.

Non-goals (reviewers must not require): slash commands, editing, a file picker, search, syntax themes, diffs of
running stages, translations.

DoD: `python3.13 devtools/fasttest.py $(ls tests/test_tui*.py | sed 's#tests/#tests.#;s#\.py$##') tests.test_live
tests.test_layout tests.test_fixture_scope tests.test_toolchain tests.test_reference` with exit 0.
Parallel note: run i2-commands edits the chat input, the bottom bar and adds a command dispatcher in MainScreen at the
same time; do not move or reformat code outside the canvas tabs, esc handling for them, and the two new methods. 
Shared areas: i2 owns the input, the bar, the dispatcher and PaneTabTests; i5 owns the file/diff canvas tabs and ArrowTabTests. CSS changes use separate selectors; docs/USER_FLOW.md changes go in separate sections.
