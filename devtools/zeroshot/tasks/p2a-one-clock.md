P2a — one clock on screen, no dangling dash, no stale refusal above the chat

Newcomer check 2026-10-26: chat rows show UTC («ты · 16:20») while
cards show local time («✓ отправлен планировщику 19:21», «✓ M1 влит в main 19:51»); the bar showed «план
составляется —»; a refused `/plan` line stayed above the chat after a later `/plan` succeeded.

Causes read on main: `stamp_at` (terminal_planner/tui/chat.py:144) takes the HH:MM out of the stored UTC `ts`
(...Z), as does its twin `stamp_hm` (tui/card_kinds.py:163, card footer); `card_clock` (:148) is local. `_clock`
(tui/activity.py:56) returns `—` when the elapsed time is unknown and `_job_text` puts it into
`bar.job_planning`. The app's own line above the chat is `chat_note` (tui/app.py: set from a refused verdict
near :1470, shown near :939).

Write-set: terminal_planner/tui/chat.py, terminal_planner/tui/card_kinds.py, terminal_planner/tui/activity.py,
terminal_planner/tui/app.py, tests/test_tui_chat.py, tests/test_tui_draft_card.py, tests/test_tui_activity.py,
tests/test_tui_commands.py, tests/test_tui_look.py, tests/test_tui_milestones.py,
tests/test_tui_rb_fixes.py, tests/test_new_session.py, tests/test_tui_activity_pane.py, tests/test_tui_split.py.

The last six only to pin the zone: existing tests that expect an HH:MM taken from a `Z` stamp (e.g. test_tui_look.py:127-137, «21:01» from
`...21:01:00Z`) keep their expected text by running under TZ=UTC (env + `time.tzset()`, restored).

Acceptance criteria:
- C1 The chat rows and card footers show local time: in `stamp_at` and `stamp_hm` a stored UTC `ts` ending in `Z`
  is converted to the local zone before its HH:MM is shown (one shared helper is fine); a `ts` without a zone is shown as today. The store keeps UTC. Example: TZ=Europe/Moscow, ts
  2026-10-26T16:20:05Z -> «ты · 19:20».
- C2 A planning job whose elapsed time is unknown shows «план составляется» with no clock and no dash; a known time
  keeps «план составляется 0:01:05». Example: `_job_text("planning", "", None)` -> «план составляется».
- C3 The refusal of a `/` command shown above the chat (`chat_note`) clears when a later command is accepted or an
  owner turn starts; other notes (U1's cancel note, a renewal's outcome) keep their own rules. Example: `/plan`
  refused -> line shown; `/plan` accepted -> the line is gone.

Non-goals (reviewers must not require): stored formats, journal or run-record stamps, English, other bar texts, the
planner-stop line «остановлен вами в HH:MM» (planning.py:546; a later slice).

Risk: low (display only). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_chat, tests.test_tui_activity,
tests.test_tui_commands, tests.test_tui_draft_card, tests.test_tui_look, tests.test_tui_milestones,
tests.test_tui_rb_fixes, tests.test_new_session, tests.test_tui_activity_pane, tests.test_tui_split,
tests.test_tui, tests.test_tui_strings, tests.test_toolchain: exit 0.
