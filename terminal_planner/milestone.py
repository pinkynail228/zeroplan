"""Milestone driver contract: manifest, amendment rules and the native driver graph.

zplan writes `.zplan/baseline.json` (immutable) and `.zplan/milestone.json`
(mutable) into the target checkout and passes the same baseline in graph input.
Graph agents run the deterministic validator:

    python3 -m terminal_planner.milestone check .zplan/milestone.json --baseline .zplan/baseline.json
"""

import argparse
import copy
from pathlib import Path
import sys

from .authority import MAX_MILESTONE_TASKS, Blocked, brief_problem, canonical, decode, validate_proposal
from .engine import record, state_binding


MAX_INITIAL_TASKS = MAX_MILESTONE_TASKS
MAX_ADDITIONS = 6
TASK_ITERATIONS = 4  # 1 implementation + 3 repairs; the bound when the milestone has no frozen profile
FINAL_REPAIRS = 3
FINAL_ATTEMPTS = 2  # executions of one final check (the first and one retry) before an incomplete check blocks the run
STATUSES = ("open", "done", "dropped")
ORIGINS = ("plan", "amendment")
KINDS = ("add", "split", "reorder", "reword", "drop")
SIGNALS = ("done", "needs_owner", "blocked")
ALL_REQUIREMENTS = "Every requirement of the milestone is satisfied."
# The review bar every milestone review shares (D1): a review rejects on a broken check, a broken task title or broken
# existing behaviour on a realistic path; every other remark is a non-blocking note. Tests assert these sentences.
REVIEW_BAR = ("A review rejects only when a check or the title of input.task fails on a realistic path, or the change "
              "breaks existing behaviour on a realistic path; anything else goes into diagnostic.message as a "
              "non-blocking note marked `note:` and never rejects the change.")
# The verification rule the worker follows (H3): proportionate to the change, the project's own way. Tests assert it.
VERIFY_RULE = ("Verify the change the project's own way and in proportion to it: in a project with a test setup, a "
               "behaviour change (a new feature included) gets a relevant test, and a test the task asks for (a "
               "project's first included) is written; a change to docs, copy or config files alone gets no new test, "
               "only the project's existing checks.")
MANIFEST = ".zplan/milestone.json"
BASELINE = ".zplan/baseline.json"
BEFORE = ".zplan/milestone.before.json"
TOOL = "python3 -m terminal_planner.milestone"
WORKER_TIMEOUT = 45 * 60 * 1000
CONTROL_TIMEOUT = 20 * 60 * 1000
# The task reviews' `conflict` verdict (C2): a brief defect only the owner can fix, never an implementation defect.
CONFLICT_BAR = ("Signal verdict=conflict only for an evidenced defect of the brief of input.task that needs a brief "
                "change, and name in diagnostic.message the task, the criterion and the incompatible requirements; an "
                "implementation defect stays rejected, a remark stays a `note:`, and a missing tool or a failed "
                "command is never a conflict.")
ERRORS = ["timeout", "crash", "malformed", "refusal"]
# The final checks' verdicts (H1): `incomplete` is a required check that could not run to the end; a seen defect is
# `rejected`. FINAL_VERDICTS feeds the state enum and the signal sets of final_verify and final_reverify; the routes
# and loops read its two parts.
FINAL_DECIDED = ["accepted", "rejected"]
FINAL_INCOMPLETE = ["incomplete"]
FINAL_VERDICTS = FINAL_DECIDED + FINAL_INCOMPLETE


class Invalid(Blocked):
    family = "milestone.manifest_invalid"


def check(ok, message):
    if not ok:
        raise Invalid(message)


def text(value, limit=8192):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def outer_iterations(initial_tasks):
    """Every task may need a work pass and a steward re-plan; +2 covers the last decision."""
    return 2 * (initial_tasks + MAX_ADDITIONS) + 2


def review_iterations(task_rounds):
    """The milestone review loop's bound: one implementation pass plus the frozen `limits.task_rounds` repair rounds
    (`1 + task_rounds`); the fixed `TASK_ITERATIONS` when the milestone has no frozen profile (`task_rounds` None)."""
    return TASK_ITERATIONS if task_rounds is None else 1 + task_rounds


# Manifest -----------------------------------------------------------------

