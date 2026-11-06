"""role_outcomes (0.13 G5): counts by graph and node, readiness findings anywhere, unreadable stores counted."""
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import role_outcomes  # noqa: E402


def store(path, events):
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("create table v2_run_events (run_id text, sequence integer, event_json text)")
        for n, (node, signals, message) in enumerate(events):
            db.execute("insert into v2_run_events values ('r', ?, ?)", (n, json.dumps({
                "kind": "node_completed", "completion": {"reference": {"node": node}, "outcome": {
                    "status": "verifier", "signals": signals, "diagnostic": {"message": message}}}})))


class RoleOutcomes(unittest.TestCase):
    def test_counts_by_graph_and_node_with_readiness_findings_and_unreadable_stores(self):
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            store(root / "runs/a/runs.sqlite3", [("comprehension", {}, ""),
                                                 ("critic", {"verdict": "rejected"}, "1. readiness: T1 W1\n- readiness: T2 F2")])
            store(root / "runs/b/runs.sqlite3", [("worker", {}, ""), ("preflight", {"preflight": "ready"}, "ok")])
            (root / "runs/c").mkdir(parents=True)
            (root / "runs/c/runs.sqlite3").write_text("not a database")
            runs, counts, readiness, failing, unreadable = role_outcomes.outcomes(root)
        self.assertEqual((runs, unreadable, readiness), (2, 1, 2))
        self.assertEqual(counts["plan_check.critic"]["rejected"], 1)
        self.assertEqual(counts["milestone.preflight"]["ready"], 1)
        self.assertEqual(len(failing), 1)


if __name__ == "__main__":
    unittest.main()
