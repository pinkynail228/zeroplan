A10c — a refused `/approve` from the plan card says why once on the main screen, not twice

Orchestrator check 2026-10-28 after a10b: `decide` now reports its error through `say_note` (tui/app.py:3157,
the main screen's `run_note`), and the plan card's `settled` still adds the same line as `chat_note`
(`approve_plan_card`, tui/card_kinds.py:681-683, `status_note` app.py:2111). A stale card's `/approve` shows
"Not done: ..." twice; the docstring (card_kinds.py:671-676) says the plan screen's lines "are not drawn here",
no longer true.

Reuse: `decide`'s own note (app.py:3150-3175); `close_card` and "card.plan_done" on success (unchanged); the
real-app test shape of tests/test_tui_failed_card.py:590-621 (RejectedCardRefusalTests, run_test).

Write-set: terminal_planner/tui/card_kinds.py, tests/test_tui_failed_card.py, tests/test_tui_approve_card.py
(only its A5 pin, test_tui_approve_card.py:332-333: its stand-in `decide` writes no note, so the pin moves to the
real `decide`'s main-screen line or to "the card stays, chat_note unchanged").

Acceptance criteria:
- P1 On an error `settled` keeps the card open and adds no line of its own; the docstring says `decide` reports
  the refusal on the main screen. Example: a plan card for r1 while the store's current proposal is r2 (or any
  `decide` error), `/approve` -> the "Not done: " line appears once on the main screen's rendered text, the card
  stays, `chat_note` is unchanged.
- P2 Success is unchanged: the card closes with "card.plan_done" and the approval line shows.
  Example: r1 proposed, `/approve` from the card -> the card gone, "Plan r1 approved." on the main screen once.

Non-goals (reviewers must not require): the wording of any line, other cards, `decide`, the plan screen, docs.

Conflict rule: if a test outside the write-set expects the card's own `chat_note` on a refused approval, change
nothing and end with `conflict: <file:line>`.

Risk: low (one message path). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_failed_card
tests.test_tui_approve_card tests.test_tui_card_keys tests.test_tui_planning tests.test_tui_split tests.test_toolchain`: exit 0;
`python3 devtools/budget.py`: OK. The P1 test fails on today's card_kinds.py (the line shows twice).
