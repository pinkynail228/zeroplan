# v2h — one result seam: the per-operation helpers fold into one, and any exception is a result

docs/PLAN_UX.md V2, last task. v2a-v2g grew one helper per operation in tui/controller.py: `_start_result`,
`_stop_result`, `_attempt_result`, `_merge_result`, `_plan_result` (each: `_result` + "notify `on_result` when the
origin is architect"), two inline approval writers, `_fate` and `_plan_fate`, and a worker-shared field
`_tool_verdict` that carries a plan tool's verdict from `_run_tool` to the plan-job seam. Two gaps the workers
named: an exception other than Blocked/OSError/ValueError in `consent` (start, resume, rebrief grants) leaves no
result.

Change (behaviour kept, except the gap):
- One writer: `_result(operation, subject, origin, outcome, family, lines, request=None)` also notifies `on_result`
  for an architect origin; every operation calls it directly; the per-operation wrappers go. One `_fate(error)`
  for every operation (Blocked -> refused with its family, anything else -> failed).
- The plan tools' verdict reaches the plan-job seam as the job's own return value; `_tool_verdict` goes.
- Any exception in a call that writes results leaves one failed result before it propagates (consent included).
- Subjects, outcomes, lines, origins, request ids, results.json and the screen's words stay exactly as they are.

Write-set: terminal_planner/tui/controller.py, tests/test_bridge.py, tests/test_consent.py,
tests/test_tui_merge_wait.py (calls `_merge_result`, :290)

Acceptance criteria:
- A1 Same results. Example: every existing results test passes, changed only to call `_result` where it called a removed helper; an architect approve, merge, start, stop,
  rebrief and revise each still reach `on_result` once, the owner's never.
- A2 The gap. Example: the owner's yes to a start request whose grant raises RuntimeError -> one result, outcome
  failed, family unknown, origin owner, the request id; the error still reaches the caller.
- A3 One writer. Example: `_start_result`, `_stop_result`, `_attempt_result`, `_merge_result`, `_plan_result`,
  `_plan_fate` and the `_tool_verdict` attribute no longer exist in controller.py.

Non-goals (reviewers must not require): new operations, persistence changes, the screen, wording.

Conflict rule: if a test outside the write-set calls a removed helper, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (refactor of the architect contract). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_consent tests.test_tui_planning tests.test_tui_live tests.test_tui_merge_wait tests.test_tui_hints`: exit 0.
