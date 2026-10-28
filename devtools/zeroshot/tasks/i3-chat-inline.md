I3-chat-inline — the chat becomes a widget list and decision cards live inline in its history
(0.5.2, docs/RELEASE_0.5.2_PLAN.md row i3-chat-inline; lab devtools/ui-lab/work.py `_render_chat`/`_card`).

Card contract: devtools/zeroshot/tasks/card-contract.md (read first). Keep its API: `show_card`, `close_card`,
`drop_card`, `unmount_card`, `render_card_sources`, `newest_card_for`, `card_specs`, `card_widgets`, the dispatcher.

Today (app.py): `ChatBody` (Static `#chat`, ~640) paints rows from `chat_view.chat_scroll` (manual offset arithmetic,
R-1..R-5, `chat_offset`, `chat_page`, pageup/pagedown bindings ~670, actions ~1706, ~2116); cards mount into a
separate `Vertical#cards` under it (~698, ~1333-1400, zplan.tcss ~116-130). Two open cards clip each other; a closed
card's receipt leaves when the next card shows.

Change: `#chat` becomes a `VerticalScroll` of one widget per history entry (owner, architect, system), with the
header/state/refusal rows (`chat_head`) in a Static above it. A card is mounted into that scroll after the newest
entry at the moment it is shown and stays there; a closed card stays in place as its receipt; `drop_card`/a source
that stops returning removes it. Paging uses the scroll's own PageUp/PageDown; the R-4 rules stay (accepted send or
a new entry -> bottom; a live update while scrolled keeps the position). Remove `#cards`, `chat_scroll` and the
offset arithmetic; tests of removed arithmetic go, tests of kept behaviour are rewritten to the widget list.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/chat_view.py, terminal_planner/tui/zplan.tcss,
docs/USER_FLOW.md (chat + cards paragraphs), tests/test_tui_chat_scroll.py, tests/test_tui_chat.py,
tests/test_tui_split.py, tests/test_tui_draft_card.py, tests/test_tui_approve_card.py, tests/test_tui_failed_card.py,
tests/test_tui_ready_card.py, tests/test_tui_milestones.py, the question/merge card tests on main
(only their slot lookups: read `screen.card_widgets[key]`, not `#cards`).

Acceptance criteria (joint example, 120x40 and 80x24: a goal draft card is shown, then the planner proposes, so the
plan card shows; the owner approves):
- A1 Both cards are fully visible with their buttons in the history, the plan card below the draft card; neither is
  clipped; the view is at the bottom.
- A2 After approve the plan card shows «✓ утверждён HH:MM» in place and the draft card's receipt is still there.
- A3 With 40 history entries, PageUp shows older entries and PageDown returns; an owner send returns to the bottom;
  a live update while scrolled up keeps the position.
- A4 A dropped card (its source stops returning it) is gone from the history and never comes back.
- A5 Narrow mode (80x24) still switches to the chat when a card opens (`show_chat`).

Non-goals (reviewers must not require): new card kinds, visuals beyond the lab layout, chat storage.

Risk: high (core UI rebuild + test retirement); every other module stays green.
DoD: `python3.13 devtools/fasttest.py` (whole suite) exit 0; quote its `fasttest:` lines.
