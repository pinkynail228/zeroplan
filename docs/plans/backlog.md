# Backlog: ideas and deferred work

The one place where an idea or a postponed piece of work is kept, so none is lost. The roadmap
(`docs/plans/2026-11-03-roadmap.md`) holds only what is planned for the next releases. An entry moves there when its
trigger fires or the owner asks for it. Plain bullets; each names its source and what brings it in.

## Decided at 0.13, deferred with triggers

- **A separate readiness node** in the plan check.
  - Trigger: a live run where `preflight` or the final check rejects an F or W class defect on a plan the critic
    accepted.
- **More critics** in the plan check.
  - Trigger: a merged change the owner rejects for its design or scope. In 0.12 the critic accepted 6 of 6.
- **A Goldfish at the end that compares the merged result with the owner's words.**
  - Trigger: a result that differs from what the owner asked. It overlaps the final check and the reader at the
    start.
- **A cuttable settle job.** Quit now waits for the base checks in a revision's first slice.
  - Trigger: a project whose checks make that wait felt.
- **The base result reaching the architect before it writes a plan.** The critic's W2 rejection and one revision
  reach the same plan.
  - Trigger: red-base chains that spend their budget.

## Seen in the 0.14 qualification, not fixed

- **A revision cannot change the chain's goal.** In m1 the owner's decline turned a CLI command into a chat command;
  the architect's `zplan_edit_plan` r2 kept r1's goal text ("CLI command"), which the plan tab then showed. The plan
  and the reader's retelling were right. `zplan_edit_plan` takes no goal; a new goal needs `zplan_plan`.
  - Goes into 0.15's single planning path (design section 8): a decline that changes the goal.

## Seen in the 0.12 qualification, not fixed

- "Files not committed: N" counts untracked caches (`__pycache__`).
- Closing reports still lack the decisions and the assumptions, although the method asks for them.
- `/new` prints its notice twice (two tests pin the chat's note; a cosmetic change).

## The product: deferred, with what brings each back

- **Graphs as fixed Zeroshot profiles** that the owner can edit in Zeroshot's editor (W0 3.1; the owner's decision of
  2026-11-05, deferred in roadmap revision 12). Version 1 changes no behaviour.
  - Trigger: the owner wants to edit a graph, or a second graph variant is needed.
- **The worker's `BLOCKED` route** with the full conflict message (4 KB, not a label and 160 characters), and the
  merge fact "paths outside the write sets" (W0 3.4, 3.2).
  - Trigger: a merge whose diff works around its brief, or a conflict the architect cannot recover from.
- **A per-plan record** (attempts, verdicts, tokens per node, wall time), **the proposal tool** that lets the architect
  propose a change to the method, `AGENTS.md` or the profile at plan end, and **tier limits** on such proposals (W0
  3.5-3.6).
  - Trigger: the owner asks for cost per plan, or for a lasting rule change proposed from a plan.
- **A separate tester role** instead of the worker's own tests (the owner's question of 2026-11-05; W0 3.7 arms 3-4:
  a probing tester whose failures are triaged first, and a code-blind tester whose tests pass an admission gate).
  - Trigger: R1 loses correctness on the behaviour checks or the follow-up goal.
- **The plan as a skeleton plus text.** The plan would hold only what code needs (milestones, order, write sets,
  checks), with each brief kept as the architect's text.
  - Trigger: a live run misses a plan, or the owner waits more than a few minutes for a first plan (today about 7
    calls in a new session, under a cap of 25).
- **Rules beyond the root `AGENTS.md` reach the workers**, delivered frozen in the run input (W0 5).
  - Trigger: a project whose rules live elsewhere.
- **Continuous observation after the first dispatch** while no screen is open.
  - Trigger: a run that needed the owner while zplan was closed.
- **One acceptance boundary for task and milestone verification.**
  - Trigger: a merge where the two disagree.
- **Provider and model per role (M4); task acceptance as executed checks (M5); a Claude Code architect.**
  - Trigger: the owner asks.
- **Active Memory of Zeroshot 11.** Off in every runtime; an on/off comparison is optional.
  - Trigger: the owner asks.
- **Linux.** Not supported or tested (owner, 2026-11-05).
  - Trigger: the owner asks.

## UI defects not yet in a release

- `/details` says "the planner keeps working" after the plan check finished.
- A stale "waits for the owner" note stays after a merge.
- The "[g] continue" view text lost its only assertion.
- The plan tab still says "Goal drafts from the architect appear here" (the protocol is dormant). This goes with the
  goal-draft removal above.

## The development harness

- **A wake can fail to reach the architect.** On 2026-11-04 the architect idled for two hours until the owner wrote.
- **`slice_run.py start` does not run `preflight`.**
- **A change to the runner cannot be gated by its own red-on-base check** when that check needs the outer context.
- **Unattended nights need three things:** `notify_cmd`, the launchd watchdog, and a way to resume the architect.
- **Known flake:** driver_qual `f_outer_exhausted` fails under heavy load. Run the driver qualification alone.
- **Known flake:** `test_checks.HardKillTests` failed once on a temp-dir cleanup race while four live runs and the full
  lane ran together (0.13 qualification); it passes alone.
- **The T2 classification and tools.** These are `devtools/defect_replay.py` and `devtools/affected.py`.
  - Trigger: the default lane passes 10 minutes, or the owner asks for a test cut.

## Housekeeping

- **Old unmerged branches:** int-s2a2, prep-05, zs-disk-guard, zs-p1b-copy-layout, zs-s1b1b-check-supervisor,
  zs-s1b1b1-check-guard, zs-v4c.
- **`.dev-runs/`** holds 923 MB of 0.9-era run data.
- **The private repository's `main` is not pushed.** Pushing it is the owner's action.
