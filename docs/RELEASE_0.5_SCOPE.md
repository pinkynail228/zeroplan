# Release 0.5 scope

Status: 2026-10-18; critic rel05-scope (session 01a1488f, xhigh) GO WITH CHANGES, applied below.
Updated 2026-10-20: critic gate22 (~/zs-pause/critic/gate22.out) moves release mode (S1c) and flake diagnosis (S6) to 0.5.x; the merge gate stays in 0.5 in plain and TUI.
Owner request: 0.5 removes the manual environment work the owner and the orchestrator do today: setup, disabling stray
tools/skills/integrations, babysitting limits and stalls, cleanup, flake triage. Each item cites an observed incident.
Experiments are listed separately.
Current decision (owner, 2026-10-19 night): 0.5 is a private dogfood release — zplan usable on its own repository.
The rename, public repository, stranger-install run and recorded demo are deferred; they need the owner's go and are
re-gated with the critic then. 0.4.0 remains a private stable tag.

Decision 2026-10-20 (owner asked for a faster process; critic proc-speed P1/P6 DO): no new roadmap admissions. Next is
an installed dogfood session of zplan on its own repository, on the fixed main HEAD; 0.5 = the fixes that session shows
are blocking. The in-flight runs s1b1c and s1a1b2 merge by usefulness and remaining defects, not by a round count.
Robustness items without an observed incident or a proven invariant violation on the dogfood path (the check
supervisor/git-bound chain, S1b2 qualification records, S1c merge gate, S3, S5 remainder) wait in 0.5.x unless dogfood
shows them blocking.

Principle: an agent gets a minimal declared environment by default; anything more is an explicit opt-in that doctor
shows. zplan owns policy, presentation, approvals and its own checkouts; the native engine owns provider failures,
retries and its own scratch/checkpoint lifecycle (PROCESS_PROFILE.md:82). There is no second scheduler or lifecycle store.

## Items

