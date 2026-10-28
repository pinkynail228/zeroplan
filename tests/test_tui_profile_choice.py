"""P1: the first start and /setup offer the preset or the owner's own settings (the profile editor).

Engine tests run `Profile` over real temporary Git repositories in production mode (the file is written and
committed); two Pilot tests drive the whole app, one for the first start (P1, P2) and one for /setup (P3, P4); a
small host app shows the editor on forms the whole-app tests do not reach. No provider, no network, isolated HOME/XDG.

Interpretations (the reviewers never see the worker's summary):

- The editor sends only what the owner changed (`ProfileScreen.changes`), not the whole form: a value the owner did not
  touch is never rewritten, so an edit made to the file elsewhere meanwhile is kept.
- «configure» is offered where «later» is (a proposal): a project whose own `zplan.process.json` already exists is
  only recorded by «accept», so its file stays the owner's; /setup «profile» edits it afterwards.
- Saving with nothing changed from the bootstrap editor accepts the proposal as it is; from /setup it writes nothing
  (no file replace, no commit).
- «profile» on a «later» profile edits the snapshot in effect (not a new proposal); saving writes it, with the
  owner's values, as the accepted file.
- Without a check the merge gate offers only «ask» (a stored `required` stays as it is until the owner presses it).
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

    def head(self):
        return self.git("log", "-1", "--format=%s").decode().strip(), self.git("show", "--name-only", "--format=", "HEAD").decode().split()

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
    def test_p1_accept_with_changes_writes_them_and_the_rest_as_proposed_in_one_commit(self):
        """P1: «configure», «ask for everything», 1, «save» -> level manual, max_runs 1, all else as proposed."""
        proposal = process.propose(self.project, {})
        before = self.git("rev-parse", "HEAD")
        status = self.profile("accept", {"level": "manual", "max_runs": 1})
        self.assertEqual((status.state, status.notice), ("accepted", ""))
        expected = json.loads(json.dumps(proposal))
        expected["autonomy"].update(level="manual", max_runs=1)
        self.assertEqual(self.document(), expected)
        self.assertEqual(self.head(), ("zplan profile", [process.PROFILE_FILE]))
        self.assertEqual(self.git("rev-parse", "HEAD~1"), before)
        self.assertEqual(self.record()["digest"], status.resolved.digest)

    def test_p1_a_role_changed_in_the_editor_is_written_whole(self):
        self.profile("accept", {"roles": {"worker": {"model": "other-model", "effort": "max"}}})
        self.assertEqual(self.document()["roles"]["worker"], {"model": "other-model", "effort": "max"})
        self.assertEqual(self.document()["roles"]["planner"], process.propose(self.project, {})["roles"]["planner"])

    def test_p1_the_merge_gate_needs_a_check(self):
        """No check: «automatic on green checks» is refused with the reason, nothing is written."""
        with self.assertRaisesRegex(Blocked, "gates.merge"):  # the reason's words are the services' (process.py)
            self.profile("accept", {"merge": "required"})
        (self.project / "package.json").write_text(json.dumps(CHECKS))
        self.profile("accept", {"merge": "off"})
        self.assertEqual(self.document()["gates"]["merge"], "off")

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

    def test_p3_revise_changes_only_the_edited_value_and_keeps_everything_else(self):
        """P3: level auto -> supervised: the file differs only in that value; unknown-to-the-editor keys and other
        sections stay; the file is replaced, committed alone, and the new digest is recorded."""
        document = process.propose(self.project, {})
        document["limits"]["plan_rounds"] = 2
        document["rules"] = []
        document["risk"] = {"rules": [{"paths": ["src/**"], "tier": "low"}]}
        document["autonomy"]["wakeups_per_hour"] = 7
        self.file.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "profile")
        self.profile("accept")
        (self.project / "notes.txt").write_text("draft\n")
        before = self.git("rev-parse", "HEAD")
        status = self.profile("revise", {"level": "supervised"})
        expected = json.loads(json.dumps(document))
        expected["autonomy"]["level"] = "supervised"
        self.assertEqual(self.document(), expected)
        self.assertEqual(self.head(), ("zplan profile", [process.PROFILE_FILE]))
        self.assertEqual(self.git("rev-parse", "HEAD~1"), before)
        self.assertEqual(self.git("status", "--porcelain").decode().split(), ["??", "notes.txt"])
        self.assertEqual(self.record()["digest"], status.resolved.digest)
        self.assertEqual(status.resolved.config["autonomy"]["level"], "supervised")
        self.assertEqual([p.name for p in self.project.iterdir() if p.name.startswith(".zplan-process-")], [])

    def test_p3_revise_adds_a_section_the_file_left_to_the_preset(self):
        self.file.write_text('{"preset": "zplan.default/2"}\n', encoding="utf-8")
        self.profile("accept")
        self.profile("revise", {"max_runs": 2, "roles": {"critic": {"model": "m-1", "effort": "low"}}})
        self.assertEqual(self.document(), {"preset": "zplan.default/2", "autonomy": {"max_runs": 2},
                                           "roles": {"critic": {"model": "m-1", "effort": "low"}}})

    def test_p2_a_refused_revision_and_an_unchanged_one_leave_the_file_and_the_record_alone(self):
        """P2/P4: a refused value, or nothing changed («cancel» sends nothing, a save without edits sends {})."""
        self.profile("accept")
        text, record, head = self.file.read_text(encoding="utf-8"), self.record(), self.git("rev-parse", "HEAD")
        with self.assertRaises(Blocked):
            self.profile("revise", {"roles": {"worker": {"model": "a b", "effort": "low"}}})
        self.profile("revise", {})
        self.profile("revise", {"level": process.propose(self.project, {})["autonomy"]["level"]})
        self.assertEqual((self.file.read_text(encoding="utf-8"), self.record(), self.git("rev-parse", "HEAD")),
                         (text, record, head))

    def test_p4_a_postponed_profile_is_accepted_by_saving_its_edited_values(self):
        """P4: «later» keeps the profile unsaved; the editor on it starts from the snapshot in effect and its save
        writes the file with the owner's value and accepts it."""
        (self.project / "package.json").write_text(json.dumps(CHECKS))
        self.git("add", "package.json")
        self.git("commit", "-qm", "checks")
        with Authority(None, self.project) as authority:
            profile = Profile.of(authority)
            self.assertEqual(profile.defer().state, "later")
            form = process.view(profile).form
        self.assertEqual((form.level, form.merge, form.checks), ("auto", "required", True))
        self.assertFalse(self.file.exists())
        status = self.profile("accept", {"max_runs": 2})
        self.assertEqual(status.state, "accepted")
        self.assertEqual(self.document()["autonomy"]["max_runs"], 2)
        self.assertEqual(self.document()["gates"]["merge"], "required")
        self.assertEqual(self.head(), ("zplan profile", [process.PROFILE_FILE]))

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
            self.assertEqual(labels("merge"), ["ask"])  # no check: only «ask», with the reason
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
    """The whole app in production mode (not a fixture session): the profile file is written and committed."""

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
        level manual and max_runs 1, committed «zplan profile»; «cancel» before that wrote nothing."""
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
        proposal = process.propose(self.project, {})
        proposal["autonomy"].update(level="manual", max_runs=1)
        self.assertEqual(self.document(), proposal)
        self.assertEqual(self.head(), ("zplan profile", [process.PROFILE_FILE]))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required for Pilot tests")
class SetupTests(ShellProfileTest):
    async def test_p3_p4_setup_profile_on_a_postponed_then_an_accepted_profile(self):
        """P4: a «later» profile shows «profile» too, «cancel» and Esc write nothing, and saving accepts it. P3: on the
        accepted profile «profile» starts on the file's values and a save changes only the edited value (level auto ->
        supervised), committed alone, the new digest recorded, a hand-written key and section kept."""
        (self.project / "package.json").write_text(json.dumps(CHECKS))
        self.git("add", "package.json")
        self.git("commit", "-qm", "checks")
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
            self.assertEqual(self.document()["autonomy"]["level"], "supervised")
            self.assertEqual(self.head(), ("zplan profile", [process.PROFILE_FILE]))
            document = self.document()  # a hand edit made while the screen is open: the save keeps it
            document["limits"]["plan_rounds"] = 2
            self.file.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            await self.press(pilot, "#settings-buttons-profile")
            await self.until_screen(pilot, "ProfileScreen")
            self.assertTrue(self.app.screen.query_one("#profile-level-supervised", Button).has_class("-chosen"))
            await self.press(pilot, "#profile-level-auto")
            await self.press(pilot, "#profile-save")
            await self.until_screen(pilot, "SettingsScreen")
            await self.until(pilot, lambda: self.document()["autonomy"]["level"] == "auto")
            await self.until(pilot, lambda: self.record()["digest"] == Profile(self.project, self.directory).status(
                write=False).resolved.digest)
        document["autonomy"]["level"] = "auto"
        self.assertEqual(self.document(), document)
        self.assertEqual(self.head(), ("zplan profile", [process.PROFILE_FILE]))
        self.assertEqual(self.git("status", "--porcelain").decode().split(), [])


if __name__ == "__main__":
    unittest.main()
