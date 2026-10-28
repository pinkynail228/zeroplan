S1 — leaving the whole-screen scheme returns the chat where it was

t4e (merged fcaa9eb): `/scheme` hides the chat and Esc brings it back (app.py toggle_scheme_full). Visual check
120x40 (2026-10-28): after Esc the chat at the bottom before `/scheme` is no longer at its end; the last message's
first line is cut off above the input ("_invalid]" shows, "zplan tools are not installed" does not).

Reuse: the chat scroll rule R-4 (tests/test_tui_chat_scroll.py: "at the bottom" is `#chat` scroll_offset.y ==
max_scroll_y); `full_return` and `settle_scheme` in toggle_scheme_full; the screen-reading helpers in
tests/tui_support.py.

Write-set: terminal_planner/tui/app.py, tests/test_tui_scheme_tab.py.

Acceptance criteria:
- S1 A chat at its end before `/scheme` is at its end again after Esc, once the layout has settled.
  Example: 120x40, one long system message, `/scheme`, Esc -> `#chat` scroll_offset.y == max_scroll_y and the
  message's first line is on screen.
- S2 A chat scrolled up before `/scheme` keeps its position after Esc. Example: PageUp, `/scheme`, Esc -> the same
  scroll_offset.y as before `/scheme`.

Non-goals (reviewers must not require): the scheme's own scroll; the Activity pane; R-4 itself.

Conflict rule: if keeping the position needs a change to the chat's own scroll rule (R-4), change nothing and end
with `conflict: <file:line>`.

Risk: low (one screen's layout return). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_tui_scheme_tab tests.test_tui_chat_scroll tests.test_toolchain`: exit 0; `python3 devtools/budget.py`:
OK. Each new test fails with the scroll restore removed.