| # | Item (minimal fix) | Incident | Layer | Depends on | Done evidence |
|---|---|---|---|---|---|
| S1a | G2 task gate before new attempts (s1a1; amendment barrier s1a2 deferred) | Task gates run by hand (ORCHESTRATOR.md) | zplan | G1 (0.4) | `/2` project: a milestone starts only after a task-gate verdict |
| S1b | G3 checks + evidence records (S6 flake diagnosis deferred to 0.5.x, critic gate22) | Suites, mutations and logs are collected by hand per merge | zplan | S1a | Check results recorded per attempt, and survive restart |
| S1c | G3 merge critic (plain + TUI) + derived truth (`zplan status`); release mode deferred to 0.5.x (critic gate22) | Merge critic and STATE by hand | zplan | S1b | Merge only after the checks and critic verdict, or an owner override |
| S1d | Preset `/2` migration | — | zplan | S1a-c | `/1` unchanged; `/2` taken only on the owner's accept |
| S2 | Agent home + profile + recovery binding + usage; undeclared skills and tools are not inherited (precedence fixed in AGENT_ENV_PLAN) | Account apps added ~73K input per turn; skills and integrations disabled by hand | zplan | — | AGENT_ENV_PLAN.md acceptance |
| S3 | Lanes as zplan setup: wrap per-node `lane` and the native connection store (connections.rs:49, :80); non-secret config and variable names only; adapter health from the configured URL, not a private install script or port | runtime-deepseek.json and install.sh by hand; resume needs GATEWAY_* set by hand (STATE Open) | zplan over native | S2 | Restart and recovery of a gateway run with no manual env; no credential in project config or Authority |
| S4 | Provider-failure diagnostics: stop with the saved result and a clear cause (limit / quota / auth / 403 / unknown), from engine data. Default: no automatic resume | A Claude limit or Codex 403 shows as `review_failed` (STATE Open) | engine data, zplan presentation | — | A seeded failure of each kind shows its cause; nothing is retried or charged again by default |
| S4b | Optional auto-resume: explicit per-run permission, attempt and time cap, cancellable, survives restart; never for auth, 403, quota or unknown | Plus 5h window as the limiter (DEV_RUNTIME_ECON) | zplan policy | S2, S3, recovery qualification | A permitted run resumes once after a seeded temporary limit, and a refused class does not |
| S5a | Durable work paths (no /tmp for zplan-owned checkouts and logs) + disk guard | A reboot wiped /tmp worktrees and logs; ENOSPC (STATE Open) | zplan | — | A reboot keeps the zplan-owned checkouts; low disk is refused up front |
| S5b | Cleanup of zplan-owned workspaces only: no live process, no recovery/export/gate reference, candidate saved. Never by prefix or age alone; foreign or ambiguous dirs are kept | /tmp/zs-agent-* ~80 GB, created by the reviewer preamble (preamble.md:2); native already removes its own execution dirs (filesystem.rs:120) | zplan | S2, S3 | Cleanup keeps the candidate and every referenced dir |
| S6 | Deferred to 0.5.x (critic gate22; briefs s1b3a/s1b3b kept, not launched). Flake diagnosis (inside S1b): bounded reruns of one repro on candidate and base, comparable env, exact SHAs, all results kept; else `unclear`. Output is diagnosis only, never a pass | Done by hand per merge (test_tui_live la1 2026-10-18: candidate 3/8, base 1/8) | zplan | S1b | 0.5.x: a failed check stays failed with a diagnosis attached; the gate is not bypassed |
| S8 | Tool-bump qualification command (pinned versions, envelope check, agent-home probe), run at every bump | 10.12 minor broke the strict envelope; Codex bumps add default-on features | devtools -> zplan | S2 | A bump without the record is refused by the release gate |
| S9 | Terminal run supervision: per-attempt view, readable scrubbed worker tail, observed stage, elapsed, activity/stall, configured model/effort versus actual unknown, usage completeness and S4 diagnostics. An optional plan-token budget blocks new starts and resumes, never live runs | Run visibility, stalls and cost watched by hand | public engine contracts, zplan | S4, S2c; dogfood-polish-04 already merged | Each stored running or finished milestone attempt is selectable in the terminal without a web page and shows time, node/review round, failure information, next step and scrubbed worker output. Unavailable stage/round or worker attribution is explicitly unknown; historical elapsed is an observation interval, not completion time. A seeded stall is visible; confirmed spend at the budget blocks the next start/resume without stopping an active run. |

Experiment, not a product item: S7, a bounded Serena trial (read-only, a separate home, one easy task, compared with
CALIBRATION). A project integration API is deferred until the trial has a result. Doctor shows stored probe results and
their conditions; it never runs a paid probe itself.

Deferred after 0.5 (owner, 2026-10-19): typed decision questions (open quantifier, size, finding in scope, convergence
probability) as structured outputs of select_verify and reviewers, backtested on past run stores; Jev
(typesafe.ai) only as an optional backend after that. For 0.5 only the devtools part applies: the task checklist and
the round-3 structural check in devtools/zeroshot/ORCHESTRATOR.md (critic foreman, GO WITH CHANGES). No rule narrowing
reviewer rejections: the data shows no reviewer scope creep, and a closed corpus never excuses a defect outside it. Superseded 2026-10-20 (critic review-loop): unnamed hostile inputs are non-rejecting spec gaps (preamble.md); see "Review-loop candidates".

## Upstream backlog (filing only with the owner's go)

Observed engine friction (each also zplan product input):
- An exhausted Claude limit or a Codex 403 surfaces as `review_failed`, indistinguishable from a review defect (S4); no typed provider failures with reset metadata, no provider retries.
- No per-visit record of the model/effort actually used, no stall signal (S9).
- The worker's final summary never reaches reviewers (the worker node returns `{"response":null}`); workaround: interpretations in regression-test docstrings (preamble.md).
- Prompt order: the static contract comes after the variable input.
- `resume --from-checkpoint` leaves the worktree on detached HEAD (move orchestrator commits with `git branch -f`); resume needs GATEWAY_BASE_URL/GATEWAY_API_KEY by hand (S3); a force-stopped run is `recoverable:false`.
- A rerun on the same HEAD needs a new submission key (run.sh ZS_ATTEMPT).
- Reviewer scratch copies (/tmp/zs-agent-*) are never cleaned (~80 GB, ENOSPC); the reviewer sandbox refuses `cp -R`/`tar` (preamble uses shutil.copytree). Engine scratch/checkpoint lifecycle is the engine's.
- Minor releases change contracts: 10.11 removed `review_repair`, 10.12 added `source.remote` (S8).
- Yandex accepts reasoning effort only up to `high`; a Responses gateway needs the shared adapter.

