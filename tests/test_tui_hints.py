"""C3: every canvas hint names a step that works in that state (walk W3, W9, W12, W15): H1-H5, each failing on the
code before C3; only H4 mounts a (bare) modal.

Interpretations: H1 drops the label word only when it is the command's own name (`[d] diff` -> `/diff`), else keeps
it after ` — `, for "Next:" lines only. H3 pins the slash state to `plan_ready` (the state the title reads). H4:
«configure» and «later» are one Tab/→ step after the button before them. H5: the texts are the real `Delivery.home`
and `Delivery.next_step` output; "its own label word" = a lowercase word right after the command.
"""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL

from terminal_planner import delivery
from terminal_planner.delivery import Delivery
from terminal_planner.tui import strings
from test_tui_auto_plan_card import HAVE, MISSING_REASON, snapshot_at

try:
    from textual.app import App
    from terminal_planner.tui import app as ui, modals, slash
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    App = ui = modals = slash = None

APPROVE = "Next: [p] plan — approve or revise"


def home_next_lines():
    def home(plan, fresh=True):
        none = lambda *args: None  # noqa: E731
        stand_in = SimpleNamespace(plan=lambda: plan, authority=SimpleNamespace(fresh=lambda: fresh), runs=SimpleNamespace(overview=list), planner_panel=none,
                                   journal=lambda record=None: (), overview_lines=lambda *args: [], focus_item=none,
                                   slots=none, g_id=none, tail_item=none, g_item=none, busy=none,
                                   panel_flow=lambda record: ((), None), row=none)
        return [line for line in Delivery.home(stand_in).lines if line.startswith("Next:")]
    goal = {"goal": "Add a README paragraph", "version": 1, "run_id": None}
    lines = home(None)
    for status in delivery.PLAN_STATUS:  # "approved" with no stage left: all merged
        lines += home(dict(goal, status=status))
    lines += home(dict(goal, status="proposed"), fresh=False)  # C5: a stale proposal
    states = ("running", "ready", "done") + delivery.CHECK + tuple(delivery.END_ACTIONS)
    return lines + ["Next: " + Delivery.next_step({"state": state, "id": "M1", "record": None}) for state in states]


