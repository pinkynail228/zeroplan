O3 — typing a `/` command: Tab completes, arrows pick, Enter runs the pick

Owner Mac test of 0.6.0 2026-10-26 (pause dir, dogfood, findings-2026-10-26-owner-mac.md) O3: "Tab and the rest do
not work when I type commands". Plan docs/RELEASE_0.6.1_PLAN.md "Owner Mac test", O3. The palette
(tui/palette.py:70) only draws rows; Tab is a priority `toggle_focus` (tui/app.py:628, :1540); Up/Down do nothing
in the input; `/op` + Enter is an unknown command.

Write-set: terminal_planner/tui/palette.py, terminal_planner/tui/app.py, terminal_planner/tui/strings.py,
terminal_planner/catalog.py (bar hints only), docs/REFERENCE.md (generated), docs/TERMINAL_UX_BRIEF.md (keys line),
tests/test_tui_palette.py, tests/test_tui_chat.py, tests/test_tui_chat_scroll.py, tests/test_tui_narrow.py,
tests/test_tui_reopen_fixes.py, tests/test_tui_planning.py.

Acceptance criteria:
- C1 The palette has a highlighted row (the first by default). Up/Down move it while the palette is shown, wrapping
  at the ends. Example: input `/`, Down twice -> the third row is highlighted.
- C2 Tab while the palette is shown fills the input with the highlighted command's name plus a space, and the
  palette re-filters. With one match, it completes that match. Example: `/ap` + Tab -> input `/approve `.
- C3 Enter while the palette is shown and the input holds only a prefix of a command (no argument) runs the
  highlighted command, as if its full name had been typed. Example: `/ap` + Enter -> runs `/approve`. A full
  command with an argument keeps today's path.
- C4 With the palette hidden: Tab keeps switching between the input and the plan pane (today's behaviour), and
  Up/Down in an empty input recall the owner's previous lines of this run (newest first; Down returns to empty).
  Example: send «привет», then Up -> the input holds «привет».
- C5 The bar and docs/TERMINAL_UX_BRIEF.md name the new keys (Tab completes, ↑↓ pick) in both languages through
  `strings.py`. Example: palette shown -> the bar shows the completion hint.

Non-goals (reviewers must not require): fuzzy matching (prefix stays); completion of command arguments; history
saved across restarts; the chat text and other screens (O4, O1).

New tests go in tests/test_tui_palette.py; the other test files change only where they pin today's keys (O4 runs
in parallel and edits tests/test_tui_chat.py).

A test outside the write-set asserting Tab = focus switch while the palette is shown -> `conflict:`.

Risk: medium (input keys on the main screen). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_palette,
tests.test_tui_chat, tests.test_tui_chat_scroll, tests.test_tui_narrow, tests.test_tui_reopen_fixes,
tests.test_tui_planning, tests.test_tui_strings, tests.test_reference, tests.test_tui,
tests.test_toolchain: exit 0.
