"""I3e2: the failure card — a failed stage or a failed planning run as a red card with «try again» and
«details» (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md run i3e2).

The card contract is devtools/zeroshot/tasks/card-contract.md: kind `failed`, keys
`failed:r<version>:<milestone>:<attempt>` and `failed:plan:<version>`, `cards.error_card` (red), the card-only
commands `/retry` and `/details`. Two whole-app
walks (the budget of two whole-app methods): A1 at 120x40 and 80x24, and A2's recoverable half with A3 (the retry
resumes the same attempt and closes the card with the receipt; «details» opens the run screen of that attempt).
A2's `failed` half (the first offered action there is a new attempt, and `check` is the third of the three), A4 (a
failed planning run), A5 (a view offering none of the three retry actions), the key shapes, the one-fetch-per-key
rule and the bound of the card's text are unit level, with a stand-in screen whose only real parts are the card
bookkeeping and the real `MainScreen` methods under test (no pilot, no project, no engine).

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- The card's text is the *body* of the end view (A1's line), not its heading or status line: the card is the short
  form of what RunScreen shows, bounded by `FAILED_CARD_LINES` (6) lines; the leading blank line the screens drop
  (the plan view starts with one) is dropped here too, and the rest is shown verbatim (`markup=False`, as every
  card text is).
- The card's `at` is the clock read *once per key*, when the end view is fetched (for the planning card: when it is
  first drawn): neither the end view nor the plan view carries a time of its own, and a refresh has to paint the
  same card again instead of remounting it every tick. It is not the attempt's time (nothing in the contracts
  carries it to the screen).
- The end view behind a stage card is fetched once per key through `controller.open_run` — the same view `[o]`
  shows — off the event loop, and cached on the screen (`failed_card_view`): the card's text and its buttons come
  from that view, so no button can act on a view that was never fetched, and a refresh never repeats the call.
- `/retry` on a stage runs the first offered of `resume`, `new_attempt`, `check` modal-less: the service call
  RunScreen makes for that action (`resume_run` / `new_attempt` with an empty note / `check_run`), without a form,
  followed by the same observation the modal path starts (`watch_run`) — a retried attempt that is not observed
  would stay `running` on screen forever. A started attempt closes the card with the `card.error_retried` receipt;
  a refusal starts nothing, says so on the status line and keeps the card.
- `/retry` on a failed planning run is the existing restart-planning path (`controller.restart_plan`, what [g] runs
  on the plan screen of a failed revision) followed by `after_submission`, exactly as the plan screen's own [g]
  does; `ready` is the verdict that means the planner was started, so that is the one that closes the card.
- A stage row without an attempt (`token is None`) has no end view to show and is no card; a failed planning run
  without a plan view (the store could not be read) has no text to show either, so the card needs the view.
- The example's failure line («Модель не ответила за 10 минут (exit 1)») is the fixture's own terminal reason here
  (`ExampleDriver`): the shipped fixture reason is `fixture_failed`, and the end view's body quotes the reason, so
  the criterion's exact line can only be asserted against the fixture that carries it. The fixture is test data,
  never product copy.
"""

import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

# imported first for its side effect: the offline wheelhouse (ZPLAN_TEST_WHEELHOUSE) joins `sys.path` before the
# guarded imports below, so this module sees Textual and Rich there on a host that installs neither.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_lines

from terminal_planner import planning
from terminal_planner.delivery import EndAction, EndView, Token
from terminal_planner.tui import strings

# The declared count of this module must not depend on Textual or Rich (tests.test_toolchain): the imports below
# are guarded, and a stand-in keeps every class declared where they are missing.
from test_tui_draft_card import MISSING_REASON, _main_method
import test_process as tpr
import test_tui_plan_gate as gate
import test_tui_planning as planning_shell
from test_tui_milestones import Gated, MilestoneShell

try:
    from textual.widgets import Button
    from terminal_planner.tui import app as ui
    from terminal_planner.tui.controller import Controller, Outcome, Row, Snapshot
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    Button = ui = Controller = Outcome = Row = Snapshot = None

HAVE = HAVE_TEXTUAL and ui is not None
# The joint example's failure line: the fixture's termina reason here, and the first body line of every end view
# this module's whole-app walks build (`delivery.reason` quotes the run's diagnostic).
FAILED_LINE = "Модель не ответила за 10 минут (exit 1)"


