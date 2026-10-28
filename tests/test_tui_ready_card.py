"""I3e1: the readiness error card — a red card with the reason and the exact fix command when work cannot start
(release 0.5.2, docs/RELEASE_0.5.2_PLAN.md run i3e1).

One acceptance criterion per test, and at most two whole-app tests for the original criteria: A1+A2+A3 drive the
real shell once at 120x40 (`ReadyCardTests`), A1's 80x24 visibility and A4 drive it once more at 80x24
(`ReadyCardSmallTests`); A5, the key rule and both start kinds are unit level, with a stand-in app and no pilot
(`ReadySourceTests`). The three lifecycle repairs the acceptance and code reviews demanded each add one focused
whole-app regression: a blocked *goal* start keeping its card across a failing recheck, and a readiness card whose
source stopped returning it staying gone when the failing set comes back (A4; `ReadyGoalStartRepairTests`), and a
*passing* recheck ending the readiness block itself so the blocked milestone-start note goes and neither a later
failing background check nor a fresh blocked start resurrects the removed card (`ReadyMilestoneStartRepairTests`).

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- The failing checks are the app's own last readiness slice (`app.checks`, set by `got_checks`), never the
  Outcome's own `checks`. A recheck that still fails delivers the same items, hence the same key, hence one card;
  a recheck that passes ends the readiness block itself (`got_checks` clears the refused submission's marker and a
  milestone start's blocked note `Not started: …`), so `ready_blocked` stops reporting the block and the card's
  source — which needs a blocked start *and* a failing check — returns nothing even before a later failing slice.

- A start counts as blocked when the goal form or the plan screen kept the refused submission (`app.goal_block` /
  `app.plan_block` — the planner-start entry points the brief names as «the goal and the plan start») or when the
  run pane shows a blocked-start note (`blocked_note`: the line `preview_milestone`/`begin_run` write). A failed or
  lost operation's note (`Not done: …`, `Watch interrupted: …`) is not a blocked start and grows no card.

- The card's `{task}` (the `card.error_title` id, the only title id this run's write-set allows) is the project
  name, exactly as the header names it. The text is the failing checks' own lines with the plain screen's `— [i] …`
  hint dropped (`FIX_KEY`), the projection the plan screen's `block_lines()` already uses, at most six of them.

- `fix` is read out of the failing origin item's own `detail` (setup.readiness carries «… Add it yourself:
  git remote add origin https://github.com/OWNER/REPO.git (or git remote set-url origin ...).»), so the card shows
  the bare command on a line of its own, never the prose around it. The fixture planning skips the origin item
  (`planning.FIXTURE_SKIPS`, unchanged), so the whole-app tests inject the *real* readiness slice at the
  controller/UI boundary (both tests remove the fixture's origin remote first, so the item really fails) instead of
  changing that rule.

- «details» opens the readiness detail: the existing `SettingsScreen`, whose «Readiness» pane lists every check
  with its own line and its `detail` (the fix command) — the only readiness detail the main screen can reach.

- A1's «on its own line» is read on the card's own text (`CardSpec.text` / the card's own `Static`): the command is
  55 characters and the 120x40 chat pane is about 50, so the *drawn* row wraps it there. The criterion's «visible at
  80x24» is the drawn own line, and that is what the 80x24 half checks (the narrow chat pane is full width, so the
  command stands on one row).

- The dispatch fix this run had to make: a card button's line goes through `slash.parse` (`on_card_chosen`), and
  `/retry`/`/details` are deliberately *not* in `slash.COMMANDS` — so the frozen dispatcher dropped them before
  `run_command`/`CARD_ROUTES` were ever reached. `on_card_chosen` now dispatches a name `slash` does not know when
  `COMMAND_ACTIONS` wires it, and keeps ignoring every other name (a typed `/retry` is still not a command).

- A `ready` key that has been shown is seen for good (A4, the acceptance review's repair): `ready_source` is
  stateless — it never edits `cards_seen` — so a recheck that still fails keeps the very same key, hence one card,
  while a key whose card `render_card_sources` took off (the failing set changed and came back, or a passed recheck
  ended the block) is never shown again, exactly like every other card kind. A *different* failing set is a card of
  its own, and this kind has no decline and no close of its own. A1+A2+A3's whole-app test proves the card shows
  and a still-failing recheck keeps it, and `ReadyGoalStartRepairTests` covers the goal-start block and the
  removed-key suppression.
"""

