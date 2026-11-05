import contextlib
import io
import os
import tempfile
import unittest

from shelf import cli


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        os.environ["SHELF_HOME"] = temp.name

    def test_add_and_list(self):
        run("add", "Dune", "--author", "Frank Herbert")
        self.assertEqual(run("list"), (0, "1 [ ] Dune — Frank Herbert\n"))

    def test_queue_hides_read_books(self):
        run("add", "A")
        run("add", "B")
        run("done", "1")
        self.assertEqual(run("queue"), (0, "2 [ ] B\n"))
