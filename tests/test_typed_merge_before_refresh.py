# tests/test_typed_merge_before_refresh.py
"""A merge has landed and its card is the receipt, but the refresh that moves the row has not answered: the screen
still reads the row as `awaiting_merge`, so the palette lets a typed `/merge` through. That line must not open the
merged attempt's end-of-run screen. The race is held open by withholding the refresh, never by load or sleeps."""
import unittest
from unittest.mock import patch

import test_tui_merge_card as mc


def withheld_refresh(controller, done):
    """`Controller.refresh` whose answer has not arrived: the app's snapshot stays as it was."""
    return False


@unittest.skipUnless(mc.HAVE, mc.MISSING_REASON)
class TypedMergeBeforeRefresh(mc.MilestoneShell):
    """The merge card's helpers, borrowed without its own tests."""
    main = mc.MergeCardShell.main
    card = mc.MergeCardShell.card
    counted_card = mc.MergeCardShell.counted_card
    counting_merge = staticmethod(mc.MergeCardShell.counting_merge)

    async def send(self, pilot, line):
        """Enter in the real chat input (the card's button may hold the focus)."""
        field = self.main().query_one("#input")
        field.focus()
        field.value = line
        await pilot.pause()
        await pilot.press("enter")

    async def finished_card_key(self, pilot):
        """M1 run to its end: the key of its open merge card."""
        await self.loaded(pilot)
        await self.begin_run(pilot)
        return (await self.counted_card(pilot)).spec.key

    async def test_a_typed_merge_before_the_refresh_answers_opens_no_end_screen(self):
        calls = []
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            key = await self.finished_card_key(pilot)
            with patch.object(mc.Controller, "merge", self.counting_merge(calls)), \
                    patch.object(mc.Controller, "refresh", withheld_refresh):
                await self.send(pilot, "/merge")
                await self.until(pilot, lambda: self.main().card_specs[key].done)
                self.assertEqual(self.app.snapshot.row("M1").state, "awaiting_merge")  # the screen is still behind
                await self.send(pilot, "/merge")
                note = mc.strings.text("note.not_now", name="/merge")
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "RunScreen" or note in self.flat())
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")
                self.assertEqual(len(calls), 1)
        self.assertEqual(self.stored()["runs"][0]["delivery"], "integrated")

    async def test_a_typed_merge_after_merge_later_still_opens_the_end_screen(self):
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            key = await self.finished_card_key(pilot)
            self.main().run_command("/merge", "later", key)
            await self.until(pilot, lambda: self.main().card_specs[key].done)
            await self.send(pilot, "/merge")
            await self.run_button(pilot, "merge")
            self.assertEqual(type(self.app.screen).__name__, "RunScreen")


if __name__ == "__main__":
    unittest.main()