def retried_pattern():
    """The retry receipt as a pattern: `card.error_retried` with a `HH:MM` time (A2's «↻ try again HH:MM»),
    read from the catalog so the check holds whatever language the runner's UI uses."""
    filled = strings.text("card.error_retried", time="00:00")
    return re.escape(filled).replace("00:00", r"\d\d:\d\d")


class ExampleDriver(Gated):
    """The gated milestone driver with the joint example's own failure line.

    The fixture's terminal reason is `fixture_failed` and the end view's body is that reason quoted
    (`delivery.reason`), so the criterion's exact line can only be asserted against a driver that carries it: the
    fixture is test data (the module docstring's interpretation), and this subclass only replaces the reason the
    fixture run ends with. Every other behaviour — the gated slices, the counted submissions — is the shell's own.
    """

    failure_line = FAILED_LINE

    def conclude(self, state):
        super().conclude(state)
        terminal = state.get("terminal")
        if terminal and terminal.get("status") == "failed":
            terminal["reason"] = self.failure_line


@unittest.skipUnless(HAVE, MISSING_REASON)
class FailedCardShell(MilestoneShell):
    """The milestone shell (a real temporary Git repository, the fixture store, the gated driver) whose failed
    attempts end with the joint example's line, plus the card helpers of the whole-app walks."""

    def setUp(self):
        super().setUp()
        self.driver = ExampleDriver(self.root / "fixture-runs")
        self.addCleanup(self.driver.gate.set)

    def main(self):
        """The main screen, whatever modal (if any) is on top."""
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def cards(self):
        """The card specs in the slot, by key (the card contract's own bookkeeping)."""
        return self.main().card_specs

    def card(self):
        """The card widget the conversation holds, or None."""
        return next(iter(self.main().card_widgets.values()), None)

    async def card_shown(self, pilot, key, timeout=8.0):
        """The card of `key`, once it is mounted and laid out (a stage card's end view is fetched on the worker
        first, so the card appears one render after the row does)."""
        await self.until(pilot, lambda: key in self.cards(), timeout)
        await pilot.pause(0.3)
        return self.cards()[key]

    def card_text(self):
        """What the card's own box shows, as one whitespace-joined text: the visible compositor rows cut to the
        card's region, its own border glyphs read as separators — so the pane beside the card is never read as the
        card's text, a body line the pane wrapped is read as one text, and a row the screen does not show
        contributes nothing. The title rides the border row and the `at` the bottom one, exactly as the card draws
        them, so both are part of what this reads."""
        card = self.card()
        rows = screen_lines(self.app)[card.region.y:card.region.bottom]
        framed = " ".join(row[card.region.x:card.region.right] for row in rows)
        for glyph in "─│╭╮╰╯":
            framed = framed.replace(glyph, " ")
        return " ".join(framed.split())

    async def choose(self, pilot, command):
        """Press the button of the card on the slot that carries the slash command `command`."""
        button = next(widget for widget in self.card().query(Button) if widget.command == command)
        await pilot.click(button)
        await pilot.pause(0.3)

    def counting(self, calls, name):
        """A spy on one controller job: records the milestone it was called with and still runs the real one."""
        real = getattr(Controller, name)

        def spy(controller, token, *args, **kwargs):
            calls.append(token.milestone)
            return real(controller, token, *args, **kwargs)
        return spy


