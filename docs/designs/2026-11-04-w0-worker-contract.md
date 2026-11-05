# W0 design: the worker contract on Zeroshot 11

Status: revision 2 (2026-11-05). Revision 1 had one Goldfish pass (`.local/goldfish/2026-11-04-w0-worker-contract/`:
comprehension, design_critic, zoom_out; section 8 resolves every Blocker and Major). Revision 2 also takes the owner's
decision of 2026-11-05: zplan's graphs become fixed Zeroshot profiles that zplan ships and knows, now rather than
after evidence (section 3.1). Builds on the accepted boundary (`docs/designs/2026-11-04-zplan-on-zeroshot-11.md`) and
the roadmap's W0 steps 6-7. Evidence is private: `.local/w0/` (`NOTES.md`, `GRAPH.md`, `ZS-R1.md`, `ZS11-CLI.md`,
`slices.jsonl`, `zplan_worker_patches.json`).

Terms:
- *Owner*: the person who uses zplan.
- *Architect*: zplan's product Codex session that talks to the owner (`PRODUCT_CONTRACT.md` section 2).
- *Elephant*: the development architect of this repository (`DEVELOPMENT.md` section 1).
- *Goldfish*: a fresh, read-only reviewer with no conversation; one pass over a document.
- *Worker contract*: what tells a worker what to deliver and a reviewer what to accept:
  - zplan's milestone graph and its instructions (`terminal_planner/milestone.py`), for the owner's projects;
  - the slice contract and the runner's rules (`devtools/slice_run.py`, `DEVELOPMENT.md` section 2), for this
    repository.
- *Check*: anything run or observed to decide whether work is accepted.
- *Durable test*: a test committed to the project.
- *Profile*: a named Zeroshot graph and runtime (`zeroshot profile`).
- Node names (`milestone.py:300`):
  - `preflight` judges the briefs before work;
  - `final_verify` checks the whole milestone after its tasks.
- *Delivery binding*: a graph's own push or pull request.
- *Ratchet*: `devtools/ratchet.py`, the test-growth gate of the slice runner.
- *Probe*: the 2026-11-04 real-provider runs E1-E9 (`.local/probe/REPORT.md`).
- Track and milestone names: Z11, A0 and T2 are tracks, M4 and M5 are later milestones
  (`docs/plans/2026-11-03-roadmap.md`).

## 0. The target flow (TO-BE)

The example used throughout: a new repository `notes` with one commit and no tests. The owner's goal: "tags on notes,
search by tag, a count command".

**The owner:**
1. Opens zplan and chooses an autonomy level. zplan says the project has no checks.
2. Writes the goal and gets an answer. Any question comes with its default.
3. Sees one plan card. It shows:
   - the goal, the requirements with examples and the non-goals;
   - three slices: S1 tags, S2 search (after S1), S3 count (independent);
   - the Goldfish retelling and the critic's findings with their resolution;
   - the checks: "none yet, S1 adds pytest".
4. Says yes once.
5. May watch the real graph and the timeline, or leave. He is not asked anything unless the answer would change the
   goal, a requirement or a non-goal, or two new attempts have failed.
6. Reads one report:
   - what merged;
   - the architect's decisions and assumptions;
   - the checks that passed and what is not verified;
   - at most one proposal to change the system.

**The system** (who acts in brackets):
1. Setup (zplan). It installs Zeroshot 11 and its three profiles into its own Zeroshot config directory (3.1).
2. Conversation (architect). It reads the working tree, and the history is durable.
3. Draft (architect, then zplan code). The architect drafts the plan and the code validates it. Format errors stay
   with the model.
4. Base checks (zplan). They run now, on the base commit (`PRODUCT_CONTRACT.md` section 2).
5. Plan check (Zeroshot, profile `zplan-plan-check`). Goldfish reviews once, and the architect resolves the findings.
6. Approval (zplan). The owner's yes freezes the revision, the base, the configuration, the profile's exact content
   (its hash) and the checks.
7. Runs (zplan, then Zeroshot). There are two milestones: M1 (S1 then S2) and M2 (S3). Each one runs in parallel in its
   own worktree. zplan supplies the frozen profile copy, the task input and zplan's runtime (sandbox, models, Active
   Memory off, no delivery).
8. Inside a run (Zeroshot). The steps are:
   - per task: the worker, then the acceptance and code reviews in parallel, then repair;
   - a worker who lacks something answers `BLOCKED` instead of working around it (3.4);
   - the final check.
9. Observation (zplan). Engine events become the graph and the timeline, and runs outlive the TUI.
10. Verification (zplan). zplan commits the candidate and runs the project checks on that exact tree.
11. Recovery (architect). A conflict leads to a plan revision and a new attempt, at most two without the owner.
12. Merge (zplan). zplan integrates the base, reruns the checks and merges the exact candidate. Automatic merge needs a
    passing check, and there is never a push.
