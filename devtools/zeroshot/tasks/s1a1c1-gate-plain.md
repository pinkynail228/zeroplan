s1a1c1-gate-plain — 0.5 item S1a, slice 3a of devtools/zeroshot/tasks/s1a1-task-gate.md (the parent; its R-5, R-6, A-1 and DoD texts apply verbatim where cited). Split of s1a1c-gate-ui.md by critic gate11 B (~/zs-pause/critic/gate11.out:9-13): the service wiring and the plain screens here, the TUI in s1a1c2-gate-tui.md. Lane L2. DeepSeek worker, sol reviewers.

Base: main after the s1a1b2-gate-barrier merge (recommended: also after s1b2a/s1b2b, see Parallelism). Lines below are cited at main 28c2c29 (product code identical to 299c377). They will move: s1a1b1/s1a1b2 add the gate store, `run_task_gate`/`rerun_task_gate`/`task_gates`, `override_task_gate`/`task_gate_state`, the barrier in `Runs.start`, the preview gate status and the five `task.gate_*` families. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged, s1a1b1-gate-record.md "Frozen contract" (record keys incl. `context`; `run_task_gate(milestone_id, context=None, progress=..., slice=None)`, `rerun_task_gate`, `task_gates`; the newest record for (revision, milestone) decides) and the s1a1b2 service API (`override_task_gate(gate_id, reason)`, `task_gate_state(milestone_id, context=None)`, the barrier in `Runs.start`, `admission` inherited by resume). If the merged code differs, stop and re-gate.
- No barrier, validity or override logic here; this slice decides only what is offered and in which order the existing service calls run.

Slices: s1a1c1 (this: Delivery offer/dispatch, the owner-context path, the plain gate screen, display, docs) → s1a1c2 (TUI). Integrated as a pair (R-9): c1 waits on an integration branch until c2 is on it; main never has one without the other.

Write-set (exclusive for this slice):
- delivery.py:
  - `g_id` :405-418, `home` :454-493 (ids :470-476), `pick` :502-541: under `gates.task == "required"`, a ready/failed/stopped g-item without a valid context-None gate gets no `[g]`; `home.gate` is offered instead; `pick("g")` and `pick("v")` on it return `Pick("gate", row)`. `failed_recoverable` (resume) and CHECK states are unchanged;
  - `Row` :155-165 gains `admitted: bool = True` (False only under required for a ready/failed/stopped row without a valid context-None gate), set in `row` :377; s1a1c2 reads it, so the TUI never re-derives the decision;
  - `state_text` :336-355 suffix and `next_step` :431-452 (ready :440-441, failed/stopped), only under required;
  - a pure `task_gate_lines(milestone_id, context=None)` from `task_gate_state`; the gate part of `details` :946-959;
  - the owner-context path: `owner_context(r, action, text="")` (R-3) and `admitted(milestone_id, context)` → True when the gate is off or `task_gate_state` is valid;
- runs.py: two pure builders, `answer_context(r, text)` and `proposal_context(r)` (candidate context or None), used by `answer` :1361-1367, `accept_proposal` :1388-1400 and, through `answer`, `retry` :1334-1340; contexts byte-identical to today;
- planning.py: `gate_lines` :541-560 generalised by subject ("плана"/"задач") with byte-identical plan output, or a sibling that reuses its round rendering;
- process.py: `describe` :768, :771-775 drop "(для следующих этапов)" for the task gate, rounds and rules only under required;
- catalog.py: screen `task_gate` (SCREENS :384-431); action `home.gate` (key `v`, home block :441-452); on `task_gate`: `run`/`rerun` (`g`), `continue` (`g`, only when bound to an action, R-3), `watch` (`w`), `override` (`o`), `details` (`i`), `back` (`q`); the remedies of `task.gate_missing`/`_running`/`_rejected`/`_failed`/`_stale` name `[v]` (s1a1b2 R-7 deferred this); no new family; docs/REFERENCE.md regenerated;
- cli.py: `dispatch` :301-322 (`v` and `Pick("gate")` → `gate_screen`); a `gate_screen(milestone_id, context=None, then=None)` mirroring `plan_screen` :502-516; an override prompt mirroring `override` :575-587; `new_attempt` :758-764, `answer` :776-784, `accept` :786-796 routed through R-3;
- docs/USER_FLOW.md ("Run a milestone" :362-386: the gate step, plain; "Details (`i`)" :413-429: one line), docs/PROCESS_PROFILE.md (:116, :141 mark G2-start built);
- new `tests/test_task_gate_ui.py`;
- the receipt `devtools/zeroshot/tasks/s1a1c1-gate-plain-receipt.md`.

