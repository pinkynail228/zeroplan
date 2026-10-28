"""G2-start records (S1a slice 2a): the durable task-gate record, its strict store validation, the dispatch
protocol and the recovery/lifecycle API.

Deterministic fixtures and real temporary Git repositories; no provider, no network. The native crash protocol is
injected through the scripted `NativeEngine` harness (never FixtureScenarioTests alone, which cannot cover it); the
fixture engine produces every semantic outcome the record contract names.

Interpretations (nothing in the parent or the slice fixes them; kept here for the reviewers):
- The gate graph's node bindings come from the resolved configuration: the `worker` presents the frozen briefs
  (`proposer`) and the profile's `critic` reviews them. The parent fixes the two read-only nodes and their scopes,
  not which profile role fills which node; `task_gate_roles` in delivery.py is the one place that maps them.
- The record's `terminal` is the native `terminalResult` (its `output` included) and `output_digest` the digest of
  that output, so `validate_gates` checks the two against each other. `concluded` and `output_invalid` carry a
  succeeded terminal plus the digest; `native_failed` a failed terminal and no digest.
- `rounds_used`, `discussion` and `critic_verdict` are filled by `concluded` alone; every other status has None.
- A live rules change between a `preparing` save and its recovery re-derives the frozen documents and refuses with
  `engine.intent_changed` if they moved; a dispatched record is observed under the frozen files on disk.
- `run_task_gate` reads the bound profile with `status(write=False)` only, so a refusal never touches the sidecar
  `process-state.json` (asserted for every control).
- Admission reads the authoritative `Authority.profile`, never the `Planning` service's copy of it, and the
  profile's own refusal (never/missing/malformed) is decided before the plan and milestone conditions.
- An existing nonterminal record is selected before any admission, so a live configuration change never blocks a
  recovery or changes a record.
- The one resolved configuration of a dispatch supplies both the record's `resolved_config_digest` and its frozen
  documents: a rule file rewritten after the resolution refuses (`process.changed`), and a rebuild of a
  never-dispatched record reads its own rule files and refuses (`engine.intent_changed`) when they no longer resolve
  to the record's digest.
- A persisted concluded record is accepted only while its verdict, discussion and round count equal what its own
  terminal output parses to under its own `rounds_limit`.
- The store validation also reproduces each record's artifact from the record's own revision, milestone and context
  (`task_gate.contextual_digest`), so a proposal candidate that is not a well-formed task list of that milestone is
  malformed even though the record's keys, enums and references are all well formed.
- A recovery whose preparation already finished on disk reuses it (`gate_prepared`), so a rule changed after the
  preparation does not refuse it (A-4l); a `preparing` record with nothing on disk still rebuilds its documents from
  its own frozen configuration and refuses (`engine.intent_changed`) when the rules no longer resolve to it.
- The crash-boundary tests (A-5) close and reopen the store, so a status only the crashed process kept in memory,
  or a save deferred past the dispatch, is not mistaken for durability.
- The observed envelope's `source.revision` must be the record's frozen HEAD (parent R-2 terminal identity), so a
  `finished` projection of another revision never concludes the record.
- Terminal identity's first field, the run id, is checked by the shared structural envelope validation
  (`validate_projection`, the plan path's own), so a foreign run id refuses `store.invalid`; only the gate's frozen
  intent fields (`source.revision`, `title`, `size`) refuse `engine.intent_changed`. The parent's "existing
  structural envelope validation still applies" is read as keeping the run-id check where it already is.
- The store's refusal domain is generated from the record schema itself (every `RECORD_KEYS` key missing, every key
  with a wrong JSON type, one unknown key): bounded by the schema, not by an arbitrary byte corpus.
"""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
from unittest.mock import Mock, patch

from terminal_planner import authority as authority_module
from terminal_planner import cli, milestone, process, runs, task_gate, toolchain
from terminal_planner.authority import Authority as RealAuthority, Blocked, PersistenceError, canonical, digest, git
from terminal_planner.delivery import Delivery
from terminal_planner.engine import FixtureEngine, SliceEnded, fixture_discussion
from terminal_planner.process import Profile
from terminal_planner.runs import MilestoneRuns
import test_process as tpr
import test_terminal_planner as tp
from test_plan_gate import round_
from test_task_gate import discussion_of, task_output
from test_terminal_planner import ROLES, ScriptedTerminal

REQUIRED = {"gates": {"task": "required"}}
OFF = {"preset": "zplan.default/1"}


def rounds(value):
    return {"gates": {"task": "required"}, "limits": {"task_rounds": value}}


def surrogate_output(left="\ud800"):
    """A two-round task-gate output whose first, rejected round carries the unpaired surrogate `left` and whose last
    round matches the accepted final fields. `json.dumps(..., ensure_ascii=True)` keeps the outer `discussion` string
    valid UTF-8 while the inner JSON decodes to the lone surrogate (R-2/R-5)."""
    rounds_ = [round_(1, findings="открыто: %s" % left),
               round_(2, verdict="accepted", findings="ok", response="ok")]
    return {"schemaVersion": "1", "taskVerdict": "accepted", "taskFindings": "ok", "taskResponse": "ok",
            "discussion": json.dumps({"version": 1, "rounds": rounds_}, ensure_ascii=True)}


def nested(depth):
    """`"x"` wrapped in `depth` lists: a refused terminal output of an exact nesting, for the store's serializer."""
    value = "x"
    for _ in range(depth):
        value = [value]
    return value


class FakePlanning:
    """The service-side stand-in `run_task_gate` needs: the bound profile and the engine factory (no milestone runs)."""

    def __init__(self, profile, factory):
        self.profile, self.engine_factory, self.terminal = profile, factory, None


