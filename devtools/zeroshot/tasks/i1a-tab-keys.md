I1a — arrows switch the right-hand tabs; F-keys and alt+N go (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i1a).

Why: the owner's MacBook has fn disabled, so F2/F3/F4 do nothing for them (baseline dead end 3,
docs/ui-redesign/baseline-0.5.1/README.md), and alt+N does not reach the app under tmux or Terminal.app. Approved
controls (docs/ui-redesign/WORK_SCREEN.md, "Owner decisions 2026-10-22"): ←→ switch the canvas tabs, a click on a tab
switches it, no F-keys, keys work in the Russian layout. Lab reference: `devtools/ui-lab/work.py` `action_view`.

Today: app-level bindings alt+1/2/3 and f2/f3/f4 -> `action_tab_live/plan/journal` (terminal_planner/tui/app.py
1923-1929, 2403-2415); the right pane is `TabbedContent#right` with Сейчас / План / Журнал (app.py 1088-1108); the key
bar and help name the F-keys (app.py near 81 and the key bar code, docs/USER_FLOW.md lines 20, 37-38, 49).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, docs/USER_FLOW.md, tests (TUI tests that
press or assert the removed keys, plus new tests).

Acceptance criteria:
- A1 On the main screen, left / right show the previous / next right-hand tab, cycling (Сейчас -> План -> Журнал ->
  Сейчас), with the focus anywhere on the main screen, when the chat input is empty.
- A2 When the chat input holds text, left / right move its text cursor as before and do not switch tabs.
- A3 Under a modal screen or on another screen the arrows keep their old meaning there (no tab switch).
- A4 alt+1/2/3 and f2/f3/f4 are no longer bound; the main key bar names "←→ вкладки" in their place; help (f1) and
  docs/USER_FLOW.md lines that named them now name ←→ and the click.
- A5 A mouse click on a tab label switches to it (Textual's own behaviour; one test proves it stays working).
- A6 Every other existing behaviour is unchanged; tests that pressed the removed keys now press arrows.
- A7 One test per criterion through tests/tui_support.py at 120x40.

Non-goals (reviewers must not require): renaming or redrawing tabs, the scheme, moving Журнал, slash commands, the
plan-pane letter keys (they stay in this run), up/down behaviour, Russian-layout letter mapping.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_live tests.test_tui_planning
tests.test_tui_polish tests.test_tui_milestones tests.test_tui_flow tests.test_toolchain tests.test_reference` with
TMPDIR short (preamble), all green.
