"""Home wiring (S2 slice s2a2; parent R-3, R-4, A-1 store half, A-2, A-3, A-4, A-7): a record acts in the Codex home it
was frozen with, and that home is not part of the identity a record is compared by.

Worker interpretations (the reviewers never see the worker's summary): a pre-0.5 four-key record acts in the *process*
home (`setup.legacy_codex_home()`, R-1); `engine_for` compares a record's home against this engine's own home — its env
`CODEX_HOME` *as stored* when that value is present and non-empty, else the effective default `str(self.codex_home())`
(s2a2b R-1, replacing the s2a2 as-stored-only comparison) — and never re-resolves a recorded `..`/symlink home, so
`bound.engine_for(binding) is bound` for every valid native binding (gate5 point 1), while an alias spelling is an
ordinary four-field refusal, never a loop; a same-binary home sibling keeps this engine's root and version, an
older-toolchain sibling uses the *recorded* root and version plus its `codex/node_modules/.bin` PATH prefix; an
unresolvable spelling (a symlink loop) takes `toolchain.mismatch` instead of a `RuntimeError` (R-2); every A-1st/A-4 row
freezes a literal record, failing on the base at its behavioral assertion, not on import (A-B).
"""

import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

import test_runs as runs_tests
import test_terminal_planner as planner
from terminal_planner import engine as engine_module
from terminal_planner import live, toolchain
from terminal_planner.authority import Blocked, canonical
from terminal_planner.engine import NativeEngine, PHASES, SliceEnded, Stale
from terminal_planner.planning import Planning
from terminal_planner.runs import MilestoneRuns, NativeDriver

ROLES = planner.ROLES
REASON = "The scope is intentional; the owner accepts the risk."
BINDING_FIELDS = toolchain.BINDING_FIELDS
OMITTED = object()  # `fixtures`: the argument was not given (an explicit `None` is an env without `CODEX_HOME`)


def timeout():
    """A watch ended by its slice (no trailing record): the engine detaches, the next call continues."""
    return subprocess.TimeoutExpired("watch", 1, output="")


def native_spy(version):
    """A `native_run` double recording (argv, kwargs) of every process, `--version` probes included (A-2)."""
    calls = []

    def run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, version + "\n", "")

    return run, calls


