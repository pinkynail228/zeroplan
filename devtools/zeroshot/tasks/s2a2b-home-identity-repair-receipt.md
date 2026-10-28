# s2a2b-home-identity-repair — receipt

Repair of the `s2a2-engine-wiring` candidate (branch `zs-s2a2-engine-wiring`). Base commit:
`5f05526a` (`s2a2-engine-wiring: native engine home wiring (run 01a155fb)`), the candidate this run starts on; the
result merges as `s2a2`. Every line the task cites was re-checked on this base. Visit 1 implemented R-1..R-3; visit 2
(rejection `phase.after=rejected`) repairs the acceptance reviewer's R-2 finding and the code reviewer's R-1 finding.

## Cause (reproduced before the visit-1 fix)

The integration gate (`03a2917`) fails `tests.test_ux.NativeJourneys.test_a5_phases_print_while_the_planner_runs_with_one_rare_heartbeat`
whenever the process env has no `CODEX_HOME` (the default `~/.codex` case, and the Linux test host), while `main`
passes. Two independent defects:

1. `NativeEngine.with_home` (engine.py:983 on the base) compared the recorded home with
   `self.native_environment().get("CODEX_HOME")` — `None` when the env has no `CODEX_HOME`. The revision records
   `str(self.codex_home())` (engine.py:1139 on the base), so the comparison never matched, `engine_for` built a new
   sibling on every slice, and every planner turn after a review printed `Составляю план…` instead of
   `Уточняю план по замечаниям…`.
2. The "a review was seen" fact was `self.reviewed` on the engine object, so a sibling lost it even where the
   comparison matched (a recorded home different from the current one).

Reproduction on the base (`TMPDIR=<scratch>`, env without `CODEX_HOME`):
`python3 -m unittest tests.test_ux.NativeJourneys.test_a5_phases...` -> `FAILED (failures=1)`,
`'Составляю план…'` where `'Уточняю план по замечаниям…'` is expected.

## Repair visit 2 (both review findings, demonstrated on the visit-1 candidate)

**Finding 1 (acceptance + code reviewer): the observation context kept one state root per run id, so another root's
observation overwrote an existing run's review fact.** `OBSERVED_RUNS[run_id] = (state_root, True)` replaced the
entry: with the same native run id in roots A and B, B's review erased A's, and A's next planner turn printed
`Составляю план…` again. Reproduced here before the fix (scratch copy, A/B key): the new
`PlanTests.test_r2_two_runs_sharing_a_run_id_in_different_state_roots_keep_their_own_history` fails at its fifth
element. Fix: the context is keyed by the run itself — `(state_root, run_id)` (engine.py:272-277, written at :1254,
read at :1256) — so entries never overwrite each other; sharing still holds process-wide for every engine object of
one run, which always carries the acting/recorded root (`engine_for`'s sibling keeps `self.state_root`,
`recorded_engine` the recorded one).

**Finding 2 (code reviewer): the recorded home was normalized before the comparison and before delegation.**
`engine_for` read `str(record_home.binding_home(binding))` (the visit-1 line 973); `str(Path(...))` drops a trailing
separator, so a valid 5-key record whose home is spelled `/…/home-a/` compared unequal to the identical env
`CODEX_HOME = /…/home-a/` (a wrong sibling), and the sibling received `/…/home-a` — no longer the recorded string.
Fix: `recorded_home(binding)` (engine.py:941-949) returns a 5-key record's `codex_home` *as stored*, and the legacy
process home for a 4-key record; `engine_for` (:982-986) and `proposal`'s prepared-unsent delegation (:1190) use it.
`record_home.binding_home` is still called first, so the R-3 shape check (ValueError for an invalid or fixture
binding) is unchanged. Extended the A-2 table with trailing-separator rows for the absolute, `..` and symlink
spellings.

## Files (write-set only)

- `terminal_planner/engine.py` (+45/-10): `OBSERVED_RUNS`/`reviewed` :272-277 (R-2 observation context, keyed by the
  run); `recorded_home` :941-949 (the record's own spelling, R-1); `NativeEngine.engine_for` :982-996 (home at :986,
  R-1 comparison through `with_home`); `NativeEngine.with_home` :999-1010 (comparison at :1007);
  `NativeEngine.phase` :1243-1259 (`run_id` parameter, mark :1254, read :1256); its only caller, `observe` :1344
  (`self.phase(status, current["run_id"])`, the observation code of R-2); `proposal`'s prepared-unsent delegation
  :1190 (one line, the literal home). `sibling`, `binding_identity`, `engine.identity_changed`, `check_recorded`,
  `recorded_engine` and the env construction (PATH prefix, `CODEX_HOME`) are untouched (R-3).
