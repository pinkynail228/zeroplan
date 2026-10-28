N1 — chat polish: one status line, plain preview, one draft label

Newcomer 0.6.3 defects 4, 5, 8 (9 is D1's) (pause dir: dogfood findings-2026-10-27-063-newcomer.md). app.py
`status_note` survives a card's `/plan` (card_host.py `action_plan`; only a typed command clears `chat_note`);
`render_status` stacks it under the thinking row; chat_view.py `thinking_row` shows raw markdown; the model writes
«Черновик цели:» above the block the app labels (chat.py `DRAFT_KINDS`); architect.py `DRAFT_RULES` says the owner
copies drafts into zplan.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, terminal_planner/tui/chat_view.py,
terminal_planner/tui/chat.py, terminal_planner/tui/strings.py, terminal_planner/architect.py,
tests/test_tui_chat_chrome.py, tests/test_tui_chat_messages.py, tests/test_architect.py, tests/test_tui_split.py,
tests/test_tui_low_batch.py (new)

Acceptance criteria:
- B1 A card's `/plan` clears the note as a typed command does; while the thinking row shows, the note is not drawn
  (one status line). Example: note shown, click «да, составить план» -> the note is gone; turn running -> one line.
- B2 The thinking preview drops markdown markers: `**`, `__`, backticks, leading `#`s, a leading `- ` or `* `; the
  L-2 escape is kept. Example: live «## **Смотрю** `app.py`» -> «Смотрю app.py».
- B3 A prose line right before a draft block that is only that block's label is not drawn. Inputs: «Черновик
  цели:», «**Черновик цели:**», «черновик цели», the same for «черновик ответа»; any other line stays.
  Example: «Вот.» / «Черновик цели:» / goal block «X» -> «Вот.», then «↳ черновик цели: X», no other label line.
- B4 `DRAFT_RULES` says zplan shows each draft as a card with buttons and the architect never asks the owner to
  copy or send a draft. Example: the first-turn preamble holds no «copies a draft».

Also: strings.py chat section comment names `chat.intro` (no «greeting»); en/zh intro keys are ru copies.

Tests: tests/test_tui_low_batch.py covers B1-B4.

Non-goals (reviewers must not require): other phrasing (start phrase, run reports); cards (D1); en/zh
translations; other notes or rows; history replies.

Risk: low. DoD: `python3.13 devtools/fasttest.py tests.test_tui_low_batch tests.test_tui_chat_chrome
tests.test_tui_chat_messages tests.test_architect tests.test_tui_split tests.test_toolchain`: exit 0 (full suite: the gate).
