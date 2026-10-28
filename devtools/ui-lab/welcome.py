"""UI lab: welcome/onboarding screen prototype (fixture data, no backend).

Run through devtools/ui-lab/run.sh; the app exits with code 3 when this file or the
logo source changes and the runner restarts it, so edits show up live.
Lab only: ctrl+t or /lab cycles fixture states (healthy, not logged in, update, background job).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Center, Horizontal, Vertical
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MASCOT = ROOT / "build/ui-lab-refs/oec-mascot-160.webp"  # third-party image, kept out of git
sys.path.insert(0, str(HERE))
from ascii_logo import braille, load  # noqa: E402

VERSION = "0.5.1"
WIDTH = 72  # usable text width inside the page

# Two-row block font for the word mark.
GLYPHS = {
    "z": ("▀█", "█▄"), "e": ("█▀▀", "██▄"), "r": ("█▀█", "█▀▄"), "o": ("█▀█", "█▄█"),
    "s": ("█▀", "▄█"), "h": ("█ █", "█▀█"), "t": ("▀█▀", " █ "),
}

COMMANDS = [
    ("/project", "открыть другой проект"),
    ("/status", "что сейчас идёт в проекте"),
    ("/login", "войти в Codex"),
    ("/setup", "проверить и починить установку"),
    ("/update", "обновить zplan"),
    ("/help", "все клавиши и команды"),
    ("/lab", "лаборатория: следующее состояние"),
]

# Fixture states: each is the list of notices the screen must surface.
# A notice = (mark, style, message, action). Healthy = no notices at all.
STATES = [
    ("всё в порядке", []),
    ("нет входа", [("!", "red", "Не выполнен вход в Codex — без него агент не ответит", "/login")]),
    ("есть обновление", [("↑", "cyan", "Вышла версия 0.5.2", "/update")]),
    ("идёт фоновая задача", [("◐", "yellow", "Планирование · проверяю покрытие цели · 4 мин", "/status")]),
    ("всё сразу", [
        ("!", "red", "Не выполнен вход в Codex — без него агент не ответит", "/login"),
        ("◐", "yellow", "Планирование · проверяю покрытие цели · 4 мин", "/status"),
        ("↑", "cyan", "Вышла версия 0.5.2", "/update"),
    ]),
]


def wordmark(word: str) -> Text:
    top = " ".join(GLYPHS[c][0] for c in word)
    bottom = " ".join(GLYPHS[c][1] for c in word)
    return Text(f"{top}\n{bottom}", style="bold")


def git(cwd: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                              timeout=2).stdout.rstrip()
    except Exception:
        return ""


def short(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text.startswith(home) else text


def clip(text: str, width: int) -> str:
    # Never wrap: cut the middle so both ends of a name stay readable.
    if len(text) <= width:
        return text
    head = (width - 1) // 2
    return text[:head] + "…" + text[len(text) - (width - 1 - head):]


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def git_root(path: Path) -> Path | None:
    top = git(path, "rev-parse", "--show-toplevel") if path.is_dir() else ""
    return Path(top) if top else None


def recent_projects(limit: int = 7) -> list[Path]:
    # Lab fixture: git repos under the usual folders, newest first. The real app
    # would keep its own list of projects zplan was opened in.
    found = []
    for base in (Path.home() / "Documents", Path.home() / "Projects", Path.home() / "code"):
        if base.is_dir():
            found += [p for p in base.iterdir() if (p / ".git").exists()]
    found.sort(key=lambda p: (p / ".git").stat().st_mtime, reverse=True)
    return found[:limit]


def dir_candidates(arg: str, cwd: Path, limit: int = 7) -> list[Path]:
    # `cd <arg>` completion: the folder typed so far plus its matching subfolders.
    raw = os.path.expanduser(arg) if arg else ""
    path = Path(os.path.normpath(raw if raw.startswith("/") else cwd / raw))
    if arg.endswith("/") or not arg:
        parent, prefix = path, ""
    else:
        parent, prefix = path.parent, path.name
    try:
        subs = sorted((p for p in parent.iterdir()
                       if p.is_dir() and not p.name.startswith(".")
                       and p.name.lower().startswith(prefix.lower())),
                      key=lambda p: ((p / ".git").exists() is False, p.name.lower()))
    except OSError:
        subs = []
    head = [path] if path.is_dir() and arg and not arg.endswith("/") else []
    return head + subs[:limit - len(head)]


class Welcome(App):
    CSS_PATH = "welcome.tcss"
    TITLE = "zplan"
    BINDINGS = [("ctrl+q", "quit", "выход"), ("ctrl+o", "pick_project", "проект"),
                ("ctrl+t", "next_state", "lab: состояние")]

    def __init__(self) -> None:
        super().__init__(watch_css=True, ansi_color=True)
        self._sources = {p: p.stat().st_mtime for p in (Path(__file__), HERE / "ascii_logo.py")}
        self.project = ROOT
        self.state = 0
        self._mode = ""          # "", "commands", "recent", "cd"
        self._choices: list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="page"):
            with Vertical(id="hero"):
                with Center(id="mascot-box"):
                    yield Static(id="mascot")
                with Center(id="brand-box"):
                    with Vertical(id="brand"):
                        yield Static(wordmark("zeroshot"), id="wordmark")
                        yield Static(id="subtitle")
            with Horizontal(id="prompt-box"):
                yield Static("›", id="chevron")
                yield Input(placeholder="Опиши, что хочешь сделать в проекте", id="prompt")
            yield Static(id="context")
            yield Static(id="notices")
            with Vertical(id="picker-box"):
                yield Static(id="picker-title")
                yield OptionList(id="picker")
            yield Static(id="footer")

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.query_one("#picker-box").display = False
        self.query_one("#picker", OptionList).can_focus = False
        subtitle = Text("p l a n n i n g   k i t", style="")
        subtitle.append(f"  {VERSION}", style="dim")
        self.query_one("#subtitle", Static).update(subtitle)
        self._render_context()
        self._render_notices()
        self._render_footer()
        self.query_one("#prompt", Input).focus()
        self._fitted = None
        self._fit_mascot()
        self.set_interval(0.2, self._fit_mascot)
        self.set_interval(0.5, self._reload_if_changed)

    # ── zone 1: where my message goes ───────────────────────────────────

    def _render_context(self) -> None:
        branch = git(self.project, "branch", "--show-current") or "без ветки"
        changed = len([l for l in git(self.project, "status", "--porcelain").splitlines() if l])
        if changed:
            change = f"{changed} {plural(changed, 'файл изменён', 'файла изменены', 'файлов изменено')}"
        else:
            change = "без изменений"
        name = self.project.name
        room = WIDTH - len(name) - len(change) - 6
        text = Text(name, style="bold")
        text.append(" · ", style="dim")
        text.append(clip(branch, max(8, room)), style="")
        text.append(" · ", style="dim")
        text.append(change, style="yellow" if changed else "dim")
        self.query_one("#context", Static).update(text)

    # ── zone 2: only what needs attention ───────────────────────────────

    def _render_notices(self) -> None:
        notices = STATES[self.state][1]
        box = self.query_one("#notices", Static)
        box.display = bool(notices) and not self._mode
        text = Text()
        for i, (mark, style, message, action) in enumerate(notices):
            if i:
                text.append("\n")
            text.append(f"{mark} ", style=f"bold {style}")
            room = WIDTH - len(action) - 4
            text.append(clip(message, room).ljust(room))
            text.append("  " + action, style="bold")
        box.update(text)

    # ── zone 3: keys for the current mode ───────────────────────────────

    def _render_footer(self) -> None:
        if self._mode:
            keys = [("↑↓", "выбрать"), ("enter", "открыть"), ("esc", "закрыть")]
            if self._mode in ("recent", "cd"):
                keys.insert(2, ("tab", "войти в папку"))
        else:
            keys = [("enter", "отправить"), ("/", "команды"), ("ctrl+o", "проект"), ("ctrl+q", "выход")]
        text = Text(style="dim")
        for i, (key, label) in enumerate(keys):
            text.append(("   " if i else "") + key, style="bold")
            text.append(f" {label}")
        self.query_one("#footer", Static).update(text)

    # ── one dropdown for commands, projects and folders ─────────────────

    def _query(self, value: str) -> tuple[str, str]:
        if value == "cd" or value.startswith("cd "):
            return "cd", value[3:]
        if value.startswith("/project "):
            return "recent", value[len("/project "):].strip()
        if value.startswith("/") and " " not in value:
            return "commands", value
        return "", ""

    def _open_dropdown(self, mode: str, arg: str) -> None:
        picker = self.query_one("#picker", OptionList)
        picker.clear_options()
        title = Text(style="dim")
        if mode == "commands":
            self._choices = [c for c in COMMANDS if c[0].startswith(arg.lower())]
            for cmd, desc in self._choices:
                row = Text(f"{cmd:<12}", style="bold")
                row.append(desc, style="dim")
                picker.add_option(Option(row))
            title.append("команды")
        elif mode == "recent":
            self._choices = [p for p in recent_projects() if arg.lower() in p.name.lower()]
            for path in self._choices:
                picker.add_option(Option(self._path_row(path, show_parent=True)))
            title.append("недавние проекты")
            title.append("   другая папка: cd <путь>", style="italic")
        else:
            self._choices = dir_candidates(arg, self.project)
            raw = os.path.expanduser(arg)
            where = Path(os.path.normpath(raw if raw.startswith("/") else self.project / raw))
            if arg and not arg.endswith("/"):
                where = where.parent
            for path in self._choices:
                picker.add_option(Option(self._path_row(path, show_parent=False)))
            title.append("папки в ")
            title.append(clip(short(where) + "/", WIDTH - 10), style="bold not dim")
        if self._choices:
            picker.highlighted = 0
        else:
            picker.add_option(Option(Text("ничего не найдено", style="dim"), disabled=True))
        self.query_one("#picker-title", Static).update(title)
        self._mode = mode
        self.query_one("#picker-box").display = True
        self.query_one("#context").display = mode == "commands"
        self._render_notices()
        self._render_footer()

    def _path_row(self, path: Path, show_parent: bool) -> Text:
        is_repo = (path / ".git").exists()
        current = path == self.project
        text = Text("● " if current else ("◆ " if is_repo else "  "),
                    style="yellow" if current else "green")
        text.append(clip(path.name, 24).ljust(26), style="bold" if is_repo else "")
        tail = short(path.parent) + "/" if show_parent else ""
        if is_repo:
            branch = git(path, "branch", "--show-current")
            tail = (tail + "  " if tail else "") + branch
        text.append(clip(tail, WIDTH - 30), style="dim")
        return text

    def _close_dropdown(self) -> None:
        self._mode = ""
        self._choices = []
        self.query_one("#picker-box").display = False
        self.query_one("#context").display = True
        self._render_notices()
        self._render_footer()

    def _highlighted(self):
        index = self.query_one("#picker", OptionList).highlighted
        return self._choices[index] if self._choices and index is not None else None

    def _set_prompt(self, value: str) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.value = value
        prompt.cursor_position = len(value)

    def _open_path(self, path: Path) -> None:
        root = git_root(path)
        if root is None:
            # Not a project yet: step into the folder and keep browsing.
            self._set_prompt("cd " + short(path) + "/")
            return
        self.project = root
        self._set_prompt("")
        self._render_context()
        self.notify(f"Открыт проект {root.name}", timeout=2)

    def _run_command(self, cmd: str) -> None:
        if cmd == "/lab":
            self._set_prompt("")
            self.action_next_state()
            return
        if cmd == "/project":
            self._set_prompt("/project ")
            return
        self._set_prompt("")
        self.notify(f"демо: {cmd}", timeout=2)

    def action_pick_project(self) -> None:
        self._set_prompt("/project ")

    def action_next_state(self) -> None:
        self.state = (self.state + 1) % len(STATES)
        self._render_notices()
        self.notify(f"lab: {STATES[self.state][0]}", timeout=1.5)

    def on_key(self, event) -> None:
        if not self._mode:
            return
        picker = self.query_one("#picker", OptionList)
        if event.key == "down":
            picker.action_cursor_down()
        elif event.key == "up":
            picker.action_cursor_up()
        elif event.key == "escape":
            self._set_prompt("")
        elif event.key == "tab" and self._mode in ("recent", "cd") and (path := self._highlighted()):
            self._set_prompt("cd " + short(path) + "/")
        elif event.key == "tab" and self._mode == "commands" and (choice := self._highlighted()):
            self._set_prompt(choice[0] + " ")
        else:
            return
        event.stop()
        event.prevent_default()

    def on_input_changed(self, event: Input.Changed) -> None:
        mode, arg = self._query(event.value)
        if mode:
            self._open_dropdown(mode, arg)
        elif self._mode:
            self._close_dropdown()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if self._mode:
            choice = self._highlighted()
            if choice is None:
                return
            if self._mode == "commands":
                self._run_command(choice[0])
            else:
                self._open_path(choice)
            return
        if not value:
            return
        self.notify("демо: здесь начнётся разговор о цели", timeout=2)
        event.input.value = ""

    # ── mascot / reload ─────────────────────────────────────────────────

    def _fit_mascot(self) -> None:
        if self.size != self._fitted:
            self._fitted = self.size
            self._render_mascot()

    def _render_mascot(self) -> None:
        # Tall window: mascot above the word mark; short window: side by side.
        compact = self.size.height < 32
        self.query_one("#hero").set_class(compact, "compact")
        rows = min(10, self.size.height - 14) if compact else min(17, self.size.height - 17)
        mascot = self.query_one("#mascot", Static)
        if rows < 6:
            mascot.display = False
            return
        mascot.display = True
        gray = load(MASCOT, 128)
        cols = min(32, int(rows * 2 * gray.width / gray.height * 0.95))
        art = braille(gray, cols, 128)[:rows]
        width = max(map(len, art))
        mascot.styles.width = width
        mascot.update("\n".join(line.ljust(width) for line in art))
        # Side by side: centre the word mark against the mascot.
        top = max(0, (len(art) - 3) // 2) if compact else 0
        self.query_one("#brand-box").styles.margin = (top, 0, 0, 0)

    def _reload_if_changed(self) -> None:
        for path, mtime in self._sources.items():
            if path.stat().st_mtime != mtime:
                self.exit(return_code=3)


if __name__ == "__main__":
    app = Welcome()
    app.run()
    sys.exit(app.return_code or 0)
