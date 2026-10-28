"""Start screen: the full-screen card that picks the project before the main screen opens (Textual).

One card at a time with a cursor list: the project here, another folder, quit. A folder without Git, or a repo
without a commit, can become a project in one step: `git init` when needed, then one empty commit (no file is
added). A project whose `origin` is not a GitHub URL gets one more step before it opens: Zeroshot names a project
by its GitHub origin, so the owner may add `https://github.com/<OWNER/REPO>.git` (nothing is pushed and the
repository need not exist) or skip. An origin that exists is never replaced by default: the card names it, «Skip»
is the first row, and the replacement shows the command that restores the old URL. Git is written only by those steps; every other path (quit, Esc, Ctrl+C,
Ctrl+Q) leaves the folder alone. `choose(start)` returns the project root, or None when the owner left."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.widgets import Input, Static

from .. import __version__
from ..authority import Blocked, discover, git
from ..setup import GITHUB_ORIGIN

# `python3 devtools/ui-lab/ascii_logo.py upstream/docs/brand/assets/oec-mascot.png braille 24 128`
MASCOT = """\
      ⣠⠖⡺⣛⡶⣶⣤⣄⡀        ⣤
      ⡇⣰⡟⠻⠛⢿⣷⣌⣉⣒⣠⡀    ⢸⠏
      ⠓⢧⣱⣄⣠⣬⣷⡖⠒⠒⠋⠁   ⢀⡟
        ⢼⣿⠯⣴⣟        ⣸⠁
       ⢀⣿⣯⣧⣠⣿⣷⡄     ⢠⠇
       ⣸⢿⣷⣾⣿⣿⣿⣿⣄    ⡞
 ⣀ ⢤⢄⡀ ⣿⣾⣿⣿⣿⣿⣿⣿⣿⣦⣤⣄⣼⣁
