"""I6: the main screen speaks the chosen UI language (tests/test_tui_language.py).

Two whole-app tests, one per acceptance group (A5): A1+A2 and A3+A4, both through `tests/test_tui.py`'s shell at
120x40. L1 adds one whole-app test (the first start with one offered language) and a unit test of `/language`; the
A1-A4 tests patch `strings.OFFERED` to all three languages, which is how they pin the chooser and the English texts. A5's "every new strings id has en, ru and zh" is `tests/test_tui_strings.py`'s catalog walk — it walks
`strings.CATALOG`, so the ids this run adds are covered there without a per-id list here.

Interpretations recorded here (the worker's summary never reaches the reviewers):

* The input placeholder is the lab's `chat.placeholder` (`Напиши архитектору… или / для команд`). i6 had the
  screen read a separate `chat.input` id whose `ru` was then today's literal, because the brief then required
  every migrated `ru` to stay the old one; i9/A2 moved the input into the chat pane as the lab's prompt box and
  took the lab's own wording with it, so `chat.placeholder` is the id the screen reads now (`chat.input` stays in
  the catalog for the callers that read it). A1's `ru` leg pins this wording.
* `QUIT_WAITS` is listed among the status lines whose text moves into the catalog, so its constant holds the id
  `chat.quit_waits` and the finishing modal renders `strings.text` of it; the rest of that modal and the other
  modals stay outside i6 (`docs/RELEASE_0.5.2_PLAN.md`, the brief's non-goals). Its `ru` is today's literal, so a
  Russian screen keeps the line (tests/test_tui_milestones.py still sees it).
* A3's first frame. When `strings.store_path()` has no file the chooser is pushed first and the profile modal only
  after the chooser answers, so the first thing the owner sees is the chooser. The test pins the *visible* frame
  (the top screen is the chooser while the profile is still undecided), then the profile modal, then the stored
  `ru` and the Russian main screen behind it — not the internal push order.
* `default_language()` (the chooser's preselection) is pinned by clearing `LC_ALL`/`LC_MESSAGES`/`LANG` exactly as
  `tests/test_tui_strings.py` does, so the first marked row is `en` on every host and one ↓ reaches «Русский».
* The screen's own texts are read from the widgets that paint them (the panes' border titles, the tab strip's
  labels, the `Bar`'s row and the `#input` placeholder): A1 names those parts, and a whole-screen Cyrillic scan
  would also catch the engine's own plan lines, which stay the engine's (out of scope). i9 dropped the readiness
  `#header` `Static` this list also named; the project and branch it carried are read from the `Bar` now.
* The first-run chooser is triggered by the missing store alone (rejection repair), so a test whose config root
  carries no `ui.json` and drives the real shell gets the chooser over the main screen. The tests that point
  `XDG_CONFIG_HOME` at their own tree therefore store a language: `tests/tui_support.py` pins `ru` process-wide,
  and `tests/test_process.py`'s `ProfileTest`, `tests/test_tui_chat.py`'s `LifecycleGuardChatTests` and the one
  `tests/test_tui_planning.py` case that runs the shell inside its own config patch store `ru` too (they override
  the pin, so it never reached them). `tests/test_tui_activity_pane.py` already stores `ru` itself.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

# First, for the wheelhouse side effect (`ZPLAN_TEST_WHEELHOUSE` joins `sys.path` before the app import), like the
# other TUI test modules.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

from test_tui import ShellTest

from terminal_planner import process
from terminal_planner.authority import Authority

try:
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import strings
except ImportError:  # pragma: no cover - the toolchain scan of tests.test_toolchain covers this path
    ui = strings = None

HAVE = HAVE_TEXTUAL and ui is not None and strings is not None
MISSING_REASON = "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"

CYRILLIC = range(0x0400, 0x0500)  # the Cyrillic block


def cyrillic(text):
    """The Cyrillic characters in `text` (A1: the `en` screen must show none)."""
    return [character for character in text if ord(character) in CYRILLIC]


@unittest.skipUnless(HAVE, MISSING_REASON)
class MainScreenLanguageTests(ShellTest):
    """A1+A2 and A3+A4 through the real shell: at most two whole-app tests (A5)."""

    def setUp(self):
        super().setUp()
        offered = patch.object(strings, "OFFERED", strings.LANGUAGES)  # L1: A1-A4 pin all three languages
        offered.start()
        self.addCleanup(offered.stop)

    def main(self):
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def chat_title(self):
        return self.main().query_one("#chat-pane").border_title

    def plan_title(self):
        """i9/A4: the canvas frame's title — the `#right` box around the tab strip, whose title names the canvas
        state (`<project> · работы нет` at idle). The plan tab's pane carries no border title of its own since the
        state title (and the border it rides) belongs to the frame across every canvas tab."""
        return self.main().query_one("#right").border_title

    def tabs(self):
        strip = self.main().query_one("#right", ui.TabbedContent)
        return [strip.get_tab(tab).label.plain for tab in (ui.TAB_LIVE, ui.TAB_PLAN)]

    def placeholder(self):
        return self.main().query_one("#input", ui.Input).placeholder

    def chat_off(self):
        """The catalog's own refusal line, the one the chat pane draws when no chat is built at all (a `--fixture`
        demo or an unknown project). It is read from the catalog at every paint, so it follows a language switch
        made after the app was built (the first-run pick does exactly that)."""
        return self.app.chat_off

    def bar(self):
        return screen_lines(self.app)[-1]

    def use_config(self, code):
        """A config root this test owns, holding `{"language": code}` (`None`: no file — the first-run case), and
        an empty locale, so `default_language()` and `language()` are deterministic. A context manager: the
        environment is restored when it leaves, and `self.store` is the `ui.json` the app reads and writes."""
        root = Path(tempfile.mkdtemp(prefix="zs-language-", dir=str(self.root)))
        self.store = root / "planning-kit" / "ui.json"
        self.store.parent.mkdir(parents=True, exist_ok=True)
        if code is not None:
            self.store.write_text(json.dumps({"language": code}), encoding="utf-8")
        return patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root), "LC_ALL": "", "LC_MESSAGES": "", "LANG": ""})

    # A1 + A2 ------------------------------------------------------------------------------------------
    async def test_a1_a2_the_main_screen_speaks_the_stored_language_and_a_switch_relabels_it(self):
        """A1: at 120x40, with `ui.json` `en` the chat pane's title, the tabs, the canvas frame's title (i9/A4:
        the `#right` box's state title) and the plan pane's footer line, the `Bar` (project, branch and the job
        phrase) and the input placeholder show no Cyrillic; with `ru` the same parts read as today's Russian. A2:
        `choose_language("zh")` on the running screen relabels the tabs and the bar at once and stores `zh` in
        `ui.json`. (i9 dropped the readiness `#header` this test also read; the project and branch it carried are
        read from the `Bar` now.)"""
        with self.use_config("en"):
            async with self.shell(size=(120, 40)) as pilot:
                await self.loaded(pilot)
                parts = {"chat title": self.chat_title(), "tabs": " ".join(self.tabs()),
                         "plan title": self.plan_title(), "bar": self.bar(),
                         "input placeholder": self.placeholder(), "chat refusal": self.chat_off()}
                for where, text in parts.items():
                    self.assertEqual(cyrillic(text), [], "%s: %r" % (where, text))
                self.assertEqual(self.tabs(), ["Scheme", "Plan"])
                self.assertEqual(self.chat_title(), "Conversation with the architect")
        with self.use_config("ru"):
            async with self.shell(size=(120, 40)) as pilot:
                await self.loaded(pilot)
                self.assertEqual(self.chat_title(), "Разговор с архитектором")
                self.assertEqual(self.tabs(), ["Схема", "План"])
                # i9/A4: the canvas frame names the idle state (`<project> · работы нет`), the plan tab's own title
                # («План») is the tab label the `tabs` check above reads
                self.assertEqual(self.plan_title(),
                                 "%s · %s" % (self.app.snapshot.project, strings.text("bar.idle")))
                self.assertEqual(self.placeholder(), "Напиши архитектору… или / для команд")
                self.assertEqual(self.chat_off(), "Чат архитектора недоступен: проект не выбран.")
                self.assertIn("вкладки", self.bar())  # the Bar's own key hint, in today's Russian
                self.assertIn("работы нет", self.bar())  # i9: the job phrase the old header/status carried
        with self.use_config("ru"):
            async with self.shell(size=(120, 40)) as pilot:
                await self.loaded(pilot)
                self.main().choose_language("zh")
                await pilot.pause()
                self.assertEqual(self.tabs(), ["流程图", "计划"])
                self.assertIn("没有任务", self.bar())  # the idle job phrase follows the language too
                self.assertEqual(self.chat_title(), "与架构师的对话")
                self.assertEqual(self.chat_off(), strings.text("chat.refused"))  # the pane's own refusal line too
                self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), {"language": "zh"})

    # A3 + A4 ------------------------------------------------------------------------------------------
    async def test_a3_a4_the_first_run_asks_once_and_slash_language_opens_the_chooser(self):
        """A3: with no `ui.json` the first frame is the chooser, before the profile modal; enter on «Русский»
        stores `ru` and the main screen behind is Russian; a second start with the store shows the profile modal
        and no chooser. A3 (rejection regression): an existing deferred profile with no store still gets the
        chooser and no profile modal, so onboarding is keyed on the store, not `profile.state`. A4: `/language`
        typed in the palette opens the chooser.

        Interpretation (flake-waits F4): this test never reads `#bootstrap-body` itself; it waits for the body to
        be mounted right after each wait for the `BootstrapScreen` class, so the reads below never run on a
        modal whose compose is not done."""
        with self.use_config(None):
            async with self.shell(self.controller(profile=True), size=(120, 40)) as pilot:
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "LanguageScreen")
                await pilot.pause()
                shown = screen_text(self.app)
                self.assertIn("English", shown)  # the three languages, each by its own display name
                self.assertIn("Русский", shown)
                self.assertIn("中文", shown)
                await pilot.press("down")  # the preselection is `default_language()`: en -> ru
                await pilot.pause()
                await pilot.press("enter")
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "BootstrapScreen")
                await self.until(pilot, lambda: self.app.screen.query("#bootstrap-body"))
                self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), {"language": "ru"})
                # the main screen behind the profile modal already reads the chosen language
                self.assertEqual(self.placeholder(), "Напиши архитектору… или / для команд")
                self.assertEqual(self.tabs(), ["Схема", "План"])
                self.assertEqual(self.chat_title(), "Разговор с архитектором")
                # the pane's own refusal line follows the pick too: it is read from the catalog at every paint,
                # never baked once at start-up, though this app was built while the language was still `en`
                self.assertEqual(self.chat_off(), "Чат архитектора недоступен: проект не выбран.")
            async with self.shell(self.controller(profile=True), size=(120, 40)) as pilot:
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "BootstrapScreen")
                await self.until(pilot, lambda: self.app.screen.query("#bootstrap-body"))
                self.assertNotIn("LanguageScreen", [type(screen).__name__ for screen in self.app.screen_stack])
                self.assertEqual(self.placeholder(), "Напиши архитектору… или / для команд")
            async with self.shell(size=(120, 40)) as pilot:
                await self.loaded(pilot)
                await pilot.press("/")
                await pilot.pause()
                await pilot.press(*"language")
                await pilot.pause()
                await pilot.press("enter")
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "LanguageScreen")
                self.assertIn("Русский", screen_text(self.app))  # the chooser, over the Russian main screen

        # Rejection A3 regression: the chooser is triggered by the missing language store alone, never by
        # `profile.state`. An existing deferred ("later") profile with no `ui.json` — the state an upgrading
        # project is in, since earlier versions stored no language — still gets the chooser first, and no profile
        # modal follows it (a deferred profile needs no first-start choice); the second start has the store and
        # shows neither.
        with self.use_config(None):
            with Authority(self.state, self.project, fixture_id="test") as authority:
                process.Profile.of(authority).defer()
            async with self.shell(self.controller(profile=True), size=(120, 40)) as pilot:
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "LanguageScreen")
                self.assertNotIn("BootstrapScreen",
                                 [type(screen).__name__ for screen in self.app.screen_stack])
                await pilot.press("enter")  # the preselected `default_language()`: `en` (locale emptied)
                await self.until(pilot, lambda: self.store.exists())
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
                self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), {"language": "en"})
            async with self.shell(self.controller(profile=True), size=(120, 40)) as pilot:
                await self.loaded(pilot)
                self.assertNotIn("LanguageScreen", [type(s).__name__ for s in self.app.screen_stack])
                self.assertNotIn("BootstrapScreen", [type(s).__name__ for s in self.app.screen_stack])


    async def test_l1_with_one_offered_language_the_first_start_opens_no_chooser(self):
        """L1/C2 (the one whole-app test L1 adds): a fresh config root (no `ui.json`) with an `en` locale and a
        profile that still needs its choice -> the top screen is the profile modal and `LanguageScreen` is never in
        the stack; the screen behind reads English (C1) and no `ui.json` is written."""
        with patch.object(strings, "OFFERED", ("en",)), self.use_config(None), \
                patch.dict(os.environ, {"LANG": "en_US.UTF-8"}):
            async with self.shell(self.controller(profile=True), size=(120, 40)) as pilot:
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "BootstrapScreen")
                await self.until(pilot, lambda: self.app.screen.query("#bootstrap-body"))
                self.assertNotIn("LanguageScreen", [type(screen).__name__ for screen in self.app.screen_stack])
                self.assertEqual(self.placeholder(), "Write to the architect… or / for commands")
                self.assertFalse(self.store.exists())


@unittest.skipUnless(HAVE, MISSING_REASON)
class MainScreenTextTests(unittest.TestCase):
    """The rejection's two non-first-run defects, checked directly on the module that causes them (no whole app:
    A5 caps `test_tui_language.py` at two whole-app tests, `MainScreenLanguageTests` above)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "config"),
                                                   "LC_ALL": "", "LC_MESSAGES": "", "LANG": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        offered = patch.object(strings, "OFFERED", strings.LANGUAGES)  # L1: the switches below pin ru and en
        offered.start()
        self.addCleanup(offered.stop)

    def test_l1_slash_language_with_one_offered_language_changes_nothing_and_says_so(self):
        """L1/C3: `choose_language` (what `/language` and `/language en` reach through `COMMAND_ACTIONS`) with
        `OFFERED` at `("en",)` opens no chooser, stores nothing and sets one note. Interpretation: any argument
        gets the same note, since there is nothing to choose; the note is shown through `status_note`, the line
        every other `/` refusal uses."""
        notes, pushed = [], []

        class Screen:
            app = type("App", (), {"push_screen": lambda self, *args: pushed.append(args)})()

            def status_note(self, line):
                notes.append(line)

            def relabel(self):
                raise AssertionError("nothing may be relabelled")

        strings.set_language("ru")  # what a 0.7.x install stored
        before = strings.store_path().read_text(encoding="utf-8")
        with patch.object(strings, "OFFERED", ("en",)):
            for argument in (None, "en", "zh", "ru"):
                ui.MainScreen.choose_language(Screen(), argument)
            self.assertEqual(strings.language(), "en")
            self.assertEqual(notes, [strings.text("note.only_russian")] * 4)
        self.assertEqual(pushed, [])
        self.assertEqual(strings.store_path().read_text(encoding="utf-8"), before)

    def test_slash_language_is_hidden_while_one_language_is_offered(self):
        """U1: with `OFFERED == ("en",)` a typed `/language` is an unknown command and `/` does not list it; with
        all three languages offered it resolves and is listed."""
        from terminal_planner.tui import slash

        with patch.object(strings, "OFFERED", ("en",)):
            self.assertIsNone(slash.parse("/language").command)
            self.assertIsNone(slash.parse("/language en").command)
            self.assertNotIn("/language", [command.name for command in slash.matches("/")])
            self.assertNotIn("/language", [command.name for command in slash.matches("/lang")])
            self.assertEqual(slash.parse("/plan x").command.name, "/plan")  # the other commands are unaffected
        self.assertEqual(slash.parse("/language").command.name, "/language")  # all three offered (setUp patch)
        self.assertIn("/language", [command.name for command in slash.matches("/")])

    def test_the_plan_screens_progress_title_keeps_the_literal_it_assigns(self):
        """Rejection scope regression: `screens.py` imports `app.PROGRESS_TITLE` and assigns it straight to the
        PlanScreen progress border (`#plan-progress`), so the constant must stay a literal that screen shows; the
        catalog id `chat.title_planning` keeps that same text in `en`. (i9 stopped the chat pane
        border cycling through that id, but the id stays in the catalog for the callers that read it.) Turning the
        constant into the id would make an out-of-scope screen show the raw id."""
        self.assertEqual(ui.PROGRESS_TITLE, "Planner")
        self.assertEqual(strings.CATALOG["chat.title_planning"]["en"], ui.PROGRESS_TITLE)

    def test_a_pending_status_renders_in_the_current_language_and_clears_by_identity(self):
        """Rejection A3/status regression: a pending main-screen status line stores its catalog identity and
        arguments, not rendered text, so it follows a language switch; the clearing paths recognise it by that
        identity, never by comparing text (a stored Russian status must still clear after switching to `en`)."""
        strings.set_language("ru")
        note = ui.RunNote(ui.STOP_REQUESTED, stage="M1")
        self.assertEqual(ui.note_text(note), "Остановка M1 запрошена; жду подтверждения Zeroshot.")
        strings.set_language("en")
        self.assertEqual(ui.note_text(note), "Stop of M1 requested; waiting for Zeroshot to confirm.")
        self.assertTrue(ui.note_is(note, ui.STOP_REQUESTED))
        self.assertFalse(ui.note_is(note, ui.READING))
        self.assertTrue(ui.note_is(ui.RunNote(ui.READING), ui.READING))
        self.assertEqual(ui.note_text("Not stopped: x"), "Not stopped: x")  # a plain note passes through

    def test_a_status_note_on_the_plan_screen_reaches_it_as_plain_text(self):
        """Rejection regression: `e` on the plan screen (`PlanScreen.action_tail` → `ZplanApp.show_tail`) says the
        catalog note `READING` while a run is tailed. On the home the note must stay a `RunNote` so a later switch
        relabels it; the plan screen is out of i6's scope and renders `plan_lines` through `text.wrapped`, which
        measures every entry (`len`), so a note reaching it must be text. Before the fix `say_note` stored the
        object and `PlanScreen.render_state` raised `TypeError: object of type 'RunNote' has no len()`.

        The route is exercised at the boundary the crash is in — the real `ZplanApp.say_note` with the real
        `PlanScreen` type check it makes and the real `text.wrapped` renderer the plan screen calls — rather than
        with a third whole-app test (A5 caps this file at two, `MainScreenLanguageTests`)."""
        from terminal_planner.tui.screens import PlanScreen
        from terminal_planner.tui.text import wrapped

        class Shell:  # only the fields `say_note` reads, the screen being the real type its branch checks
            run_note = ""
            plan_lines = ()

            def __init__(self, screen):
                self.screen = screen

            def changed(self):
                pass

        strings.set_language("ru")
        home = Shell(object())  # the home (no PlanScreen): the note stays deferred
        ui.ZplanApp.say_note(home, ui.RunNote(ui.READING))
        self.assertTrue(ui.note_is(home.run_note, ui.READING))
        self.assertEqual(ui.note_text(home.run_note), "Читаю журнал Zeroshot…")
        strings.set_language("en")  # a switch relabels the still-pending home note
        self.assertEqual(ui.note_text(home.run_note), "Reading the Zeroshot journal…")

        plan = Shell(PlanScreen())  # the plan screen: the note must arrive as text
        ui.ZplanApp.say_note(plan, ui.RunNote(ui.READING))
        self.assertEqual(plan.run_note, "")  # nothing leaks to the home's note
        self.assertEqual(plan.plan_lines, ("Reading the Zeroshot journal…",))
        self.assertTrue(all(isinstance(line, str) for line in plan.plan_lines))
        self.assertEqual(wrapped(plan.plan_lines, 60), ["Reading the Zeroshot journal…"])


if __name__ == "__main__":
    unittest.main()
