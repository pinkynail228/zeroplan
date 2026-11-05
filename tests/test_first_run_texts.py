# tests/test_first_run_texts.py
"""The first-run screens say what they do. The profile card's Accept line matches what accepting does: the decision
is kept outside the project, nothing is written or committed (`zplan profile init` is what writes the file). A demo
session (`--fixture`) plans without a GitHub origin, so its start screen opens such a project directly; a real
session still shows the origin step."""

import asyncio
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tui_support  # noqa: F401  (the offline wheelhouse joins sys.path before the guarded imports)
from tui_support import HAVE_TEXTUAL

from terminal_planner import process
from terminal_planner.authority import Authority as RealAuthority
from terminal_planner.process import Profile
from test_terminal_planner import ProjectTest

if HAVE_TEXTUAL:
    from terminal_planner.tui import start


class AcceptLineTests(ProjectTest):
    def setUp(self):
        super().setUp()
        (self.project / ".git" / "info" / "exclude").write_text("", encoding="utf-8")  # a written file would show

    def test_accepting_a_proposal_writes_nothing_and_the_card_promises_no_commit(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            profile = Profile(self.project, authority.directory, authority)
            status = profile.status()
            self.assertFalse(status.present)
            accept = [line for line in process.bootstrap_lines(status) if line.strip().startswith("Accept")]
            profile.accept()
        self.assertEqual(len(accept), 1)
        self.assertFalse((self.project / process.PROFILE_FILE).exists())
        self.assertEqual(self.git("status", "--porcelain").decode().strip(), "")
        self.assertNotIn("commit", accept[0])
        self.assertIn("outside the project", accept[0])


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable")
class DemoOriginTests(unittest.TestCase):
    def test_a_demo_start_opens_a_project_without_an_origin_and_a_real_start_asks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home = patch.dict(os.environ, {"HOME": str(root / "home"), "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
                                           "GIT_CONFIG_NOSYSTEM": "1"})
            home.start()
            self.addCleanup(home.stop)
            (root / "gitconfig").write_text("[user]\n\tname = G\n\temail = g@example.invalid\n")
            path = root / "bare"
            path.mkdir()
            for args in (("init", "-q", "-b", "main"), ("commit", "-q", "--allow-empty", "-m", "fixture")):
                subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
            seen = {}
            for name, demo in (("demo", True), ("real", False)):
                app = start.StartApp(path, origin=not demo)

                async def drive(app=app, name=name):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        await pilot.press("enter")  # open this project
                        await pilot.pause()
                        seen[name] = (app.return_value, [] if app.return_value else [label for label, _ in app.rows()])
                asyncio.run(drive())
            self.assertEqual(seen["demo"], (path, []))
            self.assertIsNone(seen["real"][0])
            self.assertIn(start.SKIP, seen["real"][1])


if __name__ == "__main__":
    unittest.main()
