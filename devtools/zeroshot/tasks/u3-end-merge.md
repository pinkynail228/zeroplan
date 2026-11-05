# u3 — the run end screen's «merge» merges at once, like the merge card and /merge

Owner decision F3 (the typed command or pressed button is the consent), deferred from p4a: the run end screen's
«merge» still opens a yes/no confirm "Merge the result of M1 into main?" (`self.confirm(end.question, merge)`,
tui/app.py:3970; the text is `Delivery.merge_question`, delivery.py:1142), while the merge card and `/merge` merge
at once. The merge's own wait for its check (begin_pending, the merge-wait flow) stays as it is.

Change: «merge» on the end screen calls the same `merge()` it calls after «yes» today, with no confirm; nothing
else about the merge changes (pending line, critic wait, receipts, refusals).

Write-set: terminal_planner/tui/app.py, tests/test_tui_milestones.py, tests/test_tui_chat.py,
tests/test_tui_live.py, tests/test_tui_merge_wait.py, tests/test_process.py

Acceptance criteria:
- A1 One press merges. Example: M1 awaiting merge, `/attempt` -> end screen -> «merge» -> the merge starts (the
  pending line shows) with no "Merge the result of M1 into main?" question; the run lands as today.
- A2 Refusals stay visible. Example: the merge refused (a profile changed) -> the end screen shows "Not done: ..."
  as today.

Non-goals (reviewers must not require): the line UI's own `[m]` confirm (cli.py), `Delivery.merge_question` itself,
/stop's confirm, the merge card.

Conflict rule: if a test outside the write-set answers the end screen's merge confirm, change nothing in it and end
with `conflict: <file:line>`.

Risk: medium (UI flow). DoD: `python3.13 devtools/fasttest.py tests.test_tui_milestones tests.test_tui_chat
tests.test_tui_live tests.test_tui_merge_wait tests.test_process tests.test_tui_merge_card`: exit 0.
