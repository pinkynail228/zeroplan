"""P1: the first start and /setup offer the preset or the owner's own settings (the profile editor).

Engine tests run `Profile` over real temporary Git repositories in production mode (v4a: the profile is a snapshot
in zplan's own state; the project's file is never written or committed); two Pilot tests drive the whole app, one for the first start (P1, P2) and one for /setup (P3, P4); a
small host app shows the editor on forms the whole-app tests do not reach. No provider, no network, isolated HOME/XDG.

Interpretations (the reviewers never see the worker's summary):

- The editor sends only what the owner changed (`ProfileScreen.changes`), not the whole form: a value the owner did not
  touch is never rewritten, so an edit made to the file elsewhere meanwhile is kept.
- «configure» is offered where «later» is (a proposal): a project whose own `zplan.process.json` already exists is
  only recorded by «accept», so its file stays the owner's; /setup «profile» refuses a change to it.
- Saving with nothing changed from the bootstrap editor accepts the proposal as it is; from /setup it records
  nothing new.
- «profile» on a «later» profile edits the snapshot in effect (not a new proposal); saving records it, with the
  owner's values, as the accepted snapshot.
- Without a check the merge gate offers only «no check before merging» (a stored `required` stays as it is until the owner presses it).
- `tui_settings.profile` and `tui_bootstrap.configure` carry the key `right`: `tests/test_reference.py` lets a screen
  share one key only for the action sets it lists, and the buttons are reached by Tab or the arrows.
- Whole-app drives: two.
"""

import json
import os
import unittest
from unittest.mock import patch

from terminal_planner import process
from terminal_planner.authority import Authority, Blocked, NATIVE_EFFORTS
from terminal_planner.process import Form, Profile
import test_terminal_planner as tp
import test_tui as tt
from tui_support import HAVE_TEXTUAL, screen_text

CHECKS = {"scripts": {"test": "node run.js"}}


class ProfileEditTest(tp.ProjectTest):
    """A project whose profile file is visible to Git (as in a real project), config and data under the scratch root."""

    def setUp(self):
        super().setUp()
        self.config = self.root / "config"
        patcher = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config), "XDG_DATA_HOME": str(self.root / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)
        ui = self.config / "planning-kit" / "ui.json"
        ui.parent.mkdir(parents=True, exist_ok=True)
        ui.write_text('{"language": "ru"}\n', encoding="utf-8")

    @property
    def file(self):
        return self.project / process.PROFILE_FILE

    def document(self):
        return json.loads(self.file.read_text(encoding="utf-8"))

    @staticmethod
    def document_of_snapshot(status):
        return process.document_of(status.resolved.config)

    @property
    def directory(self):
        """The project's state directory, read once (opening the Authority later would meet a running app's lock)."""
        if not hasattr(self, "_directory"):
            with Authority(None, self.project) as authority:
                self._directory = authority.directory
        return self._directory

    def record(self):
        return process.read_record(self.directory)

    def profile(self, action, *args):
        with Authority(None, self.project) as authority:
            return getattr(Profile.of(authority), action)(*args)


