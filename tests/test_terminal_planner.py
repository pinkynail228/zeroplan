import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from terminal_planner.authority import Authority as RealAuthority, Blocked, baseline, discover, require_workspace_outside_state, validate_proposal, validate_projection, canonical, digest, decode
from terminal_planner.cli import Terminal, safe
from terminal_planner.delivery import plan_lines
from terminal_planner.engine import (FIXTURE_PARAPHRASE, FixtureEngine, NativeEngine, SliceEnded, Stale, fixture_draft,
                                     fixture_proposal, planner_graph, planner_runtime, planner_input)
from terminal_planner import toolchain


def Authority(root, project):
    return RealAuthority(root, project, fixture_id="test")


ROOT = Path(__file__).resolve().parents[1]
ROLES = {role: {"model": "test-model", "effort": "high"} for role in ("planner", "plan_verifier", "worker", "reviewer", "steward")}


class ProjectTest(unittest.TestCase):
    def setUp(self):
        # Let the qualification harness select a supported source filesystem.
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        # Explicit initial branch: expectations name `main` whatever the host's init.defaultBranch is.
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        (self.project / "source.txt").write_text("baseline\n")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "fixture")
        self.git("remote", "add", "origin", "https://github.com/example/fixture.git")
        self.state = self.root / "isolated-state"
        home = patch.dict(os.environ, {"HOME": str(self.root / "home"), "PYTHONDONTWRITEBYTECODE": "1"})
        home.start()
        self.addCleanup(home.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.project), *args], stderr=subprocess.DEVNULL)

    def begin(self, authority, engine="fixture", goal="Requested feature", draft=None):
        """A plan as the architect writes it: a Goldfish revision of `draft` (the fixture plan, `fixture_draft()`) at
        the owner's word."""
        authority.begin(goal, ROLES, engine, draft=draft or fixture_draft(), review="goldfish", origin="plan",
                        by="owner", response="")

    def begin_old_planner(self, authority, engine="fixture"):
        """A revision of the old planner graph: only for the tests of that planner, which leave with its writer."""
        authority.begin("Requested feature", ROLES, engine)

    def propose(self, authority):
        FixtureEngine().proposal(authority, lambda _: None)


