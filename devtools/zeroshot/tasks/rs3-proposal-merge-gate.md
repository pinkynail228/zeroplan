RS3 — a fresh project with checks merges unattended in `auto`

Smoke 2026-10-25 #10 and critic r061-scope finding 1: the `/2` proposal (process.py:645 `propose`) offers `auto` but
copies the preset's `gates.merge: "off"` (process.py:92), and autonomy.py:35 allows an automatic merge only with
`gates.merge == "required"` at `auto`. So every `auto` project asks the owner to merge. A required merge gate with
no checks refuses merges (`merge.no_checks`), so the gate can only be on where checks exist.

Write-set: terminal_planner/process.py, tests/test_process.py, docs/PROCESS_PROFILE.md.

Acceptance criteria:
- C1 `propose` offers `gates.merge: "required"` when `detect_checks(project)` (process.py:609) finds a check, else
  `"off"` as today; other gates and the preset constants unchanged. Example: package.json with scripts.test ->
  `gates` == {"plan": "required", "task": "off", "merge": "required"}; an empty repository -> `"merge": "off"`.
- C2 `detect_checks` also finds Python tests by reading files only (today npm and make only): pytest configured
  (pytest.ini, or `[tool.pytest` in pyproject.toml, or `[tool:pytest]` in setup.cfg) -> `python3 -m pytest`;
  else `test_*.py` under tests/ -> `python3 -m unittest discover -s tests`; npm and make keep precedence.
  Example: tests/test_slug.py, no pytest config -> argv ["python3", "-m", "unittest", "discover", "-s", "tests"].
- C3 Accepted proposal with checks: `autonomy.decide(level, "merge", gate)` (autonomy.py:21) for that profile answers "allow" at `auto`
  and "ask" at `supervised`/`manual`. Example: accept, then the Controller's merge decision is "allow".
- C4 Existing accepted files are never rewritten; `/1` and the no-profile fallback stay as they are. Example: an
  accepted `/2` file with `"merge": "off"` still reads "off".
- C5 Docs: PROCESS_PROFILE.md says the proposal turns the merge gate on when it found checks, and which checks it
  finds. Example: its proposal paragraph names npm, make, pytest and unittest. (REFERENCE.md is a non-goal here.)

Non-goals (reviewers must not require): the merge gate itself (checks run, merge critic), autonomy.py, the
Controller, preset `/2` constants, migration of accepted files, TUI.

Risk: high (unattended merges in `auto`). DoD: `python3.13 devtools/fasttest.py` tests.test_process,
tests.test_autonomy, tests.test_bridge, tests.test_reference: exit 0.
