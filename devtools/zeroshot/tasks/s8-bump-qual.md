s8-bump-qual — 0.5 item S8 (docs/RELEASE_0.5_SCOPE.md S8 row): a tool-bump qualification command run at every bump. It covers pinned versions, an envelope check and an agent-home probe, and it writes a record. The release gate refuses a bump that has no record. Incidents: the 10.12 minor broke the strict envelope (devtools/zeroshot/tasks/tc1012-upgrade.md:6), and Codex bumps add default-on features. DeepSeek worker, sol reviewers.

Base: main with s2c-agent-usage merged (it ships devtools/zeroshot/agent_probe.py, schema `zplan-agent-probe/1`). Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- Pins: terminal_planner/toolchain.py:47-54 `DEFAULT` (zeroshot 10.12.0, codex 0.162.1, restic 0.19.1, runtime2, platform SHA256s); `tool_dir_name` :40; binding fields :57-72.
- Procedure: docs/UPGRADE.md:36-76 (contracts diff -> candidate script on Linux -> Mac real-provider smoke -> bump DEFAULT and lock -> release).
- Candidate script: devtools/toolchain-candidate.py.
  - Steps: quiescence :64, contracts :192, install/installed/driver; args :248-264.
  - It prints PASS/FAIL/WARN and `RESULT:` but saves no record.
- Strict envelope: authority.py:830-833 `validate_projection` (exact key set), :815 `validate_source_remote`, :811 `validate_receipt`, tokenUsage :875-886.
- Release gate: none scripted; docs/RELEASE_0.4.md:40-68 is a hand checklist. Pattern for a tested devtools gate: devtools/export_check.py with devtools/test_export_check.py.

Read: those files; devtools/driver_qual.py; devtools/zeroshot/agent_probe.py (from s2c); tests/test_toolchain.py (:94, :522, :537, :569, :595-614); devtools/test_export_check.py.

Rules:
- R-1 Command. `devtools/toolchain-candidate.py` gets a `--record PATH` mode that runs the existing steps plus R-3's two new ones and writes a JSON record (schema `zplan-toolchain-qual/1`). The record contains:
  - the candidate pins (versions, runtime tag, SHA256s) and `tool_dir_name`;
  - the platform (os-arch) and the zplan commit;
  - per step: name, status PASS/FAIL/WARN/SKIP, a reason, and a bounded scrubbed detail.
  `--record` explicitly allows qualifying pins equal to `toolchain.DEFAULT`; the current `candidate_chain()` refusal (toolchain-candidate.py:137-138) stays for the non-record mode.
- R-2 Platform matrix (the single source; release_check uses it). Native/installed qualification is Linux-only by project rule, and the real-provider probe runs where the owner's provider login is (the Mac).
  | Step | linux-x86_64 | darwin-arm64 |
  |---|---|---|
  | quiescence, contracts | mandatory | SKIP allowed |
  | install (checksums) | mandatory | mandatory |
  | installed, driver | mandatory | SKIP allowed |
  | envelope (R-3a) | mandatory | SKIP allowed |
  | probe (R-3b) | SKIP allowed | mandatory |
  Any FAIL fails the record. SKIP is allowed only in cells marked SKIP allowed. Every mandatory step must appear exactly once as PASS or WARN; missing or duplicate mandatory steps fail the record. WARN passes and is listed.
- R-3 New steps:
  - (a) Envelope, on the native fixture run the driver step already performs. Each transport goes through its own production validator:
    - observation/watch/status documents -> `validate_projection` (authority.py:830; it covers `source.remote` and tokenUsage);
    - receipts -> `validate_receipt` (:811);
    - zeroshot logs records go through S4a's existing tolerant consumer, never through projection or receipt validators. Do not introduce a strict log key-set check. Complete native log envelopes retain their transport fields; documented skip/unknown outcomes remain valid.
    An observation or receipt refusal is FAIL, naming the transport and the key-set difference; values are never written. The step logic is a pure function over captured lines.
  - (b) Probe: the existing s2c chain, unchanged. `agent_probe.py run` (candidate Codex, the zplan-owned probe home) -> `turn1` -> `check --baseline B --ratio 1.25` against the recorded baseline for the same provider/model/effort. An exit other than 0 is FAIL. A missing baseline is FAIL, with the hint to record one with the current DEFAULT first. This step measures input inflation from default-on Codex features; it does not inventory config keys.
- R-4 Records live in `devtools/qual/toolchain/<tool_dir_name>-<os>-<arch>.json`, tracked. They pass the real export_check: no host names, $HOME paths or tokens.
- R-5 Release gate `devtools/release_check.py --rev REV` (default HEAD) reads the records with `git show REV:path`, not from the working tree. It exits 0 only if, for `toolchain.DEFAULT` at REV and each platform in R-2, a record exists with matching pins and every mandatory step present exactly once as PASS or WARN, with no FAIL in any recorded step. It recomputes this from the steps and never trusts a stored verdict field. Otherwise it exits 2, naming the missing or failed record or step. A record present only in the working tree counts as missing. It runs nothing native or networked.
- R-6 Sequence, documented in UPGRADE.md:
  1. qualify on the candidate commit (Linux host and Mac);
  2. commit both records with the DEFAULT bump;
  3. `release_check --rev <candidate>` -> 0;
  4. merge;
  5. `release_check` on main -> 0.
  The release checklist names release_check as mandatory. Update the ORCHESTRATOR.md sentence introduced by S2c: its installed S2 check remains on Linux; tool-bump probes run on darwin-arm64 according to R-2.

Acceptance:
- A-1 Unit (devtools tests, no network): record schema with a golden record. The R-2 matrix is a table test, covering mandatory SKIP/FAIL, WARN and an allowed SKIP per platform. `--record` with pins equal to DEFAULT is accepted; the non-record mode still refuses it.
- A-2 Envelope on recorded fixtures, per transport:
  - the 10.11 and 10.12 (`source.remote`) observations pass;
  - a synthetic extra top-level key in an observation or receipt FAILs, naming the transport and key;
  - a log line routed to `validate_projection` is not the contract (the routing table is tested).
- A-3 Probe step with a fake agent_probe: exit 0 -> PASS; check exit != 0 -> FAIL; missing baseline -> FAIL with the hint.
- A-4 release_check on a temp git repo:
  - pass;
  - pin mismatch;
  - missing platform record;
  - missing mandatory step;
  - a FAIL step, parameterized over mandatory and optional steps, under a stored verdict: PASS;
  - a malformed record;
  - a record only in the working tree.
  The last six exit 2, each with its named reason.
- A-5 Base failure: release_check is absent on base, so the A-4 driver test fails at its exit-code assertion. Report named failures and skips separately.
- A-6 The orchestrator (not the worker) produces the two real records for the current DEFAULT per R-6 and runs release_check on the candidate commit before merge and on main after.

Size: about 400-700 changed lines including tests, around the ~500-line review trigger. Kept together because the record schema, the matrix and release_check are one contract; release_check without the producer cannot be qualified.

DoD:
- Unit tests pass.
- UPGRADE.md updated.
- Receipt.
- The orchestrator runs A-6.
