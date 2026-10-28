"""Activation of zplan's own Codex home (0.5 item S2, slice s2b2): R-1 (default home), R-3c (the `ensure` call
sites), R-4 (auth presence, one rule), R-4b (the architect child env), the R-5 home/profile part, R-7 default-home
text; A-3, A-3s, A-4, A-4b, A-6, A-7 and this slice's A-8. The drift/sources WARNs and R-6 are s2b3's.

Deterministic: temporary HOME/XDG dirs, a fake pinned toolchain (real files, `check_installation` patched), the
scripted fake codex of `test_architect`, spies that wrap the real `subprocess.run/Popen` so a launch really happens
while it is recorded, and no network.

Interpretations recorded here (the worker summary never reaches the reviewers):

- `agent_home(env)` resolves an override through `codex_home(env)` (the same `Path(...).expanduser().resolve()`),
  so the two agree on a nonempty `CODEX_HOME` by construction and differ only on the empty/unset case (zplan's own
  home). One resolution rule for "the override path" stays in `codex_home`.
- A-6's "the same verdict in doctor, `default_prepare` and a resumed turn's `check_home`" is read as: doctor's auth
  item (`ok` and `key`), the Blocked `default_prepare` raises for a new thread (or its success), and
  `architect.check_home(recorded, env, resumed=True)` for a continuation. All three share `setup.auth_served`.
- A-4's "a CLI planning prepare and an attempt start" is read as the real `cli.main([])` wiring: the captured engine
  (planning) and driver (milestone attempt) closures both get the env `attach_tools` built.
- The doctor entry points go through `cli.main(["doctor"])` in the fixture project's directory (the same code path
  as a doctor in the working directory); the informational profile line is asserted on its `profile ... (packaged
  ...)` / `not written yet ...` text, never on the catalog's own `[code: ...]` wording.
- `cli.Terminal` binds `sys.stdout` as a default at import time and `setup.login` inherits its stdin, so an entry
  point is captured by replacing the class and the scripted child is given an empty stdin; argv and env stay the
  product's own.
- The A-4 regression asserts only through production entry points (`native_environment`, `login`, `doctor`,
  `default_prepare`, the CLI engine/driver closures), so it replays on the base and fails at its behavioural
  assertion; the candidate-only `setup.agent_home` is checked directly in `HomeResolutionTests`, which is not part
  of the replay.
- A-7 sends real turns through the scripted codex: the new thread's stored session, a continuation's recorded home
  in the process env, and the spawned `CODEX_HOME` are all observed from the spies rather than derived.
- The R-8 "unchanged after the module" comparison is in `tearDownModule` (unittest loads classes alphabetically, so
  a class-level check would run before the classes that sort after it); the sentinel list is captured at import.
- The visit-7 doctor guard (R-5): `agent_profile.written_version` is s2b1's and out of this slice's write set, so
  the failure-tolerant read lives in `doctor`; an unreadable entry is answered as R-5's "not written yet" branch,
  because R-5 derives the line from `written_version`'s return alone (a version, or "not written yet").
- The visit-7 R-4/A-6 vs R-4b conflict: a turn's auth verdict is judged on the owner's own env (R-4's env-key rule
  is unconditional), and `setup.child_auth_env` (R-4b, the OPENAI_API_KEY *file*-auth route) shapes the child env
  only -- it must not let a resumed turn complete where readiness and `default_prepare` refuse.
- D6a (2188b60, zplan logs in and out only of the home it owns), read as the shipped behaviour the tests follow: a
  login in an override home runs no Codex and answers for that home; in the private home it first runs `codex login
  status` (the scripted codex is told "not logged in" where a device login is expected); a missing file login offers
  [l] in the private home and the instruction key [i] in an override home; a private `auth.json` byte-equal to
  `~/.codex/auth.json` is a copy (`readiness.auth`), so fixtures give zplan's own login other bytes and the
  symlinked-home alias is refused at login with that family instead of `setup.agent_home`. No product code is wrong
  here, so no `conflict:` line.
"""

import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from terminal_planner import (agent_profile, architect, catalog, cli, engine, process, record_home,
                              setup, toolchain)
from terminal_planner.architect import Architect, ArchitectStore
from terminal_planner.authority import Blocked
from terminal_planner.runs import MilestoneRuns, NativeDriver
from terminal_planner.tui import chat as chat_module
import test_runs as runs_tests
from test_architect import FAKE, THREAD, completes

REAL_ENSURE = agent_profile.ensure
# Captured before any patch: the spy wraps these, never the patched module attributes (which would recurse).
REAL_CALL, REAL_RUN, REAL_POPEN = subprocess.call, subprocess.run, subprocess.Popen
# The runner's own private home and its state, captured at import, before any fixture patches HOME/XDG_DATA_HOME
# (R-8); a fixture that forgot to isolate itself would write there and `IsolationTests` would show it.
SENTINEL = setup.private_codex_home()
SENTINEL_STATE = sorted(path.name for path in SENTINEL.iterdir()) if SENTINEL.is_dir() else None
# Distinct provider sentinels that never match the export checker's credential patterns (`sk-...` and friends), so
# a leaked value is provably absent while the source itself stays export-clean (R-8).
CODEX_SENTINEL, OPENAI_SENTINEL = "codex-sentinel-value-0001", "openai-sentinel-value-0002"
# Every provider variable a verdict here may set: each case drops the whole family before applying its own, so an
# inherited value (run.sh's, or the runner's) can never change a verdict (R-8).
PROVIDER_VARS = ("CODEX_API_KEY", "OPENAI_API_KEY", "CORP_KEY")
HELP = "exec --json --sandbox --cd --model --config"
MODEL, EFFORT = "gpt-6.1-sol", "high"


class Processes:
    """Every process launch of one test: argv and env, in order, from `call`, `run` and `Popen`.

    `run` and `Popen` delegate to the real functions, so "no launch" really means no process at all and the turns
    of `A-6` really run the scripted codex. `call` (the `login` path) delegates too, with an empty stdin: the
    scripted child would otherwise read this test's own stdin, which argv and env never carry."""

    def __init__(self):
        self.calls = []

    def _record(self, argv, kwargs):
        self.calls.append({"argv": [str(part) for part in argv], "env": dict(kwargs.get("env") or {})})

    def call(self, argv, **kwargs):
        self._record(argv, kwargs)
        return REAL_CALL(argv, stdin=subprocess.DEVNULL, **kwargs)

    def run(self, *args, **kwargs):
        self._record(args[0] if args else kwargs.get("args"), kwargs)
        return REAL_RUN(*args, **kwargs)

    def popen(self, argv, **kwargs):
        self._record(argv, kwargs)
        return REAL_POPEN(argv, **kwargs)

    def homes(self):
        return [call["env"].get("CODEX_HOME") for call in self.calls]

    def turns(self, binary):
        """The launches of `binary` that are not its `--help` tool probe: the real child processes of a turn."""
        return [call for call in self.calls if call["argv"][:1] == [str(binary)] and "--help" not in call["argv"]
                and call["argv"][1:3] != ["mcp", "list"]]