class GateBase(tpr.ProfileTest):
    """A fixture session: an accepted profile and one approved M1 plan revision (plan revision 1)."""

    def prepare(self, document=REQUIRED):
        self.accept_file(document)
        self.approved_plan()

    @contextlib.contextmanager
    def session(self, engine_obj):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            yield cli.App(ScriptedTerminal("", io.StringIO()), authority, lambda *_: engine_obj, None,
                          authority.directory / "worktrees", profile=Profile.of(authority))

    def in_session(self, engine_obj, call):
        with self.session(engine_obj) as app:
            return call(app)

    def gate(self, engine_obj, document=REQUIRED, milestone="M1", context=None):
        """Accept `document`, approve M1 and run one gate; returns the record it stored."""
        self.prepare(document)
        return self.in_session(engine_obj, lambda app: copy.deepcopy(
            app.delivery.run_task_gate(milestone, context=context)))

    def park(self, status="observing"):
        """A record parked in a nonterminal status, exactly as an interrupted dispatch leaves it (R-4)."""
        self.prepare()

        def call(app):
            record, _ = app.delivery.task_gate_new("M1", None, app.delivery.plan(),
                                                   app.planning.profile.status(write=False), FixtureEngine("accept"))
            if status == "submission_unknown":
                record.update(status=status)
            elif status != "preparing":
                record.update(run_id="fixture-parked", receipt={"runId": "fixture-parked"}, status=status)
            app.authority.save()
            return copy.deepcopy(record)
        return self.in_session(FixtureEngine("accept"), call)

    def sidecar(self, directory):
        """The sidecar bytes under `directory`, without taking the project lock (the session holds it)."""
        path = directory / process.STATE_FILE
        return path.read_bytes() if path.exists() else None

    def head(self):
        return git(self.project, "rev-parse", "HEAD").decode().strip()

    def commit(self, text="moved\n", name="source.txt"):
        (self.project / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-qm", "move")

    def assert_untouched(self, app, family, call):
        """`call(app)` refuses with `family` and leaves the store, the sidecar and the absence of `gates` intact."""
        def bytes_of():
            return app.authority.path.read_bytes() if app.authority.path.exists() else None
        before, sidecar = bytes_of(), self.sidecar(app.authority.directory)
        with self.assertRaises(Blocked) as raised:
            call(app)
        self.assertEqual(raised.exception.family, family)
        self.assertEqual(bytes_of(), before)
        self.assertEqual(self.sidecar(app.authority.directory), sidecar)
        self.assertNotIn("gates", app.authority.state or {})

    def stored_state(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return authority.path, copy.deepcopy(authority.state)

    def load_gates(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return copy.deepcopy(authority.state["gates"])

    def assert_refused(self, family="store.invalid"):
        with self.assertRaises(Blocked) as raised:
            with RealAuthority(self.state, self.project, fixture_id="test"):
                pass
        self.assertEqual(raised.exception.family, family)

    def state_dir_reset(self):
        import shutil
        shutil.rmtree(self.state, ignore_errors=True)
        self.state.mkdir(parents=True)

    def variant(self, build):
        """A fresh state directory plus one gate record built by `build` (each build starts a new plan)."""
        self.state_dir_reset()
        return build()

    def two_records(self):
        """A base state whose store holds two concluded records (a rerun appended the second)."""
        self.gate(FixtureEngine("accept"))
        self.in_session(FixtureEngine("accept"), lambda app: app.delivery.rerun_task_gate("M1"))
        path, base = self.stored_state()
        return path, base


# A-4r ------------------------------------------------------------------------------------------------------------

class RecordTests(GateBase):
    """The exact record `Delivery.run_task_gate` stores and the refusals that precede it (A-4r)."""

    def test_a_fixture_gate_stores_the_exact_frozen_values(self):
        self.prepare()
        def call(app):
            record = app.delivery.run_task_gate("M1")
            manifest = app.delivery.runs.gate_manifest("M1", 1, None)
            self.assertEqual(set(record), set(task_gate.RECORD_KEYS))
            self.assertEqual(record["gate"], "task")
            self.assertTrue(task_gate.ID.fullmatch(record["id"]))
            self.assertTrue(task_gate.KEY.fullmatch(record["submission_key"]))
            self.assertEqual((record["plan_revision"], record["milestone"], record["context"]), (1, "M1", None))
            self.assertEqual(record["binding"], {"fixture_id": "test"})
            self.assertEqual(record["override"], None)
            self.assertEqual(record["approval"], app.authority.current["approval"])
            self.assertEqual(record["identity"]["head"], self.head())
            self.assertEqual(record["identity"]["artifact_digest"], task_gate.artifact_digest(manifest))
            self.assertEqual(record["identity"]["resolved_config_digest"],
                             app.planning.profile.status(write=False).digest)
            self.assertEqual(record["rounds_limit"], record["config"]["limits"]["task_rounds"])
            self.assertEqual(record["documents"],
                             {name: digest(value) for name, value in
                              app.delivery.task_gate_documents(record).items()})
            self.assertEqual((record["status"], record["critic_verdict"], record["rounds_used"], record["discussion"]),
                             ("concluded", "accepted", 1, fixture_discussion("accept", 2)))
            self.assertEqual(record["terminal"]["status"], "succeeded")
            self.assertEqual(record["output_digest"], digest(record["terminal"]["output"]))
            return copy.deepcopy(record)
        stored = self.in_session(FixtureEngine("accept"), call)
        self.assertEqual(self.load_gates(), [stored])

    def test_every_scenario_records_its_own_outcome(self):
        for scenario, expected in (("accept", ("concluded", "accepted")), ("repair", ("concluded", "accepted")),
                                   ("exhausted", ("concluded", "rejected"))):
            with self.subTest(scenario=scenario):
                record = self.variant(lambda scenario=scenario: self.gate(FixtureEngine(scenario), rounds(2)))
                self.assertEqual((record["status"], record["critic_verdict"]), expected)
                self.assertEqual(record["discussion"], fixture_discussion(scenario, 2))
                self.assertEqual(record["terminal"]["output"]["taskVerdict"], expected[1])

    def test_a_native_failure_is_not_a_rejection(self):
        for failure in ("critic_failed", "proposer_failed", "session_lost"):
            with self.subTest(failure=failure):
                record = self.variant(lambda failure=failure: self.gate(FixtureEngine(failure=failure)))
                self.assertEqual(record["status"], "native_failed")
                self.assertEqual(record["terminal"], {"status": "failed", "reason": failure})
                for key in ("critic_verdict", "discussion", "rounds_used", "output_digest"):
                    self.assertIsNone(record[key], key)
                self.assertEqual(record["diagnostic"], failure)

    def test_a_native_shaped_binding_in_a_fixture_store_is_refused(self):
        self.gate(FixtureEngine("accept"))

        def mutate(state):
            state["gates"][0]["binding"] = {"executable": "/bin/true", "state_root": "/tmp/state", "sha256": "a" * 64,
                                            "version": "zeroshot 10.12.0", "codex_home": "/home/user/.codex"}
        path, base = self.stored_state()
        mutate(base)
        path.write_text(canonical(base) + "\n", encoding="utf-8")
        self.assert_refused()

    def test_off_and_unapproved_or_unknown_milestone_refuse_without_side_effects(self):
        for label, document, name in (("preset /1", OFF, "M1"),
                                      ("gates.task off", {"gates": {"task": "off"}}, "M1"),
                                      ("required but unapproved", None, "M1"),
                                      ("unknown milestone", REQUIRED, "M9")):
            with self.subTest(case=label):
                self.state_dir_reset()
                if label == "required but unapproved":
                    self.accept_file(REQUIRED)  # no approved plan
                else:
                    self.prepare(document)
                with self.session(FixtureEngine("accept")) as app:
                    self.assert_untouched(app, "action.refused", lambda a: a.delivery.run_task_gate(name))

    def test_a_deferred_profile_adopting_a_late_file_writes_nothing(self):
        """R-4/mutation h: admission reads the profile with `status(write=False)`; adopting the late file would
        write the sidecar `process-state.json` (a `write=True` mutation changes its bytes here)."""
        self.defer()  # state "later", no project file yet
        self.approved_plan()
        self.write(OFF)  # the file appears after "later"
        with self.session(FixtureEngine("accept")) as app:
            self.assert_untouched(app, "action.refused", lambda a: a.delivery.run_task_gate("M1"))

    def test_never_missing_or_malformed_profiles_refuse_with_their_family(self):
        self.approved_plan()
        with self.session(FixtureEngine("accept")) as app:  # never accepted
            self.assert_untouched(app, "process.pending", lambda a: a.delivery.run_task_gate("M1"))
        self.state_dir_reset()
        self.prepare()
        self.remove_accepted_file()
        with self.session(FixtureEngine("accept")) as app:
            self.assert_untouched(app, "process.missing", lambda a: a.delivery.run_task_gate("M1"))
        self.state_dir_reset()
        self.approved_plan()
        self.write("{broken")
        with self.session(FixtureEngine("accept")) as app:
            self.assert_untouched(app, "process.invalid", lambda a: a.delivery.run_task_gate("M1"))

    def test_the_bound_profile_state_precedes_the_plan_conditions(self):
        """R-4 class: the bound profile's own refusal family is decided before the plan and milestone conditions, so
        an unapproved (or absent) revision never masks a pending/missing/malformed profile. Oracles: the family and
        the untouched store/sidecar asserted by `assert_untouched`; the control is the same project with an approved
        revision (`action.refused`, the earlier test). Domain: the three profile states with no approved revision."""
        self.write(REQUIRED)  # a proposal the owner never accepted, and no plan revision at all
        with self.session(FixtureEngine("accept")) as app:
            self.assert_untouched(app, "process.pending", lambda a: a.delivery.run_task_gate("M1"))
        self.state_dir_reset()
        self.accept_file(REQUIRED)
        self.remove_accepted_file()  # the accepted file is gone and the record keeps no snapshot
        with self.session(FixtureEngine("accept")) as app:
            self.assert_untouched(app, "process.missing", lambda a: a.delivery.run_task_gate("M1"))
        self.state_dir_reset()
        self.write("{broken")
        with self.session(FixtureEngine("accept")) as app:
            self.assert_untouched(app, "process.invalid", lambda a: a.delivery.run_task_gate("M1"))


# A-4l ------------------------------------------------------------------------------------------------------------

class LifecycleTests(GateBase):
    """Recovery, observation and the explicit rerun (A-4l)."""

    def test_a_nonterminal_record_is_observed_keeping_its_id(self):
        for status in ("preparing", "observing", "detached", "observation_blocked"):
            with self.subTest(status=status):
                parked = self.variant(lambda status=status: self.park(status))

                def call(app, parked=parked):
                    record = app.delivery.run_task_gate("M1")
                    self.assertEqual(record["id"], parked["id"])
                    self.assertEqual(len(app.authority.state["gates"]), 1)
                    return copy.deepcopy(record)
                record = self.in_session(FixtureEngine("accept"), call)
                self.assertEqual(record["status"], "concluded")
                dispatched = record["run_id"] != "fixture-parked"
                self.assertEqual(dispatched, status == "preparing")

    def test_an_unconfirmed_submission_refuses_and_never_dispatches_again(self):
        parked = self.park("submission_unknown")

        def call(app):
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                app.delivery.run_task_gate("M1")
            self.assertEqual(raised.exception.family, "submission.unknown")
            self.assertEqual(app.authority.path.read_bytes(), before)
            self.assertEqual(app.authority.state["gates"][-1]["id"], parked["id"])
            self.assertEqual(app.authority.state["gates"][-1]["status"], "submission_unknown")
        self.in_session(FixtureEngine("accept"), call)

    def test_a_live_config_or_head_change_never_dispatches_again(self):
        for label, change in (("config", lambda: self.write(rounds(5))), ("head", self.commit)):
            with self.subTest(change=label):
                parked = self.variant(lambda: self.park("observing"))
                change()

                def call(app, parked=parked):
                    record = app.delivery.run_task_gate("M1")
                    self.assertEqual((record["id"], record["run_id"], record["rounds_limit"]),
                                     (parked["id"], "fixture-parked", 2))
                    self.assertEqual(len(app.authority.state["gates"]), 1)
                self.in_session(FixtureEngine("accept"), call)

    def test_recovery_is_selected_before_any_live_admission(self):
        """A-4l/R-4 class: an existing nonterminal record is recovered or observed under its own frozen
        configuration, so a live profile that would refuse a new gate (`gates.task: off`) neither blocks the
        recovery nor changes the record; `submission_unknown` still refuses with its own family, and with no record
        the same live configuration refuses with `action.refused`. Oracle: the record's id and count after the call;
        control: the empty-store case in the same loop."""
        for status in ("preparing", "observing", "detached", "observation_blocked", "submission_unknown"):
            with self.subTest(status=status):
                parked = self.variant(lambda status=status: self.park(status))
                self.write(OFF)

                def call(app, parked=parked, status=status):
                    if status == "submission_unknown":
                        with self.assertRaises(Blocked) as raised:
                            app.delivery.run_task_gate("M1")
                        self.assertEqual(raised.exception.family, "submission.unknown")
                        self.assertEqual(app.authority.state["gates"][-1]["status"], "submission_unknown")
                    else:
                        record = app.delivery.run_task_gate("M1")
                        self.assertEqual((record["id"], record["rounds_limit"]), (parked["id"], 2))
                        self.assertEqual(len(app.authority.state["gates"]), 1)
                self.in_session(FixtureEngine("accept"), call)
        self.state_dir_reset()
        self.prepare(OFF)
        with self.session(FixtureEngine("accept")) as app:
            self.assert_untouched(app, "action.refused", lambda a: a.delivery.run_task_gate("M1"))

    def test_rerun_refuses_a_nonterminal_record_and_appends_after_a_terminal_one(self):
        parked = self.park("observing")

        def refuse(app, parked=parked):
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                app.delivery.rerun_task_gate("M1")
            self.assertEqual(raised.exception.family, "action.refused")
            self.assertEqual(app.authority.path.read_bytes(), before)
            app.delivery.run_task_gate("M1")  # observes the parked record to a terminal state
            self.assertEqual(app.authority.state["gates"][0]["status"], "concluded")
            return copy.deepcopy(app.authority.state["gates"][0])
        first = self.in_session(FixtureEngine("accept"), refuse)

        def append(app, first=first):
            second = app.delivery.rerun_task_gate("M1")
            self.assertEqual(len(app.authority.state["gates"]), 2)
            self.assertNotEqual(second["id"], first["id"])
            return copy.deepcopy(app.authority.state["gates"])
        gates = self.in_session(FixtureEngine("accept"), append)
        self.assertEqual(gates[0], first)
        self.assertEqual((gates[0]["status"], gates[1]["status"]), ("concluded", "concluded"))


# A-4s / A-4o -----------------------------------------------------------------------------------------------------

class StoreTests(GateBase):
    """The strict store and the override shape (A-4s, A-4o)."""

    def test_a_valid_store_with_two_records_loads(self):
        path, base = self.two_records()
        self.assertEqual(len(base["gates"]), 2)
        self.assertEqual(self.load_gates(), base["gates"])

    def test_strict_store_refuses_each_malformation(self):
        path, base = self.two_records()
        mutations = {
            "unknown key": lambda state: state["gates"][0].update(extra=1),
            "missing key": lambda state: state["gates"][0].pop("diagnostic"),
            "bad status": lambda state: state["gates"][0].update(status="nonsense"),
            "duplicate id": lambda state: state["gates"][1].update(id=state["gates"][0]["id"]),
            "verdict on a nonterminal record": lambda state: state["gates"][0].update(
                status="observing", critic_verdict="accepted"),
            "empty list": lambda state: state.update(gates=[]),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                state = copy.deepcopy(base)
                mutate(state)
                path.write_text(canonical(state) + "\n", encoding="utf-8")
                self.assert_refused()

    def override(self, record, **over):
        value = {"reason": "The briefs stand as they are; owner overrides the verdict.", "verdict": "rejected",
                 "evidence_digest": digest(task_gate.evidence(record))}
        value.update(over)
        return value

    def with_override(self, build, **over):
        """`(path, record)` of one fresh plan written back with a single override-carrying record, built from that
        record itself, so the override is the store's only malformation and the revision reference still holds."""
        self.state_dir_reset()
        record = build()
        path, base = self.stored_state()
        record = copy.deepcopy(record)
        record["override"] = self.override(record, **over)
        state = copy.deepcopy(base)
        state["gates"] = [record]
        path.write_text(canonical(state) + "\n", encoding="utf-8")
        return path, record

    def test_a_valid_override_loads_and_every_other_shape_is_refused(self):
        path, rejected = self.with_override(lambda: self.gate(FixtureEngine("exhausted"), rounds(2)))
        self.assertEqual(rejected["critic_verdict"], "rejected")
        self.assertEqual(self.load_gates(), [rejected])
        cases = {"accepted record": lambda: self.gate(FixtureEngine("accept")),
                 "nonterminal record": lambda: self.park("observing"),
                 "native_failed record": lambda: self.gate(FixtureEngine(failure="critic_failed")),
                 "extra key": lambda: self.gate(FixtureEngine("exhausted"), rounds(2))}
        for label, build in cases.items():
            with self.subTest(case=label):
                self.with_override(build, **({"extra": 1} if label == "extra key" else {}))
                self.assert_refused()


# A-6b ------------------------------------------------------------------------------------------------------------

class EvidenceTests(GateBase):
    """s1a1a's malformed, inconsistent and over-cap outputs through the fixture dispatch path (A-6b)."""

    def test_invalid_outputs_conclude_as_output_invalid_without_a_verdict(self):
        cases = {"malformed discussion": task_output({"version": 1, "rounds": [round_(1)]}, discussion="{broken"),
                 "inconsistent last round": task_output(discussion_of(2), taskFindings="a finding never given"),
                 "over the byte cap": task_output(discussion_of(9, 32769))}
        for label, output in cases.items():
            with self.subTest(case=label):
                record = self.variant(lambda output=output: self.gate(
                    FixtureEngine("accept", terminal_output=output), rounds(9)))
                self.assertEqual(record["status"], "output_invalid")
                self.assertEqual(record["terminal"]["output"], output)
                self.assertEqual(record["output_digest"], digest(output))
                self.assertIn("task check", record["diagnostic"])
                for key in ("critic_verdict", "discussion", "rounds_used"):
                    self.assertIsNone(record[key], key)

    def test_a_well_formed_output_concludes(self):
        record = self.gate(FixtureEngine("accept"))
        self.assertEqual((record["status"], record["critic_verdict"]), ("concluded", "accepted"))
        self.assertEqual(record["output_digest"], digest(record["terminal"]["output"]))

    def test_a_decoded_lone_surrogate_is_output_invalid_without_evidence(self):
        """R-2/R-5 class: a discussion JSON that decodes to an unpaired surrogate. Checked domain: both surrogate
        ranges (`chr(0xD800)`, `chr(0xDC00)`) JSON-escaped inside the first, rejected round's findings, delivered
        through the production fixture dispatch path, with a well-formed Unicode round as control. Oracle: the
        record's own persisted status and cleared evidence fields; the fixture writes no evidence it cannot hold.
        Interpretation: the outer output stays valid UTF-8 (the escape), so only the parser's own persistence check
        can refuse it -- `read_review` refuses the decoded discussion and the record becomes `output_invalid`."""
        for left in (chr(0xD800), chr(0xDC00)):
            with self.subTest(surrogate=hex(ord(left))):
                output = surrogate_output(left)
                # the outer string is plain ASCII, never a raw surrogate
                self.assertTrue(output["discussion"].isascii())
                record = self.variant(lambda output=output: self.gate(
                    FixtureEngine("accept", terminal_output=output), rounds(2)))
                self.assertEqual(record["status"], "output_invalid")
                self.assertEqual(record["terminal"]["output"], output)
                self.assertEqual(record["output_digest"], digest(output))
                self.assertIn("saved", record["diagnostic"])
                for key in ("critic_verdict", "discussion", "rounds_used"):
                    self.assertIsNone(record[key], key)
                self.assertEqual(self.load_gates(), [record])
        control = surrogate_output("✅ Кириллица")
        self.assertEqual(self.variant(lambda: self.gate(
            FixtureEngine("accept", terminal_output=control), rounds(2)))["status"], "concluded")

    def test_an_output_the_store_cannot_hold_leaves_no_terminal(self):
        """R-2/R-5 class: an output whose own text holds a raw unpaired surrogate, so the *envelope* cannot be
        persisted either. Checked domain: `terminal.output.taskFindings` set to `chr(0xD800)`; oracle: the record's
        persisted status, its absent terminal and digest, and the fact that the store still reloads it (the refusal
        is stored, never the output). Interpretation: an output the store cannot hold at all -- not merely a decoded
        discussion -- leaves no `terminal`, so the record stays loadable rather than crashing the next writer."""
        output = {"schemaVersion": "1", "taskVerdict": "accepted", "taskFindings": chr(0xD800), "taskResponse": "ok",
                  "discussion": canonical({"version": 1, "rounds": [round_(1, verdict="accepted")]})}
        record = self.variant(lambda: self.gate(FixtureEngine("accept", terminal_output=output)))
        self.assertEqual(record["status"], "output_invalid")
        self.assertIsNone(record["terminal"])
        self.assertIsNone(record["output_digest"])
        self.assertIsNone(record["critic_verdict"])
        self.assertIn("saved", record["diagnostic"])
        self.assertEqual(self.load_gates(), [record])


# R-2 manifest ----------------------------------------------------------------------------------------------------

class ManifestTests(GateBase):
    """`MilestoneRuns.gate_manifest` is the pure artifact projection of a start (R-2, mutation f)."""

    def test_the_manifest_is_pure_and_carries_the_owner_context(self):
        self.prepare()
        with self.session(FixtureEngine("accept")) as app:
            before = app.authority.path.read_bytes()
            plain = app.delivery.runs.gate_manifest("M1", 1, None)
            self.assertEqual(app.authority.path.read_bytes(), before)  # pure: nothing persisted, no git read
            self.assertNotIn("gates", app.authority.state or {})
            baseline, _ = milestone.build_manifest(app.authority.current["proposal"], "M1", 1)
            self.assertEqual(plain, runs.bootstrap_manifest(baseline, None))
            context = {"kind": "answer", "source": 1, "text": "Owner answer.", "candidate": None}
            noted = app.delivery.runs.gate_manifest("M1", 1, context)
            self.assertEqual(noted["tasks"][0]["notes"], "Owner answer (attempt 1): Owner answer.")
            self.assertNotEqual(task_gate.artifact_digest(noted), task_gate.artifact_digest(plain))
            self.assertEqual(app.delivery.runs.gate_manifest("M1", 1, None), plain)


# Mutation g ------------------------------------------------------------------------------------------------------

class CallerStatusTests(GateBase):
    """R-4: the gate's admission reads the bound profile itself; no caller value can enable or disable it."""

    def test_the_bound_profile_decides_and_no_caller_value_does(self):
        import inspect
        self.assertNotIn("status", inspect.signature(Delivery.run_task_gate).parameters)
        self.prepare(OFF)
        with self.session(FixtureEngine("accept")) as app:
            with self.assertRaises(Blocked) as raised:
                app.delivery.run_task_gate("M1")
            self.assertEqual(raised.exception.family, "action.refused")
            self.assertIn(process.PROFILE_FILE, str(raised.exception))
            self.assertNotIn("gates", app.authority.state or {})
        self.state_dir_reset()
        self.prepare(REQUIRED)  # the same project and store: the file now requires the gate
        with self.session(FixtureEngine("accept")) as app:
            self.assertEqual(app.delivery.run_task_gate("M1")["status"], "concluded")


# A-5 / A-3h -----------------------------------------------------------------------------------------------------

class NativeGateBase(tpr.ProfileTest):
    """The scripted native binary of `test_terminal_planner` over a production store with an accepted profile
    (A-5 protocol, A-3h binding): no pinned binary, no provider, no network."""

    native = tp.NativeTests.native
    engine = tp.NativeTests.engine
    projection = tp.NativeTests.projection
    terminal = tp.NativeTests.terminal
    authority = tp.NativeTests.authority

    def accepted_profile(self, document=REQUIRED):
        self.write(document)
        with self.authority() as authority:
            Profile.of(authority).accept()

    def approved_native_plan(self):
        """A production store, a required-task profile and an approved native M1 revision."""
        self.accepted_profile()
        plan_engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal()])
        with self.authority() as authority:
            authority.profile = Profile.of(authority)
            authority.begin("Requested feature", ROLES, "native")
            plan_engine.proposal(authority, lambda _: None)
            authority.approve(1)
        return plan_engine, calls

    @contextlib.contextmanager
    def bound(self):
        """A native session whose `Authority.profile` is bound (R-4): admission reads that attribute, never the
        service's own profile, so a test that wants an unbound session opens `self.authority()` directly."""
        with self.authority() as authority:
            authority.profile = Profile.of(authority)
            yield authority

    def dispatching(self, responses, home=None):
        """(engine, calls) of the scripted gate engine, in `home` when given (the dispatching env home)."""
        engine, calls = self.engine(responses)
        if home is not None:
            engine.environment = {**os.environ, "CODEX_HOME": home}
        return engine, calls

    def delivery(self, authority, engine):
        runs = MilestoneRuns(authority, None, authority.directory / "worktrees")
        return Delivery(authority, runs, FakePlanning(Profile.of(authority), lambda *_: engine))

    def gate_output(self, rounds=None, verdict="accepted", findings="No open findings.", response="Briefs unchanged."):
        discussion = {"version": 1, "rounds": rounds or [
            {"round": 1, "verdict": verdict, "findings": findings, "response": response}]}
        return {"schemaVersion": "1", "taskVerdict": verdict, "taskFindings": findings, "taskResponse": response,
                "discussion": canonical(discussion)}

    def gate_terminal(self, output=None):
        return {"runId": "fixture-native-run", "subscriptionId": "fixture-subscription", "title": "Task gate M1",
                "source": {"repository": "example/fixture", "branch": "main",
                           "revision": self.git("rev-parse", "HEAD").decode().strip()},
                "size": "medium", "cursor": "v2:10",
                "status": {"phase": "finished", "terminalResult": {"status": "succeeded",
                                                                   "output": output or self.gate_output()}}}


class ProtocolTests(NativeGateBase):
    """R-4/A-5: a crash after `submission_unknown` and after the detach receipt; `--detach` is called once.

    Class: the state that actually reached the disk at each crash boundary. The store is closed and reopened at the
    boundary, so a status only the crashed process kept in memory, or a save deferred past the dispatch, is not
    mistaken for durability (mutation a). Checked domain: a crash inside `--detach` (uncertain submission) and one
    during the following watch (after the receipt). Oracles: the status, run id and receipt the reopened store
    itself carries, and the scripted engine's own record of the calls; control: the receipted record reaches
    `concluded` with exactly one `--detach`."""

    def dispatched(self, calls):
        return [argv for argv, _ in calls if argv[1] == "run" and "--detach" in argv]

    def test_a_crash_after_the_receipt_observes_the_same_run_id_without_resubmitting(self):
        self.approved_native_plan()
        crash = [{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()]
        with self.bound() as authority:
            engine, calls = self.dispatching(crash)
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
        with self.bound() as authority:  # a restart: only what reached the disk is known
            parked = copy.deepcopy(authority.state["gates"][0])
            self.assertEqual((parked["status"], parked["run_id"], parked["receipt"]),
                             ("detached", "fixture-native-run", {"runId": "fixture-native-run"}))
            restart, calls2 = self.dispatching([self.gate_terminal()])
            record = self.delivery(authority, restart).run_task_gate("M1")
            self.assertEqual((record["id"], record["run_id"]), (parked["id"], "fixture-native-run"))
            self.assertEqual(record["status"], "concluded")
            self.assertEqual(len(authority.state["gates"]), 1)
            self.assertEqual([argv[1] for argv, _ in calls2], ["watch"])
            self.assertEqual(len(self.dispatched(calls + calls2)), 1)

    def test_an_unconfirmed_submission_refuses_and_never_dispatches_again(self):
        self.approved_native_plan()
        crash = [{"valid": True}, KeyboardInterrupt()]
        with self.bound() as authority:
            engine, calls = self.dispatching(crash)
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
            self.assertEqual(len(self.dispatched(calls)), 1)
        with self.bound() as authority:  # the uncertainty was committed before the dispatch, so it survived
            parked = copy.deepcopy(authority.state["gates"][0])
            self.assertEqual((parked["status"], parked["run_id"], parked["receipt"]),
                             ("submission_unknown", None, None))
            restart, calls2 = self.dispatching([self.gate_terminal()])
            with self.assertRaises(Blocked) as raised:
                self.delivery(authority, restart).run_task_gate("M1")
            self.assertEqual(raised.exception.family, "submission.unknown")
            self.assertEqual(calls2, [])
            self.assertEqual(authority.state["gates"][0]["status"], "submission_unknown")

    def test_a_native_success_without_a_task_verdict_sets_nothing(self):
        """R-4: only the parsed `taskVerdict` concludes a gate; a native `succeeded` alone does not (mutation b)."""
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"},
                                          self.gate_terminal(output={"schemaVersion": "1", "taskVerdict": "nonsense",
                                                                     "taskFindings": "f", "taskResponse": "r",
                                                                     "discussion": canonical({"version": 1, "rounds": [
                                                                         {"round": 1, "verdict": "accepted",
                                                                          "findings": "f", "response": "r"}]})})])
            record = self.delivery(authority, engine).run_task_gate("M1")
            self.assertEqual(record["status"], "output_invalid")
            self.assertIsNone(record["critic_verdict"])


class BindingTests(NativeGateBase):
    """R-3/A-3h: the binding is `binary_identity()` plus the dispatching `codex_home`, and a recorded home is
    the one a later observation runs in (`engine_for`)."""

    def test_the_binding_carries_the_dispatching_home_and_observes_in_it(self):
        home, other = str(self.root / "codex-home-a"), str(self.root / "codex-home-b")
        for path in (home, other):
            os.makedirs(path, exist_ok=True)
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()],
                                         home=home)
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
            parked = copy.deepcopy(authority.state["gates"][0])
            binding = parked["binding"]
            self.assertEqual(set(binding), toolchain.BINDING_FIELDS | {"codex_home"})
            self.assertEqual(binding["codex_home"], home)
            self.assertEqual(parked["status"], "detached")
            restart, calls = self.dispatching([self.gate_terminal()], home=other)
            record = self.delivery(authority, restart).run_task_gate("M1")
            self.assertEqual((record["status"], record["binding"]), ("concluded", binding))
            homes = [kwargs["env"]["CODEX_HOME"] for argv, kwargs in calls if argv[1] == "watch"]
            self.assertEqual(homes, [home])

    def test_a_preparing_record_dispatches_in_its_recorded_home(self):
        """R-3 class: the frozen `codex_home` is the home the run starts in, whichever engine a restart passes --
        the first dispatch and a recovery alike route through `engine_for(record["binding"])`. Oracle: the
        `CODEX_HOME` of the `--detach` call; control: the same record observed in its recorded home by the test
        above (`engine_for` keeps this engine only for the recorded home)."""
        home, other = str(self.root / "home-a"), str(self.root / "home-b")
        for path in (home, other):
            os.makedirs(path, exist_ok=True)
        self.approved_native_plan()
        with self.bound() as authority:
            frozen, _ = self.dispatching([], home=home)
            service = self.delivery(authority, frozen)
            status, plan = service.task_gate_admission("M1")
            record, _ = service.task_gate_new("M1", None, plan, status, frozen)
            restarted, calls = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"},
                                                 self.gate_terminal()], home=other)
            recovered = self.delivery(authority, restarted).run_task_gate("M1")
            self.assertEqual((recovered["id"], recovered["status"]), (record["id"], "concluded"))
            self.assertEqual(record["binding"]["codex_home"], home)
            self.assertEqual([kwargs["env"]["CODEX_HOME"] for argv, kwargs in calls if "--detach" in argv], [home])

    def test_an_observation_refuses_a_moved_state_root_or_changed_binary(self):
        """R-3 class: a dispatched record is watched only on its own binary, its bytes, its version and its state
        root (`gate_bound` compares the four identity fields before any dispatch or watch); a new state root or
        changed bytes refuse with `engine.identity_changed` instead of watching the run elsewhere. Oracles: the
        refusal family plus the calls the scripted engine recorded (none while refused); control: the unmutated
        restart watches in the recorded root and concludes."""
        self.approved_native_plan()
        binary = Path(self.root / "zeroshot-fixture")
        original = binary.read_text()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()])
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
            self.assertEqual(authority.state["gates"][0]["status"], "detached")

            def restart(mutate):
                engine, calls = self.dispatching([self.gate_terminal()])
                mutate(engine)
                return engine, calls

            moved, calls = restart(lambda engine: setattr(engine, "state_root", self.native.parent / "y"))
            with self.assertRaises(Blocked) as raised:
                self.delivery(authority, moved).run_task_gate("M1")
            self.assertEqual(raised.exception.family, "engine.identity_changed")
            self.assertEqual([argv for argv, _ in calls], [])
            changed, calls = restart(lambda engine: binary.write_text(original + "# changed\n"))
            with self.assertRaises(Blocked) as raised:
                self.delivery(authority, changed).run_task_gate("M1")
            self.assertEqual(raised.exception.family, "engine.identity_changed")
            self.assertEqual([argv for argv, _ in calls], [])
            binary.write_text(original)
            control, calls = self.dispatching([self.gate_terminal()])
            record = self.delivery(authority, control).run_task_gate("M1")
            self.assertEqual(record["status"], "concluded")
            self.assertEqual([argv[1] for argv, _ in calls], ["watch"])

    def test_a_restart_on_another_toolchain_observes_through_the_recorded_engine(self):
        """R-3 class: the record's own engine is selected (`engine_for`) before its identity is compared, so a
        restart whose *current* binary lives at another path still watches the recorded run with the recorded
        binary, state root and home, while a rewritten recorded binary keeps refusing `engine.identity_changed`.
        Oracles: the concluded status under the same record id, the calls of the scripted engine and the
        `CODEX_HOME` they carry; control: the same restart after the recorded binary's bytes are rewritten, which is
        refused without a single call. Interpretation: the comparison protects the *recorded* toolchain (its bytes
        and its state root), not the process that happens to be running now."""
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()])
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
            parked = copy.deepcopy(authority.state["gates"][0])
            self.assertEqual(parked["status"], "detached")
            other = self.root / "another-toolchain" / "zeroshot"
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_text("# another binary at another path\n")
            other.chmod(0o700)

            def restart(executable=None):
                restarted, calls = self.dispatching([self.gate_terminal()])
                if executable is not None:
                    restarted.executable = str(executable)
                return restarted, calls

            recorded = Path(self.root / "zeroshot-fixture")
            original = recorded.read_text()
            changed, calls = restart()
            recorded.write_text(original + "# changed\n")  # the recorded bytes move after the engine was built
            with self.assertRaises(Blocked) as raised:
                self.delivery(authority, changed).run_task_gate("M1")
            self.assertEqual(raised.exception.family, "engine.identity_changed")
            self.assertEqual([argv for argv, _ in calls], [])
            recorded.write_text(original)
            moved, calls = restart(other)
            record = self.delivery(authority, moved).run_task_gate("M1")
            self.assertEqual((record["id"], record["status"], record["binding"]),
                             (parked["id"], "concluded", parked["binding"]))
            self.assertEqual([argv[1] for argv, _ in calls], ["watch"])
            self.assertEqual(calls[0][1]["env"]["CODEX_HOME"], parked["binding"]["codex_home"])


