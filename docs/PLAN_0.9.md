# Plan: 0.8.3 close and 0.9 from evidence

Status 2026-10-30. Replaces RELEASE_0.9_PLAN.md (private archive). Evidence: ~/zs-pause/design/replan-ledger.md
(claims, traceability, hotspots, pre-mortem; criteria fixed first in replan-preregistration.md); critic replan
(gpt-6-astra xhigh): turn 1 AGREE WITH CHANGES on ledger and plan, turn 2 test policy and `--plain` options
(~/zs-pause/critic/replan*.out). Owner decisions O1-O5 and "F: all eight" stand.

## Owner decisions (2026-10-30: the first option of each, and H1-H3 yes)

| # | Question | Options |
|---|---|---|
| Q1 | Test policy (below) | A2: final_verify is the one full DoD run inside a run / A1: the worker also runs the DoD once |
| Q2 | Interactive line UI (`--plain`, non-TTY menus; no architect chat, letter keys) | B1: cut it, keep subcommands and the `App` core / B2: keep as a limited fallback |
| Q3 | Pull into 0.9.0: the plan's milestones visible before an auto-approval (W4) and a narrow pytest detection fix (R8) | yes / keep them in M3, M4 |
| Q4 | Profile persistence (every walk: a "zplan profile" commit on the user's main before any work) | frozen proposal, no project commit by default; save the profile as an explicit action / commit on accept, as today |
| Q5 | Project without a GitHub origin (the card writes `github.com/local/...` into the user's repo) | a local identity that never touches the user's remote / require a real origin |

## Phase 0: close 0.8.3 (unchanged)
Candidate 69b44f3 suite green (2407 tests). Owner's go: `v0.8.3-rc1`; soak; `v0.8.3`.

## Test policy (Q1; replaces the 1.5x line budget)
Facts: since the 10-28 rules net tests grew 2.3x net product while budget.py passed every merge; agents spend 54%
of run time on tests (reviewers 67%); 60% of new tests pin text; the shipped acceptance prompt says "Gather fresh
evidence yourself (run the checks)" (milestone.py:503) against the local rule that reviewers run no tests.
1. A test only for new uncovered behaviour or a reproduced defect: extend an existing test first; one scenario may
   cover several criteria. Text and layout edits get no new test; exact strings are asserted only when they are a
   contract (a command, a protocol field, a required warning).
2. Review asks what real error an added assert catches that existing checks miss; test count never blocks.
3. Existing tests stay; a slice that touches a surface replaces its wording pins with the behaviour (d3: the action
   chosen after an arrow, not the button labels in 13 files). No mass pruning (audit 2026-10-28).
4. Runs: worker runs the tests of its change; acceptance and code review run none (one test id for a code-review
   hypothesis); final_verify runs the required checks once (A2: the only full DoD run); the merge gate runs the
   chosen checks on the integrated candidate; the whole Mac suite once per release candidate. A rerun needs a
   changed input or a run without a result.
5. Flakes: one isolated rerun for diagnosis; known load flakes run serially in the candidate suite, their diagnosis
   kept once; an unexplained failure is a defect.
Delete: devtools/budget.py and its DoD/gate uses; every live 1.5x rule (ORCHESTRATOR, preamble, architect_method.md);
preamble's "one smoke test per criterion", "criterion with no test rejects", the per-visit edit/test duty and the SVG
per screen; the blanket `tests.test_toolchain` in every DoD. Product (through a run): VERIFY_RULE asks for coverage
of a gap, not a test per feature; the acceptance prompt drops "run the checks"; no unconditional rerun of an
`incomplete` check (O5 stays).

## 0.9.0 milestones and tasks
Sizing (measured since 2026-10-16: 232 merges, median 61 added product lines, p90 292; 12 above 500, all splits or
translations): workers do not build oversized features here; the cost is one brief, run, gate and merge per small
slice. So a task stays one behaviour with one check that fails on today's code, explicit non-goals and at most
~300 added product lines (above: split at a stable contract); a milestone groups the tasks of one write-set cluster
and lands as one run, one gate and one merge (harness change H1, owner's go). Tasks inside a milestone run in order,
so tasks sharing a file need no extra serialization. IDs P1-P7 avoid the mechanism names M1-M4.

| Milestone | Tasks (one behaviour each) | Write-set cluster | Needs |
|---|---|---|---|
| P1 Lean tests and dead code | T1 delete journal.py, its test and catalog entry; correct the 5 false docstrings. T2 the v1 golden test checks stored documents, not a rebuilt hash. T3 shipped prompts: acceptance runs no checks, VERIFY_RULE asks for coverage of a gap, no unconditional rerun of `incomplete`; the method loses the 1.5x line and its merge-critic line matches the gate | journal, catalog, milestone, engine prompts, architect_method, their tests | Q1 for T3; the rule files and budget.py removal are mine, same day |
| P2 Merge you can trust | T4 the level matrix (O4, F6) and consistent check messages. T5 critic triggers (F1) | autonomy, delivery, runs, merge_critic, tui/controller | — |
| P3 First start without hands | T6 work from the proposed profile without the modal (F2) and max_runs from it (F5). T8 narrow pytest detection (R8). T9 max_runs offered 1-3 (F7) | process, tui/modals, delivery | Q3, Q4 |
| P4 Fewer confirmations, visible plan | T10 a typed command is consent (F3). T11 the plan card lists the milestones before an auto-approval (W4). T12 any printable override reason (F8) | tui/app, screens, card_kinds, planning, authority, task_gate | Q3 |
| P5 Stale only when it matters | T13 approve with "based on <sha>, N commits since"; re-plan only when those commits touch the plan's write-sets (F4) | authority, planning | — |
| P6 Consent card (mechanism M1, core) | design section -> critic -> tasks: the stored pending action, re-checked on consent, a repeat is a no-op; the architect never relays a command | controller, card_kinds, card_host, architect, strings | design first |
| P7 UI follows events (mechanism M2, narrowed) | T re-observation with backoff; T a true end card and S5's history line after the architect's merge | controller, app, feed, delivery | after P6 |

Moved to the UX plan (2026-10-30, preflight p093): profile persistence (Q4) needs a rule for a snapshot-accepted profile vs a file the owner writes later (`zplan profile init`, /setup edits); it goes with the first start in the chat. Outside 0.9.0's path, any free slot: P8 `--plain` cut (Q2: B1; T routing and a clear error, T delete menu-only code,
tests and docs; cli.py overlaps P2's merge wait, so after P2). Q5 local origin: its own design.
Order: P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P7, one after another (shared prompts, catalog and hotspot files).
0.9.0 scope (2026-10-30): P1-P4 and P6 (P3 without T7, P4 without the end screen's merge confirm). P7 joins the
UX plan's "UI acts on events"; P5 (F4) waits for its own design: it moves the plan's source identity, a persisted
contract, with no user report behind it.

## Harness (owner's go 2026-10-30)
| # | Change | Why |
|---|---|---|
| H1 | One run per milestone: run.sh takes several task files and builds one milestone with those tasks (the product's own driver already loops tasks and runs final_verify once); one worktree, gate and merge per milestone | removes the per-slice brief/gate/merge/STATE overhead of 232 merges in 2 weeks; dogfoods the multi-task path users get |
| H2 | CALIBRATION keeps date, task, result and the lesson; numbers come from metrics.py and the run store | the objective columns duplicate the run store and are often "not recorded" |
| H3 | Tester feedback, walk and soak records move from the pause dir into the private archive (folder records), excluded from export | the plan's evidence lives outside git today |

## Later and not doing
Later: M1 conflict recovery, M2 commit queue, transient retry and retry after a project change (no incident);
M3 facts and rule order; M4 onboarding in chat; chat order W8, commit titles W14, N2; a narrow upstream SDK use only
if it deletes code (a full swap is disproved: SDK rejects `source: null`, no usage or recovery data).
Not doing: a total test/product gate; mass test pruning; removing presets /1, /2 or stored v1 records; splitting
app.py without measured collisions.
