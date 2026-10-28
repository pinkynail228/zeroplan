# Architect as orchestrator: design (draft, 2026-10-24)

Status: draft r2 (critic architect-design: GO WITH CHANGES, 8 BLOCK + 4 NOTE, all accepted 2026-10-24; brief
and verdict in ~/zs-pause/critic/architect-design.*). Replaces the 0.6.0 scope once accepted. The public release waits for it
(owner 2026-10-24).

## 1. Why
Today the architect is an advisory, read-only chat (`terminal_planner/architect.py:1-5`, `mcp_servers={}` at :105,
:110). Everything that turns a wish into merged code is done by a human-side orchestrator session outside zplan:
plan, briefs, preflight, launch, watch, verdict handling, merge gate, cleanup, STATE. The owner's bar (seven
questions, 2026-10-24): zplan does all of that itself; the owner talks to the architect, sees the plan, the worker
graph, the history, and can reset a long architect session without losing the thread.

Measured cost of doing it by hand (CALIBRATION.md, 109 rows): 26 runs force-stopped or exhausted; 21 rows were brief
defects, 10 of them a write-set or data-reach miss that a mechanical check finds before launch (latest: p1b attempt
1, 2026-10-24, `card_kinds.py` missing). Median 2 review rounds, 36 runs needed 3 or more.

## 2. The seven requirements
| # | Requirement | Today | Target |
|---|---|---|---|
| Q1 | Plan by chatting with the architect | yes (goal draft -> planner) | unchanged, plus the architect edits the plan itself |
| Q2 | The architect runs the harness: briefs, workers, results | no | architect has tools: plan, brief, preflight, start, stop, read verdicts, merge |
| Q3 | Wishes become milestones and slices with good briefs | partly (planner makes tasks without write-set or DoD) | task = full brief: write-set, criteria with examples, non-goals, DoD |
| Q4 | See the bundle setup and where a run is in its graph | partly (live scheme, no setup view) | preset graph shown before start; live node, round, verdicts per run, several runs |
| Q5 | History with what was, what is, how long | partly (activity pane, no durations) | project journal: every step with start, end, duration |
| Q6 | Talk to the architect meanwhile | yes | unchanged; run events also arrive in the chat |
| Q7 | Session rot handled, self-documentation, reset with warm-up | no (Ctrl+R only) | project state file kept by the architect, rot signal, `/new` with a warm-up turn |

## 3. Roles (the default preset)
The roles, checks, thresholds and graph below are the **default preset**, stored as data. Later releases add
choosing and editing presets (owner 2026-10-24); now one preset, but no rule of it is hard-coded.

| Role | Who | Does | Never |
|---|---|---|---|
| Architect | long Codex session per project, with zplan tools | talks to the owner; writes and revises the plan and briefs; asks the foreman; starts, stops, re-briefs runs; reads verdicts; queues merges; keeps the project state file | edits code; pushes; publishes |
| Foreman | preflight: mechanical checks in zplan code + one agent check | before a run: write-set reach, contradictions, size, platform, open contracts; during: stuck and conflict detection | starts work itself |
| Worker, reviewers | the engine graph, unchanged roles | implement, review, repair in rounds | see other runs |
| Gatekeeper | zplan code, configured per project | integrate main, run the project's checks, classify risk, merge `--no-ff`, clean up | merge with a red check |
| Owner | the human | approves the plan; answers questions; merges or delegates merging by the autonomy level; push and publishing | — |

## 4. Architecture
```
owner <-> TUI chat <-> Architect (Codex session)
                         | tool calls (MCP stdio server "zplan-tools", or fenced blocks as fallback)
                         v
                    Controller (single worker; confirmation gates; autonomy policy)
              /           |               \                 \
         Planning    Foreman checks    Runs (N parallel)   Gatekeeper (merge queue)
                                           |
                                   Zeroshot engine: preset graph per run
                                           |
                          event feed -> journal -> architect wake-up turns + TUI
```
Decisions:
1. **Tools through our MCP server, fenced blocks as fallback.** The pinned Codex 0.162.1 has `mcp` and `-c
   mcp_servers.x...`; zplan bans MCP today on purpose. The server is a small stdio process of ours that calls the
   same Controller, so all gates stay in one place. It must reach the *live* TUI process (a local socket served by
   the running Controller): a second process cannot open the project's Authority, which is locked exclusively
   (`authority.py:381`). Unverified (slice A0 measures it end to end: Codex -> bridge -> Controller -> policy gate): tool calls under `exec`
   with `-s read-only` and `approval_policy=never`, under `exec resume`, and their shape in the `--json` stream.
   If A0 fails, the architect writes action blocks (`zplan-run`, `zplan-merge`, `zplan-state`, ...) parsed like
   today's `zplan-goal` (`architect.py:208-306`); actions then run only between turns.
   A0 result (2026-10-24, docs/spikes/A0_ARCHITECT_TOOLS.md): MCP works with
   `mcp_servers.<name>.default_tools_approval_mode="approve"`, also under `exec resume`; the fallback is not built.
