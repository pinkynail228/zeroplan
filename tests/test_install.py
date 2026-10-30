"""Installed-app gate: install offline into a temporary HOME, then use only the installed copy.

Needs ZPLAN_TEST_WHEELHOUSE (setuptools 75.8.0, wheel 0.45.1 and the closure of textual 8.2.8). Without it these
tests skip; with it, missing wheels or a failed build/install fail the gate.
"""

import hashlib
import io
import contextlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install  # noqa: E402
from terminal_planner import __version__  # noqa: E402

WHEELHOUSE = os.environ.get("ZPLAN_TEST_WHEELHOUSE")
WHEELS = ("setuptools-75.8.0-py3-none-any.whl", "wheel-0.45.1-py3-none-any.whl", "textual-8.2.8-py3-none-any.whl")
PLAN = "p\nRequested feature\n\ng\n"
START, MERGE = "g\ny\n", "m\ny\n"


def tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else os.readlink(p)
            for p in sorted(root.rglob("*")) if p.is_file() or p.is_symlink()}


class VersionTests(unittest.TestCase):
    def test_installer_package_and_project_versions_agree(self):
        project = (ROOT / "pyproject.toml").read_text()
        self.assertIn('\nversion = "%s"\n' % __version__, project)
        self.assertEqual(install.VERSION, __version__)
        self.assertEqual(install.VERSION, "0.9.0")
        self.assertIn("0.4.0", install.OWNED)  # the 0.9.0 installer keeps recognising the 0.4.0 launcher as ours
        self.assertIn("0.6.0", install.OWNED)  # and the 0.6.0 launcher too
        self.assertIn("0.6.1", install.OWNED)  # and the 0.6.1 launcher too
        self.assertIn("0.6.2", install.OWNED)  # and the 0.6.2 launcher
        self.assertIn("0.6.3", install.OWNED)  # and the 0.6.3 launcher
        self.assertIn("0.7.0", install.OWNED)  # and the 0.7.0 launcher
        self.assertIn("0.8.0", install.OWNED)  # and the 0.8.0 launcher
        self.assertIn("0.8.1", install.OWNED)  # and the 0.8.1 launcher
        self.assertIn("0.8.2", install.OWNED)  # and the 0.8.2 launcher
        self.assertIn("0.8.3", install.OWNED)  # and the 0.8.3 launcher
        self.assertEqual(install.OWNED[-1], install.VERSION)
        self.assertIn("0.5.0", install.OWNED)  # and the 0.5.0 launcher too
        self.assertIn("0.5.1", install.OWNED)  # and the 0.5.1 launcher too
        self.assertIn("0.5.2", install.OWNED)  # and the 0.5.2 launcher too
        self.assertIn("0.3.1", install.OWNED)  # and the 0.3.1 launcher too
        self.assertIn(install.VERSION, install.OWNED)