Not touched: task_gate.py, engine.py, authority.py, setup.py, architect.py, commands.py (no subcommand, Q1), tui/*, existing tests and goldens (A-1 keeps them byte-identical), README.md, docs/INSTALLATION.md.

Audit (28c2c29):
- Home offer: `g_item` delivery.py:397-403 (CHECK, then failed_recoverable/failed/stopped, then ready); `g_id` :405-418 (home.check/resume/attempt/start); `home` adds it to ids :474-476; `pick` :502-541 (g → Pick start/resume/attempt/check). `next_step` alone does not remove `[g]` (gate11 B).
- Dispatch: cli.py:301-322 (start → `self.start`, attempt → `self.new_attempt`, resume, check); end-screen handlers :730-733.
- Owner actions: plain `new_attempt` cli.py:758-764 (optional note), `answer` :776-784, `accept` :786-796; Delivery :866-874.
- Contexts: `Runs.answer` runs.py:1361-1367 → `{"kind": "answer", "source": attempt, "text": text, "candidate": None}`; `retry` :1334-1340 sends a non-empty note through `answer`; `accept_proposal` :1388-1400: a candidate → `{"kind": "proposal", ..., "candidate": candidate}` then start, else a plan revision (no start, no gate).
- Plan-gate UI to mirror: `PLAN_ACTIONS`/`plan_screen` cli.py:502-516, `override` :575-587; catalog `plan.*` :470-487; `planning.gate_lines` :541-560.
- Display: `state_text` delivery.py:336-355, `next_step` :431-452, `details` :946-959, `zplan status` cli.py:822-830; `describe` process.py:767-775.
- Reference invariants: tests/test_reference.py :221, :231, :406, :414, :433, :455, :489, :522.

Rules:
- R-1 Scope (parent A-1): with preset `/1`, `gates.task: "off"`, or a fixture authority without a profile, every screen, key list, `Дальше:` line, `zplan status` output, describe text, REFERENCE row outside the new entries, owner-action prompt sequence and store byte is identical to base. `v` is not offered; the gate screen is unreachable.
- R-2 Home offer (gate11 B write-set): under required and an approved plan, for the g-item:
  - ready, failed, stopped without a valid context-None gate: `g_id` returns None and `home.gate` is offered; "Дальше: [v] проверить задачи <id> — до запуска" (ready) / "— до новой попытки" (failed, stopped); `pick("g")` returns `Pick("gate", row)`, so a typed `g` opens the gate screen and never starts;
  - the same with a valid gate for that context: `[g]` as today, i.e. `[g]` is offered again after a gate and starts the attempt (gate12 point 2); inside the gate screen `g` runs the check (R-4);
  - failed_recoverable: `[g] продолжить` as today; resume inherits `admission` (s1a1b2 R-5) and needs no new gate;
  - CHECK states and a busy slot: unchanged.
- R-3 Owner-context path (gate11 B dead end): every action that ends in `Runs.start` computes its context first, then the gate, then continues.
  - Context: answer → `answer_context(r, text)`; new attempt → None for an empty note, else `answer_context(r, note)`; accept → `proposal_context(r)` when a candidate exists; a non-candidate accept is a plan revision and is never gated; start → None.
  - `admitted(milestone, context)` true → the action runs as today. False → "Перед запуском нужна проверка задач на этом ответе." and `gate_screen(milestone, context, then=<the action>)`.
  - The gate screen bound to an action shows the context in one line ("Ответ: …" / "Предложение steward: …", bounded); `g` runs `run_task_gate(milestone, context)` (or `rerun_task_gate` after a terminal record); after accepted or overridden, `g` "продолжить: ответить/принять/новая попытка" calls the original Delivery action with the same text.
  - Leaving (`q`) stores no separate pending continuation (no draft, no queued action); the gate record itself keeps `context` (s1a1b1-gate-record.md:22), so the owner text stays in its evidence. Typing the identical text later is admitted by that record (the newest record decides; its artifact includes the context); a different text needs a new gate (`rerun_task_gate`).
  - A race refusal from the barrier prints the s1a1b2 text (naming `[v]`) and stays on the screen.
- R-4 Gate screen (parent R-5): reads `task_gate_state(milestone, context)` and offers only what the service allows: none or terminal and not valid → `g` "проверить задачи"/"проверить заново"; nonterminal → `w` наблюдать (no new dispatch); rejected and current → `o` "допустить вопреки проверке" (reason prompt; empty cancels); valid → `g` "запустить"/"продолжить"; any record → `i`; `q` back.
- R-5 Display (parent R-6): one text through Delivery for home, `zplan status` and the preview: suffix " · задачи: <state>" (не проверено / идёт / принято / отклонено / переопределено / устарело; native_failed/output_invalid → "отклонено (сбой проверки)") only on ready/failed/stopped rows, with context None; needs_owner rows have no suffix (their context exists only during R-3). Stale → "проверка устарела" and `[v]`. `describe` per the write-set.
- R-6 `[i]`: on the gate screen and in home `details`: verdict, rounds of limit, per-round findings and replies, config digest short id, override reason, "Раунды исчерпаны без согласия" when exhausted.
- R-7 Text: every new label/hint lives in the catalog; remedies name `[v]`; REFERENCE regenerated; USER_FLOW describes "plan approved → [v] проверка задач → [g] запуск" and the answer/accept path, plain.
- R-8 Fixtures: every literal home path in tests is under `/home/user/`.
- R-9 Pair integration (gate12:11, point 3): c1 alone would show `[v]` in the TUI home lines without a binding (tui/app.py:2409-2423 still derives keys from row states). So c1 is not merged to main by itself: its candidate is committed to an integration branch, s1a1c2 is built on that branch, and the pair is integrated together after both pass review and the full suite. `[v]` is never shown on main without a binding. Off (the default presets) is byte-identical either way.

Acceptance (tests/test_task_gate_ui.py; deterministic fixtures; FixtureEngine gate scenarios from s1a1b1; the plain-terminal fixture; no network). Each test names its entry point, oracle and control.
- A-1 Off: plain home, `cli.status`, `describe`, `preview`, answer/accept/new-attempt prompt sequences with `/1` and `gates.task: off`; byte-equal to base goldens; no `v`. Control: required shows `v`.
- A-2h Home offer: required; ready, failed, stopped without a gate → ids contain `home.gate`, not `home.start`/`home.attempt`; typed `g` → the gate screen, FixtureEngine start count 0. With an accepted gate → `[g]` as today. failed_recoverable → `home.resume` without a gate and resume succeeds (control).
- A-2u Happy path: `v` → `g` → accepted → home "[g] запустить M1" → start succeeds; one gate submission.
- A-3a Answer: needs_owner end screen → `[a]`/answer text → gate screen bound to the answer → `g` → accepted → `g` продолжить → a new attempt whose context equals `answer_context(r, text)` and whose `admission.gate` is that gate. Control: a second identical answer later is admitted without a new gate; a different text is not.
- A-3p Accept: a candidate proposal → the same path with `proposal_context`; a non-candidate accept → a plan revision, no gate screen.
- A-3n New attempt: a failed run with a note → gated on the answer context; an empty note → the context-None gate (R-2).
- A-4u Rejected and override: findings shown; empty reason cancels; invalid reason refused, store unchanged; valid → "переопределено" in home, preview, `zplan status`. Control: stale, running, native_failed offer no `o`.
- A-5u Stale: a commit on the destination after acceptance → "устарело"; `v` → `g` runs `rerun_task_gate` (two records, the first byte-identical).
- A-6 States: the six R-5 states render the same suffix in plain home and `cli.status` (table-driven); `[i]` text for an accepted 2-round and an exhausted gate; plan `gate_lines` byte-identical (control); `describe` under required drops the phrase on task lines only.
- A-7 Base failure: through `Delivery.home`, required, approved plan, ready M1 without a gate: assert `"home.start" not in home.ids` and `Дальше:` equals "[v] проверить задачи M1 — до запуска". On base (s1a1b2 merged) it fails by that named assertion. Run on base with a scratch commit; report named failures and skips separately.
- Mutations, each killed by a named test:
  - (a) `g_id` unchanged (`home.start` offered without a valid gate);
  - (b) `pick("g")` still returns `Pick("start")` without a gate;
  - (c) resume made to require a gate;
  - (d) `v` offered under off;
  - (e) answer starts without the R-3 check (the barrier refusal reaches the owner);
  - (f) the gate run with context None for an answer (the start stays refused);
  - (g) `o` offered on a stale or running gate;
  - (h) a remedy without `[v]`;
  - (i) plan `gate_lines` output changed;
  - (j) `answer_context` differs from today's literal (an existing runs test or A-3a fails).

Size: estimated 500-590 changed lines, receipt and REFERENCE excluded: product ~240 (delivery ~95, runs ~15, catalog ~35, planning ~15, process ~10, cli ~70), docs ~25, tests ~260. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1) (the cut, if the critic asks for one: R-3 into its own slice).

Parallelism: with s1a1b2 none (based on it). With s1b2a/s1b2b: both edit delivery `state_text`/`next_step`, cli wiring and catalog blocks; recommended serial (either order, gate11:18), else rebase keeping both suffixes and regenerate REFERENCE. With s1b1b1/s1b1b2/s1b1c: none (checks.py, check_guard.py only). With s2b2/s2b3: as s1a1c-gate-ui.md had it (catalog with s2b3 only, different block; USER_FLOW different sections; no shared test file).

Out of scope: TUI (s1a1c2); barrier, validity, override rules, families (s1a1b2); record and dispatch (s1a1b1); qualification (s1b2a/s1b2b); merge gate (S1c); preset `/2` (S1d).

Decisions (gate11:13-16): Q1 no subcommand: the parent's "plain and CLI command" reads as TUI + `zplan --plain`; Q2 one `v` for the task gate here and s1b2b's qualification (different screens, no clash by test_reference :455); Q3 a dedicated gate screen.

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_task_gate_ui tests.test_task_gate_barrier tests.test_task_gate_record tests.test_task_gate tests.test_plan_gate tests.test_plan_override tests.test_runs tests.test_process tests.test_ux tests.test_docs tests.test_toolchain tests.test_reference` passes. No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts (named failures and skips separately), the mutation table.
- Orchestrator: commit the reviewed candidate to the integration branch (R-9), not main; the full suite runs on the pair before integration (s1a1c2 DoD).