2. **Event-driven architect.** A turn cannot wait hours. zplan watches every run (as `watch.sh` does for the
   orchestrator now) and, on a wake event (run finished, verdict, `conflict`, question, silence past the preset
   threshold, provider error), sends the architect a short turn: what happened plus a fresh snapshot. The owner's
   messages and these events share one queue; the owner's go first.
   - **Who watches (owner 2026-10-24):** the open zplan process. Runs live in the engine and continue when zplan is
     closed, but the architect reacts only while zplan runs; for `auto` overnight the owner keeps zplan open (e.g.
     in tmux). A headless `zplan serve` with the TUI as its client is later (the Authority lock, `authority.py:381`).
   - **Catch-up on open (critic architect-gaps B1):** the engine cursor (`observe`, `runs.py:914`) and the
     architect's processing are separate marks. Every observed event is stored as pending until an architect turn
     has handled it (invariant: an observed event is never lost before the architect reacts). On open: `reconcile`
     (`runs.py:847`) -> observe/history -> one catch-up turn with the pending events (what finished, verdicts, what
     waits on a decision) -> only then new actions; the owner sees the same summary in the chat.
   - **Stuck rules (preset thresholds; incident: i3-chat-inline 2026-10-24, 6 h, 7 rounds):** signals for a check,
     never an automatic stop: a worker round past 45 min without a review (look at what it spends the time on), a
     run past 2 h, and round 3 completed. Round 3 = the structural check of ORCHESTRATOR.md step 2 (critic B2): each
     finding rejected in two rounds is classified and recorded; a contradiction or open contract -> stop and
     re-brief; a real new defect -> repair goes on; only new edge cases without a violated criterion -> Later and
     the candidate goes to the gate. Liveness of the watcher alone is not a signal.
   - **Architect unavailable** (rate limit, provider error, hung turn): a hung turn is cancelled first (critic B3),
     events stay pending and are batched into the next turn; the turn is retried with backoff; after the preset limit the TUI shows «архитектор недоступен» and
     no new run is admitted (running runs continue); `/stop`, `/new`, esc work without the model (section 9); `/new` without the model skips the handoff and warms
     the new session from the stored snapshot, project STATE and journal (the model handoff stays A8).
