run-failure-cause-fix — continue run-failure-cause after the orchestrator stopped its run (run 01a1509b, force-stopped after round 9; R-3/A-1 was rejected in rounds 1-7 with new reproductions after each fix, which met the ORCHESTRATOR.md stop rule; critic run-failure-cause-converge 2026-10-19: STOP AND RE-GATE). DeepSeek worker, sol reviewers.

Worktree: the existing /tmp/zs-zplan/run-failure-cause (branch zs-run-failure-cause). HEAD = f3f4cf0, the preserved candidate (+481 product, +1971 test, +5 docs lines); its parent is the run base 9871d2d. devtools/zeroshot/tasks/run-failure-cause.md still applies, except where this task amends it; read it first. Reviewers review the whole diff 9871d2d..HEAD against both files. Where they differ, this file wins.

Receipt: devtools/zeroshot/tasks/run-failure-cause-receipt.md (replace the candidate's receipt if one exists).

The full reviewer findings of the stopped run are in /tmp/zs-zplan/run-failure-cause-findings.md (15 rejections, rounds 1-9, synthetic inputs only). They are history, not requirements. The frozen contracts below decide each of them. In the receipt, map every numbered finding to one of:
- a test (name);
- "superseded by G-n", with one line why.
Keep the interpretation in the test docstrings (preamble).

Why one run, not two: the reader (G-3) already exists in f3f4cf0 (live.py `records`/`stream`) and was rejected once (round 8). Splitting it out would add a merge cycle without removing any contention. The three contracts are independent sections of the receipt.

## G-1 Provider attribution (amends R-1 and R-3)

Input: the retained lines from G-3. Each line is handled on its own, in this order.

An execution id must be a nonempty string; other non-null values are skipped. A valid cursor fullmatches `v2:[0-9]{1,20}` and its numeric suffix is at most 18446744073709551615. Compare suffixes numerically. Identical duplicate records are deduplicated; conflicting records sharing a cursor make the result unknown.

Record disposition:

| Line | Disposition |
|---|---|
| not a JSON object, or `record.level`/`record.message` missing or not strings | skipped |
| `record.level` other than `"error"` (info, debug, system, model output) | ignored: never evidence, never decisive, never changes the result |
| error, `execution` absent or null (run-wide, e.g. `Run failed: <reason>`) | ignored |
| error with an execution id, `cursor` not matching `v2:<1-20 digits>` | the whole result is unknown |
| error with an execution id and a valid cursor, message matching COMPLETION | completion record |
| error with an execution id and a valid cursor, message matching DIAGNOSTIC | diagnostic record |
| any other error record | ignored |

Grammars (Python `re.fullmatch`, DOTALL; they are copied from upstream native_v2_supervisor/logging.rs:26-56, native_v2_runner.rs:116-117 and native_v2_capsule/provider_process/diagnostic.rs:98):
- COMPLETION = `Node (?P<node>[^\s:]+) failed: (?P<code>timeout|crash|malformed|refusal)(?: after [0-9]+\.[0-9]s)?(?P<reason>: policy denied|: interactive input required|: authentication required|: result did not match the node contract)?(?:: (?P<cause>.*))?`
- RUN_WIDE cause = `run [a-z][a-z0-9_]*`
- PROVIDER cause = `node execution failed: (?P<provider>[A-Z][A-Za-z0-9]*) provider failure: (?P<detail>.*)`
- DIAGNOSTIC message = `(?P<provider>[A-Z][A-Za-z0-9]*) provider failure: (?P<detail>.*)`

Selection:
1. Decisive = the completion record with the highest cursor whose cause is not RUN_WIDE. If there is none, the result is unknown.
2. reason `: authentication required` gives auth. Any other present reason gives unknown.
3. Without a reason, a cause that is absent or does not fullmatch PROVIDER gives unknown. Provider wording elsewhere in the cause (quoted, nested, after another label) never counts. Earlier diagnostics never rescue a non-provider completion.
4. Provider-attributed: the evidence is the decisive detail plus the detail of every diagnostic record with the same execution id and a lower cursor. Records of other executions are never evidence.
5. Classify each evidence detail with the R-2 matchers. They search the detail, so quoted non-provider wording inside a provider detail does not prevent a match. The class is the highest by limit > quota > forbidden > auth > network. The winning message is the matching detail with the highest cursor. If no detail matches, the result is unknown.
6. A truncated detail is classified like any other; it matches only on what it contains.

Planner extraction (R-1, flat formats) is unchanged, except that an envelope with a non-error level is ignored there too.

## G-2 Reset (amends R-4, A-1, A-3)

- Extract: in the winning message, the text after the last `resets `, up to the first `;`, `·`, `<`, CR or LF, with outer spaces stripped.
- Language: the value is kept only if it fullmatches
  `(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{1,2}, )?[0-9]{1,2}(?::[0-9]{2})?(?:am|pm)(?: \((?:UTC|[A-Z][A-Za-z_]+(?:/[A-Z][A-Za-z_]+){1,2})\))?`
  Otherwise it is dropped and the cause is kept. `3:10am (Europe/Moscow)` and `Oct 20, 5am (UTC)` pass. `=`, quotes, brackets, `<`, digits outside the time and words outside the parentheses cannot pass.
- No scrub or other transformation follows extraction. Keep the extracted value only when it fullmatches the language and contains at most 96 characters. Apply this same predicate during persistence, store validation and rendering. This replaces free-text reset acceptance and scrub-idempotence checking.
- `validate_run`: reset is optional; when present it must satisfy the same predicate (language and at most 96 characters) and requires cause=limit.
- Both UI surfaces render a stored reset only if it satisfies the same predicate; otherwise they render the limit line without a reset.
- A-3 reset boundaries: grammar-valid values of lengths 95/96/97 are respectively kept/kept/dropped; also:
  - each optional part present and absent;
  - one character outside the language at the start, middle and end;
  - a credential-like value inside the parentheses (`sk-ABC`, `token=x`);
  - a stored record with an invalid reset (refused by `validate_run`, never rendered).

## G-3 Reader (amends R-6)

- API (keep the existing shape): `live.records(argv, env, cwd, deadline=30.0, buffer=262144, popen=subprocess.Popen, clock=time.monotonic) -> (list[str], bool)`.
  - Lines are split on `\n`; blank lines are dropped.
  - The bool is `complete`.
- Deadline origin: `clock()` read once, right after a successful spawn; `end = origin + deadline`.
- An observation at `clock() >= end` is expired.
- `complete` is True only when all three hold:
  - EOF was read at a clock < end;
  - the process exited with code 0 at a clock < end;
  - no read error happened.
- Retention: the last `buffer` bytes. A total of exactly `buffer` bytes is not an overflow. After an overflow, the leading partial line is dropped (a line starts only after a `\n` or at the stream head). Decoding uses UTF-8 with replacement; a byte cut inside a multi-byte character only affects that dropped partial line.
- Spawn failure (OSError from popen): nothing is signalled; the caller stores unknown.
- After a successful spawn, on every path:
  - stdout is closed;
  - a process still running is killed (the reader only, its own session) and reaped with `wait` for at most 2 s;
  - a process that already exited is only reaped, never signalled.
- stderr is DEVNULL and never evidence. An incomplete read gives unknown, whatever its lines contain.
- Tests use the fake clock and fake popen. Required cases:
  - the deadline crossed during a read, exactly at EOF, and during wait;
  - equality at the deadline;
  - nonzero exit;
  - a read error;
  - spawn failure (no signal);
  - natural exit (no signal);
  - buffer-1/buffer/buffer+1 bytes, including a multi-byte character at the cut;
  - large payloads passed through a file or stdin, never one command-line argument (round 6, ARG_MAX).

## Qualification (amends A-6)

- Repair regressions: at least one behavioral test per contract (G-1, G-2, G-3) fails at its named assertion on f3f4cf0 and passes on the candidate.
- Original feature checks: run-failure-cause.md A-6 against 9871d2d, unchanged.
- Report named failures and skips separately; import, missing-symbol and setup failures do not count.
- Targeted modules for the worker: tests.test_run_cause, tests.test_ux, and the existing engine/planning/runs/catalog test modules. Broader suites are the orchestrator's gate.

Size: the candidate is already about +2450 lines (estimate was 300-450). Do not add features beyond G-1..G-3; remove candidate code and tests that these contracts make obsolete. Report the product/test split in the receipt.

DoD:
- targeted tests pass;
- run-failure-cause.md A-1..A-6 as amended here;
- receipt with the findings map;
- REFERENCE.md regenerated if catalog text changed.
critic run-failure-cause-fix-task: BLOCK, then GO WITH CHANGES (round 2; cursor/execution domain, closed code enum, reset length bound — applied), session 01a1508f-ff31-7780-9b41-31ceb7d3a788
critic rfc-merge: GO WITH CHANGES (b2dd941 accepted; receipt correction + G-1 mutation evidence applied; merge after v0.4.0 with the full gate on the merged tree), same session