def build_baseline(proposal, milestone_id, plan_revision):
    """Frozen baseline of one milestone of an approved proposal."""
    validate_proposal(proposal)
    milestone = next((m for m in proposal["milestones"] if m["id"] == milestone_id), None)
    check(milestone is not None, "Milestone %s is not in the approved plan." % milestone_id)
    tasks = [task for slice_ in milestone["slices"] for task in slice_["tasks"]]
    if len(tasks) > MAX_INITIAL_TASKS:
        raise Blocked("Milestone %s has %s tasks; the driver runs at most %s. Split the milestone in the plan "
                      "and approve a new revision before running it." % (milestone_id, len(tasks), MAX_INITIAL_TASKS), family="milestone.too_many_tasks")
    covered = {r for slice_ in milestone["slices"] for r in slice_["requirements"]}
    checks = []
    for task in tasks:
        checks += [c for c in task["checks"] if c not in checks]
    return {
        "schemaVersion": "1", "plan_revision": plan_revision,
        "milestone": {"id": milestone["id"], "title": milestone["title"], "depends_on": list(milestone["depends_on"])},
        "requirements": [copy.deepcopy(r) for r in proposal["requirements"] if r["id"] in covered],
        "slices": [{"id": s["id"], "title": s["title"], "requirements": list(s["requirements"])} for s in milestone["slices"]],
        "tasks": [dict({"id": t["id"], "title": t["title"], "checks": list(t["checks"])},
                       **({"brief": copy.deepcopy(t["brief"])} if "brief" in t else {})) for t in tasks],
        "checks": checks + [ALL_REQUIREMENTS],
        "limits": {"initial_tasks": len(tasks), "max_additions": MAX_ADDITIONS,
                   "task_iterations": TASK_ITERATIONS, "outer_iterations": outer_iterations(len(tasks)),
                   "final_repairs": FINAL_REPAIRS},
    }


def initial_manifest(baseline):
    return {
        "schemaVersion": "1", "plan_revision": baseline["plan_revision"],
        "milestone": {"id": baseline["milestone"]["id"], "title": baseline["milestone"]["title"]},
        "baseline": copy.deepcopy(baseline),
        "tasks": [dict(copy.deepcopy(t), status="open", origin="plan", notes="") for t in baseline["tasks"]],
        "amendments": [], "progress": [], "outcome": None,
    }


def build_manifest(proposal, milestone_id, plan_revision):
    """Return (baseline, manifest) for an approved proposal."""
    baseline = build_baseline(proposal, milestone_id, plan_revision)
    return baseline, initial_manifest(baseline)


def validate_baseline(baseline):
    check(isinstance(baseline, dict) and set(baseline) == {"schemaVersion", "plan_revision", "milestone", "requirements",
                                                          "slices", "tasks", "checks", "limits"}
          and baseline["schemaVersion"] == "1", "baseline: fields")
    tasks = baseline["tasks"]
    check(isinstance(tasks, list) and len(tasks) <= MAX_INITIAL_TASKS, "baseline: more than %s tasks" % MAX_INITIAL_TASKS)
    check(baseline["limits"] == {"initial_tasks": len(tasks), "max_additions": MAX_ADDITIONS,
                                 "task_iterations": TASK_ITERATIONS, "outer_iterations": outer_iterations(len(tasks)),
                                 "final_repairs": FINAL_REPAIRS}, "baseline: limits differ from the driver bounds")
    for task in tasks:
        check(isinstance(task, dict), "baseline: task")
        check("brief" not in task or brief_problem(task["brief"]) is None, "baseline: task %s: %s" % (task.get("id"), brief_problem(task.get("brief"))))
    check(isinstance(baseline["checks"], list) and baseline["checks"][-1:] == [ALL_REQUIREMENTS]
          and baseline["checks"][:-1] == list(dict.fromkeys(c for t in tasks for c in t["checks"])),
          "baseline: milestone checks are not the union of task checks plus the requirements check")
    return baseline


def validate_task(task):
    check(isinstance(task, dict) and {"id", "title", "checks", "status", "origin", "notes"} <= set(task)
          <= {"id", "title", "checks", "status", "origin", "notes", "parent", "brief"}, "task: fields")
    check(text(task["id"], 128) and text(task["title"]), "task %s: id/title" % task.get("id"))
    check(isinstance(task["checks"], list) and task["checks"] and all(text(c) for c in task["checks"]),
          "task %s: checks must be nonempty strings" % task["id"])
    check(task["status"] in STATUSES and task["origin"] in ORIGINS and isinstance(task["notes"], str),
          "task %s: status/origin/notes" % task["id"])
    check("parent" not in task or text(task["parent"], 128), "task %s: parent" % task["id"])
    check("brief" not in task or brief_problem(task["brief"]) is None,
          "task %s: %s" % (task["id"], brief_problem(task.get("brief"))))


def validate_records(values, fields, name):
    check(isinstance(values, list), name + ": list")
    for seq, value in enumerate(values, 1):
        check(isinstance(value, dict) and set(value) == fields and value["seq"] == seq,
              "%s %s: fields or seq (must be 1..n)" % (name, seq))


