S2a — the chat input becomes a TextArea that still behaves as today's one-line Input (step 1 of A4)

Tester F3 2026-10-28: a long message hides in one row. s2a swaps the widget; s2b adds lines. `#input` is an `Input` (tui/app.py:946); the handlers read `event.value`/`event.input.id`
(app.py:1844, 1855); history, palette and intro use `.value`/`cursor_position` (app.py:2004-2080, 3138-3150).

Reuse: `TextArea` (Textual 8.2.8: `placeholder`, `compact`); Message's `namespace`
(textual/message.py:75) so `namespace="input"` keeps `on_input_changed`/`on_input_submitted`; Input's paste rule
(textual/widgets/_input.py:758: first line only); the screen's `pick` action (app.py:900).

Write-set: terminal_planner/tui/chat_input.py (new), terminal_planner/tui/app.py, terminal_planner/tui/card_host.py,
terminal_planner/tui/zplan.tcss, tests/test_tui_chat_input.py (new), tests/test_fixture_scope.py,
tests/test_tui_chat.py, tests/test_tui_commands.py, tests/test_tui_run_command.py, tests/test_tui_language.py
(the last five: retype only; test_tui_language.py:98 `ui.Input`).

Acceptance criteria:
- C1 `#input` is `ChatInput(TextArea)` with the Input API used here: `value` (set puts the cursor at the end),
  `cursor_position`, `insert_text_at_cursor`, `placeholder`; it posts Changed/Submitted with `.input` and `.value`
  under namespace "input"; each `query_one("#input", Input)` names ChatInput.
  Example: type "ab" -> on_input_changed value "ab"; Enter -> on_input_submitted value "ab", the field empty.
- C2 One line, as today: Enter sends and never adds a newline; paste inserts the first line only; up/down go to the
  screen's pick (history, palette rows, intro examples, card) because ChatInput's own up/down forward on its first
  or last row (always, while it has one row); left/right, pageup, tab, escape, `/` as today.
  Example: history ["a","b"], empty field, up -> "b"; "/re" then down -> the next palette row; paste "x\ny" -> "x".
- C3 The look: one row, no border, no line numbers, the placeholder shown; the screen's size and layout unchanged.
  Example: tests.test_tui_look and tests.test_tui_narrow pass with no edit.
- C4 Forwarded typing and card keys: type_in_chat appends at the end (app.py:3142); card_host's placeholder and
  value sync (card_host.py:157-168). Example: field "ab", `x` typed on the plan screen -> "abx".

Non-goals (reviewers must not require): more than one line, growth, row-aware arrows, docs, other inputs.

Conflict rule: if a test outside the write-set breaks on the swap, change nothing in it and end with
`conflict: <file:line>`.

Risk: high (every chat keystroke). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_chat_input
tests.test_tui_chat tests.test_tui_commands tests.test_tui_run_command tests.test_fixture_scope tests.test_tui_look
tests.test_tui_narrow tests.test_tui_palette tests.test_tui_card_keys tests.test_tui_milestones tests.test_tui
tests.test_tui_language tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. New tests fail on today's
Input (C1, C2).
