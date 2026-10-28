# rel04-fixture-scope — receipt (release 0.4.0 class repair 2 of 2)

Base commit: `accec691b98854fd95e4d47343ac79454deedcdf` (main at the run start; the audit is at c242370, every
line number re-checked on this base). Runs in parallel with `rel04-lifecycle-guard` from the same base; the
lifecycle-guard overlap is `terminal_planner/authority.py`, `planning.py`, `runs.py` and `tests/test_tui_chat.py`
— this task touches none of those files, so the merge is expected to be clean and is checked by the orchestrator on
the merged candidate.

## Product (`terminal_planner` 139+/47-, net +92; docs 14+/1-)

- `terminal_planner/cli.py`: `valid_fixture_id` and a parser refusal immediately after `parse_args` and **before**
  `native_state_root()` / `attach_tools` / setup / session (repair, R-1); every `args.fixture` truthiness test
  replaced by `args.fixture is not None` (one `fixture = args.fixture is not None` local); `profile_command`
  distinguishes the fixture `accepted` case (refuses a second `profile init`) from the fixture `later` case
  (promotable) and never claims the absent project file exists; `App.bootstrap` shows the fixture accept line.
- `terminal_planner/process.py`: `Profile.fixture` (`authority.fixture_id is not None` / `fixture_id is not None`);
  `_snapshot_ok` extracted so an `accepted` record may carry a snapshot; `_accepted_record(resolved)` (repair,
  R-3) returns an `accepted` record carrying the snapshot for a fixture profile and no snapshot for a native one;
  `accept()` writes the snapshot into the fixture sidecar instead of the target's file (also when a file exists);
  `status()` resolves a fixture-accepted snapshot, adopts (heals) an existing snapshot-free `accepted` record with
  the file's snapshot, refreshes it when the file's digest moves, and finishes an interrupted `accepting` record
  with the snapshot; a fixture `accept()` from a genuinely missing profile re-records the proposal's snapshot
  instead of dereferencing the absent resolution.
- `terminal_planner/tui/__init__.py`: `ZplanApp(controller, architect=fixture_id is None)`.
- `terminal_planner/tui/app.py`: `CHAT_FIXTURE`, `architect` parameter, `chat_off`, `send_chat` returns the fixture
  line.
- `terminal_planner/tui/controller.py`: `fixture_id is not None` for the driver factory and worktrees.

## R-1 classification

Fixture mode is `fixture_id is not None` everywhere the CLI/session composition decides it (`cli.py` main, session,
status, profile_command, drivers, App.bootstrap; `tui/__init__.run`; `tui/controller.for_project`;
`process.Profile.of/peek`). `--fixture ''` and any invalid id (nonempty letters/digits/`-`/`_`) are refused by
`parser.error` immediately after parsing — **before `native_state_root()`**, before `attach_tools`,
`install_tools`, `choose_project` or any session, so no filesystem path resolution and no native-state probe runs
for a bad id (repair: the validation moved above the `args.native_state_dir = str(native_state_root())` block, so
the previous parse-order bug is gone). `Authority` still enforces the same rule; the check is duplicated at the
parse boundary on purpose (fail before I/O).

## Sinks skipped in fixture mode (R-2)

Reachable sinks at the audit point that a `--fixture ID` session no longer reaches (the A-1 spies assert all are
empty, and no production `architect` directory is created):

- `ArchitectChat` construction (`tui/app.py:1621` on the base) — never built; `send_chat`/`reset`/`retry_chat`
  return the refusal line and touch nothing.
- `ArchitectStore` construction and `transcript()` reads (the production chat history) — never reached; the store
  is built lazily by `ArchitectChat.prepare`, which no longer exists in the session.
- Provider turns (`architect.Architect` / a Codex turn on Enter) — never started.
- Tool-version probes `default_prepare -> setup.check_installation` / `adapter.verify_cli` (Zeroshot/Codex/restic)
  — never run.
- Production session/transcript/process-state writes — no write happens. The only new fixture write is the
  profile snapshot in the fixture sidecar (`<state>/v3/fixtures/<id>/<project_id>/process-state.json`), not
  production state.

