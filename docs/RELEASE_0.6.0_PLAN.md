# Release 0.6.0 plan: the architect leads

Owner 2026-10-24: the architect does what the human-side orchestrator does today (plan, briefs, preflight, runs,
verdicts, merges, project state across session resets); engine changes allowed, none needed in 0.6.0; the public
release waits for this. Design and decisions: docs/ARCHITECT_DESIGN.md (r2, critic architect-design GO WITH
CHANGES, 12 findings applied). Supersedes the "planning depth" plan (private archive, planning-depth plan:
p1a, p3a, p2a, p1b merged; p2b and p3b fold into A10).

## Before 0.6.0 (0.5.2 close-out)
- i11 `/run` (running): the manual start path; `auto` reuses the same `Controller.start_run`.
- Linux repair: test_tui_draft_card test_a1_two_open_cards_stay_fully_drawn fails 3/3 on Linux at 120x40 (plan card
  above the draft card), passes on the Mac (also with TZ=UTC and serial unittest); baseline on f4e033c.
- Tag v0.5.2 privately on the merge after both, with full Mac + full Linux green; no owner walk (owner 2026-10-24:
  the owner looks at the architect instead). Deferred: D1/D5 walk, gallery fixture, doc drift, public export.

## Slices: two lanes (owner 2026-10-24: parallel and faster, at most two worker groups)
Done: A-1 (Zeroshot 10.16.0, c9a0b9c), A1 (preset zplan.default/2 with autonomy, 92d5082), A0 (MCP works, fallback
not needed; docs/spikes/A0_ARCHITECT_TOOLS.md). Critic plan-06-lanes GO WITH CHANGES (7 findings, all applied).
Each slice is one run; a larger one splits when its brief is written. Every brief passes the foreman checks of
ARCHITECT_DESIGN.md section 6 by hand until A4a.

Lanes own files, so two runs never share a write-set (ORCHESTRATOR.md:59: one owner per shared file):
- **Lane E (engine side)** owns authority.py, milestone.py, planning.py, engine.py, runs.py, delivery.py,
  zplan.process.json and their tests.