## Deferred

The Claude lane home (own login and qualification); the owner's own Claude Code session setup (not zplan's
environment); a project integration DSL (after S7).

S1a amendment barrier (s1a2): task gates protect new attempt starts only; in-run steward amendments may reach later workers without regating. Needs a deterministic native routing node or a production record of each worker's input (critic 01a15144, 2026-10-19).

0.5.x (critic gate22, 2026-10-20): release mode (s1c1e1-release-input, s1c1e2-release-ui) and flake diagnosis (S6: s1b3a-flake-diagnosis, s1b3b-flake-ui). Diagnosis is optional and never a pass; release decisions use the existing process until then. Before launch: a shared deadline/cancel contract for diagnosis covering checkout and cleanup (the 10 h bound covers checks only), optional-limit edits serialized with s9b1, and the approved-revision accessor named in s1c1e1.

S9b2: bounded Ctrl+Q exit after 60 seconds for operations with proven durable restart reconciliation, and scrubbed UI exception logging. Neither is a 0.5 release gate. Existing mutation-wait behavior remains until separately qualified.

## Order

Parallel lanes after the v0.4.0 tag (owner 2026-10-19: 4-5 DeepSeek groups; critic swarm05 GO WITH CHANGES, ~/zs-pause/critic/swarm05.out). A slice starts when its real prerequisites are merged, not at a wave barrier.

| Lane | Order | First slice after the tag |
|---|---|---|
| L1 environment | S5a (foreman pilot) -> s2a -> s2b -> s3a -> s3b | S5a disk probe/thresholds (new module + tests) |
| L2 gates | s1a1 -> s1b (s1b1 .. s1b2b; s1b3 deferred) -> s1c1 (s1c1a -> s1c1b -> s1c1c -> s1c1d1 + s1c1d2 as a pair; s1c1e deferred) -> s1d, s1c2; s9b1 budget after s2c usage | s1a1 artifact/gate graph (new module + tests, no UI/Authority wiring) |
| L3 UI | V1 -> V2 -> V3 -> V4 -> V5; gate/env/budget UI adapters between them | V1 (owns tui/app.py) |
| L4 runs | merge S4 -> s9a1 slices -> s2c usage -> S4b, S5b | s9a1 parser/scrub core (new module, no runs.py/live.py adapters) |
| L5 devtools/public | s2c probe CLI -> S8; final docs last. Deferred (public part, owner go needed): stranger-install harness, demo and rename tooling | agent_probe.py + its tests |

