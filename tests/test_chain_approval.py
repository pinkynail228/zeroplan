"""One approval per plan chain at supervised (docs/PRODUCT_CONTRACT.md section 5.6; roadmap D3). Once the owner
approved a chain's revision, a later revision the architect makes in that chain, accepted by the critic, is the
architect's to approve; the chain's first approval and every approval at manual stay the owner's."""
import json
import unittest
from unittest.mock import patch

from terminal_planner import autonomy, process
from terminal_planner.engine import FixtureEngine

import test_terminal_planner as tp
from test_goldfish_planning import briefed
from test_goldfish_tools import ToolBase


class ChainApproval(ToolBase):
    def profile(self, level):
        (self.project / process.PROFILE_FILE).write_text(json.dumps({"preset": process.PRESET_V2, "autonomy": {"level": level}}))
        with tp.Authority(self.state, self.project) as authority:
            process.Profile.of(authority).accept()
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "profile")

    def revision(self, authority, origin, by, title=None):
        authority.begin("Requested feature", tp.ROLES, "fixture", draft=briefed(title), review="goldfish", origin=origin,
                        by=by, response="")
        FixtureEngine().proposal(authority, lambda _: None)  # the fixture critic accepts

    def chain(self, approved_start):
        with tp.Authority(self.state, self.project) as authority:
            authority.profile = process.Profile.of(authority)  # the revisions freeze the accepted profile's digest
            self.revision(authority, "plan", "owner")
            if approved_start:
                authority.approve(1)
            self.revision(authority, "edit", "architect", title="Second title")

    def approve(self, revision):
        self.controller(profile=True, engine_factory=lambda *_: FixtureEngine())
        with patch.object(autonomy, "AUTOMATIC", True):
            return self.call("zplan_approve_plan", {"revision": revision}, rid="ap%s" % revision)

    def test_supervised_the_architects_later_revision_in_an_approved_chain_is_approved_by_the_architect(self):
        self.profile("supervised")
        self.chain(approved_start=True)
        reply = self.approve(2)
        self.assertEqual(reply.get("ok", {}).get("status"), "approved", reply)

    def test_supervised_a_chain_without_the_owners_approval_still_asks_the_owner(self):
        self.profile("supervised")
        self.chain(approved_start=False)
        reply = self.approve(2)
        self.assertEqual(reply.get("ok", {}).get("status"), "awaiting_owner", reply)

    def test_manual_always_asks_the_owner(self):
        self.profile("manual")
        self.chain(approved_start=True)
        reply = self.approve(2)
        self.assertEqual(reply.get("ok", {}).get("status"), "awaiting_owner", reply)

    def test_supervised_a_revision_the_owner_declined_is_never_the_architects_to_approve(self):
        """0.14 K: in an approved chain at supervised, where the architect approves a later revision alone, the
        owner's decline of that revision is stored, so the architect's approve is refused, also in a new session, the
        status names the decline and no yes in words binds it; the owner's own plan card still approves it."""
        import threading
        from terminal_planner import application
        from terminal_planner.tui.controller import plan_state

        def job(start, *args):
            ended, errors = threading.Event(), []
            start(*args, lambda outcome, error: (errors.append(error), ended.set()))
            self.assertTrue(ended.wait(10))
            return errors[0]

        self.profile("supervised")
        self.chain(approved_start=True)
        self.assertIsNone(job(self.controller(profile=True, engine_factory=lambda *_: FixtureEngine()).decline_plan, 2))
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            state = plan_state(authority.current)
        self.assertIsNone(application.shown_plan({"revision": 2, "plan_state": state}))
        reply = self.approve(2)  # a new session reads the decline from the store
        self.assertEqual(reply.get("error"), "action.refused", reply)
        self.assertTrue(self.plan_until(lambda plan: plan["version"] == 2)["declined"])
        self.assertIsNone(job(self._controllers[-1].approve_plan, 2))  # the owner's card
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            self.assertEqual(authority.current["status"], "approved")


if __name__ == "__main__":
    unittest.main()
