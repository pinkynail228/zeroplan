K1c2 — plan and settings screens answer with buttons, not letters

No letter keys; Tab, Left/Right, Enter, Esc, arrows, PgUp/PgDn stay. Here:
tui/screens.py PlanScreen (:15, BINDINGS :18, offered :52, show_keys :87) and SettingsScreen
(:162; BINDINGS :163, offered/keys :192-237). Bars: catalog.py `tui_plan` :645-664, `tui_settings` :675-678.

Reuse: the K1c1 pattern in tui/modals.py (`Button` row in a `Horizontal`, `action_move` :35,
`on_button_pressed`, `catalog.label`), its CSS (zplan.tcss `#confirm-buttons`); `offered()`.

Write-set: terminal_planner/tui/screens.py, terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss,
terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_tui.py, tests/test_tui_milestones.py,
tests/test_tui_planning.py, tests/test_tui_plan_gate.py, tests/test_tui_polish.py, tests/test_tui_live.py,
tests/test_tui_chat.py, tests/test_tui_approve_card.py, tests/test_tui_language.py, tests/test_plan_override.py,
tests/test_tui_ready_card.py, tests/test_tui_canvas_files.py, tests/test_tui_draft_card.py,
tests/test_tui_reopen_fixes.py, tests/test_tui_split.py, tests/test_tui_stop_planning.py, tests/test_reference.py.

Acceptance criteria:
- C1 Plan screen: one button per offered action, in `offered()` order, labels from `tui_plan.*`; Enter on a
  button does what its old letter did; Tab/Left/Right move; Esc = back; letters and `?` do nothing.
  Example: proposal ready -> buttons «утвердить», «доработать», «отказаться», «подробнее»; `a` -> nothing;
  focus «утвердить», Enter -> plan approved (as `a` before).
- C2 The row follows `offered()`: when the offered actions change, the row is rebuilt; the focus stays on the same
  action if still offered, else the first button. Up/Down/PgUp/PgDn still scroll the plan body.
  Example: observing -> «журнал»; proposal -> focus «утвердить»; PgDn scrolls.
- C3 Settings screen: buttons for its offered actions (setup, login, recheck, roles); same keys as C1.
  Example: settings, `g` -> nothing; Tab to «проверить», Enter -> recheck runs.
- C4 Bars: `tui_plan` and `tui_settings` entries name buttons and Esc, no letter; REFERENCE.md regenerated
  (`catalog --write`). Example: the plan screen's key line shows Tab, Enter, Esc and no `[a]`.
- C5 The K1c1 invariant test also covers PlanScreen and SettingsScreen: no letter or `?` binding; each button
  matches an entry of its bar. Example: a `Binding("a", ...)` added to PlanScreen -> the test fails.

Tests: a letter press -> focus + Enter/Esc; an old bar-text assert is deleted, not rewritten.

Non-goals (reviewers must not require): RunScreen (K1c3); modals; LanguageScreen; the main screen;
setup/delivery/planning hint texts (K1d); the plain CLI; override reason, reject confirm past their button.

A test outside the write-set pressing a removed key -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` changed test modules + tests.test_reference
tests.test_toolchain, exit 0; quote `fasttest:` lines.
