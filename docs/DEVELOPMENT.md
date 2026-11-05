# Development harness

Status: active harness contract. Product behavior and user flows are defined in `docs/PRODUCT_CONTRACT.md`.

## 1. Roles

Direction (owner, 2026-11-03): Sonnet workers, Opus reviewers, an Opus architect; design review by
the Elephant-Goldfish method. Background: `docs/designs/2026-11-03-egm-pivot.md`.

| Role | Who | Does |
|---|---|---|
| Owner | person | goals, product decisions, actions reserved below |
| Architect (Elephant) | Claude Opus 5.5 in the main checkout | designs, contracts and acceptance checks, run decisions, integration, full suite, local commits, `STATE.md` |
| Goldfish ("Astra" in the owner's words) | fresh Opus via `devtools/goldfish.sh`, read-only tools, no conversation | one review pass over a non-trivial design, and a comprehension pass over contracts whose check encodes intent; an extra opinion that looks for omissions without our context, not an authority |
| Worker | Claude Sonnet 5.5 under the development slice runner `devtools/slice_run.py` (not part of the product), one worktree per slice | one slice from a contract |
| Reviewer | fresh Claude Opus 5.5, no tools, contract + acceptance + diff only | every slice by default |

A model named in a role is a target, not evidence of availability; never substitute a cheaper one silently.
The owner keeps: push, tags, releases, credentials, provider login/logout, and product trade-offs.

`devtools/zeroshot/` (run.sh, milestone_run.py, ORCHESTRATOR.md, preamble.md) is legacy: not a development path.
Keep it only while existing tests reference it.

## 2. Design, slices and contracts

1. Read `STATE.md`, the product contract and the code on the actual path. Never overwrite owner changes.
2. Non-trivial work starts with a short design in `docs/designs/YYYY-MM-DD-<slug>.md`: problem with evidence,
   goals and non-goals, alternatives, risks, slices. One Goldfish pass; the architect resolves every Blocker and
   Major as accept, reject or partial with a reason, in the document. A finding the architect disputes is answered
   with evidence in that reviewer's own session (`goldfish.sh --reply`), for the truth, not to win; the reviewer
   concedes or keeps it with evidence, and the outcome goes into the document. Re-review only unresolved findings.
3. Who writes a change: an open engine/product decision is decided or spiked by the architect first; about 25
   lines or fewer with the code already in context, the architect; up to ~400 changed lines, ~5 files, one
   acceptance check and a contract within 3 KB, a worker; anything larger or two behaviours, split first.
   These are another project's numbers; recalibrate them from this repository's ledgers.
4. A contract is TOML (`devtools/slice-contract.toml`), at most 3 KB: allowed files, acceptance check, gates,
   brief with every decision already made. The worker has no network, no `.local`, no git writes and no one to
   ask; if something is missing it replies `BLOCKED: <what>`.
5. Before a contract is started: grep `tests/` for every string, value, name and argument the change touches and
   list each test module that pins one in `files`, with the exact expectation to change (until T2 removes the
   pins). `slice_run.py start` refuses a contract that does not parse, allows a file under a protected path, is
   over 3 KB or has no `red_contains` naming a behaviour, and a run without a `lane_gate`.
6. A check is not a durable test (W0 design 3.3, F0). The mechanisms, all in `devtools/slice_run.py`:
   - The acceptance check is the slice's oracle, never committed: standalone modules that the runner copies into
     the worktree's `.slice/` (it ignores itself), restores before every green run and locks. The check names its
     paths, e.g. `PYTHONPATH=.slice:.:tests python3.13 -m unittest s1_acceptance` (checks run with
     `PYTHONSAFEPATH=1`, so `.` must be named and nothing planted in the tree answers for the oracle; run the
     modules directly, not through `fasttest.py`, which sets its own `PYTHONPATH`). Never overlay an existing module.
   - Red on behaviour: `red_contains` is required and names the failure (a result, a state or an error family), never
     the check's own module; a check that cannot import its own module is an invalid contract, before any worker.
   - A durable test is part of the change only when the brief asks for one (a named risk, a defect that escaped to
     `main`, words the owner must see), declared in `[ratchet] new_tests`. The ratchet refuses any other new test,
     a new sentence assertion, test module or criterion-named test, and a dropped assertion, unless the contract's
     `[ratchet]` table declares each as `"<id>: <reason>"`. Direct commits get the same ratchet from the
     `commit-msg` hook (`git config core.hooksPath devtools/hooks`), with exceptions as message trailers
     (`Ratchet-new-test: <id>: <reason>`).
   - Order: the check red on the base; the run's `lane_gate` (here `python3.13 devtools/fasttest.py`, the default
     lane) on the base unless that tree already passed it in this run; the contract review (`contract_review`, on by
     default: a fresh reviewer with read-only tools on the base tree looks for paths the contract does not name,
     decisions that miss its result, scenarios its check does not exercise, and pins outside its files; a rejection
     stops the slice before any worker); the worker; then paths, scope, size and the
     ratchet; the check green; the checks of the slices this run already passed (a later slice keeps their
     behaviour unless it lists them in `supersedes`); the contract's gates; the lane; the tree must be unchanged by
     the checks; the reviewer. A lane failure in a module outside the contract's files makes the worker reply
     `BLOCKED`: the contract missed a pin.
   A failed slice may only get a stronger check; a weaker one needs a recorded reason, and a rerun with a changed
   contract is new work, not a first pass.
