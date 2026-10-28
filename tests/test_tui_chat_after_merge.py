"""D3: the chat keeps its latest items in view after `/merge` (a regression for the newcomer check's defects 3 and 11).

The cause the first test reproduces: `#chat` is the row above `#status` and the prompt, and `#status` grows while the
architect's turn runs (the `The architect is thinking…` row joins the merge note), so the scroll shrinks by a row or more
while its `scroll_y` stays where it was. The entries are all still mounted, but the view is no longer at the end: the
newest entry and the closed card's done line sit below the visible region until the reply reloads the history. A
resize moved the same way (`max_scroll_y` follows the pane, `scroll_y` does not). The fix anchors `#chat` to its end
(`Widget.anchor`, `MainScreen.on_mount`): a view at the end stays at the end through any layout change, and an owner
who scrolled away releases the anchor and keeps the position.

Interpretations (the worker's summary never reaches the reviewers, so they are recorded here):

- "the visible region" is read off the widgets: an item is in view when its `region` lies inside `#chat`'s own
  region (the scroll's rows), and "at the bottom" is the scroll's own `scroll_offset.y == max_scroll_y`.
- The typed `/merge` is a command, not a transcript line (the owner's input is not stored), so the "owner's `/merge`
  line" of the brief's example does not exist in this build; the items that must stay are the entries and the closed
  merge card.
- The architect's turn after the merge is an event turn: the injected feed port (`test_tui_chat.Port`) carries one
  wake event and the scripted codex holds the turn open on a gate, so no timer decides the test.
- Two whole-app tests: the first drives the real `/merge` pipeline at 80x24 (C1-C3); the second settles the merge
  card through `merge_settled` (the engine verdict is the only thing it replaces) at 80x24 and 140x40, with the view
  at the bottom and scrolled away (C2-C4).
"""

import unittest
from pathlib import Path

import tui_support  # noqa: F401  (its import joins the offline wheelhouse to sys.path before the guarded imports)
from tui_support import HAVE_TEXTUAL

from test_tui_chat import OPENING, PARTIAL, REPLY, Port, event
from test_tui_chat_scroll import TEXTUAL_REASON, ChatScroll, StreamFixture

if HAVE_TEXTUAL:
    from terminal_planner.tui import cards
    from terminal_planner.tui.controller import Outcome