@unittest.skipUnless(HAVE, MISSING_REASON)
class FailedCardTests(FailedCardShell):
    async def test_a1_no_run_screen_pops_and_the_card_is_visible_at_both_sizes(self):
        """A1: an attempt that ends `failed_recoverable` no longer pops RunScreen — the red card «! Error · M1»
        takes its place under the chat with the end view's own body line («Модель не ответила за 10 минут
        (exit 1)») and both buttons, and it is visible at 80x24 as well.

        The first pass starts the attempt (the run is observed from the shell: `follow=True`), the second only opens
        the shell again over the same store: the row is still `failed_recoverable`, so the card is built from the
        stored attempt and fetched again — no second run is started and no modal pops either."""
        self.driver.outcomes = ("failed_recoverable",)
        self.approve(running=False)
        title = strings.text("card.error_title", task="M1")
        for size in ((120, 40), (80, 24)):
            with self.subTest(size=size):
                async with self.shell(size=size, follow=size == (120, 40)) as pilot:
                    await self.loaded(pilot)
                    if size == (120, 40):
                        await self.begin_run(pilot)
                    key = "failed:r1:M1:1"
                    spec = await self.card_shown(pilot, key)
                    # A1: the card replaced the automatic modal — nothing of RunScreen is on the stack
                    self.assertNotIn("RunScreen", [type(screen).__name__ for screen in self.app.screen_stack], size)
                    self.assertEqual(type(self.app.screen).__name__, "MainScreen", size)
                    self.assertTrue(spec.alarm, size)  # red
                    self.assertEqual(spec.title, title, size)
                    self.assertIn(FAILED_LINE, spec.text, size)
                    self.assertEqual([(label, command) for label, command in spec.buttons],
                                     [(strings.text("card.error_retry"), "/retry"),
                                      (strings.text("card.error_details"), "/details")], size)
                    # A1's own look: the card's box is laid out inline in the conversation, inside the pane, and
                    # its rows carry the title, the end view's line and both buttons (the body line the pane wraps
                    # is read as one text).
                    scroll = self.main().query_one("#chat")
                    pane = self.main().query_one("#chat-pane")
                    self.assertGreater(self.card().region.height, 0, size)
                    self.assertIs(self.card().parent, scroll, size)
                    self.assertLess(self.card().region.y, pane.region.bottom, size)
                    shown = self.card_text()
                    for needle in (title, FAILED_LINE, strings.text("card.error_retry"),
                                   strings.text("card.error_details")):
                        self.assertIn(needle, shown, (needle, size))

    async def test_a2_a3_details_open_the_run_screen_and_retry_resumes_the_same_attempt(self):
        """A2's recoverable half and A3 in one walk at 120x40: «details» opens RunScreen for M1 (the card's own
        cached end view, the same one [o] builds), and «try again» on the `failed_recoverable` card calls
        `resume_run` once — with the card's own token — and the card becomes «↻ try again HH:MM». The attempt
        the resume started is observed (`watch_run`), so the row follows it.

        The driver's slices are held (`gate`) while the receipt is checked: the resumed attempt's own end would
        otherwise replace the closed receipt on the slot. The gate is released before the shell closes. A2's `failed`
        half (the first offered action is `new_attempt` there) is unit level, in `FailureCardUnitTests`, as the
        whole-app budget of two methods asks."""
        self.driver.outcomes = ("failed_recoverable",)
        self.approve(running=False)
        resume = []
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            await self.card_shown(pilot, "failed:r1:M1:1")
            # A3: «details» is the attempt's own end-of-run screen
            await self.choose(pilot, "/details")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "RunScreen")
            self.assertEqual(self.app.screen.end.milestone, "M1")
            self.assertIn(FAILED_LINE, " ".join(self.app.screen.end.body))
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            # A2: the retry resumes the same attempt, modal-lessly, and closes the card with the receipt
            self.driver.gate.clear()
            with patch.object(Controller, "resume_run", self.counting(resume, "resume_run")):
                await self.choose(pilot, "/retry")
                await self.until(pilot, lambda: self.cards()["failed:r1:M1:1"].done is not None)
            self.assertEqual(resume, ["M1"])
            self.assertRegex(self.cards()["failed:r1:M1:1"].done, "^%s$" % retried_pattern())
            self.assertEqual(self.main().card_widgets["failed:r1:M1:1"].spec.done,
                             self.cards()["failed:r1:M1:1"].done)
            self.driver.gate.set()

class _Slot:
    """The conversation stand-in (`#chat`, i3-chat-inline): records what is mounted on it (and the card a
    replacement goes right after) and what is taken off, so the contract's own bookkeeping is what the assertions
    read (no running app)."""

    def __init__(self):
        self.mounted, self.removed = [], []
        self.after = []

    def mount(self, widget, after=None):
        self.mounted.append(widget)
        if after is not None:
            self.after.append((widget, after))

    def remove_children(self, widgets):
        self.removed.extend(widgets)


