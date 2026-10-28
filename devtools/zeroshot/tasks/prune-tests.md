PRUNE — speed up the bare-import check, fix the stale activation tests

Owner 2026-10-28: "overtesting". The audit (per-test coverage, sampled mutation, 20 re-inserted fixes, two
cold-start reviews; report in the pause dir, folder test-prune) found no safe mass deletion: tests sharing lines
still check distinct things. This run removes the largest single cost and the stale failures. Test-only change.

Write-set: tests/test_toolchain.py, tests/test_agent_activation.py

Acceptance criteria:
- P3 tests/test_toolchain.py: test_each_module_declares_the_same_tests_with_and_without_textual and
  test_every_test_module_imports_alone_without_textual_or_rich start one child per environment for all modules
  (today one child per module and environment: 75 s and 13 s); same oracle, and a failure still names the module.
  Example: a module-level `import textual` in tests/test_layout.py fails both tests naming test_layout; each test
  runs under 15 s.
- P4 tests/test_agent_activation.py: these fail on main since D6a (2188b60, zplan logs in and out only of the
  home it owns): AuthTests.test_a6_file_auth_verdicts_agree_in_doctor_preparation_and_a_resumed_turn,
  AuthTests.test_a6_only_unserved_file_auth_offers_the_login_key, AuthTests.test_a6_the_device_login_runs_in_the_private_home,
  FreshInstallTests.test_a4_a_fresh_install_never_uses_the_owner_codex_home,
  OverrideTests.test_a3_an_override_home_is_never_written_and_reaches_every_entry_point,
  OwnerHomeAliasTests.test_r1_a_private_home_symlinked_to_the_owner_codex_home_is_refused. Bring each to the D6a
  behaviour; the invariant each test names stays asserted. If the product, not the test, breaks the invariant:
  change nothing for that test and end with `conflict: <test> <evidence>`. Example: the alias test asserts the
  shipped refusal of a symlinked auth.json, not the old `setup.agent_home` text.
- P5 No other test is deleted or weakened. Example: `git diff main --stat` lists only the two files.

Non-goals (reviewers must not require): new tests; Russian text in tests (T3); product code.

Risk: high (P4 edits auth/home tests). DoD: run once, at the end:
`python3.13 devtools/fasttest.py tests.test_toolchain tests.test_agent_activation`: exit 0;
`python3 devtools/budget.py`: OK.
