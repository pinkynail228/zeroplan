"""N1 (0.6.3 newcomer defects 4, 5, 8): one status line, a plain thinking preview, one draft label.

One smoke test per criterion, each a pure call (no whole-app run): B1 through `CardHost.action_plan` and
`MainScreen.render_status` on stubs, B2 through `thinking_row`, B3 through `chat.entry_blocks`, B4 on the text of
`DRAFT_RULES`.

Interpretations (the task leaves these open):
- B1: the note is cleared at the top of `action_plan`, so a refusal that follows sets its own note; while the
  thinking row shows the note is only left out of the status text (not cleared) and is back when the turn ends.
- B2: the markers are dropped after L-2 has escaped the line, per line; a leading `#`s run, `- ` or `* ` is cut.
- B3: only the label of the block's own kind goes (`goal draft` before a goal block, `answer draft` before an
  answer block), case-insensitive, with optional `**`/`__`, colon and blank lines after it; `Answer draft M1:`
  and any other line stay. The 0.7.x Russian labels (`LEGACY_DRAFT_KINDS`: stored replies keep them) are cut the
  same way, and the Russian reply text in the legacy cases is input, so it stays Russian.
- B4: "copies a draft" is the old wording the preamble must no longer hold.
"""

from types import SimpleNamespace
import unittest
import unittest.mock

from terminal_planner import architect
from terminal_planner.tui import chat as chat_module
from tui_support import HAVE_TEXTUAL

if HAVE_TEXTUAL:
    from terminal_planner.tui import app as app_module
    from terminal_planner.tui.card_host import CardHost

TEXTUAL_REASON = "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed"
NOTE = "The planner is unavailable in this session."


def running(live=""):
    return chat_module.ChatState(phase="ready", running=True, elapsed=7.0, live=live)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class StatusNoteTests(unittest.TestCase):
    def test_b1_a_card_plan_clears_the_note(self):
        sent = []
        app = SimpleNamespace(chat_note=NOTE, send_unsent_plan=lambda: sent.append(True))
        host = SimpleNamespace(app=app, draft_card_ref=lambda key: None)
        CardHost.action_plan(host, "", None)
        self.assertEqual((app.chat_note, sent), ("", [True]))
        app.chat_note = NOTE
        host.status_note = lambda line: setattr(app, "chat_note", line)
        CardHost.action_plan(host, "", "gone-card")  # a button of a card that is gone: its own refusal replaces it
        self.assertIn("/plan", app.chat_note)
        self.assertNotEqual(app.chat_note, NOTE)

    def test_b1_the_note_is_not_drawn_while_the_thinking_row_shows(self):
        def status(state):
            app = SimpleNamespace(chat=SimpleNamespace(state=state), chat_note=NOTE, chat_outcome=None, run_watch="",
                                  run_note="", planner_pane=lambda: False)
            written = []
            pane = SimpleNamespace(content_region=SimpleNamespace(width=80), size=SimpleNamespace(height=40))
            screen = SimpleNamespace(app=app, status_text=None,
                                     query_one=lambda selector, *kind: pane if selector == "#chat-pane"
                                     else SimpleNamespace(update=lambda text: written.append(text.plain)))
            with unittest.mock.patch.object(app_module, "chat_outcome", lambda app: ""), \
                    unittest.mock.patch.object(app_module, "chat_refusal", lambda app: ""):
                app_module.MainScreen.render_status(screen)
            return written[-1]

        self.assertIn("The architect is thinking", status(running("читаю план")))
        self.assertNotIn(NOTE, status(running("читаю план")))
        idle = status(chat_module.ChatState(phase="ready", running=False))
        self.assertEqual(idle, NOTE)  # the note was only held back, never cleared


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class PreviewTests(unittest.TestCase):
    def test_b2_the_thinking_preview_drops_markdown_markers_and_keeps_the_escape(self):
        def live(text):
            return app_module.thinking_row(running(text)).split(" · ", 1)[1]

        self.assertEqual(live("## **Смотрю** `app.py`"), "Смотрю app.py")
        self.assertEqual(live("__a__ b"), "a b")
        self.assertEqual(live("- первый\n* второй"), "первый второй")
        self.assertEqual(live("2 * 3 и a-b"), "2 * 3 и a-b")  # only a leading marker goes
        self.assertEqual(live("`x`\t**y**\x1b[31m"), "x\\ty")  # L-2: the tab is escaped, the sequence is out
        self.assertEqual(live("a\x1b]se`cret"), "a\\x1b]secret")  # an open sequence stays escaped text


