# u9a — zplan's own run files never show as the run's changes: the worktree excludes `/.zplan/` from the start

Soak of v0.9.0-rc1, F2 (major): `MilestoneRuns.prepare` (terminal_planner/runs.py:1005) writes `.zplan/baseline.json`,
`.zplan/milestone.json` and `.zplan/milestone.before.json` into the attempt's worktree, but `/.zplan/` reaches the
repository's info/exclude only when the architect writes the project STATE (project_state.py:6, 17, 105-110). A
strict scope check ("README.md only") then sees three untracked files and rejects the milestone: 3 final-check
repairs, a rejected attempt 2 and a replan, about 25 minutes. The export already leaves `.zplan/` out.

Change: `prepare` makes sure info/exclude (the common dir every worktree of the project shares) has the line
`/.zplan/`, reusing project_state's own helper (`ensure_excluded` / `_exclude`); nothing is written to a tracked
file, and an existing line is not repeated.

Write-set: terminal_planner/runs.py, tests/test_runs.py, tests/test_cache_exclude.py (if it pins the exclude file's exact
lines)

Acceptance criteria:
- A1 The run's own files are not changes. Example: a fresh project, a milestone prepared -> `git -C <worktree>
  status --porcelain` shows no `.zplan/` entry; the project's `.git/info/exclude` has `/.zplan/` once.
- A2 Nothing tracked changes. Example: `git -C <project> status --porcelain` after prepare is as before; preparing
  again leaves one `/.zplan/` line.

Non-goals (reviewers must not require): the scope check's prompt, cleanup of old worktrees, the export, STATE.

Conflict rule: if a test outside the write-set asserts `.zplan/` shows as untracked in a run worktree, change nothing
in it and end with `conflict: <file:line>`.

Risk: medium (git config of the user's repository: a local exclude line). DoD: `python3.13 devtools/fasttest.py
tests.test_runs tests.test_export tests.test_project_state tests.test_cache_exclude tests.test_parallel_runs`: exit 0.
