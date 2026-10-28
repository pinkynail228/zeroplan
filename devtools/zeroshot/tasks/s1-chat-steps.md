S1 — event entries as one-line steps; a decided card shrinks to one line

docs/RELEASE_0.6.3_PLAN.md V3. An `events` row shows feed.py `summary` text plainly (chat.py `entries_of`); a
decided card stays boxed (card_host.py `close_card`). Look: ui-lab/chat.py `step()`.

Write-set: terminal_planner/tui/chat.py, terminal_planner/tui/app.py, terminal_planner/tui/cards.py,
terminal_planner/tui/card_host.py, terminal_planner/tui/zplan.tcss, terminal_planner/tui/strings.py,
tests/test_tui_chat.py, tests/test_tui_draft_card.py, tests/test_tui_approve_card.py, tests/test_tui_merge_card.py,
tests/test_tui_question_card.py, tests/test_tui_chat_scroll.py, tests/test_tui_cards.py, tests/test_tui_look.py,
tests/test_tui_strings.py, tests/test_tui_chat_steps.py (new)

Acceptance criteria:
- C1 An events entry is one step row per wake event line, nothing else (no head line or idle count; `… и ещё N
  событий.` -> a dim `… ещё N`). Row: 2-cell glyph gutter (✓ green, ▶ cyan, ! red, · dim), words, dim
  detail. Example: `план r1: proposed -> approved` -> `✓ План r1 утверждён`; `M1 попытка 1: submitted
  -> running` -> `▶ M1 выполняется  попытка 1`.
- C2 Every plan status (feed `PLAN_WAKE` keys and authority.py `PLAN_STATUSES`) and run state (runs.py `STATUSES`,
  `MILESTONE_STATES`) has a strings.py word and a glyph: done/merged/approved ✓, running/submitted ▶,
  failed/blocked/stopped/conflict !; unknown falls back to `· M1: a -> b`. Example: `M1 попытка 2: running
  -> failed` -> `! M1 не удался  попытка 2`; `M1 попытка 1: x -> y` -> `· M1: x -> y`.
- C3 A verdict line `M1 T1 раунд 2 reviewer: approve — ok` -> `✓ M1 проверка пройдена  раунд 2 · ok`; a
  non-approve verdict -> `! M1 замечания проверки  раунд 2 · <text>`, text clipped to the width. Example:
  verdict `reject — нет теста` -> a red `!` row ending `нет теста`.
- C4 A closed card (close_card) is one dim row `✓ <done text>`, no border or buttons, in its place; never
  reshown (key kept). Example: goal card accepted at 10:02 -> one row `✓ отправлен планировщику 10:02`.
- C5 What the architect receives is unchanged: feed.summary and stored row text byte-identical; steps render
  in the pane only. Example: tests.test_feed passes untouched.

Tests: delete the boxed done-line pins (test_tui_cards a4, test_tui_look Card.done); one invariant test in
tests/test_tui_chat_steps.py at 80x24 and 140x40 covers C1-C4.

Non-goals (reviewers must not require): feed.py; cards' buttons, commands, keys, open look; messages; empty chat;
en/zh beyond copies.

Risk: low (display). DoD: `python3.13 devtools/fasttest.py` with every test module of the write-set,
tests.test_feed and tests.test_toolchain: exit 0.
