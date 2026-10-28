"""D5: refusals on the normal path that protected nothing (E2-E6), each with a fixture and no provider.

Interpretations (none changes a stated requirement):
- E2: "the checks it needs" is `planning.TOOL_CHECKS` as the slice reports them: the chat retries when every tool
  check the slice carries passes; a slice that carries none of them (and so says nothing about the tools) retries
  nothing.
- E3: the refusals named for `runs.py` start and merge get the family their fix lives in: a destination branch that
  is not the checked-out one and a merge on another branch are `readiness.branch` (its remedy is `git switch`); a
  stale, unapproved or missing plan/milestone and a milestone waiting for another merge are `action.refused`.
- E4: [g] on a plan left in `submission_unknown` is `Planning.send`; it checks readiness, and the next watch slice
  sends the same frozen documents with the same submission key (`NativeEngine.proposal(resubmit=True)`). The
  scripted binary stands for the engine's deduplication, which is Zeroshot's own (upstream local.rs), not zplan's.
  "The same run id": the receipt of the second `--detach` is the run the plan then observes.
- E5: an interrupted clone is discarded only where nothing was prepared and nothing submitted: a plan with
  `native_prepared` false, a task gate or merge critic record whose frozen documents are not all on disk. A
  prepared revision whose checkout is gone is still refused.
- E6: Node.js/npm are checked before anything is installed when `install.py` runs by itself; when the caller runs
  `zplan setup` itself (`ZPLAN_SETUP_FOLLOWS`), install.py only drops the next-step hint, since that setup refuses
  in its own line right after.
"""

import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_runs
import test_task_gate_record as gates
import test_terminal_planner as planner
from terminal_planner import catalog, engine as engine_module, planning
from terminal_planner.authority import Blocked
from terminal_planner.planning import Planning, Watch
from terminal_planner.tui import controller as controller_module
from tui_support import HAVE_TEXTUAL
import test_tui_chat as chat_tests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install  # noqa: E402

ROLES = planner.ROLES


def check(name, ok=True):
    return controller_module.Check(name, ok, name, "", "", None)


# E2 ---------------------------------------------------------------------------------------------------------

@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class ChatRetryTests(unittest.TestCase):
    def test_only_the_tool_checks_decide_the_chat(self):
        from terminal_planner.tui.app import tools_pass  # the app module imports Rich at load
        needed = [check(name) for name in planning.TOOL_CHECKS]
        self.assertTrue(tools_pass(needed + [check("identity", False), check("branch", False)]))
        self.assertFalse(tools_pass([check("auth", False)] + [check(n) for n in planning.TOOL_CHECKS if n != "auth"]))
        self.assertFalse(tools_pass([check("identity")]))  # a slice that says nothing about the tools
        self.assertFalse(tools_pass(()))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class ChatRetryAppTests(chat_tests.ChatShell):
    async def test_e2_login_done_with_no_git_identity_still_lets_the_chat_answer(self):
        """No login + no Git identity -> `zplan login` done -> the chat prepares again without a restart; the
        identity check is still failing in the same slice (it blocks only a milestone start)."""
        fixed = chat_tests.threading.Event()
        calls = []
        build = self.fixture.prepare()

        def flaky(project=None):
            calls.append(project)
            if not fixed.is_set():
                raise Blocked("No Codex login; run zplan login.", family="readiness.auth")
            return build(project)

        async with self.shell(chat_prepare=flaky) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.chat.state.phase == "blocked")
            fixed.set()  # `zplan login` finished
            slice_ = tuple(check(name) for name in planning.TOOL_CHECKS) + (check("identity", False),)
            self.app.got_checks(slice_, None)
            await self.until(pilot, lambda: self.app.chat.state.phase == "ready")
            self.assertEqual(len(calls), 2)
            self.assertTrue(self.app.send_chat("теперь можно")[0])
            await self.chat_done(pilot)


# E3 ---------------------------------------------------------------------------------------------------------

