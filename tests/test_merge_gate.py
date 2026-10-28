"""The merge gate (A7a) and its merge critic (A7b2): a pinned candidate commit, the project checks on exactly that
commit, the critic's `go` (A7b2), then a fast-forward.

Every test runs a real fixture project through `Delivery.merge` (the production path of `[m]`): one smoke test per
criterion, plus the invariants the gate can break (the destination moving or the profile changing while the checks
run, the tree and the store after a refusal).

Interpretations (none of them waives a stated requirement):
- The risk is read from `git diff --name-only --no-renames -z <head> <candidate tree>` - the same paths as the diff
  against the candidate itself, known before the commit exists; it is stored in the gate record and the candidate's
  message does not carry it (H4: no `Risk-Tier:` line). `--no-renames` lists a rename's old path too, so a moved secret file still counts.
- The message says `Checks: <digest> passed` when the commit is written, before the checks run; the commit only lands
  if they passed.
- A checkout refusal (no evidence exists) saves no gate record; any run that produced evidence, passed or failed,
  saves it before the verdict.
- The empty-checks refusal comes after the conflict test (the spec's order: candidate first, then checks)."""

import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch

from terminal_planner import checks, delivery, engine, merge_critic, runs
from terminal_planner.authority import Blocked, digest
from terminal_planner.engine import FixtureEngine, ObservationDetached, SliceEnded, merge_critic_runtime
import test_process as tpr
import test_terminal_planner as tp

CHECKS = [{"name": "unit", "argv": ["true"], "timeout_s": 60}]
# A brief whose write_set is the fixture's one changed file, so a briefed milestone still changes the candidate.
BRIEF = {"goal": "Ship the smallest path.", "why": "Exercise the critic input.", "reuse": "Nothing.",
         "write_set": ["ZPLAN_FIXTURE.md"], "criteria": [{"id": "C1", "text": "The file changes.", "example": "Run it."}],
         "non_goals": [], "risk": "low", "dod": "The check passes."}


class CriticEngine(FixtureEngine):
    """A fixture engine whose merge critic is scripted: each `critic_run` consumes one step.

    A step is a dict of `FixtureEngine` options -- a scripted verdict or a native failure -- or one of the strings
    `"pending"` (the run is submitted, then the slice ends), `"unknown"` (the submission was never confirmed) and
    `"crash"` (the process died after the record was appended, before any dispatch). `hook` runs before the step,
    and `slices`, `documents` and `dispatches` record what the wiring handed the critic."""

    def __init__(self, steps, hook=None):
        super().__init__()
        self.steps = list(steps)
        self.hook = hook
        self.slices = []
        self.documents = []
        self.dispatches = 0

    def critic_run(self, authority, record, documents, progress, slice=None):
        self.slices.append(slice)
        self.documents.append(documents)
        if self.hook is not None:
            self.hook()
        step = self.steps.pop(0)
        if step == "pending":
            self.dispatches += 1
            run_id = "fixture-" + record["submission_key"]
            record.update(run_id=run_id, receipt={"runId": run_id}, status="detached")
            authority.save()
            raise SliceEnded()
        if step == "unknown":
            record.update(status="submission_unknown")   # saved before the dispatch, exactly as `critic_run` does
            authority.save()
            raise Blocked("The merge check submission is unconfirmed; resubmission is refused.",
                          family="submission.unknown")
        if step == "crash":
            raise ObservationDetached()
        if record["run_id"] is None:
            self.dispatches += 1
        return FixtureEngine(**step).critic_run(authority, record, documents, progress, slice)


