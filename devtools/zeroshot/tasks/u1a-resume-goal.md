# u1a — once the missing prerequisite is fixed, the goal the owner sent goes to planning without asking again

Soak 2026-10-30 N2: the goal draft is refused for a missing GitHub origin; the owner runs `git remote add`, presses
«try again» on the readiness card: nothing starts and "Not started ... ! No GitHub origin" stays; only pressing the
goal draft card's «yes» again plans. Today `start_goal` (tui/app.py:3143) stores the refused readiness items in
`goal_block` and the goal is kept by the planning service; `got_checks` (app.py:2836-2853) clears `goal_block` once
every check passes but sends nothing.

Change: `start_goal` remembers the refused submission (the goal text and its card key). When a readiness slice
comes back with every check passing while that submission is remembered, the app calls `start_goal` with it once,
and forgets it; a new goal, a sent plan or a closed draft card forgets it too. A check that still fails keeps
today's card and note.

Write-set: terminal_planner/tui/app.py, tests/test_tui_ready_card.py

Acceptance criteria:
- A1 Fixed, then planned. Example: a goal refused for no origin; `git remote add origin
  https://github.com/o/r.git`; «try again» -> the readiness slice passes -> planning starts for the same goal; the
  ready card and "Not started" note are gone.
- A2 Only once, only that goal. Example: after A1 another passing re-check starts nothing more; a goal refused, then
  the owner sends another goal -> only the new one is sent.

Non-goals (reviewers must not require): a refused milestone start (later task), the architect's turn, readiness
items themselves, wording.

Conflict rule: if a test outside the write-set needs a refused goal to stay unsent after a passing re-check, change
nothing in it and end with `conflict: <file:line>`.

Risk: medium (UI flow, spends a planner run). DoD: `python3.13 devtools/fasttest.py tests.test_tui_ready_card
tests.test_tui_draft_card tests.test_tui_chat tests.test_tui_chat_dedupe`: exit 0.