Intended local effects that remain (not defects, per the task): fixture planning/run/process stores, local Git
refs/worktrees/merge, checker runs; no fetch/push/network transport.

## R-3 decision (fixture profile)

`<target>/zplan.process.json` is never created or modified in a fixture session. Accept in a fixture session
records the effective snapshot in the fixture sidecar as an `accepted` record **with** a snapshot (the shape a
`later` record already used). Repair: `_accepted_record` is now the single producer of that record, so **every**
fixture acceptance/adoption path retains the snapshot — including `accept()` over an **existing** file
(previously it wrote a snapshot-free `accepted` record) and the `status()` present branch when a file appears
(previously it erased the fixture snapshot with a snapshot-free record). `status()` resolves the snapshot so a
reopen reads `accepted`, never `missing` — the `accept -> plan -> reopen` flow stays usable without the file, and
stays usable after the file is removed again. A project file that appears later, or that changes, is adopted as
the source: the record is rewritten through `_accepted_record` with the file's digest **and** the fixture
session's refreshed snapshot, so a later deletion of that file still reads `accepted` from the snapshot (with the
adopted file's roles) instead of `missing` — the removed file's content is not lost. The rewrite happens only
when the file's digest differs from the record's (a matching digest leaves the record untouched); for a native
record `_accepted_record` carries no snapshot, so the native behaviour is unchanged (the base also just returned
`accepted` there). Asserted by
`tests/test_process.py::StateTests.test_later_then_file_created_then_accepted_keeps_the_fixture_snapshot`.
`process.py` gained `_snapshot_ok` because an `accepted` record carrying a snapshot was previously rejected as
corrupt.

Second repair (an existing fixture namespace an older build left behind, R-3/A-3). Three more paths wrote a
snapshot-free `accepted` record, so a fixture profile could still read accepted -> missing:

- `status()`'s present branch required an already-present snapshot, so an existing snapshot-free `accepted` record
  beside a valid file was never upgraded. Now a writable fixture session adopts the file's effective snapshot
  (`self.fixture and record["snapshot"] is None` -> `_accepted_record(resolved)`), whatever the digest; a
  matching digest with a snapshot still leaves the record untouched, and a native record (no snapshot) is
  untouched.
- The interrupted-accept recovery (`state == "accepting"` with the file written) wrote a snapshot-free accepted
  record. It now finishes through `_accepted_record` in a fixture session (the unreadable-file case keeps the old
  `digest(None)` record because there is no resolution to store).
- A fixture `accept()` from a genuinely `missing` profile (an older accepted record with neither file nor
  snapshot) dereferenced `status.resolved is None` and raised `AttributeError`. It now re-decides from the
  proposal, exactly like a production `init` from `missing`, and records the snapshot in the fixture state only —
  the target's file is never written.

A deleted profile is therefore only `missing` when the record carries no snapshot either; `test_process.py`'s
fixture flows model that state explicitly (`remove_accepted_file`), and native (no `--fixture`) deletion still
refuses (`test_process.py::StateTests` and the `GuardTests` file checks).

## A-6 base-failure report

Method: copy the worktree (excluding `.git`, `.tools`, `__pycache__`), restore the five product files from the base
commit, run `tests.test_fixture_scope`. Named failures on the base (product restored, tests new): **19 failures,
0 errors, 0 skips** (`Ran 21 tests ... FAILED (failures=19)`):

- A-1 (chat isolation): 2 failures, `fixture_id='demo'` and `'demo-2_x'` — `app.chat` is a real `ArchitectChat`
  (the `ChatSpy` records construction). `AssertionError: <ChatSpy> is not None`.
- A-2 (empty id): `--fixture '' setup` returns 0 (no `SystemExit`) and `install_tools` runs.
- A-2 (invalid id / plain-TUI entry): `bad/id`, `bad id` and `''` through the plain entry all return 0 — the base
  only refuses a truthy id for `setup`, not at the parse boundary.
