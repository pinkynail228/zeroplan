"""I1b — the Scheme tab drawn by `terminal_planner/tui/scheme.py` (A1-A9) through `tests/tui_support.py`.

The tab of a running attempt is the stage scheme `scheme.render(milestone.milestone_graph(1, rounds)["root"],
scheme.observation_from_flow(snapshot.flow), width, height, limits=...)`, then one `scheme.legend()` line, then the
same `live_status(True)` lines as before; below `FLOW_MIN_WIDTH` or without a flow it keeps today's `live_view()`
(F2/A3). Every tab test drives the real shell (Textual Pilot over a real temporary repository and the fixture
store, `tests/tui_support.py`); the scheme's own lines are recomputed in the test through `scheme.render` (A6), never
hard-coded. They need Textual (the interpreter's own, or the wheels of `ZPLAN_TEST_WHEELHOUSE`) and skip without it.

Interpretations (the worker's summary does not reach the reviewers, so they are recorded here):
- A1's flow is injected into the loaded snapshot (`dataclasses.replace`, the same route `test_tui_flow` uses to
  reach a branch): the fixture plan's stored attempt carries `rounds=4` but no round yet, so "a running worker in
  round 2 of 4" is reached by replacing `snapshot.flow` and repainting. The app refreshes from the store every
  `REFRESH_SECONDS`; each assertion is made right after the repaint, before that refresh.
- A3 names 80x24; at 80 columns the right pane's content region is 36 cells, below `FLOW_MIN_WIDTH` (40), so the
  plain fallback is the required behaviour there and A3's guard ("whenever the pane is at least FLOW_MIN_WIDTH
  wide") is exercised at the boundary: at 88x24 the pane settles at exactly 40 cells and the scheme is fitted:
  the guard and the size in the criterion cannot both hold for the 80x24 layout this app has.
- A7's "the drawing is the same for `milestone_graph(1, r)` and `milestone_graph(3, r)` under the same `limits`" is
  asserted on the rendered text of the two roots, never by comparing the graphs structurally; the task loop's bound
  (`outer_iterations(tasks)`) differs between them, which is exactly what `limits` suppresses.
- A8 is asserted here (its evidence is `tests.test_tui_scheme` unchanged and green, per the criterion); A9 is this
  module's own structure — one test per criterion, checked by `test_a9_` itself.
"""

import unittest
from dataclasses import replace

from terminal_planner import milestone
from test_tui_milestones import MilestoneShell
from tui_support import HAVE_TEXTUAL, screen_text

try:
    from rich.cells import cell_len
    from terminal_planner.tui import scheme
except ImportError:  # pragma: no cover - covered by the bare import scan of tests.test_toolchain
    cell_len = scheme = None
HAVE_RICH = scheme is not None
RICH_REASON = "Rich unavailable: ZPLAN_TEST_WHEELHOUSE with the rich wheels is needed"
TEXTUAL_REASON = "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed"

NOTE = "result M1: done"  # a run's verdict note: one of the `live_status(True)` lines the tab appends


def reviewer(role, name, state):
    return {"role": role, "name": name, "state": state, "text": ""}


def flow(worker="running", round=2, rounds=4, reviewers=None, final="waiting"):
    """A `live.flow` (F1) of a running worker in round 2 of 4, both reviewers running (`live.flow`'s own shape)."""
    if reviewers is None:
        reviewers = [reviewer("acceptance_review", "приёмка", "running"),
                     reviewer("code_review", "ревью кода", "running")]
    return {"task": "T1", "round": round, "rounds": rounds, "worker": {"state": worker}, "reviewers": reviewers,
            "final": {"state": final}, "select": True, "active": ["исполнитель"],
            "elapsed": 300, "silence": 5, "command": "python3.13 -m unittest tests.test_tui_scheme_tab",
            "detached": None}


def scheme_root(rounds):
    """The stage graph `app.py` builds for a flow's `rounds` (the default bound when the flow carries none)."""
    return milestone.milestone_graph(1, rounds if isinstance(rounds, int) else milestone.TASK_ITERATIONS)["root"]


