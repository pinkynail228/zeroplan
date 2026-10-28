"""W1: the chat decision-card widget `terminal_planner/tui/cards.py` — acceptance criteria A1-A6.

A new module only, with nothing wired into the app yet: the tests mount a single `Card` in a minimal Textual `App`
(no project, no controller, no network), at 80 and 120 columns, and read the plain screen and the widget tree. They
need Textual (the interpreter's own, or the wheels of `ZPLAN_TEST_WHEELHOUSE`) and are declared and skipped without
it, never hidden.

Every test runs on a scratch `XDG_CONFIG_HOME` with the locale variables pinned empty (the same fixture as
`tests/test_tui_strings.py`): the builders read their copy through `strings.text`, which resolves the language from
`setup.config_root() / ui.json`, and that path must never be the runner's own home state.

Worker interpretations (the reviewers inspect this docstring; the worker's final summary is not shown to them):
- `error_card(fix=...)` has no `fix` field on `CardSpec` (the task fixes that field set), so the exact shell command
  is appended to the caller's `text` on its own line (`"{text}\\n{fix}"`) and is shown verbatim — never passed
  through `strings.text`, so no placeholder is substituted into it (`test_a5_...` checks the line byte-for-byte).
- The default hint of an open card is resolved by the widget from `card.hint` with the button commands joined by
  " · " (`CardSpec.hint is None`); `question_card` instead carries the fixed `card.question_hint` text (A1/A2).
- The `alarm` flag is checked on the error card, its one user (the red border class, `Card.alarm` in `DEFAULT_CSS`).
"""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner.tui import strings
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

try:  # the module needs Textual; without it the classes are declared and skipped (tests.test_toolchain)
    from textual.app import App
    from textual.widgets import Button
    from terminal_planner.tui import cards
    _HAVE_CARDS = True
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    App = Button = cards = None
    _HAVE_CARDS = False

HAVE = HAVE_TEXTUAL and _HAVE_CARDS
REASON = "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with the textual wheels is needed"
# Without Textual the helper is still declared (its tests are skipped), so the module always imports.
_AppBase = App if App is not None else object


class CardApp(_AppBase):
    """A minimal app: one card, and every `Card.Chosen` it posts recorded in `chosen`."""

    def __init__(self, card):
        super().__init__()
        self.card = card
        self.chosen = []

    def compose(self):
        yield self.card

    def on_card_chosen(self, message):
        self.chosen.append(message)


# The card's frame glyphs; dropping them lets a wrapped source line be matched against the screen text.
FRAME = "│╭╮╰╯─"


def flat(text):
    """`text` with runs of whitespace collapsed, so a wrapped screen line still matches a source line."""
    return " ".join(text.split())


def visible(app):
    """What the screen shows with the card's frame glyphs dropped and whitespace collapsed."""
    return flat("".join(character for character in screen_text(app) if character not in FRAME))


