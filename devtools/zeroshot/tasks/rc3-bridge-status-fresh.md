RC3 — the architect's `zplan_status` answers with the state of now (0.6.0 smoke 2026-10-25, defect 2, high)

Incident: ~/zs-pause/dogfood/findings-2026-10-25.md #2. The architect's status tool returned empty rows without a
token and reported M1 `running` while the screen showed blocked / awaiting merge; the architect then said it could
not request the merge. Cause: `Controller._bridge_status` (tui/controller.py:604) returns the previous `self._rows`
and only queues a coalesced refresh, so every answer is one status behind, and "rows unavailable" on the first.

Reuse: `_bridge_action` (controller.py:631-660): post one job, wait on a `threading.Event` on the socket thread,
bounded; `_rows_job` (:615) as the job that reads the rows.

Write-set: terminal_planner/tui/controller.py, tests/test_bridge.py.

Acceptance criteria:
- C1 Fresh: a status request posts the rows job and waits for it (bounded, on the requesting thread, never the
  worker), then answers from the rows that job just read. Example: milestone M1 moves from running to
  awaiting_merge, then the architect asks status -> its rows show M1 `awaiting_merge` with M1's token, in the
  same answer.
- C2 First call: the first status of a session answers real rows, not "rows unavailable", when the job finishes
  within the bound. Example: an approved plan with one ready milestone -> the first status lists it.
- C3 Bound: when the worker is busy past the bound (2 s), the answer is the last rows plus `"stale": true`; no
  exception, the worker is never blocked. Example: a worker job held 5 s -> status returns within ~2 s with
  `stale: true`.
Joint example: worker idle -> fresh rows, no `stale` key; worker held -> last rows, `stale: true`.

Non-goals (reviewers must not require): changes to `_rows_job`'s fields, to the tool list or to architect.py;
pushing rows on run events; a configurable bound.

Conflict rule: tests in tests/test_bridge.py that pin "rows unavailable" after the first call (:12, :214, :425,
:665) change with C2; any other file pinning it -> `conflict:` with path:line before any edit.

Risk: medium (a bounded wait on the socket thread). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
