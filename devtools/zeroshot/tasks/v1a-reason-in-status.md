# v1a — the architect's status carries why an attempt stopped, the same facts the owner's card shows

Soak of v0.9.0-rc1, R7 and R9 (docs/PLAN_UX.md V1): the run card showed "Reason: «Required check `python3 -m pytest
-q` remains blocked … No module named pytest»" while the architect wrote "The available status omits the reason …
What blocker is shown in the run?", and the owner retyped it. `zplan_status` rows come from `_rows_job`
(tui/controller.py:758-771): id, state, attempt, run_id, token and, for awaiting_merge, merge fields; the failure
card gets its text through `controller.open_run` -> `Delivery.end` (controller.py:1545-1557), and `Delivery.view`
(delivery.py:1057) builds the same `EndView` (heading, status, body, family) without exporting anything.

Change: in `_rows_job`, a row in a stopped state other than awaiting_merge (blocked, failed, failed_recoverable,
needs_owner, conflict, stopped) gets `"reason": {"heading", "status", "body", "family"}` from `Delivery.view` of its
latest attempt: the body cut to 12 lines of at most 300 characters each, passed through the existing scrub the
architect's reads use; active rows and awaiting_merge are unchanged. TOOL_RULES (architect.py:78-108) gains one
line: a stopped milestone's reason is in zplan_status (rows[].reason); read it, never ask the owner what the screen
shows.

Write-set: terminal_planner/tui/controller.py, terminal_planner/architect.py, tests/test_bridge.py,
tests/test_architect.py

Acceptance criteria:
- A1 The reason reaches the architect. Example: fixture, M1 blocked with the final check's finding "No module named
  pytest" -> zplan_status `rows[0].reason.body` contains "No module named pytest" and `rows[0].state` is blocked.
- A2 Nothing exports or grows. Example: M1 awaiting merge -> its row has no `reason` and no export ran; a body of
  40 long lines -> 12 lines of at most 300 characters.
- A3 The architect is told. Example: the first prompt holds the rows[].reason line; the method file stays within
  4600 bytes.

Non-goals (reviewers must not require): readiness and profile in the status (later tasks), the operation results,
the card's own fetch, the details reader, wording of the reason.

Conflict rule: if a test outside the write-set pins the exact keys of a status row, change nothing in it and end
with `conflict: <file:line>`.

Risk: medium (architect contract). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_architect
tests.test_consent tests.test_tui_failed_card`: exit 0.
