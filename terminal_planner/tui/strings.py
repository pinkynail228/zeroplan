"""Every string of the new main screen, by a stable id, in Russian, English and Chinese.

Nothing renders from this module yet: integration runs i1-i6 switch the main screen to it. Text comes from
`docs/ui-redesign/GLOSSARY.md` (its RU/EN/ZH tables) and from the approved lab `devtools/ui-lab/work.py` (the
greeting, card copy, canvas titles and empty states, the bar and the `/` command descriptions).

`text(id, **values)` returns the current language's string; a missing translation falls back to EN and an unknown id
raises KeyError (a programming error, never shown). A placeholder with no matching value is left verbatim, so the
scheme renders a templated row through it (`scheme.render(..., words=strings.text)`): the renderer fills the
`{name}`/`{n}`/`{max}` fields itself, while a caller that passes a value gets it substituted here. `language()` is
the chosen code, `set_language(code)` switches and stores it in the UI settings file
`setup.config_root() / "ui.json"` (not the project, not the engine).

Worker interpretations (the reviewers never see the worker's summary):

- The GLOSSARY ids are the tables whose area is `pane.`/`plan.`/`role.`/`state.`/`flow.`/`live.`/`key.` (the
  surface names). `bar.status` is the one row with no EN/RU/ZH cell (its column holds dashes: it labels the bottom
  line, it is not text), so it gets no id: A5 requires every id to have all three languages.
- Lab ids follow the areas the brief fixes: `chat.` (greeting, placeholder, the two pane titles, the owner label),
  `card.` (each card's title, text, buttons, the default hint and the "done" receipts), `canvas.` (tab labels, pane
  titles, empty and working states), `bar.` (job phrases, key labels, the "work continues" note), `cmd.` (the twenty
  `/` descriptions; the names themselves stay English), `note.` (the warning lines).
- The brief's fixture content (the CSV story, the diff, file names, stage/task names and dates) gets no id; a value
  the lab interpolates from that story is a placeholder instead. So `card.merge_title` is "{stage} is ready",
  `card.question_title` is "Your decision is needed · {task}", `card.draft_sent` is "✓ sent to the planner {time}".
  The count of consecutive rejections in the question card is such a value: it becomes the shared `{count}`
  placeholder, so the card keeps the lab's "four times in a row" step ("The review rejected {task} {count} times in a row").
- The chat names the architect with `role.architect` (the same word), so the lab label needs no second id.
- Lab lines that only draw plan-body data (the accepted mark, the round note) still get an id.
- The titles/details the lab's `_scheme` puts on the scheme nodes ("plan rounds", "reads the code", "checks against the goal",
  "waits for you", "the model did not answer") are generic captions, not story data, so they get `canvas.obs_*` ids and the
  scheme shows them translated. The `STEPS` worker briefs ("writes code", "runs tests", "done", "fix-up")
  and the run log lines are the scripted story (task ids, tests, times), like the task names and the diff, so they
  stay fixture content with no id.
- Counts the lab spells with a Russian plural ("2 tasks", "5 tasks", "2 checks", the "3 stages · 9 tasks" plan title)
  are UI copy and get ids too. GLOSSARY writes numbers without pluralised nouns and the brief rules out plural rules
  beyond it, so the three nouns the lab shows (task, check, stage) keep the forms the lab prints (Russian in the ru column) as plain
  catalog ids (`canvas.count_*_{one,few,many}`); nothing here selects a form, so a caller names the id whose form its
  fixture prints. `card.plan_title` takes the two rendered counts (`{stages}`, `{tasks}`) instead of a preformatted blob.
- The Liveness clocks stay as GLOSSARY spells them, `{m:ss}` / `{h:mm:ss}`. In `str.format` the text after the colon
  is a format spec (not a field), so `text` substitutes the field names only and keeps the spec-only colon spelling
  out of the result: `text("live.step_timer", m="3:07")` gives "3:07".
- `set_language` refuses a code outside `LANGUAGES` with ValueError; the stored-file checks of A4 ignore such a code
  and fall back to the locale default. The `note.view_*`/`note.needs_arg` wording is authored here (the lab only
  reaches `/open`; u3 and u4 own the reader and the parser and only fix the ids and placeholders).

i6 (the main screen reads the catalog) adds the ids the main screen's own literals need, `ru` spelled exactly as the
literal it replaces so a Russian screen does not change, the way the three added `header.*` readiness words, the
`chat.` pane titles and status lines, the `canvas.` tab labels, the plan pane's own lines and the usage row do.
`chat.title` is the chat pane's wide border title and `chat.title_narrow` is i7's; i9 stopped cycling the pane title
through `chat.title_idle`/`chat.title_planning`/`chat.title_run` (the lab keeps one title), and those ids stay for the
callers that still read them. i9 adds the `chat.partial` marker of a cancelled turn (its author-line ids went with
the author line in 0.6.3 V2). The main screen's input placeholder is now the lab's
`chat.placeholder` (`chat.input` stays for the callers that read it). The `note.language` line names a code's display
name after `/language CODE`
or a pick in the chooser.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

from .. import setup
from ..authority import Blocked, canonical, decode

LANGUAGES = ("en", "ru", "zh")
# The languages the TUI offers: the public release ships English only. The catalog keeps the ru and zh columns for a
# later localisation release; the language in effect is always one of `OFFERED`.
OFFERED = ("en",)
DEFAULT = "en"
DISPLAY_NAMES = {"en": "English", "ru": "Русский", "zh": "中文"}
THEMES = ("dark", "light", "auto")
FILENAME = "ui.json"
# LC_ALL wins over LC_MESSAGES, which wins over LANG; the first non-empty value decides the default language.
LOCALE_VARS = ("LC_ALL", "LC_MESSAGES", "LANG")

# `{name}` and `{name:spec}`; only the field name is substituted, the rest of the group (a clock spelling) is dropped.
_FIELD = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::[^{}]*)?\}")

CATALOG = {
    # ---- Surface names (GLOSSARY "Screen areas") ------------------------------------------------
    "pane.chat": {"en": "Conversation", "ru": "Разговор", "zh": "对话"},
    "pane.flow": {"en": "Scheme", "ru": "Схема", "zh": "流程图"},
    "pane.plan": {"en": "Plan", "ru": "План", "zh": "计划"},
    "pane.activity": {"en": "What's happening", "ru": "Что происходит", "zh": "动态"},
    "flow.legend": {"en": "◐ running ✓ done ✗ rejected ◌ waiting",
                    "ru": "◐ идёт ✓ готово ✗ отклонено ◌ ждёт",
                    "zh": "◐ 进行中 ✓ 已完成 ✗ 已驳回 ◌ 等待中"},

    # ---- Plan levels (GLOSSARY) ------------------------------------------------------------------
    "plan.goal": {"en": "Goal", "ru": "Цель", "zh": "目标"},
    "plan.stage": {"en": "Stage", "ru": "Этап", "zh": "阶段"},
    "plan.task": {"en": "Task", "ru": "Задача", "zh": "任务"},
    "plan.left": {"en": "Left: …", "ru": "Осталось: …", "zh": "剩余：…"},

    # ---- Roles (GLOSSARY) ------------------------------------------------------------------------
    "role.architect": {"en": "architect", "ru": "архитектор", "zh": "架构师"},
    "role.planner": {"en": "planning", "ru": "планирование", "zh": "规划"},
    "role.plan_check": {"en": "plan check", "ru": "проверка плана", "zh": "计划审查"},
    "role.worker": {"en": "worker", "ru": "исполнитель", "zh": "执行者"},
    "role.review_accept": {"en": "acceptance review", "ru": "ревью: приёмка", "zh": "验收评审"},
    "role.review_code": {"en": "code review", "ru": "ревью: код", "zh": "代码评审"},
    "role.final_check": {"en": "final check", "ru": "итоговая проверка", "zh": "最终检查"},
    "role.merge": {"en": "merge", "ru": "слияние", "zh": "合并"},
    "role.preflight": {"en": "preflight", "ru": "предпроверка", "zh": "预检"},
    "role.select_init": {"en": "first task pick", "ru": "выбор первой задачи", "zh": "选择首个任务"},
    "role.select": {"en": "task pick", "ru": "выбор задачи", "zh": "选择任务"},
    "role.select_verify": {"en": "pick check", "ru": "проверка выбора", "zh": "选择检查"},
    "role.steward_apply": {"en": "result record", "ru": "учёт результата", "zh": "记录结果"},
    "role.steward_decide": {"en": "task decision", "ru": "решение по задаче", "zh": "任务决策"},
    "role.repair": {"en": "stage fix-up", "ru": "доработка этапа", "zh": "阶段修复"},
    "role.scope_verify": {"en": "scope check", "ru": "проверка объёма", "zh": "范围检查"},
    "role.final_reverify": {"en": "final re-check", "ru": "повторная итоговая проверка", "zh": "再次最终检查"},

    # ---- Step states (GLOSSARY) ------------------------------------------------------------------
    "state.running": {"en": "running", "ru": "идёт", "zh": "进行中"},
    "state.done": {"en": "done", "ru": "готово", "zh": "已完成"},
    "state.rejected": {"en": "rejected", "ru": "отклонено", "zh": "已驳回"},
    "state.error": {"en": "error", "ru": "ошибка", "zh": "出错"},
    "state.waiting": {"en": "waiting", "ru": "ждёт", "zh": "等待中"},
    "state.skipped": {"en": "skipped", "ru": "пропущено", "zh": "已跳过"},
    "state.if_needed": {"en": "if needed", "ru": "если нужно", "zh": "如有需要"},

    # ---- Flow marks (GLOSSARY) -------------------------------------------------------------------
    "flow.loop": {"en": "back to: worker", "ru": "назад: исполнитель", "zh": "返回：执行者"},
    "flow.round": {"en": "review round 1 of 3", "ru": "раунд ревью 1 из 3", "zh": "评审第 1/3 轮"},
    "flow.loop_group": {"en": "{name} · {n} of {max} / up to {max} times",
                        "ru": "{name} · {n} из {max} / до {max} раз",
                        "zh": "{name} · 第 {n}/{max} 次 / 最多 {max} 次"},
    "flow.optional": {"en": "if needed: {name}", "ru": "если нужно: {name}", "zh": "如有需要：{name}"},
    "flow.task_loop": {"en": "tasks one by one", "ru": "задачи по очереди", "zh": "逐个任务"},
    "flow.review_loop": {"en": "review rounds", "ru": "раунды ревью", "zh": "评审轮次"},
    "flow.repair_loop": {"en": "fix-up rounds", "ru": "раунды доработки", "zh": "修复轮次"},
    "flow.final_repair": {"en": "fix-up after the final check", "ru": "доработка после итоговой проверки",
                          "zh": "最终检查后的修复"},
    "flow.fold_done": {"en": "✓ {n} stages behind ↑", "ru": "✓ ещё {n} позади ↑", "zh": "✓ 已完成 {n} 个阶段 ↑"},
    "flow.fold_next": {"en": "◌ {n} ahead: {names} ↓", "ru": "◌ ещё {n} впереди: {names} ↓",
                       "zh": "◌ 还有 {n} 个：{names} ↓"},

    # ---- Liveness (GLOSSARY) ---------------------------------------------------------------------
    "live.step_timer": {"en": "{m:ss}", "ru": "{m:ss}", "zh": "{m:ss}"},
    "live.job_timer": {"en": "{stage} running {h:mm:ss}", "ru": "{stage} идёт {h:mm:ss}",
                       "zh": "{stage} 进行中 {h:mm:ss}"},
    "live.last_event": {"en": "last: {what} · {m:ss} ago", "ru": "последнее: {what} · {m:ss} назад",
                        "zh": "最近：{what} · {m:ss} 前"},
    "live.detached": {"en": "! not watched — /status reconnect", "ru": "! без присмотра — /status подключиться",
                      "zh": "! 未在监控 — /status 重新连接"},

    # ---- Keys (GLOSSARY) -------------------------------------------------------------------------
    "key.panel": {"en": "panel", "ru": "панель", "zh": "面板"},
    "key.view": {"en": "scheme/plan", "ru": "схема/план", "zh": "流程图/计划"},
    "key.commands": {"en": "commands", "ru": "команды", "zh": "命令"},
    "key.quit": {"en": "quit (work continues)", "ru": "выйти (работа продолжится)", "zh": "退出（任务继续）"},

    # ---- Header (readiness words of `app.header_text`; i6) ---------------------------------------
    "header.checking": {"en": "checking…", "ru": "проверка…", "zh": "检查中…"},
    "header.ready": {"en": "✓ ready", "ru": "✓ готов", "zh": "✓ 就绪"},
    "header.failed_more": {"en": "{n} more", "ru": "ещё {n}", "zh": "还有 {n}"},
    "header.not_passed_one": {"en": "check not passed", "ru": "проверка не пройдена", "zh": "有检查未通过"},
    "header.not_passed_few": {"en": "checks not passed", "ru": "проверки не пройдены", "zh": "有检查未通过"},
    "header.not_passed_many": {"en": "checks not passed", "ru": "проверок не пройдено", "zh": "有检查未通过"},
    "header.detached": {"en": "detached HEAD", "ru": "HEAD отсоединён", "zh": "游离 HEAD"},

    # ---- Chat (lab: intro, placeholder, pane titles) ---------------------------------------------
    # E1: the empty chat's intro `chat.intro` (`MainScreen.sync_intro`); the three examples are generic, for any
    # repository. The zh cells of the intro keys are still copies of the ru text: translating them is not done yet.
    "chat.intro": {"en": "Describe what needs to be done. The architect will clarify the details, draw up a "
                         "plan, start the work and ask before merging.",
                   "ru": "Опиши, что нужно сделать. Архитектор уточнит детали, составит "
                         "план, запустит работу и спросит перед слиянием.",
                   "zh": "Опиши, что нужно сделать. Архитектор уточнит детали, составит "
                         "план, запустит работу и спросит перед слиянием."},
    "chat.intro_caption": {"en": "For example",
                           "ru": "Например",
                           "zh": "Например"},
    "chat.example_1": {"en": "Explain how this project works",
                       "ru": "Объясни, как устроен этот проект",
                       "zh": "Объясни, как устроен этот проект"},
    "chat.example_2": {"en": "Add tests for the most important part of the code",
                       "ru": "Добавь тесты для самой важной части кода",
                       "zh": "Добавь тесты для самой важной части кода"},
    "chat.example_3": {"en": "Update the README: how to install and run",
                       "ru": "Обнови README: как установить и запустить",
                       "zh": "Обнови README: как установить и запустить"},
    "chat.intro_hint": {"en": "↑↓ example into the input · enter send · ctrl+j new line · / commands",
                        "ru": "↑↓ пример в строку ввода · enter отправить · ctrl+j новая строка · / команды",
                        "zh": "↑↓ пример в строку ввода · enter отправить · ctrl+j новая строка · / команды"},
    "chat.placeholder": {"en": "Write to the architect… or / for commands",
                         "ru": "Напиши архитектору… или / для команд",
                         "zh": "给架构师留言…或按 / 查看命令"},
    # D2: the input's placeholder while a decision card is open (the card's choices are answered by keys; at 80x24
    # the card's own hint row is hidden, so the keys are said here).
    "chat.placeholder_card": {"en": "↑↓ choose · enter answer · or write to the architect",
                              "ru": "↑↓ выбрать · enter ответить · или напишите архитектору",
                              "zh": "↑↓ выбрать · enter ответить · или напишите архитектору"},
    "chat.title": {"en": "Conversation with the architect", "ru": "Разговор с архитектором", "zh": "与架构师的对话"},
    "chat.title_narrow": {"en": "Conversation · ←→ tabs", "ru": "Разговор · ←→ вкладки", "zh": "对话 · ←→ 切换标签"},
    "chat.input": {"en": "message to the architect", "ru": "сообщение архитектору", "zh": "给架构师留言"},
    "chat.title_idle": {"en": "Architect", "ru": "Архитектор", "zh": "架构师"},
    "chat.title_planning": {"en": "Planner", "ru": "Планировщик", "zh": "规划器"},
    "chat.title_run": {"en": "Run {stage}", "ru": "Прогон {stage}", "zh": "运行 {stage}"},
    "chat.planning": {"en": "The planner is working…", "ru": "Планировщик работает…", "zh": "规划器正在工作…"},
    "chat.observing": {"en": "Watching {stage}…", "ru": "Наблюдение {stage}…", "zh": "正在观察 {stage}…"},
    "confirm.stop_plan": {"en": "Stop planning of plan r{v}?", "ru": "Остановить планирование плана r{v}?",
                          "zh": "停止计划 r{v} 的规划？"},
    "chat.stop_requested": {"en": "Stop of {stage} requested; waiting for Zeroshot to confirm.",
                            "ru": "Остановка {stage} запрошена; жду подтверждения Zeroshot.",
                            "zh": "已请求停止 {stage}，等待 Zeroshot 确认。"},
    "chat.reading": {"en": "Reading the Zeroshot journal…", "ru": "Читаю журнал Zeroshot…",
                     "zh": "正在读取 Zeroshot 日志…"},
    "chat.quit_waits": {"en": "Finishing the operation without interrupting it. Exit right after.",
                        "ru": "Завершаю операцию, не прерывая её. Выход сразу после неё.",
                        "zh": "正在完成此次操作，不予中断；完成后立即退出。"},
    "chat.fixture": {"en": "The architect chat is unavailable in the demo (--fixture).",
                     "ru": "Чат архитектора недоступен в демо (--fixture).",
                     "zh": "演示模式（--fixture）中没有架构师聊天。"},
    "chat.refused": {"en": "The architect chat is unavailable: no project selected.",
                     "ru": "Чат архитектора недоступен: проект не выбран.",
                     "zh": "架构师聊天不可用：未选择项目。"},
    "chat.thinking": {"en": "The architect is thinking… {clock}", "ru": "Архитектор думает… {clock}",
                      "zh": "架构师思考中… {clock}"},
    "chat.tokens": {"en": "{count} tok", "ru": "{count} ток", "zh": "{count} 令牌"},
    "chat.rot": {"en": "long session: /new", "ru": "сессия длинная: /new", "zh": "会话过长：/new"},
    # `chat.partial` marks the cut tail of a cancelled turn.
    "chat.partial": {"en": "interrupted", "ru": "прервано", "zh": "已中断"},

    # ---- Cards (lab) -----------------------------------------------------------------------------
    "card.draft_title": {"en": "Goal draft", "ru": "Черновик цели", "zh": "目标草稿"},
    "card.draft_sent": {"en": "✓ sent to planning {time}", "ru": "✓ отправлен планировщику {time}",
                        "zh": "✓ 已于 {time} 发送给规划"},
    "card.draft_text": {"en": "Draft a plan from this? The full text is in the “Goal draft” tab.",
                        "ru": "Составить план из этого черновика? Полный текст — во вкладке «Черновик цели».",
                        "zh": "根据这个草稿制定计划？完整文本在「目标草稿」标签中。"},
    "card.plan_yes": {"en": "yes, draft the plan", "ru": "да, составить план", "zh": "好，制定计划"},
    "card.no": {"en": "no", "ru": "нет", "zh": "否"},
    "card.plan_title": {"en": "Plan · {stages} · {tasks}", "ru": "План · {stages} · {tasks}",
                        "zh": "计划 · {stages} · {tasks}"},
    "card.plan_done": {"en": "✓ approved {time}", "ru": "✓ утверждён {time}", "zh": "✓ 已于 {time} 批准"},
    "card.plan_text": {"en": "The plan is checked and covers the goal. Approve? The “Plan” tab is on the right.",
                       "ru": "План проверен и покрывает цель. Утвердить? Справа — вкладка «План».",
                       "zh": "计划已核查并覆盖目标。是否批准？右侧是「计划」标签。"},
    "card.plan_text_narrow": {"en": "The plan is checked and covers the goal. Approve? The plan is on the “Plan” tab (→).",
                              "ru": "План проверен и покрывает цель. Утвердить? План — на вкладке «План» (→).",
                              "zh": "计划已核查并覆盖目标。是否批准？计划在「计划」标签（→）。"},
    "card.plan_auto_text": {"en": "The plan is checked and covers the goal. The architect will approve it itself; "
                                  "to stop it, choose “revise”.",
                            "ru": "План проверен и покрывает цель. Архитектор утвердит его сам; чтобы остановить — "
                                  "«доработать».",
                            "zh": "计划已核查并覆盖目标。架构师会自行批准；要停止，请选择「修改」。"},
    "card.plan_stale_text": {"en": "The project changed after planning, so the plan cannot be approved. Revising "
                                   "rebuilds it.",
                             "ru": "Проект изменился после планирования: утвердить нельзя. Доработка пересоберёт план.",
                             "zh": "项目在规划后发生了变化，无法批准。修改会重新生成计划。"},
    "card.revise_only": {"en": "revise", "ru": "доработать", "zh": "修改"},
    "card.approve_yes": {"en": "yes, approve", "ru": "да, утвердить", "zh": "好，批准"},
    "card.revise": {"en": "no, revise", "ru": "нет, доработать", "zh": "否，修改"},
    "card.merge_title": {"en": "{stage} ready", "ru": "{stage} готов", "zh": "{stage} 已完成"},
    "card.merge_text": {"en": "{done} of {total} tasks accepted, the final check passed. Merge into main?",
                        "ru": "{done} из {total} задач приняты, итоговая проверка пройдена. Влить в main?",
                        "zh": "{done}/{total} 个任务已通过，最终检查已通过。合并进 main？"},
    "card.merge_yes": {"en": "merge", "ru": "влить", "zh": "合并"},
    "card.merge_changes": {"en": "see the changes", "ru": "посмотреть изменения", "zh": "查看改动"},
    # D4b: the merge card once the landing was refused because files of the owner's tree are in the way.
    "card.merge_overlap_title": {"en": "! {stage} not merged", "ru": "! {stage} не влит", "zh": "！{stage} 未合并"},
    "card.merge_overlap_text": {"en": "Merging would write over files of your tree: {paths}. The branch is kept.",
                                "ru": "Слияние перезаписало бы ваши файлы вне коммита: {paths}. Ветка сохранена.",
                                "zh": "合并会覆盖你工作区中的文件：{paths}。分支已保留。"},
    "card.merge_later": {"en": "merge later", "ru": "влить позже", "zh": "稍后合并"},
    "card.merge_diff": {"en": "show the differences", "ru": "показать различия", "zh": "显示差异"},
    "card.merge_later_done": {"en": "↻ {stage}: merge later, the branch is kept {time}",
                              "ru": "↻ {stage}: влить позже, ветка сохранена {time}",
                              "zh": "↻ {stage}：稍后合并，分支已保留 {time}"},
    # D4c: the commit card (the owner's own files; the zh cells are copies of the ru text, not translated yet).
    "card.commit_title": {"en": "Commit your files",
                          "ru": "Коммит ваших файлов",
                          "zh": "Коммит ваших файлов"},
    "card.commit_text": {"en": "{message}\n\n{stat}\n\nAttention: {stamp}. Commit these files?",
                         "ru": "{message}\n\n{stat}\n\nВнимание: {stamp}. Закоммитить эти файлы?",
                         "zh": "{message}\n\n{stat}\n\nВнимание: {stamp}. Закоммитить эти файлы?"},
    "card.commit_yes": {"en": "yes",
                        "ru": "да",
                        "zh": "да"},
    "card.commit_no": {"en": "no",
                       "ru": "нет",
                       "zh": "нет"},
    "card.commit_left_out": {"en": "Not included: {paths}.",
                             "ru": "Не включены: {paths}.",
                             "zh": "Не включены: {paths}."},
    "card.commit_more": {"en": "… and {count} more lines",
                         "ru": "… и ещё {count} строк",
                         "zh": "… и ещё {count} строк"},
    "card.commit_done": {"en": "✓ commit: done {time}\n{lines}",
                         "ru": "✓ закоммитить: готово {time}\n{lines}",
                         "zh": "✓ закоммитить: готово {time}\n{lines}"},
    "card.commit_failed": {"en": "✗ commit failed {time}\n{reason}",
                           "ru": "✗ коммит не выполнен {time}\n{reason}",
                           "zh": "✗ коммит не выполнен {time}\n{reason}"},
    "card.commit_declined": {"en": "↻ commit declined, files untouched {time}",
                             "ru": "↻ коммит отклонён, файлы не тронуты {time}",
                             "zh": "↻ коммит отклонён, файлы не тронуты {time}"},
    "note.commit_no_suspend": {"en": "This terminal cannot be suspended: the commit was not made, run git commit yourself.",
                               "ru": "Этот терминал не поддерживает приостановку: коммит не выполнен, выполните git commit сами.",
                               "zh": "Этот терминал не поддерживает приостановку: коммит не выполнен, выполните git commit сами."},
    "card.question_title": {"en": "Your decision is needed · {task}", "ru": "Нужно твоё решение · {task}",
                            "zh": "需要你的决定 · {task}"},
    "card.question_text": {"en": "Review rejected {task} {count} times in a row: {why}. What do we do?",
                           "ru": "Ревью отклонило {task} {count} раза подряд: {why}. Что делаем?",
                           "zh": "评审连续 {count} 次驳回 {task}：{why}。怎么办？"},
    "card.question_hint": {"en": "or answer in words, e.g. “drop the test, do it in M3”",
                           "ru": "или ответь словами, например: «убери тест, сделаем в M3»",
                           "zh": "或用文字回答，例如：「去掉测试，放到 M3 再做」"},
    "card.question_simplify": {"en": "simplify", "ru": "упростить", "zh": "简化"},
    "card.question_split": {"en": "split", "ru": "разбить", "zh": "拆分"},
    "card.question_skip": {"en": "skip", "ru": "пропустить", "zh": "跳过"},
    "card.error_title": {"en": "! Error · {task}", "ru": "! Ошибка · {task}", "zh": "！出错 · {task}"},
    "card.stopped_title": {"en": "Stopped · {task}", "ru": "Остановлено · {task}", "zh": "已停止 · {task}"},
    "card.error_text": {"en": "The worker stopped: the model did not answer within 10 minutes (exit 1). The rest "
                             "is intact, the branch is in place.",
                        "ru": "Исполнитель остановился: модель не ответила за 10 минут (выход 1). Остальное цело, "
                              "ветка на месте.",
                        "zh": "执行者已停止：模型 10 分钟内没有响应（退出码 1）。其余部分完好，分支仍在。"},
    "card.error_retry": {"en": "try again", "ru": "новая попытка", "zh": "重试"},
    "card.error_details": {"en": "details", "ru": "подробнее", "zh": "详情"},
    "card.hint": {"en": "or {commands}", "ru": "или {commands}", "zh": "或 {commands}"},
    # i3c: the merge card's own two ids — the text of a card whose attempt view is not read yet (or carries no
    # tasks line) and the receipt the card becomes once the engine merged the stage.
    "card.merge_text_bare": {"en": "The final check passed. Merge into main?",
                             "ru": "Итоговая проверка пройдена. Влить в main?",
                             "zh": "最终检查已通过。合并进 main？"},
    "card.merge_done": {"en": "✓ {stage} merged into main {time}", "ru": "✓ {stage} влит в main {time}",
                        "zh": "✓ {stage} 已并入 main {time}"},
    # i3d: the question card's own lines — the draft button (its full wording; the card wraps its buttons, so the
    # label is never shortened) and the sent receipt.
    "card.answer_draft": {"en": "send the answer draft", "ru": "отправить черновик ответа", "zh": "发送回答草稿"},
    "card.answer_sent": {"en": "✓ answer sent {time}", "ru": "✓ ответ отправлен {time}",
                         "zh": "✓ 已于 {time} 发送回答"},
    # i3e2: the receipt of a failure card the owner retried (the retry itself is the error card's «new attempt»).
    "card.error_retried": {"en": "↻ try again {time}", "ru": "↻ новая попытка {time}", "zh": "↻ 重试 {time}"},
    # S1: the words of an event step in the pane (`chat.step_of`): one id per plan status (`step.plan.*`, the
    # subject is "Plan rN") and per run state or milestone state (`step.run.*`, the subject is the milestone id).
    "step.plan": {"en": "Plan r{revision} {word}", "ru": "План r{revision} {word}", "zh": "计划 r{revision} {word}"},
    "step.verdict_ok": {"en": "{milestone} check passed", "ru": "{milestone} проверка пройдена",
                        "zh": "{milestone} 检查通过"},
    "step.verdict_bad": {"en": "{milestone} check remarks", "ru": "{milestone} замечания проверки",
                         "zh": "{milestone} 检查有意见"},
    "step.attempt": {"en": "attempt {attempt}", "ru": "попытка {attempt}", "zh": "第 {attempt} 次尝试"},
    "step.round": {"en": "round {round}", "ru": "раунд {round}", "zh": "第 {round} 轮"},
    "step.more": {"en": "… {count} more", "ru": "… ещё {count}", "zh": "… 另有 {count} 条"},
    "step.plan.planning": {"en": "is being drafted", "ru": "планируется", "zh": "规划中"},
    "step.plan.submission_unknown": {"en": "submission unconfirmed", "ru": "отправка не подтверждена", "zh": "提交状态未知"},
    "step.plan.observing": {"en": "is being watched", "ru": "наблюдается", "zh": "观察中"},
    "step.plan.observation_blocked": {"en": "observation blocked", "ru": "наблюдение прервано", "zh": "观察受阻"},
    "step.plan.detached": {"en": "detached", "ru": "отсоединён", "zh": "已分离"},
    "step.plan.run_failed": {"en": "run failed", "ru": "прогон не удался", "zh": "运行失败"},
    "step.plan.proposal_invalid": {"en": "proposal invalid", "ru": "предложение неверно", "zh": "提案无效"},
    "step.plan.review_exhausted": {"en": "reviews exhausted", "ru": "проверки исчерпаны", "zh": "评审次数用尽"},
    "step.plan.proposed": {"en": "proposed", "ru": "предложен", "zh": "已提出"},
    "step.plan.approved": {"en": "approved", "ru": "утверждён", "zh": "已批准"},
    "step.plan.stopped": {"en": "stopped", "ru": "остановлен", "zh": "已停止"},
    "step.run.waiting": {"en": "waiting", "ru": "ждёт", "zh": "等待中"},
    "step.run.ready": {"en": "ready", "ru": "готов к запуску", "zh": "就绪"},
    "step.run.running": {"en": "running", "ru": "выполняется", "zh": "运行中"},
    "step.run.stopping": {"en": "stopping", "ru": "останавливается", "zh": "正在停止"},
    "step.run.unknown": {"en": "state unknown", "ru": "состояние неизвестно", "zh": "状态未知"},
    "step.run.stopped": {"en": "stopped", "ru": "остановлен", "zh": "已停止"},
    "step.run.conflict": {"en": "conflict", "ru": "конфликт", "zh": "冲突"},
    "step.run.integrated": {"en": "merged into main", "ru": "влит в main", "zh": "已并入 main"},
    "step.run.awaiting_merge": {"en": "awaiting merge", "ru": "ждёт слияния", "zh": "等待合并"},
    "step.run.needs_owner": {"en": "needs your decision", "ru": "нужно твоё решение", "zh": "需要你决定"},
    "step.run.blocked": {"en": "blocked", "ru": "заблокирован", "zh": "已阻塞"},
    "step.run.failed_recoverable": {"en": "failed, can retry", "ru": "не удался, можно повторить", "zh": "失败，可重试"},
    "step.run.failed": {"en": "failed", "ru": "не удался", "zh": "失败"},
    "step.run.preparing": {"en": "preparing", "ru": "готовится", "zh": "准备中"},
    "step.run.submission_unknown": {"en": "submission unconfirmed", "ru": "отправка не подтверждена", "zh": "提交状态未知"},
    "step.run.submitted": {"en": "submitted", "ru": "отправлен", "zh": "已提交"},
    "step.run.resume_pending": {"en": "resume pending", "ru": "ждёт возобновления", "zh": "等待恢复"},
    "step.run.finished": {"en": "finished", "ru": "завершён", "zh": "已完成"},

    # ---- Canvas (lab: tab labels, pane titles, empty and working states) -------------------------
    "canvas.live_tab": {"en": "Now", "ru": "Сейчас", "zh": "当前"},
    "canvas.plan_tab": {"en": "Plan", "ru": "План", "zh": "计划"},
    "canvas.plan_rev": {"en": "Plan r{v}", "ru": "План r{v}", "zh": "计划 r{v}"},
    "canvas.plan_loading": {"en": "Loading…", "ru": "Загрузка…", "zh": "加载中…"},
    "canvas.plan_error": {"en": "Not opened: {error}", "ru": "Не открыто: {error}", "zh": "未打开：{error}"},
    "canvas.nothing_running": {"en": "Nothing is running now.", "ru": "Сейчас ничего не выполняется.",
                               "zh": "现在没有正在运行的任务。"},
    "canvas.plan_footer": {"en": "[p] — plan: goal, planning progress, proposal, approval.",
                           "ru": "[p] — план: цель, ход планирования, предложение, утверждение.",
                           "zh": "[p] — 计划：目标、规划进度、提案、批准。"},
    "canvas.draft_tab": {"en": "Goal draft", "ru": "Черновик цели", "zh": "目标草稿"},
    "canvas.diff_tab": {"en": "Changes {stage}", "ru": "Изменения {stage}", "zh": "改动 {stage}"},
    "canvas.scheme_empty": {"en": "The work scheme appears here once you start a plan.\n\n←→ or a click on a tab "
                                  "switches · / opens commands",
                            "ru": "Здесь появится схема работы, когда ты запустишь план.\n\n←→ или клик по вкладке "
                                  "— переключить · / — команды",
                            "zh": "启动计划后，这里会显示工作流程图。\n\n←→ 或点击标签切换 · / 查看命令"},
    "canvas.draft_intro": {"en": "This is exactly what planning gets — the whole text, no chat:",
                           "ru": "Это получит планировщик — целиком, без чата:",
                           "zh": "规划将收到这段内容——完整、不含对话："},
    "canvas.plan_empty": {"en": "No plan yet.", "ru": "Плана пока нет.", "zh": "还没有计划。"},
    "canvas.plan_empty_hint": {"en": "Tell the architect what you want to do. Once you agree, it offers a goal "
                                     "draft; you say yes, and planning drafts the plan.",
                               "ru": "Расскажи архитектору, что хочешь сделать. Когда договоритесь, он предложит "
                                     "черновик цели; ты скажешь «да» — и планировщик составит план.",
                               "zh": "告诉架构师你想做什么。谈妥后它会给出目标草稿；你说「好」，规划就会制定计划。"},
    "canvas.plan_working": {"en": "The plan is being drafted…", "ru": "План составляется…", "zh": "正在制定计划…"},
    "canvas.plan_working_hint": {"en": "Usually 1–3 minutes. Progress is on the “Scheme” tab.",
                                 "ru": "Обычно 1–3 минуты. Ход — на вкладке «Схема».",
                                 "zh": "通常需要 1–3 分钟。进度见「流程图」标签。"},
    "canvas.log_empty": {"en": "nothing has happened yet", "ru": "пока ничего не происходит",
                         "zh": "暂时还没有任何动态"},
    "canvas.scheme_running": {"en": "{stage} · running", "ru": "{stage} · идёт", "zh": "{stage} · 进行中"},
    "canvas.scheme_merge": {"en": "{stage} · ready, waiting to merge", "ru": "{stage} · готов, ждёт слияния",
                            "zh": "{stage} · 已完成，等待合并"},
    "canvas.scheme_question": {"en": "{stage} · waiting for you", "ru": "{stage} · ждёт тебя", "zh": "{stage} · 等你"},
    "canvas.scheme_error": {"en": "{stage} · stopped: error", "ru": "{stage} · остановлен: ошибка",
                            "zh": "{stage} · 已停止：出错"},
    "canvas.scheme_error_plain": {"en": "Stopped: error", "ru": "Остановлено: ошибка", "zh": "已停止：出错"},
    "canvas.scheme_stopped": {"en": "{stage} · stopped by you", "ru": "{stage} · остановлен вами",
                              "zh": "{stage} · 已被你停止"},
    "canvas.scheme_planning": {"en": "Planning · running", "ru": "Планирование · идёт", "zh": "规划 · 进行中"},
    "canvas.planning_subtitle": {"en": "from the goal draft “{goal}”", "ru": "по черновику цели «{goal}»",
                                 "zh": "根据目标草稿「{goal}」"},
    "canvas.scheme_approve": {"en": "Plan ready · waiting for your yes", "ru": "План готов · ждёт твоего да",
                              "zh": "计划已就绪 · 等待你的确认"},
    "canvas.scheme_approve_auto": {"en": "Plan ready · the architect approves", "ru": "План готов · архитектор утверждает",
                                   "zh": "计划已就绪 · 架构师会批准"},
    "canvas.plan_next_auto": {"en": "Next: the architect approves the plan itself — tell it in the chat what to change",
                              "ru": "Дальше: архитектор утвердит план сам — что изменить, скажи ему в чате",
                              "zh": "下一步：架构师会自行批准计划——要改什么，请在聊天里告诉它"},
    "canvas.scheme_draft": {"en": "Goal draft · not sent yet", "ru": "Черновик цели · ещё не отправлен",
                            "zh": "目标草稿 · 尚未发送"},
    "canvas.scheme_idle": {"en": "notes · nothing runs", "ru": "notes · работы нет", "zh": "notes · 没有任务"},
    "canvas.header_task": {"en": "task", "ru": "задача", "zh": "任务"},
    "canvas.header_tasks": {"en": "tasks", "ru": "задачи", "zh": "任务"},
    "canvas.plan_draft_badge": {"en": "plan draft — waiting for your yes",
                                "ru": "черновик плана — ждёт твоего да",
                                "zh": "计划草稿——等待你的确认"},
    "canvas.stage_merged": {"en": "merged {time}", "ru": "влит {time}", "zh": "已合并 {time}"},
    "canvas.stage_ready_merge": {"en": "ready, waiting to merge", "ru": "готов, ждёт слияния",
                                 "zh": "已完成，等待合并"},
    "canvas.final_merge_line": {"en": "final check → merge into main (your ok)",
                                "ru": "итоговая проверка → слияние в main (твоё ok)",
                                "zh": "最终检查 → 合并进 main（需你确认）"},
    "canvas.task_accepted": {"en": "accepted", "ru": "принята", "zh": "已通过"},
    "canvas.task_review_round": {"en": "review, round {n} of {max}", "ru": "ревью, раунд {n} из {max}",
                                 "zh": "评审，第 {n}/{max} 轮"},
    "canvas.plan_hint": {"en": "Ask the architect for each task's requirements and checks.",
                         "ru": "Требования и проверки каждой задачи — спроси архитектора.",
                         "zh": "每个任务的需求和检查问架构师。"},
    "canvas.view_cut": {"en": "file cut: the first {shown} of {total} KB", "ru": "файл урезан: первые {shown} "
                                                                                "из {total} КБ",
                        "zh": "文件已截断：显示前 {shown}/{total} KB"},
    "canvas.diff_empty": {"en": "no changes", "ru": "изменений нет", "zh": "没有改动"},
    # Observation captions: the titles/details the lab's `_scheme` puts on a scheme node (work.py:552-555, 570,
    # 574); flowdraw draws them as a node title or word. Generic copy, so the scheme shows them translated.
    "canvas.obs_plan_rounds": {"en": "plan rounds", "ru": "раунды плана", "zh": "计划轮次"},
    "canvas.obs_reading_code": {"en": "reading the code", "ru": "читает код", "zh": "读取代码"},
    "canvas.obs_checking_goal": {"en": "checking against the goal", "ru": "сверяет с целью", "zh": "与目标核对"},
    "canvas.obs_waiting_you": {"en": "waiting for you", "ru": "ждёт тебя", "zh": "等你"},
    "canvas.obs_model_no_answer": {"en": "the model did not answer", "ru": "модель не ответила", "zh": "模型未响应"},

    # ---- Counts (lab: "2 tasks", "5 tasks", "2 checks", the "3 stages · 9 tasks" plan title) ---
    # The three nouns the lab shows keep the forms it prints (Russian in the ru column); nothing selects among them (plural rules are
    # out of scope), so a caller names the id whose form its fixture prints.
    "canvas.count_task_one": {"en": "{n} task", "ru": "{n} задача", "zh": "{n} 个任务"},
    "canvas.count_task_few": {"en": "{n} tasks", "ru": "{n} задачи", "zh": "{n} 个任务"},
    "canvas.count_task_many": {"en": "{n} tasks", "ru": "{n} задач", "zh": "{n} 个任务"},
    "canvas.count_check_one": {"en": "{n} check", "ru": "{n} проверка", "zh": "{n} 项检查"},
    "canvas.count_check_few": {"en": "{n} checks", "ru": "{n} проверки", "zh": "{n} 项检查"},
    "canvas.count_check_many": {"en": "{n} checks", "ru": "{n} проверок", "zh": "{n} 项检查"},
    "canvas.count_stage_one": {"en": "{n} stage", "ru": "{n} этап", "zh": "{n} 个阶段"},
    "canvas.count_stage_few": {"en": "{n} stages", "ru": "{n} этапа", "zh": "{n} 个阶段"},
    "canvas.count_stage_many": {"en": "{n} stages", "ru": "{n} этапов", "zh": "{n} 个阶段"},

    # ---- Bar (lab: the job phrase, key labels and the quit note) ---------------------------------
    "bar.job_planning": {"en": "drafting the plan {clock}", "ru": "план составляется {clock}",
                         "zh": "正在制定计划 {clock}"},
    "bar.waiting_approve": {"en": "the plan waits for your yes", "ru": "план ждёт твоего да",
                            "zh": "计划等待你的确认"},
    "bar.approving_plan": {"en": "the architect approves the plan", "ru": "архитектор утверждает план",
                           "zh": "架构师正在批准计划"},
    "bar.waiting_merge": {"en": "{stage} waits to merge", "ru": "{stage} ждёт слияния", "zh": "{stage} 等待合并"},
    "bar.waiting_question": {"en": "{stage} waits for your decision", "ru": "{stage} ждёт твоего решения",
                             "zh": "{stage} 等待你的决定"},
    "bar.stopped_error": {"en": "{stage} stopped: error · /status", "ru": "{stage} остановлен: ошибка · /status",
                          "zh": "{stage} 已停止：出错 · /status"},
    "bar.error_plain": {"en": "stopped: error · /status", "ru": "остановлено: ошибка · /status",
                        "zh": "已停止：出错 · /status"},
    "bar.stopped_owner": {"en": "{stage} stopped by you", "ru": "{stage} остановлен вами",
                          "zh": "{stage} 已被你停止"},
    "bar.idle": {"en": "nothing runs", "ru": "работы нет", "zh": "没有任务"},
    "bar.architect": {"en": "the architect is replying", "ru": "архитектор отвечает", "zh": "架构师正在回复"},
    "bar.key_tabs": {"en": "tabs", "ru": "вкладки", "zh": "标签"},
    "bar.key_commands": {"en": "commands", "ru": "команды", "zh": "命令"},
    "bar.key_complete": {"en": "complete", "ru": "дополнить", "zh": "补全"},
    "bar.key_pick": {"en": "pick", "ru": "выбрать", "zh": "选择"},
    "bar.key_close": {"en": "close", "ru": "закрыть", "zh": "关闭"},
    "bar.key_quit": {"en": "quit", "ru": "выйти", "zh": "退出"},
    "bar.continue": {"en": "(the work continues)", "ru": "(работа продолжится)", "zh": "（任务继续）"},

    # ---- Command descriptions (lab COMMANDS; the names stay English) -----------------------------
    "cmd.plan": {"en": "plan a goal: /plan <goal>", "ru": "спланировать цель: /plan <цель>",
                 "zh": "为目标制定计划：/plan <目标>"},
    "cmd.approve": {"en": "approve the plan or a decision on a card", "ru": "утвердить план или решение на карточке",
                    "zh": "批准卡片上的计划或决定"},
    "cmd.decline": {"en": "decline the card", "ru": "отказаться от карточки", "zh": "拒绝该卡片"},
    "cmd.view": {"en": "open the plan screen", "ru": "открыть экран плана", "zh": "打开计划界面"},
    "cmd.run": {"en": "start the next stage", "ru": "запустить следующий этап", "zh": "启动下一个阶段"},
    "cmd.attempt": {"en": "open the selected stage's attempt (a running one is watched again)",
                    "ru": "открыть попытку выбранного этапа (идущая снова под наблюдением)",
                    "zh": "打开所选阶段的尝试（运行中的会重新被观察）"},
    "cmd.answer": {"en": "open the answer draft of the selected stage", "ru": "открыть черновик ответа выбранного этапа",
                   "zh": "打开所选阶段的回答草稿"},
    "cmd.merge": {"en": "merge the finished stage into main", "ru": "влить готовый этап в main",
                  "zh": "把已完成的阶段合并进 main"},
    "cmd.diff": {"en": "show the stage's changes on the right", "ru": "показать изменения этапа справа",
                 "zh": "在右侧显示本阶段的改动"},
    "cmd.open": {"en": "open a file on the right (view only): /open AGENTS.md",
                 "ru": "открыть файл справа (только просмотр): /open AGENTS.md",
                 "zh": "在右侧打开文件（只读）：/open AGENTS.md"},
    "cmd.log": {"en": "show the tail of the run log", "ru": "показать конец журнала прогона",
                "zh": "显示运行日志的末尾"},
    "cmd.details": {"en": "outcome first, then the plan and diagnostics", "ru": "итог, затем план и диагностика",
                    "zh": "先看结果，再看计划和诊断"},
    "cmd.retry": {"en": "try the failed step again (the card's «new attempt»)",
                  "ru": "повторить сорвавшийся шаг (кнопка «новая попытка» на карточке)",
                  "zh": "重试失败的步骤（卡片上的“新的尝试”按钮）"},
    "cmd.scheme": {"en": "the block scheme on the whole screen (again or esc: back)",
                   "ru": "блок-схема на весь экран (снова или esc: назад)",
                   "zh": "全屏显示流程图（再次输入或按 esc 返回）"},
    "cmd.status": {"en": "what the work and the engine are doing", "ru": "что с работой и с движком",
                   "zh": "查看任务和引擎的状态"},
    "cmd.stop": {"en": "stop the current work", "ru": "остановить текущую работу", "zh": "停止当前工作"},
    "cmd.language": {"en": "UI language", "ru": "язык интерфейса: English · Русский · 中文",
                     "zh": "界面语言：English · Русский · 中文"},
    "cmd.theme": {"en": "colours: auto, dark or light", "ru": "цвета: auto, dark или light",
                  "zh": "配色：auto、dark 或 light"},
    "cmd.new": {"en": "a fresh architect session (the plan and STATE carry over)",
                "ru": "новая сессия архитектора (план и STATE переносятся)",
                "zh": "新的架构师会话（计划和 STATE 会保留）"},
    "cmd.setup": {"en": "set up the project and sign-in", "ru": "настройка проекта и входа",
                  "zh": "设置项目和登录"},
    "cmd.help": {"en": "what the screen can do", "ru": "что умеет экран", "zh": "本屏能做什么"},
    "cmd.quit": {"en": "quit (the work continues)", "ru": "выйти (работа продолжится)", "zh": "退出（任务继续）"},

    # ---- Notes (the warning lines) ---------------------------------------------------------------
    "note.language": {"en": "Language: {name}", "ru": "Язык: {name}", "zh": "语言：{name}"},
    "note.merge_waiting": {
        "en": "the merge check is reviewing {stage}; zplan merges when it says go",
        "ru": "проверка слияния смотрит {stage}; zplan сольёт, когда она скажет «можно»",
        "zh": "合并检查正在审查 {stage}；它放行后 zplan 会合并"},
    "note.merge_already": {
        "en": "Already waiting: the merge check is reviewing {stage}; zplan merges when it says go",
        "ru": "Уже жду: проверка слияния смотрит {stage}; zplan сольёт, когда она скажет «можно»",
        "zh": "已在等待：合并检查正在审查 {stage}；它放行后 zplan 会合并"},
    "note.theme": {"en": "Theme: {name}", "ru": "Тема: {name}", "zh": "主题：{name}"},
    "note.bad_theme": {"en": "unknown theme: auto, dark or light", "ru": "неизвестная тема: auto, dark или light",
                       "zh": "未知主题：auto、dark 或 light"},
    "note.turn_cancelled": {"en": "The architect's reply was cancelled.", "ru": "Ответ архитектора отменён.",
                            "zh": "架构师的回复已取消。"},
    "note.only_russian": {"en": "Only Russian is available for now", "ru": "Пока доступен только русский язык",
                          "zh": "目前仅支持俄语"},
    "note.language_prompt": {"en": "Interface language", "ru": "Язык интерфейса", "zh": "界面语言"},
    "note.unknown_command": {"en": "no such command {name} · /help lists them",
                             "ru": "нет команды {name} · /help — список",
                             "zh": "没有命令 {name} · /help 查看列表"},
    "note.not_now": {"en": "{name}: nothing to do now — no card has this action",
                     "ru": "{name}: сейчас нечего — нет карточки с этим действием",
                     "zh": "{name}：现在无事可做——没有卡片带这个操作"},
    "note.not_in_lab": {"en": "{name}: not shown in the lab", "ru": "{name}: в лабе не показано",
                        "zh": "{name}：实验室中未展示"},
    "note.no_plan": {"en": "no plan yet — /plan <goal>", "ru": "плана нет — /plan <цель>",
                     "zh": "还没有计划——/plan <目标>"},
    "note.plan_needs_goal": {"en": "write /plan <goal>", "ru": "напишите /plan <цель>",
                             "zh": "请写 /plan <目标>"},
    "note.needs_arg": {"en": "{name}: give a path, e.g. /open AGENTS.md",
                       "ru": "{name}: укажи путь, например /open AGENTS.md",
                       "zh": "{name}：请给出路径，例如 /open AGENTS.md"},
    "note.bad_language": {"en": "unsupported language",
                          "ru": "язык не поддерживается: English · Русский · 中文",
                          "zh": "不支持的语言：English · Русский · 中文"},
    "note.view_empty": {"en": "the file is empty", "ru": "файл пуст", "zh": "文件为空"},
    "note.view_outside": {"en": "file outside the project: {name}", "ru": "файл вне проекта: {name}",
                          "zh": "文件在项目之外：{name}"},
    "note.view_missing": {"en": "no such file: {name}", "ru": "нет такого файла: {name}",
                          "zh": "没有这个文件：{name}"},
    "note.view_directory": {"en": "this is a directory: {name}", "ru": "это папка: {name}",
                            "zh": "这是一个目录：{name}"},
    "note.view_binary": {"en": "binary file: {name}", "ru": "двоичный файл: {name}", "zh": "二进制文件：{name}"},
    "note.files_running": {"en": "files open when no work is running: {what} is running now",
                           "ru": "файлы открываются, когда работа стоит: сейчас идёт {what}",
                           "zh": "只有在没有任务运行时才能打开文件：{what} 正在进行"},
    "note.palette_empty": {"en": "no such command · /help", "ru": "нет такой команды · /help",
                           "zh": "没有这个命令 · /help"},
}


def store_path() -> Path:
    """The UI settings file: with the user's zplan preferences, never with the project or the engine."""
    return setup.config_root() / FILENAME


