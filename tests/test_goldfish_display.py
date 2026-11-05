# tests/test_goldfish_display.py
"""R1a S5 acceptance: the owner sees the Goldfish review: the reader's paraphrase, the architect's answer, the plan
reader in the scheme, and no planner wording for a goldfish revision. The paraphrase also reaches the plan card of
every session and /details, sanitised; a planner revision shows no reader.
Before approving, the owner also reads each
task's acceptance examples and non-goals (docs/PRODUCT_CONTRACT.md section 2).

Design: docs/designs/2026-11-03-egm-planning.md 4.7. Plain view lines and the scheme renderer (no Textual), the live
Controller for the result line, the real app and the plan card's stand-in screen for the card; fixture engine, no
provider.
"""

import tui_support  # noqa: F401  bootstraps the offline wheelhouse before Rich
from tui_support import screen_text

from dataclasses import replace
import unittest

from terminal_planner import engine
from terminal_planner.authority import Authority
from terminal_planner.engine import FIXTURE_PARAPHRASE, FixtureEngine
from terminal_planner.planning import Planning
from terminal_planner.tui import strings

# The bare import scan (`tests.test_toolchain`) imports every test module without Rich: the scheme is imported only
# when Rich is there, and its test is then declared and skipped, never hidden.
try:
    from terminal_planner.tui import scheme
except ImportError:  # pragma: no cover - covered by the bare import scan of tests.test_toolchain
    scheme = None
import test_process as tpr
from test_goldfish_planning import briefed
from test_goldfish_tools import ToolBase, goldfish
from test_tui_approve_card import HAVE, MISSING_REASON, ApproveCardShell, proposal as joint_snapshot
from test_tui_auto_plan_card import card_kinds, card_of

# A reader's text with colour, a hyperlink and a line break; SANITISED is its start as a screen may show it.
HOSTILE = ("Reads \x1b[31mfine\x1b[0m.\x1b]8;;https://example.invalid\x07click\x1b]8;;\x07\nSecond line. "
           + "word " * 900)
SANITISED = "Reads fine.click Second line."
WHOLE = " ".join(["word"] * 590)  # under the stored limit, far over what the card and the plan view keep


def flat(text):
    """Text with its wrap breaks taken out."""
    return " ".join(text.split())


def reader_heading(lines):
    """The heading the plan view gives the paraphrase (its full text is pinned by the view test below)."""
    return next(line for line in lines if FIXTURE_PARAPHRASE in line).split(":", 1)[0]

# Synthetic brief text: the plan's own data, not wording of the UI.
T1_NON_GOAL = "T1 keeps the old importer"
T1_CRITERION = "T1 imports a file"
T1_EXAMPLE = "T1 given a.csv shows 3 rows"
T2_NON_GOAL = "T2 adds no new report"
T2_CRITERION = "T2 exports a file"
T2_EXAMPLE = "T2 given 3 rows writes b.csv"
BRIEF_HOSTILE = "\x1b[31m red\x1b]8;;http://x\x07 link\nnext"
BRIEF_SANITISED = " red link next"


def task_sections(lines):
    """The printed plan's text under T1 (up to T2) and under T2 (to the end)."""
    lines = list(lines)
    first, second = [next(n for n, line in enumerate(lines) if line.startswith("    %s " % task)) for task in ("T1", "T2")]
    return "\n".join(lines[first:second]), "\n".join(lines[second:])


def surfaces(app):
    """The two texts the owner can open before approving: the plan screen's details and /details."""
    return (("plan screen", app.delivery.plan_info()), ("details", app.delivery.details()))


class SchemeTests(tpr.ProfileTest):
    @unittest.skipIf(scheme is None, "Rich unavailable: ZPLAN_TEST_WHEELHOUSE with the rich wheels is needed")
    def test_the_scheme_draws_the_reader_and_the_check_side_by_side(self):
        text = scheme.render(engine.goldfish_graph()["root"], {}, 100, 30).plain
        self.assertIn("plan reader", text)
        self.assertIn("plan check", text)
        self.assertNotIn("comprehension", text)


