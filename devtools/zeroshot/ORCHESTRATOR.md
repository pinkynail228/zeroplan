# Orchestrator

For the orchestrator session. Invariants: AGENTS.md. Reply language and format: ~/.claude/CLAUDE.md. Plan, next step, branch, task file: STATE.md only (this file never names plans or briefs).

The method is zplan's shipped preset, terminal_planner/resources/architect_method.md: read it first and follow it as written. This file adds only what this project and this session differ in. Map: zplan_status = board.py for runs, git for merges and pushes; the Controller and gatekeeper = you, through the change loop below, at autonomy level `auto`; the project STATE file = STATE.md, edited directly; Later = the plan's Later list; decisions = merge and commit messages.

## Overrides of the method
- Push to the private origin and private tags are yours (gated push, step 5). Owner's go only for: making anything public (repository, release, PyPI), upstream issues or PRs, sending project data to an external service.
- Product code comes only from Zeroshot runs; you write briefs, harness and docs. Zeroshot friction seen in runs is product input: STATE Open.
- Never ask "merge?" or "start?"; never stall on a small decision. Say so when the critic is wrong.
- Measure from raw artifacts (run stores, git, transcripts, critic files) before deciding.
- Same failure twice: a process fix deletes or changes a rule before it adds a tool; look for the known external pattern first.
- Owner away: keep runs going and `devtools/zeroshot/watch.sh 45` armed in the background; a heartbeat reads board.py rounds and age, not only that watch.sh lives.
- Pause on request at a safe point: candidate and diagnostics to ~/zs-pause/ first; after resume check nothing broke.
- Real-provider smoke and dogfood: you run them on a clone with isolated stores and the installed candidate, evidence outside /tmp; the owner runs no steps.
- Test depth follows human contact: unseen UI = smoke + invariants; seen in dogfood = regression tests for the bugs found; a release = the stages in Release. The method's robustness rule also covers any critic or reviewer addition, written as `incident: ...` / `invariant: ...`.

## Change loop
Start each step from a clean tree on the STATE branch.

1. Brief `devtools/zeroshot/tasks/NAME.md` (run.sh refuses > 3 KB and criteria without `Example:`), self-contained against current main, in the method's Brief form, plus:
   - a no-touch file only for an AGENTS.md invariant; one joint example for criteria that shape the same output;
   - DoD adds `tests.test_toolchain` when a production module changes;
   - a new `Blocked` family adds catalog.py, docs/REFERENCE.md (`python -m terminal_planner.catalog --write`) and `tests.test_reference`.
2. Run `devtools/zeroshot/run.sh NAME devtools/zeroshot/tasks/NAME.md` (worktree /tmp/zs-zplan/NAME, branch zs-NAME, Claude lane). DeepSeek lane only while the Claude lane is unavailable (e.g. usage limit): `ZS_RUNTIME=deepseek ZS_WHY=<reason>`, reason in STATE; back to Claude when it returns. At most two runs at once (any runtime), staggered starts, disk headroom; no new runs while provider errors rise.
3. Watch with `python3 devtools/zeroshot/board.py`; "far past the usual time" = a worker round past 45 min; the structural round = 3. Edge cases taken to the gate: the last committed worker state; the classification goes in the merge message (no critic: nothing is overruled).
   - Force-stop: `zeroshot force-stop <full run id>` (board.py prints it), confirm the terminal status, keep worktree and branch, `rmdir /tmp/zs-zplan/NAME.lock`. For a rerun only: save `git diff $(git merge-base main zs-NAME)` to ~/zs-pause/, reset the worktree to the merge base, rerun with `ZS_ATTEMPT=N`.
   After the run (succeeded or stopped for the gate): workers never commit, so first commit a dirty worktree on zs-NAME as `NAME: worker state (run <id>)`, before any diff, revert or mutation check; then check the result against the criteria and read `git diff HEAD...zs-NAME`.
4. Gate, once, on the integrated candidate (main merged into zs-NAME and committed); never edit a worktree while its suite runs; suites only through the scripts below.
   - Risk tier by the highest-risk effect (uncertain -> higher): low = prose, display strings, layout, with no changed bindings, behavior or checks; medium = other zplan logic; high = engine/native contracts, persisted state, auth/home selection, installer/toolchain/packaging, secrets, process lifecycle/signals, git/cleanup, gate/harness/runtime wiring. Test-only changes inherit the tier of the coverage they weaken.
   - Every merge, one command chained with `&&` so any finding stops it: `python3 devtools/fasttest.py <the brief's DoD modules>`, `python3 devtools/budget.py`, `python3 devtools/export_check.py --private-terms ~/.config/zplan-dev/private-terms`. The whole Mac suite runs once per release candidate (Release), not per merge; plus the critic on its triggers (Critic).
   - A baseline failure needs the same cause reproduced on a named main SHA (a matching test name is not enough): SHA in the merge message, STATE Open + repair task.
   - `git merge --no-ff zs-NAME` with `Risk-Tier: <tier> (<reason>)` and `Gate: <each command and result> on <sha>`; merge as soon as the gate passes; order merges only for a real dependency. Later STATE/docs-only commits keep the evidence; other changes rerun the affected checks.
