W1 — the chat is the wide column; the canvas column takes 40%

docs/RELEASE_0.6.3_PLAN.md V6. Today zplan.tcss gives `#chat-pane` 38% and `#right-column` the rest, so at 100x30
the conversation is 36 columns wide and long replies wrap every few words (sandbox capture sb13 09-reply,
2026-10-27). The owner-approved lab devtools/ui-lab/chat.py has the chat `1fr` and the side column 44 wide.

Trial on 2c2ea7c (only the two tcss widths changed, full suite, under load): failed test_tui a3 panel,
test_tui_canvas_files a1_a4, test_tui_live la1, test_tui_look a1_a2 and a3, test_tui_narrow a3, test_tui_flow,
test_tui_scheme_tab (record /tmp/zs-zplan/w1-trial.log). Attempt 2 diff /tmp/zs-zplan/w1-chat-wide-a2.diff did the
work and timed out only on a second full-suite run: reuse it, run only the DoD modules (the merge gate runs the suite).

Write-set: terminal_planner/tui/zplan.tcss, tests/test_tui.py, tests/test_tui_look.py, tests/test_tui_canvas_files.py,
tests/test_tui_live.py, tests/test_tui_narrow.py, tests/test_tui_flow.py, tests/test_tui_scheme_tab.py

Acceptance criteria:
- C1 At 100 columns and wider, `#chat-pane` is `width: 1fr` and `#right-column` is `width: 40%`. Example: 140x40
  -> chat pane region 84 wide, right column 56; 100x30 -> chat 60, right 40 (each ±1).
- C2 Below 100 columns nothing changes: the chat alone at full width, the canvas hidden (test_tui_narrow A1).
  Example: 80x24 -> chat region width == screen width.
- C3 Only the split changes: borders, focus colours, tabs, the activity pane and every pane's content stay as
  today. Example: at 120x40 the plan tab still shows `Плана нет.` and the activity pane its idle line.

Tests: test_tui `test_a1_the_chat_pane_takes_the_lab_38_percent` and test_tui_look's 38% pins become the new
split (at 100x30, 120x40, 160x45, read from the regions); tests that only wrapped text at 38% get the new wrap,
keeping what they assert.

Non-goals (reviewers must not require): a side plan panel inside the chat; narrow mode; message, card or bar look;
translations.

Risk: low (layout only). DoD: `python3.13 devtools/fasttest.py` tests.test_tui, tests.test_tui_look,
tests.test_tui_canvas_files, tests.test_tui_live, tests.test_tui_narrow, tests.test_tui_flow, tests.test_tui_scheme_tab,
tests.test_toolchain: exit 0.
