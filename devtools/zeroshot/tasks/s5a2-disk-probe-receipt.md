# s5a2-disk-probe — receipt

Slice 2 of 3 of `devtools/zeroshot/tasks/disk-guard.md` (parent R-1 mechanics, R-2, R-5; A-3, A-4, the
threshold half of A-2; plus `disk-guard-fix.md` S-3 where it concerns the probe). Pure module: no production
entry point is wired, so the only callers are the new tests.

**Base commit:** `e29f986aaafd7f069ddc38b2d74940ffe8acc466` (current main at launch, v0.4.0 + S4; `git rev-parse HEAD`).

## File list (write-set, exclusive)

- `terminal_planner/disk.py` — new (168 lines): `probe`, `threshold`, `classify`, `refusal`, the frozen
  `Probe`/`Verdict` records and the literals `GIB`/`WARN_GIB`/`DEFAULT_GIB`.
- `tests/test_disk.py` — new (371 lines): 37 tests, both seams scripted.
- `devtools/zeroshot/tasks/s5a2-disk-probe-receipt.md` — this file.

No existing file was edited. Size: 539 lines with tests (module 168), under the 600-line stop line; the growth
over the ~450 target is the per-test docstrings the acceptance review required plus the mutation coverage.

## Repair round (phase: rejected) — what changed

- Feedback 1 (real `os.stat` in two tests): both tests now use scripted seams — the deep-root test keeps the
  temporary tree only for the no-create listing snapshot and probes with `scripted_stat({base: 7})`; the NUL case
  uses `nul_stat`, a scripted `stat` that raises `ValueError` on an embedded NUL. No test reads the real
  `os.stat` or `shutil.disk_usage` (only `os.listdir` for the no-create check).
- Feedback 2 (interpretations in covering docstrings; wrong `threshold` claim): every test method now has a
  docstring stating the criterion/interpretation it covers; a new test
  `test_an_error_verdict_carries_no_threshold` asserts the chosen contract, and the module/test docstrings now say
  `threshold` is the block size only for the compared (`low`/`ok`) verdicts and `None` for `error` and
  `invalid_config`.
- Feedback 3 (A-B coverage): the mutation table below lists 30 mutations and, per mutation, the exact tests it
  kills, verified by running the whole `tests.test_disk` under each mutation with bytecode generation disabled
  (`python3 -B`, `PYTHONDONTWRITEBYTECODE=1`, no `__pycache__`) in a scratch copy. Union of killed tests = all 37.

## Premise re-check on the base (cited at `07e8285`)

Every premise holds; only line numbers drifted after S4 (the code moved, its meaning did not):

- `setup.py` `data_root`/`native_state_root` still call `.resolve()` (now `:28`, `:36`), so a callable root
  source can itself raise — the reason `probe` treats a failing source callable as that root's error.
- `runs.py` worktree default is still `data_root()/"worktrees"` (now `:583`).
- `authority.py` `common_directory` (`:127`) and `Authority.directory` (`:349`/`:352`) unchanged in meaning.
- `engine.py` `NativeEngine.state_root` still exists and is resolved (now `:825`).
- `tests/test_reference.py` still requires every raised family to have a catalog entry (`ErrorFamilyTests`) —
  the reason this slice raises no family: `terminal_planner/disk.py` has no `raise` of its own (only one bare
  re-raise inside `_existing_ancestor`), no `require`, and no new catalog id. `tests.test_reference` passes.

## A-2t — thresholds (block 5 default / overrides / long values / error probes)