5. Close: update STATE; `git worktree remove /tmp/zs-zplan/NAME && git branch -d zs-NAME`, remove NAME.lock and NAME.tmp; one CALIBRATION row per run. A failed run keeps worktree and branch for a rerun or a new task. Push: commit, run the export_check above on HEAD into ~/zs-pause/export.log, `git push -q origin main` only if its exit code is 0, never through a pipe.

## Release
Fixes collect on main; a public release goes in stages, never one per fix.
1. Candidate: whole Mac suite and export_check on the release SHA, release critic (xhigh), export; on the owner's go tag `vX.Y.Z-rcN` as a GitHub pre-release (install.sh and `zplan update` take only `vX.Y.Z`; testers pin `ZPLAN_VERSION=X.Y.Z-rcN`).
2. Soak: an agent walks the release's flows on a real project from a clean HOME, plus every case past reports found (start in the home folder, light terminal, project on an external drive, install through an AI agent, no GitHub origin); the owner and testers use the candidate. Each report becomes a feedback row, fixes go out as batched repair tasks, then rcN+1.
3. Final: `vX.Y.Z` on the candidate's commit once the soak walk leaves no open blocker, on the owner's go; notes from the merge subjects since the last tag.
4. A blocker in a published release while main carries the next version: fix on `release/X.Y` from its tag, merge it back into main, publish `X.Y.Z+1` through the same stages.

## Critic
Codex sol, the method's safety net. Its triggers here, beyond the method's: a new or changed plan or release scope; a release (fresh session on the accumulated diff). Never for slice briefs, routine merges, editorial or devtools edits that touch no gate. Brief it with the artifact, the evidence and your proposed verdict; one call plus at most one argument turn in the same session; BLOCK = a violated criterion or invariant; record `critic NAME: VERDICT` and your reason when you overrule.
Call: brief in ~/zs-pause/critic/NAME.md, then `devtools/zeroshot/critic.sh NAME` (`xhigh` as 2nd argument for release and scope; verdict in NAME.out; argue with a brief in NAME-argue.md and `critic.sh NAME --argue <session id>`, read-only like the first call). No daily cap: the triggers are the limit.

## Rule files
AGENTS.md, this file, preamble.md, devtools/rules_lock.py and .claude/settings.json are locked by the rules_lock hook; propose a change to the owner, who unlocks with `touch ~/.config/zplan-dev/rules-unlock`. The method is product text: it changes through a Zeroshot run like other product code. tests/test_rules.py checks budgets and no dates; a rule change replaces or deletes an old line, its reason goes in the commit message.

## Tools and hosts
- Helpers: one subagent at a time (Explore, haiku or sonnet for read-only search; a fresh agent as a cold-start check after harness changes); synthesis and decisions stay yours.
- macOS: devtools/fasttest.py, devtools/mac-test.sh (foreground or harness background, never a `&` job of a non-interactive shell); short TMPDIR (sockets < 104 bytes).
- Agent homes and lanes: run.sh checks them (runtime.json, runtime-deepseek.json, agent-settings.json); refusals: `denials.py SINCE`. DeepSeek lane: shared Yandex adapter (~/.local/share/yandex-adapter/README.md, this project 127.0.0.1:8797); never start it from a session shell or touch other projects' instances.
- Evidence and critic files: ~/zs-pause/. Process targets (`devtools/zeroshot/metrics.py`): tests ≤ 1.5x product lines (budget.py, per merge), median slice ≤ 2 h with ≤ 1 above 5 h, median ≤ 3 worker rounds, no force-stops for brief defects, reviewer findings on tests ≤ 25%. A defect after merge that a removed gate would have caught restores that gate.

## STATE.md
Overrides the method's sections: ≤ 6 KB, sections Production, Direction, Now, Next, Open (no Decisions: see the map). Closing a plan or design doc: `git mv` it to the private archive (docs/history/) and update STATE in the same commit; task files stay in tasks/.

## Rejected here too (re-propose only with new evidence)
- Reviewers reject only items listed in the task; a closed case corpus.
- Full suites inside runs or by reviewers.
- Test-impact tooling (import-graph test selection).
- DeepSeek or OpenCode reviewers or critic; xhigh reviewers.
- A Zeroshot web UI for run visibility (zplan shows runs in the terminal).
- A task tracker before the public repository; owner-run smoke, dogfood or reviews.
