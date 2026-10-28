"""No host execution through writer-owned config, attributes or links."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from terminal_planner.authority import Blocked
from terminal_planner.snapshot import candidate


class SnapshotTests(unittest.TestCase):
    def test_adversarial_git_clean_filter_is_never_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            marker = root.parent / (root.name + "-host-execution")
            self.addCleanup(lambda: marker.unlink(missing_ok=True))
            subprocess.run(["git", "-C", str(root), "config", "filter.probe.clean", "touch '" + str(marker) + "'; cat"], check=True)
            (root / ".gitattributes").write_text("* filter=probe\n")
            (root / "tracked").write_text("writer bytes\n")
            before = candidate(root)
            self.assertFalse(marker.exists())
            (root / "tracked").write_text("different\n")
            self.assertNotEqual(candidate(root), before)
            self.assertFalse(marker.exists())

    def test_links_hash_targets_without_reading_outside_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outside").symlink_to("/nonexistent/private/credentials")
            before = candidate(root)
            (root / "outside").unlink()
            (root / "outside").symlink_to("/nonexistent/other")
            self.assertNotEqual(before, candidate(root))

    def test_special_files_fail_closed_and_git_metadata_is_fresh(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".git/config").write_text("first")
            before = candidate(root)
            (root / ".git/config").write_text("second")
            self.assertNotEqual(before, candidate(root))
            os.mkfifo(root / "pipe")
            with self.assertRaises(Blocked):
                candidate(root)

    def test_writable_alias_cannot_bypass_read_only_review_mount(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            outside = Path(directory) / "writable-state"
            outside.write_text("alias")
            os.link(outside, root / "candidate")
            with self.assertRaisesRegex(Blocked, "Hard-linked candidate"):
                candidate(root)