import re
import unittest
from unittest.mock import patch

import tui_support  # noqa: F401  (the offline wheelhouse joins sys.path first)
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

from terminal_planner import setup
from terminal_planner.tui import strings

MISSING_REASON = "Rich and Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed"
try:
    from textual.widgets import Button, Static
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import cards
    from terminal_planner.tui.controller import Controller, Outcome, checks_of
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    Button = Static = ui = cards = Controller = Outcome = checks_of = None

from test_tui import check
from test_tui_milestones import MilestoneShell

HAVE = HAVE_TEXTUAL and ui is not None and cards is not None

# A1's own literal: the exact command the no-origin readiness item carries (setup.py).
FIX = "git remote add origin https://github.com/OWNER/REPO.git"
PROJECT = "project with spaces"


class Slices:
    """The readiness slice the injected `Controller.check` answers: the *real* items of the fixture project (its
    origin remote removed by the shell), swapped for the passing one when the test's recheck is to fix the origin
    check. The injected slice is what the fixture planning cannot produce: `planning.FIXTURE_SKIPS` drops the origin
    item (the brief's own example, not changed here)."""

    def __init__(self, checks):
        self.checks = checks


def injected_check(slices):
    """A `Controller.check` (the readiness slice the UI asks for) answering `slices.checks` — delivered the way a
    real slice delivers, through the app's own hand-over, so `got_checks` runs where it always runs."""
    def check(controller, done):
        done(slices.checks, None)
        return True
    return check


def blocked_start(checks):
    """A `Controller.preview_start` whose readiness gate fails: the `blocked` Outcome carrying `checks`, exactly the
    verdict the real gate answers (the milestone start of the run pane)."""
    def preview(controller, milestone, done):
        done(Outcome("blocked", checks=checks), None)
        return True
    return preview


def unsent_start(checks):
    """A `Controller.start_planning` whose readiness gate fails: the `unsent` Outcome carrying `checks` — the verdict
    the real gate answers for a goal submission, the one `ZplanApp.start_goal`'s own callback reads (the goal
    start the repair must keep blocked)."""
    def start(controller, goal, done, draft=None, card=False):
        done(Outcome("unsent", checks=checks), None)
        return True
    return start


def _app(checks=(), run_note="", goal_block=(), plan_block=()):
    """The app side `ready_source` reads: only `checks`, the blocked note and the two refused-submission blocks."""
    class App:
        snapshot = type("Snap", (), {"project": PROJECT})()
        controller = type("Ctl", (), {"name": PROJECT})()
    app = App()
    app.checks, app.run_note, app.goal_block, app.plan_block = checks, run_note, goal_block, plan_block
    return app


class _Screen:
    """The screen side `ready_source` reads: the app double and the slot's own key bookkeeping (`card_specs` /
    `cards_seen`), so the source's own lifecycle rule is exercised too."""

    def __init__(self, app, specs=()):
        self.app = app
        self.card_specs = {key: object() for key in specs}
        self.cards_seen = set(specs)


