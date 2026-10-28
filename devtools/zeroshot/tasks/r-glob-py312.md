r-glob-py312 — risk path rules work on Python 3.11 and 3.12 (repair; incident 2026-10-25: Linux host 2,
Python 3.12, `tests.test_process` 2 errors `AttributeError: 'PurePosixPath' object has no attribute 'full_match'`,
reproduced on main dcc75e9).

Why: `process.risk_of` (process.py:500, :509, :516) calls `PurePosixPath.full_match`, new in Python 3.13, while
pyproject.toml declares `requires-python = ">=3.11"`. On 3.11/3.12 every `/2` profile with a risk section crashes
the classification, and the merge gate (runs.py `gate_merge`) calls it.

Reuse: `validate_pattern` (process.py:187) for the pattern domain; the stdlib only (`re`, `fnmatch`-style
translation done by hand).

Write-set: terminal_planner/process.py, tests/test_process.py.

Acceptance criteria:
- C1 One matcher: a module function `glob_match(path, pattern)` used by `risk_of` for rules and triggers, the same
  on every Python >= 3.11 (no version branch). Semantics of 3.13 `PurePosixPath.full_match` for patterns made of
  literal characters, `*`, `?`, `**` and `[...]` classes: segments split on `/`; `**` as a whole segment matches zero or more segments (inside a segment it acts as `*`); `*`
  matches within one segment, `?` one character other than `/`, `[...]`/`[!...]` one character of a class;
  case-sensitive; the whole path must match. Example cases (path, pattern -> result): (`a.md`, `**/*.md`) True;
  (`docs/x/y.txt`, `docs/**`) True; (`src/a.py`, `*.py`) False; (`.env.local`, `**/.env*`) True;
  (`a/b/install.sh`, `**/install*`) True; (`README.MD`, `**/*.md`) False; (`x/pyproject.toml`, `pyproject.toml`)
  False.
- C2 Parity: a test runs every pattern of the zplan.default/2 preset (process.py PRESETS) and C1's patterns against
  a fixed list of at least 20 paths, comparing `glob_match` with `PurePosixPath.full_match` when the running
  Python has it (skipped otherwise, with the reason), and C1's expected table on every Python. Example: on 3.13
  every pair agrees; on 3.12 the table test runs and passes.

Non-goals (reviewers must not require): new pattern syntax, case-insensitive matching, Windows paths, changes to
`validate_pattern`'s accepted domain, other modules.

Risk: medium (pure function; the merge gate consumer is unchanged). DoD: `python3.13 devtools/fasttest.py
tests.test_process tests.test_toolchain` exit 0; quote the `fasttest:` lines. The orchestrator reruns
`tests.test_process` on the Linux host (Python 3.12) at merge.