class EnsurePythonTests(unittest.TestCase):
    """install.py needs Python 3.11: an older interpreter hands over to the newest of python3.13/3.12/3.11 on PATH."""

    def shims(self, *names):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name).resolve()
        for name in names:
            (directory / name).write_text('#!/bin/sh\necho "re-exec: $0 $*"\n')
            (directory / name).chmod(0o755)
        return directory

    def run_ensure(self, path, version, argv=("--wheelhouse", "w")):
        with patch.dict(os.environ, {"PATH": str(path)}), patch.object(install.os, "execv") as execv:
            execv.side_effect = SystemExit(77)  # execv never returns
            try:
                install.ensure_python(list(argv), version)
            except SystemExit as stop:
                return stop, execv
            return None, execv

    def test_current_interpreter_is_left_alone(self):
        for version in ((3, 11), (3, 13), (4, 0)):
            stop, execv = self.run_ensure(self.shims("python3.13"), version)
            self.assertIsNone(stop)
            execv.assert_not_called()
        self.assertEqual(install.MINIMUM, (3, 11))

    def test_old_interpreter_re_executes_with_the_newest_one_on_path(self):
        directory = self.shims("python3.11", "python3.12", "python3.13")
        stop, execv = self.run_ensure(directory, (3, 9))
        self.assertEqual(stop.code, 77)
        executable, argv = execv.call_args[0]
        self.assertEqual(Path(executable), directory / "python3.13")
        self.assertEqual(argv[0], executable)
        self.assertEqual(Path(argv[1]), Path(install.__file__).resolve())
        self.assertEqual(argv[2:], ["--wheelhouse", "w"])  # the arguments travel unchanged

    def test_older_candidates_are_used_in_order_and_3_10_is_too_old(self):
        stop, execv = self.run_ensure(self.shims("python3.11", "python3.12"), (3, 10))
        self.assertEqual(Path(execv.call_args[0][0]).name, "python3.12")
        stop, execv = self.run_ensure(self.shims("python3.11"), (3, 10))
        self.assertEqual(Path(execv.call_args[0][0]).name, "python3.11")

    def test_no_new_interpreter_stops_with_a_message_naming_python_3_11(self):
        stop, execv = self.run_ensure(self.shims(), (3, 9))
        execv.assert_not_called()
        self.assertIn("Python 3.11", str(stop.code))
        self.assertIn("3.9", str(stop.code))

    def test_main_checks_the_interpreter_before_touching_anything(self):
        marker = self.shims()
        with patch.object(install, "ensure_python", side_effect=SystemExit("old")) as ensure, \
                patch.object(install.venv.EnvBuilder, "create") as create, \
                patch.dict(os.environ, {"XDG_DATA_HOME": str(marker)}):
            with self.assertRaises(SystemExit):
                install.main(["--wheelhouse", str(marker)])
        ensure.assert_called_once_with(["--wheelhouse", str(marker)])
        create.assert_not_called()
        self.assertEqual(list(marker.iterdir()), [])

    def test_real_process_with_an_old_version_hands_over_to_the_shim_on_path(self):
        """The whole chain through a real exec: a process that reports 3.9 runs install.py, which replaces itself
        with python3.13 from PATH on the same script and arguments (the shim prints what it was given)."""
        directory = self.shims("python3.13")
        launcher = ("import runpy, sys; sys.version_info = (3, 9, 18, 'final', 0); "
                    "sys.argv = [sys.argv[1], '--wheelhouse', 'offline']; runpy.run_path(sys.argv[0], run_name='__main__')")
        result = subprocess.run([sys.executable, "-c", launcher, str(ROOT / "install.py")], capture_output=True, text=True,
                                timeout=60, env=dict(os.environ, PATH=str(directory), PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(),
                         "re-exec: %s %s --wheelhouse offline" % (directory / "python3.13", ROOT / "install.py"))


class PackageDataTests(unittest.TestCase):
    def test_a11_package_data_ships_every_packaged_resource_kind(self):
        """A11 C3 (the wheel member set itself is `InstalledGateTests`'): every file kind under `resources/` is
        named by a package-data glob, the architect method's `.md` included."""
        import tomllib
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]
        globs = set(data["terminal_planner"])
        kinds = {path.suffix for path in (ROOT / "terminal_planner/resources").iterdir() if path.is_file()}
        self.assertIn(".md", kinds)
        self.assertEqual({"resources/*" + kind for kind in kinds}, globs)


