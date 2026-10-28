# STATE

Updated: 2026-10-28. Rules: devtools/zeroshot/ORCHESTRATOR.md (section STATE.md); merge history in `git log`, per-run numbers in devtools/zeroshot/CALIBRATION.md.

## Production
Version: v0.7.0 tagged in the private export repo pinkynail228/zeroplan (6a9947b export; R1/R2 PASS, gitleaks clean with .gitleaks.toml); stable v0.6.3 = a007b6e. Branch main, pushed to the private origin only through the gated push (ORCHESTRATOR.md step 5). Installed on macOS arm64: zplan 0.6.2 (owner's test build). Evidence: the pause dir public/ (R1R2-6a9947b.md, R4R8.md, R5.md, R6.md).
Last Linux-qualified SHA: a007b6e = v0.6.3 (2026-10-27). Owner 2026-10-28: Linux gates are dropped for 0.8.0; the release is qualified on macOS only (whole Mac suite, gitleaks, R4/R8 as fresh-HOME installs on the Mac). AGENTS.md still names the Linux host (locked; owner unlock needed to change it).

## Direction
Goal: zplan's architect runs the whole loop on any repository; autonomy auto (default) / supervised / manual. Public (owner 2026-10-27): repository `zeroplan` (command `zplan` stays), plan docs/PUBLIC_RELEASE_PLAN.md (fresh export, clean-room installs, flip R9 on the owner's go).
Release 0.8.0 (owner 2026-10-27): the public release ships an English-only interface; translate once, full suite once at the end; per merge only write-set test modules.
Designs (critic-reviewed, in the pause dir): 0.7.1-dirty-login.md (the working tree is the user's, every reader sees HEAD; zplan logs in/out only of the home it owns; owner chose the confirmed «commit» action A2), 0.8-english-ui.md (translate in place; legacy Russian input still accepted; T1 || T2, then T3 closes).
Input (owner 2026-10-25): no single-letter keys; every action is a / command in the chat.

## Now
Claude lane for every run. Process (owner 2026-10-27, after "first idea, no design"): facts -> design doc -> independent critic -> owner's product decision -> briefs.
Merged (module gates, full suite deferred): D4a-D4c, D6a, D6b, D5 99bb9dd, T1 bd91b8a (English services, CLI, installer), T2 c34d785 (English TUI; 3 attempts, 1-2 hit the 2700 s worker limit). test_agent_activation fixed by the prune run (0f3ab0a).
Test audit done 2026-10-28 (report: REPORT.md in the pause dir, folder test-prune): no safe mass deletion (two cold-start reviews: tests sharing lines check distinct things); cost is agents running tests (54% of agent wall time, reviewers 67%) and growth (1.59x test/product lines). Levers: devtools/budget.py (test budget, exit 1 = over; in every brief's DoD now) and rule diffs in the report (owner unlock).
Incident 2026-10-27: an R6 brief had an agent copy ~/.codex auth and run `zplan login`, which revoked the owner's token. Never use the owner's credentials in tests; R6 reruns use a test-only Codex login or a fake Codex.

Test policy (owner 2026-10-28, "overtesting again"):
- Translation runs touch most tests, so "changed modules" is about half the suite and a worker re-running it exhausts the 2700 s limit. Briefs say: iterate on the failing modules only, run the DoD once at the end.
- T3's worker DoD: only the new guard test + tests.test_docs + tests.test_reference + export_check, not the full suite.
- After T3 merges: the orchestrator runs the full Mac suite once (`TMPDIR=/tmp/zt python3.13 devtools/fasttest.py`), fixes failures in one follow-up run if needed, then Linux once (`ZPLAN_TEST_TIMEOUT=3600 devtools/linux-test.sh` on the Linux test host).
- A timed-out run: commit its diff on its branch, resume with `ZS_ATTEMPT=N` (rmdir the NAME.lock first); module gates include tests.test_toolchain (bare-import check).

## Next
1. T3 merged c2bb5d0, t3b merged fe0662f 2026-10-28 (install.OWNED keeps "0.7.0"; two stale pins). Mac: whole suite on 37c3cab (2305 tests, the 2 failures t3b fixed) + module gates after. README for 0.8.0 with SVG screenshots (readme_shots.py) in main. R6 (fresh HOME, no credentials) PASS 2026-10-28 after README fixes; its ~/.codex finding fixed by t3c (merged 51e80d3). Release critic r080-public (xhigh): 6 blockers, all fixed (docs commit + t3d alias guard). Whole Mac suite on 32acf43: 2308 tests, 1 failure = known load flake MergeCardDraftShell (module passes 3/3 alone); gitleaks on export 32acf43: history and tree 0. Mac R4a/R4b/R8 (fresh HOMEs, no login) PASS 2026-10-28 (R4R8.md in the pause dir, folder r4r8-080-mac). Next: export, force-push main + v0.8.0 to zeroplan, R1, flip public, curl|sh check. Next: Linux once, export 0.8.0, R1/R2, gitleaks + R4/R8 (scripts in the pause dir, public/r4r8-080), release critic, public flip (owner go 2026-10-28).
2. Docs pass items (can join T3): git identity in prerequisites, project picker screen, `/merge` is the confirmation, Codex trust entries in the own home, README:14 merge wording, merge hooks line, "zplan installs its own pinned Zeroshot/Codex beside yours".
3. New English README with screenshots and examples. Release (~1-2 h), owner go given 2026-10-28 ("roll out to the public repository"): export 0.8.0 (export.py in the pause dir), R1/R2 + gitleaks, short R4, fresh R6 without owner credentials, release critic, owner go, R9 visibility flip.

## Open
Owner decision: `/merge` asked in `auto` when a folder has no checks: (a) merge after the reviewer verdict or (b) keep the ask with a "no checks" note.
Owner unlock needed: rule diffs in the test-prune REPORT (reviewer test-run cap, budget gate); ORCHESTRATOR.md still says full Mac suite per merge; owner rules 2026-10-27/28 (Test policy above) override it until the file is updated.
Later: critic 5 s polling (audit finding 10); API-key auth; guarded `--approve-for-me`; Russian/Chinese UI back via the catalog.
Harness: `run.sh --validate-only` leaves a worktree at HEAD (commit the brief first or remove it); two run.sh launches at the same second can fail at start (stagger).
Linux hosts 2026-10-28: host 2 deleted by the owner; host 1 and a new 1-CPU host both drop SSH before the banner (the new host during a full suite, probably overload). Not used for 0.8.0 (owner).
devtools/ux_walkthrough.py is stale since the project picker (expects the profile choice first); not a 0.8.0 gate.
Linux suite needs `ZPLAN_TEST_TIMEOUT=3600`; host 2 lacks python3.13 (3 test_dev_milestone_run fails).
TUI load flakes (pass alone; confirm at the release gate): test_checks HardKill a / Lease a, test_tui_chat c4_c6/c6b, test_tui_polish ResultModal a3, TerminalTests real-pty (also under -j 2), QuitSafety c1, MergeCardDraftShell, test_tui_question_card a1_a2, test_tui_live la1, test_tui_milestones a1b, test_new_session c1.
