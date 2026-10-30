"""I3b: the plan-approval card on the main screen (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md run i3b).

While a plan is *proposed* the chat card slot holds one card, «План · N этапов · M задач», whose two buttons decide
the plan in one click: `/approve` goes straight to `ZplanApp.decide("approve", version)` (no PlanScreen, no
confirmation modal) and turns the card into the `card.plan_done` receipt; `/decline` opens the plan screen's
revision note with enter submitting. The counts are read verbatim from the plan summary line
(`PlanView.lines[1]`, e.g. "План r1 · 1 этап · 3 задачи · проверен"), the one place they exist. PlanScreen and its
keys stay: the card is an addition, not a replacement.

One acceptance criterion per test, and at most two whole-app methods (the shell tests below): A1+A2 drive the real
shell once at 120x40, A1 (narrow) + A4 drive it once more at 80x24; the source's own reading of the summary line,
A2's typed path, A3 (the note) and A5 (the refusal) are unit level on stand-in screens, where the real `show_card`/
`close_card`/`render_card_sources`/`revision_note` run and no pilot, project or engine is needed.

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- The counts come from `snapshot.plan.lines[1]` split on " · ": the fields between "План rN" and the verdict. A
  *proposed* plan whose view carries no summary line (its view could not be built, so `snapshot.plan` is None while
  the status is still `proposed`) yields the same card without counts — its title falls back to `strings.text(
  "pane.plan")` («План»), the plan word the pane itself carries. That keeps the card a real decision exactly where
  the task says a card without counts must still be shown, without a new catalog id (the run's write-set holds no
  `strings.py`; the parallel card rule adds new `card.*` ids, and none is needed here).
- The card's `at` is the wall clock the source is read at (`card_clock()`): the plan summary line carries no time
  of its own (unlike the goal-draft card, whose `at` is the reply's `HH:MM`). The receipt's time stays the clock
  read when the owner acts, as `card.plan_done` wants.
- A5 is checked through the decision's *real* contract: `ZplanApp.decide` only queues the approval on the worker and
  its verdict comes back later through the callback it hands the controller (`done(outcome, error)`), never as a
  synchronous return — so a refusal is the callback's `error` (`refusal(Blocked)`'s text, «план устарел…»), not a
  raised exception the button could catch. The route closes the card on that callback's success only and, on its
  error, keeps the open card and adds no line (A10c): `decide` itself says the reason on the main screen
  (`say_note`), so a line from the card would show it twice.
- A4's "through PlanScreen" is the acceptance shell test: the card leaves on the next render because the source
  stops returning it once the status leaves `proposed` — no card-side code runs for the PlanScreen path at all.
"""

from dataclasses import replace
import re
import unittest
from unittest.mock import patch

# imported first for its side effect: the offline wheelhouse (ZPLAN_TEST_WHEELHOUSE) joins `sys.path` before the
# guarded imports below, so this module sees Textual and Rich there on a host that installs neither.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_text

from terminal_planner.authority import Authority, Blocked, canonical
from terminal_planner.cli import refusal
from terminal_planner.engine import FixtureEngine
from terminal_planner.planning import PlanView
from terminal_planner.tui import strings
from test_terminal_planner import ROLES
from test_tui_planning import GOAL, PlanningShell

MISSING_REASON = "Rich и Textual недоступны: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"
# The app, the card widget and `Snapshot` need Rich (through Textual), so they alone are imported under the same
# guard the other TUI modules use: the module still loads (with every test class declared and skipped) where neither
# is importable, which `tests.test_toolchain` scans for.
try:
    from textual.widgets import Button
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import cards
    from terminal_planner.tui.controller import Snapshot
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    Button = ui = cards = Snapshot = None

HAVE = HAVE_TEXTUAL and ui is not None and cards is not None

