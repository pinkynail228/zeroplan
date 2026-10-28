T3d — the Codex version probe refuses the owner-home alias like a launch

Release critic r080-public (2026-10-28) on t3c (51e80d3): terminal_planner/setup.py `probe_environment` takes
`agent_home(env)` and creates it, without the implicit owner-home alias guard `launch_home` applies
(`_refuse_owner_home`, R-1/A-4). A private home `data_root()/codex-home` that is a symlink into `~/.codex` lets
`codex --version` write `~/.codex/tmp/arg0` before any launch refuses it.

Write-set: terminal_planner/setup.py, tests/test_setup.py

Acceptance criteria:
- G1 `probe_environment` resolves the home through `launch_home(env)` (the same guard as a launch), before it
  creates anything or starts Codex; the refusal is `launch_home`'s own (same family and text). An explicit
  CODEX_HOME override behaves as in t3c (used as is, nothing created). Example: with `data_root()/codex-home` a
  symlink to `HOME/.codex` and no CODEX_HOME, `check_versions` raises the launch refusal, the fake `codex` never
  runs (its record file does not exist) and `HOME/.codex/tmp` does not exist.
- G2 The t3c test `test_codex_version_probe_gets_a_codex_home_never_dot_codex` still passes unchanged. Example: the
  private home is created 0700 and recorded; the override is recorded and the private home is not created.

Non-goals (reviewers must not require): other call sites; docs; engine or turn launches; a full suite.

Conflict rule: if `launch_home` cannot be used here without changing setup's staging contract (for example it needs
a state that exists only after publish), change nothing and end with `conflict: <reason> <evidence>`.

Risk: high (auth/home selection). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_setup
tests.test_toolchain tests.test_agent_activation`: exit 0; `python3 devtools/budget.py`: OK.
