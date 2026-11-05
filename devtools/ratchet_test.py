"""The test ratchet (docs/designs/2026-11-03-test-system.md revision 4, section 4.1).

It compares tests/test_*.py between two trees. A change may not add sentence assertions, a test named after a brief
criterion or a test module, and may not drop an assertion, unless the contract's [ratchet] table declares it, each
entry as "<id or pattern>: <reason>"."""
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import shutil
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ratchet  # noqa: E402
import slice_run as sr  # noqa: E402
import slice_run_test as srt  # noqa: E402

PATH = "tests/test_calc.py"


def module(*tests):
    body = "".join(textwrap.indent(textwrap.dedent(t), "    ") for t in tests)
    return "import unittest\n\n\nclass T(unittest.TestCase):\n" + body


ADD = """
def test_add(self):
    self.assertEqual(add(2, 3), 5)
    self.assertIn("the plan is approved", text())
"""
ADD_UNPINNED = """
def test_add(self):
    self.assertEqual(add(2, 3), 5)
    self.assertEqual(state(), "approved")
"""
ADD_REPINNED = """
def test_add(self):
    self.assertEqual(add(2, 3), 5)
    self.assertIn("the plan was approved", text())
"""
ADD_DROPPED = """
def test_add(self):
    self.assertEqual(add(2, 3), 5)
"""
SUB_PINNED = """
def test_sub(self):
    self.assertIn("the owner decides now", text())
"""


def problems(base, head, allow=None):
    return ratchet.compare(base, head, allow)["problems"]


class Compare(unittest.TestCase):
    base = {PATH: module(ADD)}

    def test_an_unchanged_tree_passes(self):
        self.assertEqual(problems(self.base, dict(self.base)), [])

    def test_a_new_sentence_assertion_is_refused_unless_declared(self):
        head = {PATH: module(ADD, SUB_PINNED)}
        found = problems(self.base, head)
        self.assertTrue(found)
        self.assertTrue(any("tests.test_calc.T.test_sub" in p for p in found), found)
        self.assertEqual(problems(self.base, head, {"text_pins": ["tests.test_calc.T.test_sub: a required warning"], "new_tests": ["tests.test_calc.T.test_sub: the brief asks for it"]}), [])

    def test_a_new_test_is_refused_unless_the_brief_asks_for_it(self):
        head = {PATH: module(ADD, ADD_UNPINNED.replace("test_add", "test_sub"))}
        found = problems(self.base, head)
        self.assertTrue(any("tests.test_calc.T.test_sub" in p and "new_tests" in p for p in found), found)
        self.assertEqual(problems(self.base, head, {"new_tests": ["tests.test_calc.T.test_sub: the brief asks for it"]}), [])
        self.assertTrue(problems(self.base, head, {"new_tests": ["tests.test_calc.T.test_sub"]}), "an entry needs a reason")

    def test_unpinning_and_repinning_pass(self):
        unpinned = ratchet.compare(self.base, {PATH: module(ADD_UNPINNED)})
        self.assertEqual(unpinned["problems"], [])
        self.assertEqual(unpinned["text_pins"], (1, 0))
        self.assertEqual(problems(self.base, {PATH: module(ADD_REPINNED)}), [])

    def test_a_new_test_module_is_refused_unless_declared(self):
        head = {PATH: module(ADD), "tests/test_more.py": module(ADD_UNPINNED.replace("test_add", "test_more"))}
        found = problems(self.base, head)
        self.assertTrue(any("tests/test_more.py" in p for p in found), found)
        self.assertEqual(problems(self.base, head, {"new_modules": ["tests/test_more.py: a new product area"],
                                                    "new_tests": ["tests.test_more.*: the brief asks for them"]}), [])

    def test_a_new_criterion_named_test_is_refused_and_an_old_one_may_change(self):
        named = ADD_UNPINNED.replace("test_add", "test_a1_c2_adds")
        found = problems(self.base, {PATH: module(ADD, named)})
        self.assertTrue(any("test_a1_c2_adds" in p for p in found), found)
        old = {PATH: module(ADD.replace("test_add", "test_v6e_adds"))}
        changed = {PATH: module(ADD_UNPINNED.replace("test_add", "test_v6e_adds"))}
        self.assertEqual(problems(old, changed), [])
        self.assertEqual(problems(self.base, {PATH: module(ADD, ADD_UNPINNED.replace("test_add", "test_utf8_input"))},
                                  {"new_tests": ["tests.test_calc.T.test_utf8_input: the brief asks for it"]}), [])

    def test_a_dropped_assertion_is_refused_unless_declared_with_a_reason(self):
        head = {PATH: module(ADD_DROPPED)}
        found = problems(self.base, head)
        self.assertTrue(any("tests.test_calc.T.test_add" in p for p in found), found)
        self.assertEqual(problems(self.base, head, {"removes": ["tests.test_calc.T.test_add: the approval text moved to the screen"]}), [])
        self.assertTrue(problems(self.base, head, {"removes": ["tests.test_calc.T.test_add"]}), "an entry needs a reason")

    def test_a_renamed_test_keeps_its_assertions_and_a_deleted_one_needs_a_declaration(self):
        renamed = {PATH: module(ADD.replace("test_add", "test_adds_numbers"))}
        self.assertTrue(problems(self.base, renamed), "a rename is a new test id, declared like one")
        self.assertEqual(problems(self.base, renamed, {"new_tests": ["tests.test_calc.T.test_adds_numbers: renamed for the behaviour"]}), [])
        gone = {PATH: module(SUB_PINNED.replace("test_sub", "test_other").replace('self.assertIn("the owner decides now", text())', "self.assertTrue(ok())"))}
        found = problems(self.base, gone)
        self.assertTrue(any("tests.test_calc.T.test_add" in p for p in found), found)
        self.assertEqual(problems(self.base, gone, {"removes": ["tests.test_calc.T.*: the old adder is gone"],
                                                    "new_tests": ["tests.test_calc.T.test_other: the brief asks for it"]}), [])

    def test_only_test_modules_count(self):
        head = dict(self.base, **{"tests/support.py": "def helper():\n    assert 'two words' in text()\n",
                                   "terminal_planner/x.py": "X = 'some sentence here'\n"})
        self.assertEqual(problems(self.base, head), [])


