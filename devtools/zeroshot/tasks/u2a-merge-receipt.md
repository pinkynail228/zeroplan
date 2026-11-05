# u2a — a merge the owner did not press still leaves its receipt where the merge card stood

Soak 2026-10-30 S5 (half fixed) and walk 2026-10-29 step 12 (W8): at level auto the architect merges M1 itself;
the M1 merge card (`merge_card_source`, tui/card_kinds.py: one card per `awaiting_merge` row) disappears on the next
refresh because its row is no longer `awaiting_merge`, so the chat keeps "✓ M1 awaiting merge" as the last word
about M1 and the merge shows only as status lines out of order. When the owner presses «merge», `merge_settled`
(tui/card_host.py:720-745) closes the card as its receipt `card.merge_done` ("✓ M1 merged into main HH:MM") at the
card's own place.

Change: when a merge card's milestone leaves `awaiting_merge` as `integrated` and the card was not closed by the
owner's own merge, the card closes as the same receipt (`close_card(key, receipt)`) instead of vanishing; any other
new state (conflict, a new attempt) keeps today's behaviour.

Write-set: terminal_planner/tui/card_host.py, terminal_planner/tui/card_kinds.py, tests/test_tui_merge_card.py

Acceptance criteria:
- A1 The architect's merge leaves a receipt. Example: auto, M1 awaiting merge with its card shown; the architect's
  `zplan_merge` lands it -> the card becomes "✓ M1 merged into main HH:MM" at its place; no "awaiting merge" row is
  the last line about M1.
- A2 The owner's merge is unchanged. Example: «merge» pressed -> one receipt, as today (not two).

Non-goals (reviewers must not require): the architect's own reply, the status line, the chat's ordering of other
rows, the event feed.

Conflict rule: if a test outside the write-set pins a merge card vanishing after an outside merge, change nothing in
it and end with `conflict: <file:line>`.

Risk: low (card receipt). DoD: `python3.13 devtools/fasttest.py tests.test_tui_merge_card tests.test_tui_merge_wait
tests.test_tui_consent_card tests.test_tui_chat`: exit 0.
