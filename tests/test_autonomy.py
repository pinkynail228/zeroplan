"""C4: the architect's autonomy policy. `decide` is pure; `level` reads the accepted profile and never raises.

A5t2b: with the release gate on (`AUTOMATIC`, A4b and A7 merged 2026-10-25) auto and supervised let the architect
start, resume and re-brief; edit is allowed at every level (it only proposes, the approval stays gated). p2a: merge
follows the level and the candidate's risk tier (auto allows, supervised asks on high risk, manual asks); the merge
gate (`gates.merge`) only decides whether checks and the critic run.

Interpretations (the brief leaves them open):
- `decide` takes the level as data; `level(profile)` is the one reader of it. The Controller calls both, so a
  test that patches `autonomy.level` would only test the patch — these tests drive `decide` directly for the
  policy and `status_of`/`level` with a profile stand-in that has the one attribute they read (`status(write=False)`),
  plus `None` for "no profile". The Controller reads the status once (`status_of`) so its digest is the one both the
  preview's change check and `level_of` see.
- "unreadable" is any `Blocked`, `OSError` or `ValueError` from the status read (a corrupt or deleted store); it
  is manual, never a crash."""

import unittest
from unittest.mock import patch

from terminal_planner import autonomy
from terminal_planner.authority import Blocked


class _Resolved:
    def __init__(self, config):
        self.config = config


class _Status:
    def __init__(self, resolved):
        self.resolved = resolved


class _Profile:
    """The part of `process.Profile` that `autonomy.level` reads: `status(write=False).resolved.config`."""

    def __init__(self, config=None, raises=None):
        self.config, self.raises, self.calls = config, raises, []

    def status(self, write=True):
        self.calls.append(write)
        if self.raises is not None:
            raise self.raises
        return _Status(None if self.config is None else _Resolved(self.config))


class DecideTests(unittest.TestCase):
    def test_the_actions_are_exactly_the_gated_gates(self):
        """A5t2a/A5t2b C4: the policy names every action the Controller consults it for: the three A5t1 actions, the
        approve/resume/rebrief A5t2a adds, and the edit/merge A5t2b adds."""
        self.assertEqual(autonomy.ACTIONS, ("start", "stop", "approve", "resume", "rebrief", "edit", "merge"))

    def test_stop_is_allowed_at_every_level(self):
        for level in autonomy.LEVELS:
            with self.subTest(level):
                self.assertEqual(autonomy.decide(level, "stop"), "allow")

    def test_the_release_gate_is_on_after_a4b_and_a7(self):
        """A5t2b C3: the plan's release rule (automatic actions stay off until A4b and A7 are merged, both merged
        2026-10-25) is lifted, so the policy is live."""
        self.assertTrue(autonomy.AUTOMATIC)

    def test_actions_ask_at_every_level_while_the_release_gate_is_off(self):
        """The release gate as A5t1 shipped it: start, approve, resume and rebrief ask at every level. Patched off,
        it stays the same (a supplied profile never turns them on by itself)."""
        for level in autonomy.LEVELS:
            for action in ("start", "approve", "resume", "rebrief"):
                with self.subTest(level=level, action=action):
                    with patch.object(autonomy, "AUTOMATIC", False):
                        self.assertEqual(autonomy.decide(level, action), "ask")

    def test_with_the_gate_on_a_start_resume_and_rebrief_allow_for_auto_and_supervised_only(self):
        for action in ("start", "resume", "rebrief"):
            with self.subTest(action=action):
                self.assertEqual(autonomy.decide("auto", action), "allow")
                self.assertEqual(autonomy.decide("supervised", action), "allow")
                self.assertEqual(autonomy.decide("manual", action), "ask")
        self.assertEqual(autonomy.decide("auto", "stop"), "allow")

    def test_an_edit_is_allowed_at_every_level(self):
        """A5t2b C1: edit only proposes a new revision; the approval that lets it run stays gated, so every level
        allows it, and a patched-off release gate does not change that."""
        for level in autonomy.LEVELS:
            with self.subTest(level=level):
                self.assertEqual(autonomy.decide(level, "edit"), "allow")
                with patch.object(autonomy, "AUTOMATIC", False):
                    self.assertEqual(autonomy.decide(level, "edit"), "allow")

    def test_a_merge_follows_the_level_and_the_risk_tier_not_the_gate(self):
        """p2a A1: auto allows a merge at any tier and gate; supervised allows it below high and asks on high and on a
        tier it does not know (none included); manual asks. The merge gate never changes the answer."""
        for gate in (None, "off", "required"):
            for tier in ("low", "medium", "high", "odd", None):
                with self.subTest(gate=gate, tier=tier):
                    self.assertEqual(autonomy.decide("auto", "merge", gate, tier), "allow")
                    self.assertEqual(autonomy.decide("supervised", "merge", gate, tier),
                                     "allow" if tier in ("low", "medium") else "ask")
                    self.assertEqual(autonomy.decide("manual", "merge", gate, tier), "ask")
                    self.assertEqual(autonomy.decide("yolo", "merge", gate, tier), "ask")

    def test_with_the_gate_on_an_approve_is_allowed_for_auto_only(self):
        """A5t2a C4: with the gate on, only auto lets the architect approve the plan; supervised and manual plan
        approvals stay the owner's."""
        with patch.object(autonomy, "AUTOMATIC", True):
            self.assertEqual(autonomy.decide("auto", "approve"), "allow")
            self.assertEqual(autonomy.decide("supervised", "approve"), "ask")
            self.assertEqual(autonomy.decide("manual", "approve"), "ask")

    def test_an_unknown_level_or_action_asks(self):
        self.assertEqual(autonomy.decide("yolo", "start"), "ask")
        self.assertEqual(autonomy.decide("auto", "unknown"), "ask")
        with patch.object(autonomy, "AUTOMATIC", False):
            self.assertEqual(autonomy.decide("yolo", "start"), "ask")


