"""The bounded check executor: one disposable checkout of a commit and the profile checks run in it (S1b1/S1b1b).

Its one caller is the merge gate (`runs.MilestoneRuns.gate_merge`, A7a; tests/test_checks.py pins that); it holds no store, Authority
session, catalog entry or screen, and a refusal is a returned value (R-1). `checkout` (R-2) clones the project into a
fresh directory under `root`, detaches at the commit, verifies HEAD and its tree and removes it on every exit path;
`run_check` (R-3) runs one argv list under the s1b1b guard, killing the group at `timeout_s`; `run_checks`/`qualify`
(R-5) run the list in order, stopping at the first failure; the tail (R-4) is `live._shown`, the last 200 lines, cut
to 32 KiB at a line boundary. The guard (`check_guard.py`, stdlib only, started by absolute path) outlives zplan in
its own session and holds the check's own process group, so a SIGKILL of zplan still reaps that group and, for a
leased checkout, removes it (M-1..M-5; R-C); `sweep` (R-4) reaps what a guard death or a power loss left behind."""

import contextlib
from collections import deque
import fcntl, os, re, select, shutil, signal, socket, stat, subprocess, sys, threading, time
from pathlib import Path

from . import export, live
from .authority import digest

SHA = re.compile(r"[0-9a-fA-F]{40}")  # a 40-hex identity, either case (R-2)
WINDOW = 64 * 1024  # raw bytes of a check's output held while it streams (R-4)
READ = 65536  # bytes of one read from the pipe; tests inject a smaller size (R-4)
GRACE = 2.0  # seconds the group may outlive its parent after that parent's exit (R-3)
POLL = 0.2  # seconds one select may wait before the parent is looked at again (R-3)
REAP = 15.0  # seconds `_reap` waits for the guard: it SIGKILLs group C before it exits, so its exit is the group's
             # death (the guard's own `GONE` bound plus a margin, M-3)
MAX_LINES = 200  # lines of the stored tail (R-4)
MAX_BYTES = 32768  # UTF-8 bytes of the stored tail (R-4)
PREFIX = "checkout-"
GUARD = str(Path(__file__).resolve().parent / "check_guard.py")  # the guard, always run by absolute path (M-1)
LEASES = {}  # resolved checkout directory (str) -> the flock fd zplan and group C hold (M-5)
ABANDONED = set()  # lease keys of an unconfirmed stop: `checkout`'s exit keeps the pair for the later recovery (R-C)
ORPHANS = []  # guard `Popen`s an unconfirmed stop left unreaped; only `_drain` (under `ORPHANS_LOCK`) drops them
ORPHANS_LOCK = threading.Lock()  # guards every read-modify-write of `ORPHANS`: the GIL never makes one atomic
TRIES = 8  # bounded `O_EXCL` attempts for one lease name: a taken name is retried with a fresh random one and, if
           # eight in a row are taken, the collision is raised with every pre-existing entry left exactly as it was


def forget_after_remove():
    """A no-op seam a test replaces to interleave a removal between `_forget`'s directory and its lock (R-K)."""


def sweep_after_open():
    """A no-op seam a test replaces to interleave a publication between sweep's lock `open` and its `flock` (R-W)."""


def lease_after_create():
    """A no-op seam a test replaces to interleave a sweep between `_lease`'s lock create and its `flock` (R-W)."""


class _Supervisor:
    """zplan's handle on one guard: the guard process, the lifeline, group C's leader and its resolved status."""

    def __init__(self, process, lifeline):
        self.process = process
        self.lifeline = lifeline
        self.pid = None  # group C's leader and pgid, read from `S`; None until the guard reports the spawn (M-3)


class _Lock:
    """The owning handle of one lease lock: a file object over the flocked descriptor (R-D/R-K).

    R-D wants an object that owns the descriptor, never a raw integer carried around: this handle is what `checkout`
    keeps for the checkout's lifetime, what `fileno` lends to the guard's spawn, and what R-K's order closes last."""

    def __init__(self, descriptor):
        self.handle = os.fdopen(descriptor, "r+")

    def fileno(self):
        return self.handle.fileno()

    def close(self):
        self.handle.close()


