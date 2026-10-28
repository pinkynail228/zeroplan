"""UI lab: the work screen (chat left, canvas + activity log right). Fixtures only.

A walkable story: first open -> goal draft card -> planning -> plan approval -> the stage runs
-> merge decision; plus a question and an error state. Text, buttons and `/` commands move it on;
ctrl+t (lab only) jumps to the next state. Run: devtools/ui-lab/run.sh work.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Static

import flowdraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SPIN = "◐◓◑◒"

# Role colours (terminal ANSI palette) and plain-word names.
ROLE = {
    "arch": ("архитектор", "magenta"),
    "plan": ("планирование", "magenta"),
    "work": ("исполнитель", "yellow"),
    "acc": ("ревью: приёмка", "cyan"),
    "code": ("ревью: код", "blue"),
    "final": ("итоговая проверка", "green"),
    "merge": ("слияние", "white"),
    "err": ("ошибка", "red"),
}

# Fixture timeline of the running stage: node states + the log line each step adds.
STEPS = [
    dict(t=3, round=1, work=("run", "пишет код"), acc="wait", code="wait",
         log=("work", "T3 · начал: формат дат в ISO 8601")),
    dict(t=3, round=1, work=("run", "запускает тесты"), acc="wait", code="wait",
         log=("work", "T3 · pytest tests/test_export.py — 12 пройдено")),
    dict(t=3, round=1, work=("done", "готово"), acc="run", code="run",
         log=("work", "T3 · передал на ревью")),
    dict(t=3, round=1, work=("done", "готово"), acc="done", code="run",
         log=("acc", "T3 · одобрено: требование R2 выполнено")),
    dict(t=3, round=1, work=("done", "готово"), acc="done", code="fail",
         log=("code", "T3 · отклонено: нет теста на пустой отчёт")),
    dict(t=3, round=2, work=("run", "доработка"), acc="wait", code="wait",
         log=("work", "T3 · доработка, раунд 2 из 3")),
    dict(t=3, round=2, work=("done", "готово"), acc="run", code="run",
         log=("work", "T3 · снова на ревью")),
    dict(t=3, round=2, work=("done", "готово"), acc="done", code="done",
         log=("code", "T3 · одобрено")),
    dict(t=4, round=1, work=("run", "пишет код"), acc="wait", code="wait",
         log=("work", "T4 · начал: выгрузка по кнопке")),
    dict(t=4, round=1, work=("run", "пишет код"), acc="wait", code="wait", log=None),
]
STEP_SECONDS = 4
PLANNING_SECONDS = 12
MILESTONE_GRAPH = json.loads((HERE / "fixtures" / "milestone-graph.json").read_text())
PLANNER_GRAPH = json.loads((HERE / "fixtures" / "planner-graph.json").read_text())

TASKS = [("T1", "Модель строки отчёта"), ("T2", "Сериализация в CSV"), ("T3", "Даты в ISO 8601"),
         ("T4", "Выгрузка по кнопке"), ("T5", "Тест большого отчёта")]

STATES = ["empty", "draft", "planning", "approve", "running", "merge", "question", "error"]

DRAFT = """Экспорт отчётов в CSV.

Формат: UTF-8, заголовок по колонкам отчёта, разделитель — запятая.
Даты в ISO 8601 (2026-10-22T21:51:00).
Большой отчёт (100 000 строк) не блокирует экран: выгрузка в фоне,
кнопка «Экспорт» неактивна, пока выгрузка идёт.

Этапы: сначала модель строки отчёта, потом сам экспорт, потом документация.

Допущения архитектора — проверь:
- пустой отчёт даёт файл только с заголовком;
- имя файла: report-ГГГГ-ММ-ДД.csv.

Проверка: pytest -q проходит; тест на 100 000 строк укладывается в 5 с."""

DIFF = """ src/export.py        | 41 +++++++++++++++++++++++++++
 src/report.py        |  6 ++--
 tests/test_export.py | 58 +++++++++++++++++++++++++++++++++++++++
 3 files changed, 102 insertions(+), 3 deletions(-)

