"""I3c: the stage-done card — «M1 ready», merge or see the changes in one click (0.5.2, docs/RELEASE_0.5.2_PLAN.md
run i3c; card contract devtools/zeroshot/tasks/card-contract.md).

One acceptance criterion per test, at most two whole-app methods (the test-depth rule): A1 walks both sizes and
A2/A3/A5 are the 120x40 walk's own keys, while A1's text (the counts of the attempt's own tasks line, and the bare
card without them), A2's receipt and its failure path, A4's pending guard and the once-per-key read are unit level
on stand-in screens (no pilot, no project, no engine). A5's [o] is checked where it can be — in the whole-app walk,
because it is a pane key of the real screen.

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- The counts are read through `controller.open_run` — the brief's own call («`controller.open_run` returns the
  EndView») — but only once the attempt is *exported* (`Row.token.delivery == "awaiting_merge"`): reading the view
  is what finishes an accepted attempt, and the repository's invariant «an accepted attempt is exported first (an
  owner-visible arrival, never a refresh)» (`test_tui_milestones.QuitSafetyTests`) forbids a render from doing it.
  An attempt whose export has not run yet shows the same card without counts, exactly like one whose view carries
  no tasks line.
  Verified by removing exactly that condition: `QuitSafetyTests`'s
  `test_c3_an_open_export_is_shown_before_the_app_may_exit` then fails (the refresh's own read steals the export
  the test's own [o] makes), while the other twelve stay green.
- The joint example's tasks line «Tasks: 2/3 done» is not reachable through the shell: a run that ends `done`
  has every non-dropped task `done` (`runs.validate` refuses an open task on a `done` outcome), so a real fixture
  attempt always reads «N/N». The unit tests therefore carry the example's 2/3 line itself, and the whole-app walk
  reads the fixture plan's own line (M1 carries one task, «Tasks: 1/1 done»).
- The card's `at` is the clock read when the card first appears: a stage-done card has no stored stamp of its own
  (a goal draft carries the reply's).
- «see the changes» selects the card's own stage in the panel and then runs the existing `open_diff_tab()`; a
  typed `/diff` (whose key is None) keeps its own meaning, the diff of the row selected in the panel. An accepted
  attempt whose export has not run yet is exported first (a cut export or a reopen leaves exactly that: the row
  `awaiting_merge` while `delivery` is still `none`), because `runs.diff` needs the exported result.
- The same recovery state makes «merge» complete the export its click owes before `controller.merge`: the engine
  refuses the unexported token («Merge is possible only for an exported result»), so the click merges the
  token the export's own view carries. The refresh (the card source) still never exports, so the counts of an
  unexported attempt arrive with that click, not before it.
- That export reads the *latest* attempt, so its view is trusted only when its token still names the click's own
  attempt (revision, attempt and run — `merge_same_attempt`, and an `end` outcome at all): a view of another attempt,
  or a non-`end` outcome (an `active` view's bare `Token`, `none`, a refused export), is the merge's failure
  settlement on the status line, never merged. The card's own stage is likewise carried through the export callback
  of «see the changes» and re-selected right before the diff opens, so a selection the owner moved meanwhile
  never redirects the tab.
- A merge that fails leaves the card open and puts the engine's own line on the status line above the chat, and a
  success publishes the engine's own «Merged: …» line there too (a refusal before it is not left standing); a
  conflict also moves the row to `conflict`, so the source drops the card on the next render (the brief's own
  wording) instead of the verdict dropping it.
- `awaiting_merge` joining `AUTO_END_CARDS` takes the automatic end screen away from every test that pinned it.
  The run's write-set names `tests/test_tui_milestones.py`; four other modules carried the same kind of assertion
  and are repaired the same way — the end screen is opened with [o], exactly as the owner does: `test_tui_live`
  (`WordingTests.item8`), `test_tui_polish` (`ResultModalTests.test_a3_an_attempt_change_while_details_are_open…`),
  `test_tui_chat` (`LifecycleGuardChatTests.test_a3_a_chat_goal_handed_over_while_m1_is_active…`) and
  `test_tui_canvas_files` (`CanvasDiffTabTests.test_a2_a3_the_diff_opens_for_a_finished_stage_only…`).
- `tests/test_tui_card_hooks.py` (the i3a hook tests, in this run's DoD) pinned the hooks' two halves against the
  state of the registries at the i3a merge: its `CARD_SOURCES` patch now isolates its own made-up kind (`clear=True`
  — a source of another kind reads its own screen's app, which the stand-in has none of), and its "not in
  `AUTO_END_CARDS`" half patches an empty set, because `awaiting_merge` being in the real one is exactly what this
  run registers.
- Repair P2 (code review, merge gate): the typed `/merge` must reach the open merge card even when a goal-draft card
  is open beside it — `screen_slash_state` reads `draft` then, and the palette used to refuse the line as out of
  state although the card's own button merged. `test_regression_a_typed_merge_reaches_the_card_beside_an_open_goal_draft`
  (`MergeCardDraftShell`, the third whole-app walk, the repair's own regression) drives Enter in the real chat input
  with both cards open; `submit_verdict` judges the open card as its own state.
"""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# imported first for its side effect: the offline wheelhouse (ZPLAN_TEST_WHEELHOUSE) joins `sys.path` before the
# guarded imports below, so this module sees Textual and Rich there on a host that installs neither.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_text