def scheme_lines(data, width, height):
    """`scheme.render`'s output lines for `data`'s observation at `width`/`height` (A6: recomputed, not hard-coded)."""
    rounds = data.get("rounds")
    limits = {"review_loop": rounds} if isinstance(rounds, int) else {}
    return scheme.render(scheme_root(rounds), scheme.observation_from_flow(data), width, height,
                         limits=limits).plain.split("\n")


@unittest.skipUnless(HAVE_TEXTUAL and HAVE_RICH, RICH_REASON if not HAVE_RICH else TEXTUAL_REASON)
class SchemeTabTests(MilestoneShell):
    """A1-A7 through the real shell: the Scheme tab is the stage scheme, its legend and the live status lines."""

    def main(self):
        return next(s for s in self.app.screen_stack if type(s).__name__ == "MainScreen")

    def pane(self):
        return self.app.query_one("#live-pane")

    def live(self):
        return self.app.query_one("#live")

    async def canvas(self, pilot):
        """I7: below 100 columns the screen is narrow — one pane at a time. These checks want the canvas, so leave
        «Conversation» for «Scheme» when the chat is the shown page (a no-op once the canvas is shown)."""
        screen = self.main()
        if screen.narrow and screen.chat_shown:
            await pilot.press("right")
            await pilot.pause()

    def expected(self, data):
        """The tab's own lines for `data` as `app.py` produces them: the scheme at the pane's geometry, the legend,
        then the `live_status(True)` lines (wrapped by terminal cells, `flow.wrap_status`)."""
        from terminal_planner.tui import flow as flow_draw
        region = self.pane().scrollable_content_region
        tail = flow_draw.wrap_status(self.main().live_status(True), region.width)
        height = max(6, region.height - len(tail) - 1)
        return scheme_lines(data, region.width, height) + [scheme.legend().plain] + tail

    async def inject(self, pilot, data):
        """A snapshot carrying `data` as its flow, repainted and given one turn to settle."""
        self.app.snapshot = replace(self.app.snapshot, flow=data)
        self.app.changed()
        await pilot.pause()

    async def drawn(self, pilot):
        """Wait until the tab really draws the scheme. `render_state` runs on mount before the layout pass, so the
        first render of the Scheme pane can land while the pane has no width and leave the plain fallback on the tab
        until the redraw `show_tab` schedules after the refresh (F2/A4's settle path); the drawing's own `#live.flow`
        class is that redraw's own signal, and the pane must report a width the drawing is measured against."""
        await self.until(pilot, lambda: "flow" in self.live().classes
                         and self.pane().scrollable_content_region.width >= self.min_width())
        await pilot.pause()

    async def settled(self, pilot):
        """Wait until the tab's lines are what `render_live` makes for the pane's current geometry — the drawing at
        the settled width after a resize (`verify_live`), not a stale one or the fallback."""
        await self.until(pilot, lambda: list(self.main().live_lines) == self.expected(self.app.snapshot.flow))

    async def fallback(self, pilot):
        """Wait until the tab shows exactly today's `live_view()` with no drawing (`#live.flow` off)."""
        await self.until(pilot, lambda: "flow" not in self.live().classes
                         and list(self.main().live_lines) == self.main().live_view())

    @staticmethod
    def min_width():
        from terminal_planner.tui import app as ui
        return ui.FLOW_MIN_WIDTH

    async def test_a1_the_live_tab_draws_the_scheme_the_legend_and_the_status_lines(self):
        """A1: at 120x40 a flow of a running worker in round 2 of 4 makes the Scheme tab the scheme's own lines
        (the stage names and the round phrase exactly as `scheme.render` produces them), then one legend line, then
        the `live_status(True)` lines below them."""
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            data = flow()
            self.app.run_note = NOTE
            await self.inject(pilot, data)
            await self.drawn(pilot)
            lines = list(self.main().live_lines)
            self.assertEqual("flow" in self.live().classes, True, screen_text(self.app))
            # The scheme's own lines, exactly as `scheme.render` makes them for this observation and geometry, then
            # the legend, then the `live_status(True)` lines (a run's verdict note keeps its blank separator).
            region = self.pane().scrollable_content_region
            tail = ["", NOTE]
            drawn = scheme_lines(data, region.width, max(6, region.height - len(tail) - 1))
            self.assertEqual(lines, drawn + [scheme.legend().plain] + tail, lines)
            self.assertEqual(lines, self.expected(data))
            body = screen_text(self.app)
            for part in ("worker", "acceptance review", "code review", "final check",
                         "review rounds · 2 of 4", "◐ running", "✓ done", "✗ rejected", "◌ waiting", NOTE):
                with self.subTest(part=part):
                    self.assertIn(part, body)

    async def test_a2_a_rejected_reviewer_shows_the_rejected_mark_and_an_accepted_one_the_tick(self):
        """A2: a rejected reviewer verdict in the flow draws the scheme's ✗ on that reviewer, an accepted one ✓."""
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            data = flow(worker="done", reviewers=[reviewer("acceptance_review", "приёмка", "rejected"),
                                                  reviewer("code_review", "ревью кода", "accepted")])
            await self.inject(pilot, data)
            await self.drawn(pilot)
            lines = list(self.main().live_lines)
            self.assertEqual(lines, self.expected(data))
            body = "\n".join(lines)
            self.assertIn("✗ acceptance review", body)
            self.assertIn("✓ code review", body)
            self.assertIn("✗ acceptance review", screen_text(self.app))
            self.assertIn("✓ code review", screen_text(self.app))

    async def test_a3_a_narrow_pane_keeps_the_fitted_scheme_at_the_flow_width(self):
        """A3: a narrow pane at or above `FLOW_MIN_WIDTH` still shows the fitted scheme (no line wider than the
        pane), not the plain fallback; a pane below the bound keeps today's fallback. I7: below 100 columns the
        screen is narrow (the chat alone), so the canvas is shown first; at 44 columns its pane is exactly 40 cells
        (the bound), at 40 columns it is 36 (below it)."""
        from terminal_planner.tui import app as ui
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.drawn(pilot)
            await pilot.resize_terminal(44, 24)
            await self.canvas(pilot)
            await self.settled(pilot)
            region = self.pane().scrollable_content_region
            lines = list(self.main().live_lines)
            self.assertEqual(region.width, ui.FLOW_MIN_WIDTH, screen_text(self.app))  # the boundary, exactly
            self.assertEqual("flow" in self.live().classes, True, screen_text(self.app))
            self.assertEqual(lines, self.expected(self.app.snapshot.flow))
            self.assertTrue(lines and all(cell_len(line.rstrip()) <= region.width for line in lines), lines)  # the English legend is 40 cells plus its trailing gap
            self.assertIn("◐ running", screen_text(self.app))
            await pilot.resize_terminal(40, 24)
            await self.canvas(pilot)
            await self.fallback(pilot)
            narrow = self.pane().scrollable_content_region
            self.assertLess(narrow.width, ui.FLOW_MIN_WIDTH, screen_text(self.app))
            self.assertEqual("flow" in self.live().classes, False, screen_text(self.app))
            self.assertEqual(list(self.main().live_lines), self.main().live_view())

    async def test_a4_without_a_flow_or_below_the_flow_width_the_tab_keeps_live_view(self):
        """A4: without a flow, and with a pane narrower than `FLOW_MIN_WIDTH`, the tab shows exactly today's
        `live_view()` lines (`snapshot.panel` first, then the planner's or the run's lines)."""
        from terminal_planner.tui import app as ui
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.drawn(pilot)
            data = self.app.snapshot.flow
            self.assertIsNotNone(data)
            self.app.snapshot = replace(self.app.snapshot, flow=None)
            self.app.changed()
            await self.fallback(pilot)
            self.assertEqual("flow" in self.live().classes, False, screen_text(self.app))
            self.assertEqual(list(self.main().live_lines), self.main().live_view())
            self.assertIn(self.app.snapshot.panel[0], self.main().live_lines)
            self.app.snapshot = replace(self.app.snapshot, flow=data)
            self.app.changed()
            await self.drawn(pilot)
            await pilot.resize_terminal(40, 24)
            await self.canvas(pilot)
            await self.fallback(pilot)
            self.assertLess(self.pane().scrollable_content_region.width, ui.FLOW_MIN_WIDTH, screen_text(self.app))
            self.assertEqual("flow" in self.live().classes, False, screen_text(self.app))
            self.assertEqual(list(self.main().live_lines), self.main().live_view())

    async def test_a5_a_resize_re_renders_the_scheme_to_the_new_width(self):
        """A5: after a resize the existing `verify_live` settle path redraws the scheme at the pane's new width —
        every drawn line fits the settled pane, and the drawing is what `scheme.render` makes there."""
        from terminal_planner.tui import app as ui
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.drawn(pilot)
            first = list(self.main().live_lines)
            self.assertEqual(first, self.expected(self.app.snapshot.flow))
            widths = []
            for size in ((160, 45), (88, 40), (120, 40)):
                await pilot.resize_terminal(*size)
                await self.canvas(pilot)  # I7: the 88x40 resize lands in narrow mode; show the canvas
                await self.settled(pilot)
                region = self.pane().scrollable_content_region
                lines = list(self.main().live_lines)
                with self.subTest(size=size, pane=region.width):
                    self.assertGreaterEqual(region.width, ui.FLOW_MIN_WIDTH)
                    self.assertEqual("flow" in self.live().classes, True, screen_text(self.app))
                    widths.append(region.width)
                    self.assertTrue(all(cell_len(line) <= region.width for line in lines), lines)
                    self.assertEqual(lines, self.expected(self.app.snapshot.flow))
                    self.assertEqual(self.live().size.height, len(lines))
            self.assertEqual(len(set(widths)), len(widths))  # every size settled on its own pane width
            self.assertEqual(first, list(self.main().live_lines))  # and back at 120x40 the drawing is the first one

    async def test_a6_the_tab_no_longer_draws_flow_py_boxes_and_the_other_tabs_are_unchanged(self):
        """A6: the drawing asserted on the Scheme tab is the scheme's own output — F2's `flow.py` boxes (`■`
        legend, the delivery result line) are not drawn any more — while the other tabs keep their sources."""
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.drawn(pilot)
            lines = list(self.main().live_lines)
            body = "\n".join(lines)
            for gone in ("■ worker", "result → main:", "─ journal ─", "active:"):
                with self.subTest(gone=gone):
                    self.assertNotIn(gone, body)  # F2's `flow.py` drawing is not on the Scheme tab any more
            self.assertEqual(lines, self.expected(self.app.snapshot.flow))  # the scheme's output is drawn instead
            plan = "\n".join(self.main().plan_lines)
            for line in [piece for piece in self.app.snapshot.lines if piece.strip()][:3]:
                with self.subTest(line=line):
                    self.assertIn(line, plan)  # Plan keeps its own sources (the plan pane's lines)
            await pilot.press("right")  # Plan shows the plan pane
            await pilot.pause()
            self.assertTrue(any(line.startswith("Next:") for line in self.app.snapshot.lines), screen_text(self.app))
            await pilot.press("right")  # Journal shows the stored journal, one line per entry
            await pilot.pause()
            journal = list(self.main().journal_lines)
            self.assertEqual(journal, list(self.app.snapshot.journal) or journal[:1])

    async def test_a7_loop_bounds_come_only_from_the_flow_and_never_from_the_graph(self):
        """A7: with `flow["rounds"]` = 4 the review loop shows its bound 4; with `rounds` None no loop bound is
        shown and the task loop never shows a bound; and `milestone_graph(1, r)` and `milestone_graph(3, r)` render
        the same text under the same `limits` (asserted on the rendered text of the two roots)."""
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.drawn(pilot)
            await self.inject(pilot, flow())
            body = "\n".join(self.main().live_lines)
            self.assertIn("review rounds · 2 of 4", body)  # the flow's own bound
            self.assertIn("↻ tasks one by one", body)
            for bound in ("up to 16 times", "up to 20 times", "up to 4 times", "up to 3 times"):
                with self.subTest(bound=bound):
                    self.assertNotIn(bound, body)  # never a bound the flow does not carry
            await self.inject(pilot, flow(rounds=None))
            body = "\n".join(self.main().live_lines)
            self.assertIn("↻ review rounds · 2", body)  # the count stays, the bound is gone
            self.assertIn("↻ tasks one by one", body)
            for bound in ("of 4", "up to 4 times", "up to 3 times", "up to 16 times", "up to 20 times"):
                with self.subTest(bound=bound):
                    self.assertNotIn(bound, body)
            # The two roots the task names, rendered under one `limits` on identically captured text.
            for rounds in (4, 5):
                observation = scheme.observation_from_flow(flow(rounds=rounds))
                limits = {"review_loop": rounds}
                one = scheme.render(milestone.milestone_graph(1, rounds)["root"], observation, 76, 30,
                                    limits=limits).plain
                three = scheme.render(milestone.milestone_graph(3, rounds)["root"], observation, 76, 30,
                                      limits=limits).plain
                with self.subTest(rounds=rounds):
                    self.assertIn("review rounds · 2 of %s" % rounds, one)
                    self.assertEqual(one, three)
            # The box mode takes the same `limits` decision: the round badge keeps the count without the bound.
            loop_graph = {"kind": "seq", "name": "g", "children": [
                {"kind": "loop", "name": "review_loop", "maxIterations": 4,
                 "body": {"kind": "step", "name": "worker"}},
                {"kind": "step", "name": "steward_apply"}]}
            observation = {"review_loop": {"count": 2}}
            boxed = scheme.render(loop_graph, observation, 60, 30, limits={}).plain
            self.assertIn("↻2", boxed)
            self.assertNotIn("2/4", boxed)
            counted = scheme.render(loop_graph, observation, 60, 30, limits={"review_loop": 4}).plain
            self.assertIn("↻2/4", counted)


