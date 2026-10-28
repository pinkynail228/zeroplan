"""I3d: the owner-question card — «Нужно твоё решение · M1» with quick answers (0.5.2, docs/RELEASE_0.5.2_PLAN.md,
run i3d). A `needs_owner` milestone no longer pops the end-of-run `RunScreen` on the automatic watch; the card under
the chat is the decision, its buttons send `/approve simplify|split|skip` (and `/approve draft` for an answer draft),
`/decline` opens the answer note, and `[o]` still opens the `RunScreen`.

One smoke test per acceptance criterion (A1-A5) plus the invariants the card can break. The whole-app budget is two
methods: `QuestionCardTests` walks A1+A2 (120x40, resized to 80x24) and `QuestionDraftAndNoteTests` walks A3+A4 on
one shell (three `needs_owner` attempts in a row); A5, the source's per-key fetch, the card text and every route
refusal are unit level with stand-in screens (no pilot, no project).

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- The card's `at` border subtitle is the clock read once, when the attempt's end view is fetched (`card_clock`): the
  `EndView` carries no timestamp of its own, and caching the pair keeps the spec stable across renders (a recomputed
  time would remount the card on every render). The `HH:MM` of the sent receipt is, as everywhere else, the clock
  read when the owner acts.
- The card text is the end view's own body (`Question: …` and the task lines), each line stripped, at most
  `QUESTION_LINES` (6) *shown* lines — the body the plain end screen prints, so the card says what that screen says.
  The source *sizes* that body to what the card slot can show (`MainScreen.question_text_room`: the 40% `#cards` cap
  minus the card's own border/buttons/hint rows, and the slot's width minus the card's margin/border/padding),
  wrapping it to the slot's width and eliding the last row it cannot fit; the wrapped rows are then capped at
  `min(room rows, QUESTION_LINES)`, because the body's logical cap does not bound the wrapped output (one long
  `Question:` line plus three context lines wraps to eleven rows at a tall terminal) and the task makes the question
  text ≤6 lines. This is A1's "visible at 80x24": the frozen `cards.Card` clips whatever is taller than the slot, so
  a fixed `≤6`-line body pushed the buttons out at 80x24 and after a resize; the text re-measures on every render
  (a resize re-renders the source, so the spec — and the card — are rebuilt for the new size). The
  `(QUESTION_LINES, 0)` default (a unit call with no laid-out slot) keeps the plain body with no wrapping.
- The source fetches one end view per `needs_owner` row's own attempt of the current revision
  (`question:r<version>:<milestone>:<attempt>`) and never
  inside a render: the fetch is a `controller.open_run` job, its verdict is delivered back and cached, and the card
  appears on the next render. A key whose fetch did not build a `needs_owner` view is not fetched again (no loop), and
  a key whose attempt moved on drops its cache entry (the card is taken off because the source no longer returns it).
- The draft button appears by the *existence* of a `chat.newest_answer_draft(entries, milestone)` — an actionable
  answer draft of the card's milestone — not by resolving its token first; the send then re-checks the provenance on
  the worker (`controller.answer_draft`), and its `draft.stale` refusal is shown on the status line while the card
  stays open.
- The draft button keeps its required full «отправить черновик ответа» wording at every size. The full label (25
  cells) plus the three quick answers (26 cells) need more than the card's 50-cell inner width at the 120x40
  half-width chat pane, so the card wraps its own buttons to further rows (`ui.question_button_rows`, the widget's
  `_QuestionButtons` in `ui.QuestionCard`) instead of shortening a label or clipping the tail: the leading draft
  button and «упростить», «разбить», «пропустить» all stay in the card (A3), the first row keeps as many labels
  as fit, and the source gives each wrapped row back to the text (`question_text_room`'s chrome budgets one button
  row, so an extra row costs one text row and the card still fits the 40% `#cards` cap). A card the app has not
  laid out yet (`room` None / width 0) keeps every button in one row. The wrapping is the question kind's own
  widget (`QuestionCard`, chosen by `show_card` for a `question:` key): the shared `cards.Card` and its one-row
  `.buttons` are the other kinds' layout and stay exactly as merged, so only the question card re-flows them.
- A `/approve` argument that is neither a quick choice (`simplify`/`split`/`skip`) nor `draft` is refused with the
  shared `note.not_now` line (the same "no card action" line the other card refusals use); nothing is sent and the
  card stays. A bare `/approve` sends the answer draft when there is one and opens the note otherwise.
- The card-origin answer note submits on enter through `QuestionNoteScreen`, a `NoteScreen(..., answer=True,
  enter=True)` subclass whose enter is a *priority* binding: Textual delivers a key to the focused widget first and
  `TextArea` consumes `enter` (inserting a newline), so the frozen hook's own `on_key` is never reached while the
  field holds the focus. The plain answer forms (the `RunScreen`'s own answer) keep ctrl+g.
- An empty send keeps the card and says so (`EMPTY_ANSWER`), exactly as the `RunScreen`'s answer does.
"""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# imported first for its side effect: the offline wheelhouse joins `sys.path` before the guarded imports below.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_text

from terminal_planner.authority import Authority as RealAuthority
from terminal_planner.delivery import EndView, Token
from terminal_planner.runs import MilestoneRuns
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui import strings
from terminal_planner.tui.controller import Controller, Outcome, Row

