# s1b1b1r2-env-spawn-repair — receipt

- Base (this run's checkout HEAD, branch `zs-s1b1b1r2-env-spawn-repair`): `e159b412ad41e1160e6f3bca8326438ba838a20b`.
  `git diff --stat e159b41` lists only the write-set (`terminal_planner/checks.py`, `terminal_planner/check_guard.py`,
  `tests/test_checks.py`, this receipt). The s1b1b1r candidate the repair starts from is `a887d999c4bbbe8560655c05
  18bfedd4a633f9fb` (branch `zs-s1b1b1r-check-guard` = run result `c6d70e9` + main); the commits between `e159b41`
  and `a887d99` touch `devtools/zeroshot/` only, so the product/test content at the two bases is identical
  (`git diff --numstat a887d99 HEAD -- terminal_planner/ tests/` is empty) and the size numbers below are the same
  either way. `main` here is `5379f0e3f055ac3f44e123ae64fa0b2861a4e81c`.
- Brief sha256: `de87b8aa47d6df4514754f0a7b08a76a1cbf543f8b4d1d8762385d43c36f90e1`.
- Interpreter: `python3.13 -V` → `Python 3.13.3` (macOS, the run's required interpreter; `python3` was never used).
- Write-set (`git status --porcelain`, delivery adds them in one `git add --all`): `terminal_planner/checks.py`
  (modified), `terminal_planner/check_guard.py` (modified), `tests/test_checks.py` (modified), this receipt (new). No
  other file.
- Measured size (receipt excluded; `+/-` are added/removed lines):
  - repair delta vs `a887d99` (the s1b1b1r candidate): product `checks.py` +5/−20, `check_guard.py` +20/−60 →
    **+25/−80, net −55**; tests `tests/test_checks.py` +107/−103 → **net +4** (the framing tests removed, A-2 added,
    the A-1 oracle widened in the repair below). Product is net negative, as required.
  - vs `main` (`5379f0e`, the merge target; the whole slice): product `checks.py` +428/−96, `check_guard.py`
    +308/−0 → **+736/−96**; tests `tests/test_checks.py` +1209/−4.

## R-1 — the env framing removed

- `checks.py`: `_frame` deleted; the `--await-env` option dropped from the guard argv; `import base64` removed;
  `run_check` now hands `env` to the guard's `Popen` as `env=` and sends nothing before `_read` ("`run_check` passes
  `env` to the guard's `Popen` as `env=`", s1b1b1r R-1 for `env`, verbatim). `_send` stays (it is `_reap`'s `D`).
- `check_guard.py`: `--await-env`/`await_env` option gone; `_unframe`/`_inherited` deleted; `_handover` is the
  non-blocking `D`/EOF drain it always had (`"run"|"done"|"gone"`); the guard spawns the check with its own
  environment as received (no `env=` at all); `import base64` removed. `select`/`os` remain in use (`_pending`,
  `_supervise`, `_silence`).
- A-3: `rg -n '_frame|_unframe|await.env|_inherited' terminal_planner/checks.py terminal_planner/check_guard.py`
  prints nothing and exits **1** (verified after the edits).

## R-2 — the guard is `_settle`'s before any further access

- `checks.py` `run_check`: the `_Supervisor(process, lifeline)` registration now happens inside the spawn `try`,
  immediately after `popen` returns and **before** `_shut(guard_end)` (which is still the spawn `try`'s `finally`).
  An exception after a successful spawn can no longer take the `supervisor is None` branch of `_settle`: the guard is
  `_reap`ped (and, if the stop is unconfirmed, owned by `ORPHANS`) instead of leaking its stdout pipe and its group.

## Acceptance

- **A-1** `EnvironmentTests.test_a_handed_over_environment_loses_at_most_the_consumed_name` replaces candidate
  `tests/test_checks.py:1515` (`test_every_name_of_the_handed_over_environment_reaches_the_check`): for an explicit
  `env` and for `env=None`, missing *input* names are a subset of `{__PYVENV_LAUNCHER__}` (the oracle names the
  consumed name), every retained input value matches (`LC_CTYPE` excepted) and the non-exempt markers survive. The
  oracle compares the **complete input mapping** (not a single marker): for `env` it is the handed mapping, for
  `env=None` it is the caller's environment made deterministic with `patch.dict(os.environ, planted, clear=True)`
  and snapshotted before the call, so *any* input name lost or altered beyond the two exceptions fails the test.
  The amendments and this interpretation are recorded in the test docstring.
- **A-2** `ExceptionTests.test_a_post_spawn_cleanup_fault_still_reaps_the_registered_guard`: a wrapped `popen`
  records and returns the real guard; the parent-side `_shut(guard_end)` closes that socket and raises one saved
  `ValueError` after a successful spawn. Asserted: the same object is re-raised, `_reap` receives exactly that guard,
  it is reaped within `REAP` (`returncode` set), it is absent from `ORPHANS`, its stdout pipe is closed and the
  checkout's exit removes the directory.
- **A-3** above (exit 1, no output).
- Retained s1b1b1r oracles are unchanged except amended A-G. The pre-spawn handoff test at candidate
  `tests/test_checks.py:560` is replaced by `RuleTests.test_the_pre_spawn_drain_reads_a_queued_d_before_an_observed_eof`
  (four non-blocking cases: live peer, queued `D`, EOF, `D`+EOF; `D` precedence preserved). Candidate
  `tests/test_checks.py:814` (the queued-frame-after-death guard child, which no longer has a frame to queue) and the
  now-unused `SPAWN_HOOK`/`frame` test helpers are deleted; its M-2/H-3b coverage is retained by
  `HardKillTests.test_a_guard_that_finds_zplan_gone_spawns_nothing_and_removes_the_lease` and the drain test covers
  M-2/M-3 in-process.

## Mutations (scratch copies; never the shared worktree)

- **A-2 mutation:** moving the `_Supervisor` registration below the `_shut(guard_end)` close →
  `ExceptionTests.test_a_post_spawn_cleanup_fault_still_reaps_the_registered_guard` **fails** on
  ``self.assertEqual(reaped, spawned, "`_reap` did not receive the guard the spawn returned")``:
  `AssertionError: Lists differ: [] != [<Popen: returncode: None ...>]` (baseline: 1 test, OK).
- **A-G mutation:** the guard spawns the check with a mapping that drops a non-exempt name
  (`{k: v for k, v in os.environ.items() if k != "ZPLAN_ENV_MARK"}`) → the A-1 test **fails** with
  `AssertionError: {'__PYVENV_LAUNCHER__', 'ZPLAN_ENV_MARK'} not less than or equal to {'__PYVENV_LAUNCHER__'} : an
  explicit mapping lost a name other than the consumed one`; an `env={}` variant fails all three `EnvironmentTests`.
- **A-G mutation, `env=None` path (the acceptance/code rejection's reproduction):** with
  `ZPLAN_OTHER_INPUT=must-survive` in the runner's environment, `checks.run_check` drops `ZPLAN_OTHER_INPUT` from the
  environment handed to the guard's `Popen` only when `env is None` → the A-1 test **fails** on the `env=None` branch:
  AssertionError: `{'__PYVENV_LAUNCHER__', 'ZPLAN_OTHER_INPUT'} not less than or equal to {'__PYVENV_LAUNCHER__'}`,
  message "`env=None` lost a name other than the consumed one". The pre-repair (marker-only) oracle passed that same
  mutation: compared against its two planted names it answered `{ZPLAN_ENV_MARK: here}` (OK) while the caller's
  non-planted input name was gone (probe: "pre-repair oracle on the non-isolated caller env: True | caller name
  ZPLAN_OTHER_INPUT lost: True") — the blind spot the isolation and the full-mapping comparison close.
- **Drain mutation:** `_handover` returns `"run"` after the drain, ignoring the queued `D` and the observed EOF → the
  drain test **fails** on three subtests (`'run' != 'done'`, `'run' != 'gone'`, `'run' != 'done'`).
- **Mutation (r6) of the s1b1b1r receipt — superseded only for its frame branch.** r6's frame branch ("the pre-spawn
  handoff read the environment frame before the observed EOF") is moot: with the framing removed there is no frame to
  read, and the guard's handoff *is* the drain. The requirement r6 stood for — a queued `D` before an observed EOF is
  a normal end, never a death — is retained and now guarded by
  `RuleTests.test_the_pre_spawn_drain_reads_a_queued_d_before_an_observed_eof` (M-2/M-3), with the guard-child M-2/H-3b
  coverage kept by `HardKillTests.test_a_guard_that_finds_zplan_gone_spawns_nothing_and_removes_the_lease`. Unlike r6's
  frame branch, the drain test does not cover a *frame* behind the EOF, because no frame exists.

## Repair (phase `after: rejected`; acceptanceFeedback and codeFeedback agree)

- **Finding (both reviewers):** A-1's `env=None` oracle was incomplete -- `checked()` compared only the planted names,
  so the caller's other input names were unchecked, contrary to A-1's required missing-name and retained-value
  assertions. Reproduction: `ZPLAN_OTHER_INPUT=must-survive` in the caller's environment, the guard's check `Popen`
  omitting it when `env=None` → the variable disappeared yet the test still passed.
- **Cause:** the pre-repair oracle only knew `{__PYVENV_LAUNCHER__, ZPLAN_ENV_MARK}`, while `env=None` hands over the
  whole caller's `os.environ`; and the evidence tail is the R-4 *scrubbed* window, so a non-isolated caller
  environment (this runner's `*_API_KEY` values become `live.HIDDEN`) cannot be compared name-for-name.
- **Fix (in `tests/test_checks.py`, the A-1 oracle):** the `env=None` caller environment is isolated with
  `patch.dict(os.environ, planted, clear=True)` and snapshotted, and `checked(observed, source, mode)` now compares
  the **complete input mapping**: missing input names ⊆ `{__PYVENV_LAUNCHER__}`, every retained input name's value
  equal (`LC_CTYPE` excepted), with a third ordinary name (`ZPLAN_OTHER_INPUT`) so more than one non-exempt name is
  exercised. No production change was needed: R-1/R-2 stand, and the earlier reproductions still pass.
- **Class / domain / interpretations** are recorded in the test's docstring: the class is *any* input name lost or
  altered beyond the two A-G exceptions; the domain is an explicit three-name mapping and `env=None` over an isolated
  caller environment; the interpretations are (1) A-G's "every name with its value" read with the one-name removal
  exception, the mapping handed over untouched (`env=`), never re-framed, and (2) the isolated, snapshotted caller
  environment as the `env=None` oracle (the R-4 scrubber forbids comparing a non-isolated one).
- Re-verified after the repair: A-2 baseline OK and its registration-after-close mutation still fails the `_reap`
  assertion; the four drain cases OK and the ignore-D/EOF mutation still fails three subtests; A-3 no output, exit 1;
  `python3.13 devtools/export_check.py` → `summary: 0 findings`; `git diff --stat e159b41` still only the write-set.

## DoD evidence (macOS, Python 3.13.3, a private short `TMPDIR` under `/tmp/zs-agent-*`)

- Worker targeted: `PYTHONPATH=.:tests python3.13 -m unittest tests.test_checks tests.test_toolchain tests.test_reference`
  → `Ran 108 tests … OK` (0 failures, 0 skips, re-run after the repair); `tests.test_checks` alone → `Ran 49 tests … OK`.
- `python3.13 devtools/export_check.py` → `summary: 0 findings` (the private-term rule is skipped), so no home-path
  finding on this candidate.
- `git diff --stat e159b41` (and `git diff --stat a887d99`, product/tests only) lists only the write-set.
- Left to the orchestrator (not claimed here): the s1b1b1r integration gate on the new HEAD (Linux full, macOS
  targeted, `export_check`), then a fresh merge verdict with the size disposition.