class ChoiceEngineTests(ProfileEditTest):
    def settled(self):
        """The accepted profile as a reopen resolves it, with nothing in the project to read it from."""
        status = Profile(self.project, self.directory).status(write=False)
        self.assertEqual((status.state, status.present), ("accepted", False))
        return status

    def test_p1_accept_with_changes_keeps_them_and_the_rest_as_proposed_in_a_snapshot(self):
        """P1/v4a A1: «configure», «ask for everything», 1, «save» -> level manual, max_runs 1, all else as proposed;
        recorded as a snapshot: no file, no commit, the digest recorded."""
        proposal = process.resolve(process.propose(self.project, {}), {}, self.project, "proposal").config
        before = self.git("rev-parse", "HEAD")
        status = self.profile("accept", {"level": "manual", "max_runs": 1})
        self.assertEqual((status.state, status.notice), ("accepted", ""))
        expected = json.loads(json.dumps(proposal))
        expected["autonomy"].update(level="manual", max_runs=1)
        self.assertEqual(self.settled().resolved.config, expected)
        self.assertFalse(self.file.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("status", "--porcelain"), b"")
        self.assertEqual(self.record()["digest"], status.resolved.digest)
        self.assertEqual(self.settled().digest, status.resolved.digest)

    def test_p1_a_role_changed_in_the_editor_is_kept_whole(self):
        self.profile("accept", {"roles": {"worker": {"model": "other-model", "effort": "max"}}})
        roles = self.settled().resolved.config["roles"]
        self.assertEqual(roles["worker"], {"model": "other-model", "effort": "max"})
        self.assertEqual(roles["planner"], process.propose(self.project, {})["roles"]["planner"])

    def test_p1_the_merge_gate_needs_a_check(self):
        """No check: «checks before merging» is refused with the reason, nothing is recorded."""
        with self.assertRaisesRegex(Blocked, "gates.merge"):  # the reason's words are the services' (process.py)
            self.profile("accept", {"merge": "required"})
        self.assertIsNone(self.record())
        (self.project / "package.json").write_text(json.dumps(CHECKS))
        self.profile("accept", {"merge": "off"})
        self.assertEqual(self.settled().resolved.config["gates"]["merge"], "off")

    def test_p2_an_invalid_model_is_refused_with_the_reason_and_writes_nothing(self):
        """P2: model «a b» -> reason, no file, no record, the profile still undecided."""
        before = self.git("rev-parse", "HEAD")
        with self.assertRaises(Blocked) as raised:
            self.profile("accept", {"roles": {"worker": {"model": "a b", "effort": "low"}}})
        self.assertIn("roles.worker.model", str(raised.exception))
        self.assertEqual(raised.exception.family, "process.invalid")
        self.assertFalse(self.file.exists())
        self.assertIsNone(self.record())
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.profile("status").state, "never")

    def test_p3_revise_changes_only_the_edited_value_of_the_snapshot_and_writes_nothing(self):
        """P3/v4a A2: level auto -> supervised: the snapshot differs only in that value; the new digest is recorded;
        the project's tree and HEAD are as they were (an owner's draft included)."""
        (self.project / "package.json").write_text(json.dumps(CHECKS))
        self.git("add", "package.json")
        self.git("commit", "-qm", "checks")
        accepted = self.profile("accept", {"max_runs": 2, "roles": {"critic": {"model": "m-1", "effort": "low"}}})
        (self.project / "notes.txt").write_text("draft\n")
        before = self.git("rev-parse", "HEAD")
        status = self.profile("revise", {"level": "supervised"})
        expected = json.loads(json.dumps(accepted.resolved.config))
        expected["autonomy"]["level"] = "supervised"
        self.assertEqual(self.settled().resolved.config, expected)
        self.assertNotEqual(status.digest, accepted.digest)
        self.assertEqual(self.record()["digest"], status.resolved.digest)
        self.assertFalse(self.file.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("status", "--porcelain").decode().split(), ["??", "notes.txt"])

    def test_p3_a_revision_of_the_owners_file_is_refused_and_the_file_stays(self):
        """v4a A3: the file is the source; a change is refused naming it and the proposed value."""
        self.file.write_text('{"preset": "zplan.default/2"}\n', encoding="utf-8")
        self.profile("accept")
        before, record = self.file.read_bytes(), self.record()
        with self.assertRaises(Blocked) as raised:
            self.profile("revise", {"max_runs": 2, "roles": {"critic": {"model": "m-1", "effort": "low"}}})
        self.assertEqual(raised.exception.family, "action.refused")
        self.assertIn("zplan.process.json is the source: set max_runs to 2 there; set roles to", str(raised.exception))
        self.assertEqual((self.file.read_bytes(), self.record()), (before, record))

    def test_v4a_export_writes_the_snapshot_once_and_the_file_becomes_the_source(self):
        """v4a (`profile init`): the accepted snapshot is exported to the file and committed alone; from then on the
        file is the source (a revision is refused); an existing file is never overwritten; the same document and
        digest as the snapshot."""
        accepted = self.profile("accept", {"level": "manual"})
        self.assertFalse(self.file.exists())
        (self.project / "notes.txt").write_text("draft\n")
        before = self.git("rev-parse", "HEAD")
        exported = self.profile("export")
        self.assertEqual(self.document(), process.document_of(accepted.resolved.config))
        self.assertEqual((exported.state, exported.present, exported.digest), ("accepted", True, accepted.digest))
        self.assertEqual(self.git("log", "-1", "--format=%s").decode().strip(), "zplan profile")
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").decode().split(), [process.PROFILE_FILE])
        self.assertEqual(self.git("rev-parse", "HEAD~1"), before)
        self.assertEqual(self.git("status", "--porcelain").decode().split(), ["??", "notes.txt"])
        written = self.file.read_bytes()
        with self.assertRaises(Blocked) as raised:
            self.profile("revise", {"level": "supervised"})
        self.assertEqual(raised.exception.family, "action.refused")
        with self.assertRaises(Blocked):
            self.profile("export")
        self.assertEqual(self.file.read_bytes(), written)

    def test_p2_a_refused_revision_and_an_unchanged_one_leave_the_record_alone(self):
        """P2/P4: a refused value, or nothing changed («cancel» sends nothing, a save without edits sends {})."""
        self.profile("accept")
        record, head = self.record(), self.git("rev-parse", "HEAD")
        with self.assertRaises(Blocked):
            self.profile("revise", {"roles": {"worker": {"model": "a b", "effort": "low"}}})
        self.profile("revise", {})
        self.profile("revise", {"level": process.propose(self.project, {})["autonomy"]["level"]})
        self.assertEqual((self.record(), self.git("rev-parse", "HEAD")), (record, head))
        self.assertFalse(self.file.exists())

    def test_p4_a_postponed_profile_is_accepted_by_saving_its_edited_values(self):
        """P4: «later» keeps the profile unsaved; the editor on it starts from the snapshot in effect and its save
        records it with the owner's value as accepted; no file is written."""
        (self.project / "package.json").write_text(json.dumps(CHECKS))
        self.git("add", "package.json")
        self.git("commit", "-qm", "checks")
        before = self.git("rev-parse", "HEAD")
        with Authority(None, self.project) as authority:
            profile = Profile.of(authority)
            self.assertEqual(profile.defer().state, "later")
            form = process.view(profile).form
        self.assertEqual((form.level, form.merge, form.checks), ("auto", "required", True))
        self.assertFalse(self.file.exists())
        status = self.profile("accept", {"max_runs": 2})
        self.assertEqual(status.state, "accepted")
        config = self.settled().resolved.config
        self.assertEqual((config["autonomy"]["max_runs"], config["gates"]["merge"]), (2, "required"))
        self.assertFalse(self.file.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_a_fixture_session_never_writes_the_targets_file_but_records_the_edit(self):
        with Authority(self.state, self.project, fixture_id="test") as authority:
            profile = Profile.of(authority)
            profile.accept({"level": "manual"})
            self.assertFalse(self.file.exists())
            self.assertEqual(profile.status().resolved.config["autonomy"]["level"], "manual")
            profile.revise({"level": "supervised"})
            self.assertEqual(profile.status().resolved.config["autonomy"]["level"], "supervised")
            self.assertFalse(self.file.exists())

    def test_the_form_is_the_values_in_effect(self):
        config = process.resolve(process.propose(self.project, {}), {}, self.project).config
        form = process.form_of(config)
        self.assertEqual((form.level, form.max_runs, form.merge, form.checks), ("auto", 3, "off", False))
        self.assertEqual([r[0] for r in form.roles], list(process.ROLES))
        legacy = process.resolve({"preset": process.PRESET}, {}, self.project).config
        self.assertEqual(process.form_of(legacy).level, None)


if HAVE_TEXTUAL:
    from textual.app import App
    from textual.widgets import Button, Input
    from terminal_planner.tui.controller import Controller
    from terminal_planner.tui.modals import ProfileScreen


@unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required for Pilot tests")
class EditorFormTests(unittest.IsolatedAsyncioTestCase):
    """The editor on forms the whole-app drives do not reach, in a bare host app (no engine, no store)."""

    ROLES = tuple((name, "model-" + name, "high") for name in process.ROLES)

    def editor(self, form):
        sent = []

        class Host(App):
            def changed(self):  # the two things a modal asks of `ZplanApp`
                pass

            def deliver(self, handler):
                return handler

            def on_mount(self):
                self.push_screen(ProfileScreen(form, lambda changes, done: sent.append(changes)))
        return Host(), sent

    async def test_p1_the_offered_choices_follow_the_form(self):
        form = Form("auto", 5, "required", False, self.ROLES)
        host, _ = self.editor(form)
        async with host.run_test(size=(100, 60)) as pilot:
            await pilot.pause(0.1)
            labels = lambda group: [b.label.plain.removeprefix("● ") for b in host.screen.query("Button")
                                    if (b.name or "").startswith(group + "=")]  # the picked one carries «● » (D6b)
            self.assertEqual(labels("level"), list(process.LEVEL_NAMES.values()))  # the services' level words
            self.assertEqual(labels("max_runs"), ["1", "2", "3", "5"])  # the file's 5 is a button of its own
            self.assertEqual(labels("merge"), ["no check before merging"])  # no check: only this one, with the reason
            self.assertIn("There are no checks", screen_text(host))
            for role, model, _ in self.ROLES:
                self.assertEqual(host.screen.query_one("#profile-model-" + role, Input).value, model)
                self.assertEqual(set(labels("effort." + role)), NATIVE_EFFORTS)
            self.assertEqual([b.id for b in host.screen.query("#profile-buttons Button")], ["profile-save", "profile-cancel"])

    async def test_p1_with_a_check_the_merge_gate_offers_both_and_save_sends_only_the_changes(self):
        host, sent = self.editor(Form("supervised", 2, "off", True, self.ROLES))
        async with host.run_test(size=(100, 60)) as pilot:
            await pilot.pause(0.1)
            names = [b.name for b in host.screen.query("Button")]
            self.assertEqual(sum(n == "merge=required" for n in names) + sum(n == "merge=off" for n in names), 2)
            self.assertEqual([b.label.plain.removeprefix("● ") for b in host.screen.query("Button")
                              if (b.name or "").startswith("merge=")], ["checks before merging", "no check before merging"])
            host.screen.query_one("#profile-merge-required", Button).press()
            host.screen.query_one("#profile-effort-worker-low", Button).press()
            host.screen.query_one("#profile-model-critic", Input).value = " new-model "
            await pilot.pause(0.1)
            host.screen.query_one("#profile-save", Button).press()
            await pilot.pause(0.1)
            self.assertEqual(sent, [{"merge": "required", "roles": {
                "worker": {"model": "model-worker", "effort": "low"},
                "critic": {"model": "new-model", "effort": "high"}}}])


class ShellProfileTest(tt.ShellTest, ProfileEditTest):
    """The whole app in production mode (not a fixture session): the profile is a snapshot, the file is never written."""

    def setUp(self):
        super().setUp()
        self.assertIsNone(self.record())  # the state directory exists before the app locks it

    def native(self):
        return Controller.for_project(self.project, None, readiness=tt.Readiness(tt.check("git")),
                                      profile=True)

    def drive(self):
        controller = self.native()
        self.addCleanup(controller.stop)
        return self.shell(controller, size=(100, 50))

    async def until_screen(self, pilot, name):
        await self.until(pilot, lambda: type(self.app.screen).__name__ == name)
        await pilot.pause(0.1)

    async def press(self, pilot, selector):
        button = self.app.screen.query_one(selector, Button)
        await self.until(pilot, lambda: not button.has_class("-active"))
        button.focus()
        await pilot.pause(0.05)
        await pilot.press("enter")
        await pilot.pause(0.1)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required for Pilot tests")
class FirstStartTests(ShellProfileTest):
    async def test_p1_p2_configure_refuses_an_invalid_model_then_saves_the_owners_values(self):
        """P1/P2: «configure» sits between «accept» and «later» with the focus on «accept»; the editor opens on the
        proposal; a model «a b» keeps it open with the reason and writes nothing; «ask for everything», 1, «save» writes
        level manual and max_runs 1 as a snapshot (no file, no commit); «cancel» before that wrote nothing."""
        head = self.git("rev-parse", "HEAD")
        async with self.drive() as pilot:
            await self.until_screen(pilot, "BootstrapScreen")
            self.assertEqual([b.id for b in self.app.screen.query("#bootstrap-buttons Button")],
                             ["bootstrap-accept", "bootstrap-configure", "bootstrap-later"])
            self.assertEqual(self.app.focused.id, "bootstrap-accept")
            await self.press(pilot, "#bootstrap-configure")
            await self.until_screen(pilot, "ProfileScreen")
            self.assertIn("<svg", self.app.export_screenshot())  # the editor's look: one Textual SVG screenshot
            self.assertEqual(screen_text(self.app).count("[ctrl+s]"), 1)  # D6b G2: one hint line
            await self.press(pilot, "#profile-cancel")  # «cancel»: the choice is still open, nothing written
            await self.until_screen(pilot, "BootstrapScreen")
            self.assertFalse(self.file.exists())
            await self.press(pilot, "#bootstrap-configure")
            await self.until_screen(pilot, "ProfileScreen")
            editor = self.app.screen
            editor.query_one("#profile-model-worker", Input).value = "a b"
            await self.press(pilot, "#profile-level-manual")
            await self.press(pilot, "#profile-max_runs-1")
            await self.press(pilot, "#profile-save")
            await self.until(pilot, lambda: "roles.worker.model" in editor.problem)
            self.assertIs(self.app.screen, editor)
            self.assertIn("roles.worker.model", screen_text(self.app))
            self.assertFalse(self.file.exists())
            self.assertIsNone(self.record())
            editor.query_one("#profile-model-worker", Input).value = process.propose(self.project, {})["roles"]["worker"]["model"]
            await self.press(pilot, "#profile-save")
            await self.until_screen(pilot, "MainScreen")
            await self.until(pilot, lambda: self.app.snapshot.profile.state == "accepted")
        status = Profile(self.project, self.directory).status(write=False)
        self.assertEqual(status.state, "accepted")
        autonomy = status.resolved.config["autonomy"]
        self.assertEqual((autonomy["level"], autonomy["max_runs"]), ("manual", 1))
        self.assertFalse(self.file.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), head)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required for Pilot tests")
