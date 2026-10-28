D2 — the open card is answered by keys, and the keys are shown at 80x24

Newcomer check 2026-10-27 defect 2 (pause dir: dogfood findings-2026-10-27-063-newcomer.md): at 80x24 a card has
no hint row (zplan.tcss `MainScreen.narrow #chat .card-hint`, kept hidden so two cards fit, see its comment) and
no key reaches the card's buttons (`_CardButton`, cards.py); Enter on the empty input says
`architect.empty_message`. A newcomer sees no way to answer. Look: devtools/ui-lab/chat.py `card(...)` (selected
choice in reverse, dim key hint). Named deviation: the lab picks with ←→, but ←→ switch the tabs (app.py
`action_view`, I1a), so the product picks with ↑↓, as E1 does for the intro examples.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/cards.py, terminal_planner/tui/card_host.py,
terminal_planner/tui/zplan.tcss, terminal_planner/tui/strings.py, tests/test_tui_cards.py,
tests/test_tui_draft_card.py, tests/test_tui_palette.py, tests/test_tui_card_keys.py (new)

Acceptance criteria:
- K1 The newest open card in the chat has one selected choice, drawn as the lab's (reverse); it starts on the
  first button. Example: draft card opens -> «да, составить план» in reverse, «нет» plain.
- K2 With an open card, the palette hidden and the input empty, ↑/↓ move the selection over that card's choices
  (wrapping); Enter presses the selected choice exactly as a click does (same `Card.Chosen` path). Otherwise ↑↓
  and Enter keep O3/E1 and today's send. Example: plan card, ↓, Enter -> the same result as clicking
  «нет, доработать»; typing «абв» and Enter -> sent to the architect as today.
- K3 While such a card is open and the input is empty, the input placeholder is the catalog text
  «↑↓ выбрать · enter ответить · или напишите архитектору»; with no open card it is `chat.placeholder`. This holds
  at 80x24, where the card's own hint row stays hidden (two cards still fit, A1 unchanged).
  Example: 80x24, draft card open -> the placeholder shows the keys.
- K4 Enter on the empty input with no open card still says `architect.empty_message`. Example: no card, Enter ->
  that note, nothing sent.

Tests: tests/test_tui_card_keys.py at 80x24 and 140x40 covers K1-K4 with the draft, plan and merge cards; O3/E1
tests are kept; `test_a1_two_open_cards_stay_fully_drawn` is kept.

Non-goals (reviewers must not require): ←→ or Tab on cards; the wide card hint row's text; mouse; card texts
(D1); scroll after /merge (D3); en/zh beyond copies.

Risk: medium (Enter on an empty input now answers a card). DoD: `python3.13 devtools/fasttest.py` (the full
suite): exit 0. A test outside the write-set that pins the old Enter or placeholder: name it in the report.
