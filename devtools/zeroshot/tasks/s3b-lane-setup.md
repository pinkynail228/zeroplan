s3b-lane-setup — 0.5 item S3, part 2 of 2 (docs/RELEASE_0.5_SCOPE.md:21). zplan sets up the gateway lane itself:
- `zplan lane gateway` wraps the native connection prompt;
- an optional health URL lives in zplan's user config;
- doctor reports the lane, the stored connection and the gateway health from the configured URL, not from a private install script or port.
This part completes the no-credential-at-rest invariant. It replaces s3a's native-command remedy with `zplan lane gateway`. S3 closes with this part. DeepSeek worker, sol reviewers.

Base: main with s3a-lanes merged (on top of s2a-c). Record the base SHA in the receipt. This part reuses s3a's `connection_ready` (R-6), the gateway lane binding (R-1), the env policy (R-7) and the `lane.connection_missing` family (R-8). It also reuses S5a's warn severity and s2b's doctor layout. If any is missing on the base, stop and report: they are base requirements, not part of this task.

Observed (re-check line numbers on the base):
- Before the worker run, the orchestrator verifies the contracts against the base's pinned Zeroshot source using `git -C upstream show <pinned-tag>:<path>` and against the pinned binary. Record tag, commit, binary version and evidence. No checkout is required. Cover connection metadata, canonical gateway requirements, stored-value resolution on submission and resume, and workspace recoverability. A contract mismatch blocks the run and requires re-gating; line-number drift alone does not.
- Upstream `zeroshot connection set KEY --field ENV...` prompts each field without echo from the inherited terminal and replaces the whole connection (upstream parser.rs:271-295; execution/connections.rs:100-139; local/connections.rs:49-63). Native `connection list` itself calls `lock()` and may create the store directory and lock file (local/connections.rs:35-37, :102-108).
- The manual precedent is run.sh:26-31, which probes a private health path on a fixed port and names a private install script. Product code must do neither.
- `zplan login` already runs a native tool with the inherited terminal and never captures its output (setup.py `login`, as changed by s2b). Roles are saved atomically by `save_roles` (setup.py:69-80). Doctor is `readiness`/`doctor` (setup.py:453-582, as changed by s2b and s3a).

Read:
- the s3a changes (`connection_ready`, the lane binding, `native_environment`, the preflight and its remedy text);
- terminal_planner/setup.py: `login`, `save_roles`, `readiness`, `doctor`; cli.py (command dispatch :905-960); commands.py :30-80; catalog.py;
- docs/REFERENCE.md, README.md (code map), docs/INSTALLATION.md, docs/USER_FLOW.md, and the tests of each.

Rules:
- R-4 Connection setup. A new command `zplan lane gateway` runs the pinned `zeroshot connection set gateway --field GATEWAY_BASE_URL --field GATEWAY_API_KEY` with the engine's `native_environment()`, so with the current native state root. zplan never reads, captures, stores, logs or prints either value, and never passes a value in argv. A nonzero exit is reported as `lane.setup_failed` with the exit code only. After a successful native exit, ask for an optional health URL. Enter preserves the current value, including absence; `-` removes it. An invalid nonempty answer leaves lanes.json unchanged, but does not roll back the native connection already saved. Native setup failure leaves lanes.json unchanged. Inherit stdin, stdout and stderr; do not pipe, tee or capture them. Connection metadata readiness does not validate the stored base URL or provider access; those validations belong to the native runner. The health URL is saved to `config_root()/lanes.json` atomically, mode 0600, like `save_roles`. `zplan lane` with no argument prints, for the gateway lane: the roles using it, whether the store has the connection (s3a R-6), and the health URL or "не задан". commands.py gets the entries; catalog gets the families.
- R-5 URL and document rule. Accepted URL: an absolute `http` or `https` URL with a host, no userinfo, no query, no fragment, no whitespace, control character or backslash, a well-formed authority and a valid port (1-65535), at most 2048 characters. Empty interactive input follows R-4. An absent lanes.json means no health URL. Valid documents are exactly `{}`, `{"gateway": {}}`, or `{"gateway": {"health_url": URL}}`. Reject every other shape, wrong type, unknown key, malformed encoding or invalid URL with lane.invalid_config, without rewriting the file. Reject malformed authorities, invalid ports and backslashes.
- R-9 Doctor (tools mode). It adds lines only when an effective role has the gateway lane. Effective roles: the resolved project profile when a project is given, else roles.json.
  - "lane": the roles using it;
  - "connection": s3a R-6, BLOCKED when not ready, remedy `zplan lane gateway`;
  - "gateway health": with a health URL, a GET with a 2 s timeout and no request body. Ready iff the HTTP status is 200-299. Health requests bypass environment proxies, use no credential headers, follow no redirects, and expose no response body. Without a health URL, a WARN "health URL не задан; zplan lane gateway".
  - Doctor does not modify zplan configuration, agent profiles, Authority or connection values, and never invokes connection set/delete. Native connection-list directory and lock-file maintenance is permitted.
  - Production code names no port, adapter name, install script or health path.
- R-8 remedy. s3a's `lane.connection_missing` remedy becomes `zplan lane gateway`. Keep the recorded-state-root guidance: when the record's state root differs from the current native state root, the remedy also names `ZEROSHOT_STATE_DIR=<state_root>/runs <executable> connection set gateway --field GATEWAY_BASE_URL --field GATEWAY_API_KEY` for that record.
- R-10 (completion) No credential at rest outside the native store. zplan writes only names (`gateway`, GATEWAY_BASE_URL, GATEWAY_API_KEY) and the health URL into its files, now including lanes.json.

