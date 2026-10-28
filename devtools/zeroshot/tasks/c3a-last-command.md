C3a — an observed attempt remembers the last Codex command it saw (data half of slice C3, docs/CHAT_RELEASE_JTBD.md, job J3).

Goal: the live panel will say "молчит N мин · последнее: <command>" (C3b renders it). This run only stores the value: while a milestone attempt is observed, zplan reads the active executions' logs at a bounded rate and keeps the last "Codex command started/completed" line it found, scrubbed, with its time.

Data reach:
- Observe loop: runs.py:870 `observe` ends every slice with `self.record(r)` (runs.py:903-904; status None path) and has `r["run_id"]`, `r["binding"]`, `r["worktree"]`; the active execution refs are `r["live"]["nodes"]` pairs [node, execution] (live.py:148).
- Log read (follows an active run: upstream/zeroshot/src/native_v2_observability/subscriptions.rs:75): `engine.log_records(binding, run_id, cwd, **options)` (engine.py:1527-1534) runs `zeroshot logs RUN` through the bounded `live.records` (live.py:245; keeps the last `buffer` bytes; `deadline` option). Add an optional `execution=None` that appends `--execution <ref>` (upstream docs/zeroshot-cli.md:992-1015). The fake driver at runs.py:1665 takes the same argument.
- Log line shape: one JSON object per line, `record.message` text (tests/test_run_cause.py:120-128 `envelope`, e.g. "Codex command completed").
- Scrub: `live.scrub(line)` (live.py:427) before anything is stored; engine.py:313 says raw log text is never shown.
- Store: `live.KEYS`/`new()`/`valid()` (live.py:29-80) are a closed set enforced at authority.py:508 and runs.py:404.

Write-set: terminal_planner/live.py (new key, parser, validator), terminal_planner/engine.py (`log_records` execution option only), terminal_planner/runs.py (the slice-end read and the fake driver signature), their tests (tests/test_live.py, tests/test_runs.py, tests/test_run_cause.py).

Acceptance criteria:
- A1 New live key `command`: None or {"at": stamp, "text": str ≤ 160 chars}. `new()` sets None. `valid()` accepts a stored live record that lacks the key (written before this change) and one that has it; any other key set is still refused.
- A2 Read: at the end of an observe slice (runs.py:903-904) with at least one active execution in `live["nodes"]`, and no read attempt for this run in the last 30 s, zplan reads `logs RUN --execution REF` for exactly one execution: the active ones in `live["nodes"]` order, round-robin across attempts. One read per slice, `deadline` 1 s, the existing bounded buffer. `logs` follows an active run, so the read normally ends on the deadline with `complete=False`: the retained lines are used whatever `complete` says (timeout and nonzero exit alike). Cost: at most once per 30 s per run, one slice grows by the 1 s deadline plus the reader cleanup (live.py:333, up to 2 s); accepted, no other slice changes.
- A3 Parse: only lines whose `record.message` starts with "Codex command started: " (upstream/zeroshot/src/native_v2_codex/output.rs:396-414). `text` = the first line of the rest of the message with a trailing ` [<status>]` and ` exit=<n>` removed (the command only), scrubbed with `live.scrub`, cut to 160 chars. The last such line of the read wins; it replaces the stored value only if its `timestamp` (ms epoch) is greater than the last accepted ms timestamp kept in memory for this run (A5); with nothing in memory (a new process), it replaces when its stamp (ms floored to whole seconds, the `TIME` format) is not older than the stored `command.at`. `command.at` stores the floored stamp. Completed lines, unknown prefixes and malformed JSON are ignored.
- A4 Failure: OSError (the reader cannot start) or no matching line changes nothing in the record and never stops the observation (no exception escapes `observe`).
- A5 Throttle state: the time of the last read attempt (failed ones too), the round-robin position and the last accepted ms timestamp live in memory on the `MilestoneRuns` object, keyed by run id; nothing new is persisted besides `command`.
- A6 Tests: parser (started; completed ignored; unknown prefix; malformed JSON; credential scrubbed; multi-line message keeps line one; cut at 160); validator (old record without key, new record, extra key refused); observe with a fake driver whose log read returns lines, returns `complete=False` with lines (used), raises OSError (no change); throttle (two slices within 30 s read once; round-robin over two executions). tests/test_run_cause.py:206 `test_a_poll_loop_reads_nothing` asserts the old rule "a poll loop never reads logs": change it to "a poll loop reads at most one execution log per 30 s" and keep its intent (no failure-cause read while polling).

Non-goals (reviewers must not require): any panel or TUI change (C3b), the planner side (planning.py), `zeroshot attach`, a log cursor, a stall/"завис" verdict, migration of stored records.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_runs tests.test_run_cause tests.test_milestone tests.test_tui_live tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
