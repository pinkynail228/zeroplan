U1b — the status line names only a real architect turn; an event turn reads as one plain entry

The orchestrator's newcomer check 2026-10-26 (0.6.1): during a 19-minute run the bar kept «M1 идёт … · архитектор
отвечает» while Codex ran three turns of 13-50 s. U1's `MainScreen.turn_clock` (terminal_planner/tui/app.py) reads
`ArchitectChat.busy` (terminal_planner/tui/chat.py:590), which is also true while a bare event check waits in
`port.pending()` (`_mode == "check"`, chat.py `_check`). The chat also showed each event turn's whole prompt
(terminal_planner/feed.py `summary`: the «Статус: {json}» line and «Оцени их по снимку…»).

Write-set: terminal_planner/tui/chat.py, terminal_planner/tui/app.py, terminal_planner/tui/chat_view.py,
tests/test_tui_activity.py, tests/test_tui_chat.py.

Acceptance criteria:
- C1 The bar's «архитектор отвечает {clock}» shows only while an architect turn runs (an owner turn, or an event turn
  after the check promoted its batch); a bare check never shows it, and the clock starts when the turn starts.
  Example: a check waiting in `pending()` with no wake event -> no phrase; the event turn it then starts -> phrase
  from 0:00.
- C2 An event turn's row in the chat shows the event lines only: the head «События с прошлого хода:» may stay, the
  status line (feed.py `STATUS_PREFIX`) and the closing instruction are never shown; the prompt sent to the
  architect and the stored transcript stay as they are. Example: the row reads «M1 попытка 1: running ->
  awaiting_merge», no `{"plan":` and no «Оцени их».
- C3 U1's cancel note and the narrow-width drop order stay as they are. Example: Esc on an owner turn ->
  «Ответ архитектора отменён.»; a narrow bar drops « · архитектор отвечает» first.

Non-goals (reviewers must not require): feed.py or the event prompt text; English; other bar texts.

Risk: low (display only). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_activity, tests.test_tui_chat,
tests.test_tui_commands, tests.test_new_session, tests.test_tui_strings, tests.test_toolchain: exit 0.