try:
    from textual.widgets import Button
    from terminal_planner.tui import app as ui
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    ui = None

from test_tui_chat import ChatShell, chat_band
from test_tui_cards import CardApp
from test_terminal_planner import ROLES
from test_tui_draft_card import MISSING_REASON, _main_method, _Screen, receipt_pattern

HAVE = HAVE_TEXTUAL and ui is not None


def answer_receipt_pattern():
    """The closed card's receipt as a pattern: `card.answer_sent` with an `HH:MM` time, read from the catalog."""
    return re.escape(strings.text("card.answer_sent", time="00:00")).replace("00:00", r"\d\d:\d\d")


def end_view(state="needs_owner", body=("  Question: Что делать?",), milestone="M1", attempt=1, token=None):
    """A real `EndView` for the stand-in screens: only the fields the card reads are meaningful."""
    token = token or Token(milestone, 1, attempt, "run-%s" % attempt, "finished", state, "none")
    return EndView(state, token, milestone, milestone, "%s — итог" % milestone, "  Прогон: …", tuple(body), ())


def answer_chat(text="Ответ из черновика", milestone="M1", identity=("x",)):
    """A chat stand-in whose retained history (`chat.state.entries`, what the card reads) carries one actionable
    answer draft of `milestone`; `identity=None` makes the draft non-actionable, so no choice is offered."""
    draft = chat_module.Draft("answer", text, milestone, identity, identity is not None)
    entry = chat_module.ChatEntry(role="architect", text="Вот ответ.", drafts=(draft,))
    return SimpleNamespace(state=chat_module.ChatState(entries=(entry,)))


class _QuestionPad:
    """The app side the stand-in screen touches: the status note and `changed` wake-up (`_Pad`), plus the snapshot,
    the chat, the controller and the two app calls the card makes (`deliver`, `push_screen`, `watch_run`)."""

    def __init__(self, snapshot=None, chat=None, controller=None):
        self.chat_note, self.changes = "", 0
        self.snapshot, self.chat, self.controller = snapshot, chat, controller
        self.pushed, self.watched = [], []

    def changed(self):
        self.changes += 1

    def deliver(self, handler):
        return handler

    def push_screen(self, screen, callback=None):
        self.pushed.append((screen, callback))

    def watch_run(self, milestone):
        self.watched.append(milestone)

    def fresh_attempt(self, milestone, run_id, line=None):
        self.watched.append(milestone)


class _QuestionScreen(_Screen):
    """The `MainScreen` stand-in for i3d: the real card bookkeeping (`_Screen`) plus every method of the question
    kind, so the source, the routes and the verdicts run for real against doubled widgets and app."""

    question_cache = _main_method("question_cache")
    question_card_specs = _main_method("question_card_specs")
    question_text_room = _main_method("question_text_room")
    question_card_spec = _main_method("question_card_spec")
    question_fetched = _main_method("question_fetched")
    answer_draft_of = _main_method("answer_draft_of")
    question_end = _main_method("question_end")
    approve_question = _main_method("approve_question")
    decline_question = _main_method("decline_question")
    open_question_note = _main_method("open_question_note")
    answer_question = _main_method("answer_question")
    send_question_draft = _main_method("send_question_draft")
    question_answered = _main_method("question_answered")
    render_card_sources = _main_method("render_card_sources")
    run_command = _main_method("run_command")

    def __init__(self, rows=(), chat=None, frame=(27, 56)):
        """`frame` is the laid-out size the source sizes the card text to: `(height, width)` of the chat pane (and
        of the `#cards` slot it fills) at the 120x40 shell, so the real `question_text_room` runs against the
        geometry the live screen reports."""
        super().__init__()
        self.box.size = SimpleNamespace(width=frame[1], height=frame[0])
        self.pane_size = SimpleNamespace(width=frame[1], height=frame[0])
        self.app = _QuestionPad(snapshot=_Snapshot(rows), chat=chat, controller=self._controller())

    def query_one(self, selector, *args):
        if selector == "#chat-pane":
            return SimpleNamespace(size=self.pane_size)
        return super().query_one(selector, *args)

    def _controller(self):
        return _Fetch()

    def seed(self, key, end):
        """Put `key` in the card slot as an open question card holding `end`, as the source would once fetched."""
        self.question_cache()["ends"][key] = (end, "12:00")
        self.show_card(self.question_card_spec(key, _row(end.milestone, end.token.attempt), end, "12:00"))


class _Snapshot:
    def __init__(self, rows, version=1):
        self.rows = tuple(rows)
        # the plan revision the card keys carry (0.5.2 corrective): a test moves it to a later revision
        self.version = version


def _row(milestone="M1", attempt=1):
    return Row(id=milestone, title=milestone, state="needs_owner",
               text="нужен ответ", token=Token(milestone, 1, attempt, "run-%s" % attempt, "finished",
                                               "needs_owner", "none"))


class _Fetch:
    """A stand-in controller whose `open_run` records the milestone and parks the callback the source handed it, so a
    test decides when the end view arrives (the real fetch runs on the controller worker)."""

    def __init__(self):
        self.opened, self.done = [], []

    def open_run(self, milestone, done):
        self.opened.append(milestone)
        self.done.append(done)
        return True

    def deliver_end(self, end, error=None, index=0):
        self.done[index](Outcome("end", data=end), error)


