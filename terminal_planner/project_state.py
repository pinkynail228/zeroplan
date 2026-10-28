"""The project STATE file: the architect's plan, next step, open questions and decisions, kept across session resets.

`<project>/.zplan/STATE.md` is written only through `write` (the architect's `zplan_state_update` tool): a bounded
text of exactly four `## ` sections, every line passed through `live.scrub`, replaced atomically. The file would make
the project dirty (the planner refuses a dirty project) and change the freshness hash, so before its first write the
repository's `<git common dir>/info/exclude` gets the line `/.zplan/` (a local rule, never a tracked file)."""

import os
from pathlib import Path
import tempfile

from . import live
from .authority import Blocked, PersistenceError, common_directory

SECTIONS = ("Now", "Next", "Open", "Decisions")
MAX_BYTES = 6144
EXCLUDE = "/.zplan/"


def path(project):
    return Path(project) / ".zplan" / "STATE.md"


def validate(text):
    """Raise `Blocked` naming the rule the text breaks; return None when it is a valid STATE."""
    if not isinstance(text, str):
        raise Blocked("STATE: text must be a string.", family="action.refused")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise Blocked("STATE: text must be UTF-8.", family="action.refused") from None
    if size > MAX_BYTES:
        raise Blocked("STATE: %d bytes, at most %d." % (size, MAX_BYTES), family="action.refused")
    found = [line[3:].strip() for line in text.split("\n") if line.startswith("## ")]
    if found != list(SECTIONS):
        raise Blocked("STATE: the `## ` headings must be exactly %s in this order, got %s."
                      % (", ".join(SECTIONS), ", ".join(found) or "none"), family="action.refused")


def read(project):
    try:
        return path(project).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def ensure_excluded(project, lines):
    """Ensure each of `lines` in the repository's info/exclude (created if missing, existing lines kept, added once)."""
    try:
        target = common_directory(Path(project)) / "info" / "exclude"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            current = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        present = {line.strip() for line in current.splitlines()}
        missing = [line for line in dict.fromkeys(lines) if line not in present]
        if not missing:
            return
        with open(target, "a", encoding="utf-8") as stream:
            stream.write(("" if not current or current.endswith("\n") else "\n") + "".join(line + "\n" for line in missing))
    except OSError as error:
        raise PersistenceError("exclude") from error


def _exclude(project):
    ensure_excluded(project, (EXCLUDE,))


def exclude_caches(project):
    """Ensure one `<cache>/` line per `CLEANUP_CACHES` name (any depth) in the repository's info/exclude, so a tool
    cache never makes the project dirty and a worker's `git add --all` never stages it. Tracked files stay tracked."""
    from .delivery import CLEANUP_CACHES  # delivery imports runs, which imports this module
    ensure_excluded(project, [name + "/" for name in sorted(CLEANUP_CACHES)])


def _replace(target, text):
    stage, name = "temp_write", None
    try:
        target.parent.mkdir(mode=0o700, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=".state-")  # 0o600
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            stage = "file_fsync"
            os.fsync(stream.fileno())
        stage = "replace"
        os.replace(name, target)
        stage = "directory_fsync"
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise PersistenceError(stage) from error
    finally:
        if name is not None:
            try:
                os.unlink(name)
            except OSError:
                pass  # after a successful replace the name is gone; cleanup never hides the real cause


def write(project, text):
    """Validate, scrub and store `text`; return what was stored."""
    validate(text)
    stored = "\n".join(live.scrub(line) for line in text.split("\n"))
    validate(stored)  # a mask may be longer than the value it hides
    _exclude(project)
    _replace(path(project), stored)
    return stored
