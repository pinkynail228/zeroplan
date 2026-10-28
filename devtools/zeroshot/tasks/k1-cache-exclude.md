K1 — tool caches never enter a milestone commit

Newcomer check 0.6.2 2026-10-26 (~/zs-pause/ux-audit/sb11, empty folder made a project by the start screen, no
.gitignore): the M1 commit held `__pycache__/hello.cpython-313.pyc` and `__pycache__/test_hello.cpython-313.pyc`
next to hello.py and test_hello.py. The worker ran the tests; delivery runs `git add --all`
(upstream/zeroshot/src/native_v2_templates.rs:91), which respects the repository's info/exclude. zplan already
keeps `/.zplan/` there (terminal_planner/project_state.py `_exclude`, a local rule, never a tracked file);
terminal_planner/delivery.py `CLEANUP_CACHES` names the caches.

Write-set: terminal_planner/project_state.py, terminal_planner/runs.py, terminal_planner/export.py,
tests/test_cache_exclude.py, tests/test_export.py

Acceptance criteria:
- C1 Before a milestone attempt is prepared (terminal_planner/runs.py `start`, before its clean-tree check), the
  project's `<git common dir>/info/exclude` holds one line per cache of `CLEANUP_CACHES`, written as `__pycache__/`
  etc. (no leading `/`, so any depth), each added once, existing lines and their order kept, a missing file created.
  Example: exclude `/.zplan/\n` -> after start `/.zplan/`, then the five cache lines; a second start adds nothing.
- C2 A cache left untracked in the project no longer blocks the start, and a worker's cache never reaches the
  attempt's commit. Example: an untracked `__pycache__/x.pyc` in the project -> the start passes the clean-tree
  check; in a linked worktree of the project, `git add --all` of a new `pkg/__pycache__/a.pyc` stages nothing.
- C3 The export (terminal_planner/export.py `create_branch`) leaves out an untracked snapshot path with a
  `CLEANUP_CACHES` component that a target-local exclude drops, without refusing; any other path a target-local
  exclude drops still refuses as today (attempt 1 review: the candidate refused the export). Example: snapshot with
  hello.py and `__pycache__/hello.cpython-313.pyc` -> branch tree holds hello.py only; snapshot with `excl.txt`
  excluded in info/exclude -> the existing refusal.
- C4 Already tracked files stay tracked: a project that tracks `node_modules/x` keeps it in the attempt's tree.
  Example: `git ls-files` of the attempt's base still lists `node_modules/x`.

Non-goals (reviewers must not require): a tracked .gitignore; the start screen; the engine's delivery or worker
instructions; export rules other than C3; cleaning caches already committed; other cache names than `CLEANUP_CACHES`.

Risk: high (git writes in the target repository). DoD: `python3.13 devtools/fasttest.py` tests.test_cache_exclude,
tests.test_project_state, tests.test_runs, tests.test_parallel_runs, tests.test_export, tests.test_toolchain: exit 0.