from test_tui_draft_card import DraftCardShell, GOAL_DRAFT, MISSING_REASON, _main_method, _Screen
from test_tui_chat import chat_band
from test_tui_milestones import MilestoneShell

from terminal_planner.delivery import Delivery  # no Textual or Rich at import: the module-level `TASKS` needs it bare

try:
    from textual.widgets import Button, Input, Static
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import cards
    from terminal_planner.tui import strings
    from terminal_planner.tui.controller import Controller, Outcome, Row, Token
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    Button = Input = Static = ui = cards = strings = Controller = Outcome = Row = Token = None

HAVE = HAVE_TEXTUAL and ui is not None and cards is not None and strings is not None
MERGE_KEY = "merge:r1:M1:1"  # the joint example: plan r1, stage M1, attempt 1


def receipt_pattern(stage="M1"):
    """The closed card's receipt as a pattern: `card.merge_done` with a `HH:MM` time (A2's «✓ M1 merged into main
    HH:MM»), read from the catalog so the check holds whatever language the runner's UI uses."""
    filled = strings.text("card.merge_done", stage=stage, time="00:00")
    return re.escape(filled).replace("00:00", r"\d\d:\d\d")


def awaiting_row(milestone="M1", attempt=1, delivery="awaiting_merge"):
    """One plan row of the joint example: the stage's attempt ended and waits for its merge. `delivery="none"` is
    the recovery state a cut export or a reopen leaves: the row is already `awaiting_merge` (a done attempt), but
    the accepted result itself is still unexported."""
    token = Token(milestone=milestone, plan_revision=1, attempt=attempt, run_id="fixture-1", status="finished",
                  outcome="done", delivery=delivery)
    return Row(id=milestone, title=milestone, state="awaiting_merge", text="waiting to merge", token=token)


def tasks_line(done, total):
    """U2 (delivery.py `tasks_lines` -> card_kinds `MERGE_TASKS`): the tasks line as the real producer writes it, with
    `done` of `total` tasks done, so the card's parser is fed the producer's own output, never a hand-typed line."""
    manifest = {"tasks": [{"status": "done" if index < done else "open"} for index in range(total)],
                "amendments": []}
    return Delivery.tasks_lines(SimpleNamespace(runs=SimpleNamespace(manifest=lambda row: manifest)), None)[0]


def end_view(body):
    """An attempt's end view as the merge card reads it: the body the tasks line lives in (`Delivery.tasks_lines`'
    line)."""
    return SimpleNamespace(state="awaiting_merge", body=tuple(body))


def exported_end(milestone="M1", attempt=1, body=None):
    """The end view the export of an accepted attempt answers with (`controller.open_run` after `Delivery.end`
    exported it): its `token` is the exported attempt's, so this is the token a recovery click must merge."""
    token = Token(milestone=milestone, plan_revision=1, attempt=attempt, run_id="fixture-1", status="finished",
                  outcome="done", delivery="awaiting_merge")
    return SimpleNamespace(state="awaiting_merge", token=token, body=tuple(body or (tasks_line(2, 3),)))


TASKS = end_view([tasks_line(2, 3), "  Changes relative to the base abc1234:"])  # the joint example's line


# The unit half: the source, the two commands and the verdict, on stand-in screens. ---------------------------------


def _app_method(name):
    """The real `ZplanApp` method `name`, copied onto the stand-in app (a stub without Textual/Rich, exactly as
    `_main_method` does for the screen's own methods)."""
    def missing(self, *args, **kwargs):  # pragma: no cover - reached only where the tests skip anyway
        raise AssertionError(MISSING_REASON)
    return missing if ui is None else getattr(ui.ZplanApp, name)


