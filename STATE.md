# STATE

Updated: 2026-11-06. Current state only; history is `git log -p STATE.md` and `docs/history/` (private archive).
After a context compaction, resume from this file and the files it names.

## Production

- v0.14.0 is the latest release (published 2026-11-07 on the owner's yes): export ecf15d1 of 37847ee to
  pinkynail228/zeroplan (main, tag v0.14.0, GitHub release), qualified on the installed product with the real provider.
- Earlier releases: v0.13.0 (8b39c87), v0.12.0 (8f09913), v0.11.0 (8e5ca98).
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

**0.14, a lean zplan:** published (design `docs/designs/2026-11-06-0-14-lean-zplan.md`): the decline is stored and
goes to the architect; dead code, Linux leftovers and stale docs removed; Astra's evaluation resolved.

**0.15, one planning path, the line UI gone.** Design `docs/designs/2026-11-06-0-15-one-planning-path.md`, revision 3
(its section 8 overrides the sections above it).

| Step | State |
|---|---|
| F1-F3 Fixtures on Goldfish revisions; the plan check's documents pinned | Done 59d11cd, 2a4693d, 6c82ced |
| L The line UI goes; zplan is full-screen only | Done 5e575b1, 627e06b, 6f07e50 |
| P1-P4 Every entry point goes to the architect, binding no yes; the structural guard | Done 4ae0d32 |
| Docs (ARCHITECTURE, README, USER_FLOW, REFERENCE, UPGRADE) | Done |
| Astra as built (section 9); release 0.15 qualified (record in the private evidence) | Done e5cbe87; publishing waits for the owner's yes |

After 0.15, one design for the removals: the old planner's and the task gate's writers, the planner-era settings,
the goal-draft UI, `devtools/zeroshot/`, the observer functions (0.15 design section 6).

The plan to the target flow: `docs/plans/2026-11-03-roadmap.md` (revision 12). Ideas and deferred work, each with
its trigger: `docs/plans/backlog.md`.

## Evidence (private, gitignored)

- `.local/diag/`: the live runs and the release qualifications (rel012, rel013).
- `.local/goldfish/`: every Goldfish pass.
- `.local/a0/`, `.local/w0/`, `.local/z11/`: the earlier studies.