class PathMessageTests(unittest.TestCase):
    """The closing line asks for a PATH change only when the launcher directory is not on PATH yet."""

    def test_missing_directory_asks_to_add_it(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp).resolve() / "bin"
            line = install.installed_message(bin_dir / "zplan", bin_dir, os.pathsep.join(["/usr/bin", "", "/nonexistent"]))
        self.assertIn("Add " + str(bin_dir) + " to PATH", line)
        self.assertIn("zplan setup", line)

    def test_setup_follows_never_names_zplan_setup(self):
        """A1/A3 regression: the callers that run `zplan setup` themselves (`install.sh`, `zplan update`) pass
        `ZPLAN_SETUP_FOLLOWS`; the closing line must then not send the owner to `zplan setup` again — `zplan
        login` is the next step — while it still names the PATH change when the directory is not on PATH.

        Interpretation recorded here: the setup-follows variant names `zplan login` (the step the owner actually
        runs next) rather than dropping the next-step sentence altogether; A1 only forbids `zplan setup`."""
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp).resolve() / "bin"
            off_path = os.pathsep.join(["/usr/bin", "", "/nonexistent"])
            on_path = os.pathsep.join(["/usr/bin", str(bin_dir)])
            on = install.installed_message(bin_dir / "zplan", bin_dir, on_path, setup_follows=True)
            off = install.installed_message(bin_dir / "zplan", bin_dir, off_path, setup_follows=True)
            for line in (on, off):
                self.assertNotIn("zplan setup", line)
                self.assertIn("zplan login", line)
            self.assertIn("The zplan command is ready", on)
            self.assertIn("Add " + str(bin_dir) + " to PATH", off)

    def test_a_manual_run_keeps_naming_zplan_setup(self):
        """A1/A3: without the signal (a plain `python3 install.py`) the closing line is today's, naming
        `zplan setup` and not `zplan login`."""
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp).resolve() / "bin"
            line = install.installed_message(bin_dir / "zplan", bin_dir, os.pathsep.join(["/usr/bin", str(bin_dir)]))
        self.assertIn("zplan setup", line)
        self.assertNotIn("zplan login", line)

    def test_directory_on_path_says_the_command_is_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp).resolve() / "bin"
            bin_dir.mkdir()
            alias = Path(temp) / "alias"
            alias.symlink_to(bin_dir)
            for entry in (str(bin_dir), str(alias), str(bin_dir) + "/../bin"):
                with self.subTest(entry):
                    line = install.installed_message(bin_dir / "zplan", bin_dir, os.pathsep.join(["/usr/bin", entry]))
                    self.assertNotIn("Add ", line)
                    self.assertIn("The zplan command is ready", line)
                    self.assertIn("zplan setup", line)


class StoreProbeTests(unittest.TestCase):
    """A4 regression: `install.store_root()` asks the package *installed in the new venv*, never a checkout the
    installer happens to run inside.

    `install.py` runs from inside a zplan checkout on the manual route, when `install.sh`/`zplan update` re-run it,
    and in normal dogfooding; a plain `python -c` probe there imports the checkout's
    `terminal_planner.authority` and returns the wrong store (found during review). The probe therefore runs with
    `-I`: this test keeps a decoy copy in the working directory *and* in `PYTHONPATH` while a real (pip-less) venv
    carries the installed copy in its site-packages, so only an isolated probe answers with the installed path.
    Dropping `-I` makes the decoy win and fails the test.

    Interpretation: the caller's `HOME`/`XDG_*` still select *which* store is reported — only the imports are
    isolated — so `-I` isolates the module search, not the environment the store path is computed from.
    """

    @staticmethod
    def package(site, answer):
        """A `terminal_planner.authority` whose `production_root()` returns `answer`, laid out as installed."""
        package = site / "terminal_planner"
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("")
        (package / "authority.py").write_text(
            "from pathlib import Path\n\n\ndef production_root():\n    return Path(%r)\n" % answer)
        return package

    def test_the_probe_reads_the_installed_venv_not_an_importable_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            environment = install.venv.EnvBuilder(with_pip=False, symlinks=True)
            environment.create(root / "app/0.7.0")
            (site,) = (root / "app/0.7.0").glob("lib/python3.*/site-packages")
            installed = root / "installed-store"
            self.package(site, str(installed))
            decoy = root / "checkout"
            self.package(decoy, str(root / "decoy-store"))
            python = root / "app/0.7.0/bin/python"
            previous = os.getcwd()
            os.chdir(decoy)  # the installer ran from the checkout: the probe must not inherit its directory
            try:
                with patch.dict(os.environ, {"PYTHONPATH": str(decoy), "HOME": str(root / "home")}):
                    self.assertEqual(install.store_root(python), installed)
            finally:
                os.chdir(previous)


@unittest.skipUnless(WHEELHOUSE, "ZPLAN_TEST_WHEELHOUSE is not set: the installed-app gate needs an offline wheelhouse "
                                 "(setuptools 75.8.0, wheel 0.45.1, textual 8.2.8 with dependencies)")
