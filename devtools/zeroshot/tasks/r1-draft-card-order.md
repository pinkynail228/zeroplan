R1 — the goal-draft card keeps its place in the conversation when the screen reloads (0.5.2 tag blocker, Linux).

Why: Linux full on 117e83c (and on the older f4e033c) fails, deterministic 3/3, Mac OK incl. TZ=UTC:
`tests.test_tui_draft_card.NarrowDraftCardTests.test_a1_two_open_cards_stay_fully_drawn (size=(120, 40))`,
line 841 `assertGreater(plan.region.y, draft.region.y)` -> «13 not greater than 21». The 120x40 pass reloads the store
the 80x24 pass left, with both cards open. On reload the two cards race: the plan card comes from `CARD_SOURCES`
through `call_later(self.render_card_sources)` (app.py ~842), the draft card through `post_message(DraftCardRequested)`
(card_host.py ~251, handled at ~253); `show_card` mounts a new card at the end of `#chat` (card_host.py ~75). Whichever
pump runs first wins, so on Linux the plan card stands above the older draft it was planned from. Excluded already:
TZ, serial test order, a recent regression (the baseline f4e033c fails too).

Reuse, do not rewrite: `show_card`, `on_draft_card_requested`, `render_card_sources`, `draft_card_of`, the chat
entry widgets of `#chat`. No new message types or timers; no sleeps or pauses as the fix.

Write-set: terminal_planner/tui/card_host.py, terminal_planner/tui/app.py (only if the entry lookup lives there),
tests/test_tui_draft_card.py.

Acceptance criteria:
- O1 A new goal-draft card mounts in `#chat` right after the conversation entry of the reply that carries it, not at
  the end, so a card mounted earlier for a later event stays below it. Other card kinds keep mounting at the end; a
  same-key replacement keeps its slot. Example: store = goal reply with a draft, then a proposed plan (both open);
  force the plan card to mount first (call `render_card_sources` before the `DraftCardRequested` is handled) ->
  children of `#chat` read …, reply, draft card, plan card; `plan.region.y > draft.region.y`.
- O2 The existing test passes unchanged on Mac; the new O1 regression test fails on the old `show_card` (state the
  assertion it failed on) and passes on the fix.

Non-goals (reviewers must not require): reordering any other card kind, a card time model, Linux runs (the
orchestrator runs Linux at merge), changes to the test's layout assertions.

Risk: low (card placement only). DoD: `python3.13 devtools/fasttest.py tests.test_tui_draft_card tests.test_tui
tests.test_tui_planning tests.test_toolchain` exit 0; quote the `fasttest:` lines.