@unittest.skipUnless(HAVE, REASON)
class CardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """A scratch configuration root and pinned locale variables, as in `tests/test_tui_strings.py`.

        `strings.text` -> `language` -> `_stored` reads `setup.config_root() / ui.json`, and `config_root` follows
        the runner's `HOME`/`XDG`: without this fixture the card tests would inspect the runner's own preferences.
        `XDG_CONFIG_HOME` alone redirects `config_root` (it wins over `HOME`), and the three locale variables are
        emptied so the default language is the pinned EN.
        """
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config"),
                                                   "LC_ALL": "", "LC_MESSAGES": "", "LANG": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        offered = patch.object(strings, "OFFERED", strings.LANGUAGES)  # L1: these tests pin all three languages
        offered.start()
        self.addCleanup(offered.stop)

    def specs(self):
        """One open spec per builder, in the shapes the task names."""
        return [
            cards.draft_card("draft-1", "21:03"),
            cards.plan_card("plan-1", "21:05", "3 этапа", "9 задач"),
            cards.merge_card("merge-1", "22:06", "M2 Экспорт CSV", "5", "5"),
            cards.question_card("q-1", "21:58", "T3", "Ревью отклонило T3 четыре раза подряд. Что делаем?",
                                [("упростить", "/approve"), ("разбить", "/approve"), ("пропустить", "/decline")]),
            cards.error_card("e-1", "21:57", "T3", "Исполнитель остановился: модель не ответила за 10 минут.",
                             [("новая попытка", "/approve"), ("подробнее", "/status")]),
        ]

    def expected_hint(self, spec):
        if spec.hint is not None:
            return spec.hint
        return strings.text("card.hint", commands=" · ".join(command for _, command in spec.buttons))

    # A1 -------------------------------------------------------------------------------------------
    def test_a1_each_builder_resolves_its_ids_and_values_through_strings(self):
        """A1: every title, text, button label and the question hint equal the `strings.text` result for their ids."""
        draft = cards.draft_card("d", "21:03")
        self.assertEqual(draft.title, strings.text("card.draft_title"))
        self.assertEqual(draft.text, strings.text("card.draft_text"))
        self.assertEqual(draft.buttons, ((strings.text("card.plan_yes"), "/plan"),
                                         (strings.text("card.no"), "/decline")))
        self.assertIsNone(draft.hint)

        plan = cards.plan_card("p", "21:05", "3 этапа", "9 задач")
        self.assertEqual(plan.title, strings.text("card.plan_title", stages="3 этапа", tasks="9 задач"))
        self.assertEqual(plan.text, strings.text("card.plan_text"))
        self.assertEqual(plan.buttons, ((strings.text("card.approve_yes"), "/approve"),
                                        (strings.text("card.revise"), "/decline")))

        merge = cards.merge_card("m", "22:06", "M2 Экспорт CSV", "5", "5")
        self.assertEqual(merge.title, strings.text("card.merge_title", stage="M2 Экспорт CSV"))
        self.assertEqual(merge.text, strings.text("card.merge_text", done="5", total="5"))
        self.assertEqual(merge.buttons, ((strings.text("card.merge_yes"), "/merge"),
                                         (strings.text("card.merge_changes"), "/diff")))

        question = cards.question_card("q", "21:58", "T3", "текст", [("упростить", "/approve")])
        self.assertEqual(question.title, strings.text("card.question_title", task="T3"))
        self.assertEqual(question.text, "текст")
        self.assertEqual(question.hint, strings.text("card.question_hint"))

        error = cards.error_card("e", "21:57", "T3", "сбой", [("подробнее", "/status")])
        self.assertEqual(error.title, strings.text("card.error_title", task="T3"))
        self.assertEqual(error.text, "сбой")
        self.assertTrue(error.alarm)
        self.assertTrue(cards.error_card("e", "21:57", "T3", "сбой", [], fix="true").text.endswith("\ntrue"))

        closed = cards.closed(draft, strings.text("card.draft_sent", time="21:04"))
        self.assertEqual(closed.done, strings.text("card.draft_sent", time="21:04"))
        self.assertEqual(cards.closed(plan, strings.text("card.plan_done", time="21:05")).done,
                         strings.text("card.plan_done", time="21:05"))

    # A2 -------------------------------------------------------------------------------------------
    async def test_a2_open_card_shows_title_text_buttons_and_hint_without_overflow(self):
        """A2: at 80 and 120 columns every open card shows its title, text, all button labels and the hint; no button
        row (and no single button) is wider than the card."""
        for size in ((80, 24), (120, 40)):
            for spec in self.specs():
                with self.subTest(size=size, key=spec.key):
                    app = CardApp(cards.Card(spec))
                    async with app.run_test(size=size) as pilot:
                        await pilot.pause()
                        card = app.query_one(cards.Card)
                        seen = visible(app)
                        self.assertIn(flat(spec.title), seen)
                        self.assertIn(flat(spec.text), seen)
                        for label, _ in spec.buttons:
                            self.assertIn(flat(label), seen)
                        self.assertIn(flat(self.expected_hint(spec)), seen)
                        row = card.query_one(".buttons")
                        self.assertLessEqual(row.region.width, card.region.width)
                        for button in card.query(Button):
                            self.assertLessEqual(button.region.right, card.region.right)

    # A3 -------------------------------------------------------------------------------------------
    async def test_a3_each_button_press_posts_one_chosen_with_its_command_and_card(self):
        """A3: clicking a button posts exactly one `Card.Chosen` carrying that button's command line and the card
        whose `spec.key` is the one the builder got."""
        for spec in self.specs():
            for index, (_, command) in enumerate(spec.buttons):
                with self.subTest(key=spec.key, command=command):
                    app = CardApp(cards.Card(spec))
                    async with app.run_test(size=(80, 24)) as pilot:
                        await pilot.pause()
                        card = app.query_one(cards.Card)
                        await pilot.click(card.query(Button)[index])
                        await pilot.pause()
                        self.assertEqual(len(app.chosen), 1, "exactly one Card.Chosen per press")
                        message = app.chosen[0]
                        self.assertEqual(message.command, command)
                        self.assertIs(message.card, card)
                        self.assertEqual(message.card.spec.key, spec.key)

    # A5 -------------------------------------------------------------------------------------------
    async def test_a5_error_fix_is_shown_verbatim_on_its_own_line(self):
        """A5: `error_card(..., fix="git remote add origin URL")` shows that exact command on a line of its own, with
        the error card's red `alarm` style."""
        fix = "git remote add origin URL"
        spec = cards.error_card("e", "21:57", "T3", "Пуш не настроен.", [("подробнее", "/status")], fix=fix)
        app = CardApp(cards.Card(spec))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            card = app.query_one(cards.Card)
            self.assertIn("alarm", card.classes)
            lines = screen_lines(app)
            own = [line for line in lines
                   if line.strip().startswith("│") and line.strip().endswith("│")
                   and line.strip()[1:-1].strip() == fix]
            self.assertTrue(own, lines)

    # regression: Textual markup in caller text ----------------------------------------------------
    async def test_regression_caller_text_with_brackets_is_shown_verbatim(self):
        """Regression: `Static` parses console markup by default, so a card silently altered bracketed text -
        `error_card(..., fix="git remote add origin '../[archive]/repo.git'")` rendered `'..//repo.git'`,
        dropping `[archive]` as a markup tag, and `text="Missing config[default]. Retry?"` lost `[default]`. A2
        shows the caller's text and A5 shows `fix` as an exact shell command, so the text/fix/hint `Static`s render
        literally (`markup=False`) and the border title/subtitle take a `rich.text.Text` (a `border_title` set from
        a plain `str` is rendered as markup too, which dropped the bracketed task name).

        Interpretations recorded here (both reviewers inspect this docstring): `CardSpec` has no `fix` field (the
        task fixes that field set), so the command is appended to `text` as its own line and reaches the screen
        through that same literal `Static` - the only path from a caller's string to the screen, so `fix` needs no
        separate rendering. `question_card`/`error_card` hand caller text and a caller `task` through that path:
        the caller text of both, the exact `fix` line and the task name in the title are checked. The command is
        kept short enough to stay on one line at 120 columns, so its line can be compared byte-for-byte.
        """
        fix = "git remote add origin '../[archive]/repo.git'"
        error = cards.error_card("e", "21:57", "[T3]", "Нет origin[default].", [("подробнее", "/status")], fix=fix)
        app = CardApp(cards.Card(error))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            lines = screen_lines(app)
            self.assertIn(fix, visible(app), lines)
            own = [line for line in lines
                   if line.strip().startswith("│") and line.strip().endswith("│")
                   and line.strip()[1:-1].strip() == fix]
            self.assertTrue(own, lines)
            self.assertIn("Нет origin[default].", visible(app), lines)
            self.assertIn("[T3]", visible(app), lines)

        question = cards.question_card("q", "21:58", "[T3]", "Missing config[default]. Retry?",
                                       [("ok", "/approve")])
        app = CardApp(cards.Card(question))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            seen = visible(app)
            self.assertIn("Missing config[default]. Retry?", seen)
            self.assertIn("[T3]", seen)

    # A6 / test-environment rule -------------------------------------------------------------------
    def test_a6_cards_use_a_scratch_config_root_and_pinned_locale(self):
        """Regression: `strings.text` -> `language` -> `_stored` reads `setup.config_root() / ui.json`, so a card
        test without an isolated `XDG_CONFIG_HOME` would inspect (and might write) the runner's own preferences.

        Interpretations recorded here (both reviewers inspect this docstring): the fixture copies
        `tests/test_tui_strings.py` exactly - a temporary `XDG_CONFIG_HOME` plus `LC_ALL`/`LC_MESSAGES`/`LANG`
        emptied, so the default language is the pinned EN. Only `XDG_CONFIG_HOME` is redirected, because
        `setup.config_root()` prefers it over `HOME`. The store path is asserted to sit under the scratch root, for
        reads (`language`) and for writes (`set_language`), while the builders keep resolving through `strings.text`.
        """
        self.assertTrue(str(strings.store_path()).startswith(str(self.root) + os.sep), strings.store_path())
        self.assertEqual(strings.language(), "en")
        draft = cards.draft_card("d", "21:03")
        self.assertEqual(draft.title, strings.text("card.draft_title"))
        strings.set_language("ru")
        self.assertEqual(strings.language(), "ru")
        self.assertEqual(strings.store_path().read_text(encoding="utf-8").strip(), '{"language":"ru"}')


