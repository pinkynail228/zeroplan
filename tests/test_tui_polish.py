"""R-1..R-5 of dogfood-polish-04: the 0.4 key bar, goal hint, result modal and readiness closing lines.

The bar oracle needs only the standard library (plus the catalog); every other path here goes through production
entry points — the delivery/planning services over the fixture store, the plain lines they print, and the app's own
keys and screens under a Textual pilot — so a test that guards new behavior fails on its own assertion when that
behavior is missing, not on a helper that does not exist yet.

Interpretations (the worker's summary never reaches the reviewers, so the decisions live with the tests):

* R-1 above the floor M is read as *priority*: the lower-priority keys give up their label (down to a shortest
  nonempty one) and are dropped, in reverse catalog order, before a `primary`/`reserve` action is shortened. This is
  "drop or shorten lower-priority keys rather than show a bare key" (dogfood-polish item 1) and it keeps the
  documented `catalog.bar` reserve contract and the reserved draft label (`[c] черновик цели`), whose U-3 controls
  A-1 keeps green; the alternative "shorten every action at once" reading would break them. Below M the previous
  fallback (key-only included) is untouched.
* R-1's `W` is the *bar widget's own* usable width: the inset bars are rendered from the widget's content region
  (and re-rendered on resize), not from the screen width or a constant, so a bar narrower than the screen
  (`bootstrap`, `note`, the journal `TextScreen`) satisfies the oracle while a shell-width one would overflow it.
* R-2 "the plan screen's [i]" is reachable from *every* PlanView kind, so the goal line (and an [i]) was added to
  the `unsent`, `stale`, `unknown` and `observing` views too, not only `proposal`/`failed`; the hint names the key
  that view really offers ([i] requirements on a proposal, [i] details elsewhere). Both UIs print that same line:
  the plain plan screen's [i] shows the delivery service's `plan_info()` too, not the requirements alone.
* R-3's height counts the *physical terminal rows* the body draws: a stored journal entry may carry embedded
  newlines (one list element, several drawn rows) and wide CJK glyphs (one element, two cells), so the element count
  was short wherever an entry was multiline or wide. The measured rows are the rendered body's own wrapped content
  height, and the box is `min(rows + title + keys + padding + border, body room)`.
* R-4 interactivity is per request origin: the timer, a navigation, the blocked-start re-check and the startup are
  background (silent), while the owner's own [g]/[l]/[u] are interactive (one closing line). "Background requests
  neither erase an interactive batch nor produce closing lines" is read as covering every request that is not the
  owner's own, whatever its result: a background request during a running check gets its own coalesced follow-up
  (the base dropped it), a background error reports nothing (the base's `Проверка не выполнена` line for it is
  gone — the interactive error line is unaffected), and a background request never turns an interactive batch
  silent. A request that lands while the follow-up is merely *queued* — posted but not yet entered on the worker —
  joins that queued batch instead of opening a second one, so a batch stays one batch and closes with one line.
* R-4 closing lines belong to the journal (`say`); an action's own outcome goes to the screen it *started* from —
  the currently displayed goal or plan screen only when the action did not start on one — so the two cannot
  overwrite each other: a login cancelled or answered with a nonzero code, and a setup that failed under an
  overlay, all stay on their originating form. A remedy key is named only when the Settings screen offers it
  (`settings_keys()`); otherwise the line carries a *key-free* remedy from the catalog (`catalog.remedy_free`, keyed
  by the Check's own id), never the Check's `detail` — the production readiness items put `[u]`/`[l]` in that text
  (terminal_planner/setup.py), so a `detail`-based fallback would still name a key the screen does not offer.
* R-4 one id can carry two causes whose fixes differ, and the item's own structured key picks the applicable one:
  the auth item is a missing login file ([l] login repairs it) or an unset provider environment key (its key is
  [i]; only an export repairs it, and login cannot). The remedy is therefore keyed by the structured `(id, key)`
  with the plain id as the fallback (`catalog.remedy_free`), which keeps the id — and with it the family
  `readiness.auth` ("no login file or API key variable") and the item's place in `planning.NEEDS` — unchanged.
* R-4 a batch owns its identity until its own callback is applied: `checking` stays True until `got_checks`
  takes `check_batch`, and `start_check` refuses to start the waiting follow-up before that (it re-queues it).
  Setup completion is delivered on the same FIFO hand-over, so setup_done can run first; starting a follow-up
  there used to overwrite the identity the queued slice was still owed, closing that slice with the follow-up's
  batch and the follow-up with none.
* R-4 "an enabled next key (or remedy key)" is what the *live guards* would admit now, not what the session merely
  has a callable for: while setup runs, `start_setup` refuses [u] ("установка уже идёт") and `start_login` refuses
  [l] ("войти можно после неё"), so neither is named in a closing line then — neither among the all-OK line's next
  keys nor as the failing line's remedy key, for which the catalog's key-free remedy stands in
  (`settings_keys()`). The guard is live and not a one-off: setup's own batch, delivered once the setup ended,
  names the keys again.
* R-4 "Closing the app discards pending UI work" (C-3b) also covers readiness work that a timer would otherwise
  ask for *while a protected setup still finishes*: once the quit began (`controller.begin_closing`, read as
  `Controller.quit_begun()`), `request_check` admits no new request and `start_pending` drops the one waiting
  batch, so a timer tick cannot recreate `pending_check` or post a slice behind the exit; the protected setup
  itself still runs to completion (its own post-install check is the slice the shutdown waits for).
* A-5's walkthrough: a run that finishes while home is on top opens its end-of-run modal over it
  (`MainScreen.show_end`, identical on the base), so the home line is then not rendered at all. The harness reads
  such a modal as the allowed order — it captures it as a frame and closes it with its own [esc] закрыть before
  reading the home line (`expect_home`) instead of failing on a screen it cannot see.

A-5 evidence (base `74f1a3b`: the seven production files `terminal_planner/{catalog,cli,delivery,planning}.py`,
`terminal_planner/tui/{app,controller}.py` and `terminal_planner/tui/zplan.tcss` restored from HEAD into a copy of
this candidate, the tests as they now stand; run from `tests/` with
`TMPDIR=<scratch> PYTHONPATH=..:. python3 -m unittest test_tui_polish`): the module reports 59 subtest failures in
30 of its 33 tests and no error — every new-behavior test fails at its own assertion below, and the compatibility
controls
(last bullet) pass. The recorded assertion is the first one that fails for the test:

* `BarOracleTests.test_a1_a_mandatory_label_is_shortened_only_after_optionals_go` — at 118 the base shortens a
  mandatory action before dropping an optional one: `assertIsNone(labels.get("s"))` reports `'' is not None`.
* `BarOracleTests.test_a1_boundaries_around_the_floor_at_117_118_119` — the base bar at 118 is
  `[p] план  [g] проверить  [x] остановить  [w] наблюдать  [o] открыть  [?]  [ctrl+q] выход`:
  `assertTrue(all(label for _, label in items), ...)` reports `False is not true`.
* `BarOracleTests.test_a1_seeded_generator_of_two_hundred_cases` — `tui_input` at 27 cells holds a bare
  `[esc] отменить`: `assertTrue(all(label for _, label in items), ...)` reports `False is not true`.
* `PilotBarTests.test_a1_home_input_plan_and_a_modal_at_both_sizes` — the live 120x40 home bar ends in a bare
  `[?]`: `all(label for _, label in items)` reports `False is not true`.
* `WidgetBarTests.test_a1_the_inset_bars_fit_their_own_widget` — the 43x24 bootstrap bar emits 38 cells into a
  37-cell widget: `assertLessEqual(cells(bar), width)` reports `38 not less than or equal to 37`.
* `GoalTextTests.test_a2_empty_whitespace_and_the_100_and_200_limits` — a 101/201-character stored goal on the
  home/plan line: `assertEqual("[i]" in line, ...)` reports `False != True`.
* `GoalTextTests.test_a2_a_long_unbroken_word_multiline_unicode_and_a_literal_ellipsis` — same assertion for the
  long unbroken word, the multiline Unicode text and the ellipsis-led goals.
* `GoalTextTests.test_a2_every_view_kind_exposes_the_goal_through_its_details` — the unsent view offers no [i]:
  `assertIn("details", view.actions)` reports `'details' not found in ('start',)`.
* `GoalScreenTests.test_a2_home_and_plan_details_show_the_full_goal` — the plan [i] of a proposal shows the
  requirements without the stored goal: the goal is absent from the lines [i] put under the plan.
* `GoalScreenTests.test_a2_the_plain_home_line_and_the_tui_pane_are_the_same_text` — `assertIn("[i] подробнее",
  pane[0])` reports the cut line without a hint.
* `GoalScreenTests.test_a2_the_plain_and_the_tui_plan_details_are_the_same_text` — the plan [i] is the requirements
  alone in both UIs: the stored goal is absent from the lines [i] shows.
* `EndViewTests.test_a3_the_stored_journal_is_shown_oldest_first` — the modal body has no journal:
  `assertIn("Журнал:", body)` reports `'Журнал:' not found in` the heading/status/state text alone.
* `EndViewTests.test_a3_a_wide_glyph_entry_is_sized_to_the_rows_it_draws` — the wide entry never reaches a body
  that draws no journal: `assertIn(...)` reports it absent from the rendered body.
* `EndViewTests.test_a3_the_modal_is_sized_to_the_rows_it_draws` — the base box is 80% high:
  `assertEqual(box.region.height, min(rows + 4, room))` reports `19 != 7` at 80x24.
* `EndViewTests.test_a3_help_on_the_result_modal_lists_its_journal_key` — the catalog key list of `tui_run` has no
  journal action: `assertIn("подробнее", ...)` reports it missing.
* `EndViewTests.test_a3_a_bound_key_invokes_every_action_the_modal_names` — the unknown state's `check` is named
  with `[g]`, but the base binds that key to resume: `assertIn('check', {'resume'})` reports it absent.
* `ResultModalTests.test_a3_below_the_header_journal_details_and_return` — the modal is not in the body region:
  `assertTrue(screen.has_class("body-region"))` reports `False is not true`.
* `ResultModalTests.test_a3_an_attempt_change_while_details_are_open_cannot_act_on_the_old_token` — the base modal
  binds no [i], so the journal screen never opens and the wait times out.
* `ClosingLineTests.test_a4_recheck_login_and_setup_close_with_one_line_from_their_own_result` — no closing line is
  written for an interactive batch: `assertEqual(len(fresh), 1)` reports `0 != 1`.
* `ClosingLineTests.test_a4_a_failing_remedy_is_only_named_when_its_key_is_enabled` — the base writes no closing
  line for the batch at all: `assertTrue(fresh, ...)` reports `[] is not true` (only `Проверка готовности…`).
* `ClosingLineTests.test_a4_an_environment_key_auth_item_is_not_told_to_run_the_login` — same missing closing
  line on the base: `assertTrue(fresh, ...)` reports `[] is not true` (only `Проверка готовности…`).
* `ClosingLineTests.test_a4_a_closing_line_names_no_action_the_live_guards_refuse` — the base writes no closing
  line for the held batch (the wait for one times out: `не дождались состояния`), so an unavailable [u]/[l] can
  never be caught there; the guard itself is watched in a copy of this candidate with only its two filters removed
  (the `setting_up` term of `settings_keys()` and the two `quit_begun()` returns), where the test then fails on
  `assertNotIn("[l]", line)` (`'! Codex: нет входа — [l] войти'`, subtest `failing=True`) and on
  `assertNotIn("[u]", line)` (`'Готово: всё в порядке. Дальше: [u] установить, … '`, subtest `failing=False`).
* `CheckBatchTests.test_a4_one_line_per_batch_and_one_coalesced_follow_up` — no closing line for the held batch
  (the wait for one times out: `не дождались состояния`).
* `CheckBatchTests.test_a4_a_background_request_during_a_check_gets_its_follow_up` — the base drops the request
  (two readiness slices where three are required; the wait for the follow-up times out).
* `CheckBatchTests.test_a4_the_log_survives_navigation` — the wait for the batch's closing line times out.
* `CheckBatchTests.test_a4_a_request_before_worker_entry_joins_the_queued_batch` — the request during a merely
  queued follow-up yields no closing line for the joined batch: `assertEqual(len(lines), 1, lines)` reports `0 != 1`.
* `CheckBatchTests.test_a4_setup_keeps_the_request_that_arrives_while_it_holds_the_worker` — setup's own line
  survives but the owner's batch is dropped: `assertEqual(len(lines), 2, lines)` reports `0 != 2`.
* `CheckBatchTests.test_a4_a_completed_setup_cannot_overwrite_an_unapplied_batch` — the base writes no closing
  line for any of the three batches: `assertEqual(len(lines), 3, lines)` reports `0 != 3`.
* compatibility controls that pass on the base (the remaining three of the module's 33 tests):
  `BarOracleTests.test_a1_empty_set_and_the_scroll_actions`,
  `CheckBatchTests.test_a4_closing_the_app_discards_the_waiting_batch` and
  `ResultModalTests.test_a3_the_narrow_fallback_keeps_the_old_box`.
"""