3. **Autonomy policy in the preset**, enforced by the Controller, never by the prompt (owner 2026-10-24):
   - `auto` (default, in the spirit of an agent "auto mode"): the architect approves its own plan after the
     independent plan verifier passes, starts runs, re-briefs on conflict, and merges when every gate is green.
     It stops and asks only on a question it cannot answer from the project, a red gate after one repair, or a
     safety-net hit: a high risk tier goes to an independent critic agent first, and asks the owner only if the
     critic blocks.
   - `supervised`: the owner approves the plan; starts and merges as in `auto`; high risk asks the owner.
   - `manual`: every plan, start and merge asks the owner (today's behaviour).
   - Always the owner's, at every level: push, tags, publishing, deleting branches with unmerged work.
   The invariants "the human decides twice" and "zplan never merges on its own" (docs/product/BOUNDARY.md) become
   "zplan acts within the autonomy level the owner set; outward actions are always the owner's".
4. **Parallel runs** (after the single-run path works end to end). Not only the guards: every active attempt is
   reconciled and observed (today only the first, `runs.py:856`), delivery and snapshot projections become per
   attempt, admission uses the union write-set of each milestone, a reservation is held while a run's status is
   unknown, merges take one integration slot, rising provider errors pause admission (ORCHESTRATOR.md:28).
   Remove the single-writer rule (`runs.py:658`, `:1175`; `delivery.py:401`;
   `authority.py:702`; `Snapshot.busy` `controller.py:106`). Admission (preset): at most N runs (default 3),
   pairwise disjoint write-sets, dependencies merged, free disk. Merges stay serial through the merge queue.
5. **What the architect may read.** Read tools see only the selected project (and its worktrees), never
   credential files (`.env*`, keys, tokens, the private homes), and every text passes the existing scrub
   (`live.py:875`) before it reaches the architect, the journal or STATE.
6. **Project state file** in the project where zplan runs (owner 2026-10-24): `.zplan/STATE.md`, the directory
   zplan already reserves and keeps out of Git (`runs.py:82`, refused if tracked). At most 6 KB, sections fixed by
   the preset (Now, Next, Open, Decisions with dates). Written only through a tool (`state.update`), shown in the
   TUI. Worktrees of runs do not see it; the architect passes what a run needs in its brief.

## 5. Brief and plan
A milestone task today is `{id, title, checks[]}` (`authority.py:282`, `milestone.py:86`, `:125`). It becomes the
brief format we use now: `goal`, `why`, `reuse`, `write_set[]` (files), `criteria[{id, text, example}]` (at most 5),
`non_goals[]`, `risk`, `dod` (a test command). This is a plan schema version: stored plans migrate (old tasks read
as briefs with empty new fields), the brief is carried into the worker's input, and the planner prompt
(`engine.py:640-655`) and the verifier bar ask for the fields.

Editing: plans and briefs change only through the planning API as new revisions, never by writing files.
Re-brief while other milestones run: an attempt is bound to its milestone's approved snapshot, not to the whole
revision, so a corrected brief for one milestone does not invalidate the attempts of the others (today a new
revision is refused while a run is active, `authority.py:702`, and old attempts cannot finish after it,
`runs.py:1222`). A correction inside the approved scope (criteria, examples, write-set within the milestone) is a
milestone amendment; a change of scope needs a new approval (in `auto`: the plan verifier).

## 6. Foreman checks (before launch)
Ranked by failures they would have prevented (CALIBRATION.md):
| Check | Kind | Prevents |
|---|---|---|
| F1 write-set and data reach: every file, symbol and string a criterion reads is in the write-set or already reachable; tests that pin changed lists or strings are in the write-set | agent judgment, helped by cheap greps (named files exist, strings and symbols located); no dependency analyzer (import-graph selection was measured and rejected, ORCHESTRATOR.md:57) | 10 rows |
| F2 contradictions: a forbidden edit vs a required one; each example satisfies its criterion; joint example for criteria on one output | agent | 9 rows |
| F3 platform and environment: tests touching HOME/XDG, `/home`, interpreter version, Linux-only fixtures -> platform DoD | mechanical | 7 rows |
| F4 open contract: a criterion over an unbounded domain gets a fixed case list or is split | agent | 6 rows |
| F5 size and scope: one behavior, at most 5 criteria, brief within the cap, measured numbers | mechanical | 4 rows |
A failed check goes back to the architect with the finding; the run does not start. The agent part runs as the
first node of the milestone graph (section 7) or as a separate short Codex call, whichever A4 measures cheaper.

## 7. Engine
The engine already supports (no change): a custom graph per run (`zeroshot run --graph`, schema
`protocol/openengine-cluster/v1/graph.schema.json`), extra verdict labels, many parallel runs with idempotent
submission keys, `watch` with cursors, `force-stop`, `resume`. zplan already runs its own milestone graph, not
`software-change`, and its delivery contract matters: a success needs the output and a baseline-consistent manifest
with no open tasks (`runs.py:1117`, `:1126`). So the preset graph *extends the existing milestone graph* with a
`preflight` verifier at its head and a `conflict` label routed to `fail("conflict")`; the manifest and output stay
as they are. This turns today's `conflict:` text convention into an engine route.

No engine patch in 0.6.0 (owner 2026-10-24: minimum that works). What we would otherwise patch, and how we do
without it:
| Need | Engine today | 0.6.0 without a patch | Patch later, if ever |
|---|---|---|---|
| Live verdicts, rounds, active node per run | `watch` carries phase and active node only; the engine's history already records `node_completed` with the outcome (`upstream/zeroshot/src/native_v2_observability/history.rs:189`, `:222`) and serves it over HTTP/SSE (`profile_ui/runs.rs:644`) | first check whether that history projection is reachable from a terminal client (A0); else read the engine's local run store read-only, as `devtools/zeroshot/board.py:30-54` does today (node outcomes with the `verdict` signal); valid because zplan pins one engine version and its qualification covers the reader | node outcomes in the public `watch` status |
| Steer a running run | no input channel | three separate actions with a defined candidate: stop (confirmed, `stopped`, `runs.py:1096`; the worktree is kept), resume of the *unchanged* task (today only from `failed`, `runs.py:1172`, and native resume restarts the original graph, `upstream/docs/zeroshot-cli.md:1063`: resume after an owner stop is a lifecycle change in zplan), new attempt with the corrected brief on top of the kept candidate or from the base | — |
| Write-set as a boundary | none | foreman F1 before launch; reviewers check the diff against the write-set | per-node write scope |
| `conflict` stops the loop | verdict labels are free in a custom graph | preset graph via `--graph` with a `conflict` label and a `fail` route | — |

## 8. Session hygiene (Q7)
- Rot signal (preset thresholds): context tokens from the session usage (`session.json` `usage`), turns, age; the
  TUI shows «сессия длинная: /new» past the threshold.
- `/new` (replaces Ctrl+R as the visible command): asks the architect for a handoff (`state.update`), resets the
  thread, then sends a warm-up turn: preset rules, the project STATE file, plan snapshot, live runs, the last journal
  entries. The new session's first reply states what it is doing next; the owner sees it.
- The transcript stays; the journal (section 9) is the history, not the session.

## 9. Journal and screen (Q4, Q5)
- One journal per project: planning steps, runs (node, round, verdict), merges, owner decisions, architect actions,
  each with start, end and duration; source = engine events + Controller actions. It feeds the bottom history pane,
  the architect wake-ups and the warm-up.
- «Схема» before start shows the preset graph with roles and models (the bundle setup); during runs it shows each
  live run's node and round; a run list when several run.
- p2b (planner timers) and p3b (plan tree) fold into this.
- Input model (owner 2026-10-24): the chat with the architect is the interface; ←/→ switch the panes. Every
  decision can be answered in words; a card's buttons only answer the architect's question (supervised, manual).
  The pane letter keys go; once A5 lets the architect act, `/run`, `/approve` and the other action commands go too.
  Kept without the model, so a hung or rate-limited architect never blocks control: `/stop`, `/new`, esc, ←/→.

## 10. Merge gate (the gatekeeper)
Today `runs.py:1292` merges directly; "green" is tied to nothing. The gatekeeper:
1. pins the candidate identity: integrated commit SHA (main merged into the attempt branch and committed), base SHA,
   project config digest; any later change to the candidate voids the evidence and reruns the affected checks;
2. runs the project's required checks from the project config (the commands, their exit codes, the tested SHA are
   the evidence, stored in the journal); an empty or missing check list never allows an automatic merge;
