D5 — the zplan login is one guided step; the owner's ~/.codex is never imported (decision C, owner 2026-10-21, critic d5-login-reuse GO C: refresh tokens rotate, so a copied or linked login can log out the owner's own Codex).

Goal: on a fresh install the doctor and the failed-login message tell the owner exactly what to do once, and why zplan has its own login. Today the doctor says "нет login для provider openai в <home>; выполните zplan login (или задайте CODEX_HOME с вашим login)" (terminal_planner/setup.py:637) and a failed login points only to retrying (catalog.py:336-337, `setup.login_failed`).

Write-set: terminal_planner/setup.py (the auth readiness lines only, :620-645), terminal_planner/catalog.py (the `auth` remedy :38 and the `setup.login_failed` entry :336-337), docs/INSTALLATION.md and docs/USER_FLOW.md (only sentences about the first login), their tests. Not tui/app.py, cli.py, login() itself, agent_profile.py.

Acceptance criteria:
- A1 The blocking auth line says that zplan needs its own Codex login once, names `zplan login` (and [l] on the start screen through the existing key), and says the existing ~/.codex login is not used or changed. The explicit opt-in (`CODEX_HOME=<your home>`) stays mentioned.
- A2 The `setup.login_failed` remedy adds: if device-code login is turned off for the account, turn it on in the ChatGPT account security settings, then [l] or `zplan login` again.
- A3 A present login in zplan's home keeps the existing OK line (no new prompt).
- A4 docs/INSTALLATION.md states the decision in two sentences: zplan has its own login in its own Codex home; it never copies or links ~/.codex credentials, because a shared refresh token can log out the other copy.
- A5 One test per criterion; the auth tests use a scratch HOME/XDG and assert ~/.codex-style fixture files stay byte-identical.

Non-goals (reviewers must not require): importing, copying or linking credentials, reading auth.json content, changing login(), the TUI login flow, keyring support, option D (using ~/.codex as zplan's home).

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_setup tests.test_home_wiring tests.test_architect_home tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