class MergeGateTests(tpr.ProfileTest):
    def gated(self, argv=("true",), **more):
        self.awaiting_merge()
        self.write({"gates": {"merge": "required"},
                    "checks": [{"name": "unit", "argv": list(argv), "timeout_s": 60}], **more})

    def owner_commit(self, name="other.txt", text="owner\n"):
        (self.project / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-qm", "owner " + name)
        return self.head()

    def merge(self):
        with self.app() as app:
            return app.delivery.merge(app.delivery.latest("M1"))

    def parents(self, commit):
        return self.git("rev-list", "--parents", "-n", "1", commit).decode().split()[1:]

    def test_c1_an_unfinished_merge_refuses_every_merge_and_writes_nothing(self):
        self.awaiting_merge()
        head, state = self.head(), self.stored()
        (self.project / ".git" / "MERGE_HEAD").write_text(head + "\n")
        for _ in range(2):  # the profile gate is off here: the refusal does not depend on it
            result = self.merge()
            self.assertEqual(result.kind, "refused")
            self.assertIn("git merge --abort", result.line)
            self.assertIn("milestone.merge_refused", result.line)
        self.assertEqual((self.head(), self.stored()), (head, state))

    def test_c2_c3_c4_a_disjoint_change_gives_a_tested_candidate_that_is_fast_forwarded(self):
        self.gated()
        head = self.owner_commit()
        result_commit = self.stored()["runs"][0]["result"]["commit"]
        self.assertEqual(self.merge().kind, "integrated")
        stored = self.stored()["runs"][0]
        candidate, gate = self.head(), stored["gate"]
        self.assertEqual(self.parents(candidate), [head, result_commit])
        self.assertEqual((stored["delivery"], stored["integration"]["commit"]), ("integrated", candidate))
        message = self.git("log", "-1", "--format=%B", candidate).decode()
        self.assertNotIn("Risk-Tier", message)  # H4: the risk lives in the gate record, not in the commit
        self.assertEqual(gate["risk"]["tier"], "high")  # a /1 profile has no risk rules: the highest tier
        self.assertIn("Checks: %s passed" % digest(CHECKS), message)
        self.assertEqual(gate["candidate"], candidate)
        self.assertEqual((gate["head"], gate["result"], gate["destination"]), (head, result_commit, "refs/heads/main"))
        self.assertEqual(gate["tree"], self.git("rev-parse", candidate + "^{tree}").decode().strip())
        self.assertEqual((gate["checks"], gate["evidence"]["outcome"], gate["evidence"]["commit"]),
                         (CHECKS, "passed", candidate))
        self.assertEqual(gate["config_digest"], self.peek().status().resolved.digest)
        self.assertEqual(self.git("status", "--porcelain"), b"")

    def test_c3_a_failed_check_refuses_keeps_the_gate_and_moves_nothing(self):
        self.gated(argv=("false",))
        head = self.owner_commit()
        result = self.merge()
        self.assertEqual(result.kind, "refused")
        self.assertIn("unit", result.line)
        self.assertIn("merge.checks_failed", result.line)
        stored = self.stored()["runs"][0]
        self.assertEqual((self.head(), stored["delivery"], stored["integration"]), (head, "awaiting_merge", None))
        self.assertEqual((stored["gate"]["evidence"]["outcome"], stored["gate"]["head"]), ("failed", head))
        self.assertEqual(self.git("status", "--porcelain"), b"")
        runs.validate_gate(stored)
        other = self.git("rev-parse", "HEAD^{tree}").decode().strip()

        def corrupt(edit):
            broken = json.loads(json.dumps(stored))  # the store validates what it keeps
            edit(broken["gate"])
            return broken

        cases = {"no sha": lambda g: g.update(candidate="not-a-sha"),
                 "other tree": lambda g: g["evidence"].update(tree=other),
                 "other checks": lambda g: g["evidence"].update(checks_digest=digest([])),
                 "no results": lambda g: g["evidence"].update(checks=[]),
                 "empty check": lambda g: g.update(checks=[{}]),
                 "outcome": lambda g: g["evidence"].update(outcome="passed")}
        for name, edit in cases.items():
            with self.subTest(name), self.assertRaises(Blocked):
                runs.validate_gate(corrupt(edit))

    def test_c2_a_conflicting_candidate_is_recorded_and_the_tree_is_untouched(self):
        self.gated()
        head = self.owner_commit("ZPLAN_FIXTURE.md", "owner version\n")
        with patch.object(checks, "qualify", side_effect=AssertionError("no checks on a conflict")):
            self.assertEqual(self.merge().kind, "open")
        stored = self.stored()["runs"][0]
        self.assertEqual((stored["delivery"], stored["integration"]["conflicts"], stored["integration"]["aborted"]),
                         ("conflict", ["ZPLAN_FIXTURE.md"], True))
        self.assertEqual((self.head(), self.git("status", "--porcelain")), (head, b""))
        self.assertFalse((self.project / ".git" / "MERGE_HEAD").exists())

    def test_c4_head_moving_during_the_checks_refuses_and_merges_nothing(self):
        self.gated()
        self.owner_commit()
        real, moved = checks.qualify, []

        def qualify(*args):
            found = real(*args)
            moved.append(self.owner_commit("later.txt"))
            return found

        with patch.object(checks, "qualify", qualify):
            result = self.merge()
        self.assertEqual(result.kind, "refused")
        self.assertIn("repeat it", result.line)
        stored = self.stored()["runs"][0]
        self.assertEqual((self.head(), stored["delivery"]), (moved[0], "awaiting_merge"))
        self.assertEqual((stored["gate"]["evidence"]["outcome"], stored["gate"]["candidate"] == self.head()),
                         ("passed", False))

    def test_c4_a_profile_edited_during_the_checks_refuses_and_merges_nothing(self):
        self.gated()
        head = self.head()
        real = checks.qualify

        def qualify(*args):
            found = real(*args)
            self.write({"gates": {"merge": "required"}, "checks": [{"name": "other", "argv": ["true"], "timeout_s": 60}]})
            return found

        with patch.object(checks, "qualify", qualify):
            self.assertEqual(self.merge().kind, "refused")
        self.assertEqual((self.head(), self.stored()["runs"][0]["delivery"]), (head, "awaiting_merge"))


class MergeCriticWiringTests(tpr.ProfileTest):
    """A7b2: a gated merge asks the merge critic and lands only on its `go`.

    Every test runs a real fixture project through `Delivery.merge` (the production path of the plain CLI's `[m]`
    and of the TUI's merge job): one smoke test per criterion, plus the invariants the wiring can break (a candidate
    landing without the critic's `go`, the store after a refusal, a legacy gate record, the bounded slice). The three
    families' catalog entries and REFERENCE.md rows are checked in `tests/test_reference.py`; their `Not done: …`
    rendering and the `awaiting_merge` left behind are checked by the refusal tests here.

    Interpretations (none of them waives a stated requirement):
    - The resolved critic role is `resolved.roles()["plan_verifier"]`: `roles()` exposes the profile's `critic`
      under that legacy name (`plan_verifier`), so `roles()["critic"]` is not a key; `delivery.critic_roles` reads it
      this way and the frozen `runtime` document's digest proves the role reached the documents.
    - The fixture plan carries no task briefs, so its critic input digest binds `briefs == []`; the briefed-plan test
      proves the milestone's frozen briefs are read from the revision's bootstrap manifest (`gate_manifest`) and
      bound into the identity.
    - The five-second `CRITIC_SLICE` shows up as the `slice` the Controller's own `Delivery.merge(r)` call hands to
      `critic_run`; the plain CLI passes `None` (`wait`) and the recorded slice replays exactly that."""

    def gated(self, argv=("true",), **more):
        self.awaiting_merge()
        self.write({"gates": {"merge": "required"},
                    "checks": [{"name": "unit", "argv": list(argv), "timeout_s": 60}], **more})

    def owner_commit(self, name="other.txt", text="owner\n"):
        (self.project / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-qm", "owner " + name)
        return self.head()

    def awaiting_merge_with_brief(self):
        """An M1 awaiting the merge whose approved revision freezes `BRIEF` on its first task."""
        self.accept_file()
        plan = engine.fixture_proposal()
        plan["milestones"][0]["slices"][0]["tasks"][0]["brief"] = copy.deepcopy(BRIEF)
        with tp.Authority(self.state, self.project) as authority:
            authority.begin("Requested feature", tp.ROLES, "fixture", draft=plan)
            FixtureEngine().proposal(authority, lambda _: None)
            authority.approve(1)
        with self.app() as app:
            app.delivery.start(app.delivery.preview("M1", app.roles), app.roles)
        with self.app() as app:
            self.assertIsNotNone(app.delivery.active_run())
            mark, step = None, None
            for _ in range(200):
                step = app.delivery.step(app.delivery.latest("M1"), mark)
                mark = step.mark
                if not step.active:
                    break
            self.assertFalse(step.active)
            app.delivery.end(app.delivery.latest("M1"))  # an accepted attempt is exported on arrival
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")

    @contextlib.contextmanager
    def critic_app(self, engine):
        """The plain App over a locked fixture authority with a scripted merge-critic engine factory."""
        with tpr.RealAuthority(self.state, self.project, fixture_id="test") as authority:
            driver = tpr.FixtureDriver(self.root / "fixture-runs", "done")
            terminal = tpr.ScriptedTerminal("", io.StringIO())
            yield tpr.cli.App(terminal, authority, lambda *_: engine, driver, authority.directory / "worktrees",
                              profile=tpr.Profile.of(authority))

    def merge(self, engine):
        with self.critic_app(engine) as app:
            return app.delivery.merge(app.delivery.latest("M1"))

    def record(self, index=0):
        return self.stored()["critics"][index]

    def changed_paths(self, gate):
        diff = self.git("diff", "--name-only", "--no-renames", "-z", gate["head"], gate["tree"]).decode()
        return [path for path in diff.split("\0") if path]

    def test_c1_c4_a_pending_critic_retries_the_same_candidate_and_lands(self):
        """C1 candidate reuse + C4 pending: one candidate, one qualification, one dispatch, one record."""
        self.gated()
        self.owner_commit()
        engine = CriticEngine(["pending", {}])
        real, calls = checks.qualify, []

        def qualify(*args):
            calls.append(args)
            return real(*args)

        with patch.object(checks, "qualify", qualify):
            first = self.merge(engine)
            candidate = self.stored()["runs"][0]["gate"]["candidate"]
            second = self.merge(engine)
        self.assertEqual(first.kind, "refused")
        self.assertTrue(first.line.startswith("Not done: "), first.line)
        self.assertIn("merge.critic_pending", first.line)
        self.assertEqual(second.kind, "integrated")
        self.assertEqual(len(calls), 1)                       # the checks never rerun for the reuse
        self.assertEqual(self.head(), candidate)              # exactly the one candidate landed
        stored = self.stored()
        self.assertEqual((stored["runs"][0]["delivery"], stored["runs"][0]["gate"]["candidate"]),
                         ("integrated", candidate))
        self.assertEqual(len(stored["critics"]), 1)           # one record, one dispatch
        self.assertEqual(engine.dispatches, 1)
        self.assertEqual(engine.slices, [delivery.CRITIC_SLICE, delivery.CRITIC_SLICE])
        self.assertIsNotNone(engine.documents[0])             # the fresh dispatch froze its three documents
        self.assertIsNone(engine.documents[1])                # the retry observed the same run, never resent it
        self.assertEqual(stored["runs"][0]["gate"]["critic"], self.record()["id"])
        self.assertEqual((self.record()["status"], self.record()["verdict"]), ("concluded", "go"))

    def test_c1_a_stored_gate_without_a_critic_still_loads_and_is_reused(self):
        """C1: an old store's gate record (no `critic` key) loads and its candidate is still reused."""
        self.gated()
        self.owner_commit()
        engine = CriticEngine(["pending", {}])
        with self.critic_app(engine) as app:
            self.assertEqual(app.delivery.merge(app.delivery.latest("M1")).kind, "refused")
        with tpr.RealAuthority(self.state, self.project, fixture_id="test") as authority:
            gate = authority.state["runs"][0]["gate"]
            gate.pop("critic")                                # the shape a store written before A7b2 has
            authority.save()
            runs.validate_gate(authority.state["runs"][0])
        with self.critic_app(engine) as app:                  # reopened: the legacy gate loads and is reused
            self.assertEqual(app.delivery.merge(app.delivery.latest("M1")).kind, "integrated")
        self.assertEqual((len(self.stored()["critics"]), engine.dispatches), (1, 1))

    def test_c2_the_identity_binds_the_pinned_gate_the_engine_and_the_role(self):
        """C2: the critic's identity is the pinned gate plus the milestone and its input; the fixture binding and the
        profile's critic role reach the record and its documents."""
        self.gated()
        self.owner_commit()
        engine = CriticEngine([{}])
        self.assertEqual(self.merge(engine).kind, "integrated")
        gate, record = self.stored()["runs"][0]["gate"], self.record()
        names, paths = merge_critic.reasons(gate["risk"], {}), self.changed_paths(gate)
        self.assertTrue(names)                                # `facts={}` raises every path-less trigger
        self.assertEqual(record["reasons"], names)
        self.assertEqual(record["identity"], {
            "milestone": "M1", "plan_revision": 1, "attempt": 1, "destination": "refs/heads/main",
            "base": gate["head"], "result": gate["result"], "candidate": gate["candidate"], "tree": gate["tree"],
            "config_digest": gate["config_digest"], "input_digest": merge_critic.input_digest(names, paths, []),
            "risk": gate["risk"]})
        self.assertEqual(record["identity"]["config_digest"], self.peek().status().resolved.digest)
        self.assertEqual(record["binding"], {"fixture_id": "test"})
        critic = self.peek().status().resolved.roles()["plan_verifier"]
        self.assertEqual(record["documents"]["runtime"], digest(merge_critic_runtime({"critic": critic})))

    def test_c2_no_raised_reason_lands_without_a_critic(self):
        """C2: no raised reason -> the candidate lands as before, with no critic record and `gate["critic"]` None."""
        self.gated()
        self.owner_commit()
        with patch.object(merge_critic, "reasons", return_value=[]):
            self.assertEqual(self.merge(CriticEngine([{}])).kind, "integrated")
        stored = self.stored()
        self.assertEqual(stored["runs"][0]["gate"]["critic"], None)
        self.assertNotIn("critics", stored)

    def test_c2_the_identity_binds_the_milestone_frozen_briefs(self):
        """C2: the input digest binds the milestone's frozen briefs, read from the approved revision's manifest."""
        self.awaiting_merge_with_brief()
        self.write({"gates": {"merge": "required"}, "checks": CHECKS})
        self.assertEqual(self.merge(CriticEngine([{}])).kind, "integrated")
        gate, record = self.stored()["runs"][0]["gate"], self.record()
        self.assertEqual(record["reasons"], merge_critic.reasons(gate["risk"], {}))
        self.assertEqual(record["identity"]["input_digest"],
                         merge_critic.input_digest(record["reasons"], self.changed_paths(gate), [BRIEF]))

    def test_c3_a_crash_after_the_append_rebuilds_the_documents_and_dispatches_once(self):
        """C3: a never-prepared record (no run yet) rebuilds the same documents and then dispatches once."""
        self.gated()
        self.owner_commit()
        engine = CriticEngine(["crash", {}])
        first = self.merge(engine)
        self.assertIn("merge.critic_pending", first.line)
        self.assertEqual((self.record()["status"], self.record()["run_id"]), ("preparing", None))
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")
        self.assertEqual(self.merge(engine).kind, "integrated")
        self.assertIsNotNone(engine.documents[1])             # the rebuild, not None: nothing was prepared
        self.assertEqual(engine.documents[0], engine.documents[1])
        self.assertEqual(engine.dispatches, 1)
        self.assertEqual(len(self.stored()["critics"]), 1)

    def test_c3_an_unconfirmed_submission_refuses_and_never_resends(self):
        """C3: `submission_unknown` refuses with today's family and the second merge never reaches the critic."""
        self.gated()
        head = self.owner_commit()
        engine = CriticEngine(["unknown", {}])
        first = self.merge(engine)
        self.assertIn("submission.unknown", first.line)
        self.assertEqual(self.record()["status"], "submission_unknown")
        second = self.merge(engine)
        self.assertIn("submission.unknown", second.line)
        self.assertEqual((self.head(), self.stored()["runs"][0]["delivery"]), (head, "awaiting_merge"))
        self.assertEqual((len(self.stored()["critics"]), len(engine.steps)), (1, 1))

    def test_c4_a_block_refuses_with_the_first_three_findings_and_lands_nothing(self):
        """C4: a `block` names the first three findings and neither lands nor changes the attempt."""
        self.gated()
        head = self.owner_commit()
        block = {"schemaVersion": "1", "verdict": "block", "findings": "first\nsecond\nthird\nfourth"}
        result = self.merge(CriticEngine([{"terminal_output": block}]))
        self.assertEqual(result.kind, "refused")
        self.assertIn("milestone.critic_blocked", result.line)
        self.assertIn("first; second; third", result.line)
        self.assertNotIn("fourth", result.line)
        stored = self.stored()
        self.assertEqual((self.head(), stored["runs"][0]["delivery"]), (head, "awaiting_merge"))
        self.assertEqual((self.record()["status"], self.record()["verdict"]), ("concluded", "block"))

    def test_c4_a_block_keeps_all_three_findings_when_the_first_is_long(self):
        """C4: the three findings survive the rendered line even when the first is a long multi-sentence one.

        `refusal` bounds the whole line at 256 characters (`summary`), so the excerpts must be budgeted inside that
        room; a per-finding 300-character bound alone would let the first finding push the other two past the cut."""
        self.gated()
        head = self.owner_commit()
        findings = ("The submission recovery path leaks the daemon token into the log; " * 4).strip() + \
            "\nSubmission recovery is incomplete\nDestination changed"
        block = {"schemaVersion": "1", "verdict": "block", "findings": findings}
        result = self.merge(CriticEngine([{"terminal_output": block}]))
        self.assertEqual(result.kind, "refused")
        self.assertIn("milestone.critic_blocked", result.line)
        self.assertIn("Submission recovery is incomplete", result.line)
        self.assertIn("Destination changed", result.line)
        stored = self.stored()
        self.assertEqual((self.head(), stored["runs"][0]["delivery"]), (head, "awaiting_merge"))
        self.assertEqual((self.record()["status"], self.record()["verdict"]), ("concluded", "block"))

    def test_c4_a_critic_without_a_verdict_refuses_and_the_next_merge_starts_a_new_record(self):
        """C4: a critic that ends without a verdict is `merge.critic_failed`; the next merge appends a new record."""
        self.gated()
        self.owner_commit()
        engine = CriticEngine([{"failure": "boom"}, {}])
        first = self.merge(engine)
        self.assertEqual(first.kind, "refused")
        self.assertIn("merge.critic_failed", first.line)
        self.assertEqual((self.record()["status"], self.record()["verdict"]), ("native_failed", None))
        self.assertEqual(self.merge(engine).kind, "integrated")
        stored = self.stored()
        self.assertEqual(len(stored["critics"]), 2)           # a new record, not a re-dispatch
        self.assertEqual(stored["runs"][0]["gate"]["critic"], stored["critics"][1]["id"])

    def test_c4_head_moving_during_the_critic_refuses(self):
        """C4: the unchanged check runs after the critic, so a HEAD that moved during it refuses the landing."""
        self.gated()
        self.owner_commit()
        moved = []
        result = self.merge(CriticEngine([{}], hook=lambda: moved.append(self.owner_commit("later.txt"))))
        self.assertEqual(result.kind, "refused")
        self.assertIn("milestone.merge_refused", result.line)
        stored = self.stored()
        self.assertEqual(self.head(), moved[0])
        self.assertEqual((stored["runs"][0]["delivery"], stored["runs"][0]["gate"]["evidence"]["outcome"]),
                         ("awaiting_merge", "passed"))
        self.assertEqual(self.record()["verdict"], "go")      # the critic allowed, the identity check refused

    def test_c4_the_landing_itself_refuses_without_the_critics_go(self):
        """C4: `gate_merge` lands a raised-reason candidate only on a stored `go` for its exact identity: no
        callback, a callback returning None, or a forged `go` that is not in the store lands nothing."""
        self.gated()
        self.owner_commit()
        before = self.head()
        forged = {"id": "critic-forged", "verdict": "go", "identity": {}}
        for critic in (None, lambda *_: None, lambda *_: forged):
            with self.critic_app(CriticEngine([{}])) as app:
                resolved = app.delivery.guard("merge").resolved
                with self.assertRaises(tp.Blocked) as caught:
                    app.delivery.runs.merge(app.delivery.latest("M1"), resolved, critic=critic)
            self.assertEqual(caught.exception.family, "merge.critic_failed")
            self.assertEqual((self.head(), self.stored()["runs"][0]["delivery"]), (before, "awaiting_merge"))

    def test_merge_refuses_a_profile_other_than_the_expected_one(self):
        """`Delivery.merge(r, expected=digest)` merges only under the profile the caller decided on: another digest
        is `process.changed` and lands nothing; the matching digest lands as usual."""
        self.gated()
        self.owner_commit()
        before = self.head()
        with self.critic_app(CriticEngine([{}])) as app:
            refused = app.delivery.merge(app.delivery.latest("M1"), expected="0" * 64)
            self.assertEqual(refused.kind, "refused")
            self.assertIn("process.changed", refused.line)
            self.assertEqual((self.head(), app.delivery.latest("M1")["delivery"]), (before, "awaiting_merge"))
            digest = app.delivery.guard("merge").digest
            self.assertEqual(app.delivery.merge(app.delivery.latest("M1"), expected=digest).kind, "integrated")

    def test_c4_the_plain_cli_waits_without_a_slice(self):
        """C4: the plain CLI's own `[m]` passes `slice=None` (wait) all the way into `critic_run`."""
        self.gated()
        self.owner_commit()
        slices, real = [], FixtureEngine.critic_run

        def spy(self_engine, authority, record, documents, progress, slice=None):
            slices.append(slice)
            return real(self_engine, authority, record, documents, progress, slice)

        with patch.object(FixtureEngine, "critic_run", spy):
            output = self.run_session("o\n" + tpr.MERGE + "q\n")
        self.assertEqual(slices, [None])
        self.assertIn("Merged: M1 → main.", output)
        self.assertEqual(self.stored()["runs"][0]["delivery"], "integrated")

if __name__ == "__main__":
    unittest.main()
