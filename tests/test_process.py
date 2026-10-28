"""Process profile core (G1a): schema, resolver, acceptance state, bootstrap, guards, doctor/profile output.

Every test runs against real temporary Git repositories and the fixture store (no provider, no network). The Pilot
tests need Textual (the interpreter's own or the wheels of ZPLAN_TEST_WHEELHOUSE) and skip without it."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from terminal_planner import autonomy, cli, process, setup
from terminal_planner.authority import Authority as RealAuthority, Blocked, canonical
from terminal_planner.engine import FixtureEngine
from terminal_planner.process import Profile, ProfileChanged
from terminal_planner.runs import FixtureDriver
import test_terminal_planner as tp
import test_tui as tt
from test_runs import split_candidate
from test_terminal_planner import PLAN, START, MERGE, ROLES, ScriptedTerminal
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

MERGE_REFUSED = "Not done: "  # the merge refusal line is delivery.py's (T2); T3 translates it with the text

ROOT = Path(__file__).resolve().parents[1]
WORKER = {"model": "worker-model", "effort": "low"}


class ProfileTest(tp.ProjectTest):
    """A project with helpers to write the profile file / roles.json and to read the resolved state."""

    def setUp(self):
        super().setUp()
        self.config = self.root / "config"
        patcher = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config), "XDG_DATA_HOME": str(self.root / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)
        # i6: the main screen's own texts come from the UI string catalog, whose language lives at
        # `$XDG_CONFIG_HOME/planning-kit/ui.json`. This class points the config root at its own tree, so the
        # process-wide `ru` pin `tests/tui_support.py` sets does not reach it: store `ru` here. For the
        # full-screen shells of the subclasses it keeps the first-run language chooser from covering the screen
        # (and keeps the shell Russian, as their assertions expect); a plain session never reads it.
        ui = self.config / "planning-kit" / "ui.json"
        ui.parent.mkdir(parents=True, exist_ok=True)
        ui.write_text('{"language": "ru"}\n', encoding="utf-8")
        # a clean tree is a start precondition: keep the profile file out of it (committing it moves HEAD)
        with (self.project / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
            handle.write("\n%s\n" % process.PROFILE_FILE)

    @property
    def file(self):
        return self.project / process.PROFILE_FILE

    def write(self, document, name=process.PROFILE_FILE):
        text = document if isinstance(document, str) else json.dumps(document, ensure_ascii=False, indent=2)
        (self.project / name).write_text(text, encoding="utf-8")

    def save_roles(self, value):
        path = self.config / "planning-kit" / "roles.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def peek(self):
        return Profile.peek(self.project, root=self.state, fixture_id="test")

    def sidecar(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return authority.directory / process.STATE_FILE

    def problem(self, document):
        """The refusal text of a profile document; asserts the family and that it is the file's refusal."""
        self.write(document)
        status = self.peek().status()
        self.assertEqual(status.state, "malformed", document)
        with self.assertRaises(Blocked) as raised:
            Profile.peek(self.project, root=self.state, fixture_id="test").guard("plan")
        self.assertEqual(raised.exception.family, "process.invalid")
        return status.problem

    @contextlib.contextmanager
    def app(self, profile=True, text=""):
        """The plain App over a locked fixture authority; with `profile` it enforces the project's profile."""
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            driver = FixtureDriver(self.root / "fixture-runs", "done")
            terminal = ScriptedTerminal(text, io.StringIO())
            yield cli.App(terminal, authority, lambda *_: FixtureEngine(), driver, authority.directory / "worktrees",
                          profile=Profile.of(authority) if profile else None)

    def approved_plan(self):
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)

    def accept_file(self, document=None):
        """An accepted profile *file* (the owner's own document, or the proposal) through a production-mode Profile.

        It is deliberately a production-mode Profile over the store: a fixture session keeps its accepted snapshot
        in the fixture state and never writes `zplan.process.json` (R-3), so a test that wants the file writes it
        the way a production accept does. Any fixture record is dropped first, so the store ends up holding a
        native `accepted` record (no snapshot) beside the file — the state of a project whose real, committed
        `zplan.process.json` is its source."""
        if document is not None:
            self.write(document)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            (authority.directory / process.STATE_FILE).unlink(missing_ok=True)
            Profile(self.project, authority.directory, authority).accept()

    def remove_accepted_file(self, authority=None):
        """A deleted profile in a fixture session: the file is gone and the record keeps no snapshot.

        That is the state a deleted legacy (pre-R-3) accept leaves. After the R-3 snapshot retention a plain
        deletion is no longer "missing": a writable fixture session adopts the file's effective snapshot
        (process.Profile._accepted_record), so the accepted profile survives the file. A test that wants the
        "deleted" refusal therefore models the record explicitly, without letting a session see the file. Pass the
        session's authority when the project lock is already held."""
        self.file.unlink()

        def forget(store):
            record = process.read_record(store.directory)
            process.atomic_state(store.directory / process.STATE_FILE,
                                 process.make_record("accepted", record["digest"]))

        if authority is not None:
            forget(authority)
            return
        with RealAuthority(self.state, self.project, fixture_id="test") as store:
            forget(store)

    def head(self):
        return self.git("rev-parse", "HEAD").decode().strip()

    def rules(self, name="AGENTS.md", text="rules\n"):
        """A rules file the clean-tree start precondition does not see."""
        with (self.project / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
            handle.write("\n%s\n" % name)
        (self.project / name).write_text(text, encoding="utf-8")

    def defer(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return Profile.of(authority).defer()

    def awaiting_merge(self):
        """An accepted profile and M1 finished, waiting for the merge (made by the line UI)."""
        self.run_session("a\n" + PLAN + "a\n" + START + "l\nq\n")
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")
        # R-3: a fixture session accepts into the fixture state and writes no project file; the profile is usable.
        self.assertEqual(self.peek().status().state, "accepted")
        self.assertFalse(self.file.exists())

    def stored(self):
        with tp.Authority(self.state, self.project) as authority:
            state = copy.deepcopy(authority.state)
        if state is not None:
            state.setdefault("runs", [])
        return state

    def run_session(self, text, profile=True, outcome="done", terminal=None, **fixture):
        output = io.StringIO()
        driver = FixtureDriver(self.root / "fixture-runs", outcome, **fixture)
        terminal = terminal or ScriptedTerminal(text, output)
        terminal.output = output
        cli.session(terminal, self.project, self.state, lambda *_: FixtureEngine(), fixture_id="test",
                    driver_factory=lambda _: driver, worktrees=self.root / "worktrees", profile=profile)
        return output.getvalue()

    def env(self):
        return tt.plain_env(HOME=str(self.root / "home"), XDG_DATA_HOME=str(self.root / "data"),
                            XDG_CONFIG_HOME=str(self.config))

    def zplan(self, *args, cwd=None, stdin=b""):
        """The real entry point as a subprocess (no TTY, so always plain); returns (code, stdout, stderr)."""
        done = subprocess.run([sys.executable, "-m", "terminal_planner.cli", *args], input=stdin, capture_output=True,
                              env=self.env(), cwd=str(cwd or self.project), timeout=120)
        return done.returncode, done.stdout.decode(), done.stderr.decode()

    def fixture_args(self, *args):
        return [*args, "--project", str(self.project), "--state-dir", str(self.state), "--fixture", "test"]


# G-A1 ----------------------------------------------------------------------------------------------------------

class ValidationTests(ProfileTest):
    CASES = (
        ("unknown top-level key", {"extras": 1}, "extras"),
        ("not an object", [], "(root)"),
        ("unknown preset", {"preset": "zplan.default/9"}, "preset"),
        ("preset is a list", {"preset": ["zplan.default/1"]}, "preset"),
        ("preset is an object", {"preset": {"name": "zplan.default/1"}}, "preset"),
        ("preset is a number", {"preset": 1}, "preset"),
        ("unknown role", {"roles": {"analyst": WORKER}}, "roles.analyst"),
        ("plan_verifier is called critic", {"roles": {"plan_verifier": WORKER}}, "roles.plan_verifier"),
        ("role not an object", {"roles": {"worker": "gpt"}}, "roles.worker"),
        ("bad model id", {"roles": {"worker": {"model": "bad model", "effort": "low"}}}, "roles.worker.model"),
        ("bad effort", {"roles": {"worker": {"model": "m", "effort": "extreme"}}}, "roles.worker.effort"),
        ("role with extra key", {"roles": {"worker": dict(WORKER, temperature=1)}}, "roles.worker"),
        ("roles not an object", {"roles": []}, "roles"),
        ("unknown gate", {"gates": {"deploy": "required"}}, "gates.deploy"),
        ("gate value", {"gates": {"task": "maybe"}}, "gates.task"),
        ("plan gate off", {"gates": {"plan": "off"}}, "gates.plan"),
        ("plan_rounds out of range", {"limits": {"plan_rounds": 6}}, "limits.plan_rounds"),
        ("limit is a string", {"limits": {"task_rounds": "2"}}, "limits.task_rounds"),
        ("limit is a bool", {"limits": {"merge_rounds": True}}, "limits.merge_rounds"),
        ("limit too large", {"limits": {"task_rounds": 99}}, "limits.task_rounds"),
        ("unknown limit", {"limits": {"forever": 1}}, "limits.forever"),
        ("unknown autonomy key", {"preset": process.PRESET_V2, "autonomy": {"x": 1}}, "autonomy.x"),
        ("autonomy level", {"preset": process.PRESET_V2, "autonomy": {"level": "yolo"}}, "autonomy.level"),
        ("autonomy max_runs out of range", {"preset": process.PRESET_V2, "autonomy": {"max_runs": 9}},
         "autonomy.max_runs"),
        ("autonomy not an object", {"preset": process.PRESET_V2, "autonomy": []}, "autonomy"),
        ("autonomy bool", {"preset": process.PRESET_V2, "autonomy": {"run_minutes": True}}, "autonomy.run_minutes"),
        ("checks not a list", {"checks": "npm test"}, "checks"),
        ("empty argv", {"checks": [{"name": "unit", "argv": []}]}, "checks[0].argv"),
        ("argv element empty", {"checks": [{"name": "unit", "argv": ["npm", ""]}]}, "checks[0].argv"),
        ("argv not a list", {"checks": [{"name": "unit", "argv": "npm test"}]}, "checks[0].argv"),
        ("check name", {"checks": [{"name": "two words", "argv": ["x"]}]}, "checks[0].name"),
        ("check timeout", {"checks": [{"name": "unit", "argv": ["x"], "timeout_s": 0}]}, "checks[0].timeout_s"),
        ("check duplicate names", {"checks": [{"name": "u", "argv": ["x"]}, {"name": "u", "argv": ["y"]}]}, "checks"),
        ("second check broken", {"checks": [{"name": "a", "argv": ["x"]}, {"name": "b", "argv": []}]}, "checks[1].argv"),
        ("rules not a list", {"rules": "AGENTS.md"}, "rules"),
        ("rules outside the repository", {"rules": ["../outside.md"]}, "rules[0]"),
        ("rules absolute path", {"rules": ["/etc/passwd"]}, "rules[0]"),
        ("rules file missing", {"rules": ["MISSING.md"]}, "rules[0]"),
        ("rules twice", {"rules": ["a.md", "a.md"]}, "rules"),
    )

    def test_every_invalid_document_is_refused_naming_its_key(self):
        (self.project / "a.md").write_text("rule\n")
        for label, document, key in self.CASES:
            with self.subTest(label):
                text = self.problem(document)
                self.assertIn("'%s'" % key, text)
                self.assertIn(process.PROFILE_FILE, text)

    def test_not_json_and_duplicate_keys_are_refused(self):
        for label, text in (("not json", "{nope"), ("duplicate key", '{"rules": [], "rules": []}')):
            with self.subTest(label):
                self.assertIn("(file)", self.problem(text))

    def test_rules_link_pointing_outside_the_repository_is_refused(self):
        outside = self.root / "outside.md"
        outside.write_text("secret rules\n")
        (self.project / "link.md").symlink_to(outside)
        self.assertIn("rules[0]", self.problem({"rules": ["link.md"]}))

    def test_empty_argv_message_is_in_russian_and_names_the_fix(self):
        text = self.problem({"checks": [{"name": "unit", "argv": []}]})
        self.assertIn("checks[0].argv", text)
        self.assertIn("the check command is empty", text)
        self.assertIn("Give a program", text)

    def test_a_valid_document_is_accepted_and_nothing_is_run(self):
        (self.project / "a.md").write_text("rule\n")
        self.write({"preset": process.PRESET, "rules": ["a.md"], "roles": {"worker": WORKER},
                    "gates": {"plan": "required", "task": "off", "merge": "off"},
                    "limits": {"plan_rounds": 3, "task_rounds": 4}, "checks": [{"name": "unit", "argv": ["true"]}]})
        status = self.peek().status()
        self.assertNotEqual(status.state, "malformed", status.problem)


# G-A2 ----------------------------------------------------------------------------------------------------------

class ResolverTests(ProfileTest):
    def resolved(self):
        status = self.peek().status()
        self.assertIsNotNone(status.resolved, status.problem)
        return status.resolved

    def test_precedence_file_then_user_roles_then_preset_with_sources(self):
        self.save_roles({"worker": {"model": "user-worker", "effort": "high"},
                         "reviewer": {"model": "user-reviewer", "effort": "medium"}})
        self.write({"roles": {"worker": WORKER}})
        resolved = self.resolved()
        self.assertEqual(resolved.config["roles"]["worker"], WORKER)
        self.assertEqual(resolved.sources["roles.worker"], "file")
        self.assertEqual(resolved.config["roles"]["reviewer"], {"model": "user-reviewer", "effort": "medium"})
        self.assertEqual(resolved.sources["roles.reviewer"], "user")
        self.assertEqual(resolved.config["roles"]["planner"], {"model": "gpt-6.1-sol", "effort": "high"})
        self.assertEqual(resolved.sources["roles.planner"], "preset")
        self.assertEqual(resolved.sources["gates.plan"], "preset")
        self.assertEqual(resolved.config["roles"]["architect"], {"model": "gpt-6.1-sol", "effort": "high"})

    def test_empty_or_missing_roles_json_leaves_the_preset(self):
        for text in (None, "", "  \n", "{}"):
            with self.subTest(text):
                if text is not None:
                    self.save_roles(text)
                self.write({})
                resolved = self.resolved()
                self.assertEqual(resolved.sources["roles.worker"], "preset")
                self.assertEqual({v for k, v in resolved.sources.items() if k.startswith("roles.")}, {"preset"})
                self.assertEqual(resolved.config["roles"]["worker"], {"model": "gpt-6.1-sol", "effort": "medium"})

    def test_plan_verifier_in_roles_json_is_read_as_critic(self):
        self.save_roles({"plan_verifier": {"model": "verifier-model", "effort": "xhigh"}})
        resolved = self.resolved()
        self.assertEqual(resolved.config["roles"]["critic"], {"model": "verifier-model", "effort": "xhigh"})
        self.assertEqual(resolved.roles()["plan_verifier"], {"model": "verifier-model", "effort": "xhigh"})
        self.assertNotIn("plan_verifier", resolved.config["roles"])

    def test_critic_wins_over_plan_verifier_in_roles_json(self):
        self.save_roles({"plan_verifier": {"model": "old", "effort": "high"}, "critic": {"model": "new", "effort": "high"}})
        self.assertEqual(self.resolved().config["roles"]["critic"]["model"], "new")

    def test_corrupt_roles_json_is_refused_with_its_family(self):
        self.save_roles("{broken")
        with self.assertRaises(Blocked) as raised:
            self.peek().status()
        self.assertEqual(raised.exception.family, "readiness.roles")

    def test_legacy_effort_in_roles_json_counts_as_not_saved(self):
        for effort in ("none", "minimal", "ultra"):
            with self.subTest(effort):
                self.save_roles({"worker": {"model": "gpt-6.1-sol", "effort": effort},
                                 "reviewer": {"model": "user-reviewer", "effort": "medium"}})
                self.write({})
                resolved = self.resolved()
                self.assertEqual(resolved.sources["roles.worker"], "preset")
                self.assertEqual(resolved.config["roles"]["worker"], {"model": "gpt-6.1-sol", "effort": "medium"})
                self.assertEqual(resolved.sources["roles.reviewer"], "user")

    def test_legacy_effort_in_roles_json_does_not_block_defer_reopen_or_accept(self):
        self.save_roles({"worker": {"model": "gpt-6.1-sol", "effort": "minimal"}})
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertEqual(Profile.of(authority).defer().state, "later")
        self.assertEqual(self.peek().status().state, "later")  # the sidecar is readable after a reopen
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertEqual(Profile.of(authority).status().state, "later")
        self.accept_file()
        self.assertEqual(self.peek().status().state, "accepted")
        document = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(document["roles"]["worker"]["effort"], "max")  # the proposal is /3: the legacy value is not saved, the preset worker applies

    def test_rules_content_change_changes_the_digest_with_the_same_path(self):
        (self.project / "AGENTS.md").write_text("one\n")
        self.write({"rules": ["AGENTS.md"]})
        before = self.resolved()
        (self.project / "AGENTS.md").write_text("two\n")
        after = self.resolved()
        self.assertEqual(before.config, after.config)
        self.assertNotEqual(before.digest, after.digest)
        self.assertEqual([p for p, _ in after.rules], ["AGENTS.md"])

    def test_digest_is_stable_across_key_order(self):
        one = {"roles": {"worker": WORKER, "reviewer": WORKER}, "gates": {"plan": "required", "task": "off"},
               "limits": {"task_rounds": 4, "plan_rounds": 3}}
        two = {"limits": {"plan_rounds": 3, "task_rounds": 4}, "gates": {"task": "off", "plan": "required"},
               "roles": {"reviewer": WORKER, "worker": WORKER}}
        self.write(one)
        first = self.resolved().digest
        self.write(two)
        self.assertEqual(self.resolved().digest, first)
        self.write({"roles": {"worker": dict(WORKER, effort="high")}})
        self.assertNotEqual(self.resolved().digest, first)

    def test_editing_the_file_in_an_open_app_changes_the_next_runtime_but_not_frozen_revisions(self):
        self.accept_file({"roles": {"planner": WORKER}})
        two = {"model": "planner-two", "effort": "high"}
        with self.app() as app:
            before = app.planning.begin("First goal", app.roles)
            self.assertEqual(before["roles"]["planner"], WORKER)
            self.write({"roles": {"planner": two}})
            self.assertEqual(app.roles["planner"], two)  # the open app sees it
            app.planning.begin("Second goal", ROLES)  # a caller's older copy is not used
            revisions = app.authority.state["revisions"]
            self.assertEqual(revisions[0]["roles"]["planner"], WORKER)  # the frozen revision is untouched
            self.assertEqual(revisions[-1]["roles"]["planner"], two)

    def test_roles_feed_the_legacy_role_names(self):
        resolved = self.resolved()
        self.assertEqual(set(resolved.roles()), {"planner", "plan_verifier", "worker", "reviewer", "steward"})


# A1 ------------------------------------------------------------------------------------------------------------

AUTONOMY_DEFAULTS = {"level": "auto", "max_runs": 3, "worker_round_minutes": 45, "run_minutes": 120,
                     "structural_round": 3, "wakeups_per_hour": 12, "architect_retries": 3}
# The `/1` profile as it resolved before `autonomy` existed, captured from the resolver at 7b40c07: C3 requires the
# digest and the `describe` lines to stay byte-identical.
PRESET1_DIGEST = "4cd20d1393ccd81f56cc118262e2be210bf9ab71bd3b27edb10960e9a84e407f"
PRESET1_DESCRIBE = (
    "Process profile: accepted · file zplan.process.json · digest 4cd20d1393cc",
    "  preset zplan.default/1  [preset zplan.default/1]",
    "  role planner   gpt-6.1-sol / high  [preset zplan.default/1]",
    "  role critic    gpt-6.1-sol / high  [preset zplan.default/1]",
    "  role worker    gpt-6.1-sol / medium  [preset zplan.default/1]",
    "  role reviewer  gpt-6.1-sol / high  [preset zplan.default/1]",
    "  role steward   gpt-6.1-sol / high  [preset zplan.default/1]",
    "  role architect gpt-6.1-sol / high  [preset zplan.default/1]",
    "  plan check: required  [preset zplan.default/1]",
    "  task check: no check  [preset zplan.default/1] (for later stages)",
    "  merge check: no check  [preset zplan.default/1]",
    "  rounds: plan 3  [preset zplan.default/1]; task retries 2  [preset zplan.default/1]; merge 2 "
    "(for later stages)",
    "  rules (when planning): none",
    "  checks: no qualification",
)


class AutonomyPresetTests(ProfileTest):
    """A1: `zplan.default/2` is the `/1` roles, gates and limits plus the `autonomy` section as data; `/1` stays
    byte-identical and nothing consumes `autonomy` yet.

    Interpretations: C4's autonomy line ends with the source marker of `autonomy.level` (the section's primary key),
    rendered like every other marker, so the example's `[preset zplan.default/2]` is what a file that sets no
    `autonomy` value resolves to; C3's fix is quoted as "give "preset": "zplan.default/2"" and is rendered as the
    remedy clause of the problem, verbatim, before the generic "Fix the value."."""

    def resolved(self):
        status = self.peek().status()
        self.assertIsNotNone(status.resolved, status.problem)
        return status.resolved

    def test_preset3_moves_only_the_worker_and_keeps_preset2_as_it_is(self):
        """M1 the proposal and /3 carry the worker on gpt-6.1-terra / max, every other role gpt-6.1-sol / high;
        M2 a file naming /2 with no roles still resolves the worker to gpt-6.1-sol / medium and a /3 file with
        `autonomy.level` manual is valid. Interpretation: /3's gates, limits, autonomy and risk are compared with /2's
        as data (nothing else of /3 is pinned)."""
        sol = {"model": "gpt-6.1-sol", "effort": "high"}
        roles = process.propose(self.project, {})["roles"]
        self.assertEqual(process.propose(self.project, {})["preset"], "zplan.default/3")
        self.assertEqual(roles["worker"], {"model": "gpt-6.1-terra", "effort": "max"})
        self.assertEqual({name: roles[name] for name in roles if name != "worker"},
                         {name: sol for name in process.ROLES if name != "worker"})
        self.write({"preset": process.PRESET_V2})
        self.assertEqual(self.resolved().config["roles"]["worker"], {"model": "gpt-6.1-sol", "effort": "medium"})
        self.write({"preset": process.PRESET_V3, "autonomy": {"level": "manual"}})
        three = self.resolved()
        self.assertEqual(three.config["preset"], "zplan.default/3")
        self.assertEqual(three.config["autonomy"]["level"], "manual")
        for key in ("gates", "limits", "risk"):
            self.assertEqual(three.config[key], process.resolve({"preset": process.PRESET_V2}, {}, self.project).config[key])

    def test_preset2_is_preset1_roles_gates_and_limits_plus_autonomy(self):
        one = process.resolve(None, {}, self.project)
        self.write({"preset": process.PRESET_V2})
        two = self.resolved()
        self.assertEqual(two.config["preset"], "zplan.default/2")
        self.assertEqual(two.config["roles"], one.config["roles"])
        self.assertEqual(two.config["gates"], one.config["gates"])
        self.assertEqual(two.config["limits"], one.config["limits"])
        self.assertNotIn("autonomy", one.config)
        self.assertEqual(two.config["autonomy"], AUTONOMY_DEFAULTS)

    def test_a_file_sets_any_subset_of_autonomy_the_rest_comes_from_the_preset(self):
        self.write({"preset": process.PRESET_V2, "autonomy": {"level": "manual"}})
        resolved = self.resolved()
        self.assertEqual(resolved.config["autonomy"], dict(AUTONOMY_DEFAULTS, level="manual"))
        self.assertEqual(resolved.sources["autonomy.level"], "file")
        self.assertEqual({k: v for k, v in resolved.sources.items()
                          if k.startswith("autonomy.") and k != "autonomy.level"},
                         {("autonomy." + k): "preset" for k in process.AUTONOMY if k != "level"})
        self.write({"preset": process.PRESET_V2, "autonomy": {"max_runs": 5, "wakeups_per_hour": 1}})
        other = self.resolved()
        self.assertEqual(other.config["autonomy"], dict(AUTONOMY_DEFAULTS, max_runs=5, wakeups_per_hour=1))
        self.assertEqual(other.sources["autonomy.max_runs"], "file")
        self.assertEqual(other.sources["autonomy.wakeups_per_hour"], "file")
        self.assertEqual(other.sources["autonomy.level"], "preset")

    def test_every_autonomy_value_is_bounded_and_bool_is_refused(self):
        for key in ("auto", "supervised", "manual"):
            with self.subTest(level=key):
                self.write({"preset": process.PRESET_V2, "autonomy": {"level": key}})
                self.assertEqual(self.resolved().config["autonomy"]["level"], key)
        for name, (low, high) in process.AUTONOMY_RANGES.items():
            for value in (low, high):
                with self.subTest(key=name, accepted=value):
                    self.write({"preset": process.PRESET_V2, "autonomy": {name: value}})
                    self.assertEqual(self.resolved().config["autonomy"][name], value)
            for value in (low - 1, high + 1):
                with self.subTest(key=name, refused=value):
                    text = self.problem({"preset": process.PRESET_V2, "autonomy": {name: value}})
                    self.assertIn("'autonomy.%s'" % name, text)
                    self.assertIn("from %d to %d" % (low, high), text)

    def test_invalid_autonomy_values_are_refused_like_other_keys(self):
        text = self.problem({"preset": process.PRESET_V2, "autonomy": {"level": "yolo"}})
        self.assertEqual(text, "%s: key 'autonomy.level' - allowed: auto, manual, supervised. Fix the value."
                         % process.PROFILE_FILE)
        text = self.problem({"preset": process.PRESET_V2, "autonomy": {"max_runs": 9}})
        self.assertIn("'autonomy.max_runs'", text)
        self.assertIn("from 1 to 5", text)
        text = self.problem({"preset": process.PRESET_V2, "autonomy": {"start_runs": 1}})
        self.assertIn("'autonomy.start_runs'", text)
        self.assertIn("unknown key", text)

    def test_autonomy_is_part_of_the_resolved_digest(self):
        self.write({"preset": process.PRESET_V2})
        base = self.resolved().digest
        self.write({"preset": process.PRESET_V2, "autonomy": {"level": "manual"}})
        self.assertNotEqual(self.resolved().digest, base)
        self.write({"preset": process.PRESET_V2, "autonomy": {"max_runs": 4}})
        self.assertNotEqual(self.resolved().digest, base)

    def test_resolved_preset1_config_digest_and_describe_lines_are_frozen(self):
        fallback = process.resolve(None, {}, self.project)  # no profile at all: the /1 fallback
        self.assertEqual(fallback.digest, PRESET1_DIGEST)
        self.assertNotIn("autonomy", fallback.config)
        self.assertEqual(tuple(process.describe(process.Status("accepted", process.resolve(None, {}, self.project),
                                                              True))), PRESET1_DESCRIBE)
        self.write({"preset": process.PRESET})  # a file naming /1 resolves to the same config and digest
        named = self.resolved()
        self.assertEqual(named.digest, PRESET1_DIGEST)
        self.assertNotIn("autonomy", named.config)
        lines = process.describe(self.peek().status())
        self.assertIn("  preset zplan.default/1  [zplan.process.json]", lines)
        self.assertFalse([line for line in lines if "autonomy" in line])

    def test_preset1_refuses_autonomy_naming_the_v2_preset(self):
        for document in ({"autonomy": {"level": "auto"}}, {"preset": process.PRESET, "autonomy": {"level": "auto"}}):
            with self.subTest(document):
                text = self.problem(document)
                self.assertIn("'autonomy'", text)
                self.assertIn('give "preset": "zplan.default/2"', text)

    def test_a_stored_preset1_acceptance_snapshot_still_loads(self):
        """A fresh project is now offered /2, so the stored /1 snapshot is modelled explicitly (a project accepted
        before RC2)."""
        resolved = process.resolve(None, {}, self.project)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            process.atomic_state(authority.directory / process.STATE_FILE,
                                 process.make_record("accepted", resolved.digest, process.snapshot_of(resolved)))
        self.assertFalse(self.file.exists())
        reopened = self.peek().status()
        self.assertEqual(reopened.state, "accepted")
        self.assertEqual(reopened.resolved.digest, PRESET1_DIGEST)
        self.assertNotIn("autonomy", reopened.resolved.config)

    def test_describe_under_preset2_adds_the_autonomy_line_after_the_rounds(self):
        self.write({"preset": process.PRESET_V2})
        lines = process.describe(self.peek().status())
        index = next(n for n, line in enumerate(lines) if line.startswith("  rounds:"))
        self.assertEqual(lines[index + 1],
                         "  autonomy: auto · up to 3 runs · worker round 45 min · run 120 min · check "
                         "after round 3 · wake-ups 12/h · retries 3  [preset zplan.default/2]")  # D6b: acts, shown as is
        self.assertIn("  preset zplan.default/2  [zplan.process.json]", lines)
        self.write({"preset": process.PRESET_V2, "autonomy": {"level": "manual"}})
        manual = next(line for line in process.describe(self.peek().status()) if line.startswith("  autonomy:"))
        self.assertTrue(manual.endswith("  [zplan.process.json]"), manual)

    def test_preset2_profile_is_accepted_and_freezes_through_the_plan_guard(self):
        self.accept_file({"preset": process.PRESET_V2, "autonomy": {"level": "supervised", "max_runs": 2}})
        status = self.peek().status()
        self.assertEqual(status.state, "accepted")
        self.assertEqual(status.resolved.config["autonomy"], dict(AUTONOMY_DEFAULTS, level="supervised", max_runs=2))
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            roles, frozen = Profile.of(authority).freeze_plan()
        self.assertEqual(frozen["config_digest"], status.resolved.digest)
        self.assertEqual(set(roles), {"planner", "plan_verifier"})

    def test_a_fresh_project_is_offered_preset2_with_autonomy_auto_and_the_fallback_stays_1(self):
        """RC2 (0.6.0 smoke defect 10): C1 the proposal is /2 with the preset's `autonomy` section (level `auto`);
        C2 the accepted file resolves and reads `auto`, `gates.merge` stays off; C3 the no-profile fallback
        (`process.PRESET`) stays /1 and an accepted /1 file keeps /1 and reads `manual`, untouched.
        Interpretation: `risk` is not written into the proposal (the /2 preset's defaults apply when it is absent)."""
        self.assertEqual(process.PRESET, "zplan.default/1")
        self.assertEqual(process.resolve(None, {}, self.project).config["preset"], process.PRESET)
        status = self.peek().status()
        self.assertEqual(status.state, "never")
        self.assertEqual(status.proposal["preset"], process.PRESET_V3)
        self.assertEqual(status.proposal["autonomy"], process.PRESETS[process.PRESET_V3]["autonomy"])
        self.assertEqual(status.proposal["autonomy"]["level"], "auto")
        self.assertEqual(process.propose(self.project, {})["preset"], process.PRESET_V3)
        self.accept_file()
        written = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual((written["preset"], written["autonomy"]["level"]), (process.PRESET_V3, "auto"))
        accepted = self.peek()
        self.assertEqual(accepted.status().state, "accepted")
        self.assertEqual(autonomy.level(accepted), "auto")
        self.assertEqual(accepted.status().resolved.config["gates"]["merge"], "off")

    def test_the_proposal_turns_the_merge_gate_on_only_where_it_found_checks(self):
        """RS3. C1 npm test script -> gates == plan required, task off, merge required; an empty project -> merge off
        and the preset's constants unchanged. C2 pytest config (pytest.ini, [tool.pytest in pyproject.toml,
        [tool:pytest] in setup.cfg) -> python3 -m pytest; tests/test_*.py alone -> unittest discover -s tests;
        npm and make keep precedence. C3 the accepted file's merge decision is allow at auto, ask at
        supervised/manual. C4 an accepted file with merge off is not rewritten and still reads off; /1 and the
        no-profile fallback stay. Interpretation: `test_*.py` is searched recursively under tests/."""
        self.assertEqual(process.propose(self.project, {})["gates"], {"plan": "required", "task": "off", "merge": "off"})
        self.assertEqual(process.PRESETS[process.PRESET_V2]["gates"]["merge"], "off")
        unittest_argv = ["python3", "-m", "unittest", "discover", "-s", "tests"]
        (self.project / "tests").mkdir()
        (self.project / "tests" / "test_slug.py").write_text("")
        self.assertEqual(process.detect_checks(self.project)[0]["argv"], unittest_argv)
        for name, text in (("pytest.ini", ""), ("pyproject.toml", "[tool.pytest.ini_options]\n"),
                           ("setup.cfg", "[tool:pytest]\n")):
            (self.project / name).write_text(text)
            self.assertEqual(process.detect_checks(self.project)[0]["argv"], ["python3", "-m", "pytest"], name)
            (self.project / name).unlink()
        (self.project / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        self.assertEqual(process.detect_checks(self.project)[0]["argv"], unittest_argv)
        (self.project / "Makefile").write_text("test:\n\ttrue\n")
        self.assertEqual(process.detect_checks(self.project)[0]["argv"], ["make", "test"])
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": "node run.js"}}))
        self.assertEqual(process.detect_checks(self.project)[0]["argv"], ["npm", "test"])
        proposal = process.propose(self.project, {})
        self.assertEqual(proposal["gates"], {"plan": "required", "task": "off", "merge": "required"})
        self.assertEqual(proposal["checks"], process.detect_checks(self.project))
        self.accept_file()
        accepted = self.peek().status()
        self.assertEqual(accepted.resolved.config["gates"]["merge"], "required")
        gate = autonomy.merge_gate(accepted)
        self.assertEqual([autonomy.decide(level, "merge", gate) for level in ("auto", "supervised", "manual")],
                         ["allow", "ask", "ask"])

    def test_an_accepted_file_with_merge_off_is_not_rewritten(self):
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": "node run.js"}}))
        self.accept_file({"preset": process.PRESET_V2, "gates": {"merge": "off"}})
        before = self.file.read_bytes()
        self.assertEqual(self.peek().status().resolved.config["gates"]["merge"], "off")
        self.assertEqual(self.file.read_bytes(), before)

    def test_an_accepted_preset1_file_keeps_preset1_and_reads_manual(self):
        self.accept_file({"preset": process.PRESET})
        before = self.file.read_bytes()
        status = self.peek().status()
        self.assertEqual(status.resolved.config["preset"], process.PRESET)
        self.assertEqual(autonomy.level(self.peek()), "manual")
        self.assertEqual(self.file.read_bytes(), before)


RISK_PRESET2 = {
    "rules": [{"paths": ["**/*.md", "docs/**"], "tier": "low"},
              {"paths": ["**/install*", "pyproject.toml", "setup.py", "package.json", "Cargo.toml", "**/*.lock",
                         "Dockerfile", ".github/**", "**/.env*", "**/*secret*", "**/*credential*", "**/*.pem",
                         "**/*.key"], "tier": "high"}],
    "triggers": [{"name": "secrets", "paths": ["**/.env*", "**/*secret*", "**/*credential*", "**/*.pem", "**/*.key"]},
                 {"name": "installer", "paths": ["**/install*"]},
                 {"name": "toolchain", "paths": ["pyproject.toml", "setup.py", "package.json", "Cargo.toml",
                                                 "**/*.lock"]},
                 {"name": "packaging", "paths": ["Dockerfile", ".github/**"]},
                 {"name": "data_loss", "paths": []}, {"name": "process_kill", "paths": []},
                 {"name": "disagreement", "paths": []}]}


class RiskPresetTests(ProfileTest):
    """A1b: `zplan.default/2` carries the `risk` data (rules -> tier, triggers) and `risk_of` classifies paths;
    nothing consumes either yet. `/1` is untouched (the frozen digest test in AutonomyPresetTests covers it).

    Interpretations: the describe line ends with the source marker of `risk.rules` and `(for later stages)`,
    rendered like the autonomy line and placed right after it; the preset's `risk` is the task's lists verbatim, in
    the task's order; `risk` under /1 is refused with the same remedy clause `autonomy` gets; a pattern is checked
    for shape only (a glob that matches nothing is valid); an empty `risk` object is valid and changes nothing."""

    def resolved(self):
        status = self.peek().status()
        self.assertIsNotNone(status.resolved, status.problem)
        return status.resolved

    def classify(self, paths, document=None):
        self.write(dict(document or {}, preset=process.PRESET_V2))
        return process.risk_of(self.resolved().config, paths)

    def risk_lines(self):
        return [line for line in process.describe(self.peek().status()) if "risk" in line]

    def test_c1_each_list_comes_whole_from_the_file_else_from_the_preset(self):
        self.write({"preset": process.PRESET_V2})
        resolved = self.resolved()
        self.assertEqual(resolved.config["risk"], RISK_PRESET2)
        self.assertEqual((resolved.sources["risk.rules"], resolved.sources["risk.triggers"]), ("preset", "preset"))
        mine = [{"paths": ["src/**"], "tier": "medium"}]
        self.write({"preset": process.PRESET_V2, "risk": {"rules": mine}})
        resolved = self.resolved()
        self.assertEqual(resolved.config["risk"], {"rules": mine, "triggers": RISK_PRESET2["triggers"]})
        self.assertEqual((resolved.sources["risk.rules"], resolved.sources["risk.triggers"]), ("file", "preset"))
        self.write({"preset": process.PRESET_V2, "risk": {"triggers": [{"name": "mine", "paths": []}]}})
        resolved = self.resolved()
        self.assertEqual(resolved.config["risk"], {"rules": RISK_PRESET2["rules"],
                                                   "triggers": [{"name": "mine", "paths": []}]})
        self.assertEqual((resolved.sources["risk.rules"], resolved.sources["risk.triggers"]), ("preset", "file"))
        self.assertNotEqual(resolved.digest, process.resolve({"preset": process.PRESET_V2}, {}).digest)

    def test_c2_invalid_risk_is_refused_naming_the_key(self):
        rule = {"paths": ["docs/**"], "tier": "low"}
        cases = [
            ("bad tier", {"rules": [dict(rule, tier="critical")]}, "risk.rules[0].tier"),
            ("absolute pattern", {"rules": [dict(rule, paths=["/etc/**"])]}, "risk.rules[0].paths[0]"),
            ("dotdot pattern", {"rules": [rule, dict(rule, paths=["a", "../b"])]}, "risk.rules[1].paths[1]"),
            ("too long pattern", {"rules": [dict(rule, paths=["a" * 257])]}, "risk.rules[0].paths[0]"),
            ("rule without paths", {"rules": [dict(rule, paths=[])]}, "risk.rules[0].paths"),
            ("no rules", {"rules": []}, "risk.rules"),
            ("too many rules", {"rules": [rule] * 33}, "risk.rules"),
            ("too many triggers", {"triggers": [{"name": "t%d" % i, "paths": []} for i in range(17)]},
             "risk.triggers"),
            ("too many patterns", {"triggers": [{"name": "t", "paths": ["a"] * 33}]}, "risk.triggers[0].paths"),
            ("duplicate trigger", {"triggers": [{"name": "t", "paths": []}, {"name": "t", "paths": ["a"]}]},
             "risk.triggers"),
            ("bad trigger name", {"triggers": [{"name": "a b", "paths": []}]}, "risk.triggers[0].name"),
            ("unknown risk key", {"extra": 1}, "risk.extra"),
            ("unknown rule key", {"rules": [dict(rule, extra=1)]}, "risk.rules[0].extra"),
            ("not an object", [], "risk"),
        ]
        for label, risk, key in cases:
            with self.subTest(label):
                self.assertIn("'%s'" % key, self.problem({"preset": process.PRESET_V2, "risk": risk}))
        edge = {"rules": [dict(rule, paths=["a" * 256] + ["b"] * 31)] + [dict(rule, paths=["c"] * 32)] * 31,
                "triggers": [{"name": "t%d" % i, "paths": []} for i in range(16)]}
        self.write({"preset": process.PRESET_V2, "risk": edge})
        self.assertEqual(self.resolved().config["risk"], edge)

    def test_c2_risk_under_preset1_names_the_v2_preset(self):
        for document in ({"risk": {}}, {"preset": process.PRESET, "risk": {"rules": []}}):
            with self.subTest(document):
                text = self.problem(document)
                self.assertIn("'risk'", text)
                self.assertIn('give "preset": "zplan.default/2"', text)

    def test_c3_risk_of_takes_the_highest_tier_and_counts_unmatched_as_medium(self):
        self.assertEqual(self.classify(["README.md"]), {"tier": "low", "triggers": [], "unmatched": []})
        self.assertEqual(self.classify(["docs/a/b.txt", "README.md"])["tier"], "low")
        self.assertEqual(self.classify(["README.md", "src/a.py"]),
                         {"tier": "medium", "triggers": [], "unmatched": ["src/a.py"]})
        self.assertEqual(self.classify(["app/.env.local"]), {"tier": "high", "triggers": ["secrets"], "unmatched": []})
        self.assertEqual(self.classify(["README.md", "src/a.py", "Dockerfile"])["tier"], "high")
        self.assertEqual(self.classify([]), {"tier": "high", "triggers": [], "unmatched": []})
        both = self.classify(["tools/install.sh", "pyproject.toml", ".github/ci.yml", "a/b/uv.lock"])
        self.assertEqual(both["triggers"], ["installer", "packaging", "toolchain"])
        # a path that matches a low and a high rule is high; the project's own rules replace the preset's
        self.assertEqual(self.classify(["docs/install.md"])["tier"], "high")
        mine = {"risk": {"rules": [{"paths": ["src/**"], "tier": "low"}]}}
        self.assertEqual(self.classify(["src/a.py"], mine), {"tier": "low", "triggers": [], "unmatched": []})
        self.assertEqual(self.classify(["README.md"], mine)["unmatched"], ["README.md"])

    def test_c4_snapshot_must_carry_risk_in_full_and_describe_shows_one_line(self):
        self.write({"preset": process.PRESET_V2})
        config = self.resolved().config
        self.assertEqual(process.complete(copy.deepcopy(config))["risk"], RISK_PRESET2)
        for broken in (lambda c: c.pop("risk"), lambda c: c["risk"].pop("triggers"), lambda c: c["risk"].pop("rules")):
            damaged = copy.deepcopy(config)
            broken(damaged)
            with self.subTest(broken):
                with self.assertRaises(ValueError):
                    process.complete(damaged)
        self.assertEqual(self.risk_lines(),
                         ["  risk: 2 rules · 7 triggers  [preset zplan.default/2] (for later stages)"])
        self.write({"preset": process.PRESET_V2, "risk": {"triggers": [{"name": "t", "paths": []}]}})
        self.assertEqual(self.risk_lines(),
                         ["  risk: 2 rules · 1 triggers  [preset zplan.default/2] (for later stages)"])
        self.write({"preset": process.PRESET_V2, "risk": {"rules": [{"paths": ["a"], "tier": "low"}]}})
        self.assertEqual(self.risk_lines(),
                         ["  risk: 1 rules · 7 triggers  [zplan.process.json] (for later stages)"])
        self.write({})
        self.assertEqual(self.risk_lines(), [])

    def test_c4_preset2_with_risk_is_accepted_and_reloads_from_its_snapshot(self):
        self.accept_file({"preset": process.PRESET_V2, "risk": {"rules": [{"paths": ["src/**"], "tier": "low"}]}})
        status = self.peek().status()
        self.assertEqual(status.state, "accepted")
        self.assertEqual(status.resolved.config["risk"]["rules"], [{"paths": ["src/**"], "tier": "low"}])
        self.assertEqual(process.risk_of(status.resolved.config, ["src/a.py"])["tier"], "low")


class ProfileCommitTests(ProfileTest):
    """O2b C2: accepting the proposal that writes `zplan.process.json` also commits that file alone.

    Worker interpretations (the reviewers never see the worker's summary):

    - The commit is `git add -- zplan.process.json` then `git commit -m "zplan profile" -- zplan.process.json`: a new
      file is untracked, and `commit -- <path>` alone would not find it. Other changes, staged or not, stay as they were.
    - A failed commit (here a pre-commit hook that refuses) is not an error of the accept: the file and the accepted
      record stay, `Status.notice` names the command, and the readiness «clean» item is the profile item as before.
    - The commit is part of `Profile.accept`, which the line UI and the full-screen modal both call (neither
      caller is in this task's write-set); the line UI therefore commits too and still prints its old advice line.
    - The base class keeps the profile file in `info/exclude` to keep the tree clean; this class lifts that, as a real
      project has the file visible.
    """

    def setUp(self):
        super().setUp()
        (self.project / ".git" / "info" / "exclude").write_text("", encoding="utf-8")

    def accept(self, fixture=False):
        """A production-mode accept over the fixture store (as `accept_file`), or the fixture session's own."""
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            if fixture:
                return Profile.of(authority).accept()
            return Profile(self.project, authority.directory, authority).accept()

    def head(self):
        return self.git("log", "-1", "--format=%s").decode().strip(), self.git("show", "--name-only", "--format=", "HEAD").decode().split()

    def test_accept_commits_the_file_alone_and_leaves_other_changes_as_they_are(self):
        (self.project / "notes.txt").write_text("draft\n")
        (self.project / "source.txt").write_text("changed\n")
        self.git("add", "source.txt")
        before = self.git("rev-parse", "HEAD")
        status = self.accept()
        self.assertEqual(status.state, "accepted")
        self.assertEqual(status.notice, "")
        self.assertEqual(self.head(), ("zplan profile", [process.PROFILE_FILE]))
        self.assertEqual(self.git("rev-parse", "HEAD~1"), before)
        self.assertEqual(self.git("status", "--porcelain").decode().splitlines(), ["M  source.txt", "?? notes.txt"])
        self.git("reset", "-q", "--hard")
        self.assertTrue(self.file.is_file())

    def test_accept_in_a_clean_repo_leaves_it_clean(self):
        self.accept()
        self.assertEqual(self.head()[0], "zplan profile")
        self.assertEqual(self.git("status", "--porcelain"), b"")
        self.assertTrue(all(i["ok"] for i in setup.check_target(self.project)))

    def test_a_failed_commit_keeps_the_file_the_accept_and_the_readiness_item_and_names_the_command(self):
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        before = self.git("rev-parse", "HEAD")
        status = self.accept()
        self.assertEqual(status.state, "accepted")
        self.assertIn('git add %s && git commit -m "zplan profile" -- %s' % ((process.PROFILE_FILE,) * 2), status.notice)
        self.assertTrue(self.file.is_file())
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        clean = next(i for i in setup.check_target(self.project) if i["id"] == "clean")
        self.assertTrue(clean["ok"])  # D4a: informational, never a block; the uncommitted profile is named
        self.assertIn(process.PROFILE_FILE, clean["line"])

    def test_an_existing_file_commits_nothing(self):
        before = self.git("rev-parse", "HEAD")
        self.write(process.propose(self.project, {}))
        self.accept()
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("status", "--porcelain").decode().split(), ["??", process.PROFILE_FILE])

    def test_a_fixture_session_commits_nothing(self):
        before = self.git("rev-parse", "HEAD")
        self.accept(fixture=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertFalse(self.file.exists())

    def test_the_modal_text_says_the_file_is_committed(self):
        lines = process.bootstrap_lines(process.Status("never", process.resolve(process.propose(self.project, {}), {},
                                                                              self.project), False))
        text = "\n".join(lines)
        self.assertIn("zplan profile", text)
        self.assertNotIn("commit it", text)


class GlobMatchTests(unittest.TestCase):
    """r-glob-py312: `glob_match` is `PurePosixPath.full_match` for the `validate_pattern` domain on every Python >=
    3.11 (`full_match` itself is new in 3.13, which crashed `/2` classification on 3.11/3.12).

    Interpretations: `**` mirrors pathlib's `full_match` exactly, so a `**/` prefix may cover zero segments (`a.md`
    matches `**/*.md`) while a trailing `/**` still needs a segment under the literal parent (`docs/**` does not
    match `docs`); a segment is a maximal run between `/`; the parity matrix reads the preset's own pattern strings
    from `process.PRESETS`, so it cannot drift from the preset."""

    PATHS = (
        "a.md", "src/a.py", "a.py", "docs", "docs/x/y.txt", "docs/install.md", "docs/.hidden.md", "README.md",
        "README.MD", "pyproject.toml", "x/pyproject.toml", ".env", ".env.local", "app/.env.local", "install.sh",
        "a/b/install.sh", "src/install_tool.py", "tools/uv.lock", "Dockerfile", "Dockerfile.dev", ".github/ci.yml",
        "s/creds/credential.json", "a/key.pem", "sub/xsecretx", "Makefile", "a", "a/b", "a/b/c/d/e/f.txt",
    )

    TABLE = (
        ("a.md", "**/*.md", True),
        ("docs/x/y.txt", "docs/**", True),
        ("src/a.py", "*.py", False),
        (".env.local", "**/.env*", True),
        ("a/b/install.sh", "**/install*", True),
        ("README.MD", "**/*.md", False),
        ("x/pyproject.toml", "pyproject.toml", False),
    )

    @staticmethod
    def preset_patterns():
        risk = process.PRESETS[process.PRESET_V2]["risk"]
        return [pattern for group in risk.values() for entry in group for pattern in entry["paths"]]

    def test_c1_the_table_matches_on_every_python(self):
        for path, pattern, expected in self.TABLE:
            with self.subTest(path=path, pattern=pattern):
                self.assertEqual(process.glob_match(path, pattern), expected)

    def test_c1_risk_of_classifies_a_risk_section_on_every_python(self):
        config = {"risk": copy.deepcopy(process.PRESETS[process.PRESET_V2]["risk"])}
        self.assertEqual(process.risk_of(config, ["app/.env.local"]),
                         {"tier": "high", "triggers": ["secrets"], "unmatched": []})
        self.assertEqual(process.risk_of(config, ["docs/a.md"]), {"tier": "low", "triggers": [], "unmatched": []})

    @unittest.skipUnless(hasattr(PurePosixPath("x"), "full_match"),
                         "PurePosixPath.full_match is new in Python 3.13; parity cannot be checked here")
    def test_c2_parity_with_full_match_when_available(self):
        patterns = self.preset_patterns() + [pattern for _, pattern, _ in self.TABLE]
        for pattern in patterns:
            for path in self.PATHS:
                with self.subTest(pattern=pattern, path=path):
                    self.assertEqual(process.glob_match(path, pattern),
                                     PurePosixPath(path).full_match(PurePosixPath(pattern)))


# G-A3 ----------------------------------------------------------------------------------------------------------

class StateTests(ProfileTest):
    def test_never_proposes_and_writes_nothing(self):
        status = self.peek().status()
        self.assertEqual(status.state, "never")
        self.assertFalse(self.file.exists())
        self.assertFalse(self.sidecar().exists())
        self.assertEqual(status.resolved.config["checks"], [])

    def test_existing_valid_file_is_only_recorded_never_rewritten(self):
        self.write('{"roles":{"worker":{"model":"w","effort":"low"}}}')
        before = self.file.read_bytes()
        status = self.peek().status()
        self.assertEqual((status.state, status.present), ("never", True))
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            done = Profile.of(authority).accept()
        self.assertEqual(done.state, "accepted")
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(self.peek().status().state, "accepted")  # across a reopen

    def test_profile_init_over_an_existing_file_is_refused(self):
        self.write('{"roles":{}}')
        before = self.file.read_bytes()
        code, out, _ = self.zplan(*self.fixture_args("profile", "init"))
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED:", out)
        self.assertIn("does not overwrite it", out)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertFalse(self.sidecar().exists())

    def test_profile_init_keeps_the_demo_snapshot_and_a_second_init_refuses(self):
        """R-3: `--fixture test profile init` accepts into the fixture state; the target's `zplan.process.json` is
        never created. The accepted snapshot keeps the profile usable across a reopen, and a second init is refused
        because the fixture state already decided it."""
        code, out, _ = self.zplan(*self.fixture_args("profile", "init"))
        self.assertEqual(code, 0, out)
        self.assertFalse(self.file.exists())
        self.assertIn("Demo profile accepted", out)
        self.assertNotIn("Commit it", out)
        record = process.read_record(self.sidecar().parent)
        self.assertEqual(record["state"], "accepted")
        self.assertIsNotNone(record["snapshot"])
        reopened = self.peek().status()
        self.assertEqual(reopened.state, "accepted")  # across a reopen, without any project file
        self.assertEqual(reopened.resolved.config["preset"], process.PRESET_V3)
        code, out, _ = self.zplan(*self.fixture_args("profile", "init"))
        self.assertEqual(code, 1)
        self.assertIn("does not overwrite it", out)

    def test_later_then_file_created_then_accepted_keeps_the_fixture_snapshot(self):
        """R-3: adopting a file that appeared keeps the fixture session's effective snapshot, so the file may go
        away again and the fixture profile is still accepted — not "missing" with a git-checkout remedy."""
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertEqual(Profile.of(authority).defer().state, "later")
        self.assertFalse(self.file.exists())
        self.assertEqual(self.peek().status().state, "later")  # across a reopen, without any lock
        self.write({"roles": {"worker": WORKER}})
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            adopted = Profile.of(authority).status()
        self.assertEqual(adopted.state, "accepted")
        self.assertIn(process.PROFILE_FILE, adopted.notice)
        self.assertEqual(self.peek().status().state, "accepted")
        self.file.unlink()
        gone = self.peek().status()
        self.assertEqual(gone.state, "accepted")  # the snapshot survived the file's removal
        self.assertEqual(gone.resolved.config["roles"]["worker"], WORKER)
        self.assertFalse(self.file.exists())
        self.peek().guard("plan")  # planning stays usable without the project file

    def test_accepted_then_malformed_is_refused_with_the_invalid_family(self):
        self.accept_file()
        self.file.write_text("{broken")
        with self.assertRaises(Blocked) as raised:
            self.peek().guard("milestone")
        self.assertEqual(raised.exception.family, "process.invalid")

    def test_undecided_profile_refuses_new_work_with_the_pending_family(self):
        with self.assertRaises(Blocked) as raised:
            self.peek().guard("plan")
        self.assertEqual(raised.exception.family, "process.pending")

    def test_second_process_reading_does_not_change_the_state(self):
        for args in (("profile",), ("status",)):
            with self.subTest(args):
                code, out, _ = self.zplan(*self.fixture_args(*args))
                self.assertEqual(code, 0, out)
        self.assertFalse(self.file.exists())
        self.assertFalse(self.sidecar().exists())
        self.assertEqual(self.peek().status().state, "never")

    def test_later_snapshot_is_used_and_the_header_says_so(self):
        out = self.run_session("l\nq\n")
        self.assertIn("zplan · project with spaces (main, clean) · profile not saved", out)
        self.assertFalse(self.file.exists())
        out = self.run_session("q\n")  # reopened: no bootstrap screen again, the note stays
        self.assertNotIn("Project process profile", out)
        self.assertIn("· profile not saved", out)

    def test_later_snapshot_keeps_the_rules_and_checks_the_screen_showed(self):
        (self.project / "AGENTS.md").write_text("rules\n")
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        shown = self.peek().status()
        self.assertEqual([p for p, _ in shown.resolved.rules], ["AGENTS.md"])
        self.assertEqual(shown.resolved.config["checks"][0]["argv"], ["npm", "test"])
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            Profile.of(authority).defer()
        later = self.peek().status()  # across a reopen
        self.assertEqual(later.state, "later")
        self.assertEqual(later.resolved.rules, shown.resolved.rules)
        self.assertEqual(later.resolved.config["checks"], shown.resolved.config["checks"])
        self.assertEqual(later.resolved.digest, shown.resolved.digest)

    def test_a_fixture_session_accepts_without_the_file_and_has_no_header_note(self):
        """R-3: the line UI's accept keeps the snapshot in the fixture state; the target's file is not written, the
        accepted state survives a reopen, and the header carries no «profile not saved» note."""
        out = self.run_session("a\nq\n")
        self.assertFalse(self.file.exists())
        self.assertIn("Demo profile accepted", out)
        self.assertNotIn("Commit it", out)
        self.assertNotIn("· profile not saved", out)
        self.assertEqual(self.peek().status().state, "accepted")

    def test_interrupted_accept_is_recovered_at_the_next_start(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            profile = Profile.of(authority)
            profile._write(process.make_record("accepting"))  # intent recorded, the crash came before the file
            self.assertFalse(self.file.exists())
            self.assertEqual(profile.status().state, "never")
            self.assertFalse((authority.directory / process.STATE_FILE).exists())
            profile._write(process.make_record("accepting"))
            self.write({"roles": {"worker": WORKER}})  # the file was written, the crash came after it
            self.assertEqual(profile.status().state, "accepted")
            self.assertEqual(process.read_record(authority.directory)["state"], "accepted")

    def test_interrupted_accept_after_later_returns_to_later(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            profile = Profile.of(authority)
            later = profile.defer()
            record = process.read_record(authority.directory)
            profile._write(process.make_record("accepting", None, None, {
                "state": "later", "digest": record["digest"], "snapshot": record["snapshot"]}))
            self.assertEqual(profile.status().state, "later")
            self.assertEqual(later.digest, profile.status().digest)

    def crash_in(self, name, failing):
        """Run the real accept() in a session where the `name` step raises when `failing(*args)`: returns after the
        'crash' (the session is closed, its lock released)."""
        real = getattr(Profile, name)

        def crashing(profile, *args):
            if failing(*args):
                raise OSError("simulated crash in " + name)
            return real(profile, *args)
        with patch.object(Profile, name, crashing):
            with RealAuthority(self.state, self.project, fixture_id="test") as authority:
                with self.assertRaises(OSError):
                    # the crash recovery under test is the file-writing production accept, not the fixture one (R-3)
                    Profile(self.project, authority.directory, authority).accept()

    def test_crash_after_the_file_was_created_is_finished_at_the_next_start(self):
        self.crash_in("_write", lambda record: record["state"] == "accepted")
        self.assertTrue(self.file.exists())
        directory = self.sidecar().parent
        self.assertEqual(process.read_record(directory)["state"], "accepting")  # the intent is all the sidecar has
        self.assertEqual(self.peek().status().state, "accepted")  # a reader without the lock sees the file as accepted
        self.assertEqual(process.read_record(directory)["state"], "accepting")  # and writes nothing
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertEqual(Profile.of(authority).status().state, "accepted")
            self.assertEqual(process.read_record(authority.directory)["state"], "accepted")
            Profile.of(authority).guard("plan")
        self.assertEqual(self.peek().status().state, "accepted")

    def test_crash_before_the_file_was_created_returns_to_what_it_was(self):
        self.crash_in("_create", lambda text: True)
        self.assertFalse(self.file.exists())
        self.assertEqual(process.read_record(self.sidecar().parent)["state"], "accepting")
        self.assertEqual(self.peek().status().state, "never")
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertEqual(Profile.of(authority).status().state, "never")
            self.assertFalse((authority.directory / process.STATE_FILE).exists())

    def test_crash_before_the_file_after_later_returns_to_later(self):
        later = self.defer()
        self.crash_in("_create", lambda text: True)
        self.assertEqual(process.read_record(self.sidecar().parent)["state"], "accepting")
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            status = Profile.of(authority).status()
            self.assertEqual((status.state, status.digest), ("later", later.digest))
            self.assertEqual(process.read_record(authority.directory)["state"], "later")

    def test_profile_init_while_another_session_holds_the_lock_is_refused_quickly_and_writes_nothing(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            started = time.monotonic()
            code, out, err = self.zplan(*self.fixture_args("profile", "init"))
            elapsed = time.monotonic() - started
            self.assertEqual(code, 1, out + err)
            self.assertIn("Another terminal already manages this project's plan.", out)
            self.assertFalse(self.file.exists())
            self.assertFalse((authority.directory / process.STATE_FILE).exists())
        self.assertLess(elapsed, 30)  # LOCK_NB: a refusal, not a wait

    def test_accept_and_defer_without_the_session_lock_change_nothing(self):
        def refused(action, profile):
            with self.assertRaises(Blocked) as raised:
                action(profile)
            self.assertEqual(raised.exception.family, "action.refused")
        for name in ("accept", "defer"):
            with self.subTest("no profile file, " + name):
                refused(lambda p: getattr(p, name)(), self.peek())
                self.assertFalse(self.file.exists())
                self.assertFalse(self.sidecar().exists())
        self.write({"roles": {"worker": WORKER}})
        before = self.file.read_bytes()
        refused(lambda p: p.accept(), self.peek())  # an existing file is recorded only under the lock
        self.assertEqual(self.file.read_bytes(), before)
        self.assertFalse(self.sidecar().exists())
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            closed = Profile.of(authority)
        refused(lambda p: p.accept(), closed)  # the session that held the lock is gone
        self.assertEqual(self.file.read_bytes(), before)
        self.assertFalse(self.sidecar().exists())

    def test_corrupt_sidecar_is_refused_naming_the_file(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            path = authority.directory / process.STATE_FILE
        for text in ("{nope", '{"schema": 7}', "[]"):
            with self.subTest(text):
                path.write_text(text)
                with self.assertRaises(Blocked) as raised:
                    self.peek().status()
                self.assertEqual(raised.exception.family, "process.state")
                self.assertIn(str(path), str(raised.exception))
                self.assertIn("Delete", str(raised.exception))
        path.unlink()

    def test_sidecar_is_private_atomic_and_in_the_fixture_namespace(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            Profile.of(authority).defer()
            path = authority.directory / process.STATE_FILE
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(self.state.resolve() / "v3" / "fixtures" / "test", path.parents[1])
        self.assertEqual(sorted(p.name for p in path.parent.iterdir() if p.name.startswith(".")), [])
        self.assertEqual(json.loads(path.read_text())["schema"], 1)
        other = RealAuthority(self.state, self.project, fixture_id="other")
        self.assertEqual(Profile.of(other).status().state, "never")  # another namespace does not see it


class LaterRulesTests(ProfileTest):
    """A "later" profile is the configuration the owner saw, but its rules are read from the project every time."""

    def test_rules_edit_changes_the_digest_and_deletion_is_refused_as_a_file_profile_is(self):
        self.rules("AGENTS.md", "one\n")
        shown = self.defer()
        self.assertEqual((shown.state, [p for p, _ in shown.resolved.rules]), ("later", ["AGENTS.md"]))
        self.assertEqual(self.peek().status().digest, shown.digest)
        (self.project / "AGENTS.md").write_text("two\n")
        edited = self.peek().status()
        self.assertEqual(edited.state, "later")
        self.assertNotEqual(edited.digest, shown.digest)
        self.assertEqual(edited.resolved.rules, process.read_rules(self.project, ["AGENTS.md"]))
        (self.project / "AGENTS.md").unlink()
        gone = self.peek().status()  # the snapshot is not corrupt: the project's rules file is what is missing
        self.assertEqual(gone.state, "malformed")
        self.assertIn("rules[0]", gone.problem)
        with self.assertRaises(Blocked) as raised:
            self.peek().guard("plan")
        self.assertEqual(raised.exception.family, "process.invalid")
        self.assertEqual(process.read_record(self.sidecar().parent)["state"], "later")
        (self.project / "AGENTS.md").write_text("one\n")  # the file is back: the profile is whole again
        self.assertEqual(self.peek().status().digest, shown.digest)

    def test_a_later_profile_without_rules_has_nothing_to_reread(self):
        shown = self.defer()
        self.assertEqual(self.peek().status().digest, shown.digest)
        self.assertEqual(self.peek().status().resolved.rules, ())


# G-A4 ----------------------------------------------------------------------------------------------------------

class GuardTests(ProfileTest):
    def snapshot(self, app):
        return (copy.deepcopy(app.authority.state), self.head(),
                sorted(p.name for p in (self.root / "fixture-runs").glob("*")) if (self.root / "fixture-runs").exists() else [],
                sorted(p.name for p in (app.authority.directory / "worktrees").glob("*"))
                if (app.authority.directory / "worktrees").exists() else [])

    def test_deleted_profile_refuses_new_plans_and_starts_without_side_effects(self):
        self.accept_file({"roles": {"worker": WORKER}})
        self.approved_plan_and_remove_file()
        with self.app() as app:
            before = self.snapshot(app)
            with self.assertRaises(Blocked) as raised:
                app.planning.begin("A new goal", app.roles)
            self.assertEqual(raised.exception.family, "process.missing")
            with self.assertRaises(Blocked) as raised:
                app.delivery.preview("M1", app.roles)
            self.assertEqual(raised.exception.family, "process.missing")
            self.assertEqual(self.snapshot(app), before)

    def approved_plan_and_remove_file(self):
        self.approved_plan()
        self.file.unlink()

    def test_required_task_gate_blocks_start_with_a_named_refusal(self):
        self.accept_file({"gates": {"task": "required"}})
        self.approved_plan()
        with self.app() as app:
            before = self.snapshot(app)
            with self.assertRaises(Blocked) as raised:
                app.delivery.preview("M1", app.roles)
            self.assertEqual(raised.exception.family, "process.unbuilt")
            self.assertIn("the task check is not built yet: turn it off in zplan.process.json", str(raised.exception))
            self.assertEqual(self.snapshot(app), before)
            self.assertEqual(app.authority.state.get("runs", []), [])

    def test_start_is_refused_when_the_profile_became_unusable_after_the_preview(self):
        self.accept_file({"roles": {"worker": WORKER}})
        self.approved_plan()
        with self.app() as app:
            preview = app.delivery.preview("M1", app.roles)
            before = self.snapshot(app)
            self.write({"roles": {"worker": WORKER}, "gates": {"task": "required"}})
            with self.assertRaises(Blocked) as raised:
                app.delivery.start(preview, app.roles)
            self.assertEqual(raised.exception.family, "process.unbuilt")
            self.assertEqual(self.snapshot(app), before)
            self.remove_accepted_file(app.authority)
            with self.assertRaises(Blocked) as raised:
                app.delivery.start(preview, app.roles)
            self.assertEqual(raised.exception.family, "process.missing")
            self.assertEqual(self.snapshot(app), before)
            self.assertEqual(app.authority.state.get("runs", []), [])

    def test_later_rules_changed_after_the_preview_refuse_the_start_without_side_effects(self):
        self.rules("AGENTS.md", "one\n")
        self.defer()
        self.approved_plan()
        with self.app() as app:
            preview = app.delivery.preview("M1", app.roles)
            before = self.snapshot(app)
            (self.project / "AGENTS.md").write_text("two\n")
            with self.assertRaises(ProfileChanged):
                app.delivery.start(preview, app.roles)
            self.assertEqual(self.snapshot(app), before)
            fresh = app.delivery.preview("M1", app.roles)  # the owner confirms the new values
            self.assertNotEqual(fresh.profile, preview.profile)
            (self.project / "AGENTS.md").unlink()
            with self.assertRaises(Blocked) as raised:
                app.delivery.start(fresh, app.roles)
            self.assertEqual(raised.exception.family, "process.invalid")
            self.assertEqual(self.snapshot(app), before)
            self.assertEqual(app.authority.state.get("runs", []), [])

    def refusals(self, session_text, needle, prefix="Not done: "):
        """The plain UI over `session_text` prints a refusal containing `needle` and changes nothing."""
        head, state = self.head(), self.stored()
        out = self.run_session(session_text)
        self.assertIn(prefix, out)
        self.assertIn(needle, out)
        self.assertEqual(self.head(), head)
        self.assertEqual(self.stored(), state)
        return out

    def test_plain_required_task_gate_refuses_the_start_and_creates_nothing(self):
        self.run_session("a\n" + PLAN + "a\nq\n")
        self.write({"gates": {"task": "required"}})
        worktrees = self.root / "worktrees"
        out = self.refusals(START + "q\n", "the task check is not built yet: turn it off in zplan.process.json")
        self.assertNotIn("Start M1 ·", out)  # refused before the owner is asked to confirm a preview
        self.assertEqual(self.stored()["runs"], [])
        self.assertFalse(worktrees.exists() and any(worktrees.iterdir()))

    def test_plain_required_merge_gate_and_deleted_profile_refuse_the_merge(self):
        self.awaiting_merge()
        self.write({"gates": {"merge": "required"}})
        self.refusals("o\n" + MERGE + "l\nq\n", "there are no checks", prefix=MERGE_REFUSED)
        self.accept_file({})  # a native file profile replaces the fixture snapshot, then its file goes away
        self.file.unlink()
        self.refusals("o\n" + MERGE + "l\nq\n", "was deleted from the project", prefix=MERGE_REFUSED)
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")

    def test_active_run_is_watched_to_its_end_and_exported_after_the_profile_is_deleted(self):
        self.accept_file()
        self.approved_plan()
        with self.app() as app:
            app.delivery.start(app.delivery.preview("M1", app.roles), app.roles)
        self.remove_accepted_file()
        self.assertEqual(self.peek().status().state, "missing")
        with self.app() as app:
            run, mark = app.delivery.active_run(), None
            self.assertIsNotNone(run)
            for _ in range(200):
                step = app.delivery.step(app.delivery.latest("M1"), mark)
                mark = step.mark
                if not step.active:
                    break
            self.assertFalse(step.active)
            end = app.delivery.end(app.delivery.latest("M1"))  # an accepted attempt is exported on arrival
            self.assertEqual(end.state, "awaiting_merge")
            self.assertIn("ZPLAN_FIXTURE.md", app.delivery.diff_text(app.delivery.latest("M1")))
            with self.assertRaises(Blocked) as raised:  # the merge itself is a new action
                app.delivery.guard("merge")
            self.assertEqual(raised.exception.family, "process.missing")
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")

    def test_required_merge_gate_blocks_merge_and_leaves_the_result_unmerged(self):
        self.run_session("l\n" + PLAN + "a\n" + START + "l\nq\n", profile=True)  # M1 done, awaiting merge
        self.write({"gates": {"merge": "required"}})
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")
        head = self.head()
        with self.app() as app:
            run = app.delivery.latest("M1")
            result = app.delivery.merge(run)
            self.assertEqual(result.kind, "refused")
            self.assertIn("there are no checks", result.line)
            self.assertEqual(self.head(), head)
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")
        self.write({"gates": {"merge": "off"}})
        with self.app() as app:
            self.assertEqual(app.delivery.merge(app.delivery.latest("M1")).kind, "integrated")

    def test_profile_changed_between_preview_and_confirm_is_refused_and_shown_again(self):
        self.accept_file({"roles": {"worker": WORKER}})
        self.approved_plan()
        with self.app() as app:
            preview = app.delivery.preview("M1", app.roles)
            self.assertIn("worker worker-model/low", "\n".join(preview.lines))
            self.write({"roles": {"worker": {"model": "worker-two", "effort": "high"}}})
            with self.assertRaises(ProfileChanged) as raised:
                app.delivery.start(preview, app.roles)
            self.assertEqual(raised.exception.family, "process.changed")
            self.assertEqual(app.authority.state.get("runs", []), [])
            fresh = app.delivery.preview("M1", app.roles)
            self.assertIn("worker worker-two/high", "\n".join(fresh.lines))
            self.assertNotEqual(fresh.profile, preview.profile)
            run = app.delivery.start(fresh, app.roles)
            self.assertEqual(run["roles"]["worker"], {"model": "worker-two", "effort": "high"})

    def test_plain_start_shows_the_new_preview_after_a_change(self):
        self.accept_file({"roles": {"worker": WORKER}})
        self.approved_plan()

        class Edits(ScriptedTerminal):
            changed = False

            def ask(inner, label, default=None):
                if label.startswith("Start M1") and not inner.changed:
                    inner.changed = True
                    self.write({"roles": {"worker": {"model": "worker-two", "effort": "high"}}})
                return super().ask(label, default)
        out = self.run_session("g\ny\ny\nl\nq\n", terminal=Edits("g\ny\ny\nl\nq\n", io.StringIO()))
        self.assertIn("Not started: ", out)
        self.assertIn("The process profile changed", out)  # T2 text (delivery.py), translated by T3
        self.assertEqual(out.count("Start M1 ·"), 2)  # the preview was shown again
        self.assertIn("worker worker-model/low", out)
        self.assertIn("worker worker-two/high", out)
        runs = self.stored()["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["roles"]["worker"], {"model": "worker-two", "effort": "high"})

    def test_watching_stop_and_export_stay_available_without_the_profile(self):
        self.run_session("l\n" + PLAN + "a\n" + START + "l\nq\n", profile=True)
        self.accept_file()  # the "later" profile becomes accepted, then its file goes away
        self.assertTrue(self.file.exists())
        self.file.unlink()
        self.assertEqual(self.peek().status().state, "missing")
        out = self.run_session("o\nl\nq\n", profile=True)  # open the finished run: watching is not a new action
        self.assertIn("M1 · First usable increment — done, waiting for merge", out)
        self.assertIn("profile: error", out)
        with self.app() as app:
            run = app.delivery.latest("M1")
            self.assertIn("ZPLAN_FIXTURE.md", app.delivery.diff_text(run))  # export / diff still work
            with self.assertRaises(Blocked):
                app.delivery.new_attempt(run)

    def test_active_run_can_be_stopped_after_the_profile_is_deleted(self):
        self.accept_file()
        self.approved_plan()
        with self.app() as app:
            run = app.delivery.start(app.delivery.preview("M1", app.roles), app.roles)
            self.assertNotEqual(run["run_id"], None)
        self.remove_accepted_file()
        self.assertEqual(self.peek().status().state, "missing")
        with self.app() as app:
            run = app.delivery.active_run()
            self.assertIsNotNone(run)
            self.assertEqual(app.delivery.stop(run)["status"], "stopping")  # stop has no profile guard

    def test_missing_profile_refuses_new_plan_in_plain_flow_before_the_goal_is_asked(self):
        self.accept_file()
        self.file.unlink()
        out = self.run_session("p\nq\n", profile=True)
        self.assertIn("Not done:", out)
        self.assertIn("was deleted from the project", out)
        self.assertNotIn("(several lines", out)
        self.assertIsNone(self.stored())


# G-A5 ----------------------------------------------------------------------------------------------------------

class LiveRolesTests(ProfileTest):
    """Every new revision or attempt takes the accepted profile's roles as they are now; frozen ones stay."""
    TWO = {"model": "planner-two", "effort": "high"}

    def edited_after(self, setup):
        """An accepted profile with worker-model/low roles, `setup` run in a session, then the file edited."""
        self.accept_file({"roles": {"planner": WORKER, "worker": WORKER}})
        setup()
        self.write({"roles": {"planner": self.TWO, "worker": self.TWO}})

    def planned(self):
        self.run_session("l\n" + PLAN + "q\nq\n")
        self.assertEqual(self.stored()["revisions"][0]["roles"]["planner"], WORKER)

    def needs_owner_run(self, **fixture):
        self.run_session("l\n" + PLAN + "a\n" + START + "l\nq\nq\n", outcome="needs_owner", **fixture)
        run = self.stored()["runs"][0]
        self.assertEqual((run["outcome"], run["roles"]["worker"]), ("needs_owner", WORKER))

    def candidate_run(self):
        """needs_owner whose steward proposal is a structured task-list candidate that fits M1."""
        self.needs_owner_run(proposal=canonical(split_candidate()))

    def test_plan_revision_takes_the_current_profile_roles(self):
        self.edited_after(self.planned)
        with self.app() as app:
            app.planning.revise("Change the plan please")
            revisions = app.authority.state["revisions"]
            self.assertEqual(revisions[0]["roles"]["planner"], WORKER)  # frozen
            self.assertEqual(revisions[-1]["roles"]["planner"], self.TWO)
            self.assertEqual(app.roles["planner"], self.TWO)

    def test_restart_and_renew_take_the_current_profile_roles(self):
        self.edited_after(self.planned)
        with self.app() as app:
            self.assertEqual(app.planning.renew()["roles"]["planner"], self.TWO)
            self.write({"roles": {"planner": WORKER}})
            result = app.planning.restart()
            self.assertEqual(result.kind, "ready")
            self.assertEqual(app.authority.current["roles"]["planner"], WORKER)
            self.assertEqual(app.authority.state["revisions"][0]["roles"]["planner"], WORKER)
            self.assertEqual(app.authority.state["revisions"][1]["roles"]["planner"], self.TWO)

    def attempt_after_edit(self, action):
        self.edited_after(self.needs_owner_run)
        with self.app() as app:
            fresh = action(app.delivery, app.delivery.latest("M1"))
            self.assertEqual(fresh["attempt"], 2)
            self.assertEqual(fresh["roles"]["worker"], self.TWO)
            self.assertEqual(app.authority.state["runs"][0]["roles"]["worker"], WORKER)  # frozen

    def test_new_attempt_takes_the_current_profile_roles(self):
        self.attempt_after_edit(lambda delivery, run: delivery.new_attempt(run))

    def test_answer_takes_the_current_profile_roles(self):
        self.attempt_after_edit(lambda delivery, run: delivery.answer(run, "Use the v2 API."))

    def test_accepted_proposal_takes_the_current_profile_roles(self):
        self.edited_after(self.needs_owner_run)
        with self.app() as app:
            kind, revision = app.delivery.accept(app.delivery.latest("M1"))  # free text: a plan revision
            self.assertEqual(kind, "plan")
            self.assertEqual(revision["roles"]["planner"], self.TWO)
            self.assertEqual(app.authority.state["revisions"][0]["roles"]["planner"], WORKER)

    def test_structured_candidate_attempt_takes_the_current_profile_roles(self):
        self.edited_after(self.candidate_run)
        with self.app() as app:
            kind, fresh = app.delivery.accept(app.delivery.latest("M1"))
            self.assertEqual((kind, fresh["attempt"], fresh["context"]["kind"]), ("attempt", 2, "proposal"))
            self.assertEqual(fresh["roles"]["worker"], self.TWO)
            self.assertEqual(app.authority.state["runs"][0]["roles"]["worker"], WORKER)  # frozen
            self.assertEqual(len(app.authority.state["revisions"]), 1)  # no plan revision

    def test_new_attempt_with_a_note_after_a_structured_candidate_takes_the_current_profile_roles(self):
        self.edited_after(self.candidate_run)
        with self.app() as app:
            fresh = app.delivery.new_attempt(app.delivery.latest("M1"), "Try the smaller route.")
            self.assertEqual(fresh["attempt"], 2)
            self.assertEqual(fresh["roles"]["worker"], self.TWO)
            self.assertEqual(app.authority.state["runs"][0]["roles"]["worker"], WORKER)

    def test_return_to_plan_takes_the_current_profile_roles(self):
        self.edited_after(self.needs_owner_run)
        with self.app() as app:
            revision = app.delivery.to_plan(app.delivery.latest("M1"), "Rethink the scope.")
            self.assertEqual(revision["roles"]["planner"], self.TWO)
            self.assertEqual(app.authority.state["revisions"][0]["roles"]["planner"], WORKER)

    def test_without_a_profile_new_revisions_keep_the_inherited_roles(self):
        self.run_session("l\n" + PLAN + "q\nq\n", profile=False)
        with self.app(profile=False) as app:
            before = app.authority.current["roles"]
            app.planning.revise("Change the plan please")
            self.assertEqual(len(app.authority.state["revisions"]), 2)
            self.assertEqual(app.authority.current["roles"], before)


class BootstrapPlainTests(ProfileTest):
    def test_bootstrap_screen_lists_rules_and_obvious_checks(self):
        (self.project / "AGENTS.md").write_text("rules\n")
        (self.project / "CLAUDE.md").write_text("more rules\n")
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": "node run.js"}}))
        out = self.run_session("l\nq\n")
        self.assertIn("Rules for agents (apply when planning): AGENTS.md, CLAUDE.md", out)
        self.assertIn("Check (qualification, for later stages): npm test", out)
        self.assertIn("[a] accept  [l] later  [q] quit", out)

    def test_makefile_test_target_and_no_obvious_test(self):
        (self.project / "Makefile").write_text("build:\n\ttrue\ntest: build\n\ttrue\n")
        self.assertIn("make test", self.run_session("l\nq\n"))
        for name in ("Makefile",):
            (self.project / name).unlink()
        self.state_reset()
        self.assertIn("Check: no qualification", self.run_session("l\nq\n"))

    def state_reset(self):
        path = self.sidecar()
        if path.exists():
            path.unlink()

    def test_detection_never_executes_anything(self):
        marker = self.root / "marker-created"
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": "touch %s" % marker}}))
        (self.project / "Makefile").write_text("test:\n\ttouch %s\n" % marker)
        with patch("subprocess.Popen", side_effect=AssertionError("a subprocess was started")), \
                patch("subprocess.run", side_effect=AssertionError("a subprocess was run")), \
                patch("os.system", side_effect=AssertionError("os.system")):
            self.assertEqual(process.detect_checks(self.project)[0]["argv"], ["npm", "test"])
            proposal = process.propose(self.project, {})
            self.assertEqual(proposal["checks"][0]["argv"], ["npm", "test"])
            process.bootstrap_lines(process.Status("never", process.resolve(proposal, {}, self.project), False))
        self.run_session("l\nq\n")
        self.assertFalse(marker.exists())

    def test_makefile_alone_is_detected_without_running_anything(self):
        marker = self.root / "marker-created"
        (self.project / "Makefile").write_text("test:\n\ttouch %s\n" % marker)
        self.assertFalse((self.project / "package.json").exists())
        with patch("subprocess.Popen", side_effect=AssertionError("a subprocess was started")), \
                patch("subprocess.run", side_effect=AssertionError("a subprocess was run")), \
                patch("os.system", side_effect=AssertionError("os.system")):
            self.assertEqual(process.detect_checks(self.project)[0]["argv"], ["make", "test"])
            proposal = process.propose(self.project, {})
            self.assertEqual(proposal["checks"][0]["argv"], ["make", "test"])
            lines = process.bootstrap_lines(process.Status("never", process.resolve(proposal, {}, self.project), False))
            self.assertIn("make test", "\n".join(lines))
        self.run_session("l\nq\n")
        self.assertFalse(marker.exists())

    def test_makefile_alone_and_package_without_a_test_script(self):
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": 'echo "Error: no test specified" && exit 1'}}))
        self.assertEqual(process.detect_checks(self.project), [])
        (self.project / "package.json").write_text("{broken")
        self.assertEqual(process.detect_checks(self.project), [])

    def test_leaving_the_screen_decides_nothing(self):
        out = self.run_session("q\nq\n")
        self.assertIn("Profile undecided", out)
        self.assertFalse(self.file.exists())
        self.assertFalse(self.sidecar().exists())
        self.assertEqual(self.peek().status().state, "never")
        out = self.run_session("q\np\nq\n")
        self.assertIn("The project's process profile is not accepted yet", out)  # new work is refused until decided

    def test_existing_valid_file_is_shown_and_offers_no_later(self):
        self.write({"roles": {"worker": WORKER}})
        before = self.file.read_bytes()
        out = self.run_session("a\nq\n")
        self.assertIn("found zplan.process.json", out)
        self.assertIn("[a] accept  [q] quit", out)
        self.assertNotIn("[l] later", out)
        self.assertIn("The file is unchanged.", out)
        self.assertEqual(self.file.read_bytes(), before)

    def test_fixture_walkthrough_reaches_a_plan_after_later(self):
        out = self.run_session("l\n" + PLAN + "a\nq\n")
        self.assertIn("Plan r1 approved", out)
        self.assertEqual(self.stored()["revisions"][0]["status"], "approved")
        self.assertEqual(self.stored()["revisions"][0]["roles"]["planner"], {"model": "gpt-6.1-sol", "effort": "high"})


class BootstrapPtyTests(tt.PtyTest):
    def test_plain_mode_on_a_terminal_gets_the_same_choice_as_a_line_prompt(self):
        output, status = self.pty(self.cli("--plain"), [("[l] later".encode(), b"l\n"), ("[p] plan".encode(), b"q\n")])
        text = output.decode()
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, text)
        self.assertNotIn("\x1b", text)
        self.assertIn("Project process profile", text)
        self.assertIn("profile not saved", text)
        self.assertFalse((self.project / process.PROFILE_FILE).exists())

    def test_term_dumb_shows_the_choice_as_a_line_prompt_too(self):
        output, status = self.pty(self.cli(), [("[l] later".encode(), b"l\n"), ("[p] plan".encode(), b"q\n")], TERM="dumb")
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, output.decode())
        self.assertNotIn(b"\x1b", output)


# G-A6 / G-A7 ---------------------------------------------------------------------------------------------------

class OutputTests(ProfileTest):
    def test_profile_command_prints_state_digest_roles_with_sources_gates_and_checks(self):
        self.write({"roles": {"worker": WORKER}})
        self.accept_file()
        code, out, _ = self.zplan(*self.fixture_args("profile"))
        self.assertEqual(code, 0, out)
        digest = self.peek().status().resolved.short
        for needle in ("Process profile: accepted", "file zplan.process.json", "digest " + digest,
                       "role worker    worker-model / low  [zplan.process.json]",
                       "role planner   gpt-6.1-sol / high  [preset zplan.default/1]",
                       "plan check: required", "task check: no check", "merge check: no check",
                       "checks: no qualification"):
            self.assertIn(needle, out)

    def test_profile_command_in_a_project_without_a_file_does_not_create_one(self):
        code, out, _ = self.zplan(*self.fixture_args("profile"))
        self.assertEqual(code, 0)
        self.assertIn("not accepted", out)
        self.assertFalse(self.file.exists())

    def test_profile_command_reports_a_broken_file_with_exit_1(self):
        self.write({"roles": {"worker": {"model": "m", "effort": "nope"}}})
        code, out, _ = self.zplan(*self.fixture_args("profile"))
        self.assertEqual(code, 1)
        self.assertIn("roles.worker.effort", out)

    def test_doctor_shows_the_profile_and_never_prompts(self):
        self.write({"checks": [{"name": "unit", "argv": ["python3", "-m", "unittest"], "timeout_s": 60}]})
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}):  # doctor reads the production store
            with RealAuthority(None, self.project) as authority:
                Profile.of(authority).accept()
        code, out, err = self.zplan("doctor", "--project", str(self.project))
        self.assertNotIn("Traceback", err)
        self.assertIn("Process profile: accepted", out)
        self.assertIn("digest ", out)
        self.assertIn("role critic", out)
        self.assertIn("unit: python3 -m unittest (60 s)", out)
        self.assertNotIn("Choice", out)

    def test_doctor_from_a_subdirectory_sees_the_accepted_profile(self):
        self.write({})
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}):
            with RealAuthority(None, self.project) as authority:
                Profile.of(authority).accept()
        sub = self.project / "sub"
        sub.mkdir()
        for args, cwd in ((("doctor",), sub), (("doctor", "--project", str(sub)), self.project)):
            code, out, err = self.zplan(*args, cwd=cwd)
            self.assertNotIn("Traceback", err)
            self.assertIn("Process profile: accepted", out)
            self.assertNotIn("deleted", out)

    def test_doctor_works_outside_git(self):
        outside = Path(tempfile.mkdtemp(prefix="zs-nogit-"))
        self.addCleanup(lambda: outside.rmdir())
        code, out, err = self.zplan("doctor", cwd=outside)
        self.assertNotIn("Traceback", err)
        self.assertIn("Process profile: no project selected", out)

    def test_status_doctor_profile_and_help_never_ask_or_run_anything(self):
        marker = self.root / "marker"
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": "touch %s" % marker}}))
        for args in (self.fixture_args("status"), self.fixture_args("profile"), ["doctor", "--project", str(self.project)],
                     ["help", "profile"], ["roles", "--help"]):
            with self.subTest(args):
                code, out, err = self.zplan(*args, stdin=b"")
                self.assertNotIn("Choice", out)
                self.assertNotIn("): proposal.", out)  # the bootstrap screen is not shown
                self.assertNotIn("Traceback", err)
                self.assertNotIn("Session closed", out)
        self.assertFalse(marker.exists())
        self.assertFalse(self.file.exists())

    def test_roles_command_with_a_project_file_shows_the_roles_and_changes_nothing(self):
        self.write({"roles": {"worker": WORKER}})
        code, out, _ = self.zplan("roles", "--project", str(self.project), stdin=b"")
        self.assertEqual(code, 0, out)
        self.assertIn("role worker", out)
        self.assertIn("live in zplan.process.json", out)
        self.assertFalse((self.config / "planning-kit" / "roles.json").exists())

    def test_roles_command_without_a_file_edits_roles_json_as_before(self):
        answers = "\n".join([""] * 10) + "\n"
        code, out, _ = self.zplan("roles", "--project", str(self.project), stdin=answers.encode())
        self.assertEqual(code, 0, out)
        self.assertIn("Role defaults were saved", out)
        self.assertTrue((self.config / "planning-kit" / "roles.json").exists())

    def test_help_and_catalog_name_the_profile_command(self):
        code, out, _ = self.zplan("help", "profile")
        self.assertEqual(code, 0)
        self.assertIn("zplan profile [init]", out)


# TUI -----------------------------------------------------------------------------------------------------------

@unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required for Pilot tests")
class BootstrapTuiTests(tt.ShellTest):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        # i6: this class points the config root at its own tree, so the `ru` pin `tests/tui_support.py` sets for the
        # whole process does not reach it. Storing a language keeps the first-run chooser from being pushed before
        # `BootstrapScreen`, which is the modal these tests assert.
        ui = self.root / "config" / "planning-kit" / "ui.json"
        ui.parent.mkdir(parents=True, exist_ok=True)
        ui.write_text('{"language": "ru"}\n', encoding="utf-8")

    def profile_controller(self):
        return self.controller(profile=True)

    async def bootstrap(self, pilot):
        await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "BootstrapScreen")
        await pilot.pause(0.1)

    async def test_bootstrap_screen_fits_80x24_and_later_keeps_the_profile_unsaved(self):
        """Choosing «later» leaves the profile unsaved: its state stays `later` and no project file is written.

        i9-look interpretation: the removed `#header` used to spell this out (`process.LATER_NOTE`, «profile not
        saved»); the screen now keeps the profile's own state (`Snapshot.profile`, `process.View.state`)
        instead of a header line, so the note is read from there.
        """
        async with self.shell(self.profile_controller(), size=(80, 24)) as pilot:
            await self.bootstrap(pilot)
            lines = screen_lines(self.app)
            self.assertEqual(len(lines), 24)
            body = "\n".join(lines)
            self.assertIn("Project process profile", body)
            self.assertIn("Accept", body)
            self.assertIn("[ctrl+q] quit", lines[-1])
            await self.press_button(pilot, "later")
            await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "MainScreen")
            await self.until(pilot, lambda: self.app.snapshot.profile.state == "later")
            await pilot.pause(0.1)
            self.assertEqual(self.app.snapshot.profile.note, process.LATER_NOTE)  # «profile not saved»
        self.assertFalse((self.project / process.PROFILE_FILE).exists())

    async def test_bootstrap_screen_at_120x40_and_demo_accept_keeps_the_snapshot(self):
        """R-3: the full-screen accept of a `--fixture test` session keeps the accepted snapshot in the fixture
        state and writes no project file; the state is accepted, not later."""
        (self.project / "AGENTS.md").write_text("rules\n")
        (self.project / "package.json").write_text(json.dumps({"scripts": {"test": "node run.js"}}))
        async with self.shell(self.profile_controller(), size=(120, 40)) as pilot:
            await self.bootstrap(pilot)
            text = screen_text(self.app)
            self.assertIn("Rules for agents (apply when planning): AGENTS.md", text)
            self.assertIn("Check (qualification, for later stages): npm test", text)
            await pilot.press("enter")  # the focus starts on «accept»
            await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "MainScreen")
            await self.until(pilot, lambda: self.app.snapshot.profile.state == "accepted")
            await pilot.pause(0.1)
            self.assertNotIn("profile not saved", screen_text(self.app))
        self.assertFalse((self.project / process.PROFILE_FILE).exists())
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            record = process.read_record(authority.directory)
        self.assertEqual(record["state"], "accepted")
        self.assertEqual(record["snapshot"]["config"]["rules"], ["AGENTS.md"])
        self.assertEqual(record["snapshot"]["config"]["checks"][0]["argv"], ["npm", "test"])

    async def test_existing_file_offers_no_later_and_keys_do_nothing_else(self):
        (self.project / process.PROFILE_FILE).write_text('{"roles": {}}')
        async with self.shell(self.profile_controller(), size=(80, 24)) as pilot:
            await self.bootstrap(pilot)
            self.assertNotIn("later", screen_lines(self.app)[-1])
            self.assertEqual([b.id for b in self.app.screen.query("Button")], ["bootstrap-accept"])
            await pilot.press("l", "tab", "right")
            await pilot.pause(0.2)
            self.assertEqual(self.app.screen.__class__.__name__, "BootstrapScreen")
            await pilot.press("escape")
            await pilot.pause(0.1)
            self.assertEqual(self.app.screen.__class__.__name__, "BootstrapScreen")
            await pilot.press("enter")
            await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "MainScreen")
        self.assertEqual((self.project / process.PROFILE_FILE).read_text(), '{"roles": {}}')

    async def test_settings_show_the_profile_state_digest_roles_and_checks(self):
        (self.project / process.PROFILE_FILE).write_text(json.dumps({"roles": {"worker": WORKER}}))
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            Profile.of(authority).accept()
        async with self.shell(self.profile_controller(), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the input has the start focus; [s] is a pane key
            await self.command(pilot, "/setup")
            await self.until(pilot, lambda: "Process profile" in screen_text(self.app))
            # the summary line is long enough to wrap, so the readiness pane (max-height: 50%) scrolls: its own
            # content, not the visible screen text, is what Settings renders and what these needles check.
            text = self.app.screen.query_one("#checks").content.plain
            for needle in ("accepted", "digest ", "role worker", "worker-model / low", "plan check: required",
                           "no check", "no qualification"):
                self.assertIn(needle, text)

    async def test_deleted_profile_blocks_a_new_plan_and_the_screen_names_the_error(self):
        # A real, committed file profile (a native accepted record beside the file: a fixture accept would keep its
        # snapshot), then the file goes away: the deletion is what must refuse.
        (self.project / process.PROFILE_FILE).write_text("{}")
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            Profile(self.project, authority.directory, authority).accept()
        (self.project / process.PROFILE_FILE).unlink()
        controller = self.profile_controller()
        async with self.shell(controller, size=(120, 40)) as pilot:
            await self.loaded(pilot)
            # i9-look: the removed `#header` used to spell «profile: error»; the screen keeps the profile's own
            # state (`Snapshot.profile`, `process.header_note`) instead, and the plan start is refused below.
            self.assertEqual((self.app.snapshot.profile.state, self.app.snapshot.profile.note),
                             ("missing", "profile: error"))
            outcomes = []
            controller.start_planning("A goal", lambda outcome, error: outcomes.append((outcome, error)))
            await self.until(pilot, lambda: outcomes)
            self.assertIsNone(outcomes[0][0])
            self.assertIn("was deleted from the project", outcomes[0][1])
        self.assertIsNone(self.stored_state())

    def stored_state(self):
        with tp.Authority(self.state, self.project) as authority:
            return authority.state


@unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required for Pilot tests")
class GateTuiTests(ProfileTest, tt.ShellTest):
    """The refusals of an unbuilt gate or a missing profile in the full-screen UI: shown, and nothing changes."""

    async def refusal(self, pilot, family, text):
        """The refusal with its family code is on the screen (panels wrap it: the text is matched by its start)."""
        await self.until(pilot, lambda: family + "]" in screen_text(self.app))
        self.assertIn(text, screen_text(self.app))

    async def test_required_task_gate_refuses_the_start_and_creates_nothing(self):
        self.accept_file({"gates": {"task": "required"}})
        self.approved_plan()
        head, state = self.head(), self.stored()
        async with self.shell(self.controller(profile=True), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the input has the start focus; [g] is a pane key
            await self.command(pilot, "/run")
            await self.refusal(pilot, "process.unbuilt", "the task check is not built yet")
            self.assertNotIn("Start M1", screen_text(self.app))
        self.assertEqual((self.head(), self.stored()), (head, state))
        self.assertFalse((self.root / "fixture-runs").exists() and any((self.root / "fixture-runs").iterdir()))

    async def merge_refused(self, family, text):
        head, state = self.head(), self.stored()
        async with self.shell(self.controller(profile=True), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the input has the start focus; [o] is a pane key
            await self.command(pilot, "/attempt")
            await self.run_button(pilot, "merge")
            await self.press_button(pilot, "merge")
            await self.until(pilot, lambda: "Merge the result of M1 into main?" in screen_text(self.app))
            await self.press_button(pilot, "yes")
            await self.refusal(pilot, family, text)
            self.assertNotIn("Merged:", screen_text(self.app))
        self.assertEqual((self.head(), self.stored()), (head, state))
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")

    async def test_required_merge_gate_refuses_the_merge(self):
        self.awaiting_merge()
        self.write({"gates": {"merge": "required"}})
        await self.merge_refused("merge.no_checks", "there are no checks")

    async def test_deleted_profile_refuses_the_merge(self):
        self.awaiting_merge()
        self.accept_file({})  # a real file profile over the same store, then its file goes away
        self.file.unlink()
        await self.merge_refused("process.missing", "The accepted profile")


class RepositoryProfileTests(unittest.TestCase):
    """A4/D6: this repository's own zplan.process.json runs the plan critic at `high` - the frozen preset's value -
    and still loads through the resolver `zplan profile` uses, with no new key and so nothing new to accept.

    The peek is read-only over a fixture directory, but its roles.json comes from `config_root()` (HOME/XDG): the
    test isolates both into the scratch tree, like the profile tests, so a personal roles.json is never read."""

    def test_the_repository_profile_runs_the_critic_at_high_and_still_loads(self):
        document = json.loads((ROOT / process.PROFILE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(document["roles"]["critic"], {"model": "gpt-6.1-sol", "effort": "high"})
        self.assertLessEqual(set(document), set(process.TOP_KEYS))
        with tempfile.TemporaryDirectory() as scratch:
            with patch.dict(os.environ, {"HOME": scratch, "XDG_CONFIG_HOME": scratch}):
                status = process.Profile.peek(ROOT, root=scratch, fixture_id="a4").status(write=False)
            self.assertTrue(status.present)
            self.assertEqual(status.problem, "")
            self.assertIsNotNone(status.resolved)
            # The file binds the worker itself (terra / max, since a3abe5e); every other role is the preset's.
            roles = dict(process.resolve(None, {}, ROOT).config["roles"], worker=document["roles"]["worker"])
            self.assertEqual(status.resolved.config["roles"], roles)
            self.assertEqual(status.resolved.config["limits"], process.resolve(None, {}, ROOT).config["limits"])

    def test_the_summary_line_reports_the_task_rounds_in_effect(self):
        """A1/A2: the profile summary shows the task rounds as in effect beside the plan rounds, each with the
        source marker the plan rounds already use, and keeps "for later stages" on the merge only - the task
        rounds stopped being a "later stage" when limits.task_rounds began bounding the milestone review loop
        (f6c1db0). Asserted for this repository's own profile (the file source) and for the frozen preset default.

        Interpretations: none to resolve - the task gives the target line ("rounds: plan 3 [..]; task retries 2
        [..]; merge 2 (for later stages)") and the marker text; the `where()` helper renders the marker as
        two spaces before "[...]", which the exact strings below keep."""
        def rounds(status):
            return next(line for line in process.describe(status) if line.startswith("  rounds:"))

        with tempfile.TemporaryDirectory() as scratch:
            with patch.dict(os.environ, {"HOME": scratch, "XDG_CONFIG_HOME": scratch}):
                status = process.Profile.peek(ROOT, root=scratch, fixture_id="c0a2").status(write=False)
        self.assertEqual(rounds(status),
                         "  rounds: plan 3  [zplan.process.json]; task retries 2  [zplan.process.json]; "
                         "merge 2 (for later stages)")
        self.assertEqual(rounds(process.Status("accepted", process.resolve(None, {}, ROOT), True)),
                         "  rounds: plan 3  [preset zplan.default/1]; task retries 2  [preset zplan.default/1]; "
                         "merge 2 (for later stages)")


if __name__ == "__main__":
    unittest.main()
