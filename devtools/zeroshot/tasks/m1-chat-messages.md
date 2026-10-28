M1 — chat messages without author lines: owner accent bar, architect replies as markdown

docs/RELEASE_0.6.3_PLAN.md V2. Today an entry is a plain `ChatMessage` of `chat.entry_lines`. Look:
devtools/ui-lab/chat.py states dialog, long-reply, error (`reply()`, `Reply`, `LeftHeading`, `TightCode`, `.owner`).
Attempt 2 diff /tmp/zs-zplan/m1-chat-messages-a2.diff failed only test_fixture_scope a4 and test_tui_rb_fixes c4
(they pin the author word `архитектор`): reuse it, fix those two.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/chat.py, terminal_planner/tui/chat_view.py,
terminal_planner/tui/zplan.tcss, terminal_planner/tui/strings.py, tests/test_tui_chat.py,
tests/test_tui_chat_dedupe.py, tests/test_tui_look.py, tests/test_tui_chat_scroll.py, tests/test_tui_draft_card.py,
tests/test_layout.py, tests/test_tui_split.py, tests/test_tui_chat_chrome.py, tests/test_tui_strings.py,
tests/test_fixture_scope.py, tests/test_tui_rb_fixes.py, tests/test_tui_chat_messages.py (new)

Acceptance criteria:
- C1 No entry has an author line. A dim centred time line stands before the first shown entry and before any
  entry stored 10 min or more after the previous one: local `HH:MM`, `DD.MM HH:MM` when not today (P2a zone rule).
  Example: owner 10:00, architect 10:01, owner 10:30 -> time lines `10:00`, `10:30` only; no `ты ·`/`архитектор ·`.
- C2 An owner entry: bright text behind a yellow left bar (`border-left: outer ansi_yellow`), a blank row above.
  An architect entry: a bold magenta `●` in a 2-cell gutter, then its text rendered as rich Markdown (headings bold
  and left, lists, fenced code without background, hyperlinks off); no left bar. Example: `## План\n- M1`
  -> a row `● План` without `##`, a row with `• M1`.
- C3 L-2 runs on the raw text before Markdown: sequences removed or escaped per line as today; model markup is
  never interpreted. Example: reply `[bold]x[/] \x1b[31my` -> shows `[bold]x[/] y` literally.
- C4 Draft lines lose the `ответ N`/`арх` prefixes: `↳ черновик цели: <text>` (an answer:
  `↳ черновик ответа M1: <text>`), dim; a draft already in the text stays collapsed at its block. `reply_names` goes.
  Example: one unmatched goal draft `Сделать X` -> exactly one row `↳ черновик цели: Сделать X`.
- C5 Error entries: a red `!` gutter and the text; reset and event entries unchanged (V3).
  Example: an error entry `сбой сети` -> a row `! сбой сети`.

Tests: replacing the author line and the draft prefixes deletes the tests pinning them (test_tui_look a5,
test_tui_chat i9_a5, test_tui_chat_dedupe naming tests, test_tui_strings a6 events author); one invariant test
in tests/test_tui_chat_messages.py at 80x24 and 140x40 covers C1-C5; the L-2 tests are kept.

Non-goals (reviewers must not require): indicator, bar, cards, event rows, empty chat; feed.py; store; translations.

Risk: low (display). DoD: `python3.13 devtools/fasttest.py` (the full suite): exit 0.
