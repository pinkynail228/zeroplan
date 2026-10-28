"""The confirmed «commit» action: the owner's own uncommitted files, committed on their «yes» and never before.

The architect proposes paths and a message; nothing here runs until the owner confirms the card. The engine owns no
state for it: this is `git` and nothing else, under a few rules that keep the owner's tree and index as they were.

- The committed paths are the proposal intersected with the live `status -z --no-renames` at confirm time: files only
  (a directory or a submodule is refused), a rename needs both of its sides, a credential path
  (`project_read.is_credential`) is refused, an ignored or unchanged path is simply absent. `GIT_LITERAL_PATHSPECS=1`
  makes every path literal; nothing is ever `add -f`.
- The commit is `git commit --only -- <paths>` (a temporary index: other staged entries stay staged), with the owner's
  identity and with the hooks (never `--no-verify`). An untracked path is made known by `add -N` first and exactly the
  paths that call added are `rm --cached` again when the commit does not land, so a refusing hook leaves HEAD and the
  index as they were.
- Refused with a fix: no identity, no commit yet, a detached HEAD, a merge or a rebase in progress, a held
  `index.lock`.
- After a commit: its parent must be the HEAD from before and the paths it changed must be a subset of the selection,
  else the result names what the hooks changed.
- The architect sees only the stat and a scrubbed, bounded diff (`diff_text`), never raw file content.

`commit_only` is the one write primitive; the profile commit (`process.Profile._commit_file`) uses it too."""

import os
import signal
import subprocess
from dataclasses import dataclass

from . import live, project_read
from .authority import Blocked

GIT_TIMEOUT = 60
INTERRUPT_WAIT = 5      # seconds git gets to leave after a Ctrl-C before it is killed
MAX_PATHS = 200
MAX_MESSAGE = 4000      # characters of a commit message
MAX_DIFF = 12000        # characters of the scrubbed diff the architect sees
STAMP = "the plan goes stale first; a running milestone will not see the commit"  # said on the confirm card
TRUNCATED = "… (truncated)"
NOTHING = "Nothing to commit"


def _env():
    return dict(os.environ, GIT_LITERAL_PATHSPECS="1")


def _git(project, *args):
    """A finished `git -C project ...` with literal pathspecs; stdout and stderr captured as bytes."""
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, env=_env(), timeout=GIT_TIMEOUT,
                          start_new_session=True)


def _text(result):
    return result.stdout.decode("utf-8", "replace").strip()


def _git_path(project, name):
    """The path git keeps `name` at in this checkout (a worktree has its own), absolute."""
    result = _git(project, "rev-parse", "--git-path", name)
    path = os.fsdecode(result.stdout).strip()
    return path if os.path.isabs(path) else os.path.join(str(project), path)


# Status ---------------------------------------------------------------------------------------------------------

def status_codes(project):
    """{path: two-letter code} of `git status -z --no-renames --untracked-files=all` right now (ignored paths are
    not listed)."""
    result = _git(project, "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all")
    if result.returncode:
        raise Blocked("Git did not show the project state: %s" % _text_of(result), family="commit.refused")
    found = {}
    for record in os.fsdecode(result.stdout).split("\0"):
        if len(record) > 3:
            found[record[3:]] = record[:2]
    return found


def rename_pairs(project):
    """[(old, new)] of the renames `git status -z --renames` sees (a staged `git mv`)."""
    result = _git(project, "status", "--porcelain=v1", "-z", "--renames", "--untracked-files=all")
    fields = os.fsdecode(result.stdout).split("\0")
    pairs, index = [], 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if len(record) > 3 and (record[0] in "RC" or record[1] in "RC") and index < len(fields):
            pairs.append((fields[index], record[3:]))
            index += 1
    return pairs


def _text_of(result):
    return (result.stderr or result.stdout).decode("utf-8", "replace").strip()[:300]


# Refusals with a fix ---------------------------------------------------------------------------------------------