class _Controller:
    """The controller side of the card fetch and the card commands: `open_run` answers with the scripted end view
    of that milestone at once (as the worker's delivery does on the UI thread), and every retry job records its
    call and answers its scripted outcome."""

    def __init__(self, ends=None, outcome=None, error=None):
        self.ends = ends or {}
        self.outcome, self.error = outcome, error
        self.opens, self.calls = [], []

    def open_run(self, milestone, done):
        self.opens.append(milestone)
        done(Outcome("end", data=self.ends.get(milestone)), None)

    def resume_run(self, token, done):
        self.calls.append(("resume", token.milestone))
        done(self.outcome, self.error)

    def new_attempt(self, token, note, done):
        self.calls.append(("new_attempt", token.milestone, note))
        done(self.outcome, self.error)

    def check_run(self, token, done):
        self.calls.append(("check", token.milestone))
        done(self.outcome, self.error)

    def restart_plan(self, done):
        self.calls.append(("restart_plan",))
        done(self.outcome, self.error)


class _Pad:
    """The app side of the stand-in screen: the snapshot, the controller, the note pad and the wake-ups, plus the
    actions a card command reaches — recorded, never run (no screen stack, no worker)."""

    def __init__(self, snapshot=None, controller=None):
        self.snapshot = snapshot
        self.controller = controller if controller is not None else _Controller()
        self.chat_note, self.changes, self.refreshes = "", 0, 0
        self.ends, self.plans, self.submitted = [], [], []
        self.run_lines, self.plan_lines, self.run_watch = [], (), None

    def changed(self):
        self.changes += 1

    def request_refresh(self):
        self.refreshes += 1

    def deliver(self, handler):
        return lambda result, error: handler(result, error)

    def show_end(self, end, note=""):
        self.ends.append((end, note))

    def action_open_plan(self):
        self.plans.append(True)

    def after_submission(self, outcome):
        self.submitted.append(outcome)

    def watch_run(self, milestone):
        self.run_watch = milestone

    def fresh_attempt(self, milestone, run_id, line=None):
        self.run_lines = [] if line is None else [line]  # a new attempt's own lines
        self.run_watch = milestone

    def attach_attempt(self, milestone, run_id, line=None):
        self.run_watch = milestone
        if line is not None:
            self.run_lines.append(line)


class _Screen:
    """The MainScreen stand-in of the unit half: the real failure-card and card-slot methods run on it, and only
    the widgets they touch are doubled (the slot above and the app's pad). No DOM, no pilot, no project."""

    show_card = _main_method("show_card")
    close_card = _main_method("close_card")
    unmount_card = _main_method("unmount_card")
    status_note = _main_method("status_note")
    show_chat = _main_method("show_chat")  # a no-op here: the stand-in is wide
    render_card_sources = _main_method("render_card_sources")
    newest_card_for = _main_method("newest_card_for")
    failed_cards = _main_method("failed_cards")
    failed_card_view = _main_method("failed_card_view")
    failed_card_at = _main_method("failed_card_at")
    failed_card_fetched = _main_method("failed_card_fetched")
    failed_card_ref = _main_method("failed_card_ref")
    retry_failed_card = _main_method("retry_failed_card")
    retry_failed_plan = _main_method("retry_failed_plan")
    show_failed_card = _main_method("show_failed_card")
    narrow = False

    def __init__(self, snapshot=None, controller=None):
        self.box, self.app = _Slot(), _Pad(snapshot, controller)
        self.card_widgets, self.card_specs, self.draft_cards, self.cards_seen = {}, {}, {}, set()

    def query_one(self, selector, *args):
        if selector == "#chat":
            return self.box
        raise AssertionError(selector)

    def scroll_chat_end(self):
        """UI-only: the stand-in has no scroll to move."""

    def call_after_refresh(self, callback):
        """The card's own scroll-to-bottom request is UI work: the stand-in has no running app to schedule it on."""


def stage_row(milestone="M1", attempt=1, state="failed_recoverable"):
    """One failed milestone row with the attempt its card keys and acts on."""
    return Row(id=milestone, title="%s title" % milestone, state=state, text="сбой · можно продолжить",
               token=Token(milestone, 1, attempt, "run-" + milestone, "failed", "failed", "none"))


