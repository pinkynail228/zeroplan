# STATE

Updated: 2026-11-05 (evening). Snapshot only: replace lines in place; history is `git log -p STATE.md` and
`docs/history/` (private archive). After a context compaction, resume from this file and the files it names.

## Production

v0.11.0 published 2026-11-05 on the owner's go: export 8e5ca98 of a3af5a6 to pinkynail228/zeroplan (main and tag v0.11.0, GitHub release). Qualified: full lane 2710 OK on 3d1fa22 (a3af5a6 changes wording only: docs and devtools tests green); a fresh install from the export (install.sh, setup with Zeroshot 11.0.0, doctor); two real-provider runs of the target flow on a FigmaPot copy. The owner's Mac still runs 0.10.0 until he runs `zplan update`. The private repository's main is not pushed.

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

Roadmap: `docs/plans/2026-11-03-roadmap.md` (revision 12, the plan review with the owner on 2026-11-05): R1-R4 and release 0.12.
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

The target flow: `docs/designs/2026-11-04-w0-worker-contract.md` section 0, as roadmap revision 12 amends it. The
plan: `docs/plans/2026-11-03-roadmap.md` revision 12 (the plan review with the owner, 2026-11-05: rig-gated work cancelled,
P2/P6-P9/T2 deferred or cancelled with their triggers). How we work: `docs/DEVELOPMENT.md` section 2, Proportion.

| Step | State |
|---|---|
| 0.11.0 | Published 2026-11-05 (Production above). Live runs on a FigmaPot copy: private evidence under `.local/diag/` |
| Roadmap rev 12 | Written 2026-11-05; Goldfish pass resolved in the roadmap (R2 keeps the contract: the milestone introducing a project's first check waits for the owner's merge yes; R1 measured by unrequested test lines with a follow-up goal and a revert rule; R4 a code-made facts entry at plan end) |
| R1 Tests in proportion | Built 97bdd77; measured on the two FigmaPot goals (private `.local/diag/r1/`): correctness held (every held-out check, the follow-up included; every goal at attempt 1), test lines not lower (358 vs 324): the architect names a risk and asks for tests in every brief. Waiting for the owner's call on volume (default: keep) |
| R2 A red base, a first check (F14) | Built: R2a 2a2144d + 2876d12 (after a review of the change as built), R2b cb665ee; default lane green |
| R3 Small fixes, R4 The report | Done: R3 11b497f, b8a36d9 (pnpm store cleanup, profile wording, dim 'awaiting merge', ARCHITECTURE); R4 dc5cdaf (facts of each merged milestone in the plan view and the status) |
| Release 0.12 | Candidate 574bfb8 qualified (private evidence under `.local/diag/`): full lane 2717/2718 on 9f05934, the red test fixed in 574bfb8; installed from the export in a clean HOME; live runs L1 (two milestones, reopen, /new, stop and try again), L2 (red base fixed, merge card, then automatic), L3 (no checks, settings card, then automatic); all eight items of contract section 9. Waiting for the owner's go to publish |
| 0.13 | The plan check as the full Goldfish protocol (readiness before the yes), from the role outcomes of 0.12 (roadmap; backlog) |

Evidence folders (private): `.local/diag/`, `.local/z11/`, `.local/w0/`, `.local/a0/`, `.local/goldfish/`.

## Open

Known defects, gaps, ideas and housekeeping: `docs/plans/backlog.md` (one list; nothing kept only here).