def preflight(project):
    """Raise the one `Blocked` that names the state to fix, or return when git can take a user commit."""
    from .runs import configured_identity
    if configured_identity(project) is None:
        raise Blocked("Git user.name/user.email are not set; committing is refused: git config user.name \"Name\" && "
                      "git config user.email \"email\".", family="readiness.identity")
    if _git(project, "symbolic-ref", "--quiet", "HEAD").returncode:
        raise Blocked("HEAD is detached; committing is refused: switch to a branch (git switch <branch>).",
                      family="commit.refused")
    if _git(project, "rev-parse", "--verify", "--quiet", "HEAD^{commit}").returncode:
        raise Blocked("The project has no commit yet; make the first one yourself.", family="commit.refused")
    if _git(project, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        raise Blocked("A merge is in progress in the project (MERGE_HEAD); committing is refused: finish it or run git merge --abort.",
                      family="commit.refused")
    if any(os.path.exists(_git_path(project, name)) for name in ("rebase-merge", "rebase-apply")):
        raise Blocked("A rebase is in progress in the project; committing is refused: git rebase --continue or git rebase --abort.",
                      family="commit.refused")
    if os.path.exists(_git_path(project, "index.lock")):
        raise Blocked("index.lock is held: another git is working in the project; wait for it or, if it is not "
                      "running, delete %s." % _git_path(project, "index.lock"), family="commit.refused")


# Selection -------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Selection:
    """What a proposal comes to against the live status: `paths` are committed (sorted), `untracked` is the part of
    them `status` shows as `??`, `refused` is `(path, reason)` for every proposed path left out."""
    paths: tuple
    untracked: tuple
    refused: tuple

    def refusal_line(self):
        return "; ".join("%s — %s" % item for item in self.refused)


def select(project, proposed):
    """The `Selection` of the proposed paths now. Proposed paths that are not strings are refused by the caller."""
    live_codes = status_codes(project)
    chosen, refused, seen = {}, [], set()
    for raw in proposed:
        if raw in seen:
            continue
        seen.add(raw)
        try:
            path = project_read._relative(raw)
        except Blocked:
            refused.append((raw, "path outside the project"))
            continue
        if not path or raw.endswith("/"):
            refused.append((raw, "a file is needed, not a directory"))
        elif project_read.is_credential(path):
            refused.append((path, "credentials file"))
        elif path not in live_codes:
            refused.append((path, "no change in git status (the file is unchanged or ignored)"))
        elif "U" in live_codes[path] or live_codes[path] in ("AA", "DD"):
            refused.append((path, "merge conflict"))
        elif os.path.isdir(os.path.join(str(project), path)) and not os.path.islink(os.path.join(str(project), path)):
            refused.append((path, "directory or submodule: files only"))
        else:
            chosen[path] = live_codes[path]
    for old, new in rename_pairs(project):
        if (old in chosen) != (new in chosen):
            for path in (old, new):
                if chosen.pop(path, None) is not None:
                    refused.append((path, "rename %s → %s: both paths are needed" % (old, new)))
    paths = tuple(sorted(chosen))
    return Selection(paths, tuple(p for p in paths if chosen[p] == "??"), tuple(refused))


# What the architect and the card see -------------------------------------------------------------------------

def _capped(args, cwd, limit):
    """stdout of a git command, at most `limit` bytes read (the rest of a huge diff is never read)."""
    process = subprocess.Popen(["git", *args], cwd=str(cwd), env=_env(), stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        data = process.stdout.read(limit + 1)
    finally:
        process.kill()
        process.stdout.close()
        process.wait()
    return data[:limit].decode("utf-8", "replace"), len(data) > limit


def stat_text(project, selection):
    """`git diff --stat HEAD -- <paths>` of the selection, then the untracked files (a diff has none of them)."""
    lines = []
    tracked = [p for p in selection.paths if p not in selection.untracked]
    if tracked:
        text, _ = _capped(["-C", str(project), "diff", "--stat=120", "--no-ext-diff", "HEAD", "--", *tracked], project,
                          MAX_DIFF)
        lines.append(text.rstrip())
    lines.extend("%s | new file" % path for path in selection.untracked)
    return "\n".join(line for line in lines if line)


def diff_text(project, selection):
    """The diff of the selection as the architect may read it: scrubbed line by line (`live.scrub`), at most
    `MAX_DIFF` characters, a binary file as git's own «Binary files differ»."""
    tracked = [p for p in selection.paths if p not in selection.untracked]
    parts = []
    if tracked:
        parts.append(_capped(["-C", str(project), "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", *tracked],
                             project, MAX_DIFF * 2)[0])
    for path in selection.untracked:
        parts.append(_capped(["diff", "--no-index", "--no-ext-diff", "--no-textconv", "--", os.devnull, path], project,
                             MAX_DIFF * 2)[0])
    text = "\n".join(live.scrub(line) for line in "".join(parts).splitlines())
    return text[:MAX_DIFF] + (TRUNCATED if len(text) > MAX_DIFF else "")


def clean_message(message):
    """The commit message the owner will see: stripped, not empty, no NUL, at most `MAX_MESSAGE` characters."""
    text = message.strip() if isinstance(message, str) else ""
    if not text or "\0" in text or len(text) > MAX_MESSAGE:
        raise Blocked("A commit message is required: a non-empty string of up to %d characters." % MAX_MESSAGE,
                      family="architect.request_invalid")
    return text


# The write -------------------------------------------------------------------------------------------------------

def commit_only(project, paths, message, untracked=(), terminal=False):
    """`git commit --only -m message -- paths` for paths already checked; the CompletedProcess of the commit.

    The `untracked` ones are `add -N` first; whenever the commit does not land (a refusing hook, an error, an
    interrupt) exactly those are `rm --cached` again, so HEAD and the index are as they were. `terminal=True` hands
    the terminal to git (hooks and signing may ask the owner; the caller has suspended the interface); otherwise the
    output is captured. Hooks always run."""
    added = list(untracked)
    head = _head(project)
    saved = _index_snapshot(project) if added else None
    if added:
        result = _git(project, "add", "-N", "--", *added)
        if result.returncode:
            _undo(project, added, saved)
            raise Blocked("git add -N failed: %s" % _text_of(result), family="commit.failed")
    command = ["git", "-C", str(project), "commit", "--only", "-m", message, "--", *paths]
    try:
        if terminal:
            done = _run(command, env=_env())
        else:
            done = _run(command, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    except BaseException:
        if _head(project) == head:
            _undo(project, added, saved)
        raise
    if done.returncode or _head(project) == head:
        _undo(project, added, saved)
    return done


def _run(command, **options):
    """`subprocess.run`, except that a Ctrl-C first lets git take its own SIGINT and drop its `index.lock` (a git
    killed at once leaves the lock, and then the index cannot be put back); it is killed only if it does not leave."""
    with subprocess.Popen(command, **options) as process:
        try:
            out, err = process.communicate()
        except KeyboardInterrupt:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=INTERRUPT_WAIT)
            except subprocess.TimeoutExpired:
                process.kill()
            raise
        return subprocess.CompletedProcess(command, process.returncode, out, err)


def _head(project):
    return _text(_git(project, "rev-parse", "--verify", "--quiet", "HEAD"))


def _index_snapshot(project):
    """(the index file's bytes, `ls-files -s -z`) right now; the bytes are None when there is no index file."""
    try:
        with open(_git_path(project, "index"), "rb") as stream:
            raw = stream.read()
    except OSError:
        raw = None
    return raw, _git(project, "ls-files", "-s", "-z").stdout


def _undo(project, added, saved):
    """`rm --cached` of exactly the paths `add -N` made known. If the index then holds the very entries it held
    before, its file is put back byte for byte (`add -N` drops git's cache-tree extension, which nothing else
    rebuilds), through `index.lock` as git itself writes it; a held lock leaves the index as `rm --cached` made it."""
    if not added:
        return
    result = _git(project, "rm", "--cached", "-q", "--", *added)
    if result.returncode:
        raise Blocked("The commit was not made, but the index did not return to its previous state: git rm --cached -- %s (%s)"
                      % (" ".join(added), _text_of(result)), family="commit.failed")
    raw, entries = saved
    if raw is None or _git(project, "ls-files", "-s", "-z").stdout != entries:
        return
    index = _git_path(project, "index")
    try:
        fd = os.open(index + ".lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        return
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(index + ".lock", index)
    except OSError:
        try:
            os.unlink(index + ".lock")
        except OSError:
            pass


@dataclass(frozen=True)
class Committed:
    commit: str
    paths: tuple
    refused: tuple
    extra: tuple      # paths the commit changed beyond the selection (hooks)
    parent_moved: bool  # the commit's parent is not the HEAD from before

    def lines(self):
        found = ["Committed %s: %s." % (self.commit[:12], ", ".join(self.paths))]
        if self.refused:
            found.append("Not included: " + "; ".join("%s — %s" % item for item in self.refused) + ".")
        if self.extra:
            found.append("Hooks also changed: %s." % ", ".join(self.extra))
        if self.parent_moved:
            found.append("The commit's parent is not the previous HEAD: check git log.")
        return found


def commit(project, proposed, message, terminal=False):
    """The owner's confirmed commit: preflight, the live selection, `commit_only`, then the checks of what landed.

    Raises `Blocked` (family `commit.refused` / `readiness.identity`, `commit.failed`) when nothing was committed;
    the tree, HEAD and index are then as they were. `Committed` otherwise."""
    message = clean_message(message)
    preflight(project)
    selection = select(project, proposed)
    if not selection.paths:
        raise Blocked("%s: %s." % (NOTHING, selection.refusal_line() or "the path list is empty"), family="commit.refused")
    before = _head(project)
    try:
        done = commit_only(project, selection.paths, message, selection.untracked, terminal)
    except KeyboardInterrupt:  # Ctrl-C in a hook or a signing prompt: `commit_only` has already put the index back
        landed = _head(project) != before
        raise Blocked("Commit interrupted%s." % (": the commit is already made, check git log" if landed
                                              else "; HEAD and the index are as they were"), family="commit.failed") from None
    after = _head(project)
    if done.returncode or after == before:
        detail = "" if terminal else ": " + (done.stderr or done.stdout).decode("utf-8", "replace").strip()[-600:]
        raise Blocked("git commit made no commit (code %s)%s; HEAD and the index are as they were." % (done.returncode, detail),
                      family="commit.failed")
    parent = _text(_git(project, "rev-parse", "--verify", "--quiet", after + "^"))
    changed = os.fsdecode(_git(project, "diff-tree", "-r", "--no-renames", "--name-only", "-z", "--no-commit-id",
                               after).stdout).split("\0")
    extra = tuple(sorted(set(path for path in changed if path) - set(selection.paths)))
    return Committed(after, selection.paths, selection.refused, extra, parent != before)
