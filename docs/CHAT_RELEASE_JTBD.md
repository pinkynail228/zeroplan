# Chat release: jobs, signals, slices

Status: accepted by the owner 2026-10-21 (slice order C0-C5). critic chat-release: GO WITH CHANGES (2026-10-21, ~/zs-pause/critic/chat-release.out); changes applied below: C0b moved after 0.5, C4 source = run history contract, C2 round source, C3 command wording, C4 shows findings of consecutive rounds.
Draft 2026-10-21 (owner request: "plan in the chat, see on the right what is happening, which stage of the
cycle, switch to the plan, a separate log section that shows nothing is stuck"). Input to the 0.5 plan; the owner
accepts the jobs and the slice order before work starts.

## Requirement (owner request, rewritten)

Ship the zplan version where the owner develops zplan from the chat:

- Every element of the screen serves a named job (JTBD below); anything without a job stays off the screen.
- Every on-screen answer comes from a native engine field (signal inventory below), never from a guess.
- "Stuck" is defined from measured silence in real runs, not from a fixed feeling-based timer.
- The design is checked on a replay of a real recorded run at the owner's terminal sizes before it is built out.
- Each job has an acceptance test: the owner, or a scripted snapshot, answers its question from the screen in ≤ 5 s.
- Stack: stay on Textual unless a job cannot be met with it (see "Ratatui").

## Jobs (JTBD)

| # | When … | I want … | so that … | Today |
|---|---|---|---|---|
| J1 | I have an idea for zplan | to talk it through with the architect and turn it into a goal and a plan in the same chat | I do not write briefs by hand | exists: chat, `zplan-goal` drafts, `c` → goal form → planner. Blocked by login (D5) and focus (D4) |
| J2 | a milestone runs | to see at a glance where it is in the cycle: worker → review (acceptance + code) → delivery, round N of max | I know whether to wait or step in | partial: active roles and "раунд N" journal lines; no "of max", no cycle strip |
| J3 | the screen has not changed for a while | proof that it is alive: time since the last event and what it is doing right now (last command) | I do not kill a healthy run or wait on a dead one | partial: "последнее событие X назад"; no current command, no live log |
| J4 | I check progress | to flip to the plan (done / running / next milestones) and back without losing the chat | I keep the big picture | exists: plan pane + `p`; the right pane mixes plan and live lines |
| J5 | a review round ends | the verdicts and a one-line reason per reviewer, and whether the findings repeat or are new edge cases | I spot a non-converging loop (whack-a-mole) early, not after hours | missing: verdicts and findings are in graph state, not read while running |
| J6 | a run fails or stops | the cause in words (limit, auth, network, review failed) and the next key | I recover without reading raw logs | exists after the end (end modal, `i`) |

Out of scope for this release: live token cost (the engine reports usage only at the end), several runs side by
side, editing the plan in the chat.

## Signal inventory (engine field → zplan)

| Signal | Engine source | zplan today | Needed for |
|---|---|---|---|
| active node (stage) | watch envelope `status.activeExecutions[{node, execution}]` | live.py:148, shown "Сейчас работают" | J2 |
| round N | today derived from new worker execution ids (live.py:158-164); native `nv2-*` ids do not name the task (live.py:129), so C2 reads task/occurrence from run history | journal line | J2 |
| max rounds | `maxIterations` of the graph actually submitted (milestone.py:21-22) | constant, not shown | J2 |
| elapsed / last event | zplan stamps, watch cursor (live.py:86-90, 221-229) | shown | J3 |
| log records with ms timestamps | `zeroshot logs --after <cursor> --execution <ref>` (upstream docs/zeroshot-cli.md:992-1015) | one-shot 40-line tail on `e` (engine.py:1520, live.py:233) | J3 |
| interactive stream | `zeroshot attach` (docs/zeroshot-cli.md:1017) | not used | J3 (only if logs are too coarse) |
| verdicts + findings per round | last info line (node response JSON) of the reviewer execution in `zeroshot logs RUN --execution REF` (checked on 10.11, 2026-10-21) | not read while running | J5 |
| error class | log errors; engine.py:404 `classify` | after the end | J6 |
| token usage | `RunMetadata.tokenUsage`, only on `finished` | validated, not shown | out of scope |

## Engine 10.15.0 (studied 2026-10-21, snapshot of tag v10.15.0)

Correction 2026-10-21: the local upstream/ checkout is v10.11.0 and the dev PATH zeroshot is 10.11.0, so the v10.15.0 file references below were not
re-checked locally, and the run history contract is not reachable from the CLI in 10.11/10.12 (history lives only behind the `zeroshot ui` BFF,
which zplan does not read). C4 uses execution logs instead (slice table).

- Public, stable: `status`, `watch --after` (phase + active `{node, execution}` only), `logs --after --execution`
  (records with ms timestamps), `attach RUN REF` (live text of one active execution), terminal `tokenUsage`, and new
  in 10.15 `terminalResult.context` on a failed run (`primary` cause + up to 5 recorded errors) — J3 and J6 covered.
- Per-visit outputs (verdicts, findings) are in the public run history contract `zeroshot.run-history (v1)`
  (discovery returns list/detail/page templates when the target advertises it; v10.15.0
  crates/openengine-cluster-protocol/src/native_v2_target.rs:409). Access from the local controller is to be
  established in C2/C4. The `zeroshot ui` BFF routes (ui/README.md:62-66) are not a contract; zplan does not read them.
- `zeroshot ui` is a read-only browser view of a run; not used: the owner rejected a separate web view on 2026-10-18.
- Upgrade 10.12 -> 10.15 breaks one zplan check: a failed terminal result must be exactly `{status, reason}`
  (terminal_planner/authority.py:925, runs.py:367), so a failed result carrying the optional new `context`
  key becomes `engine.bad_output`. Both validators change together with the upgrade; then `failure_cause`
  (engine.py:1533) reads `context.primary` first. Not a prerequisite of C1-C4 (logs exist in 10.11/10.12):
  moved after 0.5 (critic chat-release).

## Measured silence (what "stuck" means)

292 Codex sessions of the dev runs (2026-10-18..21, ~155k event gaps): median gap < 1 s, p95 13 s, p99 45 s;
564 gaps > 2 min, 111 > 5 min, 62 > 10 min, max 60 min. Long silences are normal (test suites, reviewer reads).
So the screen shows "молчит N мин · последнее: <command>" and never says "завис" by itself; a stall warning needs
silence plus no live process, decided from engine data. The threshold is set from these numbers when J3 is built.

## Screen (wireframe, 160×45)

```
zplan · zeroshot-planning-kit · main · ✓ готов
┌ Архитектор ─────────────────────────────┐┌ [1] Сейчас  [2] План  [3] Журнал ───────────┐
│ ты: давай сделаем …                     ││ M2 «живой журнал» · попытка 1 · 23 мин       │
│ арх: предлагаю цель … (черновик цели)   ││ исполнитель ▶ проверка ▷ доставка            │
│                                         ││ раунд 2 из 4 · проверка идёт 4 мин           │
│                                         ││ приёмка: отклонено — нет теста на …          │
│                                         ││ код: принято                                 │
│                                         ││ повтор замечаний: нет                        │
│                                         ││ последнее событие 12 с назад                 │
│                                         ││ сейчас: python3 -m unittest tests.test_live  │
└─────────────────────────────────────────┘└──────────────────────────────────────────────┘
> ввод
[F1] клавиши  [alt+1/2/3] вкладки  [tab] фокус  [enter] отправить  [ctrl+q] выход
```

Tabs switch with keys that never collide with typing in the chat (alt+digit or F-keys), the D4 lesson.

### Visual target of Сейчас (owner reference 2026-10-21)

While a plan or a milestone runs, Сейчас is drawn as a flow, not as text lines (owner reference screenshot, kept
outside the repo: ~/zs-pause/ref/right-pane-flow-2026-10-21.png):

- a legend line: one colour per role (worker, acceptance review, code review, delivery / planner, critic);
- boxes linked top to bottom: worker box (role, model · effort, "раунд N из M", time in stage) → the parallel
  reviewers side by side (each: role, model, state running / accepted / rejected with a one-line reason) → delivery
  box ("результат → main" / next step);
- the active box is highlighted; finished boxes show ✓ or ✗; a running box shows a spinner and its silence
  ("молчит N мин · последнее: <command>");
- a session log strip at the bottom of the tab (time · role · event), the latest lines of Журнал;
- a status line: mode, active roles [k/n], run state.

Only engine fields are drawn (signal inventory above): no percentages or progress bars, because the engine reports
no progress fraction; elapsed time and silence replace them. C2-C4 deliver the data and the plain lines first; the
flow drawing is its own slice after C4 (after the data, before the v0.5.0 tag only if the owner asks for it).
The chat takes about half of the width (today 62 of 160 columns).

## Ratatui

Not for this release. zplan's TUI is Textual (terminal_planner/tui, ~4.7k lines with tests); Textual already has
split panes, tabs (`TabbedContent`) and a streaming log widget (`RichLog`), so every job above fits it. A Rust
rewrite would cost weeks and answer no job. Re-evaluate only if a measured problem appears (render speed, install).

## Slices (order)

| Slice | Jobs | Change | Done when |
|---|---|---|---|
| C0 | J1 | D4 chat focus, D5 reuse the existing Codex login; D1-D3, D6 so plans and reviews converge | the orchestrator (own CODEX_HOME, no owner login) types into the chat on first start of the installed candidate and walks chat → goal draft → form (app.py:2104) to a planner result on this repository |
| C0b (after 0.5) | J6 | zeroshot 10.15.0: accept and validate `terminalResult.context`, cause from `context.primary`, new pinned checksums, targeted Linux run | a failed-run fixture with `context` shows its cause; Linux targeted pass |
| C1 | J4 | right pane gets tabs Сейчас / План / Журнал; chat about half the width | snapshot at 120×40 and 160×45 shows all three |
| C2 | J2 | cycle strip + "раунд N из max" (round from history task/occurrence, max from the submitted graph) + time in the current stage | replayed run shows the right stage at every recorded step |
| C3 | J3 | live journal: follow `zeroshot logs --after --execution` (and `attach` for the active agent's live text), scrubbed, last observed command (`Codex command <phase>` log lines; not necessarily still running), silence counter | a replayed 10-min silence shows "молчит 10 мин · последнее: …" and no false "завис" |
| C4 | J5 | per-round verdicts and one-line reasons in the terminal (the web UI is rejected, ORCHESTRATOR.md "Rejected", owner 2026-10-18). Source (re-checked 2026-10-21): the last info line of a reviewer execution's `zeroshot logs RUN --execution REF` is the node response JSON {diagnostic:{message}, output, signals:{verdict}} (upstream/zeroshot/src/native_v2_runner/response.rs NodeResponseContract; seen on run 01a16010, acceptance execution: signals.verdict=accepted, diagnostic.message). Read with the C3a bounded log reader when a reviewer execution leaves activeExecutions. The manifest `progress` is not a per-round source: the steward writes it once per task after the review loop (terminal_planner/milestone.py:456-466). Shows the previous and current round's findings side by side; automatic "new edge case" detection is Later | a replay of a recorded run shows the rounds, their verdicts and reasons |
| C5 | all | v0.5.0: installed macOS journey, Linux qualification on the final SHA | tag |

Acceptance data: a fixture recorded from a real run store (the stopped s1b1c / s1a1b2 runs), not a hand-written one.
