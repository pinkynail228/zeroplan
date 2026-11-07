"""0.15, one planning path (docs/designs/2026-11-06-0-15-one-planning-path.md): no owner, steward or architect action
writes a revision of the old planner, and a message that code builds for the owner approves nothing.

The structural guard reads the product's own source; the route tests drive the demo session (the scripted architect
over the real bridge and fixture engine) and the planning service."""

import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from terminal_planner import application, authority as authority_module
from terminal_planner.authority import Blocked
from terminal_planner.planning import OLD_PLANNER_REFUSED, Planning
from test_demo_architect import GOAL, HAVE, MISSING_REASON, DemoShell
from test_terminal_planner import ProjectTest, Authority
from test_tui_planning import Planner

PRODUCT = Path(__file__).resolve().parents[1] / "terminal_planner"
# The old planner's writer, kept with no product caller until its removal (design section 6).
OLD_WRITERS = {"Planning.begin"}


def functions(tree):
    """(qualified name, node) of every function of a module, methods as `Class.method`."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield "%s.%s" % (node.name, item.name), item
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node


def receiver(call):
    """The dotted name a call is made on (`self.authority` for `self.authority.begin(...)`), else ""."""
    parts, node = [], call.func.value if isinstance(call.func, ast.Attribute) else None
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


class StructureTests(unittest.TestCase):
    def test_every_revision_the_product_writes_is_the_architects(self):
        """Every `Authority.begin` call in the product passes `review="goldfish"`, except the old planner's writer
        named in OLD_WRITERS, and nothing in the product calls that writer."""
        unreviewed, callers = [], []
        for path in sorted(PRODUCT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name, function in functions(tree):
                for call in ast.walk(function):
                    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and call.func.attr == "begin"):
                        continue
                    target = receiver(call)
                    if target in ("a", "authority") or target.endswith(".authority"):
                        review = next((k.value.value for k in call.keywords if k.arg == "review"
                                       and isinstance(k.value, ast.Constant)), None)
                        if review != "goldfish" and name not in OLD_WRITERS:
                            unreviewed.append("%s:%s %s" % (path.name, call.lineno, name))
                    elif target == "planning" or target.endswith(".planning"):
                        callers.append("%s:%s %s" % (path.name, call.lineno, name))
        self.assertEqual(unreviewed, [])
        self.assertEqual(callers, [])


class BindingTests(unittest.TestCase):
    def test_a_message_code_builds_shows_no_plan_to_approve(self):
        shown = {"revision": 1, "plan_state": {"status": "proposed"}}
        self.assertEqual(application.shown_plan(shown), 1)
        self.assertIsNone(application.shown_plan(dict(shown, binds=False)))


class OldPlannerRevisionTests(ProjectTest):
    def test_send_renew_and_restart_refuse_a_revision_the_old_planner_made_and_write_nothing(self):
        with Authority(self.state, self.project) as authority:
            self.begin_old_planner(authority)
            planning = Planning(authority, None, lambda *_: None)
            before = authority.path.read_bytes()
            for name in ("send", "renew", "restart"):
                with self.subTest(name), self.assertRaises(Blocked) as refused:
                    getattr(planning, name)()
                self.assertEqual((str(refused.exception), refused.exception.family),
                                 (OLD_PLANNER_REFUSED, "action.refused"))
            self.assertEqual(authority.path.read_bytes(), before)

    def test_an_unconfirmed_submission_of_the_old_planner_can_still_be_resent(self):
        """An upgrade can find an old-planner revision whose submission Zeroshot never confirmed: send resends the same
        frozen documents (it writes no revision), so the store is never stuck behind it."""
        with Authority(self.state, self.project) as authority:
            self.begin_old_planner(authority)
            Planner().prepare(authority)  # the frozen intent it was sent from, with no receipt
            authority.current.update(status="submission_unknown")
            authority.save()
            planning = Planning(authority, None, lambda *_: None)
            self.assertEqual(planning.send().kind, "ready")
            self.assertEqual(len(authority.state["revisions"]), 1)


@unittest.skipUnless(HAVE, MISSING_REASON)
class RouteTests(DemoShell):
    async def test_plan_with_a_goal_reaches_the_architect_and_writes_only_its_plan(self):
        """`/plan <goal>` is the owner's message to the architect: the scripted architect writes the plan with its
        tool, every revision written is a Goldfish one, and the plan waits for the owner's yes on its card."""
        reviews, real = [], authority_module.Authority.begin

        def spy(self_authority, *args, **kwargs):
            reviews.append(kwargs.get("review"))
            return real(self_authority, *args, **kwargs)

        app = self.demo_app()
        with patch.object(authority_module.Authority, "begin", spy):
            async with app.run_test(size=(120, 40)) as pilot:
                await self.until(pilot, lambda: app.chat.ready)
                await self.enter(pilot, "/plan " + GOAL)
                await self.until(pilot, lambda: self.commands(self.open_card("plan:")))
                self.assertIn("/approve", self.commands(self.open_card("plan:")))
                self.assertEqual([row["text"] for row in self.spoken("owner")], [GOAL])
        self.assertEqual(reviews, ["goldfish"])


if __name__ == "__main__":
    unittest.main()
