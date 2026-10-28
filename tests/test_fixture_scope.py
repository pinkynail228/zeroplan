"""R-1..R-4 (release 0.4.0, class repair 2 of 2): fixture mode is one boundary, classified by `fixture_id is not
None`, and a `--fixture ID` session reaches no production sink.

The task's class: fixture isolation is a convention per service, not one boundary. On the base a `--fixture` TUI
session built a real architect chat (a production `ArchitectChat`/`ArchitectStore`, provider and tool probes and
production transcript access), the empty `--fixture ''` slipped past the wiring into `setup`, and accepting the
process profile in a fixture session wrote the target's `zplan.process.json`.

These tests enter through the existing `cli.main` / `cli.session` / `tui.run` composition, never a new factory, so
the mode decision under test is the wiring's own (R-1). They need Textual only for the shell classes and skip
without it; the profile, refusal and docs parts need no Textual. No provider, no network: the one "provider" is
the scripted codex of `test_tui_chat`.

Interpretations recorded for the reviewers (A-6 asks for them): a) "the chat key" of R-2 is read as the chat
pane's own state line — that is where the refusal is shown at startup and after Enter/reset/retry; the send key
(`enter`), reset (`ctrl+r`) and the retry path (`App.retry_chat`) are driven to show they add nothing else. b)
"tools/login treated as available" (A-1) is read as: fixture wiring asks readiness with `tools=False` (and never
installs or logs in), so the demo needs no toolchain; asserted through the recorded `cli.readiness` call. c) A-4
"production session" is read as the production (no `--fixture`) wiring: a controller over the canonical Git
authority, the production chat prepare (the probes run) behind the scripted codex, and a production `Profile`
for the file — the object the bootstrap accept writes. d) R-3's fixture accept records the accepted record *with*
the effective snapshot in the fixture sidecar, whether the profile came from the proposal or from an existing
`zplan.process.json` (which stays byte-identical), and a file that later appears, changes or is removed does not
drop that snapshot, so a reopen never reads accepted -> missing; native records carry no snapshot, so a native
deletion still refuses (`test_process`). e) R-1 is read as "no filesystem access before the refusal", so the
regression asserts `native_state_root()` (which resolves and probes the production native-state path) is never
called for an invalid id. f) R-3 also covers a fixture namespace an older build left behind: a writable fixture
session adopts an existing `accepted` record that carries no snapshot (an older or interrupted accept) with the
file's effective snapshot — including the interrupted `accepting` recovery — and a `profile init` from a genuinely
missing fixture profile re-records the proposal's snapshot without dereferencing the absent resolution, writing
the target's file or crashing. A deleted profile is therefore only "missing" when the record carries no snapshot
either (the state `test_process.ProfileTest.remove_accepted_file` models)."""

import contextlib
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from terminal_planner import architect as adapter, catalog, cli, process, setup
from terminal_planner.authority import Authority as RealAuthority, Blocked
from terminal_planner.cli import Terminal
from terminal_planner.engine import FixtureEngine
from terminal_planner.process import Profile
from terminal_planner.runs import FixtureDriver
from terminal_planner.tui import chat as chat_module
from test_terminal_planner import ProjectTest, ScriptedTerminal
from tui_support import HAVE_TEXTUAL, screen_text

TEXTUAL_REASON = "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is required"
FIXTURE_LINE = "The architect chat is unavailable in the demo (--fixture)."
PROFILE_FILE = process.PROFILE_FILE


class Sinks:
    """The production sinks a fixture session must not reach: construction of the chat and its store, provider and
    tool-probe entry points, and transcript reads."""

    def __init__(self):
        self.chats = []
        self.stores = []
        self.architects = []
        self.prepares = []
        self.transcripts = []
        self.probes = []

    def empty(self):
        return (self.chats, self.stores, self.architects, self.prepares, self.transcripts, self.probes)


