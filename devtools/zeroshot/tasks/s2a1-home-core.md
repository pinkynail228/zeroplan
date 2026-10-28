s2a1-home-core — 0.5 item S2, slice 1 of 3 of devtools/zeroshot/tasks/s2a-home-binding.md (the parent; its R-* and A-* texts apply verbatim where cited). Lane: Environment (L1). Slicing: critic overnight05 point 3, swarm05 c (~/zs-pause/critic/). DeepSeek worker, sol reviewers. Critic split3: GO WITH CHANGES (applied).

Base: 6e23523 (C2, intended v0.4.0 tag target); record the base commit in the receipt; re-check every line number on the base and re-gate if a premise moved.

Slices: s2a1 (this) = pure home/binding core; s2a2 = engine wiring (R-3, R-4: writers, `engine_for`, `recorded_engine`, four-field compares; A-1 store half, A-2, A-3, A-4, A-7 engine mutations); s2a3 = architect continuation (R-5, R-6, R-8; A-5, A-6, A-7 architect mutations, A-8). R-7 holds in all three.

Write-set (exclusive): new `terminal_planner/record_home.py`; new `tests/test_record_home.py`; in `setup.py` only the new `legacy_codex_home()` next to `codex_home` (:209-215); in `toolchain.py` only `valid_binding` (:67-72) and a new pure `valid_codex_home(value)` next to it; the receipt named in the DoD. Nothing else. setup.py symbol ownership (critic split3): this slice only adds `legacy_codex_home`; shared imports, `codex_home`, `native_environment` and `data_root` stay unchanged (s5a1 owns `item`/`severity`/`doctor`); expanding these means re-gate.

Read: setup.py :209-233; toolchain.py :56-72; engine.py :548-589, :646-659, :675-676, :730; runs.py :407, :641-648, :773-777, :1371-1373; planning.py :231-246; authority.py :516-521; tests/test_setup.py :432-444.

Writers stay unchanged: `prepare` (engine.py:675-676), `check_binding` (runs.py:776) and `binding_changed` (planning.py:246) compare whole bindings with `binary_identity()`. Writing `codex_home` before s2a2 narrows them to four fields would make every new record Stale/`engine.identity_changed`. So `binary_identity()` and `NativeDriver.binding()` keep exactly four keys; no record gains `codex_home` here.

Rules:
- R-1 Legacy home: parent R-1 verbatim. `legacy_codex_home()` takes no argument and reads `os.environ` at call time.
- R-2 Shape: parent R-2 validator part only. `valid_codex_home(value)`: a str, nonempty, absolute, no NUL, at most 4096 characters. `valid_binding` accepts exactly BINDING_FIELDS, or BINDING_FIELDS plus `codex_home` satisfying `valid_codex_home`; any other key set is invalid. The fixture binding path is unchanged.
- R-3 Resolver (new, pure): `record_home.effective_home(recorded)` returns `Path(recorded)` for a valid recorded value as is (no resolve, mkdir or existence check), `legacy_codex_home()` for None, and raises ValueError otherwise. `record_home.binding_home(binding)` requires `valid_binding(binding)` and raises ValueError for every invalid binding (fixture binding included), also for malformed native fields such as `version=None`, a non-dict, or any value where `valid_binding` itself would raise TypeError/AttributeError: those are normalized to ValueError and returns `effective_home(binding.get("codex_home"))`. s2a2 and s2a3 (sessions) reuse it.
- R-4 No behaviour change: no caller uses the new functions yet.

Acceptance (temp HOME/CODEX_HOME; no network, provider or spawn):
- A-1s Shape (parent A-1, shape only): `valid_binding` accepts 4 keys and 4 keys + codex_home; a 4096-character absolute value is accepted; it rejects codex_home that is empty, relative, NUL-bearing, 4097 characters, or not a str (None, int, bytes), and any other fifth key.
- A-R Resolver: recorded A with process CODEX_HOME=B gives A; a 4-key binding with process CODEX_HOME=L gives L; with CODEX_HOME unset, `<test HOME>/.codex`; a recorded directory that does not exist is returned unchanged and nothing is created; an invalid recorded value and the fixture binding raise ValueError; changing os.environ between calls changes the legacy result.
- A-C Compatibility: existing toolchain, setup, engine, runs, planning, authority suites pass unchanged; named tests assert both producers keep exactly BINDING_FIELDS: `set(binary_identity())` with a fake `call`, and `set(NativeDriver(...).binding())` (engine.py :548-589) with a fake binding source.
- A-B Base replay: the 5-key acceptance cases of A-1s call the existing `valid_binding` and must fail on the base at the assertion (returns False), not on import: they live in a test class/module section that imports only the existing `toolchain.valid_binding`, so a base replay of just those cases runs without ImportError (new helpers are imported lazily or in a separate class). New-helper tests (`record_home`, `legacy_codex_home`, `valid_codex_home`) are candidate-only.
- Mutations (candidate-only, each killed by a named test): accept any fifth key; accept a relative codex_home; drop the 4096 cap; `binding_home` ignores the recorded value; `legacy_codex_home` returns `private_codex_home()`; `binary_identity()` adds codex_home (killed by the binary_identity producer test); `NativeDriver.binding()` adds codex_home (killed by the NativeDriver producer test); `binding_home` lets a TypeError escape for `version=None` (killed by a named ValueError test).

Size: ~150-300 lines with tests (target 200-450); above 600, stop and re-gate, never absorb s2a2.

Out of scope: s2a2, s2a3; s2b, s2c; docs.

DoD: targeted tests pass (`PYTHONPATH=.:tests python3 -m unittest tests.test_record_home tests.test_toolchain tests.test_setup`) + A-C suites; receipt devtools/zeroshot/tasks/s2a1-home-core-receipt.md with base commit, file list, base-replay result and mutation table (mutation, killing test, result).
