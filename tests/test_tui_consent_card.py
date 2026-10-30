"""P6b: the owner answers the architect's request on a card; the architect says the card is there (card contract:
devtools/zeroshot/tasks/card-contract.md).

After p6a the Controller holds one `ConsentRequest` (a start, a continue or a new attempt the level leaves to the
owner) and the asks for an approval and a merge. This module pins what the owner sees: the request card «The architect
asks» with «yes» (`/approve`) and «no» (`/decline`), the one line the plan card and the merge card carry while an ask
names them, and the hooks that make the app redraw. The architect's own prompt lines are `tests/test_architect.py`.

One acceptance criterion per test group, unit level: the real source, `show_card`/`close_card`/`render_card_sources`
and the two card commands run on a stand-in screen whose app records the controller calls and answers them when the
test flushes the queued hand-overs. No test drives the whole app: the Controller side (the request, `consent`,
`decline`, the asks) is `tests/test_consent.py`, and the card machinery is the commit card's.

Interpretations (the worker's summary never reaches the reviewers, so they are recorded here):
- The card closes in the controller's answer, not at the click: a «yes» that was refused (the profile moved, a gate)
  closes it too, as a receipt that says nothing was done and why, because the request is no longer awaiting then and
  the source would take the card off at the next render anyway. A job that was not admitted (the interface is
  closing) answers nothing and leaves the card as it was.
- The line of a new attempt shows the note on one line, cut at 200 characters, so a long note never grows the card.
- The ask line of the plan card is for a card that can be approved by the owner: a stale plan, or a plan the
  architect approves itself, says nothing of an ask. The merge card says it on both of its forms (with and without
  the counts) and not on the red overlap card, which is a refusal's card.
- Wording is not pinned (the card's text is copy): the tests read the catalog ids, and assert the milestone, the plan
  revision, the attempt and the note the line must name."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

# imported first for its side effect: the offline wheelhouse (ZPLAN_TEST_WHEELHOUSE) joins `sys.path` before the
# guarded imports below, so this module sees Textual and Rich there on a host that installs neither.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL

from test_tui_draft_card import MISSING_REASON, _main_method, _Screen
from test_tui_merge_card import MERGE_KEY, TASKS, _App as MergeApp, _Merge, awaiting_row

try:
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import card_kinds
    from terminal_planner.tui import strings
    from terminal_planner.tui.controller import ConsentRequest, Controller, Outcome
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    ui = card_kinds = strings = ConsentRequest = Controller = Outcome = None

HAVE = HAVE_TEXTUAL and ui is not None and strings is not None


def request(action="start", state="awaiting", **args):
    """The request the architect's tool stored (p6a): the tool's own arguments are all a card reads."""
    defaults = {"start": {"milestone": "M1", "revision": 3},
                "resume": {"milestone": "M1", "token": {"milestone": "M1", "attempt": 2}},
                "rebrief": {"milestone": "M1", "token": {"milestone": "M1", "attempt": 2}, "note": "use the fixture"}}
    return ConsentRequest("req-1", action, "M1", dict(defaults[action], **args), "digest", None, state)


class _Controller:
    """The controller side the request card touches: the stored request and the two calls, recorded."""

    def __init__(self, stored=None, asked=None):
        self.consent_request, self.asked = stored, asked or {}
        self.calls = []
        self.admitted = True

    def consent(self, request_id, done):
        self.calls.append(("consent", request_id))
        self.done = done
        return self.admitted

    def decline(self, request_id, done):
        self.calls.append(("decline", request_id))
        self.done = done
        return self.admitted


class _ConsentApp:
    """The app side the request card touches: `deliver` queues the hand-over (`flush` runs it, as the app's pump
    does once the worker answered), the refresh and the redraw are counted."""

    def __init__(self, controller):
        self.controller = controller
        self.deliveries, self.refreshed, self.changed_calls = [], 0, 0

    def deliver(self, handler):
        def done(outcome, error):
            self.deliveries.append((handler, outcome, error))
        return done

    def flush(self):
        while self.deliveries:
            handler, outcome, error = self.deliveries.pop(0)
            handler(outcome, error)

    def request_refresh(self):
        self.refreshed += 1

    def changed(self):
        self.changed_calls += 1


class _ConsentScreen(_Screen):
    """The card-contract stand-in with the request card's own methods on it (the real ones run)."""

    merge_card_at = _main_method("merge_card_at")
    confirm_consent = _main_method("confirm_consent")
    decline_consent = _main_method("decline_consent")
    render_card_sources = _main_method("render_card_sources")

    def __init__(self, controller):
        super().__init__()
        self.app = _ConsentApp(controller)
        self.merge_times = {}

    def render(self):
        with patch.dict(ui.CARD_SOURCES, {"consent": ui.CARD_SOURCES["consent"]}, clear=True):
            self.render_card_sources()

    def open_keys(self):
        return [key for key, spec in self.card_specs.items() if spec.done is None]


