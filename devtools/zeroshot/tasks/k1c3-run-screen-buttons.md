K1c3 — the run end screen answers with buttons, not letters

No letter keys; Tab, ←→, Enter, Esc, arrows, PgUp/PgDn stay. Here: tui/modals.py RunScreen (:314,
:323, `action_ids` :364, `offered_ids` :377, `next_line` :393, `action_act` :448, `action_act_g` :456).
Bar: catalog.py `tui_run` :612-632. The recoverable failed end (DELIVERY_KEYS_STATE) shows
`end.actions`, `end.back`.

Reuse: K1c1 in tui/modals.py (`Button` row in a `Horizontal`, `action_move`, `on_button_pressed`,
`catalog.label`, zplan.tcss `#confirm-buttons`); K1c2's row rebuild in tui/screens.py `ButtonScreen`
(`sync_buttons`, `rebuild_buttons`; screens imports modals, never the reverse).

Write-set: terminal_planner/tui/modals.py, terminal_planner/tui/zplan.tcss, terminal_planner/catalog.py,
docs/REFERENCE.md, tests/test_reference.py, tests/test_tui_failed_card.py, tests/test_tui_question_card.py,
tests/test_tui_milestones.py, tests/test_tui_split.py, tests/test_tui_polish.py, tests/test_tui_chat.py,
tests/test_tui_live.py, tests/test_tui.py, tests/test_process.py, tests/test_tui_merge_card.py.

Acceptance criteria:
- C1 One button per `action_ids()` entry in that order, plus «журнал» when `tailable()` and «подробнее»; labels
  from the catalog; Enter on a button does what its old letter did (resume or check for the `g` pair, answer or
  new attempt for `t`); Tab/Left/Right move; Esc closes; letters and `?` do nothing.
  Example: a finished attempt offering merge and diff -> «влить», «изменения», «подробнее»; `m` -> nothing;
  focus «влить», Enter -> merge requested (as `m` before).
- C2 The recoverable failed end shows the delivery catalog's actions as buttons in its order, then its back.
  Example: failed_recoverable -> «продолжить», «новая попытка», «план», then the back button; Enter on
  «продолжить» resumes.
- C3 `set_end` with other offered actions rebuilds the row; focus stays on the same action if still offered,
  else the first button; Up/Down/PgUp/PgDn scroll the body.
  Example: focus «изменения», set_end offering diff and leave -> focus stays on «изменения»; PgDn scrolls.
- C4 The `Дальше:` line and the `tui_run` bar name buttons, Tab, Enter and Esc, no `[letter]`; REFERENCE.md
  regenerated (`catalog --write`). Example: a finished attempt -> the key line shows Tab, Enter, Esc, no `[m]`.
- C5 The invariant test (test_tui.py :871) covers RunScreen too: no letter or `?` binding; buttons are catalog
  entries. Example: `Binding("m", ...)` added to RunScreen -> the test fails.

Non-goals (reviewers must not require): other modals and screens; the plain CLI and its line menus; setup/delivery/planning hint texts (K1d); the delivery catalog's own keys in the line UI.

Tests: a letter press -> focus + Enter. A test outside the write-set pressing a removed key -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` changed test modules, tests.test_reference,
tests.test_toolchain: exit 0.
