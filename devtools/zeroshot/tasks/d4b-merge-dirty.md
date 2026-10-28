D4b — merge lands beside uncommitted changes, never writes a conflict into the user's tree

Design ~/zs-pause/design/0.7.1-dirty-login.md (A.3', A.3''). Only the merge writes the user's tree. Today the
non-gated path (runs.py:1459 `merge --no-ff`) writes conflicts into the tree and aborts (:1474-1479); both paths
require an empty status (:1451, :1536, :1543); an ignored local file the candidate adds is overwritten silently.

Write-set: terminal_planner/runs.py, terminal_planner/setup.py, terminal_planner/catalog.py,
terminal_planner/tui/*.py, docs/REFERENCE.md, docs/USER_FLOW.md, tests/*

Acceptance criteria:
- M1 Both merge paths build the merge commit off-tree (merge-tree --write-tree + commit-tree with the user's identity,
  as gate_candidate does at runs.py:1556) and land it with `merge --ff-only`; a conflict is recorded from merge-tree,
  the tree is never touched and no abort runs. Example: conflicting candidate + dirty unrelated file -> conflict
  card, `git status` and file bytes identical before/after.
- M2 Overlap = `diff --no-renames --name-only -z HEAD <merge commit>`; landing is refused when a changed path or a
  parent dir exists on disk as untracked, ignored or modified, with one card naming the paths and «влить позже»
  (branch kept) / «показать различия». Example: candidate adds .env, local ignored .env exists -> card, local .env
  byte-identical.
- M3 Unrelated changes never block: the empty-status checks at :1451, :1536, :1543 become "dirty set identical
  before/after and no overlap", recomputed right before landing. Example: dirty notes.md, candidate touches src/ ->
  merged, notes.md still modified.
- M4 A post-landing check failure is recorded on the run and reported; zplan never resets or checks out. Example:
  fixture where the dirty set changes during landing -> record says so, HEAD stays at the merge commit.
- M5 doctor refuses git < 2.38 (merge-tree --write-tree) with family readiness.git and the upgrade hint. Example:
  fake git reporting 2.37 -> block naming 2.38.

Non-goals (reviewers must not require): plan/run clean checks and baseline (D4a); a commit action (D4c); stash;
en/zh texts.

Tests: new tests/test_merge_dirty.py, each test failing on today's code; old-behaviour tests updated.

Risk: high (writes the user's tree). DoD: `python3.13 devtools/fasttest.py tests.test_merge_dirty tests.test_runs
tests.test_setup tests.test_tui_planning tests.test_terminal_planner tests.test_reference`: exit 0.
