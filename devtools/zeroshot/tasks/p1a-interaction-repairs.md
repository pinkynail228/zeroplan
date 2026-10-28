P1a — interaction repairs: palette, input loss, plan focus and Esc, empty renew

Re-smoke 2026-10-25b (pause dir, dogfood, findings-2026-10-25b.md) #7, #9, #10, #14; plan docs/RELEASE_0.6.1_PLAN.md.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/slash.py, terminal_planner/tui/modals.py,
terminal_planner/tui/screens.py, terminal_planner/tui/card_kinds.py, tests/test_tui_palette.py,
tests/test_tui_slash.py, tests/test_tui_run_command.py, tests/test_tui_planning.py, tests/test_tui_plan_gate.py,
tests/test_tui_commands.py.

Acceptance criteria:
- C1 The palette lists `/run` only when it would act: a row with a start action exists (the same rule as
  `action_run_next`, app.py:2700, refusal at :2713). Typed `/run` still answers with that refusal. Example: plan
  proposed, not approved -> `/` palette has no `/run`; approved plan with M1 ready -> `/run` listed.
- C2 No input is lost: after Esc closes any screen, the next `/` opens the palette; printable keys typed on the
  run screen (modals.py:315) go to the chat input instead of being dropped. Example: open details, Esc, type `/st`
  -> palette shows `/status`; on the run screen of a merged milestone type `a` -> chat input holds `a`.
- C3 Plan screen (screens.py:54): after approve or renew, focus is on the screen's first button; Esc closes an open
  details view and returns focus to the plan, a second Esc leaves the screen; Enter right after an Esc never opens
  the note screen. Example: approve -> focus «подробнее» is not forced; details, Esc, Enter -> no note screen.
- C4 Renewing a stale proposal (plan.stale) accepts an empty note: it re-plans with a fixed note naming the cause
  (e.g. «Проект изменился после планирования: пересобрать план»). A non-stale revise with an empty note keeps
  EMPTY_CHANGE (app.py:121, :2552). Example: stale plan, `/view → доработать`, Enter on empty -> planning r+1.

Non-goals (reviewers must not require): copy/layout items (P1b); the CLI's empty-note texts (cli.py:574,
test_plan_override.py:455); the planner pane log of the previous revision; architect/Controller code.

A test outside the write-set asserting a changed text, palette list or focus -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` changed test modules, tests.test_reference: exit 0.

Attempt 2: gate on 5138f26 (main merged): tests.test_toolchain TestModuleImportTests fail because
tests/test_tui_run_command.py:36 imports `textual.widgets` at module level; every test module must import without
Textual (import inside the guarded tests, as `stand_in` does). Keep the earlier code; DoD adds tests.test_toolchain.
