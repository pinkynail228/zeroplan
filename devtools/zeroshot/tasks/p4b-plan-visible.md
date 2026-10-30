# p4b — the plan card lists the milestones before zplan approves the plan by itself

Walk 2026-10-29 step 6 and rc1 W4 (owner decision Q3): at level auto the plan card says "The plan is checked and
covers the goal. The architect will approve it itself; to stop it, choose “revise”." (`card.plan_auto_text`,
tui/strings.py:252) but shows no milestone, so the owner has ~30 s to object to a plan they cannot see without
/view. The proposal's milestones are already in the plan snapshot the card reads (planning.py:647).

Change: the plan card (auto and the owner's own approval alike) lists each milestone as `M1 <title> · N tasks`,
at most 5 lines, then `…and N more`; titles are cut to the card's width with `…`.

Write-set: terminal_planner/tui/card_kinds.py, terminal_planner/tui/strings.py, tests/test_tui_auto_plan_card.py

Acceptance criteria:
- A1 The auto card shows the plan. Example: level auto, a proposed plan with M1 "Add --lines" (2 tasks) and M2
  "Docs" (1 task) -> the card holds the lines "M1 Add --lines · 2 tasks" and "M2 Docs · 1 task" above its buttons.
- A2 Long plans stay bounded. Example: 7 milestones -> 5 lines and "…and 2 more"; at 80x24 the card's buttons stay
  visible.

Non-goals (reviewers must not require): the plan tab, /view, the approval timing, other languages' strings beyond a
copy of the English pattern, the merge card.

Conflict rule: if a test outside the write-set pins the plan card's exact lines, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (card text). DoD: `python3.13 devtools/fasttest.py tests.test_tui_auto_plan_card tests.test_tui_approve_card
tests.test_tui_strings`: exit 0.
