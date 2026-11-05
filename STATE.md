# STATE

Updated: 2026-11-05 (evening). Snapshot only: replace lines in place; history is `git log -p STATE.md` and
`docs/history/` (private archive). After a context compaction, resume from this file and the files it names.

## Production

v0.9.0 (Codex + Zeroshot) remains the latest public release. Nothing was pushed, tagged or released since.

## Direction

Decided 2026-11-03 (`docs/designs/2026-11-03-egm-pivot.md`):
- Zeroshot stays the execution engine.
- Planning moves to the Elephant-Goldfish Model: the architect writes the plan, stateless Goldfish review it, and
  there is no separate planner.
- Delegation (`docs/PRODUCT_CONTRACT.md` section 2): the owner approves the plan and reads the final report; the
  architect decides in between.

Decided by the owner on 2026-11-04:
- The architect is the owner's one interface: advisor, helper, planner and manager, with every function. It answers
  first; it decides itself when a plan helps and drafts it without a slash command or a "let's plan" from the owner.
  A plan is a proposal until the owner says yes once (one key or a word); nothing starts without that yes. Code
  guards the harms, not the initiative: a plan never replaces the answer, format refusals never reach the owner, the
  state is visible. The conversation is a plain read-only Codex session that reads the working tree; zplan adds the
  delegation tools and states. The first revision of every plan chain waits for the owner's yes at every level;
  he accepted that a secret in a file without a credential name reaches the model provider, as with any Codex use.
- The plan format is redesigned from the owner's jobs to be done and measured on the evaluation rig.
- Tests (T2): the deep tests (merge, durability, concurrency, scrubbing, process safety) stay; the shallow ones
  (screens, wording, structure, duplicates) are rebuilt as journeys and contract tests, batch by batch, each proved
  by a behaviour ledger, held-out defects and a cold review. No size ratio is ever a goal.
- zplan moves to Zeroshot 11 (owner, 2026-11-04 evening: "we are behind"); W0 is designed on 11's capabilities, not
  on the pinned 10.16.0.
