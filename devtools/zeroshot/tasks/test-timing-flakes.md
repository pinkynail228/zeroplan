test-timing-flakes — devtools/test-harness repair for timing failures seen under full-suite load (ORCHESTRATOR step 2 exception path, merge int-s2a2b bc64c19; critic int-s2a2b). Lane: devtools. DeepSeek worker, sol reviewers. Critic task gate: pending (write the requirements below out to the step-1 standard before launch).

Failures (diff-independent, reruns green):
- Linux `tests.test_tui_milestones.StaleModalTests.test_b5_an_action_on_a_modal_whose_attempt_moved_is_rejected_and_re_rendered`: `until()` (tests/test_tui.py:272) missed its deadline by 16 ms waiting for "Влить результат M1 в main?" (~/zs-pause/int-s2a2b-bc64c19-linux.log); 3/3 module reruns OK.
- macOS `tests.test_terminal_planner.TerminalTests.test_real_pty_ctrl_c_detaches_status_shows_running_and_w_reattaches`: 5 s `subprocess` timeout of the `--plain ... --fixture test` child (~/zs-pause/int-s2a2b-bc64c19-mac.log); 2/2 module reruns OK; earlier ~/zs-pause/merge-496f046-mac*.log. Known cause (2026-10-20, critic s1a1b1-merge): when the suite runs as a `&` job of a non-interactive shell the child inherits SIGINT=SIG_IGN, Ctrl-C never detaches and the test hangs (reproduced on main bdf708e and candidate 043963d; foreground 3/3 OK; ~/zs-pause/s1a1b1-realpty-diag). Fix: reset SIGINT to SIG_DFL in the test's `controlling_terminal()` preexec (tests/test_terminal_planner.py, PTY setup); acceptance: the test passes when the suite is launched as a background `&` job. Check whether the earlier timeouts had the same launch. Same watch list: macOS `test_a4_a_slow_setup`, Linux test_tui_chat `test_a3_a_chat_goal_handed_over...` (STATE Open).

Goal: first establish the cause of each failure from the evidence (load, a fixed wall-clock deadline, a missing synchronization point), then fix the class in the harness: waits bound by an explicit event or by a deadline derived from one shared, documented test-timeout policy, never by a per-test literal tuned to pass. Product code changes only if a cause in product code is demonstrated.

Acceptance (to be completed at the task gate): each listed test stays deterministic under an injected slow scheduler or CPU load reproduction (the failure reproduced on the base first, recorded in the receipt), passes with the fix, and a mutation restoring the old wait fails.

Write-set: tests/ helpers (`tests/test_tui.py` `until`, the PTY helpers of tests/test_terminal_planner.py), the listed tests, the receipt.

Size: ~20 product / ~150 tests. Report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).
