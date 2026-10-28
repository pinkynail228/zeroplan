# s1b1-check-executor — receipt

- Base commit: `c345b929619c055a8da1d7a756a356df13cfb892` (main); every line the brief cites was re-verified on it.
- Brief sha256: `72c3c9f0fde9b32d88fe0e60b5d3a331b1190dd6d598c0e90f65062738033003`.
- Files, all new; `git status --porcelain` lists exactly these three and `git diff --stat <base>` no existing file:
  `terminal_planner/checks.py` 226 lines, `tests/test_checks.py` 337 lines, this receipt 23 lines = 586 in total,
  under the 600-line re-gate threshold (the receipt counts; the earlier 596/620/798 claims excluded it and were rejected).
- Base replay: `checks.py` is new and nothing imports it, so no base-supported entry point exists and no test can fail
  on base through an existing path.
- Compatibility (Python 3.13.3, a private TMPDIR scratch): the candidate DoD run of `tests.test_checks tests.test_live
  tests.test_process tests.test_toolchain tests.test_reference` = 219 tests, 0 failures, 0 skips; the four pre-existing
  modules alone = 203 tests, 0 failures, 0 skips, the same on base — no named failure and no named skip.
- Mutations (each killed by a scratch-copy run of the named test in `tests/test_checks.py`; test names shortened):
  - (a) `shell=True` joined argv -> `test_an_argv_element_reaches_the_check_literally_without_a_shell`; (b) `process.kill()` for `os.killpg` -> `test_a_descendant_holding_the_pipe_does_not_extend_the_run`; (c) tree verification removed -> `test_a_wrong_tree_an_unknown_commit_and_a_bad_identity_are_refused_or_raised`
  - (d) cleanup only on success and (r) checkout root left locked -> `test_the_checkout_is_removed_after_every_path_including_a_locked_directory`; (e) line cap 201 / byte cap 32769 -> `test_the_caps_keep_the_last_lines_within_both_budgets`; (f) `scrub` skipped and (g) stderr to DEVNULL -> `test_captured_output_comes_from_both_streams_scrubbed_and_stripped`
  - (h) `timeout` counted as passed, (j) spawn failure as exit 127 and (p) spawn evidence without name/digest -> `test_pass_fail_timeout_and_spawn_failure_give_their_exact_evidence`; (i) checks in reverse order -> `test_checks_run_in_profile_order_and_qualify_returns_the_identities`
  - (i2) fail-fast removed -> `test_the_first_failure_stops_the_run_and_the_rest_are_not_run`; (k) `env=os.environ` -> `test_a_check_sees_only_the_sanitized_environment`; (l) reap skipped on interrupt -> `test_an_interrupt_kills_the_group_reaps_the_child_and_removes_the_checkout`
  - (m) rmtree without unlocking -> `test_the_checkout_is_removed_after_every_path_including_a_locked_directory`; (n) append-then-trim window -> `test_the_window_never_holds_more_than_64_kib_whatever_the_output`; (o) lowercase-only identity -> `test_a_hex_identity_is_accepted_in_either_case`
  - (q) partial-line drop removed -> `test_the_leading_partial_line_of_an_overflow_is_dropped`; (s) project path unresolved -> `test_the_checkout_holds_the_commit_tree_detached_from_a_relative_project`; (t) planted `from .checks import run_checks`, `from . import checks`, `import terminal_planner.checks` and `import checks` -> `test_no_production_module_imports_the_executor`
- Interpretations: "40-hex" is case-insensitive, so an uppercase identity is accepted and lowercased for the compare; a
  failed clone, detach or HEAD mismatch is `checkout` and only a landed HEAD with a different tree is `tree_mismatch`;
  `timeout_s` bounds the parent while `GRACE` bounds its leftover group; both caps drop whole lines from the front.
- Left to the orchestrator: the full Linux suite and the native/installed qualification (not run here, not claimed).
