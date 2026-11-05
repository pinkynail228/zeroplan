# Decision: zplan on Zeroshot 11, what it owns and what it hands over

Status: revision 2, accepted by the owner on 2026-11-04 (the boundary; a harder goal measured before any role is
cut; the work stays in this repository, no rewrite). After one Goldfish pass on revision 1 (`.local/goldfish/2026-11-04-zplan-thin/`:
zoom_out, design_critic; section 7). It fixes the product boundary the W0, A0 and T2 designs follow; it is not an
engine redesign. Evidence (private): `.local/w0/NOTES.md` (the role outcomes and their method), `.local/w0/ZS-R1.md`,
`.local/a0/REPORT.md`.

## 1. Problem and goal

- What failed or cost most on 2026-11-04 was not execution: the conversation (PenPot), the plan format (7.2 refusals
  per plan turn), and test volume (zplan's workers wrote 2.6 test lines per product line on the probe's scratch
  projects; zplan's own suite holds 68k test lines for 36k product lines). A0 and W0 own those.
- zplan pins Zeroshot 10.16.0; 11.0.0 (2026-11-02; `git log v10.16.0..v11.0.0`: 42 commits from 2026-10-21) adds
  per-node harness configuration, pi as a core harness, active memory, the planning skill and a profile editor.
- Goal: one written boundary, so that no track rebuilds what Zeroshot gives and no track moves what only zplan can own.

## 2. The boundary

zplan owns what protects the owner's intent and code:
1. one conversation with an architect that knows the project and keeps the history (A0);
2. the explicit moment of delegation: a plan the owner has seen, checked by Goldfish (the Elephant-Goldfish Model:
   the architect writes, a fresh reader retells it against the owner's words, a critic looks for holes; one pass,
   findings answered with evidence), and the owner's one yes;
3. deterministic verification and the merge policy: a model never turns red into green; only the verified
   candidate merges;
4. the TUI that shows the real graph, the history and what waits for the owner.

Zeroshot owns running the work: the graph, its sessions, repair loops, recovery and its observation. zplan never
moves a loop out of Zeroshot into its own code.

## 3. What follows now

- **Move to Zeroshot 11 as is** (Z11): zplan's milestone graph, runtime and input validate on 11.0.0 unchanged; the
  candidate qualification passed contracts and the installed tests on macOS; the status reader learns 11's optional
  `metadata` fields; the bump follows docs/UPGRADE.md, including the Linux qualification and a real-provider smoke.
- **Change instructions before structure** (W0): the test and evidence rules of the worker, acceptance and code
  review nodes, measured on probe goals against today's 2.6 test lines per product line.
- **Cut or merge graph roles only on evidence from a harder goal.** The measurement so far covers about one task
  per milestone on toy features: preflight never conflicted there (0 of 36), though on zplan's own development it
  stopped 15 attempts, 8 of them for a test outside the write set (`devtools/zeroshot/CALIBRATION.md`; corrected by the
  W0 design's Goldfish pass); code review never rejected (0 of 33), the
  three select roles only run zplan's validator, and the end-of-milestone check changed 6 of 35 outcomes (4 rejected
  after acceptance had passed, 2 incomplete). `steward_apply` judges (it may split, reword or drop tasks), so it is
  not bookkeeping. One harder, multi-task goal is measured before any role goes.
- **Graphs as Zeroshot profiles** (the owner's point: Zeroshot's profile editor builds graphs): evaluated in the W0
  design, with what zplan must check of a profile before it runs one (its input and output contract).

## 4. Alternatives

| Alternative | Verdict |
|---|---|
| Revision 1: task selection and bookkeeping move into zplan code between task runs | Rejected: it adds a durable orchestrator zplan does not have (one run per attempt in the store, crash windows between runs, a worktree carried across runs, no observation with the screen closed) and drops the end-of-milestone check for one-task milestones, the one check that changed outcomes |
| Bump only, instructions first, structure by evidence (section 3) | Chosen |
| One task per milestone (milestones chain without the owner already) | Kept for W0: removes selection with no new loop, at the cost of one merge per task |
| A frozen `map` over the tasks in one run | Kept for W0: needs the plan frozen; amendments become revisions, which already works |
| Wait for an upstream command node (`origin/codex/script-node`) | Not a plan; noted |

## 5. Risks

- **Toy-task evidence.** Mitigated by measuring a harder goal before any role is cut.
- **Mixed graph shapes.** Old run records keep their executable and graph; a later shape change keeps the TUI and
  recovery able to read both.
- **Upgrade with unfinished work.** The qualification used `--keep-old-app`: the old toolchain stays installed for
  records that name it.
- **Profiles edited by hand.** A profile that breaks zplan's contract is refused before the run, with the reason.

## 6. Questions for the owner

1. The boundary in section 2: yes or no.
2. One harder, multi-task goal measured on the current graph before cutting roles: yes or no.

## 7. Resolution of the Goldfish findings (revision 1)

| Finding | Resolution |
|---|---|
| No alternatives; a bare yes/no (Z1, D B1) | Accepted: section 4 |
| "Thin" hides a new orchestrator; no risks (Z2, D B5, D B2) | Accepted: the loop stays in Zeroshot; section 5 |
| The end-of-milestone check would go for one-task milestones (Z3, D B3, D M1) | Accepted: it stays; checks alone do not cover what it covers |
| Two "bookkeeping" roles judge (Z7, D B4) | Accepted: `steward_apply` judges |
| Preflight cannot fold into `foreman.py`, which is not wired in (Z6, D B6) | Accepted: no fold; `foreman.py` being unwired is a separate finding for W0 |
| The proposal does not address the stated problem; no metric (Z4, D M5) | Accepted: structure changes only on evidence; A0 and W0 own the stated failures |
| Same evidence, opposite decisions (Z5, D M3) | Accepted: no role is cut in this decision |
| The measurement is not reproducible (Z10, D M4) | Partly: the counts and method are in `.local/w0/NOTES.md`; the script becomes a devtools script with the W0 study |
| "In the owner's projects" (Z9, D M7) | Accepted: the ratio is from the probe's scratch projects |
| Zeroshot history unsupported (Z11, D M6) | Disputed with evidence: `git log v10.16.0..v11.0.0` in a clone of the tag gives 42 commits from 2026-10-21 to 2026-11-02; the reviewers had no git |
| Test claims overstated (Z12, D M8) | Accepted: removed |
| Q3 rests on a wrong premise: the architect is not a graph node (Z13, D M9) | Accepted: removed; the architect's harness stays roadmap M4 |
| No migration or rollback plan (D M10) | Accepted: section 5 and docs/UPGRADE.md |
