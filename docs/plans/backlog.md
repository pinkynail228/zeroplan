# Backlog: ideas and deferred work

The one place where an idea or a postponed piece of work is kept, so none is lost. The roadmap
(`docs/plans/2026-11-03-roadmap.md`) holds only what is planned for the next releases. An entry moves there when its
trigger fires or the owner asks for it. Plain bullets; each names its source and what brings it in.

## Planned for 0.13

- **The plan check as the full Goldfish protocol.** Add an implementation readiness step before the owner's yes, so
  that every brief is checked as the worker will carry it out. `preflight` stays at the start of each run.
  - Source: the Elephant-Goldfish Model (roadmap Terms); live run 1 lost an attempt to a brief line that no worker
    could satisfy.
  - Decided from the role outcomes counted at 0.12.
- **More than one antagonistic critic in the plan check.** The model uses several skeptics; zplan uses one critic,
  once. Decided together with the readiness step, from the same role outcomes.
- **A Goldfish at the end that compares the merged result with the owner's own words.** Did we deliver what he
  asked? Source: the owner's question about where Goldfish pay off (2026-11-05). Same decision.

- **The role outcomes of the 0.12 qualification** (14 Zeroshot runs): the plan critic accepted 6 of 6, `preflight`
  passed 8 of 8, the reviews each rejected 1 of 8 (a red base the worker then fixed), and the final check accepted 7 of
  7. This is the input to the 0.13 decision.
- **The architect plans before the base checks run.** On a red base its plan did not plan the fix; the repair loop
  fixed it. Candidate: the base result reaches the architect before it writes the plan, or an automatic revision.

## Seen in the 0.12 qualification, not fixed

- "Files not committed: N" counts untracked caches (`__pycache__`).
- Closing reports still lack the decisions and the assumptions, although the method asks for them.
- `/new` prints its notice twice.

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
- **The owner's own `p`, `r`, `/plan` and steward proposals still use the old planner.** Retire it (M6), together with
  the line UI (`zplan --plain`) and the dormant goal-draft protocol (A0 design 3.7).
  - Trigger: a change touches those modules.
- **Replay `foreman.py`** over the stored briefs, then wire it into the plan check or remove it (W0 3.4).
  - Trigger: the 0.13 readiness work.
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
- **The T2 classification and tools.** These are `devtools/defect_replay.py` and `devtools/affected.py`.
  - Trigger: the default lane passes 10 minutes, or the owner asks for a test cut.

## Housekeeping

- **Old unmerged branches:** int-s2a2, prep-05, zs-disk-guard, zs-p1b-copy-layout, zs-s1b1b-check-supervisor,
  zs-s1b1b1-check-guard, zs-v4c.
- **`.dev-runs/`** holds 923 MB of 0.9-era run data.
- **The private repository's `main` is not pushed.** Pushing it is the owner's action.
