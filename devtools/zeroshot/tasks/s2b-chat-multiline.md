S2b — the chat input takes several lines: it wraps, grows to 8 rows, and new-line keys work (A4 step 2, F3)

Orchestrator check 2026-10-28 after s2a (bd7ad10): `ChatInput` (tui/chat_input.py) is one row (soft_wrap off,
paste keeps line 1, `cursor_position` = column on row 0); `#input` height 1 and `#prompt-box` height 3
(tui/zplan.tcss:250-273). Textual 8.2.8's parser reads `\n` as ctrl+j, `\x1b[13;3u` alt+enter, `\x1b[13;2u`
shift+enter, but `\x1b\r` (Option+Enter as Meta) as plain `enter`, which would send.

Reuse: TextArea soft wrap and wrapped navigator; s2a's SkipAction arrows; s3a's byte filter before
`parser.feed` (theme.py:154 `read_input`); `on_input_submitted` (app.py, its card and palette order).

Write-set: terminal_planner/tui/chat_input.py, terminal_planner/tui/app.py, terminal_planner/tui/theme.py,
terminal_planner/tui/zplan.tcss, terminal_planner/tui/strings.py, tests/test_tui_chat_input.py, tests/test_tui_theme.py,
tests/test_tui_look.py, docs/USER_FLOW.md (test_tui_look.py: only its `#prompt-box` height pin, :85)

Acceptance criteria:
- M1 ctrl+j, alt+enter, shift+enter and `\x1b\r` (the filter turns it into alt+enter, also when ESC and CR come
  in two reads) add a new line; Enter sends the whole text. Example: bytes `ab\x1b\rcd\r` -> one turn "ab\ncd".
- M2 It wraps and grows from 1 to 8 visual rows, then scrolls with the cursor in view; the box stays at the pane's
  bottom; after a send it is one row again; a resize rewraps. Example:
  120x40, 12 lines typed -> 8 rows; at 80x24 the status line still shows.
- M3 Up on the first visual row and down on the last go to the screen's pick (history, palette, intro, card);
  inside the text they move the cursor; with the palette open they move its rows. Example: "a" ctrl+j "b", cursor
  on b, up -> cursor on a; up again -> the previous history entry.
- M4 A paste keeps its lines and never sends; while the value starts with `/` the new-line keys add nothing and a
  paste keeps its first line; an Enter on only spaces and new lines counts as empty (a card answer); a refused send
  keeps the text; history keeps multi-line entries; `cursor_position` is the offset in the whole text.
  Example: paste "x\ny" -> "x\ny", nothing sent; "/he" ctrl+j -> "/he".
- M5 The intro hint names the new-line key (ctrl+j); USER_FLOW says the keys in one sentence.
  Example: tests.test_tui_chat_empty passes.

Non-goals (reviewers must not require): a kitty-protocol switch, other inputs.

Conflict rule: if a test outside the write-set pins a size or a key this changes, change nothing in it and end
with `conflict: <file:line>`.

Risk: high (every chat keystroke). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_chat_input
tests.test_tui_theme tests.test_tui_look tests.test_tui_narrow tests.test_tui_chat tests.test_tui_commands
tests.test_tui_palette tests.test_tui_card_keys tests.test_tui_chat_empty tests.test_tui_chat_chrome
tests.test_tui_milestones tests.test_tui tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New tests fail
on today's code.
