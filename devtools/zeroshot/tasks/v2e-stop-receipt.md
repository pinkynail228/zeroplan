# v2e — a stop leaves one receipt that says "requested", never "stopped"

docs/PLAN_UX.md V2, fifth task; builds on v2a-v2d (`Controller._result`, `results`, `on_result`, results.json).
A stop is a request: `MilestoneRuns.stop` (runs.py:1416) saves `stopping` and force-stops; the attempt reaches
`stopped` later, seen by observation. Two entries: the owner's (app.py `action_stop_milestone` -> `Controller.stop_run`,
`run_note` "Not stopped: ..." or STOP_REQUESTED) and the architect's `_stop_tool` (a static method today; it returns
the row's status). Neither leaves a result, so the architect cannot tell "I asked" from "it stopped" except by rows.

Change:
- Every stop call leaves one result, operation "stop", subject {"milestone", "attempt"}: outcome requested when
  `stop` ran (line: "Stop of M1 requested; the run ends shortly."), refused when the attempt moved or is not
  active (family and line), failed for any other error. Origin owner (with nothing else) or architect (with the
  bridge request id). The later `stopped` state is not a result: it is the row's state, with its reason (v1a).
- The owner's path writes `run_note` from the result's lines (STOP_REQUESTED stays the requested note's text);
  the architect's result reaches the owner once through `on_result`.
- TOOL_RULES (architect.py): a stop result says requested; the row's state says stopped.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, terminal_planner/architect.py,
tests/test_bridge.py, tests/test_architect.py

Acceptance criteria:
- A1 Requested, not stopped. Example: zplan_stop of M1's running attempt -> results[-1] {operation stop, outcome
  requested, origin architect, subject M1 + attempt}, and its lines never say "stopped".
- A2 Owner stop. Example: /stop M1 confirmed -> one result, origin owner, outcome requested; run_note unchanged in
  wording.
- A3 Refusal. Example: zplan_stop with another attempt's run id -> outcome refused with family and line; nothing
  stopped.
- A4 The architect is told. Example: the first prompt holds the requested/stopped line; the method file
  stays within 4600 bytes.

Non-goals (reviewers must not require): the stop confirmation (V3), a bare /stop with several runs, the planner's
stop, resume.

Conflict rule: if a test outside the write-set pins run_note after a stop, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (architect contract, screen). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_architect tests.test_consent tests.test_tui_live tests.test_tui_milestones`: exit 0.
