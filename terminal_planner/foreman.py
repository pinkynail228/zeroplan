"""The foreman's mechanical checks of a brief against the project before a run starts (A4a).

`inspect(project, brief)` returns findings `{"check", "blocking", "text"}` sorted by check then text; an empty list
is a pass. Every file access goes through `project_read` (the HEAD tree, credentials skipped); a write_set path with
uncommitted changes is a non-blocking warning: the run starts from HEAD and does not see them."""

import fnmatch
import posixpath
import re

from . import project_read
from .authority import BRIEF_KEYS, Blocked, brief_problem, canonical

MAX_BRIEF_BYTES = 4096
MAX_WRITE_SET = 12
PATH_SUFFIXES = (".py", ".md", ".json", ".sh", ".toml")
PLATFORM_TOKENS = ("HOME", "XDG_", "/home", "sys.version", "sys.platform")
QUOTED = re.compile(r"`([^`\s]+)`")
IDENTIFIER = re.compile(r"[A-Za-z0-9_.]+")
LINE_SUFFIX = re.compile(r"^(.*):(\d+)$")


def _norm(path):
    return posixpath.normpath(path) if path else ""


def _tracked(project, path):
    """True when `path` is a listed file; the exact path sorts first among the paths sharing its prefix."""
    if not path or path.startswith(("/", "../")) or path == "..":
        return False
    return path in project_read.list_files(project, project, path)["paths"][:1]


def _has_files_under(project, directory):
    if directory.startswith("/") or directory == ".." or directory.startswith("../"):
        return False  # outside the project: nothing is listed there
    return bool(project_read.list_files(project, project, directory + "/" if directory else "")["paths"])


def _path_token(token):
    """(path, line or None) when the quoted token is a path token, else None."""
    match = LINE_SUFFIX.match(token)
    path, line = (match.group(1), int(match.group(2))) if match else (token, None)
    if "/" in path or path.endswith(PATH_SUFFIXES):
        return path, line
    return None


def _line_exists(project, path, line):
    try:
        return bool(project_read.read_file(project, project, path, start=line, count=1)["lines"])
    except Blocked:
        return True  # unreadable (binary, credential): the line count cannot be judged


def _found(project, identifier):
    names = [identifier]
    last = identifier.rstrip(".").rsplit(".", 1)[-1]
    if last and last != identifier:
        names.append(last)  # `module.name` names a definition, which the source spells as `name`
    return any(project_read.search(project, project, name)["hits"] for name in names)


def _uncommitted_writes(project, write_set):
    """{write_set entry: its uncommitted paths}: an entry is a file, a directory or a glob, as the brief spells it."""
    changed = project_read.uncommitted_paths(project)
    found = {}
    for entry in write_set:
        hit = [path for path in changed
               if path == entry or path.startswith(entry.rstrip("/") + "/") or fnmatch.fnmatchcase(path, entry)]
        if hit:
            found[entry] = hit
    return found


def _whole_text(project, path):
    parts, start = [], 1
    while True:
        part = project_read.read_file(project, project, path, start=start)
        parts.extend(part["lines"])
        if not part["lines"]:
            return "\n".join(parts)
        start += len(part["lines"])


def inspect(project, brief):
    problem = brief_problem(brief)
    if problem is not None:
        return [{"check": "F5", "blocking": True, "text": problem}]
    found = set()

    def add(check, blocking, text):
        found.add((check, blocking, text))

    write_set = [_norm(p) for p in brief["write_set"]]
    tracked_writes = []
    for path in write_set:
        if _tracked(project, path):
            tracked_writes.append(path)
        elif not _has_files_under(project, posixpath.dirname(path)):
            add("F1", True, "write_set: %s — neither a file nor a directory with files in the project" % path)

    for entry, paths in _uncommitted_writes(project, write_set).items():
        add("F6", False, "write_set: %s — not committed (%s); the run sees the last commit and will not see these edits"
            % (entry, project_read.shown_paths(paths)))

    sources = [("reuse", brief["reuse"])]
    for item in brief["criteria"]:
        sources.append(("criterion %s text" % item["id"], item["text"]))
        sources.append(("criterion %s example" % item["id"], item["example"]))
    for where, body in sources:
        for token in QUOTED.findall(body):
            parsed = _path_token(token)
            if parsed is not None:
                path, line = parsed
                path = _norm(path)
                tracked = _tracked(project, path)
                if not tracked and path not in write_set and not (token.endswith("/") and _has_files_under(project, path)):
                    add("F1", True, "%s: %s — not in the project or in write_set" % (where, token))
                elif tracked and line is not None and (line < 1 or not _line_exists(project, path, line)):
                    add("F1", True, "%s: %s — the file has fewer lines" % (where, token))
            elif where == "reuse" and IDENTIFIER.fullmatch(token) and not _found(project, token):
                add("F1", True, "reuse: %s — not found in the project" % token)

    if "linux" not in brief["dod"].lower():
        for path in tracked_writes:
            if not path.startswith("tests/"):
                continue
            try:
                body = _whole_text(project, path)
            except Blocked:
                continue
            for token in PLATFORM_TOKENS:
                if token in body:
                    add("F3", False, "%s: %s — platform-dependent, but dod does not mention linux" % (path, token))

    size = len(canonical({key: brief[key] for key in BRIEF_KEYS}).encode("utf-8"))
    if size > MAX_BRIEF_BYTES:
        add("F5", True, "brief: %d bytes against a limit of %d" % (size, MAX_BRIEF_BYTES))
    if len(write_set) > MAX_WRITE_SET:
        add("F5", True, "write_set: %d files against a limit of %d" % (len(write_set), MAX_WRITE_SET))

    return [{"check": check, "blocking": blocking, "text": text} for check, blocking, text in sorted(found, key=lambda f: (f[0], f[2]))]
