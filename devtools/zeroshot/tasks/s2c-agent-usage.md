s2c-agent-usage — 0.5 item S2, part 3 of 3 (docs/RELEASE_0.5_SCOPE.md S2 "usage"; docs/AGENT_ENV_PLAN.md design 7-8 and acceptance :129-130). Every finished native run, both planning revisions and milestone attempts, shows the engine's aggregate token usage, or "нет данных" and never a made-up 0%. A devtools probe runs a fixed single-agent workload in an isolated Codex home, identifies its one Codex session from `session_meta.id`, and checks turn-1 input against a recorded baseline. This makes the installed S2 acceptance a command. DeepSeek worker, sol reviewers.

Base: main with s2a-home-binding and s2b-agent-profile merged (after the 0.4.0 tag, with S4 and S5a merged). Record the base commit in the receipt. S4 already added optional `cause`/`reset` to the run record. Add `usage` the same way, alongside them.

Observed (verified on the tree at 19d1b8e; re-check the line numbers on the base):
- The finished native status may carry `metadata.tokenUsage`: {inputTokens, outputTokens, complete, cacheReadInputTokens?, cacheCreationInputTokens?}. It is validated at authority.py:875-886.
  - Milestone attempts: conclude receives only `terminalResult` (runs.py:813-815, :837-839, `conclude` :909), so usage is dropped.
  - Planning revisions: `Authority.commit_terminal` (authority.py:722-736) keeps the whole finished envelope as `terminal_envelope`, so the usage is already persisted but never shown. The planner end view is planning.py:407 `view`.
  - The attempt end view is delivery.py:724 `view`. Journals: delivery.py:625-633 (attempt, or the planner when r is None) over live.py `note`.
- Upstream aggregation (upstream/zeroshot/src/v2_run_ledger/state.rs:239-306): the totals add every execution's delta. An execution without usage sets complete=false. A cache count becomes None as soon as any execution lacks it. Lanes differ in whether the cache read is counted inside the input; this task makes no assumption about it.
- The architect already accumulates its own turn usage and shows it (architect.py:446-451, :770-775; tui/chat.py:193; tui/app.py:366-378). Unchanged here.
- Session ids: upstream `native_v2_codex/output.rs` `accept_thread` keeps the Codex thread id inside the adapter and returns `Ignored`. No public log maps a run to its Codex session. The probe therefore establishes the mapping by isolation and cardinality (R-5), never by cwd or mtime (AGENT_ENV_PLAN :105-107).

Read:
- authority.py :700-740 (`commit_terminal`), :860-890; runs.py: FIELDS/EXTENSION/TERMINAL :43-58, `validate_run` :371-400, observe/refresh :805-842, `conclude` :909-930, the fixture driver conclude :1518-1545;
- engine.py :840-870 (planner observe -> commit_terminal); planning.py :370-420; delivery.py `view` :724-790, journal :625-633; live.py `note`/journal :90-110; catalog.py;
- docs/REFERENCE.md, docs/USER_FLOW.md (end views), devtools/zeroshot/ORCHESTRATOR.md, and the tests of each.

Rules:
- R-1 Store. Persist and display native tokenUsage for both planning revisions and milestone runs, with the same formatter and the same missing-data semantics.
  - Milestone: when an attempt concludes from a finished status (any terminal status, stopped included), store an optional field `usage`. It is a copy of `metadata.tokenUsage` restricted to the five upstream keys, or null when there is no metadata or tokenUsage is null.
  - Planning: usage is read from the stored `terminal_envelope.status.metadata.tokenUsage`, with no new revision field.
  - `validate_run` accepts `usage` absent (old records) or null. A dict must satisfy authority.py:879-885: the required keys, integers 0..2**53-1 or null for the optional ones, and a bool `complete`. Any other value is an invalid record.
  - A resumed successor gets its own `usage` (not in LINEAGE). No extra native call is made for usage.
