# zplan 0.4 — full-screen TUI with an architect chat

Owner request (2026-10-14): `cd project && zplan` opens a full-screen ASCII interface like opencode: big logo, and from
there manage everything — setup, login, doctor, roles, plan, milestones with live progress — and talk to the zplan
architect. Owner choices: one end-to-end architect chat (advisory; start/stop/merge stay owner keys); layout = chat on
the left, plan/milestones panel on the right, input line and key bar at the bottom.

```
███████╗██████╗ ██╗      █████╗ ███╗   ██╗
╚══███╔╝██╔══██╗██║     ██╔══██╗████╗  ██║
  ███╔╝ ██████╔╝██║     ███████║██╔██╗ ██║
 ███╔╝  ██╔═══╝ ██║     ██╔══██║██║╚██╗██║
███████╗██║     ███████╗██║  ██║██║ ╚████║
╚══════╝╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝
 demoapp · main · ✓ готов
┌ Архитектор ────────────────┬ План r2 ──────────┐
│ ты: добавь счётчик очков   │ ✓ M1 Счёт   влит  │
│ арх: предлагаю 2 этапа...  │ ▶ M2 UI     3/5   │
│                            │   T3 · ревью      │
│                            │ · M3 Тесты  ждёт  │
├────────────────────────────┴───────────────────┤
│ > сообщение архитектору_                       │
└ [tab] панель [g] запуск [m] влить [s] настр [?]┘
```

## Decisions (critic tui1: GO WITH CHANGES, applied)
- Framework: Textual (MIT, pure Python). 0.4 requires Python >=3.11 (Textual's current dependency closure needs
  >=3.10/3.11); install.py re-executes itself with a found python3.13/3.12/3.11 when started by an older python3.
  Offline installs use the wheelhouse (`ZPLAN_TEST_WHEELHOUSE`); an installed offline launch is a gate from U1a on.
- Presentation layer only. Extract the minimal planning action service shared by plain and TUI; widgets never
  duplicate submission, restart or approval rules. One controller worker owns Authority/MilestoneRuns, serializes
  actions and poll slices, and hands immutable snapshots to the UI; blocking Git/CLI/setup calls never run on the UI
  event loop. Refresh is read-only (overview/status); only observation calls the mutating poll().
- Plain mode stays: `zplan --plain`, automatically when stdin/stdout is not a TTY, and `zplan status` (no escape codes).
- Keys: while the chat input has focus, letters are text; owner actions use panel focus or modifiers. Cancelling an
  architect turn and stopping a milestone are different commands. Sizes 80x24 and 120x40, resize, scroll, focus and
  terminal restoration after login/exit are tested; Pilot tests do not replace a real PTY smoke.
- Architect = conversation through the exact pinned Codex executable: initial `codex exec` with `-s read-only -C
  <project>`, then `exec resume <stored thread id>` with cwd=project and explicit `-c sandbox_mode="read-only" -c
  approval_policy="never"`; never `--last`, `--ephemeral` or any bypass; write-capable MCP tools disabled. Effective
  CODEX_HOME/provider/model from the U0 resolver and shown in the UI. New role `architect` (default gpt-6.1-sol/high).
  Thread id persisted immediately; JSONL events (thread.started, item.*, turn.completed/failed/error) displayed as
  messages/progress with capped buffers, unknown/malformed events tolerated; cancel kills only the architect process
  group; no automatic retry; one turn per owner message, zero inference on refresh; session rollover/reset and usage
  counters. Transcript + session metadata outside the checkout, separate from planning.json, atomic and private.
- The architect is advisory: a goal draft opens an editable form and goes through planner -> verifier -> approval; an
  answer draft goes through the existing answer path (a new attempt). On send, project/revision/milestone/attempt are
  re-checked (stale drafts rejected). The architect never writes proposal/approval/run state.

## Runs (each one Zeroshot dev run; orchestrator: review -> merge -> Linux suite + driver_qual -> critic -> manual check)
- U0 first-run UX fixes: done 2026-10-14.
- U1a TUI shell + foundation: Python >=3.11 + install re-exec, Textual app, logo, header (project/branch/readiness),
  plan/milestones panel (read-only), chat placeholder, key bar, Settings (readiness, setup with live log, login via
  suspended terminal, re-check, roles), serialized controller worker, plain fallback. AC: responsive with a slow
  fixture operation, no actions on refresh, offline installed launch, piped/plain/status without escape codes.
  Manual: installed TUI on Mac, resize/focus, setup log, suspend/login/return; PTY smoke on Linux.
- D1 Public reference and help, after U1a merges (owner: no public show until every command, state and error is named;
  critic z1: GO WITH CHANGES, applied). Share parser metadata for command/flag help; per-command examples and
  interactive key help. A small public contract catalog: persisted plan/run/delivery statuses, milestone view states,
  screen action IDs and stable error-family IDs with meaning, cause and remedy. Arbitrary model/provider diagnostics
  are bounded details, not catalog entries; documented unknown-error fallback. Lifecycle decisions stay in existing
  controllers. Reference tables in docs/REFERENCE.md generated from that metadata; interaction explanations and
  examples authored. AC: exact finite state/action/error-ID coverage, generated tables current, every help path works
  without tools/login/repo/inference; no tests comparing every localized literal. U1b/U2/U3b update their catalog
  entries, help and reference in the same run.