def end_view(names=("resume", "new_attempt", "plan"), state="failed_recoverable", milestone="M1", attempt=1,
             body=(FAILED_LINE,)):
    """The end view one failed attempt's card is built from, with the offered owner actions `names`."""
    token = Token(milestone, 1, attempt, "run-" + milestone, "failed", "failed", "none")
    actions = tuple(EndAction(name, "%s.%s" % (state, name)) for name in names)
    return EndView(state, token, milestone, "%s title" % milestone, "%s · title — сбой" % milestone,
                   "  Прогон: сбой · доставка: не экспортирован", tuple(body), actions)


def render(screen, renders=2):
    """One state render of the stand-in screen (what `render_state` schedules): a stage card's fetch starts on the
    first one and its answer asks for the repaint (`failed_card_fetched` -> `app.changed`) that the second one is —
    `render_card_sources` runs on every render, so a card appears on the render after its key was fetched."""
    for _ in range(renders):
        screen.render_card_sources()


def stage_snapshot(*rows, plan=None, status=None, version=1):
    """A snapshot of `rows` (and, when asked, of a plan view), the only part of it the failure-card source reads.
    `version` is the plan revision the stage cards' keys carry (the corrective: one card per revision), so its
    default names the joint example's r1."""
    return Snapshot("P", "main", True, version, status, (), (), plan=plan, rows=tuple(rows))


