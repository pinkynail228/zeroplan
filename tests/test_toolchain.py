"""The one qualified toolchain per release: single source of the literals, records of an older toolchain, and the
candidate qualification script (scratch roots only, default never changed)."""

from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_runs as runs_tests
import test_terminal_planner as planner
from terminal_planner import authority, setup, toolchain
from terminal_planner.authority import Blocked, canonical
from terminal_planner.engine import NativeEngine, SliceEnded
from terminal_planner.runs import MilestoneRuns, NativeDriver
from devtools import driver_qual

REPO = Path(__file__).resolve().parents[1]
ROLES = planner.ROLES
# The candidate script refuses a toolchain equal to the default: its tests name a version other than the default.
CANDIDATE = "10.13.0"
# Documented exemptions of the single-source rule: tests, docs and the reproducible lockfile data.
EXEMPT = ("tests/", "docs/", "prototype/", "reference/", "upstream/", "README.md", "AGENTS.md", "STATE.md",
          "devtools/zeroshot/tasks/", "terminal_planner/toolchain.py", "terminal_planner/resources/package")


# executable -> the version it reports (a sibling engine runs another executable on its own `call`)
VERSIONS = {}


def load_candidate_script():
    spec = importlib.util.spec_from_file_location("toolchain_candidate", REPO / "devtools/toolchain-candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def newer(**changes):
    return replace(toolchain.DEFAULT, zeroshot="10.12.0", **changes)


def older():
    """The previous release's default: the toolchain a record of the 10.10.1 era was bound under."""
    return replace(toolchain.DEFAULT, zeroshot="10.10.1")


class SingleSourceTests(unittest.TestCase):
    def test_tool_dir_name_is_unchanged(self):
        self.assertEqual(toolchain.current().tool_dir_name, "zeroshot-10.16.0-codex-0.162.1-runtime2")
        self.assertEqual(setup.tools_root().name, "zeroshot-10.16.0-codex-0.162.1-runtime2")

    def test_the_default_toolchain_is_the_qualified_10_16_0(self):
        """C4: this release's one default toolchain -- Zeroshot 10.16.0, Codex 0.162.1 and the three platform
        archive SHA256 of the 10.16.0 release."""
        chain = toolchain.current()
        self.assertEqual((chain.zeroshot, chain.codex, chain.runtime), ("10.16.0", "0.162.1", "runtime2"))
        self.assertEqual(chain.tool_dir_name, "zeroshot-10.16.0-codex-0.162.1-runtime2")
        self.assertEqual(chain.releases, {
            ("Linux", "x86_64"): ("x86_64-unknown-linux-musl",
                                  "2f1ad10956875eccb1aadf60b879fb4195db20fbffd9854a4537f0f1369c9a40"),
            ("Linux", "aarch64"): ("aarch64-unknown-linux-musl",
                                   "6f58bc709bbf9e5d1959834e6f03357f0fe195e4463a7065301bb8b50f794ef3"),
            ("Darwin", "arm64"): ("aarch64-apple-darwin",
                                  "d8da042239ea252b41ab39f3eba82892e51a7b01c3c0a63460d4f24bfe74e2ef"),
        })

    def test_no_version_or_archive_literal_outside_the_toolchain_module(self):
        files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=REPO, capture_output=True,
                               check=True).stdout.decode().split("\0")
        chain = toolchain.DEFAULT
        literals = {chain.zeroshot, chain.codex, chain.restic} | {sha for _, sha in chain.releases.values()}
        pattern = re.compile("|".join(re.escape(v) for v in sorted(literals)))
        found = []
        for name in filter(None, files):
            if name.startswith(EXEMPT) or not (REPO / name).is_file():
                continue
            try:
                text = (REPO / name).read_text(encoding="utf-8")
            except UnicodeError:
                continue
            found += ["%s: %s" % (name, m.group()) for m in pattern.finditer(text)]
        self.assertEqual(found, [])

    def test_bundled_lockfile_pins_the_toolchain_codex(self):
        package = json.loads((REPO / "terminal_planner/resources/package.json").read_text())
        self.assertEqual(package["dependencies"]["@openai/codex"], toolchain.DEFAULT.codex)
        lock = json.loads((REPO / "terminal_planner/resources/package-lock.json").read_text())
        self.assertEqual(lock["packages"]["node_modules/@openai/codex"]["version"], toolchain.DEFAULT.codex)

    def test_user_texts_format_versions_from_the_toolchain(self):
        chain = newer()
        with patch.object(toolchain, "DEFAULT", chain):
            self.assertEqual(toolchain.current().zeroshot_version, "zeroshot 10.12.0")
            self.assertEqual(setup.tools_root().name, "zeroshot-10.12.0-codex-0.162.1-runtime2")
            self.assertIn("Zeroshot 10.12.0", setup.tools_missing())

    def test_binding_shape_is_valid_for_any_version_and_nothing_else(self):
        good = {"executable": "/a/zeroshot", "state_root": "/b", "sha256": "a" * 64, "version": "zeroshot 9.0.0"}
        self.assertTrue(toolchain.valid_binding(good))
        self.assertTrue(toolchain.valid_binding(dict(good, version="zeroshot 11.2.3-rc.1")))
        for name, bad in {"relative": dict(good, executable="zeroshot"), "state": dict(good, state_root="~/x"),
                          "sha": dict(good, sha256="A" * 64), "short sha": dict(good, sha256="a" * 63),
                          "version": dict(good, version="codex-cli 1.2.3"), "extra": dict(good, more=1),
                          "missing": {k: v for k, v in good.items() if k != "sha256"}, "none": None}.items():
            with self.subTest(name):
                self.assertFalse(toolchain.valid_binding(bad))


