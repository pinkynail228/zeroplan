"""Before/after gallery: the 0.5.1 baseline captures beside today's main screen in the same states, as SVG.

Run from the repo root (same environment as devtools/fasttest.py):
  TMPDIR=$(mktemp -d /tmp/zg.XXXX) ZPLAN_TEST_WHEELHOUSE=~/.cache/zplan-wheelhouse PYTHONPATH=.:tests \
    ZPLAN_GALLERY=build/gallery/LABEL python3.13 devtools/ui-lab/gallery.py
Writes LABEL/{state}-{cols}x{rows}.svg (Textual's own screenshot export, fixture stores from the test harness),
LABEL/baseline/{capture}.svg (the tmux .ans captures of docs/ui-redesign/baseline-0.5.1 rendered by Rich) and
LABEL/index.html with one row per state: 0.5.1 | now 120x40 | now 80x24. Lab tooling, not a test.
"""
import html
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs/ui-redesign/baseline-0.5.1"
OUT = pathlib.Path(os.environ.get("ZPLAN_GALLERY", ROOT / "build/gallery/now")).resolve()
SIZES = ((120, 40), (80, 24))

import tui_support  # noqa: E402,F401  (wheelhouse on sys.path first)
from test_tui_canvas_files import CanvasShell  # noqa: E402

# state -> (what it shows, the 0.5.1 capture of the same moment or None)
STATES = {
    "idle": ("Empty project, nothing planned", "A03-architect-plan-in-chat"),
    "palette": ("Idle, `/` typed in the chat input", None),
    "plan-ready": ("A proposed plan waiting for approval", "A07-plan-ready"),
    "running": ("Stage M1 running", "A09-running-main"),
    "file": ("Nothing runs, README.md opened in the canvas", "C03-ask-agents-md-2"),
}


class Gallery(CanvasShell):
    async def snap(self, state, prepare=None):
        for cols, rows in SIZES:
            async with self.shell(size=(cols, rows)) as pilot:
                await self.loaded(pilot)
                if prepare:
                    await prepare(pilot)
                await pilot.pause(0.3)
                self.app.save_screenshot(f"{state}-{cols}x{rows}.svg", str(OUT))

    async def test_idle(self):
        await self.snap("idle")

    async def test_palette(self):
        async def typed(pilot):
            await pilot.press("slash")
        await self.snap("palette", typed)

    async def test_plan_ready(self):
        import test_terminal_planner as tp
        with tp.Authority(self.state, self.project) as a:
            self.begin(a)
            self.propose(a)
        await self.snap("plan-ready")

    async def test_running(self):
        self.approve()
        await self.snap("running")

    async def test_file(self):
        self.approve(running=False)
        (self.project / "README.md").write_text("# notes\n\nA tiny project.\n\n## Run\n\n    python3 notes.py\n")

        async def opened(pilot):
            self.main().open_file_tab("README.md")
        await self.snap("file", opened)


def baseline_svgs():
    from rich.console import Console
    from rich.text import Text
    out = OUT / "baseline"
    out.mkdir(parents=True, exist_ok=True)
    for _, capture in STATES.values():
        if capture:
            console = Console(record=True, width=120, file=open(os.devnull, "w"), force_terminal=True)
            console.print(Text.from_ansi((BASELINE / f"{capture}.ans").read_text(errors="replace")), end="")
            console.save_svg(str(out / f"{capture}.svg"), title=f"0.5.1 {capture}")


def index():
    rows = []
    for state, (what, capture) in STATES.items():
        cells = [f'<img src="baseline/{capture}.svg">' if capture else "<i>no such screen in 0.5.1</i>"]
        cells += [f'<img src="{state}-{c}x{r}.svg">' for c, r in SIZES]
        rows.append(f"<tr><th>{html.escape(state)}<br><small>{html.escape(what)}</small></th>"
                    + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    (OUT / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>zplan before/after</title>"
        "<style>img{width:100%}td{vertical-align:top;width:31%}th{text-align:left;width:7%}</style>"
        f"<h1>zplan: 0.5.1 vs {html.escape(OUT.name)}</h1><table>"
        "<tr><th></th><th>0.5.1 (tmux 120x40)</th><th>now 120x40</th><th>now 80x24</th></tr>"
        + "".join(rows) + "</table>")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = unittest.main(argv=[sys.argv[0], "Gallery"], exit=False).result
    baseline_svgs()
    index()
    print(OUT / "index.html")
    sys.exit(0 if result.wasSuccessful() else 1)