- `tests/test_home_wiring.py` (+159/-16, 644 lines): the module docstring (R-1 wording), the R-1 rows and the
  trailing-separator rows of `test_a2_a_detached_revision_...` :255 and `test_a2_engine_for_...` :376, the A-3 journey
  :424, the new visiting regression :450 (helpers :349-374). Interpretations are in the three test docstrings.
- `devtools/zeroshot/tasks/s2a2b-home-identity-repair-receipt.md` (this file).
- Not touched: `authority.py`, `setup.py`, `toolchain.py`, `record_home.py`, `planning.py`, `runs.py`, `tui/*`,
  `cli.py`, `docs`, `STATE.md`, `AGENTS.md`, `prototype/`, `reference/`, `upstream/`.

## A-1..A-4 -> tests and file:line

| # | Requirement | Test | Code under test |
| --- | --- | --- | --- |
| A-1 | the A5 test, unedited, on the full `tests.test_ux` module | `tests.test_ux.NativeJourneys.test_a5_phases_print_while_the_planner_runs_with_one_rare_heartbeat` (unedited) | `with_home` engine.py:1007, `phase` :1243-1259 |
| A-2 | R-1 table: env absent/empty/equal vs alias, legacy four-key, recorded `..`/symlink/trailing-separator | `tests.test_home_wiring.PlanTests.test_a2_engine_for_keeps_the_engine_whose_own_home_a_record_names` :376 (16 rows) | `recorded_home` :941, `engine_for` :986, `with_home` :999-1010 |
| A-2 | the same in the observation path, both homes and both absent/empty env values | `PlanTests.test_a2_a_detached_revision_is_observed_in_its_recorded_home_and_an_alias_never_recurses` :255 | `engine_for` :982, `with_home` :999 |
| A-3 | planner, plan_verifier, planner, each slice a fresh delegated sibling, then a second run | `PlanTests.test_a3_a_seen_review_is_observation_context_of_the_run_not_of_the_engine` :424 | `phase` :1243-1259, `observe` :1344 |
| A-3/R-2 | two runs with the same id in different state roots keep their own history (the review finding) | `PlanTests.test_r2_two_runs_sharing_a_run_id_in_different_state_roots_keep_their_own_history` :450 | `OBSERVED_RUNS` :272-277, :1254, :1256 |
| A-4 | mutations (a)-(g), each reproduced once in a scratch copy | below | - |

Evidence commands (each with a private short `TMPDIR` as the task requires):

- `TMPDIR=/tmp/zs-agent-… env -u CODEX_HOME PYTHONPATH=.:tests python3 -m unittest tests.test_ux` -> `Ran 20 tests`,
  `OK` (A-1; fails on the base).
- `TMPDIR=/tmp/zs-agent-… env -u CODEX_HOME PYTHONPATH=.:tests python3 -m unittest tests.test_home_wiring` ->
  `Ran 16 tests`, `OK` (A-2 with the trailing-separator rows, A-3 and the R-2 interleave).
- `TMPDIR=/tmp/zs-agent-… env -u CODEX_HOME PYTHONPATH=.:tests python3 -m unittest tests.test_home_wiring
  tests.test_record_home tests.test_ux tests.test_terminal_planner` -> `Ran 135 tests`, `OK` (the cross-module order
  in which a bare run-id key carried the fixture review into the A5 journey).