SUMMARY = "План r1 · 1 этап · 3 задачи · проверен"
# The joint example's plan: one stage (milestone) holding three tasks — the fixture engine's own plan has two
# milestones of two tasks, which would name other counts.
JOINT_PLAN = {
    "requirements": [{"id": "R1", "text": "The owner approves the plan in one click."},
                     {"id": "R2", "text": "A revision starts from the card without a modal."}],
    "milestones": [{"id": "M1", "title": "Plan approval", "depends_on": [], "slices": [
        {"id": "S1", "title": "The card", "requirements": ["R1"], "tasks": [
            {"id": "T1", "title": "Read the counts", "checks": ["A deterministic card test"]},
            {"id": "T2", "title": "Approve in one click", "checks": ["A deterministic click test"]}]},
        {"id": "S2", "title": "The revision note", "requirements": ["R2"], "tasks": [
            {"id": "T3", "title": "Open the note", "checks": ["A deterministic note test"]}]}]}],
}


def receipt_pattern():
    """The closed card's receipt as a pattern: `card.plan_done` with a `HH:MM` time (A2's «✓ утверждён HH:MM»),
    read from the catalog so the check holds whatever language the runner's UI uses."""
    filled = strings.text("card.plan_done", time="00:00")
    return re.escape(filled).replace("00:00", r"\d\d:\d\d")


def proposal():
    """The proposed joint-example snapshot the unit stand-ins read: version 1, status `proposed`, the summary line
    the criteria quote, and the plan view that carries it."""
    view = PlanView("proposal", 1, "proposed", ("", SUMMARY),
                    ("approve", "revise", "reject", "requirements"))
    return Snapshot(project="P", branch="main", clean=True, version=1, status="proposed", lines=(SUMMARY,), roles=(),
                    plan=view)


def _main_method(name):
    """The real `MainScreen` method `name`, copied onto the stand-in class so the method under test itself runs on
    the double (`test_tui_draft_card`'s own helper)."""
    def missing(self, *args, **kwargs):  # pragma: no cover - reached only where the tests skip anyway
        raise AssertionError(MISSING_REASON)
    return missing if ui is None else getattr(ui.MainScreen, name)


def _app_method(name):
    """The real `ZplanApp` method `name`, copied onto the stand-in app (the note's own `revision_note` runs on it)."""
    def missing(self, *args, **kwargs):  # pragma: no cover - reached only where the tests skip anyway
        raise AssertionError(MISSING_REASON)
    return missing if ui is None else getattr(ui.ZplanApp, name)


class _Slot:
    """The conversation stand-in (`#chat`, i3-chat-inline): it records the widgets mounted on it (and the card a
    replacement goes right after) and the ones taken off, so the contract's own bookkeeping (no running app) is
    what the assertions read."""

    def __init__(self):
        self.mounted, self.removed = [], []
        self.after = []

    def mount(self, widget, after=None):
        self.mounted.append(widget)
        if after is not None:
            self.after.append((widget, after))

    def remove_children(self, widgets):
        self.removed.extend(widgets)


class _Plan:
    """The controller side `ZplanApp.revision_note` reaches: a revision request is recorded, nothing runs."""

    def __init__(self):
        self.revisions = []

    def revise_plan(self, text, done):
        self.revisions.append(text)


class _Approved:
    """The verdict a successful plan decision delivers to its callback (`Outcome("approved")` in production)."""

    kind = "approved"


class _App:
    """The app double the plan-card routes touch: the snapshot the source reads, the decisions and pushed screens
    they make, and the status line a refusal writes. `revision_note` is the real method, so the note's callback is
    exercised, not re-implemented."""

    revision_note = _app_method("revision_note")

    def __init__(self, snapshot=None):
        self.snapshot, self.controller = snapshot, _Plan()
        self.chat_note, self.plan_lines = "", ()
        self.decisions, self.pushed = [], []
        self.decide_error = None  # the refusal text the callback delivers (None: the decision succeeds)

    def decide(self, name, version, reason=None, after=None):
        """`ZplanApp.decide`'s real contract: the decision is recorded (queued) and its verdict — the approved
        outcome, or `decide_error` — comes back later through `after(outcome, error)`, never as a synchronous
        return. A route that closes the card before the callback can therefore never see a refusal."""
        self.decisions.append((name, version))
        if after is not None:
            after(_Approved(), self.decide_error)

    def push_screen(self, screen, callback=None):
        self.pushed.append((screen, callback))

    def deliver(self, handler):
        return handler

    def changed(self):
        pass