class Screen:
    """The line UI of one CLI entry point: every line lands in `lines`; no input is read."""

    def __init__(self):
        self.lines = []
        self.role_preferences = None

    def show(self, value=""):
        self.lines.append(str(value))

    def ask(self, label, default=None):
        """The plain session's menu wants a key; this screen reads no input, so it ends the loop exactly as a real
        terminal at end-of-input does (`input()` raises `EOFError`, which `cli.main` turns into a clean exit). Only a
        path that wrongly continues past a refusal (mutation (g)) ever reaches it, and it then fails the refusal
        assertion instead of spinning the menu or dying on a missing method."""
        raise EOFError

    def text(self):
        return "\n".join(self.lines)


def listing(directory):
    directory = Path(directory)
    return sorted(path.name for path in directory.iterdir()) if directory.is_dir() else None


def tree(root):
    root = Path(root)
    if not root.is_dir():
        return None
    return sorted((str(path.relative_to(root)), path.read_bytes() if path.is_file() else None)
                  for path in root.rglob("*"))


def _native_plan_harness():
    """A `test_runs.RunsTest` subclass built at call time: a class created inside a function is not a module
    attribute, so unittest never collects its inherited tests here, while its approved-native-plan and attempt
    helpers stay available to `EndToEndTests`. Reusing the module that already drives `MilestoneRuns` avoids
    re-implementing a planner approval in this slice; `test_runs` is imported, never edited."""
    class _Harness(runs_tests.RunsTest):
        pass
    return _Harness


class ActivationCase(unittest.TestCase):
    """A temporary root (HOME, XDG_DATA_HOME and XDG_CONFIG_HOME inside it), a fake pinned toolchain with the
    scripted codex, a recording `agent_profile.ensure` spy and the process spies. `CODEX_HOME` and the provider key
    variables of the runner are cleared so every verdict here is the fixture's own (R-8)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zs-activation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        patched = patch.dict(os.environ, {"HOME": str(self.root / "home"), "XDG_DATA_HOME": str(self.root / "data"),
                                         "XDG_CONFIG_HOME": str(self.root / "config"), "GIT_CONFIG_NOSYSTEM": "1"})
        patched.start()
        self.addCleanup(patched.stop)
        for name in ("CODEX_HOME", "GIT_CONFIG_GLOBAL") + PROVIDER_VARS:
            os.environ.pop(name, None)  # run.sh exports CODEX_HOME and keys; a fixture must never inherit them
        (self.root / "home").mkdir()
        (self.root / "home" / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        (self.root / "roles-config").mkdir()
        self.private = setup.private_codex_home()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        for name in ("zeroshot", "codex"):
            binary = self.tools / name
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o700)
        (self.tools / "installation.json").write_text("{}\n")  # status's own gate: the tools are installed
        self.zeroshot, self.codex = self.tools / "zeroshot", self.tools / "codex"
        self.codex.write_text(FAKE % {"python": sys.executable})
        self.codex.chmod(0o755)
        self.script([{"lines": completes("Привет.")}])
        self.spy = Processes()
        for module, name, replacement in ((setup, "check_installation", lambda *a, **k: self.tools),
                                          (setup, "tool_paths", lambda *a, **k: (self.zeroshot, self.codex)),
                                          (cli, "check_installation", lambda *a, **k: self.tools),
                                          (cli, "tool_paths", lambda *a, **k: (self.zeroshot, self.codex)),
                                          (setup, "native_state_root", lambda: self.root / "zp"),
                                          (engine, "check_socket_path", lambda *a, **k: 81),
                                          (process, "config_root", lambda: self.root / "roles-config"),
                                          (subprocess, "call", self.spy.call),
                                          (subprocess, "run", self.spy.run),
                                          (subprocess, "Popen", self.spy.popen)):
            self.patch(module, name, replacement)
        self.ensures = []
        self.patch(agent_profile, "ensure", self.ensure)

    def patch(self, module, name, replacement):
        patcher = patch.object(module, name, replacement)
        patcher.start()
        self.addCleanup(patcher.stop)

    def ensure(self, home):
        """The `agent_profile.ensure` spy: it records the call and delegates, so a control case really writes."""
        self.ensures.append(Path(home))
        return REAL_ENSURE(home)

    def script(self, steps):
        (self.tools / "scenario.json").write_text(json.dumps({"steps": steps, "help": HELP}))

    # fixture builders --------------------------------------------------------------------------------------------
    def home(self, name, auth=False, config=None, owner=False):
        """A Codex home under the temporary root; `owner` puts it at `<HOME>/.codex` (the owner's own home)."""
        home = (self.root / "home" / ".codex") if owner else (self.root / name)
        home.mkdir(parents=True, exist_ok=True)
        if auth:
            (home / "auth.json").write_text("{}\n")
        if config is not None:
            (home / "config.toml").write_text(config)
        return home

    def project(self, name="proj"):
        """A clean Git project with one commit and a GitHub-shaped origin (idempotent per test)."""
        project = self.root / name
        if (project / ".git").is_dir():
            return project
        project.mkdir()
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "Fixture"],
                     ["config", "user.email", "fixture@example.invalid"], ["config", "commit.gpgsign", "false"],
                     ["add", "source.txt"], ["commit", "-qm", "fixture"],
                     ["remote", "add", "origin", "https://github.com/example/fixture.git"]):
            if args[0] == "add":
                (project / "source.txt").write_text("baseline\n")
            subprocess.run(["git", "-C", str(project), *args], check=True, capture_output=True)
        return project

    @contextlib.contextmanager
    def cwd(self, path):
        previous = os.getcwd()
        os.chdir(str(path))
        try:
            yield
        finally:
            os.chdir(previous)

    # entry points ------------------------------------------------------------------------------------------------
    def main(self, argv):
        """`cli.main(argv)` with the line UI replaced by a recording screen; returns (code, screen)."""
        screen = Screen()
        with patch.object(cli, "Terminal", lambda: screen):
            code = cli.main(list(argv))
        return code, screen

    def engine_env(self, project):
        """The env `attach_tools` builds in the real `cli.main([])` wiring, observed through the captured engine
        and driver closures (the CLI planning prepare and the milestone attempt of A-4)."""
        captured = []

        def session(terminal, project_arg, state_root, engine_factory, fixture_id=None, driver_factory=None, **kwargs):
            authority = SimpleNamespace(project=project_arg, fixture_id=fixture_id)
            captured.append((engine_factory("native", terminal), driver_factory(authority)))

        with patch.object(cli, "session", session), patch.object(cli, "choose_project", lambda *a, **k: project):
            code, screen = self.main([])
        self.assertEqual(code, 0, screen.text())
        engine_instance, driver = captured[-1]
        self.assertIsInstance(engine_instance, engine.NativeEngine)
        self.assertEqual(engine_instance.environment["CODEX_HOME"], driver.environment["CODEX_HOME"])
        return engine_instance.environment

    def prepare(self, project):
        """`default_prepare(project)` over the scripted codex (the production preparation of the chat)."""
        return chat_module.default_prepare(project)

    def architect_instance(self, project, home):
        """An `Architect` over the scripted codex with the process env an install would hand it (R-1)."""
        return Architect(self.codex, dict(os.environ, CODEX_HOME=str(home)), project, MODEL, EFFORT)


