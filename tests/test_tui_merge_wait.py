"""C6: an owner's merge waits for the merge critic itself (rc1 walk N1).

The fake stands in for `MilestoneRuns.merge`, the call under `Delivery.merge`: it raises the critic's own refusals
the way the critic slice does, so the real `Delivery.merge` turns them into its refused verdict ("Not done: ... [code:
...]"), then runs the real merge. Textual Pilot over the fixture store; they need Textual and skip without it.

Interpretations: the wait lives in `Controller.merge`, so the end modal and the merge card (`/merge`) both wait; a
pending critic is recognised by its catalog code in the refused verdict `Delivery.merge` returns. The status line is
`App.pending_text()` (the plan view's `…` line). Only a second merge is refused while one waits; other actions run."""

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from terminal_planner.authority import Blocked
from terminal_planner.delivery import Merge
from terminal_planner.runs import MilestoneRuns
from terminal_planner.tui import controller as tui_controller
from terminal_planner.tui.controller import Outcome
from test_tui_milestones import MilestoneShell
from tui_support import HAVE_TEXTUAL


def pending():
    return Blocked("The merge check did not finish within its slice; repeat the merge.", family="merge.critic_pending")


class MergeWaitController(unittest.TestCase):
    """C6b (release critic rel082b 1, 3): `Controller.merge` over a fake delivery, no store and no app.

    Interpretations: the pacing is measured between the starts of two merge calls of one wait; `CRITIC_SLICE` is
    injected through `terminal_planner.tui.controller.CRITIC_SLICE`; the probe job stands for a refresh queued
    while the wait pauses."""

    def run_merge(self, verdicts, slice=0.2):
        log, ran, answers, reached = [], [], [], threading.Event()

        class Delivery:
            def resolve(self, token, exact=True):
                return {}

            def latest(self, milestone):
                return None

            def merge(self, r):
                log.append(time.monotonic())
                if len(log) == 1:
                    controller.post("probe", lambda app: ran.append(len(log)))
                return verdicts[len(log) - 1]

        controller = tui_controller.Controller(lambda stack: SimpleNamespace(delivery=Delivery()), "identity")
        controller.start()
        self.addCleanup(controller.stop)
        with patch.object(tui_controller, "CRITIC_SLICE", slice):
            controller.merge(SimpleNamespace(milestone="M1"), lambda outcome, error: (answers.append((outcome, error)), reached.set()))
            self.assertTrue(reached.wait(10), "the merge never answered")
        return log, ran, answers

    def test_the_wait_keys_on_the_family_not_on_the_text(self):
        """A critic block that quotes the pending tag in its findings ends the wait after one call (W1)."""
        quoted = Merge("refused", "Not done: findings quote [code: merge.critic_pending] [code: milestone.critic_blocked]",
                       False, family="milestone.critic_blocked")
        log, ran, answers = self.run_merge([quoted])
        self.assertEqual(len(log), 1)
        self.assertEqual((answers[0][0].kind, answers[0][0].lines, answers[0][1]), ("refused", (quoted.line,), None))

    def test_pending_calls_are_a_slice_apart_with_the_queue_served_between(self):
        """A pending refusal that returns at once does not spin: three calls take two slices (W3)."""
        pending = Merge("refused", "Not done: pending", False, family="merge.critic_pending")
        landed = Merge("integrated", "Merged: M1 → main.", False)
        log, ran, answers = self.run_merge([pending, pending, landed])
        self.assertEqual(len(log), 3)
        self.assertTrue(all(b - a >= 0.2 for a, b in zip(log, log[1:])), [b - a for a, b in zip(log, log[1:])])
        self.assertEqual(ran[0], 1)  # the job queued during the first call ran before the second one
        self.assertEqual(answers[0][0].kind, "integrated")

    def test_no_repeat_starts_once_a_quit_began(self):
        """C6c X2: a repeat that waited behind a watch longer than the slice and meets a begun quit does not call
        `Delivery.merge` again; the wait ends with the closing line.

        Interpretation: the watch is a probe job queued by the first merge call that holds the worker past the slice."""
        calls, answers, reached, queued, release = [], [], threading.Event(), threading.Event(), threading.Event()

        class Delivery:
            def resolve(self, token, exact=True):
                return {}

            def latest(self, milestone):
                return None

            def merge(self, r):
                calls.append(1)
                controller.post("watch", lambda app: (queued.set(), release.wait(10)))
                return Merge("refused", "Not done: pending", False, family="merge.critic_pending")

        controller = tui_controller.Controller(lambda stack: SimpleNamespace(delivery=Delivery()), "identity")
        controller.start()
        self.addCleanup(controller.stop)
        self.addCleanup(release.set)
        with patch.object(tui_controller, "CRITIC_SLICE", 0.1):
            controller.merge(SimpleNamespace(milestone="M1"), lambda outcome, error: (answers.append((outcome, error)), reached.set()))
            self.assertTrue(queued.wait(10))
            time.sleep(0.3)  # the repeat is queued behind the watch and is older than a slice when it runs
            controller.begin_closing()
            release.set()
            self.assertTrue(reached.wait(10), "the merge never answered")
        self.assertEqual((len(calls), answers), (1, [(None, "zplan is closing; the merge was not repeated.")]))


    def run_repeat(self, quit_in):
        """Two merge calls of one wait; `quit_in` is "resolve" (the quit begins while the repeat resolves its token)
        or "merge" (it begins inside the repeat's merge call). Returns the calls, the answers and what
        `begin_closing()` returned."""
        calls, answers, sealed, reached = [], [], [], threading.Event()

        class Delivery:
            def resolve(self, token, exact=True):
                if quit_in == "resolve" and calls:
                    sealed.append(controller.begin_closing())
                return {}

            def latest(self, milestone):
                return None

            def merge(self, r):
                calls.append(1)
                if quit_in == "merge" and len(calls) == 2:
                    sealed.append(controller.begin_closing())
                    return Merge("integrated", "Merged: M1 -> main.", False)
                return Merge("refused", "Not done: pending", False, family="merge.critic_pending")

        controller = tui_controller.Controller(lambda stack: SimpleNamespace(delivery=Delivery()), "identity")
        controller.start()
        self.addCleanup(controller.stop)
        with patch.object(tui_controller, "CRITIC_SLICE", 0.1):
            controller.merge(SimpleNamespace(milestone="M1"), lambda outcome, error: (answers.append((outcome, error)), reached.set()))
            self.assertTrue(reached.wait(10), "the merge never answered")
        return calls, answers, sealed

    def test_a_repeat_takes_the_permit_at_the_merge_boundary(self):
        """C6d P1/P2 (rel082d 1): a quit that begins while the repeat resolves its token refuses the repeat (one
        merge call, the closing line); a repeat admitted before the quit merges and the quit waits for it.

        Interpretation: the quit is `begin_closing()` called from inside `Delivery.resolve` / `Delivery.merge`, the
        two points where the real quit can land between the c6c check and the merge call."""
        calls, answers, sealed = self.run_repeat("resolve")
        self.assertEqual((len(calls), answers), (1, [(None, "zplan is closing; the merge was not repeated.")]))
        calls, answers, sealed = self.run_repeat("merge")
        self.assertEqual((len(calls), sealed, answers[0][0].kind), (2, [True], "integrated"))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8")
