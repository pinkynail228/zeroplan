tc1012-hint — repair of tc1012-upgrade (critic tc1012 merge: NO-MERGE, blocker 2). Runs on the existing worktree /tmp/zs-zplan/tc1012-upgrade (branch zs-tc1012-upgrade, HEAD 315d5bc). DeepSeek worker, sol xhigh reviewers. Read AGENTS.md, terminal_planner/authority.py `require_workspace_outside_state` (~196-212), terminal_planner/engine.py `native_environment` (~454-458), the tests of that guard added in 315d5bc (`git show 315d5bc -- tests/`).

Defect: the overlap refusal at authority.py:211 offers `ZEROSHOT_STATE_DIR` as a remedy, but zplan always overwrites that variable with `<native_state_root>/runs` (engine.py:456), so setting it changes nothing. The message must name only remedies that work: `--native-state-dir` outside the working trees, and not pointing XDG_DATA_HOME into the native state.

Change: remove the `ZEROSHOT_STATE_DIR` alternative from that message (keep the rest of its meaning); fix the docstring sentence only if it suggests the variable is a user remedy. No other behaviour change.

Acceptance criteria:
- H-1 A test asserts that the overlap refusal names `--native-state-dir` and does not name `ZEROSHOT_STATE_DIR`; it fails on 315d5bc's message (say how you checked).
- H-2 Targeted modules green: the tests touching `require_workspace_outside_state` (tests.test_terminal_planner, tests.test_runs) and tests.test_reference if the catalog/REFERENCE carries the text. The full suites are the orchestrator's merge gate.
- H-3 Diff touches only terminal_planner/authority.py and tests/ (plus docs/REFERENCE.md only if regenerated).

critic tc1012 (session 01a1424e-173e-7fa2-9d3b-681577cd2a40): see the task file tc1012-upgrade.md.
