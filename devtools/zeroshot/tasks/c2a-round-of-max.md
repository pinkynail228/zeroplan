C2a — the live panel says "раунд N из M" for the task under review (slice C2 of docs/CHAT_RELEASE_JTBD.md, job J2).

Goal: while a milestone attempt runs, the live panel shows which repair round the current task is in and the bound of the submitted review loop, so the owner knows whether to wait. Today the panel (terminal_planner/live.py:201-228, `panel_lines`) shows active roles and times only; the round appears just as a journal line (live.py:158-164) and the bound is not shown anywhere.

Data reach: round N = `live["workers"]` with `live["task"]` set (live.py:159-161; counted only for executions proven to belong to a task). Bound M = `runs.review_rounds(revision)` (runs.py:355), the same value runs.py:672/717 passes into the submitted graph; the attempt's revision is `self.authority.state["revisions"][r["plan_revision"] - 1]` (as runs.py:715). Delivery.panel(r) (delivery.py:786) has `r`; Delivery holds `self.authority` (delivery.py:322-323); no new store read.

Write-set: terminal_planner/live.py (`panel_lines` gains an optional `rounds=None` argument, default keeps today's output), terminal_planner/delivery.py (`panel` passes it), docs/USER_FLOW.md only if it quotes the panel lines, their tests.

Acceptance criteria:
- A1 With `live["task"]` set and `live["workers"]` = N ≥ 1, the panel has one extra line "  <task>: раунд N из M" right after "Сейчас работают", M from `review_rounds` of the attempt's revision.
- A2 Without a proven task (`live["task"]` None) or for the planner panel, the output is exactly today's.
- A3 Tests: panel_lines with and without `rounds`; one Delivery.panel test with a revision whose frozen `task_rounds` is 2 (shows "из 3") and one without a frozen profile (shows "из 4").

Non-goals (reviewers must not require): a cycle strip, stage time, per-round verdicts, TUI layout changes, changing how rounds are counted.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_tui_milestones tests.test_tui_live tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