class Cli(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp(prefix="ratchet-test.")).resolve()
        self.addCleanup(shutil.rmtree, self.repo, True)
        for args in (("init", "-q", "-b", "dev"), ("config", "user.name", "t"), ("config", "user.email", "t@t")):
            self.git(*args)
        (self.repo / "tests").mkdir()
        (self.repo / PATH).write_text(module(ADD))
        self.git("add", ".")
        self.git("commit", "-qm", "base")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "ratchet.py"), *args, "--repo", str(self.repo)], capture_output=True, text=True)

    def test_the_working_tree_and_a_commit_are_checked_and_a_contract_declares_exceptions(self):
        (self.repo / PATH).write_text(module(ADD, SUB_PINNED))
        refused = self.cli("HEAD")
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn("tests.test_calc.T.test_sub", refused.stdout)
        contract = self.repo / "c.toml"
        contract.write_text('title = "x"\n\n[ratchet]\ntext_pins = ["tests.test_calc.T.test_sub: a required warning"]\n'
                            'new_tests = ["tests.test_calc.T.test_sub: the brief asks for it"]\n')
        self.assertEqual(self.cli("HEAD", "--contract", str(contract)).returncode, 0)
        self.git("commit", "-qam", "pin")
        self.assertEqual(self.cli("HEAD~1", "HEAD").returncode, 1)
        self.assertEqual(self.cli("HEAD").returncode, 0)

    def test_the_commit_msg_hook_refuses_an_undeclared_new_test_and_reads_trailers(self):
        """A direct commit gets the same ratchet as a slice; its exceptions are trailers of the message."""
        (self.repo / PATH).write_text(module(ADD, ADD_UNPINNED.replace("test_add", "test_sub")))
        self.git("add", PATH)
        message = self.repo / "MSG"
        message.write_text("Add sub\n")
        self.assertEqual(self.cli("--hook", str(message)).returncode, 1)
        message.write_text("Add sub\n\nRatchet-new-test: tests.test_calc.T.test_sub: the owner asked for subtraction\n")
        self.assertEqual(self.cli("--hook", str(message)).returncode, 0)


TEST_CALC = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(1 + 1, 2)\n        self.assertIn(\"adds two numbers\", \"it adds two numbers\")\n"


class Runner(srt.Base):
    def setUp(self):
        super().setUp()
        (self.repo / "tests").mkdir()
        (self.repo / PATH).write_text(TEST_CALC)
        self.git("add", ".")
        self.git("commit", "-qm", "tests")

    def test_a_worker_that_drops_an_assertion_fails_the_ratchet_gate(self):
        self.contract(files=["calc.py", PATH])
        dropped = TEST_CALC.replace('        self.assertIn("adds two numbers", "it adds two numbers")\n', "")
        self.steps({"edit": {"calc.py": srt.GOOD, PATH: dropped}}, {"edit": {"calc.py": srt.GOOD, PATH: dropped}})
        self.assertEqual(self.go(), 10)
        self.assertEqual([e["gate"] for e in self.events("round_failed")], ["ratchet", "ratchet"])
        self.assertEqual(self.events("slice_pass"), [])

    def test_a_worker_that_unpins_a_text_check_passes(self):
        self.contract(files=["calc.py", PATH])
        unpinned = TEST_CALC.replace('self.assertIn("adds two numbers", "it adds two numbers")', "self.assertEqual(2 * 2, 4)")
        self.steps({"edit": {"calc.py": srt.GOOD, PATH: unpinned}}, srt.ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual(len(self.events("slice_pass")), 1)



if __name__ == "__main__":
    unittest.main()
