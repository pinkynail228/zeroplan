"""Acceptance for a2 S1: a subscription limit during review waits and reviews again."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from slice_run_test import ACCEPT, GOOD, Base


class ReviewLimit(Base):
    def test_limit_during_review_waits_and_reviews_again(self):
        self.contract()
        self.steps({"edit": {"calc.py": GOOD}}, {"limit": "You've hit your session limit"}, ACCEPT)
        code = self.go()
        limits = [e for e in self.events("limit") if e.get("stage") == "review"]
        self.assertEqual(len(limits), 1, "one limit event expected with stage review")
        self.assertEqual(code, 0)
        self.assertEqual(self.events("slice_pass")[0]["rounds"], 1)

    def test_long_reset_during_review_stops_the_slice(self):
        self.run_toml(limit_max_wait_s=1)
        self.contract()
        self.steps({"edit": {"calc.py": GOOD}}, {"limit": "You've hit your limit · resets 3am (Europe/Moscow)"}, ACCEPT)
        self.go()
        self.assertEqual(self.events("slice_fail")[0]["reason"], "limit_too_long", "review_limit_acceptance_test: long reset")


if __name__ == "__main__":
    unittest.main()
