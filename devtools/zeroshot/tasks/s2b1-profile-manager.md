s2b1-profile-manager — 0.5 item S2, slice 1 of 2 of devtools/zeroshot/tasks/s2b-agent-profile.md (the parent; its R-2, R-3, A-1, A-2 and the profile mutations of A-8 apply verbatim where cited). Slicing: critic swarm05 c (~/zs-pause/critic/swarm05.out:52, "profile manager separately from default/auth/doctor activation"). Lane: Environment (L1). DeepSeek worker, sol reviewers. Critic gate7 A: GO WITH CHANGES (applied).

Base: main 6a537b5 (s2a1, s5a1 and s5a2 merged), run now in parallel with s2a2-engine-wiring (gate7 A; no wait for its merge). Lines below are cited at 6a537b5. Record the actual base and this brief's sha256 in the receipt. Activation (s2b2) stays after the whole of s2a.

The write-set is disjoint from s2a2's (s2a2-engine-wiring.md:34-47: engine.py, runs.py `check_binding`/`start`, planning.py:249, tests/test_home_wiring.py). s2a2 does not touch setup.py, catalog.py, REFERENCE.md or docs. Whichever merges second is rebased and re-gated on the full suite by the orchestrator.

Slices:
- s2b1 (this) = the profile manager:
  - the packaged versioned profile and its pinned key set (parent R-2, A-1);
  - the write lifecycle into zplan's own home: classify, back up, replace atomically, under a per-home lock (parent R-3, A-2);
  - the failure family `setup.agent_home`.
  - Nothing calls it: no launch, login or doctor path changes.
- s2b2 = activation:
  - parent R-1 (`agent_home`, default switch in `native_environment`), the R-3 call sites (`native_environment`, `login`), R-4 auth presence, R-5 doctor items, R-6 precedence table, the rest of R-7 (`readiness.agent_drift`, `readiness.agent_sources`, README/INSTALLATION/USER_FLOW/commands.py);
  - A-3 to A-8, with the A-8 mutations "write under an override", "drop the mcp_servers rule" and "skip the skills WARN".
  - Then A-9 Linux qualification by the orchestrator.

Write-set (exclusive for this slice):
- new `terminal_planner/agent_profile.py`;
- new `terminal_planner/resources/agent_profile.toml`;
- pyproject.toml: the package-data line only (:20), adding `resources/*.toml`;
- catalog.py: one entry, `setup.agent_home`, in the Setup group (:322-334);
- docs/REFERENCE.md: regenerated, with nothing hand-edited;
- new `tests/test_agent_profile.py`;
- the receipt `devtools/zeroshot/tasks/s2b1-profile-manager-receipt.md`.

