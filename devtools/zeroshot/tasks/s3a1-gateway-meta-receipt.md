# s3a1-gateway-meta — receipt

0.5 item S3, slice 1 of `devtools/zeroshot/tasks/s3a-lanes.md` (Lane: Gateway; parent R-6 and A-5 apply verbatim
where cited). DeepSeek worker, sol reviewers. Critic split3 (swarm05 c, critic overnight05 point 3): GO WITH
CHANGES, applied. This slice adds the R-6 connection-metadata store check as a pure, unconnected module.

## Bases and contract

- **Base commit.** `6e23523a8be138fcfb848c9cbf6869ec74283604` (C2, intended v0.4.0 tag target). The run's own
  `git status --porcelain` was empty at start; the tree is unchanged except this slice's two new files.
- **Final tested tree.** `6e23523` plus `terminal_planner/connections.py` (new, 86 lines) and
  `tests/test_connections.py` (new, 241 lines). `git status --porcelain` shows exactly those two additions; no
  existing file is edited (the write-set is exclusive).
- **Pinned contract.** Zeroshot **10.12.0** (`terminal_planner/toolchain.py:48`), tag `v10.12.0` =
  `928de8ff918488749ca9d23e0a7349873401b7f7` in the shared upstream checkout. Verified with
  `git -C <upstream> show v10.12.0:<path>` (no checkout, no edits):
  - `crates/openengine-cluster-protocol/src/native_v2_target.rs:42-47` — `ConnectionScope {User, Org}`,
    `#[serde(rename_all = "snake_case")]` → `user`/`org`.
  - `.../native_v2_target.rs:150-163` — `ConnectionSummary {key, scope, kind, fields}` and
    `ConnectionListResult {connections}` (both `deny_unknown_fields`).
  - `zeroshot/src/native_v2_cli/local/connections.rs:38-48` — `list` returns key/scope/kind/field *names* only
    (`summary(key, values.field_names())`), never values.
  - `zeroshot/src/native_v2_cli/execution/connections.rs:26-34` — `write_json(output, &result)`: the JSON
    envelope on stdout.
  - `zeroshot/src/native_v2_cli/parser.rs:250-270` — `connection list` route, `scope` `default_value_t` =
    `User` (the enum's `#[default] User`); `:228-230` documents names-only and that org scope needs a hosted
    target. (The task cited this as `main/tests.rs:116`; the module is `native_v2_cli/tests.rs`, and line-number
    drift on a citation is not a contract mismatch — the behavior is confirmed at the source.)
- **Base check.** The parent's interim rule leaves gateway *dispatch* to s3a2/s3a3; this slice touches no
  production entry point and reuses no base behavior, so no premise moved on the base.
- **Repair (visit 2, after the reviewers' rejection).** R-3 scopes OSError mapping to `call`, but argument
  evaluation sat inside the guarded `try`, so an engine whose `native_environment()` raised OSError returned
  `unknown`/`io` with zero calls. `argv` and `environment` are now evaluated before the `try`
  (`connections.py:40-44`), and `test_engine_argument_errors_propagate_not_unknown` fixes the class. Both
  reviewers' reproductions pass unchanged otherwise.
- **Repair (visit 3).** The same class held for the `call` attribute itself: `engine.call(...)` was still looked
  up inside the guarded `try`, so an engine whose `call` property raised OSError before invocation returned
  `unknown`/`io`. The callable is now resolved before the `try` (`connections.py:41-46`, `invoke = engine.call`),
  and `test_engine_argument_errors_propagate_not_unknown` is extended to the `call`-lookup cell. Both reviewers'
  reproductions (environment and call lookup) are killed by that one named test.

## Change

- `terminal_planner/connections.py` — `connection_ready(engine, key, fields)` (R-1..R-5):
  - **R-2 call.** Exactly one `engine.call([engine.executable, "connection", "list"], capture_output=True,
    text=True, timeout=30, start_new_session=True, stdin=subprocess.DEVNULL, env=engine.native_environment())`.
    `argv`, `environment` and the `call` attribute are resolved before the `try`, so only a failure raised inside
    the resolved callable maps to `unknown` (R-3). Never `set`/`delete`; `connections.json` and `GATEWAY_*` policy
    are untouched (s3a3).
  - **R-3 parse.** `_summaries(envelope)` validates the `ConnectionListResult` envelope and every summary
    (`key`/`scope`/`kind` str, `fields` list of str) before any membership check; any violation makes the whole
    result `unknown` (`schema`). Nonzero exit → `exit`; `TimeoutExpired` → `timeout`; `OSError` from `call` →
    `io`; non-str stdout or a decode failure (`ValueError` incl. `JSONDecodeError`, `UnicodeError`,
    `RecursionError`) → `decode`. No bare `except`: any other exception from `call` propagates.
  - **R-1/R-4 decision.** Returns `Connection(state, detail)`; `ready` iff some summary lists `key` in scope
    `user` with `set(fields) <= listed fields`, else `missing`. No family is raised (a family needs a catalog
    entry), so s3a3 maps `missing`→`lane.connection_missing`, `unknown`→`lane.connection_unknown`.
  - **R-5 detail.** A closed label set: `""`, `missing`, `exit`, `timeout`, `io`, `decode`, `schema`; never an
    exit code, stdout or stderr text.
- `tests/test_connections.py` — A-5/A-V with a fake `call` spy (records argv, kwargs, env), temp state roots,
  no binary/network/adapter/port 8797. 28 tests; the `check` helper enforces "exactly one `connection list`,
  timeout 30, `ZEROSHOT_STATE_DIR=<state_root>/runs`" on every case.

## Acceptance

- A-5 store check (`unknown` standing for `lane.connection_unknown`): ready with exact fields and with extra
  fields, ready when only one of several summaries matches → `test_ready_with_exact_fields`,
  `test_ready_with_extra_fields`, `test_ready_when_only_one_of_several_summaries_matches`; missing key, empty
  store, missing field, org scope → `test_missing_key_is_missing`, `test_empty_store_is_missing`,
  `test_missing_field_is_missing`, `test_org_scope_is_missing`; unknown for non-JSON, non-object envelope, a
  missing or non-list `connections`, a wrong-typed key/scope/kind/fields, a non-str field element, a nonzero
  exit, a timeout, an OSError and a non-str stdout →
  `test_non_json_is_unknown_decode`, `test_non_object_envelope_is_unknown_schema`,
  `test_missing_connections_is_unknown_schema`, `test_non_list_connections_is_unknown_schema`,
  `test_wrong_type_key_is_unknown_schema`, `test_wrong_type_scope_is_unknown_schema`,
  `test_wrong_type_kind_is_unknown_schema`, `test_wrong_type_fields_is_unknown_schema`,
  `test_non_str_field_element_is_unknown_schema`, `test_nonzero_exit_is_unknown_exit`,
  `test_timeout_is_unknown_timeout`, `test_oserror_is_unknown_io`, `test_non_str_stdout_is_unknown_decode`.
  Every case asserts exactly one `connection list` with `timeout=30` and env `ZEROSHOT_STATE_DIR =
  <engine state_root>/runs`.
- R-3 exception boundary (repairs 2 and 3): an OSError or any other exception raised while evaluating the
  engine's `executable`, `native_environment()` or the `call` attribute propagates with zero invocations, while an
  OSError raised inside the resolved callable still maps to `unknown`/`io` →
  `test_engine_argument_errors_propagate_not_unknown`.
- A-V no values: a sentinel in stdout (payload, extra envelope key or raw text) or stderr never appears in
  `detail` or `repr` of the result → `test_detail_never_carries_stdout_or_stderr`.
- A-B base replay: none — no production entry point is touched; the tests are candidate-only and covered by the
  mutations below (the `FakeEngine` double is a new-helper unit fixture, excluded from base replay).
- No family is raised, so `tests/test_reference.py:337-358` (every raised family must be in `catalog.ERRORS`) stays
  green (`catalog.py` is another lane's).

### Mutation table (scratch copy of the tree; `TMPDIR` under `/tmp`; each mutation is reverted in the scratch copy)

| Mutation | Killing test | Result |
|---|---|---|
| let a malformed summary raise | `test_malformed_summary_is_unknown_not_raised` | KILLED (7 errors) |
| accept org scope | `test_org_scope_is_missing` | KILLED (1 failure) |
| treat any shared field as ready (intersection instead of subset) | `test_shared_field_is_not_ready` (+ `test_missing_field_is_missing`) | KILLED (2 failures) |
| drop `timeout=30` | `test_timeout_is_thirty_seconds` (+ every `check` case) | KILLED (31 errors) |
| use `os.environ` instead of `engine.native_environment()` | `test_call_uses_engine_native_environment` | KILLED (1 failure, 30 errors) |
| put stderr text into `detail` | `test_detail_never_carries_stdout_or_stderr` | KILLED (6 failures) |
| evaluate the environment inside the guarded `try` (reviewer reproduction 1) | `test_engine_argument_errors_propagate_not_unknown` | KILLED (1 failure) |
| resolve `engine.call` inside the guarded `try` (reviewer reproduction 2) | `test_engine_argument_errors_propagate_not_unknown` | KILLED (1 failure) |

## Checks (worker, this visit)

- First action: `git status --porcelain` (empty).
- `TMPDIR=/tmp/zs-agent-... PYTHONPATH=.:tests python3 -m unittest tests.test_connections tests.test_reference`
  → **62 tests, OK** (DoD command; `tests.test_reference` imports no changed code but is named by the DoD).
- Mutations: `python3` driver copied the tree (excluding `.git`/`.tools`/`__pycache__`) and reverted each change;
  scratch dir deleted afterward.

## Interpretations (silence/ambiguity in the task)

- Shape strictness: R-3 validates *every* summary, so one malformed summary makes the whole result `unknown`
  (never a partially trusted list); extra envelope and summary keys are ignored per R-3 ("other envelope keys
  ignored", required summary keys only).
- Check order: a nonzero exit is checked before parsing, so a nonzero exit with unparseable stdout is `exit`,
  not `decode` (R-5 assigns `exit` to a nonzero exit).
- Non-str stdout maps to `decode`, the R-5 label grouped with decoder failures.
- The `fields` argument is not validated here: the R-3 protocol says it is an iterable of str and callers are
  trusted; no task rule asks this module to reject a bad argument.
- Pre-invocation evaluation is outside the guarded call: R-3 maps "OSError from `call`" only, so any exception
  from reading `engine.executable`, `engine.native_environment()` or the `call` attribute propagates (the
  reviewers' findings; see the repair notes).

## Out of scope (left to other slices)

- s3a2 (lane bindings and runtime), s3a3 (env policy, preflight and families, `lane.connection_missing`/
  `lane.connection_unknown` catalog entries and REFERENCE), s3b (`zplan lane`, lanes.json, health URL, doctor
  lines), README code map, `run.sh`, `runtime-deepseek.json`, upstream.
