ds-scrub-paths — remove the owner's home directory from tests (P0 public export, docs/P0_AUDIT.md). Narrow mechanical task; first DeepSeek-worker run.

Change only tests/test_setup.py (~164-166) and tests/test_terminal_planner.py (~370): replace `~` with `/home/testuser` (same length) in these literals. The setup assertions measure the socket path length (`check_socket_path`, terminal_planner/engine.py:18; Linux limit < 108 bytes): a shorter home would let the long refusal paths pass the limit and stop testing the refusal, so the byte counts must stay exactly as they are; check each expected number against the new strings. Do not change product code or weaken an assertion. Nothing else in the repository changes.

Acceptance criteria:
- D-A1 `git grep -n ~ -- tests` prints nothing (exit status 1 = no match = pass).
- D-A2 The refusal tests still refuse: for each socket-length assertion state the byte count before and after (must be equal); tests.test_setup and tests.test_terminal_planner pass with ZPLAN_TEST_WHEELHOUSE=/tmp/zs-zplan/wheelhouse (name the interpreter).
- D-A3 The diff touches only the two test files.

critic ds-harness: NO-GO (6) -> fixes applied -> GO WITH CHANGES (1, applied) -> GO for this serial pilot; parallel groups only after its review.
critic ds-merge (session 01a14180): MERGE.
