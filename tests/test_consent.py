"""p6a: an architect action the level leaves to the owner is a request the owner can grant, not a refusal.

A real `Controller` runs a fixture session over an approved plan (the bridge's fixtures), the architect's tools reach
it over the socket and the owner answers through the Controller's own calls (`consent`, `decline`, `approve_plan`,
`merge`), exactly as the cards will.

Interpretations (the brief leaves them open):
- The release gate (`autonomy.AUTOMATIC`) is patched off where a test needs the level to ask for a start, resume,
  rebrief or approve: the policy asks at every level then, and the test is about what the Controller does with the
  ask, not about the policy table (`test_autonomy`).
- "The profile file changes" (A2) is the owner editing and committing it after the architect asked; the stored digest
  is the one the policy read, so the request is stale whatever the new level is.
- A request's answer is an `Outcome` whose kind is the request's new state, so the owner's card reads one place."""

import json
import threading
import unittest
from unittest.mock import patch

from terminal_planner import autonomy, process
from terminal_planner.tui.controller import token_identity
import test_bridge


class ConsentTests(test_bridge.BridgeCase):
    """The bridge's fixtures without its tests (a subclass would run them again)."""

    def owner(self, call, *args):
        """The owner's own call, answered: `(outcome, error)` of its `done`."""
        event, box = threading.Event(), {}

        def done(outcome, error):
            box["answer"] = (outcome, error)
            event.set()

        self.assertTrue(call(*args, done))
        self.assertTrue(event.wait(30), "the job never answered")
        return box["answer"]

    def row(self, tool="M1"):
        return next(item for item in self.rows()["rows"] if item["id"] == tool)

    def start(self, rid):
        return self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid=rid)

    def test_a1_a_start_becomes_a_request_once_and_the_owners_yes_starts_it_once(self):
        """A1: at a level that asks, `zplan_start` stores one request and answers `awaiting_owner` with its id; the
        same start again is the same id (and the status lists it); a different action while it awaits is refused
        naming it; the owner's `consent` starts M1 once and a second `consent` starts nothing. The hook sees the
        change; an unknown id is refused and a quit that began refuses the job."""
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        seen = []
        controller.on_consent_request = lambda request: seen.append(request.state)
        first, again = self.start("one"), self.start("two")
        self.assertEqual(first["ok"]["status"], "awaiting_owner")
        self.assertEqual(again["ok"], first["ok"])
        rid = first["ok"]["request"]
        consent = self.call("zplan_status")["ok"]["consent"]
        self.assertEqual((consent["id"], consent["action"], consent["milestone"], consent["state"]),
                         (rid, "start", "M1", "awaiting"))
        self.assertIsNone(self.row()["attempt"])  # nothing started
        other = self.call("zplan_start", {"milestone": "M2", "revision": 1}, rid="other")
        self.assertEqual(other["error"], "autonomy.ask")  # the owner's answer is still owed: the policy's family
        self.assertIn(rid, other["message"])
        outcome, error = self.owner(controller.consent, rid)
        self.assertIsNone(error)
        self.assertEqual(outcome.kind, "done", outcome)
        self.assertEqual(self.row()["attempt"], 1)
        again, error = self.owner(controller.consent, rid)
        self.assertEqual((error, again.kind), (None, "done"))
        self.assertEqual(self.row()["attempt"], 1)  # the second yes started nothing
        self.assertEqual(seen, ["awaiting", "done"])
        unknown, error = self.owner(controller.consent, "nope")
        self.assertIsNone(unknown)
        self.assertIn("no longer valid", error)
        controller.begin_closing()
        self.assertFalse(controller.consent(rid))  # the closing guard of every mutation

    def test_a1_declining_starts_nothing(self):
        """A1: «no» stores `declined` with the owner's line and nothing starts; the architect may ask again."""
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        rid = self.start("one")["ok"]["request"]
        outcome, error = self.owner(controller.decline, rid)
        self.assertEqual((error, outcome.kind), (None, "declined"))
        self.assertIsNone(self.row()["attempt"])
        self.assertEqual(self.call("zplan_status")["ok"]["consent"]["state"], "declined")
        self.assertEqual(self.owner(controller.consent, rid)[0].kind, "declined")
        self.assertIsNone(self.row()["attempt"])
        self.assertNotEqual(self.start("two")["ok"]["request"], rid)

    def test_a2_a_request_whose_profile_moved_is_stale_and_runs_nothing(self):
        """A2: supervised, the architect's start is a request; the owner then edits the profile file and the
        owner's yes finds the digest moved: the request is `stale` with the reason and no attempt exists."""
        self.plan(0)
        self.write_profile(level="supervised", merge="off")
        controller = self.controller(profile=True)
        with patch.object(autonomy, "AUTOMATIC", False):
            rid = self.start("one")["ok"]["request"]
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"level": "manual"}}))
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "owner changes the profile")
        outcome, error = self.owner(controller.consent, rid)
        self.assertEqual((error, outcome.kind), (None, "stale"))
        self.assertIn("profile changed", outcome.lines[0])
        consent = self.call("zplan_status")["ok"]["consent"]
        self.assertEqual((consent["state"], consent["lines"]), ("stale", list(outcome.lines)))
        self.assertIsNone(self.row()["attempt"])

    def test_a1_a_resumed_or_rebriefed_attempt_runs_on_the_owners_yes_only(self):
        """A1: resume and rebrief become requests holding the row's exact token. The owner's yes opens attempt 2
        with the note (rebrief) or continues the same attempt under a fresh run id (resume); a token that moved
        between the ask and the yes (the owner resumed it meanwhile) is `stale` and adds nothing."""
        self.write_auto_profile()
        self.attempt("failed_recoverable")
        controller = self.controller(profile=True)
        row = self.row()
        with patch.object(autonomy, "AUTOMATIC", False):
            asked = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"], "note": "again"}, rid="b")
        self.assertEqual(asked["ok"]["status"], "awaiting_owner", asked)
        self.assertEqual(self.row()["run_id"], row["run_id"])  # nothing ran yet
        made, error = self.owner(controller.resume_run, token_identity(row["token"]))
        self.assertEqual((error, made.kind), (None, "attempt"))  # the attempt moves before the yes
        outcome, error = self.owner(controller.consent, asked["ok"]["request"])
        self.assertEqual((error, outcome.kind), (None, "stale"), outcome)
        self.assertEqual(self.row()["attempt"], 1)  # the stale request added none

        self.controller_stop()
        self.setUp()
        self.write_auto_profile()
        self.attempt("failed_recoverable")
        controller = self.controller(profile=True)
        row = self.row()
        with patch.object(autonomy, "AUTOMATIC", False):
            rid = self.call("zplan_resume", {"milestone": "M1", "token": row["token"]}, rid="r")["ok"]["request"]
        outcome, error = self.owner(controller.consent, rid)
        self.assertEqual((error, outcome.kind), (None, "done"), outcome)
        self.assertEqual((self.row()["attempt"], self.row()["run_id"] != row["run_id"]), (1, True))

        self.controller_stop()
        self.setUp()
        self.write_auto_profile()
        self.attempt("failed")
        controller = self.controller(profile=True)
        row = self.row()
        with patch.object(autonomy, "AUTOMATIC", False):
            rid = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"], "note": "again"},
                            rid="b")["ok"]["request"]
        outcome, error = self.owner(controller.consent, rid)
        self.assertEqual((error, outcome.kind), (None, "done"), outcome)
        self.assertEqual(self.row()["attempt"], 2)

    def test_a3_an_approve_and_a_merge_stay_the_owners_own_card_and_the_owners_act_clears_the_ask(self):
        """A3: supervised, `zplan_approve_plan` answers `awaiting_owner` with card `plan`, the status lists the ask
        and the owner's own approve approves and clears it; a high-risk merge is card `merge` and the owner's own
        merge lands it and clears that ask. No request is stored for either."""
        self.write_auto_profile()
        self.proposed(profile=True)
        controller = self.controller(profile=True)
        seen = []
        controller.on_asked = seen.append
        with patch.object(autonomy, "AUTOMATIC", False):
            reply = self.call("zplan_approve_plan", {"revision": 1}, rid="ap")
        self.assertEqual(reply["ok"], {"status": "awaiting_owner", "card": "plan"})
        status = self.call("zplan_status")["ok"]
        self.assertEqual(status["asked"], {"approve": 1})
        self.assertNotIn("consent", status)
        outcome, error = self.owner(controller.approve_plan, 1)
        self.assertEqual((error, outcome.kind), (None, "approved"))
        self.assertNotIn("asked", self.call("zplan_status")["ok"])
        self.assertEqual(seen, [{"approve": 1}, {}])
        self.controller_stop()

        self.setUp()
        self.awaiting_merge(level="supervised", merge="off", tier="high")
        controller = self.controller(profile=True)
        row = self.row()
        reply = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="mg")
        self.assertEqual(reply["ok"], {"status": "awaiting_owner", "card": "merge"})
        self.assertEqual(self.call("zplan_status")["ok"]["asked"], {"merge": "M1"})
        outcome, error = self.owner(controller.merge, token_identity(row["token"]))
        self.assertEqual((error, outcome.kind), (None, "integrated"), outcome)
        self.assertNotIn("asked", self.call("zplan_status")["ok"])


# The bridge's own tests are its module's; this class only borrows its fixtures.
for _name in dir(test_bridge.BridgeCase):
    if _name.startswith("test_") and not hasattr(ConsentTests.__dict__.get(_name), "__call__"):
        setattr(ConsentTests, _name, None)


if __name__ == "__main__":
    unittest.main()