def validate(baseline, manifest):
    """Check one manifest against the immutable baseline, including cumulative amendment rules."""
    validate_baseline(baseline)
    check(isinstance(manifest, dict) and set(manifest) == {"schemaVersion", "plan_revision", "milestone", "baseline",
                                                          "tasks", "amendments", "progress", "outcome"}
          and manifest["schemaVersion"] == "1", "manifest: fields")
    check(canonical(manifest["baseline"]) == canonical(baseline), "manifest: frozen baseline changed")
    check(manifest["plan_revision"] == baseline["plan_revision"]
          and manifest["milestone"] == {"id": baseline["milestone"]["id"], "title": baseline["milestone"]["title"]},
          "manifest: plan revision or milestone changed")
    tasks = manifest["tasks"]
    check(isinstance(tasks, list), "manifest: tasks")
    for task in tasks:
        validate_task(task)
    ids = [t["id"] for t in tasks]
    check(len(ids) == len(set(ids)), "manifest: duplicate task id")
    plan = {t["id"]: t for t in baseline["tasks"]}
    check({t["id"] for t in tasks if t["origin"] == "plan"} == set(plan), "manifest: plan tasks must stay listed")
    for task in tasks:
        if task["origin"] == "plan":
            check(task["checks"] == plan[task["id"]]["checks"] and "parent" not in task,
                  "task %s: plan task checks are frozen" % task["id"])
            check(task.get("brief") == plan[task["id"]].get("brief"), "task %s: plan task brief is frozen" % task["id"])
        check(task.get("parent", task["id"]) in ids and task.get("parent") != task["id"],
              "task %s: unknown parent" % task["id"])
    validate_records(manifest["amendments"], {"seq", "kind", "tasks", "parents", "reason"}, "amendment")
    for amendment in manifest["amendments"]:
        check(amendment["kind"] in KINDS and text(amendment["reason"])
              and isinstance(amendment["tasks"], list) and isinstance(amendment["parents"], list)
              and set(amendment["tasks"] + amendment["parents"]) <= set(ids),
              "amendment %s: kind/tasks/parents/reason" % amendment["seq"])
    validate_records(manifest["progress"], {"seq", "task", "phase", "text"}, "progress")
    for item in manifest["progress"]:
        check(item["task"] in ids and text(item["phase"], 64) and isinstance(item["text"], str),
              "progress %s: task/phase/text" % item["seq"])
    for task in tasks:
        if task["status"] == "done":
            phases = [p["phase"] for p in manifest["progress"] if p["task"] == task["id"]]
            check(phases[-1:] == ["accepted"],
                  "task %s: done requires a final progress record phase=accepted (both reviews accepted)" % task["id"])
    outcome = manifest["outcome"]
    check(outcome is None or (isinstance(outcome, dict) and {"signal", "message"} <= set(outcome)
                              <= {"signal", "message", "question", "proposal"} and outcome["signal"] in SIGNALS
                              and all(isinstance(v, str) for v in outcome.values())), "manifest: outcome")
    check_amendments(baseline, initial_manifest(baseline), manifest, cumulative=True)
    return manifest


def check_amendments(baseline, before, after, cumulative=False):
    """Reject baseline edits, id reuse, unrecorded scope changes and more than MAX_ADDITIONS additions.

    cumulative=True compares against the initial manifest: tasks added in earlier iterations may by now be done
    (validate() separately requires the final accepted progress record) or dropped (drop or split-parent)."""
    for name, value in (("before", before), ("after", after)):
        check(canonical(value["baseline"]) == canonical(baseline), "%s: frozen baseline changed" % name)
        check(value["plan_revision"] == baseline["plan_revision"] and value["milestone"]["id"] == baseline["milestone"]["id"],
              "%s: plan revision or milestone changed" % name)
    check(after["amendments"][:len(before["amendments"])] == before["amendments"], "amendments are append-only")
    check(after["progress"][:len(before["progress"])] == before["progress"], "progress is append-only")
    old = {t["id"]: t for t in before["tasks"]}
    new = {t["id"]: t for t in after["tasks"]}
    check(len(new) == len(after["tasks"]), "duplicate task id")
    check(set(old) <= set(new), "tasks are never removed; drop them instead (tombstone)")
    added = [t for t in after["tasks"] if t["origin"] == "amendment"]
    check(len(added) <= MAX_ADDITIONS,
          "%s tasks added; at most %s per milestone (split children and dropped tasks count)" % (len(added), MAX_ADDITIONS))
    amendments = after["amendments"][len(before["amendments"]):]

    # Only the task select chose (first open task of the before snapshot) is reviewed in an iteration.
    selected = next((t["id"] for t in before["tasks"] if t["status"] == "open"), None)

    def recorded(kinds, task_id, field="tasks"):
        return any(a["kind"] in kinds and task_id in a[field] for a in amendments)

    for task_id, task in new.items():
        if task_id not in old:
            check(task["origin"] == "amendment" and task_id not in {t["id"] for t in baseline["tasks"]},
                  "task %s: new tasks must be amendments with a fresh id" % task_id)
            check(recorded(("add", "split"), task_id), "task %s: addition without an add/split amendment" % task_id)
            if "parent" in task:
                check(recorded(("split",), task_id) and recorded(("split",), task["parent"], "parents"),
                      "task %s: parent requires a split amendment naming it" % task_id)
            if cumulative:
                check(task["status"] != "dropped" or recorded(("drop",), task_id) or recorded(("split",), task_id, "parents"),
                      "task %s: drop requires a drop/split amendment" % task_id)
            else:
                check(task["status"] == "open" or (task["status"] == "dropped" and recorded(("drop",), task_id)),
                      "task %s: a new task starts open" % task_id)
            continue
        prior = old[task_id]
        check(task["origin"] == prior["origin"] and task["checks"] == prior["checks"] and task.get("parent") == prior.get("parent")
              and task.get("brief") == prior.get("brief"),
              "task %s: origin, checks, parent and brief are fixed" % task_id)
        if task["title"] != prior["title"]:
            check(prior["status"] == "open" and recorded(("reword",), task_id), "task %s: retitle requires a reword amendment" % task_id)
        if task["status"] != prior["status"]:
            check(prior["status"] == "open", "task %s: done and dropped are final" % task_id)
            if task["status"] == "dropped":
                check(recorded(("drop",), task_id) or recorded(("split",), task_id, "parents"),
                      "task %s: drop requires a drop/split amendment" % task_id)
            else:
                check(cumulative or task_id == selected,
                      "task %s: only the selected task %s may be marked done in one iteration" % (task_id, selected))
                fresh = [p for p in after["progress"][len(before["progress"]):] if p["task"] == task_id]
                check(fresh and fresh[-1]["phase"] == "accepted",
                      "task %s: done requires a new progress record phase=accepted in this iteration" % task_id)
    order = [i for i in (t["id"] for t in after["tasks"]) if i in old]
    if order != [t["id"] for t in before["tasks"]]:
        check(any(a["kind"] == "reorder" for a in amendments), "task order changed without a reorder amendment")
    return after