class _Routes:
    """A stand-in controller for the card's own commands: it records every answer and draft and answers with the
    outcome the test set."""

    def __init__(self, answer=None, draft=None, error=None):
        self.answer_outcome, self.draft_outcome, self.error = answer, draft, error
        self.answers, self.drafts = [], []

    def answer(self, token, text, done):
        self.answers.append((token.milestone, text))
        done(self.answer_outcome, self.error)
        return True

    def answer_draft(self, identity, milestone, text, done):
        self.drafts.append((identity, milestone, text))
        done(self.draft_outcome, self.error)
        return True

    def open_run(self, milestone, done):
        return True


@unittest.skipIf(ui is None, MISSING_REASON)
class QuestionCardSourceTests(unittest.TestCase):
    """The source, the key and the card text at unit level: one card per `needs_owner` row, fetched once per key,
    off the render, and never brought back for a key that left."""

    def setUp(self):
        # Only this run's source: the other registered sources (e.g. i3b's `plan`) read app state the double does
        # not carry.
        sources = patch.dict(ui.CARD_SOURCES, {"question": ui.CARD_SOURCES["question"]}, clear=True)
        sources.start()
        self.addCleanup(sources.stop)

    def screen(self, rows=()):
        return _QuestionScreen(rows)

    def test_a1_one_card_per_needs_owner_row_fetched_once_and_titled_with_the_milestone(self):
        """A1 (unit half): the source starts exactly one `open_run` fetch for the single `needs_owner` row — a
        `ready` row gets no card and no fetch — the card appears only after the end view arrives, its key is the
        row's own attempt, its title names the milestone, and a second render neither re-fetches nor remounts it."""
        screen = self.screen(rows=[_row("M1", 1), Row(id="M2", title="M2", state="ready", text="готов",
                                                     token=Token("M2", 1, 1, "r2", "finished", None, "none"))])
        self.assertEqual(screen.question_card_specs(), [])
        self.assertEqual(screen.app.controller.opened, ["M1"])  # one fetch, for the needs_owner row only
        screen.question_card_specs()  # still nothing: the end view has not arrived...
        self.assertEqual(screen.app.controller.opened, ["M1"])  # ...and it is not fetched twice
        screen.app.controller.deliver_end(end_view())
        specs = screen.question_card_specs()
        self.assertEqual([spec.key for spec in specs], ["question:r1:M1:1"])
        self.assertEqual(specs[0].title, strings.text("card.question_title", task="M1"))
        self.assertIn("Что делать?", specs[0].text)
        screen.render_card_sources()
        widget = screen.card_widgets["question:r1:M1:1"]
        screen.render_card_sources()
        self.assertIs(screen.card_widgets["question:r1:M1:1"], widget)  # an unchanged spec is not remounted

    def test_a3_a_new_revision_shows_its_own_question_card_and_fetches_it_again(self):
        """A3 (regression, i3c corrective — the milestone card keys lacked the plan revision): the revision is part
        of `question_card_key`, so a question card closed under r1 does not suppress the same stage's card under
        r2 — an open `question:r2:M1:1` shows — and the r2 key reads its own end view (a second `open_run` fetch),
        never r1's cached one.

        Verified on the old layout (A5): reverting the key line to `question:%s:%s` collapses both revisions onto
        `question:M1:1`, so the closed r1 card (its key already in `cards_seen`) suppresses r2 and no second fetch
        is made — this test then fails with no open card and one fetch only."""
        screen = self.screen(rows=[_row()])
        screen.render_card_sources()  # the r1 fetch is queued
        screen.app.controller.deliver_end(end_view(body=("  Question: r1?",)))
        screen.render_card_sources()  # the r1 card mounts
        self.assertEqual(list(screen.card_specs), ["question:r1:M1:1"])
        # the owner answers r1: the card becomes its receipt; the approved r2 brings the stage back to needs_owner
        screen.close_card("question:r1:M1:1", "✓ ответ отправлен 12:00")
        screen.app.snapshot.version = 2
        screen.render_card_sources()  # nothing cached for the r2 key: one more fetch
        self.assertEqual(screen.app.controller.opened, ["M1", "M1"])
        self.assertEqual([k for k, spec in screen.card_specs.items() if spec.done is None], [])
        screen.app.controller.deliver_end(end_view(body=("  Question: r2?",)), index=1)
        screen.render_card_sources()
        open_keys = [k for k, spec in screen.card_specs.items() if spec.done is None]
        self.assertEqual(open_keys, ["question:r2:M1:1"])  # the r2 card is open, r1's receipt is not brought back
        self.assertIn("r2?", screen.card_specs["question:r2:M1:1"].text)

    def test_the_question_text_is_the_end_body_stripped_and_capped_at_six_lines(self):
        """The card text is the end view's own body: each line stripped, at most `ui.QUESTION_LINES` lines."""
        body = tuple("  строка %d" % index for index in range(9))
        spec = _QuestionScreen().question_card_spec("question:r1:M1:1", _row(), end_view(body=body), "12:00")
        lines = spec.text.splitlines()
        self.assertEqual(len(lines), ui.QUESTION_LINES)
        self.assertEqual(lines[0], "строка 0")
        self.assertNotIn("  ", spec.text)

    def test_a_fetch_that_does_not_build_a_question_card_is_not_retried(self):
        """An end view that is not a `needs_owner` state (an attempt that moved on under the row) yields no card and
        is not fetched again: the key is marked, so the source never loops on it."""
        screen = self.screen(rows=[_row()])
        screen.question_card_specs()
        screen.app.controller.deliver_end(end_view(state="blocked"))
        self.assertEqual(screen.question_card_specs(), [])
        self.assertEqual(screen.question_card_specs(), [])
        self.assertEqual(screen.app.controller.opened, ["M1"])

    def test_the_buttons_are_the_three_choices_and_the_draft_button_leads_only_with_a_draft(self):
        """A1/A3 (unit half): without an answer draft the buttons are «упростить», «разбить», «пропустить» with their
        `/approve` lines; an actionable answer draft of the milestone adds «отправить черновик ответа» first (the new
        `card.answer_draft`), and a draft of another milestone or a non-actionable one adds nothing."""
        plain = _QuestionScreen().question_card_spec("question:r1:M1:1", _row(), end_view(), "12:00")
        self.assertEqual([c for _, c in plain.buttons],
                         ["/approve simplify", "/approve split", "/approve skip"])
        self.assertEqual([l for l, _ in plain.buttons],
                         [strings.text("card.question_simplify"), strings.text("card.question_split"),
                          strings.text("card.question_skip")])
        with_draft = _QuestionScreen(chat=answer_chat()).question_card_spec("question:r1:M1:1", _row(), end_view(),
                                                                            "12:00")
        self.assertEqual(with_draft.buttons[0], (strings.text("card.answer_draft"), "/approve draft"))
        other = answer_chat(milestone="M2")
        without = _QuestionScreen(chat=other).question_card_spec("question:r1:M1:1", _row(), end_view(), "12:00")
        self.assertEqual([c for _, c in without.buttons], ["/approve simplify", "/approve split", "/approve skip"])
        stale = _QuestionScreen(chat=answer_chat(identity=None)).question_card_spec("question:r1:M1:1", _row(),
                                                                                    end_view(), "12:00")
        self.assertEqual([c for _, c in stale.buttons], ["/approve simplify", "/approve split", "/approve skip"])


