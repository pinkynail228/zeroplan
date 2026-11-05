# tests/test_unchecked_merge_notice.py
"""A merge no project check will verify is announced before the owner decides (docs/PRODUCT_CONTRACT.md section 2,
Delegation, and the merge rule "manual merge is explicitly labelled unverified"). With the merge gate off every merge
waits for the owner and lands unverified (`autonomy.decide`, `Delivery.merge`), so the plan card says so before the
start and the merge card says so before the click. The profile lines come from the real `process.describe`."""
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401

from terminal_planner import process
from terminal_planner.planning import PlanView
from terminal_planner.tui import strings
from terminal_planner.tui.controller import Outcome

from test_tui_approve_card import proposal
from test_tui_auto_plan_card import card_of, snapshot_at
from test_tui_merge_card import HAVE, MERGE_KEY, MISSING_REASON, TASKS, _App, _Merge, awaiting_row, ui

NOT_SAID = "no project check runs, and the card does not say so"
CHECK = {"name": "unit", "argv": ["python3", "-m", "unittest"], "timeout_s": 1800}
UNREADABLE = SimpleNamespace(lines=("profile: error", "  broken file"))
READER = 'How a fresh reader understood it: "It adds a flag."'
MILESTONE = "M1 Add --lines · 1 task"


def profile_of(merge="off", checks=(), level="auto"):
    """The profile view a snapshot holds for this merge gate, written by the real `process.describe`."""
    resolved = process.resolve({"preset": process.PRESET_V2, "autonomy": {"level": level}, "gates": {"merge": merge},
                                "checks": list(checks)}, {}, None)
    status = SimpleNamespace(state="accepted", present=True, problem="", notice="", resolved=resolved)
    return SimpleNamespace(lines=tuple(process.describe(status)))


def plan_lines(profile, level="auto"):
    return card_of(replace(snapshot_at(level), profile=profile)).text.split("\n")


def merge_card(profile, counts=True, overlap=(), asked=None):
    """The open merge card of M1 under `profile`: the real source on the merge card's stand-in screen."""
    app = _App([awaiting_row()])
    app.snapshot.profile = profile
    if asked is not None:
        app.controller.asked = asked
    if counts:
        app.answer_run(Outcome("end", data=TASKS))
    screen = _Merge(app)
    if overlap:
        screen.merge_overlap[MERGE_KEY] = overlap
    with patch.dict(ui.CARD_SOURCES, {"merge": ui.merge_card_source}, clear=True):
        screen.render_card_sources()
        app.flush()
    return screen.card_specs[MERGE_KEY]


@unittest.skipUnless(HAVE, MISSING_REASON)
class PlanCardNotice(unittest.TestCase):
    def test_the_plan_card_says_each_merge_will_wait_at_every_autonomy_level(self):
        for level in ("auto", "supervised", "manual"):
            with self.subTest(level=level):
                unchecked = plan_lines(profile_of(level=level), level)
                checked = plan_lines(profile_of("required", (CHECK,), level), level)
                self.assertEqual(len(unchecked), len(checked) + 1, NOT_SAID)
                self.assertEqual(unchecked, checked[:1] + [strings.text("card.plan_no_check")] + checked[1:])

    def test_listed_checks_with_the_gate_off_do_not_silence_the_plan_card(self):
        lines = plan_lines(profile_of("off", (CHECK,)))
        self.assertEqual(len(lines), len(plan_lines(profile_of("required", (CHECK,)))) + 1, NOT_SAID)
        self.assertIn(strings.text("card.plan_no_check"), lines)

    def test_the_notice_sits_between_the_fresh_reader_and_the_milestones(self):
        body = ("", "Plan r1 · 1 milestone · 1 task · checked", READER, "  M1 Add --lines  (after: —)",
                "    T1 Do it · 1 check")
        snapshot = replace(proposal(), plan=PlanView("proposal", 1, "proposed", body, ("approve",)), scripted=True,
                           profile=profile_of())
        lines = card_of(snapshot).text.split("\n")
        self.assertEqual(len(lines), 4, NOT_SAID)
        self.assertEqual(lines[1:], [READER, strings.text("card.plan_no_check"), MILESTONE])

    def test_a_required_gate_keeps_the_plan_card_quiet(self):
        for level in ("auto", "supervised", "manual"):
            with self.subTest(level=level):
                self.assertNotIn(strings.text("card.plan_no_check"),
                                 plan_lines(profile_of("required", (CHECK,), level), level))

    def test_an_unreadable_profile_claims_nothing_on_the_plan_card(self):
        self.assertEqual(card_of(replace(proposal(), profile=UNREADABLE)).text, card_of(proposal()).text)

    def test_a_stale_plan_keeps_its_own_text(self):
        spec = card_of(replace(snapshot_at("auto", stale=True), profile=profile_of()))
        self.assertEqual(spec.text, strings.text("card.plan_stale_text"))


@unittest.skipUnless(HAVE, MISSING_REASON)
class MergeCardNotice(unittest.TestCase):
    def test_the_merge_card_says_unverified_with_and_without_counts(self):
        for counts in (True, False):
            with self.subTest(counts=counts):
                unchecked, plain = merge_card(profile_of(), counts), merge_card(None, counts)
                lines = unchecked.text.split("\n")
                self.assertEqual(len(lines), len(plain.text.split("\n")) + 1, NOT_SAID)
                self.assertEqual(lines, plain.text.split("\n") + [strings.text("card.merge_unverified")])
                self.assertEqual(unchecked.buttons, plain.buttons)  # the owner may still choose to merge

    def test_the_architects_ask_follows_the_unverified_line(self):
        lines = merge_card(profile_of(), asked={"merge": "M1"}).text.split("\n")
        self.assertEqual(len(lines), 3, NOT_SAID)
        self.assertEqual(lines[1:], [strings.text("card.merge_unverified"),
                                     strings.text("card.merge_asked", stage="M1")])

    def test_listed_checks_with_the_gate_off_are_still_unverified(self):
        lines = merge_card(profile_of("off", (CHECK,))).text.split("\n")
        self.assertEqual(len(lines), len(merge_card(None).text.split("\n")) + 1, NOT_SAID)
        self.assertIn(strings.text("card.merge_unverified"), lines)

    def test_a_required_gate_and_an_unreadable_profile_add_nothing(self):
        plain = merge_card(None).text
        self.assertEqual(merge_card(profile_of("required", (CHECK,))).text, plain)
        self.assertEqual(merge_card(UNREADABLE).text, plain)

    def test_the_overlap_refusal_keeps_its_own_text(self):
        self.assertEqual(merge_card(profile_of(), overlap=(".env",)).text, merge_card(None, overlap=(".env",)).text)


class NoticeCatalog(unittest.TestCase):
    def test_both_lines_are_translated(self):
        for key in ("card.plan_no_check", "card.merge_unverified"):
            with self.subTest(key=key):
                entry = strings.CATALOG.get(key, {})
                self.assertEqual(len({entry.get(code) for code in strings.LANGUAGES} - {None}), 3, NOT_SAID)


if __name__ == "__main__":
    unittest.main()
