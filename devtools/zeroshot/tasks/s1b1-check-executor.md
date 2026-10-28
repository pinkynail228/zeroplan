s1b1-check-executor — 0.5 item S1b, slice 1 of 3 of devtools/zeroshot/tasks/s1b-checks.md (the parent; its Audit, R-* and A-* texts apply verbatim where cited). Slicing: critic swarm05 c ("Bounded check executor -> qualification records/actions -> flake diagnosis"); critic swarm05 a: the executor may start before the s1a1 record contract is fixed, record integration comes later. DeepSeek worker, sol reviewers.

Base: main c9f5164. All line numbers below are verified on it. Record the actual base commit and this brief's sha256 in the receipt. If the base moves, re-check every cited line and re-gate if a premise moved. Runs in parallel with s1a1a (devtools/zeroshot/tasks/s1a1a-gate-core.md) and s5a1; the write-sets are disjoint.

Slices:
- s1b1 (this) = a pure, bounded check executor:
  - a disposable clean checkout of one commit, with the tree verified and the checkout always removed;
  - sequential argv-only execution with timeout and process-group kill;
  - per-check evidence (parent R-2 execution and cleanup, the R-3 per-check evidence shape, A-2, A-6, the capture/bounds parts of A-6b, and the A-7 compatibility/executor mutations).
  - Nothing calls it yet.
- s1b2 = qualification records and the owner action:
  - parent R-1, the R-2 action (TUI key + CLI command, catalog), the R-3 Authority record and `uncertain` marker, R-4 validity, R-6 display;
  - A-1, A-3, A-4, A-7 (the Delivery-entry base failure);
  - catalog, REFERENCE.md, USER_FLOW.md, PROCESS_PROFILE.md.
  - Base: after the s1a1 merge; it reuses the gate-record store and calls this executor with zplan's data dir as the root.
- s1b3 = flake diagnosis (S6):
  - parent R-5 (the `flake_reruns` validation, alternating candidate/base reruns through this executor, the verdict table, stored 2N results);
  - A-5, the A-7 diagnosis mutations, and the A-6b verdict/`flake_reruns` parts (all b/c counts at N=1,4,10; absent -> 4 with no change to the stored config/digests; reject bool, 0 and 11).

Write-set (exclusive for this slice):
- new `terminal_planner/checks.py`;
- new `tests/test_checks.py`;
- the receipt `devtools/zeroshot/tasks/s1b1-check-executor-receipt.md`.

