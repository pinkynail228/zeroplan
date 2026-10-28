s9a1a-log-parse — 0.5 item S9, slice 1 of 3 of devtools/zeroshot/tasks/s9a1-run-reader.md (the parent; its Audit, Read list, R-* and A-* texts apply verbatim where cited). Lane L4 (docs/RELEASE_0.5_SCOPE.md Order). Slicing: critic swarm05 c (~/zs-pause/critic/swarm05.out). DeepSeek worker, sol reviewers.

Base: the v0.4.0 tag. Record the base commit in the receipt. The parent audit is on 0186e38: re-check every line number on the base, and re-gate if a premise moved. s9a1 has no dependency on s2c usage (critic swarm05 a); S4 is not needed by this pure slice.

Slices: s9a1a (this) = pure parse + scrub over retained bytes; s9a1b = observer execution map and worker attribution (parent R-1, R-4); s9a1c = cancellable reader transport, rendering and catalog text (parent R-2 rendering lines, R-5, R-6). Nothing in this slice is wired to a screen or a reader. Parent acceptance by slice: A-4 and A-5 units and the mutations below — a; A-6a execution_nodes validation/replay/conflict/limit and worker selection (incl. final repair), mutations "label run-wide output as worker output", "select by node name only", "reorder execution_nodes on replay" — b; rendering, A-5 repeated through the reader result, A-6a `--after`/separate `--execution` streams/identity reset through the reader/cancel and reap, mutations "read without --after", "leave the reader running after cancel", and the A-9 base-replay of production entries — c.

Write-set (exclusive): new `terminal_planner/run_reader.py`; new `tests/test_run_reader.py`. Read-only use of `live.scrub` (live.py) and `live.tail`'s buffer rules; no edits to live.py, runs.py, cli.py, catalog.py, tui/*, docs.

Rules:
- R-2p Grammar and totality: parent R-2 "Streams and grammar" except the rendered strings — a pure function from (stream identity, retained bytes, previous stream state) to a stream state {identity, records, cursor, latest_timestamp, malformed}; each record is {cursor, timestamp (the original int as parsed), time_ok (false when the timestamp cannot be converted to local time; such a timestamp is excluded from latest_timestamp), execution (str or null), level, text (scrubbed, possibly empty)}; the previous state is reused only when its identity equals the new one; the 40-record window, identity reset, cursor and latest_timestamp rules and the totality paragraph exactly as the parent. Rendering ("HH:MM:SS  <tag><text>", the Russian lines) is s9a1c.
- R-3 Scrub: parent R-3 in full, including the step order (sequence removal, then `live.scrub`, then isprintable/collapse/truncate). Also export the scrub for error summaries so s9a1c can apply it before display.

Acceptance (deterministic fixtures, no provider, network or subprocess):
- A-4p: parent A-4 in full except the rendered-line assertions, which become assertions on the structured result (malformed count, retained records, cursor, latest_timestamp, the unrenderable-timestamp flag).
- A-5: parent A-5 in full, tested through the parse function's result (the parent's "through the reader result" is repeated in s9a1c); the bounded generator with a fixed seed and <=200 cases, same oracle.
- A-9a Mutations (candidate-only, each killed by a named assertion): show the raw JSON envelope; skip OSC removal; mask before sequence removal; drop the isprintable step; carry a cursor across a stream identity change. New-module tests are excluded from base replay (parent A-9).

Size: about 250-350 changed lines including tests. Above 500: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

DoD: unit tests pass locally; receipt with base commit, file list, the mutation table (mutation -> killing test and assertion).