| Case | Test | Result |
| --- | --- | --- |
| 5 GiB−1 block, 5 GiB warn, 15 GiB−1 warn, 15 GiB ok, 15 GiB+1 ok | `BoundaryTests.test_default_block_five_bounds` | pass |
| block evaluated before warn | `BoundaryTests.test_block_is_evaluated_before_warn` | pass |
| equality not below block (`<=`) | `BoundaryTests.test_equality_is_not_below_the_block_threshold` | pass |
| equality not below warn (`<=`) | `BoundaryTests.test_equality_is_not_below_the_warn_threshold` | pass |
| override 3 (<15): 3 GiB−1 block, 3 GiB warn | `BoundaryTests.test_override_below_fifteen` | pass |
| override 20 (>15): 20 GiB−1 block, 20 GiB and 20 GiB+1 ok | `BoundaryTests.test_override_above_fifteen_has_no_warn_band` | pass |
| 5000 nonzero ASCII digits → that exact int, no ValueError | `ThresholdTests.test_a_5000_digit_value_is_that_exact_integer_without_overflow` | pass |
| the conversion never calls `int` on the whole digit string | `ThresholdTests.test_the_conversion_never_calls_int_on_the_whole_digit_string` | pass |
| 5000 leading zeros + `5` → 5 | `ThresholdTests.test_five_thousand_leading_zeros_then_five_is_five` | pass |
| source-callable error → class-name-only error Probe | `ProbeTests.test_a_source_callable_error_is_an_error_probe_with_only_the_class_name` | pass |
| stat error → error Probe (abspath, ancestor `""`, device `None`) | `ProbeTests.test_a_stat_error_is_an_error_probe_after_the_path_is_computed` | pass |
| stat ValueError (NUL) → error Probe | `ProbeTests.test_a_stat_value_error_such_as_a_nul_path_is_an_error_probe` | pass |
| usage error → one error Probe; later root joins; `usage` called once | `ProbeTests.test_a_usage_error_makes_one_error_probe_that_later_roots_join` | pass |

## A-3 — ancestors, dedupe, error-plus-low

| Case | Test | Result |
| --- | --- | --- |
| root three levels below its ancestor → that ancestor; temp tree unchanged, no create | `ProbeTests.test_a_deep_root_resolves_to_its_existing_ancestor_without_creating_anything` | pass |
| two roots one device → one Probe naming both, one `usage` call | `ProbeTests.test_two_roots_on_one_device_share_one_probe_and_one_usage_call` | pass |
| dedupe by `st_dev`, not ancestor path | `ProbeTests.test_device_dedupe_is_by_st_dev_not_by_ancestor_path` | pass |
| two devices → two Probes | `ProbeTests.test_two_devices_give_two_probes` | pass |
| a callable source supplies the path | `ProbeTests.test_a_callable_source_is_called_for_its_path` | pass |
| a root error does not stop the other roots | `ProbeTests.test_a_stat_error_does_not_stop_the_other_roots` | pass |
| stat PermissionError + another device at 1 GiB → low block, failing root a warn error | `PermissionAndLowTests.test_a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device` | pass |
| source PermissionError + another device at 1 GiB → same | `PermissionAndLowTests.test_a_source_permission_error_plus_a_low_device_blocks_on_the_low_device` | pass |
| refusal: first block wins, invalid_config precedes low, error never hides a block | `RefusalTests.*` (4 tests) | pass |

## A-4 — override grammar

| Case | Test | Result |
| --- | --- | --- |
| `""`, `" 5"`, `"5 "`, `"+5"`, `"-1"`, `"0"`, `"000"`, `"1.5"`, `"5.0"`, `"1e3"`, `"nan"`, `"inf"`, `"-inf"`, `"５"`, `"٥"`, `"five"` → None | `ThresholdTests.test_invalid_values_are_none` | pass |
| each invalid value → leading `invalid_config` block with no path | `InvalidConfigTests.test_every_invalid_override_leads_with_invalid_config` | pass |
| invalid config still classifies the probes against the default 5 | `InvalidConfigTests.test_invalid_config_keeps_the_probe_verdicts_against_the_default` | pass |
| unset → 5 | `ThresholdTests.test_unset_override_is_five` | pass |
| `"5"`, `"0000000005"`, `"16"`, `"2000000000"` → 5, 5, 16, 2000000000 | `ThresholdTests.test_a_valid_positive_ascii_integer_is_taken_exactly` | pass |
| `environ` defaults to `os.environ` at call time | `ThresholdTests.test_the_environment_defaults_to_os_environ_at_call_time` | pass |

## A-B base replay

None: `terminal_planner/disk.py` is a new module and no production entry point is touched (wiring is s5a3). All
37 tests are candidate-only, and the union of the mutations below kills all 37.

## Mutations (each applied once to a scratch copy of `terminal_planner/disk.py`; whole `tests.test_disk` run under it)

