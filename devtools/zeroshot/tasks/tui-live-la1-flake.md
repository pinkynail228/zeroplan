tui-live-la1-flake — make test_tui_live.PanelTests.test_la1 deterministic. Observed 2026-10-18 on the Linux test host: `AssertionError: 'идёт 0 с' not found in ...` at tests/test_tui_live.py:144 (the pane still shows "… запускаю M1…"). It failed on candidate 74fff14 and on base 4cc80bc in alternating runs (receipt ~/zs-pause/merge-u3b-drafts-answer/RECEIPT.md). Working hypothesis: driver.entered proves watch entry, not delivery of the running snapshot through ZplanApp.got_snapshot and changed(). The started callback has already run. A-2 must reproduce this ordering. DeepSeek worker, sol reviewers.

Read: tests/test_tui_live.py (PanelTests, `start_held`, `Stepper.watch` and the helpers they use), the pilot/wait helpers other TUI tests use to wait for a rendered state (tests/test_tui*.py), terminal_planner/tui/app.py (`got_snapshot`, `changed`, the started callback) and live.py, only as far as needed.

Rules:
- R-1 Keep the driver-entry wait, then wait up to 5 real monotonic seconds for 'идёт 0 с' in self.pane(), yielding through Pilot; report the current pane on timeout. Keep the original assertion. Do not advance the fake clock, release a watch turn, request a refresh, or add a fixed sleep. No production change; if the cause proves to be a production race, stop and say so in the test docstring.
- R-2 Audit PanelTests for the same driver-entry → immediate-pane-assert ordering; fix only demonstrated matches and list their test names, or "none beyond LA1", in the regression docstring.
- R-3 What la1 checks stays the same: slow records, a quiet gap, replays, a lost observation.

Acceptance criteria:
- A-1 Inside the run, execute test_tui_live.PanelTests 20 consecutive times using the preamble environment; every run executes the tests without skips. The orchestrator then runs `devtools/linux-test.sh test_tui_live.PanelTests` 10 times in a row on the Linux host on the same unchanged candidate SHA and records each exit and test/skip counts.
- A-2 In an isolated scratch copy, defer delivery of running-M1 snapshots to got_snapshot after startup; allow the worker to reach driver.entered and confirm the pane still lacks 'идёт 0 с'. Release deferred snapshots only after the new pane predicate has first evaluated false; record that this branch was reached. With only the new pane wait removed, LA1 must fail at its original assertion before release; with the wait restored, the complete LA1 must pass. Keep the UI loop running, use bounded barriers, and release/restore everything in finally. Record the complete temporary patch/harness, exact commands and outcomes in the regression docstring; do not commit the injection.
- A-3 `devtools/linux-test.sh test_tui_live` and `devtools/mac-test.sh test_tui_live` pass on the unchanged candidate without skips; orchestrator-owned checks supplement the standard merge gate.

Size: ~10-80 lines.
Out of scope: other flaky tests (STATE Open, Mac suite).
critic la1-flake-task: GO WITH CHANGES, applied (session 01a1508e-1b00-7390-934a-ed6f1b89ddf2)
