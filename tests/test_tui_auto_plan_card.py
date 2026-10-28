"""D1: the plan card tells the truth in `auto` and on a narrow screen (C1-C5).

In `auto` the architect approves a proposed plan within seconds (`feed._plan_wakes`), so the card does not ask and
the bar does not wait for the owner; at 80x24 there is no right column, so the card does not point to one. The source
(`card_kinds.plan_card_source`) and the bar job (`MainScreen.bar_job`) read the level from the profile view the
snapshot holds (`snapshot.profile.lines`, `process.describe`'s «autonomy: <level>» line) and ask the policy
(`autonomy.decide(level, "approve")`) — the rule `feed._plan_wakes` applies.

Two whole-app methods (C1 at 80x24 in `auto`, C2+C3 at 140x40 and across a resize in `supervised`); the rest is
unit level on the plan-card stand-in screen of `test_tui_approve_card`, where the real `render_card_sources` runs.

Interpretations:

- The level is read from `snapshot.profile.lines` because the snapshot carries no other form of it and the
  controller is outside this task's write-set; a missing profile, a profile view without the line (a malformed
  profile shows its error instead) or a value outside the known levels is "manual" (`autonomy.decide` asks), so C5's
  fallback is the question, never the auto text.
- A stale plan keeps its RS2 text and button at every level (C4); its bar also keeps `bar.waiting_approve`, because
  the architect does not approve a stale plan either.
- The auto text names no place for the plan, so the layout only changes the question's text (C3).
- The profile line's level is not translated by `describe`, so the parse is checked against the real `describe`
  output in `test_the_level_reads_what_describe_writes`.
"""

import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_text

from terminal_planner import process
from terminal_planner.authority import Authority
from terminal_planner.planning import PlanView
from terminal_planner.tui import strings
from test_tui_approve_card import HAVE, MISSING_REASON, ApproveCardShell, _Screen, proposal

try:
    from textual.widgets import Button
    from terminal_planner.tui import app as ui, card_kinds
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    Button = ui = card_kinds = None


def profile_view(level):
    """The profile view of a profile at `level` (None: no `autonomy` line, as of a `/1` or a malformed profile)."""
    lines = ["Process profile: accepted", "  preset zplan.default/2"]
    if level is not None:
        lines.append("  autonomy: %s · up to 3 runs · worker round 45 min (next)" % level)
    return SimpleNamespace(state="accepted", note="", lines=tuple(lines), bootstrap=(), present=True, problem="")


def snapshot_at(level, stale=False):
    base = proposal()
    if stale:
        base = replace(base, plan=PlanView("proposal", 1, "proposed", base.plan.lines, ("revise", "reject"),
                                           family="plan.stale"))
    return replace(base, profile=profile_view(level))


class _NarrowScreen(_Screen):
    """The stand-in of a screen that can be narrow: showing a card then asks the layout to show the chat pane."""

    def apply_narrow(self):
        """UI-only: the stand-in has no panes to show."""


def card_of(snapshot, narrow=False):
    screen = _NarrowScreen(snapshot)
    screen.narrow = narrow
    return list(ui.CARD_SOURCES["plan"](screen))[0]


def bar_job_of(snapshot):
    """The bar's job word the real `MainScreen.bar_job` takes for a proposed plan (state `plan_ready`, no milestone
    row, no flow); the slash state and the active row are the only parts the stand-in does not carry."""
    screen = SimpleNamespace(app=SimpleNamespace(snapshot=snapshot))
    with patch.object(ui, "screen_slash_state", return_value="plan_ready"), patch.object(ui, "active_row",
                                                                                         return_value=None):
        return ui.MainScreen.bar_job(screen)[0]


ASK = (strings.text("card.approve_yes"), "/approve")
REVISE = (strings.text("card.revise"), "/decline")
REVISE_ONLY = (strings.text("card.revise_only"), "/decline")


