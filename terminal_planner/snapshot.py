"""Byte-level identity of an isolated tree; never execute writer-controlled Git."""

import hashlib
import os
from pathlib import Path
import stat

from .authority import Blocked, canonical, require


def candidate(root, exclude=()):
    """Hash sorted path/type/mode/content identities, including Git metadata.

    Symlinks are hashed as links, never traversed. Special files fail closed.
    O_NOFOLLOW prevents a file being replaced with a link during observation.
    Callers must first prove that the owned writer boundary is stopped.
    Root entries named in `exclude` are left out.
    """
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "Invalid snapshot root.", family="project.unreadable")
    entries = {}
    def unreadable(error):
        raise error
    try:
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
            if Path(directory) == root:
                dirs[:] = [d for d in dirs if d not in exclude]
                files = [f for f in files if f not in exclude]
            for name in dirs + files:
                path = Path(directory) / name
                info = path.lstat()
                relative = path.relative_to(root).as_posix()
                mode = stat.S_IMODE(info.st_mode)
                if stat.S_ISLNK(info.st_mode):
                    entries[relative] = ["link", mode, os.readlink(path)]
                elif stat.S_ISDIR(info.st_mode):
                    entries[relative] = ["directory", mode]
                else:
                    require(stat.S_ISREG(info.st_mode), "Special file in native snapshot.", family="export.unsupported_layout")
                    require(info.st_nlink == 1, "Hard-linked candidate could be writable through another mount.", family="export.unsupported_layout")
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as stream:
                        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Snapshot file changed type.", family="export.snapshot_changed")
                        h = hashlib.sha256()
                        for block in iter(lambda: stream.read(65536), b""):
                            h.update(block)
                    entries[relative] = ["file", mode, h.hexdigest()]
        encoded = canonical(entries).encode()
    except (OSError, UnicodeError) as error:
        raise Blocked("Native snapshot unavailable; freshness cannot be proved.", family="project.unreadable") from error
    # Protocol EnumLabel requires an alphabetic initial character.
    return "candidate_" + hashlib.sha256(encoded).hexdigest()


def listed(root, paths):
    """Like `candidate`, but only for the given relative paths (the exportable product files).

    A missing path is hashed as deleted; a path below a symlinked directory fails closed; a listed
    directory (an untracked nested repository) is hashed as a directory. Files outside `paths`
    (ignored dependency caches, hardlinked package stores) are never read.
    """
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "Invalid snapshot root.", family="project.unreadable")
    entries, plain = {}, {root}
    try:
        for relative in sorted(set(paths)):
            path = root / relative.rstrip("/")
            for parent in reversed(path.parents):
                if parent in plain or root not in (parent, *parent.parents):
                    continue
                info = parent.lstat() if parent.exists() or parent.is_symlink() else None
                require(info is None or stat.S_ISDIR(info.st_mode), "Product path below a link: " + relative, family="export.unsupported_layout")
                if info is not None:
                    plain.add(parent)
            try:
                info = path.lstat()
            except FileNotFoundError:
                entries[relative] = ["deleted"]
                continue
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                entries[relative] = ["link", mode, os.readlink(path)]
            elif stat.S_ISDIR(info.st_mode):
                entries[relative] = ["directory", mode]
            else:
                require(stat.S_ISREG(info.st_mode), "Special file in native snapshot.", family="export.unsupported_layout")
                require(info.st_nlink == 1, "Hard-linked candidate could be writable through another mount.", family="export.unsupported_layout")
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Snapshot file changed type.", family="export.snapshot_changed")
                    h = hashlib.sha256()
                    for block in iter(lambda: stream.read(65536), b""):
                        h.update(block)
                entries[relative] = ["file", mode, h.hexdigest()]
        encoded = canonical(entries).encode()
    except (OSError, UnicodeError) as error:
        raise Blocked("Native snapshot unavailable; freshness cannot be proved.", family="project.unreadable") from error
    return "candidate_" + hashlib.sha256(encoded).hexdigest()
