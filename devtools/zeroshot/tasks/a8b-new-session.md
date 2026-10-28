A8b — `/new`: a fresh architect session with a handoff and a warm-up turn, plus the rot signal
(docs/ARCHITECT_DESIGN.md section 8; RELEASE_0.6.0_PLAN step 7; A8a's project STATE merged 2026-10-25).

Why: today Ctrl+R only forgets the thread (architect.py:796), so the next session starts blind: no plan, no live
runs, no STATE. A long session degrades and nothing tells the owner.

Reuse: tui/chat.py `reset`/`_reset` (:667, :841), `send`, `usage_counts` (:382); project_state.py `read`;
architect_tools.py `zplan_state_update`; app.py `chat_snapshot()` (:1848), `action_reset_session` (:1441);
slash.py `COMMANDS`; card_kinds.py `COMMAND_ACTIONS`; strings.py.

Write-set: terminal_planner/tui/chat.py, terminal_planner/tui/slash.py, terminal_planner/tui/card_kinds.py, terminal_planner/tui/app.py, terminal_planner/tui/strings.py, tests/test_new_session.py (new), tests/test_tui_slash.py, tests/test_tui_chat.py (only the tests that pin the thirteen commands or Ctrl+R's old reset).

Acceptance criteria:
- C1 Command: `/new` is a typable command in every state; it runs the same path as Ctrl+R (Ctrl+R stays as a
  hidden key). Refused while a turn runs, with today's busy line. Example: `/new` typed during an owner turn ->
  the busy refusal, no reset.
- C2 Handoff, then reset: with a ready architect, `/new` first sends one fixed turn asking the architect to save
  a handoff with `zplan_state_update`, then resets the thread. A failed or cancelled handoff turn does not block
  the reset; the chat notes it. Example: fixture architect whose handoff turn errors -> thread id forgotten,
  one note line, no crash.
- C3 Warm-up: right after the reset the chat sends one warm-up turn in the new thread carrying the project STATE
  text (`project_state.read`, "(none)" when empty) and the `chat_snapshot()` of that moment; the owner sees its
  reply like any reply. Example: STATE "## Next\nA8b" and a snapshot with one running milestone -> the warm-up
  message holds both; the new session's thread id differs from the old one.
- C4 Rot signal: past a preset threshold (chat.py constants: 40 turns or 2 000 000 tokens of `usage_counts`)
  the chat header shows «сессия длинная: /new» (en: "long session: /new"); below it nothing changes. Example:
  usage (40, 10) -> the line shows; (39, 10) -> the header is byte-identical to today.

Non-goals (reviewers must not require): the journal and its pane (A10, 0.6.1); stuck rules, backoff, hung-turn
cancel (A6b3); changes to architect.py, project_state.py or architect_tools.py; tuning the thresholds.

Conflict rule: if the handoff or warm-up turn cannot run without editing architect.py, or a test outside the write-set pins
Ctrl+R's old behaviour (e.g. tests/test_fixture_scope.py:278), answer `conflict:` with the path:line before any edit.

Risk: medium (chat turn sequencing, no new persisted shape). DoD: `python3.13 devtools/fasttest.py
tests.test_new_session tests.test_tui_chat tests.test_tui_slash tests.test_toolchain` exit 0; quote the `fasttest:` lines.