@unittest.skipUnless(HAVE, MISSING_REASON)
class ReadySourceTests(unittest.TestCase):
    """A5 and the card's own invariants at unit level (`ready_source` on a stand-in app; no pilot, no project): the
    reason of a failing check other than origin carries no fix line, the key follows the failing set, and both start
    kinds (the refused submission of the goal/plan and the run pane's blocked note) grow the card — a failed
    operation's own note does not."""

    def origin(self):
        return check("origin", False, line="No GitHub origin — [i] instructions",
                     detail="Zeroshot names the project by its origin; zplan pushes nowhere. Add it yourself: %s "
                            "(or git remote set-url origin ...)." % FIX, key="i")

    def test_a5_a_failing_check_other_than_origin_shows_its_reason_without_a_fix_line(self):
        """A5: the failing line is the card's text and no fix is added for a check that is not the origin one
        (its own `detail` carries no command either)."""
        clean = check("clean", False, line="There are uncommitted changes — [d] view",
                      detail="Commit or remove them yourself (git status); zplan commits and hides nothing.",
                      key="d")
        spec, = ui.ready_source(_Screen(_app(checks=checks_of([clean]), run_note="Not started: fix what is "
                                                                                  "marked below first.")))
        self.assertEqual(spec.text.splitlines(), ["There are uncommitted changes — /diff view"])  # K1d: the letter is its step
        self.assertNotIn("git remote", spec.text)
        self.assertEqual(spec.key, "ready:clean")
        self.assertTrue(spec.alarm)  # the red style

    def test_the_key_follows_the_failing_set_and_the_origin_fix_comes_from_the_item_detail(self):
        """The card contract: `ready:<failing ids joined by +>` — the same failures keep one key (one card), another
        set is another key; the `fix` is the command read out of the origin item's own `detail`, on its own line,
        exactly as the acceptance criterion names it."""
        both = checks_of([self.origin(), check("clean", False, line="There are uncommitted changes — [d] view")])
        spec, = ui.ready_source(_Screen(_app(checks=both, goal_block=both)))
        self.assertEqual(spec.key, "ready:origin+clean")
        self.assertEqual(spec.text.splitlines()[-1], FIX)
        self.assertIn("No GitHub origin", spec.text)
        spec2, = ui.ready_source(_Screen(_app(checks=checks_of([self.origin()]),
                                                run_note="Not started: fix what is marked below first.")))
        self.assertEqual(spec2.key, "ready:origin")

    def test_the_source_is_stateless_about_a_shown_key(self):
        """A4's source half (the acceptance review's repair): `ready_source` never edits `cards_seen` — a block that
        ended returns nothing and leaves a shown key suppressed, and the same failing set returns the same key's spec
        again. `render_card_sources` is what keeps the removed key from being mounted a second time (the whole-app
        A4 regression in `ReadyGoalStartRepairTests`)."""
        failing = checks_of([self.origin()])
        screen = _Screen(_app(checks=()), specs=("ready:origin",))
        self.assertEqual(ui.ready_source(screen), ())            # the block is gone: nothing to show...
        self.assertEqual(screen.cards_seen, {"ready:origin"})    # ...and the seen key is left alone
        screen.app.checks = failing
        screen.app.run_note = "Not started: fix what is marked below first."
        spec, = ui.ready_source(screen)
        self.assertEqual(spec.key, "ready:origin")

    def test_the_card_needs_both_a_blocked_start_and_a_failing_check(self):
        """The source's own invariant: failing checks alone grow no card (nothing is blocked), a blocked note alone
        grows none either (no failing check — what a passed recheck leaves), and a failed operation's note is not a
        blocked start. All three start kinds show it: the run pane's blocked note, `goal_block`, `plan_block`."""
        failing = checks_of([self.origin()])
        self.assertEqual(ui.ready_source(_Screen(_app(checks=failing))), ())
        self.assertEqual(ui.ready_source(_Screen(_app(checks=(), run_note="Not started: x"))), ())
        self.assertEqual(ui.ready_source(_Screen(_app(checks=failing, run_note="Not done: interrupted"))), ())
        for kind in ("run_note", "goal_block", "plan_block"):
            with self.subTest(kind):
                app = _app(checks=failing)
                setattr(app, kind, "Not started: fix what is marked below first." if kind == "run_note"
                        else failing)
                spec, = ui.ready_source(_Screen(app))
                self.assertEqual(spec.key, "ready:origin")
                self.assertEqual(spec.buttons, ((strings.text("card.error_retry"), "/retry"),
                                                (strings.text("card.error_details"), "/details")))


