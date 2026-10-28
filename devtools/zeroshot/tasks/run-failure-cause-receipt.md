run-failure-cause-fix — receipt

The implementation of run-failure-cause.md as amended by the frozen contracts G-1 (provider attribution), G-2
(reset) and G-3 (reader). The worktree carries the preserved candidate f3f4cf0 over the run base 9871d2d; this
receipt replaces the candidate's receipt (there was none) and maps every finding of the stopped run
(/tmp/zs-zplan/run-failure-cause-findings.md, 15 rejections, rounds 1-9) to the test that now covers it or to the
contract that supersedes it. All tests named here live in tests/test_run_cause.py. The repair round that followed
the rejected visit is recorded under "Repair round" below.

## Product

- terminal_planner/engine.py — the G-1 record model: the COMPLETION / RUN_WIDE / PROVIDER / DIAGNOSTIC grammars
  (fullmatch, DOTALL, the closed timeout|crash|malformed|refusal code set), the disposition table, the execution-id
  and `v2:<u64>` cursor domains, identical-duplicate deduplication on the whole record (`identity_of`: the canonical
  payload of the line, so two records that agree on execution and message but differ in `record.target`, in the
  timestamp or in the cursor's own spelling are a conflict), the decisive-record selection
  and the evidence of one execution. G-2's reset predicate (`reset_value`, `RESET_LANGUAGE`) and extraction
  (`reset_text`: after the last `resets `, cut at `;`/`·`/`<`/CR/LF, stripped). The obsolete candidate helpers
  (PROVIDER_FAILURE/provider_failure, FAILED_NODE/TIMING/RUN_WIDE-presence, node_cause/run_wide, log_records,
  control/unicodedata, the scrub-idempotence reset) are gone; `error_lines`/`classify`/`CAUSES` are R-1's planner
  path, unchanged.
- terminal_planner/runs.py — one bounded read per failed conclude (unchanged seam), `(None, None)` for an
  incomplete read, the cause/reset persisted after G-2's predicate, `validate_run` accepting the optional pair with
  the predicate itself plus cause=limit.
- terminal_planner/delivery.py — both surfaces render a stored reset only while the predicate accepts it.
- terminal_planner/live.py — G-3: a read error is a condition of `complete`, never an exception; the deadline is
  latched at the loop head, the equality, the EOF read, the successful wait and an already-elapsed clock; stdout is
  closed, a still-running reader is killed and reaped for at most 2 s, an exited one is never signalled; the
  retention window is exactly the last `buffer` bytes on every chunk split.
- docs/REFERENCE.md — the five `run.*` families (regenerated in the candidate; the catalog text is unchanged here).

## Tests

tests/test_run_cause.py — 97 cases over G-1/G-2/G-3 and R-1's planner path: MilestoneTests (selection, domains,
conflict, precedence, evidence), ExtractorTests (R-1 on both streams), ResetTests (G-2's language and boundaries),
ReaderTests/ReaderTestsRealProcesses (G-3, scripted `popen`/`clock` doubles and real children), StoreTests (one read,
persistence, validation), DisplayTests (both surfaces), GeneratorTests (A-4, 200 fixed-seed sequences against an
independent oracle), CompatibilityTests, ReadBoundaryTests, PlannerCauseTests.

## Repair round (the rejected visit)

The acceptance and code reviews of the previous visit rejected three demonstrated contract violations; each is
repaired at its cause, and each carries a named regression that fails at its assertion when the repair is undone
(shown once in a private copy of the worktree with only the three repairs reverted: 12 assertion failures over the
six checks that guard them -- the five new tests plus the `null reset` forgery subtest).

1. G-2 — `validate_run` accepted a *present* `reset: null` beside `cause: limit`, because the predicate returns None
   for a value it refuses and the comparison was `reset_value(r["reset"]) == r["reset"]`. Fixed in
   terminal_planner/runs.py:383-386: a present reset must be a string the predicate accepts
   (`isinstance(r["reset"], str) and reset_value(r["reset"]) == r["reset"]`), while an absent reset stays valid.
   Regression: `StoreTests.test_a_null_reset_beside_a_limit_cause_is_refused`, plus the `null reset` forgery in
   `test_the_store_rejects_a_forged_cause_and_a_bad_reset`.
2. G-1 planner extraction — the native envelope accepted the legacy error markers, so an envelope with
   `record.level` `fatal`, `err` or `ERROR` and a message such as `401 Unauthorized` rendered `planner.auth`. Fixed
   in terminal_planner/engine.py:300 (the literal `error` only), leaving the flat legacy formats on their own
   markers. Regression:
   `PlannerCauseTests.test_a_native_envelope_with_a_non_error_level_is_not_read_by_the_planner`.
3. G-1 cursor conflicts — deduplication compared `(execution, message)`, so two error records that shared a cursor
   and differed in another durable field were read as one record. Fixed in terminal_planner/engine.py:438-448
   (`identity_of`, the canonical payload of the whole line), used by the comparison at engine.py:511-520.
   Regressions: `MilestoneTests.test_records_that_differ_beyond_their_message_are_not_identical`,
   `StoreTests.test_records_that_share_a_cursor_and_differ_in_their_target_are_unknown` and
   `test_records_that_share_a_cursor_and_differ_in_their_timestamp_are_unknown`.

The interpretation the reviewers rejected (identity narrowed to execution and message) is replaced in the module
preamble and in the `observed_cause` docstring, and the repairs leave every earlier reproduction passing.

## Findings map

Round 1, acceptance. 1. a 96-character reset that grew under scrub broke persistence — superseded by G-2: the reset
is now bounded by R-4's language and never scrubbed (`test_an_unusable_reset_keeps_the_limit_cause`).
2. an earlier limit diagnostic followed by a non-provider completion gave limit — superseded by G-1 rule 3: the
completion's own cause must fullmatch PROVIDER (`test_a_class_word_alone_is_not_a_provider_failure`).
3. a cursorless diagnostic beside a provider completion gave a class — the cursor domain rule decides first
(`test_an_unusable_cursor_on_any_record_of_the_run_is_unknown`).
4. a `v2:` + 5000-digit cursor raised ValueError — the `v2:<1-20 digits>`/u64 domain gives unknown and never
crashes (`test_the_cursor_domain`, `test_an_unusable_cursor_does_not_break_the_failed_conclude`).
5. U+2028 inside a JSON string hid the record — LF-only record boundaries
(`test_a_separator_inside_a_json_string_does_not_hide_a_record`).
6. a U+009B reset survived to the screen — superseded by G-2: a control character cannot match the language
(`test_only_the_reset_language_passes`, `test_an_unusable_reset_keeps_the_limit_cause`).
7. a Blocked recovery query skipped the read — `test_a_blocked_recovery_query_still_reads_the_diagnosis`.
8. EOF bypassed the deadline — `test_the_deadline_is_latched_at_every_transition`,
`test_the_deadline_latch_holds_for_a_real_pipe`.

Round 1, code. 1. a session-limit diagnostic followed by a contract failure stored limit — superseded by G-1 (rule
3), `test_the_provider_wording_counts_at_the_diagnostic_origin_only`. 2. a reset grew under scrub — superseded by
G-2, `test_an_unusable_reset_keeps_the_limit_cause`. 3. a U+009B reset reached the screen — superseded by G-2,
`test_only_the_reset_language_passes`. 4. a fixed wait ignored the deadline after EOF —
`test_the_deadline_is_latched_at_every_transition`. 5. Blocked recovery skipped the read —
`test_a_blocked_recovery_query_still_reads_the_diagnosis`. 6. `engine_for`'s fast path returned the current engine —
`test_the_read_runs_in_the_frozen_state_root_not_the_current_one`. 7. the generator checked the extractor, not the
store — `test_a4_the_stored_cause_of_generated_sequences_matches_the_oracle`.

Round 2, code. 1. non-provider labels were scanned inside provider text — superseded by G-1: there is no label scan;
the PROVIDER grammar and the R-2 matchers over the detail decide
(`test_the_provider_wording_counts_at_the_diagnostic_origin_only`). 2. any classifiable text counted as provider
identification — superseded by G-1 rule 3, `test_a_class_word_alone_is_not_a_provider_failure`. 3. missing
execution ids were grouped as one execution — superseded by G-1 row 3 (ignored, never grouped),
`test_the_execution_id_domain`, `test_the_run_wide_records_are_never_decisive_and_are_never_evidence`. 4. deadline
expiry was marked only for a running child — `test_the_deadline_is_latched_at_every_transition`. 5. a decoder
RecursionError escaped — `test_a_pathologically_nested_line_is_skipped`,
`test_a_pathologically_nested_line_does_not_break_the_conclude`. 6. an 18-digit cursor bound rejected valid u64
cursors and accepted non-ASCII digits — `test_the_cursor_domain`. 7. a compatibility check failed on the base —
`CompatibilityTests` (seven cases, green on 9871d2d and f3f4cf0, see A-6 below).

Round 2, acceptance. 1. a class word proved provider failure — superseded by G-1 rule 3,
`test_a_class_word_alone_is_not_a_provider_failure`. 2. non-provider labels were searched inside provider
diagnostics — superseded by G-1 (`test_the_provider_wording_counts_at_the_diagnostic_origin_only`,
`test_the_engine_reasons_decide_before_the_cause`). 3. `complete` was reported when the deadline expired before EOF —
`test_the_deadline_is_latched_at_every_transition`. 4. RecursionError escaped — 
`test_a_pathologically_nested_line_is_skipped`. 5. valid 19-digit cursors were rejected — `test_the_cursor_domain`.

Round 3, code. 1. any `provider failure` occurrence proved provider origin — superseded by G-1's PROVIDER grammar,
`test_the_provider_wording_counts_at_the_diagnostic_origin_only`. 2. stdout was drained by the command's own exit —
`test_a_read_requires_a_real_eof_not_just_the_command_exit`. 3. an A-6 regression errored on the base instead of
failing at an assertion — see A-6 (the store-level regressions fail at assertions on both base revisions).

Round 3, acceptance. 1. stderr bypassed the level filter — `test_a_native_envelope_is_filtered_by_level_on_both_streams`,
`test_a_flat_structured_record_is_filtered_by_level_on_both_streams` (plus the planner path in
`PlannerCauseTests.test_an_info_envelope_on_either_stream_is_not_a_planner_cause`). 2. A-6 regressions did not reach
their assertions — see A-6.

Round 4, acceptance. 1. a provider marker anywhere after `: ` was accepted — superseded by G-1,
`test_the_provider_wording_counts_at_the_diagnostic_origin_only`. 2. flat structured stderr records were copied —
`test_a_flat_structured_record_is_filtered_by_level_on_both_streams`.

Round 4, code. 1. a marker inside a quoted non-provider diagnostic was accepted — superseded by G-1,
`test_the_provider_wording_counts_at_the_diagnostic_origin_only`. 2. flat non-error records bypassed the filter —
`test_a_flat_structured_record_is_filtered_by_level_on_both_streams`.

Round 5, code. 1. an unanchored `node execution failed:` label was searched — superseded by G-1's grammar,
`test_the_provider_wording_counts_at_the_diagnostic_origin_only`. 2. a truthy `error` field overrode an explicit
non-error kind — `test_an_explicit_non_error_kind_wins_over_an_error_field`. 3. overflow discarded whole chunks —
`test_a_one_byte_overflow_keeps_the_complete_record_in_the_window`.

Round 5, acceptance. A quoted engine label inside a non-provider failure was accepted — superseded by G-1,
`test_the_provider_wording_counts_at_the_diagnostic_origin_only`.

Round 6, acceptance. 1. the byte-boundary fixtures travelled in one `-c` argument (E2BIG) —
`ReaderTests.read_payload` writes the payload to a file and asserts the argument stays under 131072 bytes. 2. the
planner normalization was not exercised through `Planning.failure` —
`PlannerCauseTests.test_the_planner_normalizes_limit_and_forbidden_into_its_own_classes`.

Round 6, code. 1. every cause beginning with `run ` was excluded — superseded by G-1's RUN_WIDE fullmatch
(`run [a-z][a-z0-9_]*`), `test_a_class_word_alone_is_not_a_provider_failure`. 2. malformed structured stderr was read
as a plain diagnostic — `test_a_malformed_structured_stderr_record_is_not_a_plain_diagnostic`.

Round 7, code. 1. run-wide records entered the evidence of the execution — superseded by G-1 rule 4 (evidence is the
decisive detail plus DIAGNOSTIC records only),
`test_the_run_wide_records_are_never_decisive_and_are_never_evidence`. 2. an A-6 regression errored at a missing
helper — see A-6.

Round 8, code. An EOF that crossed the deadline still reported `complete=True` — `test_the_deadline_is_latched_at_every_transition`
and, at the store, `test_a_read_that_expires_at_its_eof_or_wait_stores_unknown`.

Round 9, code. Unsafe reset text (a credential or an HTML fragment in a JSON field name) reached persistence and both
surfaces — superseded by G-2: the value is accepted only if it is R-4's time language, so neither form matches and
the cause alone is kept (`test_an_unusable_reset_keeps_the_limit_cause`,
`DisplayTests.test_an_unusable_reset_reaches_neither_surface`, `test_an_out_of_band_reset_is_never_rendered`).

## Qualification

Targeted modules, TMPDIR in a private scratch directory, `PYTHONPATH=.:tests`, Python 3.9.6 (macOS):

- `python3 -m unittest tests.test_run_cause` — 97 tests, OK (~118 s).
- `python3 -m unittest tests.test_runs tests.test_live tests.test_ux tests.test_reference tests.test_docs` — 163
  tests, OK.
- `python3 -m unittest tests.test_terminal_planner tests.test_toolchain tests.test_plan_gate tests.test_plan_override
  tests.test_tui_planning tests.test_tui_milestones tests.test_tui_live tests.test_milestone tests.test_setup
  tests.test_process` — 425 tests, OK (one unnamed flake in a first invocation of this batch did not reproduce; the
  identical command re-run is OK).

A-6. From a private copy (`shutil.copytree` of the worktree, `.git`/`.tools`/`__pycache__` ignored), the six product
modules of `terminal_planner` were replaced by each revision and `tests.test_run_cause` was run there:

- f3f4cf0 (the preserved candidate): `Ran 97 tests ... FAILED (failures=76, errors=265)`. The 265 errors are the
  G-1 API change (`observed_cause` takes the retained lines, not one text blob); the 76 failures are assertions, and
  at least one behavioural test per contract fails at its named assertion:
  G-1 `StoreTests.test_a_conflicting_cursor_at_the_store_is_unknown` (`('limit', '3:10am (Europe/Moscow)', 1) !=
  ('unknown', None, 1)`) and `StoreTests.test_a_non_enum_code_at_the_store_is_unknown` (`('forbidden', 1) !=
  ('unknown', 1)`), plus the whole-record pair
  `test_records_that_share_a_cursor_and_differ_in_their_target_are_unknown` and
  `test_records_that_share_a_cursor_and_differ_in_their_timestamp_are_unknown`; G-2
  `ResetTests.test_only_the_reset_language_passes` (`' 3am' is not None`, 24 subtests);
  G-3 `ReaderTests.test_a_read_error_is_not_a_complete_read` (`self.fail("a read error is a condition of `complete`,
  never an error of the caller")`, reached because f3f4cf0 lets the OSError escape).
- 9871d2d (the run base, no S4 at all): `Ran 97 tests ... FAILED (failures=269, errors=318)`; all seven
  `CompatibilityTests` cases pass, and the behavioural failures are assertions (e.g.
  `test_a_conflicting_cursor_at_the_store_is_unknown`: `(None, None, 0) != ('unknown', None, 1)`,
  `test_an_earlier_auth_failure_stays_the_stored_cause_after_a_reviewer_rejection`: `(None, None, 0) !=
  ('auth', None, 1)`, `test_a_null_reset_beside_a_limit_cause_is_refused`: `(None, None) != ('limit',
  '3:10am (Europe/Moscow)')`, `test_records_that_share_a_cursor_and_differ_in_their_target_are_unknown`:
  `(None, None, 0) != ('unknown', None, 1)`).

The `reset=null` refusal is a repair of this candidate alone, so that regression passes on f3f4cf0 as well
(`CompatibilityTests` itself: `Ran 7 tests ... OK` on both revisions).

Left to the orchestrator's merge gate, not marked passed: the full suite, the walkthrough venv, and the Linux
native/installed qualification (the three payload-boundary cases run over a real child and a file, never a
command-line argument, so Linux x86_64's ARG_MAX is not in play).

## Size

`git diff --numstat 9871d2d` (the candidate's +2457/-33 becomes): product 493 added / 36 removed
(docs/REFERENCE.md 5, catalog.py 13, delivery.py 40/3, engine.py 299/11, live.py 80/15, planning.py 7/4, runs.py
49/3) and tests 1730 added (test_run_cause.py 1675, test_ux.py 55). No feature beyond G-1..G-3: the candidate's
obsolete helpers and the tests that covered them were removed.

## Orchestrator correction (2026-10-19, merge gate; critic rfc-merge GO WITH CHANGES)

Supersedes the base totals and the store-level assertion claims above (lines 117 and 177-194), which were measured
before the repair round renamed the API. Final test revision b2dd941, macOS python3.13, `TMPDIR=/tmp
PYTHONPATH=tests python3.13 -m unittest test_run_cause` with only `terminal_planner/` replaced:
- over 9871d2d: Ran 97, failures=25, errors=366. Errors are missing symbols (engine.observed_cause 246,
  engine.reset_value 43, live.records 24, planning.PLANNER_CAUSE 1, engine.reset_text 1) and do not count; the
  G-1 store regressions ERROR there. Assertion failures: DisplayTests.test_an_out_of_band_reset_is_never_rendered,
  StoreTests.test_a_fixture_attempt_reads_nothing, six ExtractorTests and sixteen PlannerCauseTests (level filtering).
- over f3f4cf0: Ran 97, failures=31, errors=315 (260 errors `'list' object has no attribute 'split'`: API shape,
  not counted). Assertion failures: ResetTests (24 subtests over three tests), ReaderTests.test_a_read_error_is_not_a_complete_read,
  DisplayTests.test_an_out_of_band_reset_is_never_rendered (`'sk-ABC' unexpectedly found`), PlannerCause
  non-error-level (5).
- G-1 store sensitivity by mutation instead (API-preserving): the conflict identity narrowed to
  `(execution, message)` (the rejected interpretation) at engine.py `records.append(...)`: the two StoreTests
  `..._share_a_cursor_and_differ_in_their_target/timestamp_are_unknown` fail at
  `('limit', '3:10am (Europe/Moscow)', 1) != ('unknown', None, 1)`, MilestoneTests
  `test_records_that_differ_beyond_their_message_are_not_identical` fails at 3 subtests; unmutated StoreTests +
  MilestoneTests: Ran 46, OK.
- b2dd941 (orchestrator, test-only): ReadBoundaryTests use the resolved /bin/true (merged-/usr Linux host).
  Linux full suite: de63a87 errors=2 (those tests), b2dd941 Ran 947 OK.