class MergeWaitShell(MilestoneShell):
    def free(self):
        lock = self.app.controller._project_op
        if not lock.acquire(blocking=False):
            return False
        lock.release()
        return True

    async def merge_end(self, pilot, refusals, hold=None, modal=True):
        """The end modal of a finished M1 (`modal` False: its merge card on the main screen); `MilestoneRuns.merge` raises `refusals` in turn (the second waits for `hold`),
        then merges for real. Returns the log of merge calls and of a probe job queued by the first one."""
        real, log = MilestoneRuns.merge, []

        def merge(runs, *args, **kwargs):
            log.append("merge")
            calls = log.count("merge")
            if calls == 1:  # a job queued during the wait: it must run before the next merge call
                self.app.controller.post("probe", lambda app: log.append("probe" if self.free() else "locked"))
            if calls == 2 and hold is not None:
                hold.wait(10)
            if refusals:
                raise refusals.pop(0)
            return real(runs, *args, **kwargs)
        for patcher in (patch.object(MilestoneRuns, "merge", merge),
                        patch.object(tui_controller, "CRITIC_SLICE", 0.1)):  # C6b: the calls of a wait are a slice apart
            patcher.start()
            self.addCleanup(patcher.stop)
        await self.loaded(pilot)
        await self.begin_run(pilot)
        if modal:
            await self.open_merge_end(pilot)
        else:
            await self.until(pilot, lambda: self.app.selection() is not None
                             and self.app.selection().state == "awaiting_merge" and self.end_card() is not None)
        return log

    async def test_the_merge_waits_slice_after_slice_and_lands(self):
        hold = threading.Event()
        self.addCleanup(hold.set)
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            log = await self.merge_end(pilot, [pending(), pending()], hold)
            await self.press_button(pilot, "merge")
            await self.press_button(pilot, "yes")
            await self.until(pilot, lambda: "merge check" in self.modal_flat())  # M2: the first slice ended pending
            for text in (self.modal_flat(), self.app.pending_text()):
                self.assertIn("merge check", text)
                self.assertIn("M1", text)
                self.assertNotIn("[m]", text)
                self.assertNotIn("Not done", text)
            await self.until(pilot, lambda: log.count("merge") == 2)  # the paced second call, held by `hold`
            self.assertEqual(log[:3], ["merge", "probe", "merge"])  # M3: the lock was free between the slices
            self.assertFalse(self.app.guard_pending("start"))  # ... and the wait holds no other owner action back
            await self.press_button(pilot, "merge")  # M4: a second press starts no second merge
            self.assertIn("Already waiting", self.modal_flat())
            self.assertEqual(log.count("merge"), 2)
            hold.set()
            await self.shows(pilot, "Merged: M1 → main.")  # M1: three merge calls, one confirm
            self.assertEqual(log.count("merge"), 3)
            self.assertNotIn("Not done", self.modal_flat())
            self.assertIsNone(self.app.merge_waiting)

    async def test_the_merge_card_waits_too_and_another_refusal_ends_the_wait(self):
        """The card's `/merge` (no modal) is the walk's own path: it waits, a second `/merge` is refused as waiting,
        and a critic block ends the wait with the engine's text (M5)."""
        hold = threading.Event()
        self.addCleanup(hold.set)
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            head = self.head()
            log = await self.merge_end(pilot, [pending(), Blocked("The merge critic blocked the candidate.",
                                                                    family="milestone.critic_blocked")], hold, False)
            await self.command(pilot, "/merge")
            await self.until(pilot, lambda: "merge check" in self.app.pending_text())
            self.assertNotIn("Not done", self.flat())
            await self.command(pilot, "/merge")
            await self.shows(pilot, "Already waiting")
            hold.set()
            await self.shows(pilot, "Not done: The merge critic blocked the candidate.")
            self.assertEqual((log.count("merge"), self.head(), self.app.merge_waiting), (2, head, None))

    async def test_the_verdict_reaches_the_owner_when_the_end_modal_is_gone(self):
        """The modal is dismissed while the merge waits; the critic's block then shows as the note and the waiting
        text is gone (W2)."""
        hold = threading.Event()
        self.addCleanup(hold.set)
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.merge_end(pilot, [pending(), Blocked("The merge critic blocked the candidate.",
                                                           family="milestone.critic_blocked")], hold)
            await self.press_button(pilot, "merge")
            await self.press_button(pilot, "yes")
            await self.until(pilot, lambda: "merge check" in self.modal_flat())
            await pilot.press("escape")
            await pilot.pause()
            hold.set()
            await self.shows(pilot, "Not done: The merge critic blocked the candidate.")
            self.assertIsNone(self.app.merge_waiting)
            self.assertNotIn("merges when it says go", self.flat())

    async def test_every_detached_verdict_replaces_the_waiting_note(self):
        """C6c X1: with the end modal gone, a changed token (`stale`, with and without a fresh end view) and a
        `blocked` verdict and an `open` one (a conflict that left no line) each replace the waiting note with their own line."""
        from terminal_planner.tui.card_kinds import NOT_STARTED_BELOW  # Rich-bound: only with Textual
        self.approve(running=False)
        gone = SimpleNamespace(is_attached=False, end=SimpleNamespace(milestone="M1"))
        waiting = "zplan merges when it says go"
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            for outcome, expected in (
                    (Outcome("stale", lines=("Plan moved.",), data=object()), "Plan moved."),
                    (Outcome("stale"), "M1: the run changed; screen refreshed."),
                    (Outcome("blocked", checks=()), NOT_STARTED_BELOW),
                    (Outcome("open"), "M1: the merge did not land")):
                self.app.say_note(waiting)
                self.app.settled(gone, outcome, None)
                self.assertIn(expected, str(self.app.run_note))
                self.assertNotIn(waiting, str(self.app.run_note))


if __name__ == "__main__":
    unittest.main()