class FamilyTests(test_runs.RunsTest):
    def refused(self, call, family):
        with self.assertRaises(Blocked) as raised:
            call()
        self.assertEqual(catalog.family(raised.exception), family)
        self.assertNotEqual(catalog.family(raised.exception), "store.invalid")
        return raised.exception

    def test_e3_start_refusals_carry_the_family_their_fix_lives_in(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            elsewhere = self.refused(lambda: controller.start("M1", 1, ROLES, destination="release"),
                                     "readiness.branch")
            self.assertIn("git switch release", str(elsewhere))
            self.assertIn("git switch", catalog.ERRORS["readiness.branch"].remedy)
            self.refused(lambda: controller.start("M9", 1, ROLES), "action.refused")
            self.refused(lambda: controller.start("M1", 2, ROLES), "action.refused")
            self.assertEqual(a.state.get("runs", []), [])  # nothing was recorded by the refusals

    def test_e3_merge_on_another_branch_names_the_branch_family(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            r = controller.observe(controller.start("M1", 1, ROLES))
            controller.finish(r)
            self.git("checkout", "-q", "-b", "elsewhere")
            error = self.refused(lambda: controller.merge(r), "readiness.branch")
            self.assertIn("git switch main", str(error))
            self.assertIn("[code: readiness.branch]", catalog.tag(catalog.family(error)))
            self.assertEqual(r["delivery"], "awaiting_merge")


# E4 and E5 --------------------------------------------------------------------------------------------------

class NativePlanTests(planner.ProjectTest):
    native = planner.NativeTests.native
    engine = planner.NativeTests.engine
    projection = planner.NativeTests.projection
    terminal = planner.NativeTests.terminal
    running = planner.NativeTests.running

    def authority(self):
        return planner.RealAuthority(None, self.project)

    def planning(self, authority, native):
        return Planning(authority, None, lambda name, terminal: native)

    def detached(self, calls):
        return [argv for argv, _ in calls if argv[1] == "run" and "--detach" in argv]

    def test_e4_g_on_an_unconfirmed_submission_sends_the_same_documents_under_the_same_key(self):
        """Fixture driver times out once -> [g] -> the same submission key and frozen documents go out again, the
        receipt is the run the plan observes, and the plan proceeds."""
        first, calls = self.engine([{"valid": True}, subprocess.TimeoutExpired("zeroshot", 120)])
        with self.authority() as a:
            self.begin(a, "native")
            with self.assertRaises(Blocked):
                first.proposal(a, lambda _: None)
            key, documents = a.current["submission_key"], copy.deepcopy(a.current["native_documents"])
        again, more = self.engine([{"valid": True}, {"runId": "fixture-native-run"},
                                   (self.running(), self.terminal())])
        with self.authority() as a:
            native_planning = self.planning(a, again)
            view = native_planning.view()
            self.assertEqual((view.kind, view.family), ("unknown", "submission.unknown"))
            self.assertIn("start", view.actions)  # the plan screen offers [g]
            with self.assertRaises(Blocked):  # nothing resends it by itself, whoever watches
                again.proposal(a, lambda _: None)
            self.assertEqual(more, [])
            self.assertEqual(native_planning.send().kind, "ready")
            self.assertEqual(a.current["status"], "submission_unknown")  # [g] decides; the watch sends
            watch = Watch(native_planning, lambda _: None)
            self.assertEqual(watch.step(), "done")
            self.assertEqual((a.current["run_id"], a.current["status"], a.current["submission_key"]),
                             ("fixture-native-run", "proposed", key))
            self.assertEqual(a.current["native_documents"], documents)
        sent = self.detached(calls) + self.detached(more)
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], sent[1])  # same documents, same key
        self.assertIn(key, sent[1])

    def test_e4_a_blocked_readiness_sends_nothing(self):
        first, _ = self.engine([{"valid": True}, subprocess.TimeoutExpired("zeroshot", 120)])
        with self.authority() as a:
            self.begin(a, "native")
            with self.assertRaises(Blocked):
                first.proposal(a, lambda _: None)
        again, more = self.engine([])
        with self.authority() as a:
            native_planning = Planning(a, None, lambda name, terminal: again,
                                       readiness=lambda: [{"id": "auth", "ok": False, "line": "auth", "detail": "",
                                                           "doctor": "", "key": None}])
            result = native_planning.send()
            self.assertEqual(result.kind, "blocked")
            self.assertIsNone(native_planning.resubmit)
        self.assertEqual(more, [])

    def test_e5_a_clone_a_kill_left_behind_is_removed_and_cloned_again(self):
        """Leftover planner checkout dir from a kill -> the next plan plans."""
        native, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"},
                                     (self.running(), self.terminal())])
        with self.authority() as a:
            self.begin(a, "native")
            checkout = a.directory / "revision-1" / "checkout"
            checkout.mkdir(parents=True)
            (checkout / "half-cloned").write_text("x")
            self.assertFalse(a.current["native_prepared"])
            native.proposal(a, lambda _: None)
            self.assertEqual(a.current["status"], "proposed")
            self.assertFalse((checkout / "half-cloned").exists())
            self.assertTrue((checkout / ".git").exists())

    def test_e5_a_prepared_revision_whose_checkout_is_gone_is_still_refused(self):
        """The discard is for nothing-prepared revisions only: a prepared one keeps its frozen checkout."""
        first, _ = self.engine([{"valid": True}, subprocess.TimeoutExpired("zeroshot", 120)])
        with self.authority() as a:
            self.begin(a, "native")
            with self.assertRaises(Blocked):
                first.proposal(a, lambda _: None)
            checkout = a.directory / "revision-1" / "checkout"
            shutil.rmtree(checkout)
        again, more = self.engine([])
        with self.authority() as a:
            native_planning = self.planning(a, again)
            native_planning.send()
            with self.assertRaises(Blocked) as raised:
                Watch(native_planning, lambda _: None).step()
            self.assertEqual(catalog.family(raised.exception), "engine.checkout")
            self.assertFalse(checkout.exists())
        self.assertEqual(more, [])

    def test_e5_discard_takes_a_file_or_a_link_without_following_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside"
            outside.mkdir()
            (outside / "keep").write_text("x")
            link, plain = root / "link", root / "plain"
            link.symlink_to(outside)
            plain.write_text("x")
            for path in (link, plain, root / "missing"):
                engine_module.discard_checkout(path)
                self.assertFalse(path.exists() or path.is_symlink())
            self.assertEqual((outside / "keep").read_text(), "x")


