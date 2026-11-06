"""A3: read tools for the architect (list, read, search) over a real temporary Git repository.

Interpretations (the task leaves them open):
- `truncated` is set when a cap (400 lines, 64 KB, 2000 paths, 200 hits) cut the answer short, not when the caller's
  own `count` ended it; a read with count <= 400 that stops early is not truncated.
- `search` matches the substring against the scrubbed line, so the search cannot be used to probe the value of a
  masked credential; the hit text is the scrubbed line, as C3 requires.
- A path the HEAD tree does not list (an ignored or uncommitted file, a missing one, a directory) and every symlink
  are refused with `read.outside_project`: a symlink is not a regular file of the tree, so what it points to is
  never read through it.
- Credential names and `.git`/`.zplan` directories are matched case-insensitively, at any depth.
- The families are not in terminal_planner.catalog yet (the wiring task adds them), so the tests read `.family`."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from terminal_planner import live, project_read
from terminal_planner.authority import Blocked

IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost"}


def git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, env={**os.environ, **IDENTITY})


class ReadTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.p = self.base / "proj"
        self.p.mkdir()
        git(self.p, "init", "-q", "-b", "main")
        self.write("a.py", 'PASSWORD = "x"\n')

    def write(self, name, text, binary=False):
        path = self.p / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if binary else text.encode())

    def commit(self):
        git(self.p, "add", "-f", "-A")
        git(self.p, "commit", "-q", "-m", "x")

    def family(self, function, *args, **kwargs):
        with self.assertRaises(Blocked) as caught:
            function(self.p, *args, **kwargs)
        return caught.exception.family


class UncommittedTests(ReadTest):
    def test_untracked_caches_are_no_uncommitted_work(self):
        """0.13 G6: an untracked `__pycache__` file is not the owner's uncommitted work; other files are."""
        self.commit()
        self.write("pkg/__pycache__/m.cpython-313.pyc", b"cache", binary=True)
        self.write("notes.txt", "mine\n")
        self.assertEqual(project_read.uncommitted_paths(self.p), ["notes.txt"])


class BoundaryTests(ReadTest):
    def test_c1_roots_paths_and_symlinks_outside_the_project_are_refused(self):
        outside = self.base / "outside.txt"
        outside.write_text("secret\n")
        (self.p / "link").symlink_to(outside)
        (self.p / "hosts").symlink_to("/etc/hosts")
        (self.p / "inside").symlink_to("a.py")
        self.commit()
        for path in ("../x", "/etc/hosts", "a/../../x", "link", "hosts", "inside", "missing.py", "."):
            with self.subTest(path):
                self.assertEqual(self.family(project_read.read_file, self.p, path), "read.outside_project")
        self.assertEqual(self.family(project_read.list_files, self.p, "../"), "read.outside_project")
        self.assertEqual(self.family(project_read.list_files, self.base), "read.outside_project")
        self.assertEqual(project_read.list_files(self.p, self.p)["paths"], ["a.py"])

    def test_c1_a_worktree_of_the_project_is_a_root_and_a_stranger_repository_is_not(self):
        self.commit()
        tree = self.base / "tree"
        git(self.p, "worktree", "add", "-q", "-b", "side", str(tree))
        (tree / "b.py").write_text("print(1)\n")
        git(tree, "add", "b.py")
        git(tree, "commit", "-q", "-m", "b")
        self.assertIn("b.py", project_read.list_files(self.p, tree)["paths"])
        stranger = self.base / "stranger"
        stranger.mkdir()
        git(stranger, "init", "-q")
        self.assertEqual(self.family(project_read.list_files, stranger), "read.outside_project")


class CredentialTests(ReadTest):
    def test_c2_credentials_are_refused_by_read_and_skipped_by_list_and_search(self):
        names = [".env", ".env.local", ".netrc", "id_rsa", "id_rsa.pub", "id_ed25519", "a.pem", "k/b.key", "c.p12",
                 "credentials.json", ".ENV", ".zplan/STATE.md", "sub/.git/config"]
        for name in names:
            self.write(name, "PASSWORD = 1\n")
        (self.p / "to_env").symlink_to(".env")
        self.write("note.txt", "safe\n")
        self.commit()
        for name in names:
            with self.subTest(name):
                self.assertEqual(self.family(project_read.read_file, self.p, name), "read.credential")
        self.assertEqual(self.family(project_read.read_file, self.p, "to_env"), "read.outside_project")
        self.assertEqual(self.family(project_read.read_file, self.p, ".git/config"), "read.credential")
        self.assertEqual(project_read.list_files(self.p, self.p)["paths"], ["a.py", "note.txt"])
        hits = project_read.search(self.p, self.p, "PASSWORD")["hits"]
        self.assertEqual([hit["path"] for hit in hits], ["a.py"])

    def test_c3_every_returned_line_is_the_scrub_of_the_raw_line(self):
        raw = 'token = "' + 'sk' + '-' + 'abcdefghijklmnopqrstuvwx"'
        self.write("k.py", raw + "\nplain\n")
        self.commit()
        self.assertNotEqual(live.scrub(raw), raw)
        self.assertEqual(project_read.read_file(self.p, self.p, "k.py")["lines"], [live.scrub(raw), "plain"])
        hit = project_read.search(self.p, self.p, "token")["hits"][0]
        self.assertEqual(hit, {"path": "k.py", "line": 1, "text": live.scrub(raw)})
        self.assertNotIn("abcdefghijklmnopqrstuvwx", hit["text"])
        # The masked value is not findable: a search cannot probe a credential.
        self.assertEqual(project_read.search(self.p, self.p, "abcdefghijkl")["hits"], [])


