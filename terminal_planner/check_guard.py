"""The restart-safe check supervisor (S1b1b1): a stdlib-only guard around one disposable check.

zplan starts it by absolute path in its own session (group G) with a `socket.socketpair` lifeline; the guard starts
the check in a second session (group C), so a kill of group C never reaches the guard while a SIGKILL of zplan leaves
the guard alive to reap group C, remove a leased checkout and exit (R-2). `python -I <path>` runs it anywhere; it
imports nothing from the package and adds no environment key of its own: the check is spawned with this process's
environment as received (A-G)."""

import os, select, shutil, signal, socket, subprocess, sys, time

PREFIX = "checkout-"  # the lease name the guard may remove (M-5: `checks.PREFIX`, copied to stay stdlib-only)
STEP = 0.05  # seconds one select may sleep before the check and the deadline are looked at again
GONE = 10.0  # seconds the guard waits for group C to disappear (R-2)


class _Lock:
    """The owning handle of one lease lock: a file object over the descriptor borrowed through `--lock-fd` (R-D/R-K).

    R-D wants an object that owns its descriptor, never a raw integer kept around: this handle is what `_release`
    closes last and what lends its `fileno` to the check's spawn, so group C inherits the flock (M-5)."""

    def __init__(self, descriptor):
        self.handle = os.fdopen(descriptor, "r+")

    def fileno(self):
        return self.handle.fileno()

    def close(self):
        self.handle.close()


def after_spawn():
    """The interleaving seam (H-3): a no-op a test replaces to block between the spawn and the `S` send."""


def after_report():
    """The interleaving seam (A-C): a no-op a test replaces to hold the guard after it sent `X`, so it does not exit
    inside zplan's bounded wait and the stop is unconfirmed (R-C)."""


def release_after_remove():
    """The removal seam (R-K/A-W): a no-op a test replaces between `_release`'s directory removal and its lock
    unlink, so a removal can be interleaved with a recovery and a fresh acquisition (s1b1b2)."""


def main(argv=None):
    """Supervise one check until zplan says `D` (normal end) or the lifeline says zplan is gone (R-2).

    A `D` that is already queued -- before the check is spawned -- is that same normal end and never a death (M-3):
    the guard removes no lease for it, because the checkout's own end belongs to zplan. The drain before the spawn is
    non-blocking (`_handover`), and the check is spawned with this process's environment as received (A-G)."""
    options, command = _options(sys.argv[1:] if argv is None else argv)
    lifeline = socket.socket(fileno=options["lifeline"])
    lock = None if options["lock_fd"] is None else _Lock(options["lock_fd"])
    buffer = [b""]
    state = _handover(lifeline, buffer)
    if state == "done":  # zplan's own timer beat the guard: the run is over, so spawn nothing and remove nothing (M-3)
        return 0
    if state == "gone":  # zplan was already gone before the check: spawn nothing (H-3b/R-2)
        _release(options, lock)
        return 0
    try:
        check = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True,
                                 pass_fds=() if lock is None else (lock.fileno(),))
    except OSError:
        _silence()
        state = _announce(lifeline, b"F\n", buffer)
        normal = state == "done" or (state == "sent" and _supervise(None, lifeline, None, buffer))
    else:
        _silence()  # EOF on zplan's pipe then means group C closed it, never the guard (M-1)
        after_spawn()
        state = _announce(lifeline, b"S %d\n" % check.pid, buffer)
        normal = state == "done" or (state == "sent" and _supervise(check, lifeline, options["deadline"], buffer))
        _kill(check)
        _await_gone(check)
    if not normal:
        _release(options, lock)
    return 0


