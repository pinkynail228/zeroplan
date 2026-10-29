C6 — an owner's merge waits for the merge critic itself and says so, instead of asking for /merge again (rc1 walk N1)

Orchestrator rc1 walk 2026-10-29 (supervised, real Codex): `/merge` of M1 answered after 9 s "Not done: ... repeat
the merge [merge.critic_pending]"; a second `/merge` showed nothing new for 10 minutes; a third merged at once. The
owner cannot tell a slow critic from a failure, and is the system's hands (class K1). Path: the TUI end modal's
merge (tui/app.py:3846-3849) -> `Controller.merge` (tui/controller.py:1463-1470) -> `Delivery.merge` -> one
critic slice of `CRITIC_SLICE` = 5 s (delivery.py:72-74) -> `Blocked(family="merge.critic_pending")`
(delivery.py:1230-1238); catalog text "[m] again" (catalog.py:322-323).

Reuse: `Delivery.merge` and its critic record as they are (the same record is observed again on each call),
`Controller._job` / `_acting`, the existing progress and note lines of the end modal.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, terminal_planner/tui/strings.py,
terminal_planner/catalog.py, tests/test_tui_merge_wait.py (new), docs/REFERENCE.md

Acceptance criteria:
- M1 A merge the owner confirmed that meets `merge.critic_pending` is not reported as "Not done": zplan calls the
  same merge again, slice after slice, until it lands, is refused for another reason, or the owner leaves zplan.
  Example: a fake delivery raising critic_pending twice then merging -> one owner confirm, three merge calls, the
  modal ends with the merged line; never "Not done".
- M2 While it waits, the modal and the status line say the merge check is reviewing the milestone and zplan merges
  when it says go. Example: after the first pending -> text contains "merge check" and the milestone id, no "[m]".
- M3 Between slices the project lock is free, so other owner actions are not blocked longer than one slice. Example:
  a refresh during the wait runs before the next merge call.
- M4 A second `/merge` or merge press while one waits starts no second merge and says it is already waiting.
  Example: two confirms -> merge calls come from one loop only.
- M5 Any other refusal (critic block, critic failed, checks failed) ends the wait with today's text. Example:
  pending then `milestone.critic_blocked` -> the modal shows the block text.

Non-goals (reviewers must not require): the architect's merge tool path, the plain CLI, the critic itself, a
timeout of its own (the critic run has one).

Conflict rule: if a test outside the write-set pins the "Not done" text for critic_pending in the TUI, change
nothing in it and end with `conflict: <file:line>`.

Risk: medium (merge path). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_merge_wait
tests.test_merge_gate tests.test_tui_cards tests.test_tui_milestones tests.test_tui tests.test_reference
tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New M1-M5 tests fail on today's code.