class InstalledGateTests(unittest.TestCase):
    """One offline install per class; every later step runs from an unrelated project without the checkout."""

    @classmethod
    def setUpClass(cls):
        cls.wheelhouse = Path(WHEELHOUSE).expanduser().resolve()
        missing = [name for name in WHEELS if not (cls.wheelhouse / name).is_file()]
        if missing:
            raise AssertionError("ZPLAN_TEST_WHEELHOUSE=%s without %s" % (cls.wheelhouse, ", ".join(missing)))
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = root = Path(cls.temp.name).resolve()
        try:
            cls.prepare()
        except BaseException:
            cls.temp.cleanup()
            raise

    @classmethod
    def prepare(cls):
        root = cls.root
        # A copy of the sources: the build never writes into the checkout, and the checkout is not importable.
        cls.source = root / "src"
        shutil.copytree(ROOT / "terminal_planner", cls.source / "terminal_planner",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("pyproject.toml", "install.py"):
            shutil.copy2(ROOT / name, cls.source / name)
        cls.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root / "home"),
                   "XDG_DATA_HOME": str(root / "data"), "XDG_CONFIG_HOME": str(root / "config"),
                   "CODEX_HOME": str(root / "codex"), "ZEROSHOT_TOOLS": str(root / "tools"),
                   "TMPDIR": os.environ.get("TMPDIR", "/tmp"), "LANG": "C.UTF-8", "PIP_CONFIG_FILE": os.devnull,
                   "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1"}
        (root / "home").mkdir()
        cls.project = root / "unrelated project"
        cls.project.mkdir()
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "Gate"],
                     ["config", "user.email", "gate@example.invalid"], ["config", "commit.gpgsign", "false"]):
            cls.git(*args)
        (cls.project / "source.txt").write_text("baseline\n")
        cls.git("add", "source.txt")
        cls.git("commit", "-qm", "fixture")
        cls.git("remote", "add", "origin", "https://github.com/example/gate.git")
        # The 0.4.0 install and its state: the new version goes next to it and leaves every byte alone.
        cls.apps = root / "data/planning-kit/app"
        old = cls.apps / "0.4.0/bin/zplan"
        old.parent.mkdir(parents=True)
        old.write_text("#!/bin/sh\necho zplan 0.4.0\n")
        old.chmod(0o755)
        (root / "data/planning-kit/native").mkdir()
        (root / "data/planning-kit/native/history.json").write_text('{"old": true}\n')
        cls.launcher = root / "tools/bin/zplan"
        cls.launcher.parent.mkdir(parents=True)
        cls.launcher.symlink_to(old)
        cls.before = tree(root / "data")
        cls.install = cls.call([sys.executable, str(cls.source / "install.py"), "--wheelhouse", str(cls.wheelhouse)],
                              timeout=600)
        cls.app = cls.apps / install.VERSION
        cls.python = cls.app / "bin/python"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def git(cls, *args):
        return subprocess.run(["git", "-C", str(cls.project), *args], check=True, capture_output=True,
                              text=True).stdout

    @classmethod
    def call(cls, command, input=None, timeout=120):
        result = subprocess.run(command, cwd=cls.project, env=cls.env, input=input, capture_output=True, text=True,
                                timeout=timeout)
        if result.returncode:
            raise AssertionError("%s exit %s\n%s" % (command[:2], result.returncode, (result.stdout + result.stderr)[-3000:]))
        return result.stdout

    def assertOutside(self, path):
        for checkout in (ROOT, self.source):
            self.assertFalse(str(Path(path).resolve()).startswith(str(checkout)), path)

    def test_launcher_prints_version_and_older_install_is_untouched(self):
        self.assertEqual(self.call([str(self.launcher), "--version"]).strip(), "zplan 0.9.0")
        self.assertEqual(self.launcher.resolve(), (self.app / "bin/zplan").resolve())
        after = {path: value for path, value in tree(self.root / "data").items()
                 if not path.startswith("planning-kit/app/%s/" % install.VERSION)}
        self.assertEqual(after, self.before)
        self.assertIn("Installed " + str(self.launcher), self.install)
        self.assertIn("Add " + str(self.launcher.parent) + " to PATH", self.install)  # not on the test PATH

    def test_installed_package_and_checker_never_resolve_to_the_checkout(self):
        probe = ("import json, sys, terminal_planner; from terminal_planner.runs import checker_command; "
                 "print(json.dumps({'file': terminal_planner.__file__, 'path': sys.path, 'checker': checker_command()}))")
        found = json.loads(self.call([str(self.python), "-c", probe]))
        self.assertTrue(Path(found["file"]).resolve().is_relative_to(self.app.resolve()), found["file"])
        for entry in found["path"]:
            if entry:
                self.assertOutside(entry)
        checker = shlex.split(found["checker"])
        self.assertEqual(checker[:2], [str(self.python), "-I"])
        self.assertNotIn(str(ROOT), found["checker"])
        self.assertNotIn(str(self.source), found["checker"])
        # The frozen checker validates a milestone manifest from the unrelated project.
        build = ("import sys; from terminal_planner import milestone; from terminal_planner.engine import fixture_proposal; "
                 "from terminal_planner.authority import canonical; "
                 "b, m = milestone.build_manifest(fixture_proposal(), 'M1', 1); "
                 "open(sys.argv[1], 'w').write(canonical(b)); open(sys.argv[2], 'w').write(canonical(m))")
        documents = self.root / "documents"
        documents.mkdir(exist_ok=True)
        baseline, manifest = documents / "baseline.json", documents / "milestone.json"
        self.call([str(self.python), "-I", "-c", build, str(baseline), str(manifest)])
        output = self.call(checker + ["check", str(manifest), "--baseline", str(baseline)])
        self.assertTrue(output.startswith("OK: "), output)

    def test_installed_app_has_textual_8_2_8_and_the_plain_entry_points_stay_plain(self):
        probe = ("import importlib.metadata as m, sys; import textual; "
                 "print(m.version('textual'), sys.version_info[:2] >= (3, 11), textual.__file__)")
        version, new_enough, where = self.call([str(self.python), "-I", "-c", probe]).split(None, 2)
        self.assertEqual((version, new_enough), ("8.2.8", "True"))
        self.assertTrue(Path(where.strip()).resolve().is_relative_to(self.app.resolve()), where)
        state = self.root / "plain-state"
        plain = [str(self.launcher), "--project", str(self.project), "--state-dir", str(state), "--fixture", "gate"]
        for extra in (["--plain", "status"], ["status"]):
            output = self.call(plain[:1] + extra + plain[1:])
            self.assertNotIn("\x1b", output)
            self.assertIn("No plan.", output)
        piped = self.call(plain, input="q\n")  # no terminal on stdin: the line UI, no escape codes
        self.assertNotIn("\x1b", piped)
        self.assertIn("zplan · unrelated project", piped)
        resource = ("from importlib import resources; "
                    "print(resources.files('terminal_planner.tui').joinpath('zplan.tcss').read_text()[:40])")
        self.assertTrue(self.call([str(self.python), "-I", "-c", resource]).strip())  # the stylesheet ships and reads

    def test_installed_fixture_journey_plan_two_dependent_milestones_export_merge(self):
        state = self.root / "journey-state"
        command = [str(self.launcher), "--project", str(self.project), "--state-dir", str(state), "--fixture", "gate"]
        output = self.call(command, input="l\n" + PLAN + "a\n" + START + MERGE + START + MERGE + "q\n", timeout=600)
        self.assertIn("Plan r1 approved", output)
        self.assertIn("Merged: M1 → main", output)
        self.assertIn("Merged: M2 → main", output)
        self.assertEqual(self.git("log", "--first-parent", "--format=%s", "main").count("Merge M"), 2)
        self.assertIn("Plan r1 · approved · 2/2 stages merged", self.call(command[:1] + ["status"] + command[1:]))
        records = [json.loads(path.read_text()) for path in state.rglob("planning.json")]
        runs = [run for record in records for run in record.get("runs", [])]
        self.assertEqual([(r["milestone"], r["delivery"]) for r in runs], [("M1", "integrated"), ("M2", "integrated")])
        for run in runs:
            self.assertEqual(shlex.split(run["checker"])[0], str(self.python))
            self.assertNotIn(str(ROOT), run["checker"])

    def test_wheel_carries_every_runtime_file_and_imports_outside_the_checkout(self):
        wheels = self.root / "wheels"
        self.call([str(self.python), "-m", "pip", "wheel", "--disable-pip-version-check", "--no-input", "--no-index",
                  "--find-links", str(self.wheelhouse), "--no-deps", "-w", str(wheels), str(self.source)], timeout=600)
        (wheel,) = wheels.glob("zeroshot_planning_kit-%s-*.whl" % install.VERSION)
        members = {name for name in zipfile.ZipFile(wheel).namelist() if name.startswith("terminal_planner/")}
        expected = {str(path.relative_to(ROOT)) for pattern in ("terminal_planner/*.py", "terminal_planner/resources/*.json",
                                        "terminal_planner/resources/*.toml", "terminal_planner/resources/*.md",
                                        "terminal_planner/tui/*.py", "terminal_planner/tui/*.tcss")
                    for path in ROOT.glob(pattern)}
        self.assertEqual(members, expected)
        probe = ("import json, sys; sys.path.insert(0, sys.argv[1]); from importlib import resources; "
                 "import terminal_planner; from terminal_planner import milestone; "
                 "data = resources.files('terminal_planner').joinpath('resources'); "
                 "names = [json.loads(data.joinpath(n).read_text())['name'] for n in ('package.json', 'package-lock.json')]; "
                 "graph = milestone.milestone_graph(1); "
                 "from terminal_planner import architect; text = architect.build_preamble(None); "
                 "print(json.dumps({'file': terminal_planner.__file__, 'names': names, 'root': sorted(graph), "
                 "'method': architect.method() in text and '## Brief' in text}))")
        found = json.loads(self.call([sys.executable, "-I", "-c", probe, str(wheel)]))
        self.assertTrue(found["file"].startswith(str(wheel)), found["file"])
        self.assertEqual(len(found["names"]), 2)
        self.assertIn("root", found["root"])
        self.assertTrue(found["method"])  # A11 C3: `build_preamble` from the wheel carries the method