⣀⡈⠛⢧⣳⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠆
 ⠉⠒⠲⠿⣿⣿⣿⣿⣿⣿⣿⣷⣿⣾⠟  ⣼⠋ ⡤
     ⠈⠙⠻⠿⣿⣿⣿⣿⣿⣿⡀  ⠸⠶⠾⠁
        ⢀⣾⣿⠏⠙⢿⣿⣷⡀
       ⢀⣾⣿⣏⡀ ⠈⢻⣿⣧⡀
       ⠙⠛⠙⠻⠿⠷⠆⢸⡿⢻⣿⣿⣶⡤"""
GLYPHS = {"z": ("▀█", "█▄"), "e": ("█▀▀", "██▄"), "r": ("█▀█", "█▀▄"), "o": ("█▀█", "█▄█"), "s": ("█▀", "▄█"),
          "h": ("█ █", "█▀█"), "t": ("▀█▀", " █ ")}
WORDMARK = "\n".join(" ".join(GLYPHS[c][row] for c in "zeroshot") for row in (0, 1))
MIN_WIDTH, MIN_HEIGHT = 60, 24  # below this the mascot is not drawn
COMPACT_HEIGHT = 36             # below this the mascot stands beside the word mark
FIRST_COMMIT = "Initial commit"
DEFAULT_BRANCH = "main"
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")  # OWNER/REPO as a GitHub URL carries it

CSS = """
Screen { align: center middle; }
#page { width: 76; max-width: 100%; height: auto; }
#hero { height: auto; width: 100%; }
Screen.compact #hero { layout: horizontal; align-horizontal: center; }
#mascot-box { height: auto; width: 100%; align-horizontal: center; }
Screen.compact #mascot-box { width: auto; margin-right: 2; }
#mascot { width: 24; height: auto; margin-bottom: 1; }
Screen.compact #mascot { margin-bottom: 0; }
#brand-box { height: auto; width: 100%; align-horizontal: center; }
Screen.compact #brand-box { width: auto; height: 13; align-vertical: middle; }
#brand { width: 29; height: auto; }
#wordmark { text-align: center; color: ansi_bright_yellow; }
#subtitle { text-align: center; }
#card { border: round ansi_yellow; padding: 0 1; height: auto; margin-top: 1; }
Screen.compact #card { margin-top: 0; }
#card Input { border: none; height: 1; padding: 0 1; margin-top: 1; background: ansi_bright_black; }
#footer { margin-top: 1; text-align: center; }
"""


class StartError(Exception):
    """A Git step failed; the message is shown on the card."""


@dataclass(frozen=True)
class Folder:
    path: Path
    exists: bool
    root: Path | None   # the Git work tree containing it, if any
    ready: bool         # a repo with at least one commit
    branch: str = ""
    commit: str = ""    # subject of the last commit


def printable(value, limit=200):
    line = (str(value).strip().splitlines() or [""])[0]
    return "".join(c for c in line if c.isprintable())[:limit]


def inspect(path) -> Folder:
    """What `path` is as a project: read-only (no hooks, no index refresh)."""
    path = Path(path)
    if not path.is_dir():
        return Folder(path, False, None, False)
    try:
        root = discover(path)
    except (Blocked, OSError):
        return Folder(path, True, None, False)
    try:
        git(root, "rev-parse", "--verify", "--quiet", "HEAD")
        branch = git(root, "branch", "--show-current").decode().strip() or "HEAD"
        commit = git(root, "log", "-1", "--format=%s").decode().strip()
    except (Blocked, OSError):
        return Folder(path, True, root, False)
    return Folder(path, True, root, True, branch, commit)


def unstaged_files(root) -> int:
    """Files the work tree has that the last commit does not (untracked included)."""
    return len([line for line in git(root, "status", "--porcelain", "--untracked-files=all").splitlines() if line])


def run_git(path, *args, input=None):
    try:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, input=input)
    except OSError as error:
        raise StartError(printable(error)) from error
    if result.returncode:
        raise StartError(printable(result.stderr or result.stdout) or "git %s failed" % args[0])
    return result.stdout.strip()


def configured(path, key) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), "config", "--get", key], capture_output=True,
                              text=True).stdout.strip()
    except OSError:
        return ""


def identity_missing(path) -> bool:
    """Git has no author name or email for a commit in `path` (read only)."""
    return not (configured(path, "user.name") and configured(path, "user.email"))


def create_project(path, name=None, email=None):
    """`git init` when `path` is in no repo, the identity into the repo's local config when given, then one empty
    commit made from the empty tree, so nothing staged or present in the folder is added to it."""
    path = Path(path)
    try:
        discover(path)
    except Blocked:
        run_git(path, "init", "-q", *(() if configured(path, "init.defaultBranch") else ("-b", DEFAULT_BRANCH)))
    if name:
        run_git(path, "config", "user.name", name)
    if email:
        run_git(path, "config", "user.email", email)
    tree = run_git(path, "hash-object", "-w", "-t", "tree", "--stdin", input="")
    run_git(path, "update-ref", "-m", "initial commit", "HEAD", run_git(path, "commit-tree", tree, "-m", FIRST_COMMIT))


def origin_url(root) -> str:
    """The URL of `origin` ("" when the repo has none); read only."""
    try:
        return git(root, "remote", "get-url", "origin").decode().strip()
    except (Blocked, OSError):
        return ""


def needs_origin(root) -> bool:
    """`origin` is missing or not a GitHub URL: Zeroshot cannot name the project (the readiness check refuses it)."""
    return not GITHUB_ORIGIN.fullmatch(origin_url(root))


def shown_url(url) -> str:
    """The URL for the card; a URL with userinfo (user:secret@) keeps its scheme and shows host and path."""
    return re.sub(r"^([a-z][a-z0-9+.-]*://)[^/]*@", r"\1", url, flags=re.IGNORECASE)


def suggested_repository(root) -> str:
    return "local/" + re.sub(r"[^A-Za-z0-9_.-]", "-", Path(root).name)


def add_origin(root, repository):
    """`git remote add origin https://github.com/<repository>.git`, or `set-url` when `origin` exists. Nothing is
    fetched or pushed; the repository need not exist."""
    if not REPOSITORY.fullmatch(repository):
        raise StartError("Expected OWNER/REPO: Latin letters, digits and _ . -")
    url = "https://github.com/%s.git" % repository
    run_git(root, "remote", "set-url" if origin_url(root) else "add", "origin", url)


def short(path):
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text == home or text.startswith(home + os.sep) else text


def clip(text, width):
    """Never wrap: cut the middle so both ends of a path stay readable."""
    if len(text) <= width:
        return text
    head = (width - 1) // 2
    return text[:head] + "…" + text[len(text) - (width - 1 - head):]


def keys_line(*pairs):
    footer = Text(style="dim")
    for i, (key, label) in enumerate(pairs):
        footer.append(("   " if i else "") + key, style="bold")
        footer.append(" " + label)
    return footer


class StartApp(App):
    """The card stack: ("project", path) | ("other",) | ("identity", path) | ("created", path) | ("origin", root)."""

    CSS = CSS
    TITLE = "zplan"
    AUTO_FOCUS = None  # a card focuses its own field; a list card has no focus, so Enter reaches the cursor list
    BINDINGS = [Binding("ctrl+q", "leave", "quit", priority=True), Binding("ctrl+c", "leave", "quit", priority=True),
                Binding("escape", "back", "back"), Binding("up", "move(-1)", show=False),
                Binding("down", "move(1)", show=False), Binding("enter", "select", show=False)]

    def __init__(self, start):
        super().__init__(ansi_color=True)
        self.start = Path(start).expanduser()
        self.stack = [("project", self.start)]
        self.info = inspect(self.start)
        self.cursor = 0
        self.error = ""
        self.old_origin = ""  # the origin the origin card would replace

    # Layout ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="page"):
            with Vertical(id="hero"):
                with Center(id="mascot-box"):
                    yield Static(Text(MASCOT), id="mascot")
                with Center(id="brand-box"):
                    with Vertical(id="brand"):
                        yield Static(Text(WORDMARK, style="bold"), id="wordmark")
                        yield Static(Text.assemble("planning kit  ", (__version__, "dim")), id="subtitle")
            with Vertical(id="card"):
                yield Static(id="card-text")
                yield Input(placeholder="Folder path", id="path")
                yield Input(placeholder="Name", id="name")
                yield Input(placeholder="Email", id="email")
                yield Input(placeholder="OWNER/REPO", id="origin")
            yield Static(id="footer")

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.show()
        self.fit()

    def on_resize(self) -> None:
        self.fit()

    def fit(self) -> None:
        width, height = self.size
        mascot = width >= MIN_WIDTH and height >= MIN_HEIGHT
        self.query_one("#mascot-box").display = mascot
        self.screen.set_class(mascot and height < COMPACT_HEIGHT, "compact")

    # Cards -------------------------------------------------------------------

    @property
    def step(self):
        return self.stack[-1]

    def go(self, step) -> None:
        self.stack.append(step)
        self.enter()

    def enter(self) -> None:
        """Show the top card, computed from the folder as it is now."""
        kind, *rest = self.step
        if kind in ("project", "created"):
            self.info = inspect(rest[0])
        self.cursor, self.error = 0, ""
        if kind == "origin":
            self.old_origin = origin_url(rest[0])
            self.query_one("#origin", Input).value = suggested_repository(rest[0])
        self.show()

    def rows(self):
        """(label, action) of the top card's cursor list."""
        kind = self.step[0]
        if kind == "project":
            if self.info.ready:
                return [("Open this project", "open"), ("Another folder", "other"), ("Quit", "leave")]
            create = [("Create a project here (git init + first commit)", "create")] if self.info.exists else []
            return create + [("Another folder", "other"), ("Quit", "leave")]
        if kind == "created":
            return [("Continue", "open")]
        if kind == "origin":
            if self.old_origin:
                return [("Skip", "skip"), ("Replace origin", "add")]
            return [("Add origin", "add"), ("Skip", "skip")]
        return []

    def card_width(self) -> int:
        return max(20, min(self.size.width, 76) - 4)

    def show(self) -> None:
        kind = self.step[0]
        card = Text()
        if kind == "project":
            if self.info.ready:
                card.append("%s · %s · %s\n" % (self.info.root.name, self.info.branch, self.info.commit), style="bold")
            else:
                card.append(("There is no Git project here" if self.info.exists else "The folder does not exist") + "\n", style="bold")
            card.append(clip(short(self.info.path), self.card_width()) + "\n", style="dim")
        elif kind == "other":
            card.append("Another folder\n", style="bold")
            card.append("The path to a project folder or to a new folder.\n", style="dim")
        elif kind == "identity":
            card.append("Who is the commit author?\n", style="bold")
            card.append("The name and email are saved in this project only.\n", style="dim")
        elif kind == "origin":
            card.append("No GitHub origin\n", style="bold")
            if self.old_origin:
                old = shown_url(self.old_origin)
                card.append("Current origin: %s\n" % old, style="yellow")
                card.append("Replacing removes this address. To restore it:\ngit remote set-url origin %s\n" % old, style="dim")
            card.append("Zeroshot names a project by its origin. zplan pushes nothing; the repository need not "
                        "exist.\nThe suggestion can be changed: OWNER/REPO.\n", style="dim")
        else:
            info = self.info
            card.append("%s · %s\n" % (info.branch, info.commit), style="bold")
            card.append(clip(short(info.root), self.card_width()) + "\n", style="dim")
            try:
                files = unstaged_files(info.root)
            except (Blocked, OSError):
                files = 0
            if files:
                card.append("%s not in the commit\n" % ("1 file" if files == 1 else "%d files" % files), style="yellow")
        for i, (label, _) in enumerate(self.rows()):
            card.append("\n" + ("❯ " if i == self.cursor else "  "), style="bold yellow")
            card.append(label, style="bold" if i == self.cursor else "")
        card.rstrip()
        if self.error:
            card.append("\n" + self.error, style="red")
        self.query_one("#card-text", Static).update(card)
        fields = {"other": ("path",), "identity": ("name", "email"), "origin": ("origin",)}.get(kind, ())
        for name in ("path", "name", "email", "origin"):
            self.query_one("#" + name, Input).display = name in fields
        if fields:
            self.query_one("#" + fields[0], Input).focus()
        else:
            self.set_focus(None)
        keys = [("enter", "continue")]
        if self.rows():
            keys.insert(0, ("↑↓", "select"))
        keys += [("esc", "quit" if len(self.stack) == 1 else "back"), ("ctrl+q", "quit")]
        self.query_one("#footer", Static).update(keys_line(*keys))

    # Keys --------------------------------------------------------------------

    def action_leave(self) -> None:
        self.exit(None)

    def action_back(self) -> None:
        if len(self.stack) == 1:
            self.exit(None)
            return
        self.stack.pop()
        self.enter()

    def action_move(self, delta: int) -> None:
        rows = self.rows()
        if rows:
            self.cursor = (self.cursor + delta) % len(rows)
            self.show()

    def action_select(self) -> None:
        rows = self.rows()
        if not rows:
            return
        action = rows[self.cursor][1]
        if action == "leave":
            self.exit(None)
        elif action == "open":
            self.open(self.info.root)
        elif action in ("add", "skip"):
            self.settle_origin(action)
        elif action == "other":
            self.go(("other",))
        else:
            self.create()

    def open(self, root) -> None:
        """Leave with the project; one step first when its origin is not a GitHub URL."""
        if needs_origin(root):
            self.go(("origin", root))
        else:
            self.exit(root)

    def settle_origin(self, action) -> None:
        """The «Add origin» / «Replace origin» / «Skip» row of the origin card: skip goes on unchanged; an invalid value or a
        failed Git call keeps the card with a note."""
        root = self.step[1]
        if action == "add":
            try:
                add_origin(root, self.query_one("#origin", Input).value.strip())
            except StartError as error:
                self.error = str(error)
                self.show()
                return
        self.exit(root)

    def create(self, name=None, email=None) -> None:
        """Create the project at the top card's folder; asks for the identity first when Git has none."""
        kind, path = self.step
        if name is None and identity_missing(path):
            self.go(("identity", path))
            return
        try:
            create_project(path, name, email)
        except StartError as error:
            self.error = str(error)
            self.show()
            return
        if kind == "identity":
            self.stack.pop()
        self.go(("created", path))

    def on_input_changed(self) -> None:
        if self.error:
            self.error = ""
            self.show()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if event.input.id == "path":
            self.pick(event.value)
        elif event.input.id == "origin":
            self.settle_origin(self.rows()[self.cursor][1])
        elif event.input.id == "name":
            self.query_one("#email", Input).focus()
        else:
            name = self.query_one("#name", Input).value.strip()
            email = event.value.strip()
            if name and email:
                self.create(name, email)
            else:
                self.error = "The name and email are required."
                self.show()

    def pick(self, value: str) -> None:
        """The path typed on the «Another folder» card: a ready project opens, anything else gets its own card."""
        text = value.strip()
        if not text:
            self.error = "Enter a path."
            self.show()
            return
        path = Path(text).expanduser()
        path = path if path.is_absolute() else self.start / path
        info = inspect(path)
        if not info.exists:
            self.error = "The folder does not exist: %s" % printable(text)
            self.show()
        elif info.ready:
            self.open(info.root)
        else:
            self.go(("project", path))


def choose(start):
    """The project root picked on the start screen, or None when the owner left."""
    return StartApp(start).run()