Acceptance criteria (deterministic: a fake `call`/Popen spy records argv, env, stdin/stdout/stderr disposition of every `zeroshot` invocation and returns scripted `connection list` JSON; temporary HOME, XDG_CONFIG_HOME, XDG_DATA_HOME and state roots; a local `http.server` on an ephemeral port for health; no real provider, no adapter, no port 8797):
- A-4 `zplan lane gateway`.
  - The spy sees exactly `connection set gateway --field GATEWAY_BASE_URL --field GATEWAY_API_KEY`, with the engine env and inherited stdin, stdout and stderr (no PIPE, no capture).
  - A sentinel key typed into the fake terminal never appears in argv, captured output, any file under the temp HOME/XDG roots, the project, or Authority state.
  - Enter keeps an existing URL and keeps absence; `-` removes the URL.
  - An invalid nonempty answer leaves lanes.json byte-identical, and the native set has already run once.
  - A nonzero native exit gives `lane.setup_failed`, no URL prompt, and lanes.json untouched.
  - URL boundaries: accepted `http://h/`, `https://h:1/x`, a 2048-character URL. Refused with lane.invalid_config and the file unchanged: a 2049-character URL, `ftp://h`, `http:///x`, an http URL to host h with userinfo u and a password, `http://h/?q`, `http://h/#f`, `http://h:0/`, `http://h:65536/`, `http://h:x/`, `http://h\x/`, a URL with a space or control character.
  - Documents: an absent file means no URL. `{}`, `{"gateway": {}}` and `{"gateway": {"health_url": URL}}` are accepted. Refused without rewriting: non-JSON, invalid UTF-8, a list, an unknown top key, another lane name, an unknown gateway key, a non-string URL, an invalid URL.
  - A bounded deterministic generator with an independent oracle covers the URL and document grammar, including the 2048/2049-character boundaries.
- A-8 Doctor.
  - No gateway role: no lane lines.
  - Gateway role, store ready and a health server answering 200: all OK.
  - A health server answering 503, or 302 (redirect refused, target never contacted), or a closed port: BLOCKED.
  - The request the server recorded has no Authorization header. Proxy env (HTTP_PROXY/HTTPS_PROXY/ALL_PROXY with credentials in them) is bypassed: the request reaches the local server directly, and no output contains the proxy credentials. The response body never appears in output.
  - No health URL: WARN. Store not ready: BLOCKED with the `zplan lane gateway` remedy.
  - Doctor makes only `connection list` native calls (metadata only), and zplan config, profile and Authority files are byte-identical after it.
  - A source scan test: no product file under terminal_planner/ contains `8797`, `install.sh`, `zplan-adapter` or `yandex`.
- A-10 Remedy. `lane.connection_missing` names `zplan lane gateway`. For a record on another state root it also names that record's executable and state root.
- A-9 Regressions.
  - Production-entry regression tests must reach the intended behavioral assertion on the named base. Replay s3b regressions on merged s3a.
  - A missing new command must be asserted as an observable CLI behavior, not fail during import or fixture setup.
  - Missing prerequisite behavior blocks the task; do not implement prerequisite repairs here.
  - New-helper unit tests are excluded from base replay and covered by targeted mutations. Imports and fixtures must stay compatible with the replay base.
  - Targeted mutations: follow redirects in the health probe; honor proxy env; capture the native set's output; write lanes.json after a failed native set; accept a 2049-character URL; drop the recorded-state-root guidance from the remedy.
  - Record the exact targeted commands and the base failures. The existing setup, process, runs, engine, terminal_planner, live and reference suites stay green; docs/REFERENCE.md is regenerated.
- L-1 — Orchestrator qualification on the Linux test host, installed pinned tools and isolated durable roots. This repeats the s3a journey through the shipped setup command `zplan lane gateway` (health URL = the stub's health endpoint), and doctor is OK before the run.
  - Before the worker run, demonstrate that the proposed failure recipe reaches native `workspaceRecovery.recoverable=true`; record the recipe and bounded timeout. If it does not, block and re-gate the recipe. Never substitute force-stop or edit native recovery state.
  - Use a stub with a dedicated health endpoint returning 200 and gateway request endpoints returning 503. Log only request path and SHA-256 of the complete Authorization header; compare against SHA-256 of `Bearer <sentinel>`.
  - Complete setup, runtime admission and milestone submission without GATEWAY_BASE_URL/GATEWAY_API_KEY. Terminate only the zplan client, restart it in a fresh process, observe the qualified recoverable failure and resume through [g]. Verify distinct predecessor/successor run IDs and matching header hashes.
  - Repeat with a conflicting inherited GATEWAY_API_KEY; the stored value still wins and doctor warns.
  - Scan project and isolated config/data/native roots without printing matching lines; the sentinel may occur only in the native connections.json.
  - Record commands, exits and sanitized evidence.

Size: ~330-420 added lines with tests: lane command and lanes.json ~70, URL/document rule ~50, doctor lines and health probe ~60, remedy and catalog/docs ~40, tests including the generator ~170. Under the 500-line soft trigger.

Ownership: terminal_planner/{setup,cli,commands,catalog,runs,engine}.py (remedy text only in runs/engine), plus a new lane helper module if needed; tests; docs/REFERENCE.md (regenerated), README.md code map, docs/INSTALLATION.md, docs/USER_FLOW.md.
Out of scope:
- the lane binding, runtime, env policy and preflight logic (s3a; change only the remedy text);
- devtools/zeroshot/run.sh and runtime-deepseek.json (a separate devtools task; critic decision 5);
- the Claude lane and other providers, hosted targets and org scope;
- `--json-stdin` (critic decision 3);
- starting, installing or probing any adapter process;
- upstream changes.

critic s3-task: GO WITH CHANGES, applied (session 01a150fa-e6a1-7dc2-8177-33273a80c10f)
