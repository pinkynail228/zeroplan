A9 — after an approval or a start the canvas shows the work once, unless the owner chose a tab since (F9)

Orchestrator map 2026-10-29: the canvas tab is picked once (`choose_tab`, tui/app.py:1471-1483) and never moved
by the app. Approvals: `decide` (app.py:3166-3182), the architect's tool (controller.py:879-899) and autonomy auto,
the last two seen only by the snapshot poll (`got_snapshot`, app.py:2652). Starts: `begin_run` -> `started`
(app.py:3338-3354) and the architect's `zplan_start` (controller.py:842-867), seen by `follow_runs`
(app.py:3534-3551; owner runs never enter `run_seen`). No flag tells the owner's tab switches from the app's.

Reuse: `show_tab` (app.py:1503); `follow_runs`/`run_seen`; the started line (app.py:3352); TabbedContent's
TabActivated for clicks.

Write-set: terminal_planner/tui/app.py, tests/test_tui_follow.py (new), tests/test_tui_milestones.py,
tests/test_tui_live.py, tests/test_tui_polish.py, docs/USER_FLOW.md (the three tests: only their pins on the old rule —
milestones 1769-1808, live 448 and polish 751 go back to Plan as plan_tab does, live 934 expects the F4 line)

Acceptance criteria:
- F1 A newly approved revision N shows the Plan tab once; a newly started run R shows the Scheme tab once, by
  any path (owner, architect tool, autonomy auto), keyed by N and R so the owner's path and the next poll
  switch once. Example: Scheme shown, `decide` approves r2 -> Plan; the poll then reports r2 approved -> no move.
- F2 The owner's own tab choice (arrows, Tab, a label click, /scheme, /status, view tabs) after their last chat
  send or command wins: the app then moves nothing. Example: owner sends a message, presses right to Plan, the
  architect starts M1 -> the tab stays on Plan, the started line still shows.
- F3 What the first snapshot already holds (approved revision, running runs) is a baseline, not an event, so a
  restart moves nothing. Example: start with r3 approved and M1 running, owner on Plan -> Plan stays.
- F4 A start from the architect or autonomy shows the same started line as the owner's start, once per run.
  Example: the poll adopts M1's run -> "M1 started · plan r2 · attempt 1" once on the main screen.
- F5 USER_FLOW's tab sentence (USER_FLOW.md:53) says the rule. Example: tests.test_docs passes.

Non-goals (reviewers must not require): new tabs, PlanScreen, journal lines moving the tab, wording.

Conflict rule: if a test outside the write-set pins that the tab never moves on an approval or a start, change
nothing in it and end with `conflict: <file:line>`.

Risk: medium (screen focus). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_follow
tests.test_tui_live tests.test_tui_polish tests.test_tui_milestones tests.test_tui_activity_pane tests.test_tui_planning tests.test_tui_approve_card
tests.test_tui_failed_card tests.test_tui_split tests.test_tui_scheme_tab tests.test_docs tests.test_toolchain`:
exit 0; budget.py: OK. New F1-F4 tests fail on today's app.py.
