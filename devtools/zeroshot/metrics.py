#!/usr/bin/env python3
"""Process metrics for the orchestrator review (ORCHESTRATOR.md, Process metrics).

Devtools only: reads git, the local Zeroshot run stores and ~/zs-pause/critic read-only; writes nothing.
Usage: python3 devtools/zeroshot/metrics.py --since 2026-10-18 [--until 2026-10-27]
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import statistics
import subprocess
from pathlib import Path

RUNS = Path(os.environ.get("ZS_RUNS", "~/.local/state/zeroshot/runs")).expanduser()
CRITIC = Path("~/zs-pause/critic").expanduser()
# A finding is "tests/evidence" when it cites tests, receipts, mutation or evidence bookkeeping and no product path only.
EVIDENCE = re.compile(r"test|receipt|mutation|evidence|assert|fixture|\ba-\d", re.I)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def lines_added(since, until):
    base = git("rev-list", "-1", "--before=%s 00:00" % since, "HEAD").strip()
    head = git("rev-list", "-1", "--before=%s 00:00" % until, "HEAD").strip() if until else "HEAD"
    out = {}
    for path in ("terminal_planner", "tests", "devtools"):
        add = sum(int(l.split("\t")[0]) for l in git("diff", "--numstat", base, head, "--", path).splitlines()
                  if l.split("\t")[0].isdigit())
        out[path] = add
    return out


def critic_calls(lo, hi):
    days = collections.Counter()
    for f in CRITIC.glob("*.out"):
        t = f.stat().st_mtime
        if lo <= t < hi:
            days[dt.date.fromtimestamp(t).isoformat()] += 1
    return days


def runs(lo, hi):
    by_slice = collections.defaultdict(lambda: {"runs": 0, "rounds": 0, "hours": 0.0, "status": []})
    findings = collections.Counter()
    for db in glob.glob(str(RUNS / "*" / "runs.sqlite3")):
        try:
            con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
            snap = json.loads(con.execute("select stored_json from v2_runs").fetchone()[0])["snapshot"]
            stamps = [json.loads(e).get("timestamp") for (e,) in con.execute("select event_json from v2_run_events")]
        except (sqlite3.Error, ValueError, KeyError, TypeError):
            continue
        stamps = [s / 1000 for s in stamps if s]
        title = snap.get("title", "")
        if not stamps or not title.startswith("zplan ") or not lo <= min(stamps) < hi:
            continue
        s = by_slice[title[len("zplan "):]]
        s["runs"] += 1
        s["hours"] += (max(stamps) - min(stamps)) / 3600
        execs = snap.get("executions", {}).values()
        s["rounds"] += sum(1 for e in execs if e["occurrence"]["node"] == "worker")
        term = snap.get("terminal")
        s["status"].append((term or {}).get("status", "?") if isinstance(term, dict) else ("running" if term is None else str(term)[:20]))
        for e in execs:
            for key in ("acceptanceFeedback", "codeFeedback"):
                text = (e.get("input") or {}).get(key) or ""
                for item in (re.split(r"\n\s*\d+\.\s", text)[1:] or ([text] if text else [])):
                    head = item[:400]
                    product_only = "terminal_planner/" in head and not re.search(r"tests/|receipt", head)
                    findings["tests/evidence" if EVIDENCE.search(head) and not product_only else "product"] += 1
    return by_slice, findings


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", required=True)
    ap.add_argument("--until")
    a = ap.parse_args()
    lo = dt.datetime.fromisoformat(a.since).timestamp()
    hi = dt.datetime.fromisoformat(a.until).timestamp() if a.until else float("inf")
    print("window: %s .. %s" % (a.since, a.until or "now"))
    print("added lines:", lines_added(a.since, a.until))
    days = critic_calls(lo, hi)
    print("critic calls: %d total, by day %s" % (sum(days.values()), dict(sorted(days.items()))))
    slices, findings = runs(lo, hi)
    print("slice | runs | worker rounds | run hours | statuses")
    for name, s in sorted(slices.items()):
        print("%s | %d | %d | %.1f | %s" % (name, s["runs"], s["rounds"], s["hours"], ",".join(s["status"])))
    if slices:
        print("median run hours per slice: %.1f; median worker rounds: %s" % (
            statistics.median(s["hours"] for s in slices.values()),
            statistics.median(s["rounds"] for s in slices.values())))
    total = sum(findings.values()) or 1
    print("reviewer findings: %s; tests/evidence share %.0f%%" % (dict(findings), 100 * findings["tests/evidence"] / total))


if __name__ == "__main__":
    main()
