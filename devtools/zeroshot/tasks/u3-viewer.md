U3 — read-only file and diff view for the canvas (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md, run u3-viewer).

Goal: `terminal_planner/tui/viewer.py` turns a project file or a unified diff into a Rich renderable for the right-hand
canvas. The owner never edits by hand; this is view only. Nothing imports it yet (integration run i5 does).
Look: as in the approved lab `devtools/ui-lab/work.py` `_render_view` (file: `rich.syntax.Syntax`, theme "ansi_dark",
line numbers, word wrap, default background; diff: lexer "diff", no line numbers).

Write-set: terminal_planner/tui/viewer.py (new), tests/test_tui_viewer.py (new). Nothing else.

Acceptance criteria:
- A1 `resolve(root: Path, name: str) -> Path` returns the file under `root` for a relative name; it raises
  `ViewError` whose `.id` is a catalog id for: empty name `note.view_empty`, an absolute path or a resolved location
  (symlinks followed) outside `root` `note.view_outside`, a missing path `note.view_missing`, a directory
  `note.view_directory`; `.values` holds the format values (`{name}`). The module never builds the message text.
- A2 `file_view(path, max_bytes=200_000) -> renderable`: syntax by suffix (.py python, .md markdown, .json json,
  .toml toml, .yaml/.yml yaml, .sh bash, other -> plain text), line numbers on; a file over `max_bytes` shows its
  first `max_bytes` and a last dim line from `words("canvas.view_cut", shown=N, total=M)` (KB; `words` is a callable
  id, **values -> str argument; default returns a built-in Russian text); a file that is not UTF-8 text raises
  `ViewError` id `note.view_binary`.
- A3 `diff_view(text) -> renderable`: unified diff coloured by the diff lexer; empty text gives a dim `words("canvas.diff_empty")`.
- A4 No writes, no subprocess, no network in the module (test: the module source imports none of `subprocess`,
  `socket`, `shutil`, and opens files only for reading).
- A5 One test per criterion; renderables are checked by rendering to plain text with a `rich.console.Console`
  (width 80, no colour) and asserting lines.

Non-goals: getting the diff from git (the controller already returns it), tabs, scrolling, search, images.

DoD: `python3.13 -m unittest tests.test_tui_viewer tests.test_toolchain tests.test_reference` with TMPDIR short, green.
