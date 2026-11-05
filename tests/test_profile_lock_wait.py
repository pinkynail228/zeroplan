# tests/test_profile_lock_wait.py
"""Two zplan sessions started in the same second. The first holds the agent profile lock for a moment; the second
waits for it, within a bound, and goes on, instead of exiting with "Another zplan is updating the profile in …; try
again". A lock held past the wait is still the busy refusal (tests/test_agent_profile.py, A2)."""

import subprocess
import sys
import unittest

from terminal_planner import agent_profile
from test_agent_profile import OLDER, HomeTestCase, seed_config


class BriefLockTests(HomeTestCase):
    def test_a_lock_released_within_the_wait_lets_the_second_start_go_on(self):
        seed_config(self.home, OLDER)
        self.home.chmod(0o700)
        (self.home / agent_profile.LOCK_NAME).touch()
        code = ("import fcntl, sys, time; f = open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX); "
                "print('held', flush=True); time.sleep(1.0)")
        child = subprocess.Popen([sys.executable, "-c", code, str(self.home / agent_profile.LOCK_NAME)],
                                 stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "held")
            self.assertEqual(agent_profile.ensure(self.home), "replaced")  # waited for the release, then updated
        finally:
            child.wait(timeout=10)
            child.stdout.close()

    def test_the_wait_is_bounded(self):
        self.assertGreaterEqual(agent_profile.LOCK_WAIT_SECONDS, 2.0)
        self.assertLessEqual(agent_profile.LOCK_WAIT_SECONDS, 10.0)


if __name__ == "__main__":
    unittest.main()
