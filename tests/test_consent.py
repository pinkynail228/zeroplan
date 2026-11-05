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
from terminal_planner.tui import controller as controller_module
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
        asked, again, other, yes = self.starts()  # v2d A2: each call is a result; the same ask is the same id
        self.assertEqual((asked["outcome"], asked["origin"], asked["request"], asked["subject"]),
                         ("asked", "architect", "one", {"milestone": "M1", "attempt": 1}))
        self.assertEqual((again["outcome"], again["request"]), ("asked", "two"))
        self.assertIn(rid, asked["lines"][0])
        self.assertEqual((other["outcome"], other["family"], other["subject"]),
                         ("refused", "autonomy.ask", {"milestone": "M2", "attempt": 1}))
        self.assertEqual((yes["outcome"], yes["origin"], yes["request"], yes["subject"]),
                         ("done", "owner", rid, {"milestone": "M1", "attempt": 1}))
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

    def move_level(self, level):
        """The owner changes the level in /setup: the profile file moves under the open controller."""
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"level": level}}))

    def said(self, controller, text, tool, args, rid, identity=None):
        """One owner turn's call: the turn is open for the call, as the chat's is for the architect's reply."""
        token = controller.begin_turn(text, 4, identity=identity)
        try:
            return self.call(tool, args, rid=rid, turn=token)
        finally:
            controller.end_turn(token)

    def test_v6b_a1_a2_a4_an_owner_turns_start_runs_as_the_owners_own_and_events_still_ask(self):
        """V6b A1, A2, A4: at manual an event turn's start (no token, a forged one, a closed one) is a consent
        request as before; an owner turn's start runs at once with no request, and its result is origin owner, via
        chat, with the turn's message reference and the bridge request id, first line «Started at your word: …»; it
        reaches `on_result` once, and a new controller on the same store lists it with these fields.

        Interpretations: the other verbs say «<verb> at your word» in the same way; the architect's answer to a call
        that ran as the owner's own carries `origin: owner`."""
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        token = controller.begin_turn("old", 1)
        controller.end_turn(token)
        for index, turn in enumerate((None, "f" * 32, token)):
            reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="e%d" % index, turn=turn)
            self.assertEqual(reply["ok"]["status"], "awaiting_owner", reply)
        self.assertIsNone(self.row()["attempt"])
        self.controller_stop()

        self.setUp()
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        heard = []
        controller.on_result = heard.append
        reply = self.said(controller, "Start M1 please", "zplan_start", {"milestone": "M1", "revision": 1}, "own")
        self.assertEqual((reply["ok"]["origin"], reply["ok"]["attempt"]), ("owner", 1), reply)
        self.assertNotIn("consent", self.call("zplan_status")["ok"])
        self.assertEqual(self.row()["attempt"], 1)
        [result] = self.starts()
        self.assertEqual((result["operation"], result["outcome"], result["origin"], result["via"], result["request"],
                          result["turn"], result["subject"]),
                         ("start", "done", "owner", "chat", "own", {"text": "Start M1 please", "occurrence": 4},
                          {"milestone": "M1", "attempt": 1}))
        self.assertEqual(result["lines"][0], "Started at your word: «Start M1 please»")
        self.assertEqual([item["seq"] for item in heard], [result["seq"]])
        self.controller_stop()
        self.controller()
        self.assertEqual(self.starts(), [result])

    def test_v6b_a1_an_owner_turn_approves_merges_resumes_and_rebriefs_as_the_owners_own(self):
        """An owner turn can approve, resume and rebrief with conversational provenance. It cannot
        consent to an unverified merge: that requires the distinct explicit owner action.
        An event turn's approve stays the card (`asked`)."""
        self.write_profile(level="manual")
        self.proposed(profile=True)
        controller = self.controller(profile=True)
        events = self.call("zplan_approve_plan", {"revision": 1}, rid="ev")
        self.assertEqual(events["ok"], {"status": "awaiting_owner", "card": "plan"})
        reply = self.said(controller, "Approve it", "zplan_approve_plan", {"revision": 1}, "ap",
                          identity={"shown_plan": 1})
        self.assertEqual(reply["ok"], {"revision": 1, "status": "approved", "origin": "owner"})
        approvals = [r for r in self.call("zplan_status")["ok"]["results"] if r["operation"] == "approve"]
        self.assertEqual([(r["outcome"], r["origin"]) for r in approvals], [("asked", "architect"), ("done", "owner")])
        self.assertEqual((approvals[-1]["via"], approvals[-1]["turn"]["text"], approvals[-1]["lines"][0]),
                         ("chat", "Approve it", "Approved at your word: «Approve it»"))
        self.assertNotIn("asked", self.call("zplan_status")["ok"])
        self.controller_stop()

        self.setUp()
        self.awaiting_merge(level="manual", merge="off", tier="low")
        controller = self.controller(profile=True)
        row = self.row()
        reply = self.said(controller, "Merge M1", "zplan_merge", {"milestone": "M1", "token": row["token"]}, "mg")
        self.assertEqual(reply["ok"], {"status": "awaiting_owner", "card": "merge"}, reply)
        merge = next(r for r in self.call("zplan_status")["ok"]["results"] if r["operation"] == "merge")
        self.assertEqual((merge["outcome"], merge["origin"], merge["via"]),
                         ("asked", "owner", "chat"))
        self.assertEqual(merge["turn"]["text"], "Merge M1")
        self.assertEqual(self.row()["state"], "awaiting_merge")
        outcome, error = self.owner(controller.merge, token_identity(row["token"]))
        self.assertEqual((error, outcome.kind), (None, "integrated"), outcome)
        self.assertEqual(self.row()["state"], "integrated")
        self.controller_stop()

        self.setUp()
        self.write_profile(level="manual")
        self.attempt("failed_recoverable")
        controller = self.controller(profile=True)
        row = self.row()
        reply = self.said(controller, "Continue M1", "zplan_resume", {"milestone": "M1", "token": row["token"]}, "rs")
        self.assertEqual(reply["ok"]["origin"], "owner", reply)
        self.assertNotIn("consent", self.call("zplan_status")["ok"])
        self.assertNotEqual(self.row()["run_id"], row["run_id"])
        self.assertEqual(self.attempts()[-1]["lines"][0], "Continued at your word: «Continue M1»")
        self.controller_stop()

        self.setUp()
        self.write_profile(level="manual")
        self.attempt("failed")
        controller = self.controller(profile=True)
        row = self.row()
        reply = self.said(controller, "Try again", "zplan_rebrief",
                          {"milestone": "M1", "token": row["token"], "note": "again"}, "rb")
        self.assertEqual((reply["ok"]["attempt"], reply["ok"]["origin"]), (2, "owner"), reply)
        self.assertNotIn("consent", self.call("zplan_status")["ok"])
        self.assertEqual(self.attempts()[-1]["lines"][0], "Started a new attempt at your word: «Try again»")

    def test_queued_owner_message_provenance_names_its_persisted_transcript_position(self):
        from test_tui_chat import Fixture, Port, REPLY, event
        from terminal_planner.tui.chat import ArchitectChat
        import time

        self.write_profile(level="manual")
        self.proposed(profile=True)
        controller = self.controller(profile=True)
        fixture = Fixture(self.root, self.project)
        release = self.root / "release-event"
        fixture.script([{"lines": REPLY, "release": str(release)}, {"lines": REPLY}])
        replies = []
        case = self

        class OwnerPort(Port):
            def begin_turn(self, message, occurrence=None):
                token = controller.begin_turn(message, occurrence, identity={"shown_plan": 1})
                replies.append(case.call("zplan_approve_plan", {"revision": 1}, rid="queued", turn=token))
                return token

            def end_turn(self, token):
                controller.end_turn(token)

        port = OwnerPort([event(1)], {})
        chat = ArchitectChat(self.project, fixture.prepare(), binding=fixture.binding(), feed=port)
        self.addCleanup(chat.close)
        chat.start()

        def wait(condition):
            end = time.monotonic() + 10
            while not condition() and time.monotonic() < end:
                time.sleep(.01)
            self.assertTrue(condition(), chat.state)

        try:
            wait(lambda: chat.turn_running and fixture.calls())
            self.assertEqual(chat.send("Approve this queued plan"), (True, ""))
            rows = fixture.store().transcript()
            owner_position, owner = next((i, row) for i, row in enumerate(rows) if row["role"] == "owner")
        finally:
            release.touch()
        wait(lambda: port.handled == [1] and not chat.busy)
        self.assertEqual(replies[0]["ok"]["status"], "approved", replies)
        result = next(r for r in self.call("zplan_status")["ok"]["results"] if r["request"] == "queued")
        self.assertEqual((result["origin"], result["via"]), ("owner", "chat"))
        self.assertEqual(result["turn"], {"text": owner["text"], "occurrence": owner_position,
                                            "shown_plan": 1})
        self.assertEqual(fixture.store().transcript()[result["turn"]["occurrence"]]["id"], owner["id"])
        self.assertEqual([row["role"] for row in fixture.store().transcript()],
                         ["events", "owner", "architect", "architect"])

    def test_a_word_approves_only_the_plan_the_owner_saw(self):
        """A yes in words approves the revision the owner's screen showed as waiting when he wrote; a word written
        before the plan was shown gets the owner's card."""
        self.write_profile(level="manual")
        self.proposed(profile=True)
        controller = self.controller(profile=True)
        reply = self.said(controller, "yes", "zplan_approve_plan", {"revision": 1}, "unseen", identity={"shown_plan": None})
        self.assertEqual(reply["ok"], {"status": "awaiting_owner", "card": "plan"}, reply)
        reply = self.said(controller, "yes", "zplan_approve_plan", {"revision": 1}, "seen", identity={"shown_plan": 1})
        self.assertEqual(reply["ok"], {"revision": 1, "status": "approved", "origin": "owner"}, reply)

    def test_v6b_a3_a_high_risk_merge_and_a_needs_owner_answer_stay_asked_in_an_owner_turn(self):
        """V6b A3: supervised, an owner turn's merge of a high-risk candidate is the merge card (`asked`, nothing
        merged); a rebrief that answers a needs_owner question is a consent request, nothing run."""
        self.awaiting_merge(level="supervised", merge="off", tier="high")
        controller = self.controller(profile=True)
        row = self.row()
        reply = self.said(controller, "Merge M1", "zplan_merge", {"milestone": "M1", "token": row["token"]}, "mg")
        self.assertEqual(reply["ok"], {"status": "awaiting_owner", "card": "merge"})
        self.assertEqual(self.call("zplan_status")["ok"]["asked"], {"merge": "M1"})
        merge = next(r for r in self.call("zplan_status")["ok"]["results"] if r["operation"] == "merge")
        self.assertEqual((merge["outcome"], merge["origin"], merge["via"], merge["turn"]["text"]),
                         ("asked", "owner", "chat", "Merge M1"))  # v6c A2: asked is the owner's result too
        self.controller_stop()

        for level in ("supervised", "manual"):  # v6c A1: whatever `decide` says at the level
            self.setUp()
            self.write_profile(level=level)
            self.attempt("needs_owner")
            controller = self.controller(profile=True)
            row = self.row()
            reply = self.said(controller, "Answer it", "zplan_rebrief",
                              {"milestone": "M1", "token": row["token"], "note": "yes"}, "rb")
            self.assertEqual(reply["ok"]["status"], "awaiting_owner", (level, reply))
            self.assertEqual(self.call("zplan_status")["ok"]["consent"]["state"], "awaiting")
            self.assertEqual(self.row()["attempt"], 1)
            asked = self.attempts()[-1]
            self.assertEqual((asked["outcome"], asked["origin"], asked["via"]), ("asked", "owner", "chat"))
            self.controller_stop()

        self.setUp()
        self.write_profile(level="auto")  # auto keeps today's behaviour: the answer runs
        self.attempt("needs_owner")
        controller = self.controller(profile=True)
        row = self.row()
        reply = self.said(controller, "Answer it", "zplan_rebrief",
                          {"milestone": "M1", "token": row["token"], "note": "yes"}, "rb")
        self.assertEqual(reply["ok"]["attempt"], 2, reply)

    def test_v6c_a2_every_result_of_an_owner_turns_call_is_the_owners_via_chat_also_after_a_reopen(self):
        """V6c A2: at manual an owner turn's merge of a low-risk candidate whose check fails leaves `refused` and an
        owner turn's start of another plan revision leaves `refused`, both origin owner, via chat, with the turn;
        results.json keeps them for a new controller. An events turn's failing call stays the architect's."""
        self.awaiting_merge(level="manual", merge="required", tier="low",
                            checks=[{"name": "unit", "argv": ["false"], "timeout_s": 60}])
        controller = self.controller(profile=True)
        row = self.row()
        reply = self.said(controller, "Merge M1", "zplan_merge", {"milestone": "M1", "token": row["token"]}, "mg")
        self.assertEqual(reply["ok"]["kind"], "refused", reply)
        self.said(controller, "Start M1", "zplan_start", {"milestone": "M1", "revision": 9}, "st")
        self.call("zplan_start", {"milestone": "M2", "revision": 9}, rid="ev")
        kept = [r for r in self.call("zplan_status")["ok"]["results"] if r["operation"] in ("merge", "start")]
        self.assertEqual([(r["operation"], r["outcome"], r["origin"], r.get("via")) for r in kept],
                         [("merge", "refused", "owner", "chat"), ("start", "refused", "owner", "chat"),
                          ("start", "refused", "architect", None)])
        self.assertEqual([r["turn"]["text"] for r in kept[:2]], ["Merge M1", "Start M1"])
        self.controller_stop()
        self.controller()
        reopened = [r for r in self.call("zplan_status")["ok"]["results"] if r["operation"] in ("merge", "start")]
        self.assertEqual(reopened, kept)

    def test_v6c_a3_an_owner_turn_doing_what_a_request_asked_settles_it_and_a_different_one_is_left(self):
        """V6c A3: at manual an events turn's start of M1 awaits; an owner turn's start of another revision fails and
        leaves it awaiting; an owner turn's start of M1 starts it once and settles the request `done` with the
        receipt line, so the status no longer waits and a later events request is not blocked by it."""
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        seen = []
        controller.on_consent_request = lambda request: seen.append(request.state)
        rid = self.start("ev")["ok"]["request"]
        self.said(controller, "Start M1", "zplan_start", {"milestone": "M1", "revision": 9}, "bad")
        self.assertEqual(self.call("zplan_status")["ok"]["consent"]["state"], "awaiting")
        reply = self.said(controller, "Start M1", "zplan_start", {"milestone": "M1", "revision": 1}, "own")
        self.assertEqual((reply["ok"]["origin"], reply["ok"]["attempt"]), ("owner", 1), reply)
        consent = self.call("zplan_status")["ok"]["consent"]
        self.assertEqual((consent["id"], consent["state"]), (rid, "done"))
        self.assertIn("M1 started", consent["lines"][0])
        self.assertEqual(seen, ["awaiting", "done"])
        self.assertEqual(self.row()["attempt"], 1)
        later = self.call("zplan_start", {"milestone": "M2", "revision": 1}, rid="later")
        self.assertEqual(later["ok"]["status"], "awaiting_owner", later)  # a new request, not refused by the old one
        self.assertNotEqual(later["ok"]["request"], rid)

        self.controller_stop()  # v6d A1/A2: the same on the allow path, once the owner has raised the level
        self.setUp()
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        seen = []
        controller.on_consent_request = lambda request: seen.append(request.state)
        self.call("zplan_start", {"milestone": "M2", "revision": 1}, rid="m2")
        self.move_level("supervised")
        self.said(controller, "Start M1", "zplan_start", {"milestone": "M1", "revision": 1}, "own1")
        self.assertEqual(self.call("zplan_status")["ok"]["consent"]["state"], "awaiting")  # A2: M2's request stays
        self.assertEqual(seen, ["awaiting"])
        self.controller_stop()

        self.setUp()
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        seen = []
        controller.on_consent_request = lambda request: seen.append(request.state)
        rid = self.start("ev")["ok"]["request"]
        self.move_level("supervised")
        reply = self.said(controller, "Start M1", "zplan_start", {"milestone": "M1", "revision": 1}, "own")
        self.assertEqual(reply["ok"]["attempt"], 1, reply)  # A1: started once, by the allow path
        consent = self.call("zplan_status")["ok"]["consent"]
        self.assertEqual((consent["id"], consent["state"]), (rid, "done"))
        self.assertIn("M1 started", consent["lines"][0])
        self.assertEqual(seen, ["awaiting", "done"])
        self.assertEqual(self.row()["attempt"], 1)
        self.move_level("manual")
        later = self.call("zplan_start", {"milestone": "M2", "revision": 1}, rid="later")
        self.assertEqual(later["ok"]["status"], "awaiting_owner", later)
        self.assertNotEqual(later["ok"]["request"], rid)

    def starts(self):
        return [r for r in self.call("zplan_status")["ok"]["results"] if r["operation"] == "start"]

    def test_v2d_the_owners_start_leaves_one_result_whichever_way_it_ends(self):
        """v2d A1/A3/A4: a readiness block of the preview is one `refused` result of the owner with the checks'
        lines (and the outcome carries the same lines for `run_note`); a preview that is only shown is no result;
        a profile that moved between the preview and `start_run` is one `refused` result `process.changed` with the
        profile-change line, nothing started; the start that goes through is exactly one more result, `done`, of
        attempt 1. Interpretation: the owner's `refused` for a block names `action.refused`, the family the
        architect's blocked start has; the result's subject attempt of a block is the next attempt number."""
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        check = controller_module.Check("git", False, "Git is missing — [i] to fix", "", "", None)
        with patch.object(controller_module.Controller, "_blocked",
                          staticmethod(lambda app, action="start": controller_module.Outcome("blocked", (check,)))):
            blocked, error = self.owner(controller.preview_start, "M1")
        self.assertEqual((error, blocked.kind, blocked.lines), (None, "blocked", ("Git is missing — [i] to fix",)))
        [result] = self.starts()
        self.assertEqual((result["outcome"], result["family"], result["origin"], result["subject"], result["lines"]),
                         ("refused", "action.refused", "owner", {"milestone": "M1", "attempt": 1},
                          ["Git is missing — [i] to fix"]))
        preview, error = self.owner(controller.preview_start, "M1")
        self.assertEqual((error, preview.kind), (None, "preview"))
        self.assertEqual(len(self.starts()), 1)  # shown, not a result
        (self.project / process.PROFILE_FILE).write_text(json.dumps(  # the profile moves after the preview
            {"preset": process.PRESET_V2, "autonomy": {"level": "supervised"}}))
        changed, error = self.owner(controller.start_run, preview.data)
        self.assertEqual((error, changed.kind), (None, "changed"))
        refused = self.starts()[-1]
        self.assertEqual((len(self.starts()), refused["outcome"], refused["family"], refused["origin"]),
                         (2, "refused", "process.changed", "owner"))
        self.assertIn("The process profile changed", refused["lines"][0])
        self.assertIsNone(self.row()["attempt"])
        started, error = self.owner(controller.start_run, changed.data)
        self.assertEqual((error, started.kind), (None, "started"))
        done = self.starts()
        self.assertEqual(len(done), 3)  # one result per call: the block, the moved profile, the start
        self.assertEqual((done[-1]["outcome"], done[-1]["origin"], done[-1]["subject"], done[-1]["lines"]),
                         ("done", "owner", {"milestone": "M1", "attempt": 1}, ["M1 started · plan r1 · attempt 1"]))
        self.assertEqual(self.row()["attempt"], 1)

    def test_v2h_a2_an_error_in_the_grant_leaves_one_failed_result_and_reaches_the_caller(self):
        """v2h A2: the owner's yes to a start request whose grant raises an error other than a refusal leaves one
        owner result (`failed`, family unknown, the request id) and the error still reaches the caller. Interpretation:
        the request itself stays awaiting (no `_settled`), as nothing is known to have run."""
        self.plan(0)
        self.write_profile(level="manual")
        controller = self.controller(profile=True)
        rid = self.start("one")["ok"]["request"]
        with patch.object(controller_module.Controller, "_grant", side_effect=RuntimeError("boom")):
            outcome, error = self.owner(controller.consent, rid)
        self.assertIsNone(outcome)
        self.assertIn("boom", str(error))
        asked, failed = self.starts()
        self.assertEqual(asked["outcome"], "asked")
        self.assertEqual((failed["outcome"], failed["family"], failed["origin"], failed["request"], failed["subject"]),
                         ("failed", "unknown_error", "owner", rid, {"milestone": "M1", "attempt": 1}))
        self.assertEqual(failed["lines"], ["boom"])

    def attempts(self):
        ops = ("resume", "rebrief", "answer")
        return [r for r in self.call("zplan_status")["ok"]["results"] if r["operation"] in ops]

    def test_v2f_resume_new_attempt_and_answer_leave_one_result_each_naming_both_attempts(self):
        """v2f A1-A4: each call of resume, new attempt and answer is exactly one result. The owner's resume (failed
        attempt 1) is `resume` done, owner, subject attempt 1 created 1; a readiness block is `refused`
        `action.refused` with the check's line (the outcome carries the same line for `run_note`) and has no
        `created`; a token that moved is `refused` with the staleness family. The architect's rebrief at auto is
        `rebrief` done, architect, with the bridge request id, attempt 1 created 2; at manual it is `asked` (the
        ConsentRequest id in the line) and the owner's yes one more result, `done`, owner, request = the
        ConsentRequest id, created 2. The owner's new attempt is `rebrief` and the owner's answer to a `needs_owner`
        attempt is `answer`, created 2. Interpretations: `created` is a key of the subject (the subject says which
        attempt it acted on and which one runs); the architect's results also reach `on_result`, the owner's do not;
        the owner's rebrief is the operation `rebrief` whichever of its two service calls (`retry`, `answer`) ran."""
        self.write_auto_profile()
        self.attempt("failed_recoverable")
        controller = self.controller(profile=True)
        heard = []
        controller.on_result = heard.append
        row = self.row()
        token = token_identity(row["token"])
        check = controller_module.Check("git", False, "Git is missing — [i] to fix", "", "", None)
        with patch.object(controller_module.Controller, "_blocked",
                          staticmethod(lambda app, action="start": controller_module.Outcome("blocked", (check,)))):
            blocked, error = self.owner(controller.resume_run, token)
        self.assertEqual((error, blocked.kind, blocked.lines), (None, "blocked", ("Git is missing — [i] to fix",)))
        [result] = self.attempts()  # one call, one result
        self.assertEqual((result["operation"], result["outcome"], result["family"], result["origin"],
                          result["subject"], result["lines"]),
                         ("resume", "refused", "action.refused", "owner", {"milestone": "M1", "attempt": 1},
                          ["Git is missing — [i] to fix"]))
        made, error = self.owner(controller.resume_run, token)
        self.assertEqual((error, made.kind), (None, "attempt"))
        done = self.attempts()[1:]
        self.assertEqual(len(done), 1)
        self.assertEqual((done[0]["operation"], done[0]["outcome"], done[0]["origin"], done[0]["subject"]),
                         ("resume", "done", "owner", {"milestone": "M1", "attempt": 1, "created": 1}))
        moved, error = self.owner(controller.resume_run, token)  # the attempt has a fresh run id now
        self.assertEqual((error, moved.kind), (None, "stale"))
        stale = self.attempts()[-1]
        self.assertEqual((len(self.attempts()), stale["outcome"], stale["family"], stale["lines"]),
                         (3, "refused", "action.refused", list(moved.lines)))
        self.assertEqual(heard, [])  # the owner's own are not sent to the screen again

        self.controller_stop()
        self.setUp()
        self.write_auto_profile()
        self.attempt("failed")
        controller = self.controller(profile=True)
        heard = []
        controller.on_result = heard.append
        row = self.row()
        reply = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"], "note": "again"}, rid="auto")
        self.assertEqual(reply["ok"]["attempt"], 2)
        [result] = self.attempts()
        self.assertEqual((result["operation"], result["outcome"], result["origin"], result["request"],
                          result["subject"]), ("rebrief", "done", "architect", "auto",
                                               {"milestone": "M1", "attempt": 1, "created": 2}))
        self.assertEqual([item["seq"] for item in heard], [result["seq"]])  # the owner hears it once

        self.controller_stop()
        self.setUp()
        self.write_auto_profile()
        self.attempt("failed")
        controller = self.controller(profile=True)
        row = self.row()
        with patch.object(autonomy, "AUTOMATIC", False):
            rid = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"], "note": "again"},
                            rid="ask")["ok"]["request"]
        [asked] = self.attempts()
        self.assertEqual((asked["outcome"], asked["origin"], asked["request"], asked["subject"]),
                         ("asked", "architect", "ask", {"milestone": "M1", "attempt": 1}))
        self.assertIn(rid, asked["lines"][0])
        outcome, error = self.owner(controller.consent, rid)
        self.assertEqual((error, outcome.kind), (None, "done"), outcome)
        yes = self.attempts()[1:]
        self.assertEqual(len(yes), 1)
        self.assertEqual((yes[0]["operation"], yes[0]["outcome"], yes[0]["origin"], yes[0]["request"],
                          yes[0]["subject"]), ("rebrief", "done", "owner", rid,
                                               {"milestone": "M1", "attempt": 1, "created": 2}))

        self.controller_stop()
        self.setUp()
        self.write_auto_profile()
        self.attempt("failed")
        controller = self.controller(profile=True)
        made, error = self.owner(controller.new_attempt, token_identity(self.row()["token"]), "retry")
        self.assertEqual((error, made.kind), (None, "attempt"))
        [result] = self.attempts()
        self.assertEqual((result["operation"], result["outcome"], result["origin"], result["subject"]),
                         ("rebrief", "done", "owner", {"milestone": "M1", "attempt": 1, "created": 2}))

        self.controller_stop()
        self.setUp()
        self.write_auto_profile()
        self.attempt("needs_owner")
        controller = self.controller(profile=True)
        made, error = self.owner(controller.answer, token_identity(self.row()["token"]), "use the fixture path")
        self.assertEqual((error, made.kind), (None, "attempt"))
        [result] = self.attempts()
        self.assertEqual((result["operation"], result["outcome"], result["origin"], result["subject"]),
                         ("answer", "done", "owner", {"milestone": "M1", "attempt": 1, "created": 2}))


# The bridge's own tests are its module's; this class only borrows its fixtures.
for _name in dir(test_bridge.BridgeCase):
    if _name.startswith("test_") and not hasattr(ConsentTests.__dict__.get(_name), "__call__"):
        setattr(ConsentTests, _name, None)


if __name__ == "__main__":
    unittest.main()
