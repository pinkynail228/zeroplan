# v2g — every planning operation leaves one receipt, written at the one plan-job seam

docs/PLAN_UX.md V2, seventh task; builds on v2a-v2f (`Controller._result`, `results`, `on_result`, results.json).
The plan operations all run through `Controller._plan_job(label, work, done)` (tui/controller.py): the owner's
goal (`start_planning`, label "start"), send (`submit_plan`), restart, revise (`revise_plan`), the planner's stop (`stop_planner`), and the architect's `zplan_edit_plan` and
`zplan_revise_plan`, which the socket thread posts as plan jobs too;
the attempt's feedback to the plan (`to_plan`) is an attempt job (`_job`). Only approve/override/reject leave results
(v2a). So "the goal was saved but not sent: readiness", "r3 sent", "the planner stop was requested" never reach
zplan_status.

Change:
- `_plan_job` takes an optional `operation`; when given, the job writes one result from its own end: operation
  plan (the goal), send, restart, revise, feedback, edit or stop_planner; subject {"revision": N} of the revision the
  plan service holds after the job (None when none); outcome sent (the service's kind sent or ready), unsent (a
  readiness block: the failing checks' lines), requested (stop_planner), refused (a Blocked: family and line) or
  failed. `to_plan` writes the same result (operation feedback) in its own job. Origin owner, or architect with the bridge request id for the two tools. The approval jobs keep v2a's own
  results (no second one). Profile, details, record and changes jobs are not operations: no result.
- Architect results reach the owner once through `on_result`; the owner's screens keep their own notes.

Write-set: terminal_planner/tui/controller.py, tests/test_bridge.py, tests/test_tui_planning.py

Acceptance criteria:
- A1 Goal not sent. Example: the owner's goal with the origin check failing -> results[-1] {operation plan, outcome
  unsent, origin owner, subject revision 1}, its lines hold the origin item.
- A2 Architect revise. Example: zplan_revise_plan of r1 -> {operation revise, outcome sent, origin architect,
  request id, subject revision 2}; the status line shows it once.
- A3 Planner stop. Example: stop_planner -> {operation stop_planner, outcome requested}.
- A4 No noise. Example: opening plan details, reading the record and an approval -> no result besides v2a's one
  approval result.

Non-goals (reviewers must not require): the plan screens' notes and wording, the goal-draft card, persistence
changes, the details reader.

Conflict rule: if a test outside the write-set pins `_plan_job`'s signature, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (architect contract). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_tui_planning
tests.test_consent tests.test_tui_hints tests.test_plan_override`: exit 0.