# A-1 ------------------------------------------------------------------------------------------------------------

class OffTests(GateBase):
    """A-1: while the record exists the lifecycle guard is still `process.unbuilt` (s1a1b2 removes it)."""

    def test_a_required_task_gate_still_refuses_a_start_as_unbuilt(self):
        self.prepare()
        with self.session(FixtureEngine("accept")) as app:
            with self.assertRaises(Blocked) as raised:
                app.delivery.preview("M1", app.roles)
            self.assertEqual(raised.exception.family, "process.unbuilt")


# Repairs (rejections of the first candidate) ----------------------------------------------------------------------

class RecordSchemaTests(GateBase):
    """R-2/R-5 (the amendment's input domain): a bounded schema-directed generator over the record's closed keys.

    Class: the closed record schema of `state["gates"]`. Checked domain: the generator walks `RECORD_KEYS` itself --
    one store with each key removed, then each key carrying a wrong JSON type, then one unknown key -- every shape
    written into an otherwise valid two-record store and loaded. Oracles: the load's own refusal family
    (`store.invalid`) for every generated shape, the number of generated shapes, and the untouched store for the
    control. Interpretation: because the domain is directed by the schema (never arbitrary bytes) the generator is
    bounded -- `len(RECORD_KEYS)` missing-key shapes plus `len(WRONG_TYPES)` wrong-type shapes plus the nested
    discussion shapes of `NESTED_WRONG_TYPES` plus the one extra key -- and a wrong JSON type is malformed like a
    missing or an extra key: the strict loader reads every field, so a shape no writer produces is refused rather
    than silently dropped. The nested shapes matter because Python's `==` compares `true == 1 == 1.0`: a persisted
    discussion field whose JSON type differs from the one the record's own output parses to is malformed even where
    `==` cannot tell the two dicts apart, so the persisted discussion is compared type-preservingly. A valid control
    closes the domain: the same base store loads when nothing is mutated."""

    # One wrong JSON type per record key: the type a value could take while the shape stays JSON-decodable.
    WRONG_TYPES = {"gate": 1, "id": 1, "plan_revision": "1", "approval": 1, "milestone": 1,
                   "context": "answer", "identity": ["a"], "config": [], "rounds_limit": "2", "documents": [],
                   "binding": 1, "submission_key": 1, "status": 1, "run_id": 1, "receipt": 1, "terminal": 1,
                   "output_digest": 1, "rounds_used": "2", "discussion": "x", "critic_verdict": 1, "override": [],
                   "diagnostic": 1, "created": 1, "updated": 1}

    # Nested fields the discussion schema closes (`read_discussion`): a persisted value whose JSON type differs
    # from the parsed one must refuse the store even where Python's `==` compares them equal (`true == 1 == 1.0`).
    NESTED_WRONG_TYPES = (
        ("discussion version true", lambda gates: gates[0]["discussion"].update(version=True)),
        ("discussion version float", lambda gates: gates[0]["discussion"].update(version=1.0)),
        ("discussion version text", lambda gates: gates[0]["discussion"].update(version="1")),
        ("round number true", lambda gates: gates[0]["discussion"]["rounds"][0].update(round=True)),
        ("round number float", lambda gates: gates[0]["discussion"]["rounds"][0].update(round=1.0)),
        ("round findings true", lambda gates: gates[0]["discussion"]["rounds"][0].update(findings=True)),
        ("round response list", lambda gates: gates[0]["discussion"]["rounds"][0].update(response=[])),
    )

    def generated(self):
        """(label, mutate) pairs: every key missing, every key with a wrong JSON type, every nested discussion
        field with a wrong JSON type, then one extra key."""
        for key in sorted(task_gate.RECORD_KEYS):
            yield "missing key %s" % key, lambda gates, k=key: gates[0].pop(k)
        for key, value in sorted(self.WRONG_TYPES.items()):
            yield "wrong type %s" % key, lambda gates, k=key, v=value: gates[0].update({k: v})
        for label, mutate in self.NESTED_WRONG_TYPES:
            yield label, mutate
        yield "unknown key", lambda gates: gates[0].update(extra=1)

    def test_every_generated_schema_violation_refuses_the_store(self):
        path, base = self.two_records()
        seen = 0
        for label, mutate in self.generated():
            with self.subTest(case=label):
                state = copy.deepcopy(base)
                mutate(state["gates"])
                path.write_text(canonical(state) + "\n", encoding="utf-8")
                self.assert_refused()
            seen += 1
        self.assertEqual(seen, len(task_gate.RECORD_KEYS) + len(self.WRONG_TYPES)
                         + len(self.NESTED_WRONG_TYPES) + 1)
        path.write_text(canonical(base) + "\n", encoding="utf-8")
        self.assertEqual(self.load_gates(), base["gates"])