@unittest.skipUnless(HAVE, MISSING_REASON)
class ReadyShell(MilestoneShell):
    """The shell over an approved fixture plan whose `origin` remote the test removes first: the readiness item that
    then really fails is the real `setup.readiness` one, carrying the real fix command in its `detail`."""

    def setUp(self):
        super().setUp()
        self.git("remote", "remove", "origin")
        self.items = setup.readiness(self.project, tools=False)
        self.assertEqual([i["id"] for i in self.items if not i["ok"]], ["origin"])

    def origin_line(self):
        """The real origin item's line as the card draws it: without the plain screen's `— [i] …` key hint."""
        line = next(i["line"] for i in self.items if i["id"] == "origin")
        return re.sub(r"\s+—\s+\[i\].*$", "", line)

    def slices(self, fixed=False, clean=False):
        """The real items as a slice, the origin item still failing (or, for the recheck that fixes it, ok); with
        `clean` one more failing check joins them, so the failing *set* changes (the returning-set lifecycle)."""
        items = [dict(i, ok=True) if fixed and i["id"] == "origin" else dict(i) for i in self.items]
        if clean:
            items.append(check("clean", False, line="There are uncommitted changes — [d] view",
                               detail="Commit or remove them yourself (git status); zplan commits nothing.",
                               key="d"))
        return checks_of(items)

    def main(self):
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def card(self):
        """The card the conversation holds, or None."""
        return next((widget for widget in self.main().card_widgets.values()
                     if isinstance(widget, cards.Card)), None)

    def cards_shown(self):
        return [widget for widget in self.main().card_widgets.values() if isinstance(widget, cards.Card)]

    def drawn(self):
        """The screen's rows with the pane borders and the card's padding stripped, so a card's own text line reads
        as exactly its own text (A1's «on its own line» at 80x24). Only a narrow screen's row is the card alone;
        at 120x40 the row carries the canvas beside it, so A1 reads the card's own widget there (`card_text`)."""
        return [line.strip().strip("│ ").strip() for line in screen_lines(self.app)]

    def card_text(self, card):
        """The card's own text, line for line, from its widget (never the row it shares with the canvas): the open
        card's text `Static` is built with `markup=False`, so its content is the caller's own string."""
        return str(card.query_one(".card-text", Static).content)

    def counting(self):
        """A `ZplanApp.request_check` spy: records each call and still runs the real one (the injected slice answers
        it), so a button's own recheck is counted on the real path."""
        real = ui.ZplanApp.request_check
        self.retries = []

        def spy(app, *args, **kwargs):
            self.retries.append(1)
            return real(app, *args, **kwargs)
        return spy

    async def card_shown(self, pilot, timeout=8.0):
        await self.until(pilot, lambda: self.card() is not None, timeout)
        await pilot.pause(0.3)
        return self.card()

    async def press(self, pilot, command):
        """Press the card button carrying the slash command `command`."""
        button = next(widget for widget in self.card().query(Button) if widget.command == command)
        await pilot.click(button)
        await pilot.pause(0.3)

    async def blocked(self, pilot):
        """The real blocked milestone start: [g] on the ready M1 answers the injected readiness refusal."""
        await self.panel(pilot)
        await self.command(pilot, "/run")
        return await self.card_shown(pilot)


@unittest.skipUnless(HAVE, MISSING_REASON)
class ReadyCardTests(ReadyShell):
    async def test_a1_a3_a2_the_card_shows_then_retry_keeps_or_drops_it(self):
        """A1 (120x40): a red card shows the origin reason and, on its own line, exactly the fix command; A3: a
        recheck that still fails keeps the card (same key, one card — never a duplicate); A2: «new attempt» calls
        `request_check` once and, with the recheck passing, the card is gone after the render."""
        slices = Slices(self.slices())
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            with patch.object(ui.ZplanApp, "request_check", self.counting()), \
                    patch.object(Controller, "check", injected_check(slices)), \
                    patch.object(Controller, "preview_start", blocked_start(self.slices())):
                card = await self.blocked(pilot)
                # A1: the card is red, names the project, carries the origin reason and the exact command on a
                # line of its own (the card's own text — the 120x40 chat pane is too narrow not to wrap the
                # 55-character command, so the *drawn* own line is what the 80x24 half below checks).
                self.assertTrue(card.spec.alarm)
                self.assertIn(strings.text("card.error_title", task=PROJECT), screen_text(self.app))
                self.assertEqual(card.spec.text.splitlines(), [self.origin_line(), FIX])
                self.assertEqual(self.card_text(card).splitlines(), [self.origin_line(), FIX])
                flat = " ".join(screen_text(self.app).split())
                self.assertIn("git remote add origin", flat)  # the command is on screen; the 120x40 chat pane
                self.assertIn("https://github.com/OWNER/REPO.git", flat)  # is too narrow not to wrap its words
                self.assertIn(strings.text("card.error_retry"), screen_text(self.app))
                # A3: the recheck still fails (the injected slice is unchanged) -> the card stays, one card
                key = card.spec.key
                self.assertEqual(key, "ready:origin")
                before = len(self.retries)
                await self.press(pilot, "/retry")
                self.assertEqual(len(self.retries), before + 1)  # A2: one press, one request_check
                await self.until(pilot, lambda: self.app.checking is False)
                await pilot.pause(0.3)
                self.assertEqual([card.spec.key for card in self.cards_shown()], [key])  # same key, one card
                # A2: the recheck passes -> the source drops the card after the render
                slices.checks = self.slices(fixed=True)
                await self.press(pilot, "/retry")
                self.assertEqual(len(self.retries), before + 2)
                await self.until(pilot, lambda: self.card() is None)
                await pilot.pause(0.3)
                self.assertIsNone(self.card())
                # A4: the card the passed recheck took off stays gone — the same failing set blocking a start again
                # does not resurrect the removed key (only a *different* failing set is a new card).
                slices.checks = self.slices()
                await self.panel(pilot)
                await self.command(pilot, "/run")
                await pilot.pause(0.3)
                self.assertIsNone(self.card())