Server note: the host Python is 3.9.6, which has no `int` string-digit limit. The mechanism is still guarded
portably by `test_the_conversion_never_calls_int_on_the_whole_digit_string` (a `builtins.int` spy), so T4 is
killed on 3.9 as well as on 3.11+.

| Mutation | Killed | Killing tests (unqualified names; `tests.test_disk.*`) |
| --- | --- | --- |
| T1 int(value) on the raw string | 5 | `a_leading_sign_or_space_is_rejected`, `every_invalid_override_leads_with_invalid_config`, `invalid_values_are_none`, `non_ascii_digits_are_rejected`, `the_conversion_never_calls_int_on_the_whole_digit_string` |
| T2 str.isdigit instead of ASCII digits | 3 | `every_invalid_override_leads_with_invalid_config`, `invalid_values_are_none`, `non_ascii_digits_are_rejected` |
| T3 leading zeros rejected | 5 | `a_valid_positive_ascii_integer_is_taken_exactly`, `every_invalid_override_leads_with_invalid_config`, `five_thousand_leading_zeros_then_five_is_five`, `invalid_values_are_none`, `leading_zeros_are_allowed_and_converted` |
| T4 chunked conversion replaced by int() | 1 | `the_conversion_never_calls_int_on_the_whole_digit_string` |
| T5 the unset default is 6 | 1 | `unset_override_is_five` |
| T6 the environment frozen at import | 1 | `the_environment_defaults_to_os_environ_at_call_time` |
| T7 off-by-one on the returned value | 6 | `a_5000_digit_value_is_that_exact_integer_without_overflow`, `a_valid_positive_ascii_integer_is_taken_exactly`, `five_thousand_leading_zeros_then_five_is_five`, `leading_zeros_are_allowed_and_converted`, `the_conversion_never_calls_int_on_the_whole_digit_string`, `the_environment_defaults_to_os_environ_at_call_time` |
| B1 <= at the block threshold | 4 | `default_block_five_bounds`, `equality_is_not_below_the_block_threshold`, `override_above_fifteen_has_no_warn_band`, `override_below_fifteen` |
| B2 <= at the warn threshold | 2 | `default_block_five_bounds`, `equality_is_not_below_the_warn_threshold` |
| B3 warn evaluated before block | 8 | `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device`, `an_error_does_not_hide_another_devices_block`, `block_is_evaluated_before_warn`, `default_block_five_bounds`, `invalid_config_keeps_the_probe_verdicts_against_the_default`, `override_below_fifteen`, `the_first_block_wins` |
| C1 an error probe classified ok | 4 | `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device`, `an_error_does_not_hide_another_devices_block`, `an_error_probe_is_a_warn_of_kind_error_with_the_class_name` |
| C2 block size forced to the default | 6 | `every_invalid_override_leads_with_invalid_config`, `invalid_config_keeps_the_probe_verdicts_against_the_default`, `invalid_config_precedes_a_low_block`, `low_and_ok_verdicts_carry_the_effective_threshold`, `override_above_fifteen_has_no_warn_band`, `override_below_fifteen` |
| C3 error verdict carries the block size | 1 | `an_error_verdict_carries_no_threshold` |
| IC1 invalid_config severity warn | 3 | `every_invalid_override_leads_with_invalid_config`, `invalid_config_keeps_the_probe_verdicts_against_the_default`, `invalid_config_precedes_a_low_block` |
| IC2 invalid config drops the probe verdicts | 1 | `invalid_config_keeps_the_probe_verdicts_against_the_default` |
| IC3 invalid_config appended last | 3 | `every_invalid_override_leads_with_invalid_config`, `invalid_config_keeps_the_probe_verdicts_against_the_default`, `invalid_config_precedes_a_low_block` |
| R1 refusal returns the last block | 2 | `invalid_config_precedes_a_low_block`, `the_first_block_wins` |
| R2 refusal returns the first non-ok verdict | 3 | `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device`, `an_error_does_not_hide_another_devices_block` |
| R3 refusal returns verdicts[0] | 5 | `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device`, `an_error_does_not_hide_another_devices_block`, `no_block_is_none`, `the_first_block_wins` |
| P1 stop probing at the first root error (stat) | 2 | `a_stat_error_does_not_stop_the_other_roots`, `a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device` |
| P2 stop probing at the first root error (source) | 2 | `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `an_error_does_not_hide_another_devices_block` |
| P3 a source error aborts the probe (re-raise) | 3 | `a_source_callable_error_is_an_error_probe_with_only_the_class_name`, `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `an_error_does_not_hide_another_devices_block` |
| P4 a stat error aborts the probe (re-raise) | 4 | `a_stat_error_does_not_stop_the_other_roots`, `a_stat_error_is_an_error_probe_after_the_path_is_computed`, `a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device`, `a_stat_value_error_such_as_a_nul_path_is_an_error_probe` |
| P5 a callable source is not invoked | 4 | `a_callable_source_is_called_for_its_path`, `a_source_callable_error_is_an_error_probe_with_only_the_class_name`, `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `an_error_does_not_hide_another_devices_block` |
| P6 a usage error does not register the device | 1 | `a_usage_error_makes_one_error_probe_that_later_roots_join` |
| P7 mkdir(parents=True) of a missing root | 10 | `a_deep_root_resolves_to_its_existing_ancestor_without_creating_anything`, `a_source_permission_error_plus_a_low_device_blocks_on_the_low_device`, `a_stat_error_does_not_stop_the_other_roots`, `a_stat_error_is_an_error_probe_after_the_path_is_computed`, `a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device`, `a_usage_error_makes_one_error_probe_that_later_roots_join`, `an_error_does_not_hide_another_devices_block`, `device_dedupe_is_by_st_dev_not_by_ancestor_path`, `two_devices_give_two_probes`, `two_roots_on_one_device_share_one_probe_and_one_usage_call` |
| P8 dedupe by ancestor path instead of st_dev | 3 | `a_usage_error_makes_one_error_probe_that_later_roots_join`, `device_dedupe_is_by_st_dev_not_by_ancestor_path`, `two_roots_on_one_device_share_one_probe_and_one_usage_call` |
| P9 all roots merged into one probe | 1 | `two_devices_give_two_probes` |
| P10 never dedupe by device | 3 | `a_usage_error_makes_one_error_probe_that_later_roots_join`, `device_dedupe_is_by_st_dev_not_by_ancestor_path`, `two_roots_on_one_device_share_one_probe_and_one_usage_call` |
| P11 a stat error probe drops the computed path | 1 | `a_stat_error_is_an_error_probe_after_the_path_is_computed` |

All 30 mutations were killed; the union is all 37 tests (no test left uncovered).

## DoD commands and results

```
SC=$(mktemp -d /tmp/zs-agent-XXXXXX)
TMPDIR=$SC PYTHONPATH=.:tests PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest tests.test_disk -v          # 37 tests, OK
TMPDIR=$SC PYTHONPATH=.:tests PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest tests.test_toolchain tests.test_disk tests.test_reference  # 96 tests, OK (68s)
```

Mutations ran in a scratch copy (`shutil.copytree` of the checkout, `.git`/`.tools`/`__pycache__` ignored), never
in the shared worktree; the copy was deleted afterwards.

## Interpretations recorded (also in the covering tests' docstrings)

- `Verdict.threshold` is the effective block size in GiB for the compared (`low`/`ok`) verdicts only; it is
  `None` for the `error` verdict (no free value was compared) and for the leading `invalid_config` verdict (no
  valid size). The invalid_config verdict has no names, no path (`""`), `free=None`.
- An error `Probe`'s `ancestor` stays `""` and its `device` is `None` when no `stat` ever succeeded (a source,
  `abspath` or `stat` failure); a `usage`-failure `Probe` keeps the first root's `path`/`ancestor`/`device`.
- Output order is the first appearance of each device (or each standalone error root) in the input root order;
  names within one `Probe` keep input order.
- The int-digit-limit guard is asserted as a mechanism (no `int(str)` sees the whole string) so it is
  host-independent.

## Deliberately left out (s5a3 or later)

Which roots are probed, readiness items/texts, catalog families `disk.low`/`disk.invalid_config`/`readiness.disk`,
the admission guard, doctor/UI texts, README code map and docs, cleanup (S5b), devtools run.sh.
