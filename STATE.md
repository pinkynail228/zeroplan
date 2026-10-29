# STATE

Updated: 2026-10-29. Rules: devtools/zeroshot/ORCHESTRATOR.md (section STATE.md); merge history in `git log`, per-run numbers in devtools/zeroshot/CALIBRATION.md.

## Production
Version: v0.8.2 PUBLIC latest at github.com/pinkynail228/zeroplan since 2026-10-29 (tag on export 7296f91 of 657bd3b, the rc1 commit; soak NO BLOCKER; clean-HOME install and `zplan update` from 0.8.1 both give 0.8.2). Previous: v0.8.1 (9a4cedf). Branch main, pushed to the private origin only through the gated push (ORCHESTRATOR.md step 5).
Linux: dropped by the owner 2026-10-28 (no Linux gate or host; last Linux-qualified SHA a007b6e = v0.6.3); qualification is macOS only.

## Direction
Goal: zplan's architect runs the whole loop on any repository; autonomy auto (default) / supervised / manual. Public repository `zeroplan` (command `zplan` stays).
Release 0.8.0 (owner 2026-10-27): the public release ships an English-only interface; translate once, full suite once at the end; per merge only write-set test modules.
Designs (critic-reviewed, in the pause dir): 0.7.1-dirty-login.md, 0.8-english-ui.md (translate in place; legacy Russian input still accepted; T1 || T2, then T3 closes).
Input (owner 2026-10-25): no single-letter keys; every action is a / command in the chat.

## Now
0.8.2 (plans moved to the private archive 2026-10-29): tracks A and C done, v0.8.2 public; merges and gates in `git log`.
0.8.3: d1-d6, v083, d5b, d3b, d3c merged; flake MergeCardDraftShell passes alone (13/13); critic rel083b argue turn AGREE (d3c closes finding 2, no blocker; d5b accepted, O5 overrule in the plan). Whole Mac suite on 69b44f3 (2026-10-29): 2407 tests OK, 377 s (suite-083c.log in the pause dir); product code unchanged since. Waiting for the owner's go on v0.8.3-rc1.
Plan (2026-10-30): docs/PLAN_0.9.md (milestones P1-P7). Owner 2026-10-30 (overnight go): Q1-Q5 and H1-H3 as recommended (A2 test policy, B1 cut `--plain`, W4+R8 into 0.9.0, no profile commit by default, local origin identity); release v0.8.3 in stages (rc1, soak, final if no blocker); implement the plan, release, then a feedback review and the next plan (UX). The 1.5x budget goes; the critic is gpt-6-astra xhigh.
Claude lane for every run. Process (owner 2026-10-27, after "first idea, no design"): facts -> design doc -> independent critic -> owner's product decision -> briefs.
Test audit 2026-10-28 (REPORT.md in the pause dir, folder test-prune): no safe mass deletion; cost is agents running tests (54% of agent time) and growth. Its rule diffs are applied (2026-10-28): reviewers run at most one test id, repairs extend tests, budget.py in the DoD and the gate (counts untracked files).
Incident 2026-10-27: an R6 brief had an agent copy ~/.codex auth and run `zplan login`, which revoked the owner's token. Automated tests never use the owner's credentials (fake Codex, isolated HOME). Owner's go 2026-10-29: manual qualification walks may run zplan with the owner's real HOME and ~/.codex in place; never copy, print or move the auth files and never run `zplan login`/`codex login`/logout there (the copy is what revoked the token).
Test policy (owner 2026-10-28, "overtesting again"): briefs iterate on the failing modules only and run the DoD once at the end; a merge runs the DoD modules, budget.py and export_check; the whole Mac suite once per release candidate. Critic: triggers only, no daily cap; argue turns through `critic.sh NAME --argue` (read-only). A timed-out run: commit its diff on its branch, resume with `ZS_ATTEMPT=N` (rmdir NAME.lock first).
Roles (owner 2026-10-28): worker `gpt-6.1-terra`/max, every other role `gpt-6.1-sol`/high. Preset `zplan.default/3` (t4a) is what a first start proposes; /1 and /2 stay frozen. This repo's and the owner's two projects' zplan.process.json carry the same split (the two projects: edited, not committed, their trees hold the owner's work).

## Next
1. v0.8.3-rc1 export and pre-release, soak walk, final v0.8.3 if no blocker.
2. Rules: A2 test policy, budget.py removed; harness H1 (one run per milestone), H2, H3.
3. P1-P5 through Zeroshot, then P6 design + critic, P7; then the 0.9.0 candidate.
4. Brief preflight: grep tests/ for every value and every graph golden the change touches (p09a, 2026-10-30).

## Open
Harness: run.sh exits 0 when milestone_run refuses a brief; check its last line, not the code. Start runs one after the other (same-second starts race). Before a brief, grep tests/ for every value the change touches (preflight conflicts s3a, a10c).
Later: critic 5 s polling (audit finding 10); API-key auth; guarded `--approve-for-me`; Russian/Chinese UI back via the catalog.
Harness: `run.sh --validate-only` leaves a worktree at HEAD (commit the brief first or remove it); two run.sh launches at the same second can fail at start (stagger).
devtools/ux_walkthrough.py is stale since the project picker (expects the profile choice first); not a 0.8.0 gate.
TUI load flakes (pass alone; confirm at the release gate): test_checks HardKill a / Lease a, test_tui_chat c4_c6/c6b, test_tui_polish ResultModal a3, TerminalTests real-pty (also under -j 2), QuitSafety c1, MergeCardDraftShell, test_tui_question_card a1_a2, test_tui_live la1, test_tui_milestones a1b, test_new_session c1.