# One child per environment loads every module in turn. Each module starts from the same `sys.modules` and `sys.path`
# (restored after the previous one), so a module cannot lean on what an earlier module imported. The child prints
# {module: {"count": n} | {"error": text}} as JSON: a module that fails is reported by name, the others still run.
MODULES_CHILD = """\
import importlib, importlib.util, json, sys, traceback, unittest
sys.path[:0] = sys.argv[1:3]
if sys.argv[3] == 'deps':
    import tui_support
    assert tui_support.HAVE_TEXTUAL, 'the wheelhouse gave no Textual'
else:
    assert importlib.util.find_spec('textual') is None, 'textual is importable'
    assert importlib.util.find_spec('rich') is None, 'rich is importable'
modules, path = dict(sys.modules), list(sys.path)
results = {}
for name in sys.argv[4:]:
    try:
        module = importlib.import_module(name)
        results[name] = {'count': unittest.defaultTestLoader.loadTestsFromModule(module).countTestCases()}
    except BaseException:
        results[name] = {'error': traceback.format_exc(limit=-3).strip()}
    sys.modules.clear()
    sys.modules.update(modules)
    sys.path[:] = path
print(json.dumps(results))
"""


class TestModuleImportTests(unittest.TestCase):
    """A-2: every test module of the suite loads on its own with neither Textual nor Rich importable.

    This is the source-hygiene scan of `tests/`: the module list comes from the directory, so a new test module is
    covered without an edit. All modules are imported by one `sys.executable -I -S` child per environment
    (isolated, no site), the interpreter's own standard-library paths kept and only the repository root and the tests
    directory added explicitly; the parent's `sys.path` is never inherited and `ZPLAN_TEST_WHEELHOUSE` is dropped from
    the bare child's environment, so Textual and Rich stay invisible — both are asserted absent before any import.
    Between modules the child puts `sys.modules` and `sys.path` back as they were, so each module is imported from the
    same clean state, as when alone. A module that needs either at import time cannot be reached
    (`importlib.import_module` raises) and the failure names it, as tests.test_layout and tests.test_tui_chat did
    before the fix. Two minutes for each child, no network and no installation.

    Interpretation: the task asks for an existing source-hygiene test module; the repository keeps no module for the
    suite's own source hygiene, so the check joins the generic source scans of this module (AGENTS.md names them as
    the source-hygiene scans of the tree). P3: one child per environment instead of one per module and environment;
    the oracle (import succeeds; equal non-zero counts) and the module named in each failure are unchanged."""

    def test_every_test_module_imports_alone_without_textual_or_rich(self):
        modules = sorted(path.stem for path in (REPO / "tests").glob("test_*.py"))
        self.assertIn("test_layout", modules)  # the scan reads the suite, not an empty directory
        results = self.load(modules, self.bare_env(), "bare")
        for module in modules:
            with self.subTest(module=module):
                self.assertNotIn("error", results[module], "%s: %s" % (module, results[module].get("error")))

    def test_each_module_declares_the_same_tests_with_and_without_textual(self):
        """The class of the u3b-chat-fix4 rejection: a test class hidden behind an import gate instead of skipped.

        Declaring a TestCase must not depend on Textual or Rich being importable: without them the classes are
        registered and skipped, never absent — unittest discovery has to see them. The oracle is the loaded test
        count of the same module in two isolated children, one without the dependencies and one with the wheelhouse
        on `sys.path` (the same child, only the dependency differs): the counts must be equal and never zero, so a
        module that hides its tests fails the check. It fails on edcd390 for tests.test_layout, which declared no
        test at all without Textual. Without a usable wheelhouse only the non-zero half runs; both merge
        environments set ZPLAN_TEST_WHEELHOUSE, so the gate sees the full comparison."""
        modules = sorted(path.stem for path in (REPO / "tests").glob("test_*.py"))
        self.assertIn("test_layout", modules)
        bare = self.load(modules, self.bare_env(), "bare")
        wheelhouse = os.environ.get("ZPLAN_TEST_WHEELHOUSE")
        deps = (self.load(modules, dict(os.environ), "deps")
                if wheelhouse and Path(wheelhouse).is_dir() else None)
        for module in modules:
            with self.subTest(module=module):
                self.assertNotIn("error", bare[module], "%s: %s" % (module, bare[module].get("error")))
                count = bare[module]["count"]
                self.assertGreater(count, 0, "%s: no test is declared without Textual/Rich" % module)
                if deps is not None:
                    self.assertNotIn("error", deps[module], "%s: %s" % (module, deps[module].get("error")))
                    self.assertEqual(count, deps[module]["count"],
                                     "%s: the declared tests depend on Textual/Rich" % module)

    @staticmethod
    def bare_env():
        return {name: value for name, value in os.environ.items() if name != "ZPLAN_TEST_WHEELHOUSE"}

    def load(self, modules, env, mode):
        """{module: {"count": n} or {"error": text}} from one isolated child; a dead child is reported with stderr."""
        done = subprocess.run([sys.executable, "-I", "-S", "-c", MODULES_CHILD, str(REPO), str(REPO / "tests"), mode,
                               *modules], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, "%s children: %s" % (mode, done.stderr.strip()))
        return json.loads(done.stdout.strip().splitlines()[-1])


