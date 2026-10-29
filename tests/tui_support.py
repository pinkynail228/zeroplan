"""Shared helpers for the TUI tests: Textual import (from the offline wheelhouse when the interpreter lacks it),
a plain-text view of a Pilot screen, and fixture stores for the shell.

i6: the main screen reads its own texts from the UI string catalog, whose language comes from
`$XDG_CONFIG_HOME/planning-kit/ui.json` (falling back to the locale). Every in-process test imports this module
before it imports the app, so the language is pinned here, once per process, to a private config directory holding
`{"language": "ru"}`: the Russian assertions of the existing tests stay green and the first-run chooser never shows
up. A test that needs another language — or the first-run case — points `XDG_CONFIG_HOME` at its own directory (the
catalog re-reads the file on every call, so per-test `patch.dict` works)."""

import atexit
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

WHEELHOUSE = os.environ.get("ZPLAN_TEST_WHEELHOUSE")
SKIP_WHEELS = ("setuptools-", "wheel-")


def ensure_textual():
    """True when `import textual` works, borrowing the pure-Python wheels of ZPLAN_TEST_WHEELHOUSE if needed."""
    try:
        import textual  # noqa: F401
        return True
    except ImportError:
        pass
    if not WHEELHOUSE or not Path(WHEELHOUSE).is_dir():
        return False
    target = Path(tempfile.mkdtemp(prefix="zs-tui-"))
    atexit.register(shutil.rmtree, str(target), True)
    for wheel in sorted(Path(WHEELHOUSE).glob("*.whl")):
        if not wheel.name.startswith(SKIP_WHEELS):
            zipfile.ZipFile(wheel).extractall(target)
    sys.path.insert(0, str(target))
    try:
        import textual  # noqa: F401
    except ImportError:
        sys.path.remove(str(target))
        return False
    return True


HAVE_TEXTUAL = ensure_textual()

# The pinned language: a per-process config directory the tests own (never the runner's own preferences). The file
# lives where `strings.store_path()` looks, so the catalog resolves `ru` before any test module imports the app.
CONFIG_HOME = tempfile.mkdtemp(prefix="zs-tui-config-")
atexit.register(shutil.rmtree, CONFIG_HOME, True)
os.environ["XDG_CONFIG_HOME"] = CONFIG_HOME
for _name in ("ZPLAN_THEME", "COLORFGBG"):  # the runner's own terminal never picks the theme a test sees
    os.environ.pop(_name, None)
_PINNED_UI = Path(CONFIG_HOME) / "planning-kit" / "ui.json"
_PINNED_UI.parent.mkdir(parents=True, exist_ok=True)
_PINNED_UI.write_text('{"language": "ru"}\n', encoding="utf-8")


def screen_lines(app):
    """What the user sees on the current screen, row by row (trailing blanks stripped)."""
    return [strip.text.rstrip() for strip in app.screen._compositor.render_strips()]


def screen_text(app):
    return "\n".join(screen_lines(app))
