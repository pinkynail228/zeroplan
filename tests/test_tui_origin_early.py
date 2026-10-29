"""D5: a project without a GitHub origin hears it before any model work (soak S2, rc1 walk N4).

O1: the origin card's skip row says what skipping costs. O2: the first message the owner sends to the architect in a
session whose project has no GitHub origin leaves one notice, with the command of the readiness item; the architect
still answers and a second message adds no second notice. O3 (a project with a GitHub origin changes nothing) is the
same journey over the shell's own GitHub origin, plus `tests.test_tui_start` with only its skip row pins updated.

Interpretations (the reviewers never see the worker's summary):

- «preceded in the chat by one notice» is the app's own note line above the chat input (`chat_note`, the place
  `status_note` writes), set when the owner's first message is accepted; the note waits while the turn runs, as every
  note does, and shows after it. The transcript is the engine's store, which the notice does not touch.
- The text is the readiness item's own fix text (`setup.check_target`, item `origin`), after «Planning needs a GitHub
  origin.»; the check runs once, at the first accepted message, and the answer holds for the session.
- Two tests: the card (one start app) and the chat journey (one whole app).
- D5b (critic rel083 finding 1): the notice is set before `chat.send` starts the turn's thread, not after it. The
  order and the refusal are pinned on `ZplanApp.send_chat` itself with a fake chat that records `origin_note` at call
  time; a refused send gives the notice back and does not spend the once-per-session check.
"""

import asyncio
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401  (joins the offline wheelhouse to sys.path before the guarded imports)
from tui_support import HAVE_TEXTUAL

from test_tui_chat import OPENING, ChatShell

if HAVE_TEXTUAL:
    from terminal_planner.tui import start
    from terminal_planner.tui.app import ZplanApp

SKIP = "Skip — zplan cannot plan until the project has a GitHub origin"
COMMAND = "git remote add origin https://github.com/OWNER/REPO.git"


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable")
class OriginCardSkipTests(unittest.TestCase):
    def test_o1_the_skip_row_says_what_skipping_costs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home = patch.dict(os.environ, {"HOME": str(root / "home"), "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
                                           "GIT_CONFIG_NOSYSTEM": "1"})
            home.start()
            self.addCleanup(home.stop)
            (root / "gitconfig").write_text("[user]\n\tname = G\n\temail = g@example.invalid\n")
            rows = {}
            for name, origin, expected in (("bare", None, ["Add origin", SKIP]),
                                           ("gitlab", "https://gitlab.com/a/b.git", [SKIP, "Replace origin"])):
                path = root / name
                path.mkdir()
                for args in (("init", "-q", "-b", "main"), ("commit", "-q", "--allow-empty", "-m", "fixture")) \
                        + ((("remote", "add", "origin", origin),) if origin else ()):
                    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
                app = start.StartApp(path)

                async def drive(app=app, name=name):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        await pilot.press("enter")  # open: the origin step
                        rows[name] = [label for label, _ in app.rows()]
                asyncio.run(drive())
                self.assertEqual(rows[name], expected)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable")
class OriginNoticeOrderTests(unittest.TestCase):
    def test_d5b_the_notice_precedes_the_turn_and_a_refused_send_keeps_nothing(self):
        """B1: `origin_note` holds the fix command when `chat.send` is called. B2: a refused send leaves no notice and
        keeps the check for the next accepted send, which gets the notice once; a third send adds none. B3: with a
        GitHub origin (`origin_fix` is "") no notice is ever set."""
        for fix in (COMMAND, ""):
            with self.subTest(fix=fix):
                seen, answers = [], [(False, "busy"), (True, ""), (True, "")]
                app = SimpleNamespace(
                    origin_told=False, origin_note="", chat_note="", chat_snapshot=lambda: None,
                    controller=SimpleNamespace(origin_fix=lambda: fix),
                    chat=SimpleNamespace(send=lambda value, snapshot=None: (
                        seen.append(app.origin_note), answers.pop(0))[1]))
                after = []
                for _ in range(3):
                    ZplanApp.send_chat(app, "add a flag")
                    after.append(app.origin_note)
                self.assertEqual([COMMAND in note for note in seen], [bool(fix)] * 3)  # the third still shows the second's
                self.assertEqual([COMMAND in note for note in after], [False, bool(fix), False])


class OriginNoticeTests(ChatShell):
    def told(self):
        """The status area holds the notice with the readiness item's command (the pane wraps it: spaces ignored)."""
        shown = "".join(self.status_text().split())
        return "".join(COMMAND.split()) in shown and "Planningneedsa" in shown

    async def test_o2_the_first_message_leaves_one_notice_with_the_command_and_the_architect_answers(self):
        """O2/O3: without an origin the first accepted message shows the notice, also while the architect's turn runs,
        and the architect answers; a second message adds none. The shell's project has a GitHub origin: the same
        journey leaves no notice."""
        for origin in (True, False):
            with self.subTest(origin=origin):
                if not origin:
                    self.git("remote", "remove", "origin")
                self.fixture.script([{"lines": OPENING + [{"type": "item.completed", "item": {
                    "id": "i1", "type": "agent_message", "text": "Drafting goal"}},
                    {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}], "hang": 2}])
                async with self.shell() as pilot:
                    await self.loaded(pilot)
                    await self.chat_ready(pilot)
                    await self.say(pilot, "add a flag")
                    await self.until(pilot, lambda: "Drafting goal" in self.status_text(), 10.0)
                    running = self.status_text()  # the turn still runs: the notice is already on the screen
                    self.assertIn("thinking", running)
                    self.assertEqual(self.told(), not origin)
                    await self.chat_done(pilot)
                    self.assertEqual(self.app.chat.state.entries[-1].role, "architect")
                    self.assertEqual(self.told(), not origin)
                    await self.say(pilot, "and another")
                    await self.chat_done(pilot)
                    self.assertFalse(self.told())
