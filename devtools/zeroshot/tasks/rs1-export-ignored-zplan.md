RS1 — export works when `.zplan/` is ignored

Re-smoke 2026-10-25b high #1: the architect writes `.zplan/STATE.md` and adds `/.zplan/` to the repository's
info/exclude (project_state.py:48). From then on every milestone export fails after a green final check:
«Git отказал: add; экспорт прерван [git.failed]», `/attempt` and `/merge` repeat it, no exit.
Cause (reproduced on git 2.50.1): export.py:99 `git add -A -- ":(top)" ":(top,exclude).zplan"` returns rc 1
«The following paths are ignored by one of your .gitignore files: .zplan» when the excluded name is itself ignored.

Write-set: terminal_planner/export.py, tests/test_export.py.

Acceptance criteria:
- C1 `create_branch` succeeds when an `exclude` name is ignored by info/exclude or .gitignore, and the tree still
  has no entry under it. Example: repo with `/.zplan/` in .git/info/exclude, `.zplan/STATE.md` in the workspace,
  a changed `a.py` -> the export branch holds `a.py`'s change and no `.zplan` path.
- C2 Unchanged when the name is not ignored, absent, or `exclude` is empty. Example: the existing test_export
  cases pass unchanged.
- C3 A real `git add` failure still raises `git.failed`. Example: an unreadable workspace file -> `git.failed`.
- C4 Regression test fails on today's code. Example: with export.py:99 restored, the C1 test fails.

Non-goals (reviewers must not require): project_state.py and its exclude line; runs.py, delivery.py; the
merge's untracked-file checks; UI texts.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` tests.test_export, tests.test_runs, tests.test_project_state:
exit 0.
