# STATE

Updated: 2026-11-06. Current state only; history is `git log -p STATE.md` and `docs/history/` (private archive).
After a context compaction, resume from this file and the files it names.

## Production

- v0.13.0 is the latest release (published 2026-11-06): export 8b39c87 of a9c8142 to pinkynail228/zeroplan (main,
  tag v0.13.0, GitHub release), qualified on the installed product with the real provider.
- Earlier releases: v0.12.0 (8f09913) and v0.11.0 (8e5ca98).
- The owner's Mac runs 0.10.0 until he runs `zplan update`.
- The private repository's main is not pushed; pushing it is the owner's action.

## Direction (the owner's decisions)

- **Zeroshot is the execution engine.** zplan owns the conversation, the plan, verification, merge policy and the TUI
  (`docs/designs/2026-11-04-zplan-on-zeroshot-11.md`).
- **The architect is the owner's one interface** (2026-11-04).
  - It answers first and writes the plan itself.
  - The Goldfish plan check (a reader, and a critic with the readiness rules) judges every plan before the owner's
    one yes.
  - Nothing starts without that yes.
- **macOS only** (2026-11-05). The line UI (`zplan --plain`) is to be removed; the subcommands stay (2026-11-04).
- **The target flow:** a goal, one checked plan card, one yes, merged and verified branches, one report
  (`docs/designs/2026-11-04-w0-worker-contract.md` section 0, as roadmap revision 12 amends it).
- **How we work** (`docs/DEVELOPMENT.md` section 2, Proportion):
  - small direct changes, checked by fast tests;
  - slices and Goldfish ("Astra") for risky work;
  - the expensive checks once per release: the full lane, live runs on real projects, `PRODUCT_CONTRACT.md`
    section 9 on the installed product;
  - a new mechanism only after an observed failure;
  - test weight: deferred, default keep.

## Plan (resume here)

**0.14, a lean zplan** (the owner, 2026-11-06: a deep refactor and cleanup, then Astra's evaluation). Design
`docs/designs/2026-11-06-0-14-lean-zplan.md`, revision 3: 0.14 does the work that changes no fixture and no consent
rule; 0.15 does the single planning path after a test-fixture migration.

| Slice | State |
|---|---|
| K The decline defect: the decline is stored on the revision, so the architect can never approve it; the note goes to the architect | Done |
| D Dead code: foreman, plan_tree, connections, disk; four functions (test observers wait for 0.15) | Done |
| X Linux leftovers; setup refuses all but macOS arm64 | Done |
| S Docs and state: ARCHITECTURE rewritten, two cancelled designs archived, this file | Done |
| E Astra's evaluation of the tree (`.local/goldfish/2026-11-06-0-14-tree/`) | Done: 1 Blocker and the Majors fixed, design section 9 |
| Release 0.14 | Qualified (record in the private evidence): the full lane, three live runs and a smoke on the candidate, contract section 9, the role outcomes; publishing waits for the owner's yes |

**0.15:**
- **One planning path for every entry point.** The owner's `/plan`, retry, renew and "back to plan", and steward
  proposals all go to the architect.
- **The removals.** The line UI's menu, goal drafts, the old planner's and the task gate's writers, the planner-era
  settings, and the legacy `devtools/zeroshot/`.
- **The fixture migration comes first.** Revision 2's second Goldfish pass is its list of requirements (design
  section 8).

The plan to the target flow: `docs/plans/2026-11-03-roadmap.md` (revision 12). Ideas and deferred work, each with
its trigger: `docs/plans/backlog.md`.

## Evidence (private, gitignored)

- `.local/diag/`: the live runs and the release qualifications (rel012, rel013).
- `.local/goldfish/`: every Goldfish pass.
- `.local/a0/`, `.local/w0/`, `.local/z11/`: the earlier studies.