3. classifies the risk tier (preset rules: paths guide, uncertainty raises the tier) and applies the critic
   triggers of today's process (ORCHESTRATOR.md:22: secrets, data loss, process killing, installer, toolchain,
   packaging, reviewer/architect disagreement): a fresh critic agent, BLOCK stops the merge;
4. merges `--no-ff` with the tier and the evidence in the message, then cleans up (worktree, branch, lock);
   a conflict aborts, records the files and goes back to the architect.

## 11. Slices (new 0.6.0 "the architect leads")
Order, splits (A2a/b, A3/b, A4a/b, A5e/t, A6a/b, A9/t, A1b) and the two lanes: docs/RELEASE_0.6.0_PLAN.md
(critic plan-06-lanes, 2026-10-24); the table below is the content summary.
Single-run vertical path first (A0-A7: one milestone planned, briefed, preflighted, run, reviewed and merged by the
architect), then session, parallel and screen. Each slice is one run with a brief; the larger ones are split when
their brief is written.
| Slice | Adds |
|---|---|
| A0 | spike, measured: Codex MCP under exec / resume / read-only -> stdio bridge -> socket of the live Controller -> policy gate; fallback blocks; reachability of the engine's history projection |
| A1 | preset as data: extend the frozen preset of `process.py:56` (generic preset vs zplan project config): roles, autonomy levels, thresholds, checks, critic triggers |
| A2 | plan schema with briefs: fields, migration of stored plans, the brief carried to the worker, planner/verifier prompts |
| A3 | read tools: project boundary, credential exclusion, scrub |
| A4 | foreman: cheap mechanical checks (F3, F5, named files) + preflight verifier and `conflict` route in the milestone graph (F1, F2, F4) |
| A5 | single-run actions: start, stop, resume unchanged, new attempt with a corrected brief (milestone amendment), autonomy gate |
| A6 | event feed: wake-up turns, catch-up turn on open, stuck rules, unavailable-architect queue (4.2), journal with durations |
| A7 | gatekeeper (section 10) |
| A8 | project STATE, rot signal, `/new` with warm-up |
| A9 | parallel runs: per-attempt reconcile and projections, admission, reservations, integration slot, provider pause |
| A10 | screen: bundle view, multi-run scheme, history pane with durations (absorbs p2b, p3b); chat-first input (section 9) |
p1b is merged (57c42a4). 0.5.2 is still tagged privately on the i11 merge.