7. Run folder `.local/slices/<run>/` (`run.toml` with `lane_gate`, or `"none: <reason>"`, `contracts/<id>.toml`, `contracts/<id>/`
   acceptance files). Passed slices land on `slices/<run>`, never on `main`.

        python3.13 devtools/slice_run.py start .local/slices/<run>   # tmux session slices-<run>
        python3.13 devtools/slice_run.py wait  .local/slices/<run>   # only without the Herdr monitor below
        python3.13 devtools/slice_run.py status|ack|retry|skip ...

8. Integration: the architect reads the diff, including every edit of an existing test (a removed assertion
   must name the removed behaviour), on `slices/<run>`, runs the default lane once on that exact tree (the full
   lane too for a release candidate or a change to stores or the engine), applies the baseline rule below, and
   only then moves it to `main` with a local commit or fast-forward.
9. Report implemented, reviewed, verified and merged separately. Human intervention beyond the declared
   autonomy is a harness failure to record, not a success.

Not blocking the architect (Herdr): once per session, `python3.13 devtools/slice_monitor.py up --tab` names the
architect's agent and starts the monitor and the status board in a background tab `slices`; the owner's tab shows
only the architect. The architect starts a run with `slice_run.py start` and ends its turn or keeps working on
something else; it never waits on a run inside a turn. On a wake or a silent runner the monitor waits until the
architect's agent is idle and prompts it once (recorded as `architect_prompted` in the ledger); a blocked or missing
architect becomes a Herdr notification. Helper agent sessions (probes, subagents) also go into a background tab
(`herdr tab create --no-focus`), never a split of the owner's tab.

Stop rules (slice runner defaults): 2 rounds per slice, the same failure twice stops at once, the architect wakes
after each `wake_after_passed` passes and on any failure, silent worker killed after 11 min, 1 h wall per agent.
Do not ask for confirmation of routine technical decisions.

Working with the owner (a lesson of 2026-11-05, after hours of technical questions put to him): the owner states goals
and says yes to plans; every technical decision is the architect's. A question reaches the owner only when its answer
changes a goal, a requirement or a non-goal, and then as one question with the default already taken. A design reaches
him as a plan with its decisions made and its distance to the target flow, never as a list of options.

## 3. Verification policy

A check result is produced by executing code, never by prompt judgment. The result includes:

```text
name, argv, cwd, environment identity, commit, tree,
started_at, ended_at, status, exit_code, bounded_output
```

Required rules:

- nonzero, timeout, spawn failure, missing interpreter, and unrun checks are not passes;
- automatic merge requires at least one real passing project check;
- baseline failure blocks automatic merge by default;
- a claimed baseline failure requires reproduction on the named base SHA, not a matching test name or model assertion;
- checks run on the exact integrated candidate before merge;
- any post-check edit invalidates the evidence;
- no pipeline may print a failure and still exit successfully;
- no manual fixup may bypass a failed or missing review.

The final LLM reviewer may add semantic findings, but its accepted verdict is necessary rather than sufficient where both review and executable checks are required.

## 4. Test layers

The suite is being rebuilt from scratch (owner, 2026-11-04; roadmap T2): minimal tests from the owner's jobs to be
done and the named risks, by module contract. Until the T2 design lands, a new test checks behaviour through a public
boundary and pins text only where the owner must see those words.

A change to the architect's behaviour (its prompt, tools or modes) is gated by the evaluation rig
`devtools/arch_eval/`: on a frozen snapshot, real model, at most two runs at once, it must not be worse than the
baseline on premature plans and missed plans.

### Pure behavior tests

Use for state transitions, plan validation, autonomy, graph projection, and other deterministic rules. No Textual, provider, or incidental internal-name assertions.

### Integration tests

Use real Git, worktrees, files, subprocesses, stores, and Application Service operations. Replace only external provider/engine transport where determinism requires it.

### Contract tests

Verify the public boundaries between zplan and Zeroshot, provider adapters, check runner, graph documents, and durable stores. Use small adversarial fixtures for malformed data and lifecycle uncertainty.

### Terminal scenario tests

Drive a small number of complete user intents at 80x24 and a wide size: message history, plan, non-linear graph, error, merge, reopen, and `/new`. Assert visible behavior and durable state, not private handler names or pixel snapshots.

