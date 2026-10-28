"""Self-tests for the installed mode of devtools/ux_walkthrough.py.

Stdlib only: no pyte, no Textual, no PTY. The child command builder is asserted directly and through what
`Walk.open()` would exec, and the installed-package probe runs as a real `-I` subprocess against throw-away venvs.

    python3 -m unittest discover -s devtools -p 'test_ux*'
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import venv
from pathlib import Path
from unittest import mock

from devtools import ux_walkthrough

ROOT = ux_walkthrough.ROOT
VERSION = ux_walkthrough.terminal_planner.__version__


def venv_python(root):
    return Path(root) / "bin" / "python"


def site_packages(python):
    """The venv's own purelib, from the venv itself (its version need not match this interpreter's)."""
    done = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError("cannot ask %s for its purelib: %s" % (python, done.stderr))
    return Path(done.stdout.strip())


def write_package(tree, version):
    """A minimal terminal_planner: the probe only needs `__version__` and both module files to import."""
    package = Path(tree) / "terminal_planner"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text('__version__ = "%s"\n' % version)
    (package / "cli.py").write_text('"""fake cli, no Textual"""\n')
    return package


class CommandTest(unittest.TestCase):
    """The one child builder: the PTY launch and the probe cannot differ in interpreter, flags, env or cwd."""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ux-cmd-"))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.python, self.project, self.state = "python-stub", self.temp / "proj", self.temp / "state"
        self.frames = self.temp / "frames"

    def test_default_runs_the_checkout_with_its_pythonpath(self):
        argv, env, cwd = ux_walkthrough.zplan_command(self.python, self.project, self.state, False,
                                                      dict(os.environ, PYTHONPATH="/elsewhere"))
        self.assertEqual(argv[0], self.python)
        self.assertEqual(argv[1:5], ["-m", "terminal_planner.cli", "--project", str(self.project)])
        self.assertEqual(env["PYTHONPATH"], str(ROOT))
        self.assertEqual(env["TERM"], "xterm-256color")
        self.assertEqual(cwd, self.project)

    def test_installed_drops_pythonpath_and_isolates_the_interpreter(self):
        argv, env, cwd = ux_walkthrough.zplan_command(self.python, self.project, self.state, True,
                                                      dict(os.environ, PYTHONPATH="/parent/checkout", KEEP="1"))
        self.assertEqual(argv[:2], [self.python, "-I"])
        self.assertEqual(argv[2:], ["-m", "terminal_planner.cli", "--project", str(self.project),
                                    "--state-dir", str(self.state), "--fixture", "smoke"])
        self.assertFalse("PYTHONPATH" in env, "the installed child must not inherit PYTHONPATH")
        self.assertEqual(env["KEEP"], "1")
        self.assertEqual(cwd, self.project)

    def test_open_execs_the_command_the_probe_uses(self):
        walk = ux_walkthrough.Walk.__new__(ux_walkthrough.Walk)  # open() alone: no git project, no frames, no pyte
        walk.python, walk.project, walk.state, walk.installed = (self.python, self.project, self.state, True)
        pyte = types.ModuleType("pyte")
        pyte.Screen = pyte.ByteStream = lambda *args, **kwargs: object()
        with mock.patch.dict(sys.modules, {"pyte": pyte}), \
             mock.patch.object(ux_walkthrough.pty, "fork", return_value=(0, 0)), \
             mock.patch.object(ux_walkthrough.fcntl, "ioctl"), \
             mock.patch.object(ux_walkthrough.os, "chdir") as chdir, \
             mock.patch.object(ux_walkthrough.os, "execvpe", side_effect=SystemExit) as execvpe:
            with self.assertRaises(SystemExit):
                walk.open()
        _, argv, env = execvpe.call_args.args
        probe_argv, probe_env, probe_cwd = ux_walkthrough.probe_command(self.python, self.project, self.frames)
        self.assertEqual(argv[:2], probe_argv[:2])  # the same interpreter, the same flags
        self.assertEqual(argv[2:4], ["-m", "terminal_planner.cli"])
        self.assertEqual(env, probe_env)
        self.assertEqual(chdir.call_args.args, (probe_cwd,))

    def test_probe_command_resolves_a_relative_frame_directory(self):
        argv, _, cwd = ux_walkthrough.probe_command(self.python, self.project, "frames", {})
        self.assertEqual(argv[-1], str((Path.cwd() / "frames").resolve()))  # the child's cwd is the project
        self.assertEqual(cwd, self.project)


class ProbeTest(unittest.TestCase):
    """The probe against real venvs, the way the walkthrough runs it: `-I`, no PYTHONPATH, cwd = the project."""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ux-probe-"))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        root = self.temp / "venv"
        venv.create(root, with_pip=False)
        self.python = venv_python(root)
        self.site = site_packages(self.python)
        self.project, self.frames = self.temp / "proj", self.temp / "frames"
        self.project.mkdir()
        self.frames.mkdir()

    def probe(self):
        """Run the probe the way the walkthrough does, capturing what it prints; the parent has a PYTHONPATH."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = ux_walkthrough.probe_installed(str(self.python), self.project, self.frames,
                                                    base_env=dict(os.environ, PYTHONPATH=str(ROOT)))
        return result, out.getvalue()

    def test_installed_package_is_accepted(self):
        write_package(self.site, VERSION)
        (version, file), out = self.probe()
        self.assertEqual(version, VERSION)
        self.assertEqual(Path(file), (self.site / "terminal_planner" / "__init__.py").resolve())
        self.assertIn("cli_file=%s" % (self.site / "terminal_planner" / "cli.py").resolve(), out)
        self.assertNotIn("warning", out)
        written = (self.frames / "installed.txt").read_text()
        self.assertIn("terminal_planner.__version__ = %s" % VERSION, written)
        self.assertIn("terminal_planner.__file__ = %s" % Path(file), written)

    def test_symlink_into_the_checkout_is_refused(self):
        (self.site / "terminal_planner").symlink_to(ROOT / "terminal_planner", target_is_directory=True)
        with self.assertRaises(ux_walkthrough.Refused) as caught:
            self.probe()
        self.assertIn("not installed in this interpreter", str(caught.exception))
        self.assertIn(str(ROOT / "terminal_planner"), str(caught.exception))
        self.assertEqual(list(self.frames.iterdir()), [])

    def test_pth_install_of_another_tree_is_refused(self):
        write_package(self.temp / "editable", VERSION)
        (self.site / "zplan-editable.pth").write_text("%s\n" % (self.temp / "editable"))
        with self.assertRaises(ux_walkthrough.Refused) as caught:
            self.probe()
        self.assertIn("not installed in this interpreter", str(caught.exception))
        self.assertEqual(list(self.frames.iterdir()), [])

    def test_missing_import_is_refused(self):
        with self.assertRaises(ux_walkthrough.Refused) as caught:
            self.probe()
        self.assertIn("No module named", str(caught.exception))
        self.assertEqual(list(self.frames.iterdir()), [])

    def test_version_mismatch_warns_but_does_not_fail(self):
        write_package(self.site, "0.0.0")
        (version, file), out = self.probe()
        self.assertEqual(version, "0.0.0")
        self.assertIn("warning: installed terminal_planner 0.0.0 differs from the checkout %s" % VERSION, out)
        self.assertTrue((self.frames / "installed.txt").exists())

    def test_relative_frame_directory_is_resolved_against_the_walkthrough_cwd(self):
        write_package(self.site, VERSION)
        here = os.getcwd()
        os.chdir(self.temp)
        self.addCleanup(os.chdir, here)
        relative = Path("frames-relative")
        relative.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            ux_walkthrough.probe_installed(str(self.python), self.project, relative)
        self.assertTrue((self.temp / "frames-relative" / "installed.txt").exists())