class StrictStoreTests(GateBase):
    """R-2/R-5 (A-4s): the persisted evidence of a concluded record must be exactly what its own run produced, and
    its revision references must exist in the store.

    Class: strict store validation of a concluded record's evidence and references. Checked domain: the verdict, the
    discussion (shape, round count, and the frozen round limit), the effective context, the `rounds_limit` type, and
    the revision/approval/milestone the record names. Oracles: an independent `task_gate.read_review` of the stored
    output under the stored limit for the evidence fields, and the store's own revisions for the references; the
    control is the untouched store. Interpretation: the persisted verdict, discussion and round count are accepted
    only while they equal what the record's own output parses to, so no record can claim evidence its run did not
    produce."""

    def test_concluded_evidence_and_references_are_validated_against_the_record(self):
        path, base = self.two_records()
        mutations = {
            "contradicted verdict": lambda g: g[0].update(critic_verdict="rejected"),
            "invented discussion": lambda g: g[0].update(discussion={"rounds": [42]}),
            "null rounds": lambda g: g[0].update(discussion={"rounds": None}),
            "unknown discussion key": lambda g: g[0]["discussion"].update(extra=True),
            "wrong round count": lambda g: g[0].update(rounds_used=3),
            "non-integer round limit": lambda g: g[0].update(rounds_limit=2.0),
            "invalid context": lambda g: g[0].update(context=42),
            "nonexistent revision": lambda g: g[0].update(plan_revision=9),
            "wrong approval": lambda g: g[0].update(approval="f" * 64),
            "nonexistent milestone": lambda g: g[0].update(milestone="M9"),
            "non version-4 id": lambda g: g[0].update(id="task-gate-12345678-1234-1234-1234-567812345678"),
            "nil uuid4 id": lambda g: g[0].update(id="task-gate-00000000-0000-0000-0000-000000000000"),
            "wrong uuid4 variant": lambda g: g[0].update(id="task-gate-12345678-1234-4abc-cdef-1234567890ab"),
            "non version-4 submission key": lambda g: g[0].update(
                submission_key="zplan-gate-12345678-1234-1234-1234-567812345678"),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                state = copy.deepcopy(base)
                mutate(state["gates"])
                path.write_text(canonical(state) + "\n", encoding="utf-8")
                self.assert_refused()
        path.write_text(canonical(base) + "\n", encoding="utf-8")
        self.assertEqual(self.load_gates(), base["gates"])


class MalformedStoreTests(GateBase):
    """R-2/R-5: shapes that make a check itself raise still refuse the store as `store.invalid`.

    Class: store validation of malformed structured fields. Checked domain: the effective context with an empty
    list / empty dict `kind`, a proposal candidate that is `{}` or carries an unknown key, and a lone surrogate
    (`chr(0xD800)`) JSON-escaped into `terminal.output.taskFindings` and into `terminal.output.discussion`.
    Oracles: the load's own refusal family for every mutation; control: the same two-record store without any
    mutation loads. Interpretation: the store is the only place that can refuse a record, so a shape the writer
    never produces must be refused there rather than crash the reader; a proposal context is additionally checked
    by reproducing the record's own artifact, so a candidate that does not fit the revision's milestone is
    malformed too, and every other raising shape (a non-string kind) is caught by the loop that validates the
    records."""

    def test_malformed_contexts_and_escaped_surrogates_refuse_the_store(self):
        path, base = self.two_records()
        contexts = {"list kind": {"kind": [], "source": 1, "text": "answer", "candidate": None},
                    "dict kind": {"kind": {}, "source": 1, "text": "answer", "candidate": None},
                    "empty candidate": {"kind": "proposal", "source": 1, "text": "candidate", "candidate": {}},
                    "unknown candidate key": {"kind": "proposal", "source": 1, "text": "candidate",
                                              "candidate": {"tasks": [], "amendments": [], "extra": []}}}
        for label, context in contexts.items():
            with self.subTest(case=label):
                state = copy.deepcopy(base)
                state["gates"][0]["context"] = context
                path.write_text(canonical(state) + "\n", encoding="utf-8")
                self.assert_refused()
        for key in ("taskFindings", "discussion"):
            with self.subTest(case="surrogate in " + key):
                state = copy.deepcopy(base)
                state["gates"][0]["terminal"]["output"][key] = chr(0xD800)
                path.write_text(json.dumps(state, ensure_ascii=True) + "\n", encoding="utf-8")
                self.assert_refused()
        path.write_text(canonical(base) + "\n", encoding="utf-8")
        self.assertEqual(self.load_gates(), base["gates"])


class PersistedEvidenceTests(GateBase):
    """R-2/R-5: evidence the store cannot hold is refused on load, never written and never a crash.

    Class: store validation of a concluded record whose decoded discussion holds an unpaired surrogate. Checked
    domain: an otherwise consistent record -- matching `output_digest`, `critic_verdict` and round count, whose
    `discussion` and the discussion inside its own succeeded `terminal.output` decode to `chr(0xD800)`/`chr(0xDC00)`
    (the outer JSON is escaped, so the record bytes are valid UTF-8). Controls: the same record with ordinary Unicode
    text, and the untouched two-record store. Oracle: the load's own refusal family for each surrogate and a clean
    load for both controls. Interpretation: a decoded lone surrogate cannot survive `canonical`, so a record carrying
    one is `store.invalid` no matter how well its other fields agree -- `parse_evidence` alone would accept it."""

    def surrogate_record(self, base, left):
        """`base`'s first record with a discussion that decodes to `left`, its output digest and references refit."""
        rounds_ = [round_(1, findings="открыто: %s" % left),
                   round_(2, verdict="accepted", findings="ok", response="ok")]
        output = {"schemaVersion": "1", "taskVerdict": "accepted", "taskFindings": "ok", "taskResponse": "ok",
                  "discussion": json.dumps({"version": 1, "rounds": rounds_}, ensure_ascii=True)}
        record = base["gates"][0]
        record["terminal"] = {"status": "succeeded", "output": output}
        record["output_digest"] = digest(output)
        record["critic_verdict"] = "accepted"
        record["discussion"] = {"version": 1, "rounds": rounds_}
        record["rounds_used"] = len(rounds_)
        record["diagnostic"] = "ok"
        return record

    def test_a_persisted_discussion_with_a_lone_surrogate_refuses_the_store(self):
        path, base = self.two_records()
        for left in (chr(0xD800), chr(0xDC00)):
            with self.subTest(surrogate=hex(ord(left))):
                state = copy.deepcopy(base)
                self.surrogate_record(state, left)
                path.write_text(json.dumps(state, ensure_ascii=True) + "\n", encoding="utf-8")
                self.assert_refused()
        for text_ in ("Кириллица ✅", "plain"):
            with self.subTest(control=text_):
                state = copy.deepcopy(base)
                self.surrogate_record(state, text_)
                path.write_text(json.dumps(state, ensure_ascii=True) + "\n", encoding="utf-8")
                self.assertEqual(self.load_gates(), state["gates"])

    def test_a_lone_surrogate_outside_the_output_refuses_the_store(self):
        """R-5 class: the record is refused from the very bytes `canonical` would write, so a lone surrogate in a
        plain string field (`diagnostic`) -- one no parser ever re-reads -- refuses the store instead of loading and
        crashing the next writer. Oracle: the load's own refusal family; control: the untouched record without the
        surrogate loads. Interpretation: the whole record, not only its output, must survive serialization."""
        path, base = self.two_records()
        state = copy.deepcopy(base)
        state["gates"][0]["diagnostic"] = chr(0xD800)
        path.write_text(json.dumps(state, ensure_ascii=True) + "\n", encoding="utf-8")
        self.assert_refused()
        path.write_text(canonical(base) + "\n", encoding="utf-8")
        self.assertEqual(self.load_gates(), base["gates"])


class PersistenceTests(GateBase):
    """R-2/A-4l (the amendment's fault model): the first directory fsync after `atomic_state` replaced the store
    with the initial `preparing` record fails once; the published record is preserved and its id recovered.

    Class: `Delivery.task_gate_new`'s rollback of a failed append. Checked domain: one synchronous `OSError` from
    that one directory fsync (ordinary I/O resumes), with a fault-free control, a second record published beside an
    existing one, and both retry paths -- the same service and a reopened `Authority`. Oracles: the reported
    `PersistenceError`, the store file's own bytes read back with `json.loads` (no production helper), the record's
    persisted `status`/`run_id` (a `preparing` record with no run id proves nothing was dispatched), the earlier
    record's bytes, and the recovered id on either retry. Interpretation: `save` publishes the file before its
    directory fsync, so the handler may roll back only an append that never reached the file; a `preparing` record
    that survives is recovered -- never resubmitted -- so an owner retry cannot erase or duplicate it."""

    def injecting(self):
        """(patch, count): the first directory fsync raises, ordinary I/O resumes."""
        real_fsync, count = os.fsync, {"directory": 0}

        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                count["directory"] += 1
                if count["directory"] == 1:
                    raise OSError(5, "injected directory fsync")
            return real_fsync(fd)

        return patch.object(authority_module.os, "fsync", side_effect=fsync), count

    def test_a_fault_free_save_publishes_exactly_one_record(self):
        """Control: without the injected failure the same call stores one concluded record."""
        self.prepare()
        with self.session(FixtureEngine("accept")) as app:
            record = app.delivery.run_task_gate("M1")
        self.assertEqual([(entry["id"], entry["status"]) for entry in self.load_gates()],
                         [(record["id"], "concluded")])

    def test_the_failed_initial_save_dispatches_nothing_and_keeps_earlier_records(self):
        """A second record's failed initial save leaves the first byte-identical and dispatches nothing: the store's
        own bytes still show the new record as `preparing` with no run id."""
        self.gate(FixtureEngine("accept"))
        path, base = self.stored_state()
        first = base["gates"][0]
        with self.session(FixtureEngine("accept")) as app:
            injected, count = self.injecting()
            with injected:
                with self.assertRaises(PersistenceError):
                    app.delivery.rerun_task_gate("M1")
            self.assertEqual(count["directory"], 1)
        after = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(after["gates"][0], first)
        self.assertEqual([entry["status"] for entry in after["gates"]], ["concluded", "preparing"])
        self.assertIsNone(after["gates"][1]["run_id"])

    def test_a_reopened_authority_recovers_the_published_record(self):
        """The guarantee's second retry path: a reopened `Authority` reads the published `preparing` record back
        from the file and recovers the same id, dispatching nothing new."""
        self.prepare()
        with self.session(FixtureEngine("accept")) as app:
            injected, count = self.injecting()
            with injected:
                with self.assertRaises(PersistenceError):
                    app.delivery.run_task_gate("M1")
            self.assertEqual(count["directory"], 1)
            record_id = json.loads(app.authority.path.read_text(encoding="utf-8"))["gates"][0]["id"]
        with self.session(FixtureEngine("accept")) as app:
            self.assertEqual([entry["id"] for entry in app.authority.state["gates"]], [record_id])
            recovered = app.delivery.run_task_gate("M1")
            self.assertEqual((recovered["id"], recovered["status"]), (record_id, "concluded"))
            self.assertEqual([entry["id"] for entry in app.authority.state["gates"]], [record_id])
        self.assertEqual([(entry["id"], entry["status"]) for entry in self.load_gates()],
                         [(record_id, "concluded")])

    def test_a_published_preparing_record_is_not_erased_by_a_failed_save(self):
        self.prepare()
        injected, count = self.injecting()

        with self.session(FixtureEngine("accept")) as app:
            with injected:
                with self.assertRaises(PersistenceError):
                    app.delivery.run_task_gate("M1")
            self.assertEqual(count["directory"], 1)
            on_disk = json.loads(app.authority.path.read_text(encoding="utf-8"))
            self.assertEqual([entry["status"] for entry in on_disk["gates"]], ["preparing"])
            record_id = on_disk["gates"][0]["id"]
            self.assertEqual([entry["id"] for entry in app.authority.state["gates"]], [record_id])
            recovered = app.delivery.run_task_gate("M1")
            self.assertEqual((recovered["id"], recovered["status"]), (record_id, "concluded"))
            self.assertEqual([entry["id"] for entry in app.authority.state["gates"]], [record_id])
        self.assertEqual([(entry["id"], entry["status"]) for entry in self.load_gates()],
                         [(record_id, "concluded")])


class NestedOutputTests(GateBase):
    """R-4/A-6b/R-5: a refused output nested deeper than the store can keep writable *and* reloadable stays safe.

    Class: nesting and the store's round trip. Checked domain: `"x"` wrapped in 1, 400 and 500 lists (all three the
    store keeps, while `copy.deepcopy` cannot walk the last), in 5000 lists (kept only when the store's own write
    and read both hold, so its case asserts the invariant rather than a fixed tuple), in 5001 and 9990 lists (past
    the retention limit, so no terminal on any interpreter), behind a serializer stub at the store envelope's own
    depth, behind a reader stub that refuses that envelope, and behind a permissive reader stub that leaves the
    nesting limit as the only guard; each delivered through the production fixture dispatch path and then listed
    with `Delivery.task_gates` and read back from the store file (no deep copy of the output, which is the very
    operation that used to crash). Oracles: the record's own persisted status and whether it kept a terminal, the
    listed ids, and the ids the file itself carries; control: a shallow output (depth 1), which the store keeps
    whole. Interpretation: the amendment names depths 1/400/500/5000 and keeps a retained payload only while it is
    writable, reloadable and listable at the complete store-envelope depth -- read as retention inside that domain
    and refusal past it, so `OUTPUT_NESTING_LIMIT` is 5000, the deepest depth named, never a probe of the
    interpreter's own reader budget, which depends on the calling stack. The stubs pin what the real ones hide."""

    def gated(self, output):
        """(id, status, kept_terminal, digest, discussion, diagnostic) of one fixture gate over `output`; never
        deep-copies the output."""
        self.state_dir_reset()
        self.prepare()

        def call(app):
            record = app.delivery.run_task_gate("M1")
            return {"id": record["id"], "status": record["status"], "terminal": record["terminal"] is not None,
                    "output_digest": record["output_digest"], "discussion": record["discussion"],
                    "critic_verdict": record["critic_verdict"], "diagnostic": record["diagnostic"]}
        return self.in_session(FixtureEngine("accept", terminal_output=output), call)

    def listed(self):
        return self.in_session(FixtureEngine("accept"), lambda app: app.delivery.task_gates("M1"))

    def on_disk(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return [(entry["id"], entry["status"]) for entry in authority.state["gates"]]

    def test_a_deep_refused_output_is_still_writable_and_listable(self):
        """The domain's holdable depths, 1 (the shallow control), 400 and 500: each stays writable, listable and on
        disk, and the record keeps the terminal whose output the parser refused."""
        for depth in (1, 400, 500):
            with self.subTest(depth=depth):
                record = self.gated(nested(depth))
                self.assertEqual((record["status"], record["terminal"]), ("output_invalid", True))
                self.assertEqual([entry["id"] for entry in self.listed()], [record["id"]])
                self.assertEqual(self.on_disk(), [(record["id"], "output_invalid")])

    def test_an_output_at_the_retention_limit_leaves_no_terminal_when_it_is_unpersistable(self):
        """The deepest nesting the input domain names (5000): kept only when the store's own round trip holds.

        Whether that payload is holdable is the *interpreter's* recursion thresholds, not this slice's contract, so
        this case asserts the invariant instead of one fixed tuple: the record is `output_invalid` without usable
        evidence, and a payload the store cannot round-trip leaves no terminal and no digest (both keys retained,
        the refusal in `diagnostic`), while a payload it can round-trip keeps the terminal the parser refused.
        Either way the record stays writable, reloadable and listable. The interpreter-independent unpersistable
        coverage is the raw-surrogate case, the serializer stub and the reader stub below, none of which depends on
        a depth; the depths *past* the limit are the next test's."""
        record = self.gated(nested(5000))
        self.assertEqual(record["status"], "output_invalid")
        self.assertIsNone(record["critic_verdict"])
        self.assertIsNone(record["discussion"])
        if record["terminal"]:
            self.assertIsNotNone(record["output_digest"])
        else:
            self.assertIsNone(record["output_digest"])
            self.assertIn("saved", record["diagnostic"])
        self.assertEqual([entry["id"] for entry in self.listed()], [record["id"]])
        self.assertEqual(self.on_disk(), [(record["id"], "output_invalid")])

    def test_an_output_past_the_retention_limit_leaves_no_terminal(self):
        """The depths past the deepest the input domain names (5001 and 9990) are refused on every interpreter.

        The contract keeps the record loadable, so the oracle is the record's own terminal pair plus the two reads
        that used to fail: `listed` reopens the store through the production loader and `on_disk` decodes the file
        directly. The 9990 case is the reported regression -- the writer held it, the reader's own recursion refused
        the whole store (`store.invalid`); a fixed retention limit, not a probe of the reader's budget, is what makes
        the outcome interpreter-independent."""
        for depth in (5001, 9990):
            with self.subTest(depth=depth):
                record = self.gated(nested(depth))
                self.assertEqual(record["status"], "output_invalid")
                self.assertIsNone(record["critic_verdict"])
                self.assertIsNone(record["discussion"])
                self.assertFalse(record["terminal"])
                self.assertIsNone(record["output_digest"])
                self.assertIn("saved", record["diagnostic"])
                self.assertEqual([entry["id"] for entry in self.listed()], [record["id"]])
                self.assertEqual(self.on_disk(), [(record["id"], "output_invalid")])

    def test_a_payload_past_the_nesting_limit_is_refused_even_when_the_reader_would_take_it(self):
        """Reader-permissive portability of the retention boundary: with the store's reader stubbed to accept every
        text, the explicit nesting limit is the last guard left for a payload the writer holds. The depth just past
        the limit (5001) then loses its terminal and digest, while the shallow control (depth 4, one every
        interpreter holds) keeps the terminal the parser refused -- so the case fails on the supported interpreter
        whenever the limit is not enforced, and the control never depends on a recursion budget, which is what makes
        it portable."""
        with patch.object(task_gate, "decode", side_effect=lambda text: None):
            past = self.gated(nested(5001))
            control = self.gated(nested(4))
        self.assertEqual((past["status"], past["terminal"], past["output_digest"]), ("output_invalid", False, None))
        self.assertIn("saved", past["diagnostic"])
        self.assertEqual((control["status"], control["terminal"]), ("output_invalid", True))
        self.assertIsNotNone(control["output_digest"])
        self.assertEqual([entry["id"] for entry in self.listed()], [control["id"]])
        self.assertEqual(self.on_disk(), [(control["id"], "output_invalid")])

    def test_the_record_is_dropped_when_the_store_cannot_read_its_own_write_back(self):
        """A reader stub that refuses the `state["gates"]` envelope while taking the bare payload pins retention on
        the store's round trip: the envelope-aware reader check drops the output (no terminal) even at depth 4, which
        the writer itself holds, while an encode-only check would keep it and leave a store the loader refuses."""
        real = task_gate.decode

        def decode_stub(text):
            if text.startswith('{"gates":['):
                raise Blocked("Invalid JSON envelope.", family="store.invalid")
            return real(text)

        with patch.object(task_gate, "decode", side_effect=decode_stub):
            record = self.gated(nested(4))
        self.assertEqual((record["status"], record["terminal"]), ("output_invalid", False))
        self.assertIsNone(record["output_digest"])
        self.assertIn("saved", record["diagnostic"])
        self.assertEqual([entry["id"] for entry in self.listed()], [record["id"]])
        self.assertEqual(self.on_disk(), [(record["id"], "output_invalid")])

    def test_the_record_is_checked_at_the_depth_the_store_writes_it(self):
        """A serializer stub that refuses the `state["gates"]` envelope while accepting the bare output pins the
        check at the depth the store writes: the envelope-aware check drops the deep output (no terminal), while an
        output-only check would keep it and refuse the store's own write."""
        real = task_gate.canonical

        def canonical_stub(value):
            if isinstance(value, dict) and "gates" in value:
                raise RecursionError("the store envelope cannot be walked")
            return real(value)

        with patch.object(task_gate, "canonical", side_effect=canonical_stub):
            record = self.gated(nested(4))
        self.assertEqual((record["status"], record["terminal"]), ("output_invalid", False))


class CandidateShapeTests(GateBase):
    """R-2/R-5: a proposal context's candidate is exactly the `{"tasks", "amendments"}` task list `runs.structured`
    accepts, so an unknown key refuses the store even when it cannot change the artifact.

    Class: store validation of a concluded proposal-context record's candidate. Checked domain: a *valid* task list
    (the milestone's own manifest tasks) with one added unknown key, and the same candidate untouched as control.
    Oracle: the load's own refusal family for the mutation and a clean load for the control. Interpretation: the
    record's artifact is reproduced from the record's own context, but an extra candidate key does not change the
    manifest, so only a closed-shape check on the candidate itself can refuse it -- the existing empty-task-list
    regression fails earlier, in the artifact reproduction."""

    def gate_with_candidate(self):
        """One concluded task gate whose context carries a valid accepted-proposal candidate for M1."""
        self.prepare()

        def call(app):
            _, manifest = milestone.build_manifest(app.authority.current["proposal"], "M1", 1)
            candidate = {"tasks": copy.deepcopy(manifest["tasks"]),
                         "amendments": copy.deepcopy(manifest["amendments"])}
            context = {"kind": "proposal", "source": 1, "text": "Owner accepted a proposal.", "candidate": candidate}
            return copy.deepcopy(app.delivery.run_task_gate("M1", context=context))
        return self.in_session(FixtureEngine("accept"), call)

    def test_an_unknown_candidate_key_refuses_the_store(self):
        record = self.gate_with_candidate()
        self.assertEqual((record["status"], record["context"]["kind"]), ("concluded", "proposal"))
        path, base = self.stored_state()
        self.assertEqual(self.load_gates(), [record])
        state = copy.deepcopy(base)
        state["gates"][0]["context"]["candidate"]["extra"] = True
        path.write_text(canonical(state) + "\n", encoding="utf-8")
        self.assert_refused()
        path.write_text(canonical(base) + "\n", encoding="utf-8")
        self.assertEqual(self.load_gates(), base["gates"])


class FrozenConfigTests(GateBase):
    """R-4: one resolved configuration supplies both the record's `resolved_config_digest` and its frozen documents.

    Class: configuration identity versus the documents. Checked domain: a rule file rewritten between the profile
    resolution and the document construction (a fresh dispatch), and between a `preparing` save and its rebuild.
    Oracles: the live configuration digest computed from the live rule hashes for the first, and the exception
    family plus the untouched store for both; the control is the untouched project whose gate concludes. The frozen
    identity digest is the only authority: the rebuild re-reads the record's own rule files and refuses
    (`engine.intent_changed`) when they no longer resolve to it, never adopting the live configuration."""

    def test_a_rule_changed_between_resolution_and_documents_refuses(self):
        self.rules()
        self.prepare({"gates": {"task": "required"}, "rules": ["AGENTS.md"]})
        with self.session(FixtureEngine("accept")) as app:
            profile = app.authority.profile
            resolved = profile.status(write=False)
            original = profile.status

            def status(*args, **kwargs):
                value = original(*args, **kwargs)
                (self.project / "AGENTS.md").write_text("changed rules\n")  # after the resolution, before the docs
                return value

            with patch.object(profile, "status", side_effect=status):
                with self.assertRaises(Blocked) as raised:
                    app.delivery.run_task_gate("M1")
            self.assertEqual(raised.exception.family, "process.changed")
            self.assertNotIn("gates", app.authority.state or {})
            live = process.config_digest(resolved.resolved.config, process.read_rules(self.project, ["AGENTS.md"]))
            self.assertNotEqual(live, resolved.digest)  # the frozen digest would have described other documents

    def test_a_rule_changed_before_a_rebuild_refuses_with_intent_changed(self):
        self.rules()
        self.prepare({"gates": {"task": "required"}, "rules": ["AGENTS.md"]})

        def park(app):
            record, _ = app.delivery.task_gate_new("M1", None, app.delivery.plan(),
                                                   app.planning.profile.status(write=False), FixtureEngine("accept"))
            return copy.deepcopy(record)
        parked = self.in_session(FixtureEngine("accept"), park)
        (self.project / "AGENTS.md").write_text("changed rules\n")

        def call(app, parked=parked):
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                app.delivery.run_task_gate("M1")
            self.assertEqual(raised.exception.family, "engine.intent_changed")
            self.assertEqual(app.authority.path.read_bytes(), before)
            self.assertEqual(app.authority.state["gates"][-1], parked)
        self.in_session(FixtureEngine("accept"), call)


class NativeRecoveryTests(NativeGateBase):
    """A-4l/R-3/R-4 over the scripted native binary: an interrupted preparation and the authoritative profile."""

    def test_a_preparation_that_completed_before_a_crash_is_recovered(self):
        """A-4l class: a `preparing` record whose checkout and three frozen files were completed before the crash is
        continued, not refused (`engine.checkout`) and not rerun: `gate_prepare` reuses the on-disk preparation while
        it still hashes to the record's own digests. Oracle: the same record id reaches a terminal state over one
        dispatch; control: `rerun_task_gate` still refuses a nonterminal record (in this module)."""
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([])
            service = self.delivery(authority, engine)
            status, plan = service.task_gate_admission("M1")
            record, documents = service.task_gate_new("M1", None, plan, status, engine)
            engine.gate_prepare(authority, record, documents)  # the preparation finished; the crash follows
        with self.bound() as authority:
            engine, calls = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, self.gate_terminal()])
            recovered = self.delivery(authority, engine).run_task_gate("M1")
            self.assertEqual((recovered["id"], recovered["status"]), (record["id"], "concluded"))
            self.assertEqual(len([argv for argv, _ in calls if argv[1] == "run" and "--detach" in argv]), 1)

    def test_a_rule_changed_after_a_completed_preparation_still_recovers(self):
        """A-4l/R-4 class: a `preparing` record whose checkout and frozen documents are already on disk is recovered
        under its own frozen configuration, so a rule file rewritten after the preparation does not refuse it; only a
        record with nothing on disk rebuilds its documents from the frozen configuration (and refuses when the rules
        moved). Oracles: the same record id reaches `concluded` over exactly one dispatch, and the refusal-free
        recovery leaves the rewritten rule out of the run; control: `FrozenConfigTests` over the same service, whose
        never-prepared record is still refused with `engine.intent_changed`."""
        self.rules()
        self.accepted_profile({"gates": {"task": "required"}, "rules": ["AGENTS.md"]})
        plan_engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal()])
        with self.authority() as authority:
            authority.profile = Profile.of(authority)
            authority.begin("Requested feature", ROLES, "native")
            plan_engine.proposal(authority, lambda _: None)
            authority.approve(1)
        with self.bound() as authority:
            engine, _ = self.dispatching([])
            service = self.delivery(authority, engine)
            status, plan = service.task_gate_admission("M1")
            record, documents = service.task_gate_new("M1", None, plan, status, engine)
            engine.gate_prepare(authority, record, documents)  # the preparation finished; the crash follows
        (self.project / "AGENTS.md").write_text("changed rules\n")
        with self.bound() as authority:
            engine, calls = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, self.gate_terminal()])
            recovered = self.delivery(authority, engine).run_task_gate("M1")
            self.assertEqual((recovered["id"], recovered["status"]), (record["id"], "concluded"))
            self.assertEqual(len([argv for argv, _ in calls if argv[1] == "run" and "--detach" in argv]), 1)

    def test_an_unbound_authority_profile_refuses_despite_a_bound_service(self):
        """R-4 class: admission reads the authoritative `Authority.profile`, never the `Planning` service's own
        profile, so a service that holds a usable profile cannot enable a gate whose authority has none. Oracles:
        the refusal family, the calls the scripted engine recorded (none) and the untouched store; control: the same
        project with a bound authority (`bound()`), which concludes."""
        self.approved_native_plan()
        with self.authority() as authority:  # bound in no session: `Authority.profile` is None here
            self.assertIsNone(authority.profile)
            engine, calls = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, self.gate_terminal()])
            before = authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                self.delivery(authority, engine).run_task_gate("M1")  # the service passes a profile of its own
            self.assertEqual(raised.exception.family, "action.refused")
            self.assertEqual(calls, [])
            self.assertEqual(authority.path.read_bytes(), before)
            self.assertNotIn("gates", authority.state or {})

    def test_the_store_refuses_a_native_binding_that_is_not_the_full_shape(self):
        """R-2/R-3 class: a production store accepts only a `toolchain.valid_binding` native binding; a missing
        `codex_home`, a `version: None` -- which must be `store.invalid`, never a `TypeError` -- and a fixture-shaped
        binding all refuse the whole store. Oracles: reloading the record's own bytes with one mutation; control: the
        untouched store loads its records."""
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, self.gate_terminal()])
            self.delivery(authority, engine).run_task_gate("M1")
        with self.authority() as authority:
            path, base = authority.path, copy.deepcopy(authority.state)
        self.assertEqual(set(base["gates"][0]["binding"]), toolchain.BINDING_FIELDS | {"codex_home"})
        mutations = {"without a home": lambda record: record["binding"].pop("codex_home"),
                     "a null version": lambda record: record["binding"].update(version=None),
                     "a fixture binding": lambda record: record.update(binding={"fixture_id": "test"})}
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                state = copy.deepcopy(base)
                mutate(state["gates"][0])
                path.write_text(canonical(state) + "\n", encoding="utf-8")
                with self.assertRaises(Blocked) as raised:
                    with self.authority():
                        pass
                self.assertEqual(raised.exception.family, "store.invalid")
        path.write_text(canonical(base) + "\n", encoding="utf-8")
        with self.authority() as authority:
            self.assertEqual(authority.state["gates"], base["gates"])