@unittest.skipIf(ui is None, MISSING_REASON)
class QuestionCardSizingTests(unittest.TestCase):
    """A1/A3 (unit half) of the card's own room: the text is wrapped to the slot's width, elided to the rows it can
    show and capped at `QUESTION_LINES` (the `#cards` slot clips what is taller than 40% of the chat pane), and the
    draft button keeps its required full «отправить черновик ответа» label, the card wrapping its buttons onto a
    second row where the 120x40 half-width card cannot hold all four in one. The stand-in reports the laid-out size
    of the chat pane; a not-laid-out slot falls back to the plain cap."""

    def test_the_text_is_wrapped_to_the_slot_and_elided_at_the_rows_it_can_show(self):
        """The card text is wrapped to the slot's width and kept to the rows the slot has, eliding the last one, so
        the card's buttons below it stay on screen (A1). The `(QUESTION_LINES, 0)` default keeps the plain body."""
        body = ("  Question: " + "слово " * 11 + "слово",)  # one long logical line, several wrapped rows
        text = ui.question_body(end_view(body=body), rows=2, width=20)
        rows = text.splitlines()
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[-1].endswith(ui.ELLIPSIS))
        self.assertTrue(all(ui.display_width(row) <= 20 for row in rows))
        plain = ui.question_body(end_view(body=body))
        self.assertEqual(plain, "Question: " + "слово " * 11 + "слово")  # no wrapping in the plain (unit) case
        short = ui.question_body(end_view(body=body), rows=1, width=20)
        self.assertEqual(len(short.splitlines()), 1)
        self.assertTrue(short.endswith(ui.ELLIPSIS))

    def test_the_room_is_the_slot_cap_minus_the_card_chrome(self):
        """`question_text_room` reads the laid-out geometry: the 40% `#cards` cap minus the card's own non-text
        rows, and the slot's width minus the card's margin/border/padding. A not-laid-out slot (all zeros) falls
        back to the plain `QUESTION_LINES` cap with no wrapping."""
        self.assertEqual(_QuestionScreen(frame=(27, 56)).question_text_room(), (5, 50))
        self.assertEqual(_QuestionScreen(frame=(16, 76)).question_text_room(), (1, 70))
        self.assertEqual(_QuestionScreen(frame=(0, 0)).question_text_room(), (ui.QUESTION_LINES, 0))

    def test_a3_the_draft_button_keeps_its_full_label_and_the_card_wraps_the_buttons(self):
        """A3: the draft button's label is the required full «отправить черновик ответа» at every size — never the
        short «черновик». At the 120x40 half-width card (room width 50) the four labels cannot share one row, so
        `ui.question_button_rows` groups them onto two rows that each fit the width, the draft button leads and the three
        quick answers stay in the card; a not-laid-out card (room width 0) keeps every button in one row."""
        screen = _QuestionScreen(chat=answer_chat())
        spec = screen.question_card_spec("question:r1:M1:1", _row(), end_view(), "12:00", room=(5, 50))
        self.assertEqual(spec.buttons[0], (strings.text("card.answer_draft"), "/approve draft"))
        self.assertEqual([code for _, code in spec.buttons[1:]],
                         ["/approve simplify", "/approve split", "/approve skip"])
        rows = ui.question_button_rows(spec.buttons, 50)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertLessEqual(sum(ui.question_button_cells(label) for label, _ in row), 50)
        self.assertEqual([button for row in rows for button in row], list(spec.buttons))
        plain = _QuestionScreen(chat=answer_chat()).question_card_spec("question:r1:M1:1", _row(), end_view(), "12:00")
        self.assertEqual(len(ui.question_button_rows(plain.buttons, 0)), 1)

    def test_the_question_text_never_shows_more_than_six_lines(self):
        """A3 (the ≤6-line requirement): the end body's logical-line cap does not bound the *wrapped* output — one
        long `Question:` line plus three context lines wraps to eleven rows in the tall terminal's room (13, 50) — so
        the shown rows are capped at `min(room rows, QUESTION_LINES)` and the last kept row carries the truncation
        ellipsis, each row staying within the slot's width."""
        body = ("Question: " + "что делать " * 30,) + ("контекст 1", "контекст 2", "контекст 3")
        screen = _QuestionScreen(frame=(47, 56))
        self.assertEqual(screen.question_text_room(), (13, 50))
        spec = screen.question_card_spec("question:r1:M1:1", _row(), end_view(body=body), "12:00",
                                         room=screen.question_text_room())
        lines = spec.text.splitlines()
        self.assertEqual(len(lines), ui.QUESTION_LINES)
        self.assertTrue(lines[-1].endswith(ui.ELLIPSIS))
        self.assertTrue(all(ui.display_width(line) <= 50 for line in lines))