13. Plan end (zplan, then architect). zplan writes a per-plan record, and the architect writes the report and at most
    one proposal (3.6).

**Not part of W0.** A plan that introduces the project's first check meets today's red-base rule (roadmap F14). That
rule is designed under F14, not here.

## 1. Problem, with evidence

**P1. The legacy contract turned checks into durable tests; this is a hypothesis for the current one.** From
2026-10-10, 72,035 of the 80,126 test lines added to `main` came through merges of the legacy Zeroshot harness
(`NOTES.md:5-10`). Its rules made each check stay as a durable test:
- the worker mapped every criterion to a test;
- the acceptance reviewer accepted a criterion only with a test name or a command result;
- every repair kept earlier reproductions (`NOTES.md:35-42`).

Advice about proportion was added at least four times (`NOTES.md:30-32`). These are first-cut counts: NOTES steps 2
and 5 are not done. The weekly ratio mixes sources (`NOTES.md:22-28`). The mechanism the evidence supports is
*requirements*, not missing advice. This design removes requirements. It adds no advice (3.2).

**P2. The product requires a test from its worker.** The rule: "in a project with a test setup, a behaviour change
... that existing tests do not cover gets a relevant test" (`milestone.py:35-38`). The acceptance review must not
"accept a worker claim without evidence in the diff or tests" (`milestone.py:504-505`). On the probe's scratch projects
the workers wrote 656 test lines for 256 product lines (`NOTES.md:63-65`). Reviews rarely reject there: acceptance 1
of 33, code review 0 of 33 (`NOTES.md:89-91`). So the volume comes from the worker's own rule, not from repair rounds.
Zeroshot 11.0.0's `software-change` template never says "test" (`ZS11-CLI.md`, end).

**P3. The foreman exists, its largest trigger is pins, and a gap found mid-run has no route.**
- `preflight` stopped 15 attempts on zplan's own development through zplan's graph
  (`devtools/zeroshot/CALIBRATION.md:130-271`). It found 0 in the 36 product sessions of 10-29 to 11-04, which were toy
  goals (`NOTES.md:89`).
- Of the 15, 8 were a test outside the write set that pinned or exercised the changed code (for example `:131`, `:156`,
  `:180`, `:189`), 5 were wrong facts or contradictory criteria in the brief, 1 was a generated document missing from
  the write set, and 1 is unrecorded. Pins also stopped 9 rounds of the slice runner (`NOTES.md:70-72`).
- A gap found mid-run became a `review_conflict` 6 times (`CALIBRATION.md:143`, `:152`, `:153`, `:156`, `:239`,
  `:286`).
- Product agents run with `danger-full-access` and no approvals (`resources/agent_profile.toml:2-3`). Nothing denies
  them, and the write set is advice.
- The product worker is never told to stop instead of working around a gap (`milestone.py:496-500`).
- The architect gets a conflict as a label plus 160 characters (`live.py:37`).
- `zplan_rebrief` keeps the brief (`architect_tools.py:111-112`), so a wider write set needs a plan revision.

**P4. zplan builds its graphs in code, and nothing aggregates a plan.**
- Five graph builders live in code: planner, plan check, task gate, merge critic and milestone (`engine.py:815-1249`,
  `milestone.py:333-593`). None is a profile.
- Verdicts reach the architect one at a time (`feed.py:246-262`). The feed is pruned on acknowledgement
  (`feed.py:355-365`). There is no per-plan record, no stored final report and no token total per plan.

**P5. Nothing measures whether a result is right without trusting its own tests.**
- The probe's results were checked by hand (`.local/probe/REPORT.md`).
- `devtools/arch_eval/` replays owner messages through the architect and stops after the plan check
  (`arch_eval.py:2-13`).

## 2. Goals and non-goals

Measured on the rig (3.7). Each goal runs twice per arm, and the decisions use sums over goals.

| Goal | Measure | Target |
|---|---|---|
| G1 Tests where asked | per goal: total durable test lines; unrequested test lines (requested is known from the frozen brief); sentence assertions | unrequested lower than the baseline in sum; total not higher; a goal at 0 stays at 0 |
| G2 Correctness and later protection | held-out script on the result; then a follow-up goal on the merged project and the first goal's script again | neither lower than the baseline |
| G3 Stop, not work around | a planted gap that `preflight` does not see; false blocks on the other goals | the worker declares it, the run ends as a conflict carrying the full message, nothing merged works around it; 0 false blocks |
| G4 Friction | repair rounds per task; tokens per node role; wall time without provider pauses | not higher than the baseline |
| G5 Profiles, same behaviour | zplan runs its graphs from the installed profiles | the run's graph document equals the code-built one for the same input; an edited profile that fails the gate is refused with the reason (tests) |
| G6 Tiers hold | an architect proposal that would weaken tier 1 | refused (tests) |
| G7 Reflection | the end of a plan | a per-plan record; at most one proposal citing it; the owner's yes commits the change (tests) |