class GateCheckoutTests(gates.NativeGateBase):
    def test_e5_a_task_gate_clone_a_kill_left_behind_is_cloned_again(self):
        self.approved_native_plan()
        real = subprocess.run

        def killed(argv, *args, **kwargs):
            if list(argv[:2]) == ["git", "clone"]:
                destination = Path(argv[-1])
                destination.mkdir(parents=True)
                (destination / "half-cloned").write_text("x")
                raise KeyboardInterrupt()
            return real(argv, *args, **kwargs)

        with self.bound() as authority:
            native, _ = self.dispatching([])
            with patch.object(engine_module.subprocess, "run", killed), self.assertRaises(KeyboardInterrupt):
                self.delivery(authority, native).run_task_gate("M1")
        with self.bound() as authority:
            native, calls = self.dispatching([{"valid": True}, {"runId": "fixture-native-run"}, self.gate_terminal()])
            record = self.delivery(authority, native).run_task_gate("M1")
            self.assertEqual(record["status"], "concluded")
            self.assertFalse((authority.directory / "gates" / record["id"] / "checkout" / "half-cloned").exists())


# E6 ---------------------------------------------------------------------------------------------------------

class NodeTests(unittest.TestCase):
    def test_e6_without_node_install_prints_only_the_refusal_and_installs_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            empty = Path(temp) / "empty"
            home.mkdir()
            empty.mkdir()
            result = subprocess.run([sys.executable, "-I", str(ROOT / "install.py")], capture_output=True, text=True,
                                    env={"PATH": str(empty), "HOME": str(home), "XDG_DATA_HOME": str(home / "data")})
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            lines = result.stderr.strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("Node.js", lines[0])
            self.assertIn("npm", lines[0])
            self.assertNotIn("zplan login", lines[0])
            self.assertFalse((home / "data").exists())  # nothing was installed

    def test_e6_a_caller_that_runs_setup_gets_no_next_step_without_node(self):
        bin_dir = Path("/opt/zplan-bin")
        for on_path in (os.pathsep.join(["/usr/bin", str(bin_dir)]), "/usr/bin"):
            line = install.installed_message(bin_dir / "zplan", bin_dir, on_path, setup_follows=True, node=False)
            self.assertNotIn("zplan login", line)
            self.assertNotIn("zplan setup", line)
        with_node = install.installed_message(bin_dir / "zplan", bin_dir, "/usr/bin", setup_follows=True, node=True)
        self.assertIn("zplan login", with_node)


if __name__ == "__main__":
    unittest.main()