class ViewTests(tpr.ProfileTest):
    def session(self):
        self.write({})
        self.accept_file()
        manager = self.app()
        app = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        return app

    def goldfish_session(self):
        """A session holding one reviewed goldfish revision: the app and the revision."""
        app = self.session()
        app.planning.plan_draft("Goal", briefed())
        FixtureEngine().proposal(app.authority, lambda _: None)
        return app, app.authority.current

    def test_the_plan_shows_the_paraphrase_and_the_architects_answer(self):
        app = self.session()
        app.planning.plan_draft("Goal", briefed())
        FixtureEngine("exhausted").proposal(app.authority, lambda _: None)
        version = app.authority.current["version"]
        app.planning.revise_draft(version, briefed(), response="F1 disputed: the scope is needed.", by="architect")
        FixtureEngine().proposal(app.authority, lambda _: None)
        current = app.authority.current
        text = "\n".join(app.planning.proposal(current).lines)
        self.assertIn('How a fresh reader understood it: "%s"' % FIXTURE_PARAPHRASE, text)
        self.assertIn('Architect\'s answer: "F1 disputed: the scope is needed."', text)
        gate = "\n".join(Planning.gate_lines(current["evidence"]))
        self.assertIn("Architect reply:", gate)
        self.assertNotIn("Planner", gate)
        self.assertNotIn("planner", text.lower())

    def test_details_show_the_paraphrase_under_the_plan_views_heading(self):
        app, current = self.goldfish_session()
        heading = reader_heading(app.planning.proposal(current).lines)
        for lines in (app.delivery.details(), app.delivery.plan_info()):
            shown = next((line for line in lines if FIXTURE_PARAPHRASE in line), "")
            self.assertIn(FIXTURE_PARAPHRASE, shown)
            self.assertIn(heading, shown)

    def test_details_keep_the_whole_paraphrase_that_the_card_cuts(self):
        _, current = self.goldfish_session()
        gate = Planning.gate_lines(dict(current["evidence"], paraphrase=WHOLE))
        self.assertIn(WHOLE, "\n".join(gate))

    @unittest.skipUnless(HAVE, MISSING_REASON)
    def test_the_paraphrase_is_sanitised_wherever_it_is_shown(self):
        app, current = self.goldfish_session()
        read = dict(current, evidence=dict(current["evidence"], paraphrase=HOSTILE))
        view = app.planning.proposal(read)
        card = card_of(replace(joint_snapshot(), plan=view), width=40).text
        for lines in (view.lines, Planning.gate_lines(read["evidence"]), (card,)):
            text = flat("\n".join(lines))
            self.assertNotIn("\x1b", text)
            self.assertIn(SANITISED, text)

    @unittest.skipUnless(HAVE, MISSING_REASON)
    def test_a_long_paraphrase_takes_at_most_three_rows_of_a_plain_sessions_card(self):
        app, current = self.goldfish_session()
        view = app.planning.proposal(dict(current, evidence=dict(current["evidence"], paraphrase=WHOLE)))
        without = replace(view, lines=tuple(line for line in view.lines if not line.startswith(card_kinds.READER_LINE)))
        rows = card_of(replace(joint_snapshot(), plan=view), width=40).text.split("\n")
        bare = card_of(replace(joint_snapshot(), plan=without), width=40).text.split("\n")
        self.assertGreater(len(rows) - len(bare), 0)
        self.assertLessEqual(len(rows) - len(bare), 3)

    @unittest.skipUnless(HAVE, MISSING_REASON)
    def test_a_planner_revision_shows_no_reader(self):
        app = self.session()
        self.begin(app.authority)
        self.propose(app.authority)
        view = app.planning.proposal(app.authority.current)
        card = card_of(replace(joint_snapshot(), plan=view))
        for text in (card.text, "\n".join(view.lines), "\n".join(app.delivery.details()),
                     "\n".join(app.delivery.plan_info())):
            self.assertNotIn(card_kinds.READER_LINE, text)

    def proposed(self, first, second=None):
        """A checked, unapproved plan whose T1 and T2 briefs carry the given fields."""
        app = self.session()
        plan = briefed()
        tasks = [task for m in plan["milestones"] for s in m["slices"] for task in s["tasks"]]
        tasks[0]["brief"].update(first)
        tasks[1]["brief"].update(second or {})
        app.planning.plan_draft("Goal", plan)
        FixtureEngine().proposal(app.authority, lambda _: None)
        self.assertEqual(app.authority.current["status"], "proposed")
        return app

    def test_before_approval_each_task_shows_its_own_examples_and_non_goals(self):
        app = self.proposed(
            {"criteria": [{"id": "C1", "text": T1_CRITERION, "example": T1_EXAMPLE}], "non_goals": [T1_NON_GOAL]},
            {"criteria": [{"id": "C1", "text": T2_CRITERION, "example": T2_EXAMPLE}], "non_goals": [T2_NON_GOAL]})
        for name, lines in surfaces(app):
            with self.subTest(surface=name):
                first, second = task_sections(lines)
                for shown in (T1_NON_GOAL, T1_CRITERION, T1_EXAMPLE):
                    self.assertIn(shown, first)
                    self.assertNotIn(shown, second)
                for shown in (T2_NON_GOAL, T2_CRITERION, T2_EXAMPLE):
                    self.assertIn(shown, second)
                    self.assertNotIn(shown, first)

    def test_brief_text_reaches_the_plan_without_terminal_sequences_and_on_one_line(self):
        app = self.proposed({
            "criteria": [{"id": "id" + BRIEF_HOSTILE, "text": "criterion" + BRIEF_HOSTILE, "example": "example" + BRIEF_HOSTILE}],
            "non_goals": ["nongoal" + BRIEF_HOSTILE]})
        for name, lines in surfaces(app):
            with self.subTest(surface=name):
                first, _ = task_sections(lines)
                for word in ("id", "criterion", "example", "nongoal"):
                    self.assertIn(word + BRIEF_SANITISED, first)
                for line in first.splitlines():
                    self.assertTrue(line.isprintable(), line)

    def test_a_very_long_brief_text_is_cut_on_the_plan(self):
        app = self.proposed({
            "criteria": [{"id": "v" * 8000, "text": "w" * 8000, "example": "x" * 8000}],
            "non_goals": ["y" * 8000]})
        for name, lines in surfaces(app):
            with self.subTest(surface=name):
                first, _ = task_sections(lines)
                for letter in "vwxy":
                    self.assertIn(letter * 300, first)
                    self.assertNotIn(letter * 401, first)

    def test_a_task_without_a_brief_prints_only_its_title_and_checks(self):
        app = self.session()
        app.planning.begin("Goal", app.roles)
        FixtureEngine().proposal(app.authority, lambda _: None)  # the fixture's own plan has no briefs
        for name, lines in surfaces(app):
            with self.subTest(surface=name):
                first, _ = task_sections(lines)
                # T1 has one check, so its title and that check come directly before milestone M2.
                self.assertTrue(first.splitlines()[2].startswith("M2 "), first)