class TerminalIdentityTests(NativeGateBase):
    """Parent R-2 terminal identity: the observed run's id, frozen HEAD, submitted title and frozen size.

    Class: the terminal envelope's identity fields, each checked on its own. Checked domain: a `finished` projection
    naming another `runId`, another commit, another title or another size, delivered through the production
    observation path to a record already dispatched and detached. Oracles: the refusal family, the record's own
    persisted status/verdict/terminal after the refusal and the calls of the scripted engine; control: the same
    restart with the recorded fields, which concludes. Interpretation: the frozen HEAD, the submitted title and the
    frozen size are the record's intent, and the amendment's closed list makes the run id a fourth identity field,
    so a *nonempty* run id that is not the recorded one refuses `engine.intent_changed` exactly like the other three;
    a missing, empty or non-string run id stays `validate_projection`'s own structural `store.invalid`."""

    def test_a_terminal_envelope_of_another_revision_is_refused(self):
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()])
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
        with self.bound() as authority:
            parked = copy.deepcopy(authority.state["gates"][0])
            self.assertEqual(parked["status"], "detached")
            alien = self.gate_terminal()
            alien["source"]["revision"] = "0" * 40
            other, _ = self.dispatching([alien])
            with self.assertRaises(Blocked) as raised:
                self.delivery(authority, other).run_task_gate("M1")
            self.assertEqual(raised.exception.family, "engine.intent_changed")
            after = authority.state["gates"][0]
            self.assertEqual((after["id"], after["status"], after["critic_verdict"], after["terminal"]),
                             (parked["id"], "observation_blocked", None, None))
            control, calls = self.dispatching([self.gate_terminal()])
            record = self.delivery(authority, control).run_task_gate("M1")
            self.assertEqual((record["id"], record["status"], record["critic_verdict"]),
                             (parked["id"], "concluded", "accepted"))
            self.assertEqual([argv[1] for argv, _ in calls], ["watch"])

    def test_a_projection_of_another_run_id_is_refused(self):
        """Parent R-2 terminal identity, the run id field: the observed envelope names the record's own run.

        Class: the terminal envelope's `runId`. Checked domain: a `finished` projection of the recorded revision,
        title and size whose `runId` names another (nonempty) run, a projection whose `runId` is structurally
        unusable (empty, then absent), and the same projection with the recorded run id as control -- each delivered
        through the production observation path to a record already dispatched and detached. Oracles: the refusal
        family, the record's own persisted status after the refusal and the calls of the scripted engine.
        Interpretation: the amendment's closed list makes the run id one of the four identity fields, so a
        *nonempty* run id that differs from the recorded one refuses `engine.intent_changed`, exactly like the
        frozen HEAD, the submitted title and the frozen size; the existing structural envelope validation still
        applies to everything else, so a missing, empty or non-string run id stays its own `store.invalid`. Either
        way the mismatching projection supplies no terminal, the record stays nonterminal and the same record
        concludes only under its own run."""
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()])
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
        with self.bound() as authority:
            record_id = authority.state["gates"][0]["id"]
        for label, mutate, family in (("foreign run id", lambda value: value.update(runId="another-run"),
                                       "engine.intent_changed"),
                                      ("empty run id", lambda value: value.update(runId=""),
                                       "store.invalid"),
                                      ("absent run id", lambda value: value.pop("runId"), "store.invalid")):
            with self.subTest(field=label):
                with self.bound() as authority:
                    parked = copy.deepcopy(authority.state["gates"][0])
                    self.assertFalse(task_gate.terminal(parked["status"]))
                    self.assertEqual(parked["run_id"], "fixture-native-run")
                    alien = self.gate_terminal()
                    mutate(alien)
                    other, _ = self.dispatching([alien])
                    with self.assertRaises(Blocked) as raised:
                        self.delivery(authority, other).run_task_gate("M1")
                    self.assertEqual(raised.exception.family, family)
                    after = authority.state["gates"][0]
                    self.assertEqual((after["id"], after["status"], after["critic_verdict"], after["terminal"]),
                                     (record_id, "observation_blocked", None, None))
        with self.bound() as authority:
            control, calls = self.dispatching([self.gate_terminal()])
            record = self.delivery(authority, control).run_task_gate("M1")
            self.assertEqual((record["id"], record["status"], record["critic_verdict"]),
                             (record_id, "concluded", "accepted"))
            self.assertEqual([argv[1] for argv, _ in calls], ["watch"])

    def test_a_projection_of_another_title_or_size_is_refused(self):
        """Parent R-2 terminal identity: the observed run's immutable intent is the submitted title and the frozen
        runtime size, next to its frozen HEAD.

        Class: the terminal envelope's `title` and `size`. Checked domain: a `finished` projection of the recorded
        revision that renames the title (`Task gate M2`) or shrinks the runtime (`small`), and the same projection
        unchanged as control, all delivered through the production observation path to a record already dispatched
        and detached. Oracles: the refusal family, the record's own persisted status after each refusal and the
        calls of the scripted engine. Interpretation: the submitted title and the frozen size are the record's
        intent exactly as its HEAD is, so a projection of another intent never concludes it; the record stays
        nonterminal and the same record then concludes under the unchanged projection."""
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()])
            with self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, engine).run_task_gate("M1")
        with self.bound() as authority:
            record_id = authority.state["gates"][0]["id"]
        for label, mutate in (("title", lambda value: value.update(title="Task gate M2")),
                              ("size", lambda value: value.update(size="small"))):
            with self.subTest(field=label):
                with self.bound() as authority:
                    parked = copy.deepcopy(authority.state["gates"][0])
                    self.assertFalse(task_gate.terminal(parked["status"]))
                    alien = self.gate_terminal()
                    mutate(alien)
                    other, _ = self.dispatching([alien])
                    with self.assertRaises(Blocked) as raised:
                        self.delivery(authority, other).run_task_gate("M1")
                    self.assertEqual(raised.exception.family, "engine.intent_changed")
                    after = authority.state["gates"][0]
                    self.assertEqual((after["id"], after["status"], after["critic_verdict"], after["terminal"]),
                                     (record_id, "observation_blocked", None, None))
        with self.bound() as authority:
            control, calls = self.dispatching([self.gate_terminal()])
            record = self.delivery(authority, control).run_task_gate("M1")
            self.assertEqual((record["id"], record["status"], record["critic_verdict"]),
                             (record_id, "concluded", "accepted"))
            self.assertEqual([argv[1] for argv, _ in calls], ["watch"])


