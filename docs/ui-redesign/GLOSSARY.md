# zplan UI glossary (EN / RU / ZH)

What every word and mark on the zplan screen means, where it comes from, and its approved text
in each UI language. For agents and people changing the UI: use only these terms; a new term is
added here first (all three languages), then used in code. Status: draft 2026-10-22, owner review.

## Rules for words
- One concept, one word, on every screen and in every language. No synonyms for variety.
- The user's words, not engine names: no `planner`, `critic`, `node`, `run id`, `cluster` on screen.
- A status says what is happening and, when it needs the user, what to press.
- Never alarm without cause: "quiet" is not "stuck" (see Liveness).
- Command names stay English in every language (`/setup`, `/status`); their descriptions are translated.
- Every string has a stable id (`area.name`); code looks text up by id, never hardcodes it.

## Language
| | |
|---|---|
| Choice | First-run setup asks for the language; `/language` changes it any time; the change applies at once |
| Default | From the terminal locale (`LANG`/`LC_ALL`): `ru*` -> RU, `zh*` -> ZH, else EN |
| Stored | UI settings of zplan (not the project, not the engine) |
| Missing string | Falls back to EN, never shows an id |
| Width | Layout is tested in all three languages: CJK characters take 2 cells, Russian words are longer |

## Screen areas
| id | EN | RU | ZH | Meaning |
|---|---|---|---|---|
| pane.chat | Conversation | Разговор | 对话 | Left column: you and the architect; plan cards and questions appear here |
| pane.flow | Scheme | Схема | 流程图 | How the current job is built and where it is now: steps, who does them, in what order |
| pane.plan | Plan | План | 计划 | The goal broken into stages and tasks, done / current / left |
| pane.activity | What's happening | Что происходит | 动态 | One line per event: time, who, what |
| bar.status | — | — | — | Bottom line: project, branch, current job, keys |
| flow.legend | ◐ running ✓ done ✗ rejected ◌ waiting | ◐ идёт ✓ готово ✗ отклонено ◌ ждёт | ◐ 进行中 ✓ 已完成 ✗ 已驳回 ◌ 等待中 | Pinned in the bottom-right corner of the scheme |

Owner decision 2026-10-22: the tab is "Схема" (was "Флоу", jargon).

## Plan levels
| id | EN | RU | ZH | Meaning | Source |
|---|---|---|---|---|---|
| plan.goal | Goal | Цель | 目标 | What you asked for, in your words | proposal |
| plan.stage | Stage | Этап | 阶段 | A part of the goal delivered and merged as a whole (engine: milestone) | proposal milestones |
| plan.task | Task | Задача | 任务 | One change a worker makes and reviewers accept (engine: task) | `.zplan/milestone.json` |
| plan.left | Left: … | Осталось: … | 剩余：… | Remaining tasks, then check and merge, then next stages | computed |

## Roles (who does the work)
| id | EN | RU | ZH | Meaning |
|---|---|---|---|---|
| role.architect | architect | архитектор | 架构师 | Talks with you, writes the plan, starts stages, asks your decisions |
| role.planner | planning | планирование | 规划 | Drafts the plan (engine: planner) |
| role.plan_check | plan check | проверка плана | 计划审查 | Checks the plan covers the goal (engine: critic) |
| role.worker | worker | исполнитель | 执行者 | Writes the code for one task |
| role.review_accept | acceptance review | ревью: приёмка | 验收评审 | Does the task do what it promised? |
| role.review_code | code review | ревью: код | 代码评审 | Is the change correct and tested? |
| role.final_check | final check | итоговая проверка | 最终检查 | After all tasks: the stage as a whole works |
| role.merge | merge | слияние | 合并 | The stage goes into the main branch, after your ok |
| role.select_init | first task pick | выбор первой задачи | 选择首个任务 | Picks where the stage starts (node `select_init`) |
| role.select | task pick | выбор задачи | 选择任务 | Picks the next task (node `select`) |
| role.select_verify | pick check | проверка выбора | 选择检查 | Checks the pick is valid (node `select_verify`) |
| role.steward_apply | result record | учёт результата | 记录结果 | Records the accepted task into the stage (node `steward_apply`) |
| role.steward_decide | task decision | решение по задаче | 任务决策 | Next task, stop, or ask you (node `steward_decide`) |
| role.repair | stage fix-up | доработка этапа | 阶段修复 | Fixes what the final check found (node `repair`) |
| role.scope_verify | scope check | проверка объёма | 范围检查 | The fix stayed within the stage (node `scope_verify`) |
| role.final_reverify | final re-check | повторная итоговая проверка | 再次最终检查 | Final check after a fix-up (node `final_reverify`) |
Unknown node names (a scheme authored elsewhere) are shown as the node's own name with `_` -> space,
never hidden. Engine node -> term map lives in one place in code (`devtools/ui-lab/flowdraw.py` NAMES).