Real dependencies (critic swarm05 a): s2b needs s2a (and S5a's WARN contract); s3a needs s2a/s2b, not s2c; s3b needs s3a and s2b; s1a1 needs no S2/S3 (new gate runtimes join the home/lane qualification later); s1c1 needs s1b records and the s1a gate interface; s1c2 needs every gate's validity predicates; s1d needs the task/check/merge gates, not s1c2; s9a1 needs no s2c; s9b1 needs s2c usage, not V1..V5; S8 needs the probe CLI and the S4 log consumer; S4b needs S4, S2, S3 and the recovery qualification, and one resume admission covering the timer and `--wait` (budget otherwise bypassed); S5b needs the recovery qualification and all reference types. The full fixture boundary gate (journeys, last line): its core is an L2 slice; its UI wiring gets an explicit L3 ownership slot.
Re-gate before start: every brief is re-gated against the tag SHA with its slice split (critic swarm05 c), and the S2 qualification matrix: provider-free Linux (installed artifact, sandbox controls, tree/ref snapshots, binding/recovery tests; a 403 or an absent write is not sandbox evidence) plus real-provider macOS (architect new/resume with a hostile config, suppression controls, the probe baseline and check, usage and restart in the recorded home); Linux suppression without its own evidence stays WARN (critic swarm05b; update s2a :44, s2b :79-83, s2c :51/:65-69, AGENT_ENV_PLAN :129-137 at that re-gate).
S9b2 is deferred. S8 runs at every bump from now on, not last.
Each item gets its own task gate; sizes are estimated at task time.

Task files (devtools/zeroshot/tasks/, all task-gated GO by the sol critic on 2026-10-19): S4 run-failure-cause; S5a disk-guard; S2 s2a/s2b/s2c; S3 s3a/s3b; S1a s1a1-task-gate (s1a2 deferred); S1b s1b-checks (S6 part deferred to 0.5.x); S1c s1c1-merge-gate (slices s1c1a..s1c1d2; release slices s1c1e1/s1c1e2 deferred to 0.5.x, critic gate22), s1c2-status-truth; S1d s1d-preset-2; S9 s9a1/s9b1 (s9b1 needs a re-gate: its base names the superseded s9a2); the S9 card flow follows devtools/zeroshot/tasks/s9-roadmap.md V1..V5, each step gated before its run (s9a2a/s9a2b/s9a3 drafts: critic s9a2-split-gate BLOCK, folded into the V steps); S4b s4b-auto-resume; S5b s5b-workspace-cleanup; S8 s8-bump-qual. The devtools reviewer scratch lifecycle (`/tmp/zs-agent-*`, preamble.md) is a separate orchestrator task outside S5b.

## Release journeys (0.5 gate)

- Restart and recovery of a run (including a gateway lane) with no manual env.
- A provider failure stops with its cause and is not charged again by default.
- Cleanup keeps the candidate and every referenced dir.
- Under `/2`, a merge needs a current qualification and an accepted merge-critic verdict, or a recorded owner override; the same cycle completes in plain and TUI. A failed check is never reported as passed (flake diagnosis moved to 0.5.x, critic gate22).
- `/1` is unchanged; `/2` only on the owner's accept.
- A fresh install starts agents in the zplan home with the profile (AGENT_ENV_PLAN acceptance).
- Terminal attempt selection and the five run-visibility answers survive reload; a budget refusal causes no submission and never stops an active run.
- Full boundary qualification (deferred from the 0.4.0 class repair, critic rel04-pushback): a mandatory session scope object for fixture/native composition, an all-keys fixture effect spy with a source-derived effect-sink inventory, and start/merge process admission inside `Runs` (S1a/S1c).

## Open items moved from STATE (2026-10-20)

- After the tag: readiness.socket ~/.zp hint, setup disk-space hint, stale build/ leak in the wheel build, wheel
  non-reproducibility, /tmp/zs-agent-* lifecycle (devtools).
- Test flakes: Linux test_tui_chat test_a3_a (once on 1386982, cause unproven); Linux test_tui_milestones test_b5 (once on
  bc64c19, deadline missed by 16 ms); macOS real_pty Ctrl-C under a `&` launch (SIGINT ignored; fix: reset SIGINT in its
  preexec); macOS test_a4_a_slow_setup under full load. Repair task: devtools/zeroshot/tasks/test-timing-flakes.md.
- commands.py English doctor help still says exit 0 only when everything is ready (s5a1 follow-up).
- engine.py OBSERVED_RUNS grows per observed run for the process lifetime (bound it later).
- TUI hand-over uses Textual's private `App._context()` (app.py:962), recheck at any Textual bump; UI handler exceptions
  are swallowed (S9b2); failure classification relies on provider errors reaching stderr (unchecked on real output).
- Linux real-provider checks are impossible from the test host (403); provider-free sandbox check substitutes.
- Owner 2026-10-19: report a run to its owner only at its terminal state; fold into S9.
- Before v0.5.0: s2a parent A-8 installed check (architect turns under a danger-full-access home refuse file writes and
  git mutations), with the installed macOS DeepSeek journey.
- After 0.5 (owner 2026-10-20): move development to the owner's VPS in Sweden (Linux; Codex reachable); measure repeated
  reviewer defect classes and, if frequent, a short "known defect classes" file via preamble.md.

## Review-loop candidates (2026-10-20, from the zplan build itself)
Evidence: 817 reviewer findings in local run stores; 14% hit hostile-input keywords, 16% receipts/bookkeeping, concentrated in
s1b1b1-check-guard and s1a1b1-gate-record (7-9 rounds). Enter 0.5 only if the dogfood session shows them blocking (scope rule).
- Brief lint before a run: size, criterion count, unconditional words without an input list.
- Finding severity: blocking only with a cited criterion on a realistic path; the rest as a "spec gaps" list for the user.
- Round trend in the run view: regressions vs new edge cases per round, with a "merge + Later" suggestion.
- Requirement origin (incident / invariant / hypothesis) visible while planning.

## Dogfood blockers (2026-10-21, installed main 6e02122, macOS)
Owner acceptance bar for 0.5: a working planning chat. Found before the first real plan; evidence ~/zs-pause/dogfood/.
| # | Blocker | Where | Fix |
|---|---|---|---|
| D1 | Shipped code reviewer rejects on any finding: open checklist (correctness, tests, scope, style), no realistic-path or severity limit; the worker must "repair every finding" | terminal_planner/milestone.py:417-432 | reject only a broken check/task on a realistic path; nits non-blocking (same rule as devtools/zeroshot/preamble.md:12) |
| D2 | Task review loop is hardcoded to 4 iterations and ignores the profile's task_rounds | milestone.py:21 | derive from the frozen task_rounds |
| D3 | Plan critic: "reject … when incomplete" with no bar; findings may add scope with no origin | engine.py:666-676 | each rejecting finding cites the goal, a requirement or an invariant; no new scope without one |
| D4 | Full-screen start: focus is not in the chat input; typed text triggers hotkeys | TUI | focus the chat input on start |
| D5 | Fresh install: doctor BLOCKED, zplan's CODEX_HOME has no login although ~/.codex has one | setup/doctor | decided 2026-10-21 (owner, critic d5-login-reuse GO C): no reuse (refresh tokens rotate; a copied or linked login can log out the owner's Codex); zplan's own login as one guided step (task d5-login-guide). Option D (~/.codex as zplan's home, profile as -c overrides) after 0.5 |
| D6 | This repo's profile runs the plan critic at xhigh | zplan.process.json | high (preset default) |
Later (not blocking 0.5): DeepSeek worker is not configurable (runtimes hardcode harness codex/provider openai; engine.py:799,906,943, milestone.py:506); architect reply language hardcoded Russian (architect.py:157-176); chat panel 62 of 160 columns.