class ResultTests(ToolBase):
    def test_the_result_of_an_architect_plan_names_the_plan_check(self):
        controller = self.controller(engine_factory=lambda *_: FixtureEngine())
        token = controller.begin_turn("Plan: add a changelog", 3)
        self.call("zplan_plan", {"goal": "Add a changelog", "plan": briefed()}, rid="ow", turn=token)
        lines = [line for result in self.call("zplan_status")["ok"]["results"] for line in result["lines"]]
        self.assertIn("Plan r1 sent to the plan check.", lines)
        self.assertNotIn("planner", " ".join(lines).lower())


@unittest.skipUnless(HAVE, MISSING_REASON)
class GoldfishOnScreen(ApproveCardShell):
    async def test_a_session_without_the_script_shows_the_reader_above_the_cards_buttons(self):
        with Authority(self.state, self.project, fixture_id="test") as authority:
            goldfish(authority, "plan", "owner", reject=False)
            FixtureEngine().proposal(authority, lambda _: None)
        async with self.shell(self.controller(), size=(80, 24)) as pilot:
            await self.loaded(pilot)
            card = await self.card_shown(pilot)
            self.assertFalse(self.app.snapshot.scripted)
            self.assertIn(FIXTURE_PARAPHRASE, flat(card.spec.text))
            shown = screen_text(self.app)
            self.assertIn(strings.text("card.approve_yes"), shown)
            self.assertIn(strings.text("card.revise"), shown)


if __name__ == "__main__":
    unittest.main()