diff --git a/src/report.py b/src/report.py
@@ -12,7 +12,7 @@ class Row:
-    created: str
+    created: datetime
     amount: Decimal
-    def as_list(self):
-        return [self.id, self.created, str(self.amount)]
+    def as_list(self):
+        return [self.id, self.created.isoformat(), str(self.amount)]
diff --git a/src/export.py b/src/export.py
@@ -0,0 +1,41 @@
+import csv
+from pathlib import Path
+
+def export(rows, path: Path) -> int:
+    with path.open("w", newline="", encoding="utf-8") as out:
+        writer = csv.writer(out)
+        writer.writerow(HEADER)
+        count = 0
+        for row in rows:
+            writer.writerow(row.as_list())
+            count += 1
+    return count
"""

# `/` commands: English names, Russian descriptions (GLOSSARY.md: command names stay English).
COMMANDS = [
    ("/plan", "составить план из черновика цели"),
    ("/approve", "утвердить план или решение на карточке"),
    ("/decline", "отказаться от карточки"),
    ("/merge", "влить готовый этап в main"),
    ("/diff", "показать изменения этапа справа"),
    ("/open", "открыть файл справа (только просмотр): /open AGENTS.md"),
    ("/status", "что с работой и с движком"),
    ("/stop", "остановить текущую работу"),
    ("/language", "язык интерфейса: English · Русский · 中文"),
    ("/setup", "настройка проекта и входа"),
    ("/help", "что умеет экран"),
    ("/quit", "выйти (работа продолжится)"),
]


def bar(done: int, total: int, width: int = 10) -> list:
    full = round(width * done / total) if total else 0
    return [("▰" * full, "yellow"), ("▱" * (width - full), "dim"), (f" {done}/{total}", "")]


class Tabs(Static):
    """The canvas tab strip; a click picks the tab under the mouse."""

    def on_click(self, event) -> None:
        if event.y == 0:
            self.app.pick_tab_at(event.x)


class Work(App):
    CSS_PATH = "work.tcss"
    BINDINGS = [("ctrl+q", "quit", "выйти"), Binding("left", "view(-1)", "", priority=True),
                Binding("right", "view(1)", "", priority=True), Binding("escape", "close_tab", "", priority=True),
                ("ctrl+t", "next_state", "")]

    def __init__(self) -> None:
        super().__init__(watch_css=True, ansi_color=True)
        self._sources = {p: p.stat().st_mtime for p in (Path(__file__), HERE / "flowdraw.py")}
        self.tick = 0
        self.started = time.monotonic()
        self.state = "empty"
        self.state_started = time.monotonic()
        self.chat: list = []
        self.log_rows: list[tuple[str, str, str]] = []
        self.step_index = -1
        self.step_started = time.monotonic()
        self.extra_tabs: list[tuple[str, str]] = []   # ("file:AGENTS.md", "AGENTS.md") / ("diff", "Изменения M2")
        self.tab = "scheme"
        self.tab_spans: list[tuple[int, int, str]] = []
        self.narrow = False
        self.typed_goal = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="chat-pane"):
                yield VerticalScroll(id="messages-scroll")
                yield Static(id="palette")
                with Horizontal(id="prompt-box"):
                    yield Static("›", id="chevron")
                    yield Input(placeholder="Напиши архитектору… или / для команд", id="prompt")
            with Vertical(id="right"):
                with Vertical(id="flow-pane"):
                    yield Tabs(id="legend")
                    yield VerticalScroll(Static(id="view"), id="view-scroll")
                yield Static(id="log-pane")
        yield Static(id="bar")

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.query_one("#chat-pane").border_title = "Разговор с архитектором"
        self.query_one("#log-pane").border_title = "Что происходит"
        self.query_one("#palette").display = False
        self.set_state("empty")
        self.set_interval(STEP_SECONDS, self._next_step)
        self.set_interval(0.15, self._frame)
        self.set_interval(0.5, self._reload_if_changed)
        self.query_one("#prompt", Input).focus()

    # ── story ───────────────────────────────────────────────────────────

    def clock(self) -> str:
        # Fixture clock: the story is set at 21:51 tonight, then runs in real time.
        now = 21 * 3600 + 51 * 60 + int(time.monotonic() - self.started)
        return f"{now // 3600:02}:{now // 60 % 60:02}"

    def say(self, who: str, text: str) -> None:
        self.chat.append((who, self.clock(), text))

    def event(self, who: str, text: str) -> None:
        now = 21 * 3600 + 51 * 60 + int(time.monotonic() - self.started)
        self.log_rows.append((f"{now // 3600:02}:{now // 60 % 60:02}:{now % 60:02}", who, text))
        self.step_started = time.monotonic()

    def set_state(self, state: str) -> None:
        """Enter a story state: rebuild the chat, the log and the default canvas tab for it."""
        self.state = state
        self.state_started = self.step_started = time.monotonic()
        goal = self.typed_goal or ("owner", "21:02", "Хочу экспорт отчётов в CSV. Даты — в ISO, и чтобы большой отчёт не вешал экран.")
        reply = ("arch", "21:03", "Понял. Предлагаю три этапа: модель строки, сам экспорт, документация. "
                                  "Черновик цели — справа целиком: ровно этот текст получит планировщик.")
        sent = ("card", "21:04", dict(title="Черновик цели", done="✓ отправлен планировщику 21:04"))
        approved = ("card", "21:05", dict(title="План · 3 этапа · 9 задач", done="✓ утверждён 21:05"))
        running = [("arch", "21:38", "M1 «Модель отчёта» прошёл ревью и влит в main."),
                   ("arch", "21:39", "Запустил M2 «Экспорт CSV». Пять задач, каждую смотрят два ревьюера. "
                                     "Напишу сюда, если понадобится твоё решение.")]
        self.chat = {
            "empty": [("arch", "21:01", "Привет. Расскажи, что хочешь сделать в проекте — обсудим и "
                                        "составим план. Пока ты не скажешь «да», ничего не запускается.")],
            "draft": [goal, reply, ("card", "21:03", dict(
                title="Черновик цели", text="Составить план из этого черновика? Полный текст — во вкладке «Черновик цели».",
                buttons=[("да, составить план", "/plan"), ("нет", "/decline")]))],
            "planning": [goal, reply, sent, ("arch", "21:04", "Планировщик составляет план, проверка сверит его "
                                                             "с целью. Обычно 1–3 минуты; схема — справа.")],
            "approve": [goal, reply, sent, ("card", "21:05", dict(
                title="План · 3 этапа · 9 задач", text="План проверен и покрывает цель. Утвердить? "
                                                       "Справа — вкладка «План».",
                buttons=[("да, утвердить", "/approve"), ("нет, доработать", "/decline")]))],
            "running": [goal, reply, sent, approved] + running,
            "merge": [goal, reply, sent, approved] + running + [("card", "22:06", dict(
                title="M2 Экспорт CSV готов", text="5 из 5 задач приняты, итоговая проверка пройдена. "
                                                  "Влить в main?",
                buttons=[("влить", "/merge"), ("посмотреть изменения", "/diff")]))],
            "question": [goal, reply, sent, approved] + running + [("card", "21:58", dict(
                title="Нужно твоё решение · T3", text="Ревью отклонило T3 четыре раза подряд: нет теста на "
                                                     "пустой отчёт, исполнитель не справляется. Что делаем? "
                                                     "",
                hint="или ответь словами, например: «убери тест, сделаем в M3»",
                buttons=[("упростить", "/approve"), ("разбить", "/approve"), ("пропустить", "/decline")]))],
            "error": [goal, reply, sent, approved] + running + [("card", "21:57", dict(
                title="! Ошибка · T3", text="Исполнитель остановился: модель не ответила за 10 минут "
                                           "(выход 1). Остальное цело, ветка на месте.",
                buttons=[("новая попытка", "/approve"), ("подробнее", "/status")]))],
        }[state]
        self.log_rows = {
            "empty": [], "draft": [],
            "planning": [("21:04:02", "plan", "начал: план по черновику цели")],
            "approve": [("21:04:02", "plan", "начал: план по черновику цели"),
                        ("21:04:51", "plan", "проверка плана: покрывает цель"),
                        ("21:05:00", "plan", "план готов · 3 этапа · 9 задач")],
        }.get(state, [("21:39:02", "arch", "M2 · запущен, 5 задач"),
                      ("21:40:10", "work", "T1 · принята обоими ревьюерами"),
                      ("21:46:31", "work", "T2 · принята обоими ревьюерами")])
        if state == "merge":
            self.log_rows += [("22:04:40", "final", "итоговая проверка пройдена"),
                              ("22:06:02", "merge", "ждёт твоего ok на слияние")]
        if state == "question":
            self.log_rows += [("21:58:10", "code", "T3 · отклонено 4-й раз: нет теста на пустой отчёт"),
                              ("21:58:11", "arch", "T3 остановлена, ждёт твоего решения")]
        if state == "error":
            self.log_rows += [("21:57:30", "err", "T3 · исполнитель: модель не ответила за 10 мин (выход 1)")]
        if state in ("planning", "running"):
            # Files are shown only while no work runs (owner decision 2026-10-22).
            self.extra_tabs = [t for t in self.extra_tabs if not t[0].startswith("file:")]
        self.step_index = -1
        if state == "running":
            self._next_step()
        self.tab = {"draft": "draft", "approve": "plan", "merge": "scheme"}.get(state, "scheme")
        if self.narrow and (state == "empty" or self.chat[-1][0] == "card"):
            self.tab = "chat"
        self._render_chat()
        self._render_all()

    def action_next_state(self) -> None:
        self.set_state(STATES[(STATES.index(self.state) + 1) % len(STATES)])

    @property
    def step(self) -> dict:
        return STEPS[max(0, self.step_index)]

    def _next_step(self) -> None:
        if self.state == "planning" and time.monotonic() - self.state_started >= PLANNING_SECONDS:
            self.set_state("approve")
            return
        if self.state != "running":
            return
        self.step_index += 1
        if self.step_index == len(STEPS):
            self.set_state("merge")
            return
        self.step_started = time.monotonic()
        if self.step["log"]:
            self.event(*self.step["log"])

    # ── input: text, commands, buttons ──────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        palette = self.query_one("#palette", Static)
        value = event.value
        if not value.startswith("/"):
            palette.display = False
            return
        word = value.split()[0]
        found = [(c, d) for c, d in COMMANDS if c.startswith(word)] or [("", "нет такой команды · /help")]
        text = Text()
        for i, (cmd, desc) in enumerate(found[:7]):
            if i:
                text.append("\n")
            text.append(f"{cmd:<11}", style="bold yellow")
            text.append(desc, style="dim")
        text.no_wrap, text.overflow = True, "ellipsis"
        palette.update(text)
        palette.display = True

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        event.input.value = ""
        self.query_one("#palette").display = False
        if not value:
            return
        if value.startswith("/"):
            self.command(value)
            return
        self.say("owner", value)
        if self.state == "empty":
            self.typed_goal = self.chat[-1]
            self.set_timer(1.5, lambda: self.set_state("draft"))
        else:
            self.set_timer(1.5, lambda: (self.say("arch", "Понял. (лаб: ответ архитектора)"), self._render_chat()))
        self._render_chat()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.command(event.button.name or "")

    def command(self, line: str) -> None:
        cmd, _, arg = line.partition(" ")
        moves = {("/plan", "draft"): "planning", ("/approve", "approve"): "running",
                 ("/approve", "question"): "running", ("/approve", "error"): "running",
                 ("/decline", "draft"): "empty", ("/decline", "approve"): "draft",
                 ("/decline", "question"): "running"}
        if (cmd, self.state) in moves:
            self.set_state(moves[(cmd, self.state)])
        elif cmd == "/merge" and self.state == "merge":
            self.set_state("empty")
            self.say("arch", "M2 влит в main (коммит 7096c3c). Дальше по плану M3 «Документация» — запустить?")
            self._render_chat()
        elif cmd == "/diff":
            self.open_tab("diff", "Изменения M2")
        elif cmd == "/open" and self.state in ("planning", "running"):
            self.note("файлы открываются, когда работа стоит: сейчас идёт " +
                      ("планирование" if self.state == "planning" else "M2"))
        elif cmd == "/open":
            path = (REPO / arg.strip()) if arg.strip() else None
            if path and path.is_file():
                self.open_tab(f"file:{arg.strip()}", arg.strip())
            else:
                self.note(f"нет такого файла: {arg.strip() or '— укажи путь: /open AGENTS.md'}")
        elif cmd == "/quit":
            self.exit()
        elif cmd in dict(COMMANDS):
            self.note(f"{cmd}: в лабе не показано" if cmd not in ("/plan", "/approve", "/decline", "/merge")
                      else f"{cmd}: сейчас нечего — нет карточки с этим действием")
        else:
            self.note(f"нет команды {cmd} · /help — список")

    def note(self, text: str) -> None:
        self.say("sys", text)
        self._render_chat()

    # ── canvas tabs ─────────────────────────────────────────────────────

    def tabs(self) -> list[tuple[str, str]]:
        base = [("chat", "Разговор")] if self.narrow else []
        base += [("scheme", "Схема"), ("plan", "План")]
        if self.state == "draft":
            base.append(("draft", "Черновик цели"))
        return base + self.extra_tabs

    def open_tab(self, key: str, label: str) -> None:
        if (key, label) not in self.extra_tabs:
            self.extra_tabs.append((key, label))
        self.tab = key
        self._render_all()

    def action_close_tab(self) -> None:
        palette = self.query_one("#palette")
        if palette.display:
            palette.display = False
            self.query_one("#prompt", Input).value = ""
            return
        if self.tab.startswith(("file:", "diff")):
            self.extra_tabs = [t for t in self.extra_tabs if t[0] != self.tab]
            self.tab = "scheme"
            self._render_all()

    def action_view(self, delta: int) -> None:
        prompt = self.query_one("#prompt", Input)
        if self.focused is prompt and prompt.value:
            # While typing, arrows keep moving the text cursor.
            prompt.action_cursor_right() if delta > 0 else prompt.action_cursor_left()
            return
        keys = [k for k, _ in self.tabs()]
        self.tab = keys[(keys.index(self.tab) + delta) % len(keys)] if self.tab in keys else keys[0]
        self._render_all()

    def pick_tab_at(self, x: int) -> None:
        for start, end, key in self.tab_spans:
            if start <= x < end:
                self.tab = key
                self._render_all()

    # ── rendering ───────────────────────────────────────────────────────

    def _fit(self) -> None:
        narrow = self.size.width < 100
        if narrow != self.narrow:
            self.narrow = narrow
            self.tab = "chat" if narrow else ("scheme" if self.tab == "chat" else self.tab)
            self._render_all()

    def _frame(self) -> None:
        self.tick += 1
        self._fit()
        self._render_all()

    def _render_all(self) -> None:
        self.screen.set_class(self.narrow, "narrow")
        self.query_one("#chat-pane").display = not self.narrow or self.tab == "chat"
        self.query_one("#right").display = not self.narrow or self.tab != "chat"
        self.query_one("#chat-pane").border_title = ("Разговор · ←→ вкладки" if self.narrow
                                                      else "Разговор с архитектором")
        self._render_view()
        self._render_log()
        self._render_bar()

    def _render_chat(self) -> None:
        scroll = self.query_one("#messages-scroll", VerticalScroll)
        scroll.remove_children()
        widgets = []
        for who, at, body in self.chat:
            if who == "owner":
                widgets.append(Static(Text.assemble(("ты", "bold"), (f" · {at}\n", "dim"), body), classes="msg owner"))
            elif who == "arch":
                widgets.append(Static(Text.assemble(("архитектор", "bold magenta"), (f" · {at}\n", "dim"), body),
                                      classes="msg arch"))
            elif who == "sys":
                widgets.append(Static(Text(body, style="dim italic"), classes="msg sys"))
            else:
                widgets.append(self._card(at, body))
        scroll.mount_all(widgets)
        self.call_after_refresh(lambda: scroll.scroll_end(animate=False))

    def _card(self, at: str, card: dict) -> Vertical:
        parts = []
        if card.get("done"):
            parts.append(Static(Text(card["done"], style="green"), classes="card-text"))
        else:
            parts.append(Static(card["text"], classes="card-text"))
            parts.append(Horizontal(*[Button(label, name=cmd, compact=True, classes="first" if i == 0 else "")
                                      for i, (label, cmd) in enumerate(card["buttons"])], classes="buttons"))
            hint = card.get("hint") or "или " + " · ".join(cmd for _, cmd in card["buttons"])
            parts.append(Static(Text(hint, style="dim"), classes="card-hint"))
        box = Vertical(*parts, classes="card" + (" done" if card.get("done") else " open")
                       + (" alarm" if card["title"].startswith("!") else ""))
        box.border_title = card["title"]
        box.border_subtitle = at
        return box

    def _tab_strip(self) -> Text:
        strip = Text()
        self.tab_spans = []
        for i, (key, label) in enumerate(self.tabs()):
            if i:
                strip.append("  ")
            start = strip.cell_len
            close = " ×" if key.startswith(("file:", "diff")) else ""
            strip.append(f" {label}{close} ", style="reverse bold" if key == self.tab else "dim")
            self.tab_spans.append((start, strip.cell_len, key))
        strip.append("   ←→", style="dim")
        return strip

    def _render_view(self) -> None:
        strip = self._tab_strip()
        pane = self.query_one("#flow-pane")
        st = self.step
        second = Text()
        if self.state in ("running", "question", "error"):
            pane.border_title = "M2 Экспорт CSV · " + {"running": "идёт", "question": "ждёт тебя",
                                                         "error": "остановлен: ошибка"}[self.state]
            second.append("задача ", style="dim")
            second.append(f"T{st['t']} · {TASKS[st['t'] - 1][1]}", style="bold")
            second.append("   задачи ", style="dim")
            second.append_text(Text.assemble(*bar(st["t"] - 1, len(TASKS), 10)))
        elif self.state == "merge":
            pane.border_title = "M2 Экспорт CSV · готов, ждёт слияния"
            second.append_text(Text.assemble(("задачи ", "dim"), *bar(5, 5, 10)))
        elif self.state == "planning":
            pane.border_title = "Планирование · идёт"
            second.append("по черновику цели «Экспорт отчётов в CSV»", style="dim")
        elif self.state == "approve":
            pane.border_title = "План готов · ждёт твоего да"
        elif self.state == "draft":
            pane.border_title = "Черновик цели · ещё не отправлен"
        else:
            pane.border_title = "notes · работы нет"
        strip.append("\n")
        strip.append_text(second)
        strip.no_wrap, strip.overflow = True, "ellipsis"
        self.query_one("#legend", Static).update(strip)
        pane.border_subtitle = Text.assemble(*flowdraw.LEGEND) if self.tab == "scheme" and self._scheme() else ""
        view = self.query_one("#view", Static)
        scroll = self.query_one("#view-scroll")
        width = max(40, scroll.size.width or 80)
        height = max(5, scroll.size.height or 20)
        centered = self.tab == "scheme"
        view.styles.content_align = ("center", "middle") if centered else ("left", "top")
        view.styles.height = "1fr" if centered else "auto"
        if self.tab == "scheme":
            scheme = self._scheme()
            drawn = flowdraw.render(*scheme, width, height, self.tick) if scheme else None
            if drawn is not None:
                drawn.no_wrap, drawn.overflow = True, "ellipsis"
            view.update(drawn if drawn is not None
                        else Text("Здесь появится схема работы, когда ты запустишь план.\n\n"
                                  "←→ или клик по вкладке — переключить · / — команды", style="dim",
                                  justify="center"))
        elif self.tab == "plan":
            view.update(self._plan())
        elif self.tab == "draft":
            view.update(Text.assemble(("Это получит планировщик — целиком, без чата:\n\n", "dim"), DRAFT))
        elif self.tab == "diff":
            view.update(Syntax(DIFF, "diff", theme="ansi_dark", background_color="default"))
        elif self.tab.startswith("file:"):
            path = REPO / self.tab[5:]
            view.update(Syntax(path.read_text(), "markdown" if path.suffix == ".md" else "python",
                               theme="ansi_dark", line_numbers=True, word_wrap=True, background_color="default"))

    def _timer(self) -> str:
        elapsed = int(time.monotonic() - self.step_started)
        return f"{elapsed // 60}:{elapsed % 60:02}"

    def _scheme(self):
        """(graph, observation) for the scheme of the current job, or None when nothing runs."""
        native = {"run": "running", "done": "succeeded", "fail": "failed", "wait": "idle", "error": "failed"}
        if self.state == "planning":
            half = time.monotonic() - self.state_started >= PLANNING_SECONDS / 2
            obs = {"review_loop": {"count": 1, "title": "раунды плана"},
                   "planner": {"state": "succeeded" if half else "running", "detail": None if half else "читает код",
                               "timer": self._timer()},
                   "critic": {"state": "running" if half else "idle", "detail": "сверяет с целью" if half else None,
                              "timer": self._timer()}}
            return PLANNER_GRAPH, obs
        if self.state not in ("running", "merge", "question", "error"):
            return None
        s = self.step
        done = {"state": "succeeded"}
        obs = {"select_init": done, "select": done, "select_verify": done,
               "task_loop": {"count": s["t"]}, "review_loop": {"count": s["round"]}}
        if self.state == "merge":
            obs.update(task_loop={"count": 5}, review_loop={"count": 1}, worker=done, acceptance_review=done,
                       code_review=done, steward_apply=done, steward_decide=done, final_verify=done)
            return MILESTONE_GRAPH, obs
        if self.state == "question":
            obs.update(review_loop={"count": 4}, worker=done, acceptance_review=done,
                       code_review={"state": "failed"}, steward_decide={"state": "running", "detail": "ждёт тебя",
                                                                        "timer": self._timer()})
            return MILESTONE_GRAPH, obs
        if self.state == "error":
            obs.update(worker={"state": "failed", "detail": "модель не ответила"})
            return MILESTONE_GRAPH, obs
        work_state, work_text = s["work"]
        obs["worker"] = {"state": native[work_state], "detail": work_text, "timer": self._timer()}
        for key, name in (("acc", "acceptance_review"), ("code", "code_review")):
            obs[name] = {"state": native[s[key]], "timer": self._timer()}
        return MILESTONE_GRAPH, obs

    def _plan(self) -> Text:
        text = Text()
        if self.state in ("empty", "draft"):
            text.append("Плана пока нет.\n\n", style="bold")
            text.append("Расскажи архитектору, что хочешь сделать. Когда договоритесь, он предложит "
                        "черновик цели; ты скажешь «да» — и планировщик составит план.", style="dim")
            return text
        if self.state == "planning":
            text.append("План составляется…\n\n", style="bold")
            text.append("Обычно 1–3 минуты. Ход — на вкладке «Схема».", style="dim")
            return text
        proposed = self.state == "approve"
        merged = self.state == "merge"
        t = 6 if merged else self.step["t"]
        text.append("Цель  ", style="dim")
        text.append("Экспорт отчётов в CSV", style="bold")
        text.append("   черновик плана — ждёт твоего да\n\n" if proposed else "\n\n", style="yellow")
        text.append("◌ M1 " if proposed else "✓ M1 ", style="dim" if proposed else "green")
        text.append("Модель отчёта".ljust(24))
        text.append("2 задачи\n" if proposed else "влит 21:38\n", style="dim")
        mark = "◌" if proposed else "✓" if merged else SPIN[self.tick % 4]
        text.append(f"{mark} M2 ", style="dim" if proposed else "green" if merged else "bold yellow")
        text.append("Экспорт CSV".ljust(24), style="bold")
        text.append("5 задач\n" if proposed else "готов, ждёт слияния\n" if merged else "идёт\n", style="dim")
        for i, (tid, title) in enumerate(TASKS, 1):
            if proposed:
                m, st, note = "◌", "dim", "2 проверки"
            elif i < t:
                m, st, note = "✓", "green", "принята"
            elif i == t:
                m, st, note = SPIN[self.tick % 4], "yellow", f"ревью, раунд {self.step['round']} из 3"
            else:
                m, st, note = "◌", "dim", ""
            text.append(f"    {m} ", style=st)
            text.append(f"{tid} {title}".ljust(30), style="" if proposed or i <= t else "dim")
            text.append(note + "\n", style="dim")
        text.append("    ◌ ", style="dim")
        text.append("итоговая проверка → слияние в main (твоё ok)\n", style="dim")
        text.append("◌ M3 ", style="dim")
        text.append("Документация".ljust(24), style="dim")
        text.append("2 задачи\n", style="dim")
        if proposed:
            text.append("\nТребования и проверки каждой задачи — спроси архитектора.", style="dim")
        return text

    def _render_log(self) -> None:
        pane = self.query_one("#log-pane", Static)
        rows = max(1, pane.size.height or 4)
        text = Text()
        if not self.log_rows:
            text.append("пока ничего не происходит", style="dim")
        for i, (at, who, body) in enumerate(self.log_rows[-rows:]):
            if i:
                text.append("\n")
            name, color = ROLE[who]
            text.append(f"{at}  ", style="dim")
            text.append(f"{name:<16}", style=f"bold {color}")
            text.append(body, style="red" if who == "err" else "")
        last = self.log_rows[-1][2] if self.log_rows else ""
        quiet = int(time.monotonic() - self.step_started)
        pane.border_subtitle = (f"последнее: {flowdraw.clip(last, 40)} · {quiet // 60}:{quiet % 60:02} назад"
                                if last else "")
        text.no_wrap, text.overflow = True, "ellipsis"
        pane.update(text)

    def _render_bar(self) -> None:
        elapsed = int(time.monotonic() - self.state_started) + (12 * 60 if self.state == "running" else 0)
        clock = f"{elapsed // 3600}:{elapsed // 60 % 60:02}:{elapsed % 60:02}"
        text = Text()
        text.append(" zeroshot-planning-kit", style="bold")
        text.append(" · main   ", style="dim")
        job = {"planning": (SPIN[self.tick % 4] + " ", "yellow", f"план составляется {clock}"),
               "running": (SPIN[self.tick % 4] + " ", "yellow", f"M2 идёт {clock}"),
               "approve": ("● ", "yellow", "план ждёт твоего да"),
               "merge": ("● ", "yellow", "M2 ждёт слияния"),
               "question": ("● ", "yellow", "M2 ждёт твоего решения"),
               "error": ("! ", "bold red", "M2 остановлен: ошибка · /status")}.get(self.state)
        if job:
            text.append(job[0], style=job[1])
            text.append(job[2], style="red" if self.state == "error" else "")
        else:
            text.append("работы нет", style="dim")
        keys = [("←→", "вкладки"), ("/", "команды")]
        if self.tab.startswith(("file:", "diff")):
            keys.append(("esc", "закрыть"))
        keys.append(("ctrl+q", "выйти"))
        for key, label in keys:
            text.append(f"   {key}", style="bold dim")
            text.append(f" {label}", style="dim")
        if job and self.size.width - text.cell_len >= 24:
            text.append("  (работа продолжится)", style="dim")
        text.no_wrap, text.overflow = True, "ellipsis"
        self.query_one("#bar", Static).update(text)

    def _reload_if_changed(self) -> None:
        for path, mtime in self._sources.items():
            if path.stat().st_mtime != mtime:
                self.exit(return_code=3)


if __name__ == "__main__":
    app = Work()
    app.run()
    sys.exit(app.return_code or 0)
