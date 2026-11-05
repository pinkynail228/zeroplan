"""Per-slice numbers in the ledger (docs/designs/2026-11-03-test-system.md revision 4, section 4.3).

A passed slice records its test and product lines (added, deleted), its sentence assertions before and after (the
ratchet's count), and the seconds its checks and gates took."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import slice_run_test as srt  # noqa: E402

PATH = "tests/test_calc.py"
TEST_CALC = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(1 + 1, 2)\n        self.assertIn(\"adds two numbers\", \"it adds two numbers\")\n"


class Numbers(srt.Base):
    def setUp(self):
        super().setUp()
        (self.repo / "tests").mkdir()
        (self.repo / PATH).write_text(TEST_CALC)
        self.git("add", ".")
        self.git("commit", "-qm", "tests")

    def test_a_passed_slice_records_its_lines_pins_and_gate_seconds(self):
        self.contract(files=["calc.py", PATH])
        unpinned = TEST_CALC.replace('self.assertIn("adds two numbers", "it adds two numbers")', "self.assertEqual(2 * 2, 4)")
        self.steps({"edit": {"calc.py": srt.GOOD, PATH: unpinned}}, srt.ACCEPT)
        self.assertEqual(self.go(), 0)
        passed = self.events("slice_pass")[0]
        self.assertEqual(passed["lines_product"], [1, 1])
        self.assertEqual(passed["lines_tests"], [1, 1])
        self.assertEqual(passed["text_pins"], [1, 0])
        self.assertGreater(passed["gate_s"], 0)


if __name__ == "__main__":
    unittest.main()