@contextlib.contextmanager
def checkout(project, commit, tree, root):
    """A disposable checkout of `commit`/`tree` under `root`, removed on every exit path (R-2/M-5).

    Yields the checkout `Path`, or the refusal `{"refused": "checkout" | "tree_mismatch"}` of a failed clone, detach
    or verification -- a value, never an exception; a bad identity or a `root` inside the project is a ValueError.
    The directory comes with a sibling `checkout-*.lock` held for the checkout's lifetime: that fd travels to the
    guard and to the check, so a surviving check keeps the entry busy long enough for a later recovery to see it."""
    project, root = Path(project).resolve(), Path(root).resolve()  # resolved before `git -C`: a relative path stays so
    if not all(isinstance(value, str) and SHA.fullmatch(value) for value in (commit, tree)):  # R-2: both are 40-hex
        raise ValueError("commit and tree must be 40 hex characters")
    commit, tree = commit.lower(), tree.lower()  # git prints lowercase, so an uppercase identity still matches
    if root == project or project in root.parents or root in project.parents:  # neither may hold the other (R-P)
        raise ValueError("root and project must be outside each other")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory, lock, key = _lease(root)
    try:
        refusal = _prepare(directory, project, commit, tree)
        yield refusal if isinstance(refusal, dict) else directory
    finally:
        try:
            _drain()  # the guards of unconfirmed stops go before this exit: they own no lease of this context (R-C)
        finally:
            _forget(key, directory, lock, key in ABANDONED)


def run_check(check, cwd, env, popen=subprocess.Popen, clock=time.monotonic):
    """One check's evidence dict (R-3): argv-only execution under the guard, deadline, group kill, bounded tail.

    `_refuse_nul` (R-A) runs before any descriptor is acquired, so a NUL argv element leaves the process untouched.
    `popen` then starts the guard in its own session with a lifeline and, for a leased `cwd`, the checkout's lock
    (M-1); the guard starts the check in a second session it outlives. `env` is handed to the guard's `Popen` as
    `env=` (the guard spawns the check with its own environment as received; `subprocess` validates the mapping). The
    status is the guard's `X` from the lifeline (the parent's own exit code), `timeout`, or `spawn_failed` (an empty
    tail, and also what a lifeline EOF before the guard reported answers, R-F). The parent's own copies are released
    before the guard is waited for, and `_settle` confirms the stop (`_reap`): an unconfirmed stop with no original
    exception still reads `timeout` however `X` answered (R-C); the guard is `_settle`'s before any further access, so
    it is reaped even when a later caller-object access raises (R-2/R-X)."""
    _drain()  # the guards of earlier unconfirmed stops are reaped here, never waited on, never killed (R-C)
    started = clock()
    _refuse_nul(check["argv"])  # R-A: a NUL element is a ValueError before any descriptor or process is created
    lease = _leased(cwd)
    lifeline = supervisor = None
    result = None
    try:
        try:
            lifeline, guard_end = socket.socketpair()
        except OSError:
            return _evidence(check, "spawn_failed", clock() - started, b"")
        fds = (guard_end.fileno(),)
        argv = [sys.executable, "-I", GUARD, "--lifeline", str(guard_end.fileno())]
        if lease is not None:
            argv += ["--lease", lease[0], "--lock-fd", str(lease[1].fileno())]  # the handle lends its fileno (R-D)
            fds += (lease[1].fileno(),)
        argv += ["--deadline", "%.3f" % (check["timeout_s"] + GRACE + 5), "--", *check["argv"]]
        try:
            process = popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True, pass_fds=fds)
            supervisor = _Supervisor(process, lifeline)  # `_settle`'s guard before any further access (R-2)
        except OSError:
            return _evidence(check, "spawn_failed", clock() - started, b"")
        finally:
            _shut(guard_end)  # the parent's own copy: an `OSError` here never replaces an original (R-D/R-X)
        window, status = _read(supervisor, check["timeout_s"], clock)
        result = _evidence(check, status, clock() - started, window)
        return result
    finally:
        _settle(lifeline, supervisor, lease[0] if lease is not None else None, result)


