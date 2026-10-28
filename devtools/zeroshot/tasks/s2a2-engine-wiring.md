s2a2-engine-wiring — 0.5 item S2, slice 2 of 3 of devtools/zeroshot/tasks/s2a-home-binding.md (the parent; its R-3, R-4 and A-1 store half, A-2, A-3, A-4, A-7 engine mutations apply verbatim where cited). Slicing: the Slices line of s2a1-home-core.md:5. Lane: Environment (L1). DeepSeek worker, sol reviewers. Critic gate5: GO WITH CHANGES (applied).

Base: main after the s2a1-home-core merge, and after s1a1a-gate-core has merged (it holds engine.py builders and authority.py helpers until then; s1a1a-gate-core.md:7). Lines below are cited at main e29f986. Record the base commit in the receipt, re-check every line on the base, and re-gate if a premise moved. First in the gate3 order s2a2 → s5a3a → s5a3b → s2b → s1a1b → s3a2 → s3a3 (~/zs-pause/critic/gate3.out point 6). Never concurrent with s1a1a or s1a1b (engine.py), s5a3a or s3a2 (runs.py `start`), or s5a3b (planning.py).

Uses s2a1's frozen interface exactly as stated in s2a1-home-core.md:14-16. It does not use the running candidate, which may be incomplete; on a mismatch on the base, stop and re-gate:
- `record_home.effective_home(recorded)`;
- `record_home.binding_home(binding)`: raises ValueError for an invalid or fixture binding;
- `setup.legacy_codex_home()`;
- `toolchain.valid_codex_home(value)`;
- `toolchain.valid_binding`, which accepts 4 keys, or 4 keys plus `codex_home`.

s2a1 keeps `binary_identity()` and `NativeDriver.binding()` at exactly four keys (s2a1-home-core.md:11, :22). This slice keeps those producers unchanged. It adds `codex_home` only at the two record writers.

Slices: s2a1 = pure home/binding core; s2a2 (this) = parent R-3, R-4, A-1 store half, A-2, A-3, A-4, A-7 engine mutations; s2a3 = architect continuation (R-5, R-6, R-8; A-5, A-6, A-7 architect mutations, A-8). R-7 holds in all three.