No edits to any existing file. live.py, export.py, process.py and authority.py are imported read-only. Out of bounds in particular: engine.py and authority.py (s1a1a), setup.py, commands.py, cli.py and tui/* (s5a1), runs.py, delivery.py, catalog.py, docs.

Read (c9f5164):
- Parent: s1b-checks.md, R-2 and R-3 (:26-36), A-2 (:48-51), A-6/A-6b (:55-56).
- Validated check shape `{name, argv, timeout_s}`: process.py `validate_check` :119-135, `MAX_CHECKS` :39, `DEFAULT_TIMEOUT` :41.
- Sanitized environment and git options: export.py `environment` :25-33, `OPTIONS` :21, `TIMEOUT` :18. Do not call `run_git` :35-46: its refusal says "экспорт прерван" under `git.failed`.
- Disposable clone pattern: engine.py:966 (`git clone --quiet --no-hardlinks --`). Group kill: engine.py:85 (`os.killpg` on a `start_new_session=True` child).
- Streaming capture to reuse as an algorithm (bounded window, select loop, deadline, drop of the leading partial line): live.py `stream` :259-344.
  - Differences here: `stream` reads stdout only (stderr to DEVNULL) and kills only the reader. The executor must capture stderr and kill the whole group.
- Display/scrub: live.py `_shown` :346-351 (ANSI strip + `scrub`, blank lines dropped), `scrub` :427, `HIDDEN` :406. Existing tail tests: tests/test_live.py `TailTests` :437.
- `digest` authority.py:159.
- Raise-site scan: tests/test_reference.py:103-115 and :339. A raise of a family-bearing class (`Blocked`, `Stale`, ...) must name a catalog family. This slice raises none.

Rules:
- R-1 Pure and unreached:
  - No Authority, store, record, catalog, TUI or CLI wiring.
  - No new user text and no family-bearing raise. Refusals are returned values; programming errors raise ValueError.
  - No production module imports `checks.py`. With any config (including `/1`), every existing record, digest, screen and golden stays byte-identical.
- R-2 Checkout: `checkout(project, commit, tree, root)`, a context manager. On success it yields the checkout `Path`; on refusal it yields the refusal dict below (no exception).
  - commit and tree must be 40-hex; `root` must resolve outside `project` (otherwise ValueError).
  - It creates a fresh directory under `root` (mode 0700) and clones `project` without hardlinks or checkout. It then detaches at `commit` and verifies that HEAD == commit and `HEAD^{tree}` == tree.
  - Every git call: argv only, `export.OPTIONS` (hooks off), `export.environment()`, `start_new_session=True`, `export.TIMEOUT`.
  - Any git failure, timeout or mismatch yields a refusal: `{"refused": "checkout" | "tree_mismatch"}`, and no check runs.
  - The directory is removed on every exit path: success, refusal, check failure, timeout, an exception inside the `with` body.
- R-3 Run one check: `run_check(check, cwd, env, popen=subprocess.Popen, clock=time.monotonic)`.
  - Execution:
    - `check` is a `validate_check` result; it is run as an argv list with `shell=False`, `start_new_session=True`, stdin DEVNULL, and stdout+stderr on one pipe.
    - At `timeout_s` the whole process group is killed (`os.killpg`, SIGKILL) and reaped.
  - Descendants: after the parent exits, the remaining group is killed after a short fixed grace (≤2 s). Reading stops, so a descendant holding the pipe can never extend the run past `timeout_s` + grace. The status is the parent's exit code.
  - Group kill and reap also run on KeyboardInterrupt or a read error (re-raised afterwards), always before the enclosing checkout is removed.
  - Spawn failure: an OSError from `popen` yields `spawn_failed` with an empty tail.
  - Evidence returned (exact keys):
    - `name`;
    - `argv_digest` (`digest(argv)`);
    - `status`: int exit code | `"timeout"` | `"spawn_failed"` (`run_checks` adds `"not_run"`, R-5);
    - `duration_s`: clock difference, rounded to 3 decimals;
    - `tail`.
- R-4 Bounds and scrub:
  - Memory: the streaming window holds at most 64 KiB of raw bytes whatever the output size. When bytes were dropped, the leading partial line is dropped too (live.py:340-342, the comment at :339).
  - Display: the window is passed through `live._shown`.
  - Final caps, applied after scrubbing: the last ≤200 lines, then trimmed from the front to ≤32768 UTF-8 bytes at a line boundary, never splitting a character.
  - `tail` is the lines joined with "\n". Scrubbing is exactly `live._shown` applied to the retained lines; no other secret detection is added, and live.py stays unchanged.
- R-5 Run the list: `run_checks(checks, cwd, env=None)` runs every check in profile order, sequentially, never in parallel; `env=None` means `export.environment()`.
  - Fail-fast: after the first nonzero exit, timeout or spawn failure, the remaining checks are not run; each gets `status="not_run"`, `duration_s=0`, `tail=""`, keeping its `name`, `argv_digest` and position. The outcome is then `failed`. (Flake diagnosis in s1b3 reruns the one failed check.)
  - Returns `{"checks_digest": digest(checks), "checks": [evidence...], "outcome": "passed" | "failed"}`, where `passed` iff every status == 0. A timeout or spawn failure is never `passed`.
  - `qualify(project, commit, tree, checks, root)` = `checkout` + `run_checks`. It returns either the refusal or that dict, with `commit` and `tree` added.

Acceptance (unit tests in tests/test_checks.py; deterministic fixtures in temp git repos; checks run `sys.executable -c ...`; no network, no provider, no sleep longer than 3 s per test):
- A-2 Run (parent A-2):
  - Pass, fail (exit 3), timeout (timeout_s=1) and spawn-failure (missing executable) checks each give the exact evidence dict. `duration_s` is checked with an injected clock.
  - The checkout's HEAD tree equals `tree`. A wrong `tree` gives `tree_mismatch` with no check spawned (spy `popen`). Also tested: an unknown commit, a non-hex commit, and a root inside the project.
  - The checkout directory is gone after pass, fail, timeout, refusal, and an exception raised inside the `with` body.
  - Profile order and sequence: each check appends to a file, and the order is asserted.
  - Fail-fast: with checks [pass, fail, pass] the third never spawns (spy `popen`) and its evidence is exactly `not_run` with name, argv_digest, `duration_s=0`, `tail=""`.
  - Interrupt: a check that signals readiness through a handshake file, then KeyboardInterrupt raised from the injected clock/read path: the group is dead, the child reaped, and the checkout removed after that; the interrupt propagates.
  - An argv element `"a; touch pwned"` arrives literally as one argument, and no file `pwned` exists.
- A-E Environment: a check printing `os.environ` shows only the keys of `export.environment()`; a planted `HOME`/`GIT_DIR`/`SECRET_TOKEN` in the parent env is absent.
- A-6 Scrub and bounds (parent A-6): a secret-shaped line printed by a check appears scrubbed (`HIDDEN`) in `tail`; ANSI sequences are stripped.
- A-6b Capture and caps (the parent A-6b capture part):
  - stderr-only output is captured.
  - A descendant that inherits the pipe and sleeps 30 s after the parent exits 0: the run returns in < timeout_s + 3 s with status 0, and the descendant's pid is dead afterwards.
  - A check printing 50 MB: the run completes and the retained window never exceeds 64 KiB (assert via an injected small read size/counter).
  - Line caps: tails of exactly 199/200/201 lines give 199/200/200 lines (the last ones).
  - Byte caps: outputs of 32767/32768/32769 UTF-8 bytes, including a multi-byte character straddling the cut, give ≤32768 bytes, valid UTF-8 and no partial first line. Both final caps are asserted on every case.
- A-7 Compatibility and mutations:
  - Base replay: there is no base-supported entry point (the module is new), so no test can fail on base through an existing path. State this in the receipt.
  - Compatibility: the targeted suites in DoD pass unchanged on base and candidate; the counts go in the receipt. The full Linux suite is the orchestrator's merge gate, not the worker's.
  - Every candidate-only invariant maps to a killed mutation, each caught by a named test in tests/test_checks.py:
    - (a) `shell=True` with the argv joined;
    - (b) `process.kill()` instead of `os.killpg` (the descendant survives);
    - (c) tree verification removed;
    - (d) cleanup only on success;
    - (e) line cap 201 or byte cap 32769;
    - (f) `scrub` skipped;
    - (g) stderr to DEVNULL;
    - (h) `timeout` counted as passed;
    - (i) checks run in reverse order;
    - (i2) checks continue after the first failure (fail-fast removed);
    - (l) cleanup/reap skipped on KeyboardInterrupt;
    - (j) a spawn failure reported as exit status 127;
    - (k) `env=os.environ`.
  - Record each mutation and its killing test in the receipt.

Size: about 200-450 changed lines including tests. Above 600, stop and report for a re-gate rather than absorbing s1b2/s1b3 work.

Out of scope:
- `uncertain` marker, Authority record, validity, stale, display, catalog, docs (s1b2);
- flake reruns and verdicts, `flake_reruns` (s1b3);
- merge critic and override (S1c).

DoD:
- `python3 -m unittest tests.test_checks tests.test_live tests.test_process tests.test_toolchain tests.test_reference` passes locally (Python ≥3.11).
- No existing file is changed: `git diff --stat <base>` lists only the write-set.
- Receipt: base commit, this brief's sha256, file list, compatibility counts (named failures and skips separately), the mutation table.
