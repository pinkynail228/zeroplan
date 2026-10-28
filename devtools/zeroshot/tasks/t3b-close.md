T3b — close 0.8.0: the 0.7.0 launcher stays ours, two stale tests

T3 (merged c2bb5d0) bumped the version to 0.8.0; the whole Mac suite on it fails only the two tests below, both
reproduced on main fcf77df before T3. Small run: change only what each criterion names.

Write-set: install.py, tests/test_install.py, tests/test_task_gate.py, tests/test_tui_split.py

Acceptance criteria:
- B1 install.OWNED lists "0.7.0" (the bump replaced VERSION "0.7.0" by "0.8.0", so a 0.7.0 -> 0.8.0 install would
  raise "Existing zplan is not owned by this installer" on the 0.7.0 launcher). tests/test_install.py asserts it
  beside the 0.6.3 line, and an existing install test that swaps an owned launcher covers a 0.7.0 one.
  Example: with ~/.local/bin/zplan -> app/0.7.0/bin/zplan, the 0.8.0 installer backs up the store, prints the
  0.7.0 app as the rollback target and swaps the launcher.
- B2 tests/test_task_gate.py OffIdenticalTests: re-pin GOLDEN "preview" and "home" on the merged tree (its docstring
  already says T3 re-pins them); "revision" stays as it is; both configurations still compare to the same goldens;
  the docstring says where they were captured. Example: both OffIdenticalTests pass, and changing one word of the
  preview text in delivery.py fails both.
- B3 tests/test_tui_split.py: NEW["card_kinds"] lists the names D4c (6d64c95) and T2 added to card_kinds.py:
  COMMIT_STAT_LINES, LEGACY_AUTONOMY_LINE, commit_card_source, commit_key, commit_spec, with a one-line comment like
  the D1 one. Example: test_app_py_defines_none_of_the_moved_card_names_and_each_new_module_holds_them passes, and
  a new top-level name in card_kinds.py fails it.

Non-goals (reviewers must not require): other tests or docs; product changes beyond the OWNED tuple; a full suite.

Conflict rule: if a golden differs for a reason other than text (a persisted field changed), change nothing for it
and end with `conflict: <test> <evidence>`.

Risk: high (installer owned-launcher list). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_install tests.test_task_gate tests.test_tui_split tests.test_english`: exit 0; `python3 devtools/budget.py`: OK.
