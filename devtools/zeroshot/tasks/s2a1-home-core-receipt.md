# s2a1-home-core — receipt (0.5 item S2, slice 1 of 3 of `s2a-home-binding.md`)

Base commit: `6e23523` (merge rel04-fixture-scope, the intended v0.4.0 tag target). Premises re-checked on that
base — every cited line number still holds, nothing moved:

- `setup.codex_home` :209-215, `legacy_codex_home` belongs beside it (R-1); `native_environment` :228-233 unchanged.
- `toolchain.BINDING_FIELDS` :57, `valid_binding` :67-72 (R-2), fixture binding path unchanged.
- Writers that compare whole bindings and stay unchanged here: `prepare` engine.py:675-676/:730, `check_binding`
  runs.py:773-777 (binding at :776), `binding_changed` planning.py:230-246; producers `binary_identity`
  engine.py:646-659 and `NativeDriver.binding` runs.py:1371-1373 both keep four fields (R-3).
- Read paths unchanged: `recorded_engine` engine.py:548-552, `engine_for`/`native_environment` engine.py:555-589,
  `validate_run` runs.py:403-407, `authority` :516-521, `tests/test_setup.py` :432-445.

## Files (write-set only; 250 added lines, target 200-450)

- `terminal_planner/toolchain.py`: new `valid_codex_home(value)` :67-71 and the widened `valid_binding` :74-85
  (4 keys alone, or 4 + `codex_home` satisfying `valid_codex_home`; any other key set invalid). R-2.
- `terminal_planner/setup.py`: new `legacy_codex_home()` :218-221 = `codex_home(os.environ)`, read at call time.
  R-1. Shared imports, `codex_home`, `native_environment` and `data_root` untouched (s5a1 owns `item`/`severity`/
  `doctor`).
- `terminal_planner/record_home.py` (new, 36 lines): `effective_home(recorded)` :15-22 (recorded path as is, no
  resolve/mkdir/existence check; `legacy_codex_home()` for `None`; ValueError otherwise) and `binding_home(binding)`
  :25-36 (`valid_binding` required, TypeError/AttributeError normalized to ValueError) — R-3.
- `tests/test_record_home.py` (new, 201 lines): `ShapeTests` (A-1s, base-replayable), `ResolverTests` (A-R),
  `ProducerTests` (A-C); interpretations recorded in the module docstring.
- R-4: no caller uses the new helpers; `git grep record_home terminal_planner/` finds only the new module.

## Acceptance evidence (scratch `TMPDIR=/tmp/zs-agent-a1`, `PYTHONPATH=.:tests`)

- DoD: `python3 -m unittest tests.test_record_home tests.test_toolchain tests.test_setup` → Ran 65, OK.
- `tests.test_record_home` alone → Ran 19, OK. New tests: A-1s = the 8 `ShapeTests` (4 keys, +home, 4096 accepted;
  4097 / empty / relative / tilde / NUL / None / int / bytes / other fifth key rejected); A-R = the 10
  `ResolverTests` (recorded A vs env B → A; 4-key + env L → L; unset → `<test HOME>/.codex`; missing dir returned
  unchanged with the parent listing unchanged; symlinked value never resolved; invalid recorded value, fixture
  binding, non-dict and `version=None` → ValueError; env changed between calls changes the legacy home);
  A-C = the 2 `ProducerTests`.
- A-C suites (unchanged): `tests.test_terminal_planner tests.test_runs` → Ran 132, OK (5 clean runs);
  `tests.test_plan_gate tests.test_plan_override tests.test_plan_qual` → Ran 88, OK;
  `tests.test_milestone tests.test_ux` (direct importers of `setup`/`toolchain`) → Ran 52, OK.
  One run of the first pair (run 1, tailed without `-v`, so the test name was lost) reported a single **error** on
  the untouched `engine.binary_identity` path (`authority.require` → `Blocked: Поддерживается только qualified
  static contract 10.12.0`); the five later runs of the same pair are green. No code this slice touches is on that
  path, and the failure is not reproducible.
- A-B base replay (`git archive 6e23523 | tar -x -C /tmp/zs-agent-a1/base`, new test file copied in):
  `python3 -m unittest tests.test_record_home.ShapeTests -v` → Ran 8, FAILED (failures=2):
  `test_shape_accepts_the_four_keys_plus_a_recorded_home` and
  `test_shape_accepts_a_4096_character_absolute_home`, both `AssertionError: False is not true` — the base
  `valid_binding` returns False; **no ImportError and no errors**. The candidate-only helpers are imported lazily
  inside their tests, so `ShapeTests` is the base-replayable section (also documented in the test module docstring).

## Mutations (candidate-only; copy at `/tmp/zs-agent-a1/mut2`, pristine copy restored after each)

Command per row: `PYTHONPATH=.:tests TMPDIR=/tmp/zs-agent-a1 python3 -m unittest <named test>` in the copy.

| Mutation | Killing test | Result |
| --- | --- | --- |
| accept any fifth key | `ShapeTests.test_shape_rejects_any_other_fifth_key` | rc=1, FAILED (2 failures) |
| accept a relative codex_home | `ShapeTests.test_shape_rejects_an_empty_or_relative_home` | rc=1, FAILED (2 failures) |
| drop the 4096 cap | `ShapeTests.test_shape_rejects_a_4097_character_home` | rc=1, FAILED (1 failure) |
| `binding_home` ignores the recorded value | `ResolverTests.test_a_recorded_home_wins_over_the_process_env` | rc=1, FAILED (1 failure) |
| `legacy_codex_home` returns `private_codex_home()` | `ResolverTests.test_a_four_key_binding_without_codex_home_uses_home_dot_codex` | rc=1, FAILED (1 failure) |
| `binary_identity()` adds `codex_home` | `ProducerTests.test_binary_identity_keeps_exactly_the_binding_fields` | rc=1, FAILED (1 failure) |
| `NativeDriver.binding()` adds `codex_home` | `ProducerTests.test_native_driver_binding_keeps_exactly_the_binding_fields` | rc=1, FAILED (1 failure) |
| `binding_home` lets a TypeError escape for `version=None` | `ResolverTests.test_malformed_native_fields_raise_value_error_not_type_error` | rc=1, FAILED (2 errors) |

## Interpretations (also in the test module docstring)

- `valid_binding` keeps its historical TypeError for malformed native fields (`version=None`): R-2 only widens the
  accepted key set, so the shape tests never assert a ValueError on that helper; `binding_home` is the boundary that
  normalizes it (R-3), pinned by a named test.
- "nonempty" for a recorded home is a nonempty str; whitespace-only values are not judged (no requirement names
  them).
- The fixture binding is refused by `binding_home` because the shape check refuses it — no fixture special case.

## Left out / deferred

- s2a2 (R-3/R-4 writers, `engine_for`, `recorded_engine`, four-field compares) and s2a3 (architect R-5/R-6/R-8);
  s2b, s2c; docs (R-8 catalog). R-7 holds vacuously here: nothing changes the default home, login or doctor, and
  no credential file is read.
- Orchestrator-owned merge checks (full suite) and the Linux-host installed checks (A-8) were not run here.

## Product input for zplan (Zeroshot friction)

None this visit: the shared workspace, the exclusive write-set and the scratch-TMPDIR rule worked as described; one
tailed (non-`-v`) batch run cost the name of a single unreproduced error (see A-C above) — a `-v` log is worth the
extra output on the first full-suite run.
