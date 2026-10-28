P1b — stale tab, stale preflight word, texts naming keys that no longer exist

Re-smoke 2026-10-26 #8 (pause dir, dogfood); plan docs/RELEASE_0.6.1_PLAN.md P1b. Since K1 the TUI has no letter
keys and no F1/Ctrl+R; every action is a `/` command (docs/TERMINAL_UX_BRIEF.md).

Write-set: terminal_planner/tui/card_host.py, terminal_planner/tui/scheme.py, terminal_planner/catalog.py,
terminal_planner/architect.py, terminal_planner/tui/app.py, terminal_planner/tui/chat.py, docs/REFERENCE.md
(generated from catalog.py), README.md (:65 Ctrl+R),
tests/test_tui_draft_card.py, tests/test_tui_scheme.py, tests/test_architect_home.py, tests/test_new_session.py,
tests/test_tui_failed_card.py, tests/test_tui_approve_card.py (the last two: `_Screen` stubs only).

Acceptance criteria:
- C1 The «Черновик цели» canvas tab (opened card_host.py:315) closes when its card closes or is dropped: `/plan`
  from the draft (card.draft_sent), plan approval (card.plan_done), `/decline`, not only through
  `retire_stale_draft_cards`. Example: draft card, `/plan` -> plan
  r1 proposed -> no «Черновик цели» tab.
- C2 The scheme shows preflight as done once the attempt moved past it (scheme.py `observation_from_flow` never
  sets `preflight`). Example: worker running
  -> the preflight node is not «ждёт».
- C3 Texts name no missing key: catalog.py:462 (`tui_plan` footer «…только [g].») names the command
  that starts planning; architect.py:102 `HOME_LOST` and catalog.py:368 `architect.home_lost` name `/new`, not
  Ctrl+R. Example: the home-lost refusal holds «/new» and no «Ctrl+R».
- C4 Stale code: app.py:129 `PRIMARY['tui_run']` drops "new_attempt" (not a `tui_run` action; catalog.py:614-634);
  comments naming F1 (app.py:309-313) or Ctrl+R (app.py:1535, chat.py:515, :694) name what exists now. Example:
  `grep -n "Ctrl+R\|\[F1\]" terminal_planner` finds nothing.
- C5 Strings that `KEY_COMMANDS` (app.py:162) rewrites on screen stay as they are. Example: tests.test_run_cause
  and tests.test_tui_look pass unchanged.

Attempt 2: attempt 1's `close_card_tab` broke the `_Screen` stubs (no attribute) and
test_tui_chat AnswerDraftTests d9 (`add_view_tab`: No Tab '--content-tab-tab-view-2'): two drafts of one reply
share a tab; closing one card must not remove a tab still open for the other or being reopened.

Non-goals: the CLI/reference repair rows; delivery.py/live.py strings; `/details` wording; dead
`canvas.plan_footer`/`PANEL_HINT`; P2 items.

A test outside the write-set asserting a changed text, tab or scheme word -> `conflict:`.

Risk: medium (card and tab lifecycle). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_draft_card,
tests.test_tui_scheme, tests.test_tui_scheme_tab, tests.test_tui_milestones, tests.test_tui_activity_pane,
tests.test_tui_rb_fixes, tests.test_architect_home, tests.test_new_session, tests.test_tui, tests.test_reference,
tests.test_tui_chat, tests.test_tui_failed_card, tests.test_tui_approve_card: exit 0.
