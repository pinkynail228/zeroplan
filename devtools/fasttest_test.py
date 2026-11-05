"""Lanes and scheduling of devtools/fasttest.py (docs/designs/2026-11-03-test-system.md revision 4, section 4.2).

The default lane skips the tests listed in tests/full_lane.txt; the full lane runs every test. Units start
longest-known first, from the seconds recorded by earlier runs."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

FASTTEST = pathlib.Path(__file__).resolve().parent / "fasttest.py"
MODULE = '''
import os, unittest
def mark(name):
    with open(os.environ["ORDER_FILE"], "a") as f:
        f.write(name + "\\n")
class Alpha(unittest.TestCase):
    def test_quick(self):
        mark("Alpha")
class Omega(unittest.TestCase):
    def test_long(self):
        mark("Omega")
    def test_slow_journey(self):
        mark("slow")
        self.fail("a full-lane test ran")
'''


class Lanes(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="fasttest-test.")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "tests").mkdir(parents=True)
        (self.repo / "tests" / "test_a.py").write_text(textwrap.dedent(MODULE))
        (self.repo / "tests" / "full_lane.txt").write_text("# slow journeys\n\ntests.test_a.Omega.test_slow_journey\n")
        for args in (("init", "-q"), ("config", "user.name", "t"), ("config", "user.email", "t@t"), ("add", "."), ("commit", "-qm", "base")):
            subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)
        self.wheels = self.tmp / "wheels"
        self.wheels.mkdir()
        (self.wheels / "textual-0.0.0-py3-none-any.whl").write_text("")
        self.order = self.tmp / "order.txt"
        self.times = self.tmp / "times.json"

    def fasttest(self, *args, lane=None):
        env = dict(os.environ, ZPLAN_TEST_WHEELHOUSE=str(self.wheels), ORDER_FILE=str(self.order), ZPLAN_FASTTEST_TIMES=str(self.times))
        env.pop("ZPLAN_TEST_LANE", None)
        if lane:
            env["ZPLAN_TEST_LANE"] = lane
        self.order.unlink(missing_ok=True)
        return subprocess.run([sys.executable, str(FASTTEST), "-j", "1", *args], cwd=self.repo, env=env, capture_output=True, text=True)

    def ran(self):
        return self.order.read_text().split() if self.order.exists() else []

    def test_the_default_lane_skips_the_full_lane_and_the_full_lane_runs_everything(self):
        r = self.fasttest()
        self.assertEqual(r.returncode, 0, "the default lane ran a full-lane test:\n" + r.stdout[-2000:])
        self.assertNotIn("slow", self.ran())
        self.assertIn("Alpha", self.ran())
        r = self.fasttest("--lane", "full")
        self.assertEqual(r.returncode, 1, r.stdout[-2000:])
        self.assertIn("slow", self.ran())
        self.assertEqual(self.fasttest(lane="full").returncode, 1)

    def test_the_longest_known_unit_starts_first_and_each_run_records_its_seconds(self):
        self.times.write_text(json.dumps({"tests.test_a.Omega": 30.0, "tests.test_a.Alpha": 1.0}))
        r = self.fasttest()
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        self.assertEqual(self.ran(), ["Omega", "Alpha"], "units must start longest-known first")
        recorded = json.loads(self.times.read_text())
        self.assertLess(recorded["tests.test_a.Omega"], 30.0)
        self.assertIn("tests.test_a.Alpha", recorded)


if __name__ == "__main__":
    unittest.main()
