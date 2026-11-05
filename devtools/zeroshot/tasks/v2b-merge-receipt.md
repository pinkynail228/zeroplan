# v2b — a merge leaves one receipt, and the owner sees the architect's merge in zplan's words

docs/PLAN_UX.md V2, second task; builds on v2a's results (`Controller._result`, `results`, tui/controller.py).
Soak of 0.9.0-rc1 F4: after the architect's own merge the owner got no zplan line; "No merge check or critic ran"
reached only the architect, which reworded it. Merge paths: the owner's card and end screen call `Controller.merge`
(its `settle` reposts internal `waiting`/`pacing` jobs while the merge critic runs; only the last answer is final);
the architect calls `_merge_tool` (returns `{milestone, kind, line}` or asks).

Change:
- `_result` takes a `subject` dict (approval keeps {"revision": N}); a merge's subject is {"milestone", "attempt"}.
- Every merge call leaves one result, operation "merge": the owner's in `merge`'s final `settle` (never for
  waiting, pacing or closing), the architect's in `_merge_tool` with its request id. Outcome: done when it landed,
  asked when the level leaves it to the owner, refused otherwise with the refusal's family; lines: the merge's own
  line(s), including "No merge check or critic ran ..." when it applies.
- A result whose origin is architect is shown to the owner once, as zplan's own line on the status line, through
  one worker-callable Controller hook (as `on_merge_wait` is wired, app.py:2471). The owner's own results are not
  repeated (their card or end screen already says it).

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, tests/test_bridge.py,
tests/test_tui_merge_wait.py

Acceptance criteria:
- A1 The architect's merge reaches the owner. Example: gate off, zplan_merge of M1 lands -> results[-1] {operation
  merge, outcome done, origin architect, subject M1 + attempt}; the status line shows zplan's line with "No merge
  check or critic ran".
- A2 One receipt per call. Example: the owner's merge waits two critic slices, then lands -> exactly one merge
  result, outcome done, origin owner; no line repeated on the status line.
- A3 Refusal and ask. Example: a failing check -> outcome refused, family merge.checks_failed; at manual the tool
  -> outcome asked.
- A4 Approval unchanged. Example: v2a's approval results keep subject {"revision": N}.

Non-goals (reviewers must not require): persistence, other operations, the history row's state, the merge card.

Conflict rule: if a test outside the write-set pins the status line after a merge, change nothing in it and end
with `conflict: <file:line>`.

Risk: medium (architect contract, screen). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_tui_merge_wait tests.test_tui_merge_card tests.test_tui_chat_after_merge tests.test_tui_stale_lines`:
exit 0.
