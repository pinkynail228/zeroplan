I1b — the Сейчас tab draws the stage scheme with tui/scheme.py (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i1b).

Why: in 0.5.1 the owner could not see the run's scheme (baseline dead end 3, docs/ui-redesign/baseline-0.5.1/README.md).
The approved look is the lab's scheme (`devtools/ui-lab/work.py` state "running", drawn by
`devtools/ui-lab/flowdraw.py`); its product port is `terminal_planner/tui/scheme.py` (merged, tested): the real stage
graph plus an observation, fitted into the pane as boxes, a tree or a window, with a legend.

Today: `MainScreen.render_live` (terminal_planner/tui/app.py, near line 1246) draws `snapshot.flow` with
`flow_draw.draw(...)` (terminal_planner/tui/flow.py) when the pane is at least `FLOW_MIN_WIDTH` wide, then appends
`live_status(True)` wrapped by `flow_draw.wrap_status`; without a flow or below that width it shows `live_view()`.

Change: when `snapshot.flow` is present and the pane is at least `FLOW_MIN_WIDTH` wide, the tab shows
`scheme.render(graph_root, scheme.observation_from_flow(snapshot.flow), width, height)` followed by one
`scheme.legend()` line, then the same `live_status(True)` lines as today. `graph_root` is
`milestone.milestone_graph(1, rounds)["root"]` (cached; a pure builder) with `rounds = snapshot.flow["rounds"]` when
it is an int, else `milestone.TASK_ITERATIONS` for the build only. The graph's loop bounds are not facts of this
attempt (the task-loop bound depends on the task count, which the flow does not carry; `rounds=None` means unknown,
live.py `flow`), so the scheme must not show them: add to `scheme.render` a keyword `limits=None` (a dict loop name ->
bound to show; loops not in it are drawn without "of N"; None keeps today's behaviour for existing callers) and pass
`{"review_loop": rounds}` only when `snapshot.flow["rounds"]` is an int, else `{}`. `height` is the pane's content height minus the legend and
status lines, never below 6. The `words` argument stays at its default (the built-in Russian words; languages are
run i6). The fallback (no flow, or narrower than `FLOW_MIN_WIDTH`) stays exactly as today.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, terminal_planner/tui/scheme.py (the `limits`
keyword only), docs/USER_FLOW.md (the line that describes the Сейчас tab, only if it names the old boxes),
tests/test_tui_flow.py, tests/test_tui_live.py, tests/test_tui_scheme.py, tests/test_tui_scheme_tab.py (new).
Do not edit terminal_planner/tui/flow.py, terminal_planner/tui/strings.py or terminal_planner/milestone.py; leave
flow.py in place (its removal is run i8).

Acceptance criteria:
- A1 With a snapshot flow of a running worker in round 2 of 4 at 120x40, the Сейчас tab text contains the scheme's
  stage names and round phrase exactly as `scheme.render` produces them for that observation, the legend words, and
  the `live_status` lines below them.
- A2 A rejected reviewer verdict in the flow shows the scheme's rejected mark (✗) on that reviewer; an accepted one
  shows ✓.
- A3 At 80x24 the tab still shows a fitted scheme (no line wider than the pane), not the plain fallback, whenever the
  pane is at least `FLOW_MIN_WIDTH` wide.
- A4 Without a flow, or with the pane narrower than `FLOW_MIN_WIDTH`, the tab shows exactly today's `live_view()` lines.
- A5 A resize re-renders the scheme to the new width (the existing `verify_live` settle path keeps working).
- A6 Every other existing behaviour is unchanged; tests that asserted the old flow.py boxes on the Сейчас tab now
  assert the scheme output (computed through `scheme.render` in the test, not hard-coded).
- A7 With `flow["rounds"]` = 4 the review loop shows its bound 4; with `rounds` None no loop bound is shown; the task
  loop never shows a bound; the drawing is the same for `milestone_graph(1, r)` and `milestone_graph(3, r)` roots
  under the same `limits` (asserted on rendered text, not by calling the same code path twice).
- A8 `scheme.render` without `limits` renders exactly as before (existing scheme tests unchanged and green).
- A9 One test per criterion through tests/tui_support.py.

Non-goals (reviewers must not require): a planner scheme or per-step timers (0.6.0), spinner animation or a new
timer (tick stays 0), translated words, moving the Журнал tab, slash commands, cards, removing flow.py, any change to
controller or engine data.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_live tests.test_tui_planning
tests.test_tui_polish tests.test_tui_milestones tests.test_tui_flow tests.test_tui_scheme tests.test_toolchain
tests.test_reference` with TMPDIR short (preamble), all green.
