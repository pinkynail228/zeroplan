I3e1 — the readiness error card: a red card with the reason and the exact fix command when work cannot start
(0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i3e1). Today readiness failures are "! ..." lines from `block_lines()`.

Card contract: devtools/zeroshot/tasks/card-contract.md (read first; builder `cards.error_card(key, at, task, text,
buttons, fix=None)`, red).

Today (app.py): a blocked start sets the blocked note (`blocked_note`), `slash_state` -> `error`; the failing checks
come from readiness items (`app.checks`); the no-origin item `origin` (setup.py ~426-430) carries `git remote add
origin https://github.com/OWNER/REPO.git` in its detail. A recheck is `request_check`; `got_checks` gets the result
(the PlanScreen-only `recheck_blocked` does nothing on MainScreen).

Change: kind `ready`, key `ready:<failing check keys joined by +>`. Source: one card while a start is blocked by
failing checks, for both the goal and the plan start; text = the failing lines (≤6), `fix` = the origin command when
the origin check fails (one helper reading it from the item's detail), else None. Buttons: «новая попытка»
(`card.error_retry`) sends `/retry` -> `request_check`; «подробнее» (`card.error_details`) sends `/details` -> the
existing readiness detail. `/retry` and `/details` are card-only entries already on main; add only your
`CARD_ROUTES` rows. When the recheck passes, the blocked state is gone and the source drops
the card.

Write-set: terminal_planner/tui/app.py, docs/USER_FLOW.md (readiness card paragraph), tests/test_tui_ready_card.py
(new).

Acceptance criteria (joint example: a blocked-start Outcome carrying the failing origin check injected at the
controller/UI boundary — the fixture skips the real origin check, planning.py ~46, 266-268, do not change that;
120x40):
- A1 A red card shows the origin reason and, on its own line, exactly `git remote add origin
  https://github.com/OWNER/REPO.git`; visible at 80x24.
- A2 «новая попытка» calls `request_check` once; with the recheck passing the card is gone after the render.
- A3 With the recheck still failing the card stays (same key, not duplicated).
- A4 «подробнее» opens the readiness detail.
- A5 A failing check other than origin shows its reason with no fix line.

Non-goals (reviewers must not require): failed stages and failed planning (run i3e2), changing setup.py checks,
inline history cards, other card kinds.

DoD: `python3.13 devtools/fasttest.py tests.test_tui_ready_card tests.test_tui_card_hooks tests.test_tui_commands
tests.test_tui_planning tests.test_toolchain tests.test_reference` exit 0; quote its `fasttest:` lines.