class DraftLabelTests(unittest.TestCase):
    def blocks(self, text, kind, body, milestone=None):
        draft = {"kind": kind, "text": body, "identity": "no plan"}
        if milestone:
            draft["milestone"] = milestone
        fence = "```zplan-goal" if kind == "goal" else "```zplan-answer " + milestone
        row = {"role": "architect", "text": text + "\n" + fence + "\n" + body + "\n```", "status": "completed",
               "drafts": [draft]}
        return chat_module.entry_blocks(chat_module.entries_of([row])[0])

    def test_b3_a_line_that_is_only_the_draft_label_is_not_drawn(self):
        for label in ("Goal draft:", "**Goal draft:**", "goal draft", "__Goal draft__:"):
            self.assertEqual(self.blocks("Here.\n" + label, "goal", "X"),
                             [("text", "Here."), ("draft", "↳ goal draft: X")], label)
        for label in ("Answer draft:", "**Answer draft:**", "answer draft"):
            self.assertEqual(self.blocks("Here.\n" + label + "\n", "answer", "Yes", "M1"),
                             [("text", "Here."), ("draft", "↳ answer draft M1: Yes")], label)
        self.assertEqual(self.blocks("Goal draft:", "goal", "X"), [("draft", "↳ goal draft: X")])
        for other in ("Goal draft below:", "Answer draft:", "Here is the goal draft:"):  # not this block's own label
            self.assertEqual(self.blocks("Here.\n" + other, "goal", "X"),
                             [("text", "Here.\n" + other), ("draft", "↳ goal draft: X")], other)
        self.assertEqual(self.blocks("Goal draft:\nTotal.", "goal", "X")[0], ("text", "Goal draft:\nTotal."))

    def test_u3_a_stored_0_7_x_reply_with_the_russian_label_is_cut_as_before(self):
        """U3: the Russian draft labels of a stored 0.7.x reply are still cut (`chat.LEGACY_DRAFT_KINDS`)."""
        for label in ("Черновик цели:", "**Черновик цели:**", "черновик цели", "__Черновик цели__:"):
            self.assertEqual(self.blocks("Вот.\n" + label, "goal", "X"),
                             [("text", "Вот."), ("draft", "↳ goal draft: X")], label)
        for label in ("Черновик ответа:", "**Черновик ответа:**", "черновик ответа"):
            self.assertEqual(self.blocks("Вот.\n" + label + "\n", "answer", "Да", "M1"),
                             [("text", "Вот."), ("draft", "↳ answer draft M1: Да")], label)
        for other in ("Черновик цели ниже:", "Черновик ответа:", "Вот черновик цели:"):  # not this block's own label
            self.assertEqual(self.blocks("Вот.\n" + other, "goal", "X"),
                             [("text", "Вот.\n" + other), ("draft", "↳ goal draft: X")], other)
        self.assertEqual(self.blocks("Черновик цели:\nИтог.", "goal", "X")[0], ("text", "Черновик цели:\nИтог."))


class DraftRulesTests(unittest.TestCase):
    def test_b4_the_rules_say_zplan_shows_a_card_and_nothing_is_copied(self):
        text = " ".join(architect.DRAFT_RULES)
        self.assertNotIn("copies a draft", text)
        self.assertIn("card with buttons", text)
        self.assertIn("never ask the owner to copy or send a draft", text.replace("\n", " "))


if __name__ == "__main__":
    unittest.main()
