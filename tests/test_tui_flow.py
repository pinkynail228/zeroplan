"""The app's Сейчас tab and the `flow.py` helpers (`wrap_status`, `clip`).

TUI tests drive the real shell through `tests/tui_support.py`: I1b/A6 — the tab of an active attempt is the stage
scheme (`scheme.render`, recomputed in the tests), so the tab tests assert the scheme's own output; a resize across
the fallback boundary re-measures it, and C0c2's plain fallback keeps Textual's own wrapping of a line wider in cells
than the pane. The flow-box drawing (`flow.draw`) was removed by i8-cleanup with its tests; `flow.py` keeps only what
the app and the activity pane call.

i8-cleanup A3 interpretation: the task's «~445-447 / ~479-483» home-screen and readiness key-bar examples sit in the
part of `docs/USER_FLOW.md` that describes the line UI (`zplan --plain`, non-TTY), which is live — `catalog.py` still
registers those keys and `delivery.py` still prints «Плана нет.». Rewriting them into the full-screen bottom bar would
make the doc wrong about `--plain`, and the non-goal forbids rewriting sections that are still accurate, so those blocks
stay as they were; the current form («/» commands, decision cards in the chat, the bottom bar
«notes · main · работы нет · ←→ вкладки · / команды · ctrl+q выйти») is documented in the full-screen section instead,
and no key-bar example contains `[c]` or `[t]`.

They need Textual (the interpreter's own, or the wheels of
ZPLAN_TEST_WHEELHOUSE) and skip without it."""

import unittest

from test_tui_milestones import MilestoneShell
from tui_support import HAVE_TEXTUAL, screen_text

# The source-hygiene scan (`tests.test_toolchain`) imports every test module with neither Textual nor Rich
# importable, so Rich — and `flow`, which uses it — is imported only when it is there.
try:
    from rich.cells import cell_len
    from terminal_planner.tui import flow, scheme
    from test_tui_scheme_tab import scheme_lines
except ImportError:  # pragma: no cover - covered by the bare import scan of tests.test_toolchain
    cell_len = flow = scheme = scheme_lines = None


def tab_lines(app, screen):
    """I1b/A6: the Сейчас tab's own lines for the snapshot's flow, recomputed through `scheme.render` at the pane's
    geometry — the scheme, its legend, then the `live_status(True)` lines (`flow.wrap_status`)."""
    region = app.query_one("#live-pane").scrollable_content_region
    tail = flow.wrap_status(screen.live_status(True), region.width)
    drawn = scheme_lines(app.snapshot.flow, region.width, max(6, region.height - len(tail) - 1))
    return drawn + [scheme.legend().plain] + tail