def run_checks(checks, cwd, env=None):
    """Every check of the resolved profile, in order, sequentially, stopping at the first failure (R-5).

    `env=None` means the sanitized environment of `export`; the checks after the first nonzero exit, timeout or
    spawn failure are not run, each with `status="not_run"`, `duration_s=0`, an empty tail; the outcome is `failed`."""
    environment = export.environment() if env is None else env
    evidence, failed = [], False
    for check in checks:
        if failed:
            evidence.append(_evidence(check, "not_run", 0, b""))
            continue
        found = run_check(check, cwd, environment)
        evidence.append(found)
        failed = found["status"] != 0
    return {"checks_digest": digest(checks), "checks": evidence, "outcome": "failed" if failed else "passed"}


def qualify(project, commit, tree, checks, root):
    """`checkout` then `run_checks`: the refusal, or the evidence with the checked `commit` and `tree` added (R-5)."""
    with checkout(project, commit, tree, root) as found:
        if isinstance(found, dict):
            return found
        result = run_checks(checks, found)
    result["commit"], result["tree"] = commit, tree
    return result


def sweep(root):
    """Reap the `checkout-*` leftovers a guard death or a power loss left directly under `root` (R-4/R-V).

    Answers `{"removed": int, "busy": int}`, one unit per name, and never raises on a filesystem `OSError`: a root
    that cannot be listed (missing, unreadable, not a directory) is zeros or one busy, and a unit whose type cannot
    be read or whose removal fails is one busy. Only the names directly under `root` that start with `PREFIX` are
    touched; every other name -- and every path outside `root` -- is left exactly as it is. Classification reads
    types with `lstat` alone (R-4): a `.lock` name that is a regular file is a lease lock (it belongs to the entry
    named without `.lock`, or is an orphan when that name is absent), every other name is an entry whose lock is
    `name + ".lock"` only when *that* is a regular file, and a `.lock` directory or link is an entry of its own,
    never a lock. Names are handled longest first, so a `.lock`-named entry is cleared before its base's lock is
    examined, and each name is counted at most once. Every removal runs under R-W's serialization: a held lock is one
    busy, left in place and never removed under its holder.

    A `lstat` that fails with anything but "no such name" is no classification at all: the unit is one busy and not
    one of its names is touched (R-V) -- reading a failed `lstat` as "not a lock" is what would let a sweep delete a
    live lock. A failure while classifying a `.lock` name counts the pair it belongs to, and the base entry is then
    not counted a second time: an unreadable type is exactly the case where a lock cannot be told from an entry.

    A `.lock` name that is the lock of an entry still on disk is left to that entry's unit, but a unit answers only
    for its own two names: clearing `X` with its lock `X.lock` can strand a lock `X.lock.lock` whose own base name is
    gone, which R-4 makes an orphan lock by then. Passes therefore repeat while one of them removed something, so
    such a name is examined again and a held orphan lock is one busy (a lease being acquired)."""
    root = Path(root)
    try:
        names = sorted(os.listdir(str(root)), key=lambda name: (-len(name), name))
    except FileNotFoundError:
        return {"removed": 0, "busy": 0}  # a missing root: nothing was ever created there
    except OSError:
        return {"removed": 0, "busy": 1}  # listed but unreadable, or not a directory: a recovery cannot be claimed
    present, removed, busy, counted, progress = set(names), 0, 0, set(), True
    while progress:
        progress = False
        for name in names:
            if not name.startswith(PREFIX) or name in counted:
                continue  # outside the domain, or a name this call has already answered for (R-4)
            entry = str(root / name)
            base = name[:-len(".lock")] if name.endswith(".lock") else None
            try:
                if base is not None and _is_regular(entry):
                    if base in present and _lstat(str(root / base)) is not None:
                        continue  # the lock of an entry still on disk: it goes with that entry's unit (R-4)
                    count = _sweep_one(None, entry)  # an orphan lock: a lease whose directory never landed (R-4/R-W)
                    counted.add(name)
                else:
                    lock = entry + ".lock"
                    unit = lock if _is_regular(lock) else None
                    count = _sweep_one(entry, unit)
                    counted.add(name)
                    if unit is not None:
                        counted.add(name + ".lock")  # that one unit answers for the lock too (R-V)
            except OSError:
                count = 0  # an unreadable type is not "no lock": the unit is one busy and every name stays (R-V)
                counted.add(name)
                if base is not None and base in present:
                    counted.add(base)  # the base entry is the other half of that same pair
            removed, busy = removed + count, busy + (1 - count)
            progress = progress or count == 1
    return {"removed": removed, "busy": busy}


