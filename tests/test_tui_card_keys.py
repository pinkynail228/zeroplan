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
- D3 (S6): the keyed card is the one ←→ move, only while the chat input has the focus and is empty and the card has
  two or more buttons; the placeholder names ←→ for such a card (`chat.placeholder_card_row`) and ↑↓ alone for a card
  with one button. Old tests that pressed ←→ over an open plan card now press Tab first (the pane's own arrows).
- D3b (critic rel083): an arrow that switched the tab keeps ←→ on the tabs while the input stays empty, though the
  switch hands the focus back to the input; typing, `Tab`, Enter, Esc or a new keyed card end it. Only the wide layout
  is covered (the narrow cycle is out of the task); Esc over a shown file tab would close it, so the Esc case runs on
  «Now», where it only cancels the (absent) turn.
- The placeholder follows the input's emptiness as well as the card: with text typed it is `chat.placeholder` (it is
  not drawn then anyway).
"""

import dataclasses
import unittest

from terminal_planner.tui import strings
from test_tui_chat import ChatShell, HAVE_TEXTUAL, TEXTUAL_REASON

if HAVE_TEXTUAL:
    from terminal_planner.tui import cards

SHOWN = strings.text("chat.placeholder_card_row")


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
            # D3 K1/K3: on the empty input ←→ move the plan card's choice (wrapping) and the tab stays; the hint names ←→
            tab = screen.query_one("#right").active
            self.assertIn("←→", field.placeholder)
            await pilot.press("right")
            self.assertEqual(self.selected(newest), [plan.buttons[1][0]])
            await pilot.press("right")
            self.assertEqual(self.selected(newest), [plan.buttons[0][0]])
            await pilot.press("left")
            self.assertEqual((self.selected(newest), screen.query_one("#right").active), ([plan.buttons[1][0]], tab))
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(ran[-1], ("/decline", "", "plan:1"))  # «нет, доработать», as a click on it would
            # D3 K2: a card with one button leaves ←→ to the tabs (and says ↑↓ only)
            one = cards.plan_card("plan:2", "12:01", "1 этап", "2 задачи")
            screen.show_card(dataclasses.replace(one, buttons=one.buttons[:1]))
            await pilot.pause()
            self.assertEqual(field.placeholder, strings.text("chat.placeholder_card"))
            await pilot.press("right")
            self.assertNotEqual(screen.query_one("#right").active, tab)
            await pilot.press("left")
            screen.drop_card("plan:2")
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

    async def test_d3b_arrows_keep_cycling_tabs_until_the_owner_does_something_else(self):
        async with self.shell(size=(140, 40)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await pilot.pause()
            screen, field = self.app.screen, self.query("#input")
            screen.run_command = lambda name, argument="", key=None: True
            plan = cards.draft_card("draft:a", "12:01")  # a plan card is dropped by the next render of its source
            screen.show_card(plan)
            screen.add_view_tab("a", "a", key="a")
            screen.add_view_tab("b", "b", key="b")
            await pilot.pause()
            key, right = "draft:a", screen.query_one("#right")
            first, second = screen.view_tabs

            async def cycled():
                """Tab, →, →, →: the first arrow hands the focus back to the input; the next ones still switch tabs."""
                await pilot.press("tab")
                active = []
                for _ in range(3):
                    await pilot.press("right")
                    active.append(right.active)
                self.assertEqual(active, [first, second, "tab-live"])
                self.assertEqual(self.selected(screen.card_widgets[key]), [plan.buttons[0][0]])
                self.assertIs(self.app.focused, field)

            await cycled()  # A1
            await pilot.press("tab", "tab")  # A2: Tab ends it — the pane, then the input again
            await pilot.press("right")
            self.assertEqual(self.selected(screen.card_widgets[key]), [plan.buttons[1][0]])
            await pilot.press("left")
            for end in ("typing", "enter", "escape", "card"):
                await cycled()
                if end == "typing":
                    field.value = "x"
                    field.value = ""
                elif end == "card":
                    other = cards.draft_card("draft:b", "12:02")
                    screen.show_card(other)
                    key, plan = "draft:b", other
                else:
                    await pilot.press(end)
                await pilot.pause()
                active = right.active
                await pilot.press("right")
                self.assertEqual((self.selected(screen.card_widgets[key]), right.active), ([plan.buttons[1][0]], active), end)
                await pilot.press("left")

    async def d3c_cycle(self, between):
        """d3c regression. A1: the plan card re-rendered with the same key (a new widget) keeps the arrows' tab cycle.
        A2: another keyed card that comes and goes ends it for good, so → moves the card's choice again.
        Interpretation: «closed» is the card taken off (`unmount_card`), the same sync as a card going away."""
        async with self.shell(size=(140, 40)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await pilot.pause()
            screen = self.app.screen
            right = screen.query_one("#right")
            screen.run_command = lambda name, argument="", key=None: True
            plan = cards.draft_card("draft:a", "12:01")
            screen.show_card(plan)
            screen.add_view_tab("a", "a", key="a")
            await pilot.pause()
            await pilot.press("tab", "right")
            self.assertEqual(right.active, screen.view_tabs[0])
            await between(screen, plan)
            await pilot.pause()
            return screen, right, plan, await self.arrow(pilot, screen, right)

    async def arrow(self, pilot, screen, right):
        before = right.active
        await pilot.press("right")
        return before, right.active, self.selected(screen.card_widgets["draft:a"])

    async def test_d3c_a_refresh_of_the_same_card_keeps_the_cycle(self):
        async def refresh(screen, plan):
            screen.show_card(cards.draft_card("draft:a", "12:02"))  # same key, new widget

        screen, right, plan, (before, after, chosen) = await self.d3c_cycle(refresh)
        self.assertNotEqual(after, before)
        self.assertEqual(chosen, [plan.buttons[0][0]])

    async def test_d3c_another_keyed_card_ends_the_cycle_for_good(self):
        async def other(screen, plan):
            screen.show_card(cards.draft_card("draft:b", "12:02"))
            screen.sync_cards()
            screen.unmount_card("draft:b")
            screen.sync_cards()

        screen, right, plan, (before, after, chosen) = await self.d3c_cycle(other)
        self.assertEqual(after, before)
        self.assertEqual(chosen, [plan.buttons[1][0]])


if __name__ == "__main__":
    unittest.main()
