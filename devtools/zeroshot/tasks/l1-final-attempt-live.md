L1 — the scheme shows the final check's real retry count during a run

h1 (merged 68012c2) wraps final_verify and final_reverify in a loop of at most 2 executions and the scheme draws
`final check ↻2/2` when its observation carries `count` 2 on the loop (tui/scheme.py RETRY_LOOPS). No live code
feeds that count: `live.flow` only reports the final stage as running or waiting, so a user never sees the retry.

Reuse: the stored executions `live.observe` already walks (live.py, the `final_verify`/`final_reverify` branch and
the `repairs` counter); `base(node)` for prefixed names; `scheme.observation_from_flow` (the `review_loop.count`
pattern); the scheme's existing ↻ drawing, unchanged.

Write-set: terminal_planner/live.py, terminal_planner/tui/scheme.py, tests/test_live.py, tests/test_tui_scheme.py,
tests/test_tui_scheme_tab.py.

Acceptance criteria:
- L1 `live.flow` carries the final check's attempt: the number of executions of the running final check since the
  last repair (final_verify before any repair, final_reverify after one); None when no final check ran.
  Example: final_verify seen twice -> attempt 2; repair, then final_reverify once -> attempt 1.
- L2 `observation_from_flow` puts that attempt as `count` on the loop the running check sits in, so the scheme
  draws `↻2/2` on the final check box for attempt 2 and nothing for attempt 1. Example: a flow with the final
  check running at attempt 2 -> the drawn Scheme tab text has "final check ↻2/2".
- L3 Stored live records without the new data (older attempts) stay readable and draw as before.
  Example: a record written before this change -> `live.flow` returns attempt None and no error.

Non-goals (reviewers must not require): the review loop's count; the Activity pane wording; the engine's own
stored state; graph changes.

Conflict rule: if the stored executions cannot tell a final_verify from a final_reverify run, change nothing and
end with `conflict: <file:line> <evidence>`.

Risk: medium (live metadata read by the panel). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_live tests.test_tui_scheme tests.test_tui_scheme_tab tests.test_toolchain`: exit 0;
`python3 devtools/budget.py`: OK. Each new test fails with the attempt feed removed.
