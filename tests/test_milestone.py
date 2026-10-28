import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request

from devtools import driver_qual
from terminal_planner import milestone, runs, toolchain
from terminal_planner.authority import Blocked, canonical
from terminal_planner.engine import fixture_proposal
from terminal_planner.setup import default_roles, tool_paths


EXECUTABLES = ("step", "verifier")


def nodes(node):
    """Every node of a graph tree, depth first."""
    yield node
    for child in node.get("children", []):
        yield from nodes(child)
    for branch in node.get("branches", []):
        yield from nodes(branch.get("node", branch))
    for key in ("body", "otherwise"):
        if node.get(key):
            yield from nodes(node[key])


def guards(guard):
    if guard["kind"] in ("any", "all"):
        for child in guard["guards"]:
            yield from guards(child)
    else:
        yield guard


def is_failed(guard, name):
    return guard == {"kind": "in", "value": {"name": name, "source": "error", "field": None}, "labels": milestone.ERRORS}


def payload_schema(payload):
    """Strict provider dialect of the pinned response contract (native_v2_runner/response.rs:373-466)."""
    kind = payload["kind"]
    if kind == "record":
        properties = {}
        for name, field in payload["fields"].items():
            schema = payload_schema(field["type"])
            properties[name] = schema if field["required"] else {"anyOf": [schema, {"type": "null"}]}
        return {"type": "object", "properties": properties, "required": sorted(properties), "additionalProperties": False}
    if kind == "enum":
        return {"type": "string", "enum": list(payload["values"])}
    return {"type": kind}


def provider_request(node, incoming):
    if node["kind"] == "verifier":
        response = {"type": "object", "required": ["diagnostic", "output", "signals"], "additionalProperties": False,
                    "properties": {"diagnostic": payload_schema(node["diagnostic"]), "output": payload_schema(node["output"]),
                                   "signals": {"type": "object", "required": sorted(node["signals"]), "additionalProperties": False,
                                               "properties": {k: {"type": "string", "enum": v} for k, v in node["signals"].items()}}}}
    else:
        response = payload_schema(node["output"])
    prompt = ("Execute this graph node using the shared workspace.\nAuthored instructions:\n%s\nInput JSON:\n%s"
              % (node["instructions"], json.dumps(incoming)))
    return {"input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "text": {"format": {"type": "json_schema", "name": "response", "strict": True, "schema": {
                "type": "object", "properties": {"response": response}, "required": ["response"], "additionalProperties": False}}}}


def interpret(case, graph, value, provider, error=None):
    """Interpret the authored milestone graph subset; deterministic control fixture, not native qualification.

    Errors write nothing and let the sequence continue; local state is cloned per scoped node and
    only promoted paths flow back; channels of a node are cleared each time it runs.
    """
    channels, calls = {}, []

    def guard(g):
        if g["kind"] == "any":
            return any(guard(child) for child in g["guards"])
        if g["kind"] == "all":
            return all(guard(child) for child in g["guards"])
        selector = g["value"]
        found = channels.get((selector["name"], selector["source"]))
        if selector.get("field") and isinstance(found, dict):
            found = found.get(selector["field"])
        return found in g["labels"]

    def bind(items, state):
        result = {}
        for binding in items:
            source = binding["value"]
            data = state if source.get("source") == "state" else channels.get((source["node"], source["channel"]))
            case.assertIsNotNone(data, "binding reads an absent channel: %s" % source)
            result[binding["target"][0]] = data[source["path"][0]]
        return result

    def run(node, parent):
        kind, name = node["kind"], node["name"]
        state = copy.deepcopy(parent) if "state" in node else parent
        result = None
        if kind in EXECUTABLES:
            incoming = bind(node["inputBindings"], state)
            calls.append(name)
            for channel in ("out", "signal", "diagnostic", "error"):
                channels.pop((name, channel), None)
            if name == error:
                channels[(name, "error")] = "crash"
            else:
                response = provider.answer(provider_request(node, incoming))
                if kind == "step":
                    channels[(name, "out")] = response
                else:
                    channels[(name, "signal")] = response["signals"]
                    channels[(name, "diagnostic")] = response["diagnostic"]
                state.update(bind(node["writeBindings"], state))
        elif kind == "seq":
            for child in node["children"]:
                result = run(child, state)
                if result is not None:
                    break
        elif kind == "par":
            for branch in node["branches"]:
                case.assertIsNone(run(branch, state))
        elif kind == "choice":
            selected = next((b["node"] for b in node["branches"] if guard(b["when"])), node.get("otherwise"))
            case.assertIsNotNone(selected, name)
            result = run(selected, state)
        elif kind == "loop":
            for _ in range(node["maxIterations"]):
                result = run(node["body"], state)
                if result is not None or guard(node["until"]):
                    channels[(name, "group")] = {"terminated": "converged"}
                    break
            else:
                channels[(name, "group")] = {"terminated": "exhausted"}
        elif kind == "succeed":
            result = {"status": "succeeded", "output": bind(node["bindings"], state), "exit": name}
        elif kind == "fail":
            case.assertNotIn("bindings", node)
            result = {"status": "failed", "reason": node["reason"], "exit": name}
        else:
            case.fail("unsupported node kind " + kind)
        for path in node.get("promotedStatePaths", []):
            parent[path[0]] = state[path[0]]
        return result

    return run(graph["root"], copy.deepcopy(value)), calls


def flow(case, scenario, error=None):
    graph, _, value = driver_qual.documents(scenario)
    provider = driver_qual.Provider(scenario["script"])
    result, calls = interpret(case, graph, value, provider, error)
    return result, calls, provider


def amend(manifest, kind, tasks, parents=(), reason="Steward amendment."):
    manifest["amendments"].append({"seq": len(manifest["amendments"]) + 1, "kind": kind, "tasks": list(tasks),
                                   "parents": list(parents), "reason": reason})


def note(manifest, task, phase, text="evidence"):
    manifest["progress"].append({"seq": len(manifest["progress"]) + 1, "task": task, "phase": phase, "text": text})


