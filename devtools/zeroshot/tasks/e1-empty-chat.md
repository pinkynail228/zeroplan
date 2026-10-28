E1 — an empty chat explains itself and offers three example goals

docs/RELEASE_0.6.3_PLAN.md V4. Today an empty chat is a blank pane; strings.py `chat.greeting` is unused. The
arrows in the input (app.py `action_pick`, O3) move the `/` palette or recall the owner's earlier lines. Look:
devtools/ui-lab/chat.py state empty (`#stream` centred when empty, `EXAMPLES`; the lab's examples are
project-specific, the product's are generic).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/chat.py, terminal_planner/tui/zplan.tcss,
terminal_planner/tui/strings.py, tests/test_tui_palette.py, tests/test_tui_polish.py, tests/test_tui_strings.py,
tests/test_tui_chat_empty.py (new)

Acceptance criteria:
- C1 While the chat shows no entry and no card, its scroll shows one centred intro (not a `ChatMessage`): «Опиши,
  что нужно сделать. Архитектор уточнит детали, составит план, запустит работу и спросит перед слиянием.», a dim
  «Например», three examples (`❯` before the selected one, `›` before the others), a dim hint
  «↑↓ пример в строку ввода · enter отправить · / команды». `chat.greeting` is replaced by these catalog ids.
  Example: fresh project, 80x24 -> all three examples visible, `❯` on the first.
- C2 The examples are generic catalog texts for any repository: «Объясни, как устроен этот проект», «Добавь
  тесты для самой важной части кода», «Обнови README: как установить и запустить». Example: no example names a
  file, language or framework.
- C3 With the intro shown, the palette hidden and the input empty or holding an example, ↑/↓ moves the selection
  (wrapping) and puts that example into the input, cursor at the end; Enter sends it as any typed line. Otherwise
  the arrows keep O3 (palette first, then recall of earlier lines). Example: ↓ -> input «Добавь тесты для самой
  важной части кода», `❯` on the second; Enter -> one owner entry with that text, the intro gone.
- C4 The intro comes back whenever the shown history is empty again (after `/new`). Example: `/new` on a chat
  with entries -> the intro with `❯` on the first example.

Tests: one invariant test in tests/test_tui_chat_empty.py at 80x24 and 140x40 covers C1-C4; O3 palette tests are
kept; while the intro shows, the arrows pick examples even if recall holds lines (`/new`, commands); recall
returns once the chat has an entry (an O3 recall test on an empty chat seeds an entry first).

Non-goals (reviewers must not require): messages, cards, indicator and bar; the start screen; the right column;
sending an example on Enter with an empty input; en/zh texts beyond copies.

Risk: medium (the input's arrows change). DoD: `python3.13 devtools/fasttest.py` (the full
suite): exit 0. A test outside the write-set that pins a blank empty chat: name it in the report.