def _options(argv):
    """The guard's own flags up to `--` and the check argv after it; a malformed command line exits silently (R-7)."""
    options, index = {"lifeline": None, "deadline": None, "lease": None, "lock_fd": None}, 0
    while index < len(argv) and argv[index] != "--":
        if argv[index] not in ("--lifeline", "--deadline", "--lease", "--lock-fd") or index + 1 >= len(argv):
            raise SystemExit(2)
        options[argv[index][2:].replace("-", "_")] = argv[index + 1]
        index += 2
    try:
        options["lifeline"] = int(options["lifeline"])
        options["lock_fd"] = None if options["lock_fd"] is None else int(options["lock_fd"])
        options["deadline"] = None if options["deadline"] is None else float(options["deadline"])
    except (TypeError, ValueError):
        raise SystemExit(2)
    return options, argv[index + 1:]


def _pending(lifeline, buffer):
    """Drain what the lifeline holds right now: `(the complete lines read, whether the peer is at EOF)` (M-2).

    Bytes that do not end a line stay in `buffer[0]`, so a caller may drain again; a read error is EOF too. Never
    blocks: one non-blocking `select` and then as many `recv` calls as the socket answers."""
    lines, closed = [], False
    while True:
        try:
            ready, _, _ = select.select([lifeline], [], [], 0)
        except (OSError, ValueError):
            return lines, True
        if not ready:
            return lines, closed
        try:
            data = lifeline.recv(4096)
        except OSError:
            return lines, True
        if not data:
            return lines, True
        buffer[0] += data
        *found, buffer[0] = buffer[0].split(b"\n")
        lines += found


def _handover(lifeline, buffer):
    """`"run"|"done"|"gone"`: the non-blocking drain before the check is spawned (M-3/M-2/H-3b).

    A queued `D` is zplan's normal end, read first, so it is never mistaken for the peer's death (M-3); an observed
    EOF without one means zplan was gone before the spawn, so no check is started (M-2/H-3b). Nothing is awaited: the
    drain reads only what the lifeline already holds, never blocking for another message (M-3)."""
    lines, closed = _pending(lifeline, buffer)
    if b"D" in lines:
        return "done"
    if closed:
        return "gone"
    return "run"


def _announce(lifeline, payload, buffer):
    """One lifeline message, in three states: `"done"` when a `D` is already queued (M-3), `"sent"` when the message
    went out and the run continues, `"gone"` when zplan is gone (M-2/R-2). A `D` read behind a failed send is `"done"`.

    Reading *before* writing is what keeps a queued `D` alive: a write to a lifeline whose peer already closed makes
    that peer's stack answer with a reset, and the reset discards the `D` still sitting in the receive queue, so a
    guard that wrote first would read the death of a run zplan had in fact ended normally."""
    lines, closed = _pending(lifeline, buffer)
    if b"D" in lines:
        return "done"  # the run is over: nothing more may be sent and nothing may be removed
    if closed:
        return "gone"  # EOF without a `D`: zplan is gone (R-2)
    try:
        lifeline.sendall(payload)
        return "sent"
    except OSError:
        lines, _ = _pending(lifeline, buffer)
        return "done" if b"D" in lines else "gone"


def _supervise(check, lifeline, deadline_s, buffer):
    """Announce the check's exit or the deadline, then wait for zplan: True on `D`, False when the lifeline is gone.

    `check` is None when the spawn failed and `F` was already sent. `X` carries the parent's own exit code (`-N` for
    a signal) or `timeout` after the guard killed group C (M-2/M-4). The deadline stays armed after `X`: a descendant
    that outlives its parent is still group C and must be killed at the backstop, not only a parent that is late."""
    deadline = None if deadline_s is None else time.monotonic() + deadline_s
    announced = check is None
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            _kill(check)  # M-4: the deadline bounds the whole group, descendants included
            _await_gone(check)
            state = _announce(lifeline, b"X timeout\n", buffer)
            if state != "sent":
                return state == "done"  # a queued `D` ends the run normally; `gone` is R-2
            deadline, announced = None, True  # fired once: the group is gone, only `D` or EOF ends the wait
            after_report()
        elif not announced:
            returned = check.poll()
            if returned is not None:
                state = _announce(lifeline, b"X %d\n" % returned, buffer)
                if state != "sent":
                    return state == "done"  # a queued `D` ends the run normally; `gone` is R-2
                announced = True
                after_report()
        if deadline is None:
            wait = None if announced else STEP  # only `D` or EOF ends the wait once the status is out
        else:
            wait = max(0.0, min(deadline - time.monotonic(), STEP))
        try:
            ready, _, _ = select.select([lifeline], [], [], wait)
        except (OSError, ValueError):
            return False
        if not ready:
            continue
        lines, closed = _pending(lifeline, buffer)
        if b"D" in lines:
            return True
        if closed:
            return False  # EOF without a preceding `D`: zplan is gone (R-2)


