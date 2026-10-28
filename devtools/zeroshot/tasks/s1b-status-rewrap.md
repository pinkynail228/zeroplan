S1b — leaving the whole-screen scheme redraws the status lines at the chat's real width

t4e (merged fcaa9eb): `/scheme` hides the chat pane and Esc brings it back (app.py toggle_scheme_full). s1 guessed a
chat scroll defect; its run found the chat scroll intact, and a probe (2026-10-28, 120x40, tests/test_tui_scheme_tab
shell) shows the real one: Esc calls render_state before the layout returns, so render_status measures the hidden
`#chat-pane` (content width 0 -> `room` 20), wraps "zplan tools are not installed: run zplan setup. [code:
setup.tools_invalid]" at 20 cells and keeps the last 2 rows: "_invalid]" is all that shows, and it stays so after
the pane is back at 68 cells until the status text changes for another reason.

Reuse: render_status as it is (`status_text` dedupe, `wrapped`, STATUS_SHARE); `settle_scheme` /
`call_after_refresh` in toggle_scheme_full; the shell helpers and `screen_text` (tests/tui_support.py).

Write-set: terminal_planner/tui/app.py, tests/test_tui_scheme_tab.py.

Acceptance criteria:
- B1 After Esc from `/scheme`, once the layout has settled, `#status` is wrapped at the chat pane's real width: the
  same lines as before `/scheme`. Example: 120x40, the tools-not-installed message, `/scheme`, Esc -> the screen
  shows "zplan tools are not installed: run zplan setup. [code:" and "setup.tools_invalid]".
- B2 The status is never wrapped for a hidden pane: while the whole-screen scheme is shown, a status update does not
  store text measured at width 0. Example: a status change during `/scheme`, then Esc -> the lines at 68 cells.

Non-goals (reviewers must not require): the chat scroll (s1 found it intact); the scheme's own drawing; status
wording or the 40% cap.

Conflict rule: if the fix needs a change to how other panes resize, change nothing and end with `conflict:
<file:line>`.

Risk: low (one screen's status after a layout toggle). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_tui_scheme_tab tests.test_tui_chat_scroll tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK.
Each new test fails with the fix removed.
