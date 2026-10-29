"""Read-only canvas views: a project file or a unified diff as a Rich renderable (release 0.5.2, run u3-viewer).

`resolve(root, name)` maps a relative name to the file under the project root and refuses anything else with a
`ViewError` that carries a catalog id and its format values — never a message: the wording belongs to the string
catalog (u2, `terminal_planner/tui/strings.py`). `file_view(path, ...)` and `diff_view(text, ...)` then turn the
resolved file, or a unified diff the controller already produced, into the renderable the right-hand canvas shows,
as in the approved lab (`devtools/ui-lab/work.py`, `_render_view`): a `rich.syntax.Syntax` with the "ansi_dark"
theme and the default background, line numbers and word wrap for a file, the "diff" lexer without line numbers for
a diff.

A file over `max_bytes` shows only its first `max_bytes` and closes with a dim line whose text comes from `words`,
the callable `(id, **values) -> str` the integration run passes in; the default here is the built-in Russian
wording that the string catalog replaces. The size values it receives are whole kilobytes, rounded up.

The owner never edits through these views: the module only reads (A4) and never spawns a process or touches the
network.
"""

from pathlib import Path

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text

# The default cut: a file larger than this shows only its head (A2).
MAX_BYTES = 200_000

# Suffix -> the Pygments lexer name of the canvas; a suffix not listed here is plain text.
LEXERS = {".py": "python", ".md": "markdown", ".json": "json", ".toml": "toml",
          ".yaml": "yaml", ".yml": "yaml", ".sh": "bash"}

THEME = "ansi_dark"


class ViewError(RuntimeError):
    """A refusal shown to the owner. `id` is a stable catalog id (`note.view_*`); `values` holds that id's format
    values, so the message text comes from the string catalog and never from this module."""

    def __init__(self, id, **values):
        super().__init__(id)
        self.id = id
        self.values = values


def words(id, **values):
    """The built-in English wording of the canvas ids, used until the string catalog (u2) supplies the chosen
    language. An unknown id is a programming error and raises KeyError, never a line shown to the owner."""
    return {
        "canvas.view_cut": "…showing the first {shown} of {total} KB",
        "canvas.diff_empty": "No changes.",
    }[id].format(**values)


def _kb(size):
    """`size` bytes as whole kilobytes, rounded up, for the `canvas.view_cut` values."""
    return (size + 1023) // 1024


def resolve(root, name):
    """The file under `root` for a relative `name`; a `ViewError` id otherwise (A1)."""
    if not name:
        raise ViewError("note.view_empty")
    if Path(name).is_absolute():
        raise ViewError("note.view_outside", name=name)
    root = Path(root).resolve()
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise ViewError("note.view_outside", name=name)
    if not target.exists():
        raise ViewError("note.view_missing", name=name)
    if target.is_dir():
        raise ViewError("note.view_directory", name=name)
    return target


def _decode(data, name):
    """`data` as UTF-8 text; anything else raises `note.view_binary` (A2). The whole file is decoded, so a bad
    byte anywhere — also past the size cap — is refused instead of silently shown as a truncated head."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ViewError("note.view_binary", name=name)


def _head(data, max_bytes):
    """The first `max_bytes` of `data`, dropping whole a multi-byte character the cap splits. `data` is already
    known to be UTF-8 text, so a decoding error here can only be that partial character."""
    if len(data) <= max_bytes:
        return data
    head = data[:max_bytes]
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as error:
        return head[:error.start]
    return head


def file_view(path, max_bytes=MAX_BYTES, words=words, code=THEME):
    """`path` as a syntax renderable: line numbers and word wrap, the lexer by suffix (A2). A file over `max_bytes`
    is cut to its first `max_bytes` and closes with the dim `canvas.view_cut` line; a file that is not UTF-8 text
    raises `ViewError` id `note.view_binary`. `code` is the Pygments theme (`ansi_dark`, or `ansi_light` on a light
    terminal)."""
    path = Path(path)
    data = path.read_bytes()
    text = _decode(data, path.name)  # the whole file must be text, not just the head shown (A2)
    lexer = LEXERS.get(path.suffix.lower(), "text")
    if len(data) > max_bytes:
        return Group(Syntax(_head(data, max_bytes).decode("utf-8"), lexer, theme=code, line_numbers=True,
                            word_wrap=True, background_color="default"),
                     Text(words("canvas.view_cut", shown=_kb(max_bytes), total=_kb(len(data))), style="dim"))
    return Syntax(text, lexer, theme=code, line_numbers=True, word_wrap=True, background_color="default")


def diff_view(text, words=words, code=THEME):
    """A unified diff coloured by the diff lexer, without line numbers (A3); empty text is the dim
    `canvas.diff_empty` line."""
    if not text:
        return Text(words("canvas.diff_empty"), style="dim")
    return Syntax(text, "diff", theme=code, background_color="default")
