"""Read tools for the architect: list, read and search the files of the selected project or one of its worktrees.

Every reader sees the last commit (HEAD), never the working tree: the user's uncommitted edits are theirs, and the
planner, the checks and the runs work on HEAD too. The file universe is the regular files of the HEAD tree
(`ls-tree`); symlinks, nested repositories and everything else are not listed, searched or read. Credential files
never leave this module, and every returned line passes through `live.scrub`."""

import fnmatch
import os
import posixpath
import subprocess
import tempfile

from . import live
from .authority import Blocked, git, require

MAX_LINES = 400
MAX_BYTES = 64 * 1024
MAX_PATHS = 2000
MAX_HITS = 200
SNIFF = 8192
CREDENTIAL_NAMES = (".env", ".env.*", ".netrc", "id_rsa*", "id_ed25519*", "*.pem", "*.key", "*.p12", "credentials*")
CREDENTIAL_DIRS = (".git", ".zplan")


def _real(path):
    return os.path.realpath(os.fspath(path))


def _check_root(project, root):
    """The real path of `root`, when it is the project or one of its `git worktree list` paths."""
    real = _real(root)
    allowed = {_real(project)}
    for line in git(project, "worktree", "list", "--porcelain").decode("utf-8", "replace").splitlines():
        if line.startswith("worktree "):
            allowed.add(_real(line[len("worktree "):]))
    if real not in allowed:
        raise Blocked("The read root is neither the project nor its worktree.", family="read.outside_project")
    return real


REGULAR_MODES = (b"100644", b"100755")


def _universe(real):
    """{relative POSIX path: blob id} of the regular files in the HEAD tree under `real`."""
    out = git(real, "ls-tree", "-r", "-z", "HEAD")
    known = {}
    for entry in out.split(b"\0"):
        meta, _, name = entry.partition(b"\t")
        mode, kind, blob = (meta.split(b" ") + [b"", b"", b""])[:3]
        if name and kind == b"blob" and mode in REGULAR_MODES:
            known[os.fsdecode(name)] = blob.decode()
    return known


def uncommitted_paths(project):
    """The paths the working tree has that HEAD does not (modified, staged, untracked), in `git status` order."""
    out = git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    paths, index = [], 0
    while index < len(out):
        entry = out[index]
        index += 1
        if len(entry) > 3:
            paths.append(os.fsdecode(entry[3:]))
            if entry[:1] in b"RC":
                index += 1  # a rename or copy carries its origin as the next field
    return paths


def shown_paths(paths, limit=5):
    """“a, b, c, d, e and N more”: the first `limit` paths of a list, then the count of the rest."""
    return ", ".join(paths[:limit]) + (" and %d more" % (len(paths) - limit) if len(paths) > limit else "")


def _relative(path):
    """A path inside the root as a normalized POSIX string; `..`, absolute and NUL paths are refused."""
    text = os.fspath(path)
    if "\0" in text or os.path.isabs(text) or text.startswith("/") or ".." in text.replace("\\", "/").split("/"):
        raise Blocked("The path is outside the project.", family="read.outside_project")
    return posixpath.normpath(text) if text else ""


def is_credential(relative):
    parts = relative.split("/")
    if any(part.lower() in CREDENTIAL_DIRS for part in parts):
        return True
    name = parts[-1].lower()
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in CREDENTIAL_NAMES)


def _blob(real, relative, known):
    """The blob id of a listed path, or Blocked when it is a credential or not a regular file of the HEAD tree."""
    if is_credential(relative):
        raise Blocked("A credentials file is not read.", family="read.credential")
    if relative not in known:
        raise Blocked("The file is not part of the project.", family="read.outside_project")
    return known[relative]


def _lines(handle):
    """(raw line, cut) pairs; a line longer than MAX_BYTES is cut and the rest of it is skipped."""
    while True:
        raw = handle.readline(MAX_BYTES + 1)
        if not raw:
            return
        cut = len(raw) > MAX_BYTES and not raw.endswith(b"\n")
        if cut:
            raw = raw[:MAX_BYTES]
            while True:
                more = handle.readline(MAX_BYTES + 1)
                if not more or more.endswith(b"\n"):
                    break
        yield raw, cut


def _open(real, blob):
    """The committed bytes of one blob as a seekable file (a spooled copy: the object database is read once)."""
    handle = tempfile.SpooledTemporaryFile(max_size=4 * MAX_BYTES)
    try:
        result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", real,
                                 "cat-file", "blob", blob], stdout=handle, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        require(result.returncode == 0, "Could not read the Git project; an existing commit is required.",
                family="project.unreadable")
    except BaseException:
        handle.close()
        raise
    handle.seek(0)
    if b"\0" in handle.read(SNIFF):
        handle.close()
        raise Blocked("A binary file is not read.", family="read.binary")
    handle.seek(0)
    return handle


def _text(raw):
    return live.scrub(raw.decode("utf-8", "replace").rstrip("\r\n"))


def _listed(known, prefix=""):
    """Sorted relative paths shown to the architect: no credentials."""
    for relative in sorted(known):
        if relative.startswith(prefix) and not is_credential(relative):
            yield relative


def list_files(project, root, prefix=""):
    real = _check_root(project, root)
    _relative(prefix)  # the same boundary as a read; the prefix itself stays a plain string match
    paths = []
    for relative in _listed(_universe(real), prefix):
        if len(paths) == MAX_PATHS:
            return {"paths": paths, "truncated": True}
        paths.append(relative)
    return {"paths": paths, "truncated": False}


def read_file(project, root, path, start=1, count=MAX_LINES):
    real = _check_root(project, root)
    relative = _relative(path)
    if is_credential(relative):
        raise Blocked("A credentials file is not read.", family="read.credential")
    blob = _blob(real, relative, _universe(real))
    start = max(1, int(start))
    count = max(0, int(count))
    take = min(count, MAX_LINES)
    lines, size, truncated = [], 0, False
    with _open(real, blob) as handle:
        for number, (raw, cut) in enumerate(_lines(handle), 1):
            if number < start:
                continue
            if len(lines) == take:
                truncated = take < count  # a line the caller asked for exists beyond the line cap
                break
            if size + len(raw) > MAX_BYTES:
                truncated = True
                break
            size += len(raw)
            lines.append(_text(raw))
            if cut:
                truncated = True
    return {"path": relative, "start": start, "lines": lines, "truncated": truncated}


def search(project, root, text):
    """Case-sensitive substring hits in the HEAD tree (`git grep`, text files only). The substring is matched in the
    scrubbed line, so a search cannot probe the value of a masked credential."""
    real = _check_root(project, root)
    hits = []
    if not text:
        return {"hits": hits, "truncated": False}
    known = _universe(real)
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", real, "grep", "-n", "-I", "-F", "-z",
               "--no-color", "-e", text, "HEAD", "--"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True) as grep:
        try:
            for record in grep.stdout:
                tree_path, _, rest = record.partition(b"\0")
                number, _, raw = rest.partition(b"\0")
                relative = os.fsdecode(tree_path)[len("HEAD:"):]
                if relative not in known or is_credential(relative):
                    continue
                line = _text(raw[:MAX_BYTES])
                if text not in line:
                    continue
                if len(hits) == MAX_HITS:
                    return {"hits": hits, "truncated": True}
                hits.append({"path": relative, "line": int(number), "text": line})
        finally:
            grep.kill()
    return {"hits": hits, "truncated": False}
