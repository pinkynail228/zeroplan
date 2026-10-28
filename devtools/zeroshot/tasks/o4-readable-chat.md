O4 — the chat shows the current conversation only; `/new` starts a clean one

Owner Mac test of 0.6.0 2026-10-26 (pause dir, dogfood, findings-2026-10-26-owner-mac.md) O4: "complete mess in
the chat with the architect, I don't understand what happens; opened in our repo, something is already written;
/new doesn't clear it". Plan docs/RELEASE_0.6.1_PLAN.md "Owner Mac test", O4. `entries_of` (tui/chat.py:150)
shows the last 40 rows of every session; `/new` (chat.py:901 `_new_session`) only appends; the handoff and warm-up
prompts (chat.py:406-410) are stored as `events` rows and shown as «соб» entries, the warm-up one with the whole
STATE and a JSON snapshot.

Write-set: terminal_planner/tui/chat.py, terminal_planner/tui/chat_view.py, terminal_planner/architect.py (only
the store/turn role handling), terminal_planner/tui/strings.py, tests/test_new_session.py, tests/test_tui_chat.py,
tests/test_architect.py.

Acceptance criteria:
- C1 The chat pane shows only the rows from the last `reset` row on (the reset row is the first line, one short
  «новый диалог» line); with no reset row, all rows as today, still capped at `HISTORY`. The store keeps every row.
  Example: transcript A, B, reset, C -> the pane shows reset, C.
- C2 The handoff and warm-up prompts zplan sends on `/new` are stored with a role of their own (e.g. "system")
  that the pane never shows; the architect's replies to them stay visible. Rows already stored as `events` whose
  text begins with the handoff or warm-up prompt are hidden too (old stores). Example: `/new` -> the pane shows the
  reset line and the architect's warm-up reply, no «Новая сессия… STATE проекта…» entry.
- C3 After `/new` completes, nothing from before the reset is on the chat pane (rows, live text, the last note).
  Example: chat with 10 rows, `/new` -> the pane holds the reset line and the warm-up reply only.
- C4 A start of zplan in a project shows the current conversation (rows since the last reset), not earlier ones.
  Example: store A, reset, B, C -> start -> B, C with the reset line.
- C5 Turn counting, rot signal, feed acks and draft actions keep working on the shown rows. Example: tests.test_tui_chat
  draft and rot tests pass (adapted only where they count hidden prompt rows).

Non-goals (reviewers must not require): wording of architect replies; event-line wording; inline cards; the
header rows; English texts (O1a); app.py.

New tests go in tests/test_new_session.py (O3 runs in parallel and edits tests/test_tui_chat.py).

A test outside the write-set asserting a hidden prompt row or a pre-reset row on the pane -> `conflict:`.

Risk: medium (transcript roles and the store). DoD: `python3.13 devtools/fasttest.py` tests.test_new_session,
tests.test_tui_chat, tests.test_architect, tests.test_architect_home, tests.test_feed_wiring,
tests.test_tui_draft_card, tests.test_tui, tests.test_toolchain: exit 0.