@unittest.skipIf(ui is None, MISSING_REASON)
class QuestionCardWidgetTests(unittest.IsolatedAsyncioTestCase):
    """The acceptance repair: the button wrapping belongs to the question kind alone. The shared `cards.Card` keeps
    its single button row (every other kind's layout is unchanged), while `QuestionCard` re-flows its *own* buttons
    onto further rows, so the full «отправить черновик ответа» and the three quick answers all stay on the card at
    the 120x40 half-width (inner 50 cells) where one shared row could not hold them."""

    async def test_only_the_question_card_wraps_the_buttons_the_shared_card_keeps_one_row(self):
        """One mini app per widget at 56 columns (card inner 50): the shared `Card` puts all four buttons in one row
        and clips the tail, `ui.QuestionCard` groups them onto two rows with every label on screen. The shared
        layout is the other kinds' and stays one row."""
        buttons = [(strings.text("card.answer_draft"), "/approve draft"),
                   (strings.text("card.question_simplify"), "/approve simplify"),
                   (strings.text("card.question_split"), "/approve split"),
                   (strings.text("card.question_skip"), "/approve skip")]
        spec = ui.cards.question_card("question:r1:M1:1", "12:00", "M1", "Question: что делать?", buttons)
        for widget, rows in ((ui.cards.Card(spec), 1), (ui.QuestionCard(spec), 2)):
            with self.subTest(widget=type(widget).__name__):
                app = CardApp(widget)
                async with app.run_test(size=(56, 24)) as pilot:
                    await pilot.pause(0.5)
                    shown = screen_text(app)
                    self.assertEqual(len({button.region.y for button in widget.query(Button)}), rows)
                    self.assertEqual(all(label in shown for label, _ in buttons), rows == 2)