def _sweep_one(entry, lock):
    """1 when one unit is gone afterwards, 0 when a held lock or a failed removal leaves it; never raises (R-4/R-W).

    `entry` is the path to remove (`None` for an orphan lock), `lock` the regular lock file already found beside it
    or `None` when it has none. A lockless entry (or the orphan case) first publishes its own lock exactly as
    `_lease` does (R-W), with `O_CREAT | O_EXCL | O_NOFOLLOW`: a name already at the path is one busy and is never
    adopted by reopening it, because a name another actor created is that actor's to hold and to clean up, and
    opening it could take a lock its creator has not flocked yet. Every removal follows R-W: after the `flock` the
    held descriptor is verified against `lstat(path)` (same dev/ino, regular, still linked); a mismatch, an absent
    path, a `flock` the holder refuses or a failed creation is one busy that removes nothing. The entry goes first,
    the lock last. The descriptor is held in one owning `_Lock` (R-D), borrowed through `fileno` for the `flock` and
    the identity check and closed only in the `finally`, after the unlink."""
    owner = None
    try:
        if lock is None:  # a lockless entry: publish our own lock, exactly as `_lease` does (R-W)
            lock = entry + ".lock"
            owner = _Lock(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600))
        else:
            owner = _Lock(os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK))
        sweep_after_open()  # the seam: after the lock is opened, before it is flocked (A-W)
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not _owned(owner.fileno(), lock):
            return 0  # the path no longer names the inode this handle holds: remove nothing (R-W)
        if entry is not None:
            _remove(entry) if _is_directory(entry) else os.unlink(entry)
            if _lstat(entry) is not None:
                return 0  # the entry survived: busy, its lock stays with it for the next sweep (R-V)
        os.unlink(lock)  # the lock goes last, after the entry it belongs to (R-4)
        return 0 if _lstat(lock) is not None else 1
    except OSError:
        return 0  # any filesystem error on the unit is one busy, never a raise (R-V)
    finally:
        if owner is not None:
            _shut(owner)  # the owning handle closes last, after the unlink (R-D/R-K)


def _owned(descriptor, path):
    """Whether `path` right now names the inode `descriptor` holds, still linked and still a regular file (R-W).

    `fstat` reads the inode this holder owns and `lstat` the path (never following a link): equal `(st_dev, st_ino)`,
    a regular file and a positive link count are the only proof that the held lock still owns the name. The open
    descriptor keeps the inode allocated, so a pathname replaced after the `open` cannot answer with the same
    identity. This is not ownership by itself: only the `flock` says who holds the lock, so a caller that never took
    it may not unlink the pathname on this answer alone (R-W)."""
    try:
        held, named = os.fstat(descriptor), os.lstat(path)
    except OSError:
        return False
    return ((held.st_dev, held.st_ino) == (named.st_dev, named.st_ino)
            and stat.S_ISREG(named.st_mode) and held.st_nlink > 0)


def _lstat(path):
    """`os.lstat(path)`, or `None` when the name is not there at all; every other error reaches the caller (R-V).

    `lstat` never follows a link (R-4), so a live and a dangling link both answer with their own type. Only the two
    "no such name" errors are a *known* absent path; any other `OSError` is an unknown type the caller must answer
    with one busy and no removal, never with "not a lock" (R-V)."""
    try:
        return os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None


def _is_regular(path):
    """Whether `path` is a regular file right now, never following a link (R-4's classification)."""
    found = _lstat(path)
    return found is not None and stat.S_ISREG(found.st_mode)


def _is_directory(path):
    """Whether `path` is a directory right now, never a symlink to one (R-4: a link is unlinked, not entered)."""
    found = _lstat(path)
    return found is not None and stat.S_ISDIR(found.st_mode)