@unittest.skipUnless(HAVE_TEXTUAL, "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8")
class FlowTabTests(MilestoneShell):
    """I1b/A6 (was F2/A4-A5) through `tests/tui_support.py`: the Сейчас tab of an active attempt draws the stage
    scheme; these checks recompute its lines through `scheme.render` (`tab_lines`) instead of F2's boxes, and keep
    F2's fallback and cell wrapping behaviour."""

    def main(self):
        return next(s for s in self.app.screen_stack if type(s).__name__ == "MainScreen")

    def tab(self):
        from textual.widgets import TabbedContent
        return self.app.query_one("#right", TabbedContent).active

    async def canvas(self, pilot):
        """I7: below 100 columns the screen is narrow — one pane at a time. The flow checks want the canvas, so
        leave «Разговор» for «Сейчас» when the chat is the shown page (a no-op once the canvas is shown)."""
        screen = self.main()
        if screen.narrow and screen.chat_shown:
            await pilot.press("right")
            await pilot.pause()

    def live_rows(self):
        """What the `#live` widget itself renders, row by row: the compositor strips cropped to the widget's own
        region, so a wide line clipped in the tab is seen even though the area above the chat repeats the same
        run lines (C0c2) elsewhere on the screen."""
        live = self.app.query_one("#live")
        region = live.region
        strips = self.app.screen._compositor.render_strips()
        return [strips[y].crop(region.x, region.right).text.rstrip() for y in range(region.y, region.bottom)]

    async def test_a6_an_active_attempt_draws_the_scheme_on_the_live_tab(self):
        from terminal_planner.tui import app as ui
        """I1b/A6: at 160x45 and 120x40 the Сейчас tab of an active attempt is the stage scheme (`scheme.render`
        for `snapshot.flow`, then its legend) — computed in the test through `tab_lines`, never hard-coded, so F2's
        `flow.py` boxes are not asserted here any more — and at a pane below `FLOW_MIN_WIDTH` (a 40-column narrow
        terminal, a 36-cell canvas) it falls back to C0c2's plain `snapshot.panel` lines (F2/A3)."""
        for size in ((160, 45), (120, 40)):
            with self.subTest(size=size, mode="scheme"):
                self.state = self.root / ("state-flow-%sx%s" % size)
                self.approve(running=True)
                async with self.shell(self.controller(), size=size) as pilot:
                    await self.loaded(pilot)
                    await self.canvas(pilot)  # I7: wide here, so a no-op; the flow checks want the canvas
                    self.assertEqual(self.tab(), ui.TAB_LIVE, screen_text(self.app))
                    # The first render can land before the layout pass (a degenerate pane), so wait for the tab to
                    # really be `tab_lines` for the pane's settled geometry, not merely for the `flow` class.
                    await self.until(pilot, lambda: list(self.main().live_lines)
                                     == tab_lines(self.app, self.main()))
                    screen, lines = self.main(), list(self.main().live_lines)
                    self.assertEqual(lines, tab_lines(self.app, screen), lines)
                    text = "\n".join(lines)
                    for word in ("worker", "acceptance review", "code review", "final check",
                                 "review rounds · up to 4 times", "◐ running  ✓ done  ✗ rejected  ◌ waiting"):
                        with self.subTest(word=word):
                            self.assertIn(word, text)
                    self.assertNotIn("■", text)  # F2's box legend is not the tab's drawing any more
        with self.subTest(size=(40, 24), mode="plain fallback"):
            self.state = self.root / "state-flow-40x24"
            self.approve(running=True)
            async with self.shell(self.controller(), size=(40, 24)) as pilot:
                await self.loaded(pilot)
                # I7: below 100 columns the screen is narrow (the chat alone), so show the canvas; at 40 columns
                # the canvas pane is 36 cells, below `FLOW_MIN_WIDTH`, and keeps today's plain fallback.
                await self.canvas(pilot)
                lines = list(self.main().live_lines)
                self.assertFalse("flow" in self.app.query_one("#live").classes, screen_text(self.app))
                self.assertEqual(lines, self.main().live_view())
                self.assertTrue(lines)
                self.assertNotIn("◐", "\n".join(lines))  # C0c2's panel line (live.py, T1's text), not the drawing

    async def test_a6_a_resize_re_measures_the_scheme_to_the_settled_width(self):
        """I1b/A6 (was F2/A4): after a resize the drawing matches the pane the layout settled on — the same mode
        (the scheme or C0c2's plain fallback) and the scheme's own output for the settled width — not a stale one.

        Reproduction before the fix, through MilestoneShell with `approve(running=True)`, resize 160x45 -> 120x40
        -> 88x40: `render_state` runs inside the resize handler, before the layout pass, so it read a stale /
        degenerate pane width (once below `FLOW_MIN_WIDTH` at the 88-column terminal, the pane settles at 40) — the
        tab kept the plain fallback although `snapshot.flow` is set, and the 120-column boxes were drawn 54 cells
        wide while the pane settled at 56. The tab now redraws (`render_settled`/`verify_live`) once the geometry
        has settled, re-checking after the redraw itself may have shown or hidden the pane's scrollbar.

        Interpretations recorded here: F2/A4 keeps drawing while `snapshot.flow` is set, so the mode is asserted per
        settled size — the scheme at every pane width at or above `FLOW_MIN_WIDTH` (the 88- and 80-column narrow
        terminals, whose canvas panes are 84 and 76 cells), C0c2's plain lines below it (the 40-column narrow
        terminal, a 36-cell canvas). I7: below 100 columns the screen is narrow, so the checks show the canvas
        (`canvas`) after each resize. I1b/A6: the drawing is recomputed through `scheme.render` (`tab_lines`) at the
        settled pane geometry, not hard-coded, and every drawn line fits the pane in terminal cells; the widget's
        auto height still follows the drawing."""
        from terminal_planner.tui import app as ui
        self.approve(running=True)
        async with self.shell(self.controller(), size=(160, 45)) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: "flow" in self.app.query_one("#live").classes)
            self.assertEqual(self.tab(), ui.TAB_LIVE, screen_text(self.app))
            # I7: below 100 columns the screen is narrow (the chat alone on a resize into it), so show the canvas
            # after each resize; the fallback boundary is crossed at the 40-column terminal (a 36-cell pane), where
            # the canvas is still narrow mode.
            for size, drawn in (((120, 40), True), ((88, 40), True), ((80, 24), True), ((40, 24), False),
                                ((160, 45), True)):  # across the fallback boundary and back
                await pilot.resize_terminal(*size)
                await self.canvas(pilot)
                if drawn:
                    # The render can run inside the resize handler before the layout pass (a stale, degenerate
                    # pane), so wait for the scheme's own lines for the settled geometry, not merely the class.
                    await self.until(pilot, lambda: list(self.main().live_lines)
                                     == tab_lines(self.app, self.main()))
                else:
                    await self.until(pilot, lambda: list(self.main().live_lines) == self.main().live_view())
                live = self.app.query_one("#live")
                pane = self.app.query_one("#live-pane")
                width = pane.scrollable_content_region.width
                with self.subTest(size=size, drawn=drawn, pane=width):
                    self.assertEqual("flow" in live.classes, drawn, screen_text(self.app))
                    screen, lines = self.main(), list(self.main().live_lines)
                    if drawn:
                        # the scheme's own lines for the settled pane, and every one of them fits it in cells
                        self.assertEqual(lines, tab_lines(self.app, screen), lines)
                        self.assertLessEqual(max(cell_len(line) for line in lines), width, lines)
                    else:
                        self.assertEqual(lines, self.main().live_view())
                    self.assertEqual(live.size.height, len(lines), screen_text(self.app))
            body = screen_text(self.app)
            self.assertIn("◐ running", body)  # the scheme's legend row is drawn again
            self.assertIn("final check", body)

    async def test_a3_the_plain_fallback_keeps_wrapping_a_line_wide_in_cells(self):
        """Regression (A3): the drawn-box `nowrap` rule never reaches C0c2's plain fallback.

        Reproduction before the fix: `#live` carried `text-wrap: nowrap` in every mode, so a fallback line short in
        characters but wide in terminal cells — 30 Chinese characters (60 cells) at a content width below 60 — was
        passed through `wrapped` unchanged (it counts characters) and then clipped on the right instead of being
        split, as C0c2 let Textual do; the tail of the line vanished from the screen. The `flow` class now tags
        `#live` only while the drawing is shown, so the fallback keeps Textual's own wrapping. Interpretations
        recorded here: F2/A3 keeps the fallback exactly as C0c2 has it, Textual's own wrapping of a line wider than
        the pane included; the snapshot is replaced in place (a copy without a flow, carrying the wide panel line)
        to reach that branch, because the fixture attempt always carries a flow (F1)."""
        from dataclasses import replace
        wide = "汉" * 30  # 30 characters, 60 terminal cells
        self.approve(running=True)
        async with self.shell(self.controller(), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: "flow" in self.app.query_one("#live").classes)
            live = self.app.query_one("#live")
            self.assertIn("flow", live.classes, screen_text(self.app))  # the drawing keeps its pre-wrapped lines
            self.app.snapshot = replace(self.app.snapshot, flow=None, panel=(wide,))
            self.app.changed()
            await pilot.pause()
            self.assertNotIn("flow", live.classes, screen_text(self.app))  # the fallback keeps Textual's wrapping
            self.assertEqual(self.main().live_lines[:1], [wide])
            body = screen_text(self.app)
            self.assertEqual(body.count("汉"), len(wide), body)  # the whole line is on screen, not clipped

    async def test_a4_appended_status_lines_wrap_by_cells_on_the_drawing(self):
        """Regression (A4): while the drawing is shown (the `#live.flow` `nowrap` rule keeps the box borders on one
        row) an appended planner/run line is wrapped by terminal cells, so a line short in characters but wide in
        cells is split, not clipped on the right.

        Reproduction before the fix: at 120x40 with an active attempt, appending `"汉" * 30 + "END"` to
        `app.run_lines` (with `run_watch = "M1"`) and refreshing left the rendered Сейчас region 28 characters wide
        and dropped `END`: `render_state` wrapped the tail through `wrapped`, which counts characters (33 <= 56, so
        no break), and the `nowrap` rule then cut the 63-cell line at the pane edge. The tail now goes through
        `flow.wrap_status`, which wraps by cells (`flow._wrap_cells`), so the whole line — `END` included — reaches
        the screen, on as many rows as it needs.

        Interpretations recorded here: the tail rows of `live_lines` belong to the drawing branch, so the pane's own
        rendered region is read (`live_rows`) rather than the whole screen, where the area above the chat repeats the
        same run lines (C0c2) and would mask a clipped tab. `flow.wrap_status` is also checked as a pure function:
        no returned line exceeds the width in cells."""
        self.approve(running=True)
        wide = "汉" * 30  # 30 characters, 60 terminal cells
        async with self.shell(self.controller(), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: "flow" in self.app.query_one("#live").classes)
            live = self.app.query_one("#live")
            self.assertIn("flow", live.classes, screen_text(self.app))
            width = self.app.query_one("#live-pane").scrollable_content_region.width
            self.app.run_watch = "M1"
            self.app.run_lines.append(wide + "END")
            self.app.changed()
            await pilot.pause()
            self.assertEqual(flow.wrap_status(["x" * width + "汉汉END"], width)[-1], "汉汉END")  # pure: cells, not chars
            self.assertTrue(all(cell_len(line) <= width for line in flow.wrap_status([wide + "END"], width)))
            # the tail rows lose nothing: concatenated, they are the whole appended line, only re-wrapped
            self.assertIn(wide + "END", "".join(self.main().live_lines))
            rows = self.live_rows()
            self.assertTrue(all(cell_len(row) <= width for row in rows), rows)  # every rendered row fits the pane
            self.assertIn("END", "\n".join(rows))  # the tail reaches the screen instead of being clipped