def next_task(baseline, manifest):
    """Task contract of the first open task, or None for an empty queue."""
    validate(baseline, manifest)
    task = next((t for t in manifest["tasks"] if t["status"] == "open"), None)
    if task is None:
        return None
    return {"milestone": manifest["milestone"], "task": {k: task[k] for k in ("id", "title", "checks", "notes", "parent", "brief") if k in task},
            "requirements": baseline["requirements"], "milestone_checks": baseline["checks"]}


# Driver graph --------------------------------------------------------------

STATE_FIELDS = ("schemaVersion", "milestone", "baseline", "task", "workerReport", "acceptanceFindings", "codeFindings",
                "stewardReport", "message", "question", "proposal", "finalFindings", "scopeFindings", "repairReport")
VERDICTS = ("acceptanceVerdict", "codeVerdict", "finalVerdict", "scopeVerdict")
REVIEW_VERDICTS = ("acceptanceVerdict", "codeVerdict")  # the task reviews may also report a brief conflict
OUTCOMES = {"doneSignal": "done", "needsOwnerSignal": "needs_owner", "blockedSignal": "blocked"}
TASK_STATE = ["workerReport", "acceptanceVerdict", "acceptanceFindings", "codeVerdict", "codeFindings"]
STEWARD_STATE = TASK_STATE + ["stewardReport"]
DECISION_STATE = ["message", "question", "proposal"]
FINAL_STATE = ["finalVerdict", "finalFindings", "scopeVerdict", "scopeFindings", "repairReport"]
FINAL_ROLES = {"final_verify": "reviewer", "repair": "worker", "scope_verify": "reviewer", "final_reverify": "reviewer"}
ROLES = {"preflight": "reviewer", "select_init": "steward", "select": "steward", "select_verify": "steward", "worker": "worker", "acceptance_review": "reviewer",
         "code_review": "reviewer", "steward_apply": "steward", "steward_decide": "steward",
         **FINAL_ROLES, **{"empty_" + name: role for name, role in FINAL_ROLES.items()}}


def milestone_state():
    state = record(*STATE_FIELDS)
    for name in VERDICTS:
        if name == "finalVerdict":
            values = ["pending"] + FINAL_VERDICTS
        else:
            values = ["pending", "accepted", "rejected"] + (["conflict"] if name in REVIEW_VERDICTS else [])
        state["fields"][name] = {"type": {"kind": "enum", "values": values}, "required": True}
    for name in OUTCOMES:
        # Graph bindings have no literals; outcome labels come from validated input constants.
        state["fields"][name] = {"type": {"kind": "enum", "values": list(SIGNALS)}, "required": True}
    return state


def milestone_output():
    output = record("signal", "message", "question", "proposal")
    output["fields"]["signal"]["type"] = {"kind": "enum", "values": list(SIGNALS)}
    for name in ("question", "proposal"):
        output["fields"][name]["required"] = False
    return output


def instructions(body, tool=TOOL):
    commands = ("Manifest: %s. Immutable baseline: %s (never edit it). Validate with: %s check %s --baseline %s"
                % (MANIFEST, BASELINE, tool, MANIFEST, BASELINE))
    return "%s\n%s" % (commands, body)