@unittest.skipUnless(HAVE, MISSING_REASON)
class ConsentCardTests(unittest.TestCase):
    def test_a1_a_request_is_a_card_with_one_line_and_yes_and_no(self):
        """A1: an awaiting request shows exactly one card, «The architect asks», whose line names what would run
        (start M1 under plan r3; continue M1's attempt 2; a new attempt of M1 with its note) and whose buttons are
        «yes» (`/approve`) and «no» (`/decline`); no request, or one that is not awaiting, shows none."""
        for action, needles in (("start", ("M1", "r3")), ("resume", ("M1", "2")),
                                ("rebrief", ("M1", "use the fixture"))):
            with self.subTest(action=action):
                screen = _ConsentScreen(_Controller(request(action)))
                screen.render()
                self.assertEqual(screen.open_keys(), ["consent:req-1"])
                spec = screen.card_specs["consent:req-1"]
                self.assertEqual(spec.title, strings.text("card.consent_title"))
                for needle in needles:
                    self.assertIn(needle, spec.text)
                self.assertEqual([command for _, command in spec.buttons], ["/approve", "/decline"])
        long_note = request("rebrief", note="word " * 100)
        spec = card_kinds.consent_spec("consent:req-1", "10:00", long_note)
        self.assertLess(len(spec.text), 260)  # a long note is cut on the card line
        for stored in (None, request(state="done"), request(state="declined"), request(state="stale")):
            screen = _ConsentScreen(_Controller(stored))
            screen.render()
            self.assertEqual(screen.open_keys(), [])

    def test_a1_yes_runs_the_request_through_the_controller_and_the_card_closes_as_a_receipt(self):
        """A1: «yes» asks the controller to consent to this card's request (nothing else runs); the card closes with
        the receipt the answer gives (what started), the app refreshes, and the card is not shown again. A refused
        answer (the request went stale) and a failed job close it too, saying nothing was done and why."""
        for outcome, error, expect in (
                (Outcome("done", lines=("M1 started · plan r3 · attempt 1",)), None, "M1 started · plan r3"),
                (Outcome("stale", lines=("The process profile changed",)), None, "The process profile changed"),
                (None, "This request is no longer valid", "This request is no longer valid")):
            with self.subTest(kind=getattr(outcome, "kind", error)):
                controller = _Controller(request())
                screen = _ConsentScreen(controller)
                screen.render()
                ui.CARD_ROUTES[("/approve", "consent")](screen, "", "consent:req-1")
                self.assertEqual(controller.calls, [("consent", "req-1")])
                self.assertEqual(screen.open_keys(), ["consent:req-1"])  # closed by the answer, not the click
                controller.done(outcome, error)
                screen.app.flush()
                self.assertEqual(screen.open_keys(), [])
                self.assertIn(expect, screen.card_specs["consent:req-1"].done)
                self.assertEqual(screen.app.refreshed, 1)
                controller.consent_request = request(state="done")
                screen.render()
                self.assertEqual(screen.open_keys(), [])

    def test_a1_no_declines_and_runs_nothing(self):
        """A1: «no» asks the controller to decline this request and never to consent; the card closes as a declined
        receipt once the controller answered `declined`. A request that was no longer awaiting (`ignored`) is no
        decision: the card is left to the next render, which takes it off."""
        controller = _Controller(request())
        screen = _ConsentScreen(controller)
        screen.render()
        ui.CARD_ROUTES[("/decline", "consent")](screen, "", "consent:req-1")
        self.assertEqual(controller.calls, [("decline", "req-1")])
        controller.done(Outcome("declined", lines=("The owner declined the architect's request.",)), None)
        screen.app.flush()
        self.assertEqual(screen.open_keys(), [])
        declined = strings.text("card.consent_declined", time="00:00").split(" 00:00")[0]
        self.assertIn(declined, screen.card_specs["consent:req-1"].done)
        again = _Controller(request())
        screen = _ConsentScreen(again)
        screen.render()
        ui.CARD_ROUTES[("/decline", "consent")](screen, "", "consent:req-1")
        again.done(Outcome("ignored"), None)
        screen.app.flush()
        self.assertEqual(screen.open_keys(), ["consent:req-1"])
        again.consent_request = request(state="done")
        screen.render()
        self.assertEqual(screen.open_keys(), [])

    def test_a2_the_plan_and_the_merge_card_carry_one_line_while_an_ask_names_them(self):
        """A2: while the architect's ask names the approval of plan r3 the plan card says so on one more line, and
        not for another revision, a stale plan or without an ask; while it names the merge of M1 the merge card says
        so (with and without the counts), not for another stage, and no second card appears. Both cards are the
        existing ones: their buttons and keys are untouched."""
        snapshot = SimpleNamespace(version=3, status="proposed", plan=SimpleNamespace(lines=(), family=None),
                                   profile=None)
        asked_plan = strings.text("card.plan_asked")
        for asked, expect in (({"approve": 3}, True), ({"approve": 2}, False), ({}, False)):
            with self.subTest(asked=asked):
                screen = SimpleNamespace(app=SimpleNamespace(snapshot=snapshot, controller=_Controller(asked=asked)),
                                         narrow=False)
                (spec,) = ui.plan_card_source(screen)
                self.assertEqual(asked_plan in spec.text, expect)
                self.assertEqual([command for _, command in spec.buttons], ["/approve", "/decline"])
        stale = SimpleNamespace(version=3, status="proposed", plan=SimpleNamespace(lines=(), family="plan.stale"),
                                profile=None)
        screen = SimpleNamespace(app=SimpleNamespace(snapshot=stale, controller=_Controller(asked={"approve": 3})),
                                 narrow=False)
        self.assertNotIn(asked_plan, next(iter(ui.plan_card_source(screen))).text)

        for asked, answer, expect in (({"merge": "M1"}, (Outcome("end", data=TASKS), None), True),
                                      ({"merge": "M1"}, (Outcome("end", data=None), None), True),
                                      ({"merge": "M2"}, (Outcome("end", data=TASKS), None), False),
                                      ({}, (Outcome("end", data=TASKS), None), False)):
            with self.subTest(asked=asked, counts=answer[0].data is not None):
                app = MergeApp([awaiting_row()])
                app.controller.asked = asked
                app.answer_run(*answer)
                screen = _Merge(app)
                with patch.dict(ui.CARD_SOURCES, {"merge": ui.merge_card_source}, clear=True):
                    screen.render_card_sources()
                    app.flush()  # the counts read's delivery re-renders the sources
                self.assertEqual(list(screen.card_specs), [MERGE_KEY])  # no second card
                spec = screen.card_specs[MERGE_KEY]
                self.assertEqual(strings.text("card.merge_asked", stage="M1") in spec.text, expect)
                self.assertEqual([command for _, command in spec.buttons], ["/merge", "/diff"])

    def test_a1_the_app_redraws_when_the_request_or_an_ask_changes(self):
        """A1/A2: the app hands its redraw to the controller's two worker hooks (like the commit proposal's), so a new
        request, its end and a recorded or cleared ask are drawn without waiting for another event."""
        controller = Controller(lambda stack: None, "t")
        app = ui.ZplanApp(controller)
        handed = []
        with patch.object(app, "from_worker", lambda handler, *args: handed.append(handler)):
            controller.on_consent_request(request())
            controller.on_asked({"merge": "M1"})
        self.assertEqual(handed, [app.changed, app.changed])


if __name__ == "__main__":
    unittest.main()
