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


def flow(worker="running", round=2, rounds=4, reviewers=None, final="waiting", attempt=None):
    """A `live.flow` (F1) of a running worker in round 2 of 4, both reviewers running (`live.flow`'s own shape)."""
    if reviewers is None:
        reviewers = [reviewer("acceptance_review", "приёмка", "running"),
                     reviewer("code_review", "ревью кода", "running")]
    return {"task": "T1", "round": round, "rounds": rounds, "worker": {"state": worker}, "reviewers": reviewers,
            "final": {"state": final, "attempt": attempt, "check": "final_verify" if attempt else None}, "select": True, "active": ["исполнитель"],
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

    async def test_l2_the_final_check_attempt_is_drawn_in_the_scheme_tab(self):
        """L2: a flow whose final check runs at attempt 2 draws `final check ↻2/2` in the Scheme tab text, attempt
        1 draws no count (a flow without the attempt, as an older record gives, draws as before)."""
        self.approve(running=True)
        async with self.shell(size=(120, 60)) as pilot:
            await self.loaded(pilot)
            await self.drawn(pilot)
            await self.inject(pilot, flow(final="running", attempt=2))
            self.assertIn("final check ↻2/2", "\n".join(self.main().live_lines))
            await self.inject(pilot, flow(final="running", attempt=1))
            self.assertNotIn("final check ↻", "\n".join(self.main().live_lines))

    async def test_t4e_scheme_on_the_whole_screen_draws_boxes_and_scrolls_to_the_running_one(self):
        """T4e F1/F2/F4: `/scheme` hides the chat, the activity pane and the input; the canvas is the window width
        minus the frame, the padding and the scrollbar (6 cells) and holds box frames (`acceptance review` and
        `code review` side by side), also at 120x30 where the Scheme tab's own pane draws the one-line list; the
        running box's row is inside the visible region after a repaint; with no flow the text is today's `live_view()`.
        Interpretations: the Esc and `/scheme`-again halves are `test_t4e_esc_...`; "box frames" are read from the
        live text (the `╭` rows holding both reviewer titles), "visible" from the pane's scroll offset and height."""
        self.approve(running=True)
        async with self.shell(size=(120, 30)) as pilot:
            await self.loaded(pilot)
            await self.inject(pilot, flow(worker="done"))
            await self.drawn(pilot)
            screen = self.main()
            self.assertNotIn("╭", "".join(screen.live_lines[:1]), screen.live_lines)  # the 40% column: the list
            screen.run_command("/scheme")
            await self.until(pilot, lambda: "flow" in self.live().classes and not self.app.query_one("#chat-pane").display
                             and any("acceptance review" in line and "code review" in line for line in screen.live_lines))
            await pilot.pause()
            for hidden in ("#chat-pane", "#activity", "#input"):
                self.assertEqual(self.app.query_one(hidden).region.width, 0, hidden)
            self.assertGreaterEqual(self.pane().scrollable_content_region.width, 120 - 6)
            top = next(i for i, line in enumerate(screen.live_lines) if "┏" in line)  # the running box's frame
            region = self.pane().scrollable_content_region
            self.assertTrue(region.height < len(screen.live_lines))  # the drawing is not cut to the pane: it scrolls
            self.assertTrue(self.pane().scroll_y <= top and top + 2 < self.pane().scroll_y + region.height)
            self.pane().scroll_to(y=self.pane().max_scroll_y, animate=False)  # the owner scrolled away ...
            await pilot.pause()
            self.app.changed()  # ... and the next repaint brings the running box back into view
            await self.until(pilot, lambda: self.pane().scroll_y <= top < self.pane().scroll_y + region.height)
            self.app.snapshot = replace(self.app.snapshot, flow=None)
            self.app.changed()
            await self.until(pilot, lambda: list(screen.live_lines) == screen.live_view())  # F4: today's text

    async def test_t4e_esc_and_a_second_scheme_restore_the_layout_the_tab_and_the_focus(self):
        """T4e F3/F5: `/scheme` typed on the whole screen (the `/` brings the prompt and the palette up at the bottom)
        or Esc restores the chat, the activity pane, the 40% column, the tab and the focus (the input) it had; an open
        palette takes the first Esc, the whole screen the second; `/scheme` is offered by the palette.
        Interpretation: the starting tab is "Plan" (the fixture's), so the restore is checked against it; the prompt
        on the whole screen is a strip over the bottom of the canvas, closed again by Esc, an emptied input or a
        command."""
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            screen = self.main()
            palette = self.app.query_one("#palette")
            column = self.app.query_one("#right-column").region.width
            tab = self.app.query_one("#right").active
            self.assertEqual(self.app.focused.id, "input")
            await pilot.press("/", "s", "c", "h")
            await pilot.pause()
            self.assertIn("/scheme", [command.name for command in palette.found])
            await pilot.press("e", "m", "e", "enter")
            for leave in ("esc", "/scheme"):
                await self.until(pilot, lambda: screen.scheme_full and self.app.focused.id == "live-pane")
                self.assertEqual(self.app.query_one("#right").active, "tab-live")
                self.assertFalse(self.app.query_one("#chat-pane").display)
                # a `/` on the whole screen opens the palette; Esc closes it first and the whole screen stays
                await pilot.press("/")
                await self.until(pilot, lambda: palette.display and self.app.focused.id == "input")
                await pilot.press("escape")
                await self.until(pilot, lambda: not palette.display and self.app.focused.id == "live-pane")
                self.assertTrue(screen.scheme_full)
                self.assertFalse(self.app.query_one("#chat-pane").display)
                if leave == "esc":
                    await pilot.press("escape")
                else:
                    await pilot.press("/", "s", "c", "h", "e", "m", "e", "enter")
                await self.until(pilot, lambda: not screen.scheme_full and self.app.query_one("#chat-pane").display)
                await pilot.pause()
                self.assertEqual(self.app.query_one("#right").active, tab)
                self.assertEqual(self.app.focused.id, "input")
                self.assertTrue(self.app.query_one("#activity").display)
                self.assertEqual(self.app.query_one("#right-column").region.width, column)
                if leave == "esc":
                    await pilot.press("/", "s", "c", "h", "e", "m", "e", "enter")


    async def test_s1b_leaving_the_scheme_wraps_the_status_at_the_chat_panes_real_width(self):
        """S1b B1/B2: Esc from `/scheme` called `render_state` before the layout returned, so `render_status` measured
        the hidden `#chat-pane` (content width 0 -> 20 cells) and kept "_invalid]" of the message until its text moved.
        B1: after Esc, once the layout has settled, `#status` holds the lines it had before `/scheme`. B2: a status
        update while the scheme is shown stores nothing, and after Esc the lines are those of the pane's real width.
        Interpretations: "the same lines as before" is read from `status_text`; "the lines at 68 cells" from the
        chat pane's content width at 120x40 (asserted, so a layout change cannot hollow the test out)."""
        message = "zplan tools are not installed: run zplan setup. [code: setup.tools_invalid]"
        later = "zplan tools are damaged: run zplan setup again, then restart. [code: setup.tools_damaged]"
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            screen = self.main()
            pane = self.app.query_one("#chat-pane")
            self.app.chat_note = message
            screen.render_state()
            await pilot.pause()
            before = screen.status_text
            self.assertEqual(pane.content_region.width, 68)
            self.assertIn("setup.tools_invalid]", before)
            self.assertIn("zplan tools are not installed", before)
            for change in (None, later):  # B1: nothing changed during `/scheme`; B2: the status changed during it
                shown = screen.status_text
                screen.run_command("/scheme")
                await self.until(pilot, lambda: screen.scheme_full and pane.content_region.width == 0)
                if change:
                    self.app.chat_note = change
                    screen.render_state()
                    await pilot.pause()
                    self.assertEqual(screen.status_text, shown)  # nothing measured at width 0 is stored
                await pilot.press("escape")
                await self.until(pilot, lambda: not screen.scheme_full and pane.content_region.width == 68)
                await pilot.pause()
                await pilot.pause()
                settled = screen.status_text
                screen.status_text = None  # what a repaint at the settled width stores
                screen.render_status()
                self.assertEqual(settled, screen.status_text)
                if not change:
                    self.assertEqual(settled, before)
                else:
                    self.assertNotEqual(settled, before)
                self.assertIn("setup.tools_" + ("damaged" if change else "invalid") + "]", screen_text(self.app))


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
        names = [name for cls in (SchemeTabTests, SchemeContractTests) for name in dir(cls) if name.startswith("test_a")]
        for criterion in "123456789":
            with self.subTest(criterion=criterion):
                self.assertEqual(len([name for name in names if name.startswith("test_a%s_" % criterion)]), 1, names)
        self.assertEqual(len(names), 9, names)