class NativeEvidenceTests(NativeGateBase):
    """R-2/R-5/A-6b over the scripted native binary: an output the store cannot hold never crashes the writer.

    Class: the native gate conclusion (`gate_conclude`). Checked domain: a `succeeded` terminal whose discussion
    JSON decodes to `chr(0xD800)` (the envelope itself is still holdable, so the parser refuses it), one whose own
    `taskFindings` holds a raw `chr(0xDC00)` (the envelope is not holdable, so no terminal is kept), and a
    well-formed Unicode output as control. Oracles: the record's own persisted status, evidence and terminal fields
    and the fact that the store still reloads. An unpaired surrogate cannot be persisted, so the run concludes
    `output_invalid` with no verdict and -- when the envelope itself is unholdable -- no terminal at all."""

    def dispatched_gate(self, output):
        """One dispatched native gate over `output`; returns the persisted record, reloaded from the store."""
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"},
                                          self.gate_terminal(output=output)])
            self.delivery(authority, engine).run_task_gate("M1")
        with self.authority() as authority:
            return copy.deepcopy(authority.state["gates"][0])

    def test_a_decoded_discussion_surrogate_is_refused_by_the_parser(self):
        record = self.dispatched_gate(surrogate_output(chr(0xD800)))
        self.assertEqual(record["status"], "output_invalid")
        self.assertIsNone(record["critic_verdict"])
        self.assertIsNone(record["discussion"])
        self.assertEqual(record["terminal"]["status"], "succeeded")  # the ASCII envelope itself is holdable
        self.assertEqual(record["output_digest"], digest(record["terminal"]["output"]))

    def test_a_raw_surrogate_in_the_envelope_leaves_no_terminal(self):
        output = {"schemaVersion": "1", "taskVerdict": "accepted", "taskFindings": chr(0xDC00), "taskResponse": "ok",
                  "discussion": canonical({"version": 1, "rounds": [round_(1)]})}
        record = self.dispatched_gate(output)
        self.assertEqual(record["status"], "output_invalid")
        self.assertIsNone(record["critic_verdict"])
        self.assertIsNone(record["terminal"])
        self.assertIsNone(record["output_digest"])

    def test_an_ordinary_unicode_output_still_concludes(self):
        record = self.dispatched_gate(surrogate_output("Кириллица ✅"))
        self.assertEqual((record["status"], record["critic_verdict"]), ("concluded", "accepted"))
        self.assertEqual(record["rounds_used"], 2)


