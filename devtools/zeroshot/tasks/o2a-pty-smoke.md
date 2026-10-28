O2a-mini repair — the PTY smoke tests pass through the new start screen

O2a-mini (terminal_planner/tui/start.py, cli.py `main`) opens a full-screen start screen before the main one on a
real terminal. Its gate (fasttest on 9a58d25) failed 2 tests that launch `zplan` on a PTY and wait for the main
screen: tests.test_tui.PtySmokeTests test_screen_shows_the_panes_and_ctrl_q_exits_cleanly (tests/test_tui.py:214)
and test_an_exception_still_restores_the_terminal (:225); both time out on the start screen's card «Открыть этот
проект / Другая папка / Выйти».

Write-set: tests/test_tui.py.

Acceptance criteria:
- C1 Both tests answer the start screen first (Enter on the highlighted «Открыть этот проект», after its text is
  on screen) and then check what they checked before, unchanged. Example: the pty script waits for «Открыть
  этот проект», sends Enter, waits for «Разговор с архитектором», sends Ctrl+Q -> exit 0, terminal restored.
- C2 One more PTY test in PtySmokeTests: an empty folder (no .git) -> the start screen's «Здесь нет Git-проекта»;
  Esc -> exit 0 and the folder still has no .git. Example: tmp dir, `zplan`, Esc -> status 0, no .git.

Non-goals (reviewers must not require): changes to start.py or cli.py (product behaviour is accepted); other PTY
tests; Linux runs.

A product change found necessary to make C1 pass -> `conflict:` naming it.

Risk: low (tests only, inheriting the PTY smoke coverage). DoD: `python3.13 devtools/fasttest.py` tests.test_tui,
tests.test_tui_start: exit 0.