SIZES = [(80, 24), (100, 30), (140, 40)]
MERGE_KEY = "merge:r1:M1:1"


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatAfterMergeTests(ChatScroll):

    def setUp(self):
        super().setUp()
        self.fixture = StreamFixture(self.root, self.project)
        self.gate = str(self.root / "turn-gate")
        self.fixture.script([{"lines": PARTIAL, "gates": [{"file": self.gate, "lines": REPLY}]}])

    def in_view(self, widget):
        """The widget's rows all lie inside the visible rows of `#chat`."""
        region, view = widget.region, self.scroll().region
        return region.height > 0 and region.y >= view.y and region.bottom <= view.bottom

    def newest_in_view(self, card):
        """The newest entry and the card (the done line when it is the closed receipt) are in view."""
        newest = self.main().chat_entry_widgets[-1]
        return self.in_view(newest) and self.in_view(card)

    def resize_path(self, start):
        """The sizes after `start`, in the cycle 80x24 -> 100x30 -> 140x40 -> 80x24 (back to where it began)."""
        index = SIZES.index(start)
        return [SIZES[(index + step) % len(SIZES)] for step in range(1, len(SIZES) + 1)]

    async def hold_turn(self, pilot):
        """The architect's event turn after the merge, held open on the gate: the status area grows a thinking row."""
        self.app.chat.feed = Port([event(1)], snapshot={})
        self.app.chat.notify()
        await self.until(pilot, lambda: self.app.chat.state.running, 10.0)
        await pilot.pause(0.5)

    async def release_turn(self, pilot):
        Path(self.gate).touch()
        await self.chat_done(pilot)
        await pilot.pause(0.5)

    async def test_the_real_merge_keeps_the_newest_items_in_view_through_the_turn_and_resizes(self):
        """C1-C3: 30 entries and the stage-done card at 80x24, the view at the bottom; the typed `/merge` settles
        (the card becomes its receipt), then the architect's turn runs. Every item shown before stays mounted, the
        newest entry and the receipt are inside the visible region and the view is at the end — while the turn runs
        (before the fix `scroll_y` stayed one row short of `max_scroll_y`: the receipt's row was cut), through the
        resize chain 80x24 -> 100x30 -> 140x40 -> 80x24, and after the reply."""
        self.approve(running=False)
        self.plain("g\ny\nl\nq\n")  # the stage done and waiting for its merge, made by the line UI
        store = self.seed_history(30)
        async with self.shell(size=(80, 24), store=store) as pilot:
            await self.start(pilot, 30)
            main = self.main()
            await self.until(pilot, lambda: MERGE_KEY in main.card_widgets and main.card_widgets[MERGE_KEY].region.height > 0)
            await self.until(pilot, self.at_bottom)
            shown = list(main.chat_entry_widgets)
            await self.say(pilot, "/merge")
            await self.until(pilot, lambda: main.card_specs[MERGE_KEY].done is not None)
            await pilot.pause(0.5)
            card = main.card_widgets[MERGE_KEY]
            await self.hold_turn(pilot)
            self.assertTrue(self.at_bottom(), (self.offset(), self.scroll().max_scroll_y))
            self.assertTrue(self.newest_in_view(card))
            self.assertEqual(main.chat_entry_widgets, shown)  # nothing shown before the merge was unmounted
            self.assertTrue(all(widget.parent is self.scroll() for widget in shown))
            for size in self.resize_path((80, 24)):
                await pilot.resize_terminal(*size)
                await pilot.pause(0.5)
                card = main.card_widgets[MERGE_KEY]
                self.assertTrue(self.at_bottom(), (size, self.offset(), self.scroll().max_scroll_y))
                self.assertTrue(self.newest_in_view(card), size)
            await self.release_turn(pilot)
            await self.until(pilot, lambda: len(main.chat_entry_widgets) > 30)
            await self.until(pilot, self.at_bottom)

    async def test_the_settled_merge_follows_the_bottom_and_leaves_a_scrolled_owner_alone(self):
        """C2-C4 at 80x24 and 140x40: the merge card is shown at the end of 40 entries and `merge_settled` closes it
        (the engine's `integrated` verdict), then a held event turn, then the resize chain. With the view at the
        bottom it stays there and the newest entry and the receipt are in view; with the owner scrolled up by a page
        (the scroll's own PgUp, up to the first entry) `scroll_y` is exactly what it was after the settle and the turn, and no resize pulls
        the view down."""
        for size in ((80, 24), (140, 40)):
            for scrolled in (False, True):
                with self.subTest(size=size, scrolled=scrolled):
                    Path(self.gate).unlink(missing_ok=True)
                    await self.walk(size, scrolled)

    async def walk(self, size, scrolled):
        store = self.seed_history(40)
        async with self.shell(size=size, store=store) as pilot:
            await self.start(pilot, 40)
            main = self.main()
            main.show_card(cards.merge_card(MERGE_KEY, "21:05", "M1", "1", "1"))
            await self.until(pilot, lambda: MERGE_KEY in main.card_widgets and main.card_widgets[MERGE_KEY].region.height > 0)
            await self.until(pilot, self.at_bottom)
            if scrolled:
                self.scroll().scroll_page_up(animate=False)
                await pilot.pause(0.3)
                above = self.offset()
                self.assertGreater(above, 0)
                self.assertFalse(self.at_bottom())
                while self.offset() > 0:                          # up to the top, where no resize can clamp it
                    self.scroll().scroll_page_up(animate=False)
                    await pilot.pause(0.1)
                above = self.offset()
            main.merge_settled(MERGE_KEY, "M1", Outcome("integrated", lines=("Влито: M1 → main.",)), None)
            await self.until(pilot, lambda: main.card_specs[MERGE_KEY].done is not None)
            await pilot.pause(0.5)
            await self.hold_turn(pilot)
            card = main.card_widgets[MERGE_KEY]
            if scrolled:
                self.assertEqual(self.offset(), above)           # neither the settle nor the turn moved it
            else:
                self.assertTrue(self.at_bottom(), (self.offset(), self.scroll().max_scroll_y))
                self.assertTrue(self.newest_in_view(card))
            for step in self.resize_path(size):
                await pilot.resize_terminal(*step)
                await pilot.pause(0.5)
                card = main.card_widgets[MERGE_KEY]
                if scrolled:
                    if self.scroll().max_scroll_y:  # a size that shows the whole conversation is at its end anyway
                        self.assertFalse(self.at_bottom(), step)    # a resize does not pull a scrolled owner down
                else:
                    self.assertTrue(self.at_bottom(), (step, self.offset(), self.scroll().max_scroll_y))
                    self.assertTrue(self.newest_in_view(card), step)
            if scrolled:
                self.assertGreater(self.scroll().max_scroll_y, 0, size)  # the last size had something to scroll...
                self.assertFalse(self.at_bottom())                      # ...and the owner is still not at its end
            await self.release_turn(pilot)


if __name__ == "__main__":
    unittest.main()
