# v2d — a milestone start leaves one receipt, whatever started or refused it

docs/PLAN_UX.md V2, fourth task; builds on v2a-v2c (`Controller._result`, `results`, `on_result`, results.json).
A start has four entries today, each with its own words: the owner's /run or button (`preview_start`, then
`start_run`; app.py `preview_milestone` and `begin_run` write `run_note`: "Not started: ...", the readiness lines
under NOT_STARTED_BELOW, the profile-changed pair), the architect's `_start_tool` (tui/controller.py; at an asking
level it becomes a `ConsentRequest`), and the owner's yes to that request (`consent` -> `_grant`). None is in
zplan_status `results`, so the architect learns a start's fate only from the rows.

Change:
- Every start call leaves one result, operation "start", subject {"milestone", "attempt"} (the previewed attempt
  number): outcome done (it started), asked (a ConsentRequest; its id in the result), refused (readiness blocked,
  the plan or attempt moved, the profile changed after the preview: the family and the existing lines), failed (any
  other error). Origin owner for preview_start/start_run and for the consent yes (with the request id), architect for
  `_start_tool` (with the bridge request id). A preview that is only shown is not a result.
- The owner's /run path writes `run_note` from its result's lines (the same words as today); the architect's
  results reach the screen through `on_result` once, as v2b's merge does, and the pending "starting M1…" line keeps
  its own `on_start_wait` rule.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, tests/test_bridge.py,
tests/test_consent.py

Acceptance criteria:
- A1 Owner start. Example: /run of M1 starts attempt 1 -> results[-1] {operation start, outcome done, origin owner,
  subject M1 + 1}; a readiness block -> outcome refused, and run_note shows the same lines as before.
- A2 Architect start. Example: zplan_start at auto -> outcome done, origin architect; at manual -> outcome asked with
  the ConsentRequest id; the owner's yes then -> a second result, outcome done, origin owner, the same request id.
- A3 Profile moved. Example: the profile changes between preview and start_run -> outcome refused, the profile-change
  line kept; nothing started.
- A4 One per call. Example: one /run that starts -> exactly one new result.

Non-goals (reviewers must not require): resume and new attempt (next tasks), stop, the pending line's wording,
the card layouts.

Conflict rule: if a test outside the write-set pins run_note after a start, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (architect contract, screen). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_consent
tests.test_tui_live tests.test_tui_stale_lines tests.test_tui_milestones tests.test_tui_ready_card`: exit 0.
