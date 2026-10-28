D1 — the plan card tells the truth in `auto` and on a narrow screen

Newcomer check 2026-10-27 defects 1 and 9 (pause dir: dogfood findings-2026-10-27-063-newcomer.md): in `auto` the
plan card asks «Утвердить?» and the bar says «план ждёт твоего да», then the architect approves within seconds
(feed.py `_plan_wakes` with `autonomy.decide(level, "approve")`); at 80x24 the card says «Справа — вкладка «План»»
where there is no right column. Sites: card_kinds.py `plan_card_spec`, activity.py
`bar.waiting_approve`, autonomy.py `decide`, `MainScreen.narrow`.

Write-set: terminal_planner/tui/card_kinds.py, terminal_planner/tui/cards.py, terminal_planner/tui/strings.py,
terminal_planner/tui/activity.py, terminal_planner/tui/app.py, tests/test_tui_approve_card.py,
tests/test_tui_cards.py, tests/test_tui_activity.py, tests/test_tui_split.py,
tests/test_tui_auto_plan_card.py (new)

Acceptance criteria:
- C1 When `decide(level, "approve")` allows (auto), a proposed plan's card does not ask: text «План проверен и
  покрывает цель. Архитектор утвердит его сам; чтобы остановить — «доработать».», one button «доработать»
  (`/decline`); the bar reads «архитектор утверждает план», not `bar.waiting_approve`. Example: profile auto, plan
  r1 proposed -> no «Утвердить?», no «да, утвердить».
- C2 Supervised and manual keep today's question and both buttons. Example: manual -> «Утвердить?», «да, утвердить»,
  «нет, доработать», bar «план ждёт твоего да».
- C3 The pointer to the plan follows the layout: wide keeps «Справа — вкладка «План».»; narrow says «План — на
  вкладке «План» (→).» and the text follows a resize while the card is open. Example: 80x24 -> no «Справа».
- C4 A stale plan keeps its RS2 text and button at any level. Example: auto + plan.stale -> `card.plan_stale_text`.
- C5 A level read failure falls back to the question (C2), never to C1. Example: unreadable profile -> «Утвердить?».

Tests: tests/test_tui_auto_plan_card.py at 80x24 and 140x40 covers C1-C5; tests pinning the old text are updated,
not deleted.

Non-goals (reviewers must not require): the approval logic itself (feed.py, controller.py, autonomy.py stay);
`/merge` in auto; other cards; key handling of cards (D2); en/zh beyond copies.

Risk: low. DoD: `python3.13 devtools/fasttest.py tests.test_tui_auto_plan_card tests.test_tui_approve_card tests.test_tui_cards tests.test_tui_activity tests.test_tui_split tests.test_toolchain`: exit 0 (the full
suite is the merge gate's).

Attempt 2: the worktree holds attempt 1 (reviewed); its gate failed only in tests/test_tui_split.py, which pins
the names card_kinds.py defines (`CardSplitTests`): list the new ones there; change nothing else.
