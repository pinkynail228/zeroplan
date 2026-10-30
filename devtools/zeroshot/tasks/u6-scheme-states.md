# u6 — the scheme's nodes follow the run: steps behind it are done, a waiting worker shows no command

Soak 2026-10-30 N7 and rc1 walk N2: the Scheme tab shows "◌ worker · zsh" under a running task pick, and preflight
stays "◌ waiting" while the run is already past it. `observation_from_flow` (tui/scheme.py:599-631) marks
preflight, select_init and select_verify succeeded only while a task is picked and no pick runs (`flow.task`), and
puts the last command echo on the worker (`detail`) whatever the worker's state.

Change: once the run is past preflight (a pick runs, a task is picked, or any worker, reviewer or final state is
present) preflight is succeeded; while a later pick runs (`flow.round` set or a task was done before), select_init
is succeeded too. The worker's `detail` is set only while the worker is running.

Write-set: terminal_planner/tui/scheme.py, tests/test_tui_scheme.py

Acceptance criteria:
- A1 Steps behind the run are done. Example: flow `{"select": True, "round": 1, "worker": {"state": "waiting"}}` ->
  `observation_from_flow` gives preflight and select_init `succeeded`, select `running`.
- A2 A waiting worker carries no command. Example: flow `{"select": True, "worker": {"state": "waiting"},
  "command": "/bin/zsh -lc 'pytest -q'"}` -> the worker has no `detail`; with `"state": "running"` -> detail `pytest`.

Non-goals (reviewers must not require): the drawing, the legend, other nodes' wording, the live flow facts
(live.py), the activity pane.

Conflict rule: if a test outside the write-set pins preflight "idle" or a worker detail while waiting, change
nothing in it and end with `conflict: <file:line>`.

Risk: low (display). DoD: `python3.13 devtools/fasttest.py tests.test_tui_scheme tests.test_tui_scheme_tab
tests.test_tui_rb_fixes tests.test_tui_activity_pane`: exit 0.