class OverrideTests(ActivationCase):
    """A-3 (R-1, R-3c): an explicit `CODEX_HOME` is used everywhere and never gets a profile; the empty value is
    zplan's own home and does get one. Mutation (a) (write under an override), (b) (skip only an equal override),
    (e) (fall back to ~/.codex), (g) (swallow the refusal) and (i) (doctor calls `ensure`) die here."""

    def test_a3_an_override_home_is_never_written_and_reaches_every_entry_point(self):
        override = self.home("override", auth=True)  # seeded before the act, so `login`'s mkdir changes nothing
        before = listing(override)
        project = self.project()
        with patch.dict(os.environ, {"CODEX_HOME": str(override)}):
            code, screen = self.main(["login"])
            self.assertEqual(code, 0, screen.text())
            self.assertIn(str(override), screen.text())     # D6a: the login answers for the override home ...
            self.assertEqual(self.spy.turns(self.codex), [])  # ... and starts no Codex in the owner's own home
            with self.cwd(project):
                code, screen = self.main(["doctor"])
            self.assertEqual(code, 0, screen.text())
            self.assertIn("your $CODEX_HOME", screen.text())          # R-5: the item names the override...
            self.assertNotIn("(packaged", screen.text())              # ... and only zplan's home gets the line
            self.assertEqual(self.engine_env(project)["CODEX_HOME"], str(override))
            self.assertEqual(self.prepare(project)[0].environment["CODEX_HOME"], str(override))
        self.assertEqual(self.ensures, [])                 # zero `ensure` calls on every entry point
        self.assertEqual(listing(override), before)         # and no profile or backup under the override
        self.assertFalse(self.private.exists())            # nor under zplan's own home
        self.private.mkdir(parents=True)                   # the override fixture is seeded before the act (R-8)...
        (self.private / "seed.txt").write_text("seed\n")   # ... so `login`'s own `mkdir` changes nothing below
        before_private = listing(self.private)
        with patch.dict(os.environ, {"CODEX_HOME": str(self.private)}):
            self.assertEqual(self.main(["login"])[0], 0)   # the private home *as* an override is still an override
        self.assertEqual(self.ensures, [])
        self.assertEqual(listing(self.private), before_private)     # login's `mkdir` left the listing as it was
        self.assertNotIn("config.toml", listing(self.private))      # and wrote no profile
        self.assertIsNone(agent_profile.written_version(self.private))

    def test_a3_the_empty_override_is_zplan_s_home_and_writes_the_profile_once(self):
        override = self.home("override", auth=True)
        before = listing(override)
        with patch.dict(os.environ, {"CODEX_HOME": ""}):
            code, screen = self.main(["login"])
            self.assertEqual(code, 0, screen.text())
            self.assertEqual(self.spy.turns(self.codex)[-1]["env"]["CODEX_HOME"], str(self.private))
        self.assertEqual(self.ensures, [self.private])     # exactly one `ensure` per login, never two
        self.assertEqual(agent_profile.written_version(self.private),
                         agent_profile.version(agent_profile.packaged()))
        self.assertEqual(listing(override), before)


class StatusTests(ActivationCase):
    """A-3s (gate9 B, R-3c): `status` builds the same env with no profile write and no `ensure`. Mutation (j)
    (`status` with `profile=True`) dies here."""

    def test_a3s_status_writes_nothing_even_when_the_tools_are_installed(self):
        project = self.project()
        code, screen = self.main(["status", "--project", str(project)])
        self.assertEqual(code, 0, screen.text())
        self.assertEqual(self.ensures, [])                 # status reads records: no `ensure`, no profile write
        self.assertFalse(self.private.exists())            # an absent private home stays absent
        self.assertIn(project.name, screen.text())         # the stored state still renders


class ExplicitBinaryTests(ActivationCase):
    """R-1 through `--native-binary`: the home is chosen exactly as for a pinned-tools launch (zplan's own home with
    no override), so neither the planner factory nor the milestone driver falls back to `~/.codex`. Mutation (m) —
    the early return that left `environment=None` for `--native-binary` — dies here."""

    def explicit_env(self, project):
        """The env the real `cli.main(["--native-binary", …])` wiring hands the engine and the driver."""
        captured = []

        def session(terminal, project_arg, state_root, engine_factory, fixture_id=None, driver_factory=None, **kwargs):
            authority = SimpleNamespace(project=project_arg, fixture_id=fixture_id)
            captured.append((engine_factory("native", terminal), driver_factory(authority)))

        with patch.object(cli, "session", session), patch.object(cli, "choose_project", lambda *a, **k: project):
            code, screen = self.main(["--native-binary", str(self.zeroshot)])
        self.assertEqual(code, 0, screen.text())
        engine_instance, driver = captured[-1]
        self.assertIsInstance(engine_instance, engine.NativeEngine)
        return engine_instance, driver

    def test_r1_a_native_binary_launch_still_uses_zplans_own_home(self):
        project = self.project("explicit-proj")
        engine_instance, driver = self.explicit_env(project)
        self.assertIsNotNone(driver.environment)                       # the driver is handed the same env
        self.assertEqual(engine_instance.codex_home(), self.private)   # the attempt home a binding would freeze
        self.assertEqual(driver.environment["CODEX_HOME"], str(self.private))
        with patch.dict(os.environ, {"CODEX_HOME": ""}):               # an empty override is zplan's own home too
            engine_instance, driver = self.explicit_env(project)
            empty_home = engine_instance.codex_home()                  # read while the empty override is in force
        self.assertEqual(empty_home, self.private)
        self.assertEqual(driver.environment["CODEX_HOME"], str(self.private))

    def test_r1_a_native_binary_launch_honours_an_explicit_home(self):
        override = self.home("explicit-override", auth=True)
        project = self.project("explicit-proj")
        with patch.dict(os.environ, {"CODEX_HOME": str(override)}):
            engine_instance, driver = self.explicit_env(project)
            home = engine_instance.codex_home()                        # read while the override is in force
        self.assertEqual(home, override.resolve())
        self.assertIsNotNone(driver.environment)
        self.assertEqual(driver.environment["CODEX_HOME"], str(override.resolve()))


