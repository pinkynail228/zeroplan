G1a fixes — merge-gate findings (critic g1a-merge: NO-MERGE) on the G1a process profile commit already on this branch (`git log -2`: the G1a commit, then an unreviewed WIP commit with a first, interrupted pass over these fixes — verify and complete it, do not trust it; task devtools/zeroshot/tasks/g1a-profile.md, design docs/PROCESS_PROFILE.md). Fix only these; no new features, no refactor. Do not touch prototype/, upstream/, reference/, docs/history/, STATE.md, AGENTS.md, LICENSE, docs/PROCESS_PROFILE.md. No real provider; no network. Russian UI, English code.

1. P1 "later" returns a stale rules digest: the snapshot restores stored rule hashes (process.py ~417) and resolution never re-reads the files (~544). Re-read the current project's rules on every resolution of a "later" snapshot (same as a file profile), so a rules change or deletion changes the digest, and a missing rules file is refused like in a file profile with family `process.invalid` (the snapshot itself is not reported as corrupt). Tests: rules edited and rules deleted after "later" -> digest changes / refusal; preview then rules change -> `start` refused with no new attempt, worktree or HEAD change.
2. P2 bootstrap promises what does not work yet: the bootstrap screen (~687) shows "Правила для агентов" and "Проверка (квалификация)" without saying they act only in later stages. Use the same wording as `describe()` ("для следующих этапов"); plain and Pilot tests assert it.
3. Crash/lock tests must exercise the real operations: inject a failure inside the real `accept()` between writing zplan.process.json and the final sidecar write, reopen, and assert recovery (the hand-written `accepting` test, test_process.py ~429, may stay for the before-file case; add the real injection after the file is created). Add: `profile init` from a second process while the Authority lock is held is refused or waits and never writes the sidecar unlocked; the refusal is bounded in time (the lock uses LOCK_NB). Also call `Profile.peek(...).accept()` / `defer()` directly without the Authority lock: refused, profile file and sidecar unchanged.
4. Unguarded branches:
   - detection with only a Makefile (no package.json) under the no-subprocess guard (test ~708 never reaches it);
   - valid preview -> profile switched to `task: required` / profile deleted -> `start` refused, snapshot state, worktrees and HEAD unchanged (test ~502 covers preview only);
   - required task/merge refusal and deleted-profile merge refusal through both frontends (TUI Pilot and plain), not only Delivery;
   - new roles reach a structured needs_owner candidate -> attempt and `new_attempt(note)` (test ~661 covers free-text -> plan only);
   - with the profile deleted, an actively running fixture attempt can still be watched to its end and exported (test ~568 opens an already exported result).
5. Non-blocking (no test): remove unused `GATE_NAMES`/`ACTING` (process.py ~46) if unused; fix docs/INSTALLATION.md ~73 (roles are not edited via [s]; say where they live).

Acceptance criteria:
- F-A1 Each behaviour in items 1-4 has a test that fails when its fix is reverted (say how you checked, per item).
- F-A2 Full suite green with ZPLAN_TEST_WHEELHOUSE=/tmp/zs-zplan/wheelhouse; devtools/ux_walkthrough.py stays green (name the interpreter).

critic g1a-fixes: GO WITH CHANGES (3), applied 2026-10-15.