class ReceiptTests(NativeGateBase):
    """R-4/A-5: a detach answer this client cannot confirm is an unconfirmed submission, never a malformed store.

    Class: `NativeEngine.gate_confirmed`'s receipt handling. Checked domain: an empty object, an empty `runId`, an
    extra receipt key, an answer the client cannot even parse (`{broken`), and a receipt the store cannot hold (a
    decoded lone surrogate `U+D800`/`U+DC00` in its `runId`) -- each a shape the native envelope may produce while
    the run is already live. Oracles: the refusal family, the run the scripted engine actually dispatched (`--detach`
    once), the record in memory *and* in the store file right after the failure (`submission_unknown`, no run id, no
    receipt -- the status saved before the dispatch), and both retries (the same service and a reopened `Authority`)
    refusing without a second dispatch; control: a well-formed receipt, which concludes. Interpretation: an
    unconfirmable answer means "the submission may have happened", so the family is `submission.unknown` --
    `store.invalid` or `engine.bad_output` would mark it repairable and let a later call resubmit a run that may
    already be live -- and the record keeps the uncertainty in memory, not only on disk."""

    def dispatched(self, calls):
        return [argv for argv, _ in calls if argv[1] == "run" and "--detach" in argv]

    def reset(self):
        """A fresh production store between the cases of one test (each case starts its own native plan)."""
        import shutil
        shutil.rmtree(authority_module.production_root(), ignore_errors=True)

    def test_an_unconfirmed_receipt_is_an_unconfirmed_submission(self):
        cases = {"empty object": {}, "empty run id": {"runId": ""}, "extra key": {"runId": "r", "extra": 1},
                 "unparsable answer": "{broken", "high surrogate run id": {"runId": chr(0xD800)},
                 "low surrogate run id": {"runId": chr(0xDC00)}}
        for label, receipt in cases.items():
            with self.subTest(case=label):
                self.reset()
                self.approved_native_plan()
                with self.bound() as authority:
                    engine, calls = self.dispatching([{"valid": True}, receipt])
                    with self.assertRaises(Blocked) as raised:
                        self.delivery(authority, engine).run_task_gate("M1")
                    self.assertEqual(raised.exception.family, "submission.unknown")
                    self.assertEqual(len(self.dispatched(calls)), 1)
                    # The uncertainty is the record's state, in memory and in the store file alike.
                    memory = authority.state["gates"][0]
                    self.assertEqual((memory["status"], memory["run_id"], memory["receipt"]),
                                     ("submission_unknown", None, None))
                    on_disk = json.loads(authority.path.read_text(encoding="utf-8"))["gates"][0]
                    self.assertEqual((on_disk["status"], on_disk["run_id"], on_disk["receipt"]),
                                     ("submission_unknown", None, None))
                    # The same service refuses, dispatches nothing and changes nothing.
                    again, calls2 = self.dispatching([self.gate_terminal()])
                    with self.assertRaises(Blocked) as same:
                        self.delivery(authority, again).run_task_gate("M1")
                    self.assertEqual(same.exception.family, "submission.unknown")
                    self.assertEqual(calls2, [])
                    self.assertEqual(authority.state["gates"][0], memory)
                with self.bound() as authority:  # a restart: only what reached the disk is known
                    parked = copy.deepcopy(authority.state["gates"][0])
                    self.assertEqual((parked["status"], parked["run_id"], parked["receipt"]),
                                     ("submission_unknown", None, None))
                    restart, calls3 = self.dispatching([self.gate_terminal()])
                    with self.assertRaises(Blocked) as reopened:
                        self.delivery(authority, restart).run_task_gate("M1")
                    self.assertEqual(reopened.exception.family, "submission.unknown")
                    self.assertEqual(calls3, [])
                    self.assertEqual(authority.state["gates"][0], parked)
                    self.assertEqual(len(authority.state["gates"]), 1)

    def test_a_well_formed_receipt_concludes(self):
        self.approved_native_plan()
        with self.bound() as authority:
            engine, _ = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, self.gate_terminal()])
            record = self.delivery(authority, engine).run_task_gate("M1")
            self.assertEqual((record["status"], record["critic_verdict"]), ("concluded", "accepted"))