class AuthorityTests(ProjectTest):
    def test_new_intents_reject_non_native_efforts(self):
        legacy = {role: dict(binding, effort="ultra" if role == "planner" else "high") for role, binding in ROLES.items()}
        with Authority(self.state, self.project) as authority:
            with self.assertRaisesRegex(Blocked, "planner effort ultra"):
                authority.begin("plan goal", legacy, "fixture")
            self.assertIsNone(authority.state)

    def test_v3_namespace_isolated_from_legacy_store(self):
        from terminal_planner import authority as module
        root = module.production_root()
        self.assertEqual(root.name, "v3")
        with RealAuthority(None, self.project) as probe:
            project_id = probe.project_id
        legacy = root.parent / project_id / "planning.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'{"schema": 3, "legacy": true}\n')
        before = legacy.read_bytes()
        with RealAuthority(None, self.project) as authority:
            self.assertIsNone(authority.state)
            authority.begin("Fresh goal", ROLES, "native")
            self.assertEqual(authority.path.parent, root / project_id)
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(authority.state["revisions"][0]["goal"], "Fresh goal")

    def test_unknown_schema_in_v3_store_is_refused(self):
        with Authority(self.state, self.project) as authority:
            self.begin(authority)
            path = authority.path
        data = json.loads(path.read_text())
        data["schema"] = 5
        path.write_text(json.dumps(data))
        raw = path.read_bytes()
        with self.assertRaisesRegex(Blocked, "Unknown planning.json schema"):
            with Authority(self.state, self.project):
                pass
        self.assertEqual(path.read_bytes(), raw)

    def test_old_role_file_loads_with_defaults(self):
        from terminal_planner import setup
        path = setup.config_root() / "roles.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        old = {role: {"model": "old-model", "effort": "high"} for role in ("planner", "worker", "acceptance", "code", "repair")}
        path.write_text(json.dumps(old))
        roles = setup.load_roles()
        self.assertEqual(set(roles), set(setup.ROLE_DEFAULTS))
        self.assertEqual(roles["planner"]["model"], "old-model")
        self.assertEqual(roles["worker"]["model"], "old-model")
        self.assertEqual(roles["plan_verifier"]["effort"], setup.ROLE_DEFAULTS["plan_verifier"])

    def test_nested_discovery_and_approval_preserve_target(self):
        child = self.project / "nested"
        child.mkdir()
        self.assertEqual(discover(child), self.project)
        before = baseline(self.project)
        with Authority(self.state, self.project) as authority:
            self.begin(authority)
            with self.assertRaises(Blocked):
                authority.approve(1)
            self.propose(authority)
            with self.assertRaises(Blocked):
                authority.approve(2)
            authority.approve(1)
            self.assertEqual(authority.current["status"], "approved")
            self.assertTrue(authority.current["approval"])
        self.assertEqual(baseline(self.project), before)

    def test_a_new_commit_invalidates_approval(self):
        for filename in ("source.txt", "new.txt"):
            with self.subTest(filename=filename):
                with Authority(self.state / filename, self.project) as authority:
                    self.begin(authority)
                    self.propose(authority)
                    (self.project / filename).write_text("changed")
                    self.git("add", filename)
                    self.git("commit", "-qm", "change " + filename)
                    with self.assertRaises(Blocked):
                        authority.approve(1)

    def test_revision_retains_history_and_requires_approval(self):
        with Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            first = copy.deepcopy(authority.current)
            authority.begin("Requested feature", ROLES, "fixture", "Different milestones")
            self.propose(authority)
            self.assertEqual(authority.state["revisions"][0], first)
            self.assertIsNone(authority.current["approval"])
            with self.assertRaises(Blocked):
                authority.approve(1)
        with Authority(self.state, self.project) as restored:
            self.assertEqual(restored.current["version"], 2)
            self.assertEqual(restored.current["status"], "proposed")

    def test_exclusive_session_and_lock_release(self):
        with Authority(self.state, self.project):
            with self.assertRaises(Blocked):
                with Authority(self.state, self.project):
                    self.fail("second owner admitted")
        with Authority(self.state, self.project):
            pass

    def test_invalid_coverage_and_dependency_cycle_rejected(self):
        mutations = [
            lambda p: p["milestones"][1].update(depends_on=["M2"]),
            lambda p: p["milestones"][1].update(depends_on=["missing"]),
            lambda p: p["milestones"][1]["slices"][0].update(requirements=["R1"]),
            lambda p: p["milestones"][0]["slices"][0]["tasks"][0].update(checks=[]),
            lambda p: p.update(completed=True),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                plan = fixture_proposal()
                mutate(plan)
                with self.assertRaises(Blocked):
                    validate_proposal(plan)


    def test_invalid_task_brief_rejected_with_proposal_family(self):
        """C1/C2: a valid brief is accepted; six criteria, an absolute or `..` path, a duplicate path, an unknown
        risk, a missing example and an extra key block with `plan.invalid_proposal`."""
        brief = {"goal": "g", "why": "w", "reuse": "", "write_set": ["a.py"],
                 "criteria": [{"id": "C1", "text": "t", "example": "e"}], "non_goals": [],
                 "risk": "low", "dod": "d"}
        mutations = [
            lambda b: b.update(criteria=[{"id": "C%d" % i, "text": "t", "example": "e"} for i in range(6)]),
            lambda b: b.update(write_set=["/etc/x"]),
            lambda b: b.update(write_set=["a/../../x"]),
            lambda b: b.update(write_set=["a.py", "./a.py"]),
            lambda b: b.update(risk="huge"),
            lambda b: b["criteria"][0].update(example=""),
            lambda b: b.update(extra=1),
        ]
        plan = fixture_proposal()
        plan["milestones"][0]["slices"][0]["tasks"][0]["brief"] = copy.deepcopy(brief)
        validate_proposal(plan)
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                plan = fixture_proposal()
                task = plan["milestones"][0]["slices"][0]["tasks"][0]
                task["brief"] = copy.deepcopy(brief)
                mutate(task["brief"])
                with self.assertRaises(Blocked) as caught:
                    validate_proposal(plan)
                self.assertEqual(caught.exception.family, "plan.invalid_proposal")


class ProductionAuthorityTests(ProjectTest):
    def test_same_path_git_directory_replacement_blocks_without_rewriting(self):
        import shutil
        with RealAuthority(None, self.project) as authority:
            self.begin(authority, "native")
            raw = authority.path.read_bytes()
            project_id = authority.project_id
            before = baseline(self.project)
            moved = self.root / "original-git"
            authority.common_dir.rename(moved)
            shutil.copytree(moved, authority.common_dir)
            self.assertEqual(baseline(self.project), before)
            with self.assertRaises(Blocked):
                authority.fresh()
            with self.assertRaises(Blocked):
                authority.save()
            self.assertEqual(authority.path.read_bytes(), raw)
        reopened = RealAuthority(None, self.project)
        self.assertEqual(reopened.project_id, project_id)
        self.assertEqual(reopened.path, authority.path)
        with self.assertRaises(Blocked):
            with reopened:
                pass
        self.assertIsNone(reopened.lock)
        self.assertEqual(reopened.path.read_bytes(), raw)

    def test_directory_identity_survives_git_updates_and_aliases(self):
        with RealAuthority(None, self.project) as authority:
            self.begin(authority, "native")
            identity = authority.state["common_identity"]
            raw = authority.path.read_bytes()
        self.git("config", "fixture.setting", "changed")
        self.git("branch", "normal-update")
        linked = self.root / "linked"
        self.git("worktree", "add", "-q", str(linked), "normal-update")
        alias = self.root / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        for path in (self.project, alias, linked):
            with RealAuthority(None, path) as reopened:
                self.assertEqual(reopened.state["common_identity"], identity)
                self.assertEqual(reopened.path.read_bytes(), raw)
                if path != linked:
                    self.assertTrue(reopened.fresh())

    def test_unqualified_schema_two_identity_is_not_silently_upgraded(self):
        authority = RealAuthority(None, self.project)
        state = authority.empty_state()
        del state["common_identity"]
        raw = canonical(state)
        authority.path.write_text(raw)
        with self.assertRaises(Blocked):
            with authority:
                pass
        self.assertEqual(authority.path.read_text(), raw)
        self.assertIsNone(authority.lock)

    def legacy(self):
        return {"schema": 1, "project": str(self.project), "revisions": [{
            "version": 1, "goal": "Old goal", "roles": copy.deepcopy(ROLES), "engine": "native",
            "baseline": baseline(self.project), "status": "approved", "proposal": fixture_proposal(), "approval": "old approval"}]}

    def test_malformed_load_unchanged_and_lock_released(self):
        authority = RealAuthority(None, self.project)
        bad = ['{', 'null', '[]', '{}', '{"schema":3}', '{"schema":1e309}']
        for key in ("engine", "status", "roles", "approval", "version", "proposal"):
            value = self.legacy()
            value["revisions"][0][key] = []
            bad.append(canonical(value))
        bad.append(canonical({**authority.empty_state(), "project_id": "wrong"}))
        bad.append(canonical({**authority.empty_state(), "revisions": {}}))
        with authority:
            self.begin(authority, "native")
            valid = copy.deepcopy(authority.state)
        for mutate in (lambda r: r.update(engine=[]), lambda r: r.update(status=[]),
                       lambda r: r.update(receipt=[]), lambda r: r.update(status="observing"),
                       lambda r: r.update(status="approved", approval="unearned"),
                       lambda r: r.update(native_prepared=True, native_documents=[]),
                       lambda r: r.update(observation_cursor=[]), lambda r: r.update(evidence=[])):
            value = copy.deepcopy(valid)
            mutate(value["revisions"][0])
            bad.append(canonical(value))
        duplicate = copy.deepcopy(valid)
        duplicate["revisions"].append(copy.deepcopy(duplicate["revisions"][0]))
        bad.append(canonical(duplicate))
        for raw in bad:
            with self.subTest(raw=raw[:90]):
                authority.path.write_text(raw)
                with self.assertRaises(Blocked):
                    with authority:
                        pass
                self.assertIsNone(authority.lock)
                self.assertEqual(authority.path.read_text(), raw)
                # Reacquire independently without loading, then restore valid state.
                import fcntl
                with (authority.directory / "session.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        authority.path.write_text(canonical(authority.empty_state()))
        with RealAuthority(None, self.project):
            pass

    def test_cross_process_symlink_worktree_lock_and_root_override(self):
        linked = self.root / "linked"
        self.git("worktree", "add", "-qb", "linked", str(linked))
        symlink = self.root / "alias"
        symlink.symlink_to(self.project, target_is_directory=True)
        code = ("import sys; from terminal_planner.authority import Authority,Blocked; "
                "a=Authority(None,sys.argv[1]); "
                "\ntry:\n with a: print(a.state['revisions'][-1]['goal'])\n"
                "except Blocked: sys.exit(7)\n")
        with RealAuthority(None, self.project) as authority:
            self.begin(authority, "native")
            for project in (symlink, linked):
                result = subprocess.run([sys.executable, "-B", "-c", code, str(project)], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(RealAuthority(None, project).path, authority.path)
            with self.assertRaises(Blocked):
                RealAuthority(self.root / "another-root", self.project)
        result = subprocess.run([sys.executable, "-B", "-c", code, str(symlink)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Requested feature")

    def test_fixture_root_isolation_and_native_submission_refusal(self):
        with RealAuthority(self.state, self.project, fixture_id="demo") as fixture:
            fixture.begin("Demo", ROLES, "fixture")
            FixtureEngine().proposal(fixture, lambda _: None)
            fixture.approve(1)
            with self.assertRaises(Blocked):
                NativeEngine("/unused", self.root / "native").proposal(fixture, lambda _: None)
            with self.assertRaises(Blocked):
                fixture.begin("Demo", ROLES, "native")
            with RealAuthority(None, self.project) as production:
                self.assertNotEqual(production.path, fixture.path)
                self.assertIsNone(production.state)
            # C2b acquires both locks even before a Task routing binding exists.
            with self.assertRaises(Blocked):
                with RealAuthority(self.root / "other", self.project, fixture_id="demo"):
                    self.fail("Second fixture owner crossed the project lock")
        with RealAuthority(self.root / "other", self.project, fixture_id="demo") as other:
            self.assertIsNone(other.state)


class NativeTests(ProjectTest):
    @property
    def native(self):
        # The controller socket path must stay under 104 bytes on macOS: a sibling of self.root is shorter than
        # self.root / "native". Keep it under TMPDIR, never in a shared parent, so concurrent copies do not churn
        # the ancestors that authority inspection re-stats.
        if not hasattr(self, "_native"):
            self._native = Path(tempfile.mkdtemp(prefix="z")).resolve()
            self.addCleanup(shutil.rmtree, self._native, ignore_errors=True)
        return self._native

    def test_long_socket_blocks_before_uncertain_submission_without_rebinding(self):
        engine, calls = self.engine([{"valid": True}])
        engine.state_root = Path("/home/testuser/.local/share/planning-kit/native")
        with patch("terminal_planner.engine.platform.system", return_value="Linux"), self.authority() as a:
            a.begin("plan goal", ROLES, "native")
            with self.assertRaisesRegex(Blocked, "socket path.*bytes"):
                engine.proposal(a, lambda _: None)
            self.assertNotEqual(a.current["status"], "submission_unknown")
            self.assertIsNone(a.current["run_id"])
            self.assertEqual(len(calls), 1)
            self.assertIn("--validate-only", calls[0][0])
            frozen = copy.deepcopy(a.current["native_binding"])
            engine.state_root = Path("/short")
            # Another binary/state binding for an unsubmitted revision: the dead end offers [n], never a rebind.
            with self.assertRaises(Stale):
                engine.prepare(a)
            self.assertEqual(a.current["native_binding"], frozen)

    def engine(self, responses, watch=None):
        """`watch(argv, kwargs)` (when given) answers every `watch` call; `responses` the rest, in order."""
        calls = []
        version = toolchain.current().zeroshot_version
        binary = self.root / "zeroshot-fixture"
        binary.write_text("#!/bin/sh\nprintf '%s\\n'\n" % version)
        binary.chmod(0o700)

        def call(argv, **kwargs):
            if argv[1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, version + "\n", "")
            calls.append((argv, kwargs))
            if watch is not None and argv[1] == "watch":
                return watch(argv, kwargs)
            result = responses.pop(0)
            if isinstance(result, BaseException):
                raise result
            if isinstance(result, subprocess.CompletedProcess):
                return result
            if isinstance(result, str):
                stdout = result
            elif isinstance(result, tuple):
                stdout = "".join(json.dumps(v) + "\n" for v in result)
            else:
                stdout = json.dumps(result) + "\n"
            return subprocess.CompletedProcess(argv, 0, stdout, "")

        return NativeEngine(binary, self.native, call=call, sleep=lambda _: None), calls

    def authority(self):
        return RealAuthority(None, self.project)

    def projection(self, status, cursor="v2:10"):
        return {"runId": "fixture-native-run", "subscriptionId": "fixture-subscription", "title": "Terminal roadmap revision 1",
                "source": {"repository": "example/fixture", "branch": self.git("branch", "--show-current").decode().strip(),
                           "revision": self.git("rev-parse", "HEAD").decode().strip()},
                "size": "medium", "cursor": cursor, "status": status}

    def terminal(self, verdict="accepted", proposal=None, findings="Final independent findings", failed=False,
                 execution=2, response="Proposed verdict: accepted.", discussion=None, goldfish=True):
        """The finished projection of a plan review: output schema "1" for a version 1 revision, "2" otherwise (its
        discussion is one final round unless given). A Goldfish review (`begin`'s revision) returns the draft with the
        reader's paraphrase; `goldfish=False` is the old planner's own review (`begin_old_planner`)."""
        goldfish = goldfish and execution == 2
        output = {"schemaVersion": "1", "proposal": canonical(proposal or (fixture_draft() if goldfish else fixture_proposal())),
                  "planVerdict": verdict, "planFindings": findings}
        if goldfish:
            output["paraphrase"] = FIXTURE_PARAPHRASE
        if execution == 2:
            rounds = discussion if discussion is not None else [
                {"round": 1, "verdict": verdict, "findings": findings, "response": response}]
            output.update(schemaVersion="2", planResponse=response,
                          discussion=canonical({"version": 1, "rounds": rounds}))
        terminal = {"status": "failed", "reason": "critic_failed"} if failed else {"status": "succeeded", "output": output}
        return self.projection({"phase": "finished", "terminalResult": terminal})

    def old_terminal(self, *args, **kwargs):
        """`terminal` of the old planner's own review: for the classes that test that planner and its line UI."""
        return NativeTests.terminal(self, *args, **dict(kwargs, goldfish=False))

    def running(self):
        return self.projection({"phase": "running", "activeExecutions": [{"node": "plan_verifier", "execution": "nv2-fixture"}]}, "v2:5")

    def source_envelope(self, source):
        return {"runId": "fixture-native-run", "subscriptionId": "fixture-subscription",
                "title": "Terminal roadmap revision 1", "source": source, "size": "medium", "cursor": "v2:1",
                "status": {"phase": "admitted"}}

    def git_in(self, repo, *args):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    def test_projection_source_remote_accepts_10_11_and_the_10_12_shapes(self):
        identity = {"repository": "example/fixture", "branch": "main", "revision": "0" * 40}
        accepted = [
            identity,  # a 10.11 envelope: no `remote` key at all
            {**identity, "remote": None},  # 10.12 explicit null
            {**identity, "remote": {"url": "https://github.com/example/fixture.git"}},  # minimal ResolvedGitRemote
            {**identity, "remote": {"url": "git@github.com:example/fixture.git", "connection": "ssh",
                                    "forge": {"provider": "github", "repository": "example/fixture"}}},  # full
            {**identity, "remote": {"url": "x", "connection": None, "forge": None}},  # optional keys present and null
        ]
        for source in accepted:
            with self.subTest(source=source):
                self.assertEqual(validate_projection(self.source_envelope(source), "fixture-native-run")["phase"], "admitted")

    def test_projection_source_remote_refuses_unknown_keys_wrong_types_and_missing_url(self):
        identity = {"repository": "example/fixture", "branch": "main", "revision": "0" * 40}
        refused = [
            {**identity, "extra": "x"},  # unknown key beside the three identities
            {**identity, "remote": {}},  # missing url
            {**identity, "remote": {"url": ""}},  # empty url
            {**identity, "remote": {"url": 1}},  # wrong url type
            {**identity, "remote": {"url": "x", "unknown": 1}},  # unknown key in remote
            {**identity, "remote": {"url": "x", "connection": 1}},  # wrong connection type
            {**identity, "remote": {"url": "x", "connection": ""}},  # empty connection
            {**identity, "remote": {"url": "x", "forge": {"provider": "github"}}},  # forge missing repository
            {**identity, "remote": {"url": "x", "forge": {"provider": "github", "repository": "r", "extra": 1}}},
            {**identity, "remote": {"url": "x", "forge": {"provider": "", "repository": "r"}}},
            {**identity, "remote": {"url": "x", "forge": 1}},
            {**identity, "remote": []},
        ]
        for source in refused:
            with self.subTest(source=source), self.assertRaises(Blocked):
                validate_projection(self.source_envelope(source), "fixture-native-run")

    def test_stored_10_11_envelopes_validate_unchanged_without_a_rewrite(self):
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal())])
        with self.authority() as authority:
            self.begin(authority, "native")
            engine.proposal(authority, lambda _: None)
            path = authority.path
        revision = decode(path.read_text())["revisions"][-1]
        for envelope in (revision["observation_envelope"], revision["terminal_envelope"]):
            self.assertEqual(set(envelope["source"]), {"repository", "branch", "revision"})  # the 10.11 shape
        raw = path.read_bytes()
        with self.authority():
            pass
        self.assertEqual(path.read_bytes(), raw)  # loading a 10.11 store never rewrites it

    def test_finished_envelope_accepts_the_10_16_failure_context_and_refuses_every_other_shape(self):
        """C1/C2 at the planning envelope: a failed terminal result may carry the optional 10.16 `context` -- absent,
        null or exactly the upstream `FailureContext` shape -- and any other context keeps the old
        `Incompatible planning state/envelope.` refusal.

        Interpretation where the schema is silent: `message` is a string of at most 16384 characters (the empty
        string and the boundary length pass) without control characters (`\\x00-\\x1f\\x7f-\\x9f`, the class this
        module already uses for a connection-requirement key); `recorded` is a list of at most five diagnostics, so
        a present null is refused; every key of the context is optional, so `{}` passes; `primary` and `execution`
        accept null; an `execution` pair is exactly `{execution, node}` with both nonempty (the `activeExecutions`
        item shape)."""
        def envelope(terminal):
            return self.projection({"phase": "finished", "terminalResult": terminal})

        accepted = [
            {"status": "failed", "reason": "node_failed"},  # a 10.12 result: no `context` at all
            {"status": "failed", "reason": "node_failed", "context": None},
            {"status": "failed", "reason": "node_failed", "context": {}},
            {"status": "failed", "reason": "node_failed", "context": {"incomplete": False, "primary": None}},
            {"status": "failed", "reason": "node_failed",
             "context": {"incomplete": False, "primary": {"message": "timeout after 1200s", "cursor": None},
                         "recorded": []}},
            {"status": "failed", "reason": "node_failed",
             "context": {"recorded": [{"message": "m" * 16384, "cursor": "v2:1",
                                       "execution": {"execution": "e", "node": "n"}}] * 5}},
            {"status": "failed", "reason": "node_failed", "context": {"primary": {"message": "", "execution": None}}},
        ]
        refused = [
            {"status": "failed", "reason": "node_failed", "context": "nope"},
            {"status": "failed", "reason": "node_failed", "context": {"extra": 1}},
            {"status": "failed", "reason": "node_failed", "context": {"incomplete": 1}},
            {"status": "failed", "reason": "node_failed", "context": {"incomplete": None}},
            {"status": "failed", "reason": "node_failed", "context": {"primary": {}}},
            {"status": "failed", "reason": "node_failed", "context": {"primary": {"message": "m", "extra": 1}}},
            {"status": "failed", "reason": "node_failed", "context": {"primary": {"message": "m", "cursor": 1}}},
            {"status": "failed", "reason": "node_failed",
             "context": {"primary": {"message": "m", "execution": {"node": "n"}}}},
            {"status": "failed", "reason": "node_failed",
             "context": {"primary": {"message": "m", "execution": {"execution": "", "node": "n"}}}},
            {"status": "failed", "reason": "node_failed", "context": {"primary": {"message": "line\nbreak"}}},
            {"status": "failed", "reason": "node_failed", "context": {"primary": {"message": "m" * 16385}}},
            {"status": "failed", "reason": "node_failed", "context": {"recorded": None}},
            {"status": "failed", "reason": "node_failed", "context": {"recorded": [{"message": "m"}] * 6}},
            {"status": "failed", "reason": "node_failed", "context": {"recorded": [{"cursor": None}]}},
            {"status": "failed", "reason": "node_failed", "output": None},  # an unknown key beside `context`
            {"status": "failed"},  # the failed terminal itself is unchanged
            {"status": "succeeded", "output": {}, "context": {}},  # a success never carries a context
        ]
        for index, terminal in enumerate(accepted):
            with self.subTest(accepted=index):
                self.assertEqual(validate_projection(envelope(terminal), "fixture-native-run")["phase"], "finished")
        for index, terminal in enumerate(refused):
            with self.subTest(refused=index), self.assertRaises(Blocked) as caught:
                validate_projection(envelope(terminal), "fixture-native-run")
            self.assertEqual(str(caught.exception), "Incompatible planning state/envelope.")

    def test_planner_clone_pins_its_branch_to_origin_and_leaves_the_user_checkout_alone(self):
        # The user's own branch tracks another remote/branch name and a second remote exists; the disposable planner
        # clone must still name origin on its own branch, and the user's config must stay untouched.
        self.git("remote", "add", "backup", "https://github.com/example/backup.git")
        self.git("config", "branch.main.remote", "backup")
        self.git("config", "branch.main.merge", "refs/heads/other")
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal())])
        with self.authority() as authority:
            self.begin(authority, "native")
            engine.proposal(authority, lambda _: None)
            checkout = authority.directory / "revision-1" / "checkout"
            self.assertEqual(self.git_in(checkout, "config", "--get", "branch.main.remote"), "origin")
            self.assertEqual(self.git_in(checkout, "config", "--get", "branch.main.merge"), "refs/heads/main")
        self.assertEqual(self.git_in(self.project, "config", "--get", "branch.main.remote"), "backup")
        self.assertEqual(self.git_in(self.project, "config", "--get", "branch.main.merge"), "refs/heads/other")

    def test_planner_clone_reuse_repins_a_stale_upstream_to_origin(self):
        # A preparation that was never submitted (crash, Ctrl-C, a closed session) is reused with the checkout
        # already on disk; its own branch config must be normalized again, not only when the clone is first made.
        self.git("remote", "add", "backup", "https://github.com/example/backup.git")
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal())])
        with self.authority() as authority:
            self.begin(authority, "native")
            _, checkout = engine.prepare(authority)
            self.assertEqual(self.git_in(checkout, "config", "--get", "branch.main.remote"), "origin")
            for key, value in (("branch.main.remote", "backup"), ("branch.main.merge", "refs/heads/other")):
                subprocess.run(["git", "-C", str(checkout), "config", key, value], check=True)
        with self.authority() as authority:
            engine.prepare(authority)  # reuse: the same frozen revision and an existing checkout
            self.assertEqual(self.git_in(checkout, "config", "--get", "branch.main.remote"), "origin")
            self.assertEqual(self.git_in(checkout, "config", "--get", "branch.main.merge"), "refs/heads/main")

    def test_planner_submission_refuses_a_checkout_overlapping_the_native_state(self):
        # XDG_DATA_HOME (or --native-state-dir) pointed inside the workspace: <native_state_root>/runs becomes the
        # submitted checkout, which 10.12 forbids. zplan refuses it before any native call with its own remedy.
        engine, calls = self.engine([{"valid": True}])
        with self.authority() as authority:
            self.begin(authority, "native")
            workspace = authority.directory / "revision-1" / "checkout"
            engine.state_root = workspace / "state"
            with self.assertRaisesRegex(Blocked, "overlaps native state"):
                engine.prepare(authority)
            self.assertEqual(calls, [])
            self.assertEqual(authority.current["native_binding"], None)

    def test_workspace_overlap_with_the_native_runs_dir_is_refused_but_a_sibling_is_allowed(self):
        # The 10.12 rule is exactly `<native_state_root>/runs`: a workspace under the native bundle but beside it
        # (its `checkouts/`) is fine, while equality and containment in either direction are refused.
        root = self.root / "native-state"
        self.assertEqual(require_workspace_outside_state(root / "checkouts" / "planner", root, family="engine.checkout"),
                         (root / "checkouts" / "planner").resolve())
        for workspace in (root / "runs", root / "runs" / "deep", root):
            with self.subTest(workspace=workspace), self.assertRaises(Blocked):
                require_workspace_outside_state(workspace, root, family="engine.checkout")

    def test_overlap_refusal_names_only_the_remedies_that_work(self):
        # zplan always overwrites ZEROSHOT_STATE_DIR with <native_state_root>/runs (NativeEngine.native_environment),
        # so naming the variable as a remedy changes nothing; only --native-state-dir outside the working trees, and
        # an XDG_DATA_HOME left out of the native state, actually move the runs dir that 10.12 compares against.
        root = self.root / "native-state"
        with self.assertRaisesRegex(Blocked, "overlaps native state") as caught:
            require_workspace_outside_state(root / "runs", root, family="engine.checkout")
        message = str(caught.exception)
        self.assertIn("--native-state-dir", message)
        self.assertNotIn("ZEROSHOT_STATE_DIR", message)

    def test_status_workspace_recovery_exact_public_contract(self):
        value = self.running()
        del value["subscriptionId"]
        value["atCursor"] = value.pop("cursor")
        valid = [{"recoverable": False}, {"recoverable": True},
                 {"recoverable": True, "connectionRequirements": {"codex/main": ["API_KEY", "_TOKEN"]},
                  "resumedFrom": "previous", "successorRunId": "next"},
                 {"recoverable": False, "connectionRequirements": {}, "resumedFrom": None, "successorRunId": None}]
        self.assertEqual(validate_projection(value, value["runId"], watch=False)["phase"], "running")
        for recovery in valid:
            with self.subTest(valid=recovery):
                validate_projection({**value, "workspaceRecovery": recovery}, value["runId"], watch=False)
        invalid = [None, [], "unknown", {}, {"recoverable": None}, {"recoverable": 1},
                   {"recoverable": "true"}, {"recoverable": True, "extra": 0},
                   {"recoverable": True, "connectionRequirements": None},
                   {"recoverable": True, "connectionRequirements": []},
                   {"recoverable": True, "resumedFrom": {}}, {"recoverable": True, "successorRunId": 1}]
        for connections in ({"": []}, {"bad\nkey": []}, {"é" * 65: []}, {"codex": "API_KEY"},
                            {"codex": [None]}, {"codex": ["1KEY"]}, {"codex": ["é"]}, {"codex": ["K" * 129]}):
            invalid.append({"recoverable": True, "connectionRequirements": connections})
        for recovery in invalid:
            with self.subTest(invalid=recovery), self.assertRaises(Blocked):
                validate_projection({**value, "workspaceRecovery": recovery}, value["runId"], watch=False)
        with self.assertRaises(Blocked):
            validate_projection({**self.running(), "workspaceRecovery": valid[0]}, value["runId"])

    def test_nonterminal_deadline_disconnect_and_reopen_preserve_projection(self):
        """Interpretation: `invoke` branches on the watch's end, not on the exit code's value, the (valid) phase or
        the output type once the end is a timeout, so `stopping` is left to the invalid-suffix test, exit code 2 to
        exit code 1 and the text timeout to the bytes timeout (the text output of the clean end and of the
        nonzero exit covers the text branch of the record loop)."""
        # Branches kept: a clean end, a timeout (bytes output) and a nonzero exit (text output), on a `running` one.
        projection = self.running()
        stdout = canonical(projection) + "\n"
        endings = [projection, subprocess.TimeoutExpired("watch", 120, output=stdout.encode()),
                   subprocess.CompletedProcess([], 1, stdout, "private diagnostic")]
        for ending in endings:
            with self.subTest(ending=type(ending).__name__):
                import shutil
                authority = self.authority()
                shutil.rmtree(authority.directory)
                engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, ending,
                                             OSError("disconnected"), (), (projection, self.terminal())])
                with self.authority() as authority:
                    self.begin(authority, "native")
                    with self.assertRaises(Blocked):
                        engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], "detached")
                    self.assertEqual(authority.current["observation_cursor"], projection["cursor"])
                    self.assertEqual(authority.current["observation_envelope"], projection)
                    saved = copy.deepcopy(authority.current)
                with self.authority() as authority:
                    with self.assertRaises(Blocked):
                        engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current, saved)
                with self.authority() as authority:
                    engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], "proposed")
                    self.assertEqual(authority.current["receipt"], saved["receipt"])
                    self.assertEqual(authority.current["intent"], saved["intent"])
                    self.assertEqual(authority.current["terminal_cursor"], "v2:10")
                self.assertEqual(sum("--detach" in args for args, _ in calls), 1)
                self.assertEqual(sum("--validate-only" in args for args, _ in calls), 1)
                self.assertEqual(calls[3][0][-2:], ["--after", projection["cursor"]])

    def test_disconnected_malformed_watch_blocks_and_terminal_still_concludes(self):
        for payload, expected in (("{broken\n", "observation_blocked"),
                                  (canonical({**self.running(), "runId": "wrong"}) + "\n", "observation_blocked"),
                                  (canonical(self.terminal()) + "\n", "proposed")):
            with self.subTest(expected=expected, payload=payload[:30]):
                import shutil
                authority = self.authority()
                shutil.rmtree(authority.directory)
                engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"},
                                         subprocess.TimeoutExpired("watch", 120, output=payload)])
                with self.authority() as authority:
                    self.begin(authority, "native")
                    if expected == "proposed":
                        engine.proposal(authority, lambda _: None)
                    else:
                        with self.assertRaises(Blocked):
                            engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], expected)

    def test_invalid_watch_suffix_preserves_each_valid_prefix_and_same_receipt(self):
        """Interpretation: the suffix fails inside `invoke`'s record loop whatever ends the watch, so the suffix
        kinds (a truncated or a complete invalid JSON line, invalid UTF-8) and the endings (timeout, nonzero exit,
        clean exit) are crossed once each, not as a product. The two-record `stopping` prefix also covers the
        single `running` record."""
        # Branches kept: JSON and UTF-8 suffix failures x timeout, nonzero and clean ends; one two-record prefix.
        import shutil
        running = self.running()
        stopping = copy.deepcopy(running)
        stopping["cursor"] = "v2:7"
        stopping["status"]["phase"] = "stopping"
        prefix = [running, stopping]
        for suffix, make_ending in (
                (b'{"status":', lambda payload: subprocess.TimeoutExpired("watch", 120, output=payload)),
                (b'{broken}\n', lambda payload: subprocess.CompletedProcess([], 2, payload, b"private diagnostic")),
                (b'{"title":"\xd0', lambda payload: subprocess.CompletedProcess([], 0, payload, b""))):
            payload = ("".join(canonical(p) + "\n" for p in prefix)).encode() + suffix
            ending = make_ending(payload)
            with self.subTest(suffix=suffix, ending=type(ending).__name__):
                shutil.rmtree(self.authority().directory, ignore_errors=True)
                engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, ending,
                                             self.terminal(), (*prefix, self.terminal())])
                with self.authority() as authority:
                    self.begin(authority, "native")
                    persisted = []
                    save = authority.save

                    def capture_save():
                        save()
                        saved = decode(authority.path.read_text())["revisions"][-1]
                        if saved["status"] == "observing" and saved["observation_envelope"]:
                            persisted.append(saved["observation_envelope"])

                    with patch.object(authority, "save", side_effect=capture_save):
                        with self.assertRaisesRegex(Blocked, "UTF-8" if b"\xd0" in suffix else "JSON"):
                            engine.proposal(authority, lambda _: None)
                    self.assertEqual(persisted, prefix)
                    self.assertEqual(authority.current["status"], "observation_blocked")
                    self.assertEqual(authority.current["observation_envelope"], prefix[-1])
                    self.assertEqual(authority.current["observation_cursor"], prefix[-1]["cursor"])
                    self.assertIsNone(authority.current["terminal_envelope"])
                    self.assertIsNone(authority.current["evidence"])
                    self.assertIsNone(authority.current["approval"])
                    with self.assertRaises(Blocked):
                        authority.approve(1)
                    saved = copy.deepcopy(authority.current)
                with self.authority() as authority:
                    self.assertEqual(authority.current, saved)
                    engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], "proposed")
                    for key in ("receipt", "run_id", "submission_key", "intent"):
                        self.assertEqual(authority.current[key], saved[key])
                    self.assertEqual(authority.current["terminal_envelope"], self.terminal())
                self.assertEqual(calls[3][0][-2:], ["--after", prefix[-1]["cursor"]])
                self.assertNotIn("--after", calls[4][0])
                self.assertFalse(calls[2][1]["text"])
                self.assertEqual(sum("--detach" in args for args, _ in calls), 1)
                self.assertEqual(sum("--validate-only" in args for args, _ in calls), 1)

    def test_invalid_first_watch_record_never_uses_later_terminal(self):
        import shutil
        for suffix in (b'{broken}\n', b'{"title":"\xd0\n',
                       (canonical({**self.running(), "runId": "wrong"}) + "\n").encode()):
            for timeout in (False, True):
                with self.subTest(suffix=suffix, timeout=timeout):
                    shutil.rmtree(self.authority().directory, ignore_errors=True)
                    payload = suffix + (canonical(self.terminal()) + "\n").encode()
                    ending = (subprocess.TimeoutExpired("watch", 120, output=payload) if timeout else
                              subprocess.CompletedProcess([], 2, payload, b""))
                    engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, ending])
                    with self.authority() as authority:
                        self.begin(authority, "native")
                        with self.assertRaises(Blocked):
                            engine.proposal(authority, lambda _: None)
                        self.assertEqual(authority.current["status"], "observation_blocked")
                        for key in ("observation_envelope", "observation_cursor", "terminal_envelope", "evidence", "approval"):
                            self.assertIsNone(authority.current[key])
                    self.assertEqual(len(calls), 3)

    def test_first_terminal_survives_invalid_suffix_and_restart_without_watch(self):
        """Interpretation: the first finished record concludes before the rest of the watch is read, so the suffix
        kind (JSON, UTF-8) and the ending (timeout, nonzero exit) never reach a branch of their own; they are
        paired with the four outcomes (each a branch of `commit_terminal`) instead of crossed with them."""
        # Branches kept: the four terminal outcomes (accepted, rejected, failed, invalid), each with one suffix/ending.
        import shutil
        for outcome, suffix, timeout in (("accepted", b'{broken}\n', False), ("rejected", b'{"title":"\xd0', True),
                                         ("failed", b'{broken}\n', True), ("invalid", b'{"title":"\xd0', False)):
            terminal = self.terminal("rejected" if outcome == "rejected" else "accepted", failed=outcome == "failed")
            if outcome == "invalid":
                terminal["status"]["terminalResult"]["output"]["planVerdict"] = "unknown"
            expected = {"accepted": "proposed", "rejected": "review_exhausted",
                        "failed": "run_failed", "invalid": "proposal_invalid"}[outcome]
            payload = (canonical(self.running()) + "\n" + canonical(terminal) + "\n").encode() + suffix
            with self.subTest(outcome=outcome, suffix=suffix, timeout=timeout):
                shutil.rmtree(self.authority().directory, ignore_errors=True)
                ending = (subprocess.TimeoutExpired("watch", 120, output=payload) if timeout else
                          subprocess.CompletedProcess([], 2, payload, b""))
                engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, ending])
                with self.authority() as authority:
                    self.begin(authority, "native")
                    if outcome in {"failed", "invalid"}:
                        with self.assertRaises(Blocked):
                            engine.proposal(authority, lambda _: None)
                    else:
                        engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], expected)
                    self.assertEqual(authority.current["terminal_envelope"], terminal)
                    saved = copy.deepcopy(authority.current)
                with self.authority() as authority:
                    if outcome in {"failed", "invalid"}:
                        with self.assertRaises(Blocked):
                            engine.proposal(authority, lambda _: None)
                    else:
                        engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current, saved)
                    if outcome != "accepted":
                        with self.assertRaises(Blocked):
                            authority.approve(1)
                self.assertEqual(len(calls), 3)

    def test_watch_subprocess_does_not_eagerly_decode_utf8(self):
        engine, _ = self.engine([])
        payload = (canonical(self.running()) + "\n").encode() + b'{"title":"\xd0'
        Path(engine.executable).write_text("#!%s\nimport sys\nsys.stdout.buffer.write(%r)\nsys.exit(2)\n" %
                                          (sys.executable, payload))
        engine.call = subprocess.run
        records = engine.invoke(self.project, "watch", "fixture-native-run")
        self.assertEqual(next(records), self.running())
        with self.assertRaisesRegex(Blocked, "UTF-8"):
            next(records)

    def execute(self, engine, old_planner=False):
        with self.authority() as authority:
            (self.begin_old_planner if old_planner else self.begin)(authority, "native")
            engine.proposal(authority, lambda _: None)
            return copy.deepcopy(authority.current)

    def test_public_submission_receipt_and_separate_checkout(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal(goldfish=False))])
        before = baseline(self.project)
        with self.authority() as authority:
            self.begin_old_planner(authority, "native")
            proposal = engine.proposal(authority, lambda _: None)
            self.assertEqual(proposal, authority.current["proposal"])
            self.assertEqual(authority.current["run_id"], "fixture-native-run")
            arguments, options = calls[1]
            self.assertIn("--detach", arguments)
            self.assertIn("--no-environment", arguments)
            self.assertIn(authority.current["submission_key"], arguments)
            self.assertNotEqual(options["cwd"], self.project)
            self.assertEqual(options["env"]["ZEROSHOT_STATE_DIR"], str(self.native / "runs"))
            runtime = json.loads((options["cwd"].parent / "runtime.json").read_text())
            self.assertEqual(runtime["nodes"]["planner"]["model"], "test-model")
            self.assertEqual(runtime["nodes"]["critic"]["sessionScope"], "node_instance")
            self.assertNotIn("plan_verifier", runtime["nodes"])
            authority.approve(1)
            self.assertEqual(authority.current["evidence"]["verdict"], "accepted")
        self.assertEqual(baseline(self.project), before)

    def test_uncertain_receipt_never_automatically_resubmits(self):
        engine, calls = self.engine([{"valid": True}, KeyboardInterrupt()])
        with self.authority() as authority:
            self.begin(authority, "native")
            key = authority.current["submission_key"]
            with self.assertRaises(KeyboardInterrupt):
                engine.proposal(authority, lambda _: None)
        with self.authority() as authority:
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda _: None)
            self.assertEqual(authority.current["submission_key"], key)
            self.assertEqual(authority.current["status"], "submission_unknown")
            with self.assertRaises(Blocked):
                self.begin(authority, "native")
        self.assertEqual(len(calls), 2)

    def test_continue_after_receipt_does_not_submit_again(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt(), self.terminal()])
        with self.authority() as authority:
            self.begin(authority, "native")
            with self.assertRaises(KeyboardInterrupt):
                engine.proposal(authority, lambda _: None)
        with self.authority() as authority:
            engine.proposal(authority, lambda _: None)
        self.assertEqual(calls[-1][0][1:], ["watch", "fixture-native-run"])
        self.assertEqual(sum("--detach" in args for args, _ in calls), 1)

    def test_failed_native_run_never_becomes_proposal_and_can_be_revised(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal(failed=True)])
        with self.authority() as authority:
            self.begin(authority, "native")
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda _: None)
            self.assertIsNone(authority.current["approval"])
            self.assertEqual(authority.current["status"], "run_failed")
            self.assertIsNone(authority.current["evidence"])
            self.assertEqual(authority.current["diagnostic"], "critic_failed")
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda _: None)
            self.assertEqual(len(calls), 3)
            authority.begin("Requested feature", ROLES, "native", "Repair the proposal")

    def revision_projection(self, version, status, cursor):
        value = self.projection(status, cursor)
        value["title"] = "Terminal roadmap revision %s" % version
        return value

    def test_revision_after_a_failed_one_still_amends_the_last_proposal(self):
        """r1 proposed, r2 asked for changes and failed, r3 is its retry: the planner of r3 gets r1's plan."""
        first = fixture_proposal()
        first["requirements"][0]["text"] = "Only the plan of r1."
        failed = self.revision_projection(
            2, {"phase": "finished", "terminalResult": {"status": "failed", "reason": "planner_failed"}}, "v2:9")
        engine, calls = self.engine([
            {"valid": True}, {"runId": "fixture-native-run"}, self.terminal(goldfish=False, proposal=first),
            {"valid": True}, {"runId": "fixture-native-run"}, failed, {"valid": True}])
        with self.authority() as authority:
            self.begin_old_planner(authority, "native")
            engine.proposal(authority, lambda _: None)
            authority.begin("Requested feature", ROLES, "native", feedback="Split the first milestone")
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda _: None)
            self.assertEqual(authority.current["status"], "run_failed")
            authority.begin("Requested feature", ROLES, "native", feedback=authority.current["feedback"])  # renew
            engine.prepare(authority)
            task = decode(decode((authority.directory / "revision-3" / "input.json").read_text())["task"])
            self.assertEqual(task["prior_proposal"], authority.state["revisions"][0]["proposal"])
            self.assertEqual(task["feedback"], "Split the first milestone")

    def running_at(self, n):
        return self.projection({"phase": "running", "activeExecutions": [{"node": "planner", "execution": "e%s" % n}]},
                               "v2:%s" % n)

    def test_replay_longer_than_a_slice_never_moves_the_cursor_back_and_reaches_the_proposal(self):
        """The planner finished while detached; replaying its history (one second per record) outlasts a slice."""
        history = [self.running_at(n) for n in range(1, 31)] + [self.terminal()]
        history[-1]["cursor"] = "v2:31"
        cursors = []

        def watch(argv, kwargs):
            start = 0
            if "--after" in argv:
                start = [r["cursor"] for r in history].index(argv[-1]) + 1
            fits = int(kwargs["timeout"])
            body = "".join(json.dumps(r) + "\n" for r in history[start:start + fits])
            if start + fits < len(history):
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=body.encode())
            return subprocess.CompletedProcess(argv, 0, body.encode(), b"")

        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}], watch=watch)
        with self.authority() as authority:
            save = authority.save

            def tracking():
                cursors.append(authority.current["observation_cursor"])
                save()
            self.begin(authority, "native")
            with patch.object(authority, "save", side_effect=tracking):
                for _ in range(12):
                    try:
                        engine.proposal(authority, lambda _: None, slice=15)
                        break
                    except SliceEnded:
                        continue
            numbers = [int(c.split(":")[1]) for c in cursors if c]
            self.assertEqual(numbers, sorted(numbers))  # never backwards
            self.assertEqual(authority.current["status"], "proposed")

    def test_changed_intent_or_native_route_blocks_resubmission(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()])
        with self.authority() as authority:
            self.begin(authority, "native")
            with self.assertRaises(KeyboardInterrupt):
                engine.proposal(authority, lambda _: None)
            other = NativeEngine("/different/zeroshot", self.native)
            with self.assertRaises(Blocked):
                other.proposal(authority, lambda _: None)
            directory = authority.directory / "revision-1"
            (directory / "input.json").write_text('{"task":"changed"}')
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda _: None)
        self.assertEqual(len(calls), 3)

    def test_final_candidate_B_is_the_only_eligible_proposal(self):
        a = fixture_proposal()
        b = copy.deepcopy(a)
        b["requirements"][0]["text"] = "Repaired candidate B"
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), self.terminal(goldfish=False, proposal=b, findings="B accepted"))])
        self.execute(engine, old_planner=True)
        with self.authority() as authority:
            self.assertEqual(authority.current["evidence"]["proposal_digest"], digest(b))
            self.assertEqual(authority.current["evidence"]["findings"], "B accepted")
            saved = copy.deepcopy(authority.current)
            authority.current["terminal_envelope"]["status"]["terminalResult"]["output"]["planFindings"] = "A rejected"
            with self.assertRaises(Blocked):
                authority.approve(1)
            authority.state["revisions"][-1] = saved
            authority.current["proposal"] = a
            with self.assertRaises(Blocked):
                authority.approve(1)

    def test_exhausted_findings_and_accepted_evidence_survive_empty_replay(self):
        for verdict in ("accepted", "rejected"):
            with self.subTest(verdict=verdict):
                engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal(verdict, findings="final " + verdict, goldfish=False)])
                if verdict == "rejected":
                    with self.authority() as authority:
                        authority.begin("Requested feature", ROLES, "native", "New review")
                        # Each subcase is a distinct revision; public title must match.
                    responses_title = "Terminal roadmap revision 2"
                    # The existing accepted revision is history, never used by the new one.
                    engine.call = self._retitle_call(engine.call, responses_title)
                    with self.authority() as authority:
                        engine.proposal(authority, lambda _: None)
                        saved = copy.deepcopy(authority.current)
                else:
                    saved = self.execute(engine, old_planner=True)
                with self.authority() as authority:
                    output = []
                    engine.proposal(authority, output.append)
                    self.assertIn("final " + verdict, "\n".join(plan_lines(authority, authority.current, ())))
                    self.assertEqual(authority.current, saved)
                    # Progress names the verdict in plain words; the findings stay in the plan view and [i].
                    self.assertEqual(output, ["Plan checked." if verdict == "accepted" else "The check did not accept the plan."])
                    if verdict == "rejected":
                        with self.assertRaises(Blocked):
                            authority.approve(2)
                        self.assertEqual(saved["status"], "review_exhausted")
                self.assertEqual(len(calls), 3)

    @staticmethod
    def _retitle_call(call, title):
        def wrapped(argv, **kwargs):
            result = call(argv, **kwargs)
            if argv[1] == "watch":
                value = json.loads(result.stdout)
                value["title"] = title
                result.stdout = json.dumps(value) + "\n"
            return result
        return wrapped

    def test_malformed_receipts_retain_frozen_intent(self):
        for receipt in (None, [], {}, {"runId": None}, ({"runId": "r"}, {"runId": "s"}), '{"runId":"r","runId":"s"}\n'):
            with self.subTest(receipt=receipt):
                # No real run is launched, so dispose each isolated authority fixture.
                engine, calls = self.engine([{"valid": True}, receipt])
                with self.authority() as authority:
                    authority.state = None
                    self.begin(authority, "native")
                    # Previous fixture checkout is isolated test data.
                    import shutil
                    shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
                    with self.assertRaises(Blocked):
                        engine.proposal(authority, lambda _: None)
                    saved = copy.deepcopy(authority.current)
                with self.authority() as authority:
                    self.assertEqual(saved["status"], "submission_unknown")
                    with self.assertRaises(Blocked):
                        engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current, saved)
                self.assertEqual(len(calls), 2)

    def test_a_finished_status_may_carry_a_delivery_receipt(self):
        """P1: Zeroshot 11 adds an optional `metadata.deliveryReceipt` to a finished status; any other unknown
        metadata key is still refused (test_malformed_observations_block_without_guessed_outcomes)."""
        value = self.terminal()
        value["status"]["metadata"] = {"tokenUsage": {"inputTokens": 1, "outputTokens": 2, "complete": True},
                                       "deliveryReceipt": {"status": "none"}}
        self.assertEqual(validate_projection(value, "fixture-native-run")["phase"], "finished")

    def test_malformed_observations_block_without_guessed_outcomes(self):
        """Interpretation: the engine has four branches for a malformed observation -- a line that does not decode, a
        non-record (only `validate_projection` stops it from being used), and a record `validate_projection` refuses
        while the run is running or finished (nothing concludes) -- so one of each goes through the engine. Every
        distinct refusal inside `validate_projection` is a branch of the validator, not of the engine, and is
        checked against it directly."""
        # Branches kept: one engine round trip per kind of refusal; every `validate_projection` refusal directly.
        refused = [None, {"runId": "fixture-native-run", "status": None}, self.projection({"phase": "queued"})]
        for metadata in ({"unknown": 1}, {"tokenUsage": []}, {"tokenUsage": {"inputTokens": -1, "outputTokens": 0, "complete": True}},
                         {"tokenUsage": {"inputTokens": 0, "outputTokens": 0, "complete": "true"}}):
            value = self.terminal()
            value["status"]["metadata"] = metadata
            refused.append(value)
        for mutation in (lambda p: p.update(runId="wrong"), lambda p: p.update(status={}),
                         lambda p: p["status"].update(activeExecutions=None), lambda p: p.update(cursor=None)):
            value = self.running()
            mutation(value)
            refused.append(value)
        for observation in refused:
            with self.subTest(refused=observation), self.assertRaises(Blocked):
                validate_projection(observation, "fixture-native-run")
        finished, running = refused[3], refused[-4]  # the first bad metadata and the first mutation of a running one
        for observation in (None, '{"overflow":1e309}', finished, running):
            with self.subTest(observation=observation):
                engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, observation, self.terminal()])
                with self.authority() as authority:
                    authority.state = None
                    self.begin(authority, "native")
                    import shutil
                    shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
                    with self.assertRaises(Blocked):
                        engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], "observation_blocked")
                    self.assertIsNone(authority.current["terminal_envelope"])
                with self.authority() as authority:
                    engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], "proposed")
                self.assertEqual(sum("--detach" in argv for argv, _ in calls), 1)

    def test_malformed_completed_reviews_are_concluded_invalid(self):
        for mutation in (lambda o: o.pop("planVerdict"), lambda o: o.update(extra="field"),
                         lambda o: o.update(schemaVersion="1"), lambda o: o.update(planVerdict="maybe"),
                         lambda o: o.update(planFindings=None), lambda o: o.update(proposal='{"requirements":[],"milestones":[]}'),
                         lambda o: o.update(proposal='{"x":1,"x":2}'), lambda o: o.update(proposal='NaN')):
            with self.subTest(mutation=mutation):
                terminal = self.terminal()
                mutation(terminal["status"]["terminalResult"]["output"])
                engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, terminal])
                with self.authority() as authority:
                    authority.state = None
                    self.begin(authority, "native")
                    import shutil
                    shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
                    with self.assertRaises(Blocked):
                        engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], "proposal_invalid")
                    self.assertIsNotNone(authority.current["terminal_envelope"])
                with self.authority() as authority:
                    with self.assertRaises(Blocked):
                        engine.proposal(authority, lambda _: None)
                self.assertEqual(len(calls), 3)

    def test_milestone_task_bound_is_instructed_validated_and_never_approved(self):
        instructions = json.dumps(planner_graph())
        self.assertIn("at most 12 tasks per milestone", instructions)
        self.assertIn("more than 12 tasks across its slices", instructions)
        oversized = fixture_proposal()
        oversized["milestones"][0]["slices"][0]["tasks"] = [
            {"id": "T%s" % n, "title": "Task %s" % n, "checks": ["Check %s" % n]} for n in range(11, 24)]
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal(goldfish=False, proposal=oversized)])
        with self.authority() as authority:
            authority.state = None
            self.begin_old_planner(authority, "native")
            shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda _: None)
            self.assertEqual(authority.current["status"], "proposal_invalid")
            self.assertIn("milestone M1 holds 13 tasks, the driver runs at most 12", authority.current["diagnostic"])
        # A record proposed before the bound existed stays readable, but is never approved.
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal(goldfish=False, proposal=oversized)])
        with self.authority() as authority:
            authority.state = None
            self.begin_old_planner(authority, "native")
            shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
            with patch("terminal_planner.authority.check_bounds", lambda plan: plan):
                engine.proposal(authority, lambda _: None)
            self.assertEqual(authority.current["status"], "proposed")
        with self.authority() as authority:
            self.assertEqual(len(authority.current["proposal"]["milestones"][0]["slices"][0]["tasks"]), 13)
            with self.assertRaisesRegex(Blocked, "holds 13 tasks"):
                authority.approve(authority.current["version"])
            self.assertEqual(authority.current["status"], "proposed")

    def test_interrupt_before_terminal_commit_replays_same_first_record(self):
        for verdict in ("accepted", "rejected"):
            with self.subTest(verdict=verdict):
                terminal = self.terminal(verdict)
                engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, (self.running(), terminal), terminal, (self.running(), terminal)])
                with self.authority() as authority:
                    authority.state = None
                    import shutil
                    shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
                    self.begin(authority, "native")
                    with patch.object(authority, "commit_terminal", side_effect=KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt):
                            engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["observation_cursor"], "v2:5")
                with self.authority() as authority:
                    engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["terminal_cursor"], "v2:10")
                    self.assertEqual(authority.current["evidence"]["verdict"], verdict)
                    saved = copy.deepcopy(authority.current)
                with self.authority() as authority:
                    engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current, saved)
                self.assertEqual(calls[-2][0][-2:], ["--after", "v2:5"])
                self.assertNotIn("--after", calls[-1][0])
                self.assertEqual(sum("--detach" in args for args, _ in calls), 1)

    def test_saved_boundary_without_evidence_reconstructs_full_history(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt(), (), self.terminal()])
        with self.authority() as authority:
            self.begin(authority, "native")
            with self.assertRaises(KeyboardInterrupt):
                engine.proposal(authority, lambda _: None)
            authority.current["observation_cursor"] = "v2:10"
            authority.save()
        with self.authority() as authority:
            engine.proposal(authority, lambda _: None)
            self.assertEqual(authority.current["terminal_cursor"], "v2:10")
        self.assertIn("--after", calls[-2][0])
        self.assertNotIn("--after", calls[-1][0])

    def test_later_finished_does_not_replace_first_boundary(self):
        for field in ("observation_cursor", "terminal_cursor"):
            with self.subTest(field=field):
                later = self.terminal(findings="Later projection must not win")
                later["cursor"] = "v2:12"
                responses = [{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()]
                if field == "observation_cursor":
                    responses.append(later)
                responses.append((self.running(), self.terminal()))
                engine, calls = self.engine(responses)
                with self.authority() as authority:
                    authority.state = None
                    import shutil
                    shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
                    self.begin(authority, "native")
                    with self.assertRaises(KeyboardInterrupt):
                        engine.proposal(authority, lambda _: None)
                    authority.current[field] = "v2:10"
                    authority.save()
                with self.authority() as authority:
                    engine.proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["terminal_cursor"], "v2:10")
                    self.assertEqual(authority.current["evidence"]["findings"], "Final independent findings")
                self.assertNotIn("--after", calls[-1][0])
                self.assertEqual(sum("--detach" in a for a, _ in calls), 1)

    def test_save_interruption_before_and_after_terminal_commit(self):
        for verdict in ("accepted", "rejected"):
            for committed in (False, True):
                with self.subTest(verdict=verdict, committed=committed):
                    terminal = self.terminal(verdict, findings="durable " + verdict)
                    engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, terminal, terminal])
                    with self.authority() as authority:
                        authority.state = None
                        import shutil
                        shutil.rmtree(authority.directory / "revision-1", ignore_errors=True)
                        self.begin(authority, "native")
                        save = authority.save
                        interrupted = False

                        def interrupt_save():
                            nonlocal interrupted
                            if authority.current["evidence"] and not interrupted:
                                interrupted = True
                                if committed:
                                    save()
                                raise KeyboardInterrupt
                            save()

                        with patch.object(authority, "save", side_effect=interrupt_save):
                            with self.assertRaises(KeyboardInterrupt):
                                engine.proposal(authority, lambda _: None)
                        self.assertNotEqual(authority.current["status"], "detached")
                        expected = copy.deepcopy(authority.current)
                    with self.authority() as authority:
                        engine.proposal(authority, lambda _: None)
                        self.assertEqual(authority.current, expected)
                    self.assertEqual(sum("--detach" in a for a, _ in calls), 1)

    def test_missing_history_never_resubmits(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, ()])
        with self.authority() as authority:
            self.begin(authority, "native")
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda _: None)
            self.assertEqual(authority.current["status"], "observation_blocked")
        self.assertEqual(sum("--detach" in argv for argv, _ in calls), 1)

    def test_all_freshness_inputs_block_approval(self):
        engine, _ = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal()])
        self.execute(engine)
        mutations = [lambda r: r.update(goal="Different goal"), lambda r: r["roles"]["plan_verifier"].update(model="changed"),
                     lambda r: r.update(baseline="changed"), lambda r: r["proposal"]["requirements"][0].update(text="A"),
                     lambda r: r["native_documents"].update(graph="changed"), lambda r: r["native_documents"].update(runtime="changed"),
                     lambda r: r["native_documents"].update(input="changed"), lambda r: r["evidence"].update(verdict="rejected"),
                     lambda r: r["evidence"].update(findings="changed"), lambda r: r["evidence"].update(output_digest="changed"),
                     lambda r: r["evidence"].update(terminal_cursor="changed"), lambda r: r["native_binding"].update(sha256="changed")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                with self.authority() as authority:
                    mutate(authority.current)
                    with self.assertRaises(Blocked):
                        authority.approve(1)
        (self.project / "source.txt").write_text("changed source")
        self.git("commit", "-qam", "changed source")
        with self.authority() as authority:
            with self.assertRaises(Blocked):
                authority.approve(1)

    def test_terminal_origin_mutations_block_restart_and_approval(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, self.terminal()])
        self.execute(engine)
        with self.authority() as authority:
            good = copy.deepcopy(authority.state)
            original = authority.path.read_bytes()
        mutations = (lambda e: e["source"].update(revision="0" * 40),
                     lambda e: e.update(title="Another frozen intent"), lambda e: e.update(size="large"))
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                # Test in-memory approval independently from restart load validation.
                with self.authority() as authority:
                    mutate(authority.current["terminal_envelope"])
                    with self.assertRaises(Blocked):
                        authority.approve(1)
                corrupt = copy.deepcopy(good)
                mutate(corrupt["revisions"][-1]["terminal_envelope"])
                raw = (canonical(corrupt) + "\n").encode()
                authority.path.write_bytes(raw)
                blocked = self.authority()
                with self.assertRaises(Blocked):
                    with blocked:
                        self.fail("Wrong-origin evidence loaded")
                self.assertIsNone(blocked.lock)
                self.assertEqual(blocked.path.read_bytes(), raw)
                blocked.path.write_bytes(original)
                with self.authority() as restored:
                    self.assertEqual(restored.state, good)
        self.assertEqual(len(calls), 3)
        # The historical origin remains bound when the target HEAD changes.
        (self.project / "source.txt").write_text("new revision")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "changed source")
        with self.authority() as authority:
            self.assertEqual(authority.state, good)
            with self.assertRaises(Blocked):
                authority.approve(1)

    def test_receipt_without_prepared_intent_blocks_load_without_mutation(self):
        engine, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, KeyboardInterrupt()])
        with self.authority() as authority:
            self.begin(authority, "native")
            with self.assertRaises(KeyboardInterrupt):
                engine.proposal(authority, lambda _: None)
            good = copy.deepcopy(authority.state)
            original = authority.path.read_bytes()
        for status in ("observing", "detached", "observation_blocked"):
            with self.subTest(status=status):
                corrupt = copy.deepcopy(good)
                corrupt["revisions"][-1].update(status=status, native_prepared=False, intent=None,
                                               native_documents=None, native_binding=None)
                raw = (canonical(corrupt) + "\n").encode()
                authority.path.write_bytes(raw)
                blocked = self.authority()
                with self.assertRaises(Blocked):
                    with blocked:
                        engine.proposal(blocked, lambda _: None)
                self.assertIsNone(blocked.lock)
                self.assertEqual(blocked.path.read_bytes(), raw)
                blocked.path.write_bytes(original)
                with self.authority() as restored:
                    self.assertEqual(restored.state, good)
        self.assertEqual(len(calls), 3)


