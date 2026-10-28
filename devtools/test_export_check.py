"""Self-tests for devtools/export_check.py.

Synthetic data only; every fixture value is assembled by string concatenation so
this test file itself never matches a content rule.  Each test checks that the
combined stdout+stderr of the checker never contains a synthetic value.

Interpretations recorded for the reviewers (the worker summary never reaches
them): the fixture credentials of this repository are silenced by line-level
entries in devtools/export-exemptions.txt instead of fixture rewrites, so the
exemption file is the S-5 guard through the checker's own stale-exemption
finding; devtools/linux-test.sh is the only devtools script that named the test
host; the manifest's ``+ .github/workflows/`` include matches nothing until the
workflow ships and a non-matching include is not a finding; the private-terms
list lives outside the repository, so the exit-0 run with the real terms is the
orchestrator's merge gate, while the exit-3 run is reproducible here.
"""
import hashlib
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

CHECK = Path(__file__).resolve().with_name("export_check.py")
LINUX_TEST = Path(__file__).resolve().parents[1] / "devtools" / "linux-test.sh"


def join(*parts):
    return "".join(parts)


OPENAI = join("sk-", "Ab1_" * 8)
OPENAI_NEAR = join("sk-", "shorttoken")
ANTHROPIC = join("sk-ant-", "Ab1_" * 8)
ANTHROPIC_NEAR = join("sk-ant-", "short")
GITHUB_GH = join("ghp_", "A1" * 18)
GITHUB_PAT = join("github_pat_", "Ab_" * 8)
AWS = join("AKIA", "ABCDEFGHIJKLMNOP")
SLACK = join("xoxb-", "abcd123456")
GOOGLE = join("AIza", "Ab1_-" * 9)
YANDEX = join("y0_", "Ab1_" * 8)
PRIVATE_KEY = join("-----BEGIN ", "RSA ", "PRIVATE KEY-----")
JWT = join("eyJ", "abcdefghij", ".eyJ", "abcdefghij", ".", "abcdefghij")
CREDENTIAL = join("api_", "key = \"", "abcdefgh1234", '"')
URL_USERINFO = join("https://", "alice", ":", "hunter2xyz", "@",
                    "example.invalid/x")
BEARER = join("Bearer ", "AbCdEf0123456789xyz")
HOME_PATH = join("/Users/", "mvp", "/work")
HOME_ALLOWED = (join("/Users/", "runner", "/x"),
                join("/home/", "user", "/y"),
                join("/Users/", "testuser"))

NOPE = "zzz-unused-term"


class ExportCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zs-check-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.secrets = []

    # -- helpers -------------------------------------------------------------
    def watch(self, *values):
        for value in values:
            if value not in self.secrets:
                self.secrets.append(value)

    def git(self, root, *args):
        return subprocess.run(["git", "-C", root, *args],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)

    def commit(self, root, message="x"):
        proc = self.git(root, "-c", "user.name=t", "-c", "user.email=t@t.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-q", "-m", message)
        self.assertEqual(proc.returncode, 0, "git commit failed")

    def write_file(self, root, rel, content):
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if isinstance(content, bytes):
            with open(full, "wb") as handle:
                handle.write(content)
        else:
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(content)
        return full

    def make_repo(self, files, manifest, exemptions=None, name="repo"):
        root = os.path.join(self.tmp, name)
        os.makedirs(root, exist_ok=True)
        self.git(root, "init", "-q")
        self.write_file(root, "devtools/export-manifest.txt", manifest)
        if exemptions is not None:
            self.write_file(root, "devtools/export-exemptions.txt", exemptions)
        for rel, content in files.items():
            self.write_file(root, rel, content)
        self.git(root, "add", "-A")
        self.commit(root)
        return root

    def make_exec_repo(self, name="execrepo"):
        root = os.path.join(self.tmp, name)
        os.makedirs(root, exist_ok=True)
        self.git(root, "init", "-q")
        self.write_file(root, "devtools/export-manifest.txt", "+ src/\n")
        full = self.write_file(root, "src/run.sh", "echo hi\n")
        os.chmod(full, 0o755)
        self.git(root, "add", "-A")
        self.commit(root)
        return root

    def terms(self, *values):
        path = os.path.join(self.tmp, "terms.txt")
        with open(path, "w", encoding="utf-8") as handle:
            for value in values:
                handle.write(value + "\n")
        return path

    def run_check(self, root, *extra):
        cmd = [sys.executable, str(CHECK), "--repo", root, *extra]
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True)

    def combined(self, proc):
        return (proc.stdout or "") + (proc.stderr or "")

    def assert_no_secrets(self, proc):
        blob = self.combined(proc)
        for value in self.secrets:
            self.assertFalse(value in blob, "output leaked a synthetic value")

    # -- tests ---------------------------------------------------------------
    def test_clean_repo_exits_zero(self):
        root = self.make_repo({"src/app.py": "print(1)\n"}, "+ src/\n")
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("summary: 0 findings", proc.stdout)
        self.assert_no_secrets(proc)

    def test_content_rule_positives(self):
        cases = (("openai", OPENAI), ("anthropic", ANTHROPIC),
                 ("github", GITHUB_GH), ("github", GITHUB_PAT), ("aws", AWS),
                 ("slack", SLACK), ("google", GOOGLE), ("yandex", YANDEX),
                 ("private-key", PRIVATE_KEY), ("jwt", JWT),
                 ("credential", CREDENTIAL), ("url-userinfo", URL_USERINFO),
                 ("bearer", BEARER), ("home-path", HOME_PATH))
        files = {"src/f%02d.txt" % i: "value: " + value + "\n"
                 for i, (_, value) in enumerate(cases)}
        root = self.make_repo(files, "+ src/\n")
        self.watch(*[value for _, value in cases])
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        for rule, _ in cases:
            self.assertIn(rule + "\t", combined)
        self.assert_no_secrets(proc)

    def test_near_miss_negatives(self):
        files = {
            "src/a.txt": "x: " + OPENAI_NEAR + "\n",
            "src/b.txt": "x: " + ANTHROPIC_NEAR + "\n",
            "src/c.txt": "".join(p + "\n" for p in HOME_ALLOWED),
        }
        root = self.make_repo(files, "+ src/\n")
        self.watch(OPENAI_NEAR, ANTHROPIC_NEAR, *HOME_ALLOWED)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("summary: 0 findings", proc.stdout)
        self.assert_no_secrets(proc)

    def test_private_term_content_and_path(self):
        term = join("zztop", "-", "hiddenterm")
        files = {
            "src/notes.txt": "note: " + term + "\n",
            "src/" + term + ".txt": "clean\n",
        }
        root = self.make_repo(files, "+ src/\n")
        self.watch(term)
        proc = self.run_check(root, "--private-terms", self.terms(term))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("private-term", combined)
        self.assertIn("private-path", combined)
        self.assertIn("<redacted:", combined)
        self.assertNotIn(term, combined)
        self.assert_no_secrets(proc)

    def test_file_outside_include_not_scanned(self):
        files = {"src/app.py": "print(1)\n", "other/leak.txt": "k=" + AWS + "\n"}
        root = self.make_repo(files, "+ src/\n")
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        self.assertEqual(proc.returncode, 0)
        self.assert_no_secrets(proc)

    def test_excluded_file_with_secret_passes(self):
        files = {"src/leak.txt": "k=" + AWS + "\n", "src/ok.txt": "fine\n"}
        root = self.make_repo(files, "+ src/\n- src/leak.txt\n")
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        self.assertEqual(proc.returncode, 0)
        self.assert_no_secrets(proc)

    def test_exclude_wins_over_include(self):
        files = {"src/leak.txt": "k=" + AWS + "\n"}
        manifest = "+ src/\n+ src/leak.txt\n- src/leak.txt\n"
        root = self.make_repo(files, manifest)
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        self.assertEqual(proc.returncode, 0)
        self.assert_no_secrets(proc)

    def test_symlink_fails(self):
        root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(root, "src"))
        self.git(root, "init", "-q")
        self.write_file(root, "devtools/export-manifest.txt", "+ src/\n")
        self.write_file(root, "src/target.txt", "clean\n")
        os.symlink("target.txt", os.path.join(root, "src", "link"))
        self.git(root, "add", "-A")
        self.commit(root)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("symlink\t", combined)
        self.assert_no_secrets(proc)

    def test_gitlink_fails(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        sha = self.git(root, "rev-parse", "HEAD").stdout.strip()
        self.git(root, "update-index", "--add", "--cacheinfo",
                 "160000,%s,src/sub" % sha)
        self.commit(root)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("gitlink\t", combined)
        self.assert_no_secrets(proc)

    def test_non_utf8_blob_fails(self):
        root = self.make_repo({"src/bin.dat": b"\xff\xfe\x00\x01"}, "+ src/\n")
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unreadable\t", combined)
        self.assert_no_secrets(proc)

    def test_dir_extra(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "ok\n")
        self.write_file(out, "src/extra.txt", "hi\n")
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dir-extra\t", combined)
        self.assert_no_secrets(proc)

    def test_dir_missing(self):
        root = self.make_repo({"src/a.txt": "ok\n", "src/b.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "ok\n")
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dir-missing\t", combined)
        self.assert_no_secrets(proc)

    def test_dir_changed(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "leak " + AWS + "\n")
        self.watch(AWS)
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dir-changed\t", combined)
        self.assertNotIn(AWS, combined)
        self.assert_no_secrets(proc)

    def test_dir_exec_bit_user_exec_missing(self):
        root = self.make_exec_repo()
        out = os.path.join(self.tmp, "out")
        full = self.write_file(out, "src/run.sh", "echo hi\n")
        os.chmod(full, 0o655)
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dir-changed\t", combined)
        self.assert_no_secrets(proc)

    def test_dir_exec_bit_user_exec_extra(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        full = self.write_file(out, "src/a.txt", "ok\n")
        os.chmod(full, 0o755)
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dir-changed\t", combined)
        self.assert_no_secrets(proc)

    def test_dir_exec_bit_match_is_clean(self):
        root = self.make_exec_repo()
        out = os.path.join(self.tmp, "out")
        full = self.write_file(out, "src/run.sh", "echo hi\n")
        os.chmod(full, 0o755)
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("summary: 0 findings", proc.stdout)
        self.assert_no_secrets(proc)

    def test_exemption_silences_only_its_line(self):
        line1 = "first " + AWS
        line2 = "second " + AWS
        line3 = "third " + SLACK
        digest = hashlib.sha256(line1.encode("utf-8")).hexdigest()
        exemptions = "src/f.txt\taws\t" + digest + "\n"
        files = {"src/f.txt": "\n".join((line1, line2, line3)) + "\n",
                 "src/g.txt": line1 + "\n",
                 "devtools/export-exemptions.txt": exemptions}
        root = self.make_repo(files, "+ src/\n")
        self.watch(AWS, SLACK)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("slack\t", combined)
        self.assertEqual(combined.count("aws\t"), 2)
        self.assert_no_secrets(proc)

    def test_directory_pattern_does_not_match_bare_file(self):
        files = {"src/skipped": "k " + AWS + "\n"}
        root = self.make_repo(files, "+ src/\n- src/skipped/\n")
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("aws\t", combined)
        self.assert_no_secrets(proc)

    def test_directory_pattern_excludes_directory(self):
        files = {"src/skipped/deep.txt": "k " + AWS + "\n"}
        root = self.make_repo(files, "+ src/\n- src/skipped/\n")
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        self.assertEqual(proc.returncode, 0)
        self.assert_no_secrets(proc)

    def test_stale_exemption_secret_path_redacted(self):
        exemptions = "src/" + AWS + ".txt\taws\t" + "0" * 64 + "\n"
        files = {"src/a.txt": "ok\n", "devtools/export-exemptions.txt": exemptions}
        root = self.make_repo(files, "+ src/\n")
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stale-exemption\t", combined)
        self.assertIn("secret-path\t", combined)
        self.assertIn("<redacted:", combined)
        self.assertNotIn(AWS, combined)
        self.assert_no_secrets(proc)

    def test_stale_exemption_private_path_redacted(self):
        term = join("zztop", "-", "exemptpath")
        exemptions = "src/" + term + ".txt\taws\t" + "0" * 64 + "\n"
        files = {"src/a.txt": "ok\n", "devtools/export-exemptions.txt": exemptions}
        root = self.make_repo(files, "+ src/\n")
        self.watch(term)
        proc = self.run_check(root, "--private-terms", self.terms(term))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stale-exemption\t", combined)
        self.assertIn("private-path\t", combined)
        self.assertIn("<redacted:", combined)
        self.assertNotIn(term, combined)
        self.assert_no_secrets(proc)

    def test_control_characters_in_path_escaped(self):
        weird = "src/tab\there\nnl.txt"
        root = self.make_repo({weird: "k " + AWS + "\n"}, "+ src/\n")
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        lines = proc.stdout.splitlines()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].startswith("summary: "))
        self.assertEqual(sum(1 for line in lines if line.startswith("aws\t")), 1)
        self.assertIn("\\x09", proc.stdout)
        self.assertIn("\\x0a", proc.stdout)
        self.assert_no_secrets(proc)

    def test_dir_extra_control_characters_escaped(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "ok\n")
        self.write_file(out, "src/odd\nname.txt", "hi\n")
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        lines = proc.stdout.splitlines()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].startswith("summary: "))
        self.assertEqual(sum(1 for line in lines if line.startswith("dir-extra\t")), 1)
        self.assertIn("\\x0a", proc.stdout)
        self.assert_no_secrets(proc)

    def test_exemption_covers_only_finding(self):
        line = "only " + AWS
        digest = hashlib.sha256(line.encode("utf-8")).hexdigest()
        exemptions = "src/f.txt\taws\t" + digest + "\n"
        files = {"src/f.txt": line + "\n",
                 "devtools/export-exemptions.txt": exemptions}
        root = self.make_repo(files, "+ src/\n")
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("stale-exemption", combined)
        self.assertIn("summary: 0 findings", combined)
        self.assert_no_secrets(proc)

    def test_stale_exemption_fails(self):
        exemptions = "src/a.txt\taws\t" + "0" * 64 + "\n"
        files = {"src/a.txt": "ok\n", "devtools/export-exemptions.txt": exemptions}
        root = self.make_repo(files, "+ src/\n")
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stale-exemption\t", combined)
        self.assert_no_secrets(proc)

    def test_manifest_working_tree_edit_ignored(self):
        root = self.make_repo({"src/leak.txt": "k " + AWS + "\n"}, "+ src/\n")
        self.watch(AWS)
        self.write_file(root, "devtools/export-manifest.txt", "+ nothing/\n")
        proc = self.run_check(root, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("aws\t", combined)
        self.assert_no_secrets(proc)

    def test_missing_private_terms_exits_three(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        proc = self.run_check(root)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("private-term rule skipped", proc.stdout)
        self.assertIn("summary: 0 findings", proc.stdout)
        self.assert_no_secrets(proc)

    def test_key_shaped_file_name_redacted(self):
        root = self.make_repo({"src/" + AWS + ".txt": "clean\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/" + AWS + ".txt", "clean\n")
        self.write_file(out, "src/" + GITHUB_GH + ".txt", "clean\n")
        self.watch(AWS, GITHUB_GH)
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("secret-path\t", combined)
        self.assertIn("<redacted:", combined)
        self.assertNotIn(AWS, combined)
        self.assertNotIn(GITHUB_GH, combined)
        self.assert_no_secrets(proc)


    def permissions_enforced(self, path):
        try:
            os.listdir(path)
        except OSError:
            return True
        return False

    def test_cli_error_does_not_leak(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        term = join("zztop", "-", "argterm")
        bogus = join("--", "bad", AWS, "-", term)
        self.watch(AWS, term)
        proc = self.run_check(root, bogus)
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", combined)
        self.assertNotIn(AWS, combined)
        self.assertNotIn(term, combined)
        self.assert_no_secrets(proc)

    def test_bad_repo_and_dir_do_not_leak(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        bogus = os.path.join(self.tmp, join("gone-", AWS))
        self.watch(AWS)
        proc = self.run_check(bogus)
        self.assertEqual(proc.returncode, 2)
        self.assert_no_secrets(proc)
        proc = self.run_check(root, "--dir", bogus)
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", combined)
        self.assert_no_secrets(proc)

    def test_private_terms_invalid_utf8(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        bad = os.path.join(self.tmp, "terms.bin")
        with open(bad, "wb") as handle:
            handle.write(b"\xff\xfe" + AWS.encode("utf-8"))
        self.watch(AWS)
        proc = self.run_check(root, "--private-terms", bad)
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", combined)
        self.assertNotIn(AWS, combined)
        self.assert_no_secrets(proc)

    def add_index_entry(self, root, mode, sha, raw_path):
        proc = subprocess.run(
            [b"git", b"-C", os.fsencode(root), b"update-index", b"--add",
             b"--cacheinfo", mode.encode() + b"," + sha.encode() + b"," + raw_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, "update-index failed")

    def test_non_utf8_path_identity_in_dir_comparison(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        sha = self.git(root, "hash-object", "-w", "src/a.txt").stdout.strip()
        self.add_index_entry(root, "100644", sha, b"src/\xff.txt")
        self.commit(root)
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "ok\n")
        self.write_file(out, "src/\ufffd.txt", "ok\n")
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dir-missing\t", combined)
        self.assertIn("dir-extra\t", combined)
        self.assert_no_secrets(proc)

    def test_dir_extra_empty_directory(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "ok\n")
        os.makedirs(os.path.join(out, "src", "emptydir"))
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("dir-extra\tsrc/emptydir\t0", combined)
        self.assert_no_secrets(proc)

    def test_dir_extra_key_shaped_directory_redacted(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "ok\n")
        os.makedirs(os.path.join(out, "src", join("sub-", AWS)))
        self.watch(AWS)
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("secret-path\t", combined)
        self.assertIn("<redacted:", combined)
        self.assertNotIn(AWS, combined)
        self.assert_no_secrets(proc)

    def test_dir_unreadable_subtree_is_error(self):
        root = self.make_repo({"src/a.txt": "ok\n"}, "+ src/\n")
        out = os.path.join(self.tmp, "out")
        self.write_file(out, "src/a.txt", "ok\n")
        blocked = os.path.join(out, join("locked-", AWS))
        self.write_file(blocked, "extra.txt", "hi\n")
        os.chmod(blocked, 0)
        self.addCleanup(os.chmod, blocked, 0o700)
        self.watch(AWS)
        if not self.permissions_enforced(blocked):
            self.skipTest("permissions are not enforced in this environment")
        proc = self.run_check(root, "--dir", out, "--private-terms", self.terms(NOPE))
        combined = self.combined(proc)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", combined)
        self.assertNotIn(AWS, combined)
        self.assert_no_secrets(proc)


def oracle_finding(path_dir, target, exported):
    """Small independent oracle for the S-2 link resolution policy.

    Re-derives the rule with stdlib path helpers instead of the production
    functions, so the generator check below has an oracle of its own: a scheme
    target is external, the walk above the repository root is found with a
    depth counter over the decoded components (the production helper walks a
    stack) *before* any normalization, and only then is the resolved path
    rebuilt with ``posixpath`` for the export-set test.
    """
    if target.startswith("#"):
        return False
    if target.startswith("<"):
        return not (target.endswith(">") and ">" not in target[1:-1]
                    and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target[1:-1]))
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return False
    core = target
    for mark in ("#", "?"):
        index = core.find(mark)
        if index >= 0:
            core = core[:index]
    if not core:
        return False
    if re.search(r"%(?![0-9A-Fa-f]{2})", core):
        return True
    decoded = urllib.parse.unquote(core)
    depth = 0 if decoded.startswith("/") else len(
        [piece for piece in path_dir.split("/") if piece not in ("", ".")])
    for piece in decoded.split("/"):
        if piece in ("", "."):
            continue
        depth += -1 if piece == ".." else 1
        if depth < 0:
            return True
    if decoded.startswith("/"):
        resolved = posixpath.normpath(decoded).lstrip("/")
    else:
        resolved = posixpath.normpath(posixpath.join(path_dir, decoded))
    if resolved in ("", "."):
        return False
    if resolved in exported:
        return False
    return not any(candidate.startswith(resolved + "/") for candidate in exported)


class MarkdownLinkCheckTest(unittest.TestCase):
    """S-2: the link/path policy over the live markdown set of one commit.

    Interpretation notes (the worker summary never reaches the reviewers, so
    they live here): the live set is the exported ``*.md`` files of the commit
    minus the closed task records under ``devtools/zeroshot/tasks/``; a
    relative target resolves against the *file's own directory*, so a top-level
    live file resolves ``docs/x.md`` from the repo root; the exact marker
    ``private archive`` on a line excuses that line's excluded-directory
    tokens, and ``upstream/`` never needs one; STATE membership checks every
    token containing ``/`` and every bare token that is a top-level file of the
    commit.  ``test_named_history_anchor`` pins the historical failure on main
    e9bbf45.  ``docs/TERMINAL_UX_BRIEF.md`` people-facing content is
    unaffected by the checker; only its links/paths are.

    Repair classes checked here (each with a regression in
    ``test_inline_resolution_and_closed_grammar`` and in the generator's case
    set): a target walking above the repository root is decided on the decoded
    components before normalization, so ``/../root.md``, ``/%2e%2e/root.md``
    and ``/docs/../../root.md`` are findings even though each flattens onto an
    exported ``root.md``; and a target is classified by its raw form, so
    ``https://example.invalid/%zz`` and ``.../%FF`` stay external while a local
    ``missing%3Afile.md`` is a dead link.  The generator domain is every
    combination of a fixed prefix, separator and suffix list, capped at 500
    cases, and its expected verdicts come from ``oracle_finding`` only.
    The angle form is external only as a whole ``<scheme:...>`` autolink: a
    suffix after the closing ``>`` is a finding in both syntaxes
    (``<https://example.invalid>missing.md`` inline and as a reference
    definition), while a bare autolink that is not a link target is never
    looked at.

    The plain-path token set is exactly the one S-2 names (``docs/history/``,
    ``prototype/``, ``reference/``, and ``history/`` inside docs), so this test
    does not cover the audit document the manifest excludes: a bare
    ``docs/P0_AUDIT.md`` in live prose is not a rule finding.  That part of the
    stand-alone requirement is a content fix (the live plan names the private
    archive instead) guarded by the zero-finding run of the checker itself.
    """

    FILES = {
        "root.md": "root\n",
        "docs/real.md": "real\n",
        "docs/sub/deep.md": "deep\n",
    }
    MANIFEST = "+ docs/\n+ root.md\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zs-md-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def git(self, root, *args):
        return subprocess.run(["git", "-C", root, *args], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)

    def write(self, root, rel, content):
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(content)
        return full

    def make_repo(self, files, manifest=None):
        root = os.path.join(self.tmp, "repo")
        os.makedirs(root, exist_ok=True)
        self.git(root, "init", "-q")
        self.write(root, "devtools/export-manifest.txt", manifest or self.MANIFEST)
        for rel, content in files.items():
            self.write(root, rel, content)
        self.git(root, "add", "-A")
        proc = self.git(root, "-c", "user.name=t", "-c", "user.email=t@t.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x")
        self.assertEqual(proc.returncode, 0, "git commit failed")
        return root

    def run_check(self, root, *extra):
        return subprocess.run([sys.executable, str(CHECK), "--repo", root, *extra],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def findings(self, root, *extra):
        """The set of (rule, path, line) rows reported by one checker run."""
        proc = self.run_check(root, *extra)
        found = set()
        for row in proc.stdout.splitlines():
            parts = row.split("\t")
            if len(parts) == 3 and parts[2].isdigit():
                found.add((parts[0], parts[1], int(parts[2])))
        return found

    def link_lines(self, root, path="docs/live.md"):
        return sorted(line for rule, found, line in self.findings(root)
                      if found == path and rule in ("dead-link", "bad-link"))

    def test_inline_resolution_and_closed_grammar(self):
        live = "\n".join([
            "[a](real.md)",
            "[b](../root.md)",
            "[c](/root.md)",
            "[d](sub)",
            "[e](missing.md)",
            "[f](real.md \"Title\")",
            "[g](https://example.com)",
            "[h](#frag)",
            "mail <https://example.com> here",
            "[i](<foo.md>)",
            "[j](unclosed",
            "[k](real%2Emd)",
            "[l](real%zz.md)",
            "[m](../../x.md)",
            "[n](missing.md#frag)",
            "[o](/../root.md)",
            "[p](/%2e%2e/root.md)",
            "[q](/docs/../../root.md)",
            "[r](https://example.invalid/%zz)",
            "[s](https://example.invalid/%FF)",
            "[t](missing%3Afile.md)",
            "[u](<https://example.com>)",
            "[v](<https://example.invalid>missing.md)",
            "",
        ]) + "\n"
        root = self.make_repo(dict(self.FILES, **{"docs/live.md": live}))
        self.assertEqual(self.link_lines(root),
                         [5, 10, 11, 13, 14, 15, 16, 17, 18, 21, 23])

    def test_reference_definitions_are_checked(self):
        live = "\n".join([
            "[r]: real.md",
            "[r]: missing.md",
            "[s]: https://example.com",
            "[t]: <https://example.invalid>missing.md",
            "[v]: <https://example.com>",
            "see [x][r] for the usage form",
            "",
        ]) + "\n"
        root = self.make_repo(dict(self.FILES, **{"docs/live.md": live}))
        self.assertEqual(self.link_lines(root), [2, 4])

    def test_plain_path_tokens_and_archive_marker(self):
        files = {
            "README.md": "history/ alone is fine here; prototype/ is not.\n",
            "docs/live.md": "\n".join([
                "docs/history/ is excluded",
                "closed records live in the private archive (docs/history/)",
                "upstream/ is an ignored checkout",
                "bare history/ inside docs",
                "",
            ]) + "\n",
        }
        root = self.make_repo(files, manifest="+ docs/\n+ README.md\n")
        found = self.findings(root)
        self.assertIn(("plain-path", "README.md", 1), found)
        self.assertEqual(sorted(line for rule, path, line in found
                                if rule == "plain-path" and path == "docs/live.md"),
                         [1, 4])

    def test_state_path_membership(self):
        state = "\n".join([
            "Plan: docs/real.md",
            "Excluded: docs/P0_AUDIT.md",
            "Top-level: root.md",
            "Bare unknown: missing.txt",
            "",
        ]) + "\n"
        files = dict(self.FILES, **{"STATE.md": state, "docs/P0_AUDIT.md": "audit\n"})
        root = self.make_repo(
            files, manifest="+ docs/\n+ root.md\n+ STATE.md\n- docs/P0_AUDIT.md\n")
        self.assertEqual(self.findings(root), {("state-path", "STATE.md", 2)})

    def test_generator_matches_independent_oracle(self):
        prefixes = ["", "real.md", "missing.md", "sub/deep.md", "sub", "/docs/",
                    "../root.md", "../..", "a%20b.md", "%zz.md", "real%2Emd",
                    "/../root.md", "/%2e%2e/root.md", "/docs/../../root.md",
                    "https://example.invalid/%zz", "missing%3Afile.md",
                    "<https://example.invalid>", "<https://example.invalid>missing.md",
                    "<foo.md>"]
        separators = ["", "#f", "?q=1", "%20"]
        suffixes = ["", "/"]
        cases = [prefix + separator + suffix for prefix in prefixes
                 for separator in separators for suffix in suffixes]
        self.assertLessEqual(len(cases), 500)
        exported = {"docs/live.md", "docs/real.md", "docs/sub/deep.md", "root.md"}
        live = "\n".join("[x](%s)" % case for case in cases) + "\n"
        root = self.make_repo(dict(self.FILES, **{"docs/live.md": live}))
        expected = sorted(index for index, case in enumerate(cases, 1)
                          if oracle_finding("docs", case, exported))
        self.assertEqual(self.link_lines(root), expected)

    def test_named_history_anchor(self):
        """main e9bbf45: docs/TERMINAL_UX_BRIEF.md links into the excluded history."""
        repo = str(Path(__file__).resolve().parents[1])
        probe = subprocess.run(["git", "-C", repo, "rev-parse", "--verify",
                                "e9bbf45^{commit}"], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        if probe.returncode != 0:
            self.skipTest("the historical commit e9bbf45 is not available")
        found = self.findings(repo, "--commit", "e9bbf45")
        self.assertTrue(
            any(path == "docs/TERMINAL_UX_BRIEF.md"
                and rule in ("dead-link", "plain-path") for rule, path, _ in found),
            "the historical TERMINAL_UX_BRIEF.md finding is missing")


class LinuxTestHostTest(unittest.TestCase):
    """S-3: devtools/linux-test.sh resolves the test host only at runtime.

    Interpretation notes (recorded here because the worker summary never
    reaches the reviewers): "blank after stripping" means empty after trimming
    leading and trailing whitespace, and the destination is the trimmed value
    from either source; a config file that is missing, unreadable or holds only
    blank lines exits 2 with a single diagnostic naming both sources and never
    calls ssh.  Fixtures use synthetic host names and a stub ``ssh`` on PATH
    that records its argv; the script is expected to fail after that first
    remote call, which is irrelevant to the assertions.  Repair class checked
    here: trimming covers the *ends* of the whole value of ``ZPLAN_TEST_HOST``,
    so a value wrapped in newlines or CRLF reaches ssh as the host alone while
    an inner character (``synth\\rhost``) is preserved from both sources; and a
    source that is not a regular readable file (a directory, an unreadable or
    missing path) produces the single-line diagnostic rather than a shell read
    error next to it.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zs-host-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = os.path.join(self.tmp, "home")
        self.config_dir = os.path.join(self.home, ".config", "zplan-dev")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, "test-host")
        self.log = os.path.join(self.tmp, "ssh.log")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        stub = os.path.join(self.bin, "ssh")
        with open(stub, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nprintf '%s\\n' \"$@\" >> \"$SSH_LOG\"\nexit 1\n")
        os.chmod(stub, 0o755)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.write(self.repo, "file.txt", "x\n")
        self.git(self.repo, "init", "-q")
        self.git(self.repo, "add", "-A")
        self.git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x")

    def git(self, root, *args):
        return subprocess.run(["git", "-C", root, *args], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)

    def write(self, root, rel, content):
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(content)
        return full

    def config(self, content=None, mode=None):
        if content is not None:
            with open(self.config_path, "w", encoding="utf-8") as handle:
                handle.write(content)
        if mode is not None:
            os.chmod(self.config_path, mode)

    def run_script(self, host=None):
        env = dict(os.environ)
        env["HOME"] = self.home
        env["SSH_LOG"] = self.log
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        env.pop("ZPLAN_TEST_HOST", None)
        if host is not None:
            env["ZPLAN_TEST_HOST"] = host
        return subprocess.run([str(LINUX_TEST)], cwd=self.repo, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def recorded(self):
        if not os.path.exists(self.log):
            return []
        # newline="": universal-newline translation would turn a carriage
        # return inside one recorded argument into a line break.
        with open(self.log, encoding="utf-8", newline="") as handle:
            text = handle.read()
        # Split on newlines only: the stub writes one argument per line, and
        # str.splitlines would also break on a carriage return inside one.
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return lines

    def assert_destination(self, host):
        argv = self.recorded()
        self.assertTrue(argv, "the stub ssh recorded no call")
        self.assertEqual(argv[0], host)

    def test_environment_wins_over_file(self):
        self.config("filehost\n")
        self.run_script(host="envhost")
        self.assert_destination("envhost")

    def test_blank_environment_falls_to_file(self):
        self.config("filehost\n")
        self.run_script(host="   ")
        self.assert_destination("filehost")

    def test_file_without_trailing_newline(self):
        self.config("filehost")
        self.run_script()
        self.assert_destination("filehost")

    def test_file_leading_blank_lines(self):
        self.config("\n\n   \nfilehost\n")
        self.run_script()
        self.assert_destination("filehost")

    def test_multiline_environment_is_trimmed(self):
        self.config("filehost\n")
        self.run_script(host="\n \tenvhost\n\t")
        self.assertEqual(self.recorded(),
                         ["envhost", "mktemp -d ~/zplan-test-XXXXXX"])

    def test_carriage_return_environment_is_trimmed(self):
        self.config("filehost\n")
        self.run_script(host="\r\nenvhost\r\n")
        self.assert_destination("envhost")

    def test_carriage_return_file_line_is_trimmed(self):
        self.config("filehost\r\n")
        self.run_script()
        self.assert_destination("filehost")

    def test_environment_keeps_inner_characters(self):
        self.config("filehost\n")
        self.run_script(host="synth\rhost")
        self.assert_destination("synth\rhost")

    def test_file_keeps_inner_characters(self):
        self.config("synth\rhost\n")
        self.run_script()
        self.assert_destination("synth\rhost")

    def test_directory_instead_of_file_exits_two(self):
        os.makedirs(self.config_path)
        self.assert_no_host(self.run_script())

    def assert_no_host(self, proc):
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(self.recorded(), [], "ssh must not run without a host")
        self.assertIn("ZPLAN_TEST_HOST", proc.stderr)
        self.assertIn("zplan-dev/test-host", proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1, "one-line diagnostic")

    def test_missing_file_exits_two(self):
        self.assert_no_host(self.run_script())

    def test_blank_only_file_exits_two(self):
        self.config("\n  \n\n")
        self.assert_no_host(self.run_script())

    def test_unreadable_file_exits_two(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("running as root: file permissions are not enforced")
        self.config("filehost\n", mode=0)
        self.assert_no_host(self.run_script())

if __name__ == "__main__":
    unittest.main()