def milestone_graph(initial_tasks, rounds=TASK_ITERATIONS, tool=TOOL):
    """Driver graph for one milestone; bounds are fixed when the graph is built. `rounds` is the review loop's
    bound: `1 + the frozen limits.task_rounds` of the plan revision's process profile, or `TASK_ITERATIONS` when
    the milestone has no frozen profile (see `review_iterations`)."""
    if not 0 <= initial_tasks <= MAX_INITIAL_TASKS:
        raise Blocked("A milestone may start with at most %s tasks." % MAX_INITIAL_TASKS, family="milestone.too_many_tasks")
    state = milestone_state()

    def guard(name, source, labels, field=None):
        return {"kind": "in", "value": {"name": name, "source": source, "field": field}, "labels": labels}

    def failed(name):
        return guard(name, "error", ERRORS)

    def write(target, node, channel, path):
        return {"target": [target], "value": {"node": node, "channel": channel, "path": [path]}}

    def fail(name):
        return {"kind": "fail", "name": name, "reason": name}

    def seq(name, children, promoted=()):
        return {"kind": "seq", "name": name, "state": state, "children": children, "promotedStatePaths": [[p] for p in promoted]}

    def choice(name, branches, otherwise, promoted=()):
        node = {"kind": "choice", "name": name, "state": state, "promotedStatePaths": [[p] for p in promoted],
                "branches": [{"when": when, "node": target} for when, target in branches]}
        if otherwise is not None:
            node["otherwise"] = otherwise
        return node

    def guarded(name, node, promoted=()):
        # Explicit choices keep runtime errors away from absent output/signal channels.
        return choice(name + "_result", [(failed(name), fail(name + "_failed"))], node, promoted)

    def executable(kind, name, body, inputs, output="report", writes=(), timeout=CONTROL_TIMEOUT, **extra):
        # Distinct worker refs: admission rejects one ref reused with different node contracts.
        return {"kind": kind, "name": name, "worker": "zplan.milestone.%s@1" % name.replace("_", "-"),
                "instructions": instructions(body, tool),
                "input": {"kind": "record", "fields": {i: state["fields"][i] for i in inputs}},
                "output": record(output) if output else {"kind": "null"},
                "inputBindings": [state_binding(i) for i in inputs], "writeBindings": list(writes),
                "attempts": 1, "timeoutMs": timeout, **extra}

    def verifier(name, body, inputs, signal, labels, verdict=None, findings=None, diagnostic=("message",), writes=None,
                 timeout=CONTROL_TIMEOUT):
        if writes is None:
            writes = [write(verdict, name, "signal", signal), write(findings, name, "diagnostic", "message")]
        return executable("verifier", name, body, inputs, output=None, writes=writes,
                          signals={signal: labels}, diagnostic=record(*diagnostic), timeout=timeout)

    def success(name, signal, bindings):
        # `succeed` ends the whole run (graph.rs:367), so loops exit only through `until` and
        # their `terminated` group; business exits sit after the loops that decide them.
        output = milestone_output()
        return {"kind": "succeed", "name": name, "output": output,
                "bindings": [{"target": ["signal"], "value": {"source": "state", "path": [signal]}}]
                + [{"target": [t], "value": {"source": "state", "path": [s]}} for t, s in bindings]}

    read_only = "Read only: change no file and no manifest field. "
    context = ["milestone", "baseline"]

    def final_stage(prefix):
        # The pinned Zeroshot (toolchain.DEFAULT) conjoins every earlier guard into a seq's completion predicate and
        # caps its assignment space at 65536 (openengine-cluster-server graph_verifier
        # analyzer_nodes.rs:127, analyzer_parallel.rs:9). The final stage after the task loop
        # exceeds it, so it lives inside each branch that reaches it: tasks done (no prefix)
        # and the empty queue ("empty_" node names).
        def n(name):
            return prefix + name
        final_inputs = context + ["finalFindings", "scopeFindings"]
        final_body = read_only + (
            "Final milestone verification: check the workspace against every frozen requirement and every derived "
            "milestone check in input.baseline, with fresh evidence you gather yourself. verdict=accepted only when all "
            "hold; verdict=rejected with actionable findings in diagnostic.message only for a defect you saw; "
            "verdict=incomplete when a required check could not run to the end (a missing tool, a "
            "timeout, evidence you could not gather), naming that check in diagnostic.message. A non-empty "
            "finalFindings holds the previous verdict's findings.")
        # The milestone's own final reviewers re-run the milestone checks, so they get the worker's budget; both
        # the normal and the no-open-task ("empty_" prefix) stage do (a resumed attempt with every task done takes
        # just as long).
        review_timeout = WORKER_TIMEOUT
        retry_state = ["finalVerdict", "finalFindings"]

        def retried(node):
            # An incomplete check runs once more with the previous findings; any other verdict or an error ends the
            # loop. `attempts` retries crashes only and a timeout is an error, so neither can express this.
            name = node["name"]
            return {"kind": "loop", "name": name + "_loop", "state": state,
                    "body": seq(name + "_attempt", [node], retry_state),
                    "until": {"kind": "any", "guards": [failed(name), guard(name, "signal", FINAL_DECIDED, "verdict")]},
                    "maxIterations": FINAL_ATTEMPTS, "promotedStatePaths": [[p] for p in retry_state]}

        final_verify = retried(verifier(n("final_verify"), final_body, context + ["finalFindings"], "verdict", FINAL_VERDICTS,
                                        "finalVerdict", "finalFindings", timeout=review_timeout))
        final_reverify = retried(verifier(n("final_reverify"), final_body, final_inputs, "verdict", FINAL_VERDICTS,
                                          "finalVerdict", "finalFindings", timeout=review_timeout))
        repair = executable("step", n("repair"), (
            "Repair the milestone so that finalFindings (and scopeFindings, when nonempty) are resolved, staying inside "
            "the frozen milestone scope. " + VERIFY_RULE + " You may change no manifest field and must not edit anything "
            "under .zplan/. Do not commit, push or rewrite Git history. Return report: what changed and the commands "
            "you ran with results."),
            final_inputs, writes=[write("repairReport", n("repair"), "out", "report")], timeout=WORKER_TIMEOUT)
        scope = verifier(n("scope_verify"), read_only + (
            "Check that the last repair (repairReport and the workspace diff) stayed inside the frozen milestone scope: "
            "the validation command passes, nothing under .zplan/ changed, and every change serves a frozen requirement "
            "or check. verdict=accepted or rejected with findings in diagnostic.message."),
            context + ["finalFindings", "repairReport"], "verdict", ["accepted", "rejected"], "scopeVerdict", "scopeFindings")
        repair_loop = {"kind": "loop", "name": n("repair_loop"), "state": state,
                       "body": seq(n("repair_iteration"), [repair, guarded(n("repair"), seq(n("verify_stage"), [
                           scope, guarded(n("scope_verify"), final_reverify, FINAL_STATE)], FINAL_STATE), FINAL_STATE)],
                           FINAL_STATE),
                       "until": {"kind": "any", "guards": [failed(n("final_reverify")),
                                                           guard(n("final_reverify"), "signal", FINAL_INCOMPLETE, "verdict"),
                                                           {"kind": "all", "guards": [
                           guard(n("scope_verify"), "signal", ["accepted"], "verdict"),
                           guard(n("final_reverify"), "signal", ["accepted"], "verdict")]}]},
                       "maxIterations": FINAL_REPAIRS, "promotedStatePaths": [[p] for p in FINAL_STATE]}
        repair_result = choice(n("final_repair_result"), [
            (failed(n("final_reverify")), fail(n("final_reverify_failed"))),
            (guard(n("final_reverify"), "signal", FINAL_INCOMPLETE, "verdict"),
             success(n("reverify_incomplete"), "blockedSignal", [("message", "finalFindings")])),
            (guard(n("repair_loop"), "group", ["converged"], "terminated"),
             success(n("repaired"), "doneSignal", [("message", "finalFindings")])),
        ], success(n("final_exhausted"), "blockedSignal", [("message", "finalFindings")]))
        final_route = choice(n("final_result"), [
            (failed(n("final_verify")), fail(n("final_verify_failed"))),
            (guard(n("final_verify"), "signal", ["accepted"], "verdict"),
             success(n("done"), "doneSignal", [("message", "finalFindings")])),
            (guard(n("final_verify"), "signal", FINAL_INCOMPLETE, "verdict"),
             success(n("final_incomplete"), "blockedSignal", [("message", "finalFindings")])),
        ], seq(n("final_repair"), [repair_loop, repair_result]))
        return seq(n("final_stage"), [final_verify, final_route])
    preflight = verifier("preflight", read_only + (
        "Preflight before any work: judge the brief of every task with status open in the manifest (brief in the task "
        "and in input.baseline) and signal preflight=conflict only for an evidenced defect that needs a brief change; "
        "otherwise preflight=ready. A conflict is exactly one of: (F1) a criterion needs an edit outside the task's "
        "write_set, or evidence that is unavailable (reading a file outside the write_set is fine); (F2) two criteria, "
        "or a criterion and a non_goal, contradict each other, or an example breaks its own criterion; (F4) a criterion "
        "over an open domain has no case list. A task without a brief, a style remark, or a missing tool or command is "
        "never a conflict. diagnostic.message on conflict: the task id, the criterion and the incompatible "
        "requirements; on ready one line."),
        context, "preflight", ["ready", "conflict"], writes=[])
    select_init = verifier("select_init", read_only + (
        "Run the validation command. Signal queue=invalid when it fails or cannot run (missing checker, unreadable or "
        "corrupt manifest); otherwise queue=open when the manifest lists at least one task with status open, "
        "queue=empty otherwise. diagnostic.message: one line with the open task ids or the validation error."),
        context, "queue", ["open", "empty", "invalid"], writes=[])
    # Read-only (a verifier carries no dependency-install guidance). A failed selection never reaches a writer: select returns no error text and the
    # read-only select_verify gate routes anything but a verified contract to a failure.
    select = executable("verifier", "select", (
        "Run exactly: %s select %s --baseline %s --before %s\nIt validates the manifest, writes the snapshot %s and prints "
        "the first open task contract as JSON. Return that stdout unchanged as task. You may change no manifest field "
        "and no other file. If the command fails or cannot run, return the empty string as task (never error text)."
        % (tool, MANIFEST, BASELINE, BEFORE, BEFORE)),
        context, output="task", writes=[write("task", "select", "out", "task")], signals={},
        diagnostic=record("message"))
    select_verify = verifier("select_verify", read_only + (
        "Run exactly: %s check %s --baseline %s --before %s\nSignal selection=selected only when it exits 0 and input.task "
        "is the JSON task contract of the first task with status open in the manifest; otherwise selection=invalid "
        "(failed or missing command, empty or non-contract task). diagnostic.message: one line with the selected task "
        "id or the error." % (tool, MANIFEST, BASELINE, BEFORE)),
        context + ["task"], "selection", ["selected", "invalid"], writes=[])
    worker = executable("step", "worker", (
        "Implement input.task (a task contract JSON) in the workspace, smallest coherent change in the project's style. "
        + VERIFY_RULE + " When acceptanceVerdict or codeVerdict is rejected, their findings describe that rejected review: "
        "repair those findings. Findings marked `note:` are non-blocking and may be left as they are. You may change no "
        "manifest field and must not edit anything under .zplan/. Do not commit, push or rewrite Git history. Return "
        "report: what changed and the commands you ran with results."),
        context + ["task", "acceptanceVerdict", "acceptanceFindings", "codeVerdict", "codeFindings"],
        writes=[write("workerReport", "worker", "out", "report")], timeout=WORKER_TIMEOUT)
    acceptance = verifier("acceptance_review", read_only + (
        "Fresh acceptance review of input.task. Gather fresh evidence yourself (run the checks); do not trust "
        "workerReport. " + REVIEW_BAR + " On rejection diagnostic.message names the failing check or title and how to "
        "reproduce it; when the review accepts, it carries the notes, each prefixed `note:`. " + CONFLICT_BAR),
        context + ["task", "workerReport"], "verdict", ["accepted", "rejected", "conflict"], "acceptanceVerdict",
        "acceptanceFindings", timeout=WORKER_TIMEOUT)
    code = verifier("code_review", read_only + (
        "Fresh code review of the workspace changes for input.task. " + REVIEW_BAR + " On rejection diagnostic.message "
        "names the failing check or the broken existing behaviour and how to reproduce it (file:line); when the review "
        "accepts, it carries any other remark (style, tests, scope) as a note prefixed `note:`. " + CONFLICT_BAR),
        context + ["task", "workerReport"], "verdict", ["accepted", "rejected", "conflict"], "codeVerdict",
        "codeFindings", timeout=WORKER_TIMEOUT)
    reviews = {"kind": "par", "name": "reviews", "state": state, "branches": [acceptance, code], "join": {"kind": "all"},
               "promotedStatePaths": [[p] for p in TASK_STATE[1:]]}
    review_loop = {"kind": "loop", "name": "review_loop", "state": state,
                   "body": seq("review_iteration", [worker, guarded("worker", reviews, TASK_STATE[1:])], TASK_STATE),
                   "until": {"kind": "any", "guards": [failed("acceptance_review"), failed("code_review"),
                                                       guard("acceptance_review", "signal", ["conflict"], "verdict"),
                                                       guard("code_review", "signal", ["conflict"], "verdict"),
                                                       {"kind": "all", "guards": [
                       guard("acceptance_review", "signal", ["accepted"], "verdict"),
                       guard("code_review", "signal", ["accepted"], "verdict")]}]},
                   "maxIterations": rounds, "promotedStatePaths": [[p] for p in TASK_STATE]}
    steward_apply = executable("step", "steward_apply", (
        "Record the result of input.task in the manifest. You may change only: tasks[].status, tasks[].notes, "
        "tasks[].title (with a reword amendment), the order of tasks (with a reorder amendment), appended tasks "
        "(origin=amendment, fresh id, with an add or split amendment; split children carry parent), appended amendments "
        "{seq,kind,tasks,parents,reason} and appended progress {seq,task,phase,text}. Never change plan_revision, "
        "milestone, baseline, outcome, existing amendments or progress, or any product file. Only input.task may be "
        "marked done (never another task). Mark the task done only "
        "when acceptanceVerdict and codeVerdict are both accepted; then append progress phase=accepted as the last "
        "record of that task. Otherwise the review loop is exhausted: never mark it done; record the findings in notes "
        "and progress and, if useful, amend scope (split/add/reword/reorder/drop). Ids are never reused; at most %s "
        "tasks may ever be added. Run the validation command before returning. Return report: the changes made."
        % MAX_ADDITIONS),
        context + ["task", "workerReport", "acceptanceVerdict", "acceptanceFindings", "codeVerdict", "codeFindings"],
        writes=[write("stewardReport", "steward_apply", "out", "report")])
    steward_decide = verifier("steward_decide", read_only + (
        "Run: %s check %s --baseline %s --before %s\nDecide signal: continue when the check passes and an open task "
        "remains; done when the check passes and no task is open; needs_owner when the check rejects a scope change "
        "(frozen baseline edit, id reuse, more than %s additions, unrecorded amendment) or a decision only the owner can "
        "make: put the rejected change in diagnostic.proposal and the owner question in diagnostic.question; blocked "
        "when no progress is possible (for example a task exhausted its reviews without a viable amendment, or input.task "
        "was marked done although acceptanceVerdict or codeVerdict is not accepted). diagnostic.message: one line "
        "reason; question and proposal are empty strings unless needs_owner." % (tool, MANIFEST, BASELINE, BEFORE, MAX_ADDITIONS)),
        context + ["task", "stewardReport", "acceptanceVerdict", "codeVerdict"],
        "signal", ["continue", "done", "needs_owner", "blocked"], diagnostic=DECISION_STATE,
        writes=[write(n, "steward_decide", "diagnostic", n) for n in DECISION_STATE])
    review_route = choice("review_result", [
        (failed("acceptance_review"), fail("acceptance_review_failed")),
        (failed("code_review"), fail("code_review_failed")),
        ({"kind": "any", "guards": [guard("acceptance_review", "signal", ["conflict"], "verdict"),
                                    guard("code_review", "signal", ["conflict"], "verdict")]}, fail("review_conflict")),
    ], steward_apply, STEWARD_STATE)
    # steward_decide is a direct child of the iteration: its writes are definite. Writes nested
    # under several error choices carry presence predicates that, with the nested final stage,
    # exceed the pinned 65536 assignment ceiling (graph_verifier/analyzer_parallel.rs:9). A
    # steward_apply error therefore costs one read-only steward_decide call before task_result fails.
    review_stage = seq("review_stage", [review_loop, review_route], STEWARD_STATE)
    selection_route = choice("select_verify_result", [
        (failed("select_verify"), fail("select_verify_failed")),
        (guard("select_verify", "signal", ["invalid"], "selection"), fail("selection_invalid")),
    ], review_stage, STEWARD_STATE)
    selection_stage = seq("selection_stage", [select_verify, selection_route], STEWARD_STATE)
    iteration = seq("task_iteration", [select, guarded("select", selection_stage, STEWARD_STATE), steward_decide],
                    DECISION_STATE)
    task_loop = {"kind": "loop", "name": "task_loop", "state": state, "body": iteration,
                 "until": {"kind": "any", "guards": [failed("steward_apply"), failed("steward_decide"),
                                                     guard("steward_decide", "signal", ["done", "needs_owner", "blocked"], "signal")]},
                 "maxIterations": outer_iterations(initial_tasks), "promotedStatePaths": [[p] for p in DECISION_STATE]}
    decision = choice("task_result", [
        (failed("steward_apply"), fail("steward_apply_failed")),
        (failed("steward_decide"), fail("steward_decide_failed")),
        (guard("steward_decide", "signal", ["needs_owner"], "signal"),
         success("needs_owner", "needsOwnerSignal", [("message", "message"), ("question", "question"), ("proposal", "proposal")])),
        (guard("steward_decide", "signal", ["blocked"], "signal"), success("steward_blocked", "blockedSignal", [("message", "message")])),
        (guard("task_loop", "group", ["exhausted"], "terminated"), success("task_loop_exhausted", "blockedSignal", [("message", "message")])),
    ], final_stage(""))
    task_stage = seq("task_stage", [task_loop, decision])
    init_route = choice("select_init_result", [
        (failed("select_init"), fail("select_init_failed")),
        (guard("select_init", "signal", ["invalid"], "queue"), fail("select_init_invalid")),
        (guard("select_init", "signal", ["open"], "queue"), task_stage),
    ], final_stage("empty_"))
    return {"profile": "openengine.graph.full/v1", "initialInput": state,
            "policy": {"policy": "policy.native-v2@1", "default": "deny"},
            "root": seq("milestone", [preflight, choice("preflight_result", [
                (failed("preflight"), fail("preflight_failed")),
                (guard("preflight", "signal", ["conflict"], "preflight"), fail("preflight_conflict")),
            ], seq("milestone_start", [select_init, init_route]))])}