- **Lane T (architect side)** owns architect.py, process.py, tui/* (controller.py, app.py, slash.py, ...) and their
  tests. Lane E exposes functions; lane T wires them into the Controller and the screen.
- A new module belongs to the lane that creates it. A lane with nothing ready may take a slice of the other lane's
  files only while no run of that lane touches them (record it in STATE).
- At most two runs at a time, one per lane; Linux host 1 for lane E, host 2 for lane T (one suite per host).
  Merges are serial through the gate (ORCHESTRATOR.md step 3): main is merged into the branch before the gate.

| Step | Lane E | Lane T | Waits for |
|---|---|---|---|
| 1 | A2a plan tasks carry a brief (write_set, criteria+examples, non_goals, risk, dod), old records unchanged, brief to the worker, planner/verifier prompts | A3 read functions (new module project_read.py): project boundary, credential exclusion, scrub | — |
| 2 | A2b plan and brief edits as new revisions through the planning API, with the independent scope check (today only feedback -> planner, planning.py:367; design 5, 15) | A1b preset data: risk rules (paths -> tier) and critic triggers (process.py:41; design 10.3) | A2b: A2a |
| 3 | A4a foreman (new module): F3, F5, named files exist, strings located; failed check -> finding | A3b tools transport: zplan MCP stdio server + read tools live in the architect (the Controller socket comes with A5t's mutation tools; reads need no Controller) (architect.py:105, :110; A0 flags) | A4a: A2a |
| 3c | — | A3c the architect sees no MCP server but zplan's (security fix found live 2026-10-25; before A6a) | — |
| 4 | A5e lifecycle: milestone amendment (new attempt with a corrected brief), resume of an unchanged task after an owner stop, attempts bound to their milestone snapshot (design 5) | A6a journal (new module): Controller hooks for actions, engine history via `zeroshot ui` (A0), start/end/duration stamped on receipt, learning records (stop cause, brief defect, fix) | — |
| 5 | A7 gatekeeper (design 10): pinned candidate, project checks, risk tier from A1b, critic triggers, merge `--no-ff`, cleanup, `MERGE_HEAD` refusal; zplan.process.json -> `/2` with zplan's own checks (Mac full, export check, Linux for platform diffs) | A5t mutation tools: start, stop, resume, re-brief, plan edit, merge queue; autonomy gate in the Controller. Automatic actions stay off until A4b and A7 are merged | A7: A1b; A5t: A2b, A3b, A4a, A5e |
| 6 | A4b preflight verifier node + `conflict` label -> `fail("conflict")` in milestone_graph (milestone.py:303) | A6b event feed: pending/handled mark separate from the engine cursor, catch-up turn before new actions, wake-ups, stuck rules, unavailable-architect queue (design 4.2) | A6b: A5t, A6a |
| 7 | A9 parallel core: per-attempt reconcile/observe and projections, single-writer rule removed (runs.py:658, :1175; delivery.py:401; authority.py:702), reservations, integration slot | A8 `.zplan/STATE.md`, rot signal, `/new` with warm-up; first slice built through zplan itself (bootstrap after A4b, A6b, A7) | A9: A7; A8: A6b |
| 8 | bug-hunt defects / Later items | A9t admission in the Controller: N runs, disjoint write-sets, provider pause (`Snapshot.busy` controller.py:106) | A9t: A9, A6b |
| 9 | — | A10 screen: bundle view, multi-run scheme, history pane with durations (absorbs p2b, p3b); chat-first input, `/stop` `/new` esc ←/→ kept | A10: A6a, A9t |

Lane order as run (2026-10-25, owner: parallel, at most two worker groups; lanes own disjoint files): lane T A6a -> A7a (gate core: candidate, checks, ff landing) -> A7c (cleanup after an integrated merge) -> A7b (critic triggers) -> A9; lane E A2b -> A4b -> A5e -> A5t -> A6b. A5e waits for A7a (both write runs.py); A5e, A7c and A7b's wiring all write delivery.py: they run one after another (critic a7c-design2). As run: A7b split into a core (merge_critic.py, engine.py, authority.py; critic a7b-design) that took lane E's free slot while A7c held delivery.py, and A7b2 wiring (runs.py, delivery.py) after A5e. A5t split (critic a5t-design): A5t1 (bridge.py, autonomy.py, architect tools, tui/controller.py; start stays "ask" until A7 is merged) took the slot freed by A7b core; A5t2 (plan edit/approve, merge, resume, re-brief) after A5e and A7b2. zplan.process.json -> `/2` with gates.merge required and zplan's checks moves to after a candidate that reads `/2` is installed and before dogfood D-A (installed v0.5.2 refuses the `/2` preset, process.py:150 at v0.5.2). A5e defers resume after an owner stop to Later (native recoverability of a force-stopped run unmeasured).

Risk tiers: high = A2a, A2b, A3, A3b, A5e, A5t, A7, A9, A9t (Linux + critic where ORCHESTRATOR.md triggers);
A4b (native graph contract) and A6a (engine history reader, a child process) take Linux + driver_qual at merge
(design 7); medium = A1b, A4a, A6b, A8, A10. D-A possible after step 6; D-C after A4b; D-D after
A8; D-B after A9t.

## Scope cut (owner 2026-10-25)
Remaining for 0.6.0: A9t, then A6b2b (feed wiring in the app/Controller) and A8. Moved to 0.6.1: A10 (screen) and
A6b3 (hung-turn cancel, backoff, «архитектор недоступен», stuck rules); A6b2a already holds event checks after a
failure until the owner's next turn, so no retry loop ships. Dogfood D-A..D-D is replaced by the owner's own test
of the candidate (a clone or `supervised` first), preceded by the orchestrator's short smoke (sandbox install from
the checkout, one trivial slice).

## K1 — slash-only input (owner 2026-10-25)
Owner: no single-letter keys (nor `?`); arrows, Enter, Esc, Tab, PgUp/PgDn, Ctrl+C/Ctrl+Q stay; every action is a
`/` command in the chat. Supersedes the single-letter keys of docs/TERMINAL_UX_BRIEF.md. Measured 2026-10-25: about
70 letter bindings on 8 screens (tui/app.py:551-558, screens.py:19/136/281, modals.py:37-295), 121 catalog.py key
entries (key bars, docs/REFERENCE.md), letter hints in tui/ and setup/delivery/planning, 284 letter presses in 19
test files.

Critic k1-design 2026-10-25: GO WITH CHANGES (10 findings, applied below).

Main screen (the plan panel's letters go; the hint «Дальше:» names the command):
| Key | Becomes |
|---|---|
| g, x, s, ? | `/run`, `/stop`, `/setup`, `/help` (exist) |
| p | `/view`, new: opens the plan screen (`/approve` stays a decision) |
| o, w | `/attempt`, new: opens the selected milestone's attempt (`action_open_milestone`, any state, not only `merge`) and resumes an interrupted observation |
| i | `/details` typed: with no error card, the plan record (`action_milestone_details`); card routing unchanged |
| e | `/log`, new: the last lines of the run's log, once |
| t | `/answer`, new: opens the newest answer draft of the selected milestone |
| n, c | `/plan` (below) |
| r | dropped: refresh is automatic (tui/app.py:1804) |
| Ctrl+S, Ctrl+R, F1, `н` | dropped: `/setup`, `/new`, `/help`, Enter cover them; Ctrl+Q and Ctrl+C stay |

`/plan` contract: with a draft card open -> the card's goal (today; a refusal writes nothing, RC6). Otherwise with
text -> that goal: a new revision and its submission (the goal form's path, form removed). Otherwise on a stale
unsent plan -> `renew_plan` then `run_plan` (the old `n`, then the send). Otherwise a note naming `/plan <goal>`.
The goal form (GoalScreen, Ctrl+G) is removed with its openers.

Screens and modals stay (plan, settings, run result, bootstrap, confirm, note, question note, language, help, text;
openers in tui/app.py:2061-2584, card_host.py:759); their letters become buttons: Tab and Left/Right (when a button
has focus) move, Enter presses, Esc is back / no / close. Help and Text: Esc only. Note: Tab to Submit, Enter. Kept:
the bootstrap `present` guard (modals.py:110) and the confirmations of merge, reject and stop. Moving them to chat
cards -> 0.6.1.

Slices, one lane, in order, after RC4 (all write tui/app.py and shared tests): K1a main screen and new commands;
K1b `/plan` + goal form removal; K1c screens and modals as buttons, split by measure (2026-10-25: 39 bindings,
~280 bar-text assertions in ~30 test files): K1c1 modals (confirm, bootstrap, help, text, note) + the shared button
bar and its CSS, K1c2 plan and settings screens, K1c3 run screen; K1d the remaining hint texts (setup.py,
delivery.py, planning.py where the TUI shows them) and docs/USER_FLOW.md, docs/TERMINAL_UX_BRIEF.md. Each slice
updates catalog.py + docs/REFERENCE.md for its surface. Non-goal: the plain CLI's letter menus (test_reference.py:246).
Then the re-smoke: observation resume, stale -> renew -> submit, first start, confirmations.

## Release gate
Superseded in part by the scope cut above. Was: ARCHITECT_DESIGN.md section 12 dogfood D-A..D-D on zplan's own
repository through zplan in `auto`. Now: orchestrator smoke -> owner test -> repairs -> gate refusals on fixtures;
full Mac + full Linux, native/installed on Linux; fresh release critic.

## A11 — shipped architect method (owner 2026-10-25)
Owner: the method the orchestrator follows ships as zplan's default, generic architect method; settings that tune
it come in later releases. Now: terminal_planner/resources/architect_method.md, carried by the architect's first
turn (task a11-architect-method, lane T, disjoint from K1). Critic a11-scope: GO WITH CHANGES (STATE sections of the
product, the STATE write named in the tool rules, resource committed before launch; all applied). Owner 2026-10-25: the
method is never locked in the product; customizing it is editing a plain file, no commands. 0.6.0 adds A12: a
project file, when present, replaces the shipped method. Later: profile keys for the method; devtools/zeroshot/ORCHESTRATOR.md becomes zplan's own overlay over it.
