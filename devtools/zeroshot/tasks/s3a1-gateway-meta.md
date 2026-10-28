s3a1-gateway-meta — 0.5 item S3, slice 1 of devtools/zeroshot/tasks/s3a-lanes.md (the parent; its R-6 and A-5 apply verbatim where cited). Lane: Gateway. Slicing: critic overnight05 point 3, swarm05 c (~/zs-pause/critic/). DeepSeek worker, sol reviewers. Critic split3: GO WITH CHANGES (applied).

Base: 6e23523 (C2, intended v0.4.0 tag target); record the base commit in the receipt; re-check every line number on the base and re-gate if a premise moved. Needs neither s2a-c nor S5a's WARN (the parent's Base binds s3a3 only).

Slices: s3a1 (this) = the R-6 connection-metadata check as a pure module; s3a2 = lane bindings and runtime (R-1..R-3; A-1..A-3); s3a3 = env policy, preflight and families (R-7, R-8, R-10; `lane.connection_missing`/`lane.connection_unknown` catalog entries and REFERENCE; A-6, A-7, A-9, L-1), on the parent's Base. Interim rule (critic split3): s3a2 must not enable live gateway dispatch; its production entry points refuse gateway lanes until s3a3 lands the preflight/env policy, and s3a3 enables them.

Write-set (exclusive): new `terminal_planner/connections.py`; new `tests/test_connections.py`; the receipt named in the DoD. No edits to existing files.

Read (pinned Zeroshot 10.12.0 = toolchain.py:48; `git -C upstream show v10.12.0:<path>`):
- crates/openengine-cluster-protocol/src/native_v2_target.rs :42-47 (scope `user`/`org`, snake_case), :150-163 (ConnectionSummary {key, scope, kind, fields}, ConnectionListResult {connections});
- zeroshot/src/native_v2_cli/local/connections.rs :38-48 (list: names only, never values); execution/connections.rs :26-34 (JSON on stdout); main/tests.rs :116 (`connection list`, default scope user);
- terminal_planner/engine.py :128-134 (`native_run`), :558-565 (`call`), :585-589 (`native_environment`), :646-653 (call convention); tests/test_reference.py :337-358 (every raised family must be in catalog.ERRORS).

Rules:
- R-1 Check: parent R-6, with one tightening: no family is raised here. `connection_ready(engine, key, fields)` returns `Connection(state, detail)`, state in `ready`/`missing`/`unknown`; s3a3 maps missing to `lane.connection_missing` and unknown to `lane.connection_unknown`. (A raised family needs a catalog entry, tests/test_reference.py:337-358; catalog.py is another lane's.)
- R-2 Call: exactly one `engine.call([engine.executable, "connection", "list"], capture_output=True, text=True, timeout=30, start_new_session=True, stdin=subprocess.DEVNULL, env=engine.native_environment())`. Never `set`/`delete`, never reads connections.json; no GATEWAY_* policy (s3a3).
- R-3 Parse: stdout must be a JSON object with a list `connections` (other envelope keys ignored). Each summary must be an object whose `key`, `scope` and `kind` are str and whose `fields` is a list of str; any violation makes the whole result `unknown`. Engine protocol: `engine` provides `executable: str`, `call(argv: list[str], **kwargs) -> subprocess.CompletedProcess` and `native_environment() -> dict[str, str]`; `key` is a str and `fields` an iterable of str. Exactly these failures become `unknown`: nonzero exit; `subprocess.TimeoutExpired`; OSError from `call`; non-str stdout; decode failures from `json.loads` (ValueError incl. JSONDecodeError, UnicodeError, RecursionError); shape violations. Other exceptions from the passed object are not suppressed (no bare `except`/`except Exception`).
- R-4 Decision: `ready` iff some summary has the given key, scope `user` and `set(fields) <= set(listed fields)`; otherwise `missing` (missing key, missing field, or org scope only).
- R-5 No values: `detail` is exactly one of `""` (ready), `"missing"` (missing), `"exit"` (nonzero exit), `"timeout"` (TimeoutExpired), `"io"` (OSError), `"decode"` (non-str stdout or decoder failure), `"schema"` (shape violation); no other value, no exit code, stdout or stderr text.

Acceptance (fake `call` spy records argv, kwargs, env; temp state roots; no binary, network, adapter or port 8797):
- A-5 Store check: parent A-5, `unknown` standing for `lane.connection_unknown`: all its ready/missing/unknown cases. Each case spawns exactly one `connection list` with timeout=30 and env ZEROSHOT_STATE_DIR = `<engine state_root>/runs`.
- A-V No values: a stdout/stderr carrying a sentinel string never appears in `detail` or `repr` of the result.
- A-B Base replay: none (no production entry touched); all tests candidate-only, covered by mutations.
- Mutations (each killed by a named test): let a malformed summary raise; accept org scope; treat any shared field as ready (intersection instead of subset); drop timeout=30; use `os.environ` instead of `engine.native_environment()`; put stderr text into `detail`.

Size: about 120-250 changed lines including tests (target 200-450). Above 600, stop and report for a re-gate.

Out of scope: s3a2, s3a3 as above; s3b (`zplan lane`, lanes.json, health URL, doctor lines); README code map (s3a3); run.sh, runtime-deepseek.json; upstream.

DoD: `PYTHONPATH=.:tests python3 -m unittest tests.test_connections tests.test_reference` pass; receipt devtools/zeroshot/tasks/s3a1-gateway-meta-receipt.md with base commit, pinned tag/commit used for the contract, file list and mutation table (mutation, killing test, result).