class _App:
    """The app side the merge card touches: the pending guard, the controller calls and the status notes. `deliver`
    queues the hand-over instead of running it (`flush` runs it, as the app's own pump does — never inside a
    render), and the controller records every call; an answer is queued by the test (`answer_run`/`answer_merge`).
    `merge` keeps the engine's own guard: an unexported token is refused
    («Merge is possible only for an exported result»), so the recovery click has to export first."""

    pending_text = _app_method("pending_text")
    begin_pending = _app_method("begin_pending")
    guard_pending = _app_method("guard_pending")
    clear_pending = _app_method("clear_pending")

    def __init__(self, rows=()):
        self.pending = None
        self.chat_note = ""
        self.selected = None
        self.changed_calls = 0
        self.refreshed = 0
        self.opens = []        # controller.open_run calls (the one counts read of a card key)
        self.merges = []       # controller.merge calls (the token each merge was asked for)
        self.milestones = []   # action_open_milestone: the run screen the typed line falls back to
        self.deliveries = []   # queued hand-overs, run by `flush`
        self._run_answer = None
        self._merge_answer = None
        self.controller = SimpleNamespace(open_run=self._open_run, merge=self._merge)
        self._rows = tuple(rows)
        # the plan revision the card keys carry (0.5.2 corrective): a test moves it to a later revision
        self.snapshot = SimpleNamespace(rows=self._rows, row=self._row, version=1)

    def _row(self, milestone):
        return next((row for row in self._rows if row.id == milestone), None)

    def rows(self):
        return self._rows

    def deliver(self, handler):
        def done(outcome, error):
            self.deliveries.append((handler, outcome, error))
        return done

    def flush(self):
        """Run the queued deliveries, as the app's pump would once the worker answered."""
        while self.deliveries:
            handler, outcome, error = self.deliveries.pop(0)
            handler(outcome, error)

    def _open_run(self, milestone, done):
        self.opens.append(milestone)
        if self._run_answer is not None:
            done(*self._run_answer)
        return True

    def _merge(self, token, done):
        self.merges.append(token)
        if token.delivery != "awaiting_merge":  # the engine's own guard: an unexported attempt is refused
            done(Outcome("refused",
                         lines=("Not done: Merge is possible only for an exported result.",)), None)
            return True
        if self._merge_answer is not None:
            done(*self._merge_answer)
        return True

    def answer_run(self, outcome, error=None):
        """Answer the counts read (every later `open_run`) with `outcome`."""
        self._run_answer = (outcome, error)

    def answer_merge(self, outcome, error=None):
        self._merge_answer = (outcome, error)

    def action_open_milestone(self):
        self.milestones.append(True)

    def request_refresh(self):
        self.refreshed += 1

    def changed(self):
        self.changed_calls += 1

    def say_note(self, line):
        self.chat_note = line


class _Merge(_Screen):
    """The card-contract stand-in with the merge card's own methods on it (the real ones run); only the canvas'
    `open_diff_tab` is doubled, so the selection a `/diff` makes is what the assertions read."""

    merge_counts = _main_method("merge_counts")
    merge_counts_arrived = _main_method("merge_counts_arrived")
    merge_card_at = _main_method("merge_card_at")
    merge_later = _main_method("merge_later")
    merge_card_ref = _main_method("merge_card_ref")
    action_merge = _main_method("action_merge")
    merge_exported = _main_method("merge_exported")
    merge_run = _main_method("merge_run")
    action_merge_diff = _main_method("action_merge_diff")
    merge_diff_exported = _main_method("merge_diff_exported")
    merge_settled = _main_method("merge_settled")
    render_card_sources = _main_method("render_card_sources")

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.merge_view = {}
        self.merge_times = {}
        self.merge_overlap = {}
        self.diffs = 0

    def render_state(self):
        """The re-render the app's own pump runs when a delivery arrived: here it is the sources' own render."""
        self.render_card_sources()

    def open_diff_tab(self):
        self.diffs += 1