Not touched: setup.py (`native_environment` :234-239, `login` :242-247 and doctor are s2b2), cli.py, commands.py, tui/*, engine.py, runs.py, planning.py, README.md, docs/INSTALLATION.md, docs/USER_FLOW.md.

Audit (6a537b5):
- Homes:
  - `codex_home(env)` setup.py:209-215: `$CODEX_HOME` or ~/.codex;
  - `legacy_codex_home()` :218-221;
  - `private_codex_home()` :224-225: `data_root()/codex-home`, with `data_root` at :28;
  - nothing writes a config.toml into any home today.
- Lock precedent: `setup_lock` :146-155 (`fcntl.flock` on a lock file, `LOCK_EX | LOCK_NB`, `setup.busy`). This slice uses the same non-blocking shape on its own per-home lock, refusing with `setup.agent_home`.
- TOML reading: `read_toml` :423-429 (tomllib or `minimal_toml` :372 on Python 3.9; the local interpreter is 3.9.6).
- Package data: pyproject.toml:19-20 ships `resources/*.json` only; `importlib.resources` is already imported at setup.py:9.
- Catalog: the Setup families at catalog.py:322-334. The REFERENCE generation and raise-site scan are in tests/test_reference.py:103-115, :339-359 and :535.
- Decision table: docs/AGENT_ENV_PLAN.md:60-79 (the profile rows); parent R-2 (:25-30) fixes the exact keys.

Rules:
- R-1 Unreached: no production module imports `agent_profile`, except that the catalog gains its family. Every existing launch, login, doctor, record, digest and golden stays byte-identical.
- R-2 Resource: parent R-2 verbatim.
  - The first line is exactly `# zplan-agent-profile: 1`.
  - `agent_profile.EXPECTED` is the one constant holding the expected flattened key -> value map. A test pins it to the parsed file in both directions.
  - Marker grammar (closed): the bytes up to the first LF must equal `b"# zplan-agent-profile: " + N + b"\n"`, where N matches `[1-9][0-9]{0,8}` (ASCII digits, no sign, no leading zero, no spaces, no CR). N is compared as an int.
  - `packaged()` returns the resource bytes via `importlib.resources`. `version(data: bytes)` returns that int, or None for anything else: no marker, another spelling, a leading zero, CRLF, a BOM or undecodable bytes.
- R-3 Lifecycle: `ensure(home)`, parent R-3 verbatim, plus:
  - Guard: `ensure` refuses (ValueError, before any write) any `home` whose resolved path is not `setup.private_codex_home()` resolved.
    - This guard is necessary but not sufficient for "never under an override": `CODEX_HOME=<private_codex_home()>` passes it.
    - s2b2 must therefore skip `ensure` entirely whenever `CODEX_HOME` is set and nonempty, whatever its value. Record this as a binding note for s2b2 in the receipt.
  - Lock: `<home>/.zplan-profile.lock`, taken with `fcntl.flock(LOCK_EX | LOCK_NB)` after the home exists. When it is held, raise `Blocked(..., family="setup.agent_home")` saying another zplan is updating the profile, with the remedy "retry". A busy refusal writes nothing else. Classification happens under the lock.
  - Classification of `<home>/config.toml` by `os.lstat`, in this precedence:
    1. absent → write the profile (`"written"`);
    2. a symlink, whatever it points to and whatever its target's N → back up the link and replace it (`"replaced"`). A symlink is never "current";
    3. a regular file whose `version()` equals the packaged N → no write, even if edited (`"current"`);
    4. a regular file with another N, no marker or undecodable bytes → back up the bytes and replace (`"replaced"`);
    5. anything else (directory, fifo, ...) → `setup.agent_home`, with no write.
  - Backup:
    - The new `.bak` is first built under a temp name in the home: a byte copy for case 4, `os.symlink(os.readlink(config))` for case 2. It is then moved with `os.replace` onto `config.toml.bak`.
    - An existing `.bak`, including a `.bak` that is itself a symlink, is only ever replaced as a directory entry. Its target is never opened for writing.
  - Write: the profile goes to a temp file in the home (fsync), then `os.replace` onto config.toml. The symlink target of case 2 is never opened for writing.
  - Fault points: an OSError at each finite point below raises `setup.agent_home` naming the path, removes its own temp file, and leaves exactly these residual files:
    - F1 creating the home → nothing created;
    - F2 opening the lock file → home only (when new), no lock taken;
    - F3 writing the backup temp → config and any old `.bak` unchanged;
    - F4 `os.replace` onto `.bak` → config and any old `.bak` unchanged;
    - F5 writing the profile temp → the new `.bak` (== the old config) in place, config unchanged;
    - F6 `os.replace` onto config → same as F5.
    - A retry after any of F1-F6 completes as `"replaced"` or `"written"`, with `.bak` == the original config.
    - No other failure point is promised.
  - Returns `"written" | "current" | "replaced"` for s2b2's display.
- R-4 Read side for s2b2: `written_version(home)` = `version()` of the existing config.toml, or None when absent. It never writes, never takes the lock and never follows a symlink outside reading it.
- R-5 Text: one catalog entry `setup.agent_home` (summary, cause, remedy in the existing tuple shape). REFERENCE.md is regenerated by the existing generator, never hand-edited.
- R-6 Fixtures: every literal home path in tests is under `/home/user/` (export_check home-path allows only user/testuser/runner); real file operations use `tempfile` directories with `XDG_DATA_HOME` pointed into them.

Acceptance (tests/test_agent_profile.py; temporary XDG_DATA_HOME; no network, no Codex):
- A-1 Profile (parent A-1):
  - Oracle: the packaged file parses with `read_toml`, its line 1 is the marker, and its flattened key set and values equal `EXPECTED`.
  - Control: a copy with one key removed and a copy with one value changed each fail the same comparison helper.
  - The forbidden tables of parent R-2 are absent.
  - The resource is read through `importlib.resources` from the checkout. This does not prove packaging; the wheel smoke is the orchestrator's (DoD).
- A-2 Lifecycle (parent A-2, every bullet):
  - absent → written, home mode 0700;
  - same N with an edited body → bytes untouched;
  - N-1, no marker, or binary garbage → `.bak` == old bytes and config == `packaged()`, and an existing `.bak` is replaced;
  - a second `ensure` changes nothing and keeps `.bak`;
  - symlink → `.bak` is a link with the same target, the target is byte-identical, and config.toml is a regular file;
  - an existing `.bak` that is a symlink to a sentinel file → replaced as an entry; the sentinel is byte-identical (regression for gate7 A);
  - a symlinked config.toml whose target carries the current N → still `"replaced"` (precedence 2 over 3);
  - marker grammar: `1`, `01`, `+1`, ` 1`, CRLF, BOM, `1000000000` and a missing LF each give the documented `version()` result;
  - fault points F1-F6, each forced by patching the named call → `setup.agent_home`, the exact residual file set listed in R-3 (directory listing compared), no temp file; then a retry gives `.bak` == the original;
  - deterministic two-writer concurrency with Events (parent A-2 as updated by gate7): writer 1 is paused in the critical section, and writer 2 gets `setup.agent_home` (busy) and writes nothing. After the release, writer 2 retries and gets `"current"`. `.bak` holds the original N-1 bytes and no temp file remains.
- A-3 Guard: `ensure("/home/user/.codex")` and `ensure(<tmp>/other)` raise ValueError and create nothing. The control `ensure(private_codex_home())` writes.
- A-4 Unreached: `git grep -n "agent_profile" -- terminal_planner` lists only agent_profile.py itself (asserted in the test by scanning the package sources). tests.test_setup and the doctor/readiness goldens pass unchanged.
- A-5 Base replay and mutations:
  - There is no production entry point (R-1), so no behavioral test can fail on base through an existing path; say so in the receipt.
  - Compatibility: the DoD targeted modules (except the new one) pass on base and candidate, with counts in the receipt; the full suite is the orchestrator's.
  - Each mutation is killed by a named test:
    - (a) drop a profile key from the file;
    - (b) drop the same key from `EXPECTED` only;
    - (c) skip the `.bak` copy;
    - (d) remove the lock, or make it blocking;
    - (e) write the target of a symlink;
    - (f) remove the private-home guard;
    - (g) write without the temp file/`os.replace`, so a forced failure leaves a partial file;
    - (h) treat "same N, edited" as replace;
    - (i) open an existing `.bak` symlink for writing instead of replacing the entry;
    - (j) classify a symlink with the current N as `"current"`;
    - (k) accept a leading zero or CRLF in the marker.

Size: about 300-450 changed lines including tests (product ~120, resource ~20, catalog ~3, tests ~250, REFERENCE generated). Above 600, stop and report for a re-gate rather than absorbing s2b2 work.

Out of scope:
- `agent_home` and the default switch, the `native_environment`/`login` call sites, auth presence, doctor items, drift/sources warnings, the precedence table, README/INSTALLATION/USER_FLOW/commands.py text (s2b2);
- A-9 qualification (orchestrator, after s2b2);
- s2c; devtools/zeroshot/run.sh.

DoD:
- Worker (targeted): `python3 -m unittest tests.test_agent_profile tests.test_setup tests.test_toolchain tests.test_reference` passes locally. The worker does not run the full suite.
- Orchestrator, at the merge gate:
  - the full suite;
  - a wheel resource smoke: build the wheel, install it into a fresh venv, and read `agent_profile.toml` through `importlib.resources` from the installed package; its `version()` equals the packaged N.
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate (exit 3 "incomplete" for a missing private list is reported, not a failure).
- Receipt: base commit, this brief's sha256, file list, compatibility counts (named failures and skips separately), the mutation table.