class SetupTests(ShellProfileTest):
    async def test_p3_p4_setup_profile_on_a_postponed_then_an_accepted_profile(self):
        """P4: a «later» profile shows «profile» too, «cancel» and Esc write nothing, and saving accepts it. P3: on the
        accepted profile «profile» starts on the snapshot's values and a save changes only the edited value (level auto
        -> supervised), the new digest recorded, nothing written or committed. A file the owner then writes is the
        source: the editor's save is refused naming it, and the file stays."""
        (self.project / "package.json").write_text(json.dumps(CHECKS))
        self.git("add", "package.json")
        self.git("commit", "-qm", "checks")
        head = self.git("rev-parse", "HEAD")
        async with self.drive() as pilot:
            await self.until_screen(pilot, "BootstrapScreen")
            await self.press(pilot, "#bootstrap-later")
            await self.until_screen(pilot, "MainScreen")
            await self.until(pilot, lambda: self.app.snapshot.profile.state == "later")
            await self.command(pilot, "/setup")
            await self.until_screen(pilot, "SettingsScreen")
            await self.until(pilot, lambda: self.app.screen.query("#settings-buttons-profile"))
            await self.press(pilot, "#settings-buttons-profile")
            await self.until_screen(pilot, "ProfileScreen")
            self.assertEqual(self.app.screen.query_one("#profile-merge-required", Button).has_class("-chosen"), True)
            await self.press(pilot, "#profile-level-manual")
            await pilot.press("escape")  # Esc: nothing written, the profile stays postponed
            await self.until_screen(pilot, "SettingsScreen")
            self.assertEqual((self.file.exists(), self.record()["state"]), (False, "later"))
            await self.press(pilot, "#settings-buttons-profile")
            await self.until_screen(pilot, "ProfileScreen")
            await self.press(pilot, "#profile-level-supervised")
            await self.press(pilot, "#profile-save")
            await self.until_screen(pilot, "SettingsScreen")
            await self.until(pilot, lambda: self.app.snapshot.profile.state == "accepted")
            settled = Profile(self.project, self.directory).status(write=False)
            self.assertEqual(settled.resolved.config["autonomy"]["level"], "supervised")
            self.assertEqual(self.record()["digest"], settled.resolved.digest)
            self.assertEqual((self.file.exists(), self.git("rev-parse", "HEAD")), (False, head))
            owners = self.document_of_snapshot(settled)  # the owner writes the file: it is the source now
            owners["limits"]["plan_rounds"] = 2
            self.file.write_text(json.dumps(owners, indent=2) + "\n", encoding="utf-8")
            written = self.file.read_bytes()
            await self.press(pilot, "#settings-buttons-profile")
            await self.until_screen(pilot, "ProfileScreen")
            editor = self.app.screen
            await self.press(pilot, "#profile-level-manual")
            await self.press(pilot, "#profile-save")
            await self.until(pilot, lambda: "zplan.process.json is the source" in editor.problem)
            self.assertIs(self.app.screen, editor)
        self.assertEqual(self.file.read_bytes(), written)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)


if __name__ == "__main__":
    unittest.main()
