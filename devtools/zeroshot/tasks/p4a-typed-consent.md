# p4a — a typed command or a pressed card button is the consent: no second yes/no for run, resume, approve

Owner decision F3 (docs/PLAN_0.9.md, P4; dogfood 2026-10-25b: every action asked twice). Today a typed /run or a
run card opens a yes/no confirm (`self.confirm(...)`, tui/app.py:3497 and :3514 after a profile change), resume
asks "Continue M1 (attempt N)?" (:3560) and the plan screen's approve asks
"Approve plan rN? ..." (tui/screens.py:205).

Change: these four paths act at once. The /stop and the end screen's merge confirmations stay. A profile changed since the preview still
refuses the start with today's "Not started: ..." note and a fresh preview line; the owner starts again with /run.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/screens.py, tests/test_tui_run_command.py,
tests/test_tui_commands.py, tests/test_tui_live.py, tests/test_tui_plan_gate.py, tests/test_tui_split.py,
tests/test_tui.py, tests/test_tui_chat.py, tests/test_tui_approve_card.py, tests/test_tui_planning.py,
tests/test_tui_failed_card.py, tests/test_tui_milestones.py (its `begin_run` helper, inherited by other modules)

Acceptance criteria:
- A1 /run starts at once. Example: approved plan, M1 ready, type `/run` -> no confirm screen; the run line shows M1
  starting.
- A2 Resume and plan-screen approve act at once. Example: a recoverable M1 -> `/retry` resumes it
  with no "Continue M1" question; plan screen «approve» -> the plan is approved with no "Approve plan r1?" question.
- A3 Stop still asks. Example: M1 running, `/stop` -> the yes/no confirm opens; «no» leaves it running.
- A4 A changed profile still stops a start. Example: preview, then the profile file changes -> `/run` gives "Not
  started: ..." and nothing starts.

Non-goals (reviewers must not require): the end screen's merge confirm (tui/app.py:3944), the ConfirmScreen class, the line UI (cli.py), chat cards' own
buttons, wording elsewhere.

Conflict rule: if a test outside the write-set drives one of the removed confirms, change nothing in it and end
with `conflict: <file:line>`.

Risk: medium (UI flow). DoD: `python3.13 devtools/fasttest.py tests.test_tui_run_command tests.test_tui_commands
tests.test_tui_live tests.test_tui_plan_gate tests.test_tui_split tests.test_tui tests.test_tui_chat
tests.test_tui_approve_card tests.test_tui_planning tests.test_tui_failed_card tests.test_tui_stop_planning
tests.test_tui_milestones tests.test_tui_merge_card tests.test_tui_canvas_files tests.test_tui_merge_wait`: exit 0.