class _Screen:
    """The `MainScreen` stand-in of the plan-card tests: the real card bookkeeping runs on it (`show_card`,
    `close_card`, `unmount_card`, `render_card_sources`, `newest_card_for`, `status_note`) and only the widgets they
    touch are doubled — the slot above the chat and the app. No DOM, no project, no pilot."""

    show_card = _main_method("show_card")
    close_card = _main_method("close_card")
    unmount_card = _main_method("unmount_card")
    render_card_sources = _main_method("render_card_sources")
    status_note = _main_method("status_note")
    show_chat = _main_method("show_chat")
    newest_card_for = _main_method("newest_card_for")
    narrow = False

    def __init__(self, snapshot=None):
        self.box, self.app = _Slot(), _App(snapshot)
        self.card_widgets, self.card_specs, self.draft_cards, self.cards_seen = {}, {}, {}, set()

    def query_one(self, selector, *args):
        if selector == "#chat":
            return self.box
        raise AssertionError(selector)

    def scroll_chat_end(self):
        """UI-only: the stand-in has no scroll to move."""

    def call_after_refresh(self, callback):
        """The card's own scroll-to-bottom request is UI work: the stand-in has no running app to schedule it on."""


@unittest.skipUnless(HAVE, MISSING_REASON)
class PlanCardSourceTests(unittest.TestCase):
    """A1's data at unit level: the source reads the counts out of the summary line and the card is the frozen
    builder's own spec."""

    def test_the_source_shows_one_card_for_a_proposed_plan_with_the_lines_counts(self):
        """A1: a proposed plan yields exactly one card, keyed `plan:<version>`, reading «План · 1 этап · 3 задачи»
        with the approve/revise pair — the counts taken verbatim from the summary line, the labels the frozen
        catalog's own."""
        screen = _Screen(proposal())
        specs = list(ui.CARD_SOURCES["plan"](screen))
        self.assertEqual([spec.key for spec in specs], ["plan:1"])
        spec = specs[0]
        self.assertEqual(spec.title, strings.text("card.plan_title", stages="1 этап", tasks="3 задачи"))
        self.assertEqual(spec.title, "Plan · 1 этап · 3 задачи")
        self.assertEqual(spec.text, strings.text("card.plan_text"))
        self.assertEqual(spec.buttons, ((strings.text("card.approve_yes"), "/approve"),
                                         (strings.text("card.revise"), "/decline")))
        self.assertIsNone(spec.done)
        self.assertFalse(spec.alarm)

    def test_rs2_a_stale_proposal_card_offers_revise_only(self):
        """RS2 C1: a proposed plan the project has moved away from (its view's family is `plan.stale`) cannot be
        approved, so its card keeps the key and the counts but offers «доработать» alone and says why."""
        snapshot = proposal()
        stale = replace(snapshot, plan=PlanView("proposal", 1, "proposed", snapshot.plan.lines,
                                                ("revise", "reject", "requirements"), family="plan.stale"))
        spec = list(ui.CARD_SOURCES["plan"](_Screen(stale)))[0]
        self.assertEqual(spec.key, "plan:1")
        self.assertEqual(spec.title, "Plan · 1 этап · 3 задачи")
        self.assertEqual(spec.text, strings.text("card.plan_stale_text"))
        self.assertEqual(spec.buttons, ((strings.text("card.revise_only"), "/decline"),))
        self.assertNotIn("/approve", spec.hint or "".join(command for _, command in spec.buttons))

    def test_the_source_carries_no_card_outside_a_proposed_plan(self):
        """The source's own gate: version/status are the task's own definition of a proposed plan, and an approved,
        absent or running plan yields no card."""
        cases = (Snapshot(project="P", branch="main", clean=True, version=1, status="approved", lines=(), roles=()),
                 Snapshot(project="P", branch="main", clean=True, version=None, status=None, lines=(), roles=()),
                 Snapshot(project="P", branch="main", clean=True, version=1, status="run_failed", lines=(), roles=()))
        for snapshot in cases:
            with self.subTest(status=snapshot.status):
                self.assertEqual(list(ui.CARD_SOURCES["plan"](_Screen(snapshot))), [])
        self.assertEqual(list(ui.CARD_SOURCES["plan"](_Screen(None))), [])

    def test_a_summary_line_without_counts_shows_the_card_without_them(self):
        """The task's «no counts in the line -> the card without them»: a proposed plan whose view names no summary
        line (its view could not be built) still yields the decision, reading just the plan word — the counts are
        never invented and the buttons are unchanged."""
        snapshot = proposal()
        self.assertEqual(ui.plan_card_counts(None), ("", ""))
        self.assertEqual(ui.plan_card_counts(snapshot.plan), ("1 этап", "3 задачи"))
        self.assertEqual(ui.plan_card_counts(PlanView("proposal", 1, "proposed", ("", "План r1 · проверен"), ())),
                         ("", ""))
        spec = list(ui.CARD_SOURCES["plan"](_Screen(replace(snapshot, plan=None))))[0]
        self.assertEqual(spec.title, strings.text("pane.plan"))
        self.assertEqual(spec.buttons, ((strings.text("card.approve_yes"), "/approve"),
                                        (strings.text("card.revise"), "/decline")))


