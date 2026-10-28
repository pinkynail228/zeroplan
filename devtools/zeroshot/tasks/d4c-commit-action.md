D4c — confirmed «закоммитить» action for the user's own files

Owner decision 2026-10-27 (A2): when the goal needs uncommitted files, zplan offers to commit them; never
automatic. Design ~/zs-pause/design/0.7.1-dirty-login.md, "A2 commit action, safety rules" (critic-reviewed).

Write-set: terminal_planner/user_commit.py, terminal_planner/architect.py, terminal_planner/architect_tools.py,
terminal_planner/process.py, terminal_planner/catalog.py, terminal_planner/tui/*.py, docs/REFERENCE.md,
docs/USER_FLOW.md, tests/*

Acceptance criteria:
- U1 The architect can propose a commit (paths + message); zplan shows a card with `git diff --stat HEAD --` of
  those paths, the message, «сначала план станет устаревшим; идущий этап коммит не увидит» and «да» / «нет». Only
  «да» commits. Example: proposal of 2 paths -> card lists both; «нет» -> HEAD, index, tree unchanged.
- U2 Paths committed = proposal ∩ live `status -z --no-renames` at «да»; files only; GIT_LITERAL_PATHSPECS=1; a rename
  needs both sides; never `add -f` (ignored stay out); credential paths (project_read.is_credential) refused. The
  architect sees only stat and a scrubbed diff, never raw content. Example: proposal [".env", "a.py"] -> .env
  refused and named, a.py committed.
- U3 Commit = `git commit --only -- <paths>` with the user's identity, hooks run (never --no-verify), under the
  terminal suspend used by login; untracked paths are `add -N` first and exactly those are `rm --cached` on any
  failure; process.py `_commit_file` gets the same undo. Example: failing pre-commit hook -> HEAD and index
  byte-identical to before.
- U4 Refused with a fix: no identity (runs.configured_identity), detached HEAD, MERGE_HEAD or rebase in progress,
  index.lock held; the action takes the project lock used by merge. Example: MERGE_HEAD present -> «идёт merge»
  refusal, nothing run.
- U5 After the commit: parent == HEAD before and changed paths ⊆ selection, else the card reports what the hooks
  changed; other staged entries stay staged. Example: other file staged before -> still staged after, not in the
  commit.

Non-goals (reviewers must not require): stash; push; amend; partial hunks; en/zh texts.

Tests: new tests/test_user_commit.py with fixture repos and hooks, each test failing on today's code.

Risk: high (commits in the user's repo). DoD: `python3.13 devtools/fasttest.py tests.test_user_commit
tests.test_architect tests.test_architect_tools tests.test_process tests.test_tui_chat tests.test_reference`: exit 0.
