# r6 — three whole-suite regressions on main: results seeding, a stale stub, a test git call

A whole-suite run on main (588221a, 2026-10-30) fails three modules the per-merge gates did not run; each was
bisected or reproduced:
1. tests/test_parallel_home.py ObserveIdentityTests (2 failures, "the slice's verdict never came back"): broken by
   v2c (98d7804). The worker seeds results at the session open from `app.authority.directory / RESULTS_FILE`
   (tui/controller.py, after `open_session`); an app without that attribute (the test's fake session, any session
   whose authority cannot name a directory) raises there and the worker never answers. v2c's own rule: results
   are never in the way.
2. tests/test_feed_wiring.py WakeTests.test_c1b_c1 (TypeError): its `_run_tool` stub takes
   `(app, tool, args, planning=None)` while the Controller now passes the request id and the turn binding (v2a,
   v6a).
3. tests/test_merge_cleanup.py (2 errors): the test helper runs `git add -A -- ':!.zplan'`; since u9a writes
   `/.zplan/` to info/exclude, git refuses the explicitly named ignored path ("The following paths are ignored",
   exit 1). Reproduced in a fresh repository.

Change:
- Seeding results at the session open never fails the open: any error while naming or reading the file leaves no
  results (as an unreadable file does today) and the session works.
- The feed-wiring stub accepts the Controller's current `_run_tool` arguments.
- The merge-cleanup helper stages with `git add -A` (the exclude already keeps .zplan out).

Write-set: terminal_planner/tui/controller.py, tests/test_feed_wiring.py, tests/test_merge_cleanup.py,
tests/test_bridge.py

Acceptance criteria:
- A1 Seeding is never in the way. Example: a session whose authority has no `directory` -> the worker answers
  every slice and `results` is [].
- A2 The three modules pass. Example: test_parallel_home, test_feed_wiring and test_merge_cleanup exit 0 without
  changing what they assert.

Non-goals (reviewers must not require): other modules, a new results design, git behaviour in production.

Conflict rule: if a fix needs a file outside the write-set, change nothing in it and end with `conflict: <file:line>`.

Risk: low (test repair, one guard). DoD: `python3.13 devtools/fasttest.py tests.test_parallel_home
tests.test_feed_wiring tests.test_merge_cleanup tests.test_bridge`: exit 0.
