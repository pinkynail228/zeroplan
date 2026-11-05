import os
import tempfile
import unittest

from shelf import store


class StoreTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        os.environ["SHELF_HOME"] = temp.name

    def test_add_gives_increasing_ids(self):
        self.assertEqual(store.add("A")["id"], 1)
        self.assertEqual(store.add("B")["id"], 2)

    def test_mark_read(self):
        store.add("A")
        self.assertTrue(store.mark_read(1)["read"])
        self.assertTrue(store.load()[0]["read"])

    def test_mark_read_unknown(self):
        with self.assertRaises(KeyError):
            store.mark_read(7)