Revert rule: if G2 is worse on the sum, or on any goal after one re-run, the instruction change (W0.3) is reverted.
Development harness: the next runs' ledger against `.local/w0/slices.jsonl` (first-round passes, blocked causes,
lines of acceptance kept).

Non-goals:
- cutting or merging graph roles: profile v1 is today's graph (3.1);
- deterministic task-level checks (M5);
- a new plan field: the plan format is A0's open failure, at 6.3 refusals per plan turn (`.local/a0/REPORT.md` section 8);
- the F14 rule above;
- Active Memory on;
- models or harnesses per role (M4);
- upstream Zeroshot changes;
- rewriting zplan's existing tests (T2).

## 3. Design

### 3.1 Graphs as fixed profiles (the owner's decision, 2026-11-05)

- zplan ships three profiles:
  - `zplan-milestone`, from `milestone_graph`;
  - `zplan-plan-check`, from `goldfish_graph`;
  - `zplan-merge-critic`, from `merge_critic_graph`.

  The planner graphs leave with M6. The task gate (`gates.task`, off by default) keeps its code graph until it is
  either used or removed.
- **Version 1 is today's graph, unchanged.** The parts that vary move into the input:
  - The loop bounds use `maxIterationsInput`. It exists in 11.0.0 (`ZS11-CLI.md`), and a spike admits it with
    `--validate-only` first.
  - The validation command is already in the input (`milestone.py:603-610`).
  - Anything that differs per installation is written when zplan installs the profile.
- **Where.** zplan installs the profiles into its own Zeroshot config directory (`engine.py:1391-1393`) at setup and
  upgrade, with a content hash. `zeroshot ui` edits the CLI's local store (`ZS11-CLI.md`), so zplan documents the
  command that opens the editor on zplan's directory.
- **At approval.** zplan reads the profile, runs the gate below and freezes its exact content into the attempt
  (`PRODUCT_CONTRACT.md:122`). The attempt then runs with `--graph` as today (`runs.py:2120`). A later edit affects
  only later approvals.
- **The profile gate (tier 1).** Before any profile content is used, zplan checks that:
  - the input accepts zplan's milestone input, and the output is the `signal` record;
  - it keeps the manifest contract, because a finished run's manifest is evaluated (`runs.py:1419-1451`,
    `milestone.py:1-8`);
  - every `done` exit passes a verifier with a fresh session;
  - it has no delivery binding (`software-change` delivers a pull request by default: `ZS11-CLI.md`);
  - its runtime comes from zplan: permissions, Active Memory off, models by role. A node name unknown to
    `milestone.ROLES` takes its role by kind: a step is a worker and a verifier is a reviewer;
  - the engine admits it (`--validate-only`, including the 65,536 assignment ceiling noted at `milestone.py:395-399`).
- **The TUI** labels known node names and draws unknown ones by their raw name, through the fallbacks that exist today
  (`live.py:48`, `tui/scheme.py:86-87`).
- **The contract.** `PRODUCT_CONTRACT.md:141` (a zplan graph editor) is amended: the editor is Zeroshot's, and zplan
  renders whatever graph it runs.

### 3.2 A check is not a durable test (product)

A worker writes a durable test only when:
- (a) the brief asks for it, in a criterion or in `dod`;
- (b) the project's root `AGENTS.md` asks for it. That file is the only rules file the milestone roles see: Codex loads
  it natively, and zplan delivers no rules to them (`docs/spikes/B1_B3_B4_RULES_AND_FACTS.md:23-28`);
- (c) the task fixes a defect that escaped a merge.

Otherwise the worker proves each criterion by running it, and reports the command and its output. A durable test goes
through a public boundary. It does not break on a neutral change: a change of wording or of private structure that
changes no behaviour. Output that *is* the contract may be asserted: a CLI's output format, or words the owner must
see (`DEVELOPMENT.md:104`). Examples:
- `greet --shout` prints `HELLO`: asserting it is allowed;
- a status line's exact sentence that the owner does not depend on: asserting it is not.

The changes:
- **Worker** (`VERIFY_RULE`, `milestone.py:35-38`): replaced by the rule above. The instructions state that rule (b)
  overrides zplan's default. The repair node keeps the same rule.
- **Acceptance review** (`milestone.py:504-505`):
  - "evidence in the diff or tests" becomes "evidence in the diff and in the commands `workerReport` reports, with
    their output";
  - a missing test is not a defect unless (a) to (c) applies;
  - "run no checks" and the read-only prefix stay.