## 12. Release gate (0.6.0)
Dogfood on zplan's own repository through zplan, not `devtools/zeroshot`, in `auto`:
- D-A one slice from a wish to a merge; D-B two parallel slices with disjoint write-sets, both merged;
- D-C a seeded brief defect: preflight or a reviewer `conflict` -> the architect re-briefs -> merged;
- D-D `/new` while a run is live: the fresh session states the plan and the live run correctly and continues.
Gate refusals (red check, empty check list, critic BLOCK, overlapping write-sets, credential read) are proven on
fixtures. The release qualification stays: full Mac and full Linux, native/installed on Linux (AGENTS.md), a fresh
release critic on the accumulated diff.

## 13. Owner decisions (2026-10-24)
1. Autonomy: three levels, `auto` default, `supervised`, `manual` (4.3).
2. Engine: no patch in 0.6.0; the run-store reader replaces E1 (section 7).
3. Project state: `.zplan/STATE.md` in the project (4.6).
4. Input: chat-first; pane letter keys and action commands go; `/stop`, `/new`, esc, ←/→ stay (section 9).
5. Watching: the open zplan process; `auto` overnight = zplan kept open (tmux); `zplan serve` later (4.2).

## 14. Risks
- Codex MCP under the read-only sandbox may not work (A0 decides; the fallback costs autonomy between turns).
- An autonomous merge with a weak gate lands bad code: the gate commands come from the project config, a red gate
  always stops, high risk goes to the critic agent.
- The run-store reader depends on engine internals: pinned version, a qualification test on the real store, and a
  fallback to `watch` phase-only display if the schema differs.
- Cost: an always-on architect plus wake-ups spends tokens; the preset caps wake-ups per hour and batches events.
- Parallel runs collide on shared files: admission by disjoint write-sets; the merge queue integrates main first.

## 15. Assignments from critic architect-gaps (2026-10-24, GO WITH CHANGES; ~/zs-pause/critic/architect-gaps.*)
| Item | Slice | Rule |
|---|---|---|
| Pending events + architect-handled mark, catch-up order | A6 | 4.2 (B1) |
| Plan/scope check (today's critic gate on plans) | A1 triggers, A2 runs it | may share the independent plan verifier; no critic per brief |
| Production MCP bridge / fallback routing | A3, A5 | A0 stays a spike; plan and brief edit operations in A2, tools wired after |
| Preset change | A1 | new preset `/2` with migration; `/1` kept, never edited |
| zplan's own project checks (Mac full, export check, Linux full for platform diffs) | A1 config, A7 runs | an `argv` may call a remote wrapper that serializes the Linux slot; no remote-executor framework |
| Merge with unknown result or `MERGE_HEAD` present | A7 | keep the candidate, refuse until the state is resolved; never mark `integrated` falsely (start already recovers, `runs.py:835`) |
| Learning loop (incident: repeated brief defects, p1b) | A6 records stop cause, brief defect, fix; A3 reads; A8 warm-up passes lessons | STATE updated on transitions, not only on `/new` |
| Bootstrap | after A6+A7 | A8 is the first slice built through zplan; parallel by the product after A9 |
| Red gate | A7 | stricter than today on purpose: a proven baseline failure does not allow an automatic merge |
Later: owner notification (bell/OS), `zplan serve`, a general crash-recovery framework, preset tuning from CALIBRATION.
