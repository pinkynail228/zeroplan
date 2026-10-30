# r5 — zplan stops proposing `python3 -m pytest` for unconfigured pytest-style tests (0.9.0-rc1 soak blocker)

Soak of v0.9.0-rc1, F1 (blocker): p3c added a rule to `process.detect_checks` (terminal_planner/process.py:676-679,
`_pytest_style` :690) that proposes `python3 -m pytest` for `test_*.py` files with `def test_` or `import pytest`
and no pytest configuration. zplan's check environment puts `/usr/bin:/bin` before the owner's PATH
(terminal_planner/export.py:27-29, checks.py:151), so `python3` is the system one without pytest even when the
owner's venv has it: "The check 'test' failed (1); the merge was not done. [code: merge.checks_failed]", and the
proposed merge gate blocks every merge of such a project. In 0.8.3 such a project got no proposed check.

Change: remove that rule, `_pytest_style` and the tests that cover it; configured pytest (pytest.ini, a
`[tool.pytest` table, `[tool:pytest]`) and the unittest rules stay as they are. In docs/USER_FLOW.md fix the lines
that still say a typed `/run` (the `/run` row, the "Developing zplan with zplan" paragraph: "confirm with «yes»") and
the plan screen's «approve» ask yes/no: since p094 they act at once; /stop still asks.

Write-set: terminal_planner/process.py, tests/test_process.py, docs/USER_FLOW.md

Acceptance criteria:
- A1 No guessed pytest check. Example: a root `test_wc.py` with `def test_counts(): assert ...`, no config ->
  `detect_checks(root)` == []; with a `pytest.ini` -> `python3 -m pytest` as before.
- A2 The docs match. Example: USER_FLOW.md's `/run` row and the developing paragraph name no yes/no step for /run;
  the plan screen's «approve» row says it approves at once.

Non-goals (reviewers must not require): the check environment's PATH, which interpreter runs checks, other
detection rules, the profile modal.

Conflict rule: if a test outside the write-set needs the guessed pytest check, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (proposed checks). DoD: `python3.13 devtools/fasttest.py tests.test_process tests.test_docs`: exit 0.