@unittest.skipUnless(HAVE, MISSING_REASON)
class FailureCardUnitTests(unittest.TestCase):
    """A4, A5 and the card's own rules, without a shell: the real `MainScreen` methods on a stand-in screen whose
    card slot and app are doubled, and a controller whose `open_run` answers at once (so the fetch a card needs is
    deterministic here, while the whole-app walks exercise it on the worker)."""

    def setUp(self):
        # Only this run's source: the other registered sources (e.g. i3e1's `ready`) read app state the double
        # does not carry.
        sources = patch.dict(ui.CARD_SOURCES, {"failed": ui.CARD_SOURCES["failed"]}, clear=True)
        sources.start()
        self.addCleanup(sources.stop)

    def test_a4_a_failed_planning_run_shows_a_card_whose_retry_restarts_planning_once(self):
        """A4: a failed planning run (r2, `run_failed`, its plan view `kind == "failed"`) shows the red card
        «! Error · Plan r2» with the plan view's own lines and both buttons; «details» opens the plan screen and
        «try again» restarts planning once through `controller.restart_plan` (the existing path), starting the
        observation (`after_submission`) and closing the card with the receipt. The key carries the version, so the
        revision a restart prepares is a card of its own."""
        view = planning.PlanView("failed", 2, "run_failed",
                                 ("", "План r2 · планирование не завершено.", "Цель: Add a paragraph"),
                                 ("retry", "revise"))
        controller = _Controller(outcome=Outcome("ready"))
        screen = _Screen(stage_snapshot(plan=view, status="run_failed", version=2), controller)
        screen.render_card_sources()
        key = "failed:plan:2"
        self.assertEqual(list(screen.card_specs), [key])
        spec = screen.card_specs[key]
        self.assertTrue(spec.alarm)
        self.assertEqual(spec.title, strings.text("card.error_title",
                                                  task=strings.text("canvas.plan_rev", v=2)))
        self.assertIn("План r2 · планирование не завершено.", spec.text)
        self.assertEqual(spec.buttons, ((strings.text("card.error_retry"), "/retry"),
                                        (strings.text("card.error_details"), "/details")))
        self.assertTrue(ui.MainScreen.run_command(screen, "/details", "", key))
        self.assertEqual(screen.app.plans, [True])  # A4's «details»: the plan screen, no request
        self.assertEqual(controller.opens, [])
        self.assertTrue(ui.MainScreen.run_command(screen, "/retry", "", key))
        self.assertEqual(controller.calls, [("restart_plan",)])
        self.assertEqual([outcome.kind for outcome in screen.app.submitted], ["ready"])
        self.assertRegex(screen.card_specs[key].done, "^%s$" % retried_pattern())
        screen.render_card_sources()  # a closed card is never offered again
        self.assertIsNotNone(screen.card_specs[key].done)

    def test_a10_b3_a_rejected_plan_shows_its_card_with_three_buttons_at_every_level_and_the_screen_is_not_idle(self):
        """A10 B3: the current revision `review_exhausted` (r2, the autonomy level unread: the snapshot has no
        profile, i.e. manual) shows «The plan check rejected revision 2» with the findings and «revise» / «approve
        anyway» / «details»; «revise» is the plan screen's revision note, «approve anyway» its override form and the
        typed reason goes to `override_note`, «details» the plan screen; the screen state is `error`, not `idle`; a
        version 1 plan (no `override` action) has no «approve anyway»; the card leaves with the status.
        Interpretation: the buttons are the plan screen's actions, offered as it offers them."""
        view = planning.PlanView("proposal", 2, "review_exhausted", ("", "Plan r2 · checked"),
                                 ("revise", "restart", "override", "requirements"), findings="Too broad: split M2.")
        screen = _Screen(stage_snapshot(plan=view, status="review_exhausted", version=2))
        pushed, noted = [], []
        screen.app.push_screen = lambda note, callback: pushed.append((note, callback))
        screen.app.revision_note = lambda text: noted.append(("revise", text))
        screen.app.override_note = lambda version, text: noted.append(("override", version, text))
        with patch.dict(ui.CARD_SOURCES, {"rejected": ui.rejected_card_source}, clear=True):
            screen.render_card_sources()
            key = "rejected:plan:2"
            spec = screen.card_specs[key]
            self.assertEqual(spec.title, "The plan check rejected revision 2")
            self.assertIn("Too broad: split M2.", spec.text)
            self.assertEqual(spec.buttons, ((strings.text("card.revise_only"), "/decline"),
                                            ("approve anyway", "/approve"),
                                            (strings.text("card.error_details"), "/details")))
            self.assertEqual(ui.slash_state(screen.app.snapshot), "error")
            self.assertTrue(ui.MainScreen.run_command(screen, "/details", "", key))
            self.assertEqual(screen.app.plans, [True])
            ui.MainScreen.run_command(screen, "/decline", "", key)
            ui.MainScreen.run_command(screen, "/approve", "", key)
            self.assertEqual([callback for _, callback in pushed][0], screen.app.revision_note)
            pushed[1][1]("The owner accepts the risk.")
            self.assertEqual(noted, [("override", 2, "The owner accepts the risk.")])
            screen.app.snapshot = stage_snapshot(plan=view, status="approved", version=2)
            screen.render_card_sources()
            self.assertNotIn(key, screen.card_specs)
            old = planning.PlanView("proposal", 1, "review_exhausted", (), ("revise", "restart", "requirements"),
                                    findings="x")
            screen.app.snapshot = stage_snapshot(plan=old, status="review_exhausted", version=1)
            screen.render_card_sources()
            self.assertEqual([label for label, _ in screen.card_specs["rejected:plan:1"].buttons],
                             [strings.text("card.revise_only"), strings.text("card.error_details")])

    def test_rs2_a_typed_retry_does_what_the_cards_button_does_and_the_palette_lists_it(self):
        """RS2 C2: `/retry` typed in the chat (no card key) acts on the newest open card that routes it, exactly like
        the card's «try again» button, and is a command in every screen state the palette offers.
        Interpretation: «every state a card offers it» is every slash state — a failed card stays open beside a
        running stage, a merge wait or a draft, and a typed `/retry` with no card behind it says `note.not_now`."""
        from terminal_planner.tui import palette, slash
        for state in slash.STATES:
            with self.subTest(state=state):
                self.assertEqual(palette.submit("/retry", state), palette.Submitted("/retry", ""))
                self.assertIn("/retry", [command.name for command in slash.matches("/ret", state)])
        view = planning.PlanView("failed", 2, "run_failed", ("", "План r2 · планирование не завершено."),
                                 ("retry", "revise"))
        controller = _Controller(outcome=Outcome("ready"))
        screen = _Screen(stage_snapshot(plan=view, status="run_failed", version=2), controller)
        screen.render_card_sources()
        self.assertTrue(ui.MainScreen.run_command(screen, "/retry"))  # typed: key None -> the newest card for it
        self.assertEqual(controller.calls, [("restart_plan",)])
        self.assertRegex(screen.card_specs["failed:plan:2"].done, "^%s$" % retried_pattern())
        bare = _Screen(stage_snapshot(), _Controller())
        self.assertTrue(ui.MainScreen.run_command(bare, "/retry"))  # no card: the refusal line, nothing started
        self.assertEqual(bare.app.chat_note, strings.text("note.not_now", name="/retry"))

    def test_a5_a_stage_whose_view_offers_no_retry_action_shows_the_card_with_details_only(self):
        """A5: an attempt whose end view offers none of `resume`, `new_attempt`, `check` (here the blocked end
        view, which offers an answer and a plan revision) shows the card with «details» only — no retry button —
        and `/retry` on it starts nothing and leaves the card open; «details» still opens the attempt's end
        view."""
        end = end_view(names=("answer", "plan"), state="blocked", body=("  Причина: «fixture_failed»",))
        controller = _Controller(ends={"M1": end})
        screen = _Screen(stage_snapshot(stage_row(state="blocked")), controller)
        render(screen)
        key = "failed:r1:M1:1"
        spec = screen.card_specs[key]
        self.assertIn("Причина: «fixture_failed»", spec.text)
        self.assertEqual(spec.buttons, ((strings.text("card.error_details"), "/details"),))
        ui.COMMAND_ACTIONS["/retry"](screen, "", key)
        self.assertEqual(controller.calls, [])  # nothing was started
        self.assertIsNone(screen.card_specs[key].done)  # and the card is still an open decision
        ui.COMMAND_ACTIONS["/details"](screen, "", key)
        self.assertEqual(screen.app.ends, [(end, "")])

    def test_the_stage_card_is_fetched_once_per_key_red_and_bounded_to_six_lines(self):
        """The card's own rules: one card per failed row, keyed `failed:r<version>:<milestone>:<attempt>` (the plan
        revision and the attempt are part of the key, so a later revision or attempt is a card of its own), its end
        view fetched exactly once per key however often the state is rendered (and the card not remounted), its text
        the view's body bounded to `FAILED_CARD_LINES` (6) lines, and the card red (the error card's `alarm`)."""
        long_end = end_view(body=tuple("line %d" % n for n in range(1, 9)))
        second = end_view(names=("new_attempt", "plan"), state="failed", milestone="M2", attempt=2, body=("сбой",))
        controller = _Controller(ends={"M1": long_end, "M2": second})
        screen = _Screen(stage_snapshot(stage_row(), stage_row("M2", attempt=2, state="failed")), controller)
        render(screen)
        self.assertEqual(sorted(screen.card_specs), ["failed:r1:M1:1", "failed:r1:M2:2"])
        self.assertEqual(controller.opens, ["M1", "M2"])  # one fetch per key, off the event loop
        first = screen.card_specs["failed:r1:M1:1"]
        self.assertEqual(len(first.text.splitlines()), ui.FAILED_CARD_LINES)
        self.assertEqual(first.text.splitlines()[0], "line 1")
        self.assertTrue(first.alarm and screen.card_specs["failed:r1:M2:2"].alarm)
        widget = screen.card_widgets["failed:r1:M1:1"]
        screen.render_card_sources()
        self.assertEqual(controller.opens, ["M1", "M2"])  # the cache answers, the worker is not asked again
        self.assertIs(screen.card_widgets["failed:r1:M1:1"], widget)  # and the same card is not remounted

    def test_a3_a_new_revision_shows_its_own_failed_card_and_fetches_it_again(self):
        """A3 (regression, i3c corrective — the milestone card keys lacked the plan revision): the revision is part
        of `failed_card_key`, so a failed-stage card retried (closed) under r1 does not suppress the same stage's
        card under r2 — an open `failed:r2:M1:1` shows — and the r2 key fetches its own end view (a second
        `open_run`), never r1's cached one.

        Verified on the old layout (A5): reverting the key line to `failed:%s:%s` collapses both revisions onto
        `failed:M1:1`, so the closed r1 card (its key already in `cards_seen`) suppresses r2 and no second fetch is
        made — this test then fails with no open card and one fetch only."""
        controller = _Controller(ends={"M1": end_view()})
        screen = _Screen(stage_snapshot(stage_row()), controller)
        render(screen)
        self.assertIn("failed:r1:M1:1", screen.card_specs)
        # the owner retries r1: the card becomes its receipt; the approved r2 fails the same stage again
        screen.close_card("failed:r1:M1:1", "↻ try again 12:00")
        screen.app.snapshot = stage_snapshot(stage_row(), version=2)
        render(screen)
        open_keys = [k for k, spec in screen.card_specs.items() if spec.done is None]
        self.assertEqual(open_keys, ["failed:r2:M1:1"])  # the r2 card is open, r1's receipt is not brought back
        self.assertEqual(controller.opens, ["M1", "M1"])  # one fetch per key: the r2 key fetches its own view

    def test_a2_the_retry_runs_the_first_offered_action_modal_less(self):
        """A2, the mapping: the retry runs the *first* offered of `resume`, `new_attempt`, `check` — a `failed`
        attempt's card (which offers a new attempt and a plan revision) calls `new_attempt` once with an empty note
        (the modal-less path has no note field), a `check`-only view calls `check_run` once — and the attempt it
        starts is observed exactly as the modal's own action observes it (`watch_run`), the card closing with the
        receipt. A readiness refusal starts nothing, keeps the card open and says why on the status line. The
        `resume` half is the whole-app walk's (the same method, one call, end to end)."""
        for names, expected in ((("new_attempt", "plan"), ("new_attempt", "M1", "")), (("check",), ("check", "M1"))):
            with self.subTest(names=names):
                controller = _Controller(ends={"M1": end_view(names=names, state="failed")},
                                         outcome=Outcome("attempt"))
                screen = _Screen(stage_snapshot(stage_row(state="failed")), controller)
                render(screen)
                key = "failed:r1:M1:1"
                ui.COMMAND_ACTIONS["/retry"](screen, "", key)
                self.assertEqual(controller.calls, [expected])
                self.assertRegex(screen.card_specs[key].done, "^%s$" % retried_pattern())
                self.assertEqual(screen.app.run_watch, "M1")  # the observation the modal path starts too
        blocked = Outcome("blocked", checks=(SimpleNamespace(ok=False, line="Инструменты zplan не установлены"),))
        controller = _Controller(ends={"M1": end_view(names=("new_attempt",), state="failed")}, outcome=blocked)
        screen = _Screen(stage_snapshot(stage_row(state="failed")), controller)
        render(screen)
        ui.COMMAND_ACTIONS["/retry"](screen, "", "failed:r1:M1:1")
        self.assertEqual(controller.calls, [("new_attempt", "M1", "")])
        self.assertIsNone(screen.card_specs["failed:r1:M1:1"].done)  # nothing started: the card stays
        self.assertIn("Инструменты zplan не установлены", screen.app.chat_note)
        self.assertEqual(screen.app.run_watch, None)


