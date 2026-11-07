"""D1: no line keeps describing a state that is over (soak of rc1: S4 the merge wait note, S7 the old plan card, S8 the
start hint). Stand-in screens and apps; the real `ZplanApp`/`MainScreen`/`Controller` methods run on them.

Interpretations: L1's wait note is the one `merge_wait_shown` wrote itself (a verdict line that replaced it stays);
L2's "until the new revision's snapshot" is a snapshot of another version, or one no longer proposed, and a failed
revision request gives the card back; L3 is the pending `starting M1…` line the owner's own start already sets, which
the Plan tab already hides `Next:` for, held while the architect's start tool runs and lifted when it fails."""

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401

from terminal_planner.tui import strings
from terminal_planner.tui.controller import Controller
from test_tui_approve_card import HAVE, MISSING_REASON, _Screen, _app_method, _main_method, proposal, ui


class _Merge:
    """The app double of the merge wait: the real note/wait methods, no modal and no screen."""
    merge_wait_shown = _app_method("merge_wait_shown")
    say_note = _app_method("say_note")
    screen = None
    screen_stack = ()

    def __init__(self):
        self.merge_waiting, self.run_note, self.plan_lines = None, "", ()

    def request_refresh(self):
        pass

    def changed(self):
        pass


class _Start:
    """The app double of an architect-started run: the real pending methods."""
    start_wait_shown = _app_method("start_wait_shown")
    begin_pending = _app_method("begin_pending")
    pending_text = _app_method("pending_text")
    confirm_pending = _app_method("confirm_pending")
    clear_pending = _app_method("clear_pending")

    def __init__(self):
        self.pending, self.snapshot = None, None

    def changed(self):
        pass


@unittest.skipUnless(HAVE, MISSING_REASON)
class StaleLines(unittest.TestCase):
    def test_l1_a_merge_wait_that_ends_leaves_no_waiting_note(self):
        waiting = strings.text("note.merge_waiting", stage="M1")
        app = _Merge()
        app.merge_wait_shown("M1")
        self.assertEqual(app.run_note, waiting)
        app.merge_wait_shown(None)  # any verdict, card or end modal: the controller ends the wait the same way
        self.assertEqual((app.run_note, app.merge_waiting), ("", None))
        app.merge_wait_shown("M1")
        app.run_note = "Merged: M1 → main."  # a verdict line that already replaced the note stays
        app.merge_wait_shown(None)
        self.assertEqual(app.run_note, "Merged: M1 → main.")

    def test_l3_a_start_the_architect_asked_for_holds_the_pending_line_until_it_ends(self):
        app = _Start()
        for outcome, held in (("done", True), ("failed", False)):
            app.pending = None
            app.start_wait_shown("M1", "begin")
            self.assertEqual(app.pending_text(), "starting M1…")  # the Plan tab hides `Next:` while this is set
            app.start_wait_shown("M1", outcome)
            self.assertEqual(bool(app.pending_text()), held)
        app.pending = None
        app.start_wait_shown("M1", "begin")
        view = SimpleNamespace(app=app, live_status=lambda leading: [])
        app.snapshot = replace(proposal(), lines=("Plan r1 approved", "Next: [g] start M1"))
        app.progress, app.run_note, app.run_watch = (), "", None
        self.assertNotIn("Next:", _main_method("live_view")(view)[0])  # the Now tab hides it too while the start is in flight
        calls = []
        controller = Controller(lambda stack: None, "identity")
        controller.on_start_wait = lambda milestone, state: calls.append(state)
        controller._start_tool = lambda app, milestone, revision: {"status": "ok"}
        controller._run_tool(SimpleNamespace(), "zplan_start", {"milestone": "M1", "revision": 1})
        controller._start_tool = lambda app, milestone, revision: 1 / 0
        with self.assertRaises(ZeroDivisionError):
            controller._run_tool(SimpleNamespace(), "zplan_start", {"milestone": "M1", "revision": 1})
        self.assertEqual(calls, ["begin", "done", "begin", "failed"])


if __name__ == "__main__":
    unittest.main()
