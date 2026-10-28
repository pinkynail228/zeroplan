I9-look-fix — finish the i9-look candidate (commit 9ff3886 on branch zs-i9-look, force-stopped in round 3).
Brief of the original: devtools/zeroshot/tasks/i9-look.md (A1-A5 stand; read it). This run closes the two round-2
rejections and nothing else. First run on the Claude lane (Sonnet worker, Opus reviewers; owner trial 2026-10-24).

State: the candidate already holds the look (no logo/header, input inside the chat pane, ANSI palette, titles,
author · time lines). Round 3 started a targeted timestamp stamp in terminal_planner/tui/chat.py (`("stamp", index, …)`
instead of a whole history replacement); finish or correct it, do not redo the look.

Write-set: terminal_planner/tui/activity.py, terminal_planner/tui/chat.py, terminal_planner/tui/app.py,
tests/test_tui_look.py, tests/test_tui_activity.py, tests/test_tui_chat.py.

Acceptance criteria:
- F1 (A1 wording) The idle bottom bar at 120x40 for project `notes`, branch `main` reads exactly
  «notes · main · работы нет · ←→ вкладки · / команды · ctrl+q выйти»: groups joined by « · », one space each side.
  Example: `bar_text('notes', 'main', None, '', None, BAR_KEYS_IDLE, 118).plain` equals that string. Running jobs
  and the `bar.continue` tail use the same separator; width fitting (never wider than `width`) stays.
  tests/test_tui_look.py asserts the exact string (drop the docstring that waived the punctuation).
- F2 (no lost replies) A timestamp refresh never removes or replaces a newer chat entry. Example (scripted Codex
  fixture): owner sends «ordinary question»; the stamp reader is paused after it reads the owner row; the reply
  «Привет.» completes and its events drain; the reader is released. The UI history is then
  [('owner', 'ordinary question'), ('architect', 'Привет.')] and the owner line carries its `HH:MM`.
  A regression test in tests/test_tui_chat.py drives exactly this ordering and fails on a whole-history replacement.

Non-goals (reviewers must not require): anything else from i9-look already accepted in rounds 1-2 (A2-A5), new
behaviour, other bar layouts, EN/ZH wording, NO_COLOR/16 colours, pixel spacing.

Risk: medium (chat threading). DoD: `python3.13 devtools/fasttest.py tests.test_tui_look tests.test_tui_activity
tests.test_tui_chat tests.test_tui_split tests.test_tui` exit 0; quote its `fasttest:` lines.
