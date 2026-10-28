s1b1c-git-bound — 0.5 item S1b, second prerequisite slice; depends on s1b1b1r-check-guard.md (the guard) and s1b1b2-check-sweep.md (`sweep`), split from s1b1b-check-supervisor.md after its round-9 stop (critic s1b1b-stop, gate17); not the other way round. Origin: critic gate12 (~/zs-pause/critic/gate12.out:6): `export.TIMEOUT` lives in zplan's own `subprocess.run` (s1b1 candidate checks.py:118), so after zplan dies or stalls a hung git (clone, checkout, rev-parse) keeps the checkout lock and `sweep` reports busy forever. Revised by gate13 (~/zs-pause/critic/gate13.out): the deadline is the s1b1b1r guard's (parent M-4 owned by s1b1b1r; the guard is outside the group it kills, so `X timeout` is sendable), and the `_git` deadline is tested on the production path. DeepSeek worker, sol reviewers. Re-gate after s1b1b1r: critic regate-after-s1b1b1r GO WITH CHANGES (applied), session 01a1594a-a691-72a2-859a-8ac49e602d3f.

Order: s1b1 → s1b1b1r → s1b1b2 → s1b1c (this) → s1b2a → s1b2b.

Base: main b0ef3ea, including guard merge 13153c6 (s1b1b1r + s1b1b1r2 repair) and sweep merge 2577d06. Implementation citations below refer to this base. Record the actual base and this brief's sha256 in the receipt; re-check cited lines and re-gate if a premise changes. Premise check: critic s1b1c-premise GO WITH CHANGES (applied; session 01a15aaa-6ba9-7633-8f7d-e3b6b43704be).
- Consumes the guard as written in s1b1b1r-check-guard.md, as amended by s1b1b1r2-env-spawn-repair.md (parent s1b1b-check-supervisor.md M-1..M-5, R-2, R-3, plus s1b1b1r R-C/R-F, descriptor ownership and interrupted-call limits R-D/R-X, lease cleanup order R-K, and A-G as amended by s1b1b1r2-env-spawn-repair.md:12 (allowed input-name removals exactly {__PYVENV_LAUNCHER__} on both platforms), with its R-1/R-2: no env framing, env= handoff, supervisor registration before the parent-side close) and `sweep` as written in s1b1b2-check-sweep.md (parent R-4) (guard in its own group outside group C, lifeline `S`/`F`/`X`/`D`, `--deadline`, lease + lock fd, `sweep`). If the merged guard or sweep differs, stop and re-gate.

Write-set (exclusive for this slice):
- terminal_planner/checks.py: `_git` :682-685 runs each git call through the guard with `--deadline <export.TIMEOUT>`, a lifeline, and the lease of the checkout being prepared (the clone target, from `_prepare` :688-707); output captured from the pipe as today; status from `X` subject to s1b1b1r R-C: `X timeout`, or an unconfirmed stop even after `X 0`, maps to the same checkout refusal as today's `subprocess.TimeoutExpired`; zplan keeps its own wait bound and `_reap`; a module-level git executable name that tests may override (today the literal at :684); necessary `_prepare` call-site changes are included. Resolve the clone lease from `directory`, not `project`; borrow the owning lock handle's `fileno()` for `--lock-fd` and `pass_fds`, never close it in `_git`. Register the supervisor before closing the parent's guard endpoint.
- tests/test_checks.py: the new tests; existing spawn-argv/spy assertions and fixture hook/spy scoping may change solely to accommodate guarded git preparation (e.g. test_checks.py:1082 and :2146 install the hold hook and `REAP=0.5` before checkout, which would now catch the clone). Preserve every existing behavioral oracle, including sweep/ownership regressions; list all adaptations in the receipt.
- the receipt `devtools/zeroshot/tasks/s1b1c-git-bound-receipt.md`.

