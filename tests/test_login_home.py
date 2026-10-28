"""D6a: zplan logs in and out only of the Codex home it owns.

A fake `codex` (a shell script that appends its argv to a log) stands in for the pinned Codex; HOME, XDG and
CODEX_HOME are scratch paths, never the runner's. Each test fails on the code before D6a (which ran `login
--device-auth` in whatever home it was given, had no `logout` and no copy check).

Interpretations (the reviewers never see the worker's summary):
- L1 "exit 0 if logged in else 1" in a home that is not owned is judged by presence of the login (`auth.json`, or a
  provider that needs none) and not by running `codex login status`, because the same criterion says no Codex runs.
- L2/L4 "refused while a run or the architect is live there": a run record of any project store whose status is
  active (or a planner revision observed, or a planned one with a run id) and whose recorded home is the owned one, or
  an architect lock held by another process whose session did not record another home. Refusals are `action.refused`.
- L3 "rm <path>" is the same text for a symlink, a non-regular entry and a byte copy; the message never names logout.
- L4's "asks to confirm" is the `confirm` callable of `setup.login(refresh=True)`; declining changes nothing.
"""

import fcntl
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner import cli, planning, setup
from terminal_planner.authority import Blocked, production_root
from terminal_planner.cli import Terminal, main

FAKE = """#!/bin/sh
echo "$@" >> "$FAKE_CODEX_LOG"
case "$*" in *"login status"*) exit "${FAKE_CODEX_STATUS:-1}" ;; esac
exit 0
"""
STATUS = '-c cli_auth_credentials_store="file" login status'
DEVICE = '-c cli_auth_credentials_store="file" login --device-auth'
BINDING = {"executable": "/opt/zeroshot", "state_root": "/tmp/zp", "sha256": "a" * 64, "version": "zeroshot 10.16.0"}


class LoginHomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.log = self.root / "codex.log"
        environment = patch.dict(os.environ, {"HOME": str(self.home), "XDG_DATA_HOME": str(self.root / "data"),
                                              "XDG_CONFIG_HOME": str(self.root / "config"),
                                              "FAKE_CODEX_LOG": str(self.log), "FAKE_CODEX_STATUS": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY"):
            os.environ.pop(name, None)
        for patcher in (patch.object(setup, "platform_key", return_value=("Darwin", "arm64")),
                        patch.object(setup, "check_installation", return_value=setup.tools_root())):
            patcher.start()
            self.addCleanup(patcher.stop)
        codex = setup.tool_paths()[1]
        codex.parent.mkdir(parents=True)
        codex.write_text(FAKE)
        codex.chmod(0o755)
        self.private = setup.private_codex_home()
        self.shown = []

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def login(self, **options):
        return setup.login(self.shown.append, **options)

    def mine(self, name="mine", login=True):
        """The owner's own Codex home (an override), with or without a login."""
        mine = self.root / name
        mine.mkdir()
        if login:
            (mine / "auth.json").write_text('{"tokens": "theirs"}\n')
        return mine

    def own_auth(self, content='{"tokens": "private"}\n'):
        self.private.mkdir(parents=True, exist_ok=True)
        (self.private / "auth.json").write_text(content)

    # L1 -----------------------------------------------------------------------------------------------------

    def test_l1_a_home_that_is_not_owned_runs_no_codex(self):
        for login, code in ((True, 0), (False, 1)):
            with self.subTest(login=login):
                mine = self.mine("mine%s" % login, login)
                with patch.dict(os.environ, {"CODEX_HOME": str(mine)}):
                    self.assertEqual(self.login(), code)
                    self.assertEqual(setup.logout(self.shown.append), code)
                self.assertIn("This is your Codex (%s): log in via codex login" % mine, self.shown)
                self.assertFalse(self.log.exists())  # no codex process

    def test_l1_the_private_home_counts_as_owned_however_it_is_spelled(self):
        self.private.mkdir(parents=True)
        alias = self.root / "alias"
        alias.symlink_to(self.private)
        for spelling in (self.private, alias, str(self.private) + "/"):
            with self.subTest(spelling=str(spelling)):
                self.assertTrue(setup.owned_home(spelling))
                self.log.unlink(missing_ok=True)
                with patch.dict(os.environ, {"CODEX_HOME": str(spelling)}):
                    self.login()
                self.assertEqual(self.calls()[0], STATUS)
        self.assertFalse(setup.owned_home(self.mine()))

    # L2 -----------------------------------------------------------------------------------------------------

    def test_l2_an_existing_login_is_kept_and_nothing_else_runs(self):
        os.environ["FAKE_CODEX_STATUS"] = "0"
        self.assertEqual(self.login(), 0)
        self.assertEqual(self.calls(), [STATUS])
        self.assertIn("Login already present", self.shown)

    def test_l2_no_login_runs_the_device_login_after_the_status(self):
        self.assertEqual(self.login(), 0)
        self.assertEqual(self.calls(), [STATUS, DEVICE])

    def test_l2_logout_runs_codex_logout_in_the_owned_home_only(self):
        self.assertEqual(setup.logout(self.shown.append), 0)
        self.assertEqual(self.calls(), ["logout"])

    def test_l2_logout_is_refused_while_a_run_or_the_architect_is_live_there(self):
        store = production_root() / ("p" * 64)
        store.mkdir(parents=True)
        run = {"status": "running", "binding": dict(BINDING, codex_home=str(self.private))}
        elsewhere = {"status": "running", "binding": dict(BINDING, codex_home=str(self.mine()))}
        planner = {"status": "observing", "run_id": "r1", "native_binding": dict(BINDING, codex_home=str(self.private))}
        for state in ({"runs": [run]}, {"revisions": [planner]}):
            with self.subTest(state=sorted(state)):
                (store / "planning.json").write_text(json.dumps(state))
                with self.assertRaises(Blocked) as raised:
                    setup.logout(self.shown.append)
                self.assertEqual(raised.exception.family, "action.refused")
        (store / "planning.json").write_text(json.dumps({"runs": [elsewhere, dict(run, status="finished")]}))
        self.assertEqual(setup.logout(self.shown.append), 0)  # a run elsewhere or a finished one is no reason
        self.log.unlink()
        lock = setup.data_root() / "architect" / "project-1" / "lock"
        lock.parent.mkdir(parents=True)
        with lock.open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Blocked):
                setup.logout(self.shown.append)
        self.assertFalse(self.log.exists())  # Codex was never called by a refusal

    def test_l2_the_logout_command_is_wired_and_documented(self):
        output = io.StringIO()
        with patch("terminal_planner.cli.Terminal", return_value=Terminal(io.StringIO(), output)):
            self.assertEqual(main(["logout"]), 0)
        self.assertEqual(self.calls(), ["logout"])
        self.assertIn("logout", cli.commands.NAMES)

    # L3 -----------------------------------------------------------------------------------------------------

    def test_l3_a_copied_private_auth_json_blocks_login_logout_and_doctor(self):
        owner = self.home / ".codex"
        owner.mkdir()
        (owner / "auth.json").write_text('{"tokens": "owner-token"}\n')
        before = (owner / "auth.json").read_bytes()
        self.own_auth('{"tokens": "owner-token"}\n')  # the same bytes
        path = self.private / "auth.json"
        cases = {"copy": lambda: None,
                 "symlink": lambda: (path.unlink(), path.symlink_to(owner / "auth.json")),
                 "directory": lambda: (path.unlink(), path.mkdir())}
        for name, make in cases.items():
            with self.subTest(name):
                if path.is_symlink() or path.is_dir():
                    path.unlink() if path.is_symlink() else path.rmdir()
                    self.own_auth('{"tokens": "owner-token"}\n')
                make()
                for action in (lambda: self.login(), lambda: setup.logout(self.shown.append),
                               lambda: self.login(refresh=True, confirm=lambda question: True)):
                    with self.assertRaises(Blocked) as raised:
                        action()
                    self.assertEqual(raised.exception.family, "readiness.auth")
                    text = str(raised.exception)
                    self.assertTrue(text.startswith("remove the copy: rm %s" % path), text)
                    self.assertNotIn("logout", text)
                    self.assertNotIn("owner-token", text)
                self.assertFalse(self.log.exists())  # Codex never ran, so nothing was revoked
                auth = next(c for c in setup.readiness(None) if c["id"] == "auth")
                self.assertFalse(auth["ok"])
                self.assertIn("remove the copy: rm %s" % path, auth["doctor"])
        self.assertEqual((owner / "auth.json").read_bytes(), before)

    def test_l3_a_login_of_its_own_is_not_a_copy(self):
        self.own_auth('{"tokens": "private"}\n')
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "auth.json").write_text('{"tokens": "owner-token"}\n')
        self.assertIsNone(setup.copied_auth(self.private))
        auth = next(c for c in setup.readiness(None) if c["id"] == "auth")
        self.assertTrue(auth["ok"])

    # L4 -----------------------------------------------------------------------------------------------------

    def failed_view(self, home):
        report = type("Report", (), {"failure_cause": staticmethod(lambda authority: "auth")})()
        binding = dict(BINDING, codex_home=str(home))
        return planning.Planning(None, None, lambda name, terminal: report).failure(
            {"version": 1, "status": "run_failed", "engine": "native", "run_id": None, "diagnostic": "planner_failed",
             "native_binding": binding}, "Цель")

    def test_l4_the_auth_failure_action_targets_the_recorded_home(self):
        mine = self.mine()
        view = self.failed_view(mine)
        self.assertEqual(view.home, str(mine))
        self.assertIn("login", view.actions)
        calls = []
        stub = type("App", (), {"planning": type("P", (), {"view": staticmethod(lambda: view)})(),
                                "attempt": lambda self, action, key: action(),
                                "login": lambda self, **options: calls.append(options)})()
        cli.App.relogin(stub)
        self.assertEqual(calls, [{"home": str(mine), "refresh": True}])
        # in an override home the login answers with the L1 message and starts no Codex, whatever the process home is
        self.assertEqual(self.login(home=view.home, refresh=True), 0)
        self.assertIn("This is your Codex (%s): log in via codex login" % mine, self.shown)
        self.assertFalse(self.log.exists())

    def test_l4_in_the_owned_home_it_confirms_then_logs_out_and_in(self):
        asked = []
        with self.assertRaises(Blocked) as raised:  # declined: nothing runs
            self.login(home=self.private, refresh=True, confirm=lambda question: asked.append(question) or False)
        self.assertEqual(raised.exception.family, "action.refused")
        self.assertEqual(len(asked), 1)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.login(home=self.private, refresh=True, confirm=lambda question: True), 0)
        self.assertEqual(self.calls(), ["logout", DEVICE])

    # L5 -----------------------------------------------------------------------------------------------------

    def test_l5_no_text_sends_zplan_into_the_owners_codex_home(self):
        root = Path(__file__).resolve().parents[1]
        files = [*sorted((root / "terminal_planner").rglob("*.py")), root / "README.md", *sorted((root / "docs").glob("*.md"))]
        for path in files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                self.assertNotIn("CODEX_HOME=$HOME/.codex zplan login", text)
                self.assertNotIn("CODEX_HOME=... zplan login", text)
                self.assertNotIn("log in to your own Codex directory", text)
        upgrade = (root / "docs" / "UPGRADE.md").read_text(encoding="utf-8")
        self.assertIn("copied `auth.json`", upgrade)
        self.assertIn("rm ~/.local/share/planning-kit/codex-home/auth.json", upgrade)


if __name__ == "__main__":
    unittest.main()