import contextlib
import os
import random
import re
import threading
import unicodedata
import unittest
from unittest.mock import patch

from terminal_planner import catalog, delivery, live, planning, setup
from terminal_planner.authority import Authority, Blocked
from terminal_planner.delivery import Delivery
from terminal_planner.engine import FixtureEngine
from terminal_planner.tui import controller as controller_module
from terminal_planner.runs import FixtureDriver, MilestoneRuns
from test_terminal_planner import ROLES
from test_tui import ShellTest, check
from test_tui_live import HAVE_TEXTUAL, LiveShell, bar_items, known_item
from test_tui_milestones import MilestoneShell
from test_tui_planning import Planner, PlanningShell
from tui_support import screen_lines, screen_text

TEXTUAL_REASON = "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed"
JOURNAL_HEAD = catalog.JOURNAL + ":"
JOURNAL_EMPTY = catalog.JOURNAL_EMPTY
NEXT_HEAD = catalog.NEXT
CHECK_DONE = catalog.CHECK_DONE
CHECK_EMPTY = catalog.CHECK_EMPTY
CHECK_ERROR = catalog.CHECK_ERROR
GOAL = planning.goal_line("", 100, "home.details")  # the goal line's prefix, whatever language the service speaks
CLOSING = (CHECK_DONE, CHECK_EMPTY, CHECK_ERROR, "! ")  # the four catalog closing results, as prefixes


def cells(text):
    """The oracle's cell count: a wide or full-width glyph is two, a combining mark nothing (stdlib only)."""
    total = 0
    for char in str(text):
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def mandatory_floor(screen, include, primary, reserve, keep=("help",)):
    """(M, ids): the mandatory offered actions at their shortest nonempty label, joined with the same separator."""
    chosen = [a for a in catalog.ACTIONS.values() if a.screen == screen and (include is None or a.id in include)]
    names = set(primary) | set(reserve) | set(keep)
    mandatory = [a for a in chosen if a.id.split(".", 1)[1] in names]
    return (cells("  ".join("[%s] %s" % (a.key, a.short or a.label) for a in mandatory)),
            {a.id for a in mandatory})


def render_bar(screen, include, width, primary, reserve):
    return catalog.bar(screen, include, width, primary=primary, reserve=reserve, keep=("help",))


@contextlib.contextmanager
def services(root, state, project, fixture_id="test"):
    """The delivery and planning services over a store, exactly as both UIs build them."""
    with Authority(state, project, fixture_id=fixture_id) as authority:
        runs = MilestoneRuns(authority, FixtureDriver(root / "fixture-runs"),
                             worktrees=authority.directory / "worktrees")
        yield Delivery(authority, runs, planning.Planning(authority, runs, lambda *_: FixtureEngine()))


def closing_lines(lines):
    """The catalog closing lines among `lines` (the four results R-4 names)."""
    return [line for line in lines if line.startswith(CLOSING)]


class StoredGoal:
    """A store writer: one record with the goal as written, whatever the authority would accept as a goal."""

    @staticmethod
    def write(state, project, goal, status=None):
        with Authority(state, project, fixture_id="test") as authority:
            authority.begin(goal or "цель", ROLES, "fixture")
            authority.current["goal"] = goal
            if status is not None:
                authority.current.update(status=status)
            authority.save()


class BarOracleTests(unittest.TestCase):
    """A-1: the R-1 rule as an oracle, independent of the production `cells`/shortest helpers."""

    def test_a1_seeded_generator_of_two_hundred_cases(self):
        """A sealed generator of <= 200 cases: complete labelled actions, priority (mandatory kept) and width."""
        rng = random.Random(20261019)
        screens = sorted({a.screen for a in catalog.ACTIONS.values() if a.screen.startswith("tui_")})
        done = 0
        for _ in range(200):
            screen = rng.choice(screens)
            ids = [a.id for a in catalog.ACTIONS.values() if a.screen == screen]
            include = tuple(rng.sample(ids, rng.randint(0, len(ids))))
            names = [i.split(".", 1)[1] for i in ids]
            primary = tuple(rng.sample(names, rng.randint(0, min(3, len(names)))))
            reserve = tuple(rng.sample(names, rng.randint(0, min(2, len(names))))) if screen == "tui_panel" else ()
            floor, mandatory = mandatory_floor(screen, include, primary, reserve)
            width = rng.choice([floor - 1, floor, floor + 1, rng.randint(10, 200)])
            if width < 1:
                continue
            done += 1
            text = render_bar(screen, include, width, primary, reserve)
            items = bar_items(text)
            self.assertTrue(all(known_item(k, v) for k, v in items), (screen, include, width, text))
            if width >= floor:
                self.assertTrue(all(v for _, v in items), (screen, include, width, text))
                shown = {k for k, _ in items}
                self.assertTrue(all(a.key in shown for a in catalog.ACTIONS.values()
                                    if a.id in mandatory), (screen, width, text))
                self.assertLessEqual(cells(text), max(width, cells(render_bar(screen, include, 10, primary,
                                                                               reserve))))
        self.assertGreater(done, 100)

