I3e2 — the failure card: a red card for a failed stage or a failed planning run, with retry and details (0.5.2,
docs/RELEASE_0.5.2_PLAN.md, run i3e2). Today a failed stage pops RunScreen; a failed plan is a pane line.

Card contract: devtools/zeroshot/tasks/card-contract.md (read first; builder `cards.error_card(key, at, task, text,
buttons)`, red).

Today (app.py): rows in `failed`, `failed_recoverable`, `blocked`, `stopped`, `conflict`; a failed planning run is
`snapshot.plan.kind == "failed"` or `snapshot.status in ("run_failed", "proposal_invalid")`. `controller.open_run`
returns the EndView (`body`, offered `actions`: `resume`, `new_attempt`, `check`); RunScreen runs them through
`modal_action`; planning restarts through the existing restart-planning path.

Change: kind `failed`, keys `failed:<milestone>:<attempt>` and `failed:plan:<version>`. Source: one card per such
row (text = the EndView body, fetched once per key off the event loop and cached, ≤6 lines) and one for a failed
planning run (text from the plan view). «новая попытка» (`card.error_retry`) sends `/retry`: a stage -> the first
offered of `resume`, `new_attempt`, `check`, run modal-less; no offered action -> no retry button; planning ->
restart planning. «подробнее» sends `/details`: RunScreen for a stage, PlanScreen for planning. `/retry`, `/details`
are card-only entries already on main; add only your `CARD_ROUTES` rows.
A started retry closes the card with `card.error_retried` (new id «↻ новая попытка HH:MM», en/ru/zh). The row states
above join `AUTO_END_CARDS`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/strings.py, docs/USER_FLOW.md (failure card paragraph),
tests/test_tui_failed_card.py (new), tests/test_tui_milestones.py (only assertions that RunScreen pops at a failed
end: open it with [o] instead).

Acceptance criteria (joint example: fixture M1 attempt 1 ends `failed_recoverable` with body «Модель не ответила
за 10 минут (exit 1)», 120x40):
- A1 No RunScreen pops; a red card «! Ошибка · M1» shows that line, «новая попытка», «подробнее»; visible at 80x24.
- A2 «новая попытка» calls `resume_run` once and the card reads «↻ новая попытка HH:MM»; for `failed` it calls
  `new_attempt` once.
- A3 «подробнее» opens RunScreen for M1.
- A4 A failed planning run r2 shows a card whose retry restarts planning once.
- A5 A stage whose EndView offers none of the three actions shows the card with «подробнее» only.

Non-goals (reviewers must not require): readiness errors (run i3e1), removing RunScreen, inline history cards,
other card kinds.

DoD: `python3.13 devtools/fasttest.py tests.test_tui_failed_card tests.test_tui_card_hooks tests.test_tui_milestones
tests.test_tui_planning tests.test_toolchain tests.test_reference` exit 0; quote its `fasttest:` lines.