def _lease(root):
    """A fresh `checkout-*` directory and its sibling `.lock`, flocked for the checkout's lifetime (M-5).

    Answers `(directory, lock, key)`, `lock` being the owning handle (R-D) of the descriptor created by `O_EXCL`; the
    key is the resolved path *at creation*, the only name this lease is ever registered, looked up and dropped under.
    A name whose sidecar lock is already taken is retried with a fresh random name; an acquisition that never obtained
    its `O_EXCL` lock closes only its own handle and unlinks nothing (R-K). After the `flock` the just-created lock is
    verified against `lstat(path)` (R-W): a pathname no longer naming this inode (a sweep between the create and the
    flock unlinked it) makes this attempt close its own fd and try a fresh name, so publication never registers a
    checkout whose lock is not on disk. A failure *before* that `flock` -- a failing `flock` itself, or the seam --
    closes only this attempt's own handle and never unlinks the pathname either (R-W): the pathname is a lock only
    for the holder of `flock` on the inode at it, and an attempt that never took the flock has nothing to release."""
    for _ in range(TRIES):
        directory = root / (PREFIX + os.urandom(8).hex())
        try:
            lock = _Lock(os.open(str(directory) + ".lock",
                                 os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600))
        except FileExistsError:
            continue  # the sidecar name is taken: an entry this call does not own is left alone and a new name tried
        created, owner = False, False  # `owner` is never True before this attempt has taken its own `flock` (R-W)
        try:
            lease_after_create()  # the seam: between the lock's create and its flock (R-W/A-W)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            owner = True  # only from here is the lock pathname this attempt's to unlink (R-W/R-K)
            if not _owned(lock.fileno(), str(directory) + ".lock"):
                _shut(lock)  # the path no longer names this inode: this attempt's own fd goes, a fresh name is tried
                continue
            directory.mkdir(mode=0o700)
            created = True  # the directory is this attempt's own from here on, so a later failure releases it too
            key = str(directory.resolve())  # the lease's only name, fixed before anything can replace it (M-5)
            LEASES[key] = lock
        except FileExistsError:
            if owner:
                _discard(directory, lock, created)  # a name taken by an entry we never created is left alone
            else:
                _shut(lock)  # no flock of this attempt's own: only its handle goes, the pathname is not its to unlink
            continue  # ... and a fresh name is tried instead of removing it
        except BaseException:  # an `OSError` or an interrupt: release this attempt's pair, then re-raise (R-X)
            if owner:
                _discard(directory, lock, created)
            else:
                _shut(lock)  # a failure before the flock: the pathname stays exactly as it is (R-W)
            raise
        return directory, lock, key
    raise FileExistsError("no free %s name under %s" % (PREFIX, root))


def _discard(directory, lock, created):
    """Give up an *unregistered* lease attempt this call still holds: the pair it created, then its handle (R-K).

    Only an attempt that created the directory removes it; the lock pathname this call created goes with it (or
    alone, when the directory was never created) and the fd is closed last. A directory that is really gone is the
    only one that takes its sidecar: a failed removal keeps the lock pathname for the later recovery. An `OSError`
    from the removal is swallowed -- the leftover belongs to the later recovery -- and the fd still closes."""
    try:
        try:
            if not created or _remove(directory):  # a removed directory takes the lock pathname with it (R-K)
                if created:
                    forget_after_remove()  # the seam: between the directory removal and the lock unlink (R-K/A-W)
                os.unlink(str(directory) + ".lock")
        except OSError:
            pass  # a failed removal or seam keeps the sidecar for the recovery, never raised from cleanup
    finally:
        _shut(lock)  # the owning handle closes last, after the unlink attempt (R-K)


def _forget(key, directory, lock, keep):
    """Drop the lease by the key captured at creation and remove the directory, its lock and the handle (R-K).

    With `keep` (a lease whose stop was unconfirmed, R-C) the registration and the fd still go but the directory and
    the lock pathname stay for the later recovery. Otherwise the removal keeps R-K's order -- directory, then the
    lock pathname, then the fd -- under the still-held lock, and only a directory that is really gone takes its
    sidecar with it. The key is never re-resolved from the mutable path."""
    LEASES.pop(key, None)
    ABANDONED.discard(key)
    try:
        if not keep:
            try:
                if _remove(directory):  # a removed directory takes the lock pathname with it (R-K)
                    forget_after_remove()  # the seam: between the directory removal and the lock unlink (R-K/A-W)
                    os.unlink(str(directory) + ".lock")
            except OSError:
                pass  # the removal or the seam refused: the leftover goes to the recovery, never raised from cleanup
    finally:
        _shut(lock)  # the owning handle closes last, after the unlink attempt (R-K)