class GraphTests(unittest.TestCase):
    def run_graph(self, passes, error=None):
        """Interpret only the authored graph subset, including scoped promotion.

        This deterministic control fixture is not a native scheduler qualification.
        Real CLI admission is separately exercised against the unchanged executable.
        """
        graph = planner_graph()
        channels, calls = {}, []
        candidates = iter(passes)
        current_pass = None

        def guard(g):
            if g["kind"] == "any":
                return any(guard(child) for child in g["guards"])
            selector = g["value"]
            value = channels.get((selector["name"], selector["source"]), {})
            if selector.get("field"):
                value = value.get(selector["field"])
            return value in g["labels"]

        def bindings(items, state):
            result = {}
            for binding in items:
                value = binding["value"]
                source = state if value.get("source") == "state" else channels[(value["node"], value["channel"])]
                self.assertEqual(len(value["path"]), 1)
                result[binding["target"][0]] = source[value["path"][0]]
            return result

        def run(node, parent):
            nonlocal current_pass
            kind, name = node["kind"], node["name"]
            state = copy.deepcopy(parent) if "state" in node else parent
            result = None
            if kind in {"step", "verifier"}:
                self.assertEqual(node["attempts"], 1)
                incoming = bindings(node["inputBindings"], state)
                calls.append((name, incoming))
                channels[(name, "error")] = None
                if error == name:
                    channels[(name, "error")] = "crash"
                    return None
                if kind == "step":
                    current_pass = next(candidates)
                    channels[(name, "out")] = {"proposal": canonical(current_pass[0])}
                else:
                    self.assertEqual(incoming["proposal"], canonical(current_pass[0]))
                    channels[(name, "signal")] = {"verdict": current_pass[1]}
                    channels[(name, "diagnostic")] = {"message": current_pass[2]}
                state.update(bindings(node["writeBindings"], state))
            elif kind == "seq":
                for child in node["children"]:
                    result = run(child, state)
                    if result is not None:
                        break
            elif kind == "choice":
                selected = next((b["node"] for b in node["branches"] if guard(b["when"])), node.get("otherwise"))
                self.assertIsNotNone(selected)
                result = run(selected, state)
            elif kind == "loop":
                self.assertEqual(node["maxIterations"], 3)
                for _ in range(node["maxIterations"]):
                    result = run(node["body"], state)
                    if result is not None or guard(node["until"]):
                        channels[(name, "group")] = {"terminated": "converged"}
                        break
                else:
                    channels[(name, "group")] = {"terminated": "exhausted"}
            elif kind == "succeed":
                result = {"status": "succeeded", "output": bindings(node["bindings"], state)}
            elif kind == "fail":
                result = {"status": "failed", "reason": node["reason"]}
            else:
                self.fail("Unsupported graph fixture node " + kind)
            for path in node.get("promotedStatePaths", []):
                self.assertEqual(len(path), 1)
                parent[path[0]] = state[path[0]]
            return result

        return run(graph["root"], planner_input({"goal": "fixture"})), calls

    def test_repair_pairing_promotion_and_stop_after_acceptance(self):
        a = fixture_proposal()
        b = copy.deepcopy(a)
        b["requirements"][0]["text"] = "candidate B"
        result, calls = self.run_graph([(a, "rejected", "findings A"), (b, "accepted", "findings B")])
        self.assertEqual([name for name, _ in calls], ["planner", "plan_verifier"] * 2)
        self.assertEqual(calls[2][1]["planFindings"], "findings A")
        self.assertEqual(calls[2][1]["proposal"], canonical(a))
        self.assertEqual(result, {"status": "succeeded", "output": {
            "schemaVersion": "1", "proposal": canonical(b), "planVerdict": "accepted", "planFindings": "findings B"}})

    def test_three_completed_rejections_and_errors_never_export_seed(self):
        p = fixture_proposal()
        result, calls = self.run_graph([(p, "rejected", "pass " + str(i)) for i in range(3)])
        self.assertEqual(len(calls), 6)
        self.assertEqual(result["output"]["planFindings"], "pass 2")
        self.assertEqual(result["output"]["planVerdict"], "rejected")
        for name in ("planner", "plan_verifier"):
            result, calls = self.run_graph([(p, "accepted", "must not export")], error=name)
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("output", result)
            self.assertEqual(len(calls), 1 if name == "planner" else 2)


