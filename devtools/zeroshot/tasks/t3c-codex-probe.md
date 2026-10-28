T3c — the Codex version probe never writes ~/.codex

R6 of 0.8.0 (fresh HOME, no credentials): `install.sh` / `zplan setup` created `$HOME/.codex/tmp/arg0/...`. Cause,
reproduced: the pinned Codex 0.162.1 writes `<CODEX_HOME>/tmp/arg0` on every start, `--version` too, and
setup.check_versions (terminal_planner/setup.py:124) runs it without CODEX_HOME, so Codex falls back to ~/.codex.
README promises "Your own ~/.codex is used only when you ask for it" (D6a, R-1: no implicit launch reads or
writes it).

Write-set: terminal_planner/setup.py, tests/test_setup.py

Acceptance criteria:
- K1 Every Codex process setup.py starts outside a login or a turn (check_versions; any other `codex` probe found in
  setup.py) runs with CODEX_HOME = `agent_home(os.environ)`: an explicit $CODEX_HOME override as is, else zplan's own
  `private_codex_home()`, created first with mode 0700 when missing. The rest of the environment is unchanged.
  Example: a fake `codex` that records its CODEX_HOME, under a HOME with no ~/.codex and no CODEX_HOME, records the
  private home after `check_versions`, and HOME/.codex does not exist afterwards.
- K2 With CODEX_HOME=/x/override set, the probe gets /x/override and the private home is not created. Example: the
  same fake records /x/override; data_root()/codex-home does not exist.

Non-goals (reviewers must not require): engine.py or turn launches (they already pass the selected home); other
setup behaviour; docs; a full suite.

Conflict rule: if some probe cannot get a home (for example it runs before data_root exists and creating it would
change setup's staging contract), change nothing for it and end with `conflict: <call site> <evidence>`.

Risk: high (auth/home selection). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_setup
tests.test_toolchain tests.test_english tests.test_agent_activation`: exit 0; `python3 devtools/budget.py`: OK.
