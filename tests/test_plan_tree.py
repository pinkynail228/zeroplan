"""Plan task tree (P3a A1-A5): plan order and nesting, statuses from the manifest, an added manifest task, a
milestone without a manifest, the done/tasks-not-dropped counter and ids shown once.

Interpretation: an added manifest task can be the first open one, so it also shows as `current` (`+ ▸`); the
counter counts added tasks and excludes dropped ones. Fixtures are plain proposal/manifest data: no files.
"""

import unittest

from terminal_planner import plan_tree


def proposal():
    return {"requirements": [{"id": "R1", "text": "r"}],
            "milestones": [
                {"id": "M1", "title": "Title1", "depends_on": [],
                 "slices": [{"id": "S1", "title": "Title", "requirements": ["R1"],
                             "tasks": [{"id": tid, "title": "Title", "checks": ["check"]}
                                       for tid in ("T1", "T2", "T3")]}]},
                {"id": "M2", "title": "Title2", "depends_on": ["M1"],
                 "slices": [{"id": "S2", "title": "Title", "requirements": ["R1"],
                             "tasks": [{"id": "T4", "title": "Title", "checks": ["check"]}]}]}]}


def manifest(items):
    return {"tasks": [{"id": tid, "title": "Title", "checks": ["check"], "status": status,
                       "origin": origin, "notes": ""} for tid, status, origin in items]}


JOINT = proposal()
MANIFESTS = {"M1": manifest([("T1", "done", "plan"), ("T2", "open", "plan"), ("T3", "dropped", "plan"),
                             ("T9", "open", "amendment")]),
             "M2": None}
JOINT_LINES = [
    "M1 Title1 1/3",
    "  S1 Title",
    "    ✓ T1 Title",
    "    ▸ T2 Title",
    "    ✗ T3 Title",
    "  + · T9 Title",
    "M2 Title2 0/1",
    "  S2 Title",
    "    · T4 Title",
]


class PlanTreeTests(unittest.TestCase):
    def test_a1_plan_order_and_nesting(self):
        self.assertEqual(plan_tree.lines(plan_tree.build(JOINT, MANIFESTS)), JOINT_LINES)

    def test_a2_statuses_from_manifest_and_the_added_task(self):
        milestone = plan_tree.build(JOINT, MANIFESTS)[0]
        self.assertEqual([(t.id, t.status) for t in milestone.slices[0].tasks],
                         [("T1", "done"), ("T2", "current"), ("T3", "dropped")])
        self.assertEqual([(t.id, t.status, t.added) for t in milestone.added], [("T9", "open", True)])

    def test_a3_a_milestone_without_a_manifest_is_all_open(self):
        milestone = plan_tree.build(JOINT, MANIFESTS)[1]
        self.assertEqual([(t.id, t.status) for t in milestone.slices[0].tasks], [("T4", "open")])
        self.assertEqual(milestone.added, ())

    def test_a4_counter_is_done_over_tasks_not_dropped_added_counted(self):
        m1, m2 = plan_tree.build(JOINT, MANIFESTS)
        self.assertEqual((m1.done, m1.total), (1, 3))
        self.assertEqual((m2.done, m2.total), (0, 1))

    def test_a5_a_manifest_plan_id_is_shown_once(self):
        tree = plan_tree.build(JOINT, MANIFESTS)
        ids = [t.id for m in tree for s in m.slices for t in s.tasks] + [t.id for m in tree for t in m.added]
        self.assertEqual(sorted(ids), ["T1", "T2", "T3", "T4", "T9"])

    def test_a5_a_manifest_task_shared_with_another_milestone_is_not_added(self):
        """Regression: filtering additions by the current milestone's plan ids only showed an amendment T4 that
        also names M2's plan task twice (as `+ \u00b7 T4` under M1 and `\u00b7 T4` under M2); the filter is
        proposal-wide."""
        manifests = dict(MANIFESTS)
        manifests["M1"] = manifest([("T1", "done", "plan"), ("T2", "open", "plan"), ("T3", "dropped", "plan"),
                                    ("T4", "open", "amendment")])
        tree = plan_tree.build(JOINT, manifests)
        self.assertEqual(tree[0].added, ())
        self.assertEqual([line for line in plan_tree.lines(tree) if "T4" in line], ["    \u00b7 T4 Title"])

    def test_an_added_first_open_task_is_current(self):
        manifests = {"M1": manifest([("T1", "done", "plan"), ("T2", "done", "plan"), ("T3", "dropped", "plan"),
                                     ("T9", "open", "amendment")]), "M2": None}
        self.assertIn("  + ▸ T9 Title", plan_tree.lines(plan_tree.build(JOINT, manifests)))

    def test_every_task_is_open_without_any_manifest(self):
        tree = plan_tree.build(JOINT, {})
        statuses = [t.status for m in tree for s in m.slices for t in s.tasks]
        self.assertEqual(statuses, ["open"] * 4)
        self.assertEqual([(m.done, m.total) for m in tree], [(0, 3), (0, 1)])


if __name__ == "__main__":
    unittest.main()
