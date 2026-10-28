"""D2 (0.6.3 newcomer defect 2): the open card is answered by keys, and the keys are shown at 80x24.

One whole-app walk through the real shell, at 80x24 and at 140x40, covers K1-K4 with the draft, plan and merge cards:
the newest open card draws one selected choice in reverse, starting on its first button (K1); ↑↓ move it (wrapping)
and Enter on the empty input presses it through the card's own `Card.Chosen` path, the same `run_command` call a click
makes, while text in the input keeps today's send (K2); the input's placeholder is the catalog's key line while a card
is open and `chat.placeholder` otherwise, the card's hint row staying hidden at 80x24 (K3); Enter with no open card
still says `architect.empty_message` and sends nothing (K4).

Interpretations (the task leaves these open; reviewers do not see the worker's summary):
- "Newest open card" is the last open card, in the order the screen keeps its cards (history order), that has
  buttons; an older open card draws no selection and is not reached by the keys until the newer one is closed.
- The selection of a card is kept when the same key is refreshed in place and reset (first button) for a new card.
- The placeholder follows the input's emptiness as well as the card: with text typed it is `chat.placeholder` (it is
  not drawn then anyway).
"""

import unittest

from terminal_planner.tui import strings
from test_tui_chat import ChatShell, HAVE_TEXTUAL, TEXTUAL_REASON

if HAVE_TEXTUAL:
    from terminal_planner.tui import cards

SHOWN = strings.text("chat.placeholder_card")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class CardKeysTests(ChatShell):
    def selected(self, card):
        """The labels of the card's buttons drawn selected (reverse)."""
        return [str(button.label) for button in card.query("Button") if button.has_class("selected")]

    def reversed_labels(self, labels):
        """Which of `labels` are drawn in reverse in the rendered screen (what the owner sees)."""
        drawn = {segment.text.strip() for strip in self.app.screen._compositor.render_strips() for segment in strip
                 if segment.style is not None and segment.style.reverse}
        return [label for label in labels if label in drawn]

    async def drive(self, size):
        async with self.shell(size=size) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await pilot.pause()
            app, screen, field = self.app, self.app.screen, self.query("#input")
            field.focus()
            ran = []
            screen.run_command = lambda name, argument="", key=None: ran.append((name, argument, key)) or True
            # K4 + K3: no open card -> the plain placeholder; Enter on the empty input says the empty-message note
            self.assertEqual(field.placeholder, strings.text("chat.placeholder"))
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(ran, [])
            self.assertIn("The empty message to the architect was not sent.", "\n".join(
                line.text for line in app.screen._compositor.render_strips()))
            self.assertEqual(list(app.chat.state.entries), [])
            # K1 + K3: the draft card opens; the first button is selected, the keys are in the placeholder
            draft = cards.draft_card("draft:d", "12:00")
            screen.show_card(draft)
            await pilot.pause()
            shown = screen.card_widgets["draft:d"]
            self.assertEqual(self.selected(shown), [draft.buttons[0][0]])
            self.assertEqual(field.placeholder, SHOWN)
            self.assertEqual(self.reversed_labels([label for label, _ in draft.buttons]), [draft.buttons[0][0]])
            self.assertEqual(shown.query(".card-hint")[0].display, size[0] > 100)  # hidden at 80x24 (A1)
            # K2: Down moves to «нет» and wraps; Enter presses it through Card.Chosen -> run_command
            await pilot.press("down")
            self.assertEqual(self.selected(shown), [draft.buttons[1][0]])
            await pilot.press("down")
            self.assertEqual(self.selected(shown), [draft.buttons[0][0]])
            await pilot.press("up")
            self.assertEqual(self.selected(shown), [draft.buttons[1][0]])
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(ran, [("/decline", "", "draft:d")])
            # a click on the same button is the very same call
            shown.query("Button")[1].press()
            await pilot.pause()
            self.assertEqual(ran[-1], ran[0])
            # the newest open card owns the keys: the plan card opens under the draft; the draft draws none
            plan = cards.plan_card("plan:1", "12:01", "3 этапа", "5 задач")
            screen.show_card(plan)
            await pilot.pause()
            newest = screen.card_widgets["plan:1"]
            self.assertEqual((self.selected(newest), self.selected(shown)), ([plan.buttons[0][0]], []))
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(ran[-1], ("/decline", "", "plan:1"))  # «нет, доработать», as a click on it would
            # text in the input keeps today's send and the arrows' recall; the placeholder is the plain one
            field.value = "абв"
            await pilot.pause()
            self.assertEqual(field.placeholder, strings.text("chat.placeholder"))
            count = len(ran)
            field.value = ""
            await pilot.pause()
            self.assertEqual(field.placeholder, SHOWN)
            # the merge card: closing the newer cards hands the keys on; closing the last restores the placeholder
            merge = cards.merge_card("merge:1", "12:02", "этап 1", "3", "3")
            screen.show_card(merge)
            screen.drop_card("plan:1")
            screen.drop_card("draft:d")
            await pilot.pause()
            self.assertEqual(self.selected(screen.card_widgets["merge:1"]), [merge.buttons[0][0]])
            await pilot.press("down", "enter")
            await pilot.pause()
            self.assertEqual(ran[count:], [("/diff", "", "merge:1")])
            screen.close_card("merge:1", strings.text("card.plan_done", time="12:03"))
            await pilot.pause()
            self.assertEqual(field.placeholder, strings.text("chat.placeholder"))
            self.assertEqual(self.selected(screen.card_widgets["merge:1"]), [])
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(len(ran), count + 1)  # no open card: Enter is the empty-message path again

    async def test_k1_k4_at_80x24(self):
        await self.drive((80, 24))

    async def test_k1_k4_at_140x40(self):
        await self.drive((140, 40))


if __name__ == "__main__":
    unittest.main()
