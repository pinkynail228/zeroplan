"""Export a verified snapshot as a new local branch of the target repository.

Plumbing only: a temporary index, the snapshot as `--work-tree`, `commit-tree` on the
frozen source revision, and an `update-ref` that refuses an existing branch. The target
worktree, index, HEAD and existing branches are never touched; the snapshot's own `.git`
is never read; nothing is fetched or pushed.
"""

import os
from pathlib import Path
import re
import subprocess
import tempfile

from .authority import Blocked, require

ZERO = "0" * 40
TIMEOUT = 300
IDENTITY = {"GIT_AUTHOR_NAME": "zplan", "GIT_AUTHOR_EMAIL": "zplan@localhost",
            "GIT_COMMITTER_NAME": "zplan", "GIT_COMMITTER_EMAIL": "zplan@localhost"}
OPTIONS = ("-c", "commit.gpgSign=false", "-c", "core.autocrlf=false", "-c", "core.fsmonitor=false",
           "-c", "core.hooksPath=/dev/null")


def environment():
    # Deliberately do not inherit HOME, GIT_*, loader paths, shell startup or editor policy.
    allowed = {k: os.environ[k] for k in ("PATH", "TMPDIR", "LANG", "LC_ALL") if k in os.environ}
    if "PATH" in allowed:
        allowed["PATH"] = "/usr/bin:/bin:" + allowed["PATH"]
    allowed.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0",
                   GIT_OPTIONAL_LOCKS="0", GIT_ATTR_NOSYSTEM="1", GIT_NO_REPLACE_OBJECTS="1")
    return allowed


def run_git(target, *args, env=None, data=None, work_tree=None):
    command = ["git", "--no-optional-locks", *OPTIONS, "-C", str(target)]
    if work_tree is not None:
        command.append("--work-tree=" + str(work_tree))
    try:
        result = subprocess.run(command + list(args), capture_output=True, input=data, timeout=TIMEOUT,
                                start_new_session=True, env={**environment(), **(env or {})})
    except subprocess.TimeoutExpired as error:
        raise Blocked("Git did not answer in time; export aborted.", family="git.failed") from error
    require(result.returncode == 0, "Git refused: " + (args[0] if args else "?") + "; export aborted.", family="git.failed")
    return result.stdout


def scan(workspace, exclude=()):
    """Regular paths of the snapshot; refuse any Git administration below the root.

    Root entries named in `exclude` (and the root `.git`) are not part of the inventory."""
    root, paths, skipped = Path(workspace), [], {".git", *exclude}
    for directory, dirs, files in os.walk(root, followlinks=False):
        if Path(directory) == root:
            dirs[:] = [d for d in dirs if d not in skipped]
            files = [f for f in files if f not in skipped]
        for name in dirs + files:
            relative = (Path(directory) / name).relative_to(root).as_posix()
            require(name.lower() not in {".git", ".gitmodules"},
                    "Snapshot contains a nested .git or submodules: " + relative + "; export forbidden.", family="export.unsupported_layout")
        paths += [(Path(directory) / name).relative_to(root).as_posix() for name in files
                  + [d for d in dirs if (Path(directory) / d).is_symlink()]]
    return sorted(paths)


def tracked(target, source, names):
    """Root entries among `names` that the commit `source` tracks."""
    if not names:
        return []
    listing = run_git(target, "ls-tree", "-z", "--name-only", source, "--", *names).split(b"\0")
    return sorted(name.decode() for name in listing if name)


def ignored(target, workspace, names, env):
    """Names among `names` that the ignore rules of target and snapshot cover."""
    if not names:
        return set()
    # check-ignore exits 1 when no name is ignored; run_git accepts only 0.
    try:
        result = subprocess.run(["git", "--no-optional-locks", *OPTIONS, "-C", str(target), "--work-tree=" + str(workspace),
                                 "check-ignore", "-v", "-n", "-z", "--stdin"],
                                capture_output=True, input=b"".join(n.encode() + b"\0" for n in names), timeout=TIMEOUT,
                                start_new_session=True, env={**environment(), **env})
    except subprocess.TimeoutExpired as error:
        raise Blocked("Git did not answer in time; export aborted.", family="git.failed") from error
    require(result.returncode in (0, 1), "Git refused: check-ignore; export aborted.", family="git.failed")
    found = result.stdout.split(b"\0")[:-1]
    require(len(found) == 4 * len(names), "Git returned an invalid check-ignore; export aborted.", family="git.failed")
    return {found[i + 3].decode() for i in range(0, len(found), 4) if found[i + 2] and not found[i + 2].startswith(b"!")}


