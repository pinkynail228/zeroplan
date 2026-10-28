A7c — after a merge lands, remove the attempt's worktree and branches (RELEASE_0.6.0_PLAN lane T; ARCHITECT_DESIGN.md
section 10 item 4, "then cleans up").

Why: every integrated attempt leaves its worktree under `<data_root>/worktrees`, its working branch and its result
branch in the project for good.

Reuse: `Delivery.merge` (delivery.py:1018), `MilestoneRuns.product_tree` (runs.py:1211), record fields `worktree`,
`branch`, `result.branch` (runs.py:690, :1262); `git_call` from runs.py for git commands. After `integrated`, nothing reads the worktree or the
branches: `refresh`/`delivered` use commit ancestry only (runs.py:1319, :1350); the readers tolerate a missing worktree
(runs.py:264, :959).

Write-set: terminal_planner/delivery.py, tests/test_merge_cleanup.py (new), tests/test_terminal_planner.py (:1678
reads the worktree after the merge: check it before).

Acceptance criteria:
- C1 Cleanup: when `Delivery.merge` returns `integrated` (gated or not), in order: (a) if the worktree directory
  exists, `self.runs.product_tree(r) == r["result"]["tree"]` (all the attempt made is in the result) and every
  ignored or untracked path left (`git status --porcelain=v1 -z --ignored --untracked-files=all` in it) is under
  `.zplan/` or one of the disposable caches `__pycache__/`, `node_modules/`, `.pytest_cache/`, `.mypy_cache/`,
  `.ruff_cache/` (at any depth), then `git worktree remove --force <worktree>` and, only if it succeeded, `git branch -D <branch>`; (b) if
  the directory was already gone, `git worktree prune` and `git branch -d <branch>` (kept unless merged); (c) `git
  branch -d <result branch>` (merged, so `-d`). Never `gc`, never any other path. Example: an attempt with only
  `.zplan/` and `__pycache__/` left merged -> its worktree, `branch` and `result.branch` are gone; the merge and
  result commits stay reachable from the destination.
- C2 Best effort: a step that fails or is skipped (product tree differs or cannot be read) never changes the outcome
  (`integrated`, delivery and store unchanged); the next steps follow C1's conditions. The line is today's "Влито:
  M → B." when every item is gone (removed now or absent before); otherwise "Влито: M → B; оставлено: " and the
  items left by name (worktree path, branch name), then ".". Example: an ignored `.env.local` in the worktree -> "Влито: M1 → main; оставлено: <worktree path>, <branch>.", result branch removed.
- C3 Scope: refused, conflict and open merges clean nothing. Example: a conflict -> worktree and branches stay.

Non-goals (reviewers must not require): cleanup of attempts merged by hand outside zplan (refresh), of failed or
superseded attempts, or of `<authority>/runs/<name>` documents; the merge critic (A7b); zplan.process.json /2 (at the
0.6.0 release); progress display; changes to runs.py.

Risk: high (git cleanup, data loss trigger). DoD: `python3.13 devtools/fasttest.py tests.test_merge_cleanup
tests.test_terminal_planner tests.test_toolchain` exit 0; quote the `fasttest:` lines.