## Step states (marks)
Colour always comes with a mark, so the meaning survives without colour.
| id | Mark | EN | RU | ZH | Meaning | Engine state |
|---|---|---|---|---|---|---|
| state.running | ◐ (spins) | running | идёт | 进行中 | Working now | running |
| state.done | ✓ green | done | готово | 已完成 | Finished, accepted | succeeded |
| state.rejected | ✗ red | rejected | отклонено | 已驳回 | A review said no; work goes back to the worker (↺) | failed verdict |
| state.error | ! red | error | ошибка | 出错 | The step itself broke (crash, timeout); needs a look | failed |
| state.waiting | ◌ dim | waiting | ждёт | 等待中 | Not started yet | idle |
| state.skipped | – dim | skipped | пропущено | 已跳过 | Not needed in this run | skipped |
| flow.loop | ↺ red edge | back to: worker | назад: исполнитель | 返回：执行者 | Rejection sends the task back for another round | choice/loop |
| flow.round | ▰▱ 1/3 | review round 1 of 3 | раунд ревью 1 из 3 | 评审第 1/3 轮 | Rounds used of the allowed limit | plan limits |
| flow.loop_group | ↻ | {name} · {n} of {max} / up to {max} times | {name} · {n} из {max} / до {max} раз | {name} · 第 {n}/{max} 次 / 最多 {max} 次 | A repeating part of the scheme (graph `loop`) | loop + observation count |
| flow.optional | ? and ┆ | if needed: {name} | если нужно: {name} | 如有需要：{name} | Runs only when the check before it did not accept | choice whose exit is an `accepted` verdict |
| flow.task_loop | ↻ | tasks one by one | задачи по очереди | 逐个任务 | The stage's task loop (node `task_loop`) | loop |
| flow.review_loop | ↻ | review rounds | раунды ревью | 评审轮次 | One task's worker -> review rounds (node `review_loop`) | loop |
| flow.repair_loop | ↻ | fix-up rounds | раунды доработки | 修复轮次 | Fix-up rounds after the final check (node `repair_loop`) | loop |
| flow.final_repair | ? | fix-up after the final check | доработка после итоговой проверки | 最终检查后的修复 | The optional branch name (node `final_repair`) | choice |
| state.if_needed | ◌ dim | if needed | если нужно | 如有需要 | A waiting step inside an optional branch | idle |

Choices: only the path taken (or the default one before it starts) is drawn; exits on error are hidden
until they happen. Sequences are invisible wiring.

Rejected is normal work (a round of review), error is a problem. They must never look the same.

## Liveness (is it alive?)
Owner decision 2026-10-22: no "quiet"/"stuck" thresholds and no time-based alarms. Reassurance comes
from clocks that visibly tick every second, and from showing what the step is doing.
| id | Where | EN | RU | ZH |
|---|---|---|---|---|
| live.step_timer | every running step (box or tree line) | {m:ss} | {m:ss} | {m:ss} |
| live.job_timer | bottom line, the running job | {stage} running {h:mm:ss} | {stage} идёт {h:mm:ss} | {stage} 进行中 {h:mm:ss} |
| live.last_event | bottom border of "What's happening" | last: {what} · {m:ss} ago | последнее: {what} · {m:ss} назад | 最近：{what} · {m:ss} 前 |
| live.detached | watcher gone (engine signal) | ! not watched — /status reconnect | ! без присмотра — /status подключиться | ! 未在监控 — /status 重新连接 |
Red appears only on an engine signal (error, rejected, detached), never because time passed.

### Planned: what the step is doing (backend, not in this redesign)
Cheap sources the engine already exposes; none costs model tokens, only reading a stream:
| Source | Gives | Cost | Status |
|---|---|---|---|
| `live.command` (`terminal_planner/live.py:29`, from the Codex adapter's "command started" log line) | the command running now, e.g. `pytest tests/test_export.py` | already collected | UI can show it now |
| `zeroshot attach RUN_ID EXECUTION` (`upstream/docs/guides/observe-and-control.md:61`; events `working` / `output{text}` / `settled`, `native-v2-observation.schema.json` `AgentAttachEvent`) | the agent's own progress text ("updating the serializer…") | one open stream per running step while watched | to plan; check the engine version zplan pins supports it |
| `status` → active executions (`ActiveExecution{node, execution}`) | which steps run right now, per step | one status call per refresh (already polled) | to plan |
| `TokenUsage` in run status | tokens growing = the model is producing | already in status | optional |
The attach stream has no reasoning or tool frames by design; we show its output text clipped to one line.

## Scheme fitting (big pipelines)
The scheme picks the first mode that fits the pane, on every frame and resize.
| Mode | When | Shows |
|---|---|---|
| boxes | fits in width and height | framed steps, arrows, moving dots on active edges, ↺ on rejection |
| tree | boxes do not fit | one line per step, parallel steps as `├` branches |
| window | the tree does not fit | steps around the current one; the ends folded into one line each |

| id | EN | RU | ZH |
|---|---|---|---|
| flow.fold_done | ✓ {n} stages behind ↑ | ✓ ещё {n} позади ↑ | ✓ 已完成 {n} 个阶段 ↑ |
| flow.fold_next | ◌ {n} ahead: {names} ↓ | ◌ ещё {n} впереди: {names} ↓ | ◌ 还有 {n} 个：{names} ↓ |

Source of the scheme (next step): the public Zeroshot graph format
(`upstream/protocol/openengine-cluster/v1/graph.schema.json`) plus per-step observation states
(`upstream/ui/src/workflow-observation.ts`), the same data the Zeroshot web UI draws. zplan's own
stage graph is built in that format (`terminal_planner/milestone.py:303`). Running a scheme authored
in the web UI is a backend feature, out of the UI redesign.

## Keys
| id | Key | EN | RU | ZH |
|---|---|---|---|---|
| key.panel | tab | panel | панель | 面板 |
| key.view | ←→ | scheme/plan | схема/план | 流程图/计划 |
| key.commands | / | commands | команды | 命令 |
| key.quit | ctrl+q | quit (work continues) | выйти (работа продолжится) | 退出（任务继续） |
Keys work in the Russian layout; no F-keys (PRINCIPLES.md 8).
