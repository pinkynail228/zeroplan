"""A1/A2/A3/A6: `zplan update` and the one-command `install.sh`.

Every test builds a local bare repository with `vX.Y.Z` tags (through `ZPLAN_REPOSITORY`, no network) and an
isolated HOME/XDG/`ZEROSHOT_TOOLS`: nothing here reads or writes the runner's own state. The released tag's own
`install.py` is stubbed, so the tests pin *which* tag was fetched and that the launcher and the store are left
alone exactly when the release installer fails.

Interpretations recorded here for the reviewers:
- The task says update "copies runs" the new tag's `install.py`; read as "runs it" (the installer is run out of
  the shallow checkout, never copied over the installed app).
- "prints the backup path" (A6, failing installer) is read as the release installer's own output reaching the
  owner: `zplan update` runs it without capturing stdout, so whatever it printed — the store backup path — is
  visible; the backup itself is A4's job (tests/test_install.py), not update's.
- `--check` and a same-or-older newest tag are asserted to touch nothing by letting the released tag's stub write
  a marker into HOME and checking that no marker appears.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terminal_planner import update  # noqa: E402
import install  # noqa: E402

REPO_URL = "https://github.com/pinkynail228/zeroplan.git"


def run_git(*args, env=None):
    return subprocess.run(["git", *args], env=env, capture_output=True, text=True, check=True).stdout


def bare_repo(directory, releases):
    """A bare repository with one commit and one lightweight tag per (tag, install.py text)."""
    work = directory / "work"
    work.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.com")
    run_git("init", "-q", str(work), env=env)
    for tag, body in releases:
        (work / "install.py").write_text("#!/usr/bin/env python3\n" + body)
        run_git("-C", str(work), "add", "install.py", env=env)
        run_git("-C", str(work), "commit", "-q", "--allow-empty", "-m", tag, env=env)
        run_git("-C", str(work), "tag", tag, env=env)
    bare = directory / "repo.git"
    run_git("clone", "-q", "--bare", str(work), str(bare), env=env)
    return bare


def tool_path(directory, *names):
    """A PATH directory holding symlinks to only `names` (resolved from the current PATH), so a test can run
    `install.sh` with exactly `git` and `python3` present and prove how it reports a `zplan setup` that needs
    Node.js/npm (A2)."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        found = shutil.which(name)
        assert found, "not on PATH: " + name
        (directory / name).symlink_to(found)
    return str(directory)

def store(home):
    """The production store, exactly as terminal_planner.authority.production_root() lays it out for this OS."""
    base = home / ("Library/Application Support" if sys.platform == "darwin" else ".local/state")
    return base / "PlanningKit/production/v3"


def run_cli(home, *argv, repo, tools=None, extra=None):
    environment = dict(os.environ, HOME=str(home), PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1",
                       PYTHONUTF8="1", TERM="dumb", ZPLAN_REPOSITORY=str(repo))
    environment.pop("ZPLAN_VERSION", None)
    environment.pop(install.SETUP_FOLLOWS, None)  # never inherit the signal: a caller must set it itself
    if tools is not None:
        environment["ZEROSHOT_TOOLS"] = str(tools)
    else:
        environment.pop("ZEROSHOT_TOOLS", None)
    environment.update(extra or {})
    return subprocess.run([sys.executable, "-m", "terminal_planner.cli", *argv], capture_output=True, text=True,
                          env=environment, timeout=180)