class OlderToolchainTests(runs_tests.RunsTest):
    """A record bound to another Zeroshot version: the default changes underneath it (toolchain.DEFAULT patched)."""

    def binary(self, name, version):
        path = self.root / name
        path.write_text("#!/bin/sh\nprintf '%s\\n'\n" % version)
        path.chmod(0o700)
        VERSIONS[str(path)] = version
        return path

    def native_engine(self, name, version, responses):
        """Engine over its own executable; every call is logged with the executable it was made on."""
        binary, calls = self.binary(name, version), []

        def call(argv, **kwargs):
            if argv[1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, VERSIONS.get(str(argv[0]), version) + "\n", "")
            calls.append((argv, kwargs))
            result = responses.pop(0)
            if isinstance(result, BaseException):
                raise result
            stdout = "".join(json.dumps(v) + "\n" for v in result) if isinstance(result, tuple) else json.dumps(result) + "\n"
            return subprocess.CompletedProcess(argv, 0, stdout, "")

        return NativeEngine(binary, self.native, call=call, sleep=lambda _: None, version=None), calls

    def older_and_newer(self):
        """(old engine, new default engine): the old one has already bound the stored plan and run."""
        old, old_calls = self.native_engine("zeroshot-old", "zeroshot 10.10.1",
                                            [{"valid": True}, {"runId": "fixture-native-run"},
                                             (planner.NativeTests.running(self), planner.NativeTests.terminal(self)),
                                             {"valid": True}, {"runId": "m-run"}])
        return old, old_calls

    def plan_bound_to_old(self, approve=True):
        old, calls = self.older_and_newer()
        with patch.object(toolchain, "DEFAULT", older()), self.authority() as a:
            self.begin(a, "native")
            old.proposal(a, lambda _: None)
            if approve:
                a.approve(1)
            return old, calls

    def started_on_old(self):
        old, _ = self.plan_bound_to_old()
        with patch.object(toolchain, "DEFAULT", older()), self.authority() as a:
            controller = MilestoneRuns(a, NativeDriver(old.executable, old.state_root, call=old.call, sleep=lambda _: None),
                                       worktrees=self.worktrees)
            return old, controller.start("M1", 1, ROLES)

    def new_driver(self, responses, version="zeroshot 10.12.0"):
        engine_, calls = self.native_engine("zeroshot-new", version, responses)
        return NativeDriver(engine_.executable, engine_.state_root, call=engine_.call, sleep=lambda _: None), calls

    def store_bytes(self):
        with self.authority() as a:
            return a.path.read_bytes()

    def test_record_of_an_older_zeroshot_loads_shows_and_observes_with_its_own_executable(self):
        old, r = self.started_on_old()
        self.assertEqual(r["binding"]["version"], "zeroshot 10.10.1")
        frozen = (r["binding"], r["documents"], r["approval"], r["submission_key"])
        with patch.object(toolchain, "DEFAULT", newer()):
            with self.authority() as a:
                self.assertEqual(a.current["native_binding"]["version"], "zeroshot 10.10.1")  # loads and shows
                driver, calls = self.new_driver([subprocess.TimeoutExpired(
                    "watch", 120, output=canonical(self.running(r)) + "\n")])
                controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
                r = controller.observe(controller.active())
                self.assertEqual(r["status"], "running")
                self.assertEqual([c[0][0] for c in calls], [old.executable])  # never the new default's executable
                self.assertEqual((r["binding"], r["documents"], r["approval"], r["submission_key"]), frozen)

    def test_older_record_with_missing_or_changed_executable_stops_with_a_remedy_and_is_not_rewritten(self):
        old, r = self.started_on_old()
        binary = Path(old.executable)
        content = binary.read_bytes()
        for name, damage in {"missing": lambda: binary.unlink(),
                             "changed": lambda: binary.write_bytes(content + b"# tampered\n")}.items():
            with self.subTest(name):
                binary.write_bytes(content)
                before = self.store_bytes()
                damage()
                with patch.object(toolchain, "DEFAULT", newer()), self.authority() as a:
                    driver, calls = self.new_driver([])
                    controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
                    with self.assertRaises(Blocked) as caught:
                        controller.observe(controller.active())
                    self.assertEqual(caught.exception.family, "toolchain.mismatch")
                    self.assertIn("zeroshot 10.10.1", str(caught.exception))
                    self.assertIn("new plan revision", str(caught.exception))
                    self.assertIn("reinstall", str(caught.exception))
                    self.assertEqual(calls, [])
                self.assertEqual(self.store_bytes(), before)

    def planner_left_mid_run_on_old(self):
        """A planning revision submitted on the old engine whose watch slice ended before the planner finished."""
        old, calls = self.native_engine("zeroshot-old", "zeroshot 10.10.1", [
            {"valid": True}, {"runId": "fixture-native-run"},
            subprocess.TimeoutExpired("watch", 1, output=canonical(planner.NativeTests.running(self)) + "\n")])
        with patch.object(toolchain, "DEFAULT", older()), self.authority() as a:
            self.begin(a, "native")
            with self.assertRaises(SliceEnded):
                old.proposal(a, lambda _: None, slice=1)
            self.assertEqual((a.current["run_id"], a.current["status"]), ("fixture-native-run", "detached"))
        self.assertEqual(len(calls), 3)
        return old

    def test_planner_run_of_an_older_zeroshot_is_observed_with_its_own_executable(self):
        old = self.planner_left_mid_run_on_old()
        keys = ("native_binding", "native_documents", "intent", "submission_key", "run_id", "receipt")
        with self.authority() as a:
            frozen = [a.current[k] for k in keys]
        with patch.object(toolchain, "DEFAULT", newer()):
            new, calls = self.native_engine("zeroshot-new", "zeroshot 10.12.0", [planner.NativeTests.terminal(self)] * 2)  # the cursor boundary, then the full replay
            with self.authority() as a:
                proposal = new.proposal(a, lambda _: None)
                self.assertTrue(proposal)
                self.assertIsNotNone(a.current["terminal_envelope"])
                self.assertEqual([a.current[k] for k in keys], frozen)
                self.assertEqual(a.current["native_binding"]["version"], "zeroshot 10.10.1")
            self.assertEqual({c[0][1] for c in calls}, {"watch"})
            self.assertEqual({c[0][0] for c in calls}, {old.executable})  # never the new default's executable

    def test_a_stored_plan_whose_workspace_overlaps_the_native_state_is_still_watched(self):
        # 10.11 had no workspace/state rule, so a plan it recorded may place its checkout inside the native state.
        # The 10.12 submission guard is a submission-path check: watching that frozen record with its own executable
        # must never hit it.
        def overlapping():
            return self.native / "runs" / "v3"  # the planner checkout then sits inside <native_state_root>/runs

        old, old_calls = self.native_engine("zeroshot-old", "zeroshot 10.10.1", [
            {"valid": True}, {"runId": "fixture-native-run"},
            subprocess.TimeoutExpired("watch", 1, output=canonical(planner.NativeTests.running(self)) + "\n")])
        with patch.object(authority, "production_root", overlapping), \
                patch("terminal_planner.engine.require_workspace_outside_state", lambda *args, **kwargs: None), \
                patch.object(toolchain, "DEFAULT", older()), self.authority() as a:
            self.begin(a, "native")
            self.assertTrue(str(a.directory).startswith(str(self.native / "runs")))
            with self.assertRaises(SliceEnded):
                old.proposal(a, lambda _: None, slice=1)  # a 10.11-era submission, recorded before the rule existed
            self.assertEqual((a.current["run_id"], a.current["status"]), ("fixture-native-run", "detached"))
        with patch.object(authority, "production_root", overlapping), patch.object(toolchain, "DEFAULT", newer()):
            new, calls = self.native_engine("zeroshot-new", "zeroshot 10.12.0", [planner.NativeTests.terminal(self)] * 2)
            with self.authority() as a:
                self.assertTrue(new.proposal(a, lambda _: None))  # the overlap guard does not run while watching
                self.assertIsNotNone(a.current["terminal_envelope"])
            self.assertEqual({c[0][1] for c in calls}, {"watch"})
            self.assertEqual({c[0][0] for c in calls}, {old.executable})
        self.assertEqual(len(old_calls), 3)

    def test_planner_run_of_an_older_zeroshot_with_missing_or_changed_executable_stops_and_is_not_rewritten(self):
        old = self.planner_left_mid_run_on_old()
        binary = Path(old.executable)
        content = binary.read_bytes()
        for name, damage in (("missing", lambda: binary.unlink()),
                             ("changed", lambda: binary.write_bytes(content + b"# tampered\n"))):
            with self.subTest(name):
                binary.write_bytes(content)
                binary.chmod(0o700)
                before = self.store_bytes()
                damage()
                with patch.object(toolchain, "DEFAULT", newer()):
                    new, calls = self.native_engine("zeroshot-new", "zeroshot 10.12.0", [])
                    with self.authority() as a, self.assertRaises(Blocked) as caught:
                        new.proposal(a, lambda _: None)
                    self.assertEqual(caught.exception.family, "toolchain.mismatch")
                    self.assertIn("zeroshot 10.10.1", str(caught.exception))
                    self.assertEqual(calls, [])
                self.assertEqual(self.store_bytes(), before)

    def test_approving_an_older_proposal_checks_the_recorded_executable_only(self):
        old, _ = self.plan_bound_to_old(approve=False)
        binary = Path(old.executable)
        content = binary.read_bytes()
        before = self.store_bytes()
        binary.unlink()
        with patch.object(toolchain, "DEFAULT", newer()), self.authority() as a:
            with self.assertRaises(Blocked) as caught:
                a.approve(1)
            self.assertEqual(caught.exception.family, "toolchain.mismatch")
        self.assertEqual(self.store_bytes(), before)
        binary.write_bytes(content)
        binary.chmod(0o700)
        with patch.object(toolchain, "DEFAULT", newer()), self.authority() as a:
            a.approve(1)  # the recorded executable is present with the recorded sha256
            self.assertEqual(a.current["status"], "approved")
            self.assertEqual(a.current["native_binding"]["version"], "zeroshot 10.10.1")

    def test_new_revision_and_new_attempt_bind_the_current_default(self):
        old, _ = self.plan_bound_to_old()
        chain = newer()
        with patch.object(toolchain, "DEFAULT", chain):
            new, _ = self.native_engine("zeroshot-new", "zeroshot 10.12.0", [])
            with self.authority() as a:
                first = a.state["revisions"][0]["native_binding"]
                a.begin("Next revision", ROLES, "native")
                new.prepare(a)
                binding = a.current["native_binding"]
                self.assertEqual(a.current["version"], 2)
                self.assertEqual((binding["version"], binding["executable"]), (chain.zeroshot_version, new.executable))
                self.assertEqual((first["version"], first["executable"]), ("zeroshot 10.10.1", old.executable))
                self.assertEqual(a.state["revisions"][0]["native_binding"], first)
        # A new attempt of the approved plan runs on the current default, whatever bound the plan.
        with patch.object(toolchain, "DEFAULT", chain):
            driver, calls = self.new_driver([{"valid": True}, {"runId": "m-new"}])
            with self.authority() as a:
                a.state["revisions"].pop()
                a.save()
            with self.authority() as a:
                controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
                r = controller.start("M1", 1, ROLES)
                self.assertEqual((r["binding"]["version"], r["binding"]["executable"]),
                                 (chain.zeroshot_version, driver.executable))
                self.assertEqual({c[0][0] for c in calls}, {driver.executable})

    def test_toolchain_mismatch_is_cataloged_with_a_remedy(self):
        from terminal_planner import catalog
        entry = catalog.ERRORS["toolchain.mismatch"]
        self.assertTrue(entry)
        self.assertIn("toolchain.mismatch", Path(REPO / "docs/REFERENCE.md").read_text())