class LimitTests(ReadTest):
    def test_c4_line_byte_path_and_hit_caps_set_truncated(self):
        self.write("big.txt", "".join("line %d\n" % n for n in range(1, 1001)))
        self.write("wide.txt", "x" * 1000 + "\n" + ("y" * 1000 + "\n") * 100)
        self.write("many/placeholder", "")
        self.commit()
        result = project_read.read_file(self.p, self.p, "big.txt", start=1, count=1000)
        self.assertEqual((len(result["lines"]), result["truncated"], result["lines"][-1]), (400, True, "line 400"))
        tail = project_read.read_file(self.p, self.p, "big.txt", start=601, count=400)
        self.assertEqual((tail["lines"][0], len(tail["lines"]), tail["truncated"]), ("line 601", 400, False))
        short = project_read.read_file(self.p, self.p, "big.txt", start=10, count=3)
        self.assertEqual((short["lines"], short["truncated"]), (["line 10", "line 11", "line 12"], False))
        wide = project_read.read_file(self.p, self.p, "wide.txt")
        self.assertTrue(wide["truncated"])
        self.assertLessEqual(sum(len(line) + 1 for line in wide["lines"]), 64 * 1024)
        for n in range(2100):
            (self.p / "many" / ("f%04d" % n)).write_text("")
        self.commit()
        listing = project_read.list_files(self.p, self.p)
        self.assertEqual((len(listing["paths"]), listing["truncated"]), (2000, True))
        self.assertEqual(project_read.list_files(self.p, self.p, "many/f00")["truncated"], False)
        hits = project_read.search(self.p, self.p, "line")
        self.assertEqual((len(hits["hits"]), hits["truncated"]), (200, True))

    def test_c4_a_file_with_a_nul_byte_in_its_first_8_kb_is_binary(self):
        self.write("blob.bin", b"abc\0def", binary=True)
        self.write("late.txt", b"a" * 9000 + b"\0", binary=True)
        self.write("t.txt", "needle\n")
        self.commit()
        self.assertEqual(self.family(project_read.read_file, self.p, "blob.bin"), "read.binary")
        self.assertEqual(project_read.read_file(self.p, self.p, "late.txt")["lines"][0][:3], "aaa")
        self.assertEqual([h["path"] for h in project_read.search(self.p, self.p, "needle")["hits"]], ["t.txt"])
        self.assertEqual(project_read.search(self.p, self.p, "def")["hits"], [])


class UncommittedTests(ReadTest):
    """F17 (owner's PenPot, 2026-11-04): a project whose files are not committed. The tools still read the last commit
    only, and every answer says so: an empty listing is not silence, an untracked file is not "outside the project"."""

    def setUp(self):
        super().setUp()
        (self.p / "a.py").unlink()
        git(self.p, "commit", "-q", "--allow-empty", "-m", "init")
        self.write("README.md", "hello\n")
        self.write("docs/plan.md", "needle\n")
        self.write(".env", "PASSWORD = 1\n")

    def test_tools_on_an_uncommitted_project_name_what_they_cannot_see(self):
        listing = project_read.list_files(self.p, self.p)
        self.assertEqual(listing["paths"], [])
        self.assertIn("README.md", listing["note"])
        self.assertIn("docs/plan.md", listing["note"])
        self.assertNotIn(".env", listing["note"])  # a credential name is never shown, as in the listing itself
        self.assertEqual(self.family(project_read.read_file, self.p, "README.md"), "read.uncommitted")
        self.assertEqual(self.family(project_read.read_file, self.p, "missing.md"), "read.outside_project")
        found = project_read.search(self.p, self.p, "needle")
        self.assertEqual(found["hits"], [])
        self.assertIn("docs/plan.md", found["note"])

    def test_a_modified_file_reads_its_committed_lines_with_a_note_and_a_clean_project_has_none(self):
        self.commit()
        self.write("README.md", "changed\n")
        read = project_read.read_file(self.p, self.p, "README.md")
        self.assertEqual(read["lines"], ["hello"])
        self.assertIn("note", read)
        self.assertIn("README.md", project_read.list_files(self.p, self.p)["note"])
        git(self.p, "checkout", "--", "README.md")
        self.assertNotIn("note", project_read.read_file(self.p, self.p, "README.md"))
        self.assertNotIn("note", project_read.list_files(self.p, self.p))
        self.assertNotIn("note", project_read.search(self.p, self.p, "needle"))

    def test_the_architect_is_told_its_tools_read_the_last_commit(self):
        from terminal_planner import architect, architect_tools
        rule = " ".join(line for line in architect.TOOL_RULES[:3])
        self.assertIn("zplan_list_files", rule)
        self.assertIn("last commit", rule)
        listed = [tool for tool in architect_tools.TOOLS if tool["name"] == "zplan_list_files"][0]
        self.assertIn("last commit", listed["description"])


if __name__ == "__main__":
    unittest.main()