def _shut(owner):
    """Close one owning handle this call holds, never raising from cleanup (R-D/R-X)."""
    try:
        owner.close()
    except OSError:
        pass


def _shut_fd(number):
    """Close one descriptor this call owns, never raising from cleanup (R-D/R-X)."""
    try:
        os.close(number)
    except OSError:
        pass


def _orphan(process):
    """Own an unreaped guard in `ORPHANS`, under `ORPHANS_LOCK` (R-C), so a later entry can poll it."""
    with ORPHANS_LOCK:
        ORPHANS.append(process)


def _drain():
    """Reap what earlier unconfirmed stops left: poll every entry, drop the ones that exited (R-C).

    The whole poll pass runs in one critical section; an entry that has not exited is left exactly where it is --
    nothing here waits on or kills it, and nothing here ever calls `wait` (a `poll` reaps an exited guard)."""
    with ORPHANS_LOCK:
        alive = []
        for process in ORPHANS:
            try:
                if process.poll() is None:
                    alive.append(process)
            except OSError:
                alive.append(process)  # a poll that failed is no proof of exit: keep the guard (R-C)
        ORPHANS[:] = alive


def _leased(cwd):
    """The registered `(directory, lock fd)` of a leased `cwd`: an exact resolved-path match, never a name or a
    prefix (M-5), so a direct call on a project is never mistaken for a checkout."""
    try:
        key = str(Path(cwd).resolve())
    except OSError:
        return None
    fd = LEASES.get(key)
    return None if fd is None else (key, fd)


def _read(supervisor, timeout_s, clock):
    """(the bounded window the check wrote, its status): `WINDOW` raw bytes at most, the byte before it kept so the
    leading partial line of an overflow can be dropped; the status is the guard's `X` (the parent's own exit code),
    read until `GRACE` seconds after it -- `F` is `spawn_failed`, and a lifeline EOF before `S` or `F` is
    `spawn_failed` with an empty tail (R-F); every other missing `X` (a fired deadline, or an EOF after `S`) is
    `timeout`, never a numeric status (R-C/R-F)."""
    deadline = clock() + timeout_s
    chunks, size, dropped, grace_end, timed_out, pending = deque(), 0, b"", None, False, b""
    fd, lifeline, status, pipe_open = supervisor.process.stdout.fileno(), supervisor.lifeline, None, True
    lifeline.setblocking(False)
    while True:
        if status is None and lifeline is None and supervisor.pid is None:
            break  # the guard is gone before `S` or `F`: the run never started, so waiting is pointless (R-F)
        if status is None and not pipe_open and lifeline is None:
            break  # the guard is gone after `S` with no writer left: the deadline alone would only wait (R-3)
        if status is None:
            left = deadline - clock()
            if left <= 0:
                timed_out = True
                break
            wait = min(left, POLL)
        else:
            if grace_end is None:
                grace_end = clock() + GRACE
            if not pipe_open or clock() >= grace_end:
                break
            wait = max(grace_end - clock(), 0.0)  # the grace may end between the check above and here
        watch = ([fd] if pipe_open else []) + ([lifeline.fileno()] if lifeline else [])
        ready, _, _ = select.select(watch, [], [], wait)
        if lifeline is not None and lifeline.fileno() in ready:
            try:
                data = lifeline.recv(4096)
            except OSError:
                data = b""
            if data:
                pending += data
                *lines, pending = pending.split(b"\n")
                for line in lines:
                    status = _message(supervisor, line, status)
            else:
                lifeline = None  # the guard is gone: the pipe and the deadline still bound the read (R-3)
        if pipe_open and fd in ready:
            data = os.read(fd, READ)
            if not data:
                pipe_open = False  # EOF: every writer, the check and its descendants, let the pipe go
            else:
                if len(data) > WINDOW:
                    dropped = data[-WINDOW - 1:-WINDOW]  # one read larger than the window keeps only its tail
                    data = data[-WINDOW:]
                while chunks and size + len(data) > WINDOW:  # evict before the append: the window never exceeds `WINDOW`
                    chunk = chunks.popleft()
                    excess = size + len(data) - WINDOW
                    if len(chunk) > excess:
                        dropped = chunk[excess - 1:excess]
                        chunks.appendleft(chunk[excess:])
                        size -= excess
                    else:
                        dropped = chunk[-1:]
                        size -= len(chunk)
                chunks.append(data)
                size += len(data)
    window = b"".join(chunks)
    if dropped and dropped != b"\n":  # the cut fell inside a line: that leading partial line goes with it (R-4)
        window = window.split(b"\n", 1)[1] if b"\n" in window else b""
    if status is None:
        if not timed_out and lifeline is None and supervisor.pid is None:
            return b"", "spawn_failed"
        status = "timeout"
    return window, status


