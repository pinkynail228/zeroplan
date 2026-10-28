"""C2: an architect reply cannot smuggle controls or lose prose; the chat's worker start cannot race its wait.

S1-S2 render `app.Reply` (Rich Markdown) without an app; S3 drives the chat's unit harness with a patched
`Thread.start`; S4 is the old M1/M2 pins (HTML-like text, Rich markup, raw CSI/OSC, hyperlinks off) re-checked
on the same renderer.

Interpretations (the worker's summary never reaches the reviewers):
- «shows as L-2 shows that character typed raw» is read as: the rendered text equals the rendered text of the same
  reply with the decoded character typed in place (`plain_scan` escapes: `\\u202e`, `\\x1b`, ...).
- An image is drawn as its alt text in the place it stands in the paragraph (no glyph, no URL): Rich draws an image
  element ahead of the paragraph's words, so the token is made plain text before rendering.
- S3's interleave hook runs `wait` on a second thread while the first thread is inside `Thread.start` (a `wait` on
  the starting thread itself would wait for the guard it holds); with the shared guard the waiter joins the started
  turn, without it the waiter raised «cannot join thread before it is started».
"""

import io
import threading
import time
import unittest
from unittest.mock import patch

from tui_support import HAVE_TEXTUAL
import test_tui_chat as chat_tests
from test_tui_chat import TEXTUAL_REASON

if HAVE_TEXTUAL:
    from rich.console import Console

    from terminal_planner.tui import app as app_module
    from terminal_planner.tui.text import plain_lines

CONTROLS = ["\u202e", "\u200e", "\u200b", "\x1b", "\x9b"]


def drawn(markup):
    """The text a `Reply` draws, with its hyperlink styles (a Rich `Style.link`) collected beside it."""
    console = Console(width=80, record=True, force_terminal=False, file=io.StringIO())
    console.print(app_module.Reply(markup, code_theme="ansi_dark", inline_code_theme="ansi_dark", hyperlinks=False))
    segments = list(console.render(app_module.Reply(markup, hyperlinks=False)))
    links = [seg.style.link for seg in segments if seg.style is not None and seg.style.link]
    return console.export_text(), links


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ReplyEscapeTests(unittest.TestCase):
    def test_s1_an_entity_that_decodes_to_a_control_is_shown_as_the_raw_character_is(self):
        for char in CONTROLS:
            entity = "&#x%x;" % ord(char)
            for template in ("a %s b", "`a %s b`", "```\na %s b\n```", "# a %s b", "- a %s b", "[a %s b](http://x.invalid/)",
                             "![a %s b](http://x.invalid/i.png)", "*a %s b*", "> a %s b"):
                with self.subTest(char=ascii(char), template=template):
                    text, _ = drawn(template % entity)
                    for bad in CONTROLS:
                        self.assertNotIn(bad, text)
                    # an entity is decoded in prose only (a code span keeps it literal); markdown-it already turns
                    # an ESC or C1 entity into U+FFFD, so the raw comparison is for the bidi and zero-width ones
                    if char in "\u202e\u200e\u200b" and not template.startswith(("`", "```")):
                        raw, _ = drawn("\n".join(plain_lines(template % char)))
                        self.assertEqual(text, raw)

    def test_s1_the_named_example(self):
        text, _ = drawn("a &#x202e;b &lrm;c")
        self.assertNotIn("\u202e", text)
        self.assertNotIn("\u200e", text)
        self.assertIn("\\u202e", text)
        self.assertIn("\\u200e", text)

    def test_s2_an_image_keeps_its_paragraph_in_order_and_opens_no_link(self):
        text, links = drawn("before ![alt](https://example.invalid/i.png) after")
        words = text.split()
        self.assertEqual([w for w in words if w in ("before", "alt", "after")], ["before", "alt", "after"])
        self.assertEqual(links, [])
        self.assertNotIn("example.invalid", text)

    def test_s4_what_m1_and_m2_pinned_stays(self):
        # the reply reaches `Reply` after L-2, as `chat.entry_blocks` hands it over
        text, links = drawn("\n".join(plain_lines(
            "`Vec<String>` [b]x[/b] Vec<String> <!-- hi -->\n\n<div>x</div>\n\n\x1b[31mred \x1b]8;;http://a\x07link")))
        for kept in ("Vec<String>", "[b]x[/b]", "<!-- hi -->", "<div>x</div>"):
            self.assertIn(kept, text)
        self.assertNotIn("\x1b", text)
        self.assertEqual(links, [])
        _, links = drawn("[label](http://x.invalid/)")
        self.assertEqual(links, [])


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class StartWaitTests(unittest.TestCase):
    def test_s3_a_wait_between_creation_and_start_never_joins_an_unstarted_thread(self):
        case = chat_tests.ChatUnitTests("wait")
        case.setUp()
        self.addCleanup(case.doCleanups)
        release = case.root / "release"
        case.fixture.script([{"lines": [], "release": str(release), "release_timeout": 30}])
        gate = chat_tests.Deferred()
        chat = case.chat(hand_over=gate.hand_over, gate=gate)
        outcome = {}
        real_start = threading.Thread.start

        def waiter():
            try:
                started = time.monotonic()
                outcome["alive"] = not chat.wait(0.5)
                outcome["waited"] = time.monotonic() - started
            except RuntimeError as error:
                outcome["error"] = error

        def hooked(thread):
            if thread.name == "zplan-chat-turn" and "thread" not in outcome:
                helper = outcome["thread"] = threading.Thread(target=waiter)
                real_start(helper)
                time.sleep(0.2)  # the waiter is inside `wait` while this start is still pending
            return real_start(thread)

        try:
            with patch.object(threading.Thread, "start", hooked):
                self.assertTrue(chat.send("вопрос")[0])
            outcome["thread"].join(5)
            self.assertNotIn("error", outcome)
            self.assertTrue(outcome["alive"])  # the running turn was joined, for the bounded time
            self.assertGreaterEqual(outcome["waited"], 0.4)
        finally:
            release.write_text("go")
            chat.close()


if __name__ == "__main__":
    unittest.main()
