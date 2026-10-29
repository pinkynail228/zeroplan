L2b — the login refused outside a terminal gets no "Login not finished; retry" hint after it

Orchestrator check 2026-10-28 after l2 (A2): `zplan login </dev/null | cat` prints the new line "zplan login needs
your terminal: run `zplan login` there yourself." and exit 2, then the CLI adds the generic hint "Login not finished;
retry zplan login. If device-code login is turned off ... [code: setup.login_failed]" (cli.py:1069, 1119,
`login_unfinished` cli.py:827). An agent reading it retries or blames device codes; the terminal line already said why.

Reuse: `setup.on_terminal` (setup.py:489, the test `login` now runs); `login_unfinished`'s existing "" cases
(Ctrl-C, a foreign home); tests/test_setup.py and tests/test_first_run_fixes.py fixtures (isolated HOME, fake codex).

Write-set: terminal_planner/cli.py, tests/test_setup.py, tests/test_first_run_fixes.py.

Acceptance criteria:
- H1 `login_unfinished` returns "" when `on_terminal()` is false, so neither `zplan login` (cli.py:1069) nor the
  TUI's sign_in (cli.py:1119) adds the hint after the terminal refusal. Example: `zplan login` with stdout a pipe,
  an isolated HOME -> output is exactly the one terminal line, exit 2, no "setup.login_failed".
- H2 In a terminal the hint stays as today. Example: both TTYs patched true, the fake codex login exits 1 -> the
  "Login not finished; retry zplan login." hint with "[code: setup.login_failed]".
- H3 The Ctrl-C and foreign-home cases are unchanged. Example: INTERRUPTED -> "", a non-owned home -> "".

Non-goals (reviewers must not require): setup.py, the wording of any login line, logout, doctor, docs, the TUI's
screens.

Conflict rule: if a test outside the write-set expects the hint after a TTY-less login, change nothing and end with
`conflict: <file:line>`.

Risk: medium (auth messages only). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_setup
tests.test_login_home tests.test_first_run_fixes tests.test_agent_activation tests.test_toolchain`: exit 0;
`python3 devtools/budget.py`: OK. Each new test fails on the old cli.py. Fake codex and an isolated HOME only.
