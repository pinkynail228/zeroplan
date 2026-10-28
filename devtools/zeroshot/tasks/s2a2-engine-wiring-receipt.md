# s2a2-engine-wiring — receipt (repair visit 4)

Base commit: `6a537b5a3e63ecc79aa5a0f23f01ec440b5ecbc4` — `main` after the `s2a1-home-core` and `s1a1a-gate-core`
merges. Every line the task cites was re-checked on this base with `git show 6a537b5:<file> | grep -n`; the premises
hold. **On the base** (the task's `e29f986` cites differ, as the batches in between shifted them): the planning writer
is engine.py:1103 (`current["native_binding"] = binding`) and the compare that guards it is :1049
(`if current.get("native_binding") not in (None, binding):`); `MilestoneRuns.start` writes the binding at runs.py:655
and `check_binding` (:786) compares whole bindings at :789; `binding_changed` returns whole-binding equality at
planning.py:249. **On the candidate** those six sites are engine.py:1139/:1085, runs.py:658/:791 and planning.py:249.
`engine_for`/`recorded_engine`/`read_engine` are as cited, and s2a1's helpers are exactly as frozen. The running
candidate was not used.

## Files (write-set only)

- `terminal_planner/engine.py` (+63/-21): `binding_identity` :921 (the native-only four-field projection; a binding
  without `executable` — a fixture binding, `None` — is returned as it is, R-2); `recorded_engine` :928 (the process
  env, the record's `CODEX_HOME` :935 and its `codex/node_modules/.bin` PATH prefix :932-934, R-3/A-2);
  `toolchain_path` :940; `NativeEngine.engine_for` :958 — itself only when executable, version **and** home are its
  own, an alias spelling resolving to the same binary (:963) and a spelling that cannot be resolved (a symlink loop)
  guarded by `except (OSError, RuntimeError): same = False` (:964-966), after which `check_recorded` decides — else a
  sibling on the record's binary and state root with the record's PATH prefix (:970-971); `with_home` :974 (the
  engine's own stored `CODEX_HOME` as the comparison, never re-resolved, never filled in from the default);
  `codex_home` :980; `sibling` :984; `prepare` compare :1085 and writer :1139
  (`{**binding, "codex_home": str(self.codex_home())}`); `proposal` prepared-unsent branch :1157. `read_engine` needs
  no edit (it already rebuilds from `engine_for`'s environment, which carries the home).
- `terminal_planner/runs.py` (+7/-3): `start` :656-658 stores the driver env's home for a native binding only;
  `check_binding` :791-793 projects the record through `binding_identity`.
- `terminal_planner/planning.py` (+2/-2): `binding_changed` :249.
- `tests/test_home_wiring.py` (new, 500 lines: the `Homes` mixin, `PlanTests`, `DriverTests`; the interpretations are
  in its module docstring and in the two R-2 regression tests' docstrings).
- `devtools/zeroshot/tasks/s2a2-engine-wiring-receipt.md` (this file).
- Not touched: `authority.py`, `setup.py`, `toolchain.py`, `record_home.py`, `architect.py`, `tui/*`, `cli.py`,
  `catalog.py`, `docs`, `STATE.md`, `AGENTS.md`.

## Edited existing assertions

**None.** No existing test asserted a whole stored binding equal to a four-key `binary_identity()`: the three
whole-binding compares are covered by the production projection, so the 13 DoD modules pass unedited (`git status`
lists only the three production files plus the two new ones).

## A-2 path table (record home `A`, process env `B`; every test asserts the spawn env's `CODEX_HOME == A`)

| Path (entry) | Where | Test |
| --- | --- | --- |
| validate + submit of a frozen, receipt-less record (`reconcile` -> `NativeDriver.validate`/`submit`) | runs.py:1426, :1435 | `DriverTests.test_a2_a_replayed_validate_and_submit_use_the_recorded_home` |
| validate + submit of a new attempt (`MilestoneRuns.start` -> `dispatch`) | runs.py:607, :796 | `DriverTests.test_a1st_a_new_attempt_stores_the_driver_env_home_and_every_driver_path_uses_it` |
| watch, status, force-stop, resume, and the resumed successor's watch | runs.py:1441, :1445, :1450, :1463 | same |
| `log_tail` / `log_records` (`read_engine`, another state root) | engine.py:1239, :1248 | `DriverTests.test_a2_logs_and_the_failure_cause_read_in_the_recorded_home` |
| `failure_cause` (its own state root) | engine.py:1257 | same |
| planning observation (`proposal` -> `invoke`) | engine.py:1157, :999 | `PlanTests.test_a2_a_detached_revision_is_observed_in_its_recorded_home_and_an_alias_never_recurses` |
| submission of a prepared but unsent revision (R-4), its probe included | engine.py:1157 | `PlanTests.test_r4_a_prepared_unsent_revision_is_submitted_in_its_recorded_home` (+ the named negative: another state root still reaches `Stale` through `prepare`) |
| `recorded_engine` under `Authority.approve` **and** `Authority.override`, older toolchain's PATH prefix included | authority.py:777, :807 | `PlanTests.test_a4_approve_and_override_revalidate_in_the_records_own_root_and_home` |
| an older toolchain's binary on a milestone path (its own executable, home and PATH prefix) | runs.py:1445 | `DriverTests.test_a2_an_older_toolchain_binary_acts_in_the_recorded_home_with_its_path_prefix` |
| a spelling that cannot be resolved (a symlink loop), every family | engine.py:963-966 | `DriverTests.test_a_run_record_...` and `PlanTests.test_a_plan_revision_whose_executable_cannot_be_resolved_is_refused_not_crashed` |

## Base replay (base = this slice's base; the three production files restored to `6a537b5`, the current test module in place)

`PYTHONPATH=.:tests python3 -m unittest tests.test_home_wiring` -> `Ran 13 tests`, `FAILED (failures=8, errors=7)`,
**no ImportError** and **no `TypeError`** (the module imports only names that exist on the base):

- intended failures: 11/13 tests, 15 outcomes: A-1st (no `codex_home` stored: planning FAIL and attempt FAIL, both at
  `set(binding) == BINDING_FIELDS | {"codex_home"}` — the store assertions in the attempt test run *before* the
  probe-env one, so the base fails there. In the round-4 candidate that test instead raised
  `TypeError: 'NoneType' object is not subscriptable` from `self.setup_probes`, because the base's
  `recorded_engine` builds `NativeEngine` without `environment` and the spy recorded that omitted env as `None`; the
  spy now normalizes it to `{}` and the assertion reads `.get("CODEX_HOME")`, so the omission is a clean assertion
  failure, not an error. The earlier receipt mis-classified that TypeError as the missing stored `codex_home`); A-2
  (every spawn env is `B`: replay FAIL, older-toolchain FAIL, logs FAIL, detached ERROR in five subtests,
  observation FAIL); A-3 (`B`, not the process home: FAIL); A-4 (a literal five-key milestone record refused by the
  base `check_binding`: ERROR; the approve/override record refused by the base `prepare`: ERROR); R-3 (the base
  `engine_for` returns `self` for another home: FAIL); R-4 (the unsent revision submits in `B`: FAIL). Every one
  fails on a behavioral assertion, never on import.
- candidate-only guard passes: 2 tests —
  `DriverTests.test_a_run_record_whose_executable_cannot_be_resolved_is_refused_not_crashed` and
  `PlanTests.test_a_plan_revision_whose_executable_cannot_be_resolved_is_refused_not_crashed`. They guard the
  candidate-only `except (OSError, RuntimeError)`; the base compares executable *strings* and never reaches a
  `resolve()`, so it passes them by design. They are not legacy compatibility cases.
- compatibility passes: 0 whole tests (the A-3 legacy-load and digest assertions *inside* `test_a3_...` do pass on
  the base; its spawn assertion fails, so the test counts as an intended failure).
- skips: 0.

## Mutations (candidate-only; scratch copy, pristine sources restored before each row)

Command per row: `PYTHONPATH=.:tests TMPDIR=<scratch> python3 -m unittest <module or the named test>` in the copy, on
the final test module; `tests.test_runs` added where the row needs a fixture path. Every row below was re-run this
visit against the current candidate; the outcome count is the number of reported failures + errors.

| Mutation | Killing test | Result |
| --- | --- | --- |
| `engine_for` calls `resolve()` unguarded (a symlink loop raises `RuntimeError`) | `DriverTests.test_a_run_record_...` + `PlanTests.test_a_plan_revision_...` | killed (10 errors, Python 3.9/3.11/3.12; 3.13 no longer raises there) |
| `engine_for` compares the recorded home after `resolve()` | `PlanTests.test_r3_engine_for_is_idempotent_...` + `PlanTests.test_a2_a_detached_revision_...` | killed (2 failures) |
| `with_home` fills an absent/empty own home in from the default | `PlanTests.test_a2_a_detached_revision_...` | killed (1 error) |
| `sibling` drops the recorded home (`engine_for`'s and `with_home`'s env) | `DriverTests.test_a1st_a_new_attempt_...` (+8 tests) | killed (1 failure, 12 errors) |
| `recorded_engine` drops the recorded home | `DriverTests.test_a1st_a_new_attempt_...`, `PlanTests.test_a4_approve_and_override_...` | killed (2 failures) |
| `engine_for` returns `self` on an equal binary despite another home | `DriverTests.test_a1st_a_new_attempt_...` (+7 tests) | killed (10 failures, 1 error) |
| the same-binary home sibling takes the record's state root (`engine_for` :967-968), hiding a state-root change | `DriverTests.test_a4_a_home_change_...` (+3 tests) | killed (2 failures, 6 errors; the named test: `Blocked not raised`) |
| `prepare` compares whole bindings | `DriverTests.test_a1st_a_new_attempt_...` (+9 tests) | killed (13 errors) |
| `check_binding` compares whole bindings (`binding_identity` dropped, runs.py:791) | `DriverTests.test_a4_a_home_change_...` (+6 tests) | killed (7 errors) |
| `binding_changed` compares whole bindings | `PlanTests.test_a4_approve_and_override_...` | killed (1 failure) |
| `check_binding` projects a fixture binding | `DriverTests.test_a1st_a_new_attempt_...`, `tests.test_runs` | killed (1 failure, 25 errors) |
| `read_engine` drops the environment | `DriverTests.test_a2_logs_and_the_failure_cause_...` | killed (1 failure) |
| the prepared-unsent submission ignores the recorded home | `PlanTests.test_r4_...` | killed (1 failure) |
| the writer stores `codex_home(os.environ)` | `PlanTests.test_a1st_a_new_planning_revision_...` (+4 tests) | killed (5 failures) |
| `binary_identity()` gains `codex_home` (the producer, engine.py:1054) | `tests.test_record_home.ProducerTests.test_binary_identity_keeps_exactly_the_binding_fields` | killed (1 failure) |
| `binding_identity()` gains `codex_home` (the projection, engine.py:921) | `DriverTests.test_a1st_a_new_attempt_...` (+9 tests) | killed (13 errors) |
| approve/override use the current session root, not the frozen binding's | `PlanTests.test_a4_approve_and_override_...` | killed (1 error) |
| the fixture-setup probe is left unstubbed (no `engine.native_run` patch) | `DriverTests.test_a1st_a_new_attempt_...` (probe env not recorded) | killed (1 failure) |

## Size

Added lines before this receipt: 72 production (`engine.py` 63, `runs.py` 7, `planning.py` 2) + 501 test lines =
**573**; with the 26 deletions, **599** changed lines — below the 600-line re-gate trigger on both counts (the
round-3 candidate measured 618 added / 641 changed; the round-4 candidate 541 / 567). The band target is 200-450; the
excess over the band is the A-2 path matrix (eleven entry points, each with its own spy) and the two R-2 regressions.
No s2a3 work was absorbed; docstrings and comments were compacted, never the guards.

## Repair notes (this visit, vs the round-5 candidate)

- A-B/A-1st `TypeError`: `Homes.control_native` now records a probe that ran without an `env` as `{}` and
  `DriverTests.test_a1st_a_new_attempt_...` reads `.get("CODEX_HOME")`, so the base's env-less `recorded_engine`
  produces a clean assertion failure; that test's store assertions (the missing `codex_home`) now run *before* the
  probe one, so the base fails there. Verified: the base replay reports `failures=8, errors=7` with no `TypeError`,
  and the a1st attempt test fails at `set(binding) == BINDING_FIELDS | {"codex_home"}`. The base-replay section above
  was corrected accordingly (it had mis-classified the old TypeError as the missing stored `codex_home`).
- Mutation table: the two missing required rows are recorded — `check_binding` comparing whole bindings (killed by
  `DriverTests.test_a4_a_home_change_...`, 7 errors) and the same-binary home sibling taking the record's state root
  (killed by the same test, `Blocked not raised`) — and the whole table was re-measured this visit against the
  current candidate and test module.
- Base citations: the header now cites the base's own lines, read with `git show 6a537b5:<file> | grep -n`
  (engine.py:1049/:1103, runs.py:655/:789, planning.py:249), and labels the candidate's separately.

## Repair notes (round-4 findings, applied in the visit before this one)

- Acceptance finding 1 (R-2 crash on a recorded spelling that cannot be resolved): `engine_for` :963-966 now guards
  the alias `resolve()`; a spelling that cannot be resolved (a self-referencing symlink) is never taken for the
  acting binary, so the record takes the existing `toolchain.mismatch` refusal through `check_recorded` instead of a
  `RuntimeError` — on the candidate's `validate`, `submit`, `watch`, `status`, `force-stop`, `resume`, `check_binding`,
  `log_tail`, `log_records`, `failure_cause` and `proposal` paths. Valid-alias idempotence is unchanged
  (`test_r3_engine_for_is_idempotent_...`, `test_a2_a_detached_revision_...`): the alias row is still an ordinary
  four-field refusal, never a delegation loop. Two named regressions cover the two entry families and both fail
  under the unguarded-`resolve()` mutation.
- Acceptance finding 2 (wording): the module docstring and the interpretations below now say that an *older-toolchain*
  sibling uses the recorded root and version, while a same-binary home sibling keeps the acting engine's.
- Code finding 1 (`fixtures(codex_home=None)` hid the absent-key boundary): `fixtures` now takes an `OMITTED`
  sentinel — omitted means the recorded home, an explicit `None`/`""` is an env without, resp. with an empty,
  `CODEX_HOME` — and `test_a2_a_detached_revision_...` asserts the engine's own env *as built* (key absent for
  `None`, present and empty for `""`) before the invocation. The `with_home`-default mutation fails that test (row 2).
- Code finding 2 (unstubbed fixture-setup probe): `Homes.control_native` patches `engine.native_run` in both flow
  classes and records every env it is asked to run in in `self.setup_probes`; `DriverTests.test_a1st...` asserts
  those envs are the recorded home, so the `--version` probe that `RunsTest.approve_native` reaches through
  `Authority.approve` -> `recorded_engine` is controlled and inspected (the last mutation row shows the test fails
  when that patch is removed).
- Code finding 3 (A-4 override row): the corrupted `review_exhausted` row now calls `a.override(version, REASON)`
  instead of `a.approve(version)` and still asserts the store bytes are unchanged. Note, recorded for transparency:
  in that fixture the refusal is raised by the shared `validate_state` intent check (`Frozen goal/configuration/source
  изменены.`) before either entry's own body, so a scratch probe that removes `override`'s own `check_evidence` is
  not distinguished by this row (nor was it by the pre-fix form). `override`'s own body is covered positively in the
  same test by the older-toolchain row, which asserts its recorded home and PATH prefix.

## Left out / deferred

- `planning.planner_commands`/`unknown_lines` (planning.py:564-585) name the state dirs and the executable but no
  `CODEX_HOME`: follow-up, out of scope.
- s2a1's helpers, the architect continuation (s2a3), the default home/login/doctor (s2b) and telemetry (s2c) are
  untouched; no new `.begin(` call (R-5, `tests.test_lifecycle_guard` green); no credential file is read (R-7); no
  test starts a real `zeroshot`/`codex` (every `call`/`native_run` is a double, the two R-2 regressions included).
- Orchestrator-owned merge checks (the full suite, ~15 min; the Linux-host native/installed qualification) were not
  run here. The DoD command passed 520 tests in 670 s on the shell's Python 3.9.6 (re-run on this visit's candidate),
  and this visit's
  `tests.test_home_wiring` (the two R-2 regressions included) is green on Python 3.13.3 as well; on 3.13
  `Path.resolve()` no longer raises for a symlink loop, so the unguarded-`resolve()` mutation is only killed on
  3.9/3.11/3.12 — the guard itself is required and correct on all three.
- Environment note (product input for zplan, no source change involved): one DoD run reported 35 errors while its
  `TMPDIR=/tmp/zs-agent-XXXXXX` directory disappeared mid-run (it was gone when the run ended); the same command
  passed twice with `TMPDIR` outside that name pattern (520 tests, 679 s and 698 s). A scratch directory removed
  under a running suite is the only difference observed.

## Interpretations

Recorded in the module docstring of `tests/test_home_wiring.py`: a pre-0.5 record acts in the process home
(`setup.legacy_codex_home()`); the home comparison is against the engine's own stored env value (as stored, never
re-resolved, never filled in from the default); an alias executable spelling is an ordinary four-field refusal,
never a delegation loop, and a spelling that cannot be resolved takes `toolchain.mismatch`; a same-binary home
sibling keeps the acting engine's root and version, while an older-toolchain sibling uses the *recorded* root and
version and only adds the record's `codex/node_modules/.bin` PATH prefix; every A-1st/A-4 row freezes a literal
record of its own, so it fails on the base at its behavioral assertion, not on import.
