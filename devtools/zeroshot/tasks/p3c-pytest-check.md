# p3c — pytest-style tests without a pytest config are found as the project's check

Owner decision Q3, rc1 walk R8: a project with pytest-style tests (`def test_...` functions, `import pytest` or
plain asserts) and no pytest configuration gets "Check: no qualification", so its merge runs with no test check and
the reviewers accepted without running the tests. `process.detect_checks` (process.py:638-673) finds pytest only
when configured (`_pytest_configured`) and `test_*.py` only when the file imports unittest.

Change: after today's rules and before "none", `test_*.py` files under tests/ or at the root that do not import
unittest but import pytest or define a top-level `def test_` function propose `python3 -m pytest`. Nothing is
executed or installed; a missing pytest shows up when the check runs (the final check reports it as incomplete).

Write-set: terminal_planner/process.py, tests/test_process.py

Acceptance criteria:
- A1 Plain pytest tests are found. Example: root `test_wc.py` with `def test_counts(): assert ...` and no config ->
  `detect_checks(root)` == `[{"name": "test", "argv": ["python3", "-m", "pytest"], "timeout_s": 1800}]`.
- A2 Earlier rules win and unrelated files stay unproposed. Example: the same file plus a root unittest file ->
  the unittest check; a root `test_data.py` with neither pytest nor a test function -> [].

Non-goals (reviewers must not require): other languages, installing pytest, running checks, test layouts beyond
tests/ and the root, the profile modal's words.

Conflict rule: if a test outside the write-set pins "no qualification" for a pytest-style project, change nothing
in it and end with `conflict: <file:line>`.

Risk: medium (proposed checks). DoD: `python3.13 devtools/fasttest.py tests.test_process`: exit 0.
