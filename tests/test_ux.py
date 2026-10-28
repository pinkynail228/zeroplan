"""First-run UX journeys: the stale dead end, view-only navigation, planner progress and failure causes, plain
words in the normal flow, and the planner/verifier prompt contract. Fixture engine/driver and scripted native CLI."""

import copy
import io
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal_planner import setup
from terminal_planner.planning import Planning
from terminal_planner.authority import Authority as RealAuthority, canonical
from terminal_planner.cli import Terminal, plain, session
from terminal_planner.engine import (DRIVER_MECHANICS, MAX_MILESTONE_TASKS, MILESTONE_ISOLATION, SMALL_PLAN, STALE,
                                     FixtureEngine, fixture_proposal, planner_graph, planner_graph_v2)
from terminal_planner.runs import FixtureDriver
from test_setup import Steps
import test_terminal_planner as tp
from test_terminal_planner import ProjectTest, ROLES

GOAL = "Add a README paragraph"
SECRET = "sk-live-ux-secret-0123"
# Internal words the normal flow must not show (they stay under [i]).
FORBIDDEN = re.compile(r"fixture-native-run|digest|intent|receipt|acceptance role|native|fixture", re.IGNORECASE)


class Counting(FixtureEngine):
    """The fixture engine, counting every submission to the planner."""

    def __init__(self, sent):
        self.sent = sent

    def proposal(self, authority, progress, slice=None):
        self.sent.append(authority.current["version"])
        return super().proposal(authority, progress, slice)


class Recording(Terminal):
    """Remembers how many scripted native responses were still unread when each line was shown."""

    def __init__(self, steps, responses):
        super().__init__(Steps(*steps), io.StringIO())
        self.responses, self.seen = responses, []

    def show(self, value=""):
        self.seen.append((value, len(self.responses)))
        super().show(value)


class UxTest(ProjectTest):
    def setUp(self):
        super().setUp()
        xdg = patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"), "XDG_CONFIG_HOME": str(self.root / "config")})
        xdg.start()
        self.addCleanup(xdg.stop)

    def fixture(self, *steps, readiness=None, outcome="done"):
        """A fixture session; returns (output, revisions sent to the planner)."""
        sent = self.sent = []  # this session's submissions, also for steps checking them mid-session
        output = io.StringIO()
        driver = FixtureDriver(self.root / "fixture-runs", outcome, delay=0)
        session(Terminal(Steps(*steps), output), self.project, self.state, lambda *_: Counting(sent), fixture_id="test",
                driver_factory=lambda _: driver, worktrees=self.root / "worktrees", readiness=readiness)
        return output.getvalue(), sent

    def stored(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return copy.deepcopy(authority.state)


class StaleTests(UxTest):
    def detach(self):
        self.git("checkout", "-q", "--detach")

    def test_a3_blocked_then_fixed_and_n_prepares_r2_without_the_model(self):
        """D4a: the blocker is a detached HEAD (uncommitted changes no longer block anything)."""
        readiness = lambda: list(setup.check_target(self.project))
        output, sent = self.fixture("p", GOAL, "", self.detach, "g", "q", "q", "q", readiness=readiness)
        self.assertIn("! HEAD detached — [i] instructions", output)
        self.assertIn("Goal saved: plan r1 is not sent yet.", output)
        self.assertEqual(sent, [])
        r1 = self.stored()["revisions"][0]
        self.assertEqual((r1["goal"], r1["status"], r1["run_id"]), (GOAL, "planning", None))
        self.owner_commit()
        output, sent = self.fixture("p", "n", lambda: self.assertEqual(self.sent, []), "g", "q", "q",
                                   readiness=readiness)
        stale = output.index(STALE)
        self.assertIn("[g] start the planner  [n] prepare a new plan on the current project  [i] details  [q] back",
                      output[stale:])  # the dead end offers [g] as well as [n]
        self.assertNotIn("Unknown command", output)
        self.assertIn("Plan r2 prepared on the current project; same goal and settings. No model was run.", output)
        self.assertEqual(sent, [2])  # only the explicit [g] on r2 reached the planner
        revisions = self.stored()["revisions"]
        self.assertEqual(revisions[0], r1)  # r1 untouched
        self.assertEqual((revisions[1]["goal"], revisions[1]["roles"]), (r1["goal"], r1["roles"]))
        self.assertEqual(revisions[1]["status"], "proposed")

    def owner_commit(self):
        """The owner returns to the branch and commits: the project moves on."""
        self.git("checkout", "-q", "main")
        (self.project / "draft.txt").write_text("draft\n")
        self.git("add", "draft.txt")
        self.git("commit", "-qm", "owner commit")

    def blocked_goal(self, readiness):
        """r1: a goal saved by a readiness block (nothing sent), then the owner's own commit moves the project."""
        output, sent = self.fixture("p", GOAL, "", self.detach, "g", "q", "q", "q", readiness=readiness)
        self.assertEqual(sent, [])
        self.owner_commit()
        return self.stored()["revisions"][0]

    def test_c1_g_on_a_stale_unsent_goal_renews_and_sends_in_one_action(self):
        readiness = lambda: list(setup.check_target(self.project))
        r1 = self.blocked_goal(readiness)
        output, sent = self.fixture("p", "g", "q", "q", readiness=readiness)
        self.assertIn(STALE, output)
        self.assertIn("Plan r2 is built on the current project state (r1 → r2); the goal and settings are the same.", output)
        self.assertNotIn("Plan r2 prepared", output)  # one line, not the [n] announcement
        self.assertEqual(sent, [2])  # the planner ran once, on the new revision
        revisions = self.stored()["revisions"]
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0], r1)  # r1 stays unsent and untouched
        self.assertEqual((revisions[1]["goal"], revisions[1]["roles"]), (r1["goal"], r1["roles"]))
        self.assertEqual(revisions[1]["status"], "proposed")

    def test_c2_g_on_a_stale_unsent_goal_with_readiness_still_failing_sends_nothing(self):
        readiness = lambda: list(setup.check_target(self.project))
        r1 = self.blocked_goal(readiness)
        output, sent = self.fixture("p", self.detach, "g", "q", "q", "q", readiness=readiness)
        self.assertIn("Not started: fix what is marked above first.", output)
        self.assertNotIn("is built on the current project state", output)
        self.assertEqual(sent, [])
        self.assertEqual(self.stored()["revisions"], [r1])  # no revision was created


