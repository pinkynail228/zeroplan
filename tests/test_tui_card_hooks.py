"""The shared card hooks frozen at the i3a merge (0.5.2): `CARD_ROUTES` + `card_route`, `CARD_SOURCES`,
`AUTO_END_CARDS` and `NoteScreen(enter=True)`. The card runs (i3b-i3e) add rows to them; these tests pin the hook
behaviour on stand-ins (the real methods run; no pilot, no project)."""

import unittest
from types import SimpleNamespace
from unittest import mock

import tui_support  # noqa: F401  (the offline wheelhouse joins sys.path first)

from test_tui_draft_card import MISSING_REASON, _main_method, _Screen

try:
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import cards
    from terminal_planner.tui import modals
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    ui = cards = modals = None


class _HookScreen(_Screen):
    render_card_sources = _main_method("render_card_sources")
    action_decline = _main_method("action_decline")


@unittest.skipIf(ui is None, MISSING_REASON)
class CardHookTests(unittest.TestCase):
    def test_a_typed_shared_command_acts_on_the_newest_open_card_of_a_routed_kind(self):
        screen = _HookScreen()
        older, newer = cards.draft_card("draft:a", at="21:00"), cards.draft_card("draft:b", at="21:05")
        for spec in (older, newer):
            screen.show_card(spec)
            screen.draft_cards[spec.key] = object()
        ui.COMMAND_ACTIONS["/decline"](screen, "", None)
        self.assertEqual(list(screen.card_specs), ["draft:a"])  # the newest one was declined
        opened = []
        screen.app.action_open_plan = lambda: opened.append(True)
        ui.COMMAND_ACTIONS["/approve"](screen, "", None)  # no card routes /approve yet: the fallback runs
        self.assertEqual(opened, [True])

    def test_card_sources_show_and_take_off_cards_and_never_bring_a_dropped_one_back(self):
        screen = _HookScreen()
        returned = [cards.draft_card("x:1", at="10:00")]
        # `clear=True`: the stand-in app is no real screen, so the *registered* run sources are taken off for this
        # probe — each of them reads app state (`checks`, a draft) the double does not carry.
        with mock.patch.dict(ui.CARD_SOURCES, {"x": lambda s: list(returned)}, clear=True):
            screen.render_card_sources()
            self.assertEqual(list(screen.card_specs), ["x:1"])
            widget = screen.card_widgets["x:1"]
            screen.render_card_sources()  # unchanged: not remounted
            self.assertIs(screen.card_widgets["x:1"], widget)
            returned.clear()
            screen.render_card_sources()  # the state is gone: the stale card leaves
            self.assertEqual(screen.card_specs, {})
            screen.show_card(cards.draft_card("x:2", at="10:01"))
            screen.drop_card("x:2")
            returned.append(cards.draft_card("x:2", at="10:01"))
            screen.render_card_sources()  # dropped by the owner: stays gone
            self.assertEqual(screen.card_specs, {})

    def test_an_auto_end_card_state_replaces_the_automatic_end_modal(self):
        shown = []
        app = SimpleNamespace(run_watch="M1", run_note="", run_lines=[], request_refresh=lambda: None,
                              changed=lambda: None, show_end=shown.append)
        outcome = SimpleNamespace(kind="end", data=SimpleNamespace(state="awaiting_merge"))
        with mock.patch.object(ui, "AUTO_END_CARDS", frozenset({"awaiting_merge"})):
            ui.ZplanApp.run_watched(app, "r1", outcome, None)
        self.assertEqual(shown, [])
        self.assertEqual(app.run_lines, ["M1 finished."])
        # not in the set: the modal opens as before (i3c: `awaiting_merge` IS in the real set, so the case is its
        # own patch rather than the default one)
        with mock.patch.object(ui, "AUTO_END_CARDS", frozenset()):
            ui.ZplanApp.run_watched(app, "r1", outcome, None)
        self.assertEqual(shown, [outcome.data])

    def test_a_card_origin_note_sends_with_enter(self):
        sent = []
        for enter, expected in ((True, ["sent"]), (False, [])):
            note = SimpleNamespace(enter=enter, action_send=lambda: sent.append("sent"))
            event = mock.Mock(key="enter")
            sent.clear()
            modals.NoteScreen.on_key(note, event)
            self.assertEqual(sent, expected, enter)


if __name__ == "__main__":
    unittest.main()