class MainTest(unittest.TestCase):
    """main() must always finish (clean the throw-away project) and must not index a refused installed run."""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ux-main-"))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.frames = self.temp / "frames"

    def run_main(self, error):
        """Run main() with Walk's journey replaced by `error`; return (finish mock, what escaped, exit code)."""
        out = io.StringIO()
        with mock.patch.object(ux_walkthrough.Walk, "__init__", lambda self, *args: None), \
             mock.patch.object(ux_walkthrough.Walk, "run", side_effect=error), \
             mock.patch.object(ux_walkthrough.Walk, "finish") as finish, \
             mock.patch.object(sys, "argv", ["ux_walkthrough.py", str(self.frames), "--installed"]), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                return finish, None, ux_walkthrough.main()
            except BaseException as caught:
                return finish, caught, None

    def test_interrupt_still_finishes_and_writes_the_index(self):
        finish, caught, _ = self.run_main(KeyboardInterrupt())
        self.assertIsInstance(caught, KeyboardInterrupt)
        finish.assert_called_once_with(False, index=True)

    def test_refusal_finishes_without_the_index(self):
        finish, caught, code = self.run_main(ux_walkthrough.Refused("not installed"))
        self.assertIsNone(caught)
        self.assertEqual(code, 1)
        finish.assert_called_once_with(False, index=False)


class ReusedFramesTest(unittest.TestCase):
    """A reused FRAMES_DIR must not keep the previous run's outputs: frames, receipt and INDEX.md go first."""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ux-reuse-"))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.frames = self.temp / "frames"
        self.frames.mkdir()
        (self.frames / "INDEX.md").write_text("walkthrough OK\n")  # the previous run passed and left its index
        (self.frames / "01-x.txt").write_text("old frame\n")
        (self.frames / "installed.txt").write_text("terminal_planner.__version__ = %s\n" % VERSION)
        (self.frames / "notes.txt").write_text("keep me\n")  # not a walkthrough output: left alone

    def kept(self):
        """The frame directory after the run: only the unrelated file survives."""
        return sorted(p.name for p in self.frames.iterdir())

    def test_constructing_the_walk_clears_the_previous_run_and_keeps_others(self):
        walk = ux_walkthrough.Walk(self.frames, sys.executable, 60)  # the real constructor, no run
        self.addCleanup(shutil.rmtree, walk.base, ignore_errors=True)
        self.assertEqual(self.kept(), ["notes.txt"])

    def test_refused_installed_run_leaves_no_previous_run_outputs(self):
        root = self.temp / "venv"
        venv.create(root, with_pip=False)
        write_package(self.temp / "editable", VERSION)
        (site_packages(venv_python(root)) / "zplan-editable.pth").write_text("%s\n" % (self.temp / "editable"))
        walk = ux_walkthrough.Walk(self.frames, str(venv_python(root)), 60, installed=True)
        self.addCleanup(shutil.rmtree, walk.base, ignore_errors=True)
        with self.assertRaises(ux_walkthrough.Refused) as caught:
            walk.run()  # refuses at the probe, before the first frame
        self.assertIn("not installed in this interpreter", str(caught.exception))
        self.assertEqual(self.kept(), ["notes.txt"])


if __name__ == "__main__":
    unittest.main()