@unittest.skipUnless(HAVE, MISSING_REASON)
class PlanCardCommandTests(unittest.TestCase):
    """A2, A3 and A5 at the dispatcher level: the same one dispatcher the button and the typed line share, with the
    stand-in screen whose card bookkeeping is the real methods."""

    def setUp(self):
        # Only this run's source: the other registered sources (e.g. i3e1's `ready`) read app state the double
        # does not carry.
        sources = patch.dict(ui.CARD_SOURCES, {"plan": ui.CARD_SOURCES["plan"]}, clear=True)
        sources.start()
        self.addCleanup(sources.stop)

    def test_a2_approve_decides_once_opens_no_modal_and_writes_the_receipt(self):
        """A2: the button's `/approve` (and a typed `/approve` with no key, which finds the newest open card) calls
        `decide("approve", 1)` exactly once and turns the card into «✓ утверждён HH:MM», with no screen pushed — the
        PlanScreen confirmation modal is what the card exists to replace."""
        for key in ("plan:1", None):
            with self.subTest(key=key):
                screen = _Screen(proposal())
                screen.render_card_sources()
                ui.COMMAND_ACTIONS["/approve"](screen, "", key)
                self.assertEqual(screen.app.decisions, [("approve", 1)])
                self.assertEqual(screen.app.pushed, [])
                closed = screen.card_specs["plan:1"]
                self.assertIsNotNone(closed.done)
                self.assertRegex(closed.done, "^%s$" % receipt_pattern())
                self.assertEqual(screen.box.mounted[-1].spec, closed)  # the slot shows the receipt

    def test_a3_decline_opens_the_enter_note_and_a_cancel_keeps_the_card(self):
        """A3: «нет, доработать» opens the plan screen's note with enter submitting and the app's own
        `revision_note` as its callback; the callback's text starts the revision (`revise_plan` asked once), and a
        cancel (the `None` an esc delivers) asks nothing — the plan stays proposed, so the source still yields the
        card and it stays open."""
        screen = _Screen(proposal())
        screen.render_card_sources()
        ui.COMMAND_ACTIONS["/decline"](screen, "", "plan:1")
        self.assertEqual(len(screen.app.pushed), 1, screen.app.pushed)
        note, callback = screen.app.pushed[0]
        self.assertEqual(type(note).__name__, "NoteScreen")
        self.assertTrue(note.enter)  # a card-origin note: enter submits
        self.assertEqual(callback, screen.app.revision_note)
        self.assertIs(callback.__self__, screen.app)
        callback(None)  # esc: the note closes unchanged
        self.assertEqual(screen.app.controller.revisions, [])
        self.assertEqual([spec.key for spec in ui.CARD_SOURCES["plan"](screen)], ["plan:1"])
        self.assertIsNone(screen.card_specs["plan:1"].done)  # still an open decision
        callback("короче")  # enter: the revision request goes to the controller
        self.assertEqual(screen.app.controller.revisions, ["короче"])

    def test_a5_a_refused_approve_keeps_the_card_and_says_why(self):
        """A5 through the real decision contract: the refusal arrives later, as the `error` of the callback
        `ZplanApp.decide` hands the controller («план устарел…», exactly the text `refusal(Blocked)` produces) — not
        as an exception the button could catch. The open card stays (no receipt, no modal) and the reason is written
        by `decide` itself (A10c: the card adds no line of its own, `chat_note` stays empty); the decision was still
        attempted exactly once, and a receipt is written only after a success comes back (the positive half of
        this contract is A2's own test)."""
        screen = _Screen(proposal())
        screen.render_card_sources()
        screen.app.decide_error = refusal(Blocked("план устарел", family="plan.stale"))
        ui.COMMAND_ACTIONS["/approve"](screen, "", "plan:1")
        self.assertEqual(screen.app.decisions, [("approve", 1)])
        self.assertIsNone(screen.card_specs["plan:1"].done)
        self.assertEqual(screen.app.chat_note, "")
        self.assertEqual(screen.app.pushed, [])


