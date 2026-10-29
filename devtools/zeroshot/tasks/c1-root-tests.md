C1 — the proposed profile finds unittest files at the project root, so a small Python project gets a merge check (walk W2)

Orchestrator walk 2026-10-29 (real Codex, a word-count project with `test_wc_cli.py` at its root and "python3 -m
unittest" in its README): the profile card said "Check: no qualification", the proposal left `gates.merge` off and
M1 merged with no test run. `detect_checks` (terminal_planner/process.py:638-666) looks for `test_*.py` only under
tests/ (process.py:661-665).

Reuse: `detect_checks` and its order; `propose` turns the merge gate on when a check is found (process.py:703).

Write-set: terminal_planner/process.py, tests/test_process.py, docs/PROCESS_PROFILE.md (test_process.py: the RS3
test at 580-610 may gain cases; its existing assertions stay)

Acceptance criteria:
- R1 With no npm, make or pytest match and no `tests/test_*.py`, a `test_*.py` file directly in the project root
  gives the check argv `["python3", "-m", "unittest"]` (unittest's own discovery from the root); the name, timeout
  and the merge gate rule are those of today's unittest case. Example: root holds wc.py and test_wc.py ->
  checks[0].argv == ["python3", "-m", "unittest"], proposal gates.merge "required".
- R2 Every earlier rule keeps its precedence and its argv: npm, make, pytest, then `tests/` (recursive), then the
  root (not recursive, files only, read without executing anything). Example: root test_a.py plus tests/test_b.py ->
  `discover -s tests`; a root Makefile with `test:` -> `make test`.
- R3 A root with no `test_*.py` and no other match still gives no check. Example: root holds only README.md and
  a directory named test_data -> [].
- R4 PROCESS_PROFILE.md's list of detected commands names the root case in its order. Example: tests.test_docs
  passes.

Non-goals (reviewers must not require): other languages, `*_test.py`, a `test/` folder, running the found command.

Conflict rule: if a test outside the write-set pins the empty result for a root `test_*.py`, change nothing in it
and end with `conflict: <file:line>`.

Risk: low (proposal only, nothing is executed). DoD: once at the end, `python3.13 devtools/fasttest.py
tests.test_process tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New R1 and R3 tests fail on
today's process.py where they assert the new result.
