D3 — on a card with buttons, ← and → move between its buttons, so Enter presses what the owner sees picked (soak S6)

Soak of rc1 2026-10-29: on the plan card the owner pressed → to pick "no"; → switched the right pane's tab
(MainScreen bindings `left`/`right` -> `view(±1)`, priority, tui/app.py:915-916; `action_view` at :2116 switches
whenever the input is empty), and Enter then pressed the card's default first button «approve» (app.py:1903-1906
-> `card.press_choice()`; default `choice = 0`, cards.py:168). Card buttons are laid out in a row (cards.py:185) but
move only with ↑↓ (`action_pick` :2061 -> `Card.move_choice`, cards.py:201).

Reuse: `Card.move_choice`, `keyed_card` (card_host.py:148), the `view` action's guard.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/cards.py, tests/test_tui_card_keys.py,
tests/test_tui_milestones.py, tests/test_tui_activity_pane.py, tests/test_tui_canvas_files.py, tests/test_tui_follow.py,
tests/test_tui_flow.py, tests/test_process.py, tests/test_tui_hints.py, tests/test_tui_narrow.py,
tests/test_tui_planning.py, tests/test_tui_polish.py, tests/test_tui_run_command.py, tests/test_tui_scheme_tab.py,
tests/test_tui.py

Old tests: change only a ← or → press made while a keyed card with two or more buttons is shown (the write-set has every
test file that presses ← or →; a modal's own → binding, e.g. the bootstrap modal's «configure», is not a card and stays). S6 is the owner's decision: such a press reaches the tab the K2 way (focus the
pane first) and the test keeps its intent.

Acceptance criteria:
- K1 While the chat input has focus and is empty and a keyed card with two or more buttons is shown, ← and → move
  that card's choice (wrapping) and the pane's tab stays. Example: plan card, choice approve -> → -> choice is the
  second button, tab unchanged; Enter presses the second button.
- K2 Everywhere else ← and → act as today: the input with text moves its cursor, no keyed card or a card with one
  button switches tabs, the pane with focus switches tabs. Example: no card, empty input, → -> next tab.
- K3 The key bar or the card's hint names ←→ for the buttons while K1 applies. Example: the plan card shows a hint
  containing "←→".

Non-goals (reviewers must not require): ↑↓ behaviour, the palette, other screens and modals, the card's default
choice.

Conflict rule: if a test outside the write-set pins other arrow behaviour, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (keys). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py tests.test_tui_card_keys
tests.test_tui_chat_input tests.test_tui_approve_card tests.test_tui_milestones tests.test_tui_activity_pane tests.test_tui_canvas_files tests.test_tui_follow
tests.test_tui_flow tests.test_tui_hints tests.test_process tests.test_tui tests.test_docs
tests.test_toolchain`: exit 0; budget.py: OK. New K1 and K3 tests fail on today's code.
