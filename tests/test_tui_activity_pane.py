"""I1c — the Journal tab becomes the always-visible «What's happening» pane under the canvas (A1-A5).

Two whole-app tests through `tui_support` (A7: the pane's own logic is tested in `tests/test_tui_activity.py`, so
this module drives the real shell only twice). The pane is `terminal_planner.tui.activity.Activity`, id `activity`,
a child of the `Vertical#right-column` under the canvas `TabbedContent#right`; its lines are `Snapshot.journal` and
its silence is `flow["silence"]`.

Interpretations (the worker's summary does not reach the reviewers, so they are recorded here):
* A2's «the newest lines that fit» is the pane's own rule, so the test computes the expected lines from the pane's
  content height (`pane.size.height`) and asserts the older lines are dropped, never a hard-coded count; an empty
  journal is the widget's own `canvas.log_empty` line (the old `JOURNAL_EMPTY` is gone, A2).
* A3 is checked by injecting a minimal `live.flow` (F1) carrying `silence = 187` into the loaded snapshot
  (`dataclasses.replace`, the route `test_tui_scheme_tab` uses) and reading the pane's own `border_subtitle`; the
  expected text is `strings.text("live.last_event", …)`, and the language is pinned to `ru` in `setUp`, so the
  literal «last: … · 3:07 ago» holds. `flow = None` is the "no flow" leg.
* A1's «no Journal» is read off the widget tree (the real `Tab` labels and the absence of `#journal-pane`/`#journal`)
  and off the module (`TAB_JOURNAL`/`TAB_JOURNAL_TITLE` are gone), not off doc text.
* A5's «help, key bar, catalog and USER_FLOW no longer name a Journal tab»: the key bar and the main help carry the
  arrow segment `←→ tabs` and no `Journal` (the [e] tail action's label is the lowercase `log`, a different
  thing); the catalog never had a tab row, so the check is that no screen title or action label is `Journal`; in
  `docs/USER_FLOW.md` the wireframe tab strip and the old cycle string are gone while «What's happening» is named. The
  pane's own height (8 rows at the 40-row layout, never below 4, `zplan.tcss`) is baked into the layout; the tests
  read `pane.size.height` rather than restating the number, and only A1 checks the pane sits under the canvas.
"""

import os
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from terminal_planner import catalog, live
from terminal_planner.authority import Authority, atomic_state, decode
from terminal_planner.delivery import Delivery
from terminal_planner.tui import strings
from test_tui_milestones import MilestoneShell
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

TEXTUAL_REASON = "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"

if HAVE_TEXTUAL:
    from terminal_planner.tui.activity import Activity
    from terminal_planner.tui.flow import clip