@unittest.skipUnless(HAVE, MISSING_REASON)
class MergeCardTests(unittest.TestCase):
    """A1, A2, A3 and A4 at unit level: the source, the two commands and the verdict, with the real methods running
    on a stand-in screen whose app answers the controller calls when the test flushes them."""

    def setUp(self):
        # The stand-in screen serves the merge kind only (card contract: other kinds' sources need a real app).
        sources = patch.dict(ui.CARD_SOURCES, {"merge": ui.CARD_SOURCES["merge"]}, clear=True)
        sources.start()
        self.addCleanup(sources.stop)

    @staticmethod
    def show(screen, answer=None):
        """Render the sources once, with only the merge kind registered (the assertions then read this card alone)."""
        if answer is not None:
            screen.app.answer_run(*answer)
        with patch.dict(ui.CARD_SOURCES, {"merge": ui.merge_card_source}, clear=True):
            screen.render_card_sources()
        screen.app.flush()  # the counts read's delivery, as the app's pump would run it
        return screen

    def test_a1_the_source_shows_one_card_per_awaiting_merge_row_with_the_attempt_tasks_counts(self):
        """A1 (joint example): one `awaiting_merge` row of M1 attempt 1 under plan r1, whose EndView carries
        «Tasks: 2/3 done», gives exactly one open card `merge:r1:M1:1` titled «M1 ready» and reading «2 of 3
        tasks …», with the buttons «merge» and «see the changes»; a row of another state, and an
        `awaiting_merge` row without an attempt at all, give none."""
        app = _App([awaiting_row(), Row(id="M2", title="M2", state="running", text="running"),
                    Row(id="M3", title="M3", state="awaiting_merge", text="waiting to merge", token=None)])
        screen = self.show(_Merge(app), answer=(Outcome("end", data=TASKS), None))
        self.assertEqual(list(screen.card_specs), [MERGE_KEY])
        spec = screen.card_specs[MERGE_KEY]
        self.assertEqual(app.opens, ["M1"])  # the read names the card's own stage
        self.assertEqual(spec.title, strings.text("card.merge_title", stage="M1"))
        self.assertEqual(spec.text, strings.text("card.merge_text", done="2", total="3"))
        self.assertEqual([label for label, _ in spec.buttons],
                         [strings.text("card.merge_yes"), strings.text("card.merge_changes")])
        self.assertEqual([command for _, command in spec.buttons], ["/merge", "/diff"])
        self.assertIsNone(spec.done)
        self.assertIsNone(spec.hint)  # the shared `card.hint` line is built from the two buttons
        self.assertEqual(screen.box.mounted[-1].spec, spec)

    def test_a1_the_card_is_read_once_per_key_and_stays_bare_without_a_counts_line(self):
        """A1's other half and the read invariant: before the answer the card is the bare one
        (`card.merge_text_bare`, no counts) and the engine is asked once per key however often the sources render;
        a view without a tasks line leaves it bare too, and never asks a second time."""
        app = _App([awaiting_row()])
        screen = self.show(_Merge(app))  # the read is queued but not answered yet
        self.assertEqual(screen.card_specs[MERGE_KEY].text, strings.text("card.merge_text_bare"))
        self.assertEqual(app.opens, ["M1"])
        screen.render_card_sources()
        screen.render_card_sources()
        self.assertEqual(app.opens, ["M1"])  # one read for this key, whatever the refreshes
        patchy = _App([awaiting_row()])
        bare = self.show(_Merge(patchy), answer=(Outcome("end", data=end_view(["  Changes: none"])), None))
        self.assertEqual(patchy.opens, ["M1"])
        self.assertEqual(bare.card_specs[MERGE_KEY].text, strings.text("card.merge_text_bare"))
        bare.card_specs.clear()  # a fresh key is a fresh read, never a second one for the observed line
        self.assertNotIn(MERGE_KEY, bare.card_specs)

    def test_a1_a2_a4_a_new_revision_shows_a_new_card_with_its_own_counts_and_still_names_stage_m1(self):
        """A1/A2/A4 (regression, i3c corrective — reviewer conflict: the milestone card keys lacked the plan
        revision): the revision is part of `merge_key`, so a card the owner closed under r1 must not suppress the
        same stage's card under r2 — after the close and the new revision an *open* `merge:r2:M1:1` shows — and the
        r2 card reads its own counts (a second `open_run` read, keyed `merge:r2:M1:1`), never r1's cached numbers.
        A4: the r2 key still names stage M1, so `/merge` and `/diff` act on it (a typed `/diff`, key None, keeps the
        canvas diff tab's own meaning).

        Verified on the old layout (A5): reverting the key line to `merge:%s:%s` (dropping `r<version>`) makes both
        revision cards collapse onto `merge:M1:1`, so the closed r1 receipt suppresses r2's open card and the r2 read
        is never made — this test then fails on `merge:r2:M1:1`."""
        app = _App([awaiting_row()])
        screen = self.show(_Merge(app), answer=(Outcome("end", data=TASKS), None))
        self.assertEqual(list(screen.card_specs), ["merge:r1:M1:1"])
        self.assertEqual(screen.card_specs["merge:r1:M1:1"].text,
                         strings.text("card.merge_text", done="2", total="3"))
        # the owner closes r1's card; the approved revision r2 leaves the same stage attempt awaiting its merge
        screen.close_card("merge:r1:M1:1", "✓ M1 merged into main 12:00")
        app.snapshot.version = 2
        app.answer_run(Outcome("end", data=end_view([tasks_line(1, 2)])), None)
        screen.render_card_sources()
        app.flush()
        screen.render_card_sources()
        r2 = screen.card_specs["merge:r2:M1:1"]
        self.assertIsNone(r2.done)  # r2's card is an open decision, not suppressed by the closed r1 receipt
        self.assertEqual(r2.text, strings.text("card.merge_text", done="1", total="2"))  # its own numbers
        self.assertEqual(app.opens, ["M1", "M1"])  # one read per key: the r2 key reads its own view
        # A4: /diff on the r2 key selects stage M1 and opens the canvas tab; a typed /diff keeps its own meaning
        app.selected = "M2"
        ui.COMMAND_ACTIONS["/diff"](screen, "", "merge:r2:M1:1")
        self.assertEqual((app.selected, screen.diffs), ("M1", 1))
        ui.COMMAND_ACTIONS["/diff"](screen, "", None)
        self.assertEqual((app.selected, screen.diffs), ("M1", 2))
        # A4: /merge on the r2 key merges M1's own attempt and closes the r2 card
        app.answer_merge(Outcome("integrated", lines=("Merged: M1 → main.",)))
        ui.COMMAND_ACTIONS["/merge"](screen, "", "merge:r2:M1:1")
        app.flush()
        self.assertEqual([(token.milestone, token.attempt) for token in app.merges], [("M1", 1)])
        self.assertRegex(screen.card_specs["merge:r2:M1:1"].done, "^%s$" % receipt_pattern())

    def test_a2_the_merge_success_closes_the_card_and_a_refusal_leaves_it_open(self):
        """A2: the card's merge carries the row's own attempt token; the engine's `integrated` verdict publishes the
        engine's own line on the status line above the chat and closes the card as `card.merge_done`, while a
        refusal puts the engine's line there and leaves the card open. The pending line clears either way — this is its answer. The
        command reaches the engine the same way whether it is the card's own «merge» button (its card's key) or the
        same `/merge` typed in the chat (no key: the newest open merge card is the one it names)."""
        ways = (MERGE_KEY, None)  # the button's card key, then the same command typed in the chat
        for verdict, closes in ((Outcome("integrated", lines=("Merged: M1 → main.",)), True),
                                (Outcome("conflict", lines=("Not done: merge conflict in main.",)), False)):
            for way in ways:
                with self.subTest(kind=verdict.kind, way=way):
                    app = _App([awaiting_row()])
                    app.answer_merge(verdict)
                    screen = self.show(_Merge(app), answer=(Outcome("end", data=TASKS), None))
                    ui.COMMAND_ACTIONS["/merge"](screen, "", way)
                    app.flush()  # the merge's own verdict
                    self.assertEqual([token.run_id for token in app.merges], ["fixture-1"])
                    self.assertEqual(app.merges[0].attempt, 1)
                    self.assertIsNone(app.pending)  # the verdict cleared the pending line
                    self.assertEqual(app.refreshed, 1)
                    if closes:
                        self.assertRegex(screen.card_specs[MERGE_KEY].done, "^%s$" % receipt_pattern())
                        # i3c repair: the modal-less settle publishes the engine's own success line, so a refusal
                        # that preceded it is not left on the status line
                        self.assertEqual(app.chat_note, verdict.lines[0])
                    else:
                        self.assertIsNone(screen.card_specs[MERGE_KEY].done)
                        self.assertEqual(app.chat_note, verdict.lines[0])

    def test_d4b_an_overlap_refusal_turns_the_card_red_naming_the_files_and_later_closes_it_without_merging(self):
        """D4b: the engine's `overlap` verdict (lines = the refusal, then the files in the way) leaves the card open as
        the red card that names them with «merge later» and «show the differences»; `/merge later` closes it as a receipt
        and asks the engine for nothing."""
        app = _App([awaiting_row()])
        app.answer_merge(Outcome("overlap", lines=("Not merged: …", ".env", "src/a.py")))
        screen = self.show(_Merge(app), answer=(Outcome("end", data=TASKS), None))
        ui.COMMAND_ACTIONS["/merge"](screen, "", MERGE_KEY)
        app.flush()
        spec = screen.card_specs[MERGE_KEY]
        self.assertTrue(spec.alarm)
        self.assertIsNone(spec.done)
        self.assertIn(".env, src/a.py", spec.text)
        self.assertEqual([label for label, _ in spec.buttons],
                         [strings.text("card.merge_later"), strings.text("card.merge_diff")])
        self.assertEqual([command for _, command in spec.buttons], ["/merge later", "/diff"])
        ui.COMMAND_ACTIONS["/merge"](screen, "later", MERGE_KEY)
        app.flush()
        self.assertEqual(len(app.merges), 1)  # «merge later» merged nothing
        self.assertIn("the branch is kept", screen.card_specs[MERGE_KEY].done)

    def test_a4_a_second_merge_while_one_is_pending_is_refused_and_the_engine_is_asked_once(self):
        """A4: the first merge is in flight (its verdict has not come back), so the pending guard refuses the
        second `/merge` with its own line and `controller.merge` stays at one call; the verdict then clears the
        pending line and closes the card, so the decision is gone with it."""
        app = _App([awaiting_row()])
        screen = self.show(_Merge(app), answer=(Outcome("end", data=TASKS), None))
        ui.COMMAND_ACTIONS["/merge"](screen, "", MERGE_KEY)  # in flight: no answer was queued for it
        self.assertIsNotNone(app.pending)
        app.chat_note = ""
        ui.COMMAND_ACTIONS["/merge"](screen, "", MERGE_KEY)
        self.assertEqual(len(app.merges), 1)
        self.assertIn("Already in progress", app.chat_note)
        screen.merge_settled(MERGE_KEY, "M1", Outcome("integrated", lines=("Merged: M1 → main.",)), None)
        self.assertIsNone(app.pending)
        self.assertEqual(len(app.merges), 1)
        self.assertRegex(screen.card_specs[MERGE_KEY].done, "^%s$" % receipt_pattern())

    def test_a3_the_card_diff_selects_its_own_stage_and_a_typed_line_keeps_its_own_meaning(self):
        """A3: `/diff` from the card selects the card's stage before the existing `open_diff_tab()`, so the canvas
        and the panel agree on what was inspected, and asks for the repaint that shows the new selection (as the
        pane keys' own `action_select` does); a typed `/diff` (no card key) leaves the selection alone, and a typed
        `/merge` with no merge card open keeps the run screen's own path (today's `/merge`)."""
        app = _App([awaiting_row(), awaiting_row("M2")])
        screen = self.show(_Merge(app), answer=(Outcome("end", data=TASKS), None))
        app.selected = "M2"
        ui.COMMAND_ACTIONS["/diff"](screen, "", MERGE_KEY)
        self.assertEqual((app.selected, screen.diffs, app.changed_calls), ("M1", 1, 1))
        ui.COMMAND_ACTIONS["/diff"](screen, "", None)
        # a typed line keeps today's selection, and the repaint it asks for is not its business
        self.assertEqual((app.selected, screen.diffs, app.changed_calls), ("M1", 2, 1))
        other = _Merge(_App([awaiting_row()]))
        ui.COMMAND_ACTIONS["/merge"](other, "", None)  # no merge card open
        self.assertEqual((other.app.milestones, other.app.merges), ([True], []))

    def test_a2_a3_a_recovered_unexported_attempt_is_exported_before_the_merge_and_the_diff(self):
        """The recovery state a cut export or a reopen leaves -- the row already `awaiting_merge` while the accepted
        attempt is still unexported (`delivery == "none"`): «merge» and «see the changes» complete the export
        their own click owes (`controller.open_run`, the owner's arrival, exactly as [o] reads the view) and then act
        on the token that view produced. The unexported token itself is refused by the engine, so without this the
        click merged nothing (the card stayed open) and `runs.diff` could not open the tab; the card source itself
        stays read-only and shows the bare text until the export runs. The export's view is also where the card's
        counts come from.

        Interpretation: a refresh never exports (`QuitSafetyTests`' own open export must stay the owner's arrival),
        so the counts of an unexported attempt can only arrive with this click; the card is `card.merge_text_bare`
        until it does."""
        app = _App([awaiting_row(delivery="none")])
        app.answer_run(Outcome("end", data=exported_end()))
        app.answer_merge(Outcome("integrated", lines=("Merged: M1 → main.",)))
        screen = self.show(_Merge(app))
        self.assertEqual(screen.card_specs[MERGE_KEY].text, strings.text("card.merge_text_bare"))
        self.assertEqual(app.opens, [])  # the read-only source exported nothing
        ui.COMMAND_ACTIONS["/merge"](screen, "", MERGE_KEY)  # A2: one click on «merge»
        app.flush()
        self.assertEqual(app.opens, ["M1"])  # the click completed the export first
        self.assertEqual([token.delivery for token in app.merges], ["awaiting_merge"])  # ... and merged its token
        self.assertIsNone(app.pending)
        self.assertRegex(screen.card_specs[MERGE_KEY].done, "^%s$" % receipt_pattern())
        self.assertEqual(app.chat_note, "Merged: M1 → main.")
        # A3: «see the changes» on the same state exports first, then opens the existing diff tab
        diff_app = _App([awaiting_row(delivery="none")])
        diff_app.answer_run(Outcome("end", data=exported_end()))
        diff_screen = self.show(_Merge(diff_app))
        ui.COMMAND_ACTIONS["/diff"](diff_screen, "", MERGE_KEY)
        diff_app.selected = "M2"  # the owner moves the selection while the export is still in flight
        diff_app.flush()
        self.assertEqual((diff_app.opens, diff_screen.diffs, diff_app.selected), (["M1"], 1, "M1"))
        self.assertEqual(diff_screen.merge_view[MERGE_KEY], (2, 3))  # the export's view is where the counts come from

    def test_a2_a_recovered_merges_export_of_another_attempt_is_refused_and_the_engine_is_not_asked(self):
        """The recovery click's export reads the *latest* attempt: a view whose token no longer names the clicked
        attempt (a revision or a run that moved under the click) is refused as the merge's failure — the engine is
        never asked to merge the wrong attempt, the pending line clears and the changed state is on the status line."""
        app = _App([awaiting_row(delivery="none")])
        app.answer_run(Outcome("end", data=exported_end(attempt=2)))  # the stage moved to a newer attempt
        screen = self.show(_Merge(app))
        ui.COMMAND_ACTIONS["/merge"](screen, "", MERGE_KEY)
        app.flush()
        self.assertEqual(app.opens, ["M1"])
        self.assertEqual(app.merges, [])  # never the other attempt's token
        self.assertIsNone(app.pending)  # the failure path settled the click
        self.assertEqual(app.chat_note, "Not done: " + ui.MOVED)
        self.assertEqual(app.refreshed, 1)
        self.assertEqual(screen.card_specs[MERGE_KEY].done, None)  # the card stays an open decision

    def test_a2_a_recovered_merges_export_that_is_not_an_end_settles_without_unpacking_it(self):
        """The recovery click's export can answer with a non-`end` outcome — the latest attempt still runs (an
        `active` view carrying a `Token`), no run at all (`none`), or a refused export (`end` with no view). Each is
        the merge's failure settlement (status note, pending cleared, refresh), never unpacked as a view: a `Token`
        has no `.token`, so the click must not raise and must not merge anything."""
        for verdict in (Outcome("active", data=Token(milestone="M1", plan_revision=1, attempt=1, run_id="fixture-1",
                                                      status="running", outcome=None, delivery="none")),
                        Outcome("none", lines=("M1: no runs.",)),
                        Outcome("end")):
            with self.subTest(kind=verdict.kind):
                app = _App([awaiting_row(delivery="none")])
                app.answer_run(verdict)
                screen = self.show(_Merge(app))
                ui.COMMAND_ACTIONS["/merge"](screen, "", MERGE_KEY)
                app.flush()
                self.assertEqual(app.merges, [])
                self.assertIsNone(app.pending)
                self.assertTrue(app.chat_note)
                self.assertEqual(app.refreshed, 1)