class ReadinessPerActionTests(UxTest):
    """Each model action passes only the checks it needs (planning.NEEDS)."""
    IDS = ("socket", "tools", "codex", "codex_home", "auth", "roles", "git", "identity", "repo", "branch", "origin", "clean")

    def blocked(self, authority, failing, action):
        """True when `action` is blocked while only the readiness item `failing` is not ok."""
        items = lambda: [setup.item(name, name != failing, name, name) for name in self.IDS]
        runs = type("Runs", (), {"engine": object()})()
        return not Planning(authority, runs, lambda *_: None, readiness=items).gate(action=action).ok

    def test_each_action_is_blocked_only_by_the_checks_it_needs(self):
        expected = {"plan": set(self.IDS) - {"identity", "clean"}, "start": set(self.IDS) - {"clean"},
                    "resume": set(self.IDS) - {"clean"}}  # D4a: the tree never blocks
        with RealAuthority(None, self.project) as authority:
            for failing in self.IDS:
                for action, needs in expected.items():
                    self.assertEqual(self.blocked(authority, failing, action), failing in needs, (failing, action))

    def test_the_fixture_engine_needs_no_tools_login_or_origin(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            for failing in ("socket", "tools", "codex", "codex_home", "auth", "roles", "origin"):
                for action in ("plan", "start", "resume"):
                    self.assertFalse(self.blocked(authority, failing, action), (failing, action))
            self.assertTrue(self.blocked(authority, "branch", "plan"))

    def test_a_fixture_plan_is_sent_without_origin_or_git_identity(self):
        items = lambda: [setup.item(name, name not in ("origin", "identity"), name, name, key="i") for name in
                         ("repo", "branch", "origin", "identity", "clean")]
        output, sent = self.fixture("", "p", GOAL, "", "g", "q", "q", readiness=items)  # Enter: past the home check
        self.assertEqual(sent, [1], output)
        self.assertNotIn("Not started", output)


class NavigationTests(UxTest):
    def test_a4_enter_p_and_q_only_view_an_unsubmitted_plan(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            authority.begin(GOAL, ROLES, "fixture")
        output, sent = self.fixture("", "", "p", "q", "q")
        self.assertEqual(output.count("Plan r1 has not been sent yet."), 2)
        self.assertIn("[g] start the planner  [i] details  [q] back", output)
        self.assertEqual(sent, [])
        self.assertEqual(self.stored()["revisions"][0]["status"], "planning")

    def test_a4_q_leaves_every_plan_menu_and_exits_from_home(self):
        output, sent = self.fixture("p", GOAL, "", "q", "p", GOAL, "", "g", "i", "q", "q")
        self.assertIn("The goal was not saved; no plan was created.", output)  # q on the roles menu
        self.assertEqual(sent, [1])
        self.assertTrue(output.rstrip().endswith("[q] quit\nChoice:"), output[-200:])


class NativeJourneys(UxTest):
    native = tp.NativeTests.native
    engine = tp.NativeTests.engine
    projection = tp.NativeTests.projection
    terminal = tp.NativeTests.terminal

    def running(self, node, cursor):
        return self.projection({"phase": "running", "activeExecutions": [{"node": node, "execution": "e-" + cursor}]}, cursor)

    @staticmethod
    def slice(*records):
        return subprocess.TimeoutExpired("watch", 15, output="".join(canonical(r) + "\n" for r in records).encode())

    def journey(self, engine, responses, *steps, login=None):
        terminal = Recording(steps, responses)
        clock = iter(range(0, 10 ** 6, 61)).__next__
        session(terminal, self.project, None, lambda *_: engine, login=login, clock=clock)
        output = terminal.output.getvalue()
        self.assertNotIn(SECRET, output)
        return output, terminal.seen

    def test_a5_phases_print_while_the_planner_runs_with_one_rare_heartbeat(self):
        responses = [{"valid": True}, {"runId": "fixture-native-run"},
                     self.slice(self.running("planner", "v2:1")), self.slice(self.running("planner", "v2:2")),
                     self.slice(), self.slice(self.running("plan_verifier", "v2:3")),
                     self.slice(self.running("planner", "v2:4")), (self.terminal(),), (self.terminal(),)]
        engine, calls = self.engine(responses)
        output, seen = self.journey(engine, responses, "p", GOAL, "", "g", "q", "q")
        lines = [value.strip() for value, _ in seen]
        phases = ["Starting the planner…", "Drafting the plan…", "…still working, 4 min elapsed",
                  "Checking that the plan covers the goal…", "Refining the plan from the findings…", "Plan checked."]
        self.assertEqual([line for line in lines if line in phases], phases)  # in order, each once
        pending = dict((value.strip(), left) for value, left in seen)
        for phase in phases[:5]:
            self.assertGreaterEqual(pending[phase], 2, phase)  # shown while the terminal record was still unread
        self.assertEqual(sum(all(a in args for a in ("watch", "--after")) for args, _ in calls), 5)
        self.assertIn("Plan r1 · 2 milestones · 2 tasks · checked", output)

    def fresh(self):
        with RealAuthority(None, self.project) as authority:
            directory = authority.directory
        shutil.rmtree(directory)

    def failure(self, log, stderr="", **actions):
        self.fresh()
        responses = [{"valid": True}, {"runId": "fixture-native-run"}, (self.terminal(failed=True),),
                     subprocess.CompletedProcess([], 1, log, stderr)]
        engine, calls = self.engine(responses)
        # Enter and q on the failure screen go back; Enter on home only reopens it; nothing is resubmitted.
        output, _ = self.journey(engine, responses, "p", GOAL, "", "g", "", "", "q", "q", **actions)
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[3][0][1:], ["logs", "fixture-native-run"])
        self.assertEqual(sum("--detach" in args for args, _ in calls), 1)
        self.assertEqual(output.count("Plan r1 · planning did not finish."), 2)
        return output

    def test_a5_failure_causes_name_the_next_step_without_secrets(self):
        output = self.failure("provider error: 401 Unauthorized; token %s expired\n" % SECRET, login=lambda: None)
        self.assertIn("Planning stopped: the service rejected the authorization.", output)
        self.assertIn("Next: [l] refresh login, then [g] check readiness.", output)
        self.assertIn("[l] refresh login  [g] check readiness and start again", output)
        self.assertNotIn("401", output)
        output = self.failure("", "429 Too Many Requests: usage limit reached for %s\n" % SECRET)
        self.assertIn("the service rejected the request because of a limit or quota", output)
        record = {"level": "error", "message": "provider: 429 rate limit exceeded for %s" % SECRET}
        output = self.failure(canonical(record) + "\n")
        self.assertIn("the service rejected the request because of a limit or quota", output)
        output = self.failure("worker exited with status 1 (%s)\n" % SECRET)
        self.assertIn("Planning stopped at the plan check step; the cause is unknown", output)
        self.assertIn("Next: [i] Zeroshot diagnostic commands, then [g] start again.", output)

    def test_model_text_about_authentication_is_not_a_provider_failure(self):
        """A goal about authentication / rate limiting: its words in the planner's own output never name the cause."""
        goal = "Add authentication and rate limiting (401 on a bad token) to the API"
        log = "\n".join([
            canonical({"type": "message", "role": "assistant", "text": "Plan: authentication, token refresh, 429 rate limit"}),
            "I will add authentication middleware; unauthorized requests get 401 and a rate limit applies.",
            canonical({"type": "tool_result", "output": "usage limit: not logged in handler present in auth.py"}),
            "worker exited with status 1"]) + "\n"
        self.fresh()
        responses = [{"valid": True}, {"runId": "fixture-native-run"}, (self.terminal(failed=True),),
                     subprocess.CompletedProcess([], 1, log, "")]
        engine, calls = self.engine(responses)
        output, _ = self.journey(engine, responses, "p", goal, "", "g", "q", "q")
        self.assertIn("the cause is unknown", output)
        self.assertNotIn("the service rejected the authorization", output)
        self.assertNotIn("limit or quota", output)

    def test_a_flat_structured_info_stderr_record_is_not_a_planner_cause(self):
        """R-1 on the planner journey: a flat structured non-error record on the CLI's stderr is model output.

        Domain: the planner failure screen when `zeroshot logs` writes a `{"level": "info"}` record (carrying 401
        words and a credential) to stderr; checked value: the rendered screen. Interpretation: the level filter
        covers flat structured records on both streams, so the screen keeps today's unknown-cause text, shows no
        credential and never renders the auth remedy.
        """
        record = canonical({"level": "info", "message": "Model example: 401 Unauthorized; token %s" % SECRET})
        output = self.failure("", stderr=record + "\n")
        self.assertIn("the cause is unknown", output)
        self.assertNotIn("the service rejected the authorization", output)
        self.assertNotIn("401", output)
        self.assertNotIn(SECRET, output)

    def test_a_truncated_structured_stderr_record_is_not_a_planner_cause(self):
        """R-1/A-3 on the planner journey: a malformed structured record on stderr is not a plain diagnostic.

        Domain: the planner failure screen when `zeroshot logs` writes a native info envelope whose closing braces
        are cut, to stderr, carrying 401 words and a credential; checked value: the rendered screen. Interpretation:
        a line that was meant to be a structured record but does not decode is dropped whole, so the screen keeps
        today's unknown-cause text, shows no credential and renders no auth remedy. On the base revision the
        fragment is read as a plain stderr diagnostic (auth), so this case fails at its first assertion there (A-6).
        """
        record = canonical({"cursor": "v2:1", "record": {"level": "info", "target": "zeroshot",
                                                         "message": "Model example: 401 Unauthorized; token %s" % SECRET}})
        output = self.failure("", stderr=record[:-2] + "\n")
        self.assertIn("the cause is unknown", output)
        self.assertNotIn("the service rejected the authorization", output)
        self.assertNotIn("401", output)
        self.assertNotIn(SECRET, output)

    def test_a_provider_limit_renders_the_planner_quota_wording(self):
        """R-2/A-6 through the whole planner journey: the shared `limit` class renders as the planner's own `quota`.

        Domain: the planner failure screen -- `Planning.failure`, reached through the real CLI journey -- over a
        native error envelope carrying the session-limit excerpt, a class the base revision does not know; checked
        values: the rendered wording, the catalog family tag and the plain-text action clue. Interpretation:
        `Planning.failure` normalizes the shared class before its own branch, keeps its own families and wording and
        never renders the reset or the raw diagnostic, so the screen shows the quota remedy instead of
        `planner.unknown`; the base revision classifies the same text as nothing, so this case fails at its first
        assertion there (A-6).
        """
        envelope = canonical({"cursor": "v2:204", "execution": "nv2-1",
                              "record": {"level": "error", "target": "zeroshot",
                                         "message": "Node code failed: crash after 55.0s: node execution failed: "
                                                    "Claude provider failure: You've hit your session limit · "
                                                    "resets 3:10am (Europe/Moscow); token %s" % SECRET}})
        output = self.failure(envelope + "\n")
        self.assertIn("Planning stopped: the service rejected the request because of a limit or quota.", output)
        self.assertIn("[code: planner.quota]", output)
        self.assertNotIn("the cause is unknown", output)
        self.assertNotIn("3:10am", output)  # the planner screen keeps its wording: no reset, no raw diagnostic
        self.assertNotIn(SECRET, output)

    def prepared_unsent(self, engine, responses):
        """r1: prepared for `engine` but never sent (admission refused it), so its binding is on the record."""
        self.fresh()
        self.journey(engine, responses, "p", GOAL, "", "g", "q", "q")
        revision = self.stored_native()["revisions"][0]
        self.assertEqual((revision["status"], revision["run_id"], revision["native_prepared"]), ("planning", None, True))
        return revision

    def stored_native(self):
        with RealAuthority(None, self.project) as authority:
            return copy.deepcopy(authority.state)

    def test_unsent_revision_for_another_zeroshot_binding_is_stale_and_names_why(self):
        responses = [{"valid": False}]
        engine, calls = self.engine(responses)
        r1 = self.prepared_unsent(engine, responses)
        engine.state_root = Path("/short")  # another state directory (or toolchain, or a rebuilt binary)
        output, _ = self.journey(engine, responses, "p", "n", "q", "q")
        self.assertIn("made for another Zeroshot version or state", output)
        self.assertNotIn("The project changed after it was created", output)
        self.assertIn("[n] prepare a new plan on the current project", output)
        self.assertIn("Plan r2 prepared on the current project; same goal and settings. No model was run.", output)
        self.assertEqual(len(calls), 1)  # nothing reached Zeroshot after the admission check of r1
        revisions = self.stored_native()["revisions"]
        self.assertEqual(revisions[0], r1)
        self.assertEqual((revisions[1]["goal"], revisions[1]["native_binding"]), (GOAL, None))

    def test_a3_known_receipt_reattaches_and_unknown_submission_is_resent_only_by_g(self):
        responses = [{"valid": True}, {"runId": "fixture-native-run"}, OSError("disconnected"), (self.terminal(),)]
        engine, calls = self.engine(responses)
        output, _ = self.journey(engine, responses, "p", GOAL, "", "g", "q", "q")
        self.assertIn("Plan r1 · the planner is working.", output)
        output, _ = self.journey(engine, responses, "p", "w", "q", "q")
        self.assertIn("Plan r1 · 2 milestones · 2 tasks · checked", output)
        self.assertEqual(sum("--detach" in args for args, _ in calls), 1)
        self.assertEqual(sum("--validate-only" in args for args, _ in calls), 1)

        self.fresh()
        responses[:] = [{"valid": True}, OSError("lost"), {"valid": True}, {"runId": "fixture-native-run"}, (self.terminal(),)]
        engine, calls = self.engine(responses)
        output, _ = self.journey(engine, responses, "p", GOAL, "", "g", "i", "g", "q", "q")
        # D5/E4: nothing resends by itself (the unconfirmed screen and [i] cost no call); [g] sends the same
        # frozen documents once more under the same submission key, and the plan proceeds.
        self.assertGreaterEqual(output.count("the planner submission is unconfirmed"), 2)
        self.assertRegex(output, r"ZEROSHOT_STATE_DIR=\S+ ZEROSHOT_CONFIG_DIR=\S+ \S+ list")
        self.assertIn("Plan r1 · 2 milestones · 2 tasks · checked", output)
        sent = [args for args, _ in calls if "--detach" in args]
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], sent[1])


    def test_a6_no_internal_words_in_the_normal_flow(self):
        responses = [{"valid": True}, {"runId": "fixture-native-run"}, self.slice(self.running("planner", "v2:1")),
                     (self.terminal(),), (self.terminal(),)]
        engine, _ = self.engine(responses)
        flows = {"native plan": self.journey(engine, responses, "p", GOAL, "", "g", "a", "q")[0]}
        shutil.rmtree(self.state, ignore_errors=True)
        flows["milestone"], _ = self.fixture("p", GOAL, "", "g", "a", "g", "y", "m", "y", "q")
        shutil.rmtree(self.state)
        flows["blocked"], _ = self.fixture("p", GOAL, "", "g", "a", "g", "y", "q", "q", outcome="blocked")
        self.assertIn("Reason: «", flows["blocked"])
        for name, text in flows.items():
            with self.subTest(name):
                # Fixture data stands in for model text (scripted driver notes, demo file): not UI words.
                text = re.sub(r"Fixture(?: driver)?: [^\n»]*|ZPLAN_FIXTURE\.md", "", text)
                found = FORBIDDEN.search(text)
                self.assertIsNone(found, found and text[max(0, found.start() - 80):found.end() + 40])


