foreman-pilot — devtools process pilot on S5a disk-guard after the v0.4.0 tag (owner 2026-10-19: a DeepSeek foreman slices the task before the workers, a clerk fills the cards after the reviewers). critic foreman: GO WITH CHANGES (~/zs-pause/critic/foreman.out, session 01a15375-895d-7402-aae0-bfba5d11deec). No change to the native software-change template.

Foreman (DeepSeek proposes, the sol critic checks):
- Input: the brief with its SHA, base SHA, contracts, test environment, the nearest historical cards (CALIBRATION.md rows).
- Output per slice: id, original_requirements, acceptance_domain, oracle, entry_points, read_set, write_set, interface_contracts, dependencies, expected_product/test_lines, comparator_runs.
- Checklist the critic applies: the task checklist of ORCHESTRATOR.md step 1, plus: every original R/A assigned to a slice; each contract closed (valid/malformed/unknown, bounds, fallback); one owner per invariant.
- Approved slices run through `devtools/zeroshot/run.sh` as ordinary tasks.

Clerk (after each run; it reads the terminal state from the run store, since the CLI exit may be a detach):
- A script computes: run id and hashes, rounds, verdicts versus crashes, usage per role, diff split product/test, receipts.
- The model writes only: summary, proposed rejection coding (Q open input space, A ambiguity, D defect, T evidence gap, S reviewer scope creep, I environment), risks, merge-summary draft.
- Card order: identity, scope map, rounds/findings, usage/time, diff, evidence, status, remaining work. Cleanup: only registered temporary files, only after the terminal state; a product edit goes back to review; an accepted run is never qualified or merged automatically.

Pre-registered success criteria (freeze the brief and checklist before the run):
- Each slice accepted in ≤3 completed review rounds and ≤71.75M input+output tokens.
- Total ≤239.38M tokens including foreman, clerk and gates (the measured minimum of the first stopped disk-guard run; both disk-guard runs used ≥397.39M). Cached tokens are not added to input again.
- disk-guard R-1..R-5, A-1..A-6 and the accepted S-1..S-5 preserved; the overall gate green.
- Incomplete usage data or lost evidence → inconclusive, not a pass.
- Comparators: drafts-data, drafts-goal, pub-scrub, dedupe, scroll, la1, run-failure-cause repair: 2-3 rounds, median 51.45M, maximum 71.75M (run ids in foreman.out).
