R-A attempt 3 — four regressions of the R-A change (commit 188a49f on zs-r-a-reopen-focus); R-A C4 narrowed.

Why: the merge gate (whole suite on the Mac, 2026-10-24) fails 4 tests on the R-A branch; all pass on main.
Attempt 2 stopped on a reviewer `conflict:` (2026-10-24): test_tui_milestones a3 (:1858-1863: Tab to the pane, `p`,
Esc, `i` opens details) and test_tui_chat c7 (:1793-1798: Tab to the pane, `s`, Esc, `p` opens the plan) need the
pane to keep focus when the owner opened the screen from the pane; R-A C4 sent focus to `#input` always. Orchestrator
decision: those tests are the contract; the dogfood defect is the case where the screen was opened from the input.
The worktree carries attempt 2's uncommitted move of `leave_to_input` into `ZplanApp` (fixes test_tui_split); keep it.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/screens.py, terminal_planner/tui/card_host.py,
tests/test_tui_reopen_fixes.py, tests/test_tui_merge_card.py.

Acceptance criteria:
- C1 (replaces R-A C4) Esc from PlanScreen or SettingsScreen returns focus to the widget that had it when the screen
  opened. Example: focus in `#input`, ctrl+s, Esc, type `/run` -> the input holds `/run`, no pane action fired; Tab to
  the pane, `p`, Esc, `i` -> details open (test_tui_milestones a3, unchanged). The tests.test_tui_reopen_fixes C4
  test is rewritten to the input-opened case and fails on main.
- C2 tests.test_tui_merge_card regression_a seeds its goal draft the way a draft written after the plan exists is
  stored (its identity names plan r1, as `append_plan_draft` does in tests/test_tui_draft_card.py:529), so R-A C1
  (a stale draft never opens as a card) holds and the test still proves a typed `/merge` reaches the card.
- C3 These pass: `python3.13 devtools/fasttest.py tests.test_tui_milestones tests.test_tui_chat tests.test_tui_split
  tests.test_tui_merge_card tests.test_tui_reopen_fixes` (test_tui_milestones and test_tui_chat unchanged).

Non-goals (reviewers must not require): a pane focus indicator; R-B mediums; behavior beyond R-A
(devtools/zeroshot/tasks/r-a-reopen-focus.md) other than C1 above; test_tui_chat c3 (known load flake, passes alone).

Risk: medium. DoD: `python3.13 devtools/fasttest.py tests.test_tui_milestones tests.test_tui_chat tests.test_tui_split
tests.test_tui_merge_card tests.test_tui_reopen_fixes tests.test_tui_draft_card tests.test_tui_live tests.test_toolchain`
exit 0; quote the `fasttest:` lines.
