R-A — three high defects from the 0.5.2 bug hunt (2026-10-24): stale draft card, first-run dirty tree, focus.

Why: dogfood on 9afd63e. (1) After ctrl+q + reopen a declined or bypassed goal draft reopens as a card;
`slash_state` (app.py:424-490) then returns "draft" before the plan, so `/run` `/approve` `/open` say
«сейчас нечего — нет карточки с этим действием». (2) Accepting the profile writes an untracked zplan.process.json;
`/plan` is Blocked by engine.py:1197 with a line that names no file; nothing says to commit it. (3) Esc from the plan
screen or Settings (screens.py:215, :364) leaves focus on the pane; typed text fires letter actions.

Reuse: `chat.stale_reason` + `plan_identity_now()` (card_host.py ~190), `refresh_draft_card` (card_host.py:231),
`MainScreen.on_screen_resume` (app.py:1087), the existing porcelain call at engine.py:1197.

Write-set: terminal_planner/tui/card_host.py, terminal_planner/tui/app.py, terminal_planner/tui/screens.py,
terminal_planner/engine.py, terminal_planner/tui/strings.py, tests/test_tui_reopen_fixes.py (new),
tests/test_tui_draft_card.py, tests/test_tui_slash.py, tests/test_tui_planning.py, tests/test_tui_live.py.

Acceptance criteria:
- C1 A goal draft whose `stale_reason` against the current plan is non-empty never opens as a card on mount or
  refresh. Example: draft d1, plan r1 from d1 exists, restart -> no draft card, no «Черновик цели» tab, `/run` acts.
- C2 With a plan present, retained goal-form text alone does not make the slash state "draft". Example: plan_ready +
  non-blank `app.goal_draft` -> `/approve` acts on the plan card. A draft with no plan still gives "draft" (unchanged).
- C3 The engine's dirty-tree Blocked text (engine.py:1197 and :1421) names up to 5 dirty paths, «и ещё N» beyond.
  Example: only `?? zplan.process.json` -> «Есть незакоммиченные изменения (zplan.process.json): планировщику нужен
  чистый проект. Закоммитьте или уберите их; цель сохранена.»; family stays readiness.clean; check unchanged.
- C4 After Esc from PlanScreen or SettingsScreen back to the main screen, focus is on `#input`. Example: Tab to the
  pane, `p`, Esc, type `/run` -> the input holds `/run`; no pane action fired. The tab-switch deferral path in
  `on_screen_resume` is unchanged; a closed goal form keeps today's focus (test_tui_planning.py:319).
- C5 One test per criterion in tests/test_tui_reopen_fixes.py, each failing on the unfixed code.

Non-goals (reviewers must not require): persisting declined keys; a commit action in zplan; changing setup.py's
readiness line or the clean check; R-B mediums; process.py (another run owns it).

Risk: medium (TUI state + one engine message). DoD: `python3.13 devtools/fasttest.py tests.test_tui_reopen_fixes
tests.test_tui_draft_card tests.test_tui_slash tests.test_tui_planning tests.test_tui_live tests.test_toolchain`
exit 0; quote the `fasttest:` lines.