class LevelTests(unittest.TestCase):
    def test_no_profile_is_manual(self):
        self.assertEqual(autonomy.level(None), "manual")
        self.assertEqual(autonomy.level_of(None), "manual")  # the Controller passes the status it read once

    def test_the_level_comes_from_the_accepted_profile_without_writing(self):
        for level in autonomy.LEVELS:
            with self.subTest(level):
                profile = _Profile({"autonomy": {"level": level}})
                self.assertEqual(autonomy.level(profile), level)
                self.assertEqual(profile.calls, [False])  # a pure read: a refusal never writes the store

    def test_preset_1_and_an_unresolved_profile_are_manual(self):
        self.assertEqual(autonomy.level(_Profile({"roles": {}})), "manual")  # /1 has no autonomy section
        self.assertEqual(autonomy.level(_Profile(None)), "manual")  # never/missing: nothing resolved

    def test_an_unreadable_or_unknown_level_is_manual(self):
        self.assertEqual(autonomy.level(_Profile(raises=Blocked("store", family="store.invalid"))), "manual")
        self.assertEqual(autonomy.level(_Profile(raises=OSError("gone"))), "manual")
        self.assertEqual(autonomy.level(_Profile({"autonomy": {"level": "yolo"}})), "manual")

    def test_level_of_reads_an_already_resolved_status(self):
        """The Controller reads the profile status once and binds the policy to that same digest; `level_of` is the
        reader of that status (no second read, so nothing can move between the preview and the decision)."""
        for level in autonomy.LEVELS:
            with self.subTest(level):
                self.assertEqual(autonomy.level_of(_Status(_Resolved({"autonomy": {"level": level}}))), level)
        self.assertEqual(autonomy.level_of(_Status(_Resolved({"roles": {}}))), "manual")  # /1: no autonomy section
        self.assertEqual(autonomy.level_of(_Status(None)), "manual")                      # unresolved

    def test_merge_gate_reads_the_resolved_config(self):
        self.assertEqual(autonomy.merge_gate(_Status(_Resolved({"gates": {"merge": "required"}}))), "required")
        self.assertEqual(autonomy.merge_gate(_Status(_Resolved({"gates": {"merge": "off"}}))), "off")
        self.assertIsNone(autonomy.merge_gate(_Status(_Resolved({}))))   # no gates section
        self.assertIsNone(autonomy.merge_gate(_Status(None)))            # unresolved
        self.assertIsNone(autonomy.merge_gate(None))                     # no profile

    def test_status_of_is_one_pure_read_and_never_raises(self):
        profile = _Profile({"autonomy": {"level": "auto"}})
        status = autonomy.status_of(profile)
        self.assertEqual(status.resolved.config, {"autonomy": {"level": "auto"}})
        self.assertEqual(profile.calls, [False])                       # write=False: a refusal never writes
        self.assertIsNone(autonomy.status_of(None))                    # no profile
        self.assertIsNone(autonomy.status_of(_Profile(raises=OSError("gone"))))  # unreadable -> None (manual)


if __name__ == "__main__":
    unittest.main()