Observed at e29f986 (premise shifts from the parent's 19d1b8e audit):
- Writers:
  - planning: `binding = self.binary_identity()` engine.py:940, stored at :995;
  - milestone: `binding = self.driver().binding(a)` runs.py:655, `NativeDriver.binding` :1413-1415.
- Whole-binding compares:
  - `prepare` engine.py:941 (Stale or `engine.identity_changed` at :942-944);
  - `check_binding` runs.py:786-790 (`engine.binding(a) == r["binding"]`);
  - `binding_changed` planning.py:249 (`binary_identity() != binding`).
- `engine_for` engine.py:832-848 returns `self` on equal executable and version (:839-840). A sibling for another toolchain keeps `self.environment` plus a PATH prefix (:842-848).
- `native_environment` (:850-854) copies `self.environment`, or `os.environ` when it is None.
- `read_engine` (:1075-1087) rebuilds with `engine.environment`. It serves `log_tail` (:1089-1096) and `log_records` (:1098-1105).
- `failure_cause` uses `engine_for` (:1113).
- `recorded_engine` (:813-817) builds `NativeEngine(..., version=...)` with `environment=None`, so it runs in the process env. It is called by `Authority.approve`/`override` (authority.py:776, :806).
- `proposal` (:1001-1014) delegates through `engine_for` only when `run_id` is set (:1010-1013). A prepared but unsent revision is submitted by `self.prepare` on the current engine (:1014).
- Driver operations go through `engine_for`: validate :1423, submit :1432, watch :1438, status :1442, force_stop :1449, resume :1460. A resumed successor inherits `binding` through LINEAGE (runs.py:78-79).
- Engine construction: the CLI builds engines with `environment=` the setup env (cli.py:975, :982). `setup.native_environment()` sets `CODEX_HOME` = `codex_home(env)` (setup.py:228-233).
- Digests already include the binding: `intent_identity` (authority.py:580-581, `native_binding`) and the approval digest over the intent (:635-639). Record validation is by `valid_binding` (authority.py:521, runs.py:420). So authority.py needs no edit.

Write-set (exclusive, by symbol):
- engine.py:
  - `recorded_engine` (:813-817);
  - `NativeEngine.engine_for` (:832-848);
  - a new `NativeEngine.codex_home()` = `setup.codex_home(self.native_environment())`, plus a private sibling-with-home helper;
  - in `prepare`, the compare at :941 and the writer at :995;
  - in `proposal`, the prepared-unsent path (:1010-1014);
  - `read_engine` (:1082-1086) only if needed to keep the home.
- runs.py: `check_binding` (:786-790) and the binding line of `start` (:655).
- planning.py: `binding_changed` return (:249).
- new `tests/test_home_wiring.py`.
- Existing tests that assert a whole stored binding equals `binary_identity()`: only those assertions, each listed in the receipt.
- The receipt named in the DoD.

Not touched: authority.py, setup.py, toolchain.py, record_home.py, architect.py, tui/*, cli.py, catalog.py, docs.

Read:
- s2a-home-binding.md :5-10, :20-24, :36-43;
- s2a1-home-core.md :5, :7, :11, :14-16, :22;
- setup.py :209-233; toolchain.py :57, :67-72;
- engine.py :813-854, :911-925, :926-1014, :1075-1120;
- runs.py :60-79, :385-421, :607-673, :786-790, :1410-1465, :1493-1500;
- planning.py :233-249, :564-585;
- authority.py :510-524, :580-583, :635-639, :753-810;
- cli.py :960-985;
- tests/test_lifecycle_guard.py :73-99.

Rules:
- R-1 Writers (parent R-2 store, R-3).
  - A new planning revision (engine.py:995) stores `{**binary_identity(), "codex_home": str(self.codex_home())}`.
  - A new milestone attempt (runs.py:655) stores the driver binding plus `codex_home` of the driver's env.
  - `binary_identity()` and `NativeDriver.binding()` stay four keys.
  - Fixture bindings are unchanged.
  - Nothing in a record's lifecycle rewrites `codex_home`.
- R-2 Four-field identity (parent R-3).
  - The compares at engine.py:941, runs.py:789 and planning.py:249 project both sides on `toolchain.BINDING_FIELDS`, for native bindings only (gate5 point 4): `check_binding` keeps the exact comparison of a fixture binding (`{fixture_id}`), and a binding without `executable` is never projected.
  - A different home is never Stale or `engine.identity_changed`.
  - A change of executable, sha256, state_root or version stays detectable exactly as today.
- R-3 Recorded home (parent R-4). The record home is `binding_home(binding)`: the recorded value, or `legacy_codex_home()` for a 4-key binding.
  - `engine_for(binding)` returns an engine whose `native_environment()["CODEX_HOME"]` is that home. All other variables are the current env, plus the existing PATH prefix for another toolchain.
  - `engine_for` returns `self` only when executable, version and home all equal its own. The home comparison uses `str(binding_home(binding))` against the engine's own env value `native_environment()["CODEX_HOME"]` as stored, with no second `resolve()` of the recorded home (gate5 point 1). A recorded path with `..` or through a symlink differs from a freshly resolved `codex_home()`, so resolving would make every call build a new sibling.
  - Idempotence (gate5 point 1): `bound = engine.engine_for(binding)` implies `bound.engine_for(binding) is bound` for every native binding, including a recorded home with `..` and one through a symlink; `proposal` therefore delegates at most once.
  - Same binary, other home: a sibling with self's executable, state root and version, and only `CODEX_HOME` replaced. A changed state root therefore still surfaces through the four-field compare.
  - `engine_for` keeps returning `self` for a binding without an executable (fixture or None).
  - `recorded_engine(binding)` builds its engine with the current process env and `CODEX_HOME` = the record home.
  - `read_engine` keeps the home of `engine_for`.
  - A missing home directory is passed through as is: no substitute, no mkdir.
- R-4 Prepared but unsent revision (parent R-3).
  - When `proposal` submits a prepared revision (`native_prepared`, `run_id` None), it uses `engine_for(native_binding)` if the four fields equal this engine's identity.
  - A four-field difference still raises Stale through `prepare`, as today. An unprepared revision binds this engine's own home through R-1.
- R-5 Invariants:
  - No new `.begin(` call (tests/test_lifecycle_guard.py:73-99).
  - No credential file is read, copied or printed (R-7).
  - The default home, login and doctor are unchanged (s2b).
  - New tests fake `call`/Popen and never spawn `zeroshot` or `codex`.

Acceptance (deterministic setup):
- Spies on `call`, `native_run` and `live.tail`/`live.records` record the env of every `zeroshot` invocation.
- Temporary HOME and CODEX_HOME directories; no real provider.

Cases:
- A-1st (parent A-1, store half): a new planning revision (`prepare`) and a new attempt (`MilestoneRuns.start`) store `codex_home` equal to the engine env's home; fixture records store `{fixture_id}` only. The stored records pass `valid_binding`, and their intent/approval digests include `codex_home`.
- A-2 (parent A-2). Process env CODEX_HOME=B, record codex_home=A. Each of these spawns with CODEX_HOME=A:
  - validate, submit, watch, status, force-stop and resume;
  - the resumed successor's watch;
  - `log_tail`, `log_records`, `failure_cause` and planning observation;
  - `recorded_engine()` under `Authority.approve` and override revalidation;
  - submission of a prepared but unsent revision.

  The same paths with an older toolchain's binary (a `check_recorded`-valid fake) also use A, and keep the PATH prefix, except prepared-unsent submission (gate5 point 2). Its positive case requires the current engine's four fields to equal the frozen binding; another executable, version or state root still gives Stale through `prepare`, per R-4, and that negative case is a named test.
- A-3 (parent A-3):
  - A 4-key binding, with process env CODEX_HOME=L and an engine env CODEX_HOME=Z, spawns with L.
  - With CODEX_HOME unset in the process env, it spawns with `<test HOME>/.codex`.
  - Pre-0.5 records load and validate unchanged, and keep their digests.
- A-4 (parent A-4). Use separate fixtures:
  - a submitted milestone record;
  - an unsent prepared planning revision (`binding_changed`, `prepare`);
  - a proposed revision for approve;
  - a `review_exhausted` revision for override.

  Changing only the current home gives no Stale and no `engine.identity_changed`. Changing sha256 or state_root stays detectable, and what changes is fixed per fixture (gate5 point 3):
  - milestone record and unsent prepared revision: the current engine's state root (or sha256) changes; the record stays as frozen;
  - approve/override: the frozen `native_binding` is changed in the record without recomputing `intent`, and the refusal is the existing intent/identity check; changing only the current session's state root does not block approval, because `recorded_engine` deliberately uses the record's root (engine.py:817).
  A same-binary home sibling still detects a changed current state root.
  Edited existing assertions check the four identity fields and the recorded `codex_home` separately (gate5 point 4).
- A-B Base replay (parent A-7), base = this slice's base, where s2a1's helpers exist:
  - The A-1st, A-2, A-3 and A-4 cases drive existing entry points (`prepare`/`proposal`, `MilestoneRuns.start`, driver operations, `log_tail`, `failure_cause`, `approve`/`override`) with literal records. On the base they fail at their behavioral assertion (env CODEX_HOME=B, no `codex_home` stored, Stale on a 5-key record), not on import.
  - `NativeEngine.codex_home` and the sibling helper are candidate-only.
  - Compatibility cases (A-3 legacy load and digests) may pass on the base.
  - Report intended failures, compatibility passes and skips separately.
- Mutations, each killed by a named test:
  - From parent A-7: drop the recorded home in `engine_for`; drop it in `recorded_engine`; compare whole bindings in `check_binding`.
  - Also:
    - compare whole bindings in `prepare`, or in `binding_changed`;
    - `engine_for` returns `self` on equal binary despite another home;
    - the sibling takes the binding's state root on the same binary (hides a state-root change);
    - `read_engine` drops the environment;
    - the prepared-unsent submission ignores the recorded home;
    - the writer stores `codex_home(os.environ)` instead of the engine env's home;
    - `binary_identity()` gains `codex_home`;
    - `engine_for` compares the recorded home after `resolve()` (killed by the `..`/symlink idempotence tests);
    - `check_binding` projects a fixture binding;
    - approve compares the current session root instead of the frozen binding's.

Size: ~250-400 lines with tests (product ~60, tests ~250; target 200-450). Above 600, stop and re-gate; never absorb s2a3.

Out of scope:
- s2a1 helpers (unchanged);
- the architect session, chat header and `architect.home_lost` (s2a3);
- default home, login, doctor and profile (s2b);
- telemetry (s2c);
- the copy-paste diagnostics in `planner_commands`/`unknown_lines` (planning.py:564-585), which name state dirs but no CODEX_HOME: recorded in the receipt as a follow-up;
- authority.py;
- upstream changes.

DoD:
- `PYTHONPATH=.:tests python3 -m unittest tests.test_toolchain tests.test_reference tests.test_home_wiring tests.test_record_home tests.test_setup tests.test_runs tests.test_terminal_planner tests.test_milestone tests.test_plan_gate tests.test_plan_override tests.test_run_cause tests.test_live tests.test_lifecycle_guard` passes.
- Receipt devtools/zeroshot/tasks/s2a2-engine-wiring-receipt.md, containing:
  - base commit;
  - file list;
  - the edited existing assertions;
  - the A-2 path table (path, entry, test);
  - base-replay results;
  - the mutation table (mutation, killing test, result).
