D1 — no line keeps describing a state that is over: the merge wait note, the old plan card, the start hint (soak S4, S7, S8)

Soak of rc1 2026-10-29 (real Codex). S4: after a merge the run note keeps "the merge check is reviewing M1"
(strings.py:552 `note.merge_waiting`): `merge_wait_shown` (tui/app.py:3903-3915) writes it with `say_note`
(app.py:2888-2899, `run_note`), and `merge_wait_shown(None)` only resets `merge_waiting`; the card's merge verdict
(`merge_settled`, card_host.py:673) goes to the status line and leaves `run_note`. S7: while a plan is revised
the old plan card keeps live approve/revise buttons: `plan_card_source` (card_kinds.py:655-666) shows it while the
snapshot is `proposed`, and `revision_note` (app.py:3217-3226) closes nothing. S8: at supervised the Plan tab shows
"Next: /run — start M1" for ~25 s after the architect's start tool began M1 (controller.py:835 `_start_tool`): the
tab hides `Next:` only while `app.pending_text()` is set (app.py:1229-1230), and the tool sets no pending.

Reuse: `say_note`, `run_note`, `merge_waiting`, `pending_text`, `plan_card_source`, the card receipt path,
`_start_tool`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, terminal_planner/tui/card_kinds.py,
terminal_planner/tui/controller.py, tests/test_tui_stale_lines.py (new)

Acceptance criteria:
- L1 When a merge wait ends, by any verdict and through the card or the end modal, the waiting note is gone.
  Example: pending, then merged through the card -> `run_note` and the status line contain no "merge check is
  reviewing"; the merged line is shown.
- L2 Once a revision is asked for a proposed plan, that plan's card offers no approve or revise until the new
  revision's snapshot arrives. Example: /revise "x" -> the old card's buttons are gone or disabled at once; pressing
  its approve key does nothing and starts no approval.
- L3 While a start the architect or the owner asked for is in flight, no `Next:` line offers that start. Example:
  supervised, the start tool begins M1 -> the Plan tab shows no "Next: /run — start M1" before the next snapshot.
- L4 Today's hints and cards stay otherwise. Example: tests.test_tui_hints and tests.test_tui_approve_card pass
  unchanged.

Non-goals (reviewers must not require): other notes, the plan screen, the scheme, the merge path itself, wording.

Conflict rule: if a test outside the write-set pins the waiting note after a merge or the old card's buttons during
a revision, change nothing in it and end with `conflict: <file:line>`.

Risk: low (visible state). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py
tests.test_tui_stale_lines tests.test_tui_merge_wait tests.test_tui_hints tests.test_tui_approve_card
tests.test_tui_auto_plan_card tests.test_tui_cards tests.test_tui tests.test_docs tests.test_toolchain`: exit 0;
budget.py: OK. New L1-L3 tests fail on today's code.
