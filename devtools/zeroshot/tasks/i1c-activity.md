I1c — the Журнал tab becomes the always-visible «Что происходит» pane under the canvas (0.5.2,
docs/RELEASE_0.5.2_PLAN.md, run i1c).

Why: in 0.5.1 a silent or stuck run is invisible unless the owner opens the Журнал tab; the approved screen
(docs/ui-redesign/WORK_SCREEN.md, lab `devtools/ui-lab/work.py` `#log-pane`, walk with ctrl+t) keeps a short activity
log always on screen under the canvas, with "последнее: … · m:ss назад" in its border. The widget exists and is
tested: `terminal_planner/tui/activity.py` `Activity` (`show(lines, silence)`; journal lines as-is, silence from
`flow.silence`, None -> no subtitle).

Today (terminal_planner/tui/app.py, `MainScreen.compose`): the right column is `TabbedContent#right` with Сейчас,
План, Журнал (`TAB_JOURNAL`, `#journal-pane`, `render_journal`, `journal_view`, `journal_follow`); after run i1a the
tabs are switched with ←→ and a click.

Change:
- The right column becomes a `Vertical` holding `TabbedContent#right` (Сейчас, План only) above an `Activity` pane
  (id `activity`, height 8 rows at 40 rows, never below 4; the canvas keeps the rest). The Журнал tab, its pane and its
  tab action go.
- The activity pane shows `snapshot.journal` (the same lines the Журнал tab showed, `JOURNAL_EMPTY` replaced by the
  widget's own empty line) with `silence = snapshot.flow["silence"]` when a flow is present, else None; it repaints
  whenever the Журнал tab used to (every snapshot refresh), no matter which tab is shown.
- The old follow/scroll-back logic of the Журнал tab goes; the pane always shows the newest lines that fit.
- Every place that named the Журнал tab (help, key bar segment, catalog rows, docs/USER_FLOW.md) now names the pane
  «Что происходит» or drops the tab; ←→ cycles Сейчас <-> План.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, terminal_planner/catalog.py (rows of the
Журнал tab only), docs/USER_FLOW.md, docs/REFERENCE.md (only lines naming the Журнал tab), tests/test_tui_live.py,
tests/test_tui_milestones.py, tests/test_tui_polish.py, tests/test_tui.py, tests/test_tui_activity_pane.py (new).
Do not edit terminal_planner/tui/activity.py, strings.py, scheme.py, terminal_planner/live.py, controller, engine.

Acceptance criteria:
- A1 At 120x40 and 80x24 the main screen shows the canvas tabs Сейчас and План (no Журнал) and the «Что происходит»
  pane under them, whichever tab is active.
- A2 With a snapshot journal of 12 lines the pane shows the newest lines that fit, oldest first; with none it shows
  the widget's empty line.
- A3 With `snapshot.flow["silence"]` = 187 the pane's border subtitle reads the `live.last_event` text with "3:07";
  without a flow it has no subtitle.
- A4 A new snapshot with one more journal line updates the pane while the План tab is active.
- A5 ←→ cycle Сейчас <-> План; the removed tab is not reachable by any key, click or action; help, key bar,
  catalog and USER_FLOW no longer name a Журнал tab.
- A6 Every other existing behaviour is unchanged; tests that opened the Журнал tab now read the pane.
- A7 Tests per preamble: pane logic is already tested in tests/test_tui_activity.py; at most two new whole-app tests
  (A1+A2+A3 in one, A4+A5 in the other). Delete, not rewrite, the tests that pinned the Журнал tab
  (devtools/zeroshot/test-retire-0.5.2.md, row i1c: JournalTabTests; shrink ArrowTabTests to the 2-tab cycle and delete
  PaneTabTests a1_the_arrows_switch_the_tab_from_anywhere).

Non-goals (reviewers must not require): the bottom bar / job timer (run i2 replaces the key bar), role colours,
alarm rows, scrolling back in the pane, the scheme, slash commands, cards, translations.

DoD: `python3.13 devtools/fasttest.py tests.test_tui tests.test_tui_chat tests.test_tui_live tests.test_tui_planning
tests.test_tui_polish tests.test_tui_milestones tests.test_tui_flow tests.test_tui_scheme_tab tests.test_tui_activity
tests.test_tui_activity_pane tests.test_live tests.test_toolchain tests.test_reference` with exit 0.
Parallel note: run s0-app-split moves other blocks of app.py at the same time; do not move or reformat code outside
MainScreen and the lines this task changes.
