C0c2 — the right pane gets two tabs, Сейчас and План (slice C1 of docs/CHAT_RELEASE_JTBD.md; job J4).

Goal: the plan and the live state are one key apart. Today the plan pane (`PlanPanel`, id `plan-pane`, terminal_planner/tui/app.py:992) mixes the plan lines with the live lines of an active attempt (`snapshot.panel`, appended at app.py:1041-1042 in `render_state`), and the planner/run status lines are rendered above the chat (app.py:1077-1088: `app.progress`, `app.finish_note`, `app.run_lines`, `app.run_note`). The third tab (Журнал) is a later run: its data is not reachable from the TUI yet.

Data reach: everything shown is already held by the app: `app.snapshot.panel`, `snapshot.lines` (render_state, app.py:1021-1047), `app.progress`, `app.finish_note`, `app.run_lines`, `app.run_note`, `app.planner_pane()`, `app.run_watch` (app.py:1077-1088).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, docs/USER_FLOW.md (full-screen shell section), TUI tests. No controller, catalog, engine, runs or live changes: the tabs show data MainScreen already holds.

Acceptance criteria:
- A1 The right pane is a Textual `TabbedContent` with tabs «Сейчас» and «План». План holds the existing `PlanPanel` (same id `plan-pane`). Сейчас shows `snapshot.panel` (the live lines of the active attempt) followed by the planner or run lines that app.py:1077-1088 shows (same sources, same order); with none of them, one line saying nothing is running and naming the key that starts the next step when the snapshot has a «Дальше:» line. План keeps today's content unchanged (including the live lines), and the status lines above the chat stay as they are.
- A1b The tab shown at start is Сейчас when a planner or a milestone attempt is active, else План; the app never switches tabs on its own afterwards.
- A2 alt+1 / alt+2 (and F2 / F3) switch to Сейчас / План from anywhere, including while the chat input has focus; these keys never insert text. The key bar names them.
- A3 Everything the plan pane does today (keys p n c t g x o i w e, selection, refresh, Tab focus to it and back to the chat) still works on the План tab; start-up focus stays in the chat input.
- A4 One test per criterion through tests/tui_support.py, at 160x45 and 120x40.

Non-goals (reviewers must not require): a Журнал tab, chat width changes, a live log stream (C3), a cycle strip or round-of-max (C2), per-round verdicts (C4), the --plain UI.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_live tests.test_tui_planning tests.test_tui_polish tests.test_tui_milestones tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