@unittest.skipIf(ui is None, MISSING_REASON)
class QuestionCardRouteTests(unittest.TestCase):
    """A5 and the `/approve`/`/decline` rows at unit level: the choice answers the attempt, the draft button sends
    through `answer_draft`, a bare `/approve` picks the draft or the note, and every refusal keeps the card."""

    def screen(self, chat=None, key="question:r1:M1:1", end=None):
        screen = _QuestionScreen(chat=chat)
        end = end or end_view()
        screen.seed(key, end)
        return screen

    def test_a5_a_typed_approve_with_an_unknown_argument_is_refused_and_sends_nothing(self):
        """A5: `/approve maybe` reaches the card's route and is refused on the status line with the shared
        `note.not_now`; no answer and no draft is sent and the card stays open."""
        screen = self.screen(chat=answer_chat())
        routes = _Routes()
        screen.app.controller = routes
        self.assertTrue(screen.run_command("/approve", "maybe", None))
        self.assertEqual(screen.app.chat_note, strings.text("note.not_now", name="/approve"))
        self.assertEqual((routes.answers, routes.drafts), ([], []))
        self.assertIsNone(screen.card_specs["question:r1:M1:1"].done)  # the card is still a decision

    def test_a_choice_answers_the_attempt_with_its_own_catalog_text(self):
        """A2 (unit half): each quick answer answers the attempt the card stands for with its own catalog text and
        watches the new attempt; on a started attempt the card closes with the sent receipt."""
        for choice, string_id in (("simplify", "card.question_simplify"), ("split", "card.question_split"),
                                  ("skip", "card.question_skip")):
            with self.subTest(choice=choice):
                screen = self.screen()
                routes = _Routes(answer=Outcome("attempt", data=None))
                screen.app.controller = routes
                self.assertTrue(screen.run_command("/approve", choice, "question:r1:M1:1"))
                self.assertEqual(routes.answers, [("M1", strings.text(string_id))])
                self.assertEqual(screen.app.watched, ["M1"])
                done = screen.card_specs["question:r1:M1:1"].done
                self.assertRegex(done, "^%s$" % answer_receipt_pattern())

    def test_the_draft_button_and_a_bare_approve_send_the_answer_draft(self):
        """A3 (unit half): «отправить черновик ответа» (and a bare `/approve`, when a draft exists) sends the newest
        actionable answer draft of the milestone through `controller.answer_draft` with the draft's own identity,
        milestone and text, and closes the card once the attempt started."""
        screen = self.screen(chat=answer_chat())
        routes = _Routes(draft=Outcome("attempt", data=None))
        screen.app.controller = routes
        self.assertTrue(screen.run_command("/approve", "draft", "question:r1:M1:1"))
        self.assertEqual(routes.drafts, [(("x",), "M1", "Ответ из черновика")])
        self.assertIsNotNone(screen.card_specs["question:r1:M1:1"].done)
        bare = self.screen(chat=answer_chat())
        bare_routes = _Routes(draft=Outcome("attempt", data=None))
        bare.app.controller = bare_routes
        self.assertTrue(bare.run_command("/approve", "", None))
        self.assertEqual(bare_routes.drafts, [(("x",), "M1", "Ответ из черновика")])

    def test_a_stale_draft_refusal_is_shown_and_the_card_stays(self):
        """A3: the `draft.stale` refusal of `answer_draft` is put on the status line and the card stays open."""
        screen = self.screen(chat=answer_chat())
        routes = _Routes(error="draft is outdated: another attempt started")
        screen.app.controller = routes
        screen.run_command("/approve", "draft", "question:r1:M1:1")
        self.assertEqual(routes.drafts, [(("x",), "M1", "Ответ из черновика")])
        self.assertIn(chat_module.OUTDATED, screen.app.chat_note)
        self.assertIsNone(screen.card_specs["question:r1:M1:1"].done)
        self.assertEqual(screen.app.watched, [])

    def test_a_bare_approve_without_a_draft_opens_the_answer_note(self):
        """The no-argument `/approve` without an answer draft opens the card's answer note and sends nothing yet."""
        screen = self.screen()
        routes = _Routes()
        screen.app.controller = routes
        self.assertTrue(screen.run_command("/approve", "", None))
        self.assertEqual((routes.answers, routes.drafts), ([], []))
        self.assertEqual(len(screen.app.pushed), 1)
        note, _ = screen.app.pushed[0]
        self.assertEqual(type(note).__name__, "QuestionNoteScreen")
        self.assertTrue(note.enter)
        self.assertIsNone(screen.card_specs["question:r1:M1:1"].done)

    def test_decline_opens_the_answer_note_and_its_text_answers_the_card(self):
        """A4 (unit half): `/decline` opens the card's answer note; a sent text goes through `controller.answer` with
        exactly that text (and closes the card), esc (None) and an empty send keep it."""
        screen = self.screen()
        routes = _Routes(answer=Outcome("attempt", data=None))
        screen.app.controller = routes
        self.assertTrue(screen.run_command("/decline", "", None))
        note, sent = screen.app.pushed[0]
        self.assertEqual(type(note).__name__, "QuestionNoteScreen")
        sent(None)  # esc: nothing sent, the card stays
        self.assertEqual(routes.answers, [])
        self.assertIsNone(screen.card_specs["question:r1:M1:1"].done)
        sent("")  # an empty send: the card stays and the status line says so
        self.assertEqual(routes.answers, [])
        self.assertEqual(screen.app.chat_note, ui.EMPTY_ANSWER)
        sent("сделай без теста")  # the owner's own words
        self.assertEqual(routes.answers, [("M1", "сделай без теста")])
        self.assertRegex(screen.card_specs["question:r1:M1:1"].done, "^%s$" % answer_receipt_pattern())

    def test_an_answer_that_does_not_start_keeps_the_card(self):
        """The other half of the answer path: a refusal (an error, a stale token, a readiness block) sends nothing
        new, keeps the card an open decision and says why on the status line."""
        cases = (("error", _Routes(error="the planner is unavailable"), None, "the planner is unavailable"),
                 ("stale", _Routes(answer=Outcome("stale", lines=("the attempt has moved on",))), None, ui.MOVED),
                 ("blocked", _Routes(answer=Outcome("blocked", checks=())), None, ui.NOT_STARTED_BELOW))
        for name, routes, _, expected in cases:
            with self.subTest(verdict=name):
                screen = self.screen()
                screen.app.controller = routes
                screen.run_command("/approve", "simplify", "question:r1:M1:1")
                self.assertIn(expected, screen.app.chat_note)
                self.assertIsNone(screen.card_specs["question:r1:M1:1"].done)  # the card stays a decision
                self.assertEqual(screen.app.watched, [])

    def test_a_command_on_a_card_that_is_not_open_is_refused(self):
        """A closed or forgotten key has no route: `/approve` and `/decline` are refused with `note.not_now` and
        send nothing (a closed card is not a decision any more)."""
        screen = self.screen()
        routes = _Routes()
        screen.app.controller = routes
        screen.close_card("question:r1:M1:1", "✓ ответ отправлен 12:00")
        for command, argument in (("/approve", "simplify"), ("/decline", "")):
            with self.subTest(command=command):
                screen.app.chat_note = ""
                screen.run_command(command, argument, "question:r1:M1:1")
                self.assertEqual(screen.app.chat_note, strings.text("note.not_now", name=command))
        self.assertEqual((routes.answers, routes.drafts), ([], []))