## Owner test of 0.5.1 (2026-10-22, installed app/0.5.1, macOS)
Recorded only; no fix started. Screenshot: owner's chat, architect tab.
| # | Problem | Evidence | Fix candidate |
|---|---|---|---|
| T1 | `/new` is not a command: it is sent to the architect as a message and answered ("Готов к новой теме"); the thread is not reset. Only Ctrl+R starts a new dialog | screenshot; no slash handling in terminal_planner/tui/chat.py | treat `/new` (and `/clear`) as Ctrl+R; any other `/word` -> local hint, not sent |
| T2 | The architect continues a session created 2026-10-20 (dev build) that has no `codex_home`; it is read as pre-0.5 and runs in the owner's `~/.codex` (header "CODEX_HOME ~/.codex"), i.e. with the owner's memories/plugins/MCP, not zplan's clean home | architect/<key>/session.json: no codex_home, thread set; architect.py:706-716, setup.py:218 | on the first turn after upgrade, start a fresh thread in zplan's home (or ask once) instead of silently continuing in ~/.codex; workaround now: Ctrl+R |
| T3 | The header block shows raw diagnostics (provider, CODEX_HOME, token count); the transcript is bottom-aligned under a large empty area | screenshot | decide with the owner what the header shows |
| T4 | STATE.md line 4 is stale ("Installed … main 55f5c4f … reports 0.3.1"); the architect quoted it as the current next step | STATE.md:4 | orchestrator updates STATE (installed app/0.5.1) |
| T5 | Key-hint line is cut at the window edge ("[f1] клавиши" clipped) | screenshot | minor |