@unittest.skipUnless(HAVE, MISSING_REASON)
class ReadyCardSmallTests(ReadyShell):
    async def test_a1_at_80x24_and_a4_details_opens_the_readiness_detail(self):
        """A1 (80x24): the same red card with the origin reason and the fix command is visible in the narrow chat
        pane; A4: «details» opens the readiness detail — `SettingsScreen`, whose «Readiness» pane carries the
        failing item's own line and its `detail` (the fix command)."""
        slices = Slices(self.slices())
        self.approve(running=False)
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            with patch.object(Controller, "check", injected_check(slices)), \
                    patch.object(Controller, "preview_start", blocked_start(self.slices())):
                await self.command(pilot, "/run")  # typed in the chat input: the narrow screen keeps the chat tab
                await self.card_shown(pilot)
                self.assertIn(self.origin_line(), self.drawn())
                self.assertIn(FIX, self.drawn())  # the whole command on one drawn row at 80x24
                # A4
                await self.press(pilot, "/details")
                self.assertEqual(type(self.app.screen).__name__, "SettingsScreen")
                checks = self.app.screen.query_one("#checks", Static).content.plain
                self.assertIn(self.origin_line(), checks)
                self.assertIn(FIX, checks)


@unittest.skipUnless(HAVE, MISSING_REASON)
class ReadyGoalStartRepairTests(ReadyShell):
    async def test_the_blocked_goal_start_keeps_its_card_until_readiness_passes(self):
        """Repair regression (acceptance + code finding 1, A3 for goal starts): `ZplanApp.start_goal` — the *actual
        goal callback*, with the card's own key — answering the readiness gate's `unsent` sets the blocked marker
        (`goal_block`) and asks for the automatic recheck. `got_checks` used to clear that marker on *any* successful
        slice, so the card vanished while the origin check still failed; the marker must survive a recheck that
        still fails (one card, the same key) and clear only once readiness passes."""
        slices = Slices(self.slices())
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            with patch.object(Controller, "check", injected_check(slices)), \
                    patch.object(Controller, "start_planning", unsent_start(self.slices())):
                self.app.start_goal("цель", card_key="draft:k")  # the real callback, the goal-card refusal path
                # The automatic recheck (started on the refusal) still fails with the very same set: wait for its
                # fresh failing slice, then the marker must still be there (the defect cleared it here).
                await self.until(pilot, lambda: self.app.checks is not None
                                 and any(not c.ok for c in self.app.checks))
                await self.until(pilot, lambda: self.app.checking is False)
                await pilot.pause(0.3)
                self.assertTrue(self.app.goal_block)  # the marker survived the failing recheck
                card = await self.card_shown(pilot)
                self.assertEqual(card.spec.key, "ready:origin")
                self.assertEqual([shown.spec.key for shown in self.cards_shown()], ["ready:origin"])
                # A recheck that passes clears the block and the card leaves.
                slices.checks = self.slices(fixed=True)
                await self.press(pilot, "/retry")
                await self.until(pilot, lambda: self.card() is None)
                self.assertFalse(self.app.goal_block)

    async def test_a_removed_ready_card_never_comes_back(self):
        """A4 regression (the acceptance review's repair): a readiness card its source stopped returning is gone
        from the history and never comes back. Through the real `render_card_sources`: the blocked start shows
        `ready:origin`; the failing set changes to `origin+clean`, so the origin card leaves and the new key's card
        shows; the set returns to `origin`, and `ready:origin` is *not* shown again — the removed key stays in
        `cards_seen` like any other card's, so the state returning does not resurrect it. A passed recheck then
        drops the block and the remaining card."""
        slices = Slices(self.slices())
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            with patch.object(Controller, "check", injected_check(slices)), \
                    patch.object(Controller, "preview_start", blocked_start(self.slices())):
                await self.blocked(pilot)  # the run pane's blocked start, the run note retained
                self.assertEqual([shown.spec.key for shown in self.cards_shown()], ["ready:origin"])
                self.assertIn("ready:origin", self.main().cards_seen)
                # The failing set changes: the source's key changes and the card follows it.
                slices.checks = self.slices(clean=True)
                await self.press(pilot, "/retry")
                await self.until(pilot, lambda: [shown.spec.key for shown in self.cards_shown()]
                                 == ["ready:origin+clean"])
                # The earlier set returns: the removed key is not resurrected (A4), so no card shows.
                slices.checks = self.slices()
                await self.press(pilot, "/retry")
                await pilot.pause(0.3)
                self.assertEqual(self.cards_shown(), [])
                self.assertIn("ready:origin", self.main().cards_seen)   # the key stays seen for good
                # A recheck that passes ends the block; no card is left either way.
                slices.checks = self.slices(fixed=True)
                self.app.request_check()
                await self.until(pilot, lambda: self.app.checking is False)
                await pilot.pause(0.3)
                self.assertIsNone(self.card())



