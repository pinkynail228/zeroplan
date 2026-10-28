"""UI lab: the architect chat, v2 (owner 2026-10-27: "readable and convenient"). Fixture states only, no backend.

What changes against 0.6.2 (owner screenshot 2026-10-27 00:05):
- the stream holds only the conversation: no model, provider, CODEX_HOME or usage rows, no stacked notes;
- the owner's lines are a block with an accent bar; the architect's replies are rendered markdown behind one marker;
  no name and clock on every message, one quiet time line where the talk resumes;
- work progress is one plain line per step (✓ ▶ !), decisions are cards; a decided card shrinks to one line;
- "thinking", "running" and short notes live in one line above the input, never in the stream;
- the stream sits on the input (chat order), the empty chat says what to do and offers example goals;
- the bottom bar carries project · branch · state; the model and the token count sit dim at its right end;
- 120+ columns: the plan stays visible at the right; narrower: the chat alone.

Live:     devtools/ui-lab/run.sh chat.py        (ctrl+t / ctrl+y: next / previous state; resize to see the layouts)
Gallery:  build/ui-lab-venv/bin/python devtools/ui-lab/chat.py --gallery DIR   (SVG per state and size + index.html)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.markdown import CodeBlock, Heading, Markdown
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Static

PROJECT = "pixel-arena"
WIDE = 120  # columns from which the plan stays visible beside the chat
SPIN = "◐◓◑◒"


class LeftHeading(Heading):
    """A heading in a chat reply: bold, left, no box (rich centres, frames and underlines them by default)."""

    @classmethod
    def create(cls, markdown, token):
        heading = super().create(markdown, token)
        heading.style_name = "bold"
        return heading

    def __rich_console__(self, console, options):
        self.text.justify = "left"
        self.text.style = "bold"
        yield self.text


class TightCode(CodeBlock):
    """A code block in a chat reply: no padding rows, indented two cells."""

    def __rich_console__(self, console, options):
        yield Syntax(str(self.text).rstrip(), self.lexer_name, theme=self.theme, word_wrap=True,
                     padding=(0, 2), background_color="default")


class Reply(Markdown):
    elements = {**Markdown.elements, "heading_open": LeftHeading, "fence": TightCode, "code_block": TightCode}


def reply(md: str) -> Table:
    grid = Table.grid(expand=True)
    grid.add_column(width=2)
    grid.add_column(ratio=1)
    grid.add_row(Text("●", style="bold magenta"), Reply(md, code_theme="ansi_dark", inline_code_theme="ansi_dark"))
    return grid


def step(mark: str, style: str, text: str, detail: str = "") -> Table:
    grid = Table.grid(expand=True)
    grid.add_column(width=2)
    grid.add_column(ratio=1)
    line = Text(text)
    if detail:
        line.append("  " + detail, style="dim")
    grid.add_row(Text(mark, style="bold " + style), line)
    return grid


def card(question: str, body: list[str], choices: list[str], chosen: int = 0, tone: str = "yellow",
         keys: str = "←→ выбрать · enter") -> Text:
    text = Text()
    text.append(question + "\n", style="bold")
    for line in body:
        text.append_text(Text.from_markup(line))
        text.append("\n")
    text.append("\n")
    for i, label in enumerate(choices):
        if i == chosen:
            text.append(f" {label} ", style=f"bold reverse {tone}")
        else:
            text.append(f" {label} ")
        text.append("   ")
    text.append(keys, style="dim")
    return text


# Stream items: (kind, payload). Kinds: owner, arch, step, card, done, time.
GOAL = "Добавь экран настроек: громкость музыки и эффектов, сохраняется между запусками."
PLAN = [("Этап 1", "Хранилище настроек и громкость", "running"), ("Этап 2", "Экран настроек в меню", "wait")]
DONE_PLAN = [("Этап 1", "Хранилище настроек и громкость", "ready"), ("Этап 2", "Экран настроек в меню", "wait")]

STATES = [
    ("empty", "Первое открытие проекта: пусто, подсказка и примеры", [], None, None),
    ("dialog", "Тот же разговор, что на скриншоте 00:05", [
        ("time", "сегодня 00:04"),
        ("owner", "так ты тут?"),
        ("arch", "Тут. Плана пока нет. Напиши, что нужно сделать в **pixel-arena**, — я уточню детали, "
                 "составлю план и запущу работу. Или спроси, что в проекте стоит улучшить."),
    ], None, None),
    ("thinking", "Цель отправлена, архитектор думает", [
        ("time", "сегодня 00:04"),
        ("owner", "так ты тут?"),
        ("arch", "Тут. Плана пока нет. Напиши, что нужно сделать в **pixel-arena**."),
        ("owner", GOAL),
    ], ("think", "Архитектор думает", "0:12", "esc — прервать"), None),
    ("goal-card", "Архитектор сформулировал цель: решение карточкой", [
        ("owner", GOAL),
        ("arch", "Понял. Музыка и эффекты уже идут через `audio.py`, настроек пока нет. Предлагаю так:\n\n"
                 "- громкость музыки и эффектов, 0–100 %, по умолчанию 80 %;\n"
                 "- хранится в `settings.json` рядом с сохранениями;\n"
                 "- экран открывается из главного меню, **Esc** — назад.\n\n"
                 "Управление клавишами оставлю на потом."),
        ("card", ("Составить план по этой цели?", ["[dim]Около 2 этапов. Текст цели — во вкладке «Цель».[/dim]"],
                  ["Составить план", "Изменить цель", "Нет"], 0, "yellow")),
    ], None, None),
    ("working", "План утверждён, этап 1 идёт; справа план (широкий экран)", [
        ("owner", GOAL),
        ("done", "Цель принята · план составлен"),
        ("step", ("✓", "green", "План утверждён", "2 этапа")),
        ("step", ("▶", "cyan", "Этап 1 запущен", "Хранилище настроек и громкость")),
        ("owner", "а громкость по умолчанию лучше 60"),
        ("arch", "Хорошо, учту на этапе 1: он ещё идёт, поправлю в его проверке. Этап 2 не меняется."),
    ], ("run", "Этап 1 выполняется", "3:41", "/stop — остановить"), PLAN),
    ("merge", "Этап 1 готов: решение о слиянии", [
        ("step", ("✓", "green", "План утверждён", "2 этапа")),
        ("step", ("▶", "cyan", "Этап 1 запущен", "Хранилище настроек и громкость")),
        ("step", ("✓", "green", "Этап 1 готов", "проверки прошли · 3 файла · +84 −6")),
        ("arch", "Этап 1 готов: `settings.py` хранит громкость (по умолчанию 60 %), `audio.py` её применяет, "
                 "тест `test_settings.py` проходит. Можно вливать."),
        ("card", ("Влить этап 1 в main?", ["[dim]Ветка zplan/m1 · проверки: python -m unittest — ok.[/dim]",
                                            "[dim]Изменения — во вкладке «Этап 1».[/dim]"],
                  ["Влить", "Посмотреть изменения", "Позже"], 0, "green")),
    ], None, DONE_PLAN),
    ("long-reply", "Длинный ответ: заголовок, список, код", [
        ("owner", "что в проекте можно улучшить?"),
        ("arch", "## Что я бы сделал первым\n\n"
                 "1. **Падение без звуковой карты.** `audio.init()` бросает исключение, игра не стартует.\n"
                 "2. **Нет тестов на столкновения.** `collide()` менялся 4 раза за месяц.\n"
                 "3. **Сохранения в рабочей папке.** Лучше в папке пользователя:\n\n"
                 "```python\nSAVE_DIR = Path.home() / \".pixel-arena\"\n```\n\n"
                 "С чего начнём? Могу сразу оформить первый пункт целью."),
    ], None, None),
    ("note", "Короткая заметка над вводом (исчезает сама)", [
        ("time", "сегодня 00:04"),
        ("owner", "так ты тут?"),
        ("arch", "Тут. Плана пока нет. Напиши, что нужно сделать в **pixel-arena**."),
    ], ("note", "Пока доступен только русский язык", "", ""), None),
    ("error", "Архитектор не может ответить: понятная причина и выход", [
        ("owner", GOAL),
        ("card", ("Архитектор не ответил", ["Нет входа в Codex на этом компьютере.",
                                            "[dim]Сообщение сохранено, его не нужно писать заново.[/dim]"],
                  ["Войти", "Повторить", "Закрыть"], 0, "red")),
    ], None, None),
]

EXAMPLES = ["Добавь экран настроек с громкостью", "Почини падение при старте без звука",
            "Что в проекте стоит улучшить?"]

CSS = """
Screen { layout: vertical; }
#main { height: 1fr; }
#chat-col { width: 1fr; padding: 0 1; }
#stream { height: 1fr; scrollbar-size-vertical: 1; padding-bottom: 1; }
#stream > .owner { border-left: outer ansi_yellow; padding: 0 1; margin: 1 0 0 0; color: ansi_bright_white; }
#stream > .arch { margin: 1 0 0 0; }
#stream > .step { margin: 0 0 0 0; }
#stream > .first { margin-top: 1; }
#stream > .time { color: ansi_bright_black; text-align: center; margin: 1 0 0 0; }
#stream > .done { color: ansi_bright_black; margin: 1 0 0 0; }
#stream > .card { border: round ansi_yellow; padding: 0 1; margin: 1 0 0 0; }
#stream > .card.green { border: round ansi_green; }
#stream > .card.red { border: round ansi_red; }
#stream > .empty { height: 1fr; content-align: center middle; }
#indicator { height: 1; padding: 0 1; }
#prompt-box { height: 3; border: round ansi_yellow; padding: 0 1; }
#chevron { width: 2; color: ansi_yellow; text-style: bold; }
#input { border: none; background: transparent; padding: 0; height: 1; }
#side { width: 44; border-left: solid ansi_bright_black; padding: 0 1; }
#side.hidden { display: none; }
#bar { height: 1; padding: 0 1; }
"""


class ChatLab(App):
    CSS = CSS
    TITLE = "zplan"
    BINDINGS = [("ctrl+q", "quit", "quit"), ("ctrl+t", "move(1)", "next"), ("ctrl+y", "move(-1)", "previous")]

    def __init__(self, state: int = 0) -> None:
        super().__init__(ansi_color=True)
        self.state = state
        self.tick = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="chat-col"):
                yield VerticalScroll(id="stream")
                yield Static(id="indicator")
                with Horizontal(id="prompt-box"):
                    yield Static("›", id="chevron")
                    yield Input(placeholder="Опиши задачу или задай вопрос  ·  / — команды", id="input")
            yield Static(id="side")
        yield Static(id="bar")

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.render_state()
        self.set_interval(0.25, self.spin)

    def on_resize(self) -> None:
        self.render_layout()

    def action_move(self, delta: int) -> None:
        self.state = (self.state + delta) % len(STATES)
        self.render_state()

    def spin(self) -> None:
        self.tick += 1
        self.render_indicator()

    def render_layout(self) -> None:
        plan = STATES[self.state][4]
        self.query_one("#side").set_class(not plan or self.size.width < WIDE, "hidden")

    def render_state(self) -> None:
        _, _, items, _, plan = STATES[self.state]
        stream = self.query_one("#stream", VerticalScroll)
        stream.remove_children()
        widgets = []
        if not items:
            widgets.append(Static(self.empty(), classes="empty"))
        for kind, payload in items:
            if kind == "owner":
                widgets.append(Static(Text(payload), classes="owner"))
            elif kind == "arch":
                widgets.append(Static(reply(payload), classes="arch"))
            elif kind == "step":
                widgets.append(Static(step(*payload), classes="step"))
            elif kind == "card":
                question, body, choices, chosen, tone = payload
                widgets.append(Static(card(question, body, choices, chosen, tone), classes="card " + tone))
            elif kind == "done":
                widgets.append(Static(Text("✓ " + payload), classes="done"))
            elif kind == "time":
                widgets.append(Static(payload, classes="time"))
        prev = None
        for widget in widgets:
            if widget.has_class("step") and prev is not None and not prev.has_class("step"):
                widget.add_class("first")
            prev = widget
        stream.mount_all(widgets)
        # the conversation sits on the input, like a chat; the empty chat is centred
        stream.styles.align_vertical = "bottom" if items else "middle"
        stream.scroll_end(animate=False)
        self.render_indicator()
        self.render_side(plan)
        self.render_bar(plan)
        self.render_layout()

    def empty(self) -> Text:
        text = Text(justify="left")
        text.append(PROJECT, style="bold")
        text.append(" · main · изменений нет\n\n", style="dim")
        text.append("Опиши, что нужно сделать. Архитектор уточнит детали,\n")
        text.append("составит план, запустит работу и спросит перед слиянием.\n\n")
        text.append("Например\n", style="dim")
        for i, example in enumerate(EXAMPLES):
            text.append("  › " if i else "  ❯ ", style="bold yellow")
            text.append(example + "\n", style="bold" if i == 0 else "")
        text.append("\n↑↓ выбрать пример · enter отправить · / команды", style="dim")
        return text

    def render_indicator(self) -> None:
        line = STATES[self.state][3]
        widget = self.query_one("#indicator", Static)
        if not line:
            widget.update("")
            return
        kind, label, clock, hint = line
        text = Text()
        if kind == "think":
            text.append(SPIN[self.tick % 4] + " ", style="bold magenta")
            text.append(label + "… ")
        elif kind == "run":
            text.append("▶ ", style="bold cyan")
            text.append(label + " ")
        else:
            text.append("ℹ ", style="bold blue")
            text.append(label, style="dim")
        if clock:
            text.append(clock, style="dim")
        if hint:
            text.append("   " + hint, style="dim")
        widget.update(text)

    def render_side(self, plan) -> None:
        if not plan:
            return
        text = Text()
        text.append("План", style="bold")
        text.append("  r1 · утверждён\n", style="dim")
        text.append(GOAL + "\n\n", style="dim")
        marks = {"running": ("▶", "cyan"), "ready": ("✓", "green"), "wait": ("·", "bright_black")}
        for name, title, status in plan:
            mark, style = marks[status]
            text.append(mark + " ", style="bold " + style)
            text.append(name + "  ", style="bold" if status != "wait" else "dim")
            text.append(title + "\n", style="" if status != "wait" else "dim")
        text.append("\nСейчас\n", style="bold")
        if plan[0][2] == "running":
            for row in ("пишет settings.py", "добавил тест test_settings.py", "запускает тесты…"):
                text.append("  " + row + "\n", style="dim")
        else:
            text.append("  этап 1 ждёт решения о слиянии\n", style="dim")
        text.append("\n/plan-view  подробно\n/stop       остановить", style="dim")
        self.query_one("#side", Static).update(text)

    def render_bar(self, plan) -> None:
        line = STATES[self.state][3]
        if line and line[0] == "think":
            state = "архитектор думает"
        elif not plan:
            state = "ничего не идёт"
        else:
            state = "этап 1 из 2 идёт" if plan[0][2] == "running" else "этап 1 ждёт слияния"
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(justify="right")
        grid.add_row(Text.assemble((PROJECT, "bold"), (" · main · ", "dim"), state),
                     Text("sol high · 15.6k", style="dim"))
        self.query_one("#bar", Static).update(grid)


SIZES = ((80, 24), (100, 45), (140, 40))


async def gallery(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, (slug, what, *_rest) in enumerate(STATES):
        cells = []
        for cols, lines in SIZES:
            app = ChatLab(index)
            async with app.run_test(size=(cols, lines)) as pilot:
                await pilot.pause(0.3)
                name = "%02d-%s-%dx%d.svg" % (index, slug, cols, lines)
                app.save_screenshot(filename=name, path=str(out))
            cells.append('<td valign="top"><img src="%s" width="%d"></td>' % (name, cols * 6))
        rows.append("<tr><th align=left>%02d %s<br><small>%s</small></th>%s</tr>" % (index, slug, what, "".join(cells)))
    (out / "index.html").write_text(
        "<html><meta charset=utf-8><body style='background:#222;color:#ddd;font-family:sans-serif'>"
        "<table cellspacing=12>%s</table></body></html>\n" % "\n".join(rows))
    print(out / "index.html")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--gallery"]:
        asyncio.run(gallery(Path(sys.argv[2])))
    else:
        ChatLab(int(sys.argv[1]) if sys.argv[1:] else 0).run()