- **Code review and `REVIEW_BAR`:** unchanged. A test that pins a neutral change, or one nobody asked for, is a
  `note:`. The rig counts the notes. If workers ignore them, a later change of `REVIEW_BAR` is measured on its own.
- **Deterministic facts.** At merge, zplan code computes two facts from git: the paths outside the union of the write
  sets, and the test lines added. They are shown on the merge card and kept in the per-plan record (3.6). They refuse
  nothing in W0.
- **The architect.** One line in `architect_method.md`: ask for a durable test in `dod` when a named risk or the owner
  needs one. It is gated by the A0 rig (`DEVELOPMENT.md` section 4) and lands with A0's next slice.

### 3.3 A check is not a durable test (development harness): F0, built 2026-11-05

The problem in this harness: the architect's acceptance checks stayed in the suite (3,319 test lines in the
slice-runner era, `NOTES.md:9`), a change broke pins in modules the contract did not list (`NOTES.md:70-72`), and
the architect's direct commits added tests with no gate at all (since 2026-11-03: 81 direct commits, 2,858 test lines
for 3,468 product lines, `git log --first-parent --since=2026-11-03 --numstat main`). The rules and their order are
`DEVELOPMENT.md` 2.5-2.6; the mechanisms, all in `devtools/slice_run.py` and `devtools/ratchet.py`:

| Need | Mechanism |
|---|---|
| The oracle never lands | acceptance modules copied into the worktree's `.slice/` (it ignores itself); a staged `.slice` path is `locked_path` |
| The oracle cannot be faked | restored from the contract folder before every green run; checks run with `PYTHONSAFEPATH=1` and name their paths, so nothing planted in the tree answers for it; bytecode is read from an empty prefix |
| Red on behaviour | `red_contains` required at `start`, never the check's own module; a check that cannot import its own module is `contract_invalid` before any worker |
| Durable tests only when asked | the ratchet refuses a new test not declared in `[ratchet] new_tests`; direct commits get the same ratchet from the `commit-msg` hook, exceptions as message trailers |
| Pins outside the contract caught in the slice | the run's `lane_gate` (the default lane) after the contract's gates; `start` refuses a run without one (`"none: <reason>"` opts out, recorded in `run_start`); on a lane failure outside its files the worker replies `BLOCKED` |
| A red base never charged to the worker | the lane runs on the base before the worker unless that tree already passed it in this run (`lane_green` by tree); a red base ends the slice as `lane_red_on_base` |
| The committed tree is the tree that passed | a check that changes the tree fails the slice (`tree_changed`) |
| A later slice keeps an earlier one's behaviour | the checks of the slices this run already passed run again; `supersedes` names a deliberate change |
| The contract's holes are found before a worker spends a round | the contract review: a fresh reviewer with read-only tools on the base tree checks paths, decisions, the check's coverage and pins; a rejection stops the slice (`contract_rejected`). Added 2026-11-05 after four of five failed rounds that day came from the contract |

Alternatives:
- **Remove the acceptance files after green** (revision 1): rejected, because the committed tree would differ from
  the verified one.
- **Hold the checks in `.local`**: rejected, because the worker could not run them to close its own loop.
- **Lane only at integration** (as before): rejected. A pin found there costs a new contract and a rerun; found in
  the slice, it costs one round or a `BLOCKED`.