### Installed real-provider qualification

Run the same installed path the owner uses. No fixture-only claim can substitute for it. Every release candidate repeats all critical scenarios, not only the delta from the previous candidate.

### Test economics and evidence

- Protect current behavior and named risks, not test counts, private structure, historical stage names, incidental wording or decorative layout. There is no target number of tests.
- Check each behavior at the cheapest trustworthy layer. Reserve full terminal journeys for visible intent, accessibility, focus and production wiring; keep one real end-to-end path for each critical contract instead of repeating the same behavior through many shells.
- Keep adversarial coverage for merge admission, exact-candidate identity, durability, replay, crash/concurrency, scrubbing and process/filesystem safety. Do not remove it as duplication merely because several tests exercise the same module.
- A defect that escaped to `main` earns a focused regression; a finding fixed inside a slice does not. Tests leave with the code they test: removing a behaviour removes its tests, declared in `[ratchet] removes`. Any other removal needs an assertion inventory that follows helpers and one cold review of the batch; coverage percentages and mutation scores alone are not evidence (2026-10-28 audit). When a neutral change breaks a text assertion, assert the state, error family or command instead of re-pinning the new text.
- A deterministic verifier runs the full suite once on the final candidate. An independent reviewer primarily inspects missing boundaries and runs targeted probes; it need not ritually repeat the full suite on an unchanged tree. Any later edit creates a new candidate and invalidates affected evidence.
- Report passed, failed, skipped and not-run separately. A missing dependency for a required lane is a preparation failure, not a pass. Stateless design review complements executable tests and never replaces them.

### Flakes and environment

Test commands use a sanitized environment with explicit terminal, locale, home, temp, and interpreter configuration. A passing rerun does not erase a flake: quarantine it with an owner and diagnosis. Never weaken the assertion merely to make the suite green.

## 5. Tool policy

### ast-grep

Use the installed `ast-grep` or `sg` CLI for structural questions: call sites, declarations, signature migrations, repeated code shapes, and codemods. Use normal text search for strings, comments, filenames, and documentation.

Rules:

- validate a pattern against a representative positive and negative sample;
- always inspect search results and a dry-run before applying a rewrite;
- review `git diff` after a codemod and run behavior checks;
- do not use ast-grep rules as a replacement for behavior tests.

### Ponytail

Ponytail is a ruleset, not needed as another plugin in the execution runtime. Apply its useful order: no code, existing repository code, standard library, platform capability, installed dependency, then minimal new code. Never simplify away validation, safety, accessibility, or error handling.

Do not use its code-volume benchmarks as this project's success metric. Measure working user journeys and escaped defects.

### context-mode

The outer interactive development session may use context-mode for large logs, repository-wide mechanical analysis, and compaction recovery. Project-level `.mcp.json` registers it for that session only.

It must not be injected into zplan's curated worker/reviewer/critic homes or release-evidence runs. zplan already owns its durable journal; context-mode is not a second source of product truth. Raw evidence must remain on disk even when a compact projection enters the model context.

Do not enable its hosted analytics or send project content to external services without explicit owner approval.

## 6. Current local commands

```sh
python3.13 devtools/fasttest.py                 # default lane: skips tests/full_lane.txt (slow journeys)
python3.13 devtools/fasttest.py --lane full     # every test: release candidates, store or engine changes
python3.13 devtools/ratchet.py main             # test ratchet of the working tree against main
(cd devtools && python3.13 -m unittest slice_run_test ratchet_test)   # slice runner and ratchet tests, fake claude
git config core.hooksPath devtools/hooks       # once per clone: the ratchet on direct commits
devtools/goldfish.sh DOC .local/goldfish/<slug> # one Goldfish pass over a design
devtools/goldfish.sh --reply .local/goldfish/<slug> PERSONA FILE   # answer a disputed finding in its session
python3.13 devtools/arch_eval/arch_eval.py run REV OUT [--only ids] [--repeat N]   # architect rig, real model
python3.13 devtools/arch_eval/arch_eval.py score OUT [OUT ...]          # its metrics from the stores
python3.13 devtools/export_check.py             # export/private-content check when configured
ast-grep --version                              # structural-search prerequisite
context-mode doctor                             # outer interactive session only
```

The merge profile for this repository must name a real check. Changing a check command or its environment requires requalification.

## 7. Definition of Done

A change is done only when:

- its observable behavior is implemented;
- the focused and integrated checks pass on the exact candidate;
- required independent review is complete on that same candidate;
- no unresolved blocker or unclassified failure remains;
- conversation/state/history invariants are preserved where relevant;
- the UI remains usable at 80x24 and a wide size for touched flows;
- evidence and any manual intervention are recorded;
- no push, release, or external action was taken implicitly.

A green unit suite alone is not a product-complete claim.
