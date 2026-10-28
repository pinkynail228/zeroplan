"""Export of a verified snapshot to a local branch; real temporary Git repos."""

import importlib.util
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_terminal_planner import ProjectTest
from terminal_planner.authority import Authority, Blocked
from terminal_planner.export import create_branch
from terminal_planner.snapshot import candidate


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout.decode().strip()


def other_refs(root):
    return [line for line in git(root, "for-each-ref").split("\n") if "refs/heads/zplan/" not in line]


class BranchTests(ProjectTest):
    """The plumbing core against a real target repo and a cloned snapshot."""

    def setUp(self):
        super().setUp()
        self.workspace = self.root / "snapshot"
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(self.project), str(self.workspace)], check=True)
        self.source = git(self.project, "rev-parse", "HEAD")
        (self.workspace / "source.txt").write_text("changed\n")
        (self.workspace / "new.txt").write_text("new\n")
        self.sealed = candidate(self.workspace)

    def target_state(self):
        return (git(self.project, "rev-parse", "HEAD"), other_refs(self.project),
                git(self.project, "status", "--porcelain=v1", "--untracked-files=all"),
                (self.project / ".git" / "index").read_bytes(), (self.project / "source.txt").read_bytes())

    def export(self, branch="zplan/abcd1234", verify=None):
        return create_branch(self.project, self.workspace, self.source, branch, ["Subject", "Task: x"],
                             verify or (lambda: candidate(self.workspace) == self.sealed))

    def zplan_refs(self):
        return git(self.project, "for-each-ref", "refs/heads/zplan")

    def test_branch_holds_exactly_snapshot_tree_on_source_without_touching_target(self):
        before = self.target_state()
        sha, behind = self.export()
        self.assertFalse(behind)
        self.assertEqual(git(self.project, "rev-parse", "refs/heads/zplan/abcd1234"), sha)
        self.assertEqual(git(self.project, "rev-parse", sha + "^"), self.source)
        self.assertEqual(git(self.project, "ls-tree", "-r", "--name-only", sha).split("\n"), ["new.txt", "source.txt"])
        self.assertEqual(git(self.project, "show", sha + ":source.txt"), "changed")
        self.assertEqual(git(self.project, "log", "-1", "--format=%an <%ae>|%cn <%ce>", sha),
                         "zplan <zplan@localhost>|zplan <zplan@localhost>")
        self.assertEqual(self.target_state(), before)

    def test_root_control_directory_is_excluded_and_a_nested_one_kept(self):
        for path in (".zplan/milestone.json", "d/.zplan/kept.txt"):
            (self.workspace / path).parent.mkdir(parents=True, exist_ok=True)
            (self.workspace / path).write_text("x\n")
        sealed = candidate(self.workspace, exclude=(".git", ".zplan"))
        sha, _ = create_branch(self.project, self.workspace, self.source, "zplan/control", ["Subject"],
                               lambda: candidate(self.workspace, exclude=(".git", ".zplan")) == sealed, exclude=(".zplan",))
        self.assertEqual(git(self.project, "ls-tree", "-r", "--name-only", sha).split("\n"),
                         ["d/.zplan/kept.txt", "new.txt", "source.txt"])
        # The rule is what keeps it out: without it the control file is exported like any other.
        plain, _ = self.export("zplan/plain", verify=lambda: True)
        self.assertIn(".zplan/milestone.json", git(self.project, "ls-tree", "-r", "--name-only", plain).split("\n"))

    def test_ignored_control_directory_still_exports(self):
        """Regression RS1: `git add` refused the exclude pathspec when the control directory is itself ignored
        (the architect puts `/.zplan/` into info/exclude). Interpretation: an ignored name needs no exclude pathspec,
        because `add -A` skips it; the tree check still refuses a control path in the tree."""
        (self.workspace / ".zplan").mkdir()
        (self.workspace / ".zplan" / "STATE.md").write_text("x\n")
        keep = (".git", ".zplan")
        for rule in ("info/exclude", ".gitignore"):
            (self.project / ".git" / "info" / "exclude").write_text("/.zplan/\n" if rule == "info/exclude" else "")
            (self.workspace / ".gitignore").write_text(".zplan\n" if rule == ".gitignore" else "")
            sealed = candidate(self.workspace, exclude=keep)
            sha, _ = create_branch(self.project, self.workspace, self.source, "zplan/" + rule.split("/")[-1].strip("."),
                                   ["Subject"], lambda: candidate(self.workspace, exclude=keep) == sealed, exclude=(".zplan",))
            names = git(self.project, "ls-tree", "-r", "--name-only", sha).split("\n")
            self.assertEqual([n for n in names if n.startswith(".zplan")], [])
            self.assertIn("new.txt", names)

    def test_real_add_failure_still_raises_git_failed(self):
        (self.workspace / "secret.txt").write_text("x\n")
        (self.workspace / "secret.txt").chmod(0)
        self.addCleanup((self.workspace / "secret.txt").chmod, 0o644)
        with self.assertRaises(Blocked) as raised:
            self.export(verify=lambda: True)
        self.assertEqual(raised.exception.family, "git.failed")

    def test_tracked_control_directory_is_refused_up_front(self):
        (self.project / ".zplan").mkdir()
        (self.project / ".zplan" / "note.txt").write_text("tracked\n")
        git(self.project, "add", ".zplan")
        git(self.project, "commit", "-qm", "track control dir")
        before = self.target_state()
        verify = Mock(return_value=True)
        with self.assertRaisesRegex(Blocked, "reserved path .zplan"):
            create_branch(self.project, self.workspace, git(self.project, "rev-parse", "HEAD"), "zplan/control",
                          ["Subject"], verify, exclude=(".zplan",))
        verify.assert_not_called()
        self.assertEqual((self.zplan_refs(), self.target_state()), ("", before))

    def test_untracked_cache_dropped_by_target_exclude_is_left_out(self):
        """C3: a snapshot path with a cache component that info/exclude drops is left out without refusing; any
        other path the target-local exclude drops still refuses."""
        (self.project / ".git" / "info" / "exclude").write_text("__pycache__/\nexcl.txt\n")
        (self.workspace / "__pycache__").mkdir()
        (self.workspace / "__pycache__" / "hello.cpython-313.pyc").write_bytes(b"\0")
        (self.workspace / "pkg" / "__pycache__").mkdir(parents=True)
        (self.workspace / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"\0")
        self.sealed = candidate(self.workspace)
        sha, _ = self.export()
        self.assertEqual(git(self.project, "ls-tree", "-r", "--name-only", sha).split("\n"), ["new.txt", "source.txt"])
        (self.workspace / "excl.txt").write_text("writer\n")
        self.sealed = candidate(self.workspace)
        with self.assertRaisesRegex(Blocked, "excl.txt"):
            self.export("zplan/other")

    def test_tracked_ignored_file_stays_and_excluded_writer_file_is_refused(self):
        (self.project / ".gitignore").write_text("*.log\n")
        (self.project / "keep.log").write_text("keep\n")
        git(self.project, "add", ".gitignore")
        git(self.project, "add", "-f", "keep.log")
        git(self.project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "ignored")
        self.source = git(self.project, "rev-parse", "HEAD")
        shutil.rmtree(self.workspace)
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(self.project), str(self.workspace)], check=True)
        (self.workspace / "new.txt").write_text("new\n")
        (self.workspace / "build.log").write_text("untracked ignored\n")
        self.sealed = candidate(self.workspace)
        sha, _ = self.export()
        names = git(self.project, "ls-tree", "-r", "--name-only", sha).split("\n")
        self.assertIn("keep.log", names)
        self.assertNotIn("build.log", names)
        (self.project / ".git" / "info" / "exclude").write_text("excl.txt\n")
        (self.workspace / "excl.txt").write_text("writer\n")
        self.sealed = candidate(self.workspace)
        with self.assertRaises(Blocked):
            self.export(branch="zplan/second")
        self.assertEqual(self.zplan_refs().count("zplan/second"), 0)

    def test_snapshot_git_directory_is_ignored_even_when_tampered(self):
        # A writer-controlled .git (hostile config) is never read and never exported.
        git(self.workspace, "config", "core.worktree", "/nonexistent")
        git(self.workspace, "config", "filter.x.clean", "false")
        sha, _ = self.export(verify=lambda: True)
        self.assertNotIn(".git", git(self.project, "ls-tree", "-r", "--name-only", sha))

    def test_refuses_nested_git(self):
        nested = self.workspace / "vendor" / "lib"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(nested)], check=True)
        (nested / "f").write_text("x")
        with self.assertRaisesRegex(Blocked, "nested .git"):
            self.export(verify=lambda: True)
        self.assertEqual(self.zplan_refs(), "")

    def test_refuses_gitmodules(self):
        (self.workspace / ".gitmodules").write_text("[submodule a]\n\tpath = a\n\turl = x\n")
        with self.assertRaisesRegex(Blocked, "submodules"):
            self.export(verify=lambda: True)
        self.assertEqual(self.zplan_refs(), "")

    def test_refuses_gitlink_that_dodges_the_name_scan(self):
        nested = self.workspace / "sub"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(nested)], check=True)
        git(nested, "-c", "user.name=a", "-c", "user.email=a@b.c", "commit", "--allow-empty", "-qm", "x")
        with patch("terminal_planner.export.scan", return_value=["new.txt", "source.txt"]):
            with self.assertRaisesRegex(Blocked, "gitlink"):
                self.export(verify=lambda: True)
        self.assertEqual(self.zplan_refs(), "")

    def test_refuses_filters_declared_for_snapshot_files(self):
        (self.workspace / ".gitattributes").write_text("*.txt filter=lfs\n")
        with self.assertRaisesRegex(Blocked, "filters"):
            self.export(verify=lambda: True)
        self.assertEqual(self.zplan_refs(), "")

    def test_refuses_existing_branch_and_keeps_it(self):
        git(self.project, "branch", "zplan/abcd1234")
        marker = git(self.project, "rev-parse", "zplan/abcd1234")
        with self.assertRaisesRegex(Blocked, "already exists"):
            self.export()
        self.assertEqual(git(self.project, "rev-parse", "zplan/abcd1234"), marker)

    def test_rerun_after_crash_adopts_only_the_identical_branch(self):
        sha, _ = self.export()
        self.assertEqual(self.export()[0], sha)
        git(self.project, "branch", "-D", "zplan/abcd1234")
        tree = git(self.project, "rev-parse", sha + "^{tree}")
        other = git(self.project, "-c", "user.name=t", "-c", "user.email=t@t", "commit-tree", tree, "-m", "no parent")
        git(self.project, "update-ref", "refs/heads/zplan/abcd1234", other)
        with self.assertRaisesRegex(Blocked, "already exists"):
            self.export()
        self.assertEqual(git(self.project, "rev-parse", "zplan/abcd1234"), other)

    def test_newline_in_file_name_exports(self):
        (self.workspace / "odd\nname.txt").write_text("odd\n")
        self.sealed = candidate(self.workspace)
        sha, _ = self.export()
        self.assertIn("odd\nname.txt", git(self.project, "ls-tree", "-r", "-z", "--name-only", sha).split("\0"))

    def test_ref_race_is_refused_atomically_by_update_ref(self):
        original = subprocess.run

        def racing(command, *args, **kwargs):
            if "update-ref" in command:
                git(self.project, "branch", "zplan/abcd1234")
            return original(command, *args, **kwargs)
        marker = git(self.project, "rev-parse", "HEAD")
        with patch("terminal_planner.export.subprocess.run", side_effect=racing):
            with self.assertRaisesRegex(Blocked, "was not created"):
                self.export()
        self.assertEqual(git(self.project, "rev-parse", "zplan/abcd1234"), marker)

    def test_refuses_tampered_snapshot_before_and_during_export(self):
        (self.workspace / "new.txt").write_text("tampered\n")
        with self.assertRaisesRegex(Blocked, "candidate"):
            self.export()
        results = iter([True, False])
        with self.assertRaisesRegex(Blocked, "during export"):
            self.export(verify=lambda: next(results))
        self.assertEqual(self.zplan_refs(), "")

    def test_refuses_missing_source_revision(self):
        with self.assertRaisesRegex(Blocked, "source revision is missing"):
            create_branch(self.project, self.workspace, "1" * 40, "zplan/abcd1234", ["s"], lambda: True)
        self.assertEqual(self.zplan_refs(), "")

    def test_behind_head_is_reported_and_branch_stays_on_source(self):
        (self.project / "later.txt").write_text("later\n")
        git(self.project, "add", "later.txt")
        git(self.project, "commit", "-qm", "later")
        head = git(self.project, "rev-parse", "HEAD")
        sha, behind = self.export()
        self.assertTrue(behind)
        self.assertEqual(git(self.project, "rev-parse", sha + "^"), self.source)
        self.assertEqual(git(self.project, "rev-parse", "HEAD"), head)

    def test_attribute_conversion_cannot_change_exported_bytes(self):
        (self.workspace / "crlf.txt").write_bytes(b"a\r\nb\r\n")
        (self.workspace / ".gitattributes").write_text("*.txt text eol=lf\n")
        with self.assertRaisesRegex(Blocked, "conversion"):
            self.export(verify=lambda: True)
        self.assertEqual(self.zplan_refs(), "")


