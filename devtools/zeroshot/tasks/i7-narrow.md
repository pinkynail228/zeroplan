I7 — below 100 columns the main screen shows one pane at a time: «Разговор» first, the canvas tabs beside it
(0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i7).

Why: at 80x24 the chat and the canvas share the width and both are too narrow to read. The approved screen
(docs/ui-redesign/WORK_SCREEN.md; lab `devtools/ui-lab/work.py` `_fit`, `tabs`, `_render_all`, `set_state`) switches
to one pane at a time below 100 columns: a «Разговор» tab joins the front of the tab cycle, the chat pane takes the
full width while it is active, otherwise the canvas column does.

Today (terminal_planner/tui/app.py, MainScreen): `compose` builds `#logo`, `#header`, `Horizontal#panes` holding
`Vertical#chat-pane` (`#status`, `#chat`) and `Vertical#right-column` (`TabbedContent#right` with `TAB_LIVE`,
`TAB_PLAN`, then the file/diff tabs from run i5; `Activity#activity` below it), then `#palette`, `#input`, `Bar#keys`.
`on_resize` -> `layout_for(size)` (logo only) and `render_state()`; `action_view(delta)` cycles the canvas tabs
(Сейчас -> План -> view tabs) and is the input's own key while the input holds text; `show_tab(tab)` switches and
manages focus. strings.py has `chat.title_narrow` («Разговор · ←→ вкладки»).

Change:
- `NARROW_COLUMNS = 100`. `layout_for(size)` sets `self.narrow = size.width < NARROW_COLUMNS` and the screen class
  `narrow`. Narrow: exactly one of `#chat-pane` / `#right-column` is displayed, full width; wide: both, as today.
- Entering narrow shows the chat; leaving it shows the canvas tab that was last active (or План).
- In narrow mode ←→ cycle «Разговор» -> Сейчас -> План -> view tabs -> «Разговор» (same `action_view`, same rule
  for an input holding text). «Разговор» is not a TabPane (the chat pane is outside `#right`): keep the state in one
  attribute (e.g. `self.chat_shown`) and draw a one-row strip for it the way the lab does, or prepend a label to the
  tab strip; pick the simpler one and say which.
- The chat pane's border title in narrow mode is `strings.text("chat.title_narrow")`; the wide title is unchanged.
- `MainScreen.show_chat()`: in narrow mode shows «Разговор»; in wide mode does nothing. The card runs call it when a
  card appears (wiring is the orchestrator's at merge; do not add cards here). Opening a file/diff tab (i5) in
  narrow mode shows the canvas.
- Input, palette and Bar stay full width in both modes; the logo rule stays.
- Test harness: `ShellTest.shell()` (tests/test_tui.py) defaults to `size=(80, 24)`; 46 whole-app calls use the
  default and 32 pass 80x24 explicitly, and many read the canvas, which narrow mode hides. Change the default to
  (120, 40). For the explicit 80x24 calls that now fail, keep the test's purpose: show the canvas first (`→`) when the
  test is about the canvas, or assert the narrow layout when it is about 80 columns. Do not delete tests to get green;
  list in the summary which tests changed and why.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, docs/USER_FLOW.md (narrow section),
tests/test_tui_narrow.py (new), tests/test_tui.py (the default size and LayoutTests), and other tests/test_tui*.py
only for the 80x24 adaptations above. Do not edit strings.py, cards.py, activity.py, palette.py, controller, engine.

Acceptance criteria:
- A1 At 80x24 the first frame shows the chat at full width and no canvas; →, → shows Сейчас then План at full
  width; ← back to «Разговор». At 120x40 both panes show, as today.
- A2 Resizing 120x40 -> 80x24 -> 120x40 switches modes and keeps the canvas tab that was active.
- A3 `show_chat()` from the canvas at 80x24 shows the chat; `open_file_tab("README.md")` from the chat at 80x24 shows
  the file tab.
- A4 Tests per preamble: at most two whole-app tests (A1+A2, A3) in tests/test_tui_narrow.py; the harness change
  keeps the existing suite green.

Non-goals (reviewers must not require): card wiring, inline cards, a 2-column narrow variant, translations,
redesigning the 80x24 logo/header.

Parallel note: runs i3a (cards, dispatcher) and i6 (language: texts, `relabel()`, the chat pane wide title) edit
app.py at the same time; do not move or reformat code outside the layout, `action_view`'s narrow branch, `show_chat`
and the harness size.

DoD: `python3.13 devtools/fasttest.py $(ls tests/test_tui*.py | sed 's#tests/#tests.#;s#\.py$##') tests.test_live
tests.test_layout tests.test_toolchain tests.test_reference` with exit 0; quote its `fasttest:` lines.
