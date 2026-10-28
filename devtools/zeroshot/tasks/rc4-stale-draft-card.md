RC4 — an open goal-draft card closes once the plan moved past it (0.6.0 smoke 2026-10-25, defect 4, high)

Incident: ~/zs-pause/dogfood/findings-2026-10-25.md #4 (repeat of 2026-10-24 #1, this time without a reopen). The
plan built from the draft was approved; the draft card stayed open, so `/run` answered «сейчас нечего — нет
карточки с этим действием» while the panel said «Дальше: /run»; workaround `/decline`. Cause: `draft_cards` is
filled in `refresh_draft_card` (tui/card_host.py:232-259) and emptied only by drop/close; nothing re-checks an
already open card against the plan, and `draft_card_open()` (:166) keeps `screen_slash_state` (app.py:482-492) at
`draft`, where `/run` is not allowed. R-A only skips creating a card for an already stale draft.

Reuse: `chat_module.stale_reason(draft.identity, self.plan_identity_now())` as `refresh_draft_card` uses it;
`unmount_card`, `cards_seen`; the «Черновик цели» canvas tab close as esc does.

Write-set: terminal_planner/tui/card_host.py, terminal_planner/tui/app.py, tests/test_tui_draft_card.py,
tests/test_tui_chat.py (only tests that pin an open card after the plan moved).

Acceptance criteria:
- C1 Retire: on every refresh, an open draft card whose draft is stale against a snapshot that names a plan is
  closed (unmounted, key kept in `cards_seen`, its «Черновик цели» tab closed). Example: card open at "no plan",
  the plan from it is approved -> after the next refresh no draft card, no draft tab.
- C2 Commands follow: with the card retired, `screen_slash_state` reads the plan's state. Example: approved plan,
  M1 ready -> `/run` starts M1; «Дальше: /run» and `/run` agree.
- C3 Not on refusal: a card is never retired while the plan identity has not moved (a refused `/plan`, no snapshot
  yet). Example: refused `/plan` at "no plan" -> the card stays open (today's i3a behavior).
Joint example: card open, `/plan` refused -> stays (C3); `/plan` sent, plan approved -> card gone (C1), `/run` works (C2).

Non-goals (reviewers must not require): changes to chat.py or the stale wording; the right-panel title (#12);
the draft card's look; reopen behavior beyond what C1 gives.

Conflict rule: a test outside the write-set that pins an open draft card after the plan moved -> `conflict:` with
path:line before any edit.

Risk: medium (card lifecycle). DoD: `python3.13 devtools/fasttest.py tests.test_tui_draft_card tests.test_tui_chat
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
