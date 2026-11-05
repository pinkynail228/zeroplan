# v2a — a plan approval leaves one receipt; the screen never promises a start

docs/PLAN_UX.md V2, first task (Astra's consult: the Controller is the one writer, one receipt per operation call).
Soak of 0.9.0-rc1 F10: after /approve the note said "zplan starts the first stage." and nothing started. The note is
a guess: `decide` (tui/app.py:3365-3380) reads the level and the chat phase before any start, keeps it in
`approval_note` and clears it in `approval_note_over` (app.py:2793). The architect's own approval
(`_approve_tool`, tui/controller.py) leaves no trace the screen or a later zplan_status reads.

Change:
- The Controller keeps results: one `{seq, operation, subject, outcome, family, lines, origin}` per approval call,
  written in the job that ran it: `operation` approve/override/reject, `subject` {"revision": N}, `outcome` done,
  refused or asked, `family` the refusal's catalog family ("" otherwise), `lines` at most 4 scrubbed lines,
  `origin` owner (approve_plan, override_plan, reject_plan) or architect (`_approve_tool`, plus the bridge request
  id). Memory only, the last 20 kept; zplan_status gains `results` (oldest first). No feed event, no wake.
- `decide` shows the result's own line ("Plan rN approved", "... despite the check"), nothing about starting; the
  next step is what the snapshot shows. `approval_note` and `approval_note_over` go.
- TOOL_RULES (architect.py): the outcome of an action is in zplan_status `results`.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, terminal_planner/architect.py,
tests/test_bridge.py, tests/test_tui_hints.py, tests/test_architect.py

Acceptance criteria:
- A1 No promise. Example: level auto, a ready chat, /approve of r1 -> the note is "Plan r1 approved." and holds no
  "starts"; the same at manual.
- A2 One receipt, both paths. Example: the owner's approve of r1 -> results[-1] {operation approve, outcome done,
  origin owner}; zplan_approve_plan of r2 -> {outcome done, origin architect, request id}; at manual the tool ->
  outcome asked.
- A3 A refusal is a receipt. Example: approving a stale revision -> outcome refused with family and line.
- A4 Bounded. Example: 25 approvals -> 20 results, seq increasing, no feed event written.

Non-goals (reviewers must not require): persistence, other operations, the details reader, the plan card.

Conflict rule: if a test outside the write-set pins the approval note or zplan_status keys, change nothing in it and
end with `conflict: <file:line>`.

Risk: medium (architect contract, screen). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_tui_hints tests.test_architect tests.test_consent tests.test_tui_planning`: exit 0.
