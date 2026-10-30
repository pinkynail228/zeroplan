# STATE

Updated: 2026-10-29. Rules: devtools/zeroshot/ORCHESTRATOR.md (section STATE.md); merge history in `git log`, per-run numbers in devtools/zeroshot/CALIBRATION.md.

## Production
Version: v0.8.3 PUBLIC latest at github.com/pinkynail228/zeroplan since 2026-10-30 (tag on export 63465b1 of 44f0edb, the rc1 commit; soak NO BLOCKER, report in the private archive; pinned rc1 install gives 0.8.3, unpinned and `zplan update` kept 0.8.2 until final). Previous: v0.8.2 (7296f91). Branch main, pushed to the private origin only through the gated push (ORCHESTRATOR.md step 5).
Linux: dropped by the owner 2026-10-28 (no Linux gate or host; last Linux-qualified SHA a007b6e = v0.6.3); qualification is macOS only.

## Direction
Goal: zplan's architect runs the whole loop on any repository; autonomy auto (default) / supervised / manual. Public repository `zeroplan` (command `zplan` stays).
Release 0.8.0 (owner 2026-10-27): the public release ships an English-only interface; translate once, full suite once at the end; per merge only write-set test modules.
Designs (critic-reviewed, in the pause dir): 0.7.1-dirty-login.md, 0.8-english-ui.md (translate in place; legacy Russian input still accepted; T1 || T2, then T3 closes).
Input (owner 2026-10-25): no single-letter keys; every action is a / command in the chat.

## Now
0.9.0 candidate (2026-10-30): P1 p091, P2 p092, P3 p093 (without Q4), P4 p094 (without the end screen's merge confirm), P6 p096, u4, u6, v090, repairs r1, r23, r4 merged. Critic rel090: turn 1 BLOCK (two merge-policy holes) -> r23; turn 2 BLOCK 1 open on the gated path -> r4 (verified by its test, not by a third critic round: the owner decides). Whole Mac suite on the release SHA in a detached worktree.
Claude lane hit its 5-hour limit once (r2 attempt 1 died at select_init); rerun after the reset.
Plan (2026-10-30): docs/PLAN_0.9.md (milestones P1-P7). Owner 2026-10-30 (overnight go): Q1-Q5 and H1-H3 as recommended (A2 test policy, B1 cut `--plain`, W4+R8 into 0.9.0, no profile commit by default, local origin identity); release v0.8.3 in stages (rc1, soak, final if no blocker); implement the plan, release, then a feedback review and the next plan (UX). The 1.5x budget goes; the critic is gpt-6-astra xhigh.
Claude lane for every run. Process (owner 2026-10-27, after "first idea, no design"): facts -> design doc -> independent critic -> owner's product decision -> briefs.
Test policy (owner 2026-10-30, A2): a test only for new uncovered behaviour or a reproduced defect; reviewers run no tests; the final check runs the DoD once; budget.py and every 1.5x rule are gone (preamble, ORCHESTRATOR; the shipped method in P1).
Incident 2026-10-27: an R6 brief had an agent copy ~/.codex auth and run `zplan login`, which revoked the owner's token. Automated tests never use the owner's credentials (fake Codex, isolated HOME). Owner's go 2026-10-29: manual qualification walks may run zplan with the owner's real HOME and ~/.codex in place; never copy, print or move the auth files and never run `zplan login`/`codex login`/logout there (the copy is what revoked the token).
Roles (owner 2026-10-28): worker `gpt-6.1-terra`/max, every other role `gpt-6.1-sol`/high. Preset `zplan.default/3` (t4a) is what a first start proposes; /1 and /2 stay frozen. This repo's and the owner's two projects' zplan.process.json carry the same split (the two projects: edited, not committed, their trees hold the owner's work).

## Next
1. Suite green on the release SHA -> export and tag v0.9.0-rc1 (pre-release), soak walk; final v0.9.0 waits for the owner (critic rounds used up, last BLOCK fixed by r4).
2. Then docs/PLAN_UX.md (critic planux taken): U1-U6 for 0.9.1, U7-U8 for 0.9.2.
3. Later from 0.9.0: the "No merge check" line for the owner's own /merge (critic rel090 item 3); F4 stale rule (own design); v1 golden; the incomplete rerun.
4. Brief preflight: grep tests/ for every value, returned field and helper the change touches (p09a, p092, p094 conflicts).

## Open
Harness: run.sh exits 0 when milestone_run refuses a brief; check its last line, not the code. Start runs one after the other (same-second starts race). Before a brief, grep tests/ for every value the change touches (preflight conflicts s3a, a10c).
Later: critic 5 s polling (audit finding 10); API-key auth; guarded `--approve-for-me`; Russian/Chinese UI back via the catalog.
Harness: `run.sh --validate-only` leaves a worktree at HEAD (commit the brief first or remove it); two run.sh launches at the same second can fail at start (stagger).
devtools/ux_walkthrough.py is stale since the project picker (expects the profile choice first); not a 0.8.0 gate.
TUI load flakes (pass alone; confirm at the release gate): test_tui_card_keys k1_k4_at_80x24, test_tui_run_command p1a_c1_c2 (focus under load, suite on 867bc5c), test_checks HardKill a / Lease a, test_tui_chat c4_c6/c6b, test_tui_polish ResultModal a3, TerminalTests real-pty (also under -j 2), QuitSafety c1, MergeCardDraftShell, test_tui_question_card a1_a2, test_tui_live la1, test_tui_milestones a1b, test_new_session c1.