def create_branch(target, workspace, source, branch, message, verify, exclude=()):
    """Create `branch` at one commit of the snapshot tree on `source`; return (sha, behind_head).

    `exclude` names root entries of the snapshot (zplan's `.zplan/` control files) that never enter the
    inventory or the temporary index; a source that tracks one of them is refused up front."""
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None, "The frozen source revision is invalid.", family="export.source_missing")
    try:
        run_git(target, "cat-file", "-e", source + "^{commit}")
    except Blocked as error:
        raise Blocked("The source revision is missing from the target repo; export forbidden.", family="export.source_missing") from error
    clash = tracked(target, source, exclude)
    require(not clash, "The target tracks the reserved path %s; export forbidden." % ", ".join(clash), family="export.reserved_path")
    ref = "refs/heads/" + branch
    require(verify(), "The snapshot does not match the verified candidate; export forbidden.", family="export.snapshot_changed")
    paths = scan(workspace, exclude)
    behind = run_git(target, "rev-parse", "--verify", "HEAD^{commit}").decode().strip() != source
    with tempfile.TemporaryDirectory(prefix="zplan-export-") as scratch:
        index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        listing = b"".join(p.encode() + b"\0" for p in paths)
        attributes = run_git(target, "check-attr", "--stdin", "-z", "filter", "ident", "working-tree-encoding",
                             env=index, data=listing, work_tree=workspace).split(b"\0")
        for value in attributes[2::3]:
            require(value in {b"unspecified", b"unset"}, "The target uses filters (LFS/ident/encoding) for snapshot files; export forbidden.", family="export.unsupported_layout")
        # Seed from the frozen source so tracked-but-ignored files stay tracked and real deletions are staged.
        run_git(target, "read-tree", source, env=index)
        # `add -A` already skips an ignored name, and refuses (rc 1) a pathspec exclude that names one.
        hidden = ignored(target, workspace, exclude, index)
        run_git(target, "add", "-A", "--", ":(top)", *[":(top,exclude)" + name for name in exclude if name not in hidden],
                env=index, work_tree=workspace)
        entries = run_git(target, "ls-files", "-s", "-z", env=index).split(b"\0")[:-1]
        require(all(not e.startswith(b"160000 ") for e in entries), "Snapshot contains a gitlink/submodule; export forbidden.", family="export.unsupported_layout")
        names = [e.split(b"\t", 1)[1].decode() for e in entries]
        require(not [n for n in names for x in exclude if n == x or n.startswith(x + "/")],
                "A reserved path got into the tree; export forbidden.")
        # The tree must be the snapshot bytes exactly: no attribute or config conversion.
        staged = {e.split(b"\t", 1)[1].decode(): e.split()[1].decode() for e in entries if e.startswith((b"100644 ", b"100755 "))}
        listed = {e.split(b"\t", 1)[1].decode() for e in entries}
        missing = [p for p in paths if p not in listed]
        if missing:
            # Untracked paths ignored by the snapshot's own .gitignore files travel with the repo and may be left
            # out; anything dropped by target-local excludes would be silent loss, so refuse.
            found = run_git(target, "check-ignore", "-v", "-n", "-z", "--stdin", env=index, work_tree=workspace,
                            data=b"".join(p.encode() + b"\0" for p in missing)).split(b"\0")[:-1]
            # A cache (`__pycache__/` ...) that the target-local exclude drops is not a loss either.
            from .delivery import CLEANUP_CACHES  # delivery imports runs, which imports this module
            local = [found[i + 3].decode() for i in range(0, len(found) - 3, 4)
                     if (Path(found[i].decode()).name != ".gitignore" or Path(found[i].decode()).is_absolute()
                         or not found[i].strip())
                     and not (found[i + 2] and not CLEANUP_CACHES.isdisjoint(found[i + 3].decode().split("/")))]
            require(len(found) == 4 * len(missing) and not local,
                    "Snapshot files did not get into the tree (target ignore/exclude): "
                    + ", ".join(sorted(set(local) or set(missing))[:5]) + "; export forbidden.")
        files = [p for p in paths if p in staged]
        require(len(files) == len(staged), "The snapshot tree does not match the files; export forbidden.", family="export.snapshot_changed")
        if files:
            # Paths as arguments: --stdin-paths is newline-delimited and cannot carry such names.
            hashed = []
            for start in range(0, len(files), 200):
                hashed += run_git(target, "hash-object", "--no-filters", "--",
                                  *[str(Path(workspace) / p) for p in files[start:start + 200]]).decode().split()
            require(hashed == [staged[p] for p in files], "The snapshot tree was changed by a Git conversion; export forbidden.", family="export.snapshot_changed")
        tree = run_git(target, "write-tree", env=index).decode().strip()
    require(verify(), "The snapshot changed during export; export forbidden.", family="export.snapshot_changed")
    existing = subprocess.run(["git", "-C", str(target), "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                              capture_output=True, start_new_session=True, timeout=TIMEOUT, env=environment())
    if existing.returncode == 0:
        # A crash after update-ref but before the Task record was saved leaves exactly this commit; adopt only that.
        sha = existing.stdout.decode().strip()
        require(run_git(target, "rev-parse", sha + "^{tree}").decode().strip() == tree
                and run_git(target, "rev-list", "--parents", "-n", "1", sha).decode().split()[1:] == [source],
                "Branch %s already exists; export refused." % branch, family="export.branch_exists")
        return sha, behind
    arguments = ["commit-tree", tree, "-p", source]
    for paragraph in message:
        arguments += ["-m", paragraph]
    sha = run_git(target, *arguments, env=IDENTITY).decode().strip()
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "Git returned an invalid commit.", family="git.failed")
    try:
        run_git(target, "update-ref", ref, sha, ZERO)
    except Blocked as error:
        raise Blocked("Branch %s was not created (it exists or conflicts); export refused." % branch, family="export.branch_exists") from error
    return sha, behind