class QualificationTests(NativeGateBase):
    """R-6: `devtools/task_gate_qual.py` resumes a bounded observation slice instead of failing the scenario.

    Class: a `SliceEnded` from the production entry point is a normal observation step. Checked domain: a scripted
    `[SliceEnded(), terminal record]` and the control `[terminal record]`, both through `run_scenario` with its
    workspace, terminate and engine patched out (no binary, no network). Oracle: the number of calls into
    `Delivery.run_task_gate`, the mock's own count. Interpretation: the scenario deadline stays the caller's
    `timeout` and the loop is the script's only change -- its scenario tables, provider and checker are untouched."""

    def qualify(self, side_effect):
        from devtools import task_gate_qual as qual
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal()])
        with patch.object(qual.dq, "setup_work", return_value=(self.project, {**os.environ}, Mock())), \
                patch.object(qual.dq, "terminate"), \
                patch.object(qual, "NativeEngine", return_value=engine), \
                patch.object(qual.Delivery, "run_task_gate", side_effect=side_effect) as call:
            problems = qual.run_scenario("a_accept_r1", qual.SCENARIOS["a_accept_r1"], engine.executable,
                                         self.root, 100)
        return call.call_count, problems

    def terminal_record(self):
        return {"status": "concluded", "critic_verdict": "accepted", "rounds_used": 1,
                "terminal": {"status": "succeeded"}, "discussion": {"version": 1, "rounds": []}}

    def test_a_watch_slice_that_ends_is_resumed_until_the_record_is_terminal(self):
        count, problems = self.qualify([SliceEnded(), self.terminal_record()])
        self.assertEqual(count, 2)
        self.assertFalse([problem for problem in problems if "refusal" in problem])

    def test_a_terminal_record_takes_one_call(self):
        count, _ = self.qualify([self.terminal_record()])
        self.assertEqual(count, 1)