Not touched: check_guard.py (its `--deadline` is s1b1b1r's), every other file; `_prepare` keeps its refusal mapping (timeout, non-zero, `OSError` → `{"refused": "checkout"}`).

Rules:
- R-1 Bound outside zplan: every git process of a qualification runs in a guard-supervised group C with the guard's deadline, so it ends within `export.TIMEOUT` (+ the 10 s wait bound) whether zplan is alive, stopped or dead.
- Product need and fault model: a hung qualification git must not keep the checkout busy indefinitely after zplan stalls or dies. The model covers git and descendants remaining in group C, a running guard under normal scheduling and working process-group signals, controller SIGSTOP with an open lifeline, and controller SIGKILL, synchronized by A-P/A-K handshakes. Direct guard termination and processes escaping C retain parent R-3/R-6 limits. Completing cleanup under asynchronous exceptions during acquisition or cleanup, exactly-once descriptor recovery, and async-signal-safe handlers are non-goals; s1b1b1r R-D/R-X apply.
- R-2 Death of zplan during a git call: parent s1b1b R-2 as owned by s1b1b1r applies (kill group C, remove the leased checkout and lock). Between git calls: parent R-3 (s1b1b1r) and `sweep` (s1b1b2 R-4).
- R-3 Unchanged contract: `checkout`/`qualify` preserve s1b1 return shapes and refusal values; an unconfirmed git stop is a checkout refusal under R-C, never a successful preparation; `export.environment()` and `export.OPTIONS` unchanged; argv only.
- R-4 Fixtures: home paths under `/home/user/`; the git stub is a test-written script whose path is set through the module-level name, never through PATH (export.environment() prepends /usr/bin:/bin).

Acceptance (tests/test_checks.py; temp git repos; controller = a separate `sys.executable` child calling `checks.qualify` with the stub as git and `export.TIMEOUT` patched to 1 s; the stub ignores SIGTERM, starts a sleeping descendant, writes a handshake file and never exits on its own; no network):
- A-P Production-path deadline (gate13 point 3): after the handshake the test SIGSTOPs the controller, keeping its lifeline open. Oracle within 3 s, while the controller is still stopped: the stub's group is gone. Then SIGCONT: `qualify` returns `{"refused": "checkout"}` and the checkout root is empty. This is the only test that kills mutation (a): zplan's own timer cannot run while stopped, and the lifeline gives no EOF.
- A-K Kill during clone: SIGKILL the controller after the handshake → within 3 s the stub group, the checkout directory and lock are gone; `sweep(root)` returns zeros.
- A-T Timeout with zplan running: `qualify` returns `{"refused": "checkout"}`; no process or directory left (control for R-3).
- A-A Argv assertion: a `popen` spy on `_git` records `--deadline` and the `export.TIMEOUT` value in the guard argv for clone, checkout and both rev-parse calls.
- A-C Git fail-closed: through `checks.qualify` and production `_git`, reuse s1b1b1r A-C hold 2 (`check_guard.after_report`, `X 0`, hold 2 s, REAP 0.5 s). Oracle: `{"refused": "checkout"}`; control without the hold permits normal git preparation. Reuse the existing seam; no new guard hook or injection matrix.
- A-7 Base failure: A-P on base (s1b1b1r and s1b1b2 merged) fails by a named assertion (the stub pid alive after 3 s with the controller stopped). Report named failures and skips separately.
- Mutations, each killed by a named test: (a) `_git` without `--deadline` (A-P, A-A); (b) `_git` without the lease (A-K: the checkout survives the kill); (c) `X timeout` mapped to anything but the checkout refusal (A-T); (d) git spawned directly, not via the guard (A-K).

Size: estimated 160-240 changed lines, receipt excluded: checks.py ~35, tests ~125-205. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: checks.py and test_checks.py only: serial after s1b1b1r and s1b1b2; parallel with every non-S1b slice. s1b2a waits for it.

Out of scope: records, marker, display (s1b2a/s1b2b); flake reruns (s1b3).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_checks tests.test_live tests.test_toolchain tests.test_reference` passes locally.
- `git diff --stat <base>` lists only the write-set; `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table, the edited existing assertions and fixture hook/spy scoping.
- Orchestrator, before merge: `tests.test_checks` on the Linux test host, then the full suite.