- Same modules with the runner's `CODEX_HOME` set -> `Ran 99 tests`, `OK` (`test_home_wiring test_ux test_record_home
  test_plan_gate`); the R-1 change is confined to an absent/empty env value.

## A-4 mutations

One scratch copy (`shutil.copytree` into `/tmp/zs-agent-mut/repo`, `.git`/`.tools`/`__pycache__` ignored); every
mutation undone by re-copying, nothing reverted in the shared worktree.

| # | Mutation (in the scratch copy) | Result |
| --- | --- | --- |
| a | `with_home` with the as-stored comparison (`if home == stored:`) | A-2 fails: 3 subtests (`test_a2_engine_for_…` absent/empty/legacy rows). A-1 still passes under (a) — the visit-1 R-2 fix alone makes the A5 journey share the review fact, so the A-2 table is what kills this mutation |
| b | `phase` keeps `self.reviewed` on the engine instance | A-3 fails: `'Составляю план…'` where `'Уточняю план по замечаниям…'` is expected |
| c | one global key instead of the run key (`OBSERVED_RUNS[("seen", run_id)]`, `reviewed("seen", …)`) | A-3 fails on the second run: `'Уточняю план по замечаниям…'` where `'Составляю план…'` is expected |
| d | the explicit env value resolved (`str(Path(stored).expanduser().resolve())`) | A-2 fails: 11 subtests (alias, `..`, trailing-separator and symlink rows) |
| e | `engine_for` normalizes the home again (`home = str(record_home.binding_home(binding))`) | A-2 fails: 6 subtests, the three trailing-separator spellings (compared unequal, and the sibling drops the separator) |
| f | one state root per run id again (`OBSERVED_RUNS[run_id] = (state_root, True)`) | the R-2 interleave test fails at its fifth element (`'Составляю план…'`) — the rejection reproduction |
| g | the bare run-id key (`run_id in OBSERVED_RUNS` / `OBSERVED_RUNS[run_id] = True`) | the R-2 interleave test fails at its third element (B inherits A's review) and A5 fails after `tests.test_terminal_planner` |

## Repair visit measurement

Product `+45/-10` (task: ~40 product). Tests `+159/-16` in `tests/test_home_wiring.py` (644 lines; task: ~160 test
lines). Measured overrun: about +5 product lines vs the estimate — the second review finding's `recorded_home`
helper and its docstring (7 lines) plus the reworded context comment; no overrun in tests. No unrelated change, no
refactor, no new module.

## Interpretations (silence, ambiguity or contradiction)

1. **The observation context is keyed by the run: `(state_root, run_id)`** (engine.py:272-277). R-2 says "keyed by
   the native run id, shared by every engine object in the process". A run id is unique only inside its own
   `<state_root>/runs`; the fixture suite freezes one id in different stores, and `unittest discover -s tests` runs
   `tests.test_terminal_planner` before `tests.test_ux` (verified with `unittest.defaultTestLoader.discover` module
   order). Reproduced with a bare-id key: `tests.test_terminal_planner tests.test_ux.NativeJourneys.test_a5_phases…`
   -> `FAILED`, the A5 journey printing the repair line on its *first* planner turn — A-1 forbids that. The state
   root is therefore part of the run's identity, both reviewers required each root to keep its own history, and the
   process-wide sharing R-2 asks for holds over every engine object of one run (the acting engine, its `engine_for`
   siblings and `recorded_engine` all carry the acting/recorded root). No store or Authority state is added.
2. **R-2's context is reachable only through `phase`'s `run_id` argument.** `phase(self, status, run_id)` now takes
   the run from its caller (`observe`), the only in-engine caller; nothing else in the tree calls `phase`.
3. **`with_home`'s default is `str(self.codex_home())`, not an env-`HOME`-based default of its own.**
   `setup.codex_home` reads `Path.home()` (the *process* `HOME`) for an absent or empty `CODEX_HOME`, so the engine's
   own home for the comparison is exactly what the record writers stored (`str(self.codex_home())`, engine.py:1170)
   — the round trip the requirement describes. No separate default is computed.
4. **A recorded home is compared and delegated in its literal spelling** (the visit-2 repair of finding 2):
   `recorded_home(binding)` returns the 5-key `codex_home` as stored — a trailing separator, a repeated separator or
   an alias spelling included — and the legacy process home for a 4-key record. `record_home.binding_home` still runs
   first for the R-3 shape check. `recorded_engine` and the env construction keep the s2a2 `str(binding_home(...))`
   form (R-3: unchanged), so an approval/override engine still receives the normalized spelling.
5. **Two pre-existing R-3-era rows in `tests/test_home_wiring.py` were updated** (not new behaviour): the
   absent/empty env rows of `test_a2_a_detached_revision_…` asserted the s2a2 R-3 comparison ("never filled in from
   the resolved default"), which R-1 of this task replaces. They now expect the env as stored when the record names
   the effective default, and a sibling for another recorded home (the new R-1 table test covers the same domain).
   A-1's "do not edit" covers only the A5 test, which is untouched.
6. **The R-2 interleave regression drives `engine_for`'s delegated engines rather than a full `proposal` journey**
   from the second root: R-3 (unchanged) refuses that — `prepare` compares the recorded `state_root` with the acting
   engine's (`binary_identity()`) and raises `engine.identity_changed` (reproduced while writing the test). The
   delegated engines are the objects `proposal` observes through, so the context sharing under test is the real one.
7. **`OBSERVED_RUNS` is never cleared** (R-2 asks for no store state and no reset); it grows by one entry per run
   observed in the process, and the A-3/interleave tests use their own run ids so no other module's run is touched.

## DoD

`TMPDIR=/tmp/zs-agent-… env -u CODEX_HOME PYTHONPATH=.:tests python3 -m unittest tests.test_toolchain tests.test_reference tests.test_home_wiring tests.test_record_home tests.test_ux tests.test_runs tests.test_terminal_planner tests.test_milestone tests.test_plan_gate tests.test_plan_override tests.test_live tests.test_tui_planning`
-> `Ran 443 tests in 586.459s`, `OK` (macOS arm64, Python 3.9; Linux qualification is the orchestrator's merge gate).

Left to the orchestrator's merge gate: the full suite on Linux (`devtools/linux-test.sh`) and on macOS
(`devtools/mac-test.sh`), the native/installed qualification, `devtools/export_check.py`, and the installed
walkthrough.