HELP = "#!/bin/sh\necho 'usage: zeroshot %s --title --graph --runtime-config --input --no-environment " \
       "--submission-key --detach --validate-only --after'\n"


def snapshot(root):
    """Everything under root: directories, file contents and modes (a read-only check must leave it equal)."""
    found = {}
    for directory, names, files in os.walk(root):
        for name in names + files:
            path = Path(directory) / name
            info = path.lstat()
            body = hashlib.sha256(path.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None
            found[str(path.relative_to(root))] = (stat.S_IFMT(info.st_mode), info.st_mode, body)
    return found


class CandidateScriptTests(runs_tests.RunsTest):
    """devtools/toolchain-candidate.py with fake tools: scratch roots only, the default never changes."""

    def setUp(self):
        super().setUp()
        self.script = load_candidate_script()
        self.default_tools = self.root / "default-tools"
        self.default_tools.mkdir()
        self.tool(self.default_tools / "zeroshot", "")
        self.upstream = self.root / "upstream-checkout"
        self.upstream.mkdir()
        (self.upstream / "contracts.rs").write_text("\n".join(self.script.identifiers()))
        self.installs, self.children = [], []

    def tool(self, path, extra):
        path.write_text(HELP % extra)
        path.chmod(0o700)

    def fake_install(self, show, chain=None, archive=None):
        root = setup.tools_root(chain)
        root.mkdir(parents=True)
        self.tool(root / "zeroshot", "candidate")
        self.installs.append((root, chain, os.environ["HOME"], os.environ["TMPDIR"], archive))

    def run_script(self, *extra, fail=None):
        """main() with the install and the two child suites faked; returns (exit code, report text)."""
        def child(argv, env, timeout):
            self.children.append((argv, env))
            name = "driver" if "driver_qual.py" in " ".join(argv) else "installed"
            return (1, "boom in " + name) if name == fail else (0, "ok")

        arguments = ["--zeroshot", CANDIDATE, "--sha256", "a" * 64, "--default-tools", str(self.default_tools),
                     "--upstream", str(self.upstream), *extra]
        out = io.StringIO()
        with patch.object(self.script, "run_child", side_effect=child), \
                patch.object(self.script.setup, "install_tools", side_effect=self.fake_install), \
                patch.object(self.script.setup, "check_installation", side_effect=lambda chain=None: setup.tools_root(chain)), \
                patch.object(self.script.platform, "system", return_value="Linux"), \
                patch.object(self.script.platform, "machine", return_value="x86_64"), \
                redirect_stdout(out):
            code = self.script.main(arguments)
        return code, out.getvalue()

    @staticmethod
    def scratch(path):
        """Inside a short zt-* directory directly under /tmp (the script's scratch)."""
        parts = Path(path).resolve().relative_to(Path("/tmp").resolve()).parts
        return parts[0].startswith("zt-")

    def default_dir(self):
        return setup.tools_root()

    def test_pass_runs_only_in_scratch_roots_and_changes_nothing_in_the_production_roots(self):
        before = snapshot(self.root)
        code, report = self.run_script()
        self.assertEqual(code, 0, report)
        self.assertIn("RESULT: PASS", report)
        for step in ("quiescence", "install", "contracts", "installed", "driver"):
            self.assertRegex(report, "PASS " + step)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.default_dir().exists())
        root, chain, home, tmp, _ = self.installs[0]
        self.assertEqual(chain.tool_dir_name, "zeroshot-10.13.0-codex-0.162.1-runtime2")
        for path in (home, tmp, str(root)):
            self.assertTrue(self.scratch(path), path)
        self.assertEqual(len(self.children), 2)
        driver = next(argv for argv, _ in self.children if "driver_qual.py" in " ".join(argv))
        self.assertEqual(driver[driver.index("--zeroshot-version") + 1], CANDIDATE)
        for argv, env in self.children:
            for name in ("HOME", "XDG_DATA_HOME", "ZEROSHOT_STATE_DIR", "ZEROSHOT_CONFIG_DIR"):
                self.assertTrue(self.scratch(env[name]), (name, env[name]))
            self.assertEqual(env["ZEROSHOT_TEST_BINARY"], str(root / "zeroshot"))
        self.assertEqual(toolchain.current().zeroshot, "10.16.0")
        self.assertFalse(Path(home).exists(), "scratch is removed")

    def test_a_failing_step_fails_the_report_and_keeps_the_default(self):
        for step in ("driver", "installed"):
            with self.subTest(step):
                code, report = self.run_script(fail=step)
                self.assertEqual(code, 1)
                self.assertIn("FAIL " + step, report)
                self.assertIn("boom in " + step, report)
                self.assertIn("RESULT: FAIL", report)
                self.assertFalse(self.default_dir().exists())
                self.assertEqual(toolchain.current().tool_dir_name, "zeroshot-10.16.0-codex-0.162.1-runtime2")

    def test_install_failure_fails_before_any_suite_runs(self):
        with patch.object(self.script.setup, "install_tools", side_effect=Blocked("checksum mismatch")):
            out = io.StringIO()
            with redirect_stdout(out):
                code = self.script.main(["--zeroshot", CANDIDATE, "--sha256", "a" * 64,
                                         "--default-tools", str(self.default_tools), "--upstream", str(self.upstream)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL install", out.getvalue())
        self.assertEqual(self.children, [])

    def test_contract_diff_fails_on_a_vanished_flag_and_on_a_missing_identifier(self):
        def lost(show, chain=None, archive=None):
            root = setup.tools_root(chain)
            root.mkdir(parents=True)
            (root / "zeroshot").write_text(HELP.replace("--detach ", "") % "candidate")
            (root / "zeroshot").chmod(0o700)
        with patch.object(self, "fake_install", lost):
            code, report = self.run_script()
        self.assertEqual(code, 1)
        self.assertRegex(report, "FAIL contracts help run.*--detach")
        (self.upstream / "contracts.rs").write_text("nothing here")
        code, report = self.run_script()
        self.assertEqual(code, 1)
        self.assertRegex(report, "FAIL contracts identifier: policy.native-v2@1")

    def test_candidate_equal_to_the_default_or_codex_without_a_package_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            self.script.main(["--zeroshot", toolchain.DEFAULT.zeroshot, "--sha256", "a" * 64])
        self.assertIn("совпадает с default", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            self.script.main(["--zeroshot", CANDIDATE, "--codex", "0.161.0", "--sha256", "a" * 64])
        self.assertIn("--codex-package", str(caught.exception))

    def test_unfinished_work_blocks_activation_unless_the_old_app_is_kept(self):
        self.approve_native()  # approved plan, no milestone integrated
        before = snapshot(self.root)
        code, report = self.run_script()
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED", report)
        self.assertRegex(report, "FAIL quiescence.*не завершён")
        self.assertEqual(self.installs, [])
        self.assertEqual(snapshot(self.root), before)  # read-only: no lock, no directory, no byte changed
        code, report = self.run_script("--keep-old-app")
        self.assertEqual(code, 0, report)
        self.assertRegex(report, "WARN quiescence")
        self.assertEqual(snapshot(self.root), before)

    def test_active_intent_and_unknown_submission_block(self):
        old, _ = self.older_started()
        blockers = self.script.quiescence(authority.production_root())
        self.assertTrue(any("submitted" in b or "running" in b for b in blockers), blockers)
        code, report = self.run_script()
        self.assertEqual(code, 1)
        self.assertRegex(report, "FAIL quiescence.*unknown/active intent")
        code, report = self.run_script("--keep-old-app")
        self.assertEqual(code, 0, report)

    def test_quiescence_is_clean_without_a_store_and_unreadable_store_blocks(self):
        self.assertEqual(self.script.quiescence(authority.production_root()), [])
        self.approve_native()
        with self.authority() as a:
            path = a.path
        path.write_text("{not json")
        self.assertRegex("\n".join(self.script.quiescence(authority.production_root())), "не читается")

    older_started = OlderToolchainTests.started_on_old
    older_and_newer = OlderToolchainTests.older_and_newer
    plan_bound_to_old = OlderToolchainTests.plan_bound_to_old
    native_engine = OlderToolchainTests.native_engine
    binary = OlderToolchainTests.binary


class CandidateDriverTests(unittest.TestCase):
    """The driver_qual child of the candidate script runs the real identity path against a candidate-versioned
    binary: toolchain.current() there is still the default, so the candidate's version must be passed down."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="z")).resolve()  # short: state dirs hold socket paths
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.binary = self.root / "zeroshot"
        self.binary.write_text("#!/bin/sh\nprintf 'zeroshot %s\\n'\n" % CANDIDATE)
        self.binary.chmod(0o700)

    def test_identity_of_a_candidate_binary_needs_its_version_and_refuses_the_default(self):
        engine = NativeEngine(self.binary, self.root / "s", version="zeroshot " + CANDIDATE)
        self.assertEqual(engine.binary_identity()["version"], "zeroshot " + CANDIDATE)
        with self.assertRaises(Blocked) as caught:
            NativeEngine(self.binary, self.root / "s").binary_identity()
        self.assertEqual(caught.exception.family, "engine.identity_changed")

    def test_adapter_session_builds_the_driver_with_the_candidate_version(self):
        q = driver_qual.Adapter(self.root, str(self.binary), {}, driver_qual.Provider({}), time.monotonic() + 60,
                                version="zeroshot " + CANDIDATE)
        authority_stub = type("A", (), {"fixture_id": None})()
        with patch.object(driver_qual, "Authority") as authority_class, \
                patch.object(driver_qual, "MilestoneRuns", side_effect=lambda a, driver, worktrees: driver):
            authority_class.return_value.__enter__.return_value = None
            with q.session() as driver:
                self.assertEqual(driver.binding(authority_stub)["version"], "zeroshot " + CANDIDATE)
            with q.session(driver_qual.LostStop) as driver:
                self.assertEqual(driver.binding(authority_stub)["version"], "zeroshot " + CANDIDATE)

    def test_approve_scripts_a_candidate_plan_when_given_its_version(self):
        project, home = self.root / "p", self.root / "h"
        home.mkdir()
        project.mkdir()
        driver_qual.git(project, "init", "-q", "-b", "main")
        (project / "README.md").write_text("fixture\n")
        driver_qual.git(project, "add", ".")
        driver_qual.git(project, "commit", "-qm", "fixture")
        driver_qual.git(project, "remote", "add", "origin", "https://github.com/zplan-qual/fixture.git")
        with patch.dict(os.environ, {"HOME": str(home)}):
            driver_qual.approve(project, self.binary, self.root / "s", "zeroshot " + CANDIDATE)
            with driver_qual.Authority(None, project) as a:
                self.assertEqual(a.current["status"], "approved")
                self.assertEqual(a.current["native_binding"]["version"], "zeroshot " + CANDIDATE)


if __name__ == "__main__":
    unittest.main()
