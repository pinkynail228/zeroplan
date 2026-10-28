s1a1b2-gate-barrier — 0.5 item S1a, slice 2b of devtools/zeroshot/tasks/s1a1-task-gate.md (the parent; its R-* and A-* texts apply verbatim where cited). Slicing: critic gate7 B (~/zs-pause/critic/gate7.out). Lane L2. DeepSeek worker, sol reviewers. Critic gate8: GO WITH CHANGES (applied). Re-gate after the s1a1b1 amendment: critic s1a1b1-regate GO WITH CHANGES (applied), session 01a1596a-337e-7d91-b098-9d8de9ff59e1.

Base checked: main 9497dff, containing s1a1b1 merge eda066e (reviewed candidate 043963d, receipt append 9232397). Audit citations below are historical at 6a537b5. Current anchors: Runs.start runs.py:615, HEAD base:642, refresh:648, documents/bootstrap:661-662, first save:679; retry:1346, answer:1373, accept_proposal:1400, resume:1042; Delivery.guard delivery.py:564, preview:570. Record the actual launch base and this brief's sha256; re-gate if a semantic premise changes. Premise check: critic s1a1b2-premise GO WITH CHANGES (applied; session 01a15ad5-adc7-7633-b5aa-a78c5afdd8f9). Authority validates runs before gates (authority.py:436-441): the new admission validator must refuse safely on malformed references.
- Consumes unchanged both the Frozen contract and the Re-gate amendment 2026-10-20 of s1a1b1-gate-record.md, as approved for its rerun. Record the merged s1a1b1 implementation SHA and the referenced brief's sha256 in this receipt.
- If the merged implementation differs from that contract, stop and re-gate. This slice does not expand its input domain, fault model or guarantees, and does not change its dispatch or validation paths.

Slices: s1a1b1 (record, dispatch, qualification) → s1a1b2 (this: parent R-4, R-6 override part, A-3, A-3b, A-4 validity, A-6, A-7) → s1a1c (keys, commands, display, docs).
- "Closed until enforcement is ready": this slice removes `process.unbuilt` for `gates.task == "required"` (process.py:707-708) in the same change that installs the barrier.
- Before s1a1c, a gate is created only through `Delivery.run_task_gate`. The refusal texts name the action generically and promise no CLI command or key that does not exist yet.

Write-set (exclusive for this slice):
- task_gate.py: `valid(record, live)` and the refusal classification;
- runs.py:
  - in `Runs.start` :607, the admission check before `self.refresh()` (:640) and before any persistence (:665);
  - the optional run-record field `admission` (`FIELDS`/`OPTIONAL` :60-69, `validate_run` :385);
  - `LINEAGE` :78-79 / `lineage` :121 handling of `admission`;
  - resume runs.py:1042-1067: preserve the native recovery protocol; permit the minimal admission inheritance and frozen-config resolution required by R-5. No live-profile lookup or new gate.
- delivery.py: `override_task_gate(gate_id, reason)`, `task_gate_state(milestone_id, context=None)`, and the read-only gate status in `preview` :564; Delivery.guard and its milestone callers may receive the minimal changes needed to prevent sidecar writes before a required-gate refusal; preserve off, plan and merge behavior.
- process.py: remove :707-708; remove UNBUILT["task"] only when unused. Permit the minimal Profile.guard adjustment needed for read-only required-milestone admission; preserve off, plan and merge behavior (today Delivery.guard -> Profile.guard calls status(write=True), and process.py:579-593 can publish a sidecar before the barrier).
- catalog.py: `task.gate_missing`, `task.gate_running`, `task.gate_rejected`, `task.gate_failed`, `task.gate_stale`; docs/REFERENCE.md regenerated only;
- new `tests/test_task_gate_barrier.py`;
- existing native unit fixtures that reach `Runs.start` (test_runs, test_lifecycle_guard, test_live, test_fixture_scope, the tui suites, and any other the run finds):
  - only the lines that bind an accepted profile with `gates.task: off` explicitly (R-2);
  - assertions are unchanged, and there is no test-only bypass in product code;
  - every edited test file and line range is listed in the receipt;