@unittest.skipUnless(HAVE, MISSING_REASON)
class RejectedCardRefusalTests(tpr.ProfileTest, planning_shell.PlanningShell):
    async def test_a10b_a_refusal_from_the_rejected_card_shows_on_the_main_screen(self):
        """A10b C1/C3 on the real app: «approve anyway» on the rejected-plan card with a reason the rule refuses says
        so on the main screen (with the run lines) and the card stays, nothing is written; a valid reason approves,
        the card leaves and the outcome line shows there. C2 (the plan screen keeps its line under the plan view) is
        `test_tui_plan_gate`'s override walk. Interpretation: «shows» is the screen text with the pane's wraps
        removed (`flat`); the refusal's tail is not pinned, only the lead of the task's example."""
        gate.PlanGateShell.argued(self, "exhausted")
        path = self.sidecar().parent / "planning.json"
        before = path.read_bytes()
        async with self.shell(size=(140, 50)) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: "rejected:plan:1" in self.app.screen.card_specs)
            await pilot.pause(0.3)
            for reason in ("x" * 501, "the owner accepts the broad scope"):
                self.app.screen.run_command("/approve", "", "rejected:plan:1")
                await self.shows(pilot, "Approve plan r1 despite the check?")
                await self.type(pilot, reason)
                await self.press_button(pilot, "send")
                await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
                if len(reason) > 500:
                    await self.until(pilot, lambda: "Not done: A reason is required" in self.flat())
                    self.assertIn("rejected:plan:1", self.app.screen.card_specs)
                    self.assertEqual(path.read_bytes(), before)
            await self.until(pilot, lambda: "Plan r1 approved despite the check." in self.flat())
            await self.until(pilot, lambda: "rejected:plan:1" not in self.app.screen.card_specs)
        self.assertEqual(self.stored()["revisions"][0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