@unittest.skipUnless(HAVE_RICH, RICH_REASON)
class SchemeContractTests(unittest.TestCase):
    """A8/A9: `scheme.render`'s default behaviour, and the one-test-per-criterion shape of this module."""

    def test_a8_render_without_limits_is_unchanged(self):
        """A8: `scheme.render` without `limits` renders exactly as before — the same lines as `limits=None`, with
        the graph's own loop bounds (the behaviour `tests.test_tui_scheme`, unchanged, still asserts)."""
        observation = {"worker": {"state": "running"}, "review_loop": {"count": 2}}
        for tasks in (1, 3):
            for width, height in ((40, 10), (70, 30), (120, 40)):
                root = milestone.milestone_graph(tasks)["root"]
                before = scheme.render(root, observation, width, height)
                with self.subTest(tasks=tasks, size=(width, height)):
                    self.assertEqual(before.plain, scheme.render(root, observation, width, height, limits=None).plain)
                    self.assertEqual([str(s.style) for s in before.spans],
                                     [str(s.style) for s in
                                      scheme.render(root, observation, width, height, limits=None).spans])
        plain = scheme.render(milestone.milestone_graph(1)["root"], observation, 76, 30).plain
        self.assertIn("review rounds · 2 of 4", plain)  # the graph's own review bound, as today
        self.assertIn("up to 16 times", plain)  # and the graph's own task-loop bound, as today

    def test_a9_one_test_per_criterion_through_the_shell(self):
        """A9: this module keeps exactly one test per acceptance criterion A1-A8 (and this one for A9), each driving
        the real shell through `tests/tui_support.py` (`SchemeContractTests`' two are the pure halves A8 needs)."""
        names = [name for cls in (SchemeTabTests, SchemeContractTests) for name in dir(cls) if name.startswith("test_")]
        for criterion in "123456789":
            with self.subTest(criterion=criterion):
                self.assertEqual(len([name for name in names if name.startswith("test_a%s_" % criterion)]), 1, names)
        self.assertEqual(len(names), 9, names)