class PlainTextTests(unittest.TestCase):
    def test_f10_blocked_reason_hides_internal_tokens(self):
        self.assertEqual(plain("Needs the export path; acceptanceVerdict=rejected; 4 open; manifest: T1 open"),
                         "Needs the export path")
        self.assertEqual(plain("Use the default."), "Use the default.")


class PromptTests(unittest.TestCase):
    run_graph = tp.GraphTests.run_graph

    def prompts(self):
        graph = planner_graph()
        found = {}

        def walk(node):
            if isinstance(node, dict):
                if node.get("name") in ("planner", "plan_verifier") and "instructions" in node:
                    found[node["name"]] = node["instructions"]
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(graph)
        return found["planner"], found["plan_verifier"]

    def test_a7_both_prompts_exclude_driver_mechanics_and_keep_plans_small(self):
        planner, verifier = self.prompts()
        for prompt in (planner, verifier):
            self.assertIn(DRIVER_MECHANICS, prompt)
            self.assertIn(SMALL_PLAN, prompt)
            self.assertIn("a README paragraph -> 1 milestone, 1 task, 1-2 checks", prompt)
            self.assertIn("unless the goal explicitly asks for them", prompt)
            self.assertIn("in the repository as it is", prompt)
        self.assertIn("at most %s tasks per milestone" % MAX_MILESTONE_TASKS, planner)
        self.assertIn("more than %s tasks across its slices" % MAX_MILESTONE_TASKS, verifier)
        self.assertIn("Reject any task or check about those mechanics", verifier)
        self.assertIn("Reject any check that cannot be verified", verifier)
        self.assertNotIn("Include independent acceptance/code review", planner)

    def test_rc1_planner_and_verifier_prompts_isolate_the_milestone_from_main(self):
        """C1/C2: both graphs (v1 and v2) carry the one isolation constant in the planner and verifier prompts; the
        verifier also rejects a check that reads main and never rejects a plan for lacking a merge to main."""
        for graph in (planner_graph(), planner_graph_v2(3)):
            found = {}

            def walk(node):
                if isinstance(node, dict):
                    if node.get("name") in ("planner", "plan_verifier", "critic") and "instructions" in node:
                        found[node["name"]] = node["instructions"]
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for value in node:
                        walk(value)
            walk(graph)
            planner = found["planner"]
            verifier = found.get("plan_verifier") or found["critic"]
            self.assertIn(MILESTONE_ISOLATION, planner)
            self.assertIn(MILESTONE_ISOLATION, verifier)
            self.assertIn("never reject a plan for lacking a merge to main", verifier)
            for read in ("`git diff main`", "`git show main:`", "`git log main`"):
                self.assertIn(read, verifier)
        self.assertIn("address planFindings against the previous proposal", planner)

    def test_a7_rejected_mechanics_plan_goes_back_to_the_planner_with_findings(self):
        mechanics = fixture_proposal()  # M2 "Acceptance and code review": driver mechanics
        product = copy.deepcopy(mechanics)
        del product["milestones"][1]
        product["requirements"] = product["requirements"][:1]
        findings = "Reject: T2 plans the driver's acceptance and code review; remove mechanics tasks."
        result, calls = self.run_graph([(mechanics, "rejected", findings), (product, "accepted", "Product only.")])
        self.assertEqual([name for name, _ in calls], ["planner", "plan_verifier", "planner", "plan_verifier"])
        self.assertEqual(calls[2][1]["planFindings"], findings)
        self.assertEqual(calls[2][1]["proposal"], canonical(mechanics))
        self.assertEqual(result["output"]["proposal"], canonical(product))
        self.assertEqual(result["output"]["planVerdict"], "accepted")


if __name__ == "__main__":
    unittest.main()
