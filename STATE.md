# STATE

Updated: 2026-10-29. Rules: devtools/zeroshot/ORCHESTRATOR.md (section STATE.md); merge history in `git log`, per-run numbers in devtools/zeroshot/CALIBRATION.md.

## Production
Version: v0.8.1 PUBLIC at github.com/pinkynail228/zeroplan since 2026-10-28 (export 9a4cedf of 6713650; GitHub Release v0.8.1 latest; critic rel081b GO; macOS only). Previous: v0.8.0 (export 6893e2f of 6795a0c). v0.7.0 tag deleted (history is one commit). Branch main, pushed to the private origin only through the gated push (ORCHESTRATOR.md step 5).
Linux: dropped by the owner 2026-10-28 (no Linux gate or host; last Linux-qualified SHA a007b6e = v0.6.3); qualification is macOS only.

## Direction
Goal: zplan's architect runs the whole loop on any repository; autonomy auto (default) / supervised / manual. Public repository `zeroplan` (command `zplan` stays).
Release 0.8.0 (owner 2026-10-27): the public release ships an English-only interface; translate once, full suite once at the end; per merge only write-set test modules.
Designs (critic-reviewed, in the pause dir): 0.7.1-dirty-login.md, 0.8-english-ui.md (translate in place; legacy Russian input still accepted; T1 || T2, then T3 closes).
Input (owner 2026-10-25): no single-letter keys; every action is a / command in the chat.

## Now
Track A (docs/RELEASE_0.8.2_PLAN.md) done 2026-10-28/29: A1 s4, A1b s5, A2 l2+l2b, A3 s3a+s3b, A4 s2a+s2b, A6, A7 p1, A8, A9, A10 a10+a10b+a10c; merge commits and gates in `git log`. Residuals: a terminal reply tail >100 ms after a stall is typed as text; no single key empties a multi-line input.
Track C (docs/RELEASE_0.8.2_WALK_PLAN.md, from a real walk on 2026-10-29) done 2026-10-29: c1 + c1b, c2, c3, c4 merged; v082 (version 0.8.2) merged; UPGRADE.md: 0.8.1 refuses a 0.8.2 store, so rollback only to the installer's backup. Candidate 1552ea4: suite 2378 tests, 1 failure (STATE.md budget, fixed); critic rel082 AGREE WITH CHANGES (c5 stale-plan Next merged; README auto merge; notes; spike not exported); rc1 re-walk: U1, U2, U4, U5 PASS, U3 partial; N1 (merge asks again while the critic works) fixed by c6, c6b-c6d (critics rel082b-d), N3/N5 by c7; N2, N4, N6, N7 in the walk plan.
Owner's go 2026-10-29 (overnight, limits lifted, past 0.8.2 too): tag v0.8.2-rc1 as a pre-release, soak walk (real project, clean HOME, every past case), final v0.8.2 if no blocker (no wait), else rc2; then Track B research (B1-B7; B8 is the owner's).
Claude lane for every run. Process (owner 2026-10-27, after "first idea, no design"): facts -> design doc -> independent critic -> owner's product decision -> briefs.
Test audit 2026-10-28 (REPORT.md in the pause dir, folder test-prune): no safe mass deletion; cost is agents running tests (54% of agent time) and growth. Its rule diffs are applied (2026-10-28): reviewers run at most one test id, repairs extend tests, budget.py in the DoD and the gate (counts untracked files).
Incident 2026-10-27: an R6 brief had an agent copy ~/.codex auth and run `zplan login`, which revoked the owner's token. Automated tests never use the owner's credentials (fake Codex, isolated HOME). Owner's go 2026-10-29: manual qualification walks may run zplan with the owner's real HOME and ~/.codex in place; never copy, print or move the auth files and never run `zplan login`/`codex login`/logout there (the copy is what revoked the token).
Test policy (owner 2026-10-28, "overtesting again"): briefs iterate on the failing modules only and run the DoD once at the end; a merge runs the DoD modules, budget.py and export_check; the whole Mac suite once per release candidate. Critic: triggers only, no daily cap; argue turns through `critic.sh NAME --argue` (read-only). A timed-out run: commit its diff on its branch, resume with `ZS_ATTEMPT=N` (rmdir NAME.lock first).
Roles (owner 2026-10-28): worker `gpt-6.1-terra`/max, every other role `gpt-6.1-sol`/high. Preset `zplan.default/3` (t4a) is what a first start proposes; /1 and /2 stay frozen. This repo's and the owner's two projects' zplan.process.json carry the same split (the two projects: edited, not committed, their trees hold the owner's work).

## Next
1. Plans: docs/RELEASE_0.8.2_PLAN.md (track A done; track B = 0.9 chat-first design: B0, B4 done; B1 source tracing and B3 draft schema done (spike B1_B3_B4, not exported); open B1 canaries, B2 corpus, B3 probe, B5-B7, B8 the owner's, B10) and docs/RELEASE_0.8.2_WALK_PLAN.md (soak and 0.9 rows). Feedback rows: 0.8.1-testers.md in the pause dir, folder feedback.
2. Owner R6 0.8.0 items (F3-F5, F7-F8) and the demo cards from the cold README run: folded into B5.
3. Track C, after a measurement: fewer model calls (select trio, scope_verify); merge-critic facts need a design; the empty-queue final check's live count (l1 note).
4. README: rework from tester feedback (item 1) after the 0.8.2 soak (plan, track C): lead with goal -> checked plan -> your branch, scope changes as your decision; double review credited as Zeroshot's core.

## Open
Harness: run.sh exits 0 when milestone_run refuses a brief; check its last line, not the code. Start runs one after the other (same-second starts race). Before a brief, grep tests/ for every value the change touches (preflight conflicts s3a, a10c).
Owner decision: `/merge` asked in `auto` when a folder has no checks: (a) merge after the reviewer verdict or (b) keep the ask with a "no checks" note.
Later: critic 5 s polling (audit finding 10); API-key auth; guarded `--approve-for-me`; Russian/Chinese UI back via the catalog.
Harness: `run.sh --validate-only` leaves a worktree at HEAD (commit the brief first or remove it); two run.sh launches at the same second can fail at start (stagger).
devtools/ux_walkthrough.py is stale since the project picker (expects the profile choice first); not a 0.8.0 gate.
TUI load flakes (pass alone; confirm at the release gate): test_checks HardKill a / Lease a, test_tui_chat c4_c6/c6b, test_tui_polish ResultModal a3, TerminalTests real-pty (also under -j 2), QuitSafety c1, MergeCardDraftShell, test_tui_question_card a1_a2, test_tui_live la1, test_tui_milestones a1b, test_new_session c1.