def _message(supervisor, line, status):
    """One lifeline line: `S` carries group C's leader, `F` a spawn failure, `X` the parent's own status (M-2)."""
    if line.startswith(b"S "):
        supervisor.pid = int(line[2:])
    elif line == b"F":
        return "spawn_failed"
    elif line.startswith(b"X "):
        token = line[2:].decode("utf-8", "replace").strip()
        return "timeout" if token == "timeout" else int(token)
    return status


def _settle(lifeline, supervisor, key, result):
    """The one cleanup path of `run_check` (R-X/R-C): release the parent's own copies, then reap the guard.

    With no supervisor (a spawn that never started or that failed) only this call's own lifeline end is closed. With
    one, `_reap` kills group C, sends `D`, releases this call's copies and waits for the guard; a stop that `_reap`
    could not confirm -- a wait that timed out or raised, or an interrupt during cleanup -- makes `result` read
    `timeout` however `X` answered, and an `OSError` from the cleanup is swallowed, never replacing an original."""
    if supervisor is None:
        try:
            if lifeline is not None:
                lifeline.close()
        except OSError:
            pass
        return
    try:
        confirmed = _reap(supervisor, key)
    except OSError:
        confirmed = False  # a cleanup `OSError` is swallowed (R-X): the stop is unconfirmed, never raised
    except BaseException:
        if result is not None:
            result["status"] = "timeout"
        raise
    if not confirmed and result is not None:
        result["status"] = "timeout"


def _reap(supervisor, key=None):
    """Kill group C, tell the guard the run is over, reap the guard; answer whether the stop is confirmed (R-C).

    Before `S` the pid of group C is unknown, so the guard is the only one who can kill it; `_reap` therefore waits
    for the guard to exit -- it SIGKILLs group C first -- instead of returning on a short wait with the group still
    alive. The four releases stay ahead of the wait and each runs on its own, so an `OSError` from one is swallowed
    and never skips the later ones (R-X). The wait is confirmed only when the guard was reaped inside `REAP` *and*
    group C is gone; anything else is unconfirmed and fail-closed, so the unreaped guard is owned by `ORPHANS`
    (polled, never waited on, never killed, by a later entry) and a lease is marked so `checkout`'s exit keeps the
    pair for the later recovery instead of removing a directory whose check may still run (R-C)."""
    broken = None
    for release in (lambda: _kill(supervisor.pid), lambda: supervisor.lifeline.setblocking(True),
                    lambda: _send(supervisor.lifeline, b"D\n"), lambda: supervisor.lifeline.close(),
                    lambda: supervisor.process.stdout.close()):
        try:
            release()
        except OSError:
            pass  # an `OSError` from cleanup is swallowed and never replaces an original exception (R-X)
        except BaseException as error:  # an interrupt: the later releases and the wait still run (R-X)
            if broken is None:
                broken = error
    reaped = False
    try:
        supervisor.process.wait(timeout=REAP)
        reaped = True
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        pass  # a wait that failed is no proof the guard was reaped: the stop stays unconfirmed below (R-C)
    except BaseException as error:
        if broken is None:
            broken = error
    try:
        gone = supervisor.pid is None or not _present(supervisor.pid)
    except BaseException as error:  # an interrupt in the confirmation still transfers ownership (R-C)
        gone = False
        if broken is None:
            broken = error
    if broken is not None or not (reaped and gone):
        try:
            _orphan(supervisor.process)  # the only reference that outlives this call (R-C)
        except BaseException as error:
            if broken is None:
                broken = error
        if key is not None:
            ABANDONED.add(key)
    if broken is not None:
        raise broken
    return reaped and gone


