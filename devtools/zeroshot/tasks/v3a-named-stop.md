# v3a — a stop that names one run acts at once; a bare /stop with several runs asks which

docs/PLAN_UX.md V3, owner decision Q4 (2026-10-30). Today every milestone stop asks "yes/no" first
(`action_stop_milestone`, tui/app.py, `self.confirm(Delivery.stop_text(row.token), stop)`), and `/stop` ignores its
argument (card_kinds.py:84 routes it to `stop_running_row`, app.py:1984, which takes the selected running row or
the first running one). With parallel runs a bare /stop may stop a run the owner did not mean.

Change:
- `/stop M1` stops M1's running attempt at once, no confirmation; an id that is not running answers one status line
  "M1 is not running; nothing to stop." and stops nothing.
- A bare `/stop` with exactly one running milestone stops it at once; with several it stops nothing and shows one
  line naming them and the command for each ("Several runs: /stop M1, /stop M2"); with none it keeps today's
  planner-stop path.
- The panel's own stop key on a selected running row is a named stop: at once.
- The stop itself, its receipt (v2e) and `run_note` wording are unchanged; the planner's stop keeps its confirmation.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_kinds.py, tests/test_tui_commands.py,
tests/test_tui_milestones.py (p4a pins "/stop still asks", :222), tests/test_tui_live.py

Acceptance criteria:
- A1 Named. Example: M1 and M2 running, `/stop M2` -> M2's stop is requested with no confirmation screen; M1 runs on.
- A2 Ambiguous. Example: M1 and M2 running, bare `/stop` -> nothing stopped, the line names /stop M1 and /stop M2.
- A3 Single. Example: only M1 running, bare `/stop` -> M1's stop requested, no confirmation.
- A4 Not running. Example: `/stop M3` with M3 done -> the "not running" line, nothing stopped.

Non-goals (reviewers must not require): the planner's stop, other confirmations, the stop receipt, wording beyond
the lines above.

Conflict rule: if a test outside the write-set pins the stop confirmation, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (owner screen). DoD: `python3.13 devtools/fasttest.py tests.test_tui_commands tests.test_tui_live
tests.test_tui_milestones`: exit 0.