def milestone_runtime(roles):
    """Map graph nodes to worker/reviewer/steward roles; reviewers always open fresh sessions."""
    scopes = {"worker": "node_instance", "reviewer": "execution", "steward": "execution"}
    return {"harness": "codex", "provider": "openai", "size": "medium", "nodes": {
        name: {"kind": "agent", "sessionScope": scopes[role], **roles[role]} for name, role in ROLES.items()}}


def milestone_input(baseline, tool=TOOL):
    validate_baseline(baseline)
    value = {name: "" for name in STATE_FIELDS}
    value.update({name: "pending" for name in VERDICTS}, **OUTCOMES)
    value.update(schemaVersion="1", baseline=canonical(baseline), milestone=canonical({
        "plan_revision": baseline["plan_revision"], "id": baseline["milestone"]["id"], "title": baseline["milestone"]["title"],
        "manifest": MANIFEST, "baseline": BASELINE, "validate": "%s check %s --baseline %s" % (tool, MANIFEST, BASELINE)}))
    return value


# Command line --------------------------------------------------------------

def load(path):
    return decode(Path(path).read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m terminal_planner.milestone")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "select"):
        command = commands.add_parser(name)
        command.add_argument("manifest")
        command.add_argument("--baseline", required=True)
        command.add_argument("--before", required=name == "select")
    args = parser.parse_args(argv)
    try:
        baseline, manifest = load(args.baseline), load(args.manifest)
        validate(baseline, manifest)
        if args.command == "check":
            if args.before:
                before = load(args.before)
                validate(baseline, before)
                check_amendments(baseline, before, manifest)
            print("OK: %s open, %s done, %s dropped, %s added" % tuple(
                [sum(t["status"] == s for t in manifest["tasks"]) for s in STATUSES]
                + [sum(t["origin"] == "amendment" for t in manifest["tasks"])]))
            return 0
        contract = next_task(baseline, manifest)
        Path(args.before).write_text(canonical(manifest) + "\n")
        print(canonical(contract))
        return 0
    except (Blocked, OSError, KeyError, TypeError, ValueError) as error:
        print("INVALID: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