def spies(sinks):
    """Patch every production sink with a recorder; a list of context managers for an ExitStack."""
    real_chat = chat_module.ArchitectChat
    real_architect = chat_module.Architect

    class ChatSpy(real_chat):
        def __init__(self, *args, **kwargs):
            sinks.chats.append(args[:1])
            super().__init__(*args, **kwargs)

    class StoreSpy:  # never calls the real store: that alone would create the production directory
        def __init__(self, *args, **kwargs):
            sinks.stores.append(args[:1])

        def transcript(self):
            sinks.transcripts.append("transcript")
            return []

        def load(self):
            return None

    class ArchitectSpy(real_architect):
        def __init__(self, *args, **kwargs):
            sinks.architects.append(args[:1])
            super().__init__(*args, **kwargs)

    def prepare_spy(project):
        sinks.prepares.append(project)
        raise Blocked("fixture: no production prepare", family="action.refused")

    def probe_spy(*args, **kwargs):
        sinks.probes.append(args[:1])
        raise Blocked("fixture: no tool probe", family="setup.tools_invalid")

    return [patch.object(chat_module, "ArchitectChat", ChatSpy),
            patch.object(chat_module, "ArchitectStore", StoreSpy),
            patch.object(chat_module, "Architect", ArchitectSpy),
            patch.object(chat_module, "default_prepare", prepare_spy),
            patch.object(adapter, "ArchitectStore", StoreSpy),
            patch.object(setup, "check_installation", probe_spy),
            patch.object(adapter, "verify_cli", probe_spy)]


def capture_tui(argv):
    """Run `cli.main`'s TUI path with the app captured instead of run (the real composition builds it): returns the
    constructed app. `Controller.stop` is neutralized so the app can be piloted afterwards."""
    from terminal_planner.tui import app as app_module
    from terminal_planner.tui import controller as controller_module

    captured = []
    with patch.object(cli, "tui_wanted", lambda *args, **kwargs: True), \
            patch.object(app_module.ZplanApp, "run", lambda self: captured.append(self)), \
            patch.object(controller_module.Controller, "stop", lambda self, timeout=None: None):
        code = cli.main(argv)
    return code, captured[0]


def accept_fixture_profile(project, state, fixture_id):
    """Decide the fixture profile up front so a demo shell opens on the main screen, not the bootstrap modal."""
    with RealAuthority(state, project, fixture_id=fixture_id) as authority:
        Profile.of(authority).accept()


def toolchain_patches(root, fixture):
    """The production preparation over the scripted codex as the installed toolchain (as test_tui_chat's C-7):
    the real `default_prepare` runs its tool probe on `fixture.codex` instead of a real install."""
    config = root / "roles-config"
    config.mkdir(exist_ok=True)
    home = setup.codex_home(fixture.env)
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text("{}", encoding="utf-8")
    return [patch.object(process, "config_root", lambda: config),
            patch.object(setup, "check_installation", return_value=fixture.bin),
            patch.object(setup, "tool_paths", return_value=(None, fixture.codex)),
            patch.object(setup, "native_environment", return_value=fixture.env)]


def fixture_argv(project, state, fixture_id, command=None):
    argv = ["--project", str(project), "--state-dir", str(state), "--fixture", fixture_id]
    return ([command] if command else []) + argv