class ScriptedTerminal(Terminal):
    """A terminal over piped input: the session core's `terminal` in tests that need one."""

    def __init__(self, text, output, keys=()):
        super().__init__(io.StringIO(text), output)


class CliTests(unittest.TestCase):
    def test_version_flag(self):
        result = subprocess.run([sys.executable, "-m", "terminal_planner", "--version"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "zplan 0.15.0")

    def test_terminal_control_sequences_are_neutralized(self):
        value = safe("title\x1b]52;c;secret\x07\r\x9b31m")
        for control in ("\x1b", "\x07", "\r", "\x9b"):
            self.assertNotIn(control, value)


class StatusTests(ProjectTest):
    def test_status_prints_home_once_without_prompts(self):
        from terminal_planner.cli import status
        from terminal_planner.delivery import Delivery
        from terminal_planner.planning import Planning
        from terminal_planner.runs import FixtureDriver, MilestoneRuns
        with Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, FixtureDriver(self.root / "fixture-runs"), worktrees=self.root / "worktrees")
            service = Delivery(authority, runs, Planning(authority, runs, lambda *_: FixtureEngine()))
            r, mark = service.start(service.preview("M1", ROLES), ROLES), None
            while r["status"] in {"submitted", "running", "stopping"}:
                mark = service.step(r, mark).mark
            service.end(r)
        out = io.StringIO()
        status(Terminal(io.StringIO(), out), self.project, self.state, "test", lambda _: FixtureDriver(self.root / "fixture-runs"),
               worktrees=self.root / "worktrees")
        text = out.getvalue()
        self.assertIn("zplan · project with spaces (main, clean)", text)
        self.assertIn("Plan r1 · approved · 0/2 stages merged", text)
        self.assertIn("M1 First usable increment    waiting for merge", text)


class MilestoneCountWordingTests(unittest.TestCase):
    """The overview summary names the plan's milestones as "stage" or "stages" after the fraction."""

    def test_overview_summary_pluralises_stage(self):
        from terminal_planner.delivery import Delivery
        plan = {"version": 2}
        for total, word in ((1, "stage"), (2, "stages"), (5, "stages"), (11, "stages"), (21, "stages"), (12, "stages")):
            items = [{"id": "M%s" % i, "title": "t", "state": "ready"} for i in range(total)]
            first = Delivery.overview_lines(plan, items, text=lambda i: i["state"])[0]
            self.assertEqual(first, "Plan r2 · approved · 0/%s %s merged" % (total, word))
            self.assertNotIn("milestone", first)


if __name__ == "__main__":
    unittest.main()