@unittest.skipUnless(HAVE, MISSING_REASON)
class AutoPlanCardTests(unittest.TestCase):
    def test_c1_in_auto_the_card_does_not_ask_and_offers_revise_only(self):
        for narrow in (False, True):
            with self.subTest(narrow=narrow):
                spec = card_of(snapshot_at("auto"), narrow)
                self.assertEqual(spec.text, strings.text("card.plan_auto_text"))
                self.assertEqual(spec.buttons, (REVISE_ONLY,))
                self.assertTrue(spec.title.startswith("Plan · "), spec.title)  # the counts are the planning service's own text
                self.assertNotIn("Approve?", spec.text)
                self.assertNotIn("on the right", spec.text)

    def test_c1_the_bar_job_follows_the_policy(self):
        """The bar says the architect approves in `auto`, and waits for the owner at the other levels."""
        for level, job in (("auto", "approve_auto"), ("supervised", "approve"), ("manual", "approve"), (None, "approve")):
            with self.subTest(level=level):
                self.assertEqual(bar_job_of(snapshot_at(level)), job)
        from terminal_planner.tui.activity import bar_text
        text = bar_text("P", "main", "approve_auto", "", None, (), 200).plain
        self.assertIn(strings.text("bar.approving_plan"), text)
        self.assertNotIn(strings.text("bar.waiting_approve"), text)

    def test_c2_supervised_and_manual_keep_the_question_and_both_buttons(self):
        for level in ("supervised", "manual"):
            with self.subTest(level=level):
                spec = card_of(snapshot_at(level))
                self.assertEqual(spec.text, strings.text("card.plan_text"))
                self.assertEqual(spec.buttons, (ASK, REVISE))

    def test_c3_the_pointer_follows_the_layout_and_an_open_card_follows_a_resize(self):
        wide, narrow = card_of(snapshot_at("manual")), card_of(snapshot_at("manual"), narrow=True)
        self.assertIn("The “Plan” tab is on the right.", wide.text)
        self.assertIn("The plan is on the “Plan” tab (→).", narrow.text)
        self.assertNotIn("on the right", narrow.text)
        self.assertEqual(narrow.buttons, (ASK, REVISE))
        screen = _NarrowScreen(snapshot_at("manual"))
        # only this run's source: the other registered ones read app state the stand-in does not carry
        with patch.dict(ui.CARD_SOURCES, {"plan": ui.CARD_SOURCES["plan"]}, clear=True):
            screen.render_card_sources()
            self.assertEqual(screen.card_specs["plan:1"], wide)
            screen.narrow = True  # a resize re-renders the sources (`on_resize` -> `render_state`)
            screen.render_card_sources()
        self.assertEqual(screen.card_specs["plan:1"], narrow)
        self.assertIsNone(screen.card_specs["plan:1"].done)

    def test_c4_a_stale_plan_keeps_its_text_and_button_at_any_level(self):
        for level in ("auto", "supervised", "manual", None):
            for narrow in (False, True):
                with self.subTest(level=level, narrow=narrow):
                    spec = card_of(snapshot_at(level, stale=True), narrow)
                    self.assertEqual(spec.text, strings.text("card.plan_stale_text"))
                    self.assertEqual(spec.buttons, (REVISE_ONLY,))
        self.assertEqual(bar_job_of(snapshot_at("auto", stale=True)), "approve")

    def test_c5_an_unreadable_level_falls_back_to_the_question(self):
        unreadable = (replace(proposal(), profile=None), snapshot_at(None), snapshot_at("turbo"), snapshot_at(""),
                      replace(proposal(), profile=SimpleNamespace(lines=("profile: error", "  broken file"))))
        for snapshot in unreadable:
            with self.subTest(profile=snapshot.profile):
                spec = card_of(snapshot)
                self.assertEqual(spec.text, strings.text("card.plan_text"))
                self.assertEqual(spec.buttons, (ASK, REVISE))
                self.assertEqual(bar_job_of(snapshot), "approve")

    def test_the_level_reads_what_describe_writes(self):
        """`profile_level` parses the line `process.describe` writes for a resolved profile."""
        for level in ("auto", "supervised", "manual"):
            resolved = process.resolve({"preset": process.PRESET_V2, "autonomy": {"level": level}}, {}, None)
            status = SimpleNamespace(state="accepted", present=True, problem="", notice="", resolved=resolved)
            view = SimpleNamespace(lines=tuple(process.describe(status)))
            self.assertEqual(card_kinds.profile_level(SimpleNamespace(profile=view)), level)

    def test_u3_the_0_7_x_russian_autonomy_line_is_still_read(self):
        """U3 (interpretation): `process.describe` is T1's file; until it speaks English its Russian line, and a stored
        0.7.x profile view, must still give the level (`card_kinds.LEGACY_AUTONOMY_LINE`), never a silent "manual"."""
        view = SimpleNamespace(lines=(card_kinds.LEGACY_AUTONOMY_LINE + "auto · прогонов до 3",))
        self.assertEqual(card_kinds.profile_level(SimpleNamespace(profile=view)), "auto")
        view = SimpleNamespace(lines=(card_kinds.AUTONOMY_LINE + "supervised · up to 3 runs",))
        self.assertEqual(card_kinds.profile_level(SimpleNamespace(profile=view)), "supervised")


@unittest.skipUnless(HAVE and HAVE_TEXTUAL, MISSING_REASON)
class AutoPlanCardShell(ApproveCardShell):
    def propose_at(self, level):
        """The joint proposal under an accepted profile of autonomy `level` (the file committed first, as the
        parallel-watch fixtures do)."""
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"level": level}}))
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "profile")
        with Authority(self.state, self.project, fixture_id="test") as authority:
            authority.profile = process.Profile.of(authority)
            authority.profile.accept()
        self.propose_joint()

    def labels(self):
        return [button.label.plain for button in self.card().query(Button)]

    async def test_c1_at_80x24_in_auto_the_card_and_the_bar_do_not_ask(self):
        self.propose_at("auto")
        async with self.shell(self.controller(profile=True), size=(80, 24)) as pilot:
            await self.loaded(pilot)
            card = await self.card_shown(pilot)
            self.assertEqual(card.spec.text, strings.text("card.plan_auto_text"))
            self.assertEqual(self.labels(), [strings.text("card.revise_only")])
            shown = screen_text(self.app)
            self.assertNotIn("Approve?", shown)
            self.assertNotIn("on the right", shown)
            self.assertIn(strings.text("bar.approving_plan"), shown)
            self.assertNotIn(strings.text("bar.waiting_approve"), shown)

    async def test_c2_c3_supervised_keeps_the_question_and_its_pointer_follows_the_resize(self):
        self.propose_at("supervised")
        async with self.shell(self.controller(profile=True), size=(140, 40)) as pilot:
            await self.loaded(pilot)
            card = await self.card_shown(pilot)
            self.assertEqual(card.spec.text, strings.text("card.plan_text"))
            self.assertEqual(self.labels(), [strings.text("card.approve_yes"), strings.text("card.revise")])
            self.assertIn(strings.text("bar.waiting_approve"), screen_text(self.app))
            await pilot.resize_terminal(80, 24)
            await self.until(pilot, lambda: self.card() is not None
                             and self.card().spec.text == strings.text("card.plan_text_narrow"))
            await pilot.pause(0.3)
            self.assertNotIn("on the right", screen_text(self.app))
            self.assertEqual(self.labels(), [strings.text("card.approve_yes"), strings.text("card.revise")])


if __name__ == "__main__":
    unittest.main()