class StartupRefusalTests(ProjectTest):
    """R-1/A-2: the fixture id is validated right after parsing, before any setup or process lives."""

    def run_main(self, argv):
        """`cli.main` with a recording Terminal and no real setup/attach_tools; returns (exit code, calls). A
        parser refusal is a `SystemExit(2)`, caught here so the calls made before it can be asserted."""
        calls = []
        out = io.StringIO()
        patches = [patch.object(cli, "install_tools", lambda show: calls.append(("install", show))),
                   patch.object(cli, "Terminal", lambda: Terminal(io.StringIO(), out)),
                   patch.object(cli, "check_installation", lambda *a, **k: calls.append(("check",))),
                   patch.object(cli, "load_roles", lambda: {}),
                   patch.object(cli, "session", lambda *a, **k: calls.append(("session",)))]
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    code = cli.main(argv)
                except SystemExit as raised:
                    code = raised.code
        return code, calls

    def test_a2_an_empty_fixture_id_setup_is_refused_before_any_install(self):
        """`--fixture '' setup` must be refused by the parser, before `install_tools`: on the base the empty id is
        falsy, slips past the wiring and the tools are installed (named failure)."""
        code, calls = self.run_main(fixture_argv(self.project, self.state, "", "setup"))
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])

    def test_a2_an_invalid_fixture_id_and_the_tui_entry_are_refused_before_the_session(self):
        """An invalid id (`bad/id`, `bad id`, the empty one) is refused for `setup` and for the plain/TUI entry,
        before `cli.session` is ever reached or a tool probe runs."""
        for fixture_id in ("bad/id", "bad id", ""):
            with self.subTest(fixture_id=fixture_id):
                code, calls = self.run_main(fixture_argv(self.project, self.state, fixture_id, "setup"))
                self.assertEqual(code, 2)
                self.assertEqual(calls, [])
                code, calls = self.run_main(fixture_argv(self.project, self.state, fixture_id))
                self.assertEqual(code, 2)
                self.assertNotIn(("session",), calls)

    def test_a2_an_invalid_id_never_probes_the_native_state_path(self):
        """R-1: the refusal comes before any filesystem access. `native_state_root()` resolves and probes the
        production native-state directory, so it must not run for `''` or an invalid id, on `setup` or on the
        plain/TUI entry (the reviewer's reproduction: it ran once per entry, before the refusal)."""
        seen = []
        real = cli.native_state_root

        def spy():
            seen.append("native_state_root")
            return real()

        for fixture_id in ("", "bad/id"):
            for command in ("setup", None):
                with self.subTest(fixture_id=fixture_id, command=command):
                    seen.clear()
                    with patch.object(cli, "native_state_root", spy):
                        code, calls = self.run_main(fixture_argv(self.project, self.state, fixture_id, command))
                    self.assertEqual(code, 2)
                    self.assertEqual(seen, [])  # no filesystem access before the parser refusal
                    self.assertEqual(calls, [])

    def test_a2_a_valid_id_still_reaches_the_wiring(self):
        """The guard refuses only what is not an id: a valid one is not stopped by it (the session path runs)."""
        code, calls = self.run_main(fixture_argv(self.project, self.state, "demo"))
        self.assertEqual(code, 0)
        self.assertIn(("session",), calls)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class FixtureChatIsolationTests(ProjectTest, unittest.IsolatedAsyncioTestCase):
    """R-2/A-1: a fixture TUI session shows the disabled chat and touches no production sink."""

    def fixture_app(self, fixture_id="demo"):
        """The app `cli.main`'s TUI path builds for `--fixture fixture_id`, with every sink spied and readiness
        recorded for the whole test (the controller asks readiness while the pilot runs); returns (app, sinks)."""
        accept_fixture_profile(self.project, self.state, fixture_id)
        sinks = Sinks()
        self.readiness_calls = []
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for p in spies(sinks):
            stack.enter_context(p)
        # fixture wiring asks readiness with tools=False: the demo needs no toolchain and never installs one
        stack.enter_context(patch.object(cli, "readiness",
                                         lambda project, state, tools=True: self.readiness_calls.append(tools) or []))
        code, app = capture_tui(fixture_argv(self.project, self.state, fixture_id))
        self.assertEqual(code, 0)
        return app, sinks

    async def until(self, pilot, condition, timeout=5.0):
        end = time.monotonic() + timeout
        while not condition():
            self.assertLess(time.monotonic(), end, "timed out waiting:\n" + screen_text(self.app))
            await pilot.pause(0.05)

    async def test_a1_a_fixture_shell_shows_the_disabled_chat_and_reaches_no_sink(self):
        """Startup, the send key, reset and retry all show the R-2 line; no `ArchitectChat`/`ArchitectStore`, no
        provider, no tool probe and no production transcript access happen (spies). Named failure on the base: the
        `chats` spy is not empty, because the fixture app is built with a real `ArchitectChat`."""
        from textual.widgets import Input
        for fixture_id in ("demo", "demo-2_x"):
            with self.subTest(fixture_id=fixture_id):
                app, sinks = self.fixture_app(fixture_id)
                self.app = app
                self.addCleanup(app.controller.stop)
                self.assertFalse(os.path.exists(Path(setup.data_root()) / "architect"))
                async with app.run_test(size=(200, 50)) as pilot:
                    await pilot.pause(0.2)
                    await self.until(pilot, lambda: self.readiness_calls, 5.0)
                    self.assertIsNone(app.chat)
                    self.assertIsNone(app.controller.install)  # tools/login are "available": nothing to install,
                    self.assertIsNone(app.controller.login)    # nothing to log into for the demo
                    self.assertIn(FIXTURE_LINE, screen_text(app))
                    field = app.query_one("#input", Input)
                    field.focus()
                    field.value = "привет"
                    await pilot.press("enter")  # the send key: refused, the text stays, nothing is queued
                    self.assertEqual(app.chat, None)
                    self.assertIn(FIXTURE_LINE, screen_text(app))
                    self.assertEqual(field.value, "привет")
                    field.value = "/new"
                    await pilot.press("enter")  # reset: nothing to reset
                    self.assertEqual(app.chat, None)
                    app.retry_chat()             # the readiness retry path: nothing to retry
                    self.assertEqual(app.chat, None)
                    self.assertIn(FIXTURE_LINE, screen_text(app))
                self.assertEqual(sinks.empty(), ([], [], [], [], [], []))
                self.assertFalse(os.path.exists(Path(setup.data_root()) / "architect"))
                self.assertTrue(self.readiness_calls and all(tools is False for tools in self.readiness_calls))

    async def test_a1_a_plain_fixture_session_has_no_chat_and_makes_no_sink(self):
        """The line UI in a fixture session is unchanged (it never had the chat) and reaches no sink either."""
        accept_fixture_profile(self.project, self.state, "demo")
        sinks = Sinks()
        out = io.StringIO()
        driver = FixtureDriver(self.root / "fixture-runs")
        with contextlib.ExitStack() as stack:
            for p in spies(sinks):
                stack.enter_context(p)
            cli.session(ScriptedTerminal("q\n", out), self.project, self.state, lambda *_: FixtureEngine(),
                        fixture_id="demo", driver_factory=lambda _: driver,
                        worktrees=self.root / "worktrees", profile=True)
        self.assertEqual(sinks.empty(), ([], [], [], [], [], []))
        self.assertIn("full-screen only", out.getvalue())