- U1b Planning flow in TUI: goal, readiness gate, planner progress, failure/restart, compact proposal,
  approve/revise/reject through the shared planning service. AC: U0 journeys in Pilot incl. stale baseline and unknown
  submission; plain and TUI use the same decisions. Manual: dirty->clean recovery, a real small README plan.
- U2 Milestone actions: start modal, live observe in the panel, stop, end-of-run modals (done/diff/merge,
  needs_owner accept/answer, blocked, failures, conflict, submission unknown), details. AC: P5 journeys + cancelled
  confirmations, lost stop, resume->export->merge, scope-change routing, stale modal rejection. Manual: detach/reopen
  across UIs, diff/merge, fixture conflict resolution, no double submission.
- Z1 Qualified toolchain and controlled upgrade (owner: don't depend on one Zeroshot version; critic z1 replaced a
  multi-version registry). One qualified default toolchain per zplan release; exact versions, platform checksums,
  Codex lockfile and restic pin centralized (today literals in engine.py:293, authority.py:408, setup.py:104,
  milestone.py:351). No multi-version registry, capability flags, auto-discovery or auto-cleanup. Never replace an
  installed bundle in place; candidate qualification uses a separate checkout and a short isolated native state root.
  Activation requires quiescence (no unknown/active intents, recoverable failures, unexported results, unfinished
  approved plans) or explicitly keeping the older app. Older app/checker/tool dirs and records preserved; SHA, graph
  digests and approval identities never rewritten; no cross-version resume promise (upstream guarantees versioned
  graph/protocol contracts only). Upgrade checklist/script: compare tagged CLI/schema/template contracts and verifier
  behavior; installed tests, planner qualification, all driver/adapter scenarios, architect gates when Codex changes;
  Mac real-provider smoke; zplan patch release. AC: candidate cannot touch production state; old bindings stay
  readable unchanged; incompatible actions give an actionable fallback; failed qualification leaves the default intact.
  Sequential (not parallel with U1b); before the public preview or when Zeroshot ships a release we want.
- P0 Public preview gate (critic show1: SHOW AFTER cleanup; TUI not required). Must fix: license + provenance and
  public repo scope (the private archive: prototype/, reference/, historical docs); new preview version/tag including U0, installable from
  the published tag (README must not need a private repo); readiness rejects layouts export refuses (submodules,
  nested Git, LFS/filters/encodings: export.py:59,96,102) before any model call; details screen drops stale claims
  after merge (cli.py:140,174) and leads with the real outcome (moved into U2); honest platform matrix (macOS arm64 real-provider,
  Linux x86_64 scripted); one correct upstream link (the-open-engine/zeroshot). Polish: full checks before approval,
  elapsed time/usage, UI language stated in README. The architect chat is not advertised until U3b ships.
  External review (owner-triggered `/code-review ultra`, 3 free runs): #1 before P0 on a branch based at v0.3.0 with
  product code only (terminal_planner/, tests/, install.py); #2 and #3 replaced by fresh critic reviews of the full diff (plan reset 2026-10-16 (owner; critic plan-reset GO WITH CHANGES); the owner
  runs no steps; release go: ORCHESTRATOR.md section Owner).
- U3a (done 2026-10-14) Architect adapter (no chat UI): pinned argv/env, session/transcript store, JSONL parsing, cancel, context
  builder, usage. AC: scripted-process tests initial/resume/reopen/failure/partial turn; no lifecycle actions.
  Orchestrator gate: real initial+resume turn and a forced write attempt on Mac and Linux proving the sandbox.
- U5 Live run visibility before dogfooding (owner 2026-10-15: develop zplan with zplan; make it obvious the system
  works; critic live-ux: GO WITH CHANGES, applied). Task devtools/zeroshot/tasks/live-ux.md: active roles, elapsed,
  last-event age and heartbeat from zplan's own clock; bounded per-attempt journal; on-demand `zeroshot logs` tail;
  pending states; a "Дальше:" line from END_ACTIONS; readiness named on home; key bar and text fixes from a pyte
  PTY walkthrough (devtools/ux_walkthrough.py). Runs after the review #1 fixes merge; then a real-provider dogfood
  walkthrough on a clone of this repo.
- G1a/G1b/G2/G3 Process profile (owner 2026-10-15: the orchestrator's process — rules, critic gates on plan/task/
  merge, qualification, truth — built into zplan, on by default; design docs/PROCESS_PROFILE.md, critic profile1 GO
  WITH CHANGES, applied). 0.4 order after the plan reset 2026-10-16 (owner; critic plan-reset GO WITH CHANGES): G1a, G1b, tc1012, critic accumulated-diff review (replaces
  owner review #2), U3b, orchestrator dogfood-polish on a clone, U4. G2/G3 and preset `/2` move to 0.5, planned from
  dogfood findings. Not in 0.4: task gate + amendment barrier inside a milestone (R3), merge/release gate (R4/R5),
  derived truth (R7); `/1` keeps task/merge `off`.
- U3b Chat UI + draft bridges (on top of the process service; shows gate discussions; transcript is not authority): message display, editable goal/answer drafts, stale-context handling, interrupt.
  AC: chat works during milestone polling; shortcuts safe while typing; drafts start nothing without an owner key.
  Manual: conversation before/after merge and app restart, goal/answer transfer, cancel a long turn.
- U4 Release 0.4.0: installed full journey, docs (README, USER_FLOW with TUI screens), package assets (CSS) in the wheel,
  upgrade 0.3 -> 0.4 (keep "0.3.0" in installer OWNED), orchestrator real-provider walkthrough on a clone of the
  owner's project before handing back.
