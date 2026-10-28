"""E1 (0.6.3 V4): an empty chat explains itself and offers three example goals.

One invariant test through the real shell, at 80x24 and at 140x40, covers C1-C4: the intro in the scroll (C1, the
generic examples of C2), the arrows picking an example and Enter sending it (C3), the arrows recalling the lines
again once the chat has an entry and the intro back after `/new` (C4). The `chat.greeting` id is gone (C1).

Interpretations (the task leaves these open; reviewers do not see the worker's summary):
- `/new` leaves one `reset` entry in the shown history (the divider the pane keeps since O4), so "the shown history is
  empty again" is read as "holds no entry but a `reset` one": the intro shows below that divider line and
  `test_tui_chat.py` keeps seeing the reset entry's text.
- Up on a fresh intro (input empty, `❯` on the first example) wraps to the last example, Down goes to the second; an
  input that holds an example (typed or picked) starts the move from that example.
- The selection returns to the first example whenever the intro is taken off, so it is on the first after `/new`.
"""

import unittest

from terminal_planner.tui import strings
from test_tui_chat import ChatShell, HAVE_TEXTUAL, OPENING, REPLY, TEXTUAL_REASON, chat_band

SILENT = OPENING + [{"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 0}}]

EXAMPLES = ("chat.example_1", "chat.example_2", "chat.example_3")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatEmptyTests(ChatShell):
    def examples(self):
        return [strings.text(example) for example in EXAMPLES]

    def marked(self):
        """The example the intro marks with `❯` (None: no example is marked), and the marks of the other rows."""
        rows = list(self.app.query(".intro .examples")[0].content.plain.split("\n"))
        picked = [row[2:] for row in rows if row.startswith("❯ ")]
        self.assertEqual([row[:2] for row in rows if not row.startswith("❯ ")], ["› "] * (len(rows) - len(picked)))
        return picked[0] if len(picked) == 1 else None

    async def drive(self, size):
        # the sent example gets a reply; `/new`'s handoff turn says nothing and its warm-up turn is still running (its
        # reply would be an entry of the new conversation)
        self.fixture.script([{"lines": REPLY}, {"lines": SILENT}, {"lines": OPENING, "hang": 30}])
        first, second, third = self.examples()
        async with self.shell(size=size) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await pilot.pause()
            app, field = self.app, self.query("#input")
            # C1/C2: one centred intro, no entry; every text from the catalog; `❯` on the first example
            self.assertNotIn("chat.greeting", strings.CATALOG)
            self.assertEqual(len(app.query("#chat .msg")), 0)
            self.assertEqual(len(app.query("#chat .intro")), 1)
            band = chat_band(app)
            for text in (strings.text("chat.intro"), strings.text("chat.intro_caption"), first, second, third,
                         strings.text("chat.intro_hint")):
                self.assertIn(text, band)
            self.assertEqual(self.marked(), first)
            self.assertIn("› " + third, band)
            # a card is no empty chat: the intro leaves while a card is in the scroll and returns when it is gone
            from terminal_planner.tui import cards
            app.screen.show_card(cards.CardSpec("k", "title", "text", (), None, "", None, False))
            await pilot.pause()
            self.assertEqual(len(app.query("#chat .intro")), 0)
            app.screen.drop_card("k")
            await pilot.pause()
            self.assertEqual((len(app.query("#chat .intro")), self.marked()), (1, first))
            # C3: the arrows pick (wrapping) into the input, the cursor at its end
            await pilot.press("down")
            self.assertEqual((field.value, self.marked()), (second, second))
            self.assertEqual(field.cursor_position, len(second))
            await pilot.press("down", "down")
            self.assertEqual((field.value, self.marked()), (first, first))
            await pilot.press("up")
            self.assertEqual((field.value, self.marked()), (third, third))
            await pilot.press("down", "down")
            self.assertEqual(field.value, second)
            await pilot.press("enter")
            await self.until(pilot, lambda: app.chat.state.entries)
            await self.chat_done(pilot)
            await pilot.pause()
            owners = [entry.text for entry in app.chat.state.entries if entry.role == "owner"]
            self.assertEqual(owners, [second])
            self.assertEqual(len(app.query("#chat .intro")), 0)
            self.assertEqual(field.value, "")
            # the arrows keep O3 once the chat has an entry: Up recalls the sent line
            await pilot.press("up")
            self.assertEqual(field.value, second)
            await pilot.press("down")
            # C4: `/new` empties the shown history again; the intro returns with `❯` on the first, and the arrows
            # pick examples although recall holds `/new`
            await self.command(pilot, "/new")
            await self.until(pilot, lambda: [e.role for e in app.chat.state.entries] == ["reset"])
            await self.until(pilot, lambda: len(app.query("#chat .intro")) == 1)
            await pilot.pause()
            self.assertEqual(self.marked(), first)
            self.assertIn(first, chat_band(app))
            await pilot.press("down")
            self.assertEqual((field.value, self.marked()), (second, second))

    async def test_c1_c4_at_80x24(self):
        await self.drive((80, 24))

    async def test_c1_c4_at_140x40(self):
        await self.drive((140, 40))


if __name__ == "__main__":
    unittest.main()
