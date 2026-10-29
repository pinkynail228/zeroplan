# d3c — the arrows' tab cycle is tied to the card's key, not its widget (critic rel083b finding 2)

Critic rel083b 2026-10-29 on 72a6ea3: d3b stores the keyed card's widget (`tab_cycle_card = card`,
tui/app.py:2179) and compares identity (app.py:2160). Two failures follow:
- a card refreshed in place (same `spec.key`, new widget: tui/card_host.py:65-80; the plan card re-renders when
  its `HH:MM` crosses a minute, tui/card_kinds.py:669) silently ends the cycle, so the next → moves the card;
- cycle over card A, then keyed card B appears and goes away: the latch still names A, so when A is keyed again →
  switches tabs instead of moving A's choice.

Change: keep the keyed card's `spec.key` (a str) in `tab_cycle_card` and compare keys. `sync_card_keys`
(tui/card_host.py:159, called whenever a card comes or goes) clears it when the keyed card's key differs from the
stored one (including no keyed card). Typing, Tab, Enter and Esc keep clearing it as today.

Reuse: `action_view`, `keyed_card`, `sync_card_keys`, `Card.move_choice`, tests/test_tui_card_keys.py.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, tests/test_tui_card_keys.py

Acceptance criteria:
- A1 A refresh of the same card keeps the cycle. Example: wide, two file tabs, plan card keyed: Tab, →, then the
  plan card is re-rendered with the same key (new widget), → -> file tab 2 shows; the card's choice is unchanged.
- A2 Another keyed card ends the cycle for good. Example: cycle over card A (Tab, →); keyed card B appears, then
  is closed; A is keyed again; → -> A's choice moves, the tab stays.
- A3 d3 and d3b behaviour holds otherwise. Example: tests.test_tui_card_keys passes unchanged apart from new tests
  and the attribute's type.

Non-goals (reviewers must not require): ↑↓, the narrow layout's cycle, modals, other screens, the card's default.

Conflict rule: if a test outside the write-set pins the widget identity, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (keys). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py tests.test_tui_card_keys
tests.test_tui_canvas_files tests.test_tui_activity_pane tests.test_tui_run_command tests.test_tui_milestones
tests.test_tui tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New A1 and A2 tests fail on today's code.