@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class PilotBarTests(LiveShell):
    """A-1 pilot: each bar at its own usable width (widget width - 2), 80x24 and 120x40, both focus modes, a modal."""

    def assert_bar(self, line, width, where, all_labelled):
        items = bar_items(line)
        self.assertTrue(items, (where, line))
        for key, label in items:
            self.assertTrue(known_item(key, label), (where, key, label, line))
        if all_labelled:
            self.assertTrue(all(label for _, label in items), (where, line))
        self.assertLessEqual(cells(line.strip()), width, (where, line))

    def focus(self):
        """The focused widget's id (None: nothing focused) — the focus mode the bar belongs to."""
        return getattr(self.app.focused, "id", None)

    async def test_a1_the_plan_and_modal_bars_fit_at_both_sizes(self):
        """A-1 pilot, shrunk by i2 to the non-main bars: the plan screen's bar and a modal's bar fit the widget's
        usable width (screen width - 2) with every action labelled, at 80x24 and 120x40. The home/panel/input legs
        this test also read named the old *main* key bar, which i2 replaced with the shared `activity.Bar` (checked
        in `tests/test_tui_commands.py`, A3); the focus-toggle behaviour itself stays in
        `tests/test_tui.LayoutTests.test_input_focus_and_tab_toggle`."""
        from terminal_planner.tui import app as ui
        self.approve(running=False)
        for size in ((80, 24), (120, 40)):
            with self.subTest(size=size):
                async with self.shell(self.controller(), size=size, follow=True) as pilot:
                    await self.loaded(pilot)
                    width = self.app.size.width - 2
                    await self.panel(pilot)  # D4: the pane owns the keys that reach the plan screen
                    await self.command(pilot, "/view")
                    await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "PlanScreen")
                    self.assert_bar(screen_lines(self.app)[-1], width, "plan", all_labelled=True)
                    await self.press_button(pilot, "revise")  # K1c2: the note form is the modal over the plan
                    await self.until(pilot, lambda: isinstance(self.app.screen, ui.NoteScreen))
                    self.assert_bar(screen_lines(self.app)[-1], width, "modal", all_labelled=True)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class WidgetBarTests(ShellTest):
    """A-1/R-1: a bar inside an inset modal is cut to its own widget's usable width (`content_region.width`), not
    to the screen width minus a constant or to a fixed estimate. The app runs its production path here: a
    profile-enabled session on a project whose process profile is not decided pushes `BootstrapScreen` on the
    first snapshot (as `test_process.BootstrapTuiTests` does); the note and text modals are pushed as their own
    keys open them. 43x24 is the reviewed case: the screen-wide estimate overflows the widget there, while the
    widget's own width fits."""

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        # i6: this class points the config root at its own tree, so the `ru` pin `tests/tui_support.py` sets for the
        # whole process does not reach it. Storing a language keeps the first-run chooser from being pushed before
        # `BootstrapScreen`, which is the modal this class asserts.
        ui = self.root / "config" / "planning-kit" / "ui.json"
        ui.parent.mkdir(parents=True, exist_ok=True)
        ui.write_text('{"language": "ru"}\n', encoding="utf-8")

    def profile_controller(self):
        return self.controller(profile=True)

    def assert_fits(self, widget, where):
        """The bar text does not overflow the widget's own usable width (R-1)."""
        text = str(widget.content)
        self.assertTrue(text, where)
        self.assertLessEqual(cells(text), widget.content_region.width, (where, text))

    async def test_a1_the_inset_bars_fit_their_own_widget(self):
        from terminal_planner.tui import app as ui
        for size in ((80, 24), (120, 40), (43, 24)):
            with self.subTest(size=size):
                async with self.shell(self.profile_controller(), size=size) as pilot:
                    await self.until(pilot, lambda: isinstance(self.app.screen, ui.BootstrapScreen))
                    await pilot.pause()
                    self.assert_fits(self.app.screen.query_one("#bootstrap-keys"), ("bootstrap", size))
                    note = ui.NoteScreen()
                    self.app.push_screen(note)
                    await self.until(pilot, lambda: self.app.screen is note)
                    await pilot.pause()
                    self.assert_fits(note.query_one("#note-keys"), ("note", size))
                    text = ui.TextScreen("Title", ["line"])
                    self.app.push_screen(text)
                    await self.until(pilot, lambda: self.app.screen is text)
                    await pilot.pause()
                    self.assert_fits(text.query_one("#text-keys"), ("text", size))