- **Select the affected tests from the import graph** (T2's `affected.py`): deferred to T2. Until it is measured,
  the default lane is the honest gate.
- **An automated pin inventory at `start`**: deferred to T2. Removing the pins removes the need.
- **Keep the checks of earlier slices only within `depends`**: rejected. A slice can break any earlier one in the
  run, and the checks are cheap.

Risks and limits:
- **Less protection over time.** Without a durable test, nothing re-checks a behaviour after its run.
- **The lane's reach.** Tests in `tests/full_lane.txt` and `devtools/*_test.py` are outside it.
- **Lane time per slice.** The default lane took 391 s at `-j 9` on 2026-11-05, within `gate_timeout_s` 1200.
- **A flake can still stop a slice.** It is classified by the architect, never retried away.
- **The ratchet reads only `tests/test_*.py`.**
- **An architect's edit of an acceptance file mid-slice changes the oracle.** The rule stays: a changed contract is
  new work.

Success measure, over the next 10 slices against the slice-runner era of `.local/w0/slices.jsonl`:
- no acceptance line lands;
- every added test is declared in `new_tests`;
- lane failures are classified as a contract miss or a worker regression, and contract misses are counted until T2;
- first-round passes and wall time per slice are reported (lane minutes included).

### 3.4 Stop, do not work around (product task worker)

- **The worker.** When a task has a brief and its worker finds a gap, it makes no workaround edit. Its report starts
  with `BLOCKED: <kind>: <what>`, where the kind is one of:
  - `scope`: it needs a file outside `write_set`;
  - `brief`: criteria contradict each other or a non-goal;
  - `tool`: a command it needs fails to run; the report gives the command and its error.

  A task without a brief, and the repair node, keep today's rules.
- **The reviews.** `CONFLICT_BAR` (`milestone.py:46-49`) is amended: a worker's declared blocker with its evidence is a
  `conflict`. A reviewer's own missing tool still is not. The worker is a step, and a step's output cannot drive a
  guard (`ZS-R1.md` section 2), so the cost is one review round.
- **The record.** The conflict's full message, scrubbed and bounded at 4 KB, is stored with the attempt and reaches the
  architect. Today it gets a label and 160 characters.
- **The architect:**
  - for `scope` and `brief`, it writes a plan revision. In an approved chain the plan check's accepted verdict
    approves it (`tui/controller.py:1370-1371`). Then it starts a new attempt;
  - for `tool`, it either revises the plan to avoid the tool or asks the owner, because installing a tool is the
    owner's action;
  - at most two new attempts happen without the owner.
- **`preflight`** stays: it is the foreman that works (P3).
- **`foreman.py`** is decided by replaying it over the briefs of the stored plan revisions:
  - if it finds gaps that `preflight` missed, it is wired into the plan check;
  - otherwise it is removed, with `tests/test_foreman.py` and its use in `tests/test_dirty_head.py:20-23`.

### 3.5 Three tiers

| Tier | What | Who changes it |
|---|---|---|
| 1 Fixed in code | nothing starts without the owner's yes; only the exact verified candidate merges; automatic merge needs a passing project check (a manual merge is labelled unverified); a model never turns red into green; durable history; sandbox, grants and secrets; push, tags, releases and credentials stay the owner's; the profile gate (3.1) | a code change, reviewed as one |
| 2 Configurable | the process profile (`process.py:50`); the architect's method (`zplan.architect.md`); the project's `AGENTS.md`; the graph profiles (3.1); Active Memory | the owner's own edit, or his yes on the architect's proposal |
| 3 In the plan | plan revisions after a conflict, new attempts (at most two without the owner), merges within the level | the architect (`PRODUCT_CONTRACT.md` section 2) |

**Tier 1 holds whatever tier 2 contains, because code enforces it.** Validation applies where structure exists:
- the process profile is schema-validated (`process.py:155-157`);
- graph profiles pass the gate;
- an architect's proposal may not remove a check, turn a gate off, raise autonomy or touch a profile's gate fields.
  Those changes remain the owner's own edits.

Prose files, such as the method or `AGENTS.md`, cannot weaken tier 1 and are not validated against it. A missing
method file uses the shipped default, as today (`architect.py:408-420`). An invalid structured file is refused with its
reason.

### 3.6 The reflection loop (after the tiers)

- **The per-plan record.** A new store written as events happen, with bounded fields:
  - attempts and rounds;
  - the first line of each verdict;
  - conflicts with their message;
  - refusals and final-check verdicts;
  - tokens per node, from Zeroshot's status `tokenUsage`;
  - wall time without provider pauses;
  - at each merge, the facts of 3.2: test lines added and paths outside the write sets.
- **Plan end.** The plan ends when its last milestone merges or is dropped. The architect gets the record, and its
  report is stored as a timeline entry (`PRODUCT_CONTRACT.md` section 2). Today the report exists only as an
  instruction.
- **The proposal.** At most one per plan. A new tool, `zplan_propose_change`, puts the following on the owner's card:
  - a path (one of the tier-2 files);
  - the full new content and the resulting diff;
  - the record lines it cites.

  The architect is read-only, so on the owner's yes zplan writes the change and commits it, as the commit-proposal
  card does (`architect_tools.py:142-149`). This avoids a dirty base. The tool is allowed in the plan-end turn, and the
  card is the gate.
- **Active Memory** stays off. A rig arm with it on and off is optional slice W0.8.

### 3.7 The rig

- **Frozen plans.**
  - For each goal the Elephant writes an approved plan revision: briefs, write sets, criteria, and whether a durable
    test is requested.
  - The Elephant also writes a held-out script that tests the goal's user-visible behaviour. The script is never in
    the input or the project. One author writing both the brief and the script is a stated limit on its independence.
  - The architect's reaction to a conflict is a separate A0 rig scenario.
- **The driver.** It runs zplan's own milestone run path headless on scratch copies, from a seeded approved revision,
  so there are no architect turns. The held-out script runs on the candidate. The two arms differ only in the
  instruction texts of `milestone.py`, at one pinned zplan revision.
- **The goals:**
  - five single-milestone goals on the probe's projects (wordcount, notes, greet);
  - one harder multi-task goal;
  - one planted gap that `preflight` does not catch; this is checked by running `preflight` on it first;
  - one goal that asks for a durable test;
  - a follow-up goal per project for G2.
- **Counting:**
  - test files by path (`test_*.py`, `*_test.py`, `tests/**`, `*.test.*`, `*.spec.*`);
  - assertions by a counter that also handles pytest functions, since the ratchet's reads only `tests/test_*.py`
    classes (`ratchet.py:28-30`);
  - roles by node name from Zeroshot's run status. This replaces the instruction-prefix markers of `NOTES.md` and is
    the devtools script the boundary decision promised.
- **Arms** (the owner's question of 2026-11-05, "a separate graph of testers instead of workers that test";
  prior art in `.local/w0/TESTER-R1.md`, checked against the sources in `TESTER-R2.md`):
  1. today's instructions: the worker adds a test per behaviour change;
  2. the worker runs the project's checks and its brief's check but adds no kept test unless the brief asks (3.2);
  3. arm 2 plus a tester: the acceptance review runs throwaway probes of the behaviour in an isolated home, outside
     the tree. A failing probe goes to the architect for triage and blocks only once confirmed (about 80% of Meta's
     reported catching-test candidates were false after its assessors); it never counts as a pass or as the merge
     check; its false-alarm rate is measured;
  4. arm 2 plus a code-blind tester (it sees the brief, not the diff: AgentCoder's test designer) that writes kept
     tests, each admitted only if it fails on the base, passes on the candidate, is stable across reruns and asserts
     the public surface.

  Decision rule, fixed before the runs with its non-inferiority margin and sample size: the cheapest arm that is not
  worse than arm 1 on the held-out pass rate and on the follow-up regressions; ties go to fewer tests broken by a
  neutral change. A small sample detects only a large loss (2602.07900 saw 1.8-2.6 points lost, not significant over
  500 tasks, when tests were discouraged), so a "no difference" result is reported as such, never as equivalence.
- **The check is the bottleneck** (TDFlow: 94.3% with human-written tests, 68.0% at four times the cost with
  LLM-written ones). The held-out scripts follow the owner's acceptance examples where the plan has them, and every
  acceptance check is red on the base for its stated reason (F0) before any worker runs. No arm removes the worker's own
  check run: every documented harness gives the coding agent a check to close its loop.
- **Noise and budget:**
  - two runs per goal per arm, plus one more where the two disagree on the held-out script;
  - a run is stopped at 2 hours, and an arm at 12 hours of wall time;
  - tokens are recorded, and provider pauses are excluded from the timings.

## 4. Alternatives

| Alternative | Verdict |
|---|---|
| Profiles only after evidence (revision 1) | Superseded by the owner's decision. Version 1 is today's graph, so no behaviour changes with it |
| New graph roles: a foreman node, a test planner | Rejected: `preflight` already catches write-set gaps (P3) |
| More advice about proportion | Rejected: added four times without effect (P1). This design removes requirements instead |
| New rejection rules in the reviews (revision 1) | Deferred: they contradict `REVIEW_BAR`, and product reviews almost never reject (P2), so the measured minimal edit comes first |
| Reviewer probes of behaviour (revision 1) | Dropped: model-written code under full access (a security surface) and more minutes in a read-only role |
| Typed `blockers[]` with a guard (`ZS-R1.md` 7a) | Deferred: a step's output cannot drive a guard; the map-over-blockers form is unverified for non-empty arrays |
| One task per milestone, or a frozen `map` over the tasks (the boundary decision, section 4) | Deferred to a profile version 2, measured with the role outcomes on the harder goal |
| Write-set and test-volume refusals at the merge gate | Partly adopted: shown as facts in W0; a refusal only if the rig shows the instructions fail |
| Typed check kinds in the plan (`ZS-R1.md` 7b) | Deferred: the plan format is A0's open failure |
| Active Memory as the reflection loop | Rejected: no read-out (`zeroshot memory` has only `init`) |

## 5. Risks

**Security:**
- A worker can edit `AGENTS.md`, and reviewers then read the edited version (B1 spike). The edit shows in the diff,
  and its path counts as outside the write set (3.2 facts).
- Record lines carry model-written text from the project. A proposal built on them can change a lasting instruction,
  such as the method. The owner's yes on a visible diff is the only gate, and that is stated on the card.
- An owner-edited profile can drop a review. The gate refuses that.

**Other risks:**
- **Less protection over time.** Guarded by G2's follow-up phase. Automatic merge still needs a passing check, while a
  manual merge stays labelled unverified.
- **Rules beyond the root `AGENTS.md` do not reach workers.** Accepted for W0. Delivering frozen rules in the profile
  input is a later change.
- **Toy goals.** The harder goal is in the rig, and toy results alone cut no role.
- **Rig cost.** At most 12 hours of wall time per arm, tokens recorded. Removing the architect from the loop cuts the
  probe's cost.
- **Reflection noise.** One proposal per plan, with the record cited, tier 1 refused, and the revert rule.

## 6. Slices

| Slice | Result | Acceptance |
|---|---|---|
| Z11 | Zeroshot 11 by default, Active Memory off, the status reader allows `deliveryReceipt` | `docs/UPGRADE.md`: Linux qualification, full lane, real-provider smoke |
| W0.1 profiles v1 | spike (`maxIterationsInput`); install the three profiles; read, gate and freeze at approval; the editor command | G5: graph equality per input; gate refusals; the full lane |
| W0.2 rig | frozen-plan driver, goals, held-out scripts, counters, role outcomes; the baseline | baseline numbers, two runs per goal |
| W0.3 product instructions | 3.2 and 3.4 in `milestone.py`; the conflict message in the record; the merge-card facts | the rig against the baseline: G1 to G4; the revert rule |
| W0.4 development harness | Done as F0 (3.3) | `slice_run_test`, `ratchet_test`; the next runs' ledger |
| W0.5 `foreman.py` | the replay, then wire or remove | the replay's counts |
| W0.6 tiers | the table in `PRODUCT_CONTRACT.md`; proposal limits | G6 tests |
| W0.7 record and proposal | 3.6 | G7 tests; one live plan end |
| W0.8 (optional) | the Active Memory arm | the rig, memory on against off |

Order: Z11, W0.1, W0.2, then W0.3 and W0.4, the measurement, then W0.5 to W0.7. The architect's method line (3.2)
lands with A0's next slice. A0 S2b to S4 and T2 follow the rules of W0.3 and W0.4.

## 7. Decisions taken (the Elephant, 2026-11-05)

1. Profile version 1 is today's graph unchanged. Simplifying it (a `map` instead of task selection) is a measured
   version 2.
2. A profile configures the graph. Permissions, sandbox, Active Memory and models come from zplan.
3. A durable test is written only when the brief asks, `AGENTS.md` asks, or a defect escaped.

The slices of section 6 are steps of the roadmap (revision 11): W0.1 is P2, W0.2 is P6, W0.3 and W0.4 are P7, W0.5 is
part of P10, W0.6 and W0.7 are P8 and P9.

## 8. Resolution of the Goldfish findings (revision 1)

Reviewers: D design_critic, Z zoom_out, C comprehension. The Elephant re-checked every finding in the code before
resolving it.

| Finding | Resolution |
|---|---|
| The rig goes through the architect, so plans differ between arms; the plant cannot be produced; pairing undefined (D B1, Z B1, C 15) | Accepted: frozen plans, a headless driver, pairing and noise rules, a revert rule (2, 3.7) |
| The "later change" risk is never measured; G2 saturates (D B2) | Accepted: a follow-up goal and a rerun of the held-out script (G2) |
| Project rules do not reach workers (D B3, Z 7, C 6) | Partly accepted: verified (B1 spike, `process.py:1278`); narrowed to the root `AGENTS.md`, with precedence stated; frozen rules in the input deferred (5) |
| The stop is no stop: a review round, no route for a tool, the repair node, full access, message size, tasks without a brief (D B4, Z B2, C 3, C 4) | Accepted: kinds and routes per node; a declared blocker is a conflict; the full message stored; a plan revision, not a rebrief; the brief condition; the cost of one round stated; false blocks measured (3.4, G3) |
| The rebrief cannot widen a write set (Z B2, C 3) | Accepted, verified (`architect_tools.py:111-112`): a plan revision (3.4) |
| The new rejections contradict `REVIEW_BAR` (D 5, Z 5, C 5) | Accepted: no new rejections; notes counted (3.2) |
| The `preflight` evidence is selective, and P3's product claim rests on development data (D 6, C nit) | Accepted, verified (`CALIBRATION.md`): P3 rewritten; the foreman works, and tests outside the write set are its largest trigger (8 of 15). The boundary decision's "never conflicted" is corrected there too |
| The plant cannot decide `foreman.py`; it may hide the worker path (D 7, Z nit 14) | Accepted: a replay over stored briefs; the plant must pass `preflight` (3.4, 3.7) |
| G1 passes without volume falling; prose against prose; no classifier; zero baselines (D 8, Z 4, C 1, C 15) | Accepted: total lines reported; requested known from the frozen brief; zero stays zero; the change removes requirements, not adds advice (P1, G1) |
| Reviewer probes: security and cost (D 9, Z 6, C 7) | Accepted: dropped (4) |
| "Never pins wording" collides with CLI output and `DEVELOPMENT.md:104` (D 10) | Accepted: a neutral-change definition, examples (3.2) |
| Tier-2 validation undefined; a silent default; the order of slices (D 11, Z 10, C 16) | Accepted: tier 1 by code, validation where structure exists, proposal limits; tiers before the loop (3.5, 6) |
| The digest cannot be computed from the stores; P4 overstated; no final report; untrusted text (D 12, Z 11, C 10, C 11) | Accepted: a new per-plan record, a plan-end trigger, P4 corrected, a security risk. Z's "reuse `zplan_propose_commit`" is partly accepted: same card and commit flow, but a new tool, because the architect cannot write files (3.6) |
| W0.3 harness is larger: base, locks, diff, overlays, the verified tree (D 13, Z 9, C 13) | Accepted: `.slice/` git-ignored standalone modules; no removal after green (3.3) |
| Alternatives incomplete (D 14, Z 12, C 14) | Accepted: section 4 |
| Causal evidence thin; tables not comparable; role script missing (D 15, Z 4, C 2) | Accepted: P1 labelled as a hypothesis for the current contract; role outcomes by node name in W0.2 |
| Rig cost, pauses, the counter's reach, session attribution (D 16) | Accepted: limits, pauses excluded, a general counter, node names (3.7) |
| The profile gate misses the manifest contract, runtime mapping, the ceiling, the config directory; facts from `main` (D 17) | Accepted: added to the gate (3.1); the CLI facts and the template re-verified on 11.0.0 (`ZS11-CLI.md`) |
| 3.4 more than W0 needs; bad trigger (Z nit 15) | Superseded by the owner's decision (3.1); the unknown-name fallbacks it pointed to are used |
| The merge mitigation is overstated (Z 8, C 8) | Accepted: "automatic merge"; a manual merge is labelled unverified (3.5, 5) |
| Q2's architect rule has no slice (C 9) | Accepted: the method line with A0's next slice, under the A0 rig (3.2) |
| "Architect" has two meanings (D 21, C 12) | Accepted: architect and Elephant in Terms |
| Undefined terms (C 17) | Accepted: Terms |
| Nits: `REFUSED` at `:73`; four rewrites, not five; the foreman mention; the "test setup" qualifier; "outside tracked source"; `final_verify` does not run the suite | Fixed in the text, or the claim removed |

## 9. Resolution of the Goldfish findings on F0 as built (2026-11-05)

Reviewers: D design_critic, Z zoom_out, B codebase_details (`.local/goldfish/2026-11-05-f0/`). Each finding was
re-checked in the code; none was disputed. Most were found in the change itself.

| Finding | Resolution |
|---|---|
| No alternatives, risks or success measure; `lane_gate` without a design (D B1, D 2, Z B1, Z 2, B B1, B B2) | Accepted: 3.3 |
| The lane has no baseline; a red base or a flake is charged to the worker (D 5, Z 4, B 10) | Accepted: the lane runs on the base, cached by tree; `lane_red_on_base` |
| Files written during the checks are committed unchecked (D 8, Z 5, B 5) | Accepted: `tree_changed` |
| "Red on behaviour" is prose; the template's `red_contains` is the module name (D 7, Z 6, B 8) | Accepted: `red_contains` required and never the module; an import failure of the check's own module is `contract_invalid`; the template fixed |
| The pre-run red step cannot run in the main checkout (D 7, B 9) | Accepted: removed from `DEVELOPMENT.md` 2.5; the runner runs red before any worker |
| A worker can plant a module that answers for the oracle (B 4; bytecode: Z nit 6) | Accepted: `PYTHONSAFEPATH=1` for checks, an empty bytecode prefix |
| Dependent slices lose protection (D 6, Z 7, B 6) | Accepted: the earlier checks of the run rerun; `supersedes` |
| The lane detects a pin but the repair worker cannot fix it (D 4, Z 3, B 11) | Accepted: the lane failure tells the worker to reply `BLOCKED`; the root waits for T2, stated |
| "Durable tests only when asked" has no mechanism (D 9, B 7) | Accepted: `[ratchet] new_tests` |
| Direct commits are a larger source and ungated (D 3, Z 1, B 12) | Accepted, measured (2,858 test lines since 2026-11-03): the `commit-msg` hook |
| `lane_gate` opt-outs leave no trace; `run` skips the refusal; `"none"` without a reason (D 9, B 13, B nits) | Accepted: `"none: <reason>"`, recorded in `run_start`; `run_slice` fails closed |
| The documented gate order contradicts the code (B B3) | Accepted: `DEVELOPMENT.md` 2.6 lists the order the code runs |
| Test gaps: a staged `.slice` path, the lane order (D 12, Z nit 3, B 14) | Accepted: `slice_run_test.Foundation` and the lane test |
| Stale documents; the redundant `test_toolchain` rule (D 14, D 15, Z nit 7, B nits) | Accepted: fixed; the lane covers `test_toolchain` |
| Found while fixing: `preflight` looped forever on the first contract problem (it appended to the list it iterated) | Fixed |