@unittest.skipUnless(HAVE, REASON)
class ProducerConsumerHintTests(unittest.TestCase):
    """U2 (delivery.py:542 -> tui/app.py PLAN_TAB_HINTS; the glossary phrases -> app.py RUN_TAB_HINT / KEY_HINT): the
    producer's real output is fed to the consumer, so the two ends cannot drift apart again. The tasks line pair
    (delivery `tasks_lines` -> card_kinds `MERGE_TASKS`) is `tests/test_tui_merge_card.py`'s `tasks_line`, which
    feeds the real producer's line through the merge card's source.

    Interpretations: (1) the home lines come from the real `Delivery.home` on a stand-in holding only the plan read
    it uses (a no-plan home and a proposed plan), never typed by hand. (2) T1's texts are not merged yet, so the
    glossary phrases (`[g] start|new attempt|check|continue`, `[u] install (tools)`, `[l] log in|refresh login`,
    `[r] revise|reconsider`) are the literal agreed forms; the one real T1-side string used is
    `delivery.CAUSE_TEXT["auth"]`, which this run owns. (3) The assertions name the command a hint becomes
    (`/run`, `/approve`, `/setup → install`, `/setup → log in`, `/view → revise`), not the sentence around it."""

    @staticmethod
    def home_lines(plan):
        from types import SimpleNamespace
        from terminal_planner.delivery import Delivery
        stand_in = SimpleNamespace(plan=lambda: plan, planner_panel=lambda: None)
        return Delivery.home(stand_in).lines

    def test_u2_the_home_plan_hints_delivery_writes_become_the_tui_step(self):
        from terminal_planner.tui import app as ui
        none = self.home_lines(None)
        hint = next(line for line in none if line.startswith("Next:"))
        self.assertIn(hint, ui.PLAN_TAB_HINTS)
        self.assertEqual(ui.plan_tab_line(hint), ui.PLAN_TAB_HINTS[hint])
        proposed = self.home_lines({"goal": "Add a README paragraph", "status": "proposed", "version": 1,
                                    "run_id": None})
        hint = next(line for line in proposed if line.startswith("Next:"))
        self.assertIn(hint, ui.PLAN_TAB_HINTS)
        shown = ui.plan_tab_line(hint)
        self.assertIn("/approve", shown)
        self.assertNotRegex(shown, r"\[[a-z]\]")

    def test_u2_the_glossary_letter_keys_become_the_tui_commands(self):
        from terminal_planner import delivery
        from terminal_planner.tui import app as ui
        for text, command in (("[u] install tools", "/setup → install"), ("[u] install", "/setup → install"),
                              ("[l] log in", "/setup → log in"), ("[l] refresh login", "/setup → log in"),
                              ("[r] revise", "/view → revise"), ("[r] reconsider", "/view → revise")):
            with self.subTest(text):
                self.assertEqual(ui.command_hints(text), command)
        # delivery's own cause text for a rejected login names the key with its label and a tail that stays
        self.assertIn("/setup → log in (`zplan login`)", ui.command_hints(delivery.CAUSE_TEXT["auth"]))
        for phrase in ("start M1", "new attempt M1 — from the current HEAD", "check M1", "continue M1"):
            with self.subTest(phrase):
                shown = ui.plan_tab_line("Next: [g] " + phrase)
                self.assertTrue(shown.startswith("Next: /run — "), shown)
                self.assertNotRegex(shown, r"\[[a-z]\]")
