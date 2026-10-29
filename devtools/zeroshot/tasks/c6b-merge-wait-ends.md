C6b — the merge wait ends on the refusal's own family, its verdict always reaches the owner, and it never spins (release critic rel082b 1-3)

Release critic rel082b on 800c26e (xhigh, probes reproduced each): `Controller.merge` (tui/controller.py:1464-1486)
waits while `catalog.tag("merge.critic_pending") in merged.line`, so a `milestone.critic_blocked` refusal whose
findings quote that tag is retried for ever (1). `settled` (tui/app.py:3925-3933) returns without showing the
verdict when the end modal was closed during the wait, and the status line keeps "reviewing ... merges when it says
go" (2). A native watch that exits at once becomes `ObservationDetached` -> pending (delivery.py:1229-1238), and the
loop re-posts with no pause (3).

Reuse: `delivery.Merge` (delivery.py:328-334), `refusal`, `Blocked.family`, `CRITIC_SLICE`, `say_note`,
`merge_wait_shown`, the c6 tests in tests/test_tui_merge_wait.py.

Write-set: terminal_planner/delivery.py, terminal_planner/tui/controller.py, terminal_planner/tui/app.py,
tests/test_tui_merge_wait.py

Acceptance criteria:
- W1 The wait keys on the refusal's family, never on its text. Example: `Merge` carries the family of the
  `Blocked` it came from (default ""); a `milestone.critic_blocked` refusal whose line contains
  ` [code: merge.critic_pending]` ends the wait with that refusal after one call.
- W2 The final verdict of a waited merge reaches the owner when the end modal is gone: the status line or note shows
  it, and the waiting text is gone. Example: pending, modal dismissed, then critic_blocked -> the note shows the
  block text; `merge_waiting` is None and no line says "merges when it says go".
- W3 Slices are paced: two merge calls of one wait start at least one slice apart (`CRITIC_SLICE`, injectable for
  tests), however fast a pending refusal returns, and the project lock is not held during the pause. Example: a fake
  delivery whose pending returns at once, slice 0.2 s -> three calls take >= 0.4 s; a refresh queued in the pause
  runs before the next call.
- W4 Today's c6 behaviour stays. Example: the c6 tests pass unchanged (one confirm, merge after pending, a second
  confirm says "Already waiting", no "Not done" for pending).

Non-goals (reviewers must not require): the critic itself, the architect's merge path, the plain CLI, a timeout of
the wait.

Conflict rule: if a test outside the write-set constructs `Merge` positionally in a way the new field breaks, change
nothing in it and end with `conflict: <file:line>`.

Risk: medium (merge path). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_merge_wait
tests.test_merge_gate tests.test_tui_cards tests.test_tui_milestones tests.test_tui tests.test_live
tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New W1-W3 tests fail on today's code.