- R-2 Formatter `usage_line(usage)`, total over its input domain:
  - absent, null, `complete` false, or inputTokens == 0 -> "Токены: нет данных";
  - otherwise "Токены: вход N, выход M" plus a cache part, where c = cacheReadInputTokens and i = inputTokens:
    - c null/absent -> ", кэш нет данных";
    - c == 0 -> ", кэш 0%";
    - 0 < 100*c < i -> ", кэш <1%";
    - 100*c >= i and c <= i -> ", кэш P%", where P = floor(100*c/i), computed in integers;
    - c > i -> ", кэш прочитан N, доля нет данных". No clamp, no share above 100%, and no claim about the provider's accounting.
  Numbers are plain digits. No threshold, colour or alarm (AGENT_ENV_PLAN :104).
- R-3 Display. Every EndView derived from a record whose status is in `runs.TERMINAL` contains exactly one usage line, including conflict and needs_owner, and so does every planner end view of a finished revision (planning.py `view`). Persist one journal entry at native conclusion (attempt conclude; planner `commit_terminal`). Replay or reload adds none. Legacy records display valid stored usage when available, including usage in terminal_envelope. Missing, null, incomplete or zero-input usage follows R-2. Reading legacy records never backfills journal entries. The TUI and the plain UI both show the line.
- R-4 Probe workload. Add `devtools/zeroshot/probe/` with a fixed native graph containing exactly one Codex agent node, and its runtime and input documents. The workload is named `probe-v1` and asks for a short fixed answer with no tools. Start in the run's workspace directory; nothing target-specific.
- R-5 Probe CLI: `devtools/zeroshot/agent_probe.py`, Python stdlib only. Every JSON document carries `"schema": "zplan-agent-probe/1"`. Subcommands:
  - `run --home DIR --zeroshot PATH --provider P --model M --effort E --workload probe-v1 --manifest OUT.json`:
    - DIR is a home reserved exclusively for probes; Codex processes of other homes do not matter. Acquire the exclusive home lock (held for the whole run) before taking either snapshot. Snapshots before launch: `config_sha256` (sha256 of DIR/config.toml bytes, or null) and the set of `DIR/sessions/**/rollout-*.jsonl`;
    - run the workload in the foreground with CODEX_HOME=DIR;
    - Count all new rollout paths: require exactly one, then validate its session_meta.id (first record `{"type":"session_meta","payload":{"id": <nonempty str>}}`). A second malformed rollout still causes failure;
    - Publish a manifest {schema, provider, model, effort, workload, config_sha256, run_id, node, session_id, rollout} only after a successful native terminal result.
  - `turn1 --manifest M.json --out RESULT.jsonl` reads the manifest's rollout and appends one result {schema, provider, model, effort, workload, config_sha256, run_id, node, session_id, turn1_input, turn1_cached}. Rollout grammar:
    - one JSON object per line; token events are `{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":int,"cached_input_tokens":int?,"output_tokens":int,...}}}}`;
    - Initialize comparison counters to zero. Turn 1 is the first valid sample with input_tokens > 0 whose supported cumulative counter tuple differs from the previous tuple. Ignore exact repeats. Missing cached_input_tokens produces null;
    - a line that is not JSON, a truncated last line, or `info: null` is skipped;
    - a token_count whose totals are not integers in 0..2**53-1 (bools rejected) is an error;
    - a session_meta id different from the manifest's is an error, and so is a file without a qualifying event.
    auth.json is never opened.
  - `record --result RESULTS.jsonl --baseline B.json [--replace]` requires exactly three valid results with the same key and distinct session_id values. Store the median integer turn1_input. Baseline schema: {schema, entries:[{provider, model, effort, workload, config_sha256, turn1_input, samples:[{session_id, turn1_input}]}]}. Keys are unique; an existing key requires --replace. Validate schemas and integer token domains before arithmetic. The committed baseline is devtools/zeroshot/agent-baseline.json.
  - `check --baseline B.json --result RESULT.jsonl --ratio R` exits 0 only when every result satisfies turn1_input <= R * baseline, compared in integers: R is a positive decimal with at most 3 fractional digits, scaled to thousandths, never a float. It exits nonzero for an empty result file, a duplicate key, a malformed line, a missing baseline key, or an invalid ratio.
  - ORCHESTRATOR.md gets one line: the S2 installed check and every Codex bump (S8) use `run` -> `turn1` -> `check` on the Linux test host.