- A-2 (native-state probe, repair): 4 failures (`test_a2_an_invalid_id_never_probes_the_native_state_path`,
  ids `''` and `bad/id` × commands `setup` and `None`) — the base calls `native_state_root` before the refusal, so
  the spy records a filesystem/native-state probe for every bad id. This is the R-1 reproduction the repair
  addresses.
- A-3 (`profile init`): the file is created (`AssertionError: True is not false`) and the message is the
  production one (`'fixture-состоянии' not found`).
- A-3 (bootstrap accept): the file is created.
- A-3 (snapshot retention, repair): 2 failures — `test_a3_accept_over_an_existing_file_keeps_the_snapshot_and_
  survives_its_removal` and `test_a3_a_file_that_appears_does_not_erase_the_fixture_snapshot` — the base loses the
  fixture snapshot on an existing-file accept and on a file appearing (R-3 reproduction). `..._profile_init_
  promotes_a_deferred_demo_profile` also fails on the base (the base falsely reports the absent file).
  `..._a3_profile_init_records_the_snapshot_and_creates_no_file` and `..._bootstrap_accept_...` fail on the base as
  in the description above.
- A-3 (existing namespace, second repair): 4 more failures — `..._an_existing_snapshot_free_acceptance_is_healed_
  and_survives_the_file`, `..._an_interrupted_fixture_accept_recovers_with_the_snapshot`,
  `..._an_interrupted_fixture_accept_after_a_defer_recovers_with_the_snapshot` and `..._profile_init_from_a_
  missing_demo_profile_writes_no_file_and_stays_usable` — the base never records a fixture snapshot at all, so a
  reopen after the file's removal reads `missing` (and `profile init` from `missing` writes the target's file).
  Under a surgical mutation of the candidate (only the three new guards disabled) the same four tests fail, the
  `profile init` one with the reviewer's `AttributeError`.

Passing on the base (positive controls, so the guard is not the docs or the counter): A-4 (production chat +
probes + file), A-5 (docs + generator), A-3 defer and A-3 existing-file (neither writes a new file on the base),
A-2 valid id. No skips in this module on this host (Textual 8.2.8 present); on a host without Textual the two
shell classes skip and the rest still run.

## Product/test split

- Product: `terminal_planner/cli.py`, `process.py`, `tui/__init__.py`, `tui/app.py`, `tui/controller.py`
  (139+/47-, net +92).
- Tests: new `tests/test_fixture_scope.py` (582 lines, **21 tests**: A-1..A-5, spies, composition helpers, the
  repaired R-1/R-3 boundary checks and the existing-namespace/interrupted-accept/init-from-missing regressions) and
  `tests/test_process.py` adapted to R-3 (fixture accept keeps the snapshot; the file-writing helpers moved to a
  production-mode `Profile`; `remove_accepted_file` models a genuinely missing fixture profile) — 81+/29-.
- Docs (R-5): `docs/REFERENCE.md:147` (`architect` sets model/effort per chat turn), `README.md` code map
  (`process.py`, `tui/chat.py`), `docs/USER_FLOW.md` new "Demo mode" section.

Targeted runs (scratch TMPDIR, `TMPDIR=/tmp/zsw-... PYTHONPATH=.:tests python3 -m unittest ...`):
`test_fixture_scope` 21 OK; `test_process` 88 OK; `test_tui`+`test_terminal_planner`+`test_setup`+`test_docs`+
`test_reference` 167 OK; `test_plan_gate`+`test_plan_override`+`test_plan_qual`+`test_tui_plan_gate`+
`test_layout` 114 OK; `test_tui_chat` 116 OK. The REFERENCE generator check
(`python3 -m terminal_planner.catalog --check docs/REFERENCE.md` -> `docs current`) is in `test_docs`/`test_reference`.
Full suite and the merge-tree gate are the orchestrator's.

Size note: product is within the 60–120 target; tests are above the 150–300 guide (582 new + 81 adapted), so the
combined change is past the 500-line re-gate point. Acceptance was not cut — A-1..A-6 are all covered; the size is
flagged for the orchestrator's re-gate decision.

