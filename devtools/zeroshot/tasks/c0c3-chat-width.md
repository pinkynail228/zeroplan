C0c3 — the chat takes about half of the screen width (slice C1 of docs/CHAT_RELEASE_JTBD.md, job J1; ~/zs-pause/dogfood/findings.md item 5).

Goal: the chat is the main surface, but today `#chat-pane` is `width: 2fr` and `#plan-pane` `width: 3fr` (terminal_planner/tui/zplan.tcss:28-38), so the chat gets 40% and long answers wrap early.

Data reach: CSS only; the widths come from zplan.tcss:28-38; the test reads `app.query_one("#chat-pane").region.width` and the screen width.

Write-set: terminal_planner/tui/zplan.tcss (those two width rules only), docs/USER_FLOW.md only if it states the split, tests/test_tui.py (A1's test and the size in test_a3_panel_matches_the_plain_overview_of_the_same_store), tests/test_tui_chat.py (the SUPPORTED / UNSUPPORTED size tables of ChatHeaderFieldTests and their region comments).

Acceptance criteria:
- A1 At 160x45 and 120x40 the chat pane's width is between 45% and 55% of the screen width.
- A2 The rules are exactly `#chat-pane { width: 1fr; }` and `#plan-pane { width: 1fr; }`; no min-width, max-width or other new layout rule.
- A3 Existing tests whose expectations depend on the old 2:3 split are re-measured, not weakened. Measured on main a6906dc with only the 1fr/1fr change, exactly these fail (2026-10-22): test_tui.PanelTests.test_a3_panel_matches_the_plain_overview_of_the_same_store (at 120x40 the plan line "задача 1/1 (T1)" now wraps: run it at 160x45 instead) and test_tui_chat.ChatHeaderFieldTests.test_g7_below_the_supported_layout_the_header_is_dropped (58x17 now gives a 25-column chat region). Recompute SUPPORTED / UNSUPPORTED so the first supported size gives exactly the L-1 minimum chat region (app.CHAT_MIN_COLS x CHAT_MIN_ROWS), the unsupported ones give a chat region one column short, one row short, and far below both, and update the region comments with the measured regions. No assertion is removed or loosened; no other existing test changes.

Non-goals (reviewers must not require): tabs, keeping the old size tables, narrow-screen fallbacks, colours, borders, any app.py change.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_polish tests.test_tui_planning tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