class ReadmeImageTests(unittest.TestCase):
    """E1-E3: devtools/export_check.py accepts a GIF or PNG under docs/img/ and nothing else that is not UTF-8.

    Interpretation: an accepted image is scanned only for private terms (the content rules target text), as a
    substring match on its latin-1 decoding."""

    GIF = b"GIF89a\xc0\x03\xff\xfe" + bytes(range(256))
    PNG = b"\x89PNG\r\n\x1a\n\xff\x00" + bytes(range(256))
    TERM = "hidden-client-name"

    def setUp(self):
        spec = importlib.util.spec_from_file_location("export_check", Path(__file__).resolve().parents[1] / "devtools" / "export_check.py")
        self.check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.check)
        self.repo = Path(tempfile.mkdtemp(prefix="zs-img-"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        git(self.repo, "init", "-q")
        (self.repo / "devtools").mkdir()
        (self.repo / "devtools" / "export-manifest.txt").write_text("+ docs/\n+ tests/\n")

    def run_check(self, files, out=None, terms=("zzz-unused",)):
        for rel, data in files.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_bytes(data)
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "--allow-empty", "-qm", "x")
        return sorted((row["rule"], row["raw_path"]) for row in self.check.check(str(self.repo), "HEAD", out, list(terms)))

    def test_image_is_accepted_only_under_all_four_conditions(self):
        """E1: the accepted shape gives no finding; every deviation stays `unreadable`."""
        big = self.check.IMAGE_MAX_BYTES
        pad = lambda size: self.GIF + b"\0" * (size - len(self.GIF))
        ok = {"docs/img/demo.gif": self.GIF, "docs/img/old.gif": b"GIF87a\xff", "docs/img/a.png": self.PNG, "docs/img/edge.gif": pad(big)}
        bad = {"tests/demo.gif": self.GIF, "docs/other/demo.gif": self.GIF, "docs/img/random.gif": b"\xff\xfe\x00\x01" * 8,
               "docs/img/wrong.gif": self.PNG, "docs/img/wrong.png": self.GIF, "docs/img/big.gif": pad(big + 1),
               "docs/img/clip.png": self.PNG[:7], "docs/img/photo.jpg": b"\xff\xd8\xff\xe0", "docs/img/GIF89a.dat": self.GIF}
        self.assertEqual(self.run_check({**ok, **bad}), sorted(("unreadable", path) for path in bad))

    def test_accepted_image_is_scanned_for_private_terms_on_raw_bytes(self):
        """E2: a term in a GIF comment or a PNG tEXt chunk is found, case-insensitively; a clean image is not."""
        gif = b"GIF89a\x01\x00\xff\xfe\x20" + self.TERM.upper().encode() + b"\x00;"
        png = self.PNG + b"\x00\x00\x00\x20tEXtComment\x00" + self.TERM.encode() + b"\xff\xfe"
        found = self.run_check({"docs/img/a.gif": gif, "docs/img/a.png": png, "docs/img/clean.gif": self.GIF}, terms=(self.TERM,))
        self.assertEqual(found, [("private-term", "docs/img/a.gif"), ("private-term", "docs/img/a.png")])

    def test_dir_mode_compares_an_accepted_image_byte_for_byte(self):
        """E3: the export tree's image with one changed byte is `dir-changed`; the identical one is clean."""
        out = self.repo.parent / (self.repo.name + "-out")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        (out / "docs" / "img").mkdir(parents=True)
        (out / "docs" / "img" / "demo.gif").write_bytes(self.GIF)
        self.assertEqual(self.run_check({"docs/img/demo.gif": self.GIF}, out=str(out)), [])
        (out / "docs" / "img" / "demo.gif").write_bytes(self.GIF[:-1] + b"\x00")
        self.assertEqual(self.run_check({}, out=str(out)), [("dir-changed", "docs/img/demo.gif")])