@unittest.skipUnless(HAVE, MISSING_REASON)
class ReadyMilestoneStartRepairTests(ReadyShell):
    async def test_a_passing_recheck_clears_the_blocked_milestone_start(self):
        """Repair regression (acceptance + code finding 3, "When the recheck passes, the blocked state is gone"):
        a *milestone* start refused by the readiness keeps its blocked note in the run pane (`preview_milestone`
        writes «Not started: …»), and that note is what `ready_blocked` reads. A passing recheck used to rewrite
        only the check slice, so the note stayed, `ready_blocked` stayed true and the screen stayed in `error` —
        and a later failing *background* check (no new start) resurrected `ready:origin` out of nothing. The
        passing recheck must end the readiness block itself: the blocked-start note goes with it, the screen
        leaves `error`, and the removed card stays gone (A4) — neither a later failing background check nor a fresh
        blocked start with the same failing set resurrects the key. A failed operation's own note (`Not done: …`)
        is not a readiness block and stays, still shown as the screen's error — that is what the closing lines
        pin."""
        slices = Slices(self.slices())
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            with patch.object(Controller, "check", injected_check(slices)), \
                    patch.object(Controller, "preview_start", blocked_start(self.slices())):
                await self.blocked(pilot)  # the run pane's blocked start: the note the card is keyed off
                self.assertEqual([shown.spec.key for shown in self.cards_shown()], ["ready:origin"])
                # The recheck passes: the block is gone — the card leaves *and* the blocked state clears.
                slices.checks = self.slices(fixed=True)
                await self.press(pilot, "/retry")
                await self.until(pilot, lambda: self.card() is None)
                await pilot.pause(0.3)
                self.assertFalse(ui.ready_blocked(self.app))
                self.assertNotEqual(ui.screen_slash_state(self.app), "error")
                # A later failing background check (no new blocked start) must not resurrect the card.
                slices.checks = self.slices()
                self.app.request_check()
                await self.until(pilot, lambda: self.app.checking is False)
                await pilot.pause(0.3)
                self.assertIsNone(self.card())
                self.assertFalse(ui.ready_blocked(self.app))
                # A4: a fresh blocked start with the same failing set does not resurrect the removed key — the
                # block is back, the card is not (the card is shown once per key, like every other card kind).
                await self.panel(pilot)
                await self.command(pilot, "/run")
                await pilot.pause(0.3)
                self.assertIsNone(self.card())
                self.assertTrue(ui.ready_blocked(self.app))
                # A failing recheck does not touch an unrelated failed operation's note (`Not done: …`): it is
                # not the readiness block, and the screen still reports it as its error.
                self.app.run_note = "Not done: interrupted"
                slices.checks = self.slices(fixed=True)
                self.app.request_check()
                await self.until(pilot, lambda: self.app.checking is False)
                await pilot.pause(0.3)
                self.assertEqual(self.app.run_note, "Not done: interrupted")
                self.assertEqual(ui.screen_slash_state(self.app), "error")


if __name__ == "__main__":
    unittest.main()