class HomeResolutionTests(ActivationCase):
    """R-1: `agent_home(env)` is the nonempty override (resolved exactly as `codex_home`) else zplan's own home.
    This direct unit check is candidate-only, so the A-4 regression in `FreshInstallTests` reaches the same rule
    through production entry points only and stays replayable on the base."""

    def test_r1_agent_home_is_the_override_else_the_private_home(self):
        override = self.home("override")
        self.assertEqual(setup.agent_home({}), self.private)                       # unset -> zplan's own home
        self.assertEqual(setup.agent_home({"CODEX_HOME": ""}), self.private)       # empty -> zplan's own home
        self.assertEqual(setup.agent_home({"CODEX_HOME": str(override)}), override.resolve())
        self.assertEqual(setup.agent_home({"CODEX_HOME": str(override)}),          # the one override resolution
                         setup.codex_home({"CODEX_HOME": str(override)}))
        self.assertFalse((self.root / "home" / ".codex").exists())                 # never the owner's home


class OwnerHomeAliasTests(ActivationCase):
    """R-1/A-4: zplan's own home must never be the owner's `~/.codex`, not even through a symlink.

    A private home that is a link — the `codex-home` entry itself, or a parent such as `planning-kit` — to `~/.codex`
    made `native_environment()` replace the owner's `config.toml` with the packaged profile, leave a
    `config.toml.bak` behind and hand Codex the owner's home. `native_environment` now refuses that alias with the
    `setup.agent_home` family before the env is returned or the profile is written; the oracle for "untouched" is
    the byte tree of the owner's home, read before and after.

    Interpretations (the worker's summary never reaches the reviewers, so the decisions live here):

    * Only the *implicit* home is judged. An explicit `CODEX_HOME` — `~/.codex` itself included — stays the owner's
      documented opt-in (`FreshInstallTests.test_a4_an_explicit_owner_home_is_used_and_gets_no_profile`).
    * The refusal reuses the existing `setup.agent_home` family rather than a new catalog id: R-3c already routes
      that family to `attach_tools`, `zplan login` and `default_prepare`, the three places a fresh launch and
      `login` get the env that would be written to and launched with.
    * The `--native-binary` development route is refused too (`setup.launch_home` is shared with
      `native_environment`): it writes no profile, but it is still a launch that would otherwise hand Codex the
      owner's own home. The route's non-alias behavior stays `ExplicitBinaryTests`'.
    * `doctor` and `readiness` stay read-only and do not refuse: they neither write nor launch a Codex child, and
      R-5 adds no new item.
    """

    def owner(self):
        """The owner's `$HOME/.codex`, with the apps config and a login: the tree a launch must not touch."""
        return self.home(".codex", auth=True, config="[features]\napps = true\n", owner=True)

    def assert_alias_refused(self, project, login_family="setup.agent_home"):
        """Every fresh-launch entry point refuses with `setup.agent_home`, spawning and writing nothing.

        D6a: `zplan login` judges the private `auth.json` first, so a home that is a link to `~/.codex` holding the
        owner's `auth.json` is refused as a copy of someone else's login (`readiness.auth`); `login_family` names the
        refusal the login route gives for the fixture."""
        launched = list(self.spy.calls)                        # `project()` already ran git; only new launches count
        with self.assertRaises(Blocked) as caught:
            setup.native_environment()
        self.assertEqual(caught.exception.family, "setup.agent_home")
        with patch.object(cli, "choose_project", lambda *a, **k: project):
            code, screen = self.main([])                       # a fresh launch: `attach_tools` first
        self.assertEqual(code, 1, screen.text())
        self.assertIn("setup.agent_home", screen.text())       # the family reaches the owner, not "tools missing"
        self.assertNotIn("readiness.tools", screen.text())
        with patch.object(cli, "choose_project", lambda *a, **k: project):
            code, screen = self.main(["--native-binary", str(self.zeroshot)])   # the development route too
        self.assertEqual(code, 1, screen.text())
        self.assertIn("setup.agent_home", screen.text())
        code, screen = self.main(["login"])                    # the device login writes nothing either
        self.assertEqual(code, 1, screen.text())
        self.assertIn(login_family, screen.text())
        with self.assertRaises(Blocked) as caught:
            self.prepare(project)                              # the chat refuses with the same family
        self.assertEqual(caught.exception.family, "setup.agent_home")
        self.assertEqual(self.spy.calls, launched)             # no codex and no zeroshot ever started
        self.assertEqual(self.ensures, [])                     # and no profile write was attempted

    def test_r1_a_private_home_symlinked_to_the_owner_codex_home_is_refused(self):
        owner = self.owner()
        project = self.project("alias-proj")
        self.private.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(owner, self.private)                        # `planning-kit/codex-home` -> `~/.codex`
        self.assertEqual(setup.private_codex_home().resolve(), owner.resolve())
        before = tree(owner)
        self.assert_alias_refused(project, login_family="readiness.auth")   # the owner's auth.json is seen as a copy
        self.assertEqual(tree(owner), before)                  # byte-identical: no profile, no `config.toml.bak`

    def test_r1_a_parent_symlink_into_the_owner_codex_home_is_refused(self):
        owner = self.owner()
        project = self.project("alias-proj")
        self.private.parent.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(owner, self.private.parent)                 # `planning-kit` -> `~/.codex`
        self.assertIn(owner.resolve(), setup.private_codex_home().resolve().parents)
        self.assertFalse(setup.private_codex_home().exists())  # the alias hides it: a fresh home inside ~/.codex
        before = tree(owner)
        self.assert_alias_refused(project)
        self.assertEqual(tree(owner), before)

    def test_r1_a_symlinked_profile_lock_does_not_write_outside_the_private_home(self):
        """R-1/A-4 write confinement: the profile lock is opened with `O_CREAT`, so a symlink at that name would
        make zplan create the file it points at — the reviewer's `~/.codex/unexpected-lock-target`. The launch
        refuses before `ensure` is reached, and neither tree changes."""
        owner = self.owner()
        project = self.project("lock-proj")
        self.private.mkdir(parents=True)
        target = owner / "unexpected-lock-target"
        os.symlink(target, self.private / ".zplan-profile.lock")
        before_owner, before_private = tree(owner), tree(self.private)
        launched = list(self.spy.calls)
        with self.assertRaises(Blocked) as caught:
            setup.native_environment()
        self.assertEqual(caught.exception.family, "setup.agent_home")
        with patch.object(cli, "choose_project", lambda *a, **k: project):
            code, screen = self.main([])
        self.assertEqual(code, 1, screen.text())
        self.assertIn("setup.agent_home", screen.text())
        code, screen = self.main(["login"])
        self.assertEqual(code, 1, screen.text())
        with self.assertRaises(Blocked) as caught:
            self.prepare(project)
        self.assertEqual(caught.exception.family, "setup.agent_home")
        self.assertFalse(target.exists())                        # nothing was created in the owner's home
        self.assertEqual(tree(owner), before_owner)
        self.assertEqual(tree(self.private), before_private)     # nor changed in zplan's own home
        self.assertEqual(self.spy.calls, launched)
        self.assertEqual(self.ensures, [])                       # the profile write was never reached

    def test_r1_a_looping_owner_codex_home_does_not_break_a_launch(self):
        """R-1: a launch must not depend on Codex's own home being resolvable. A `~/.codex` symlink that points at
        itself is a home the alias guard must never resolve; it answers with `os.path.realpath`, so the launch
        keeps its own independent private home instead of crashing into the owner's broken path.

        The "unresolvable" precondition is injected, not read from the interpreter: `pathlib.Path.resolve` is
        patched to raise `RuntimeError` for the owner's `~/.codex` alone and to delegate every other call to the
        saved original, and the patch is held across all three acts (`native_environment`, `engine_env`,
        `prepare`). `Path.resolve`'s behaviour on a self-loop is version-dependent -- `RuntimeError` up to Python
        3.12, a returned path on 3.13 -- while `pyproject.toml` supports `>=3.11`, so the guard must be shown to
        avoid a raising resolution on every supported interpreter rather than only where the standard library
        happens to raise.

        Interpretation: the owner path is recognised by its exact `Path.home() / ".codex"` spelling, the argument
        an implicit resolution passes; a resolved or prefix comparison would itself be the call under test."""
        owner = self.root / "home" / ".codex"
        os.symlink(".codex", owner)                              # `~/.codex` -> `.codex`, a loop
        original_resolve = Path.resolve

        def resolve(path, strict=False):
            if Path(path) == owner:                              # only the owner's own home is unresolvable
                raise RuntimeError("symlink loop: %s" % path)    # what `Path.resolve` raises up to Python 3.12
            return original_resolve(path, strict)

        with patch.object(Path, "resolve", resolve):
            with self.assertRaises(RuntimeError):                # the resolution the guard must never use
                owner.resolve()
            env = setup.native_environment()
            self.assertEqual(Path(env["CODEX_HOME"]), self.private)
            self.assertEqual(self.ensures, [self.private])       # exactly the one profile write, into the private home
            self.assertTrue((self.private / "config.toml").is_file())
            (self.private / "auth.json").write_text("{}\n")      # a login in zplan's own home
            project = self.project("loop-proj")
            engine_env = self.engine_env(project)                # a fresh launch through `cli.main([])`
            self.assertEqual(Path(engine_env["CODEX_HOME"]), self.private)
            prepared, _header = self.prepare(project)            # the chat prepares against the private home
            self.assertEqual(prepared.environment["CODEX_HOME"], str(self.private))