# The whole-app half: A1 at both sizes, and A2/A3/A5 in one 120x40 walk. ---------------------------------------------


@unittest.skipUnless(HAVE, MISSING_REASON)
class MergeCardShell(MilestoneShell):
    """The milestone shell with the stage-done card: the fixture plan approved, M1 run to its awaiting-merge end —
    where the card, not the end screen, is what the shell shows."""

    def main(self):
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def card(self):
        """The newest card in the conversation, or None."""
        cards = list(self.main().card_widgets.values())
        return cards[-1] if cards else None

    async def counted_card(self, pilot, done="1", total="1", timeout=20.0):
        """The merge card of M1 once its counts arrived from M1's own attempt (the fixture plan's M1 carries one
        task, so its tasks line is «Tasks: 1/1 done»)."""
        text = strings.text("card.merge_text", done=done, total=total)
        await self.until(pilot, lambda: self.card() is not None and self.card().spec.key.startswith("merge:r1:M1:")
                         and self.card().spec.text == text, timeout)
        await pilot.pause(0.3)
        return self.card()

    async def choose(self, pilot, command):
        """Press the card button that carries the slash command `command`."""
        button = next(widget for widget in self.card().query(Button) if widget.command == command)
        await pilot.click(button)
        await pilot.pause(0.3)

    def assert_card_under_the_chat(self, card, size):
        """A1: the card is an entry of the conversation inside the chat pane, and its title and both buttons are
        drawn (i3-chat-inline: cards live in the history, not in a slot under it)."""
        main = self.main()
        chat, pane = main.query_one("#chat"), main.query_one("#chat-pane")
        self.assertIs(card.parent, chat, size)
        self.assertGreater(card.region.height, 0, size)
        self.assertLessEqual(card.region.bottom, pane.region.bottom, size)
        shown = screen_text(self.app)
        self.assertIn(strings.text("card.merge_title", stage="M1"), shown, size)
        for label in (strings.text("card.merge_yes"), strings.text("card.merge_changes")):
            self.assertIn(label, shown, size)

    @staticmethod
    def counting_merge(calls):
        """A `Controller.merge` spy: records the token and still merges, so a merge that must not run is caught by
        the empty list and one that must is the recorded call."""
        real = Controller.merge

        def spy(controller, token, done):
            calls.append(token)
            return real(controller, token, done)
        return spy

    async def test_a1_a2_a3_a5_the_card_is_the_decision_the_run_screen_waits_behind_and_both_buttons_work(self):
        """A1 at 120x40: the run ends `done, waiting to merge` with **no** run screen popping — the card under the
        chat reads «M1 ready» and the counts of the attempt's own tasks line (the fixture's «1 of 1 tasks …»), with
        the buttons «merge» and «see the changes». A5: [o] on the same row still opens the run screen with its
        merge action. A3: «see the changes» selects M1 and opens its diff as a canvas tab. A2: «merge» calls
        `controller.merge` once with the row's attempt, shows no modal, and the card becomes the receipt."""
        self.approve(running=False)
        calls = []
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            card = await self.counted_card(pilot)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")  # A1: no run screen popped
            self.assert_card_under_the_chat(card, (120, 40))
            # the counts are the attempt's own tasks line, read and drawn (the card wraps its own width, so the
            # whole text is checked on the spec and its counts clause on the screen). i9-look: the card lives in
            # the 38%-wide chat pane, so the clause wraps inside it and `screen_text` interleaves the plan pane's
            # cells; `chat_band` reads the chat pane's own rows.
            self.assertEqual(card.spec.text, strings.text("card.merge_text", done="1", total="1"))
            self.assertIn(card.spec.text.split(".")[0] + ".", chat_band(self.app))
            self.assertEqual([command for _, command in card.spec.buttons], ["/merge", "/diff"])
            # A5: [o] still opens the end screen, whose own «merge» button is untouched
            await self.panel(pilot)
            await self.command(pilot, "/attempt")
            await self.run_button(pilot, "merge")
            await pilot.press("escape")
            await pilot.pause(0.3)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")
            self.assertIsNotNone(self.card())  # the decision stayed while the owner looked at the modal
            # A3: the card's «see the changes» selects its stage and opens the existing diff tab
            await self.choose(pilot, "/diff")
            right = self.main().query_one("#right")
            tab_id = self.main().view_tabs[0]
            self.assertEqual(right.get_tab(tab_id).label.plain, strings.text("canvas.diff_tab", stage="M1"))
            self.assertEqual(right.active, tab_id)
            # the pane's body is a `Syntax` (viewer.diff_view): its own text is `code`
            self.assertIn("+Fixture driver change for milestone M1",
                          right.get_pane(tab_id).query_one(Static).content.code)
            self.assertEqual(self.app.selected, "M1")
            # A2: the button merges that attempt with no confirmation modal
            with patch.object(Controller, "merge", self.counting_merge(calls)):
                await self.choose(pilot, "/merge")
                await self.until(pilot, lambda: self.card() is not None and self.card().spec.done)
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")
                self.assertRegex(self.card().spec.done, "^%s$" % receipt_pattern())
                self.assertEqual([type(widget).__name__ for widget in self.card().compose()], ["Static"])
                self.assertEqual(len(calls), 1)
                self.assertEqual((calls[0].milestone, calls[0].attempt), ("M1", 1))
        self.assertEqual(self.stored()["runs"][0]["delivery"], "integrated")

    async def test_a1_at_80x24_the_stage_done_card_is_visible_under_the_chat(self):
        """A1's narrow half: the same stage, waiting for its merge (made by the line UI before the shell opens, so
        the shell has nothing to drive), shows its card under the chat at 80x24 — where the shell shows one pane at
        a time and the card's own `show_chat()` is what brings the chat (and the card) into view — with the counts
        read from the attempt and the title and both buttons drawn."""
        self.approve(running=False)
        self.plain("g\ny\nl\nq\n")  # the stage done and waiting for its merge, made by the line UI
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            card = await self.counted_card(pilot)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")  # no run screen popped here either
            self.assert_card_under_the_chat(card, (80, 24))
            self.assertEqual(self.card().spec.text, strings.text("card.merge_text", done="1", total="1"))