class FixtureProfileTests(ProjectTest):
    """R-3/A-3: the fixture profile lives in the fixture state; the target's file is never created or changed."""

    def sidecar(self, fixture_id="demo"):
        with RealAuthority(self.state, self.project, fixture_id=fixture_id) as authority:
            return authority.directory / process.STATE_FILE

    def raw_record(self):
        """The fixture sidecar as raw JSON: the oracle is the stored record, not the product's record helpers."""
        return json.loads(self.sidecar().read_text(encoding="utf-8"))

    def write_raw_record(self, record):
        self.sidecar().write_text(json.dumps(record), encoding="utf-8")

    def run_main(self, argv):
        out = io.StringIO()
        with patch.object(cli, "Terminal", lambda: Terminal(io.StringIO(), out)):
            code = cli.main(argv)
        return code, out.getvalue()

    def run_session(self, text, fixture_id="demo", profile=True):
        out = io.StringIO()
        driver = FixtureDriver(self.root / "fixture-runs")
        cli.session(ScriptedTerminal(text, out), self.project, self.state, lambda *_: FixtureEngine(),
                    fixture_id=fixture_id, driver_factory=lambda _: driver,
                    worktrees=self.root / "worktrees", profile=profile)
        return out.getvalue()

    def test_a3_profile_init_records_the_snapshot_and_creates_no_file(self):
        """`cli.main --fixture demo profile init` accepts into the fixture state and never writes
        `zplan.process.json` (named failure on the base: the file appears)."""
        code, text = self.run_main(["profile", "init"] + fixture_argv(self.project, self.state, "demo"))
        self.assertEqual(code, 0)
        self.assertIn("fixture state", text)
        self.assertFalse((self.project / PROFILE_FILE).exists())
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")
        self.assertTrue(self.sidecar().exists())

    def test_a3_bootstrap_accept_keeps_the_snapshot_and_reopen_stays_usable(self):
        """A plain fixture session accepting at bootstrap writes no file; accept -> plan -> reopen without the file
        still works (the profile is not read as deleted)."""
        self.run_session("a\nq\n")
        self.assertFalse((self.project / PROFILE_FILE).exists())
        with RealAuthority(self.state, self.project, fixture_id="demo") as authority:
            self.assertEqual(Profile.of(authority).status().state, "accepted")
        # accept -> plan: the fixture profile guards planning, and no "deleted" refusal appears without the file
        out = self.run_session("p\nRequested feature\n\ng\nq\nq\n")
        self.assertNotIn("deleted", out)
        self.assertIn("Plan r1", out)
        # reopen: the accepted profile is still there without the file
        status_out = io.StringIO()
        cli.status(Terminal(io.StringIO(), status_out), self.project, self.state, "demo",
                   lambda _: FixtureDriver(self.root / "fixture-runs"))
        self.assertNotIn("deleted", status_out.getvalue())
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")

    def test_a3_an_existing_project_file_is_refused_and_stays_byte_identical(self):
        """A fixture `profile init` with an existing file refuses (as in production) and the file is untouched; a
        fixture bootstrap accept over it leaves it byte-identical too."""
        document = json.dumps({"roles": {"planner": {"model": "owner-model", "effort": "high"}}}, ensure_ascii=False,
                              indent=2) + "\n"
        (self.project / PROFILE_FILE).write_text(document, encoding="utf-8")
        before = (self.project / PROFILE_FILE).read_bytes()
        code, _text = self.run_main(["profile", "init"] + fixture_argv(self.project, self.state, "demo"))
        self.assertEqual(code, 1)  # refused: the file is the source
        self.assertEqual((self.project / PROFILE_FILE).read_bytes(), before)
        self.run_session("a\nq\n")
        self.assertEqual((self.project / PROFILE_FILE).read_bytes(), before)

    def test_a3_accept_over_an_existing_file_keeps_the_snapshot_and_survives_its_removal(self):
        """R-3 (the reviewer's reproduction): a fixture accept in a project that already has `zplan.process.json`
        keeps the file byte-identical and records the effective snapshot in the fixture state, so `accept -> plan ->
        remove the file -> reopen` reads accepted, never accepted -> missing. Oracle: the raw sidecar record."""
        document = json.dumps({"roles": {"worker": {"model": "owner-model", "effort": "low"}}}, ensure_ascii=False,
                              indent=2) + "\n"
        (self.project / PROFILE_FILE).write_text(document, encoding="utf-8")
        before = (self.project / PROFILE_FILE).read_bytes()
        self.run_session("a\nq\n")  # accept at bootstrap, with the file present
        self.assertEqual((self.project / PROFILE_FILE).read_bytes(), before)
        with RealAuthority(self.state, self.project, fixture_id="demo") as authority:
            record = process.read_record(authority.directory)
        self.assertEqual(record["state"], "accepted")
        self.assertIsNotNone(record["snapshot"])  # the fixture record keeps the effective snapshot
        plan = self.run_session("p\nRequested feature\n\ng\nq\nq\n")
        self.assertIn("Plan r1", plan)
        (self.project / PROFILE_FILE).unlink()
        self.assertFalse((self.project / PROFILE_FILE).exists())
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")

    def test_a3_a_file_that_appears_does_not_erase_the_fixture_snapshot(self):
        """R-3 (the other half of the reviewer's finding): a project file that appears is the source, but a fixture
        session keeps its snapshot beside the file's digest, so the file may go away again and the profile is still
        accepted — status() must not erase the snapshot."""
        self.run_session("a\nq\n")  # a fixture accept without any project file
        self.assertFalse((self.project / PROFILE_FILE).exists())
        (self.project / PROFILE_FILE).write_text("{}", encoding="utf-8")
        self.run_session("q\n")  # a session adopts the file that appeared
        with RealAuthority(self.state, self.project, fixture_id="demo") as authority:
            record = process.read_record(authority.directory)
        self.assertEqual(record["state"], "accepted")
        self.assertIsNotNone(record["snapshot"])
        (self.project / PROFILE_FILE).unlink()
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")

    def test_a3_profile_init_promotes_a_deferred_demo_profile(self):
        """The reported spec gap, resolved: `profile init` refuses only an already *accepted* demo profile; a
        deferred one is promoted, exactly like a production `init` that writes the file over a "later"; the
        refusal message names the demo state, never a project file that was never created."""
        self.run_session("l\nq\n")  # defer at bootstrap
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "later")
        code, text = self.run_main(["profile", "init"] + fixture_argv(self.project, self.state, "demo"))
        self.assertEqual(code, 0)
        self.assertIn("fixture state", text)
        self.assertFalse((self.project / PROFILE_FILE).exists())
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")
        code, text = self.run_main(["profile", "init"] + fixture_argv(self.project, self.state, "demo"))
        self.assertEqual(code, 1)
        self.assertIn("The demo profile is already accepted", text)
        self.assertNotIn("already exists", text)  # no claim about a project file that does not exist

    def test_a3_a_fixture_defer_still_leaves_no_file(self):
        """`l` (later) in a fixture session decides in fixture state only: no file is written."""
        self.run_session("l\nq\n")
        self.assertFalse((self.project / PROFILE_FILE).exists())
        self.assertEqual(self.sidecar().exists(), True)

    def test_a3_an_existing_snapshot_free_acceptance_is_healed_and_survives_the_file(self):
        """R-3 (the reviewer's reproduction, an existing fixture namespace): the base left an `accepted` record
        without a snapshot beside a real `zplan.process.json`. A writable fixture session adopts the file's
        effective snapshot, so `accept -> plan -> remove the file -> reopen` reads accepted, never missing. The
        oracle is the sidecar parsed as raw JSON, independent of the product's record helpers."""
        document = json.dumps({"roles": {"worker": {"model": "owner-model", "effort": "low"}}}, ensure_ascii=False,
                              indent=2) + "\n"
        (self.project / PROFILE_FILE).write_text(document, encoding="utf-8")
        self.run_session("a\nq\n")  # a fixture accept with the file present: the record adopts the file's snapshot
        record = self.raw_record()
        self.assertEqual(record["state"], "accepted")
        self.assertIsNotNone(record["snapshot"])
        record["snapshot"] = None  # exactly the base's record: the file's digest, no snapshot
        self.write_raw_record(record)
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")
        plan = self.run_session("p\nRequested feature\n\ng\nq\nq\n")  # a writable session adopts the snapshot
        self.assertIn("Plan r1", plan)
        self.assertIsNotNone(self.raw_record()["snapshot"])
        (self.project / PROFILE_FILE).unlink()
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")

    def test_a3_an_interrupted_fixture_accept_recovers_with_the_snapshot(self):
        """R-3: a fixture accept interrupted between the file and the record (`accepting` in the sidecar, the file
        written, no previous record — the base's `profile init`) is finished with the effective snapshot, so
        removing the file still reads accepted. Oracle: the sidecar parsed as raw JSON."""
        document = json.dumps({"roles": {"worker": {"model": "owner-model", "effort": "low"}}}, ensure_ascii=False,
                              indent=2) + "\n"
        (self.project / PROFILE_FILE).write_text(document, encoding="utf-8")
        self.write_raw_record({"schema": 1, "state": "accepting", "digest": None, "snapshot": None, "previous": None})
        self.run_session("q\n")  # a writable session finishes the interrupted accept
        record = self.raw_record()
        self.assertEqual(record["state"], "accepted")
        self.assertIsNotNone(record["snapshot"])
        (self.project / PROFILE_FILE).unlink()
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")

    def test_a3_an_interrupted_fixture_accept_after_a_defer_recovers_with_the_snapshot(self):
        """R-3: the same interruption with a nested previous record (the base writes one when a deferred profile
        existed) still recovers to an accepted record that carries the snapshot."""
        self.run_session("l\nq\n")  # defer: the later record with its snapshot
        later = self.raw_record()
        self.assertEqual(later["state"], "later")
        (self.project / PROFILE_FILE).write_text("{}", encoding="utf-8")  # the file the accept wrote before crashing
        self.write_raw_record({"schema": 1, "state": "accepting", "digest": None, "snapshot": None,
                               "previous": {"state": "later", "digest": later["digest"], "snapshot": later["snapshot"]}})
        self.run_session("q\n")
        record = self.raw_record()
        self.assertEqual(record["state"], "accepted")
        self.assertIsNotNone(record["snapshot"])
        (self.project / PROFILE_FILE).unlink()
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")

    def test_a3_profile_init_from_a_missing_demo_profile_writes_no_file_and_stays_usable(self):
        """R-3 (the code reviewer's reproduction): a fixture namespace whose accepted record has no snapshot and
        whose file is gone reads `missing`; `profile init` must not dereference that None and must not write the
        target's file — it re-records the snapshot in the fixture state (like a production `init` deciding from the
        proposal), so a reopen is usable again."""
        (self.project / PROFILE_FILE).write_text("{}", encoding="utf-8")
        self.run_session("a\nq\n")
        record = self.raw_record()
        record["snapshot"] = None
        self.write_raw_record(record)
        (self.project / PROFILE_FILE).unlink()
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "missing")
        code, text = self.run_main(["profile", "init"] + fixture_argv(self.project, self.state, "demo"))
        self.assertEqual(code, 0, text)
        self.assertIn("fixture state", text)
        self.assertFalse((self.project / PROFILE_FILE).exists())
        self.assertIsNotNone(self.raw_record()["snapshot"])
        self.assertEqual(Profile.peek(self.project, root=self.state, fixture_id="demo").status().state, "accepted")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ProductionSessionTests(ProjectTest, unittest.IsolatedAsyncioTestCase):
    """R-4/A-4: production (no `--fixture`) keeps working: the chat prepares with the real probes, one turn
    completes with the scripted provider, and accepting the profile writes the target's file."""

    def controller(self):
        from terminal_planner.tui.controller import Controller
        # production (no --state-dir, no fixture id): the canonical Git authority and the production profile
        controller = Controller.for_project(self.project, None, fixture_id=None,
                                            driver_factory=lambda _: FixtureDriver(self.root / "fixture-runs"),
                                            readiness=lambda: [])
        self.addCleanup(controller.stop)
        return controller

    async def test_a4_production_chat_probes_and_the_profile_file(self):
        """One production turn through the production prepare (the tool probe runs) with the scripted codex; the
        production `Profile.of` accept writes `zplan.process.json` (no regression)."""
        from test_tui_chat import Fixture, chat_band
        from textual.widgets import Input
        fixture = Fixture(self.root, self.project)
        prepares = []
        real_prepare = chat_module.default_prepare

        def spy_prepare(project):
            prepares.append(project)
            return real_prepare(project)

        from terminal_planner.tui.app import ZplanApp
        with contextlib.ExitStack() as stack:
            for patcher in toolchain_patches(self.root, fixture):
                stack.enter_context(patcher)
            stack.enter_context(patch.object(chat_module, "default_prepare", spy_prepare))
            app = ZplanApp(self.controller(), chat_prepare=None, chat_binding=fixture.binding())
            async with app.run_test(size=(120, 40)) as pilot:
                end = time.monotonic() + 8
                while not (app.chat is not None and app.chat.state.phase != "preparing"):
                    self.assertLess(time.monotonic(), end, screen_text(app))
                    await pilot.pause(0.05)
                field = app.query_one("#input", Input)
                field.focus()
                field.value = "привет"
                await pilot.press("enter")
                while app.chat.busy:
                    await pilot.pause(0.05)
                await pilot.pause(0.2)
                self.assertIn("Привет.", chat_band(app))
            self.assertEqual(prepares, [self.project])  # the production prepare (tool probes) ran
        # production accept writes the file, and a second accept leaves it byte-identical
        with RealAuthority(None, self.project) as authority:  # production: no --state-dir (canonical authority)
            status = Profile.of(authority).accept()
        self.assertEqual(status.state, "accepted")
        target = self.project / PROFILE_FILE
        self.assertTrue(target.is_file())
        before = target.read_bytes()
        with RealAuthority(None, self.project) as authority:
            Profile.of(authority).accept()
        self.assertEqual(target.read_bytes(), before)


class DocsTests(unittest.TestCase):
    """R-5/A-5: the live docs name the fixture chat boundary, and the REFERENCE generator check still passes."""

    def test_a5_the_reference_generator_check_passes(self):
        repo = Path(__file__).resolve().parents[1]
        self.assertEqual(catalog.main(["--check", str(repo / "docs" / "REFERENCE.md")]), 0)

    def test_a5_the_docs_state_the_fixture_chat_boundary(self):
        repo = Path(__file__).resolve().parents[1]
        self.assertIn("sets the model and effort of each architect chat turn",
                      (repo / "docs" / "REFERENCE.md").read_text(encoding="utf-8"))
        architecture = (repo / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("process.py:", architecture)
        self.assertIn("tui/chat.py:", architecture)
        flow = (repo / "docs" / "USER_FLOW.md").read_text(encoding="utf-8")
        self.assertIn("The architect chat is unavailable in the demo", flow)
        self.assertIn("zplan.process.json", flow)

    def test_a5_the_docs_markdown_stays_unbroken(self):
        import test_docs
        report = test_docs.glued((Path(__file__).resolve().parents[1] / "docs" / "USER_FLOW.md").read_text(
            encoding="utf-8"))
        self.assertEqual(report, [])