class InstallerUpgradeTests(unittest.TestCase):
    """A4: `install.py` in a temporary HOME — the same-version re-run is a no-op, and replacing another owned
    version copies the store before it moves the launcher.

    The venv, pip and the `--version` probe are replaced, so no interpreter is built and no wheel is fetched; the
    store is a real directory tree, so the backup and its failure mode are exercised for real. Interpretations: the
    store path is the one `authority.production_root()` lays out for this OS under the isolated HOME; the store is
    copied only when the launcher moves to a *different* owned version (a fresh install has nothing to roll back);
    the store is asked through the new venv's python with `-I`, so it comes from the installed package and not from
    an importable checkout the installer runs inside (`StoreProbeTests` proves the isolation for real).
    """

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.data = self.home / "data"
        self.tools = self.home / "tools"
        self.apps = self.data / "planning-kit/app"
        self.bin_dir = self.tools / "bin"

    def store(self):
        base = self.home / ("Library/Application Support" if sys.platform == "darwin" else ".local/state")
        return base / "PlanningKit/production/v3"

    def launcher_at(self, version):
        """An owned launcher (`$ZEROSHOT_TOOLS/bin/zplan`) pointing at `app/<version>/bin/zplan`."""
        app = self.apps / version
        (app / "bin").mkdir(parents=True, exist_ok=True)
        (app / "bin/zplan").write_text("#!/bin/sh\necho zplan %s\n" % version)
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        entry = self.bin_dir / "zplan"
        if entry.is_symlink() or entry.exists():
            entry.unlink()
        entry.symlink_to(app / "bin/zplan")
        return entry

    def install(self, version_output, copy=None, calls=None, env=None, has_node=True):
        """`install.main([])` with the venv, pip and `--version` probe replaced; returns (code, stdout, commands,
        venv-create). The setup-follows signal is pinned off unless `env` turns it on, so the result never
        depends on the runner's environment."""
        calls = [] if calls is None else calls

        def fake_run(command, *args, **kwargs):
            calls.append(list(command))
            if list(command[1:2]) == ["--version"]:
                return subprocess.CompletedProcess(command, 0, stdout=version_output, stderr="")
            if "-c" in command:
                return subprocess.CompletedProcess(command, 0, stdout=str(self.store()) + "\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        captured = io.StringIO()
        copier = patch.object(install.shutil, "copytree", side_effect=copy) if copy is not None else contextlib.nullcontext()
        with patch.dict(os.environ, {"HOME": str(self.home), "XDG_DATA_HOME": str(self.data),
                                     "ZEROSHOT_TOOLS": str(self.tools), install.SETUP_FOLLOWS: "",
                                     **(env or {})}), \
                patch.object(install, "ensure_python"), \
                patch.object(install, "has_node", return_value=has_node), \
                patch.object(install.venv.EnvBuilder, "create") as create, \
                patch.object(install.subprocess, "run", side_effect=fake_run), \
                copier:
            with contextlib.redirect_stdout(captured):
                code = install.main([])
        return code, captured.getvalue(), calls, create

    def test_re_running_the_active_version_is_a_no_op(self):
        entry = self.launcher_at(install.VERSION)
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION)
        self.assertEqual(code, 0)
        self.assertIn("zplan %s is already installed" % install.VERSION, output)
        create.assert_not_called()  # the active venv is never rebuilt (`--force-reinstall` never runs)
        self.assertEqual([c for c in calls if "-m" in c and "pip" in c], [])
        self.assertEqual(entry.resolve(), self.apps / install.VERSION / "bin/zplan")

    def test_replacing_another_owned_version_backs_up_the_store_before_the_swap(self):
        entry = self.launcher_at("0.4.0")
        made = self.store()
        made.mkdir(parents=True)
        (made / "planning.json").write_text("original")
        order = []
        real_copytree = shutil.copytree

        def copy(src, dst, **kwargs):
            order.append("copy")
            return real_copytree(src, dst, **kwargs)

        real_replace = os.replace

        def swap(src, dst):
            order.append("swap")
            return real_replace(src, dst)

        with patch.object(install.os, "replace", side_effect=swap):
            code, output, calls, create = self.install("zplan %s\n" % install.VERSION, copy=copy)
        self.assertEqual(code, 0)
        create.assert_called()  # a real install ran
        self.assertEqual(order, ["copy", "swap"])  # the store is copied before the launcher moves
        (backup,) = made.parent.glob("v3.backup-0.4.0-*")
        self.assertEqual((backup / "planning.json").read_text(), "original")
        (probe,) = [command for command in calls if "-c" in command]
        self.assertIn("-I", probe)  # the store path probe cannot be shadowed by the caller's PYTHONPATH/cwd
        self.assertIn(str(backup), output)
        self.assertIn(str(self.apps / "0.4.0"), output)  # the previous app directory (rollback target)
        self.assertEqual(entry.resolve(), self.apps / install.VERSION / "bin/zplan")

    def test_the_0_7_0_launcher_is_ours_and_is_the_rollback_target(self):
        """B1: a 0.7.0 -> 0.8.0 install backs the store up, prints the 0.7.0 app as the rollback target and swaps
        the launcher, instead of refusing "Existing zplan is not owned by this installer"."""
        entry = self.launcher_at("0.7.0")
        made = self.store()
        made.mkdir(parents=True)
        (made / "planning.json").write_text("original")
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION)
        self.assertEqual(code, 0)
        create.assert_called()
        (backup,) = made.parent.glob("v3.backup-0.7.0-*")
        self.assertEqual((backup / "planning.json").read_text(), "original")
        self.assertIn(str(self.apps / "0.7.0"), output)
        self.assertEqual(entry.resolve(), self.apps / install.VERSION / "bin/zplan")

    def test_the_0_8_0_launcher_is_ours_and_is_the_rollback_target(self):
        """V2: a 0.8.0 -> 0.8.1 install (and so `zplan update`) backs the store up, prints the 0.8.0 app as the
        rollback target and swaps the launcher. Interpretations: none."""
        entry = self.launcher_at("0.8.0")
        made = self.store()
        made.mkdir(parents=True)
        (made / "planning.json").write_text("original")
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION)
        self.assertEqual(code, 0)
        create.assert_called()
        (backup,) = made.parent.glob("v3.backup-0.8.0-*")
        self.assertEqual((backup / "planning.json").read_text(), "original")
        self.assertIn(str(self.apps / "0.8.0"), output)
        self.assertEqual(entry.resolve(), self.apps / install.VERSION / "bin/zplan")

    def test_the_0_8_1_launcher_is_ours_and_is_the_rollback_target(self):
        """V2: a 0.8.1 -> 0.8.2 install (and so `zplan update`) backs the store up, prints the 0.8.1 app as the
        rollback target and swaps the launcher. Interpretations: none."""
        entry = self.launcher_at("0.8.1")
        made = self.store()
        made.mkdir(parents=True)
        (made / "planning.json").write_text("original")
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION)
        self.assertEqual(code, 0)
        create.assert_called()
        (backup,) = made.parent.glob("v3.backup-0.8.1-*")
        self.assertEqual((backup / "planning.json").read_text(), "original")
        self.assertIn(str(self.apps / "0.8.1"), output)
        self.assertEqual(entry.resolve(), self.apps / install.VERSION / "bin/zplan")

    def test_the_0_8_2_launcher_is_ours_and_is_the_rollback_target(self):
        """V2: a 0.8.2 -> 0.8.3 install (and so `zplan update`) backs the store up, prints the 0.8.2 app as the
        rollback target and swaps the launcher. Interpretations: none."""
        entry = self.launcher_at("0.8.2")
        made = self.store()
        made.mkdir(parents=True)
        (made / "planning.json").write_text("original")
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION)
        self.assertEqual(code, 0)
        create.assert_called()
        (backup,) = made.parent.glob("v3.backup-0.8.2-*")
        self.assertEqual((backup / "planning.json").read_text(), "original")
        self.assertIn(str(self.apps / "0.8.2"), output)
        self.assertEqual(entry.resolve(), self.apps / install.VERSION / "bin/zplan")

    def test_the_0_8_3_launcher_is_ours_and_is_the_rollback_target(self):
        """V2: a 0.8.3 -> 0.9.0 install (and so `zplan update`) backs the store up, prints the 0.8.3 app as the
        rollback target and swaps the launcher. Interpretations: none."""
        entry = self.launcher_at("0.8.3")
        made = self.store()
        made.mkdir(parents=True)
        (made / "planning.json").write_text("original")
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION)
        self.assertEqual(code, 0)
        create.assert_called()
        (backup,) = made.parent.glob("v3.backup-0.8.3-*")
        self.assertEqual((backup / "planning.json").read_text(), "original")
        self.assertIn(str(self.apps / "0.8.3"), output)
        self.assertEqual(entry.resolve(), self.apps / install.VERSION / "bin/zplan")

    def test_main_turns_the_setup_follows_signal_into_the_login_line(self):
        """A1/A3: `install.main` reads `install.SETUP_FOLLOWS` (set by install.sh and `zplan update`) and the
        closing line then names `zplan login`, never `zplan setup` (which the caller runs itself)."""
        self.launcher_at("0.4.0")
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION, env={install.SETUP_FOLLOWS: "1"})
        self.assertEqual(code, 0)
        self.assertIn("zplan login", output)
        self.assertNotIn("zplan setup", output)

    def test_main_without_the_signal_keeps_the_setup_line(self):
        """A1/A3 companion: the signal is what changes the line; a manual `install.main` still names
        `zplan setup`."""
        self.launcher_at("0.4.0")
        code, output, calls, create = self.install("zplan %s\n" % install.VERSION)
        self.assertEqual(code, 0)
        self.assertIn("zplan setup", output)
        self.assertNotIn("zplan login", output)

    def test_a_failed_store_copy_keeps_the_old_launcher(self):
        entry = self.launcher_at("0.4.0")
        made = self.store()
        made.mkdir(parents=True)
        (made / "planning.json").write_text("original")

        def explode(src, dst, **kwargs):
            raise OSError("no space")

        with self.assertRaises(RuntimeError):
            self.install("zplan %s\n" % install.VERSION, copy=explode)
        self.assertEqual(entry.resolve(), self.apps / "0.4.0" / "bin/zplan")  # the launcher did not move
        self.assertEqual((made / "planning.json").read_text(), "original")
        self.assertFalse((self.bin_dir / (".zplan-" + install.VERSION)).exists())  # no leftover pending entry


if __name__ == "__main__":
    unittest.main()
