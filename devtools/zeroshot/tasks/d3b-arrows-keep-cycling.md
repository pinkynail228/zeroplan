D3b — once the arrows cycle tabs, they keep cycling every tab, even where the focus falls back to the chat input
(critic rel083 finding 2)

Critic rel083 2026-10-29: in the wide layout, with two file tabs and a keyed card of two or more buttons: `Tab`
focuses the pane, `→` shows the first file tab, `restore_tab_focus` (tui/app.py:1568-1575) puts the focus back on
the empty input because the pane is hidden, and the next `→` moves the card (d3, `action_view` app.py:2147-2151)
instead of the tab. The second file tab is unreachable that way, against docs/USER_FLOW.md:89 ("`←`/`→` cycle every
open tab").

Reuse: `action_view`, `restore_tab_focus`, `keyed_card`, `Card.move_choice`, tests/test_tui_card_keys.py.

Write-set: terminal_planner/tui/app.py, tests/test_tui_card_keys.py

Acceptance criteria:
- A1 An arrow that switched the tab makes the next arrows switch tabs too, while the input stays empty and the owner
  presses no other key. Example: wide, two file tabs, plan card keyed: Tab, →, →, → -> the tabs shown are file 1,
  file 2, then the next tab in the cycle; the card's choice is unchanged.
- A2 Typing in the input, `Tab`, Enter, Esc, or a new keyed card ends that, so ←→ move the card again under d3's
  rule. Example: after A1, Tab back to the input, → -> the card's choice moves, the tab stays.
- A3 d3 K1-K3 hold as today. Example: tests.test_tui_card_keys passes unchanged apart from new tests.

Non-goals (reviewers must not require): ↑↓, the narrow layout's cycle, modals, other screens, the card's default.

Conflict rule: if a test outside the write-set pins the card moving after an arrow tab switch, change nothing in it
and end with `conflict: <file:line>`.

Risk: low (keys). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py tests.test_tui_card_keys
tests.test_tui_canvas_files tests.test_tui_activity_pane tests.test_tui_run_command tests.test_tui_milestones
tests.test_tui tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New A1 and A2 tests fail on today's code.