## Interpretations (also in the test docstrings)

- "The chat key" (R-2/A-1) is read as the chat pane's state line: it shows the fixture refusal at startup and
  after Enter/reset/retry. The send key, `ctrl+r` and `App.retry_chat` are driven directly to show they add
  nothing else.
- "tools/login treated as available" (A-1) is read as fixture wiring asking readiness with `tools=False` and never
  installing or logging in; asserted through the recorded `cli.readiness` call.
- A-4 "production session" is read as the production wiring: a controller over the canonical Git authority (no
  `--state-dir`, no fixture id), the production `default_prepare` (probes run) behind the scripted codex, and
  `Profile.of` over a production `Authority` — the object the bootstrap accept writes.
- Empty/invalid ids are refused for the plain/TUI entry as well as `setup` (R-1 says "before setup/attach_tools or
  any other external I/O", which covers the entry).
- R-1's "before setup/attach_tools or any other external I/O" is read as **before `native_state_root()` too**: the
  refusal runs before the native-state default is computed, so no filesystem path is resolved for a bad id. This
  was the repair's R-1 cause (the previous order called `native_state_root` first).
- The `profile init` transition over a fixture session (task silence; raised as a spec gap) is read as: refuse only
  an already-`accepted` fixture profile, and promote a fixture `later` (deferred) profile — mirroring production
  `init` over `later` — instead of reporting the absent project file as existing.

## Acceptance -> tests (`tests/test_fixture_scope.py`)

- A-1: `FixtureChatIsolationTests.test_a1_a_fixture_shell_shows_the_disabled_chat_and_reaches_no_sink`
  (startup/Enter/reset/retry, `demo` + `demo-2_x`, all spies empty, no production `architect` dir, readiness
  `tools=False`, `install`/`login` None); `..._a_plain_fixture_session_has_no_chat_and_makes_no_sink`.
- A-2: `StartupRefusalTests.test_a2_an_empty_fixture_id_setup_is_refused_before_any_install`,
  `..._an_invalid_fixture_id_and_the_tui_entry_are_refused_before_the_session`,
  `..._an_invalid_id_never_probes_the_native_state_path` (repair, R-1),
  `..._a_valid_id_still_reaches_the_wiring`.
- A-3: `FixtureProfileTests.test_a3_profile_init_records_the_snapshot_and_creates_no_file`,
  `..._bootstrap_accept_keeps_the_snapshot_and_reopen_stays_usable`,
  `..._an_existing_project_file_is_refused_and_stays_byte_identical`, `..._a_fixture_defer_still_leaves_no_file`,
  `..._accept_over_an_existing_file_keeps_the_snapshot_and_survives_its_removal` (repair, R-3),
  `..._a_file_that_appears_does_not_erase_the_fixture_snapshot` (repair, R-3),
  `..._profile_init_promotes_a_deferred_demo_profile` (repair, spec gap),
  `..._an_existing_snapshot_free_acceptance_is_healed_and_survives_the_file` (repair 2, R-3),
  `..._an_interrupted_fixture_accept_recovers_with_the_snapshot` (repair 2, R-3),
  `..._an_interrupted_fixture_accept_after_a_defer_recovers_with_the_snapshot` (repair 2, R-3),
  `..._profile_init_from_a_missing_demo_profile_writes_no_file_and_stays_usable` (repair 2, R-3).
- A-4: `ProductionSessionTests.test_a4_production_chat_probes_and_the_profile_file`.
- A-5: `DocsTests.test_a5_the_reference_generator_check_passes`,
  `..._the_docs_state_the_fixture_chat_boundary`, `..._the_docs_markdown_stays_unbroken`.
- A-6: the base-failure report above (run on a scratch copy; deleted afterwards).

## Repair visit (phase.after = rejected)

Two demonstrated violations from the acceptance/code review, both fixed at the cause:

- **R-1 (validation order).** `cli.main` set `args.native_state_dir = str(native_state_root())` before validating
  `--fixture`, so every entry (TUI / plain / `setup`) resolved filesystem paths and probed the production
  native-state directory for `''` and invalid ids, and a `RuntimeError` (e.g. an `XDG_DATA_HOME` symlink loop)
  could win over the refusal. Fix: the `valid_fixture_id` refusal now runs immediately after `parse_args`, above
  the native-state defaults, so no path resolution and no native-state probe happens for a bad id. The new
  `test_a2_an_invalid_id_never_probes_the_native_state_path` spies `cli.native_state_root` and asserts zero calls
  for `''` and `bad/id` across `setup` and the default entry; it is red on the base (4 subcases) and green here.
- **R-3 (snapshot retention).** `process.Profile.accept()` over an existing fixture file wrote a snapshot-free
  `accepted` record, and `status()`'s present branch rewrote an existing fixture snapshot with a snapshot-free
  record when a file appeared — so `fixture accept -> plan -> remove project file -> reopen` degraded to
  `missing`. Fix: a single `Profile._accepted_record(resolved)` producer (fixture -> snapshot; native -> none) is
  used by both branches, and the present branch only rewrites when the file digest differs from the record's. New
  tests `..._accept_over_an_existing_file_keeps_the_snapshot_and_survives_its_removal` and
  `..._a_file_that_appears_does_not_erase_the_fixture_snapshot` are red on the base and green here.
- **Spec gap resolved (non-rejecting).** `cli.profile_command` for a fixture session now refuses a second
  `profile init` only when the fixture state is already `accepted`; a fixture `later` (deferred) profile is
  promotable, exactly like production `init` over `later`, and the message no longer claims the absent project
  file exists (`test_a3_profile_init_promotes_a_deferred_demo_profile`). The chosen transition is recorded in the
  module docstring, which both reviewers inspect.

No acceptance criterion was weakened; A-1..A-6 all still hold (targeted runs above). The base reproductions for
both violations are in the A-6 report above.

## Receipt correction (visit 3, phase.after = rejected)

Documentation only; no product change. The R-3 decision above said a different-digest project file that later
disappears reads `missing`; that contradicted the implementation (`process.py:580-593` retains the refreshed
snapshot and returns `accepted`, asserted by `tests/test_process.py`), so the sentence now describes the adopted
file's snapshot retention. The fixture sidecar filename is also corrected to `process-state.json` (the real
`STATE_FILE`), not `process.json`. Both reviewers' findings were documentation-only.