class ChildAuthEnvTests(ActivationCase):
    """R-4b unit form (candidate-only helper `setup.child_auth_env`): the engine's own OPENAI->CODEX mapping, and a
    copy always. The behavioural half — the env the architect's child really receives at a spawn — stays in
    `AuthTests` and replays on the base."""

    def test_r4b_child_auth_env_maps_openai_only_when_codex_key_is_absent(self):
        self.assertEqual(setup.child_auth_env({"OPENAI_API_KEY": OPENAI_SENTINEL, "PATH": "p"}),
                         {"OPENAI_API_KEY": OPENAI_SENTINEL, "PATH": "p", "CODEX_API_KEY": OPENAI_SENTINEL})
        both = {"CODEX_API_KEY": CODEX_SENTINEL, "OPENAI_API_KEY": OPENAI_SENTINEL}
        self.assertEqual(setup.child_auth_env(both), both)          # (2) and (4b): unchanged ...
        self.assertIsNot(setup.child_auth_env(both), both)          # ... and always a copy
        empty = {"CODEX_API_KEY": "", "OPENAI_API_KEY": OPENAI_SENTINEL}
        self.assertEqual(setup.child_auth_env(empty), empty)        # (4): the empty key still blocks the fallback
        self.assertEqual(setup.child_auth_env({}), {})


class DoctorTests(ActivationCase):
    """R-5/R-3c: the default-home `doctor` reads the profile version and writes nothing. Mutation (i) in its
    default-home form — a guarded `ensure(private_codex_home())` added to `doctor` — dies here, because nothing
    else on the `doctor` path (no `attach_tools`) calls `ensure`."""

    def test_the_default_home_doctor_writes_no_profile(self):
        project = self.project("doctor-proj")
        with self.cwd(project):
            code, screen = self.main(["doctor"])
        self.assertEqual(code, 1, screen.text())          # the zplan home has no login yet
        self.assertEqual(self.ensures, [])                # doctor reads `written_version`, never writes a profile
        self.assertFalse(self.private.exists())           # an absent private home stays absent
        self.assertIn("not written yet", screen.text())   # R-5 informational line

    def test_the_default_home_doctor_survives_an_unreadable_profile_entry(self):
        """R-5: the informational profile read must never abort doctor. A `config.toml` that is a directory (an
        entry that cannot be read as a profile) is answered as "no profile yet" and the rest of the report -- the
        process profile -- still runs; the base's doctor reads no version at all and also completes, so the guard is
        the candidate's own.

        Interpretation recorded here: R-5 derives the line from `written_version`'s return alone (a version, or
        "not written yet"); it does not name an unreadable entry, so the failed read is answered as "no profile"
        rather than inventing new wording."""
        project = self.project("doctor-unreadable")
        self.private.mkdir(parents=True)
        (self.private / "config.toml").mkdir()      # an entry that cannot be read as a profile
        with self.cwd(project):
            code, screen = self.main(["doctor"])
        self.assertEqual(code, 1, screen.text())
        self.assertIn("not written yet", screen.text())
        self.assertIn("zplan.default/3", screen.text())   # the report continued past the profile line (the process profile)
        self.assertEqual(self.ensures, [])                # doctor still writes nothing


