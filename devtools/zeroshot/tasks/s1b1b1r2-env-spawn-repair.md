s1b1b1r2-env-spawn-repair — repair of the s1b1b1r-check-guard candidate (critic s1b1b1r-merge BLOCK, session 01a158b6-d6cf-7023-8d91-4fadabba4a6f, ~/zs-pause/critic/s1b1b1r-merge.out). Task gate: critic s1b1b1r2-gate GO WITH CHANGES (applied; new session 01a159b8-9ef1-7011-8adc-bd8c641c19d1 after rotation). The A-G removal allowance holds on Linux too (CPython 3.13.3 Modules/getpath.c:902 clears the name without a macOS condition). DeepSeek worker, sol reviewers.

Base: this run starts on the s1b1b1r candidate (branch zs-s1b1b1r-check-guard at a887d99 = run result c6d70e9 + main); the result merges as s1b1b1r. Record the base and this brief's sha256 in the receipt. The s1b1b1r brief (devtools/zeroshot/tasks/s1b1b1r-check-guard.md) stays in force except where this brief amends it.

Findings:
- F-1 Spawn ownership gap (R-C/R-X). checks.py:132 reads the caller's env mapping a second time (`_frame`) after `popen` succeeded and before `_Supervisor` exists; an exception there takes the `supervisor is None` branch of `_settle` (checks.py:377), which closes only the lifeline: the guard is never reaped nor put in `ORPHANS`, its stdout pipe stays open (critic probe on 3.13: a mapping whose second `items()` raises ValueError -> spawned=1, `_reap` calls 0, `ORPHANS` empty).
- F-2 Env handoff outside the gated design. The receipt (s1b1b1r-check-guard-receipt.md:138) resolved an A-G vs R-1 conflict (`__PYVENV_LAUNCHER__` is unset by a macOS framework interpreter in every child before `check_guard.py` runs) by framing the mapping on the lifeline (`_frame`, `--await-env`, `_handover`, `_inherited`). No S1b product need requires carrying `__PYVENV_LAUNCHER__`; the framing phase and its lifecycle are the main size overrun.

Write-set (exclusive): terminal_planner/checks.py, terminal_planner/check_guard.py, tests/test_checks.py, the receipt devtools/zeroshot/tasks/s1b1b1r2-env-spawn-repair-receipt.md. No other file.

Amendments to s1b1b1r:
- A-G (amended again): the check sees every name of the `env` given to `run_check` (or the caller's environment for `env=None`) with its value, except that the guard's interpreter may add names (`LC_CTYPE`, macOS `__CF_USER_TEXT_ENCODING`), coerce the value of `LC_CTYPE`, and remove names it consumes before guard code runs (measured: macOS `__PYVENV_LAUNCHER__`). The allowed set of removed names is exactly {`__PYVENV_LAUNCHER__`}; the test oracle names it.

Rules:
- R-1 Remove the env framing: delete `_frame`, the `--await-env` option, `_handover`'s framed-environment path and `_inherited` (also delete `_unframe`, the test-only `frame` helper and unused framing imports; replace test_checks.py:560 with non-blocking open-peer, D, EOF and D+EOF cases, preserving D precedence; delete :814; replace :1515 under A-1; record receipt mutation r6 as superseded only for its frame branch, retaining M-2/M-3/H-3b coverage). `run_check` passes `env` to the guard's `Popen` as `env=` and the guard spawns the check with its own environment as received (s1b1b1r R-1 for `env`, verbatim). Keep the guard's non-blocking `D`/EOF drain that existed without `--await-env`.
- R-2 Register the returned guard for `_settle` before `_shut(guard_end)` or any further caller-object access. Prepare internal cleanup state before spawn if needed. The synchronous A-2 fault is covered; R-D's asynchronous non-goal remains unchanged; allocator-failure injection is not required.

Acceptance (tests/test_checks.py; the s1b1b1r test conventions):
- A-1 Retained s1b1b1r oracles remain unchanged except amended A-G. Replace the test at candidate test_checks.py:1515 rather than deleting it: for explicit env and env=None, missing input names are a subset of {`__PYVENV_LAUNCHER__`} on both macOS and Linux; retained input values match except LC_CTYPE; a non-exempt marker must survive.
- A-2 Post-spawn fault: wrap `popen` to record and return the real guard. At the parent-side `_shut(guard_end)`, close that socket and raise one saved ValueError, once, only after successful spawn. Assert that the same exception is re-raised, `_reap` receives that guard, it is reaped within REAP, is absent from ORPHANS, stdout is closed, and checkout exit removes the directory. Mutation: move registration below that same close; the `_reap` assertion must fail. Record baseline and mutation results.
- A-3 `rg -n '_frame|_unframe|await.env|_inherited' terminal_planner/checks.py terminal_planner/check_guard.py` prints nothing and exits 1; exit 2 is a failure.

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3.13 -m unittest tests.test_checks tests.test_toolchain tests.test_reference` passes (short TMPDIR, e.g. `TMPDIR=/tmp`).
- `git diff --stat <base>` lists only the write-set.
- Receipt: base, brief sha256, interpreter, the A-2 mutation result, size vs main (product and tests separately, +/-).
- Orchestrator, after acceptance: the s1b1b1r integration gate on the new HEAD (Linux full, macOS targeted, export_check), then a fresh merge verdict with the size disposition.

Size: product net negative vs a887d99 (framing removed, R-2 a few lines); tests: framing tests removed, A-2 ~40 lines.
