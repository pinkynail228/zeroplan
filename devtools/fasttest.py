#!/usr/bin/env python3
"""Run unittest modules in parallel, one process and one short TMPDIR per module.

Usage: python3 devtools/fasttest.py [-j N] [--durations K] [MODULE ...]
  MODULE: tests.test_x (default: every tests/test_*.py); each module runs as one process per top-level test class,
  so a big module does not set the wall time. Exit 0 only when every part passed.
  --durations K: print the K slowest tests across all modules.
Same environment as devtools/mac-test.sh (PYTHONPATH=.:tests, wheelhouse, python3.13), but no clean-tree check:
the merge-gate evidence stays mac-test.sh / linux-test.sh; this is the fast loop for workers and the orchestrator.
"""
import argparse
import json
import re
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

# The checkout under test is the current directory's (a worktree may run the main checkout's runner).
REPO = pathlib.Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
                    or pathlib.Path(__file__).resolve().parent.parent)


def run_one(module, out_json):
    """Child mode: run one module, record per-test durations to out_json."""
    times = []

    class Timed(unittest.TextTestResult):
        def startTest(self, test):
            self._t0 = time.monotonic()
            super().startTest(test)

        def stopTest(self, test):
            times.append((time.monotonic() - self._t0, test.id()))
            super().stopTest(test)

    name, _, attr = module.rpartition(".")
    if name.count(".") >= 1:  # tests.test_x.Class: skip helper classes that are not test cases
        import importlib
        obj = getattr(importlib.import_module(name), attr, None)
        if not (isinstance(obj, type) and issubclass(obj, unittest.TestCase)):
            pathlib.Path(out_json).write_text(json.dumps({"tests": 0, "times": []}))
            return 0
    suite = unittest.defaultTestLoader.loadTestsFromName(module)
    result = unittest.TextTestRunner(resultclass=Timed, verbosity=1).run(suite)
    pathlib.Path(out_json).write_text(json.dumps({
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "times": times}))
    return 0 if result.wasSuccessful() else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        sys.exit(run_one(sys.argv[2], sys.argv[3]))
    ap = argparse.ArgumentParser()
    # Default -j takes only the idle cores: parallel runs on one Mac each ran -j 10 at load 25-39 (2026-10-24),
    # timing tests flaked and a 2-minute DoD took 54 minutes.
    cpus = os.cpu_count() or 2
    ap.add_argument("-j", type=int, default=max(2, min(cpus - 2, cpus - int(os.getloadavg()[0]))))
    ap.add_argument("--durations", type=int, default=0)
    ap.add_argument("modules", nargs="*")
    args = ap.parse_args()
    modules = args.modules or sorted("tests." + p.stem for p in (REPO / "tests").glob("test_*.py"))
    py = os.environ.get("ZPLAN_MAC_PYTHON", "python3.13")
    wheels = os.environ.get("ZPLAN_TEST_WHEELHOUSE", os.path.expanduser("~/.cache/zplan-wheelhouse"))
    if not list(pathlib.Path(wheels).glob("textual-*.whl")):
        sys.exit("fasttest: no textual wheel in %s; set ZPLAN_TEST_WHEELHOUSE" % wheels)
    logs = pathlib.Path(tempfile.mkdtemp(prefix="zs-ft-", dir="/tmp"))
    units = []
    for module in modules:
        path = REPO / (module.replace(".", "/") + ".py")
        classes = re.findall(r"^class (\w+)\(", path.read_text(), re.M) if path.exists() else []
        units += [module + "." + c for c in classes] or [module]

    def job(module):
        tmp = tempfile.mkdtemp(prefix="zs-", dir="/tmp")  # short: macOS socket paths < 104 bytes
        env = dict(os.environ, TMPDIR=tmp, PYTHONPATH=".:tests", ZPLAN_TEST_WHEELHOUSE=wheels)
        out = logs / (module + ".json")
        t0 = time.monotonic()
        with open(logs / (module + ".log"), "w") as log:
            rc = subprocess.call([py, __file__, "--child", module, str(out)], cwd=REPO, env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
        shutil.rmtree(tmp, ignore_errors=True)
        data = json.loads(out.read_text()) if out.exists() else {"tests": 0, "times": []}
        return module, rc, time.monotonic() - t0, data

    t0 = time.monotonic()
    # Longest-known modules first would be better; alphabetical keeps output stable.
    with ThreadPoolExecutor(args.j) as pool:
        results = list(pool.map(job, units))
    wall = time.monotonic() - t0
    failed = [r for r in results if r[1] != 0]
    for module, rc, secs, data in sorted(results, key=lambda r: -r[2])[:10]:
        print("%-70s %4d tests %6.1fs %s" % (module, data["tests"], secs, "ok" if rc == 0 else "FAIL rc=%d" % rc))
    if args.durations:
        times = sorted((t for r in results for t in r[3]["times"]), reverse=True)[:args.durations]
        print("slowest:")
        for secs, name in times:
            print("  %6.2fs %s" % (secs, name))
    total = sum(r[3]["tests"] for r in results)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    print("fasttest: tree %s %s" % (head, "dirty" if dirty else "clean"))
    print("fasttest: %d modules in %d parts, %d tests, wall %.0fs, -j %d, %s; logs %s" % (
        len(modules), len(results), total, wall, args.j, "FAILED %d" % len(failed) if failed else "OK", logs))
    for module, *_ in failed:
        print("--- %s (tail)" % module)
        print("\n".join((logs / (module + ".log")).read_text().splitlines()[-25:]))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