class FreshInstallTests(ActivationCase):
    """A-4 (R-1): a fresh implicit launch never reads or writes the owner's `~/.codex`; an explicit override does.
    Every assertion here goes through a production entry point, so this class replays on the base and fails at its
    behavioural assertion (the candidate-only `setup.agent_home` is exercised in `HomeResolutionTests` instead)."""

    def test_a4_a_fresh_install_never_uses_the_owner_codex_home(self):
        owner = self.home("owner-codex", owner=True, auth=True, config="[features]\napps = true\n")
        before = tree(owner)
        project = self.project()
        self.assertEqual(setup.native_environment()["CODEX_HOME"], str(self.private))
        code, screen = self.main(["login"])
        self.assertEqual(code, 0, screen.text())
        self.assertEqual(self.spy.turns(self.codex)[-1]["env"]["CODEX_HOME"], str(self.private))
        # the login file the zplan home holds, never the owner's (D6a: bytes equal to `~/.codex/auth.json` are a copy)
        (self.private / "auth.json").write_text('{"login": "zplan"}\n')
        with self.cwd(project):
            doctor_code, doctor_screen = self.main(["doctor"])
        self.assertNotIn(str(owner), doctor_screen.text())
        self.assertEqual(self.engine_env(project)["CODEX_HOME"], str(self.private))
        self.assertEqual(self.prepare(project)[0].environment["CODEX_HOME"], str(self.private))
        self.assertEqual([home for home in self.spy.homes() if home == str(owner)], [])
        self.assertEqual(tree(owner), before)                        # the owner's tree is byte-identical
        self.assertEqual(agent_profile.written_version(owner), None)  # and no profile landed in it
        self.assertEqual(doctor_code, 0, doctor_screen.text())

    def test_a4_an_explicit_owner_home_is_used_and_gets_no_profile(self):
        owner = self.home("owner-codex", owner=True, auth=True)
        before = tree(owner)
        project = self.project()
        with patch.dict(os.environ, {"CODEX_HOME": str(owner)}):
            self.assertEqual(self.engine_env(project)["CODEX_HOME"], str(owner))
            self.assertEqual(self.prepare(project)[0].environment["CODEX_HOME"], str(owner))
        self.assertEqual(self.ensures, [])
        self.assertEqual(tree(owner), before)
        self.assertFalse(self.private.exists())


class SurfacingTests(ActivationCase):
    """A-4b (R-3c): a `setup.agent_home` refusal reaches the owner and starts nothing. Mutation (g) (swallow it in
    `attach_tools`) dies here."""

    def test_a4b_a_profile_refusal_reaches_the_owner_and_starts_nothing(self):
        project = self.project()
        refusal = Blocked("Не удалось записать профиль агента в %s: busy." % self.private, family="setup.agent_home")
        with patch.object(agent_profile, "ensure", side_effect=refusal):
            code, screen = self.main(["login"])
            self.assertEqual(code, 1, screen.text())
            self.assertIn("setup.agent_home", screen.text())          # the owner sees the family ...
            self.assertNotIn("readiness.tools", screen.text())        # ... and never `readiness.tools`
            self.assertEqual(self.spy.turns(self.codex), [])          # login spawned no Codex at all
            with patch.object(cli, "choose_project", lambda *a, **k: project):
                code, screen = self.main([])
            self.assertEqual(code, 1, screen.text())
            self.assertIn("setup.agent_home", screen.text())
            self.assertNotIn("readiness.tools", screen.text())
            with self.assertRaises(Blocked) as raised:
                self.prepare(project)                                 # `default_prepare` refuses the chat with it
            self.assertEqual(catalog.family(raised.exception), "setup.agent_home")
            self.assertEqual(self.spy.turns(self.codex), [])
        self.assertFalse(self.private.exists())


