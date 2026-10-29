A10 — a rejected plan stops for the owner: one automatic revision, then a card

Tester 2026-10-28: r5, nothing built. review_exhausted wakes the architect (feed.py:49-50, 156-160), it revises
again, with no limit; the main screen shows the rejected plan as idle (tui/app.py:518-524; the failed-plan card
covers only FAILED_PLAN_STATUS, card_kinds.py:800-828); [i] says it "cannot be approved" (planning.py:701) while
an override exists (planning.py:661-664). A8 gives the architect the findings and zplan_revise_plan.

Reuse: the feed in the planning store (`state["feed"]`, validate_feed); the controller's `_revise_tool` and
`_edit_tool`; the failed-plan card (failed_plan_view, failed_plan_card_key, failed_card_text); the plan screen's
revise and override actions.

Write-set: terminal_planner/feed.py, terminal_planner/tui/controller.py, terminal_planner/tui/card_kinds.py,
terminal_planner/tui/card_host.py, terminal_planner/tui/app.py, terminal_planner/planning.py,
terminal_planner/architect.py, tests/test_feed.py, tests/test_bridge.py, tests/test_tui_failed_card.py,
tests/test_plan_override.py, tests/test_architect.py.

Acceptance criteria:
- B1 Brake: the store records which revisions an architect tool (revise or edit) created; when the current
  revision is review_exhausted and was created that way, both tools refuse (action.refused, "the owner decides
  now"), nothing written, also after an app restart. Example: owner r2 rejected -> architect revise -> r3; r3
  rejected -> architect revise refused; restart, still refused; owner revises -> r4 rejected -> architect may
  revise once.
- B2 The review_exhausted event of an architect-made revision wakes no turn. Example: r3 above -> event wake false.
- B3 From the first rejection, at every autonomy level, the main screen shows a card for the current
  review_exhausted revision: «The plan check rejected revision N», the findings (card bound), buttons «revise»
  (the plan screen's revise input), «approve anyway» (its override with a typed reason), «details»; the screen
  state is no longer idle. Example: manual level, r2 rejected -> the card with the three buttons.
- B4 [i] names both ways: "[r] revise or approve anyway with a reason". Example: the exhausted line has no
  "cannot be approved".
- B5 The architect rules: on review_exhausted never call zplan_approve_plan; say the check rejected it and point
  to the card. Example: the rules text holds this.

Non-goals: a cap on owner revisions, a stop button, translation, the critic's text, layout beyond the failed card.

Conflict rule: if a test outside the write-set pins the idle state of a review_exhausted plan or the [i] line,
change nothing and end with `conflict: <file:line>`.

Risk: high (persisted planning store). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_feed
tests.test_feed_wiring tests.test_bridge tests.test_tui_failed_card tests.test_plan_override tests.test_architect
tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new test fails on the old code.
