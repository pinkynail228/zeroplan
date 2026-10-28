Flake-waits — make the load-flaky TUI tests wait on the value they assert (0.5.2, before the tag; STATE Open).

Cause (orchestrator audit 2026-10-24, static read): each test asserts right after a proxy wait (a header on screen,
a screen class on top, one `pilot.pause()`) while a worker hand-over or a `call_after_refresh` repaint is still due.
Use the existing helpers only: `ShellTest.until(pilot, condition, timeout)` (tests/test_tui.py:278) and `shows(pilot,
text)`. Pattern: wait on the exact value you then assert. No new helper, no sleeps, no longer timeouts.

Write-set: tests/test_tui_milestones.py, tests/test_tui_planning.py, tests/test_tui_language.py, tests/test_tui_chat.py,
tests/test_tui_live.py, terminal_planner/tui/modals.py (BootstrapScreen only).

Acceptance criteria:
- F1 PaneTabTests.test_a1_the_live_tab_shows_the_live_lines_then_the_planner_or_the_run_lines (~:1707-1752) waits
  until `screen.live_lines == tab_lines()` before each compare. Example of the failure it removes: live_lines
  `['  идёт 1 с']` (plain branch, pane not yet wide) vs the flow lines.
- F2 test_tui_planning GoalFormTests.test_a2_* waits for `len(self.app.progress) == 4` before comparing `progress`
  and for the clean readiness re-check before `press("g")`; RevisionStateTests.test_c1_* uses `await self.shows(pilot,
  "(r1 → r2)")` and waits on the full bottom bar before its `[g]`/`[n]` asserts.
- F3 test_tui_chat LifecycleGuardChatTests.test_a3_a_chat_goal_handed_over_while_m1_is_active* waits until
  `"ещё выполняется" in self.app.goal_message` before the store and message asserts, and `shows(pilot, "M1")` for the
  one-shot `flat()` read; test_tui_live la5 bar tests wait on the whole final bar, not a substring.
- F4 BootstrapScreen.render_state (modals.py ~97-101) returns when the screen is not attached or `#bootstrap-body`
  is not mounted (mirror MainScreen's closing guard); test_tui_language MainScreenLanguageTests.test_a3_a4 waits for
  `#bootstrap-body` before reading it. Example: a Resize before compose no longer raises NoMatches.
- F5 No assertion is weakened or removed: every changed test asserts the same values as before.

Non-goals (reviewers must not require): other tests, other sleeps in the suite, a new wait helper, refactoring the
`settled` duplicates, Linux runs.

Risk: low (tests + one guard). DoD: three consecutive runs of `python3.13 devtools/fasttest.py tests.test_tui_milestones
tests.test_tui_planning tests.test_tui_language tests.test_tui_chat tests.test_tui_live`, each exit 0; quote the
three `fasttest:` lines.
