C1b — a unittest check is proposed only for test files that use unittest, so a pytest-style file never gets a check that finds nothing (critic walk082 Q3)

Orchestrator check 2026-10-29 after c1 (merged): `detect_checks` (terminal_planner/process.py:638-672) proposes
`python3 -m unittest` for a root `test_*.py` and `unittest discover -s tests` for `tests/test_*.py` by file name
only. A pytest-style file (`def test_x(): assert ...`, no pytest config) then runs 0 tests; Python 3.12+ exits 5
on that, so the required merge check would block every merge. Critic walk082 Q3 reproduced exit 5 on 3.13.3.

Reuse: `detect_checks`'s order and the bounded reads (`MAX_FILE_BYTES`) the npm and make rules use.

Write-set: terminal_planner/process.py, tests/test_process.py, docs/PROCESS_PROFILE.md (test_process.py: the RS3
test's fixture file at 590-592 may gain an `import unittest` line; its assertions stay)

Acceptance criteria:
- U1 The tests/ rule and the root rule apply only when one of their `test_*.py` files, read bounded and never run,
  contains `import unittest` or `from unittest`. Example: root test_wc.py with `import unittest` ->
  ["python3", "-m", "unittest"]; tests/test_a.py with `from unittest import TestCase` -> `discover -s tests`.
- U2 Files with no such line give no unittest check, and then the next rule or no check applies. Example: root
  test_x.py holding only `def test_x(): assert 1` -> [] (gates.merge "off"); with a pytest.ini -> pytest as today.
- U3 An unreadable, oversized or non-UTF-8 test file counts as not naming unittest, and no error reaches the
  caller. Example: a test_big.py over the byte bound -> it is skipped.
- U4 PROCESS_PROFILE.md says the unittest cases need a file that imports unittest. Example: tests.test_docs passes.

Non-goals (reviewers must not require): proposing pytest without its config, other frameworks, running anything.

Conflict rule: if a test outside the write-set pins a unittest check for a file without `unittest` in it, change
nothing in it and end with `conflict: <file:line>`.

Risk: low (proposal only). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_process
tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New U1-U3 tests fail on today's process.py
where they assert the new result.