class VersionSelectionTests(unittest.TestCase):
    """A6: the newest tag wins numerically, non-version tags are not releases."""

    def test_versions_sort_numerically_and_ignore_other_tags(self):
        output = ("a\trefs/tags/v0.9.0\n"
                  "b\trefs/tags/v0.10.0\n"
                  "c\trefs/tags/v0.10.0^{}\n"
                  "d\trefs/tags/nightly\n"
                  "e\trefs/tags/v0.10\n"
                  "f\trefs/tags/release-1.0.0\n"
                  "g\trefs/tags/v2.0.0-beta\n")
        self.assertEqual(update.versions(output), ["0.9.0", "0.10.0"])
        self.assertLess(update.version_tuple("0.9.0"), update.version_tuple("0.10.0"))

    def test_a_namespaced_tag_is_not_a_release(self):
        """A6/A3 regression: a tag whose reference is `refs/tags/archive/v9.9.9` is not a release `9.9.9`.
        `git ls-remote` reports the whole reference; matching only its last path component selected the namespaced
        tag, so `--check` named 9.9.9 and `update` tried to clone the nonexistent `v9.9.9`."""
        output = ("a\trefs/tags/v0.6.0\n"
                  "b\trefs/tags/archive/v9.9.9\n")
        self.assertEqual(update.versions(output), ["0.6.0"])

    def test_a_namespaced_tag_is_ignored_against_a_real_repository(self):
        """A6/A3 regression, end to end: a local bare repo with `v0.5.0` and `archive/v9.9.9` reports 0.5.0 as
        the newest release, so `--check` never names the namespaced tag and update is a no-op, not a clone of a
        tag that does not exist."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home = root / "home"
            home.mkdir()
            repo = bare_repo(root, [("v0.5.0", "pass\n"), ("archive/v9.9.9", "pass\n")])
            self.assertEqual(update.remote_versions(str(repo)), ["0.5.0"])
            result = run_cli(home, "update", "--check", repo=repo, tools=home / "tools")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("9.9.9", result.stdout)

    def test_the_repository_is_named_once_and_overridable(self):
        self.assertEqual(update.REPOSITORY, REPO_URL)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ZPLAN_REPOSITORY", None)
            self.assertEqual(update.repository(), REPO_URL)
        with mock.patch.dict(os.environ, {"ZPLAN_REPOSITORY": "/local/repo.git"}):
            self.assertEqual(update.repository(), "/local/repo.git")
        self.assertIn("ZPLAN_REPOSITORY", (ROOT / "install.sh").read_text(encoding="utf-8"))

    def test_remote_versions_reads_the_bare_repo_and_keeps_only_version_tags(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = bare_repo(Path(temp).resolve(), [("v0.9.0", "pass\n"), ("v0.10.0", "pass\n"),
                                                    ("nightly", "pass\n")])
            self.assertEqual(update.remote_versions(str(repo)), ["0.9.0", "0.10.0"])

    def test_a_repository_that_cannot_be_read_is_an_act_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(update.UpdateError):
                update.remote_versions(str(Path(temp).resolve() / "missing.git"))


class CheckTests(unittest.TestCase):
    """A3: `--check` prints both versions and changes nothing."""

    def test_check_prints_the_current_and_newest_version_without_touching_anything(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp).resolve() / "home"
            home.mkdir()
            repo = bare_repo(Path(temp).resolve(), [("v0.5.0", "pass\n"),
                                                    ("v0.6.0", 'import os, pathlib\npathlib.Path(os.environ["HOME"], "ran").write_text("x")\n')])
            result = run_cli(home, "update", "--check", repo=repo, tools=home / "tools")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(update.__version__, result.stdout)
            self.assertIn("0.6.0", result.stdout)
            self.assertFalse((home / "ran").exists())  # the released tag's installer never ran
            self.assertEqual(list(home.iterdir()), [])

    def test_update_with_nothing_newer_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp).resolve() / "home"
            home.mkdir()
            repo = bare_repo(Path(temp).resolve(), [("v0.1.0", 'import os, pathlib\npathlib.Path(os.environ["HOME"], "ran").write_text("x")\n')])
            result = run_cli(home, "update", repo=repo, tools=home / "tools")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already the newest", result.stdout)
            self.assertFalse((home / "ran").exists())
            self.assertEqual(list(home.iterdir()), [])


class FailedReleaseTests(unittest.TestCase):
    """A3/A6: a release installer that fails leaves the launcher and the store untouched and its output — the
    backup path — is what the owner sees."""

    def test_a_failing_release_installer_keeps_the_launcher_and_the_store_and_prints_the_backup_line(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools = root / "home", root / "tools"
            (tools / "bin").mkdir(parents=True)
            old_app = root / "app/0.4.0/bin"
            old_app.mkdir(parents=True)
            (old_app / "zplan").write_text("#!/bin/sh\necho zplan 0.4.0\n")
            launcher = tools / "bin/zplan"
            launcher.symlink_to(old_app / "zplan")
            before = launcher.resolve()
            backup = home / "v3.backup-0.5.0-20260101T000000Z"
            repo = bare_repo(root, [("v9.9.9", 'import os, pathlib, sys\n'
                                              'pathlib.Path(os.environ["HOME"], "ran").write_text("yes")\n'
                                              'print("Store backup: %s" % pathlib.Path(os.environ["HOME"], "v3.backup-0.5.0-20260101T000000Z"))\n'
                                              'sys.exit(1)\n')])
            made = store(home)
            made.mkdir(parents=True)
            (made / "planning.json").write_text("original")
            result = run_cli(home, "update", repo=repo, tools=tools)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("Store backup: " + str(backup), result.stdout)  # the installer's own line reaches the owner
            self.assertEqual(launcher.resolve(), before)  # the launcher did not move
            self.assertEqual((made / "planning.json").read_text(), "original")
            self.assertTrue((home / "ran").exists())  # the release installer did run, then failed



class SuccessfulUpdateTests(unittest.TestCase):
    """A3: a newer release is installed by its own install.py and then `zplan setup` runs; the new version and the
    rollback line are printed."""

    def test_update_installs_the_newest_tag_then_runs_setup_and_prints_the_new_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools = root / "home", root / "tools"
            (tools / "bin").mkdir(parents=True)
            home.mkdir()
            repo = bare_repo(root, [("v0.5.0", "pass\n"), ("v9.9.9", "pass\n")])
            launcher = tools / "bin/zplan"
            launcher.write_text('#!/bin/sh\nprintf "setup\\n" >> "$(dirname "$0")/../setup.log"\n')
            launcher.chmod(0o755)
            result = run_cli(home, "update", repo=repo, tools=tools)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("zplan updated to 9.9.9", result.stdout)
            self.assertIn("Rollback", result.stdout)  # the rollback line names the previous version and the store copy
            self.assertIn(update.__version__, result.stdout)
            self.assertEqual((tools / "setup.log").read_text(), "setup\n")

    def test_update_expands_a_tilde_in_zeroshot_tools_before_running_setup(self):
        """A3 regression: `ZEROSHOT_TOOLS=~/zplan-tools` is a supported configuration, and `install.py` expands
        it (`Path(...).expanduser()`). `update.launcher()` must resolve the launcher the same way; a literal `~`
        reaches `subprocess` unexpanded, so setup would fail after the swap with "no such file".

        Interpretation: only the leading `~` / `~/` is expanded, exactly as `Path.expanduser()` and the `sh` branch
        in install.sh do; a `~user` form is not part of the supported configuration the task names."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home = root / "home"
            home.mkdir()
            launcher = home / "tools/bin/zplan"
            launcher.parent.mkdir(parents=True)
            launcher.write_text('#!/bin/sh\nprintf "setup\\n" >> "$(dirname "$0")/../setup.log"\n')
            launcher.chmod(0o755)
            repo = bare_repo(root, [("v0.5.0", "pass\n"), ("v9.9.9", "pass\n")])
            result = run_cli(home, "update", repo=repo, tools="~/tools")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / "tools/setup.log").read_text(), "setup\n")


    def test_update_tells_the_release_installer_that_setup_follows(self):
        """A1/A3: `zplan update` runs `zplan setup` itself, so it passes `install.SETUP_FOLLOWS` to the release's
        install.py; without it that installer would print "...then zplan setup" and update would run setup right
        after — the confusion this task fixes."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools = root / "home", root / "tools"
            (tools / "bin").mkdir(parents=True)
            home.mkdir()
            stub = ('import os, pathlib\n'
                    'pathlib.Path(os.environ["HOME"], "signal").write_text(os.environ.get(%r, ""))\n'
                    % install.SETUP_FOLLOWS)
            repo = bare_repo(root, [("v0.5.0", "pass\n"), ("v9.9.9", stub)])
            launcher = tools / "bin/zplan"
            launcher.write_text("#!/bin/sh\nexit 0\n")
            launcher.chmod(0o755)
            result = run_cli(home, "update", repo=repo, tools=tools)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / "signal").read_text(), "1")


class InstallShTests(unittest.TestCase):
    """A2/A6: install.sh picks the newest tag, runs the release installer, then `zplan setup`, and cleans up."""

    def test_install_sh_picks_the_newest_tag_runs_setup_and_removes_its_temp_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools, tmp = root / "home", root / "tools", root / "tmp"
            (tools / "bin").mkdir(parents=True)
            tmp.mkdir()
            home.mkdir()
            marker = 'import os, pathlib\npathlib.Path(os.environ["HOME"], "picked").write_text(%r)\n'
            repo = bare_repo(root, [("v0.9.0", marker % "v0.9.0"), ("v0.10.0", marker % "v0.10.0"),
                                    ("nightly", marker % "nightly")])
            launcher = tools / "bin/zplan"
            launcher.write_text('#!/bin/sh\nprintf "setup\\n" >> "$(dirname "$0")/../setup.log"\n')
            launcher.chmod(0o755)
            environment = dict(os.environ, HOME=str(home), ZPLAN_REPOSITORY=str(repo), ZEROSHOT_TOOLS=str(tools),
                               TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
            environment.pop("ZPLAN_VERSION", None)
            result = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / "picked").read_text(), "v0.10.0")  # newest wins, `nightly` is not a release
            self.assertEqual((tools / "setup.log").read_text(), "setup\n")  # the launcher ran setup
            self.assertEqual(list(tmp.iterdir()), [])  # the temp checkout is gone on the success path

    def test_install_sh_removes_its_temp_dir_when_the_installer_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools, tmp = root / "home", root / "tools", root / "tmp"
            (tools / "bin").mkdir(parents=True)
            tmp.mkdir()
            home.mkdir()
            repo = bare_repo(root, [("v0.10.0", "import sys\nsys.exit(1)\n")])
            environment = dict(os.environ, HOME=str(home), ZPLAN_REPOSITORY=str(repo), ZEROSHOT_TOOLS=str(tools),
                               TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
            environment.pop("ZPLAN_VERSION", None)
            result = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(list(tmp.iterdir()), [])  # every exit path removes it

    def test_install_sh_without_tags_stops_with_one_message(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools, tmp = root / "home", root / "tools", root / "tmp"
            (tools / "bin").mkdir(parents=True)
            tmp.mkdir()
            home.mkdir()
            repo = bare_repo(root, [("nightly", "pass\n")])
            environment = dict(os.environ, HOME=str(home), ZPLAN_REPOSITORY=str(repo), ZEROSHOT_TOOLS=str(tools),
                               TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
            environment.pop("ZPLAN_VERSION", None)
            result = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(len([line for line in result.stderr.strip().splitlines() if line.strip()]), 1)
            self.assertIn("no vX.Y.Z releases", result.stderr)

    def test_install_sh_reports_a_missing_tool_in_one_line(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp).resolve() / "home"
            home.mkdir()
            environment = dict(os.environ, HOME=str(home), PATH="", TMPDIR=str(home))
            result = subprocess.run(["/bin/sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(len(result.stderr.strip().splitlines()), 1)
            self.assertIn("git", result.stderr)

    def test_install_sh_honours_zplan_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools, tmp = root / "home", root / "tools", root / "tmp"
            (tools / "bin").mkdir(parents=True)
            tmp.mkdir()
            home.mkdir()
            marker = 'import os, pathlib\npathlib.Path(os.environ["HOME"], "picked").write_text(%r)\n'
            repo = bare_repo(root, [("v0.9.0", marker % "v0.9.0"), ("v0.10.0", marker % "v0.10.0")])
            launcher = tools / "bin/zplan"
            launcher.write_text("#!/bin/sh\nexit 0\n")
            launcher.chmod(0o755)
            environment = dict(os.environ, HOME=str(home), ZPLAN_REPOSITORY=str(repo), ZEROSHOT_TOOLS=str(tools),
                               TMPDIR=str(tmp), ZPLAN_VERSION="0.9.0", PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / "picked").read_text(), "v0.9.0")

    def test_install_sh_expands_a_tilde_in_zeroshot_tools(self):
        """A2 regression: `ZEROSHOT_TOOLS=~/zplan-tools` is supported and `install.py` expands it, but a shell
        variable keeps the literal `~`, which `subprocess`/`exec` does not expand. install.sh must resolve the
        launcher path the same way install.py does, or `setup` after the install fails."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tmp = root / "home", root / "tmp"
            tmp.mkdir()
            home.mkdir()
            launcher = home / "tools/bin/zplan"
            launcher.parent.mkdir(parents=True)
            launcher.write_text('#!/bin/sh\nprintf "setup\\n" >> "$(dirname "$0")/../setup.log"\n')
            launcher.chmod(0o755)
            repo = bare_repo(root, [("v0.10.0", "pass\n")])
            environment = dict(os.environ, HOME=str(home), ZPLAN_REPOSITORY=str(repo), ZEROSHOT_TOOLS="~/tools",
                               TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
            environment.pop("ZPLAN_VERSION", None)
            result = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / "tools/setup.log").read_text(), "setup\n")  # the literal ~ was expanded

    def test_install_sh_fails_when_setup_cannot_complete_without_node(self):
        """A2 prerequisite contract (repair): the one command is complete only when `zplan setup` succeeded.

        The engine's `zplan setup` runs `npm ci` and requires Node.js >= 16 with npm (terminal_planner/setup.py,
        outside this task's write-set; `zplan login` needs the Codex it installs). A2's wording "needs only `git`
        and `python3`" therefore cannot deliver a *working* zplan on its own. That conflict is escalated to the
        owner rather than waived: `install.sh` still fetches and installs with git and python3 alone, but a setup
        that cannot run is a failure of the one command — it never reports a half-ready install. Interpretations
        recorded here: A2's "runs `<launcher> setup`" = the command completes setup itself and fails if it cannot;
        the owner finishes with `zplan setup` after providing Node.js.

        Regression: with git, python3 and the shell utilities on PATH and node/npm deliberately absent, install.sh
        exits non-zero, its single `zplan:` line names Node.js, npm and the launcher, and the temp checkout is
        removed on this exit path too. Asserting exit 0 here was the review finding (R1)."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools, tmp, bin = root / "home", root / "tools", root / "tmp", root / "bin"
            (tools / "bin").mkdir(parents=True)
            tmp.mkdir()
            home.mkdir()
            launcher = tools / "bin/zplan"
            launcher.write_text("#!/bin/sh\nexit 1\n")  # a setup that fails, saying nothing itself
            launcher.chmod(0o755)
            repo = bare_repo(root, [("v0.10.0", "pass\n")])
            # git, python3 and the shell utilities install.sh uses, deliberately without node/npm
            path = tool_path(bin, "git", "python3", "sed", "sort", "tail", "mktemp", "rm", "sh")
            environment = dict(os.environ, HOME=str(home), PATH=path, ZPLAN_REPOSITORY=str(repo),
                               ZEROSHOT_TOOLS=str(tools), TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
            environment.pop("ZPLAN_VERSION", None)
            result = subprocess.run(["/bin/sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            self.assertNotEqual(result.returncode, 0)  # setup did not complete: the one command failed
            self.assertEqual(result.stdout, "")
            ours = [line for line in result.stderr.splitlines() if line.startswith("zplan:")]
            self.assertEqual(len(ours), 1)  # one clear line, not a bare "setup failed"
            for needed in ("Node.js", "npm", str(launcher)):
                self.assertIn(needed, ours[0])
            self.assertEqual(list(tmp.iterdir()), [])  # the temp checkout is removed on this exit path too

    def test_install_sh_signals_setup_follows_and_ends_with_the_login_step(self):
        """A1/A2/A3: install.sh passes `install.SETUP_FOLLOWS` to the release's install.py, and, setup having
        succeeded, ends with exactly one line naming `zplan login`; when the launcher directory is not on PATH
        that line carries the `export PATH=...` that puts it there.

        Interpretation recorded here: "the PATH export" is printed as the shell statement the owner would run,
        the same form docs/INSTALLATION.md uses after the one command; the line always names `zplan login` as
        the next step."""
        def run(on_path):
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            root = Path(temp.name).resolve()
            home, tools, tmp = root / "home", root / "tools", root / "tmp"
            (tools / "bin").mkdir(parents=True)
            tmp.mkdir()
            home.mkdir()
            stub = ('import os, pathlib\n'
                    'pathlib.Path(os.environ["HOME"], "signal").write_text(os.environ.get(%r, ""))\n'
                    % install.SETUP_FOLLOWS)
            repo = bare_repo(root, [("v0.10.0", stub)])
            launcher = tools / "bin/zplan"
            launcher.write_text("#!/bin/sh\nexit 0\n")
            launcher.chmod(0o755)
            path = str(tools / "bin") + os.pathsep + os.environ["PATH"] if on_path else os.environ["PATH"]
            environment = dict(os.environ, HOME=str(home), PATH=path, ZPLAN_REPOSITORY=str(repo),
                               ZEROSHOT_TOOLS=str(tools), TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
            environment.pop("ZPLAN_VERSION", None)
            environment.pop("ZPLAN_SETUP_FOLLOWS", None)
            result = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            return root, tools, result

        for on_path in (False, True):
            with self.subTest(on_path=on_path):
                root, tools, result = run(on_path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / "home" / "signal").read_text(), "1")  # install.py was told setup follows
                lines = [line for line in result.stdout.splitlines() if line.strip()]
                self.assertEqual(len(lines), 1)  # A2: one closing line, not a message per tool
                self.assertIn("zplan login", lines[-1])
                if on_path:
                    self.assertNotIn("export PATH", lines[-1])  # already on PATH: no export needed
                else:
                    self.assertIn('export PATH="%s:$PATH"' % (tools / "bin"), lines[-1])  # off PATH: the export

    def test_install_sh_still_fails_when_setup_fails_with_node_present(self):
        """A2 repair companion: the non-zero exit is not specific to the missing-Node.js hint. With Node.js/npm on
        PATH a failing `zplan setup` is also a failure of the one command, and its one clear line points at
        re-running setup instead of blaming Node.js, which is present."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            home, tools, tmp, bin = root / "home", root / "tools", root / "tmp", root / "bin"
            (tools / "bin").mkdir(parents=True)
            tmp.mkdir()
            home.mkdir()
            launcher = tools / "bin/zplan"
            launcher.write_text("#!/bin/sh\nexit 1\n")
            launcher.chmod(0o755)
            repo = bare_repo(root, [("v0.10.0", "pass\n")])
            path = tool_path(bin, "git", "python3", "sed", "sort", "tail", "mktemp", "rm", "sh", "true")
            (bin / "node").symlink_to(shutil.which("true"))  # present on PATH, so setup must succeed to install
            (bin / "npm").symlink_to(shutil.which("true"))
            environment = dict(os.environ, HOME=str(home), PATH=path, ZPLAN_REPOSITORY=str(repo),
                               ZEROSHOT_TOOLS=str(tools), TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE="1")
            environment.pop("ZPLAN_VERSION", None)
            result = subprocess.run(["/bin/sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env=environment, timeout=180)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            ours = [line for line in result.stderr.splitlines() if line.startswith("zplan:")]
            self.assertEqual(len(ours), 1)
            self.assertNotIn("Node.js", ours[0])  # node/npm are present: do not send the owner after them
            self.assertIn(str(launcher), ours[0])
            self.assertEqual(list(tmp.iterdir()), [])  # still cleaned up on this exit path


if __name__ == "__main__":
    unittest.main()