- the receipt `devtools/zeroshot/tasks/s1a1b2-gate-barrier-receipt.md`.

Not touched: engine.py (the gate path is s1a1b1's; s2a2's binding symbols), authority.py, cli.py, tui/*, setup.py, planning.py, docs other than REFERENCE.

Audit (6a537b5):
- `Runs.start` runs.py:607-673:
  - revision approval :616-619; HEAD `base` :634; `self.refresh()` :640;
  - documents :653; bootstrap :654; first persistence :665.
- `retry` :1334, `answer` :1361, `accept_proposal` :1388 all call `start`. `resume` :1030-1055 does not call `start`; it copies `lineage(r)` (:1043-1045), with `LINEAGE` :78-79.
- Profile:
  - bound `Authority.profile` authority.py:372, set at cli.py:138; `Profile.guard` process.py:693-711; `live_digest` :722.
  - `Delivery.guard` delivery.py:558-562 is caller-side only.
  - Callers: cli.py:647, :764, :784, :789; tui/controller.py:663, :760, :832.
  - Authority construction sites (finite inventory, gate8): cli.py:809, :824, :893; tui/controller.py:296 (profile bound through cli.App :138, controller :300). Production main passes `profile=True` (cli.py:1045, :1048).
  - Also covered: the textual watch path tui/app.py:2702 (`watch_run`) and the two composition tests of tests/test_fixture_scope.py (`cli.main`/`tui.run` composition, :9, :118).
  - `Profile.status(write=True)` may write the sidecar `process-state.json` (process.py:546-593, :10, :387); `status(write=False)` writes nothing. Refusal families: never/missing/malformed → `process.pending`/`process.missing`/`process.invalid` (:697-702); `ProfileChanged` → `process.changed` (:69-71).
- Override helpers: authority.py `override_reason` :819, `override_matches` :828 (`verdict_field`, `subject`), `gate_stale` :338.
- Catalog: `plan.gate_stale` :202, `process.unbuilt` :365.

Rules:
- R-1 Scope: parent R-1. With a bound profile whose `gates.task == "off"`, or a fixture authority (`authority.fixture_id is not None`) without a profile, every graph, record, digest, screen and refusal is byte-identical. No `admission` field is written on such attempts.
- R-2 Authoritative config, fail-closed:
  - `Runs.start` itself reads the live resolved config from the bound `self.authority.profile` via `status(write=False)`, whatever the caller passes and whatever `Delivery.guard` returned. A caller-supplied None, off or stale Status never bypasses it. There is no admission argument.
  - never/missing/malformed → `process.pending`/`process.missing`/`process.invalid`.
  - A native authority (`fixture_id is None`) with no bound profile refuses (`process.pending`); it is never treated as off.
  - The native unit fixtures that start attempts bind an accepted off profile explicitly (write-set). No test-only bypass exists.
- R-2r Roles: under `gates.task == "required"`, the execution roles must equal `status.resolved.roles()` for worker/reviewer/steward. Caller roles that differ are refused with `ProfileChanged` (`process.changed`) before any side effect. A gate on config A therefore never admits a runtime with roles B.
- R-3 Validity: `task_gate.valid(record, live)` is true only when all of these hold:
  - Input precondition: record has passed s1a1b1 store validation. The barrier consumes that validated record; it does not repeat native projection validation. Native succeeded, or the presence of terminal/output_digest, is not sufficient evidence of validity.
  - the record is `concluded`;
  - `critic_verdict == "accepted"`, or an override that passes `override_matches(task_gate.evidence(record), override, verdict_field="critic_verdict", subject=SUBJECT)`;
  - `identity_matches(record["identity"], live)`;
  - `record["plan_revision"]`, `["approval"]` and `["milestone"]` equal the live revision, approval and milestone.
  A gate from another revision with an equal identity triple is refused (`task.gate_missing` for this revision).
- R-4 Barrier: parent R-4.
  - Placement and inputs: in `Runs.start`, after the revision/milestone checks and HEAD `base` (:634) but before `self.refresh()` (:640). It computes `gate_manifest(milestone_id, plan_revision, context)` and the live identity (artifact digest, live config digest, `base`).
  - Selection: the newest record for (revision, milestone) decides.
    - none → `task.gate_missing`;
    - preparing/submission_unknown/observing/detached/observation_blocked → `task.gate_running`;
    - rejected without override → `task.gate_rejected`;
    - native_failed/output_invalid → task.gate_failed, including a valid output_invalid record whose terminal and output_digest are both None.
    - identity mismatch → `task.gate_stale`.
  - No side effect: no run record, worktree, branch, refresh write or store write.
- R-5 Admission linkage: a required attempt stores `admission = {"gate": <id>, "config_digest": <live digest>}`. Off attempts have no such key.
  - `validate_run` checks:
    - that `admission.gate` exists in `state["gates"]`;
    - that the gate's `plan_revision`, `approval` and `milestone` equal the run's;
    - admission.config_digest equals gate["identity"]["resolved_config_digest"]. Never substitute digest(gate["config"]) or recompute historical admission from live rule files (process.py:261 hashes version/config/rules).
    Anything else is `store.invalid`.
  - `LINEAGE` copies `admission` when present, and a successor must carry its predecessor's admission.
  - `Runs.resume` inherits that linkage and reads the frozen config through it (the gate's `config`), never the live profile. It neither requires a new gate nor substitutes the current config.
- R-6 Override: parent A-6 rules. `Delivery.override_task_gate(gate_id, reason)` uses `override_reason`, and is allowed only on a concluded, current (R-3 identity and revision) rejection. It stores `override = {reason, verdict, evidence_digest}`, and `critic_verdict` stays.
- R-7 Text: five catalog families. Remedies are generic ("запустите проверку задач", "пересмотрите план или переопределите с причиной"). No key or CLI command is named until s1a1c. REFERENCE.md is regenerated.
- R-8 Fixtures: every literal home path in tests is under `/home/user/`.

Acceptance (unit tests; deterministic fixtures; FixtureEngine gates from s1a1b1; no network or provider). Each test names its production entry point, its oracle and its control.
- A-3 Barrier (parent A-3):
  - Entry points: `Delivery.start`/`new_attempt`/`answer`/`accept`; the CLI App and the TUI controller where a pilot already exists; and direct negative calls of `MilestoneRuns.start`, `retry`, `answer` and `accept_proposal`, with `Delivery.guard` bypassed and no Status.
  - States: no gate; running; rejected; exhausted; critic_failed; session_lost; output_invalid; stale by artifact, by config, by rules, by HEAD; a gate of another revision with an equal identity triple.
  - Oracle: the named family, plus a byte snapshot of the store and of the sidecar `process-state.json` (or its absence), and a listing of the worktrees directory, all unchanged.
  - Control: the same call is allowed after an accepted gate and after an override.
- A-3p Invalid-output records: use validated s1a1b1 fixture records for both output_invalid shapes: retained malformed raw output, and terminal=None/output_digest=None. Both classify as task.gate_failed; listing and preview remain readable. Start and override refuse without changing store or sidecar bytes, creating worktrees, or writing admission. Control: a concluded accepted gate permits the same start. Reuse s1a1b1 record construction; add no new dispatch fault injection.
- A-3c Caller Status: `Delivery.guard` patched to return None, and separately an off Status, while the bound profile says required → still refused. The control: the bound profile off → allowed, with no `admission` key.
- A-3f Fail-closed:
  - A native authority with no bound profile → `MilestoneRuns.start` refuses, with no side effect.
  - never/missing/malformed profiles → their families, with the sidecar unchanged.
  - The control: a fixture authority without a profile → allowed as on base.
- A-3i Inventory:
  - An AST scan pins the production `Authority(` construction sites to exactly cli.py:809, :824, :893 and tui/controller.py:296 (by enclosing function, robust to line moves). A new site fails the test.
  - For each site, plus the textual watch and the two composition tests, a start reaching `Runs.start` runs with the profile bound, or refuses.
- A-3r Roles: a required start with caller roles ≠ the profile's → `process.changed`, with no side effect. The control: equal roles → allowed.
- A-3b Owner paths: parent A-3b, via `Delivery.answer`/`accept`, with gates run through `run_task_gate(context=...)`. The original gate refuses the changed context. A gate on the exact context permits the start. A further change invalidates it.
- A-4 Validity: parent A-4 invalidation list, each producing `task.gate_stale`. A new revision needs its own gate.
- A-5r Resume:
  - A required attempt fails recoverably, then the gate goes stale and the profile changes. `Runs.resume` still succeeds; the successor's `admission` equals the predecessor's, and the config it reads is the gate's frozen one.
  - Controls, each → `store.invalid` on load:
    - a store whose `admission.gate` is missing;
    - a gate of another revision/approval/milestone;
    - a mismatched `config_digest`;
    - a successor admission differing from its predecessor's.
    - Check admission round trips with and without rule files; digest(gate["config"]) must refuse. Resume after live rule changes retains the original admission.
- A-6 Override: parent A-6 in full, with refusal without mutation for missing, running, malformed, stale, native_failed, session_lost and output_invalid gates.
- A-1 Off: `/1` and `gates.task: off` goldens (s1a1a `OffIdenticalTests`) and the plan-gate suites pass unchanged.
- A-7 Base failure: parent A-7.
  - The regression goes through `Delivery.start` with `gates.task: required` and no gate, expecting `task.gate_missing`. On base (s1a1b1 merged) it fails by a named assertion: `process.unbuilt` is returned.
  - Run the new tests on base with a scratch commit and report named failures and skips separately.
- Mutations, each killed by a named test:
  - (a) barrier after `self.refresh()`;
  - (b) config taken from the caller Status;
  - (c) barrier only in Delivery;
  - (d) `identity_matches` without `head`;
  - (e) revision/approval not compared;
  - (f) override allowed on a stale gate;
  - (g) `admission` dropped from lineage;
  - (h) resume requiring a fresh gate;
  - (i) `unbuilt` removed but `accept_proposal` unguarded;
  - (j) an unbound native authority treated as off;
  - (k) `status()` with write=True (the sidecar snapshot changes);
  - (l) caller roles accepted under required;
  - (m) `validate_run` without the `admission.gate` existence or config_digest check;
  - (n) resume reading the live config.

Size estimate: product 250-350 changed lines; new tests 700-1000; existing fixture bindings measured separately. Keep the scope together because barrier, admission and lineage enforce one invariant. Receipt and generated REFERENCE are reported separately. Above 600 changed lines: report measured insertions/deletions and rationale; merge requires explicit critic disposition.

Out of scope: record, dispatch and qualification (s1a1b1); TUI key, CLI/plain command, `[i]`, R-6 display texts, USER_FLOW/PROCESS_PROFILE (s1a1c); preset `/2` (S1d); merge gate (S1b/S1c); s1a2.

DoD:
- Worker (targeted): `python3 -m unittest tests.test_task_gate_barrier tests.test_task_gate_record tests.test_task_gate tests.test_plan_gate tests.test_plan_override tests.test_tui_plan_gate tests.test_process tests.test_runs tests.test_toolchain tests.test_reference` passes. The worker does not run the full suite.
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, the A-7 counts (named failures and skips separately), the mutation table.
- Orchestrator, before merge: the full suite, and `devtools/task_gate_qual.py` rerun on the Linux test host on the integrated candidate.
