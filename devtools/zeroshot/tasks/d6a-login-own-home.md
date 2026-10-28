D6a — zplan logs in and out only of the Codex home it owns

R6 2026-10-27: `zplan login` on a home with a login revoked that token server-side. Codex rust-v0.162.1: every login
flow first revokes and deletes the stored token (login.rs:151/339/390); refresh tokens are single-use, so a copied
auth.json breaks the other copy on its first refresh; `codex login status` is local and changes nothing. Design
~/zs-pause/design/0.7.1-dirty-login.md part B (critic-reviewed).

Write-set: terminal_planner/setup.py, terminal_planner/cli.py, terminal_planner/commands.py,
terminal_planner/planning.py, terminal_planner/catalog.py, terminal_planner/architect.py, terminal_planner/tui/*.py,
README.md, docs/REFERENCE.md, docs/USER_FLOW.md, docs/INSTALLATION.md, docs/UPGRADE.md, tests/*

Acceptance criteria:
- L1 Owned = realpath(home) == realpath(setup.private_codex_home()). `zplan login` (setup.py:351) on a home not owned
  runs no Codex: «Это ваш Codex (<home>): входите через codex login», exit 0 if logged in else 1. Example:
  CODEX_HOME=/tmp/x -> no codex process; CODEX_HOME=<private home> counts as owned.
- L2 In an owned home `zplan login` first runs `codex -c cli_auth_credentials_store="file" login status`; exit 0 ->
  «Вход уже есть», exit 0, nothing else run. New `zplan logout` (owned home only, refused while a run or the
  architect is live there) runs `codex logout`. Example: fake codex with status 0 -> only `login status` is called.
- L3 A private auth.json that is a symlink or not a regular file, or whose bytes equal ~/.codex/auth.json (digest
  in-process, never printed), refuses login, logout, doctor-ok and starts with «удалите копию: rm <path>» (never
  «logout»). Example: copied auth.json -> readiness.auth block naming rm; logout refused, fake codex not called.
- L4 The auth-failure action «[l] обновить вход» (planning.py:572, cli.py:554) targets the run's recorded home
  (engine.py:1160) under L1; in an owned home it asks to confirm, then logout + login. Example: recorded override
  home -> the L1 message, no codex login.
- L5 No text recommends logging zplan into the user's Codex home or copying auth.json: commands.py:50-53,
  catalog.py:190, architect.py:789, setup.py:649, README.md:113, REFERENCE.md:39-41/131, USER_FLOW.md:711; UPGRADE.md tells
  0.6.x/0.7.0 users who copied auth.json to delete the copy. Example: `grep -rnF 'CODEX_HOME=$HOME/.codex zplan login'
  terminal_planner README.md docs/*.md` -> nothing.

Non-goals (reviewers must not require): API-key flows; Codex keyring store; other first-run fixes (D6b); en/zh.

Tests: new tests/test_login_home.py with a fake codex binary (records argv), each test failing on today's code.
Never use a real Codex home.

Risk: high (credentials). DoD: `python3.13 devtools/fasttest.py tests.test_login_home tests.test_setup
tests.test_architect_home tests.test_terminal_planner tests.test_reference`: exit 0.
