D6 — the goal draft tab closes once its plan exists, and the chat history ends a milestone with its merge (soak S5)

Soak of rc1 2026-10-29: after M1 merged, the right pane still had the «Goal draft» tab; a second goal added a second
one. The tab opens in `add_view_tab(strings.text("canvas.draft_tab"), ...)` (tui/card_host.py:343) once per draft
key and closes only when the draft goes stale (`retire_stale_draft_cards`, card_host.py:303-322) or on Esc
(app.py:2329); `close_started_card` (app.py:3163-3170) turns the card into its receipt and leaves the tab. The
chat history kept "✓ M1 awaiting merge" as the last line of M1: STATE_LINE events render `step.run.<state>`
(tui/chat.py:1232, :1293); no line followed for the merge although feed WAKE has "integrated" (feed.py:48).

Reuse: `close_started_card`, the view-tab registry of card_host, `retire_stale_draft_cards`, chat STATE_LINE
rendering, the feed events.

Write-set: terminal_planner/tui/card_host.py, terminal_planner/tui/app.py, terminal_planner/tui/chat.py,
terminal_planner/tui/strings.py, tests/test_tui_draft_tab_ends.py (new), tests/test_tui_draft_card.py

Acceptance criteria:
- D1 When a draft was sent and its plan revision exists, the draft's tab closes and the pane shows the tab it showed
  before the draft (else the plan tab). Example: send the draft card -> plan r1 snapshot arrives -> no «Goal draft»
  tab; a second goal's draft -> exactly one «Goal draft» tab.
- D2 A merged milestone's history ends with a merged line after its awaiting-merge line. Example: feed with M1
  awaiting_merge then integrated -> the chat shows "✓ M1 awaiting merge" then a line containing "M1" and "merged".
- D3 A draft that was not sent keeps its tab as today. Example: tests.test_tui_draft_card passes with only pins of
  the sent-draft tab updated.

Non-goals (reviewers must not require): the draft card itself, Esc, the plan tab content, feed storage.

Conflict rule: if a test outside the write-set pins the sent draft's tab staying open, change nothing in it and end
with `conflict: <file:line>`.

Risk: low (visible state). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py
tests.test_tui_draft_tab_ends tests.test_tui_draft_card tests.test_tui_chat_steps tests.test_tui_chat tests.test_feed
tests.test_tui tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New D1 and D2 tests fail on today's code.