class Homes:
    """The pieces both flow classes build on: homes, state roots, the fake binary, the doubles and the writers."""

    revision_version = 1

    def homes(self):
        self.probes = []                        # every `--version` probe's env, per test (see `fixtures`)
        self.home = self.root / "home"          # the process HOME every env below names
        self.recorded_home, self.current_home = self.root / "home-a", self.root / "home-b"
        for path in (self.home, self.recorded_home, self.current_home):
            path.mkdir(exist_ok=True)
        self.native_state, self.other_state = (Path(tempfile.mkdtemp(prefix="z")).resolve() for _ in range(2))  # short: macOS sockets <104 bytes
        for path in (self.native_state, self.other_state):
            self.addCleanup(shutil.rmtree, path, ignore_errors=True)

    def env(self, codex_home):
        """An engine env: the test HOME and an explicit CODEX_HOME (`None`: absent, `""`: empty)."""
        return {"HOME": str(self.home), "PATH": os.environ.get("PATH", ""), **({} if codex_home is None else {"CODEX_HOME": str(codex_home)})}

    @contextlib.contextmanager
    def process_env(self, codex_home=None, extra=None):
        """The process env (HOME, CODEX_HOME, `extra`) as `setup.legacy_codex_home()` reads it, restored on exit."""
        values = {"HOME": str(self.home), **(extra or {}), **({} if codex_home is None else {"CODEX_HOME": str(codex_home)})}
        with patch.dict(os.environ, values):
            if codex_home is None:
                os.environ.pop("CODEX_HOME", None)
            yield

    def binary(self, extra=b"", name="zeroshot-fixture", version=None):
        """The fake `#!/bin/sh` binary every engine runs; `extra` is appended, so the sha256 can change."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"#!/bin/sh\nprintf '%s\\n'\n" % (version or toolchain.current().zeroshot_version).encode() + extra)
        path.chmod(0o700)
        return path

    def fixtures(self, responses, codex_home=OMITTED, watch=None):
        """`NativeTests.engine` with an explicit env; each `--version` probe's env is appended to `self.probes`.
        `codex_home` omitted is the recorded home; an explicit `None` is an env whose `CODEX_HOME` key is absent."""
        engine, calls = planner.NativeTests.engine(self, responses, watch)
        engine.environment = self.env(self.recorded_home if codex_home is OMITTED else codex_home)

        def call(argv, _inner=engine.call, **kwargs):  # the planner's own double, recorded through
            if argv[1:] == ["--version"]:
                self.probes.append(kwargs.get("env"))
            return _inner(argv, **kwargs)

        engine.call = call
        return engine, calls

    def home_of(self, calls):  # the envs of `calls`, every CODEX_HOME asserted to be the recorded home
        self.assertEqual({c[1]["env"]["CODEX_HOME"] for c in calls}, {str(self.recorded_home.resolve())})
        return [c[1]["env"] for c in calls]

    def link(self, name, target):
        path = self.root / name  # a symlink spelling of `target`, for the never-resolved-away cases
        path.symlink_to(target)
        return path

    def freeze_plan(self, binding):  # a literal revision binding of this test's own (A-B), intent and evidence recomputed
        with self.authority() as a:
            r = a.current
            r["native_binding"] = binding
            r["intent"] = a.intent_identity(r)
            if r["evidence"] is not None:
                r["proposal"], r["evidence"] = a.review_evidence(r, r["terminal_cursor"], r["terminal_envelope"]["status"]["terminalResult"]["output"])
            a.save()

    def freeze_run(self, binding):  # a literal milestone binding of this test's own, in the store (A-B)
        with self.authority() as a:
            a.state["runs"][0]["binding"] = binding
            a.save()

    def control_native(self):
        """R-5: `native_run` — the default `call` of `recorded_engine`, the one `RunsTest.approve_native` reaches through
        `Authority.approve` — is stubbed, and every env it is asked to run in is recorded in `self.setup_probes`."""
        def run(argv, **kwargs):
            self.setup_probes.append(kwargs.get("env") or {})  # an engine built without an env records no home at all (the base)
            return subprocess.CompletedProcess(argv, 0, toolchain.current().zeroshot_version + "\n", "")
        self.setup_probes, patcher = [], patch.object(engine_module, "native_run", run)
        patcher.start()
        self.addCleanup(patcher.stop)


class PlanTests(runs_tests.RunsTest, Homes):
    """A-1st (planning half), R-3 idempotence, R-4 (prepared but unsent) and A-4 for the plan revision."""

    running = planner.NativeTests.running
    terminal = planner.NativeTests.terminal

    def setUp(self):
        super().setUp(); self.homes()
        self.control_native()

    def projection(self, status, cursor="v2:10"):
        """`NativeTests.projection` titled for the revision under test (`begin` numbers revisions 1, 2, ...)."""
        value = planner.NativeTests.projection(self, status, cursor)
        value["title"] = "Terminal roadmap revision %s" % self.revision_version
        return value

    def prepared(self, codex_home, run_id="fixture-native-run"):
        """A `prepare`d revision: detached with a run id, or `planning` without one (frozen, unsent)."""
        engine, calls = self.fixtures([{"valid": True}, {"runId": run_id}, timeout()] if run_id else [{"valid": False}], codex_home=codex_home)
        with self.authority() as a:
            self.begin(a, "native")
            with self.assertRaises(SliceEnded if run_id else Blocked):
                engine.proposal(a, lambda _: None, slice=1 if run_id else None)
            self.assertEqual((a.current["status"], a.current["run_id"]), ("detached", run_id) if run_id else ("planning", None))

    def literal(self, home=None, executable=None):
        """Respell the stored revision into a literal record of this test's own (A-B): `home` and/or `executable`."""
        with self.authority() as a:
            four = {k: a.current["native_binding"][k] for k in BINDING_FIELDS}
            recorded = a.current["native_binding"].get("codex_home")
        self.freeze_plan({**four, "codex_home": str(home or recorded or self.recorded_home), **({"executable": str(executable)} if executable else {})})

    def gate(self, verdict="accepted"):
        """A literal record of this test's own (A-B) for the plan gate of `verdict`: `proposed`/`review_exhausted`."""
        with self.authority() as a:
            self.revision_version = len(a.state["revisions"]) + 1 if a.state else 1
        engine, _calls = self.fixtures([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal(verdict))], codex_home=self.recorded_home)
        with self.authority() as a:
            self.begin(a, "native")
            engine.proposal(a, lambda _: None)
        self.literal()

    def test_a1st_a_new_planning_revision_stores_the_engine_env_home(self):
        """A-1 store half: the revision stores the engine env's home, passes `valid_binding`, and its digests cover it."""
        engine, calls = self.fixtures([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal())], codex_home=self.recorded_home)
        with self.process_env(self.current_home), self.authority() as a:  # the process env names another home
            self.begin(a, "native")
            engine.proposal(a, lambda _: None)
            binding = a.current["native_binding"]
            self.assertEqual(set(binding), set(BINDING_FIELDS) | {"codex_home"})
            self.assertEqual(binding["codex_home"], str(self.recorded_home.resolve()))  # the engine env, not process
            self.assertTrue(toolchain.valid_binding(binding))
            moved = copy.deepcopy(a.current)
            moved["native_binding"]["codex_home"] = str(self.current_home)
            self.assertNotEqual(a.intent_identity(moved), a.current["intent"])  # the home is in the intent
            self.assertNotEqual(a.approval_identity(dict(moved, intent=a.intent_identity(moved))), a.approval_identity(a.current))
        self.home_of(calls)

    def test_r3_engine_for_is_idempotent_for_every_valid_native_binding(self):
        """R-3 (gate5 point 1): `bound.engine_for(binding) is bound` for a `..` home, a symlink home, a missing home and an alias executable."""
        self.prepared(self.recorded_home)
        with self.authority() as a:
            four = {k: a.current["native_binding"][k] for k in BINDING_FIELDS}
        actor, missing = self.fixtures([], codex_home=self.current_home)[0], self.root / "not-there"
        for home, executable in ((str(self.recorded_home / ".." / "home-a"), None), (str(self.link("link-home", self.recorded_home)), None), (str(missing), None),
                                 (str(self.recorded_home), self.link("zeroshot-alias", four["executable"]))):
            binding = {**four, "codex_home": home, **({"executable": str(executable)} if executable else {})}
            bound = actor.engine_for(binding)
            self.assertIs(bound.engine_for(binding), bound, home)
            self.assertIsNot(bound, actor)  # another home: a sibling, none the less
            self.assertEqual((bound.executable, bound.state_root), (actor.executable, actor.state_root))
            self.assertEqual(bound.native_environment()["CODEX_HOME"], home)  # as stored, never re-resolved
        self.assertFalse(missing.exists())  # a missing home is passed through as is: no substitute, no mkdir

    def test_a_plan_revision_whose_executable_cannot_be_resolved_is_refused_not_crashed(self):
        """R-2 (regression): a plan revision whose recorded executable spelling cannot be resolved — a self-referencing
        symlink — gets `proposal`'s existing `toolchain.mismatch` refusal, and `failure_cause` (which swallows Blocked)
        finds no cause, instead of the `RuntimeError` a bare `resolve()` raises (the base compares plain strings)."""
        self.gate("accepted")  # a literal submitted revision of this test's own (A-B)
        self.literal(executable=self.link("zeroshot-loop", self.root / "zeroshot-loop"))
        actor, calls = self.fixtures([], codex_home=self.current_home)
        with self.process_env(self.current_home), self.authority() as a:
            self.assertEqual(a.current["native_binding"]["executable"], str(self.root / "zeroshot-loop"))
            with self.assertRaisesRegex(Blocked, "toolchain"):
                actor.proposal(a, lambda _: None)
            self.assertIsNone(actor.failure_cause(a))
        self.assertEqual(calls, [])  # neither ever reached a native invocation

    def test_r4_a_prepared_unsent_revision_is_submitted_in_its_recorded_home(self):
        """R-4/A-2: the prepared-unsent revision is submitted in the record's home (probe included); another state root still reaches Stale."""
        self.prepared(self.recorded_home, run_id=None)
        other, other_calls = self.fixtures([], codex_home=self.current_home)  # a state-root change is a real change
        other.state_root = self.other_state
        with self.authority() as a:
            before = canonical(a.state["revisions"][0])
            with self.assertRaises(Stale):
                other.proposal(a, lambda _: None)  # still unsent: a four-field difference reaches prepare's Stale
            self.assertEqual(canonical(a.state["revisions"][0]), before)  # nothing rewritten
        self.assertEqual([c[0][1] for c in other_calls], [])  # nothing reached Zeroshot
        with self.process_env(self.current_home):
            self.probes = []
            actor, actor_calls = self.fixtures([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal())], codex_home=self.current_home)
            with self.authority() as a:
                frozen = copy.deepcopy(a.current["native_binding"])
                actor.proposal(a, lambda _: None)
                self.assertEqual(a.current["status"], "proposed")
                self.assertEqual(a.current["native_binding"], frozen)
        self.assertEqual([c[0][1] for c in actor_calls], ["run", "run", "watch"])
        self.home_of(actor_calls)
        self.assertTrue(self.probes)  # every probe (the delegation's and the submission's) ran in the record's home
        self.assertEqual({env["CODEX_HOME"] for env in self.probes}, {str(self.recorded_home.resolve())})

    def test_a2_a_detached_revision_is_observed_in_its_recorded_home_and_an_alias_never_recurses(self):
        """A-2 observation and R-1 idempotence: the home is used as stored; an absent/empty env home names the effective
        default (R-1), so it is this engine's own only for a record that names exactly that default."""
        self.prepared(self.recorded_home)  # a record left detached mid-watch, its binding frozen in home A
        executable = self.fixtures([], codex_home=self.current_home)[0].executable  # the fixture binary, resolved
        for home in (str(self.recorded_home / ".." / "home-a"), str((self.home / ".codex").resolve())):
            with self.subTest(home=home):
                self.literal(home)
                actor, calls = self.fixtures([timeout()], codex_home=self.recorded_home)
                with self.process_env(self.current_home), self.authority() as a:
                    frozen = copy.deepcopy(a.current["native_binding"])
                    with self.assertRaises(SliceEnded):
                        actor.proposal(a, lambda _: None, slice=1)
                    self.assertEqual(a.current["native_binding"], frozen)  # the frozen binding is not rebound
                self.assertEqual([c[0][1:] for c in calls], [["watch", "fixture-native-run"]])
                self.assertEqual(calls[0][1]["env"]["CODEX_HOME"], home, "the home as stored, never re-resolved")
        default = str((self.home / ".codex").resolve())  # the effective home of an engine env without `CODEX_HOME`
        for home, overridden in ((str(self.recorded_home / ".." / "home-a"), True), (default, False)):
            for absent in (None, ""):  # R-1: the record's home *is* this engine's effective default, so such an engine
                with self.subTest(env_home=absent, home=home), self.process_env(self.current_home):  # keeps its env
                    self.literal(home)
                    self.probes = []
                    actor, calls = self.fixtures([timeout()], codex_home=absent)
                    self.assertEqual(actor.native_environment().get("CODEX_HOME", "<absent>"), "<absent>" if absent is None else absent)  # absent, or empty
                    with self.authority() as a, self.assertRaises(SliceEnded):
                        actor.proposal(a, lambda _: None, slice=1)
                    expected = home if overridden else ("<absent>" if absent is None else "")
                    self.assertEqual([c[1]["env"].get("CODEX_HOME", "<absent>") for c in calls], [expected])
                    self.assertEqual({env.get("CODEX_HOME", "<absent>") for env in self.probes}, {expected})  # the probe too
        self.literal(home, executable=self.link("zeroshot-alias", executable))
        with self.process_env(self.current_home), self.authority() as a, \
                self.assertRaisesRegex(Blocked, "binary/state"):  # the four fields, never a delegation loop
            self.fixtures([], codex_home=self.current_home)[0].proposal(a, lambda _: None)

    def test_a4_approve_and_override_revalidate_in_the_records_own_root_and_home(self):
        """A-4/A-2 (gate5 points 3, 4): a home is no Stale, a state root still is; `approve`/`override` revalidate in the
        frozen record's own root and home (never the session's), refuse a changed frozen binding, older binaries keeping
        their PATH prefix."""
        self.prepared(self.recorded_home, run_id=None)
        self.literal(self.recorded_home / ".." / "home-a")  # a literal home with `..`, never re-resolved
        with self.process_env(self.current_home), self.authority() as a:
            before, actor = a.path.read_bytes(), self.fixtures([], codex_home=self.current_home)[0]
            self.assertEqual(actor.prepare(a)[0], a.directory / "revision-1")  # no Stale for another home
            self.assertEqual(a.path.read_bytes(), before)
            planning = Planning(a, None, lambda name, terminal: actor)
            self.assertTrue(planning.unsent())
            self.assertFalse(planning.binding_changed())
            self.assertFalse(planning.stale())
        other, _calls = self.fixtures([], codex_home=self.current_home)
        other.state_root = self.other_state
        with self.process_env(self.current_home), self.authority() as a:
            self.assertTrue(Planning(a, None, lambda name, terminal: other).binding_changed())
            with self.assertRaises(Stale):
                other.prepare(a)
        real, built = engine_module.NativeEngine, []
        def factory(*args, **kwargs):  # the record's own engine: its root and home are not in its argv
            built.append((str(args[0]), str(Path(args[1]).resolve()), (kwargs.get("environment") or {}).get("CODEX_HOME")))
            return real(*args, **kwargs)

        for verdict, act in (("accepted", "approve"), ("rejected", "override")):
            built.clear()
            self.gate(verdict)
            with self.authority() as a:  # the frozen intent/identity check, not the current session's root
                version, before = a.current["version"], a.path.read_bytes()
                a.current["native_binding"]["state_root"] = str(self.other_state)
                with self.assertRaises(Blocked):  # the frozen intent/identity check refuses both entries
                    a.approve(version) if act == "approve" else a.override(version, REASON)
                self.assertEqual(a.path.read_bytes(), before)
            run, calls = native_spy(toolchain.current().zeroshot_version)
            with self.process_env(self.current_home, {"ZEROSHOT_STATE_DIR": str(self.other_state / "runs")}), \
                    patch.object(engine_module, "native_run", run), patch.object(engine_module, "NativeEngine", factory):
                with self.authority() as a:
                    a.approve(version) if act == "approve" else a.override(version, REASON)
                    self.assertEqual(a.current["status"], "approved")
                    frozen = copy.deepcopy(a.current["native_binding"])
            self.assertEqual(built, [(frozen["executable"], str(Path(frozen["state_root"]).resolve()), str(self.recorded_home.resolve()))])
            self.assertEqual([c[0][0] for c in calls], [frozen["executable"]])
        older = {"executable": str(self.binary(name="old/zeroshot", version="zeroshot 10.10.1")), "state_root": str(self.native_state),
                 "version": "zeroshot 10.10.1", "codex_home": str(self.recorded_home), "sha256": hashlib.sha256((self.root / "old/zeroshot").read_bytes()).hexdigest()}
        bin_dir = self.root / "old/codex/node_modules/.bin"
        bin_dir.mkdir(parents=True)
        for verdict, act in (("accepted", "approve"), ("rejected", "override")):
            self.gate(verdict)
            self.freeze_plan(dict(older))
            run, calls = native_spy(older["version"])
            with self.process_env(self.current_home), patch.object(engine_module, "native_run", run):
                with self.authority() as a:
                    a.approve(self.revision_version) if act == "approve" else a.override(self.revision_version, REASON)
                    self.assertEqual(a.current["status"], "approved")
                    self.assertEqual(a.current["native_binding"], older)  # never rewritten
            self.assertTrue(calls)
            self.assertEqual({env["PATH"].split(os.pathsep)[0] for env in self.home_of(calls)}, {str(bin_dir)})


    def tagged(self, value, run_id):
        """A projection of this test's own run: `NativeTests` hardcodes the fixture run id, one per module stream."""
        value = copy.deepcopy(value)
        value["runId"] = run_id
        return value

    def node_status(self, node, cursor):
        """A running projection whose only active execution is `node`."""
        return self.projection({"phase": "running", "activeExecutions": [{"node": node, "execution": "e-" + cursor}]}, cursor)

    def closing_slice(self, *records):
        """A watch ended by its slice with `records` read (no trailing newline): the engine detaches, the next call continues."""
        return subprocess.TimeoutExpired("watch", 1, output="".join(canonical(r) + "\n" for r in records).encode())

    def phase_journey(self, run_id, nodes, progress):
        """A detached revision of `run_id` observed slice by slice, each slice by a fresh delegated engine: the acting
        engine's env home is this test's current home, the record's own is another (R-1 makes every slice a sibling)."""
        self.prepared(self.recorded_home, run_id=run_id)
        responses = [self.closing_slice(self.tagged(status, run_id)) for status in nodes] + \
                    [(self.tagged(self.terminal(), run_id),)] * 2  # the terminal record, then the full replay of it
        actor, _calls = self.fixtures(responses, codex_home=self.current_home)
        with self.process_env(self.current_home), self.authority() as a:
            for _ in nodes:
                with self.assertRaises(SliceEnded):
                    actor.proposal(a, progress, slice=1)
            actor.proposal(a, progress)

    def test_a2_engine_for_keeps_the_engine_whose_own_home_a_record_names(self):
        """R-1/A-2 table over the task's domain: env `CODEX_HOME` absent, empty, an absolute path, a path with `..`,
        a legacy four-key record, and recorded `..`, symlink and trailing-separator spellings.

        Interpretations recorded here for the reviewers (they never see the worker's summary): this engine's own home
        is its env `CODEX_HOME` *as stored* when present and non-empty, else the effective default of an env without
        it — `str(codex_home())`, i.e. the process `HOME`'s `.codex` (s2a2b R-1). An absent or empty env home is
        therefore this engine's own exactly when the record names that default, and otherwise a sibling whose
        `CODEX_HOME` is the recorded string untouched: a `..`/symlink alias of the engine's own home may get a
        sibling. The engine's stored value is read from `native_environment()`, so a `.get()`-absent key stays absent.
        A recorded home is compared and delegated *in its own spelling* (the repair of the s2a2b code review's first
        finding): `str(Path(home))` drops a trailing separator, so a home recorded as `/…/home-a/` must compare equal
        to the same env value and must reach a sibling as `/…/home-a/` again — never as `/…/home-a`.
        """
        self.prepared(self.recorded_home)
        with self.authority() as a:
            four = {k: a.current["native_binding"][k] for k in BINDING_FIELDS}
        default = str((self.home / ".codex").resolve())  # the effective home of an env without a `CODEX_HOME`
        dotted, link = str(self.recorded_home / ".." / "home-a"), str(self.link("alias-home", self.recorded_home))
        rows = [  # (env `CODEX_HOME`, recorded home or None for the legacy four-key record, this engine keeps its own)
            (None, default, True),                                    # absent env home: the default the record names
            ("", default, True),                                      # empty env home: the same default
            (None, None, True),                                       # pre-0.5 four-key record: the process home, the same
            (str(self.current_home), str(self.current_home), True),    # the env value as stored, exactly
            (str(self.current_home), str(self.recorded_home), False),  # control: another recorded home -> a sibling
            (str(self.current_home / ".." / "home-b"), str(self.current_home), False),  # an alias of the env's own dir
            (str(self.recorded_home), dotted, False),                 # a recorded `..` spelling: never re-resolved
            (None, dotted, False),                                    # an absent env home against another record
            (link, link, True),                                       # the very same symlink spelling, as stored
            (link, str(self.recorded_home), False),                   # a symlink vs its canonical target: a sibling
        ]
        for spelled in (str(self.recorded_home) + os.sep, dotted + os.sep, link + os.sep):
            # a trailing separator is part of the recorded string: `str(Path(...))` would drop it
            rows += [(spelled, spelled, True),                        # the identical spelling, separator kept
                     (str(self.current_home), spelled, False)]        # another current home: a sibling keeps it too
        for env_home, recorded, own in rows:
            with self.subTest(env_home=env_home, recorded=recorded):
                binding = four if recorded is None else {**four, "codex_home": recorded}
                with self.process_env(None):  # `HOME` is this test's home: an absent env home resolves to `default`
                    engine, _calls = self.fixtures([], codex_home=env_home)
                    bound = engine.engine_for(binding)
                    self.assertIs(bound.engine_for(binding), bound)  # gate5 point 1: no delegation loop
                    if own:
                        self.assertIs(bound, engine)
                    else:
                        self.assertIsNot(bound, engine)
                        self.assertEqual(bound.native_environment()["CODEX_HOME"], recorded)  # literally as recorded

    def test_a3_a_seen_review_is_observation_context_of_the_run_not_of_the_engine(self):
        """R-2/A-3: "a review was seen" belongs to the native run id, not to an engine object. A journey on a recorded
        home different from the acting engine's (planner, plan_verifier, planner, each slice a fresh delegated
        sibling) prints the repair line on its second planner turn; a second run (a new run id) in the same process
        starts from the plain planner line.

        Interpretations recorded for the reviewers: the observation context (`engine.OBSERVED_RUNS`) is process-wide
        and in memory only; its entry is keyed by the native run id (R-2) and holds the state root the run was
        observed in, so the same id in another store is another run and starts unreviewed as well. A run id is unique
        inside its `<state_root>/runs` alone, and `tests/test_terminal_planner` and `tests/test_ux` both freeze a run
        called `fixture-native-run`: a key of the bare id would carry that other store's review into the A5 journey
        (discovery runs `test_terminal_planner` before `test_ux`), which A-1 forbids (this was reproduced: with a
        bare-id key, `test_a5_phases_print_while_the_planner_runs_with_one_rare_heartbeat` prints the repair line on
        its first planner turn). Every engine object of one run shares the acting engine's root (`sibling` keeps it),
        so the context is still shared by the current engine, its siblings and `recorded_engine`. These runs use their
        own run ids as well."""
        progress = []
        self.revision_version = 1
        self.phase_journey("fixture-home-run-1", [self.node_status("planner", "v2:1"), self.node_status("plan_verifier", "v2:2"),
                                                  self.node_status("planner", "v2:3")], progress.append)
        self.assertEqual(progress, [PHASES["planner"], PHASES["plan_verifier"], PHASES["repair"], "Plan checked."])
        again = []
        self.revision_version = 2
        self.phase_journey("fixture-home-run-2", [self.node_status("planner", "v2:1")], again.append)
        self.assertEqual(again, [PHASES["planner"], "Plan checked."])  # a new run id starts unreviewed

    def test_r2_two_runs_sharing_a_run_id_in_different_state_roots_keep_their_own_history(self):
        """R-2 (the code review's second finding): two runs with the same native run id in *different* state roots
        each keep their own "a review was seen" fact. The two engines below are the delegated siblings `proposal`
        observes through (`engine_for` keeps the acting engine's root); run A sees planner/verifier, run B (the same
        id, another root) sees planner/verifier in between, and run A's closing planner turn must still be the repair
        line: a context keeping one state root per run id would let B's review overwrite A's, and one keyed by the
        bare id would make B's first planner turn a repair.

        Interpretations recorded for the reviewers: the context key is the run itself -- its state root and its run
        id (`OBSERVED_RUNS`, engine.py) -- because a run id is unique only inside its own `<state_root>/runs`, while
        R-2's process-wide sharing holds for every engine object of one run (the acting engine, its `engine_for`
        siblings, and `recorded_engine`, which all carry the acting/recorded root). The interleave runs on
        `engine_for`'s delegated engines rather than on `proposal`, because R-3 (unchanged) refuses a full journey
        from another root: `prepare` compares the recorded `state_root` with the acting engine's and raises
        `engine.identity_changed`."""
        run_id = "fixture-home-run-ab"
        actor, _calls = self.fixtures([], codex_home=self.current_home)
        neighbour, _more = self.fixtures([], codex_home=self.current_home)
        neighbour.state_root = self.other_state  # a second run: the same native run id, another state root
        binding = {**actor.binary_identity(), "codex_home": str(self.recorded_home)}
        first, second = actor.engine_for(binding), neighbour.engine_for(binding)
        for bound in (first, second):
            self.assertIsNot(bound, actor)  # another recorded home, so the delegated engine is a sibling
            self.assertIs(bound.engine_for(binding), bound)
        self.assertNotEqual(first.state_root, second.state_root)

        def running(node):
            return {"phase": "running", "activeExecutions": [{"node": node, "execution": "e-" + node}]}

        seen = [engine.phase(running(node), run_id) for engine, node in
                ((first, "planner"), (first, "plan_verifier"), (second, "planner"), (second, "plan_verifier"),
                 (first, "planner"))]
        self.assertEqual(seen, [PHASES["planner"], PHASES["plan_verifier"], PHASES["planner"],
                                PHASES["plan_verifier"], PHASES["repair"]])


