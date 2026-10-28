# STATE

Updated: 2026-10-28. Rules: devtools/zeroshot/ORCHESTRATOR.md (section STATE.md); merge history in `git log`, per-run numbers in devtools/zeroshot/CALIBRATION.md.

## Production
Version: v0.8.0 PUBLIC at github.com/pinkynail228/zeroplan since 2026-10-28 11:12 (export 6893e2f of 6795a0c; R1/R2/R9 PASS, curl|sh from GitHub verified on macOS: R1R2R9-6795a0c.md in the pause dir, folder public). v0.7.0 tag deleted (history is one commit). Branch main, pushed to the private origin only through the gated push (ORCHESTRATOR.md step 5). Installed on macOS arm64: zplan 0.6.2 (owner's test build).
Last Linux-qualified SHA: a007b6e = v0.6.3 (2026-10-27). Owner 2026-10-28: Linux gates are dropped for 0.8.0; the release is qualified on macOS only (whole Mac suite, gitleaks, R4/R8 as fresh-HOME installs on the Mac). AGENTS.md still names the Linux host (locked; owner unlock needed to change it).

## Direction
Goal: zplan's architect runs the whole loop on any repository; autonomy auto (default) / supervised / manual. Public (owner 2026-10-27): repository `zeroplan` (command `zplan` stays), plan docs/PUBLIC_RELEASE_PLAN.md (fresh export, clean-room installs, flip R9 on the owner's go).
Release 0.8.0 (owner 2026-10-27): the public release ships an English-only interface; translate once, full suite once at the end; per merge only write-set test modules.
Designs (critic-reviewed, in the pause dir): 0.7.1-dirty-login.md (the working tree is the user's, every reader sees HEAD; zplan logs in/out only of the home it owns; owner chose the confirmed «commit» action A2), 0.8-english-ui.md (translate in place; legacy Russian input still accepted; T1 || T2, then T3 closes).
Input (owner 2026-10-25): no single-letter keys; every action is a / command in the chat.

## Now
Claude lane for every run. Process (owner 2026-10-27, after "first idea, no design"): facts -> design doc -> independent critic -> owner's product decision -> briefs.
Test audit 2026-10-28 (REPORT.md in the pause dir, folder test-prune): no safe mass deletion; cost is agents running tests and growth. Levers: devtools/budget.py (in every brief's DoD) and rule diffs in the report (owner unlock).
Incident 2026-10-27: an R6 brief had an agent copy ~/.codex auth and run `zplan login`, which revoked the owner's token. Never use the owner's credentials in tests; R6 reruns use a test-only Codex login or a fake Codex.
Test policy (owner 2026-10-28, "overtesting again"): briefs iterate on the failing modules only and run the DoD once at the end; the orchestrator runs the whole Mac suite once per merge. A timed-out run: commit its diff on its branch, resume with `ZS_ATTEMPT=N` (rmdir NAME.lock first).
Roles (owner 2026-10-28): worker `gpt-6.1-terra`/max, every other role `gpt-6.1-sol`/high. Preset `zplan.default/3` (t4a) is what a first start proposes; /1 and /2 stay frozen. This repo's and the owner's two projects' zplan.process.json carry the same split (the two projects: edited, not committed, their trees hold the owner's work).

## Next
1. One release 0.8.1 (owner 2026-10-28: no separate 0.8.2) = t4a role split, t4b version, t4c code-map tests, t4d export_check images, t4e `/scheme` whole screen, h1 final check `incomplete` (68012c2), h3 proportionate checks (c75cf86), h2 read-only verifiers (e929980), h4 prompt hygiene, no Risk-Tier in commits (f990a82), h5 (61a90ea), l1 live final-attempt count (2976b6b), s1b status rewrap after `/scheme` (b4a5fd1). Whole Mac suite 2331 OK on cfdd7d7, export_check 0 findings. Left: README (item 4) -> re-export (pub-081 at 5b0ba8f is stale) with tag v0.8.1, gitleaks + lychee. No Linux qualification (owner). Push, Release, topics only on the owner's yes.
2. Owner UX items from R6 0.8.0 (F3-F5, F7-F8) and the demo auto card without an architect; cold README run 2026-10-28 (0.8.1 candidate) adds: the demo profile card promises a commit that does not happen, the demo plan card says "the architect will approve it itself" while the pane says /approve, the action.refused line shows before any input, /run confirm keys read "[tab] yes [enter] start".
3. Next release, after a measurement: fewer model calls (select trio, scope_verify); merge-critic facts need a design; the empty-queue final check's live count (l1 note).
4. README: the owner reviews it once items 1 and 3 are merged, then a rework before the export: lead with goal -> checked plan -> your branch, scope changes as your decision; double review credited as Zeroshot's core.

## Open
Owner decision: `/merge` asked in `auto` when a folder has no checks: (a) merge after the reviewer verdict or (b) keep the ask with a "no checks" note.
Owner unlock needed: rule diffs in the test-prune REPORT (reviewer test-run cap, budget gate); ORCHESTRATOR.md still says full Mac suite per merge; owner rules 2026-10-27/28 (Test policy above) override it until the file is updated.
Later: critic 5 s polling (audit finding 10); API-key auth; guarded `--approve-for-me`; Russian/Chinese UI back via the catalog.
Harness: `run.sh --validate-only` leaves a worktree at HEAD (commit the brief first or remove it); two run.sh launches at the same second can fail at start (stagger).
Linux hosts 2026-10-28: host 2 deleted by the owner; host 1 and a new 1-CPU host both drop SSH before the banner (the new host during a full suite, probably overload). Not used for 0.8.0 (owner).
devtools/ux_walkthrough.py is stale since the project picker (expects the profile choice first); not a 0.8.0 gate.
Linux suite needs `ZPLAN_TEST_TIMEOUT=3600`.
TUI load flakes (pass alone; confirm at the release gate): test_checks HardKill a / Lease a, test_tui_chat c4_c6/c6b, test_tui_polish ResultModal a3, TerminalTests real-pty (also under -j 2), QuitSafety c1, MergeCardDraftShell, test_tui_question_card a1_a2, test_tui_live la1, test_tui_milestones a1b, test_new_session c1.
