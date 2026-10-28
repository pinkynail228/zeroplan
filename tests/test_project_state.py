"""A8a: the project STATE file (`.zplan/STATE.md`) and its two architect tools, one smoke test per criterion.

Interpretations (the task leaves them open):
- A refusal of the format (C1) raises `Blocked` with the existing family `action.refused` (the write-set holds no
  catalog); a failed write raises `PersistenceError` (`store.write_failed`).
- A heading is a line starting with `## `; its name is the rest of the line stripped, so `## Now ` is `Now`.
- The size and the headings are checked twice: on the text given and on the scrubbed text (a mask may be longer).
- `zplan_state_update` answers with a short plain-text line; `zplan_state` answers with the file text as is.
- The exclude line is the literal `/.zplan/`, matched on stripped lines; a missing final newline is completed first."""

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from terminal_planner import architect_tools, authority, project_state
from terminal_planner.authority import Blocked

IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost"}
GOOD = "".join("## %s\n- line\n" % name for name in project_state.SECTIONS)


def status(project):
    return subprocess.run(["git", "-C", str(project), "status", "--porcelain=v1", "--untracked-files=all"],
                          check=True, capture_output=True, text=True).stdout


class ProjectStateTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name).resolve() / "proj"
        self.project.mkdir()
        env = {**os.environ, **IDENTITY}
        git = lambda *args: subprocess.run(["git", "-C", str(self.project), *args], check=True, env=env,
                                           capture_output=True)
        git("init", "-q", "-b", "main")
        (self.project / "a.txt").write_text("a\n")
        git("add", "-A")
        git("commit", "-q", "-m", "init")
        self.exclude = self.project / ".git" / "info" / "exclude"

    # C1
    def test_validate_format(self):
        project_state.validate(GOOD)
        project_state.validate(GOOD + "x" * (5 * 1024 - len(GOOD)))
        for bad in (GOOD + "## Later\n", GOOD.replace("## Next\n", ""), "## Next\n## Now\n## Open\n## Decisions\n",
                    GOOD + "x" * (6145 - len(GOOD)), "", "## Now\n## Next\n## Open\n## Decisions\n## Now\n"):
            with self.assertRaises(Blocked, msg=bad[:30]):
                project_state.validate(bad)
        project_state.validate(GOOD + "x" * (6144 - len(GOOD)))
        with self.assertRaises(Blocked) as raised:
            project_state.validate(GOOD + "## Later\n")
        self.assertIn("headings", str(raised.exception))
        with self.assertRaises(Blocked):  # bytes, not characters
            project_state.validate(GOOD + "я" * 3072)

    # C2
    def test_write_scrubs_and_replaces_atomically(self):
        self.assertEqual(project_state.read(self.project), "")
        project_state.write(self.project, GOOD + "api_key=abc\n")
        stored = project_state.read(self.project)
        self.assertNotIn("abc", stored)
        self.assertIn("api_key=", stored)
        project_state.write(self.project, GOOD)
        self.assertEqual(project_state.read(self.project), GOOD)
        directory = self.project / ".zplan"
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((directory / "STATE.md").stat().st_mode), 0o600)
        self.assertEqual([p.name for p in directory.iterdir()], ["STATE.md"])

    def test_a_refused_write_changes_nothing(self):
        project_state.write(self.project, GOOD)
        with self.assertRaises(Blocked):
            project_state.write(self.project, GOOD + "## Later\n")
        self.assertEqual(project_state.read(self.project), GOOD)

    # C3
    def test_the_project_stays_clean_and_fresh(self):
        before = authority.baseline(self.project)
        project_state.write(self.project, GOOD)
        self.assertEqual(status(self.project), "")
        self.assertEqual(authority.baseline(self.project), before)
        self.assertEqual(self.exclude.read_text().splitlines().count("/.zplan/"), 1)
        kept = self.exclude.read_bytes()
        project_state.write(self.project, GOOD.replace("- line", "- other"))
        self.assertEqual(self.exclude.read_bytes(), kept)

    def test_existing_exclude_lines_are_kept(self):
        self.exclude.write_text("# mine\n*.log")
        project_state.write(self.project, GOOD)
        self.assertEqual(self.exclude.read_text(), "# mine\n*.log\n/.zplan/\n")
        self.exclude.unlink()  # created when missing
        project_state.write(self.project, GOOD)
        self.assertEqual(self.exclude.read_text(), "/.zplan/\n")

    # C4
    def test_tools(self):
        names = [tool["name"] for tool in architect_tools.TOOLS]
        self.assertIn("zplan_state", names)
        self.assertIn("zplan_state_update", names)
        self.assertFalse({"zplan_state", "zplan_state_update"} & set(architect_tools.ACTION_TOOLS))

        def call(name, arguments):
            result, error = architect_tools.handle(
                str(self.project), {"method": "tools/call", "params": {"name": name, "arguments": arguments}})
            return result, error

        result, _ = call("zplan_state", {})
        self.assertEqual(result["content"][0]["text"], "")
        result, _ = call("zplan_state_update", {"text": GOOD})
        self.assertNotIn("isError", result)
        result, _ = call("zplan_state", {})
        self.assertEqual(result["content"][0]["text"], GOOD)
        result, error = call("zplan_state_update", {"text": GOOD + "## Fifth\n"})
        self.assertTrue(result["isError"])
        self.assertTrue(result["content"][0]["text"].startswith("action.refused: "))
        self.assertEqual(project_state.read(self.project), GOOD)
        self.assertEqual(call("zplan_state_update", {})[1][0], architect_tools.INVALID_PARAMS)
        self.assertEqual(call("zplan_state", {"text": "x"})[1][0], architect_tools.INVALID_PARAMS)

    def test_a_failed_write_is_a_tool_error(self):
        (self.project / ".zplan").write_text("a file where the directory belongs")
        result, _ = architect_tools.handle(
            str(self.project), {"method": "tools/call", "params": {"name": "zplan_state_update",
                                                                   "arguments": {"text": GOOD}}})
        self.assertTrue(result["isError"])
        self.assertTrue(result["content"][0]["text"].startswith("store.write_failed: "))


if __name__ == "__main__":
    unittest.main()