def display_name(code: str) -> str:
    return DISPLAY_NAMES[code]


def default_language(environ=None) -> str:
    """The language the terminal locale asks for: `ru*` -> ru, `zh*` -> zh, anything else -> en."""
    values = os.environ if environ is None else environ
    for name in LOCALE_VARS:
        value = (values.get(name) or "").strip().lower()
        if value:
            return "ru" if value.startswith("ru") else "zh" if value.startswith("zh") else DEFAULT
    return DEFAULT


def _data():
    """What `ui.json` holds, or {} when nothing usable is stored (missing, unreadable or not an object)."""
    try:
        data = decode(store_path().read_text(encoding="utf-8"))
    except (Blocked, OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _stored():
    """The saved code, or None when nothing usable is stored (missing, unreadable or unknown)."""
    code = _data().get("language")
    return code if code in LANGUAGES else None


def stored_theme():
    """The saved theme (dark, light or auto), or None when nothing usable is stored."""
    code = _data().get("theme")
    return code if code in THEMES else None


def language() -> str:
    """The current language: what was chosen and stored, else the locale default; one outside `OFFERED` reads as the
    first offered language."""
    code = _stored() or default_language()
    return code if code in OFFERED else OFFERED[0]


def set_language(code: str) -> None:
    """Switch the language at once and store it. An unknown code is a programming error."""
    if code not in LANGUAGES:
        raise ValueError("unknown UI language: %r" % (code,))
    _store(language=code)


def set_theme(code: str) -> None:
    """Store the theme (dark, light or auto), keeping the rest of `ui.json`. An unknown code is a programming error."""
    if code not in THEMES:
        raise ValueError("unknown UI theme: %r" % (code,))
    _store(theme=code)


def _store(**changes) -> None:
    """Write `ui.json` with `changes` over what it holds, atomically."""
    root = setup.config_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=root, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(canonical({**_data(), **changes}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, root / FILENAME)
        finally:
            temporary.unlink(missing_ok=True)


def text(id, **values) -> str:
    """The current language's text for `id`, with `values` substituted by placeholder name.

    A missing translation falls back to EN; an unknown id is a programming error (KeyError). The colon part of a
    clock placeholder (`{m:ss}`) is GLOSSARY spelling and is not applied as a format spec. A placeholder the caller
    gives no value for is left verbatim (`{name}`), so the renderer's own `words=strings.text` may format it.
    """
    entry = CATALOG[id]
    template = entry.get(language()) or entry[DEFAULT]
    return _FIELD.sub(lambda match: str(values[match.group(1)]) if match.group(1) in values else match.group(0),
                      template)