class DriverTests(runs_tests.RunsTest, Homes):
    """A-1st (attempt half), A-2 for every milestone path and A-4 for a submitted milestone record."""

    def setUp(self):
        super().setUp(); self.homes()
        self.control_native()

    def fake(self, responses, watch=None, codex_home=None):
        """`RunsTest`'s engine double (`started`/`approve_native` use it too), defaulting to the recorded home."""
        return self.fixtures(responses, watch=watch, codex_home=self.recorded_home if codex_home is None else codex_home)

    def driver(self, responses, codex_home=None, state=None, version=None):
        engine, calls = self.fake(responses, codex_home=codex_home)
        return NativeDriver(engine.executable, state or engine.state_root, call=engine.call, sleep=lambda _: None, environment=engine.environment, version=version), calls

    def runs(self, a, responses, codex_home=None, state=None):
        driver, calls = self.driver(responses, codex_home=codex_home, state=state)
        return MilestoneRuns(a, driver, worktrees=self.worktrees), calls

    def test_a1st_a_new_attempt_stores_the_driver_env_home_and_every_driver_path_uses_it(self):
        """A-1 store half + A-2: a native attempt records the driver env's home; every driver path runs there, not in the process env's."""
        r = self.started()
        self.assertEqual(set(r["binding"]), set(BINDING_FIELDS) | {"codex_home"})  # A-1st first: the base writes no home (A-B)
        self.assertEqual(r["binding"]["codex_home"], str(self.recorded_home.resolve()))
        self.assertTrue(toolchain.valid_binding(r["binding"]))
        # R-5: the fixture-setup probe is stubbed too; its env is the record home (an engine built without an env records none)
        self.assertEqual({(env or {}).get("CODEX_HOME") for env in self.setup_probes}, {str(self.recorded_home.resolve())})
        self.approve_fixture()
        with self.fixture_authority() as a:
            self.assertEqual(self.fixture_runs(a).start("M1", 1, ROLES)["binding"], {"fixture_id": "test"})
        running_2 = self.envelope(r, {"phase": "running", "activeExecutions": [{"node": "worker", "execution": "e1"}]}, "v2:5", run_id="m-run-2")
        responses = [(self.running(r),), self.live(r), (self.finished(r, reason="worker_failed"),), self.status(r, {"recoverable": True}), self.status(r, {"recoverable": True}),
                     {"runId": "m-run-2", "resumedFrom": "m-run"}, (running_2,), subprocess.CompletedProcess([], 0, "", "")]
        with self.process_env(self.current_home), self.authority() as a:  # the process env names another home
            controller, calls = self.runs(a, responses, codex_home=self.current_home)
            rr = controller.active()
            controller.observe(rr, seconds=1)
            controller.status(rr)
            rr = controller.observe(rr)
            successor = controller.resume(rr)  # the successor inherits the binding through LINEAGE
            controller.observe(successor, seconds=1)
            controller.stop(successor)
        self.assertEqual([c[0][1:] for c in calls], [["watch", "m-run"], ["status", "m-run"], ["watch", "m-run", "--after", "v2:5"], ["status", "m-run"],
                          ["status", "m-run"], ["resume", "m-run"], ["watch", "m-run-2"], ["force-stop", "m-run-2"]])
        self.home_of(calls)

    def test_a2_a_replayed_validate_and_submit_use_the_recorded_home(self):
        """A-2: a crashed attempt is reconciled — `--validate-only` and `--detach` replayed in the record's home."""
        self.approve_native()  # the plan is frozen in home A too
        with self.authority() as a:  # a crash before the receipt: the record is frozen, unsent
            controller, _calls = self.runs(a, [{"valid": True}], codex_home=self.recorded_home)
            with patch.object(NativeDriver, "submit", side_effect=runs_tests.Crash), self.assertRaises(runs_tests.Crash):
                controller.start("M1", 1, ROLES)
            r = self.stored(a)[0]
        self.assertEqual((r["status"], r["run_id"]), ("submission_unknown", None))
        with self.process_env(self.current_home), self.authority() as a:
            controller, replay = self.runs(a, [{"valid": True}, {"runId": "m-run"}], codex_home=self.current_home)
            adopted = controller.reconcile()
            self.assertEqual((adopted["status"], adopted["run_id"]), ("submitted", "m-run"))
        self.assertEqual([c[0][1] for c in replay], ["run", "run"])  # --validate-only, then --detach
        self.home_of(replay)

    def test_a2_logs_and_the_failure_cause_read_in_the_recorded_home(self):
        """A-2: `log_tail`/`log_records` follow the record's root *and* home; `failure_cause` the record's home."""
        r = self.started()
        other, recorded = self.other_state, {**r["binding"], "state_root": str(self.other_state)}
        seen = []
        with self.process_env(self.current_home):
            driver, calls = self.driver([subprocess.CompletedProcess([], 0, "", "")], codex_home=self.current_home)
            with patch.object(live, "tail", side_effect=lambda argv, env, cwd, **kw: seen.append(env)), \
                    patch.object(live, "records", side_effect=lambda argv, env, cwd, **kw: (seen.append(env), ([], True))[1]):
                driver.log_tail(recorded, "m-run", r["worktree"])
                driver.log_records(recorded, "m-run", r["worktree"])
            with self.authority() as a:
                driver.failure_cause(a)
        seen += [c[1]["env"] for c in calls]  # plus the failure cause's own bounded read
        self.assertEqual([env["CODEX_HOME"] for env in seen], [str(self.recorded_home.resolve())] * 3)
        self.assertEqual({env["ZEROSHOT_STATE_DIR"] for env in seen[:2]}, {str(other / "runs")})  # read_engine
        self.assertEqual(seen[2]["ZEROSHOT_STATE_DIR"], str(driver.state_root / "runs"))  # failure_cause keeps its own

    def test_a2_an_older_toolchain_binary_acts_in_the_recorded_home_with_its_path_prefix(self):
        """A-2: an older toolchain's record acts on its own executable, in the recorded home, with its PATH prefix."""
        with patch.object(toolchain, "DEFAULT", replace(toolchain.DEFAULT, zeroshot="10.10.1")), self.process_env(self.current_home):
            r = self.started()
            self.assertEqual(r["binding"]["version"], "zeroshot 10.10.1")
            bin_dir = Path(r["binding"]["executable"]).parent / "codex/node_modules/.bin"; bin_dir.mkdir(parents=True)
            engine, calls = self.fixtures([self.live(r)])
            driver = NativeDriver(self.binary(name="zeroshot-new"), self.root / "new-state", call=engine.call, sleep=lambda _: None, environment=self.env(self.current_home))
            with self.authority() as a:
                controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
                controller.status(controller.active())
        self.assertEqual([c[1]["env"]["CODEX_HOME"] for c in calls], [str(self.recorded_home.resolve())])
        self.assertEqual(calls[0][0][0], r["binding"]["executable"])  # the recorded executable, not the acting one
        self.assertTrue(calls[0][1]["env"]["PATH"].startswith(str(bin_dir) + os.pathsep))  # and its PATH prefix

    def test_a3_a_pre_05_record_loads_unchanged_and_acts_in_the_process_home(self):
        """A-3: a four-key record loads unchanged (digests kept) and acts in the process home: `CODEX_HOME` else `<HOME>/.codex`."""
        r = self.started()
        with self.authority() as a:
            path, revision = a.path, copy.deepcopy(a.current)
        state = json.loads(path.read_text())
        state["runs"][0]["binding"] = {k: state["runs"][0]["binding"][k] for k in BINDING_FIELDS}
        path.write_text(canonical(state) + "\n")
        for process_home, expected in ((self.recorded_home, self.recorded_home.resolve()), (None, (self.home / ".codex").resolve())):
            with self.process_env(process_home), self.authority() as a:
                self.assertEqual(a.state["runs"][0]["binding"], state["runs"][0]["binding"])
                self.assertEqual(a.state["revisions"][0], revision)  # digests unchanged by the legacy load
                driver, calls = self.driver([self.live(r)], codex_home=self.current_home)
                controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
                controller.status(controller.active())
                self.assertEqual([c[1]["env"]["CODEX_HOME"] for c in calls], [str(expected)], process_home)

    def test_a_run_record_whose_executable_cannot_be_resolved_is_refused_not_crashed(self):
        """R-2 (regression): a recorded executable spelling that cannot be resolved — a self-referencing symlink — is never
        taken for the acting engine's binary, so every driver entry point below gets the existing `toolchain.mismatch`
        refusal instead of the `RuntimeError` a bare `resolve()` raises (the base compares plain strings)."""
        r, loop = self.started(), self.link("zeroshot-loop", self.root / "zeroshot-loop")
        binding = {**{k: r["binding"][k] for k in BINDING_FIELDS}, "executable": str(loop), "codex_home": str(self.recorded_home)}
        run = {**r, "binding": binding}
        self.freeze_run(binding)  # the run record the driver operations read
        with self.process_env(self.current_home), self.authority() as a:
            controller, calls = self.runs(a, [], codex_home=self.current_home)
            driver = controller.driver()
            targets = (("check_binding", controller.check_binding, (run,)), ("validate", driver.validate, (run, [])),
                       ("submit", driver.submit, (run, [])), ("watch", driver.watch, (run, "v2:1")),
                       ("status", driver.status, (run, "m-run")), ("force-stop", driver.force_stop, (run,)),
                       ("resume", driver.resume, (run, "m-run")), ("log_tail", driver.log_tail, (binding, "m-run", run["worktree"])),
                       ("log_records", driver.log_records, (binding, "m-run", run["worktree"])))
            for label, method, args in targets:
                with self.subTest(label), self.assertRaisesRegex(Blocked, "toolchain"):
                    method(*args)
        self.assertEqual(calls, [])  # nothing ever reached a native invocation

    def test_a4_a_home_change_is_not_an_identity_change_for_a_milestone_record(self):
        """A-4: another recorded home (symlink or missing) is no refusal; a changed state root or sha256 still is."""
        r = self.started()
        missing = self.root / "not-there"
        binding = {k: r["binding"][k] for k in BINDING_FIELDS}  # a literal record of this test's own (A-B)
        for home, checks in ((str(self.link("link-home", self.recorded_home)), True), (str(missing), False)):
            binding["codex_home"] = home
            self.freeze_run(binding)
            with self.process_env(self.current_home), self.authority() as a:
                controller, calls = self.runs(a, [self.live(r)], codex_home=self.current_home)
                if checks:
                    controller.check_binding(controller.active())  # the home alone is no refusal
                controller.status(controller.active())
                self.assertEqual(self.stored(a)[0]["binding"], binding)  # the record stays as frozen
            self.assertEqual([c[1]["env"]["CODEX_HOME"] for c in calls], [home])
        self.assertFalse(missing.exists())  # a missing recorded home is passed through as it is
        with self.process_env(self.current_home), self.authority() as a:  # a changed state root still surfaces
            controller, _calls = self.runs(a, [], codex_home=self.current_home, state=self.other_state)
            with self.assertRaisesRegex(Blocked, "binary/state"):
                controller.check_binding(controller.active())
        with self.process_env(self.current_home), self.authority() as a:  # ... and so does a changed sha256
            controller, _calls = self.runs(a, [], codex_home=self.current_home)
            self.binary(extra=b"# tampered\n")  # after the driver exists: the same path, another content
            with self.assertRaisesRegex(Blocked, "binary/state"):
                controller.check_binding(controller.active())
            self.assertEqual(self.stored(a)[0]["binding"], binding)
