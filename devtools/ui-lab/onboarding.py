"""UI lab: first-run onboarding on the welcome screen (fixture states, no backend). Mockups for owner approval.

Every setup step happens on the approved welcome layout (welcome.py: mascot, word mark, one card under it); the
main screen opens only after the first goal. English is the default language.

Live:     ../../build/ui-lab-venv/bin/python onboarding.py            (ctrl+t / ctrl+y: next / previous state)
Gallery:  ../../build/ui-lab-venv/bin/python onboarding.py --gallery DIR   (SVG per state at 120x40 and 80x24)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Center, Vertical
from textual.widgets import Static

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from welcome import GLYPHS, MASCOT, wordmark  # noqa: E402,F401
from ascii_logo import braille, load  # noqa: E402
sys.path.insert(0, str(HERE.parents[1]))
from terminal_planner.toolchain import DEFAULT as CHAIN  # noqa: E402  (versions have one source: test_toolchain)

VERSION = "0.6.1"
STEPS = ("Language", "Project", "Tools", "Sign in", "Autonomy")
FOLDER = "~/Documents/promt.engineer"

# A state: (slug, step index or None, title, body lines, options [(label, hint)], highlighted, progress rows, keys)
# progress row: (mark, style, text). Body/option text may use Rich markup.
STATES = [
    ("language", 0, "Choose your language",
     ["You can change it any time with [b]/language[/b]."],
     [("English", ""), ("Русский", ""), ("中文", "")], 0, [],
     [("↑↓", "choose"), ("enter", "continue"), ("ctrl+q", "quit")]),
    ("project-no-git", 1, "This folder is not a Git project yet",
     [f"[b]{FOLDER}[/b] · 3 files, no Git repository",
      "zplan plans work as Git branches and merges them back, so it needs a repository with one commit."],
     [("Create a repository here", "git init, then a first commit of the 3 files"),
      ("Open another folder…", "recent projects, or type a path"),
      ("Quit", "")], 0, [],
     [("↑↓", "choose"), ("enter", "continue"), ("esc", "back"), ("ctrl+q", "quit")]),
    ("project-identity", 1, "Who should the commits be from?",
     ["Git has no author name and email on this computer yet."],
     [("Name    [reverse] Ada Lovelace     [/reverse]", ""),
      ("Email   [reverse] ada@example.com  [/reverse]", ""),
      ("Save for this project only", "or press tab to save for every project")], 0, [],
     [("tab", "next field"), ("enter", "save and commit"), ("esc", "back")]),
    ("project-created", 1, "Repository created",
     [f"[b]{FOLDER}[/b] · branch main · first commit 3f2c1a0 «Initial commit»"],
     [("Continue", "")], 0, [],
     [("enter", "continue"), ("esc", "back")]),
    ("tools-installing", 2, "Installing the tools zplan runs on",
     ["Downloaded once into ~/.local/share/planning-kit; checksums are verified."],
     [], 0,
     [("✓", "green", f"Zeroshot {CHAIN.zeroshot:<12} verified"),
      ("◐", "yellow", f"Codex {CHAIN.codex:<15} installing · 62%"),
      ("·", "dim", "Check the project      waiting")],
     [("esc", "run in background"), ("ctrl+q", "quit")]),
    ("tools-failed", 2, "Codex could not be installed",
     ["npm reported: network unreachable (registry.npmjs.org).",
      "Nothing was changed in your project. Details: ~/.local/state/planning-kit/setup.log"],
     [("Try again", ""), ("Skip for now", "the architect cannot answer until the tools are installed")], 0,
     [("✓", "green", f"Zeroshot {CHAIN.zeroshot:<12} verified"),
      ("✗", "red", f"Codex {CHAIN.codex:<15} failed")],
     [("↑↓", "choose"), ("enter", "continue"), ("ctrl+q", "quit")]),
    ("signin", 3, "Sign in to Codex",
     ["zplan's architect and agents run on your ChatGPT plan through Codex."],
     [("Sign in with ChatGPT", "opens your browser"),
      ("Use an OpenAI API key", "billed per use"),
      ("Later", "you can look around; the architect cannot answer yet")], 0, [],
     [("↑↓", "choose"), ("enter", "continue"), ("esc", "back")]),
    ("signin-waiting", 3, "Waiting for the browser…",
     ["Finish signing in on the page that opened. If no page opened, visit",
      "[b]https://auth.openai.com/codex/device[/b] and enter the code [b]WXYZ-1234[/b]."],
     [], 0, [("◐", "yellow", "waiting · 0:12")],
     [("esc", "cancel")]),
    ("autonomy", 4, "How much should the architect do on its own?",
     ["Models: [b]gpt-6.1-sol[/b] (worker [b]gpt-6.1-terra/max[/b]) · checks: [b]npm test[/b] (from package.json)",
      "Change any of this later with [b]/settings[/b]."],
     [("Auto", "recommended · plans, starts and merges by itself"),
      ("Supervised", "asks before it starts or merges anything"),
      ("Manual", "you approve and start every step")], 0, [],
     [("↑↓", "choose"), ("enter", "finish setup"), ("esc", "back")]),
    ("ready", None, "", [], [], 0, [], [("enter", "send"), ("/", "commands"), ("ctrl+o", "project"), ("ctrl+q", "quit")]),
    ("returning-notices", None, "", [], [], 0,
     [("!", "red", "Not signed in to Codex: the architect cannot answer        /login"),
      ("◐", "yellow", "M1 «Add a README» running · review · 4 min            /status"),
      ("↑", "cyan", "zplan 0.6.2 is available                               /update")],
     [("enter", "send"), ("/", "commands"), ("ctrl+o", "project"), ("ctrl+q", "quit")]),
]

CSS = """
Screen { align: center middle; }
#page { width: 80; max-width: 100%; height: auto; }
#hero { height: auto; align-horizontal: center; margin-bottom: 1; }
#mascot { width: auto; margin-bottom: 1; }
#brand { width: 40; height: auto; }
#wordmark { text-align: center; color: ansi_bright_yellow; }
#subtitle { text-align: center; }
#steps { margin: 0 2 1 2; height: 1; }
#card { border: round ansi_yellow; padding: 0 1; height: auto; }
#prompt { border: round ansi_yellow; padding: 0 1; height: 3; }
#context { margin: 0 2; height: 1; }
#notices { margin: 1 2 0 2; height: auto; }
#footer { margin-top: 1; text-align: center; }
"""


def steps_line(step: int) -> Text:
    text = Text()
    for i, name in enumerate(STEPS):
        if i:
            text.append("  ")
        mark, style = ("●", "green") if i < step else ("●", "bold yellow") if i == step else ("○", "dim")
        text.append(mark + " ", style=style)
        text.append(name, style="bold" if i == step else "dim")
    return text


class Onboarding(App):
    CSS = CSS
    TITLE = "zplan"
    BINDINGS = [("ctrl+q", "quit", "quit"), ("ctrl+t", "move(1)", "next"), ("ctrl+y", "move(-1)", "previous")]

    def __init__(self, state: int = 0) -> None:
        super().__init__(ansi_color=True)
        self.state = state

    def compose(self) -> ComposeResult:
        with Vertical(id="page"):
            with Vertical(id="hero"):
                with Center():
                    yield Static(id="mascot")
                with Center():
                    with Vertical(id="brand"):
                        yield Static(wordmark("zeroshot"), id="wordmark")
                        yield Static(Text.assemble("p l a n n i n g   k i t", ("  " + VERSION, "dim")), id="subtitle")
            yield Static(id="steps")
            yield Static(id="card")
            yield Static(id="prompt")
            yield Static(id="context")
            yield Static(id="notices")
            yield Static(id="footer")

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.render_state()

    def on_resize(self) -> None:
        self.render_mascot()

    def action_move(self, delta: int) -> None:
        self.state = (self.state + delta) % len(STATES)
        self.render_state()

    def render_mascot(self) -> None:
        mascot = self.query_one("#mascot", Static)
        setup = STATES[self.state][1] is not None
        rows = min(8 if setup else 14, self.size.height - (24 if setup else 14))
        if rows < 5 or not MASCOT.exists():
            mascot.display = False
            return
        gray = load(MASCOT, 128)
        art = braille(gray, min(28, int(rows * 2 * gray.width / gray.height * 0.95)), 128)[:rows]
        width = max(map(len, art))
        mascot.styles.width = width
        mascot.update("\n".join(line.ljust(width) for line in art))
        mascot.display = True

    def render_state(self) -> None:
        slug, step, title, body, options, chosen, progress, keys = STATES[self.state]
        setup = step is not None
        self.query_one("#steps").display = setup
        self.query_one("#card").display = setup
        for name in ("#prompt", "#context"):
            self.query_one(name).display = not setup
        notices = self.query_one("#notices", Static)
        if setup:
            self.query_one("#steps", Static).update(steps_line(step))
            card = Text()
            card.append(title + "\n", style="bold")
            for line in body:
                card.append_text(Text.from_markup(line, style="dim"))
                card.append("\n")
            for mark, style, row in progress:
                card.append(f"\n{mark} ", style=f"bold {style}")
                card.append(row)
            if progress:
                card.append("\n")
            for i, (label, hint) in enumerate(options):
                card.append("\n")
                card.append("❯ " if i == chosen else "  ", style="bold yellow")
                card.append_text(Text.from_markup(label, style="bold" if i == chosen else ""))
                if hint:
                    card.append("  " + hint, style="dim")
            self.query_one("#card", Static).update(card)
            notices.display = False
        else:
            self.query_one("#prompt", Static).update(
                Text.assemble(("› ", "bold yellow"), ("Describe what you want to build or change", "dim")))
            self.query_one("#context", Static).update(
                Text.assemble(("promt.engineer", "bold"), (" · ", "dim"), "main", (" · ", "dim"),
                              ("clean", "dim"), (" · ", "dim"), ("auto", "dim")))
            notices.display = bool(progress)
            text = Text()
            for i, (mark, style, row) in enumerate(progress):
                text.append(("\n" if i else "") + mark + " ", style=f"bold {style}")
                text.append(row)
            notices.update(text)
        footer = Text(style="dim")
        for i, (key, label) in enumerate(keys):
            footer.append(("   " if i else "") + key, style="bold")
            footer.append(" " + label)
        self.query_one("#footer", Static).update(footer)
        self.render_mascot()


async def gallery(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, state in enumerate(STATES):
        cells = []
        for cols, lines in ((120, 40), (80, 24)):
            app = Onboarding(index)
            async with app.run_test(size=(cols, lines)) as pilot:
                await pilot.pause()
                name = "%02d-%s-%dx%d.svg" % (index, state[0], cols, lines)
                app.save_screenshot(filename=name, path=str(out))
            cells.append('<td><img src="%s" width="%d"></td>' % (name, 640 if cols == 120 else 430))
        rows.append("<tr><th>%02d %s</th>%s</tr>" % (index, state[0], "".join(cells)))
    (out / "index.html").write_text("<html><body><table>%s</table></body></html>\n" % "\n".join(rows))
    print(out / "index.html")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--gallery"]:
        asyncio.run(gallery(Path(sys.argv[2])))
    else:
        Onboarding().run()