def flow(silence=187):
    """A minimal `live.flow` (F1): the keys `scheme.observation_from_flow` and the activity pane read."""
    return {"task": "T1", "round": 2, "rounds": 4, "worker": {"state": "running"},
            "reviewers": [{"role": "acceptance_review", "name": "приёмка", "state": "running", "text": ""},
                          {"role": "code_review", "name": "ревью кода", "state": "running", "text": ""}],
            "final": {"state": "waiting"}, "select": True, "active": ["исполнитель"],
            "elapsed": 300, "silence": silence, "command": None, "detached": None}


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ActivityPaneTests(MilestoneShell):
    """A1-A5 through the real shell at the two supported sizes."""

    SIZES = ((120, 40), (80, 24))

    def setUp(self):
        super().setUp()
        from terminal_planner.tui import app as ui
        self.ui = ui
        self.environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "ui-config")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        strings.set_language("ru")  # the pane's words come from the frozen catalog; pin them for the literal checks

    def main(self):
        return next(s for s in self.app.screen_stack if type(s).__name__ == "MainScreen")

    def canvas(self):
        from textual.widgets import TabbedContent
        return self.app.query_one("#right", TabbedContent)

    def tab(self):
        return self.canvas().active

    def labels(self):
        """Every canvas tab label in strip order (the whole strip, so a stray third label is caught)."""
        from textual.widgets._tabs import Tab
        return [tab.label_text for tab in self.app.query(Tab)]

    def pane(self):
        return self.app.query_one("#activity", Activity)

    def seed_journal(self, entries):
        """Give the dispatched attempt a stored live record with `entries` (`(at, text)` pairs, oldest first) as its
        journal, exactly as the delivery service's store holds it (the `SharedServiceTests` pattern, written before
        the shell opens so the session's own Authority loads it)."""
        with Authority(self.state, self.project, fixture_id="test") as a:
            path = a.path
        state = decode(path.read_text())
        record = state["runs"][-1]
        record["live"] = {**live.new(), "journal": [{"at": at, "text": text} for at, text in entries]}
        atomic_state(path, state)
        return record

    async def append_journal(self, pilot, at, text):
        """A new stored entry while the app holds the session: on the controller's worker, under the session's own
        authority, the way the delivery service writes it — then a read-only refresh carries it to the screen."""
        def work(app):
            record = app.authority.state["runs"][-1]
            record["live"]["journal"].append({"at": at, "text": text})
            app.authority.save()
        await self.post_and_wait(pilot, work)

    async def test_a1_a2_a3_the_pane_is_under_the_two_tab_canvas_and_shows_the_journal_and_its_silence(self):
        """A1+A2+A3 at both supported sizes through the real shell: the canvas is the two tabs «Scheme»/«Plan» (no
        Journal tab, pane or action) with the «What's happening» pane under it, whichever tab is active; the pane shows
        the newest journal lines that fit, oldest first, or the widget's own empty line; with `flow["silence"] = 187`
        its border subtitle is `live.last_event` with «3:07», and no flow leaves it empty."""
        self.approve(running=True)  # one attempt in the store: its live record carries the seeded journal
        self.seed_journal([("2026-10-15T09:%02d:00Z" % i, "T1: строка %02d" % i) for i in range(12)])
        expected = list(Delivery.journal_lines(self.stored()["runs"][-1]["live"]))
        self.assertEqual(len(expected), 12)
        empty_line = strings.text("canvas.log_empty")
        for size in self.SIZES:
            with self.subTest(size=size):
                async with self.shell(size=size) as pilot:
                    await self.loaded(pilot)
                    pane = self.pane()
                    # I7: below 100 columns the screen is narrow (the chat alone at start), so show the canvas —
                    # the first [→] leaves «Conversation» for «Scheme» — before the pane geometry below is read.
                    if self.main().narrow:
                        await pilot.press("right")
                        await pilot.pause()
                    # A1: exactly the two canvas tabs, no Journal tab and no Journal pane body (I7 adds the narrow
                    # strip's «Conversation» label in front of them)
                    labels = ["Scheme", "Plan"]
                    if self.main().narrow:
                        labels = [strings.text("pane.chat")] + labels
                    self.assertEqual(self.labels(), labels)
                    self.assertEqual(self.tab(), self.ui.TAB_LIVE)  # a live attempt opens «Scheme»
                    self.assertEqual(len(self.app.query("#journal-pane")), 0)
                    self.assertEqual(len(self.app.query("#journal")), 0)
                    self.assertFalse(hasattr(self.ui, "TAB_JOURNAL"))
                    self.assertFalse(hasattr(self.ui, "TAB_JOURNAL_TITLE"))
                    # A1: the pane is under the canvas — whichever tab is active
                    for shown in (self.ui.TAB_LIVE, self.ui.TAB_PLAN):
                        self.main().show_tab(shown)
                        await pilot.pause()
                        self.assertEqual(self.tab(), shown)
                        self.assertEqual(pane.border_title, strings.text("pane.activity"))
                        self.assertGreater(pane.region.y, self.canvas().region.y)
                        self.assertGreater(pane.region.height, 0)
                        self.assertGreater(pane.region.width, 0)
                        self.assertIn(strings.text("pane.activity"), screen_text(self.app))
                    self.main().show_tab(self.ui.TAB_PLAN)
                    await pilot.pause()
                    # A2: the newest lines that fit, oldest first; the older lines are dropped
                    rows = pane.size.height
                    self.assertGreaterEqual(rows, 1)
                    self.assertLess(rows, len(expected))  # the journal overflows the pane at both sizes
                    self.assertEqual(pane.render().plain, "\n".join(expected[-rows:]))
                    self.assertNotIn(expected[0], pane.render().plain)
                    # A3: the measured silence names the last line and reads as «3:07»; no flow means no subtitle
                    self.app.snapshot = replace(self.app.snapshot, flow=flow(187))
                    self.app.changed()
                    await pilot.pause()
                    self.assertEqual(pane.border_subtitle,
                                     strings.text("live.last_event", what=clip(expected[-1], 40), m="3:07"))
                    self.assertIn("3:07", pane.border_subtitle)
                    self.app.snapshot = replace(self.app.snapshot, flow=None)
                    self.app.changed()
                    await pilot.pause()
                    self.assertEqual(pane.border_subtitle, "")
                    # A2: with no stored entry the pane shows the widget's own empty line
                    self.app.snapshot = replace(self.app.snapshot, journal=())
                    self.app.changed()
                    await pilot.pause()
                    self.assertEqual(pane.render().plain, empty_line)
                    self.assertEqual(pane.border_subtitle, "")  # no lines: nothing for the subtitle to name

    async def test_a4_a5_a_new_journal_line_reaches_the_pane_on_the_plan_tab_and_only_the_pair_cycles(self):
        """A4+A5 at 120x40 through the real shell: a snapshot with one more journal line repaints the pane while the
        «Plan» tab is active; `←`/`→` cycle only «Scheme» <-> «Plan», the Journal tab is unreachable by any key, click
        or action, and neither the key bar, the help, the catalog nor `docs/USER_FLOW.md` names it any more."""
        self.approve(running=True)
        record = self.seed_journal([("2026-10-15T09:00:00Z", "T1: реализация")])
        expected = list(Delivery.journal_lines(record["live"]))
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            pane = self.pane()
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)  # a live attempt opens «Scheme»
            # A5: ←→ cycle the two tabs, from the chat input and from the plan pane
            for key, shown in (("right", self.ui.TAB_PLAN), ("right", self.ui.TAB_LIVE),
                               ("left", self.ui.TAB_PLAN), ("left", self.ui.TAB_LIVE)):
                await pilot.press(key)
                await pilot.pause()
                self.assertEqual(self.tab(), shown, key)
                self.assertIn(self.tab(), (self.ui.TAB_LIVE, self.ui.TAB_PLAN))
            # A5: no key reaches a Journal tab; the old function / alt keys stay unbound
            for key in ("f2", "f3", "f4", "alt+1", "alt+2", "alt+3"):
                self.assertNotIn(key, self.app.active_bindings, key)
                await pilot.press(key)
                await pilot.pause()
                self.assertIn(self.tab(), (self.ui.TAB_LIVE, self.ui.TAB_PLAN))
            from textual.widgets._tabs import Tab
            self.assertEqual(len(list(self.app.query(Tab))), 2)  # nothing to click but the two labels
            self.assertFalse(any(name.startswith("action_") and "journal" in name.lower()
                                 for name in dir(self.main())))
            # A5: the key bar and the main help carry the arrow segment and no Journal
            bar = screen_lines(self.app)[-1]
            self.assertIn("←→ tabs", bar)
            self.assertNotIn("Journal", bar)
            await self.command(pilot, "/help")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "HelpScreen")
            help_body = str(self.app.screen.query_one("#help-body").content)
            self.assertIn("tabs", help_body)
            self.assertNotIn("Journal", help_body)
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            # A5: the catalog has no Journal screen or action, and USER_FLOW names the pane, not a tab
            self.assertTrue(all("Journal" not in screen.title for screen in catalog.SCREENS.values()))
            self.assertTrue(all("Journal" not in action.label for action in catalog.ACTIONS.values()))
            doc = (Path(__file__).resolve().parents[1] / "docs" / "USER_FLOW.md").read_text(encoding="utf-8")
            self.assertIn("What's happening", doc)
            self.assertNotIn("«Journal»", doc)
            self.assertNotIn("Plan  Journal", doc)  # the wireframe's tab strip
            self.assertNotIn("-> «Journal» ->", doc)  # the old cycle string
            # A4: a new journal line repaints the pane while «Plan» is active, and the tab does not move
            self.main().show_tab(self.ui.TAB_PLAN)
            await pilot.pause()
            self.assertEqual(self.tab(), self.ui.TAB_PLAN)
            self.assertIn(expected[0], pane.render().plain)
            await self.append_journal(pilot, "2026-10-15T09:00:05Z", "T1: приёмка")
            self.app.request_refresh()
            await self.until(pilot, lambda: "T1: приёмка" in pane.render().plain)
            self.assertEqual(self.tab(), self.ui.TAB_PLAN)
            new_line = Delivery.journal_lines({"journal": [{"at": "2026-10-15T09:00:05Z",
                                                           "text": "T1: приёмка"}]})[0]
            self.assertEqual(pane.render().plain, "\n".join(expected + [new_line]))  # oldest first, the new line last


if __name__ == "__main__":
    unittest.main()
