#!/usr/bin/env python3
"""Wake the architect when a background process ends: the slice monitor's wake path, reused for probes.

    python3.13 devtools/wake_on.py RUN_DIR --pid PID --reason "R1 report ready" [--every 10]

Writes into RUN_DIR (a probe run under .local/slices) a run_start, then waits for PID to exit and writes one wake
with REASON and a run_end. The slice monitor prompts the architect's pane on that wake, as it does for a slice run;
`slice_run.py ack RUN_DIR` acknowledges it. Several wakers may share one probe run: each adds its own wake.
"""
import argparse
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import slice_run as sr  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--every", type=float, default=10)
    args = ap.parse_args(argv)
    path = pathlib.Path(args.run_dir)
    path.mkdir(parents=True, exist_ok=True)
    toml = path / "run.toml"
    if not toml.exists():
        toml.write_text('run = "%s"\nrepo = "%s"\nqueue = []\n' % (path.name, pathlib.Path.cwd()))
    run = sr.Run(path)
    run.event("run_start", pid=os.getpid())
    while sr.pid_alive(args.pid):
        run.beat()
        time.sleep(args.every)
    sr.wake(run, args.reason)
    run.event("run_end", reason=args.reason, code=0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