# The whole-app half: A1+A2 and A1+A4, one shell method each. --------------------------------------------------

class JointEngine(FixtureEngine):
    """The fixture engine whose review carries the joint example's plan (1 milestone, 3 tasks): the fixture's own plan
    has two milestones of two tasks and would name other counts."""

    def output(self, authority):
        output = super().output(authority)
        output["proposal"] = canonical(JOINT_PLAN)
        return output


@unittest.skipUnless(HAVE, MISSING_REASON)
class ApproveCardShell(PlanningShell):
    """The planning shell that can seed the joint-example proposed plan and reads the main screen's card slot."""

    def propose_joint(self):
        """The joint example's proposed revision, written before the shell opens (exactly as the fixture shell
        writes a proposed plan, only with this run's counts)."""
        with Authority(self.state, self.project, fixture_id="test") as authority:
            authority.begin(GOAL, ROLES, "fixture")
            JointEngine().proposal(authority, lambda _: None)

    def main(self):
        """The main screen, whatever modal (if any) is on top."""
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def card(self):
        """The card the conversation holds, or None."""
        return next(iter(self.main().card_widgets.values()), None)

    async def card_shown(self, pilot, timeout=8.0):
        """The plan card of the slot, once it is mounted and laid out."""
        await self.until(pilot, lambda: self.card() is not None, timeout)
        await pilot.pause(0.3)
        return self.card()

    async def choose(self, pilot, command):
        """Press the card button that carries the slash command `command`."""
        button = next(widget for widget in self.card().query(Button) if widget.command == command)
        await pilot.click(button)
        await pilot.pause(0.3)

    def assert_card_under_the_chat(self, card, size):
        """A1 (i3-chat-inline): the card is mounted inline in the conversation's scroll (`#chat`), inside the chat
        pane, and its title and both buttons are drawn (the view is at the bottom, where the card was mounted)."""
        main = self.main()
        scroll, pane = main.query_one("#chat"), main.query_one("#chat-pane")
        self.assertIs(card.parent, scroll, size)                 # the card is an entry of the conversation
        self.assertGreater(card.region.height, 0, size)          # it took its own rows
        self.assertLessEqual(card.region.bottom, pane.region.bottom, size)  # inside the chat pane
        shown = screen_text(self.app)
        self.assertIn(strings.text("card.plan_title", stages="1 milestone", tasks="3 tasks"), shown, size)
        for label in (strings.text("card.approve_yes"), strings.text("card.revise")):
            self.assertIn(label, shown, size)


