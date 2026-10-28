followups-1 — two small fixes found while gating the night's merges.

Goal and evidence:
1. Since c0c3 (964d440, chat and plan panes `width: 1fr`) the plan pane at 120x40 is ~60 columns, so the milestone row wraps "статус отправки неизвестен" across two screen lines with the chat pane's text between them; `JourneyTests.test_b3_submission_unknown_is_shown_and_never_resent` (tests/test_tui_milestones.py:360) and `UxNoteTests.test_missing_driver_blocks_driver_actions_with_the_tools_remedy_in_both_uis` (:980) fail on main (reproduced 2026-10-22 on mac and Linux) because `flat()` reads the whole screen. The product text is right; the tests read it the wrong way.
2. review-timeout (823a1fa) gave final_verify/final_reverify the worker budget but left their no-open-task twins `empty_final_verify`/`empty_final_reverify` (same body: they re-run every milestone check) at 20 min, so a resumed attempt with all tasks done can still time out the same way.

Data reach: tests/test_tui_milestones.py (`flat`, `shows`, the two tests; `PlanPanel` id `plan-pane` in terminal_planner/tui/app.py); terminal_planner/milestone.py `review_timeout = CONTROL_TIMEOUT if prefix else WORKER_TIMEOUT` in the final stage; tests/test_milestone.py `test_executable_contracts_and_runtime`.

Write-set: tests/test_tui_milestones.py, terminal_planner/milestone.py, tests/test_milestone.py.

Acceptance criteria:
- A1 The two TUI tests pass at 120x40 and still check that the plan pane says the submission status is unknown: read the text of the `#plan-pane` widget (whitespace-joined like `flat`) instead of the whole screen for that assertion. No product change for this item.
- A2 empty_final_verify and empty_final_reverify get WORKER_TIMEOUT; the long-node set in test_executable_contracts_and_runtime includes them, so the test fails if they go back to 20 min.

Non-goals (reviewers must not require): layout changes, other tests, other timeouts.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_tui_milestones tests.test_milestone tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
