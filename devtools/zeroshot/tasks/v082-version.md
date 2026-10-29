V082 — version 0.8.2

Owner 2026-10-29: release 0.8.2 = 0.8.1 + Track A and Track C (docs/RELEASE_0.8.2_WALK_PLAN.md). This task only moves
the version; no behavior changes.

Reuse: the 0.8.0 -> 0.8.1 bump (t4b) (pyproject.toml, terminal_planner/__init__.py, install.py `VERSION` and `OWNED`).
`OWNED` lists every earlier version whose launcher the installer treats as its own.

Write-set: pyproject.toml, terminal_planner/__init__.py, install.py, tests/test_install.py,
tests/test_terminal_planner.py.

Acceptance criteria:
- V1 The version is 0.8.2 in all three places, and `zplan --version` prints it.
  Example: `install.VERSION` = `"0.8.2"`, `terminal_planner.__version__` = `"0.8.2"`, pyproject `version = "0.8.2"`;
  the installed launcher prints `zplan 0.8.2`.
- V2 An installed 0.8.1 launcher is recognized as owned, so 0.8.1 -> 0.8.2 installs and `zplan update` replace it.
  Example: `"0.8.1" in install.OWNED` and `install.OWNED[-1] == install.VERSION`; the earlier entries are unchanged.

Non-goals (reviewers must not require): docs, README, STATE, CHANGELOG; historical comments or docstrings that
name 0.8.1 as the version a change shipped in; devtools/.

Conflict rule: if anything outside the write-set pins 0.8.1 as the current version (not as history), change nothing
and end with `conflict: <file:line>`.

Risk: high (installer/packaging). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_install
tests.test_terminal_planner tests.test_update tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK.
