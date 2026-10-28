C1 — the chat pane shows the conversation; chrome moves to the indicator and the bar

docs/RELEASE_0.6.3_PLAN.md V1. Look: devtools/ui-lab/chat.py states thinking, working, note.
Attempt 1 diff /tmp/zs-zplan/c1-chat-chrome-a1.diff failed only test_tui k1d: reuse it.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/chat_view.py, terminal_planner/tui/chat.py,
terminal_planner/tui/activity.py, terminal_planner/tui/zplan.tcss, terminal_planner/tui/strings.py, tests/test_layout.py,
tests/test_tui_chat.py, tests/test_tui_chat_scroll.py, tests/test_tui_activity.py, tests/test_tui_look.py,
tests/test_tui_commands.py, tests/test_tui_live.py, tests/test_new_session.py, tests/test_tui_split.py,
tests/test_tui.py, tests/test_tui_chat_chrome.py (new)

Acceptance criteria:
- C1 `#chat-head` and `CHAT_HEADER_ROWS` go; a short conversation sits at the scroll's bottom, right above the
  indicator. Example: gpt-6.1-sol/high, provider openai, usage (3, 15600), two entries, 100x30 -> no row
  holds `provider`, `CODEX_HOME` or `ходов`; no blank row between the last entry and the indicator.
- C2 The bar ends, dim, with `model/effort · N ток` (N: `short_count`), then `chat.rot` when
  the session is long; the tail is dropped whole before any other field is cut. Example: 100 cols -> the bar
  ends `gpt-6.1-sol/high · 15.6k ток`; 80 cols, long project name -> no tail, rest as today.
- C3 `#status` (id kept) moves directly above the palette and prompt box; top to bottom: the running turn's one
  row `<spinner> Архитектор думает… M:SS · <live>` (spinner `◐◓◑◒`, a step a second), else the newest planner
  or run line wrapped in full (its `/attempt` remedy kept), a run note; then the chat's own lines
  (note, outcome, refusal) wrapped in full. Example: turn at 7 s, live `читаю план`, a lock refusal -> `◑ Архитектор
  думает… 0:07 · читаю план`, then the refusal with remedy and code; planner lines a, b -> only `b`.
- C4 `app.chat_note` clears on the owner's next accepted send or command, whatever set it. Example:
  `/language en` -> «Пока доступен только русский язык»; owner sends `привет` -> note gone.
- C5 L-2/L-4 hold for the indicator (split on LF, escape per line, one row); tests move here. Example: live
  `a\tb\x1b[31mc\nd` -> one row `a\tbc d`: TAB escaped, the full sequence removed.

Tests: delete header-row pins (test_layout l3, test_tui_chat c9); tests/test_tui_chat_chrome.py covers C1-C3 at
80x24 and 140x40.

Non-goals (reviewers must not require): message look, cards, event rows, the empty chat; feed.py; the right
column, narrow mode, other bars; translations.

Risk: low (layout, text). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_chat_chrome,
tests.test_layout, tests.test_tui_chat, tests.test_tui_chat_scroll, tests.test_tui_activity, tests.test_tui_look,
tests.test_tui_commands, tests.test_tui_live, tests.test_new_session, tests.test_tui_split,
tests.test_tui, tests.test_toolchain: exit 0.