## Repair 2 (visit 4, phase.after = rejected)

Both reviewers rejected on the same R-3/A-3 class: an *existing* fixture namespace an older build left behind
(a snapshot-free `accepted` record beside a real file, or an interrupted `accepting` record) still degraded to
`accepted -> missing` when the file went away, and a fixture `profile init` from `missing` crashed with
`AttributeError`. Fixed at the cause in `process.py` (details in the R-3 section above): a writable fixture
session now adopts an existing snapshot-free `accepted` record with the file's effective snapshot, the
interrupted-accept recovery finishes through `_accepted_record`, and a fixture `accept()` from `missing`
re-decides from the proposal and records the snapshot in fixture state only (no file write, no crash).

Four deterministic regressions in `tests/test_fixture_scope.py` (raw-JSON sidecar oracles, independent of the
product's record helpers) cover the two reviewer reproductions, the interrupted accept with and without a nested
`previous` record, and the init-from-missing path. All four are red on the base (19 named failures across 21
tests, 0 errors, 0 skips) and red under a surgical candidate mutation that disables only the three new guards
(the init one with the reviewer's `AttributeError`). `tests/test_process.py`'s fixture flows that need a
genuinely missing profile now model it explicitly (`remove_accepted_file`); native deletion still refuses.

## Deferred to 0.5 (STATE Open; not acceptance here)

- The mandatory session scope object.
- The all-keys effect spy.
- The source-derived sink inventory.

## Product input for zplan (Zeroshot friction)

None this visit: the shared workspace, the scratch TMPDIR rule and the composition entry points worked as
described; no unclear contract or odd failure was hit.