@unittest.skipUnless(HAVE, MISSING_REASON)
class MergeCardDraftShell(DraftCardShell):
    """The input-submission regression (code-review finding P2): a goal-draft card and the stage-done merge card are
    open at once, so `screen_slash_state` reads `draft` (the i3a precedence) while the merge card waits. The typed
    `/merge` must still reach that card — the failure this repair fixes — while the draft's own commands stay in
    reach and `guard_pending` keeps its refusal.

    Interpretation: the button/typed-line divergence of the i3a repair is the same class of bug, so the fix is
    judged as its own state (`submit_verdict`) rather than by moving the single `draft` precedence; the draft card
    staying open with `screen_slash_state` still `draft` is what pins "draft commands preserved" (the palette the
    input uses submits `/plan`), and a second typed `/merge` before the first answers is the guard's own refusal."""

    def merge_card(self):
        """The merge card in the conversation (a draft card may sit beside it)."""
        cards = self.main().card_widgets
        return next((card for key, card in cards.items() if key.startswith("merge:r1:M1:")), None)

    def draft_card(self):
        """The goal-draft card in the conversation, or None."""
        cards = self.main().card_widgets
        return next((card for key, card in cards.items() if key.startswith("draft:")), None)

    async def both_cards(self, pilot, timeout=20.0):
        """Both decisions of the walk: the goal-draft card (from the retained history) and the stage-done merge card
        with the counts of M1's own attempt (the fixture plan's M1 carries one task, «Tasks: 1/1 done»)."""
        text = strings.text("card.merge_text", done="1", total="1")
        await self.until(pilot, lambda: (self.draft_card() is not None and self.merge_card() is not None
                                         and self.merge_card().spec.text == text), timeout)
        await pilot.pause(0.3)

    counting_merge = staticmethod(MergeCardShell.counting_merge)

    async def test_regression_a_typed_merge_reaches_the_card_beside_an_open_goal_draft(self):
        """P2: with a goal-draft card open, `screen_slash_state` is `draft` and the typed `/merge` was refused by
        the palette's state gate before it ever reached the merge card, while the card's own button merged. Here the
        typed line (Enter in the real chat input) merges the card's own attempt exactly once with no modal, the
        card becomes the receipt, the draft card is still an open decision (`draft` stays the state, so the palette
        still submits `/plan`), and a second `/merge` typed while the first is still in flight is refused by the
        merge's own `guard_pending` (one `controller.merge` call)."""
        calls = []
        # a draft written after the plan exists names plan r1 in its identity (R-A: a stale draft opens no card)
        store = self.seed_goal_draft(identity=[1, {"status": "approved", "override": False}])
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True, store=store) as pilot:
            await self.settled(pilot)
            await self.card_shown(pilot)
            await self.begin_run(pilot)  # K1a: a typed `/run` starts M1 beside the open draft card, as `g` did
            await self.until(pilot, lambda: (self.app.selection() is not None
                                             and self.app.selection().state == "awaiting_merge"), 20.0)
            await self.both_cards(pilot)
            state = ui.screen_slash_state(self.app)
            self.assertEqual(state, "merge")  # R-B: the merge wait outranks the open draft card...
            self.assertIsInstance(ui.palette.submit("/merge", state), ui.palette.Submitted)  # ...so `/merge` is
            with patch.object(Controller, "merge", self.counting_merge(calls)):
                await self.send(pilot, "/merge")
                await self.until(pilot, lambda: self.merge_card() is not None and self.merge_card().spec.done)
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")  # no modal popped
                self.assertEqual(len(calls), 1)
                self.assertEqual((calls[0].milestone, calls[0].attempt), ("M1", 1))
                self.assertRegex(self.merge_card().spec.done, "^%s$" % receipt_pattern())
                self.assertIsNotNone(self.draft_card())  # the other decision is untouched
                # the merge answered: a second typed /merge finds no open card and keeps today's refusal
                await self.send(pilot, "/merge")
                self.assertEqual(len(calls), 1)
                note = strings.text("note.not_now", name="/merge")
                await self.until(pilot, lambda: note in self.flat())  # the refusal note lands a frame later
                self.assertIn(note, self.flat())
        self.assertEqual(self.stored()["runs"][0]["delivery"], "integrated")


if __name__ == "__main__":
    unittest.main()
