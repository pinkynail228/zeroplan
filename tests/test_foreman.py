"""A4a: the foreman's mechanical brief checks over a real temporary Git repository.

Interpretations (the task leaves them open):
- A tracked file is what `project_read.list_files` reports (tracked and unignored-untracked, as the architect sees it).
- "Parent directory has no tracked file" means no listed file under that directory at any depth; for a path in the
  repository root the root counts as the parent.
- An identifier in `reuse` such as `authority.brief_problem` is found when the whole token or its last dotted part
  (`brief_problem`) is found by `search`, since source spells a definition without its module prefix.
- A path token ending in `/` is accepted when a listed file lies under it; line 0 is a line beyond the file.
- Only `reuse` is searched for identifiers; criteria tokens are checked as path tokens only (C2).
- C3 scans the whole write-set test file, once per token; every finding is emitted once however often it recurs."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from terminal_planner import foreman
from terminal_planner.authority import BRIEF_KEYS

IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost"}


def make_brief(**over):
    brief = {"goal": "g", "why": "w", "reuse": "", "write_set": ["src/new.py"],
             "criteria": [{"id": "C1", "text": "t", "example": "e"}], "non_goals": [], "risk": "low", "dod": "d"}
    brief.update(over)
    assert set(brief) == set(BRIEF_KEYS)
    return brief


class ForemanTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.p = Path(temp.name).resolve() / "proj"
        self.p.mkdir()
        subprocess.run(["git", "-C", str(self.p), "init", "-q", "-b", "main"], check=True)
        self.write("src/old.py", "def old_fn():\n    pass\n")

    def write(self, name, text):
        path = self.p / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        env = {**os.environ, **IDENTITY}
        subprocess.run(["git", "-C", str(self.p), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(self.p), "commit", "-q", "-m", "x", "--allow-empty"], check=True, env=env)

    def inspect(self, **over):
        self.commit()
        return foreman.inspect(self.p, make_brief(**over))

    def test_invalid_brief_is_one_blocking_f5(self):
        result = foreman.inspect(self.p, {"goal": "g"})
        self.assertEqual([(f["check"], f["blocking"]) for f in result], [("F5", True)])
        self.assertIn("brief", result[0]["text"])

    def test_c1_write_set_reach(self):
        self.write("tests/a.py", "")
        result = self.inspect(write_set=["tests/test_x.py", "nowhere/new.py"])
        self.assertEqual([(f["check"], f["blocking"]) for f in result], [("F1", True)])
        self.assertIn("nowhere/new.py", result[0]["text"])

    def test_c2_stale_references(self):
        self.write("a.py", "1\n2\n3\n")
        result = self.inspect(reuse="`a.py:9` and `missing_fn`")
        self.assertEqual([f["check"] for f in result], ["F1", "F1"])
        self.assertTrue(all(f["blocking"] for f in result))
        texts = " ".join(f["text"] for f in result)
        self.assertIn("a.py:9", texts)
        self.assertIn("missing_fn", texts)

    def test_c2_criterion_tokens_and_found_references(self):
        result = self.inspect(reuse="`src/old.py:2`, `old_fn`, `src.old_fn`",
                              criteria=[{"id": "C1", "text": "reads `gone.py`", "example": "see `src/new.py`"}])
        self.assertEqual(len(result), 1)
        self.assertIn("gone.py", result[0]["text"])

    def test_c2_outside_directory_tokens_are_findings(self):
        """Regression: an absolute or `..` directory token with a trailing slash is an F1 finding, not a raised Blocked."""
        for token in ("/tmp/", "/", "../"):
            result = self.inspect(reuse="see `%s`" % token,
                                  criteria=[{"id": "C1", "text": "never write under `%s`" % token, "example": "e"}])
            self.assertEqual([f["check"] for f in result], ["F1", "F1"], token)

    def test_c3_platform_is_not_blocking(self):
        self.write("tests/test_h.py", 'import os\nos.environ["HOME"]\n')
        result = self.inspect(write_set=["tests/test_h.py"])
        self.assertEqual([(f["check"], f["blocking"]) for f in result], [("F3", False)])
        self.assertIn("tests/test_h.py", result[0]["text"])
        self.assertIn("HOME", result[0]["text"])
        self.assertEqual(self.inspect(write_set=["tests/test_h.py"], dod="skips on Linux"), [])

    def test_c3_scans_past_the_read_line_cap(self):
        """Regression: a platform token after line 400 of a write-set test file is still found."""
        self.write("tests/test_long.py", "x = 1\n" * 450 + "import sys\nsys.platform\n")
        result = self.inspect(write_set=["tests/test_long.py"])
        self.assertEqual([f["check"] for f in result], ["F3"])
        self.assertIn("sys.platform", result[0]["text"])

    def test_c4_size(self):
        result = self.inspect(why="x" * 5000)
        self.assertEqual([(f["check"], f["blocking"]) for f in result], [("F5", True)])
        self.assertRegex(result[0]["text"], r"\b5\d{3}\b")
        many = ["src/f%d.py" % i for i in range(13)]
        result = self.inspect(write_set=many)
        self.assertEqual([f["check"] for f in result], ["F5"])
        self.assertIn("13", result[0]["text"])

    def test_joint_example_passes(self):
        result = self.inspect(reuse="`src/old.py`",
                              criteria=[{"id": "C1", "text": "edits `src/new.py`", "example": "e"}])
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