class GoalTextTests(PlanningShell):
    """A-2 plain lines: the home line, the plan screen's goal line and the plan [i] text, from the services."""

    home_line = staticmethod(lambda service: service.home().lines[0])

    @staticmethod
    def plan_goal_line(service):
        return next(line for line in service.planning.view().lines if line.startswith(GOAL.rstrip()))

    def line(self, goal, limit):
        """The stored goal's line on the screen with that limit, through the service that prints it."""
        StoredGoal.write(self.state, self.project, goal)
        with services(self.root, self.state, self.project) as service:
            return self.home_line(service) if limit == 100 else self.plan_goal_line(service)

    def raw_lines(self, goal):
        """(home line, plan line) for the raw goal `goal`, never stored: the store holds a valid goal and the value
        is handed to the same services in memory. An empty or whitespace-only goal is refused by the authority
        (`nonempty`), so no store can carry one — this is the raw value a screen would be handed."""
        StoredGoal.write(self.state, self.project, "цель")
        with services(self.root, self.state, self.project) as service:
            service.authority.current["goal"] = goal
            return self.home_line(service), self.plan_goal_line(service)

    def test_a2_empty_whitespace_and_the_100_and_200_limits(self):
        """The hint appears iff the normalized stored goal is longer than the screen's limit. The stored goals
        (99/100/101 on home, 199/200/201 on the plan screen) go through the services that print the lines. Empty
        and whitespace-only goals are refused by the authority (`nonempty`, so no store can hold one), so they go
        through `planning.goal_line`, the shared render both UIs call, with the raw value a screen would be
        handed; that half is a compatibility control (the base never hints), the stored half is not."""
        for goal in ("ц" * 99, "ц" * 100, "ц" * 101):
            with self.subTest(goal=repr(goal[:8]), limit=100):
                line = self.line(goal, 100)
                self.assertEqual(line.split(" — [")[0], GOAL + planning.one_line(goal, 100), line)
                self.assertEqual("[i]" in line, len(" ".join(goal.split())) > 100, line)
        for goal in ("ц" * 199, "ц" * 200, "ц" * 201):
            with self.subTest(goal=repr(goal[:8]), limit=200):
                line = self.line(goal, 200)
                self.assertEqual(line.split(" — [")[0], GOAL + planning.one_line(goal, 200), line)
                self.assertEqual("[i]" in line, len(" ".join(goal.split())) > 200, line)
                self.assertTrue(line.endswith(catalog.text("plan.details")) if "[i]" in line else True, line)
        for goal in ("", "   \n "):
            with self.subTest(goal=repr(goal)):
                home, plan = self.raw_lines(goal)
                self.assertEqual(home, GOAL + planning.one_line(goal, 100), home)
                self.assertEqual(plan, GOAL + planning.one_line(goal, 200), plan)
                self.assertNotIn("[i]", home + plan)

    def test_a2_a_long_unbroken_word_multiline_unicode_and_a_literal_ellipsis(self):
        """A long unbroken word and multiline Unicode are cut by the same `one_line` normalization (with the hint
        when characters went); a goal whose own last character is an ellipsis is hinted only when the
        normalization really dropped something."""
        cases = [("я" * 150, True),
                 ("строка один\nстрока два\t多字 и ещё немного текста для обрезки слова " + "я" * 60, True),
                 ("строка один\nстрока два\t多字 и ещё немного текста для обрезки слова", False),
                 ("слово " * 40, True), ("ц" * 99 + "…", False), ("ц" * 100 + "…", True)]
        for goal, hinted in cases:
            with self.subTest(goal=repr(goal[:8])):
                line = self.line(goal, 100)
                self.assertTrue(line.startswith(GOAL + planning.one_line(goal, 100)), line)
                self.assertEqual("[i]" in line, hinted, line)
                self.assertEqual(line.split(" — [")[0], GOAL + planning.one_line(goal, 100), line)

    def test_a2_every_view_kind_exposes_the_goal_through_its_details(self):
        """Every PlanView kind offers its [i] and that [i] text carries the whole stored goal."""
        goal = "полная цель\n" + "Ц" * 230 + " конец"
        for kind in ("unsent", "stale", "unknown", "observing", "failed", "proposed", "approved"):
            with self.subTest(kind=kind):
                state = self.root / ("state-" + kind)
                with Authority(state, self.project, fixture_id="test") as authority:
                    authority.begin(goal, ROLES, "fixture")
                    runs = MilestoneRuns(authority, FixtureDriver(self.root / "fixture-runs"),
                                         worktrees=authority.directory / "worktrees")
                    planner = Planner()
                    if kind == "unknown":
                        planner.prepare(authority)
                        authority.current.update(status="submission_unknown")
                        authority.save()
                    elif kind in ("observing", "failed"):
                        planner.receipt(authority)
                        if kind == "failed":
                            planner.fail(authority)
                    elif kind in ("proposed", "approved"):
                        FixtureEngine().proposal(authority, lambda _: None)
                        if kind == "approved":
                            authority.approve(authority.current["version"])
                    elif kind == "stale":
                        (self.project / "untracked").write_text("x")
                    service = Delivery(authority, runs, planning.Planning(authority, runs, lambda *_: FixtureEngine()))
                    view = service.planning.view()
                    self.assertIn("details" if kind not in ("proposed", "approved") else "requirements",
                                  view.actions, (kind, view.actions))
                    self.assertIn(goal, "\n".join(service.plan_info()), kind)
                    self.assertIn(GOAL, "\n".join(view.lines), kind)
                (self.project / "untracked").unlink(missing_ok=True)
                self.assertEqual(self.sent, [])  # opening the plan screen and its [i] submits nothing

    @property
    def sent(self):
        return self.planner.sent


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class GoalScreenTests(MilestoneShell):
    """A-2 pilot: the plain line, the TUI pane, the home [i] and the plan [i] — no work started by any of them."""

    def proposal(self, goal):
        with Authority(self.state, self.project, fixture_id="test") as authority:
            authority.begin(goal, ROLES, "fixture")
            FixtureEngine().proposal(authority, lambda _: None)
            authority.approve(1)

    async def test_a2_home_and_plan_details_show_the_full_goal(self):
        from terminal_planner.tui import app as ui
        goal = "Ц" * 160 + " конец"
        self.proposal(goal)
        async with self.shell(size=(120, 40), follow=False) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)                                 # D4: the pane's [i] needs the pane
            await self.command(pilot, "/details")                                  # home [i]: the full record in a TextScreen
            await self.until(pilot, lambda: isinstance(self.app.screen, ui.TextScreen))  # the callback delivered
            await pilot.pause()
            self.assertIn(goal, "\n".join(self.app.screen.lines))
            await pilot.press("escape")
            await self.until(pilot, lambda: not isinstance(self.app.screen, ui.TextScreen))
            await self.command(pilot, "/view")
            await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "PlanScreen")
            await self.press_button(pilot, "info")                  # plan «подробнее»: the same text, inline
            await self.until(pilot, lambda: bool(self.app.details_lines))   # the details callback delivered
            await pilot.pause()
            self.assertIn(goal, "\n".join(self.app.plan_lines))
            self.assertEqual(self.driver.sent, [])
            await pilot.press("escape")

    async def test_a2_the_plain_home_line_and_the_tui_pane_are_the_same_text(self):
        """R-2: the plain UI and the TUI print the same goal text and hint (the line UI's home line is the pane's)."""
        goal = "Ц" * 150 + " конец"
        self.proposal(goal)
        plain = [line for line in self.plain("q\n").splitlines() if line.startswith(GOAL.rstrip())]
        async with self.shell(size=(120, 40), follow=False) as pilot:
            await self.loaded(pilot)
            pane = [line for line in self.app.snapshot.lines if line.startswith(GOAL.rstrip())]
            self.assertTrue(pane and plain, (pane, plain))
            self.assertIn(catalog.hint("home.details"), pane[0])
            self.assertIn(catalog.hint("home.details"), plain[0])
            self.assertEqual(plain[0], pane[0])

    async def test_a2_the_plain_and_the_tui_plan_details_are_the_same_text(self):
        """R-2/A-2: the plan [i] of both UIs is the delivery service's plan text — the whole stored goal, then the
        requirements — so the line UI's plan [i] is not the requirements alone (its home [i] rule, applied to the
        plan screen). Opening it starts no work."""
        goal = "Ц" * 220 + " конец"
        self.proposal(goal)
        plain = self.plain("p\ni\nq\nq\n")
        async with self.shell(size=(120, 40), follow=False) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)                               # D4: the pane's [p] needs the pane
            await self.command(pilot, "/view")
            await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "PlanScreen")
            await self.press_button(pilot, "info")                # plan «подробнее»: the same text, inline
            await self.until(pilot, lambda: bool(self.app.details_lines))
            await pilot.pause()
            tui = "\n".join(self.app.details_lines)
            self.assertEqual(self.driver.sent, [])
        self.assertIn(goal, tui)                                  # the full stored goal, not the cut line
        self.assertIn(goal, plain)
        self.assertIn("R1  Demonstrate the requested user interaction.", tui)  # the requirements block (heading is T1's text)
        self.assertIn("R1  Demonstrate the requested user interaction.", plain)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class EndViewTests(MilestoneShell):
    """A-3: the modal's entries, its size and its help, from the store and the app's own screens."""

    def end_view(self, entries, label, state="needs_owner"):
        """The end view of one stored attempt, built by the delivery service (the modal's own source): `entries`
        seeds that attempt's stored journal exactly as the engine keeps it."""
        self.state = self.root / ("state-" + label)      # a fresh store per case
        self.approve(running=True)
        with Authority(self.state, self.project, fixture_id="test") as authority:
            run = authority.state["runs"][0]
            run["live"] = dict(live.new(), journal=[{"at": "2026-10-19T04:%02d:00Z" % (i % 60), "text": text}
                                                    for i, text in enumerate(entries)])
            authority.save()
            runs = MilestoneRuns(authority, FixtureDriver(self.root / "fixture-runs"),
                                 worktrees=authority.directory / "worktrees")
            service = Delivery(authority, runs, planning.Planning(authority, runs, lambda *_: FixtureEngine()))
            return service.view(run, state)

    async def open_modal(self, pilot, end):
        from terminal_planner.tui import app as ui
        modal = ui.RunScreen(end)
        self.app.push_screen(modal)
        await self.until(pilot, lambda: self.app.screen is modal and modal.ready)
        await pilot.pause()
        return modal

    @staticmethod
    def body(modal):
        """The modal's body as its widget draws it: one string, the physical newlines included."""
        return str(modal.query_one("#run-body").content)

    async def test_a3_the_stored_journal_is_shown_oldest_first(self):
        from terminal_planner.tui import app as ui
        for count in (0, 1, live.JOURNAL_LIMIT):
            with self.subTest(count=count):
                entries = ["entry %d" % i for i in range(count)]
                end = self.end_view(entries, "journal-%d" % count)
                async with self.shell(size=(120, 40)) as pilot:
                    await self.loaded(pilot)
                    modal = await self.open_modal(pilot, end)
                    body = self.body(modal)
                    self.assertIn(JOURNAL_HEAD, body)
                    self.assertIn(NEXT_HEAD, body)
                    # R-3/K1c3: «Дальше:» names the buttons of the offered actions (their catalog labels) and the
                    # keys that work them — Tab, Enter, Esc — and no letter key.
                    after = " ".join(body[body.index(NEXT_HEAD):].split())
                    for name in end.names:
                        if name in ui.RunScreen.IDS:
                            self.assertIn("«%s»" % catalog.label(ui.RunScreen.IDS[name]), after)
                    for key in ("Tab", "Enter", "Esc"):
                        self.assertIn(key, after)
                    self.assertNotRegex(after, r"\[[a-z?]\]")
                    shown = [line for line in body.split("\n") if "entry" in line]
                    self.assertEqual(len(shown), count)
                    for index, line in enumerate(shown):
                        self.assertIn("entry %d" % index, line)     # the attempt's own entries, in order
                    if not count:
                        self.assertIn(JOURNAL_EMPTY, body)

    async def test_a3_the_modal_is_sized_to_the_rows_it_draws(self):
        """The box starts at the body's top — i9 dropped the logo and the header, so `screen_header_rows` (R-3's
        own rule) is 0 — and is as high as the physical rows its body draws plus title, button row, keys and border, capped by
        the room below that; the overflow scrolls and survives a resize."""
        from terminal_planner.tui import app as ui
        entries = ["ID%02d first line\nsecond\nthird" % i for i in range(live.JOURNAL_LIMIT)]
        for count in (0, 1, live.JOURNAL_LIMIT):
            with self.subTest(count=count):
                end = self.end_view(entries[:count], "sized-%d" % count)
                async with self.shell(size=(80, 24)) as pilot:
                    await self.loaded(pilot)
                    modal = await self.open_modal(pilot, end)
                    for size in ((80, 24), (120, 40), (80, 24)):
                        await pilot.resize_terminal(*size)
                        await self.until(pilot, lambda: tuple(modal.size) == size)
                        modal.render_state()
                        await pilot.pause()
                        box = modal.query_one("#run")
                        top = ui.screen_header_rows(*size)   # R-3: the rows MainScreen spends above its body
                        self.assertGreaterEqual(box.region.y, top, (size, count))
                        room = size[1] - top
                        rows = len(self.body(modal).split("\n"))
                        self.assertEqual(box.region.height, min(rows + 1 + 1 + 1 + 2, room), (size, count))
                        scroll = modal.query_one("#run-scroll")
                        scroll.scroll_end(animate=False)
                        await pilot.pause()
                        self.assertEqual(scroll.scroll_y, scroll.max_scroll_y, (size, count))

    async def test_a3_a_wide_glyph_entry_is_sized_to_the_rows_it_draws(self):
        """R-3/A-3: a wide CJK glyph takes two terminal cells, so a journal entry of them wraps where the terminal
        wraps it; the box is as high as the rows the body widget really draws, measured after the layout settled —
        not the characters a character-based wrap counted."""
        from terminal_planner.tui import app as ui
        entries = ["字" * 60]
        for count in (1, live.JOURNAL_LIMIT):
            end = self.end_view(entries * count, "wide-%d" % count)
            for size in ((80, 24), (120, 40)):
                with self.subTest(count=count, size=size):
                    async with self.shell(size=size) as pilot:
                        await self.loaded(pilot)
                        modal = await self.open_modal(pilot, end)
                        await pilot.resize_terminal(*size)
                        await self.until(pilot, lambda: tuple(modal.size) == size)
                        modal.render_state()
                        await pilot.pause()
                        box = modal.query_one("#run")
                        body = modal.query_one("#run-body")
                        room = size[1] - ui.screen_header_rows(*size)
                        self.assertIn("字" * 60, str(body.content))          # the entry it was given
                        rows = body.size.height                              # the rows the widget really draws
                        self.assertEqual(box.region.height, min(rows + 1 + 1 + 1 + 2, room),
                                         (size, count, rows, body.size))

    def test_a3_a_button_exists_for_every_action_the_modal_names(self):
        """A-3/K1c3: every action the delivery service offers on an end state is a button of this modal, labelled
        by a catalog entry and running that same service action, in the service's order, «подробнее» last — the
        recoverable failed end with the delivery catalog's own IDs and its back. A mapping between the END_ACTIONS
        table, the catalog and the modal's own `buttons`: no terminal, no store.

        Interpretation: «later» is not a modal action (this state closes with Esc), so it has no button."""
        from types import SimpleNamespace
        from terminal_planner.tui import app as ui
        self.assertNotIn("later", ui.RunScreen.IDS)
        for state, actions in delivery.END_ACTIONS.items():
            with self.subTest(state=state):
                end = SimpleNamespace(
                    state=state, token=None, back=delivery.END_BACK.get(state), names=tuple(n for n, _ in actions),
                    actions=tuple(SimpleNamespace(name=n, id=i) for n, i in actions))
                buttons = ui.RunScreen(end).buttons()
                expected = [(name, _id) for name, _id in actions if name != "later"]
                if state == ui.RunScreen.DELIVERY_KEYS_STATE:
                    expected += [("back", end.back)]
                else:
                    expected = [(name, ui.RunScreen.IDS[name]) for name, _ in expected]
                self.assertEqual(buttons, expected + [("details", "tui_run.details")])
                for _name, action_id in buttons:
                    self.assertTrue(catalog.label(action_id))

    async def test_k1c3_the_end_screen_answers_with_buttons_not_letters(self):
        """K1c3 C1/C3/C4: one button per offered action in the service's order, «подробнее» last; Enter on a button
        runs that action, Tab/←→ move, Esc closes, letters and `?` do nothing; `set_end` rebuilds the row with the
        focus kept on the same action (else the first button); ↑↓ PgUp PgDn scroll; the `Дальше:` line and the bar
        name Tab, Enter and Esc and no `[letter]`.

        Interpretations: the end is a stored `needs_owner` attempt (answer, leave) and its variants made with
        `dataclasses.replace`, so the walk needs no worktree; `modal_action` is replaced by a recorder, the service
        call behind each action is the other tests' business."""
        import dataclasses
        from terminal_planner.tui import app as ui
        end = self.end_view(["entry %d" % i for i in range(live.JOURNAL_LIMIT)], "buttons")
        names = lambda modal: [b.name for b in modal.query("#run-buttons Button")]
        calls = []
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            with patch.object(type(self.app), "modal_action", lambda app, modal, name: calls.append(name)):
                modal = await self.open_modal(pilot, end)
                await self.until(pilot, lambda: names(modal) == ["answer", "leave", "details"])
                self.assertEqual([b.label.plain for b in modal.query("#run-buttons Button")],
                                 [catalog.label(i) for i in modal.action_ids()])
                self.assertEqual(modal.action_ids()[:2], [ui.RunScreen.IDS[n] for n in ("answer", "leave")])
                for text in (modal.key_bar(120), modal.next_line()):  # C4
                    self.assertNotRegex(text, r"\[[a-z?]\]")
                    for key in ("Tab", "Enter", "Esc") if text == modal.next_line() else ("tab", "enter", "esc"):
                        self.assertIn(key, text)
                await pilot.press("a", "t", "x", "i", "q", "question_mark")  # no letter and no `?` does anything
                await pilot.pause(0.1)
                self.assertIs(self.app.screen, modal)
                self.assertEqual(calls, [])
                self.assertEqual(self.app.focused.name, "answer")
                await pilot.press("right")
                self.assertEqual(self.app.focused.name, "leave")
                await pilot.press("tab")
                self.assertEqual(self.app.focused.name, "details")
                await pilot.press("left", "left")
                self.assertEqual(self.app.focused.name, "answer")
                await pilot.press("enter")
                await self.until(pilot, lambda: calls == ["answer"])  # Enter does what the old [t] did
                # C3: another set of offered actions rebuilds the row; the focus stays on the same action ...
                await pilot.press("right")
                modal.set_end(dataclasses.replace(end, actions=tuple(a for a in end.actions if a.name == "leave")))
                await self.until(pilot, lambda: names(modal) == ["leave", "details"])
                await self.until(pilot, lambda: getattr(self.app.focused, "name", None) == "leave")
                # ... else goes to the first button
                modal.set_end(dataclasses.replace(end, actions=tuple(a for a in end.actions if a.name == "answer")))
                await self.until(pilot, lambda: names(modal) == ["answer", "details"])
                await self.until(pilot, lambda: getattr(self.app.focused, "name", None) == "answer")
                scroll = modal.query_one("#run-scroll")
                self.assertGreater(scroll.max_scroll_y, 0)
                await pilot.press("pagedown")
                await self.until(pilot, lambda: scroll.scroll_y > 0)
                await pilot.press("pageup")
                await self.until(pilot, lambda: scroll.scroll_y == 0)
                await pilot.press("down")
                await self.until(pilot, lambda: scroll.scroll_y > 0)
                await pilot.press("up")
                await self.until(pilot, lambda: scroll.scroll_y == 0)
                await pilot.press("escape")
                await self.until(pilot, lambda: self.app.screen is not modal)

    async def test_k1c3_the_recoverable_failed_end_shows_the_delivery_catalogs_actions_as_buttons(self):
        """K1c3 C2: the recoverable failed end's buttons are the delivery catalog's actions in its order, then its
        back; Enter on «продолжить» resumes (the action name `resume` reaches the app's `modal_action`).

        Interpretation: «журнал» (the activity tail) and «подробнее» keep their places between and after them as
        on every end screen; the stored attempt carries no native run here, so no «журнал»."""
        end = self.end_view(["entry"], "recoverable", "failed_recoverable")
        calls = []
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            with patch.object(type(self.app), "modal_action", lambda app, modal, name: calls.append(name)):
                modal = await self.open_modal(pilot, end)
                await self.until(pilot, lambda: modal.query("#run-buttons Button"))
                buttons = list(modal.query("#run-buttons Button"))
                self.assertEqual([b.name for b in buttons][:3], ["resume", "new_attempt", "plan"])
                self.assertEqual([b.label.plain for b in buttons][:3],
                                 [catalog.label("failed_recoverable." + n) for n in ("resume", "new_attempt", "plan")])
                self.assertIn("back", [b.name for b in buttons])
                self.assertEqual(self.app.focused.name, "resume")
                await pilot.press("enter")
                await self.until(pilot, lambda: calls == ["resume"])


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ResultModalTests(LiveShell):
    """A-3 pilot through a real attempt: header clearance, the stored journal, [i], the stale token, the narrow
    fallback."""

    async def test_a3_below_the_header_journal_details_and_return(self):
        from terminal_planner.tui import app as ui
        self.driver.outcomes = ("needs_owner",)
        self.approve(running=False)
        self.driver.release()
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            await self.open_question_end(pilot)  # i3d: a needs_owner end is a card now; [o] opens the end screen
            await self.shows(pilot, "needs an answer")
            screen = self.app.screen
            self.assertIsInstance(screen, ui.RunScreen)
            self.assertTrue(screen.has_class("body-region"))
            self.assertGreaterEqual(screen.query_one("#run").region.y, ui.screen_header_rows(*self.app.size))
            body = str(screen.query_one("#run-body").content)
            self.assertIn(JOURNAL_HEAD, body)
            self.assertIn(NEXT_HEAD, body)
            entries = tuple(screen.journal())
            self.assertTrue(entries and all(entry for entry in entries))
            await self.press_button(pilot, "details")             # the stored entries, no native log needed
            await self.until(pilot, lambda: isinstance(self.app.screen, ui.TextScreen))
            await pilot.pause()
            self.assertEqual(tuple(self.app.screen.lines), entries)
            await pilot.press("escape")
            await self.until(pilot, lambda: self.app.screen is screen)
            self.assertIn("needs an answer", screen_text(self.app))

    async def test_a3_an_attempt_change_while_details_are_open_cannot_act_on_the_old_token(self):
        from terminal_planner.tui import app as ui
        self.approve(running=False)
        self.driver.release()
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            await self.open_merge_end(pilot)  # i3c: the card replaces the automatic end screen
            modal = self.app.screen
            await self.press_button(pilot, "details")             # the journal screen, over the result modal
            await self.until(pilot, lambda: isinstance(self.app.screen, ui.TextScreen))
            await pilot.pause()
            await self.post_and_wait(pilot, merge_elsewhere)       # another window integrated that attempt
            head = self.head()
            self.app.request_refresh()
            # the re-render callback delivers the move to the modal itself, not only to the screen above it
            await self.until(pilot, lambda: "The state changed" in modal.note)
            await pilot.press("escape")                            # back to the modal, now showing the change
            await self.until(pilot, lambda: self.app.screen is modal)
            await pilot.pause()
            self.assertIn("The state changed while the screen was open", self.flat())
            await self.until(pilot, lambda: not modal.query("#run-buttons-merge"))  # the old modal's merge button is gone
            await pilot.press("m")                                 # and the letter does nothing
            await pilot.pause()
            self.assertEqual(self.head(), head)                    # the second merge never ran
            self.assertIn("— merged", self.flat())

    async def test_a3_the_narrow_fallback_keeps_the_old_box(self):
        from terminal_planner.tui import app as ui
        self.driver.outcomes = ("needs_owner",)
        self.approve(running=False)
        self.driver.release()
        async with self.shell(size=(60, 20), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            # i3d: a needs_owner end is a card now and the narrow layout shows the chat tab with it (the pane and its
            # [o] are off screen there); this test is about the box's layout, so it opens the box through [o]'s action
            await self.until(pilot, lambda: "Your decision is needed" in self.flat())
            self.app.action_open_milestone()
            # I7: the narrow layout shows the panel behind the box (the panel keeps the focus the run keys need), so
            # the pane's border column can fall between the two wrapped halves of the phrase; wait on the box's line.
            await self.shows(pilot, "needs an answer")
            screen = self.app.screen
            self.assertIsInstance(screen, ui.RunScreen)
            self.assertFalse(screen.has_class("body-region"))  # below 80x24 the previous centred box stays


def merge_elsewhere(app):
    """The merge another window would have done while the result modal is open."""
    app.delivery.merge(app.delivery.latest("M1"))


class ResultReadiness:
    """A readiness whose next slice returns whatever the test put in `self.result` (items, or an exception to
    raise), counting its calls: the app's own keys drive it."""

    def __init__(self, *items):
        self.result, self.calls = list(items), 0

    def __call__(self):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return [dict(i) for i in self.result]


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ClosingLineTests(MilestoneShell):
    """A-4: one catalog closing line per interactive batch, from its own result, through the owner's own keys."""

    def setUp(self):
        super().setUp()
        self.readiness = ResultReadiness(check("branch", True, "ready"))

    @contextlib.contextmanager
    def fixture_home(self):
        """R-8: `setup.readiness` judges `agent_home(os.environ)`, and with an empty or unset `CODEX_HOME` that is
        `private_codex_home()` — a resolution that goes *around* any `codex_home` patch — so the real-readiness tests
        below pin `XDG_DATA_HOME` into this fixture's root and clear the provider variables a developer shell (or
        `run.sh`) may export. The runner's own data root and dev shell never decide a verdict."""
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"), "CODEX_API_KEY": "",
                                     "OPENAI_API_KEY": ""}):
            yield

    async def test_a4_recheck_login_and_setup_close_with_one_line_from_their_own_result(self):
        @contextlib.contextmanager
        def suspend():
            yield
        async with self.shell(self.controller(self.readiness, install=lambda emit: None, login=lambda: 0),
                              size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await self.until(pilot, lambda: not self.app.checking)
            results = [([check("branch", True, "ready")], CHECK_DONE),
                       ([check("branch", False, "Codex: not logged in — [l] log in", "Run zplan login.", key="l")],
                        "! Codex: not logged in"),
                       ([], CHECK_EMPTY),
                       (ValueError("matrix error"), CHECK_ERROR)]
            for key in ("recheck", "login", "setup"):
                for result, prefix in results:
                    with self.subTest(key=key, result=prefix):
                        self.readiness.result = result
                        marker = len(self.app.log_lines)
                        with patch.object(self.app, "suspend", suspend):
                            await self.press_button(pilot, key)
                            await self.until(pilot, lambda: closing_lines(list(self.app.log_lines)[marker:]))
                        await self.until(pilot, lambda: not self.app.checking and not self.app.setting_up)
                        await pilot.pause()
                        fresh = closing_lines(list(self.app.log_lines)[marker:])
                        self.assertEqual(len(fresh), 1, (key, prefix, fresh))  # exactly one line for this batch
                        self.assertTrue(fresh[0].startswith(prefix), (key, prefix, fresh[0]))
                        if prefix == CHECK_DONE:
                            self.assertIn("[esc] " + catalog.label("tui_settings.back"), fresh[0])   # the enabled next keys of the Settings screen
                            self.assertIn(catalog.text("tui_settings.recheck"), fresh[0])

    async def test_a4_a_failing_remedy_is_only_named_when_its_key_is_enabled(self):
        """With neither login nor install available, a failing tools/codex/login item must not suggest its own key
        ([u]/[l] are not in `settings_keys()`), and must not echo the item's `detail` either: a real readiness item
        puts that very key into its detail (`Установка: [u] ...`, `[l] запускает вход Codex ...`), so a line that
        repeats the detail repeats a disabled key. The line names the catalog's key-free remedy for the item's own
        id instead (the commands are asserted, not the table, so the oracle is the production line itself).
        The three items come from `setup.readiness` itself — the real readiness the Settings screen shows."""
        home = self.root / "missing-home"
        with self.fixture_home(), patch.object(setup, "tool_paths",
                          return_value=(self.root / "missing-zero", self.root / "missing-codex")), \
                patch.object(setup, "check_installation", side_effect=Blocked("missing")), \
                patch.object(setup, "codex_home", return_value=home), \
                patch.object(setup, "codex_provider", return_value=("openai", "file")), \
                patch("terminal_planner.engine.check_socket_path", return_value=81):
            items = {item["id"]: item for item in setup.readiness(self.project)}
        cases = [("tools", "u", "zplan setup"), ("codex", "u", "zplan setup"), ("auth", "l", "zplan login")]
        for item_id, key, command in cases:
            with self.subTest(item=item_id):
                item = items[item_id]
                self.assertEqual([item["ok"], item["key"]], [False, key])   # the fixture is a real failing item
                self.assertIn("[%s]" % key, item["detail"])                 # ... whose detail repeats its own key
                self.readiness.result = [item]
                # a real, non-fixture session: the deterministic engine skips the toolchain items entirely, so
                # the tools/codex/login items this test is about only reach the Settings screen without one
                controller = controller_module.Controller.for_project(self.project, None,
                                                                     readiness=self.readiness)
                self.addCleanup(controller.stop)
                async with self.shell(controller, size=(120, 40)) as pilot:
                    await self.loaded(pilot)
                    await self.command(pilot, "/setup")
                    await self.until(pilot, lambda: not self.app.checking)
                    self.assertIsNone(self.app.controller.login)     # the preconditions this test is about
                    self.assertIsNone(self.app.controller.install)
                    await self.press_button(pilot, "recheck")
                    await self.until(pilot, lambda: not self.app.checking)
                    await pilot.pause()
                    fresh = closing_lines(list(self.app.log_lines))
                    self.assertTrue(fresh, list(self.app.log_lines))   # an interactive batch closes with a line
                    line = fresh[-1]
                    self.assertNotIn("[%s]" % key, line)
                    self.assertNotIn(item["detail"], line)           # the detail's disabled key never travels
                    self.assertIn(command, line)

    async def test_a4_an_environment_key_auth_item_is_not_told_to_run_the_login(self):
        """R-4: the auth id carries two causes whose fixes differ, and the item's own structured key picks the
        applicable one. A missing login file is repaired by [l] login; an unset provider environment key is not —
        only an export is, and that item asks for [i], not [l]. The failing item comes from `setup.readiness`
        itself with the provider's auth mode patched to `("env", NAME)`, so the closing line must name the
        export and never `zplan login` (the base maps every auth failure to the login remedy).

        Interpretations: the two causes share the catalog's structured id `auth` — its family already says "no
        login file or API key variable" — so the remedy is keyed by the item's structured id *and* key instead
        of by a new id, which is also why the item stays in `planning.NEEDS` for a model action."""
        with self.fixture_home(), patch.object(setup, "tool_paths",
                          return_value=(self.root / "missing-zero", self.root / "missing-codex")), \
                patch.object(setup, "check_installation", side_effect=Blocked("missing")), \
                patch.object(setup, "codex_home", return_value=self.root / "missing-home"), \
                patch.object(setup, "codex_provider",
                             return_value=("example", ("env", "ZPLAN_UNSET_KEY"))), \
                patch("terminal_planner.engine.check_socket_path", return_value=81):
            item = next(i for i in setup.readiness(self.project) if i["id"] == "auth")
        self.assertEqual(item["ok"], False)                       # a real, failing readiness item
        self.assertEqual(item["key"], "i")                        # ... whose own key is the instruction, not login
        self.assertNotIn("[l]", item["detail"])
        self.readiness.result = [item]
        # a real, non-fixture session: the deterministic engine skips the toolchain items entirely, so an auth
        # item only reaches the Settings screen without one (as in the remedy test above)
        controller = controller_module.Controller.for_project(self.project, None, readiness=self.readiness,
                                                             login=lambda: 0)
        self.addCleanup(controller.stop)
        async with self.shell(controller, size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await self.until(pilot, lambda: not self.app.checking)
            self.assertIsNotNone(self.app.controller.login)   # login is offered here, yet is not the remedy
            await self.press_button(pilot, "recheck")
            await self.until(pilot, lambda: not self.app.checking)
            await pilot.pause()
            fresh = closing_lines(list(self.app.log_lines))
            self.assertTrue(fresh, list(self.app.log_lines))   # an interactive batch closes with a line
            line = fresh[-1]
            self.assertNotIn("zplan login", line)
            self.assertIn(catalog.CHECK_REMEDY_FREE_KEY[("auth", "i")], line)

    async def test_a4_a_closing_line_names_no_action_the_live_guards_refuse(self):
        """R-4: a closing line names only actions that would really run.

        While setup runs, `start_setup` refuses [u] ("установка уже идёт") and `start_login` refuses [l] ("войти
        можно после неё"), so neither may appear in a closing line — not as the enabled remedy key, not among the
        all-OK line's next keys; the catalog's key-free remedy stands in for the refused one. The reproduction
        holds the interactive readiness slice on an Event, starts setup (held on its own Event) while that batch
        is in flight and releases the slice, so its batch is delivered during the setup; every step is
        synchronized on the observed Events and deliveries, never on elapsed time. Setup's own batch, delivered
        once setup ended, names the keys again — so the guard is the live one, not a one-off.

        Interpretations: "enabled next keys" is what the live guards would admit *now*, not what the session has a
        callable for; the Settings screen keeps its own pre-existing capability list, which this finding did not
        name."""
        for failing in (True, False):
            with self.subTest(failing=failing):
                held, release, entered, release_setup = (threading.Event(), threading.Event(), threading.Event(),
                                                         threading.Event())
                self.addCleanup(release.set)
                self.addCleanup(release_setup.set)
                active = {"hold": False}

                def readiness():
                    if active["hold"]:
                        held.set()
                        release.wait(10)
                    return [check("auth", not failing, "Codex: not logged in — [l] log in", "Run zplan login.",
                                  key="l")]

                def install(emit):
                    entered.set()
                    release_setup.wait(10)

                controller = controller_module.Controller.for_project(self.project, None, readiness=readiness,
                                                                     install=install, login=lambda: 0)
                self.addCleanup(controller.stop)
                async with self.shell(controller, size=(120, 40)) as pilot:
                    await self.loaded(pilot)
                    await self.command(pilot, "/setup")
                    await self.until(pilot, lambda: not self.app.checking)
                    active["hold"] = True
                    await self.press_button(pilot, "recheck")                       # the owner's recheck, held on the readiness
                    await self.until(pilot, held.is_set)
                    await self.press_button(pilot, "setup")                       # setup starts while that batch is in flight
                    self.assertTrue(self.app.setting_up)
                    marker = len(self.app.log_lines)
                    release.set()                                # the held batch is delivered during the setup
                    await self.until(pilot, entered.is_set)
                    await self.until(pilot, lambda: closing_lines(list(self.app.log_lines)[marker:]))
                    line = closing_lines(list(self.app.log_lines)[marker:])[0]
                    self.assertNotIn(catalog.text("tui_settings.setup"), line)  # both live guards refuse while setup runs
                    self.assertNotIn(catalog.text("tui_settings.login"), line)
                    if failing:
                        self.assertNotIn(CHECK_DONE, line)
                        self.assertIn(catalog.CHECK_REMEDY_FREE["auth"], line)   # the key-free catalog remedy
                    else:
                        self.assertIn(CHECK_DONE, line)
                        self.assertIn(catalog.text("tui_settings.recheck"), line)  # the keys that do work stay named
                    active["hold"] = False
                    release_setup.set()                          # setup ends: its own batch names them again
                    await self.until(pilot, lambda: not self.app.setting_up)
                    await self.until(pilot, lambda: len(closing_lines(list(self.app.log_lines)[marker:])) > 1)
                    later = closing_lines(list(self.app.log_lines)[marker:])
                    self.assertIn(catalog.text("tui_settings.login"), later[-1])  # the same result, the key back: live guard


class GatedReadiness:
    """A fixture readiness whose every slice can be held on its own Event.

    `held` counts the calls a test still holds; `release()` releases the oldest held call and `fail_next` makes the
    next slice's result a failure, so a closing line identifies exactly the batch it belongs to."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls = 0
        self.hold = False
        self.fail_next = False
        self.entered = threading.Event()
        self.open = []

    def __call__(self):
        with self.lock:
            self.calls += 1
            number = self.calls
            gate = threading.Event() if self.hold else None
            if gate is not None:
                self.open.append(gate)
                self.entered.set()
        if gate is not None:
            gate.wait(10.0)
            with self.lock:
                self.open.remove(gate)
        with self.lock:                       # read after the hold: a held slice can still be made to fail
            fail, self.fail_next = self.fail_next, False
        return [check("git", not fail, "ready #%d" % number, detail="fix #%d" % number, key="d")]

    @property
    def held(self):
        with self.lock:
            return len(self.open)

    def release(self):
        with self.lock:
            gate = self.open[-1] if self.open else None
        if gate is not None:
            gate.set()


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class CheckBatchTests(MilestoneShell):
    """A-4 pilot: batches close once, coalesce, and a request during a running check is satisfied afterwards."""

    async def open_settings(self, pilot):
        await self.command(pilot, "/setup")
        await self.until(pilot, lambda: not self.app.checking)
        await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "SettingsScreen")

    async def test_a4_one_line_per_batch_and_one_coalesced_follow_up(self):
        gated = GatedReadiness()
        ok = lambda: sum(line.startswith(CHECK_DONE) for line in self.app.log_lines)
        bad = lambda: [line for line in self.app.log_lines if line.startswith("! ready")]
        async with self.shell(self.controller(gated), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)                              # the startup background check
            await self.open_settings(pilot)
            gated.hold = True
            await self.press_button(pilot, "recheck")                                # the owner's recheck: held
            await self.until(pilot, lambda: gated.held >= 1)
            started = gated.calls
            await self.press_button(pilot, "recheck")                   # repeated interactive requests: coalesce
            await self.press_button(pilot, "recheck")
            self.app.request_check()                              # a background request: cannot replace the batch
            self.assertEqual(gated.calls, started)                # the running check is never disturbed
            gated.fail_next = True                                # the held batch gets a distinct failing result
            gated.release()
            await self.until(pilot, lambda: len(bad()) == 1)      # exactly one closing line for that batch
            # ... from that held slice's own result, not from a later one (the name identifies the batch)
            self.assertTrue(bad()[0].startswith("! ready #%d — " % started), bad()[0])
            self.assertEqual(ok(), 0)                             # and no OK line for it
            await self.until(pilot, lambda: gated.held >= 1)      # the one coalesced follow-up is running
            self.assertEqual(gated.calls, started + 1)
            await self.press_button(pilot, "recheck")                                # a request during the follow-up
            gated.release()                                       # the follow-up completes (all OK)
            await self.until(pilot, lambda: ok() >= 1)
            await self.until(pilot, lambda: gated.held >= 1 and gated.calls == started + 2)
            gated.hold = False
            gated.release()                                       # the request made during the follow-up
            await self.until(pilot, lambda: ok() == 2 and not self.app.checking)
            self.assertEqual([len(bad()), gated.calls], [1, started + 2])
            # a background-only batch emits no closing line
            marker = ok() + len(bad())
            self.app.request_check()
            await self.until(pilot, lambda: not self.app.checking)
            await pilot.pause()
            self.assertEqual(ok() + len(bad()), marker)

    async def test_a4_a_background_request_during_a_check_gets_its_follow_up(self):
        """R-4: a request arriving while a check runs is satisfied only by a check started after it — a
        background request too, silently, through one coalesced follow-up."""
        gated = GatedReadiness()
        async with self.shell(self.controller(gated), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)                              # the startup background check
            gated.hold = True
            self.app.request_check()                              # the held slice
            await self.until(pilot, lambda: gated.held >= 1)
            started = gated.calls
            self.app.request_check()                              # the request that has to be satisfied later
            self.assertEqual(gated.calls, started)                # nothing starts while the slice is held
            gated.hold = False                                    # the follow-up itself runs freely
            gated.release()
            await self.until(pilot, lambda: gated.calls == started + 1)   # its own follow-up ran
            await self.until(pilot, lambda: not self.app.checking)
            await pilot.pause()
            self.assertEqual(closing_lines(list(self.app.log_lines)), [])  # a background batch stays silent

    async def test_a4_the_log_survives_navigation(self):
        gated = GatedReadiness()
        async with self.shell(self.controller(gated), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.open_settings(pilot)
            await self.press_button(pilot, "recheck")                                # an interactive batch, not held: closes at once
            await self.until(pilot, lambda: any(l.startswith(CHECK_DONE) for l in self.app.log_lines))
            await pilot.pause()
            lines = list(self.app.log_lines)
            await pilot.press("escape")                           # back to the main screen
            await self.until(pilot, lambda: self.app.screen.__class__.__name__ == "MainScreen")
            await self.open_settings(pilot)                       # and back again
            self.assertEqual(list(self.app.log_lines), lines)

    async def test_a4_closing_the_app_discards_the_waiting_batch(self):
        """R-4 shutdown: the exit discards the waiting follow-up; the late delivery of the cut batch writes no
        closing line."""
        gated = GatedReadiness()
        async with self.shell(self.controller(gated), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            gated.hold = True
            self.app.request_check()
            await self.until(pilot, lambda: gated.held >= 1)
            marker = len(self.app.log_lines)
            await pilot.press("ctrl+q")
            gated.hold = False
            gated.release()
            await self.until(pilot, lambda: self.app._exit)
            self.assertEqual(closing_lines(list(self.app.log_lines)[marker:]), [])

    async def test_a4_a_request_before_worker_entry_joins_the_queued_batch(self):
        """R-4: a slice that is queued but has not entered the worker has read nothing yet, so a request arriving
        then is satisfied by that very slice — it joins that batch instead of asking for one more. Two [g] presses
        and a background request, made while a follow-up waits behind a held refresh job, yield one follow-up
        slice and one closing line, not two (the reviewed defect counted the queued slice as already running)."""
        gated = GatedReadiness()
        refresh_entered, refresh_release = threading.Event(), threading.Event()
        self.addCleanup(refresh_release.set)
        original = controller_module.take_snapshot

        def held(app, name):                                  # the worker job the follow-up queues behind
            refresh_entered.set()
            refresh_release.wait(10)
            return original(app, name)

        async with self.shell(self.controller(gated), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)                           # the startup background slice
            with patch.object(controller_module, "take_snapshot", held):
                gated.hold = True
                self.app.request_check()                       # the held slice, background
                await self.until(pilot, lambda: gated.held >= 1)
                started = gated.calls
                self.app.request_refresh()                     # a worker job, queued behind the held slice
                self.app.recheck()                             # the owner's request, to be satisfied later
                self.assertEqual(gated.calls, started)         # nothing starts while the held slice runs
                gated.release()                                # the held slice returns; the refresh runs ...
                await self.until(pilot, refresh_entered.is_set)     # ... and is held, with the follow-up behind
                # the held slice's own result has reached the UI: its follow-up is posted and waits for the worker
                await self.until(pilot, lambda: any(getattr(c, "line", "") == "ready #%d" % started
                                                    for c in (self.app.checks or ())))
                self.app.recheck()                             # the owner's own [g], twice ...
                self.app.recheck()
                self.app.request_check()                       # ... and a background refresh of the checks
                self.assertEqual(gated.calls, started)         # all three joined the queued slice, not a new one
                gated.hold = False
                refresh_release.set()                          # the refresh ends: the joined follow-up runs
                await self.until(pilot, lambda: not self.app.checking)
            await pilot.pause()
            self.assertEqual(gated.calls, started + 1)         # one follow-up slice for the whole batch
            lines = closing_lines(list(self.app.log_lines))
            self.assertEqual(len(lines), 1, lines)             # one line for the one joined batch
            self.assertTrue(lines[0].startswith(CHECK_DONE), lines[0])

    async def test_a4_setup_keeps_the_request_that_arrives_while_it_holds_the_worker(self):
        """R-4: setup's own post-install check runs on the worker; a request landing while it does is not lost when
        setup finishes. A queued background slice, then the owner's [g], both wait for that slice and each close
        once — setup's own line and the owner's line (the reviewed defect dropped the owner's batch wholesale)."""
        entered, release = threading.Event(), threading.Event()
        queued, release_queued = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        self.addCleanup(release_queued.set)
        slices = []
        async with self.shell(self.controller(lambda: [check("branch", True, "ready")], install=lambda emit: None),
                              size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.open_settings(pilot)

            def checker(app):                                  # the worker's own check, held per slice
                slices.append(len(slices) + 1)
                if len(slices) == 1:                           # setup's own post-install check, already started
                    entered.set()
                    release.wait(10)
                if len(slices) == 2:                           # the queued slice waiting behind setup
                    queued.set()
                    release_queued.wait(10)
                number = len(slices)
                return controller_module.checks_of([check("branch", number != 1, "slice #%d" % number, key="d")])

            with patch.object(self.app.controller, "_check", checker):
                await self.press_button(pilot, "setup")        # the owner's setup
                await self.until(pilot, entered.is_set)
                self.app.request_check()                       # a background slice, queued behind setup
                marker = len(self.app.log_lines)
                await self.press_button(pilot, "recheck")                         # the owner's recheck, while setup holds the worker
                release.set()                                  # setup's check returns; setup completes
                await self.until(pilot, lambda: not self.app.setting_up)
                await self.until(pilot, queued.is_set)         # the queued slice has really started now
                release_queued.set()
                await self.until(pilot, lambda: not self.app.checking)
                await pilot.pause()
            lines = closing_lines(list(self.app.log_lines)[marker:])
            self.assertEqual(len(lines), 2, lines)             # setup's result and the owner's recheck, each once
            self.assertTrue(lines[0].startswith("! slice #1 — "), lines[0])
            self.assertTrue(lines[1].startswith(CHECK_DONE), lines[1])

    async def test_a4_a_completed_setup_cannot_overwrite_an_unapplied_batch(self):
        """R-4: a batch keeps its identity until its own callback is applied.

        Setup's post-install check finishes on the worker while the delivery of another interactive batch is
        still queued on the busy UI thread, so setup_done is applied first; the waiting follow-up used to start
        right there and overwrite the batch `check_batch` was still owed. The queued slice then closed with the
        follow-up's own batch and the follow-up closed with none — two lines for three distinguishable results.
        The coroutine holds the UI thread between the worker completions, so the hand-overs really queue behind
        each other, and the assertions are synchronized on those observations (worker Events and the applied
        callbacks), never on elapsed time.

        Interpretations: setup's own post-install check is the first batch, so its line names `result #1`; the
        owner's two rechecks are the next two, and a line is read as its own check's result (`result #N`), never
        as another batch's generation — that identity is exactly what the reproduction checks."""
        calls = []

        def checker(app):
            calls.append(len(calls) + 1)
            return controller_module.checks_of([check("branch", False, "result #%d" % len(calls))])

        setup_queued, check_queued, third_applied = threading.Event(), threading.Event(), threading.Event()
        async with self.shell(self.controller(lambda: [check("git")], install=lambda emit: None),
                              size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await self.until(pilot, lambda: not self.app.checking)
            real = self.app.deliver                                 # the app's own hand-over, before it is observed

            def observe(handler):
                def applied(value, error):
                    handler(value, error)
                    if handler.__name__ == "got_checks" and value and value[0].line == "result #3":
                        third_applied.set()

                def done(value, error):
                    real(applied)(value, error)                     # the production delivery order, one FIFO
                    if handler.__name__ == "setup_done":
                        setup_queued.set()
                    elif handler.__name__ == "got_checks":
                        check_queued.set()
                return done

            with patch.object(self.app.controller, "_check", checker), \
                    patch.object(self.app, "deliver", observe):
                self.app.start_setup()                              # setup's check finishes on the busy UI
                self.assertTrue(setup_queued.wait(5), "setup's check never reached the UI hand-over")
                self.app.recheck()                                  # A: a second, distinct check
                self.assertTrue(check_queued.wait(5), "recheck A never reached the UI hand-over")
                self.app.recheck()                                  # B: a slice started after it must answer
                await self.until(pilot, third_applied.is_set)
                await pilot.pause()
            lines = [line for line in self.app.log_lines if line.startswith("! result #")]
            self.assertEqual(len(lines), 3, lines)                  # each batch closed from its own result
            self.assertEqual([line.split("#", 1)[1][:1] for line in lines], ["1", "2", "3"], lines)
