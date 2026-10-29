C6c — every verdict of a waited merge reaches the owner after the end modal closed, and no repeat starts once a quit began (release critic rel082c 1, 3)

Release critic rel082c on 346852c (xhigh, probes through the real Controller): `settled` (tui/app.py:3931-3938)
shows a detached verdict only for integrated, conflict, overlap and refused. A merge that waited, then met a changed
token, ends `stale`: `merge_waiting` is None but the visible note still says "zplan merges when it says go".
`blocked` (with its checks) is dropped the same way. Also a repeat queued behind a watch can reach `acting`
(tui/controller.py:1485-1490) after `begin_closing()` and call `Delivery.merge` once more (reproduced).

Reuse: `say_note`, `MOVED`, `NOT_STARTED_BELOW`, `FIX_KEY`, `summary`, `Controller.quit_begun`, the c6/c6b tests in
tests/test_tui_merge_wait.py.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/controller.py, tests/test_tui_merge_wait.py

Acceptance criteria:
- X1 With the end modal gone, every verdict kind of a merge replaces the waiting note with its own line. Example:
  pending, modal dismissed, then a `stale` outcome -> the note is the MOVED line (or "<M>: the run changed; screen
  refreshed."), never "merges when it says go"; a `blocked` outcome -> the note starts with the not-started text.
- X2 Once a quit began, a waiting merge calls `Delivery.merge` no more and ends with "zplan is closing; the merge
  was not repeated.". Example: pending, `begin_closing()`, then the queued repeat runs -> merge calls stay at one.
- X3 c6 and c6b behaviour stays. Example: the existing tests in tests/test_tui_merge_wait.py pass unchanged.

Non-goals (reviewers must not require): verdicts of non-merge actions with an attached modal, the critic, the plain
CLI, the architect's merge path.

Conflict rule: if a test outside the write-set pins the detached-modal behaviour of `settled`, change nothing in it
and end with `conflict: <file:line>`.

Risk: medium (merge path). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_merge_wait
tests.test_merge_gate tests.test_tui_cards tests.test_tui_milestones tests.test_tui tests.test_docs
tests.test_toolchain`: exit 0; budget.py: OK. New X1-X2 tests fail on today's code.