class AuthTests(ActivationCase):
    """A-6 (R-4, R-4b): one auth rule for doctor, `default_prepare` and a resumed turn; values never printed.
    Mutations (f) (ignore the key variables), (f2) (an empty `CODEX_API_KEY` is absent) and (f3) (no child env)
    die here."""

    def verdicts(self, home, keys):
        """(doctor's auth item, a new thread, a resumed turn) for one home and one set of provider variables."""
        project = self.project("auth-proj")
        environment = {name: value for name, value in os.environ.items() if name not in PROVIDER_VARS}
        environment.update(keys)
        environment["CODEX_HOME"] = str(home)
        with patch.dict(os.environ, environment, clear=True):
            item = next(i for i in setup.readiness(None) if i["id"] == "auth")
            try:
                self.prepare(project)
                new_thread = True
            except Blocked:
                new_thread = False
            try:
                architect.check_home(home, dict(os.environ), True)   # a resumed turn: None, or the refusal
                resumed = True
            except Blocked:
                resumed = False
        return (item["ok"], item["key"]), new_thread, resumed

    def test_a6_file_auth_verdicts_agree_in_doctor_preparation_and_a_resumed_turn(self):
        with_file = self.home("with-file", auth=True)
        plain = self.home("plain")  # an override home is the owner's own Codex (D6a): no [l], the instruction key [i]
        cases = (
            ("auth.json", with_file, {}, (True, None)),
            ("CODEX_API_KEY", plain, {"CODEX_API_KEY": CODEX_SENTINEL}, (True, None)),
            ("OPENAI_API_KEY fallback", plain, {"OPENAI_API_KEY": OPENAI_SENTINEL}, (True, None)),
            ("empty CODEX_API_KEY blocks the fallback", plain,
             {"CODEX_API_KEY": "", "OPENAI_API_KEY": OPENAI_SENTINEL}, (False, "i")),
            ("both keys", plain, {"CODEX_API_KEY": CODEX_SENTINEL, "OPENAI_API_KEY": OPENAI_SENTINEL}, (True, None)),
            ("both empty", plain, {"CODEX_API_KEY": "", "OPENAI_API_KEY": ""}, (False, "i")),
            ("neither, and no auth.json", plain, {}, (False, "i")),
        )
        for label, home, keys, doctor in cases:
            with self.subTest(label):
                self.assertEqual(self.verdicts(home, keys), (doctor, doctor[0], doctor[0]))

    def test_a6_env_key_providers_keep_their_own_branch(self):
        home = self.home("custom", config='model_provider = "corp"\n[model_providers.corp]\nname = "C"\n'
                                          'base_url = "https://llm.example/v1"\nenv_key = "CORP_KEY"\n')
        for keys, doctor in (({"CORP_KEY": CODEX_SENTINEL}, (True, None)), ({"CORP_KEY": ""}, (False, "i")), ({}, (False, "i"))):
            with self.subTest(keys):
                self.assertEqual(self.verdicts(home, keys), (doctor, doctor[0], doctor[0]))

    def test_a6_a_codex_key_env_provider_is_refused_before_a_resumed_child(self):
        """R-4/A-6 parity against R-4b: a custom provider whose `env_key` is `CODEX_API_KEY` gets one verdict in all
        three judges. `test_a6_env_key_providers_keep_their_own_branch` judges `check_home` directly; this one runs
        an *actual* resumed turn through the scripted codex, so it fails on the candidate that mapped the child env
        (R-4b) before the auth check and so let a resumed turn complete that readiness and preparation refuse.

        Interpretation recorded here (the worker summary never reaches the reviewers): R-4's env-key rule is
        unconditional (`env.get(NAME)` non-empty) and R-4b's mapping is scoped to the OPENAI_API_KEY *file*-auth
        route, so a turn's auth verdict is judged on the owner's own env, before the child mapping. With only
        OPENAI_API_KEY set the provider is unserved everywhere: readiness says (False, 'i'), `default_prepare`
        refuses a new thread, and a resumed turn refuses before any child (family `architect.home_lost`, s2a3's own
        resumed refusal). With `CODEX_API_KEY` set the turn completes and the child receives exactly that value."""
        config = ('model_provider = "corp"\n[model_providers.corp]\nname = "C"\n'
                  'base_url = "https://llm.example/v1"\nenv_key = "CODEX_API_KEY"\n')
        home = self.home("codex-key-home", config=config)
        project = self.project("codex-key-proj")
        with patch.dict(os.environ, {"OPENAI_API_KEY": OPENAI_SENTINEL, "CODEX_HOME": str(home)}):
            item = next(i for i in setup.readiness(None) if i["id"] == "auth")
            self.assertEqual((item["ok"], item["key"]), (False, "i"))
            with self.assertRaises(Blocked) as prepared:
                self.prepare(project)                       # a new thread: the same verdict, refused
            self.assertEqual(catalog.family(prepared.exception), "readiness.auth")
            store = ArchitectStore(project)
            store.session_path.parent.mkdir(parents=True, exist_ok=True)
            store.session_path.write_text(json.dumps({"version": 1, "thread_id": THREAD, "codex_home": str(home),
                                                      "model": MODEL, "created": "2026-01-01T00:00:00Z", "turns": 1,
                                                      "usage": {}}))
            resumed = self.architect_instance(project, home)
            self.assertEqual(resumed.next_home(), (home, True))
            with self.assertRaises(Blocked) as refused:
                resumed.send("привет")                      # the actual turn: refused before any child
            self.assertEqual(catalog.family(refused.exception), "architect.home_lost")
            self.assertEqual(self.spy.turns(self.codex), [])
        with patch.dict(os.environ, {"CODEX_API_KEY": CODEX_SENTINEL, "CODEX_HOME": str(home)}):
            self.assertEqual(next(i for i in setup.readiness(None) if i["id"] == "auth")["ok"], True)
            self.architect_instance(project, home).send("привет")
            spawn = self.spy.turns(self.codex)[-1]["env"]
            self.assertEqual(spawn.get("CODEX_API_KEY"), CODEX_SENTINEL)

    def test_a6_the_device_login_runs_in_the_private_home(self):
        self.script([{"exit": 1}, {"exit": 0}])   # D6a: `codex login status` first -- not logged in, so the device login runs
        code, screen = self.main(["login"])
        self.assertEqual(code, 0, screen.text())
        launch = self.spy.turns(self.codex)[-1]
        self.assertEqual(launch["argv"][-2:], ["login", "--device-auth"])
        self.assertEqual(launch["env"]["CODEX_HOME"], str(self.private))
        self.assertEqual(agent_profile.written_version(self.private),
                         agent_profile.version(agent_profile.packaged()))

    def test_a6_the_architect_child_env_mirrors_the_engine_mapping(self):
        """(3), (2) and (4b) at the spawn: the env Codex actually receives. Goes through production entry points
        only, so it replays on the base and fails there at the spawned-env assertion (the pure helper is checked in
        `ChildAuthEnvTests`). The home is seeded (`auth.json`) so the base's auth check still lets the turn run."""
        project, home = self.project("child-proj"), self.home("child-home", auth=True)
        with patch.dict(os.environ, {"OPENAI_API_KEY": OPENAI_SENTINEL}):    # (3): the engine's own mapping
            result = self.architect_instance(project, home).send("привет")
            self.assertEqual(result.status, "completed", result.cause)
            self.assertEqual(self.spy.turns(self.codex)[-1]["env"].get("CODEX_API_KEY"), OPENAI_SENTINEL)
        for keys in ({"CODEX_API_KEY": CODEX_SENTINEL},                      # (2) and (4b): an existing key stays
                     {"CODEX_API_KEY": CODEX_SENTINEL, "OPENAI_API_KEY": OPENAI_SENTINEL}):
            with patch.dict(os.environ, keys):
                self.architect_instance(project, home).send("привет")
                self.assertEqual(self.spy.turns(self.codex)[-1]["env"].get("CODEX_API_KEY"), CODEX_SENTINEL)

    def test_a6_the_empty_codex_key_refuses_the_turn_before_any_child(self):
        project, home = self.project("refuse-proj"), self.home("refuse-home")
        with patch.dict(os.environ, {"CODEX_API_KEY": "", "OPENAI_API_KEY": OPENAI_SENTINEL}):
            with self.assertRaises(Blocked) as raised:
                self.architect_instance(project, home).send("привет")   # (4): refused before the Popen
        self.assertEqual(catalog.family(raised.exception), "readiness.auth")
        self.assertEqual(self.spy.turns(self.codex), [])

    def test_a6_no_sentinel_value_reaches_a_line_a_reply_or_a_transcript(self):
        project, home = self.project("leak-proj"), self.home("leak-home", auth=True)
        keys = {"CODEX_API_KEY": CODEX_SENTINEL, "OPENAI_API_KEY": OPENAI_SENTINEL}
        with patch.dict(os.environ, keys):
            with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                code, screen = self.main(["doctor", "--project", str(project)])
                result = self.architect_instance(project, home).send("привет")
        text = screen.text() + "\n" + (result.text or "")
        transcript = json.dumps(ArchitectStore(project).transcript(), default=str)
        self.assertNotIn(CODEX_SENTINEL, text + transcript)
        self.assertNotIn(OPENAI_SENTINEL, text + transcript)

    def test_a6_only_unserved_file_auth_offers_the_login_key(self):
        corp = ('model_provider = "corp"\n[model_providers.corp]\nname = "C"\n'
                'base_url = "https://llm.example/v1"\nenv_key = "CORP_KEY"\n')
        self.private.mkdir(parents=True)
        # D6a: [l] is offered for zplan's own home only; the same missing file login in an override home is [i]
        for label, config, key, home in (("file", None, "l", self.private), ("file override", None, "i", None),
                                         ("env-key", corp, "i", None)):
            with self.subTest(label):
                home = home or self.home("key-" + label, config=config)
                with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                    item = next(i for i in setup.readiness(None) if i["id"] == "auth")
                self.assertEqual((item["ok"], item["key"]), (False, key))
                self.assertEqual("[l]" in item["detail"], key == "l")