- R-6 Text: add a catalog entry if the usage line uses a family, regenerate REFERENCE, and describe the line in docs/USER_FLOW.md.

Acceptance criteria (deterministic fixtures; no real provider; the probe tests use tmp homes and rollouts built from the R-5 grammar):
- A-1 Store:
  - milestone: full usage is stored; no metadata or null tokenUsage stores null; a legacy record loads; each invalid value (negative, 2**53, float, str, missing `complete`, extra key) is rejected; stopped and failed attempts store usage; a resume successor does not inherit the predecessor's usage;
  - planning: finished and failed revisions show usage from terminal_envelope, also after a reload; fixtures of an old planner envelope with usage (shown) and without metadata ("нет данных"); reading them backfills no journal entry.
- A-2 Formatter boundaries: complete false; i=0,c=0; c null; c=0 (0%); (i=101, c=1) -> <1%; (i=100, c=1) -> 1%; (i=2**53-1, c=1) -> <1%; c == i (100%); c = i+1 -> "прочитан N, доля нет данных"; 9999/10000 -> 99%. A bounded generator (fixed seed, <= 200 cases) checks against an independent oracle that "0%" appears only for c == 0, there is never a share above 100%, and there is never a share when c > i.
- A-3 Display: for every status in runs.TERMINAL and every derived EndView state (including conflict and needs_owner), and for the planner end view, exactly one usage line. One journal entry at conclusion; replay, reload and a second observation add none; an old journal gains nothing.
- A-4 Probe (deterministic part):
  - `turn1`: one manifest gives one result with all key fields; Zero, repeated zero, positive sample selects the positive sample; positive sample followed by its duplicate selects the first positive sample; missing cached_input_tokens gives null; a non-JSON line and a truncated last line are skipped; a bool or 2**53 total is an error; an id mismatch is an error; auth.json is never opened (spy);
  - `run`, with a fake zeroshot that creates 0, 1 or 2 rollouts: exactly 1 passes and 0 or 2 is an error; one valid plus one malformed rollout is an error; Test lock serialization (a second `run` on the same home cannot take the lock or snapshot while the first holds it) and unsuccessful termination (no manifest is published); config_sha256 is taken before launch, so a fake that edits config.toml during the run does not change the manifest hash;
  - `check`: pass at exactly 1.2x, fail at 1.2x+1; nonzero for an empty file, a duplicate key, a malformed line, a missing key, and ratios 0, -1, 1.2345 and "abc";
  - `record` refuses an existing key without --replace, fewer or more than three results, mixed keys, and a repeated session_id; the stored turn1_input is the median of the three.
- A-5 End-to-end across S2 (installed, orchestrator on the Linux test host):
  - Initialize the installed candidate under a fresh dedicated XDG_DATA_HOME through zplan login and reserve its home exclusively for probes;
  - in that home: three times `run` then `turn1` (appending to one RESULTS.jsonl), then one `record` of the median as the baseline for probe-v1 (artifact devtools/zeroshot/agent-baseline.json); then one more `run`, `turn1` and `check --ratio 1.2` passes (same config hash);
  - Run milestone, planning and recovery journeys under another fresh data root: one milestone run and one planning revision show usage in their end views;
  - a restart mid-run resumes in the same home (s2a) and the final usage still shows.
  The 9.5K/11.6K numbers of the study are context, not the baseline.
- A-6 Regressions: production-entry regression tests must reach the intended behavioral assertion on the named base. New-helper unit tests are excluded from base replay and covered by targeted mutations. Imports and fixtures must stay compatible with the replay base. Mutations: render 0% for a null cache; drop the `complete` check; render a share when c > i; journal on every reload; let the probe pick the newest file. Record the commands and the base failures. Existing end-view and journal tests stay green.

Size: ~350-500 added lines with tests. Kept as one task: storage, formatter and probe share the "нет данных" rule and are qualified by one installed run (critic s2-task).
Out of scope: architect usage (exists); alarm thresholds and budgets (S9); the Claude lane; S8's release gate that requires the probe record; upstream changes (a public run->session mapping would be an upstream issue, filed only with the owner's go).
critic s2-task: round 3 GO (session 01a150e9-43d9-7da2-ac3a-3948c0e033ef)