def _kill(check):
    """SIGKILL group C (its leader is the check's own session, M-1); a gone group is fine."""
    if check is not None:
        try:
            os.killpg(check.pid, signal.SIGKILL)
        except OSError:
            pass


def _await_gone(check):
    """Wait until group C is gone, bounded by `GONE` seconds (R-2): reap its leader, then probe the group."""
    if check is None:
        return
    end = time.monotonic() + GONE
    while time.monotonic() < end:
        try:
            check.wait(timeout=0.0)  # reaps the leader once it exited; a leader still running raises
        except (subprocess.TimeoutExpired, OSError):
            time.sleep(0.02)
            continue
        try:
            os.killpg(check.pid, 0)  # the leader is reaped, so only other group C members can remain
        except ProcessLookupError:
            return
        except OSError:
            pass  # anything but `ESRCH` is no proof the group is gone (macOS reports `EPERM` for a zombie member)
        time.sleep(0.02)
    try:
        check.wait(timeout=0.0)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _silence():
    """Point the guard's own stdout/stderr at /dev/null so EOF on zplan's pipe means group C closed it (M-1)."""
    try:
        null = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        return
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
    finally:
        if null > 2:
            try:
                os.close(null)
            except OSError:
                pass


def _release(options, lock):
    """Remove a lease, and only a lease: a `checkout-*` directory with a sibling lock file (M-5/R-2/R-K).

    The order is R-K's -- directory, then the lock pathname, then the fd -- under this process's transferred copy of
    the still-held lock, and only a directory that is really gone takes its sidecar with it: a failed removal leaves
    both for the later recovery. An `OSError` in the removal is swallowed and leaves the rest for the later
    recovery; the fd is closed in a `finally`, so an interrupt or an `OSError` in between never skips the close."""
    lease = options["lease"]
    try:
        try:
            if (lease is not None and lock is not None and os.path.basename(lease).startswith(PREFIX)
                    and os.path.isfile(lease + ".lock")):
                if _remove(lease):  # a removed directory takes the lock pathname with it (R-K)
                    release_after_remove()  # the seam: between the directory removal and the lock unlink (R-K/A-W)
                    try:
                        os.unlink(lease + ".lock")
                    except OSError:
                        pass
        except OSError:
            pass  # the removal or the seam refused: the leftover goes to the recovery, never raised from cleanup
    finally:
        if lock is not None:
            try:
                lock.close()  # the owning handle closes its borrowed descriptor exactly once (R-D/R-K)
            except OSError:
                pass


def _remove(directory):
    """The s1b1 removal, copied: relax a lost write/search bit outside-in, then rmtree; nothing here raises (R-2).

    A `directory` that is itself a symlink is unlinked, not entered, so a `--lease` link can never carry the removal
    outside the root it belongs to (R-2/R-4 containment). Answers whether the directory is *gone*, so a removal that
    failed keeps the lease's lock pathname for the later recovery (R-K)."""
    if os.path.islink(directory):
        try:
            os.unlink(directory)
        except OSError:
            pass
        return not os.path.lexists(directory)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    for root, directories, files in os.walk(directory):
        for name in directories + files:
            path = os.path.join(root, name)
            if not os.path.islink(path):
                try:
                    os.chmod(path, 0o700)
                except OSError:
                    pass
    try:
        shutil.rmtree(directory)
    except OSError:
        pass  # a removal that failed is answered, never raised: the caller keeps the sidecar (R-K)
    return not os.path.lexists(directory)


if __name__ == "__main__":
    sys.exit(main())
