T4a — preset `zplan.default/3`: the worker defaults to gpt-6.1-terra / max, every other role stays gpt-6.1-sol / high

Owner 2026-10-28: only the worker moves, to `gpt-6.1-terra` at effort `max` (the highest the engine accepts);
planner, critic, reviewer, steward and architect keep `gpt-6.1-sol` high.

Reuse: `PRESETS` and the comment above it in process.py (a shipped preset is frozen; a change ships as a new
version). /3 = /2's gates, limits, `autonomy` and `risk` as they are, only the worker binding differs. The key-set
logic already reads `PRESETS[name]`, so /3 needs no new branches.

Write-set: terminal_planner/process.py, terminal_planner/setup.py, terminal_planner/cli.py, tests/test_process.py,
tests/test_setup.py, tests/test_agent_activation.py (its first-start screen pins the proposal's preset name).

Acceptance criteria:
- M1 `zplan.default/3` exists; `propose()` and the first-start proposal line name /3. Roles: worker
  `gpt-6.1-terra` max; planner, critic, reviewer, steward, architect `gpt-6.1-sol` high.
  Example: `propose(project, {})["roles"]["worker"]` = `{"model": "gpt-6.1-terra", "effort": "max"}`,
  `["reviewer"]` = `{"model": "gpt-6.1-sol", "effort": "high"}`, `["preset"]` = `zplan.default/3`.
- M2 /1 and /2 are byte-identical to today: a file naming /2 with no roles resolves the worker to `gpt-6.1-sol`
  medium; the existing /1 and /2 tests pass unchanged. Example: `resolve({"preset": "zplan.default/2"}, {})`
  roles.worker = `{"model": "gpt-6.1-sol", "effort": "medium"}`; a /3 file with `"autonomy": {"level": "manual"}`
  is valid.
- M3 Outside the profile the same defaults hold, from one place (no repeated model literals): `setup.default_roles()`,
  the `configure_roles` prompt default and the shell's `_roles` start value. Example: `setup.default_roles()["worker"]`
  = `{"model": "gpt-6.1-terra", "effort": "max"}`, `["plan_verifier"]` = `{"model": "gpt-6.1-sol", "effort":
  "high"}`; the invalid-model hint says "for example gpt-6.1-terra".

Non-goals (reviewers must not require): a migration of /2 profiles or stored records; docs, README, screenshots;
the dev harness (devtools/); model ids or presets used as arbitrary fixtures in other tests.

Conflict rule: if /3 cannot reuse /2's autonomy/risk validation without new per-preset branches, change nothing
and end with `conflict: <reason> <evidence>`.

Risk: medium (profile defaults; /1 and /2 identity must hold). DoD: run once, at the end: `python3.13
devtools/fasttest.py tests.test_process tests.test_setup tests.test_agent_activation tests.test_toolchain`: exit 0;
`python3 devtools/budget.py`: OK.