@unittest.skipUnless(HAVE, MISSING_REASON)
class QuestionCardShell(ChatShell):
    """The chat shell over an approved fixture plan whose M1 is driven to a `needs_owner` end."""

    def runs(self, authority):
        return MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")

    def seed_needs_owner(self, milestone="M1"):
        """An approved fixture plan and one finished `needs_owner` attempt of `milestone`; returns its `Token`."""
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            if not (authority.state and authority.state.get("revisions")):
                self.begin(authority)
                self.propose(authority)
                authority.approve(1)
            runs = self.runs(authority)
            record = runs.start(milestone, 1, ROLES)
            runs.observe(record)
            return Token.of(record)

    def seed_answer_draft(self, token, text, milestone="M1", status="completed"):
        """One architect reply carrying an actionable answer draft of `milestone` with `token`'s identity."""
        store = self.fixture.store()
        store.append("owner", text="вопрос")
        store.append("architect", text="Вот ответ.", status=status,
                     drafts=[{"kind": "answer", "text": text, "milestone": milestone,
                              "identity": ui.token_fields(token)}])
        return store

    @staticmethod
    def counting_answer(calls):
        """A `Controller.answer` spy: records `(milestone, text)` and still runs the real answer."""
        real = Controller.answer

        def spy(controller, token, text, done):
            calls.append((token.milestone, text))
            return real(controller, token, text, done)
        return spy

    @staticmethod
    def counting_draft(calls):
        """A `Controller.answer_draft` spy: records `(identity, milestone, text)` and still runs the real send."""
        real = Controller.answer_draft

        def spy(controller, identity, milestone, text, done):
            calls.append((identity, milestone, text))
            return real(controller, identity, milestone, text, done)
        return spy

    def main(self):
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def cards(self):
        return list(self.main().card_widgets.values())

    def open_card(self):
        return next((card for card in self.cards() if card.spec.done is None), None)

    def card(self, key):
        return next((card for card in self.cards() if card.spec.key == key), None)

    async def card_shown(self, pilot, timeout=8.0):
        await self.until(pilot, lambda: self.open_card() is not None, timeout)
        await pilot.pause(0.3)
        return self.open_card()

    async def chose(self, pilot, command):
        """Press the open card's button carrying the slash command `command`."""
        button = next(widget for widget in self.open_card().query(Button) if widget.command == command)
        await pilot.click(button)
        await pilot.pause(0.3)

    async def send(self, pilot, line):
        """Put `line` in the chat input and press Enter."""
        field = self.query("#input")
        field.focus()
        field.value = line
        await pilot.press("enter")
        await pilot.pause(0.3)

    async def closed_card(self, pilot, key, timeout=8.0):
        await self.until(pilot, lambda: self.card(key) is not None and self.card(key).spec.done is not None, timeout)
        return self.card(key)


@unittest.skipUnless(HAVE, MISSING_REASON)
class QuestionCardTests(QuestionCardShell):
    async def test_a1_a2_the_question_card_shows_and_a_choice_answers_it(self):
        """A1: a `needs_owner` end pops no `RunScreen` — the card appears under the chat, titled «Нужно твоё
        решение · M1», showing the question and the three quick-answer buttons, and every button stays visible at
        80x24 as well: the card text is sized to the `#cards` slot (the source re-measures it on the resize), so
        even the *normal* four-line question body cannot push the buttons out of the slot. A2: «упростить» answers
        the attempt once with the choice's own text, watches the new attempt, and the card turns into the «✓ ответ
        отправлен HH:MM» receipt. The 80x24 check is a resize of the same shell (the card lives in the layout; a
        second shell would start another attempt)."""
        self.driver.outcomes = ("needs_owner", "needs_owner")
        self.approve(running=False)
        answers = []
        with patch.object(Controller, "answer", self.counting_answer(answers)):
            async with self.shell(size=(120, 40)) as pilot:
                await self.loaded(pilot)
                await self.begin_run(pilot)  # [g] + [y]: starts M1 and watches it to its end
                card = await self.card_shown(pilot)
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")  # A1: no RunScreen popped
                title = strings.text("card.question_title", task="M1")
                self.assertEqual(card.spec.title, title)
                # i9-look: the card lives in the 38%-wide chat pane, so its own text wraps the question body;
                # the flattened text is compared (the product text is right, only the reading was wrong).
                self.assertIn("Fixture: approve the scope change?", " ".join(card.spec.text.split()))
                labels = [label for label, _ in card.spec.buttons]
                self.assertEqual(labels, [strings.text("card.question_simplify"),
                                          strings.text("card.question_split"),
                                          strings.text("card.question_skip")])
                for size in ((120, 40), (80, 24)):
                    with self.subTest(size=size):
                        await pilot.resize_terminal(*size)
                        await pilot.pause(0.3)
                        # i9-look: the chat pane is 38% wide, so a card line wraps inside it and `screen_text`
                        # interleaves the plan pane's cells; the band reads the chat pane's own rows.
                        shown = chat_band(self.app)
                        self.assertIn(title, shown)
                        self.assertIn("Fixture: approve the scope change?", shown)  # the question, not just its card
                        for label in labels:
                            self.assertIn(label, shown)
                await pilot.resize_terminal(120, 40)
                await pilot.pause(0.3)
                key = card.spec.key
                await self.chose(pilot, "/approve simplify")
                closed = await self.closed_card(pilot, key)
                self.assertEqual(answers, [("M1", strings.text("card.question_simplify"))])
                self.assertRegex(closed.spec.done, "^%s$" % answer_receipt_pattern())
        runs = self.stored()["runs"]
        self.assertEqual((runs[1]["context"]["kind"], runs[1]["context"]["text"]),
                         ("answer", strings.text("card.question_simplify")))


