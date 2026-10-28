O3 repair — two regression tests' fake screens know the new palette pick

O3 (terminal_planner/tui/app.py `MainScreen.on_input_submitted` now calls `self.palette_pick(line)`) passed its
own DoD, but its gate (fasttest on 7defef6) failed 2 tests that call `on_input_submitted` on a `_FakeScreen`:
tests.test_tui_commands CommandWiringTests test_regression_an_unwired_command_keeps_the_input
(tests/test_tui_commands.py:443) and tests.test_tui_run_command RunCommandWhileRunning
test_regression_a_typed_run_while_a_stage_runs_reaches_the_busy_branch (tests/test_tui_run_command.py:124), both
`AttributeError: '_FakeScreen' object has no attribute 'palette_pick'`.

Write-set: tests/test_tui_commands.py, tests/test_tui_run_command.py.

Acceptance criteria:
- C1 Each `_FakeScreen` gets what `on_input_submitted` reads now (a `palette_pick` with no highlighted row and a
  `remember` that keeps nothing), so both tests check what they checked before, unchanged. Example: the unwired
  command test -> the input keeps its text, as before.

Non-goals (reviewers must not require): changes to app.py or palette.py (product behaviour is accepted); new tests.

A product change found necessary to make C1 pass -> `conflict:` naming it.

Risk: low (tests only). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_commands, tests.test_tui_run_command,
tests.test_tui_palette: exit 0.
