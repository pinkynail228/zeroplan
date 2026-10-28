C0a repair 1 — isolate one profile test from the runner's personal config.

Context: branch zs-c0a-review-bar carries the c0a-review-bar change (review bar, loop bound from the frozen `limits.task_rounds`, critic effort high). Round 1 reviewers found one defect besides a write-set conflict in the old brief. The orchestrator accepts the existing changes in terminal_planner/authority.py, runs.py and process.py (freezing and validating `task_rounds`) as in scope; do not revert or rework them.

Defect: tests/test_process.py:1324 (`RepositoryProfileTests`, the critic-effort check) calls `process.Profile.peek(ROOT, root=scratch, fixture_id="a4").status(write=False)` without a scratch roles path or isolated HOME/XDG, so process.py:551 `saved_roles(None)` reads the runner's personal `config_root()/roles.json`.

Write-set: tests/test_process.py only.

Acceptance criteria:
- A1 That test passes a scratch roles path or isolates HOME/XDG the way the neighbouring tests in tests/test_process.py already do (reuse their helper; no new helper if one exists), so it reads no file outside its scratch directory.
- A2 The test still asserts the same profile facts (critic effort high, status present with no problem, resolved roles and limits).

Non-goals (reviewers must not require): changes to any other file, other tests, refactoring of process.py.

Testing: while iterating run only `tests.test_process`; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_milestone tests.test_plan_gate tests.test_terminal_planner tests.test_process tests.test_task_gate tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