@unittest.skipUnless(HAVE, MISSING_REASON)
class HintTests(unittest.TestCase):
    def test_h1_h2_a_letter_key_becomes_the_command_and_a_new_goal_goes_to_the_architect(self):
        for line, shown in (("Next: [w] watch M1", "Next: /attempt — watch M1"), ("Next: [d] diff", "Next: /diff"),
                            ("Next: [g] start M2", "Next: /run — start M2"),
                            (next(line for line in home_next_lines() if "merged" in line),
                             "Next: all stages are merged — write a new goal to the architect in the chat")):
            with self.subTest(line):
                self.assertEqual(ui.plan_tab_line(line), shown)

    def test_h3_where_the_architect_approves_the_canvas_does_not_wait_for_a_yes(self):
        for level, auto in (("auto", True), ("supervised", False), ("manual", False)):
            with self.subTest(level=level), patch.object(ui, "screen_slash_state", return_value="plan_ready"):
                snapshot = snapshot_at(level)
                self.assertIs(ui.plan_auto_approves(snapshot), auto)
                title, step = ui.canvas_title(SimpleNamespace(snapshot=snapshot)), ui.plan_tab_line(APPROVE, auto)
                self.assertEqual(title == strings.text("canvas.scheme_approve"), not auto)
                self.assertEqual("/approve" in step, not auto)
                self.assertEqual(step == strings.text("canvas.plan_next_auto"), auto)

    def test_c5_a_stale_proposal_names_revision_not_approval(self):
        """S1 home's Next line (fresh: unchanged), S2 the Plan tab line with auto False/True, S3 is `home_next_lines`
        above (H5 runs it). Interpretation: the Plan tab text is the task's example, verbatim."""
        lines = home_next_lines()
        self.assertIn(delivery.REVISE_NEXT, lines)
        self.assertEqual(delivery.REVISE_NEXT, "Next: [r] revise — the project changed after planning")
        self.assertIn(APPROVE, lines)
        for auto in (False, True):
            shown = ui.plan_tab_line(delivery.REVISE_NEXT, auto)
            self.assertEqual(shown, "Next: the project changed after planning — tell the architect to revise the plan")
            self.assertNotIn("/approve", shown)

    def test_h5_every_next_text_names_a_command_that_exists_and_no_label_after_it(self):
        names = {command.name for command in slash.COMMANDS}
        texts = [(line, False) for line in home_next_lines()] + [(APPROVE, True)]
        for language in ("en", "ru", "zh"):
            with patch.object(strings, "language", lambda: language):
                for line, auto in texts:
                    shown = ui.plan_tab_line(line, auto)
                    with self.subTest(language=language, line=line):
                        self.assertIsNotNone(shown)  # no letter key without a step
                        self.assertLessEqual(set(re.findall(r"/[a-z]+", shown)), names, shown)
                        plain = re.sub(r" → (?:install|log in|revise)", "", shown)  # a step of a button, not a label
                        self.assertNotRegex(plain, r"/[a-z]+ [a-z]", shown)  # `/attempt watch`, `/diff diff`

    def test_c7_n1_a_label_word_that_is_the_commands_own_name_is_dropped_in_any_line(self):
        self.assertEqual(ui.command_hints("Goal: x — [i] details"), "Goal: x — /details")
        self.assertEqual(ui.command_hints("Goal: x — [l] refresh login"), "Goal: x — /setup → log in")

    def decided(self, level, kind):
        """The note `ZplanApp.decide` says when the owner's decision came back as `kind`, on a stand-in app."""
        said = []
        outcome = SimpleNamespace(kind=kind)
        app = SimpleNamespace(
            controller=SimpleNamespace(approve_plan=lambda version, done: done(outcome, ""),
                                       override_plan=lambda version, reason, done: done(outcome, "")),
            deliver=lambda callback: callback, plan_approved=lambda version: None, progress=[], finish_note="x",
            snapshot=snapshot_at(level), approval_note=None, say_note=said.append, request_refresh=lambda: None,
            changed=lambda: None)
        ui.ZplanApp.decide(app, "override" if kind == "overridden" else "approve", 1, "reason")
        return said[0], app

    def test_c7_n2_where_zplan_starts_the_work_the_approval_notes_say_so(self):
        for kind in ("approved", "overridden"):
            for level in ("auto", "supervised", "manual"):
                note, _ = self.decided(level, kind)
                with self.subTest(kind=kind, level=level):
                    self.assertTrue(note.startswith("Plan r1 approved"), note)
                    starts = ui.autonomy.decide(level, "start") == "allow"
                    self.assertEqual("zplan starts the first stage." in note, starts, note)
                    self.assertEqual("/run" in note or "not started" in note, not starts, note)
        self.assertEqual(self.decided("auto", "approved")[0], "Plan r1 approved. zplan starts the first stage.")

    def test_c7_n3_once_a_run_of_the_approved_revision_started_the_approval_note_is_gone(self):
        note, app = self.decided("manual", "approved")
        app.run_note, app.plan_lines = note, (note,)  # said on the home and on the plan screen
        row = lambda token: SimpleNamespace(token=token)  # noqa: E731
        ui.ZplanApp.approval_note_over(app, SimpleNamespace(rows=(row(None),)))
        self.assertEqual((app.run_note, app.plan_lines), (note, (note,)))  # no run yet: the note stays
        ui.ZplanApp.approval_note_over(app, SimpleNamespace(rows=(row(SimpleNamespace(plan_revision=1)),)))
        self.assertEqual((app.run_note, app.plan_lines, app.approval_note), ("", (), None))


@unittest.skipUnless(HAVE_TEXTUAL and modals is not None, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required")
class BootstrapBarTests(unittest.IsolatedAsyncioTestCase):
    async def test_h4_the_bar_lists_the_keys_in_button_order_and_each_reaches_its_button(self):
        screen = modals.BootstrapScreen(SimpleNamespace(bootstrap=("Process profile",), present=False, form=object()))

        class Host(App):
            changed = lambda self: None  # noqa: E731  (what the modal's mount asks the app for)

            def on_mount(self):
                self.push_screen(screen)
        async with Host().run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            bar = screen.key_bar(100)
            keys = re.findall(r"\[([^\]]+)\] (\w+)", bar)
            self.assertEqual(keys, [("enter", "accept"), ("right", "configure"), ("tab", "later"), ("ctrl+q", "quit")])
            self.assertEqual(screen.focused.id, "bootstrap-accept")
            for key, button in keys[1:3]:
                await pilot.press(key)
                self.assertEqual(screen.focused.id, "bootstrap-" + button)