### Owner verdict on the chat UI (2026-10-22): "UI/UX is unusable"
| # | Problem (owner's words, summarized) |
|---|---|
| U1 | Ctrl+R does not clear the screen: the old transcript stays and one line "new session" is appended; a new dialog must look new (empty transcript) |
| U2 | No visual difference between the owner's messages and the replies: same font, same colour, only a "ты:/арх:" prefix; needs distinct blocks (colour/indent/separator) |
| U3 | Status (model, provider, CODEX_HOME, tokens) lies on top as plain text in the same font as the dialog; status belongs in a compact, styled status line, not in the content |
| U4 | Key hints are always on screen; they should be hidden (F1 / on demand), not a permanent bar |
| U5 | Overall: no visual hierarchy, the screen reads as one undifferentiated mass of monospace text; reference bar: Codex/Claude Code chat |
| U6 | Speaker labels "ты:" / "арх:" are cryptic; the owner does not know what "арх" (architect) is or why the chat partner is called that. Role names must be plain or absent (style distinguishes speakers, U2) |
| U7 | The agent's internal steps (commands it runs, file reads, numbered items) are shown in the chat; the owner does not want them. Show the answer; steps at most as one collapsible "working…" line |
| U8 | Numbers next to replies/steps mean nothing to the owner (source to confirm from a screenshot) |
| U9 | Plan screen ("План r1 · планировщик работает", goal "создать минимальный план"): the owner cannot tell what mode this is or what is happening. Jargon (r1, планировщик, событие, проверено), the same fact repeated in three places (header, body, bottom "Планировщик" box), 95% empty screen, no answer to "what will I get, how long, what do I do next". Also unclear to the owner how chat and plan relate (how they got here) |
| U10 | `[e] журнал` opens the raw engine log: one JSON object per line (subscriptionId, runId, cursor, timestamps, execution ids) with whole file bodies the planner read (preamble.md, STATE.md) inlined as escaped text. Unreadable for a person; a debug dump presented as a user feature |
| U11 | Path to the plan screen: Tab -> «План» -> plan button -> typed two lines -> the planner started at once. Nothing said what "plan" means, what it costs/takes, or that typing there launches a planner run; the two lines became the plan goal |
| U12 | No way to stop a running planner from the TUI or the CLI (no key, no command); the orchestrator had to `zeroshot force-stop` run 01a164b0 for the owner (224k input tokens spent on a two-line goal) |
| U13 | Hotkeys are Latin letters only; with the Russian layout active they do nothing, the owner must switch layout for every key. Keys must work by physical key (е/e, ш/i, ч/x…) or be layout-free |
| U14 | Plan screen shows the plan/critic loop as an unexplained repeating list ("Проверяю, что план покрывает цель… / Уточняю план по замечаниям…" ×2), the same status twice, "Проект: ИЗМЕНИЛСЯ — требуется доработка плана" (caused by an unrelated commit to main during the run) and a "Для диагностики" block with run ids, env vars and full binary paths. The owner cannot tell what is being refined, why, or whether it will ever end |
| U15 | The owner does not understand the key list itself ([e] журнал, [i] подробнее, [w] наблюдать, [g], [x]…): names are internal, actions unexplained |
| U16 | Back from the plan screen the layout changes: a right side panel (Сейчас/План/Журнал) appears and duplicates the planner status lines, which are also dumped into the top of the chat transcript, above the session header (model/provider/CODEX_HOME/turns/tokens). The owner reads it as "a separate mode appeared" |
| U17 | The owner believed leaving the plan screen stopped the planner. It did not: the orchestrator force-stopped it; the "Планирование остановилось" line gives no cause, so any stop looks like the owner's fault |
| U8 source | "ответ 5 · арх · черновик цели" — architect replies that carry a goal draft are numbered "ответ N" |
| U18 | Bottom key bar on the chat screen has 11 entries ([p] план, [c] черновик цели, [r] обновить, …); the architect's own reply tells the owner to press "Tab → c" then "Ctrl+G" — a hidden multi-key ritual to turn a chat suggestion into a plan |
