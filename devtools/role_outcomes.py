#!/usr/bin/env python3
"""Role outcomes of every Zeroshot run under one state root (0.13 design, G5): what each node decided.

    python3 devtools/role_outcomes.py STATE_ROOT

STATE_ROOT is a Zeroshot state root: `<home>/.zp` for an installed zplan, `<data root>/native` for the development
data. Every `runs.sqlite3` below it is read (read-only). Output, comparable across releases:
- one line per graph and node (`plan_check.critic`, `milestone.preflight`, ...; a run's graph is told by its nodes:
  `comprehension` is the plan check, `worker` a milestone, `proposer` a task gate, anything else `other`): its counts by
  signal value (a verdict, a preflight value, the steward's signal, a selection or queue), or by completion status
  when the node has no signal;
- the plan check critic's `readiness:` findings (0.13's readiness rules), counted apart wherever they stand;
- every non-passing outcome with the first 150 characters of its message."""
import collections
import contextlib
import json
import pathlib
import re
import sqlite3
import sys

SIGNALS = ("verdict", "preflight", "signal", "selection", "queue")
NOT_PASSING = {"rejected", "conflict", "blocked", "block", "needs_owner", "incomplete",
               "timeout", "crash", "malformed", "refusal", "error"}
READINESS = re.compile(r"\breadiness:", re.I)


def outcomes(root):
    counts = collections.defaultdict(collections.Counter)
    failing, readiness, runs, unreadable = [], 0, 0, 0
    for path in sorted(pathlib.Path(root).rglob("runs.sqlite3")):
        try:
            with contextlib.closing(sqlite3.connect("file:%s?mode=ro" % path, uri=True)) as db:
                events = [json.loads(text) for (text,) in
                          db.execute("select event_json from v2_run_events where event_json like '%node_completed%'")]
            events = [e for e in events if e.get("kind") == "node_completed"]
            names = {e["completion"]["reference"]["node"] for e in events}
        except (sqlite3.Error, ValueError, KeyError, TypeError):
            unreadable += 1
            continue
        runs += 1
        graph = ("plan_check" if "comprehension" in names else "milestone" if "worker" in names
                 else "task_gate" if "proposer" in names else "other")
        for event in events:
            completion = event["completion"]
            node, outcome = graph + "." + completion["reference"]["node"], completion["outcome"]
            signals = outcome.get("signals") or {}
            value = next((signals[k] for k in SIGNALS if k in signals), outcome.get("status"))
            counts[node][value] += 1
            message = ((outcome.get("diagnostic") or {}).get("message") or "").strip()
            if node == "plan_check.critic":
                readiness += len(READINESS.findall(message))
            if value in NOT_PASSING:
                failing.append("%s %s: %s" % (node, value, " ".join(message.split())[:150]))
    return runs, counts, readiness, failing, unreadable


def main(argv):
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    runs, counts, readiness, failing, unreadable = outcomes(argv[1])
    print("Zeroshot runs: %d (unreadable: %d)" % (runs, unreadable))
    for node in sorted(counts):
        print("%-24s %s" % (node, ", ".join("%s %d" % (k, v) for k, v in sorted(counts[node].items(), key=str))))
    print("critic readiness findings: %d" % readiness)
    print("Non-passing outcomes: %d" % len(failing))
    for line in failing:
        print("- " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
