L2 — `zplan login` outside a usable terminal says so at once and touches nothing

Tester 2026-10-28 (0.8.1, installed through an AI agent): the agent ran `zplan login` in its own shell (no
terminal); `codex login --device-auth` waited silently. Device auth needs a person at a terminal: zplan must say so
before it runs Codex or writes anything.

Reuse: `setup.login` (terminal_planner/setup.py:493), the shared path of the CLI (`zplan login`, cli.py:1118) and
the TUI callback (`tui_login`, cli.py:1123); the stdin+stdout isatty test cli.py:890 uses; `foreign` as the shape
of an early refusal; tests/test_setup.py and tests/test_login_home.py fixtures (isolated HOME, fake codex).

Write-set: terminal_planner/setup.py, tests/test_setup.py, tests/test_login_home.py, tests/test_agent_activation.py,
tests/test_first_run_fixes.py. The check is one module-level function in setup.py; existing tests that drive a login
run without a TTY, so they patch it true (one patch per class or setUp, no other edit to them).

Acceptance criteria:
- T1 When stdin or stdout is not a terminal, `login` (refresh or not) shows one line "zplan login needs your
  terminal: run `zplan login` there yourself." and returns 2 before any Codex call, `native_environment()`, mkdir
  of the home or refresh prompt. Example: stdout a pipe, fake codex recording calls, a fresh HOME -> exit 2, the
  line shown, codex never called, the zplan Codex home not created.
- T2 The same guard holds for the TUI callback path, refresh included. Example: `login(..., refresh=True)` with
  stdin not a TTY -> 2, no confirm asked, no logout run.
- T3 In a terminal nothing changes: login status, "Login already present", device auth and refresh run as today.
  Example: both TTYs patched true, fake codex status 0 -> "Login already present", exit 0.
- T4 A foreign home keeps its own refusal first; `logout` gets no terminal check. Example: non-owned CODEX_HOME,
  no TTY -> the foreign message, not the terminal line; `logout` without a TTY runs as today.

Non-goals (reviewers must not require): API-key login, a browser login, `zplan doctor`, the TUI's own screens,
docs, the installer, wording of other login messages.

Conflict rule: if a test outside the write-set drives `login` and expects Codex to run, change nothing and end
with `conflict: <file:line>`.

Risk: high (auth). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_setup
tests.test_login_home tests.test_agent_activation tests.test_first_run_fixes tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new test fails on the
old setup.py. Never the runner's real Codex login: fake codex and an isolated HOME only.
