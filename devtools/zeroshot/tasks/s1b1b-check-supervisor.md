Superseded by s1b1b1/s1b1b2 after the round-9 stop (critic s1b1b-stop, gate17).

s1b1b-check-supervisor — 0.5 item S1b, prerequisite slice between s1b1 and s1b2a of devtools/zeroshot/tasks/s1b-checks.md (the parent; its R-2 "the checkout is removed in every outcome" and R-3 "a restart reports прервана, never pass" apply). Origin: critic gate11 A (~/zs-pause/critic/gate11.out:3-5): the s1b1 executor cleans up only in `finally`, so a SIGKILL of zplan leaves the check group running and the checkout on disk. Revised by gate12 (~/zs-pause/critic/gate12.out:4-6) and gate13 (~/zs-pause/critic/gate13.out): the guard lives outside the group it kills, so it survives the kill, reaps, cleans up and reports; cleanup rights come only from a checkout lease. DeepSeek worker, sol reviewers.

Base: main after the s1b1-check-executor merge. Lines below are cited at the s1b1 candidate commit 00e5184 (worktree /tmp/zs-zplan/s1b1-check-executor, terminal_planner/checks.py, 226 lines). Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.

Order: s1b1 → s1b1b (this: the guard, the lease, the lock, `sweep`) → s1b1c-git-bound.md (git calls under this guard with a deadline) → s1b2a (records) → s1b2b (UI). No production wiring of qualification before s1b1b and s1b1c are merged (gate13).

