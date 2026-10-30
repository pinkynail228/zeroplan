V090 — version 0.9.0

Owner 2026-10-30: release 0.9.0 = 0.8.3 + P1-P4 and P6 of docs/PLAN_0.9.md. This task only moves
the version; no behavior changes.

Reuse: the 0.8.2 -> 0.8.3 bump (v083) (pyproject.toml, terminal_planner/__init__.py, install.py `VERSION` and `OWNED`).
`OWNED` lists every earlier version whose launcher the installer treats as its own.

Write-set: pyproject.toml, terminal_planner/__init__.py, install.py, tests/test_install.py,
tests/test_terminal_planner.py.

Acceptance criteria:
- V1 The version is 0.9.0 in all three places, and `zplan --version` prints it.
  Example: `install.VERSION` = `"0.9.0"`, `terminal_planner.__version__` = `"0.9.0"`, pyproject `version = "0.9.0"`;
  the installed launcher prints `zplan 0.9.0`.
- V2 An installed 0.8.3 launcher is recognized as owned, so 0.8.3 -> 0.9.0 installs and `zplan update` replace it.
  Example: `"0.8.3" in install.OWNED` and `install.OWNED[-1] == install.VERSION`; the earlier entries are unchanged.

Non-goals (reviewers must not require): docs, README, STATE, CHANGELOG; historical comments or docstrings that
name 0.8.3 as the version a change shipped in; devtools/.

Conflict rule: if anything outside the write-set pins 0.8.3 as the current version (not as history), change nothing
and end with `conflict: <file:line>`.

Risk: high (installer/packaging). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_install
tests.test_terminal_planner tests.test_update tests.test_toolchain`: exit 0.
