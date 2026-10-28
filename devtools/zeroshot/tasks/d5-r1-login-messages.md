D5 repair 1 — the failed-login messages on screen carry the device-code guidance.

Context: branch zs-d5-login-guide (candidate bcaec40) already updates the doctor auth line, the `setup.login_failed` catalog entry (English, terminal_planner/catalog.py:336-339) and the docs; keep them. Round 1 reviewers found that the messages the owner actually sees after a failed login stay retry-only, because the old brief excluded their files.

Data reach (checked by the orchestrator): the three displayed messages are literal strings at terminal_planner/cli.py:1018 ("Вход не завершён; повторите zplan login."), cli.py:1044 ("Вход не завершён; повторите [l] или zplan login.") and terminal_planner/tui/app.py:2968 ("Вход не завершён (код %s); повторите [l]."), each followed by `catalog.tag("setup.login_failed")`.

Write-set: terminal_planner/catalog.py (one new Russian constant beside the existing short message constants), cli.py (those two lines), tui/app.py (that one line), their tests.

Acceptance criteria:
- A1 One catalog constant holds the Russian guidance: if device-code login is turned off for the account, turn it on in the ChatGPT account security settings. All three messages use it; their retry hint and the tag stay as they are.
- A2 One test asserts the CLI message and one the TUI message contain the guidance (the TUI test through tests/tui_support.py, with `setup.login` stubbed to return a nonzero code).

Non-goals (reviewers must not require): login() changes, distinguishing a cancelled login from a disabled one, other messages, credential handling.

Testing: while editing run only the test you change; the DoD command once at the end (acceptance reviewer only).

DoD: `python3.13 -m unittest tests.test_setup tests.test_tui tests.test_tui_polish tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
