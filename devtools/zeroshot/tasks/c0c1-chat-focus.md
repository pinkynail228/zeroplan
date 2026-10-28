C0c1 — the chat input has focus on start (dogfood blocker D4; job J1 of docs/CHAT_RELEASE_JTBD.md).

Goal: the owner opens `zplan` and types into the chat at once. Today MainScreen sets `AUTO_FOCUS = "#plan-pane"` (terminal_planner/tui/app.py:977), so typed letters fire panel keys ('?' opened help instead of typing).

Write-set: terminal_planner/tui/app.py (MainScreen focus only), docs/USER_FLOW.md (only a sentence that says where focus starts, if one exists), TUI tests.

Acceptance criteria:
- A1 On start of the main screen the chat input (`#input`, app.py:991) has focus; typed letters, including `?` and the panel keys (p n c t g x o i w e), go into the input as text.
- A2 Tab still moves focus to the plan pane and back (binding app.py:968); once the pane is focused, its keys work on the first press.
- A3 One test per criterion through tests/tui_support.py, at 120x40.

Non-goals (reviewers must not require): tabs, layout widths, key-bar wording beyond what the focus change forces, other screens, the --plain UI.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_planning tests.test_tui_polish tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