Write-set (exclusive for this slice):
- terminal_planner/checks.py: `checkout` (lease + lock), `run_check` (spawn via the guard), `_read` (the parent's status from the lifeline), `_reap`, and a new `sweep(root)`;
- new `terminal_planner/check_guard.py`: a stdlib-only guard script, run by absolute path;
- tests/test_checks.py: the new tests, plus only the existing assertions that inspect the spawned argv or the `popen` spy (listed in the receipt; their oracles are unchanged);
- the receipt `devtools/zeroshot/tasks/s1b1b-check-supervisor-receipt.md`.

Not touched: every other file; `_git` and `_prepare` (s1b1c). No Authority, store, catalog, CLI, TUI or doc change; nothing outside checks.py imports the guard.

Audit (s1b1 candidate 00e5184; main 28c2c29 for the rest):
- Public API kept: `checkout(project, commit, tree, root)` context manager :29-46, `run_check(check, cwd, env, popen=..., clock=...)` :49-64, `run_checks` :67, `qualify` :84.
- Spawn: `popen(argv, ..., start_new_session=True)` :55-57; spawn failure = `OSError` :58-59. Cleanup only in-process: `checkout` `finally` :45-46; `_reap` :201-214 from the `finally` at :62-63. A SIGKILL runs neither.
- Direct calls on a project cwd: candidate tests/test_checks.py:91 and :130 call `run_check(check, self.project, ...)`; the project must never be deleted by anything in this slice.
- Checkout lifetime: `mkdtemp(prefix=PREFIX, dir=root)` :41 (`PREFIX` :25); `_git` :115-118 (zplan-side timer, s1b1c).
- Status: `_read` :143-198 (the parent's exit via `process.poll()`, grace :152-153, `GRACE` :21).
- Patterns (rg over terminal_planner/ for lifeline, PDEATHSIG, prctl, `os.pipe(`, `pass_fds`, `getppid`, `os.fork`): none. Helper-process precedent runs.py:348-352 (`[sys.executable, "-I", "-c", code]`). Lock precedent authority.py:374-389 (`flock(LOCK_EX | LOCK_NB)`).

Mechanism:
- M-1 Two groups. `run_check` spawns the guard `[sys.executable, "-I", <absolute path of check_guard.py>, *options, "--", *argv]` with `start_new_session=True` (group G, the guard alone), today's cwd/env/stdout/stderr, and `pass_fds` = (the guard's lifeline end, plus the lock fd when there is a lease). The guard spawns the check with `start_new_session=True` (group C, leader = the check pid), stdin DEVNULL, stdout/stderr inherited (the pipe zplan reads), the lock fd inherited when there is a lease. Right after the spawn the guard points its own fds 1 and 2 at /dev/null, so EOF on the pipe still means "group C closed it". Killing group C never kills the guard.
- M-2 Lifeline protocol (a `socket.socketpair()` per guard; zplan's end non-inheritable):
  - guard → zplan: `S <check pid>\n` after the spawn (the pid is C's pgid); `F\n` after an `OSError` (zplan reports `spawn_failed` with an empty tail, as today); `X <status>\n` when the check exits (`-N` for a signal) or `X timeout\n` when a `--deadline` fired (M-4).
  - zplan → guard: `D\n` ("done, normal end") before zplan closes its end in `_reap`.
  - Before spawning, the guard checks the lifeline: EOF → spawn nothing, R-2 cleanup.
  - A send error (`BrokenPipeError`, `ConnectionResetError`, other `OSError`) or EOF without a preceding `D`, at any step, means zplan is gone → R-2.
- M-3 zplan side: `_read` takes the parent's exit from `X` instead of `process.poll()`; grace, window and "timeout" unchanged. `_reap` sends `SIGKILL` to group C (from `S`), sends `D`, closes its end and reaps the guard. After `D`+EOF the guard kills group C (a no-op if gone), waits for it to be gone, and exits without touching the filesystem.
- M-4 Optional `--deadline <s>`: at the deadline the guard kills group C, waits for it to be gone, then sends `X timeout`. The guard is alive, so the message is always sendable. `run_check` passes `timeout_s + GRACE + 5` as a backstop (zplan's own timer normally fires first); s1b1c passes `export.TIMEOUT` for git.
- M-5 Lease. `checkout` creates `root/checkout-<random>.lock` (mode 0600), takes `flock(LOCK_EX)`, creates the directory with the same stem, and records the lease (resolved directory path → lock fd) in a module-level map for the lifetime of the context manager. `run_check` looks up its resolved `cwd`: a match passes `--lease <dir>` and the lock fd to the guard; no match (any direct call, e.g. on a project) passes neither. The guard deletes only a `--lease` directory, and only if its name starts with `PREFIX` and its sibling lock file exists. Normal exit of `checkout`: remove the directory, the lock file, drop the lease.

Rules:
- R-1 Unchanged contract: `checkout`, `run_check`, `run_checks`, `qualify` keep the s1b1 signatures, return shapes, refusal values, fail-fast, bounds and scrub. Every existing s1b1 test oracle stays (the direct project-cwd calls included); only spawn-argv/spy assertions may change.
- R-2 Death of zplan while the guard lives (before `S`, during the check, or after the check exited with descendants alive): the guard kills group C (SIGKILL), waits until `os.killpg(C, 0)` raises `ProcessLookupError` (bounded 10 s), then, only with a lease, removes the directory (the s1b1 `_remove` logic, copied: the guard imports nothing from the package) and the lock file, and exits. Without a lease it removes nothing. No fork, no second process.
- R-3 Between processes (no guard alive: zplan dies between checks or during a git call before s1b1c; power loss or a kernel crash; the guard itself killed by a direct signal): no immediate cleanup. The directory and lock stay until `sweep`; an orphaned process of group C that still holds the inherited lock fd makes `sweep` report busy. Direct guard termination is outside the cleanup guarantee of 0.5; lock contention detects surviving fd holders, not group liveness, so `busy` is not guaranteed after a guard death and no safe automatic recovery of that case is promised (critic gate14; record it in the receipt and STATE Open).
- R-4 `sweep(root)` → `{"removed": int, "busy": int}`: for each `checkout-*` entry, `flock(LOCK_EX | LOCK_NB)` on its lock succeeds → remove the directory and the lock; fails → busy, left in place. A directory without a lock file is removed. A missing root → zeros. Never raises on filesystem errors (counts busy). `sweep` only touches `checkout-*` entries under `root`.
- R-5 Rerun gate for callers: a new qualification may start only after `sweep(root)` returns `busy == 0` (s1b2a R-2 step 1).
- R-6 Containment limit: a check process that leaves group C itself (`setsid`, daemonizing) is not contained, as in s1b1; stated in the receipt, not tested.
- R-7 No new user text, no family-bearing raise; programming errors raise ValueError as in s1b1. Fixtures: every literal home path in tests is under `/home/user/`.

Seams: the guard is importable (`check_guard.main(...)`); tests that need a fixed interleaving run it as `[sys.executable, "-c", "import check_guard as g; g.after_spawn = ...; g.main()"]` and replace the module-level no-op hook `after_spawn`. No environment variable and no production flag.

Acceptance (tests/test_checks.py; temp git repos; checks run `sys.executable -c ...`; the controlling zplan is a separate `sys.executable` child that calls `checks.qualify` or `run_check`, so the test can SIGKILL it; no network; each wait bounded at 3 s):
- A-H Hard kill, handshake (gate11:5, gate12:5; a SystemExit stub does not count). Common oracle within 3 s of the kill: group C is gone (`killpg(C, 0)` → `ProcessLookupError`), the guard pid is gone, every recorded pid is gone, the checkout directory and lock are gone, 2.5 s later the side-effect file is unchanged, `sweep(root)` returns zeros.
  - H-1 Check running: the check starts a descendant (sleeps 2 s, then appends to the side-effect file), writes both pids to a handshake file, sleeps; SIGKILL the controller after the handshake.
  - H-2 Check exited, descendant alive: the check starts the descendant and exits 0; the descendant keeps stdout open, waits until the parent pid is gone, writes the handshake; SIGKILL the controller during the grace.
  - H-3 Death before `S`: the `after_spawn` hook blocks until the test has SIGKILLed the controller; the `S` send fails; oracle as above.
  - H-3b Death before the guard reads the lifeline: the peer is closed first → no check spawned (its side-effect absent), directory and lock removed.
  - Control: the H-1 check without the kill completes with status 0 and the normal cleanup.
- A-L Lease: a controller calls `run_check` directly on a project directory (as candidate tests :91/:130) and is SIGKILLed mid-check → group C gone, the project directory and every file in it still present. Control: the same under `checkout` → the checkout removed.
- A-D Deadline: the guard run directly with `--deadline 1`, a lifeline the test keeps open, and a check that ignores SIGTERM and never exits → within 3 s group C is gone and the test reads `X timeout`; the guard then exits only after `D`.
- A-S Sweep: an unheld leftover → removed; lock held by a live helper → busy, then removed after it exits; a directory without a lock → removed; missing root → zeros; a power-loss leftover (files only) → removed; a non-`checkout-*` entry under root → untouched.
- A-G Guard transparency: exit 0/3, SIGTERM death (negative status as before), stderr-only output, the 50 MB bound, the descendant grace, `"a; touch pwned"` literal argv, the environment keys (the guard adds none): the s1b1 tests pass through the guard.
- A-F Spawn failure: a missing executable → `spawn_failed`, empty tail, `duration_s` from the injected clock; no guard left alive.
- A-7 Base failure: H-1 on base (s1b1 merged) fails by a named assertion (the descendant alive or the checkout present after 3 s). Run on base with a scratch commit; report named failures and skips separately.
- Mutations, each killed by a named test:
  - (a) the guard ignores lifeline EOF (H-1);
  - (b) the guard exits after `X` (H-2: the descendant survives);
  - (c) the check spawned in the guard's group (A-D: `X timeout` never arrives, the guard died with the group);
  - (d) a failed `S` send ignored (H-3);
  - (e) the guard removes `cwd` without a lease (A-L: the project is deleted);
  - (f) the lease looked up by name prefix instead of the registered path (A-L with a project directory named `checkout-x`);
  - (g) the lock fd not passed with the lease (sweep removes under a running check);
  - (h) `sweep` ignores a held lock;
  - (i) `F` reported as an exit status;
  - (j) EOF after `D` treated as a death (the checkout is removed between two checks of one `qualify`).

Size: estimated 450-580 changed lines, receipt excluded: check_guard.py ~100, checks.py ~90 (spawn via guard and lifeline ~25, `_read`/`_reap` ~15, lease and lock ~20, `sweep` ~30), tests ~260-390. Git calls are s1b1c. Above 600, stop and report.

Parallelism: checks.py, the new guard and test_checks.py only; parallel with s1a1b2, s1a1c1/c2, s2b2, s2b3. s1b1c and s1b2a wait for it.

Out of scope: git calls (s1b1c); records, the marker, display (s1b2a); cancelling a qualification from the UI (parked after this boundary, gate11 point 2); flake reruns (s1b3).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_checks tests.test_live tests.test_process tests.test_toolchain tests.test_reference` passes locally (Python ≥3.11).
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, the A-7 counts (named failures and skips separately), the mutation table, the edited existing assertions, R-6.
- Orchestrator, before merge: `tests.test_checks` on the Linux test host (A-H under Linux process semantics), then the full suite.