def _kill(pgid):
    """SIGKILL group `pgid`; an unknown (before `S`), gone or unreachable group is fine (M-3)."""
    if pgid is None:
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass


def _send(lifeline, payload):
    """One lifeline message; a guard whose peer is already gone is fine (M-2)."""
    try:
        lifeline.sendall(payload)
    except OSError:
        pass


def _present(pgid):
    """Whether group `pgid` still has a member; only `ProcessLookupError` proves it gone, anything else fails closed."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _refuse_nul(argv):
    """A NUL in an argv element is refused before anything is acquired, as `subprocess` refuses it (R-A)."""
    for element in argv:
        if isinstance(element, bytes):
            bad = b"\0" in element
        elif isinstance(element, str):
            bad = "\0" in element
        else:
            continue
        if bad:
            raise ValueError("embedded null byte")


def _remove(directory):
    """Remove a checkout root first, then every entry a check may have made read-only for its owner (R-2/A-2).

    A lost write or search bit (`chmod 0500`/`000`) blocks `rmtree` below it and, on the root, hides every entry
    from `os.walk` too, so both are relaxed outside-in (a parent before the walk enters it); no symlink is followed.
    A `directory` that is itself a symlink is unlinked, not entered, so neither `checkout`'s exit nor the guard can
    ever reach a target outside `root`. Answers whether the directory is *gone*: a removal that failed leaves both it
    and its lock pathname to the later recovery (R-K). Nothing here may raise: it runs in a `finally`, where a new
    exception would replace the caller's own."""
    if os.path.islink(str(directory)):
        try:
            os.unlink(str(directory))
        except OSError:
            pass
        return not os.path.lexists(str(directory))
    try:
        os.chmod(directory, 0o700)  # the root itself may have lost its bits, which hides everything below it
    except OSError:
        pass
    for root, directories, files in os.walk(directory):
        for name in directories + files:
            path = Path(root) / name
            if not path.is_symlink():
                try:
                    os.chmod(path, 0o700)
                except OSError:
                    pass
    try:
        shutil.rmtree(directory)
    except OSError:
        pass  # a removal that failed is answered, never raised: the caller keeps the sidecar (R-K)
    return not os.path.lexists(str(directory))


def _git(project, *arguments):
    """One git call: argv only, the export options (hooks off) and sanitized environment, its own session."""
    command = ["git", "--no-optional-locks", *export.OPTIONS, "-C", str(project), *arguments]
    return subprocess.run(command, capture_output=True, timeout=export.TIMEOUT, start_new_session=True, env=export.environment())


def _prepare(directory, project, commit, tree):
    """The fresh clone detached at `commit` with its tree verified, or the refusal that stops the run (R-2)."""
    try:
        cloned = _git(project, "clone", "--quiet", "--no-hardlinks", "--no-checkout", "--", str(project), str(directory))
        if cloned.returncode:
            return {"refused": "checkout"}
        detached = _git(directory, "checkout", "--detach", commit)
        if detached.returncode:
            return {"refused": "checkout"}
        head = _git(directory, "rev-parse", "HEAD")
        if head.returncode or head.stdout.decode().strip() != commit:
            return {"refused": "checkout"}
        tree_of = _git(directory, "rev-parse", "HEAD^{tree}")
    except (OSError, subprocess.TimeoutExpired):
        return {"refused": "checkout"}
    if tree_of.returncode:
        return {"refused": "checkout"}
    if tree_of.stdout.decode().strip() != tree:
        return {"refused": "tree_mismatch"}
    return None


def _evidence(check, status, elapsed, window):
    return {"name": check["name"], "argv_digest": digest(check["argv"]), "status": status, "duration_s": round(elapsed, 3), "tail": _tail(window)}


def _tail(window):
    """The tail of a retained window (R-4): `live._shown`, the last `MAX_LINES` lines, then at most `MAX_BYTES`."""
    lines = live._shown(window)[-MAX_LINES:]
    while lines and len("\n".join(lines).encode("utf-8")) > MAX_BYTES:
        lines.pop(0)
    return "\n".join(lines)