- The boundary (`docs/designs/2026-11-04-zplan-on-zeroshot-11.md`): zplan owns the conversation and history, the
  moment of delegation (a Goldfish-checked plan and the owner's one yes), deterministic verification and the merge
  policy, and the TUI; Zeroshot owns execution, and no loop moves out of it. Instructions change before structure;
  a graph role is cut only on evidence from a harder goal. The work stays in this repository: no rewrite, removal
  in place.
- No Linux testing (owner, 2026-11-05): macOS only, as the README says.
- The line UI (`zplan --plain`) is removed; zplan is the full-screen TUI only. Non-interactive subcommands (status,
  doctor, setup, login, exec) stay.

Roadmap: `docs/plans/2026-11-03-roadmap.md` (revision 11): the plan P1-P10 from `main` to the target flow.
Development (`docs/DEVELOPMENT.md`): an Opus architect, Sonnet workers under `devtools/slice_run.py`, Opus
reviewers, Goldfish ("Astra" in the owner's words) via `devtools/goldfish.sh`.

## Now

- `main` (checked out) = a0-next: the 0.10.0 candidate c0aaee3, F17, A0 S1a-S1c and S2a, the Z11/W0/T2 records; full
  lane on ecf3334 (later commits docs only): 2704 tests OK. The Mac still runs `zplan 0.10.0` from c0aaee3 (0.8.1 is
  the rollback target). The tag is the owner's decision.
- F17, fixed: the architect's read tools see the last commit only, and now say so (rules, tool text, a `note` naming
  uncommitted paths, `read.uncommitted` for an untracked file); the first message of a session shows
  "Files not committed: N. zplan and its workers see only committed files."
- A0 steps 1-5 (study before any behaviour change), evidence in `.local/a0/` (private):
  - `REPORT.md`: the coded owner messages, every zplan_plan decision traced, the capability decision, prior art;
  - `labels.json`, `cc_messages.jsonl`, `cc_sample150.jsonl`: the data and its hand coding;
  - `eval/base-main/`: the rig's baseline on main 7feb4a4 (summary.md; `arch_eval.py score` re-judges it);
  - `T2-R1.md`: the first research for the test rebuild.
- Findings so far: 74% of the owner's session openers ask to explore, 5% of later messages are his own goals and 21%
  accept the agent's proposal; 22 of the 24 messages in zplan's own history were scripted by the development agent;
  every first zplan_plan call failed its format (10 of 10; the model sees `plan: {[key: string]: unknown}`); the
  PenPot message gets a plan on a fully committed project too (F18 does not depend on F17).
- Baseline (24 cases): premature plan 6 of 22 answer turns (all in "explore + a wish"), missed plan 0 of 8, first
  useful answer in 1 turn for 12 of 18 explore cases, 101 format refusals over 14 plan-writing turns.
- Evaluation rig: `devtools/arch_eval/` (scenarios, the `shelf` fixture, the driver). It gates every change to the
  architect's behaviour on both failure modes at once: premature plan and missed plan, plus turns to the first
  useful answer and format refusals.

## Plan (resume here)

The target flow: `docs/designs/2026-11-04-w0-worker-contract.md` section 0. The plan and its distance table: roadmap
revision 11. Technical decisions are the Elephant's (`docs/DEVELOPMENT.md` section 1, the 2026-11-05 lesson).

| Step | State |
|---|---|
| F0 Development foundation (Elephant) | Done: Goldfish on the change as built (`.local/goldfish/2026-11-05-f0/`), every finding resolved in W0 design section 9 (the oracle cannot be faked or land; red on behaviour enforced; new tests declared in `new_tests`; direct commits ratcheted by the `commit-msg` hook; the lane with a baseline per tree; earlier slices' checks rerun; the tree unchanged by checks). devtools tests 78 OK |
| P1 Zeroshot 11 (Elephant) | 9e46cd6 on `main`; full lane 2706 OK (the lane read HEAD cc71466, STATE only; docs edited during it, `test_docs`+`test_toolchain` re-run green). No Linux testing (owner, 2026-11-05). Left: one real-provider milestone on the installed product |
| P2 Profiles v1 | P2a on `main` 19894c7: one milestone graph for every milestone (task and review loops carry the ceilings of the largest milestone and read `taskLoopBound`/`reviewLoopBound` from the input); full lane 2709 OK; driver_qual a, b, d, f on Zeroshot 11.0.0 pass (the driver cannot run inside the gate seatbelt, so the Elephant runs it at integration). Next: P2b, the three profiles installed into zplan's Zeroshot config, the profile gate, the exact content frozen at approval |
| P3 Plan format, P4 The yes | On `main`: P3a, P4a, P3b, P4b, P4c (settings as the owner's consent card, `Profile.preview`) and P4c2 (the rules and the tool say so); full lanes green (2709 on 5b5e27f). The contract review caught three holes of P4c before any worker; P4c and P4c2 then passed in one round each. P4d (goal drafts) moves to P10 with T2.1: the prompt no longer asks for goal drafts, so the protocol is dormant, and test_tui_draft_card is in T2.1's batch. P3c on main 19316e1. The A0 rig on 19316e1 (the A0 report (private evidence), section 9): answers 18/18, unwanted plans 0/14 (was 1/14), format refusals 2.8 per plan turn (was 6.3), but missed plans 9/16: the cap of 3 cut converging plans off one fix short; the two wrong approvals followed a missed plan. P3d (88d6f63): cap 6, a plan sent as JSON text is read. P3d's rig (17 of 18 plan cases, stopped when the owner closed the Mac, `.local/a0/eval/p3d/`): missed plans 8/15, 96 format refusals in 19 plan turns (5.1): a patch again, not a fix. Decided (the reflection with the owner, 2026-11-05): no more format patches. Design r2 `docs/designs/2026-11-05-plan-as-text.md` after its Goldfish pass (every finding resolved, section 7; the second call is lean JSON in 30 of 35, so one normalizer takes text and lean JSON; fidelity over shape; criteria become the task's checks). Re-planned with the owner (2026-11-05 evening): PT stopped (a prose grammar fitted to one fixture was whack-a-mole); no per-change rig or end-to-end runs: aim at a release, cheap tests between changes, the expensive runs once at the end. The format cap became a runaway bound (7ed30b2, 25). Diagnostic run 1 on a FigmaPot copy (private evidence under `.local/diag/`): goal to merged branch in 30 min, one yes, no owner intervention, on Zeroshot 11.0.0 with the real provider (closes P1's real-provider milestone). Found: the final check demanded a clean tree from a DoD sentence the architect wrote at planning (attempt 1 lost); scope_verify rejects every repair against the select-time snapshot; test weight 4.4 to 1; UI wording. The plan format was not the bottleneck (6 hidden refusals, 3 minutes). Release 0.11 fixes on main (b11051d, afab5ff): the final and scope checks never require a commit or judge .zplan/; dod is the finished change; event turns in the owner's language; transcript scrubbed per line. Release acceptance: full lane 2709/2710 on b11051d (the red K5 text check fixed in afab5ff, module green); run 2 (two milestones, M2 after M1) merged both at attempt 1 in 22 min with one yes and 0 format refusals. Left open: test weight (about 5 to 1; one sentence did nothing), worktrees left when a .pnpm-store/ is inside, end lines out of order, the Drafts pointer. Next: the owner's version and tag decision. r1 was: the architect writes the plan as a labelled text (32 of 35 first calls already send text; the corpus `.local/a0/plan-corpus/`), `plan_text.parse` derives the stored plan (one task, slice and requirement per milestone; the stored format unchanged); a prototype turns 30 of 32 corpus texts into a valid plan. Then slices PT1 (parser) and PT2 (the tools and rules, A0 rig gate); then a live run of the target flow on a copy of PenPot (closes P1's real-provider milestone and A0's acceptance) before P2b, P5, P6-P7 |
| P5-P10 | In order (roadmap) |

Evidence folders: `.local/z11/`, `.local/w0/`, `.local/a0/`, `.local/goldfish/`.

## Open

- UI defects:
  - `/details` says "the planner keeps working" after the plan check finished;
  - end lines arrive out of order ("merged" before "awaiting merge");
  - a stale "waits for the owner" note stays after a merge;
  - the "[g] continue" view text lost its only assertion with D4a.
- Product gaps:
  - the owner's own `p`, `r`, `/plan` and steward proposals still use the planner (R1b);
  - no continuous no-screen observation after the initial dispatch;
  - task and milestone verification are not one acceptance boundary;
  - `docs/ARCHITECTURE.md` describes the old direction.
- Flake (diagnosed, kept): driver_qual `f_outer_exhausted` failed once at P2a's integration under heavy load (the full lane and the A0 rig at once): a 50 s provider call made the engine re-execute `steward_decide` and `select`, which used up the scripted entries ("unexpected call #17"); alone it passed (156 s). Run the driver qualification without other load.
- Harness gaps:
  - a wake can fail to reach the architect: on 2026-11-04 it idled 12:07-14:24, until the owner wrote;
  - `start` does not run `preflight` (its 10-minute hang on 2026-11-04 was a loop on the first contract problem, fixed in F0);
  - a runner change cannot be gated by its own red-on-base when the check needs the outer context;
  - unattended nights need `notify_cmd`, the launchd watchdog, and an architect resume path for this harness.
- Old branches kept unmerged: int-s2a2, prep-05, zs-disk-guard, zs-p1b-copy-layout, zs-s1b1b-check-supervisor,
  zs-s1b1b1-check-guard, zs-v4c (abandoned UX v4c WIP). `.dev-runs/` holds 0.9-era run data (923 MB).