@unittest.skipUnless(HAVE, MISSING_REASON)
class ApproveCardTests(ApproveCardShell):
    async def test_a1_a2_the_card_shows_the_counts_and_approves_in_one_click(self):
        """A1 at 120x40: with the joint-example proposed plan the card shows under the chat, reading «План · 1 этап
        · 3 задачи» with «да, утвердить» and «нет, доработать». A2: pressing «да, утвердить» calls `decide("approve",
        1)` exactly once and no modal opens (the screen is still the main one), and the card turns into «✓ утверждён
        HH:MM»; the real approval ran, so the stored revision is `approved`."""
        self.propose_joint()
        calls, real = [], ui.ZplanApp.decide

        def spy(app, name, version, reason=None, after=None):
            calls.append((name, version))
            return real(app, name, version, reason, after)

        with patch.object(ui.ZplanApp, "decide", spy):
            async with self.shell(size=(120, 40)) as pilot:
                await self.loaded(pilot)
                card = await self.card_shown(pilot)
                self.assert_card_under_the_chat(card, (120, 40))
                self.assertEqual(card.spec.title, strings.text("card.plan_title", stages="1 milestone", tasks="3 tasks"))
                self.assertEqual([button.label.plain for button in card.query(Button)],
                                 [strings.text("card.approve_yes"), strings.text("card.revise")])
                await self.choose(pilot, "/approve")
                await self.until(pilot, lambda: self.card() is not None and self.card().spec.done)
                self.assertEqual(calls, [("approve", 1)])
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")  # no confirmation modal
                self.assertRegex(self.card().spec.done, "^%s$" % receipt_pattern())
        self.assertEqual(self.stored()["revisions"][0]["status"], "approved")


@unittest.skipUnless(HAVE, MISSING_REASON)
class RefusedApproveCardTests(ApproveCardShell):
    def drawn(self):
        return " ".join(screen_text(self.app).replace("│", " ").split())

    async def test_a10c_a_refused_approve_says_why_once_and_a_success_shows_its_line_once(self):
        """A10c P1/P2 on the real app: `/approve` from the plan card for a version that is no longer the current
        proposal (r9 against the stored r1) shows «Not done: …» once on the main screen and the card stays, the
        card adding no line of its own; the approval of r1 closes the card and «Plan r1 approved.» shows once.
        Interpretation: the stale card is the plan route run with a key the store no longer proposes; «once» is
        counted on the screen text with the pane's wraps removed (`drawn`; `flat` would add the status widget's text again)."""
        self.propose_joint()
        async with self.shell(size=(140, 50)) as pilot:
            await self.loaded(pilot)
            await self.card_shown(pilot)
            self.main().run_command("/approve", "", "plan:9")
            await self.until(pilot, lambda: "Not done: " in self.flat())
            await pilot.pause(0.5)
            self.assertEqual(self.drawn().count("Not done: "), 1)
            self.assertIn("plan:1", self.main().card_widgets)
            self.assertIsNone(self.card().spec.done)
            self.main().run_command("/approve", "", "plan:1")
            await self.until(pilot, lambda: self.card() is not None and self.card().spec.done)
            await pilot.pause(0.5)
            self.assertEqual(self.drawn().count("Plan r1 approved."), 1)
        self.assertEqual(self.stored()["revisions"][0]["status"], "approved")


@unittest.skipUnless(HAVE, MISSING_REASON)
class NarrowApproveCardTests(ApproveCardShell):
    async def test_a1_a4_at_80x24_the_card_is_visible_and_plan_screen_approval_takes_it_off(self):
        """A1 at 80x24: the card is visible under the chat (the chat pane is the shown one in narrow mode, and the
        card takes rows of the slot under the chat body). A4: approving r1 through PlanScreen ([p], [a] and the
        confirmation) ends the proposed state, so the source returns nothing and the card is off the main screen on
        the next render — no card-side code runs for that path."""
        self.propose_joint()
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            card = await self.card_shown(pilot)
            self.assert_card_under_the_chat(card, (80, 24))
            await self.panel(pilot)
            await self.command(pilot, "/view")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "PlanScreen")
            await self.press_button(pilot, "approve")  # p4a: the button is the consent, no second question
            await self.until(pilot, lambda: self.card() is None)
        self.assertEqual(self.stored()["revisions"][0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