def add(manifest, task_id, parent=None, kind="add", record=True):
    task = {"id": task_id, "title": "Added " + task_id, "checks": ["Check " + task_id], "status": "open",
            "origin": "amendment", "notes": ""}
    if parent:
        task["parent"] = parent
    manifest["tasks"].append(task)
    if record:
        amend(manifest, kind, [task_id], [parent] if parent else [])
    return task


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.baseline, self.manifest = milestone.build_manifest(driver_qual.proposal(2), "M1", 3)

    def rejects(self, manifest, message, before=None):
        with self.assertRaisesRegex(milestone.Invalid, message):
            if before is None:
                milestone.validate(self.baseline, manifest)
            else:
                milestone.check_amendments(self.baseline, before, manifest)

    def accepts(self, manifest, before=None):
        milestone.validate(self.baseline, manifest)
        if before is not None:
            milestone.check_amendments(self.baseline, before, manifest)

    def test_build_freezes_baseline_and_derives_checks(self):
        proposal = fixture_proposal()
        tasks = proposal["milestones"][0]["slices"][0]["tasks"]
        tasks.append({"id": "T3", "title": "Second task", "checks": ["Deterministic interaction test", "Extra check"]})
        baseline, manifest = milestone.build_manifest(proposal, "M1", 7)
        self.assertEqual(baseline["plan_revision"], 7)
        self.assertEqual(baseline["milestone"], {"id": "M1", "title": "First usable increment", "depends_on": []})
        self.assertEqual(baseline["requirements"], [{"id": "R1", "text": "Demonstrate the requested user interaction."}])
        self.assertEqual(baseline["slices"], [{"id": "S1", "title": "Implement the smallest useful path", "requirements": ["R1"]}])
        self.assertEqual([t["id"] for t in baseline["tasks"]], ["T1", "T3"])
        self.assertEqual(baseline["checks"], ["Deterministic interaction test", "Extra check", milestone.ALL_REQUIREMENTS])
        self.assertEqual(baseline["limits"], {"initial_tasks": 2, "max_additions": 6, "task_iterations": 4,
                                              "outer_iterations": 18, "final_repairs": 3})
        self.assertEqual([(t["status"], t["origin"]) for t in manifest["tasks"]], [("open", "plan")] * 2)
        self.assertEqual((manifest["amendments"], manifest["progress"], manifest["outcome"]), ([], [], None))
        self.assertEqual(milestone.build_manifest(fixture_proposal(), "M2", 7)[0]["milestone"]["depends_on"], ["M1"])
        self.accepts(self.manifest)

    def test_task_brief_reaches_baseline_manifest_and_next_task(self):
        """C1/C3/C2 (stored). A valid `brief` travels unchanged proposal -> baseline -> manifest -> next_task and is
        frozen for plan tasks; records without a brief (0.5.x) build and validate as before. Interpretation: a stored
        baseline with an invalid brief is refused by the existing baseline check (`milestone.manifest_invalid`)."""
        brief = {"goal": "g", "why": "w", "reuse": "", "write_set": ["a.py"],
                 "criteria": [{"id": "C1", "text": "t", "example": "e"}], "non_goals": [],
                 "risk": "low", "dod": "python3 -m unittest tests.test_a"}
        proposal = fixture_proposal()
        proposal["milestones"][0]["slices"][0]["tasks"][0]["brief"] = copy.deepcopy(brief)
        baseline, manifest = milestone.build_manifest(proposal, "M1", 1)
        self.assertEqual(baseline["tasks"][0]["brief"], brief)
        self.assertEqual(manifest["tasks"][0]["brief"], brief)
        self.assertEqual(milestone.next_task(baseline, manifest)["task"]["brief"], brief)
        manifest["tasks"][0]["brief"]["risk"] = "high"
        with self.assertRaisesRegex(milestone.Invalid, "brief is frozen"):
            milestone.validate(baseline, manifest)
        stored = copy.deepcopy(baseline)
        stored["tasks"][0]["brief"]["risk"] = "huge"
        with self.assertRaisesRegex(milestone.Invalid, "baseline: task T1: brief: risk"):
            milestone.validate_baseline(stored)
        plain, plain_manifest = milestone.build_manifest(fixture_proposal(), "M1", 1)
        self.assertNotIn("brief", plain["tasks"][0])
        self.assertNotIn("brief", milestone.next_task(plain, plain_manifest)["task"])
        self.assertEqual(plain["schemaVersion"], "1")

    def test_initial_task_bound_refused_before_a_run(self):
        milestone.build_manifest(driver_qual.proposal(12), "M1", 1)
        with self.assertRaisesRegex(Blocked, "M1 has 13 tasks; the driver runs at most 12. Split the milestone"):
            milestone.build_manifest(driver_qual.proposal(13), "M1", 1)
        with self.assertRaises(Blocked):
            milestone.milestone_graph(13)
        with self.assertRaisesRegex(Blocked, "not in the approved plan"):
            milestone.build_manifest(fixture_proposal(), "M9", 1)
        grown = copy.deepcopy(self.baseline)
        grown["limits"]["max_additions"] = 7
        with self.assertRaisesRegex(milestone.Invalid, "limits"):
            milestone.validate_baseline(grown)

    def test_frozen_baseline(self):
        for edit in (lambda m: m["baseline"]["requirements"][0].update(text="Weaker requirement."),
                     lambda m: m["baseline"]["checks"].pop(),
                     lambda m: m["tasks"][0].update(checks=["Weaker check"]),
                     lambda m: m.update(plan_revision=4),
                     lambda m: m["milestone"].update(title="Other"),
                     lambda m: m["tasks"].pop(0)):
            manifest = copy.deepcopy(self.manifest)
            edit(manifest)
            self.rejects(manifest, "baseline|frozen|revision|plan tasks")
        changed = copy.deepcopy(self.baseline)
        changed["requirements"][0]["text"] = "Other."
        with self.assertRaisesRegex(milestone.Invalid, "frozen baseline changed"):
            milestone.check_amendments(changed, self.manifest, self.manifest)

    def test_ids_are_never_reused_or_removed(self):
        manifest = copy.deepcopy(self.manifest)
        add(manifest, "T1")
        self.rejects(manifest, "duplicate task id")
        before = copy.deepcopy(self.manifest)
        add(before, "X1")
        before["tasks"][-1]["status"] = "dropped"
        amend(before, "drop", ["X1"])
        self.accepts(before)
        after = copy.deepcopy(before)
        after["tasks"].pop()
        self.rejects(after, "never removed", before)
        add(after, "X1")  # reusing the tombstoned id reopens it
        self.rejects(after, "done and dropped are final", before)

    def test_addition_bound_counts_split_children_and_dropped_tasks(self):
        manifest = copy.deepcopy(self.manifest)
        for i in range(6):
            add(manifest, "X%s" % i)
        self.accepts(manifest)
        add(manifest, "X6")
        self.rejects(manifest, "7 tasks added; at most 6")

        split = copy.deepcopy(self.manifest)
        split["tasks"][0]["status"] = "dropped"
        split["tasks"] += [add(copy.deepcopy(split), c, "T1", "split", record=False) for c in ("T1-a", "T1-b")]
        amend(split, "split", ["T1-a", "T1-b"], ["T1"])
        self.accepts(split)
        for i in range(5):
            add(split, "X%s" % i)
        self.rejects(split, "7 tasks added")

        dropped = copy.deepcopy(self.manifest)
        for i in range(6):
            add(dropped, "X%s" % i)
        dropped["tasks"][-1]["status"] = "dropped"
        amend(dropped, "drop", ["X5"])
        self.accepts(dropped)
        add(dropped, "X6")
        self.rejects(dropped, "7 tasks added")

    def test_done_requires_both_reviews_accepted(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks"][0]["status"] = "done"
        self.rejects(manifest, "done requires")
        note(manifest, "T1", "accepted")
        self.accepts(manifest)
        note(manifest, "T1", "rejected")
        self.rejects(manifest, "done requires")

    def test_done_requires_acceptance_in_the_current_iteration(self):
        before = copy.deepcopy(self.manifest)
        note(before, "T1", "accepted", "earlier iteration")
        after = copy.deepcopy(before)
        after["tasks"][0]["status"] = "done"
        self.accepts(after)  # cumulative view alone cannot tell iterations apart
        self.rejects(after, "in this iteration", before)
        note(after, "T1", "accepted", "this iteration")
        self.accepts(after, before)

    def test_only_the_selected_task_may_be_done_in_an_iteration(self):
        before = copy.deepcopy(self.manifest)
        after = copy.deepcopy(before)
        other = next(t for t in after["tasks"] if t["id"] != "T1")
        other["status"] = "done"
        note(after, other["id"], "accepted", "never reviewed")
        self.accepts(after)  # cumulative view alone cannot tell which task was selected
        self.rejects(after, "only the selected task", before)
        after = copy.deepcopy(before)
        after["tasks"][0]["status"] = "done"
        note(after, "T1", "accepted", "reviewed")
        self.accepts(after, before)
        other = next(t for t in after["tasks"] if t["id"] != "T1")
        other["status"] = "done"
        note(after, other["id"], "accepted", "never reviewed")
        self.rejects(after, "only the selected task", before)

    def test_scope_changes_require_recorded_amendments(self):
        cases = {
            "retitle requires a reword": (lambda m: m["tasks"][0].update(title="Reworded"), "reword", ["T1"]),
            "order changed": (lambda m: m["tasks"].reverse(), "reorder", ["T1-2", "T1"]),
            "drop requires": (lambda m: m["tasks"][1].update(status="dropped"), "drop", ["T1-2"]),
        }
        for message, (edit, kind, ids) in cases.items():
            manifest = copy.deepcopy(self.manifest)
            edit(manifest)
            self.rejects(manifest, message)
            amend(manifest, kind, ids)
            self.accepts(manifest)
        manifest = copy.deepcopy(self.manifest)
        add(manifest, "X1", record=False)
        self.rejects(manifest, "addition without an add/split amendment")
        manifest = copy.deepcopy(self.manifest)
        add(manifest, "X1", parent="T1", kind="add")
        self.rejects(manifest, "parent requires a split")
        manifest = copy.deepcopy(self.manifest)
        added = add(manifest, "X1")
        added["status"] = "done"
        self.rejects(manifest, "starts open", self.manifest)

    def test_amended_tasks_can_be_done_in_a_later_iteration(self):
        for kind, parent in (("add", None), ("split", "T1")):
            first = copy.deepcopy(self.manifest)
            add(first, "X1", parent=parent, kind=kind)
            if parent:
                first["tasks"][0]["status"] = "dropped"
            self.accepts(first, self.manifest)
            for index in range(len(first["tasks"]) - 1):  # X1 is selected only once the earlier tasks are finished
                if first["tasks"][index]["status"] == "open":
                    step = copy.deepcopy(first)
                    step["tasks"][index]["status"] = "done"
                    note(step, step["tasks"][index]["id"], "accepted")
                    self.accepts(step, first)
                    first = step
            second = copy.deepcopy(first)
            second["tasks"][-1]["status"] = "done"
            note(second, "X1", "accepted")
            self.accepts(second, first)
            stale = copy.deepcopy(second)
            stale["progress"].pop()
            with self.assertRaises(milestone.Invalid):
                milestone.validate(self.baseline, stale)

    def test_final_statuses_fixed_fields_and_append_only_records(self):
        before = copy.deepcopy(self.manifest)
        before["tasks"][0]["status"] = "done"
        note(before, "T1", "accepted")
        add(before, "X1")
        self.accepts(before)
        for message, edit in (("final", lambda m: m["tasks"][0].update(status="open")),
                              ("final|retitle", lambda m: m["tasks"][0].update(title="Reworded after done")),
                              ("fixed", lambda m: m["tasks"][2].update(checks=["Weaker"])),
                              ("plan tasks must stay listed", lambda m: m["tasks"][2].update(origin="plan")),
                              ("amendments are append-only", lambda m: m["amendments"][0].update(reason="Rewritten.")),
                              ("progress is append-only", lambda m: m["progress"][0].update(text="Rewritten."))):
            after = copy.deepcopy(before)
            edit(after)
            amend(after, "reword", ["T1"])
            with self.assertRaisesRegex(milestone.Invalid, message):
                milestone.validate(self.baseline, after)
                milestone.check_amendments(self.baseline, before, after)

    def test_next_task_contract(self):
        contract = milestone.next_task(self.baseline, self.manifest)
        self.assertEqual(contract["task"], {"id": "T1", "title": "Synthetic task 1", "checks": ["Synthetic check 1"], "notes": ""})
        self.assertEqual(contract["milestone_checks"], self.baseline["checks"])
        for task in self.manifest["tasks"]:
            task["status"] = "dropped"
        amend(self.manifest, "drop", ["T1", "T1-2"])
        self.assertIsNone(milestone.next_task(self.baseline, self.manifest))

    def test_cli_check_and_select(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {name: root / name for name in ("baseline.json", "milestone.json", "before.json")}
            paths["baseline.json"].write_text(canonical(self.baseline))
            paths["milestone.json"].write_text(canonical(self.manifest))

            def cli(*args):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = milestone.main([str(a) for a in args])
                return code, out.getvalue(), err.getvalue()

            check = ("check", paths["milestone.json"], "--baseline", paths["baseline.json"])
            self.assertEqual(cli(*check)[:2], (0, "OK: 2 open, 0 done, 0 dropped, 0 added\n"))
            code, out, _ = cli("select", paths["milestone.json"], "--baseline", paths["baseline.json"],
                               "--before", paths["before.json"])
            self.assertEqual((code, json.loads(out)["task"]["id"]), (0, "T1"))
            self.assertEqual(json.loads(paths["before.json"].read_text()), self.manifest)
            changed = copy.deepcopy(self.manifest)
            changed["tasks"][0]["title"] = "Reworded silently"
            paths["milestone.json"].write_text(canonical(changed))
            code, out, err = cli(*check, "--before", paths["before.json"])
            self.assertEqual((code, out), (1, ""))
            self.assertIn("INVALID: task T1: retitle requires a reword amendment", err)
            self.assertEqual(cli("check", root / "missing.json", "--baseline", paths["baseline.json"])[0], 1)


class GraphStructureTests(unittest.TestCase):
    def test_bounds_are_fixed_by_the_formula(self):
        for tasks in range(milestone.MAX_INITIAL_TASKS + 1):
            loops = {n["name"]: n["maxIterations"] for n in nodes(milestone.milestone_graph(tasks)["root"]) if n["kind"] == "loop"}
            self.assertEqual(loops, {"task_loop": 2 * (tasks + 6) + 2, "review_loop": 4, "repair_loop": 3, "empty_repair_loop": 3})
            self.assertLessEqual(max(loops.values()), 100)

    def test_the_review_bar_rejects_only_a_broken_check_or_title(self):
        """A1/D1: both milestone reviews carry the review bar - a review rejects only when a check or the title of
        input.task fails on a realistic path or the change breaks existing behaviour on a realistic path, and every
        other remark is a non-blocking `note:` - and the worker instruction repairs the findings of a rejected review
        while leaving `note:` items. The bar's sentences are asserted, not a whole-prompt snapshot."""
        graph = milestone.milestone_graph(2)
        bodies = {node["name"]: node["instructions"].split("\n", 2)[2]
                  for node in nodes(graph["root"]) if node["kind"] == "verifier"}
        for name in ("acceptance_review", "code_review"):
            with self.subTest(node=name):
                text = bodies[name]
                self.assertIn("rejects only when a check or the title of input.task fails on a realistic path", text)
                self.assertIn("breaks existing behaviour on a realistic path", text)
                self.assertIn("non-blocking note marked `note:` and never rejects the change", text)
                self.assertIn("`note:`", text)
        worker = next(node for node in nodes(graph["root"]) if node["name"] == "worker")["instructions"]
        self.assertIn("rejected, their findings describe that rejected review: repair those findings", worker)
        self.assertIn("`note:` are non-blocking and may be left", worker)

    def test_the_review_loop_bound_follows_the_frozen_task_rounds(self):
        """A2/D2: the review loop's bound is one implementation pass plus the revision's frozen limits.task_rounds
        (preset 2 -> 3); a milestone built without a frozen profile - a version 1 revision or an older version 2 one -
        keeps the fixed TASK_ITERATIONS (the current 4). `runs.review_rounds` reads the frozen snapshot (the value
        `process.freeze_plan` stores and `authority.validate_frozen` accepts). Interpretation: the bound is the loop
        graph's maxIterations only; the preview's "ремонтов на задачу" and the run view's "ремонт i/n" labels stay
        untouched - the task's non-goals exclude any UI change, and `delivery.py`/`node_label` are outside the write
        set."""
        self.assertEqual(milestone.TASK_ITERATIONS, 4)
        self.assertEqual((milestone.review_iterations(1), milestone.review_iterations(2), milestone.review_iterations(10)),
                         (2, 3, 11))
        self.assertEqual(milestone.review_iterations(None), 4)
        for task_rounds, expected in ((1, 2), (2, 3), (5, 6)):
            with self.subTest(task_rounds=task_rounds):
                graph = milestone.milestone_graph(2, rounds=milestone.review_iterations(task_rounds))
                loop = next(n for n in nodes(graph["root"]) if n["name"] == "review_loop")
                self.assertEqual(loop["maxIterations"], expected)
        frozen = {"frozen": {"plan_rounds": 3, "rules": [], "config_digest": "a" * 64, "task_rounds": 2}}
        older = {"frozen": {"plan_rounds": 3, "rules": [], "config_digest": "a" * 64}}
        self.assertEqual(runs.review_rounds(frozen), 3)
        self.assertEqual(runs.review_rounds(older), 4)
        self.assertEqual(runs.review_rounds({"version": 1, "roles": {}}), 4)

    def test_exits_signals_and_error_branches(self):
        graph = milestone.milestone_graph(2)
        every = list(nodes(graph["root"]))
        succeed = {n["name"]: n for n in every if n["kind"] == "succeed"}
        signals = {"done": "doneSignal", "repaired": "doneSignal", "final_exhausted": "blockedSignal",
                   "needs_owner": "needsOwnerSignal", "steward_blocked": "blockedSignal", "task_loop_exhausted": "blockedSignal",
                   "empty_done": "doneSignal", "empty_repaired": "doneSignal", "empty_final_exhausted": "blockedSignal"}
        self.assertEqual({k: v["bindings"][0]["value"]["path"][0] for k, v in succeed.items()}, signals)
        for node in succeed.values():
            self.assertEqual(node["output"], milestone.milestone_output())
            self.assertTrue(all(b["value"]["source"] == "state" for b in node["bindings"]))
        executables = {n["name"]: n for n in every if n["kind"] in EXECUTABLES}
        choices = [n for n in every if n["kind"] == "choice"]
        for name in executables:
            routed = [b for c in choices for b in c["branches"] if is_failed(b["when"], name)]
            self.assertTrue(routed and all(b["node"]["kind"] == "fail" and "bindings" not in b["node"] for b in routed), name)
        for node in choices:
            for index, branch in enumerate(node["branches"]):
                for g in guards(branch["when"]):
                    if g["value"]["source"] == "error":
                        self.assertTrue(is_failed(branch["when"], g["value"]["name"]) and branch["node"]["kind"] == "fail", node["name"])
                    elif g["value"]["source"] == "signal":
                        reader = g["value"]["name"]
                        self.assertTrue(any(is_failed(b["when"], reader) for b in node["branches"][:index])
                                        or reader + "_result" in {c["name"] for c in choices}, (node["name"], reader))
        for loop in (n for n in every if n["kind"] == "loop"):
            for g in guards(loop["until"]):
                reader = g["value"]["name"]
                if g["value"]["source"] == "signal":
                    self.assertTrue(any(is_failed(u, reader) for u in loop["until"]["guards"])
                                    or reader + "_result" in {c["name"] for c in choices}, (loop["name"], reader))
        self.assertNotIn("succeed", {n["kind"] for n in every if n["name"].endswith(("_loop", "_iteration"))})

    def test_preflight_and_conflict_routes(self):
        """C1/C2: the root is `seq(preflight, preflight_result)`; `preflight` is a read-only reviewer-role verifier
        (no writes, input milestone + baseline, signal ready/conflict) whose error and conflict end the run and whose
        `ready` runs the former root subtree; only the two task reviews may signal `conflict`, which stops the review
        loop and fails the run (after the error branches, before `steward_apply`).

        Interpretation: the former root sequence `milestone` keeps its children under the new name `milestone_start`
        (node names are unique and the root keeps the name `milestone`)."""
        graph = milestone.milestone_graph(2)
        by_name = {n["name"]: n for n in nodes(graph["root"])}
        root = graph["root"]
        self.assertEqual((root["name"], [c["name"] for c in root["children"]]), ("milestone", ["preflight", "preflight_result"]))
        preflight = by_name["preflight"]
        self.assertEqual((preflight["kind"], preflight["writeBindings"], preflight["signals"], milestone.ROLES["preflight"]),
                         ("verifier", [], {"preflight": ["ready", "conflict"]}, "reviewer"))
        self.assertEqual(set(preflight["input"]["fields"]), {"milestone", "baseline"})
        text = preflight["instructions"].split("\n", 2)[2]
        self.assertTrue(text.startswith("Read only"))
        for word in ("F1", "F2", "F4", "write_set", "non_goal"):
            self.assertIn(word, text)
        result = by_name["preflight_result"]
        self.assertTrue(is_failed(result["branches"][0]["when"], "preflight"))
        self.assertEqual(result["branches"][0]["node"]["reason"], "preflight_failed")
        self.assertEqual(result["branches"][1]["when"]["labels"], ["conflict"])
        self.assertEqual(result["branches"][1]["node"], {"kind": "fail", "name": "preflight_conflict", "reason": "preflight_conflict"})
        self.assertEqual([c["name"] for c in result["otherwise"]["children"]], ["select_init", "select_init_result"])
        for name in ("acceptance_review", "code_review"):
            self.assertEqual(by_name[name]["signals"], {"verdict": ["accepted", "rejected", "conflict"]})
            self.assertIn("conflict", by_name[name]["instructions"])
        for name in ("final_verify", "final_reverify", "scope_verify"):
            self.assertEqual(by_name[name]["signals"], {"verdict": ["accepted", "rejected"]})
        fields = graph["initialInput"]["fields"]
        self.assertEqual({n: f["type"]["values"] for n, f in fields.items() if n in milestone.VERDICTS},
                         {"acceptanceVerdict": ["pending", "accepted", "rejected", "conflict"],
                          "codeVerdict": ["pending", "accepted", "rejected", "conflict"],
                          "finalVerdict": ["pending", "accepted", "rejected"], "scopeVerdict": ["pending", "accepted", "rejected"]})
        self.assertEqual(milestone.milestone_output()["fields"]["signal"]["type"]["values"], list(milestone.SIGNALS))
        self.assertEqual(by_name["reviews"]["join"], {"kind": "all"})
        conflicts = [g["value"]["name"] for g in guards(by_name["review_loop"]["until"]) if g["labels"] == ["conflict"]]
        self.assertEqual(conflicts, ["acceptance_review", "code_review"])
        review = by_name["review_result"]
        self.assertEqual([b["node"]["reason"] for b in review["branches"]],
                         ["acceptance_review_failed", "code_review_failed", "review_conflict"])
        self.assertEqual([g["labels"] for g in guards(review["branches"][2]["when"])], [["conflict"]] * 2)
        self.assertEqual(review["otherwise"]["name"], "steward_apply")

    def test_failed_selection_cannot_reach_a_writer(self):
        graph = milestone.milestone_graph(2)

        def routes(node, trail=()):
            # (node, choice routes taken to reach it): (choice name, branch labels or "otherwise").
            yield node, trail
            for child in node.get("children", []):
                yield from routes(child, trail)
            for branch in node.get("branches", []):
                if "when" in branch:
                    labels = [g.get("labels") for g in guards(branch["when"])]
                    yield from routes(branch["node"], trail + ((node["name"], labels),))
                else:
                    yield from routes(branch, trail)
            if node.get("body"):
                yield from routes(node["body"], trail)
            if node.get("otherwise"):
                yield from routes(node["otherwise"], trail + ((node["name"], "otherwise"),))

        found = list(routes(graph["root"]))
        by_name = {n["name"]: n for n, _ in found}
        init = by_name["select_init_result"]["branches"]
        self.assertEqual([g["labels"] for b in init for g in guards(b["when"])][:2], [milestone.ERRORS, ["invalid"]])
        self.assertEqual(init[1]["node"], {"kind": "fail", "name": "select_init_invalid", "reason": "select_init_invalid"})
        verify = by_name["select_verify_result"]["branches"]
        self.assertTrue(is_failed(verify[0]["when"], "select_verify") and verify[0]["node"]["kind"] == "fail")
        self.assertEqual((verify[1]["when"]["value"], verify[1]["when"]["labels"], verify[1]["node"]["kind"]),
                         ({"name": "select_verify", "source": "signal", "field": "selection"}, ["invalid"], "fail"))
        for name in ("select_init", "select_verify"):
            self.assertEqual(by_name[name]["writeBindings"], [])
            self.assertTrue(by_name[name]["instructions"].split("\n", 2)[2].startswith("Read only"))
        self.assertNotIn("error text as task", by_name["select"]["instructions"])
        self.assertIn("return the empty string as task", by_name["select"]["instructions"])
        writers = [(n["name"], trail) for n, trail in found if n["kind"] == "step" and n["writeBindings"]
                   and n["name"] != "select"]
        self.assertEqual({w for w, _ in writers}, {"worker", "steward_apply", "repair", "empty_repair"})
        for name, trail in writers:
            init_route = [labels for choice, labels in trail if choice == "select_init_result"]
            # Writers sit only under queue=open or the empty-queue final stage, never queue=invalid.
            self.assertIn(init_route, ([[["open"]]], ["otherwise"]), name)
            # Task writers run only after a verified selection (repair follows the task loop, whose
            # every iteration passed this gate or ended the run).
            if name in ("worker", "steward_apply"):
                self.assertIn(("select_verify_result", "otherwise"), trail, name)

    def test_executable_contracts_and_runtime(self):
        """A1/A2: the four milestone reviewers re-run the checks, so they get the worker's 45 min budget.

        Interpretation: the final reviewers of both routes are extended — the milestone's normal final stage
        (`final_verify`/`final_reverify`) and its no-open-task twins (`empty_final_verify`/`empty_final_reverify`,
        built by the same `final_stage("empty_")` helper), so a resumed attempt with every task done no longer times
        out the same way. The long-node set below therefore names all four: the test fails if any goes back to 20 min.
        """
        graph = milestone.milestone_graph(2, tool="zplan-check")
        executables = [n for n in nodes(graph["root"]) if n["kind"] in EXECUTABLES]
        names = [n["name"] for n in executables]
        self.assertEqual(sorted(names), sorted(milestone.ROLES))
        self.assertEqual(len({n["worker"] for n in executables}), len(executables))
        for node in executables:
            self.assertTrue(node["instructions"].startswith("ZPLAN_NODE=%s\n" % node["name"]))
            self.assertIn("zplan-check check .zplan/milestone.json --baseline .zplan/baseline.json", node["instructions"])
            long = node["name"] in ("worker", "repair", "empty_repair", "acceptance_review", "code_review",
                                    "final_verify", "final_reverify", "empty_final_verify", "empty_final_reverify")
            self.assertEqual((node["timeoutMs"], node["attempts"]), (45 * 60000 if long else 20 * 60000, 1))
            text = node["instructions"]
            self.assertTrue("change no file and no manifest field" in text or "may change no manifest field" in text
                            or "You may change only" in text, node["name"])
        runtime = milestone.milestone_runtime(default_roles())
        self.assertEqual(set(runtime["nodes"]), set(names))
        for name, binding in runtime["nodes"].items():
            role = milestone.ROLES[name]
            self.assertEqual(binding["sessionScope"], {"reviewer": "execution", "worker": "node_instance", "steward": "execution"}[role])
            self.assertEqual(binding["model"], default_roles()[role]["model"])

    def test_input_matches_initial_state(self):
        baseline, _ = milestone.build_manifest(fixture_proposal(), "M1", 1)
        value = milestone.milestone_input(baseline, tool="zplan-check")
        fields = milestone.milestone_graph(1)["initialInput"]["fields"]
        self.assertEqual(set(value), set(fields))
        for name, field in fields.items():
            self.assertTrue(field["required"])
            if field["type"]["kind"] == "enum":
                self.assertIn(value[name], field["type"]["values"])
            else:
                self.assertIsInstance(value[name], str)
        self.assertEqual((value["doneSignal"], value["needsOwnerSignal"], value["blockedSignal"]), ("done", "needs_owner", "blocked"))
        self.assertEqual(json.loads(value["baseline"]), baseline)
        self.assertEqual(json.loads(value["milestone"])["validate"], "zplan-check check .zplan/milestone.json --baseline .zplan/baseline.json")


class FlowTests(unittest.TestCase):
    """Graph control flow under the interpreter, driven by the qualification scenario scripts."""

    EMPTY_REPAIRED = dict(tasks=1, script={"preflight": ["ready"], "select_init": ["empty"], "empty_final_verify": ["rejected"],
                                           "empty_scope_verify": ["rejected", "accepted"], "empty_final_reverify": ["accepted"] * 2},
                          order=["preflight", "select_init", "empty_final_verify"]
                          + ["empty_repair", "empty_scope_verify", "empty_final_reverify"] * 2,
                          output=driver_qual.output("done", "empty_final_reverify message #2"))
    EMPTY_EXHAUSTED = dict(tasks=1, script={"preflight": ["ready"], "select_init": ["empty"], "empty_final_verify": ["rejected"],
                                            "empty_scope_verify": ["accepted"] * 3, "empty_final_reverify": ["rejected"] * 3},
                           order=["preflight", "select_init", "empty_final_verify"]
                           + ["empty_repair", "empty_scope_verify", "empty_final_reverify"] * 3,
                           output=driver_qual.output("blocked", "empty_final_reverify message #3"))

    def test_scenarios_and_every_business_exit(self):
        exits = set()
        scenarios = dict(driver_qual.SCENARIOS, empty_repaired=self.EMPTY_REPAIRED, empty_exhausted=self.EMPTY_EXHAUSTED)
        for name, scenario in scenarios.items():
            with self.subTest(name):
                result, calls, provider = flow(self, scenario)
                exit = result.pop("exit")
                if result["status"] == "succeeded":
                    exits.add(exit)
                self.assertEqual(driver_qual.normalize(calls), driver_qual.normalize(scenario["order"]))
                self.assertEqual([n for n, _ in provider.calls], calls)
                self.assertEqual(driver_qual.check(scenario, provider, result), [])
                finals = [n for n in calls if "final" in n or "repair" in n or "scope" in n]
                if exit in ("needs_owner", "steward_blocked", "task_loop_exhausted"):
                    self.assertEqual(finals, [], "needs_owner/blocked bypass the final phase")
        graph = milestone.milestone_graph(2)
        self.assertEqual(exits, {n["name"] for n in nodes(graph["root"]) if n["kind"] == "succeed"})

    def test_native_errors_stay_failures(self):
        script = {"preflight": ["ready"], "select_init": ["open"] * 2, "acceptance_review": ["accepted"] * 2,
                  "code_review": ["accepted"] * 2, "steward_decide": ["done"] * 2, "final_verify": ["rejected"], "scope_verify": ["accepted"],
                  "final_reverify": ["accepted"], "select_verify": ["selected"] * 2}
        expected = {"preflight": "preflight_failed", "select_init": "select_init_failed", "select": "select_failed",
                    "select_verify": "select_verify_failed", "worker": "worker_failed",
                    "acceptance_review": "acceptance_review_failed", "code_review": "code_review_failed",
                    "steward_apply": "steward_apply_failed", "steward_decide": "steward_decide_failed",
                    "final_verify": "final_verify_failed", "repair": "repair_failed", "scope_verify": "scope_verify_failed",
                    "final_reverify": "final_reverify_failed"}
        for node, reason in expected.items():
            with self.subTest(node):
                result, calls, _ = flow(self, dict(tasks=1, script=script), error=node)
                self.assertEqual((result["status"], result["reason"]), ("failed", reason))
                self.assertEqual(calls.count(node), 1)
                if node == "steward_apply":
                    self.assertEqual(calls[-1], "steward_decide")
        result, _, _ = flow(self, dict(tasks=1, script={"preflight": ["ready"], "select_init": ["empty"]}),
                         error="empty_final_verify")
        self.assertEqual(result["reason"], "empty_final_verify_failed")

    def test_failed_selection_ends_before_any_writer(self):
        # Missing checker or corrupt manifest: the validation/selection commands fail.
        writers = {"worker", "steward_apply", "repair", "empty_repair"}
        for script, reason in (({"select_init": ["invalid"]}, "select_init_invalid"),
                               ({"select_init": ["open"], "select_verify": ["invalid"]}, "selection_invalid")):
            with self.subTest(reason):
                result, calls, provider = flow(self, dict(tasks=1, script=dict(script, preflight=["ready"])))
                self.assertEqual((result["status"], result["reason"]), ("failed", reason))
                self.assertFalse(writers & set(calls), calls)
                self.assertEqual(provider.leftovers(), {})


class QualificationHarnessTests(unittest.TestCase):
    def request(self, *markers, schema=None):
        node = {"kind": "verifier", "output": {"kind": "null"}, "signals": {"verdict": ["accepted", "rejected"]},
                "diagnostic": milestone.record("message"), "instructions": ""}
        request = provider_request(node, {})
        request["input"] = [{"role": "user", "content": [{"type": "input_text", "text": "ZPLAN_NODE=%s\n" % m}]} for m in markers]
        if schema is not None:
            request["text"]["format"]["schema"] = schema
        return request

    def test_dispatch_uses_the_last_marker(self):
        provider = driver_qual.Provider({"acceptance_review": ["rejected"], "code_review": ["accepted"]})
        answer = provider.answer(self.request("worker", "code_review"))
        self.assertEqual(answer, {"output": None, "signals": {"verdict": "accepted"},
                                  "diagnostic": {"message": "code_review message #1"}})
        self.assertEqual(provider.calls, [("code_review", "accepted")])
        self.assertEqual(provider.leftovers(), {"acceptance_review": ["rejected"]})
        with self.assertRaisesRegex(driver_qual.QualError, "unexpected call #2"):
            provider.answer(self.request("code_review"))
        with self.assertRaisesRegex(driver_qual.QualError, "without a ZPLAN_NODE"):
            provider.answer(self.request())

    def test_answers_are_validated_against_the_request_schema(self):
        provider = driver_qual.Provider({"code_review": ["approved"]})
        with self.assertRaisesRegex(driver_qual.QualError, "violates the request schema"):
            provider.answer(self.request("code_review"))
        with self.assertRaisesRegex(driver_qual.QualError, "scripted labels for a step"):
            driver_qual.Provider({"worker": ["accepted"]}).answer(
                provider_request({"kind": "step", "output": milestone.record("report"), "instructions": "ZPLAN_NODE=worker"}, {}))
        self.assertEqual(driver_qual.Provider({}).answer(
            provider_request({"kind": "step", "output": milestone.record("report"), "instructions": "ZPLAN_NODE=repair"}, {})),
            {"report": "repair report #1"})
        closed = {"type": "object", "properties": {"a": {"type": "string", "enum": ["x"]}}, "required": ["a"],
                  "additionalProperties": False}
        self.assertTrue(driver_qual.valid(closed, {"a": "x"}))
        for value in ({}, {"a": "y"}, {"a": "x", "b": 1}, [], {"a": None}):
            self.assertFalse(driver_qual.valid(closed, value), value)
        self.assertTrue(driver_qual.valid({"anyOf": [{"type": "string"}, {"type": "null"}]}, None))
        with self.assertRaisesRegex(driver_qual.QualError, "unsupported"):
            driver_qual.valid({"type": "string", "pattern": "x"}, "x")

    def test_loopback_server_streams_scripted_answers(self):
        provider = driver_qual.Provider({"code_review": ["accepted"]})
        server, port = driver_qual.serve(provider)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def post(request):
            return urllib.request.urlopen(urllib.request.Request(
                "http://127.0.0.1:%s/v1/responses" % port, json.dumps(request).encode(),
                {"Content-Type": "application/json"}), timeout=10)

        with post(self.request("code_review")) as response:
            events = [json.loads(line[6:]) for line in response.read().decode().split("\n\n") if line]
        self.assertEqual([e["type"] for e in events], ["response.created", "response.output_item.done", "response.completed"])
        self.assertEqual(json.loads(events[1]["item"]["content"][0]["text"])["response"]["signals"], {"verdict": "accepted"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            post(self.request("code_review"))
        self.assertEqual(caught.exception.code, 500)
        self.assertEqual(provider.errors, ["code_review: unexpected call #2"])

    def test_check_reports_order_leftovers_repairs_and_root(self):
        scenario = driver_qual.SCENARIOS["b_review_repair"]
        provider = driver_qual.Provider({"final_verify": ["accepted"]})
        provider.calls = [("select_init", "open"), ("select", None), ("worker", None), ("code_review", "accepted"),
                          ("acceptance_review", "accepted"), ("worker", None)]
        problems = driver_qual.check(scenario, provider, {"status": "failed", "reason": "x"})
        self.assertEqual([p.split(" ")[0] for p in problems], ["node", "unused", "repair", "root"])
        self.assertEqual(driver_qual.normalize(["code_review", "acceptance_review", "worker"]),
                         ["acceptance_review", "code_review", "worker"])
        self.assertEqual(driver_qual.repairs_after_acceptance(
            [("final_verify", "rejected"), ("repair", None), ("scope_verify", "rejected"), ("final_reverify", "accepted"),
             ("repair", None), ("scope_verify", "accepted"), ("final_reverify", "accepted"), ("repair", None)]), ["repair"])

    def test_main_skips_without_the_pinned_binary(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(driver_qual.main(["--binary", "/nonexistent/zeroshot"]), 2)
            self.assertEqual(driver_qual.main(["--binary", "/nonexistent/zeroshot", "m_adapter_resume"]), 2)
        self.assertIn("SKIP", out.getvalue())

    # Adapter scenario wiring (the native runs themselves are Linux-only: devtools/linux-test.sh --py) -----------

    def test_adapter_scenarios_are_named_and_wired_to_adapter_steps(self):
        self.assertEqual(sorted(driver_qual.ADAPTER), ["k_adapter_done_merge", "l_adapter_lost_stop", "m_adapter_resume"])
        self.assertFalse(set(driver_qual.ADAPTER) & set(driver_qual.SCENARIOS))
        self.assertEqual(driver_qual.ALL, {**driver_qual.SCENARIOS, **driver_qual.ADAPTER})
        # Each scenario gets its own short scratch directory named by its prefix.
        self.assertEqual(len({name.split("_")[0] for name in driver_qual.ALL}), len(driver_qual.ALL))
        for name, scenario in driver_qual.ADAPTER.items():
            self.assertEqual(scenario["drive"].__name__, "adapter_" + name.split("_", 2)[2])
            for method in scenario["hooks"].values():
                self.assertTrue(callable(getattr(driver_qual.Adapter, method)), method)
        self.assertEqual(driver_qual.ADAPTER["m_adapter_resume"]["broken"], ["steward_apply"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            driver_qual.main(["--binary", "/nonexistent/zeroshot", "z_unknown"])

    def test_provider_hooks_broken_nodes_and_repeat(self):
        seen = []
        provider = driver_qual.Provider({"code_review": ["rejected", "accepted"]}, repeat=True, broken={"worker"},
                                        hooks={"code_review": lambda: seen.append("code_review"),
                                               "worker": lambda: seen.append("worker")})
        labels = [provider.answer(self.request("code_review"))["signals"]["verdict"] for _ in range(3)]
        self.assertEqual(labels, ["rejected", "accepted", "accepted"])
        self.assertEqual(provider.answer(self.request("worker")), {})
        self.assertEqual(seen, ["code_review"] * 3)
        self.assertEqual(provider.calls[-1], ("worker", "malformed"))
        provider.hooks["code_review"] = lambda: 1 / 0
        with self.assertRaisesRegex(driver_qual.QualError, "code_review hook: division"):
            provider.answer(self.request("code_review"))
        with self.assertRaisesRegex(driver_qual.QualError, "unexpected call #2"):
            once = driver_qual.Provider({"code_review": ["accepted"]})
            once.answer(self.request("code_review"))
            once.answer(self.request("code_review"))

    def adapter(self):
        work = Path(tempfile.mkdtemp(prefix="zq"))
        self.addCleanup(shutil.rmtree, work, ignore_errors=True)
        return driver_qual.Adapter(work, "/unused/zeroshot", {}, driver_qual.Provider({}), time.monotonic() + 60)

    def test_adapter_hooks_leave_a_done_manifest_and_a_product_file(self):
        q = self.adapter()
        worktree = q.worktrees / "one"
        (worktree / ".zplan").mkdir(parents=True)
        baseline, manifest = milestone.build_manifest(driver_qual.proposal(2), "M1", 1)
        for relative, value in ((milestone.BASELINE, baseline), (milestone.MANIFEST, manifest)):
            (worktree / relative).write_text(canonical(value) + "\n")
        q.produce()
        self.assertTrue((worktree / "qual-M1.txt").is_file())
        for count in (1, 2, 3):
            q.accept()
            accepted = milestone.validate(baseline, json.loads((worktree / milestone.MANIFEST).read_text()))
            self.assertEqual([t["status"] for t in accepted["tasks"]], ["done"] * min(count, 2) + ["open"] * (2 - min(count, 2)))
        self.assertEqual([p["phase"] for p in accepted["progress"]], ["accepted", "accepted"])
        (q.worktrees / "two").mkdir()
        with self.assertRaisesRegex(driver_qual.QualError, "found 2"):
            q.worktree()

    def test_adapter_script_with_hooks_reaches_done_through_the_graph(self):
        q = self.adapter()
        scenario = driver_qual.ADAPTER["k_adapter_done_merge"]
        graph, _, value = driver_qual.documents({"tasks": 1})
        seen = []
        provider = driver_qual.Provider(scenario["script"], repeat=True,
                                        hooks={node: (lambda node=node: seen.append(node)) for node in scenario["hooks"]})
        result, calls = interpret(self, graph, value, provider)
        self.assertEqual(result["output"]["signal"], "done")
        self.assertEqual(seen, ["worker", "steward_apply"])
        self.assertTrue(all(callable(getattr(q, method)) for method in scenario["hooks"].values()))

    def test_adapter_records_a_source_from_a_timed_out_watch_slice(self):
        # Every bounded watch slice ends by timing out (runs.poll passes a short `slice`); the whole records
        # already read must still count, and the trailing partial line is re-read by the next slice.
        q = self.adapter()
        r = {"branch": "zs-M1", "destination": {"base": "a" * 40}}
        source = {"repository": "zplan-qual/fixture", "branch": "zs-M1", "revision": "a" * 40}
        cut = (json.dumps({"source": source}) + "\n" + '{"source": {"repo').encode()
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("watch", 1, output=cut)):
            with self.assertRaises(subprocess.TimeoutExpired):
                q.call(["zeroshot", "watch", "run-1"], capture_output=True, timeout=1)
        self.assertEqual(q.sources, [source])
        q.check_source(r)
        # A completed watch records too; a non-watch call never does.
        done = subprocess.CompletedProcess(["zeroshot", "watch", "run-1"], 0, (json.dumps({"source": source}) + "\n").encode(), b"")
        with mock.patch("subprocess.run", return_value=done):
            q.call(["zeroshot", "watch", "run-1"], capture_output=True)
            q.call(["zeroshot", "status", "run-1"], capture_output=True, text=True)
        self.assertEqual(q.sources, [source, source])

    def test_lost_stop_drops_only_the_first_force_stop(self):
        calls = []
        driver = driver_qual.LostStop("/bin/sh", Path(tempfile.gettempdir()) / "zq-state",
                                      call=lambda argv, **kwargs: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", ""))
        r = {"run_id": "run-1", "worktree": tempfile.gettempdir()}
        with self.assertRaisesRegex(Blocked, "stopping"):
            driver.force_stop(r)
        self.assertEqual(calls, [])
        driver.force_stop(r)
        self.assertEqual([argv[1:] for argv in calls], [["force-stop", "run-1"]])

    def test_follow_polls_bounded_slices_until_done_or_deadline(self):
        q = self.adapter()
        r = {"status": "running"}

        class Runs:
            polls = 0

            def poll(self, record, mark):
                self.polls += 1
                if self.polls == 3:
                    record["status"] = "finished"
                return ["slice %s" % self.polls], {"n": self.polls}

        self.assertEqual(q.follow(Runs(), r), (3, ["slice 1", "slice 2", "slice 3"]))
        q.deadline = 0
        r["status"] = "running"
        with self.assertRaisesRegex(driver_qual.QualError, "timeout in status running"):
            q.follow(Runs(), r)

    def test_approve_scripts_an_approved_native_plan_under_the_scratch_home(self):
        root = Path(tempfile.mkdtemp(prefix="z")).resolve()  # short: the state dir holds the controller socket path
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        project, home, binary = root / "p", root / "h", root / "zeroshot"
        home.mkdir()
        binary.write_text("#!/bin/sh\nprintf '%s\\n'\n" % toolchain.current().zeroshot_version)
        binary.chmod(0o700)
        project.mkdir()
        driver_qual.git(project, "init", "-q", "-b", "main")
        (project / "README.md").write_text("fixture\n")
        driver_qual.git(project, "add", ".")
        driver_qual.git(project, "commit", "-qm", "fixture")
        driver_qual.git(project, "remote", "add", "origin", "https://github.com/zplan-qual/fixture.git")
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            driver_qual.approve(project, binary, root / "s")
            with driver_qual.Authority(None, project) as a:
                self.assertEqual((a.current["status"], a.current["engine"]), ("approved", "native"))
                self.assertEqual(a.current["proposal"], driver_qual.proposal(1))
                self.assertTrue(a.directory.is_relative_to(home.resolve()))


def pinned_binary():
    path = Path(os.environ.get("ZEROSHOT_TEST_BINARY") or tool_paths()[0])
    return path if path.is_file() else None


@unittest.skipUnless(pinned_binary(), "pinned zeroshot binary absent (set ZEROSHOT_TEST_BINARY)")
class AdmissionTests(unittest.TestCase):
    def test_driver_graph_passes_native_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "fixture"]):
                subprocess.run(["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
                               check=True, capture_output=True)
            env = dict(os.environ, ZEROSHOT_STATE_DIR=str(root / "state"), ZEROSHOT_CONFIG_DIR=str(root / "config"))
            for tasks in (1, milestone.MAX_INITIAL_TASKS):
                with self.subTest(tasks=tasks):
                    for kind, value in zip(("graph", "runtime", "input"), driver_qual.documents({"tasks": tasks})):
                        (root / (kind + ".json")).write_text(json.dumps(value))
                    result = subprocess.run([str(pinned_binary()), "run", "--title", "zplan driver admission",
                                             "--graph", str(root / "graph.json"), "--runtime-config", str(root / "runtime.json"),
                                             "--input", str(root / "input.json"), "--no-environment", "--validate-only"],
                                            cwd=project, env=env, capture_output=True, text=True, timeout=120)
                    self.assertEqual(result.returncode, 0, result.stderr[-2000:])
                    self.assertIs(json.loads(result.stdout)["valid"], True)


if __name__ == "__main__":
    unittest.main()