class EndToEndTests(ActivationCase):
    """A-7 (with s2a): a fresh install records zplan's own home on a new attempt and a new architect thread, and the
    thread records that home in its session; a record keeps the home it was frozen with, so its continuation spawns
    Codex in the *recorded* home even when the process env names another one (R-5). The turns really run the
    scripted codex through the process spies, so the stored session and the spawned `CODEX_HOME` are observed."""

    def test_a7_a_fresh_install_records_the_private_home(self):
        project = self.project("e2e-proj")
        engine_env = self.engine_env(project)                 # an attempt: the env cli hands the planner and driver
        self.assertEqual(engine_env["CODEX_HOME"], str(self.private))
        instance = engine.NativeEngine(self.zeroshot, self.root / "zp", environment=engine_env)
        self.assertEqual(instance.codex_home(), self.private)
        (self.private / "auth.json").write_text("{}\n")       # the login the zplan home holds after `zplan login`
        # A *real* fresh attempt: an approved native plan and one `MilestoneRuns.start` (the milestone writer).
        recorded, commands = self.native_attempt(engine_env, [{"valid": True}, {"runId": "m-run"}])
        self.assertEqual([command[0] for command in commands], ["run", "run"])   # validated, then detached
        expected = self.root / "data" / "planning-kit" / "codex-home"   # the private home, from the fixture layout
        self.assertEqual(recorded["binding"].get("codex_home"), str(expected))   # the attempt persisted the home
        self.assertEqual(str(setup.private_codex_home()), str(expected))         # and it is zplan's own home
        self.assertTrue(toolchain.valid_binding(recorded["binding"]))
        self.assertEqual(record_home.binding_home(recorded["binding"]), expected)
        prepared, _header = self.prepare(project)             # a new architect thread
        self.assertEqual(prepared.next_home(), (self.private, False))
        self.assertEqual(prepared.environment["CODEX_HOME"], str(self.private))
        prepared.send("привет")                               # the turn really runs and persists the thread
        session = ArchitectStore(project).load()
        self.assertEqual(session["thread_id"], THREAD)
        self.assertEqual(session.get("codex_home"), str(self.private))   # R-5: the thread records its home
        elsewhere = self.home("elsewhere", auth=True)         # the process env moves on the next launch ...
        with patch.dict(os.environ, {"CODEX_HOME": str(elsewhere)}):
            resumed = self.architect_instance(project, elsewhere)
            self.assertEqual(resumed.next_home(), (self.private, True))   # ... but the thread keeps its own home
            resumed.send("ещё")                                # the continuation spawns Codex in the recorded home
        self.assertEqual(self.spy.turns(self.codex)[-1]["env"]["CODEX_HOME"], str(self.private))

    def native_attempt(self, environment, responses):
        """A real fresh attempt for `EndToEndTests`: an approved native plan (through the harness the other modules
        already use) and one `MilestoneRuns.start` whose driver env is `environment`. Returns the saved record and
        the scripted native CLI's argv tails, so the persisted home *and* the fact that the attempt really ran are
        both observable. The harness is a function-local subclass, so unittest never collects its own tests."""
        harness = _native_plan_harness()("runTest")
        harness.setUp()
        try:
            harness.approve_native()
            engine_double, calls = harness.fake(responses)
            driver = NativeDriver(engine_double.executable, engine_double.state_root, call=engine_double.call,
                                  sleep=lambda _: None, environment=environment)
            with harness.authority() as authority:
                controller = MilestoneRuns(authority, driver, worktrees=harness.root / "worktrees")
                return controller.start("M1", 1, runs_tests.ROLES), [call[0][1:] for call in calls]
        finally:
            harness.doCleanups()

    def test_a7_a_record_still_spawns_with_its_own_home(self):
        legacy, recorded = self.home("legacy-codex", auth=True), self.home("recorded-codex", auth=True)
        project = self.project("record-proj")
        store = ArchitectStore(project)
        store.session_path.parent.mkdir(parents=True, exist_ok=True)
        store.session_path.write_text(json.dumps({"version": 1, "thread_id": THREAD, "model": MODEL,
                                                  "created": "2026-01-01T00:00:00Z", "turns": 1, "usage": {}}))
        with patch.dict(os.environ, {"CODEX_HOME": str(legacy)}):   # a pre-0.5 session: no recorded home
            self.assertEqual(record_home.effective_home(None), setup.legacy_codex_home())
            pre = self.architect_instance(project, legacy)
            self.assertEqual(pre.next_home(), (legacy, True))
            pre.send("привет")                                        # the child really runs in the legacy home
            self.assertEqual(self.spy.turns(self.codex)[-1]["env"]["CODEX_HOME"], str(legacy))
        store.session_path.write_text(json.dumps({"version": 1, "thread_id": THREAD, "codex_home": str(recorded),
                                                  "model": MODEL, "created": "2026-01-01T00:00:00Z", "turns": 1,
                                                  "usage": {}}))
        with patch.dict(os.environ, {"CODEX_HOME": str(legacy)}):   # an s2a session keeps its own home
            post = self.architect_instance(project, legacy)
            self.assertEqual(post.next_home(), (recorded, True))
            post.send("ещё")                                          # ... even though the env names `legacy`
            self.assertEqual(self.spy.turns(self.codex)[-1]["env"]["CODEX_HOME"], str(recorded))


class IsolationTests(unittest.TestCase):
    """R-8: the sentinel is the runner's real private home, captured at import, not a fixture's temporary one. The
    definitive "unchanged after the module" comparison lives in `tearDownModule`, not here (see its docstring)."""

    def test_the_sentinel_is_the_process_home_not_a_fixtures(self):
        self.assertEqual(SENTINEL.name, "codex-home")
        self.assertNotIn("zs-activation-", str(SENTINEL))          # never a fixture root of this module
        self.assertEqual(str(setup.private_codex_home()), str(SENTINEL))


def tearDownModule():
    """R-8: after the whole module (every fixture restored) the runner's own private home is byte-for-byte as it was
    at import. unittest loads test classes in alphabetical order, so a comparison inside a test class runs before the
    classes that sort after it; only a module teardown can compare after them all. Raising here is reported as an
    error by unittest."""
    if str(setup.private_codex_home()) != str(SENTINEL):
        raise AssertionError("the module resolved a different private home: %r" % (setup.private_codex_home(),))
    state = sorted(path.name for path in SENTINEL.iterdir()) if SENTINEL.is_dir() else None
    if state != SENTINEL_STATE:
        raise AssertionError("the module wrote into the runner's own private home %s: %r" % (SENTINEL, state))


if __name__ == "__main__":
    unittest.main()
