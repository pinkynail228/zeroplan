D3 — the chat keeps its latest items in view after `/merge`

Newcomer check 2026-10-27 defect 3, plus 11 (pause dir: dogfood findings-2026-10-27-063-newcomer.md, caps 26b,
27, 23 in ux-audit/sb14/caps): at 80x24, for ~10 s after `/merge` the chat shows nothing after «✓ План r1
предложен» (reply, merge card, question gone); they come back with the next architect reply. Cap 26b shows a
scrollbar near the top, so the likely cause is the scroll leaving the bottom while the entries are still mounted.
After a resize to 100x30 the chat is not pinned to the bottom (the merge question's last line cut). Path:
card_host.py `merge_settled` -> `close_card` / `show_card`; chat.py `_turn(owner=False)` reloads in `finally`
`_sync_later`; app.py `sync_chat_history`, `chat_go_end`, `show_chat` / `show_canvas` / `apply_narrow`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, terminal_planner/tui/chat.py,
tests/test_tui_chat_scroll.py, tests/test_tui_merge_card.py, tests/test_tui_chat_after_merge.py (new)

Acceptance criteria:
- C1 First a pilot test at 80x24 reproduces the gap: a chat with entries and an open merge card, `/merge` settled,
  then a check that the newest entry and the card's done line are inside the visible region (scroll_y vs
  max_scroll_y and the mounted entries). It fails on the current code; the report names the cause found.
  Example: before the fix the test fails on the visible-region assertion.
- C2 After `/merge` settles and while the architect's turn runs, the chat stays at the bottom when it was at the
  bottom: every item shown before `/merge` that still exists stays mounted, the newest is visible. Example: 80x24,
  `/merge` -> the merge card's done line and the owner's `/merge` line visible at all times until the reply.
- C3 A resize (80x24 -> 100x30 -> 140x40) with the chat at the bottom keeps it at the bottom. Example: after the
  resize the last line of the newest entry is visible.
- C4 An owner who scrolled up (PgUp) is not pulled down by `/merge` settling or a resize. Example: PgUp, then a
  merge settles -> scroll_y unchanged.

Tests: tests/test_tui_chat_after_merge.py covers C1-C4 at 80x24 and 140x40; existing chat scroll tests are kept.

Non-goals (reviewers must not require): merge logic, card texts, step rows, duplicate merge lines (defect 6),
history storage.

Risk: low-medium (chat scroll and remount). DoD: `python3.13 devtools/fasttest.py tests.test_tui_chat_after_merge tests.test_tui_chat_scroll tests.test_tui_merge_card tests.test_toolchain`: exit 0 (the full
suite is the merge gate's).
