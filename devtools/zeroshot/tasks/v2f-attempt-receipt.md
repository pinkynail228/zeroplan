# v2f — continuing an attempt or making a new one leaves one receipt naming both attempts

docs/PLAN_UX.md V2, sixth task; builds on v2a-v2e (`Controller._result`, `results`, `on_result`, results.json; v2d
made the start receipt, including the consent yes for a start). Three operations create or continue an attempt:
resume (owner: `resume_run`; architect: `_resume_tool`), new attempt (owner: `new_attempt`; architect:
`_rebrief_tool`) and the owner's answer to a question (`answer`); the owner's three go through `_creating`
(tui/controller.py), the architect's resume and rebrief may become a `ConsentRequest` whose yes runs `_grant`. The
screen's words come from app.py `attempt_job` (`run_note`: "Not done: ...", the readiness lines, "... Screen
refreshed."). None of them is in zplan_status `results`.

Change:
- Every call of these three operations leaves one result: operation resume, rebrief (the owner's new attempt and
  the architect's rebrief both) or answer; subject {"milestone", "attempt"} of the attempt it acted on, plus
  "created" the attempt number that runs now (equal to "attempt" for a resume) when it ran; outcome done, asked
  (with the ConsentRequest id), refused (readiness, a moved attempt or profile: family and lines) or failed. Origin
  owner (the owner's paths and the consent yes, with the request id) or architect (with the bridge request id).
- `attempt_job` writes `run_note` from the result's lines, the same words as today; the architect's results reach
  the owner once through `on_result`.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, tests/test_bridge.py,
tests/test_consent.py

Acceptance criteria:
- A1 Resume. Example: the owner continues M1 attempt 2 -> results[-1] {operation resume, outcome done, origin owner,
  subject M1, attempt 2, created 2}; a readiness block -> outcome refused, run_note in today's words.
- A2 New attempt linked. Example: zplan_rebrief of M1 attempt 1 at auto -> {operation rebrief, outcome done, origin
  architect, attempt 1, created 2}; at manual -> asked with the request id, and the owner's yes -> done, origin owner,
  created 2.
- A3 Answer. Example: the owner answers M1's question -> {operation answer, outcome done, created} the new attempt.
- A4 One per call. Example: one resume -> exactly one new result.

Non-goals (reviewers must not require): the confirmations (V3), accept, plan revision, the card layouts.

Conflict rule: if a test outside the write-set pins run_note after these actions, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (architect contract, screen). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_consent
tests.test_tui_live tests.test_tui_milestones tests.test_tui_failed_card`: exit 0.
