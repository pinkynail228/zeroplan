#!/usr/bin/env python3
"""Test budget: net test lines a change adds stay within RATIO x the product lines it adds, plus SLACK.

Usage: python3 devtools/budget.py [BASE [HEAD]]   (BASE defaults to the merge base with main; without HEAD
compares BASE with the working tree). Exit 0 = within budget, 1 = over budget. Tests = tests/ and devtools/test_*.py;
product = terminal_planner/ without resources/. A change with no product lines (a test-only prune) is never
over budget when it removes more test lines than it adds.
"""
import subprocess
import sys

RATIO, SLACK = 1.5, 60


def numstat(*revs):
    out = subprocess.run(["git", "diff", "--numstat", *revs], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        added, deleted, path = line.split("\t", 2)
        if added != "-":
            yield int(added), int(deleted), path


def main(argv):
    base = argv[1] if len(argv) > 1 else subprocess.run(
        ["git", "merge-base", "HEAD", "main"], capture_output=True, text=True, check=True).stdout.strip()
    test_net = prod_added = 0
    for added, deleted, path in numstat(base, *argv[2:3]):
        if path.startswith("tests/") or path.startswith("devtools/test_"):
            test_net += added - deleted
        elif path.startswith("terminal_planner/") and "/resources/" not in path:
            prod_added += added
    limit = int(RATIO * prod_added + SLACK)
    ok = test_net <= limit
    print("test_budget: tests %+d net, product +%d, limit %d: %s" % (test_net, prod_added, limit, "OK" if ok else "OVER"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