@unittest.skipUnless(HAVE, MISSING_REASON)
class QuestionDraftAndNoteTests(QuestionCardShell):
    async def test_a3_a4_the_draft_button_the_note_and_the_stale_refusal(self):
        """A3: with an actionable answer draft for M1 the card's first button is the draft button, it sends through
        `controller.answer_draft` (the draft's own text lands as the attempt's answer), and once the draft's attempt
        has moved on the same button's `draft.stale` refusal shows on the status line while the card stays open. A4:
        `/decline` opens the card's answer note, esc keeps the card, and enter with «сделай без теста» sends exactly
        that text.

        The draft button's wording is the required full «отправить черновик ответа» at both sizes: at the 120x40
        half-width chat pane the card wraps its buttons onto two rows (`ui.question_button_rows`) so the full label and
        the three quick answers all stay in the card, and at the 80x24 whole-width pane they share one row. The
        draft button leads and all four labels stay visible together either way.

        The three `needs_owner` outcomes drive one attempt per answer, so the same shell walks every clause: card 1
        (attempt 1) carries the fresh draft, the two refusals/notes are checked on it, then cards 2 and 3 carry the
        attempt the previous answer started."""
        self.driver.outcomes = ("needs_owner", "needs_owner", "needs_owner")
        token = self.seed_needs_owner()
        self.seed_answer_draft(token, "Ответ из черновика")
        drafts, answers = [], []
        with patch.object(Controller, "answer_draft", self.counting_draft(drafts)), \
                patch.object(Controller, "answer", self.counting_answer(answers)):
            async with self.shell(size=(120, 40)) as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                first = await self.card_shown(pilot)
                # A3: the draft button leads with its required full label, the three choices follow, and the four
                # stay visible together — at 120x40 the card wraps them onto two rows
                self.assertEqual(first.spec.buttons[0], (strings.text("card.answer_draft"), "/approve draft"))
                self.assertEqual([c for _, c in first.spec.buttons[1:]],
                                 ["/approve simplify", "/approve split", "/approve skip"])
                for label in [text for text, _ in first.spec.buttons]:
                    self.assertIn(label, screen_text(self.app))
                key1 = first.spec.key
                await pilot.resize_terminal(80, 24)
                await pilot.pause(0.3)
                small = self.open_card()
                self.assertEqual(small.spec.buttons[0], (strings.text("card.answer_draft"), "/approve draft"))
                small_shown = screen_text(self.app)
                for label in [text for text, _ in small.spec.buttons]:
                    self.assertIn(label, small_shown)
                await pilot.resize_terminal(120, 40)
                await pilot.pause(0.3)
                self.assertEqual(self.open_card().spec.buttons[0],
                                 (strings.text("card.answer_draft"), "/approve draft"))
                # A4: /decline opens the note; esc keeps the card
                await self.send(pilot, "/decline")
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "QuestionNoteScreen")
                await pilot.press("escape")
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
                self.assertIsNotNone(self.card(key1))
                self.assertIsNone(self.card(key1).spec.done)
                self.assertEqual(answers, [])  # esc sent nothing
                # A3: the draft button sends through answer_draft and closes the card
                await self.chose(pilot, "/approve draft")
                closed1 = await self.closed_card(pilot, key1)
                self.assertEqual(drafts, [(ui.token_fields(token), "M1", "Ответ из черновика")])
                self.assertRegex(closed1.spec.done, "^%s$" % answer_receipt_pattern())
                second = await self.card_shown(pilot)
                self.assertNotEqual(second.spec.key, key1)
                key2 = second.spec.key
                # A4: the note's enter sends exactly the owner's words
                await self.send(pilot, "/decline")
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "QuestionNoteScreen")
                await self.type(pilot, "сделай без теста")
                await pilot.press("enter")
                closed2 = await self.closed_card(pilot, key2)
                self.assertEqual(answers, [("M1", "сделай без теста")])
                self.assertRegex(closed2.spec.done, "^%s$" % answer_receipt_pattern())
                # A3: the draft is stale now (its attempt moved on): the button refuses on the status line
                third = await self.card_shown(pilot)
                self.assertEqual(third.spec.buttons[0], (strings.text("card.answer_draft"), "/approve draft"))
                await self.chose(pilot, "/approve draft")
                await self.until(pilot, lambda: chat_module.OUTDATED in screen_text(self.app))
                self.assertEqual(len(drafts), 2)  # the button reached answer_draft again; the second was refused
                self.assertIsNone(self.card(third.spec.key).spec.done)  # the card stayed an open decision
        runs = self.stored()["runs"]
        self.assertEqual([r["context"]["text"] for r in runs[1:]],
                         ["Ответ из черновика", "сделай без теста"])


if __name__ == "__main__":
    unittest.main()
