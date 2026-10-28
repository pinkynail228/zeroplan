"""S1b1/S1b1b1: the check executor — the disposable checkout, the bounded runner, its evidence and the guard.

Deterministic fixtures: real temporary Git repositories under TMPDIR and `sys.executable -c` checks; no network, no
provider, no store and no catalog. The hard-kill tests kill a real zplan child and then require the guard to reap
group C and remove the leased checkout (A-H/A-L); every wait is bounded at 3 s. Recovery of a leftover entry (the
later slice's recovery) is out of this module: an entry that nobody owns is asserted by a directory listing."""

import ast, contextlib, errno, fcntl, importlib.util, os, select, shutil, signal, socket, subprocess, sys
import tempfile, threading, time
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

from terminal_planner import checks, export, live
from terminal_planner.authority import digest

REPO = str(Path(checks.__file__).resolve().parents[1])
GUARD_DIR = str(Path(checks.__file__).resolve().parent)
GUARD = getattr(checks, "GUARD", str(Path(checks.__file__).resolve().parent / "check_guard.py"))

NATIVE_ENV = {"name": "native-env", "argv": ["/usr/bin/env"], "timeout_s": 5}  # the A-E oracle: a native program

QUALIFY = """
import sys
from terminal_planner import checks
checks.qualify(sys.argv[2], sys.argv[3], sys.argv[4],
               [{"name": "hard", "argv": [sys.executable, "-c", sys.argv[1]], "timeout_s": 60}], sys.argv[5])
"""

DIRECT = """
import sys
from terminal_planner import checks, export
checks.run_check({"name": "hard", "argv": [sys.executable, "-c", sys.argv[1]], "timeout_s": 60},
                 sys.argv[2], export.environment())
"""

LEASED = """
import sys
from terminal_planner import checks, export
check = {"name": "hard", "argv": [sys.executable, "-c", sys.argv[1]], "timeout_s": 60}
with checks.checkout(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]) as found:
    checks.run_check(check, found, export.environment())
"""

SEAM = """
import sys
from terminal_planner import checks
checks.GUARD = sys.argv[1]  # the guard that blocks in `after_spawn`, so zplan is killed before the `S` send
checks.qualify(sys.argv[3], sys.argv[4], sys.argv[5],
               [{"name": "hard", "argv": [sys.executable, "-c", sys.argv[2]], "timeout_s": 60}], sys.argv[6])
"""


def git(cwd, *arguments):
    """One git call of the fixture: a fixed identity, no system or user configuration."""
    identity = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost", "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@localhost", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    result = subprocess.run(["git", *arguments], cwd=str(cwd), capture_output=True, env=dict(os.environ, **identity))
    if result.returncode:
        raise AssertionError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode().strip()


def load_guard():
    """The guard module, loaded in-process by absolute path (stdlib only, it imports nothing from the package)."""
    spec = importlib.util.spec_from_file_location("check_guard_under_test", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture(unittest.TestCase):
    """The temporary project repository, the scratch root the executor checks out into, and the shared helpers."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.work, self.project = self.base / "checks", self.base / "project"
        self.project.mkdir()
        git(self.project, "init", "-q", "-b", "main")
        (self.project / "file.txt").write_text("one\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "one")
        self.commit = git(self.project, "rev-parse", "HEAD")
        self.tree = git(self.project, "rev-parse", "HEAD^{tree}")
        # Isolation: every test starts with no orphan guard and no registered lease (R-C). `getattr` keeps this
        # module importable against the s1b1 base, where the guard machinery does not exist (the A-7 run).
        for name in ("ORPHANS", "ABANDONED"):
            collection = getattr(checks, name, None)
            if collection is not None:
                collection.clear()
        leases = getattr(checks, "LEASES", None)
        if leases is not None:
            leases.clear()

    def check(self, name, code, timeout_s=1800):
        return {"name": name, "argv": [sys.executable, "-c", code], "timeout_s": timeout_s}

    def marker(self, name, path, status=0):
        """A check that appends its own name to `path` and exits with `status`, so order and stops become visible."""
        code = "import sys, pathlib\npathlib.Path(sys.argv[1]).open('a').write(sys.argv[2])\nsys.exit(int(sys.argv[3]))\n"
        return {"name": name, "argv": [sys.executable, "-c", code, str(path), name, str(status)], "timeout_s": 1800}

    def clock(self):
        """The injected clock: every read of monotonic time is kept on `clock.reads` and answered as it is."""
        reads = []

        def clock():
            reads.append(time.monotonic())
            return reads[-1]
        clock.reads = reads
        return clock

    def leftovers(self):
        return sorted(p.name for p in self.work.iterdir()) if self.work.exists() else []

    def spy_on_spawning(self):
        spawned, real = [], checks.run_check

        def spy(*arguments, **options):
            spawned.append(arguments[0]["name"])
            return real(*arguments, **options)
        return spawned, spy

    def assert_is_dead(self, pid):
        """Wait for `pid` to go: a killed descendant reparented to init needs a moment to be reaped."""
        for _ in range(300):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.01)
        self.fail("process %d is still alive" % pid)

    def spawn(self, argv, **options):
        """One child of the fixture: `argv`, with the environment that reaches this package inside it (A-H)."""
        options.setdefault("env", dict(os.environ, PYTHONPATH=REPO))
        return subprocess.Popen(argv, **options)

    def controller(self, code, *arguments, **options):
        """A separate `sys.executable` running `code`, so the test can SIGKILL the zplan it stands for (A-H)."""
        options.setdefault("stdin", subprocess.DEVNULL)
        options.setdefault("stdout", subprocess.DEVNULL)
        options.setdefault("stderr", subprocess.STDOUT)
        return self.spawn([sys.executable, "-c", code, *arguments], **options)

    def until(self, predicate, timeout=3.0):
        """Poll `predicate` for at most `timeout` seconds; every wait of this module is bounded this way (3 s)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.02)
        return predicate()

    def alive(self, pid):
        """Whether `pid` still names a live (or not yet reaped) process; `ProcessLookupError` is the only proof."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def group_gone(self, pgid):
        """Whether group `pgid` has no member left: only `ProcessLookupError` (`ESRCH`) proves it gone (A-H/A-D/R-2,
        the same oracle as `checks._present`). Any other `OSError` -- macOS answers `EPERM` while a member is still
        an unreaped zombie -- is no proof, so the caller's bounded `until` polls again instead of reading it as
        gone."""
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        return False

    def exited(self, pid):
        """Whether child `pid` has exited *without* reaping it: `waitid(..., WNOWAIT)` reports the state and leaves
        the child waitable, so the reap `ORPHANS` owes a later entry is still the only one (A-C/mutation z; a
        `poll`/`wait` here would reap it, and `kill(pid, 0)` answers for a zombie too)."""
        try:
            return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
        except ChildProcessError:
            return True

    def entries(self):
        """The names under the scratch root, so a leftover checkout pair or its absence is a directory listing."""
        return sorted(p.name for p in self.work.iterdir()) if self.work.exists() else []

    def checkouts(self):
        """The `checkout-*` entries under the scratch root (the amended parent oracle: no `sweep` in this slice)."""
        return [name for name in self.entries() if name.startswith(checks.PREFIX)]

    def pids(self, path):
        """The pids a handshake file records, as ints, once the file has appeared (bounded by the caller's wait)."""
        return [int(token) for token in path.read_text().split()]

    def holds(self, path):
        """Whether a fresh `flock(LOCK_EX | LOCK_NB)` on `path` is refused (someone else still holds the lock)."""
        fd = os.open(path, os.O_RDWR)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            return False
        finally:
            os.close(fd)

    def forget(self, *paths):
        """Remove fixture leftovers of a mutation test that built them by hand; never raises."""
        for path in paths:
            if path is None:
                continue
            try:
                os.unlink(str(path) + ".lock")
            except OSError:
                pass
            try:
                if Path(path).is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.unlink(path)
            except OSError:
                pass

    def hook(self, name):
        """A guard wrapper that replaces `check_guard.<name>` with a 2 s hold (A-C), run by absolute path."""
        path = self.base / ("hook-%s.py" % name)
        path.write_text(HOOK % (GUARD_DIR, name))
        return str(path)

    def lines_from(self, sock, count, timeout=3.0):
        """`count` newline-terminated lifeline messages from `sock`, within `timeout` (A-D reads the guard directly)."""
        sock.setblocking(False)
        buffer, lines, end = b"", [], time.monotonic() + timeout
        while len(lines) < count and time.monotonic() < end:
            ready, _, _ = select.select([sock], [], [], 0.05)
            if not ready:
                continue
            try:
                data = sock.recv(4096)
            except OSError:
                break
            if not data:
                break
            buffer += data
            *found, buffer = buffer.split(b"\n")
            lines += found
        return lines


class RunCheckTests(Fixture):
    """R-3/R-4: one check's execution, its status, its bounded window and the scrubbed tail it returns."""

    def test_pass_fail_timeout_and_spawn_failure_give_their_exact_evidence(self):
        """Class: the evidence dict is exactly the five keys of R-3 for a pass, an exit 3, a timeout and a spawn
        failure (a foreign duration only for `spawn_failed` is caught here). Domain: the four outcomes, each with an
        injected clock. Oracle: the dict literals, written from the spec."""
        for code, status, tail in (("print('ok')", 0, "ok"), ("import sys; print('nope'); sys.exit(3)", 3, "nope")):
            with self.subTest(status=status):
                check, clock = self.check("unit", code), self.clock()
                found = checks.run_check(check, self.project, export.environment(), clock=clock)
                self.assertEqual(found, {"name": "unit", "argv_digest": digest(check["argv"]), "status": status,
                                         "duration_s": round(clock.reads[-1] - clock.reads[0], 3), "tail": tail})
        slow = self.check("slow", "import time; time.sleep(30)", timeout_s=1)
        clock, began = self.clock(), time.monotonic()
        timed = checks.run_check(slow, self.project, export.environment(), clock=clock)
        self.assertEqual(timed, {"name": "slow", "argv_digest": digest(slow["argv"]), "status": "timeout",
                                 "duration_s": round(clock.reads[-1] - clock.reads[0], 3), "tail": ""})
        self.assertGreaterEqual(timed["duration_s"], 1)
        self.assertLess(time.monotonic() - began, 1 + checks.GRACE + 1)
        ghost, clock = {"name": "ghost", "argv": ["zplan-no-such-program"], "timeout_s": 5}, self.clock()
        stranded = checks.run_check(ghost, self.project, export.environment(), clock=clock)
        self.assertEqual(stranded, {"name": "ghost", "argv_digest": digest(ghost["argv"]), "status": "spawn_failed",
                                    "duration_s": round(clock.reads[-1] - clock.reads[0], 3), "tail": ""})
        for check, expected in ((slow, "timeout"), (ghost, "spawn_failed")):  # never a pass, and the rest stop
            listed = checks.run_checks([check, self.marker("after", self.base / "m")], str(self.project))
            self.assertEqual(([c["status"] for c in listed["checks"]], listed["outcome"]), ([expected, "not_run"], "failed"))

    def test_an_argv_element_reaches_the_check_literally_without_a_shell(self):
        directory = self.base / "cwd"
        directory.mkdir()
        literal = "a; touch pwned"
        check = {"name": "argv", "timeout_s": 5, "argv": [sys.executable, "-c", "import sys; print(sys.argv[1])", literal]}
        found = checks.run_check(check, directory, export.environment())
        self.assertEqual((found["status"], found["tail"]), (0, literal))
        self.assertEqual([str(p) for p in (directory, self.project) if (p / "pwned").exists()], [])

    def test_a_check_sees_only_the_sanitized_environment(self):
        """Class: the check sees every key of the environment it was handed and none of the planted secrets; the
        guard's own interpreter may add the two names or coerce the locale of `LC_CTYPE` (A-G amendment). Domain: the
        sanitized environment with `HOME`/`GIT_DIR`/`SECRET_TOKEN` planted. Oracle: the sanitized set, the widened
        allowed-additions set `{__CF_USER_TEXT_ENCODING, LC_CTYPE}`, the planted names absent."""
        check = self.check("env", "import os; print('\\n'.join(sorted(os.environ)))")
        with patch.dict(os.environ, {"HOME": "/planted", "GIT_DIR": "/planted", "SECRET_TOKEN": "planted"}):
            found = checks.run_checks([check], str(self.project))  # env=None: the executor's own environment
        environment, shown = export.environment(), set(found["checks"][0]["tail"].split("\n"))
        self.assertLessEqual(set(environment), shown)  # every key of the sanitized environment is visible
        self.assertLessEqual(shown - set(environment), {"__CF_USER_TEXT_ENCODING", "LC_CTYPE"})  # A-G amendment
        self.assertEqual(shown & {"HOME", "GIT_DIR", "SECRET_TOKEN"}, set())

    def test_captured_output_comes_from_both_streams_scrubbed_and_stripped(self):
        code = ("import sys\nsys.stderr.write('boom\\n')\nprint('api_key: sk-abcdefghijklmnop')\n"
                "print('\\x1b[31mred\\x1b[0m')\n")
        found = checks.run_check(self.check("noisy", code), self.project, export.environment())
        self.assertEqual(found["status"], 0)
        self.assertIn("boom", found["tail"])  # stderr shares the one pipe
        self.assertEqual((live.HIDDEN in found["tail"], "sk-abcdefghijklmnop" in found["tail"]), (True, False))
        self.assertIn("\nred", found["tail"])

    def test_a_descendant_holding_the_pipe_does_not_extend_the_run(self):
        code = ("import subprocess, sys\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                "print(child.pid, flush=True)\n")
        began = time.monotonic()
        found = checks.run_check(self.check("holder", code, timeout_s=4), self.project, export.environment())
        self.assertLess(time.monotonic() - began, 4 + 3)
        self.assertEqual(found["status"], 0)
        self.assert_is_dead(int(found["tail"]))

    def test_the_window_never_holds_more_than_64_kib_whatever_the_output(self):
        """Class: the streaming window holds at most 64 KiB of raw bytes at every moment, whatever the output
        size (R-4/A-6b). Domain: 50 MB printed by a check, read in 1024-byte pieces. Oracle: a deque subclass written
        here that measures the retained bytes after each append."""
        held = []

        class Watching(deque):
            def append(self, chunk):
                super().append(chunk)
                held.append(sum(len(c) for c in self))

        code = "import sys\nfor _ in range(800): sys.stdout.write('x' * 65536)\n"
        with patch.object(checks, "READ", 1024), patch.object(checks, "deque", Watching):
            found = checks.run_check(self.check("flood", code), self.project, export.environment())
        self.assertEqual(found["status"], 0)
        self.assertGreater(len(held), 100)
        self.assertLessEqual(max(held), checks.WINDOW)


class CheckoutTests(Fixture):
    """R-2: the disposable checkout — its tree, the identities it accepts and its refusals."""

    def test_the_checkout_holds_the_commit_tree_detached_from_a_relative_project(self):
        """Class: a relative project path works exactly like an absolute one (R-2); both are resolved before any
        Git command, so `git -C project` cannot look for `project/project`. Domain: a relative `project` with an
        absolute external `root`, selected from its parent. Oracle: the checkout's own HEAD, tree, mode and file."""
        previous = os.getcwd()
        os.chdir(self.base)
        self.addCleanup(os.chdir, previous)
        with checks.checkout(Path("project"), self.commit, self.tree, self.work) as found:
            self.assertIsInstance(found, Path)
            self.assertEqual(found.stat().st_mode & 0o777, 0o700)
            self.assertEqual((git(found, "rev-parse", "HEAD"), git(found, "rev-parse", "HEAD^{tree}")),
                             (self.commit, self.tree))
            self.assertEqual((found / "file.txt").read_text(), "one\n")
            self.assertEqual(git(found, "status", "--porcelain"), "")
        self.assertEqual(self.leftovers(), [])

    def test_a_hex_identity_is_accepted_in_either_case(self):
        """Class: a valid 40-hex identity is accepted whatever its case (R-2 requires 40-hex, not lowercase); the
        old lowercase-only check raised ValueError on `.upper()` values. Domain: an uppercase commit and tree."""
        with checks.checkout(self.project, self.commit.upper(), self.tree.upper(), self.work) as found:
            self.assertEqual((git(found, "rev-parse", "HEAD"), git(found, "rev-parse", "HEAD^{tree}")),
                             (self.commit, self.tree))
        self.assertEqual(self.leftovers(), [])

    def test_a_wrong_tree_an_unknown_commit_and_a_bad_identity_are_refused_or_raised(self):
        for commit, tree, refused in ((self.commit, "0" * 40, "tree_mismatch"), ("1" * 40, self.tree, "checkout")):
            with self.subTest(refused=refused):
                spawned, spy = self.spy_on_spawning()
                with patch.object(checks, "run_check", spy):
                    found = checks.qualify(self.project, commit, tree, [self.marker("never", self.base / "m")], self.work)
                self.assertEqual(found, {"refused": refused})
                self.assertEqual((spawned, self.leftovers()), ([], []))
        for commit, tree, root in (("not-hex", self.tree, self.work), ("a" * 39, self.tree, self.work),
                                   (self.commit, self.tree[:-1], self.work), (self.commit, self.tree, self.project / "inside")):
            with self.subTest(root=str(root)):
                with self.assertRaises(ValueError):
                    with checks.checkout(self.project, commit, tree, root):
                        pass

    def test_the_checkout_is_removed_after_every_path_including_a_locked_directory(self):
        """Class: the checkout is gone on every exit path, whatever a check left behind (R-2/A-2). A lost write or
        search bit blocks `rmtree` below it and, on the root, hides every entry from `os.walk`, so the root and each
        entry are relaxed outside-in. Domain: pass, exit 3, timeout, refusal, a locked nested directory, a locked root
        on each of those outcomes, an exception in the `with` body. Oracle: the scratch root, empty afterwards."""
        locked = ("import os, pathlib, time\nnested = pathlib.Path('nested'); nested.mkdir()\n"
                  "(nested / 'file').write_text('x')\nos.chmod(%r, %d)\n")
        cases = [("pass", self.tree, self.check("ok", "print('done')"), 0),
                 ("fail", self.tree, self.marker("bad", self.base / "m", status=3), 3),
                 ("timeout", self.tree, self.check("slow", "import time; time.sleep(30)", timeout_s=1), "timeout"),
                 ("locked-nested-0500", self.tree, self.check("locked", locked % ("nested", 0o500)), 0),
                 ("locked-nested-000", self.tree, self.check("locked", locked % ("nested", 0o000)), 0),
                 ("locked-root-pass", self.tree, self.check("locked", locked % (".", 0o500)), 0),
                 ("locked-root-fail", self.tree, self.check("locked", locked % (".", 0o000) + "raise SystemExit(3)\n"), 3),
                 ("locked-root-timeout", self.tree, self.check("locked", locked % (".", 0o000) + "time.sleep(30)\n", 1), "timeout"),
                 ("refusal", "0" * 40, None, {"refused": "tree_mismatch"})]
        for name, tree, check, expected in cases:
            with self.subTest(name):
                with checks.checkout(self.project, self.commit, tree, self.work) as found:
                    if check is None:
                        self.assertEqual(found, expected)
                    else:
                        self.assertEqual(checks.run_check(check, found, export.environment())["status"], expected)
                self.assertEqual(self.leftovers(), [])
        with self.assertRaises(RuntimeError):
            with checks.checkout(self.project, self.commit, self.tree, self.work):
                raise RuntimeError("body")
        self.assertEqual(self.leftovers(), [])

    def test_checks_run_in_profile_order_and_qualify_returns_the_identities(self):
        order = self.base / "order.txt"
        listed = [self.marker(name, order) for name in ("first", "second", "third")]
        listed.append(self.check("inside", "print(open('file.txt').read().strip())"))
        found = checks.qualify(self.project, self.commit, self.tree, listed, self.work)
        self.assertEqual(order.read_text(), "firstsecondthird")
        self.assertEqual([(e["name"], e["tail"]) for e in found["checks"]],
                         [("first", ""), ("second", ""), ("third", ""), ("inside", "one")])  # ran in the checkout
        self.assertEqual((found["commit"], found["tree"]), (self.commit, self.tree))
        self.assertEqual((found["checks_digest"], found["outcome"]), (digest(listed), "passed"))
        self.assertEqual(self.leftovers(), [])

    def test_the_first_failure_stops_the_run_and_the_rest_are_not_run(self):
        order = self.base / "failfast.txt"
        listed = [self.marker("first", order), self.marker("second", order, status=3), self.marker("third", order)]
        spawned, spy = self.spy_on_spawning()
        with patch.object(checks, "run_check", spy):
            found = checks.run_checks(listed, str(self.project))
        self.assertEqual(spawned, ["first", "second"])
        self.assertEqual(order.read_text(), "firstsecond")
        self.assertEqual(found["outcome"], "failed")
        self.assertEqual(found["checks"][2], {"name": "third", "argv_digest": digest(listed[2]["argv"]),
                                              "status": "not_run", "duration_s": 0, "tail": ""})

    def test_an_interrupt_kills_the_group_reaps_the_child_and_removes_the_checkout(self):
        handshake, pidfile = self.base / "ready", self.base / "pid"
        code = ("import os, pathlib, time\npathlib.Path(%r).write_text(str(os.getpid()))\n"
                "pathlib.Path(%r).write_text('ready')\ntime.sleep(30)\n") % (str(pidfile), str(handshake))

        def clock():
            if handshake.exists():
                raise KeyboardInterrupt
            return time.monotonic()

        with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
            with self.assertRaises(KeyboardInterrupt):
                checks.run_check(self.check("interrupted", code), found, export.environment(), clock=clock)
        self.assertEqual(self.leftovers(), [])
        self.assert_is_dead(int(pidfile.read_text()))


class RuleTests(Fixture):
    """Class-level checks whose oracle is written here from the spec, independent of the executor's helpers.

    Interpretations (the summary does not reach the reviewers): the no-spawn assertions spy on `checks.run_check`,
    because `run_checks`/`qualify` fix the runner's defaults; a failed clone, a failed detach and a HEAD that is not
    the commit are all `checkout`, only a landed HEAD with a different `HEAD^{tree}` is `tree_mismatch`; `timeout_s`
    bounds the parent, `GRACE` its leftover group; both caps drop whole lines from the front; nothing here raises a
    family-bearing class (R-1)."""

    def test_the_caps_keep_the_last_lines_within_both_budgets(self):
        """Class: the stored tail is the last 200 lines and at most 32768 UTF-8 bytes, cut at a line boundary
        (R-4/A-6b), both caps asserted on every case. Domain: 199/200/201 printed lines and 32767/32768/32769-byte
        outputs, one multi-byte character straddling the cut. Oracle: the expected tail rebuilt here."""
        for printed in (199, 200, 201):
            with self.subTest(lines=printed):
                code = "import sys\nfor n in range(%d): print('line', n)\n" % printed
                found = checks.run_check(self.check("lines", code), self.project, export.environment())
                kept = found["tail"].split("\n")
                self.assertEqual((len(kept), kept[0], kept[-1]), (min(printed, 200), "line %d" % (printed - len(kept)),
                                                                  "line %d" % (printed - 1)))
                self.assertLessEqual(len(found["tail"].encode("utf-8")), 32768)
        first = "ё" * 5 + "p" * 9  # 19 bytes, multi-byte: the head of the line the byte cap drops whole
        for size, dropped in ((32767, False), (32768, False), (32769, True)):
            with self.subTest(size):
                payload = first + "\n" + "b" * (size - len(first.encode("utf-8")) - 1)
                code = "import sys; sys.stdout.buffer.write(%r.encode('utf-8'))" % payload
                found = checks.run_check(self.check("bytes", code), self.project, export.environment())
                expected = "\n".join(payload.split("\n")[1:] if dropped else payload.split("\n"))
                self.assertEqual((len(payload.encode("utf-8")), found["tail"]), (size, expected))
                self.assertLessEqual(len(found["tail"].encode("utf-8")), 32768)  # the byte cap
                self.assertLessEqual(len(found["tail"].split("\n")), 200)  # the line cap
                self.assertNotIn("\ufffd", found["tail"])  # no character is split, no line is a fragment

    def test_the_leading_partial_line_of_an_overflow_is_dropped(self):
        """Class: when the window drops bytes, the leading partial line goes with them (R-4/A-6b, live.py:339-342).
        Domain: a secret-shaped first line past the window, then a blank run and a final line, so the cut lands inside
        the secret's own line. Oracle: the tail must be exactly the final line, written here from the spec."""
        # The payload is built in the child: as one literal argv element it exceeds Linux MAX_ARG_STRLEN (128 KiB).
        code = "import sys; sys.stdout.write('api_key: ' + 's' * 70000 + '\\n' + '\\n' * 60001 + 'last')"
        found = checks.run_check(self.check("overflow", code), self.project, export.environment())
        self.assertEqual(found["status"], 0)
        self.assertEqual(found["tail"], "last")
        self.assertLessEqual(len(found["tail"].encode("utf-8")), checks.MAX_BYTES)
        self.assertLessEqual(found["tail"].count("\n") + 1, checks.MAX_LINES)

    def test_no_production_module_imports_the_executor(self):
        """Class: no production module but runs.py (the merge gate, A7a) imports the executor, in any import form
        (R-1). Domain: every other module of the package, at the AST level, for `import a.b.checks`, `from .checks
        import x`, `from . import checks` and the bare names; a scratch copy with `from .checks import run_checks`
        added fails here."""
        package = Path(checks.__file__).resolve().parent
        for path in sorted(package.rglob("*.py")):
            if path.relative_to(package).as_posix() in {"checks.py", "runs.py"}:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    parts = (node.module or "").split(".") + [name.name for name in node.names]
                elif isinstance(node, ast.Import):
                    parts = [part for name in node.names for part in name.name.split(".")]
                else:
                    continue
                self.assertNotIn("checks", parts, path.name)

    @unittest.skipUnless(os.path.exists(GUARD), "the guard is absent on this base (the A-7 run)")
    def test_only_esrch_proves_the_group_is_gone(self):
        """Class: the group-gone oracle is `ProcessLookupError` (`ESRCH`) alone, in the guard too (R-2/A-H); any other
        `OSError` is no proof, so the guard keeps its bounded wait instead of releasing a group that may still run.
        Interpretation recorded here (the worker's summary does not reach the reviewers): an earlier reading that macOS
        answers `EPERM` for a group whose *leader* has been reaped is wrong -- a reaped leader with no members answers
        `ESRCH`, while an unreaped zombie member answers `EPERM` -- so `EPERM` must not be read as gone anywhere.
        Domain: the guard module loaded in-process (stdlib only, it imports nothing from the package), a fake check
        whose leader is already reaped, `killpg` injected to raise `EPERM` and then `ESRCH`, `GONE` shortened. Oracle:
        the number of `killpg` probes -- more than one while only `EPERM` is raised, exactly one for `ESRCH`."""
        guard = load_guard()
        probes = []

        class Reaped:
            """A check whose leader is reaped already: `wait` answers at once, so only the group probe can loop."""

            pid = 4242

            def wait(self, timeout=0.0):
                return 0

        def refusing(error):
            def killpg(pgid, sig):
                probes.append(sig)
                raise error
            return killpg

        with patch.object(guard.os, "killpg", refusing(PermissionError(errno.EPERM, "injected"))), \
                patch.object(guard, "GONE", 0.1):
            guard._await_gone(Reaped())
        self.assertGreater(len(probes), 1, "a non-`ESRCH` error was read as proof the group is gone")
        probes.clear()
        with patch.object(guard.os, "killpg", refusing(ProcessLookupError(errno.ESRCH, "injected"))), \
                patch.object(guard, "GONE", 0.1):
            guard._await_gone(Reaped())
        self.assertEqual(len(probes), 1, "`ProcessLookupError` did not end the wait")

    @unittest.skipUnless(os.path.exists(GUARD), "the guard is absent on this base (the A-7 run)")
    def test_the_pre_spawn_drain_reads_a_queued_d_before_an_observed_eof(self):
        """Class: the guard's pre-spawn drain is non-blocking and its precedence is fixed -- a queued `D` is a
        normal end (M-3) before an observed EOF is zplan gone (M-2/H-3b); a `D` queued ahead of that EOF is still a
        normal end, never a death. Domain: four socketpairs -- a live peer with nothing queued, a queued `D`, a
        closed peer with no `D`, and a queued `D` followed by the peer's close. Oracle: the state `_handover`
        returns, written here from the spec, independent of the executor's helpers; the live peer also proves the
        drain never waits (the call returns while the peer stays open)."""
        guard = load_guard()
        cases = (("run", b"", False), ("done", b"D\n", False), ("gone", b"", True), ("done", b"D\n", True))
        for state, queued, closing in cases:
            with self.subTest(state=state, queued=queued, closing=closing):
                lifeline, peer = socket.socketpair()
                try:
                    if queued:
                        peer.sendall(queued)
                    if closing:
                        peer.close()  # an observed EOF, either alone or behind the queued `D`
                    self.assertEqual(guard._handover(lifeline, [b""]), state)
                finally:
                    lifeline.close()
                    peer.close()


HOOK = """
import sys, time
sys.path.insert(0, %r)
import check_guard as guard
guard.%s = lambda: time.sleep(2)
guard.main(sys.argv[1:])
"""

ORDER_HOOK = """
import os, sys
sys.path.insert(0, %r)
import check_guard as guard
order = open(%r, 'w', buffering=1)
lock_fd = int(sys.argv[sys.argv.index('--lock-fd') + 1])
real_remove, real_unlink, real_close = guard._remove, os.unlink, guard._Lock.close


def remove(*arguments, **options):
    order.write('remove\\n')
    return real_remove(*arguments, **options)


def unlink(*arguments, **options):
    if arguments and str(arguments[0]) == %r:
        order.write('unlink\\n')
    return real_unlink(*arguments, **options)


def close(owner):
    if owner.fileno() == lock_fd:
        order.write('close\\n')
    return real_close(owner)


guard._remove, os.unlink = remove, unlink
guard._Lock.close = close
guard.main(sys.argv[1:])
"""

FAIL_HOOK = """
import os, shutil, sys
sys.path.insert(0, %r)
import check_guard as guard
order = open(%r, 'w', buffering=1)
lease = %r
lock_fd = int(sys.argv[sys.argv.index('--lock-fd') + 1])
real_remove, real_unlink, real_close, real_rmtree = guard._remove, os.unlink, guard._Lock.close, shutil.rmtree


def rmtree(path, *arguments, **options):
    if str(path) == lease:
        raise OSError(5, 'injected removal failure')
    return real_rmtree(path, *arguments, **options)


def remove(*arguments, **options):
    order.write('remove\\n')
    return real_remove(*arguments, **options)


def unlink(*arguments, **options):
    if arguments and str(arguments[0]) == lease + '.lock':
        order.write('unlink\\n')
    return real_unlink(*arguments, **options)


def close(owner):
    if owner.fileno() == lock_fd:
        order.write('close\\n')
    return real_close(owner)


guard._remove, os.unlink = remove, unlink
guard._Lock.close = close
guard.shutil.rmtree = rmtree
guard.main(sys.argv[1:])
"""


class HardKillTests(Fixture):
    """A-H: a SIGKILL of zplan leaves the guard alive to reap group C and remove the leased checkout (gate11:5)."""

    def descendant(self, side, pidfile):
        """A grandchild of the guard: it records its pid, then writes to `side` after 2 s so a survivor is visible."""
        return ("import os, pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                "time.sleep(2)\n"
                "pathlib.Path(sys.argv[2]).open('a').write('x')\n"
                "time.sleep(30)\n")

    def test_a_hard_kill_of_zplan_reaps_group_c_and_removes_the_checkout(self):
        """Class: with the check still running, SIGKILL of the controlling zplan makes the guard kill group C (its
        descendant included), remove the checkout and the lock, and exit (A-H/H-1; mutations a and e: a guard that
        ignores lifeline EOF, or removes the cwd without a lease, fails the checkout and side-effect assertions).
        Domain: one leased checkout, one running check with a live descendant. Oracle: the shared A-H oracle."""
        side, handshake, pidfile = self.base / "side.txt", self.base / "handshake.txt", self.base / "pid.txt"
        code = ("import os, pathlib, subprocess, sys, time\n"
                "subprocess.Popen([sys.executable, '-c', %r, %r, %r])\n"
                "pathlib.Path(%r).write_text('%%d %%d' %% (os.getpid(), os.getppid()))\n"
                "time.sleep(30)\n") % (self.descendant(side, pidfile), str(pidfile), str(side), str(handshake))
        controller = self.controller(QUALIFY, code, self.project, self.commit, self.tree, self.work)
        self.assertTrue(self.until(handshake.exists), "the handshake never appeared")
        group, guard = self.pids(handshake)
        self.assertTrue(self.until(pidfile.exists), "the descendant pid never appeared")
        descendant = int(pidfile.read_text())
        before = side.read_text() if side.exists() else None
        controller.kill()
        self.assertEqual(controller.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertTrue(self.until(lambda: not self.alive(guard)), "the guard %d still runs" % guard)
        for pid in (group, descendant):
            self.assertTrue(self.until(lambda pid=pid: not self.alive(pid)), "pid %d still runs" % pid)
        self.assertTrue(self.until(lambda: self.checkouts() == []), "a checkout entry survived")
        self.assertEqual(self.entries(), [])  # the amended parent oracle: no `checkout-*` entry under the root
        time.sleep(2.5)  # the descendant would append 2 s after the kill; the guard's SIGKILL must have stopped it
        self.assertEqual(side.read_text() if side.exists() else None, before)

    def test_a_hard_kill_during_the_grace_reaps_a_surviving_descendant(self):
        """Class: after the check exited the guard stays alive; a SIGKILL of zplan during the grace still kills the
        descendant that holds the pipe and removes the checkout (A-H/H-2; mutation b: a guard that exits after `X`
        leaves both). Domain: a check that exits 0 leaving a descendant holding stdout. Oracle: the shared oracle."""
        side, handshake, pidfile = self.base / "side.txt", self.base / "handshake.txt", self.base / "pid.txt"
        descendant = ("import os, pathlib, sys, time\n"
                      "parent = int(sys.argv[1])\n"
                      "while True:\n"
                      "    try: os.kill(parent, 0)\n"
                      "    except ProcessLookupError: break\n"
                      "    time.sleep(0.02)\n"
                      "pathlib.Path(sys.argv[3]).write_text('%d %d' % (parent, os.getpid()))\n"
                      "time.sleep(2)\n"
                      "pathlib.Path(sys.argv[2]).open('a').write('x')\n"
                      "time.sleep(30)\n")
        code = ("import os, pathlib, subprocess, sys\n"
                "subprocess.Popen([sys.executable, '-c', %r, str(os.getpid()), %r, %r])\n"
                "pathlib.Path(%r).write_text('%%d %%d' %% (os.getpid(), os.getppid()))\n"
                ) % (descendant, str(side), str(pidfile), str(handshake))
        controller = self.controller(QUALIFY, code, self.project, self.commit, self.tree, self.work)
        self.assertTrue(self.until(handshake.exists), "the handshake never appeared")
        group, guard = self.pids(handshake)
        self.assertTrue(self.until(pidfile.exists), "the descendant handshake never appeared")
        descendant = self.pids(pidfile)[1]
        before = side.read_text() if side.exists() else None
        controller.kill()
        self.assertEqual(controller.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertTrue(self.until(lambda: not self.alive(guard)), "the guard %d still runs" % guard)
        for pid in (group, descendant):
            self.assertTrue(self.until(lambda pid=pid: not self.alive(pid)), "pid %d still runs" % pid)
        self.assertEqual(self.entries(), [])
        time.sleep(2.5)
        self.assertEqual(side.read_text() if side.exists() else None, before)

    def test_a_death_before_the_send_still_reaps_group_c_and_removes_the_lease(self):
        """Class: the `after_spawn` hook holds the guard between the spawn and `S`; a SIGKILL of zplan then makes the
        lost lifeline a death signal, so the guard reaps group C and removes the lease (A-H/H-3; mutation d: a failed
        `S` send treated as a normal end leaves group C and the lease). Domain: the seam run of the guard itself."""
        side, handshake = self.base / "side.txt", self.base / "handshake.txt"
        hooked, proceed = self.base / "hooked", self.base / "proceed"
        hook = self.base / "hook.py"
        hook.write_text("import pathlib, sys, time\nsys.path.insert(0, %r)\nimport check_guard as guard\n"
                        "def block():\n    pathlib.Path(%r).write_text('hooked')\n"
                        "    while not pathlib.Path(%r).exists():\n        time.sleep(0.02)\n"
                        "guard.after_spawn = block\nguard.main(sys.argv[1:])\n"
                        % (GUARD_DIR, str(hooked), str(proceed)))
        code = ("import os, pathlib, time\n"
                "pathlib.Path(%r).write_text('%%d %%d' %% (os.getpid(), os.getppid()))\n"
                "time.sleep(30)\n") % (str(handshake),)
        controller = self.controller(SEAM, str(hook), code, self.project, self.commit, self.tree, self.work)
        self.assertTrue(self.until(hooked.exists), "the guard never blocked after the spawn")
        self.assertTrue(self.until(handshake.exists), "the handshake never appeared")
        group, guard = self.pids(handshake)
        before = side.read_text() if side.exists() else None
        controller.kill()
        self.assertEqual(controller.wait(timeout=3), -signal.SIGKILL)
        proceed.write_text("go")
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertTrue(self.until(lambda: not self.alive(guard)), "the guard %d still runs" % guard)
        self.assertTrue(self.until(lambda: not self.alive(group)), "the group leader %d still runs" % group)
        self.assertEqual(self.entries(), [])
        self.assertEqual(side.read_text() if side.exists() else None, before)

    def test_a_guard_that_finds_zplan_gone_spawns_nothing_and_removes_the_lease(self):
        """Class: zplan is gone before the guard reads its lifeline (EOF with no `D`) → no check is spawned (its
        side-effect absent) and the leased pair is removed (A-H/H-3b). Domain: the guard run alone under a manual
        lease whose transferred fd it holds. Oracle: the absent side-effect and the empty root."""
        self.work.mkdir()
        directory = self.work / (checks.PREFIX + "eleven")
        directory.mkdir()
        (directory / "file.txt").write_text("x")
        holder = os.open(str(directory) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(holder, fcntl.LOCK_EX)
        self.addCleanup(lambda: os.close(holder))
        side = self.base / "side.txt"
        lifeline, peer = socket.socketpair()
        peer.close()  # zplan gone before the guard reads: EOF with no `D` (H-3b)
        guard = self.spawn([sys.executable, "-I", GUARD, "--lifeline", str(lifeline.fileno()),
                            "--lease", str(directory), "--lock-fd", str(holder), "--",
                            sys.executable, "-c", "import pathlib; pathlib.Path(%r).write_text('ran')" % str(side)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, pass_fds=(lifeline.fileno(), holder))
        lifeline.close()
        self.assertTrue(self.until(lambda: guard.poll() is not None), "the guard never exited")
        self.assertEqual(guard.returncode, 0)
        self.assertFalse(side.exists(), "the check was spawned although zplan was already gone")
        self.assertEqual(self.entries(), [])

    def test_the_same_check_without_the_kill_ends_normally_and_cleans_up(self):
        """Class: the H-1 shape without a kill passes, reaps its leftover descendant and removes the checkout (the
        A-H control: the guard is transparent on the normal path). Domain: a check exiting 0 with a live descendant."""
        handshake = self.base / "handshake.txt"
        code = ("import os, pathlib, subprocess, sys\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                "pathlib.Path(%r).write_text('%%d %%d %%d' %% (os.getpid(), child.pid, os.getppid()))\n"
                ) % (str(handshake),)
        found = checks.qualify(self.project, self.commit, self.tree,
                               [{"name": "ok", "argv": [sys.executable, "-c", code], "timeout_s": 60}], self.work)
        group, descendant, guard = self.pids(handshake)
        self.assertEqual((found["outcome"], found["checks"][0]["status"]), ("passed", 0))
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertTrue(self.until(lambda: not self.alive(guard)), "the guard %d still runs" % guard)
        self.assertTrue(self.until(lambda: not self.alive(descendant)), "the descendant %d still runs" % descendant)
        self.assertEqual(self.entries(), [])


class LeaseTests(Fixture):
    """A-L/M-5: cleanup rights come only from a checkout lease; a project a check runs in is never removed."""

    def test_a_killed_zplan_never_removes_the_project_a_check_runs_in(self):
        """Class: a controller that calls `run_check` directly on a project directory named `checkout-x` is SIGKILLed
        mid-check → group C is gone and every file of the project is still there (A-L; mutation e: a guard that
        removes its cwd would delete the project; mutation f: a lease looked up by name prefix would lease it).
        Domain: a project directory that already looks like a lease. Oracle: its contents after the kill."""
        handshake = self.base / "handshake.txt"
        directory = self.work / (checks.PREFIX + "direct")
        directory.mkdir(parents=True)
        (directory / "keep.txt").write_text("keep\n")
        code = ("import os, pathlib, time\n"
                "pathlib.Path(%r).write_text('%%d %%d' %% (os.getpid(), os.getppid()))\n"
                "time.sleep(30)\n") % (str(handshake),)
        controller = self.controller(DIRECT, code, directory)
        self.assertTrue(self.until(handshake.exists), "the handshake never appeared")
        group, guard = self.pids(handshake)
        controller.kill()
        self.assertEqual(controller.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertTrue(self.until(lambda: not self.alive(guard)), "the guard %d still runs" % guard)
        self.assertEqual((directory / "keep.txt").read_text(), "keep\n")
        self.assertEqual(self.entries(), [directory.name])

    def test_a_killed_zplan_removes_a_leased_checkout(self):
        """Class: the same kill under `checkout` removes the checkout and its lock (the A-L control). Domain: a leased
        checkout with a running check. Oracle: the empty root."""
        handshake = self.base / "handshake.txt"
        code = ("import os, pathlib, time\n"
                "pathlib.Path(%r).write_text('%%d %%d' %% (os.getpid(), os.getppid()))\n"
                "time.sleep(30)\n") % (str(handshake),)
        controller = self.controller(LEASED, code, self.project, self.commit, self.tree, self.work)
        self.assertTrue(self.until(handshake.exists), "the handshake never appeared")
        group, guard = self.pids(handshake)
        controller.kill()
        self.assertEqual(controller.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertTrue(self.until(lambda: not self.alive(guard)), "the guard %d still runs" % guard)
        self.assertEqual(self.entries(), [])

    def test_a_leased_checkout_hands_its_lease_and_lock_fd_to_the_guard(self):
        """Class: with a registered lease, the spawned argv carries `--lease <resolved>` and `--lock-fd <fd>` and the
        fd is in `pass_fds`; a direct call carries neither (M-1/M-5). The registered lease is an *owning handle* that
        lends its `fileno`, never a raw integer kept around (R-D). Domain: a leased and an unleased `run_check`,
        observed through the `popen` spy. Oracle: the argv, pass_fds and the handle, written here from the spec."""
        seen, real = [], subprocess.Popen

        def spy(argv, **options):
            seen.append((argv, options))
            return real(argv, **options)

        with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
            key = str(Path(found).resolve())
            checks.run_check(self.check("ok", "print('done')"), found, export.environment(), popen=spy)
            lease = checks.LEASES[key]  # the lease is registered while it is open
            self.assertIsInstance(lease, checks._Lock, "the lease lock is a raw descriptor, not an owning handle")
            self.assertIsInstance(lease.fileno(), int)
        argv, options = seen[0]
        self.assertEqual(argv[argv.index("--lease") + 1], key)
        self.assertEqual(argv[argv.index("--lock-fd") + 1], str(options["pass_fds"][1]))
        self.assertIn(GUARD, argv)
        checks.run_check(self.check("ok", "print('done')"), self.project, export.environment(), popen=spy)
        self.assertNotIn("--lease", seen[1][0])  # a direct call on a project is never handed a lease

    def test_group_c_holds_the_lease_lock_the_guard_handed_over(self):
        """Class: the lock fd travels from `checkout` through the guard *to the check*, so a surviving group C keeps
        the lease busy after the guard itself is gone (M-5; mutation g: a guard that spawns the check with
        `pass_fds=()` leaves the lock free, so the oracle below fails). Domain: the guard run alone with a lease and a
        lock fd the test hands over and then closes, the guard SIGKILLed (its copy dies with it) while the check still
        runs. Oracle: a test-side `flock(LOCK_EX | LOCK_NB)` on the lease lock fails while group C runs and succeeds
        once it is gone."""
        self.work.mkdir()
        directory = self.work / (checks.PREFIX + "handover")
        directory.mkdir()
        lock = str(directory) + ".lock"
        handshake = self.base / "handover.pid"
        code = ("import os, pathlib, time\n"
                "pathlib.Path(%r).write_text(str(os.getpid()))\n"
                "time.sleep(30)\n") % (str(handshake),)
        lifeline, peer = socket.socketpair()
        holder = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(holder, fcntl.LOCK_EX)
        try:
            guard = self.spawn([sys.executable, "-I", GUARD, "--lifeline", str(lifeline.fileno()),
                                "--lease", str(directory), "--lock-fd", str(holder), "--",
                                sys.executable, "-c", code],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               pass_fds=(lifeline.fileno(), holder))
        finally:
            lifeline.close()  # the guard holds its own end of the lifeline
            os.close(holder)  # and the describing fd: from here only the guard and group C keep the flock
        self.assertTrue(self.until(handshake.exists), "the check never started")
        group = int(handshake.read_text())
        guard.kill()  # the guard's own copy goes with it, so only group C can hold the lock now
        self.assertEqual(guard.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(self.alive(group), "group C %d exited with the guard" % group)
        self.assertTrue(self.holds(lock), "group C %d did not keep the lease lock it inherited" % group)
        os.killpg(group, signal.SIGKILL)
        self.assertTrue(self.until(lambda: not self.holds(lock)), "the lock stayed held after group C died")
        self.assertTrue(self.until(lambda: not self.alive(group)), "group C %d still runs" % group)
        peer.close()
        self.forget(directory)

    def test_a_name_collision_never_touches_an_entry_the_lease_does_not_own(self):
        """Class: an acquisition that collides with an existing `checkout-*` entry retries a fresh `O_EXCL` name and
        leaves that entry exactly as it found it -- a directory, a file, and a link whose target is another *active*
        checkout (M-5: cleanup rights come only from a registered lease). Domain: one pinned stem per case and the
        three entry types, each with a pre-existing witness; a run with no free name at all raises `FileExistsError`
        after `checks.TRIES` attempts. Oracle: the witnesses' existence, mode and content, and the registered lease."""
        for kind, stem in (("directory", "0" * 16), ("file", "4" * 16), ("symlink", "5" * 16)):
            with self.subTest(kind):
                self.work.mkdir(exist_ok=True)
                collided = self.work / (checks.PREFIX + stem)
                other, holder, mode = None, None, None
                if kind == "directory":
                    collided.mkdir(mode=0o755)
                    (collided / "keep.txt").write_text("keep\n")
                    mode = os.stat(collided).st_mode & 0o777
                elif kind == "file":
                    collided.write_text("keep\n")
                    os.chmod(collided, 0o644)
                    mode = 0o644
                else:
                    other = self.work / (checks.PREFIX + "1" * 16)
                    other.mkdir()
                    (other / "keep.txt").write_text("keep\n")
                    holder = checks._Lock(os.open(str(other) + ".lock", os.O_CREAT | os.O_RDWR, 0o600))
                    fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
                    checks.LEASES[str(other.resolve())] = holder  # a live lease of another checkout
                    collided.symlink_to(other)
                pinned, real = [bytes.fromhex(stem), b"\x3f" * 8], os.urandom
                try:
                    with patch("os.urandom", side_effect=lambda size: pinned.pop(0) if pinned else real(size)):
                        with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                            leased = Path(found).name
                    self.assertNotEqual(leased, collided.name, "the colliding name was leased")
                    self.assertTrue(os.path.lexists(str(collided)), "the %s collision was removed" % kind)
                    if kind == "symlink":
                        self.assertEqual((other / "keep.txt").read_text(), "keep\n")
                        self.assertIn(str(other.resolve()), checks.LEASES, "another checkout's lease was dropped")
                    else:
                        kept = collided.read_text() if kind == "file" else (collided / "keep.txt").read_text()
                        self.assertEqual(kept, "keep\n")
                        self.assertEqual(os.stat(collided).st_mode & 0o777, mode)
                finally:
                    if holder is not None:
                        checks.LEASES.pop(str(other.resolve()), None)
                        holder.close()
                    self.forget(collided, other)
        exhausted = self.work / (checks.PREFIX + "2" * 16)
        exhausted.mkdir(mode=0o755)
        (exhausted / "keep.txt").write_text("keep\n")
        try:
            with self.assertRaises(FileExistsError), patch("os.urandom", return_value=bytes.fromhex("2" * 16)):
                with checks.checkout(self.project, self.commit, self.tree, self.work):
                    self.fail("a lease was acquired under a name that is taken")
            self.assertEqual((exhausted / "keep.txt").read_text(), "keep\n")
        finally:
            self.forget(exhausted)


class DeadlineTests(Fixture):
    """A-D/M-4: the guard's own deadline, run directly, kills group C and reports `X timeout`."""

    def test_the_deadline_kills_group_c_and_reports_timeout(self):
        """Class: with a lifeline the test keeps open and a check that ignores SIGTERM, `--deadline 1` makes the
        guard -- outside group C -- kill the group, send `X timeout`, and exit only after `D` (A-D; mutation c: a
        check spawned in the guard's own group would take the guard down instead). Domain: the guard run alone."""
        pidfile = self.base / "deadline.pid"
        check = ("import os, pathlib, signal, sys, time\n"
                 "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                 "pathlib.Path(%r).write_text(str(os.getpid()))\n"
                 "time.sleep(30)\n") % (str(pidfile),)
        lifeline, peer = socket.socketpair()
        guard = self.spawn([sys.executable, "-I", GUARD, "--lifeline", str(lifeline.fileno()), "--deadline", "1",
                            "--", sys.executable, "-c", check],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, pass_fds=(lifeline.fileno(),))
        lifeline.close()
        self.assertTrue(self.until(pidfile.exists), "the check never started")
        group = int(pidfile.read_text())
        lines = self.lines_from(peer, 2, 3.0)
        self.assertEqual(lines[0].split()[0], b"S")  # the check's pid, the leader of group C
        self.assertEqual(lines[1], b"X timeout")
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertIsNone(guard.poll(), "the guard exited before `D`")
        peer.sendall(b"D\n")
        self.assertTrue(self.until(lambda: guard.poll() is not None), "the guard never exited")
        self.assertEqual(guard.returncode, 0)
        peer.close()


class SpawnTests(Fixture):
    """A-F/A-G: a missing executable is a spawn failure, a signalled check keeps its negative status."""

    def test_a_missing_executable_reports_spawn_failed_and_leaves_no_guard(self):
        """Class: a missing executable → `spawn_failed`, an empty tail, `duration_s` from the injected clock, no
        guard left alive (A-F; mutation i: `F` reported as an exit status would read a number). Domain: a single
        unspawnable argv, with the injected clock. Oracle: the evidence dict and the untouched root."""
        ghost, clock = {"name": "ghost", "argv": ["zplan-no-such-program"], "timeout_s": 5}, self.clock()
        found = checks.run_check(ghost, self.project, export.environment(), clock=clock)
        self.assertEqual(found, {"name": "ghost", "argv_digest": digest(ghost["argv"]), "status": "spawn_failed",
                                 "duration_s": round(clock.reads[-1] - clock.reads[0], 3), "tail": ""})
        self.assertEqual(checks.ORPHANS, [])  # no guard left alive: nothing was orphaned

    def test_a_signalled_check_reports_its_negative_status_and_stderr_is_kept(self):
        """Class: a check killed by a signal reports the negative status (`-N`), and its stderr still reaches the
        tail (A-G, the guard passes the parent's own exit through). Domain: a `SIGTERM` self-kill with a stderr line."""
        code = "import os, signal, sys\nsys.stderr.write('boom\\n')\nos.kill(os.getpid(), signal.SIGTERM)\n"
        found = checks.run_check(self.check("killed", code), self.project, export.environment())
        self.assertEqual(found["status"], -signal.SIGTERM)
        self.assertEqual(found["tail"].strip(), "boom")

    def test_a_nul_argv_element_is_refused_before_anything_is_created(self):
        """Class: a NUL in an argv element is a `ValueError` before any descriptor or process is created (R-A).
        Domain: a NUL in a later element, with the open-descriptor count sampled around the call and spies on
        `socket.socketpair` and the injected `popen`. Oracle: the raise, the unchanged count, the empty orphan list
        and -- the early-refusal oracle -- neither the pair nor the spawn called at all (a mere late
        `subprocess` `ValueError` would still create and close both, so it cannot satisfy this)."""
        check = {"name": "nul", "argv": [sys.executable, "-c", "print('x')", "a\0b"], "timeout_s": 5}
        before = len(os.listdir("/dev/fd"))
        pairs, spawned = [], []
        real_pair, real_popen = socket.socketpair, subprocess.Popen

        def pair():
            pairs.append(1)
            return real_pair()

        def popen(*arguments, **options):
            spawned.append(1)
            return real_popen(*arguments, **options)

        with patch.object(socket, "socketpair", pair):
            with self.assertRaises(ValueError):
                checks.run_check(check, self.project, export.environment(), popen=popen)
        self.assertEqual((pairs, spawned), ([], []), "the NUL was refused after a descriptor or process was made")
        self.assertEqual((checks.ORPHANS, len(os.listdir("/dev/fd"))), ([], before))


class UnconfirmedTests(Fixture):
    """A-C: an unconfirmed stop is fail-closed -- `timeout`, never a pass, and the lease pair stays for the recovery."""

    def test_an_unconfirmed_stop_after_the_spawn_returns_timeout(self):
        """Class: the guard held in `after_spawn` for 2 s makes zplan's own timer win; with `REAP` patched to 0.5 s
        and no original exception, `run_check` reads `timeout` (never a pass), the guard sits in `ORPHANS` and is
        dropped (reaped, not a zombie) by the next entry, the checkout's exit keeps the pair for the recovery, and the
        lease lock stays held while the guard lives, free once it exits (A-C; mutations n, y, z and g). Domain: a
        leased checkout whose check outlives the stop. Oracle: the status, the directory listing and `flock`. The
        guard is observed to exit with `waitid(WNOWAIT)`, never `poll`/`wait`: the reap is the next entry's (mutation
        z, `_drain` replaced by `ORPHANS.clear()`, must fail on `returncode`)."""
        hook = self.hook("after_spawn")
        check = self.check("slow", "import time; time.sleep(30)", timeout_s=1)
        with patch.object(checks, "REAP", 0.5), patch.object(checks, "GUARD", hook):
            with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                key, lock = str(Path(found).resolve()), str(Path(found).resolve()) + ".lock"
                self.assertEqual(checks.run_check(check, found, export.environment())["status"], "timeout")
                self.assertEqual(len(checks.ORPHANS), 1)
                guard_process = checks.ORPHANS[0]
                self.assertTrue(os.path.isdir(found))
                self.assertTrue(os.path.exists(lock))
                self.assertTrue(self.holds(lock), "the guard's transferred copy of the lock is not held")
            self.assertTrue(os.path.isdir(found))  # the unconfirmed stop kept the pair (R-C)
            self.assertTrue(os.path.exists(lock))
            self.assertTrue(self.holds(lock), "the lock was released with the checkout although the guard lives")
        # the guard is left to exit on its own: a `poll`/`wait` here would do the reaping the next entry owes
        # `ORPHANS` and would hide a `_drain` that only clears the list without polling (mutation z)
        self.assertTrue(self.until(lambda: self.exited(guard_process.pid)), "the guard never exited")
        self.assertEqual(checks.ORPHANS, [guard_process], "the guard left ORPHANS before a later entry polled it")
        checks.run_check(self.check("ok", "print('done')"), self.project, export.environment())
        self.assertEqual(checks.ORPHANS, [], "the exited guard was not dropped from ORPHANS")
        self.assertIsNotNone(guard_process.returncode, "the next entry never reaped the guard (still a zombie)")
        self.assertFalse(self.holds(lock), "the lock is still held after the guard exited")
        self.forget(Path(key), Path(lock))

    def test_an_unconfirmed_stop_after_an_x_zero_returns_timeout(self):
        """Class: `X 0` received, then the guard held in `after_report` for 2 s; with `REAP` patched to 0.5 s and no
        original exception, `run_check` reads `timeout`, never the `X` status (A-C hold 2; mutations y and z).
        Domain: a leased checkout whose check exited 0. Oracle: the status, the held lock while the guard lives and
        the reaping of the orphan by the next entry, with the guard's exit observed by `waitid(WNOWAIT)` only."""
        hook = self.hook("after_report")
        check = self.check("quick", "print('done')")
        with patch.object(checks, "REAP", 0.5), patch.object(checks, "GUARD", hook):
            with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                key, lock = str(Path(found).resolve()), str(Path(found).resolve()) + ".lock"
                self.assertEqual(checks.run_check(check, found, export.environment())["status"], "timeout")
                self.assertEqual(len(checks.ORPHANS), 1)
                guard_process = checks.ORPHANS[0]
                self.assertTrue(self.holds(lock), "the guard's transferred copy of the lock is not held")
            self.assertTrue(os.path.exists(lock))
            self.assertTrue(self.holds(lock), "the lock was released with the checkout although the guard lives")
        self.assertTrue(self.until(lambda: self.exited(guard_process.pid)), "the guard never exited")
        self.assertEqual(checks.ORPHANS, [guard_process], "the guard left ORPHANS before a later entry polled it")
        checks.run_check(self.check("ok", "print('done')"), self.project, export.environment())
        self.assertEqual(checks.ORPHANS, [])
        self.assertIsNotNone(guard_process.returncode, "the next entry never reaped the guard (still a zombie)")
        self.assertFalse(self.holds(lock))
        self.forget(Path(key), Path(lock))

    def test_a_confirmed_stop_removes_both(self):
        """Class: the same 1 s timeout without the hold reaps the guard inside `REAP`, so the stop is confirmed and
        the context's exit removes the pair (the A-C control). Domain: a leased checkout, an ordinary timeout."""
        check = self.check("slow", "import time; time.sleep(30)", timeout_s=1)
        with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
            self.assertEqual(checks.run_check(check, found, export.environment())["status"], "timeout")
        self.assertEqual(self.entries(), [])
        self.assertEqual(checks.ORPHANS, [])


class ExceptionTests(Fixture):
    """A-X: the original exception is the one re-raised after cleanup, and no descriptor is left behind."""

    def test_a_popen_that_raises_leaves_the_process_untouched(self):
        """Class: an injected `popen` raising `ValueError` re-raises the same object, leaves no guard alive and does
        not change this process's open-descriptor count (A-X 1). Domain: the injected spawn, the `/dev/fd` count."""
        error = ValueError("injected spawn failure")

        def popen(*arguments, **options):
            raise error

        before = len(os.listdir("/dev/fd"))
        with self.assertRaises(ValueError) as caught:
            checks.run_check(self.check("boom", "print('x')"), self.project, export.environment(), popen=popen)
        self.assertIs(caught.exception, error)
        self.assertEqual((checks.ORPHANS, len(os.listdir("/dev/fd"))), ([], before))

    def test_a_post_spawn_cleanup_fault_still_reaps_the_registered_guard(self):
        """Class: the guard a successful spawn returned belongs to `_settle` *before* the parent's own lifeline end
        is closed, so a fault raised by that close is re-raised and the guard is still reaped -- within `REAP`,
        absent from `ORPHANS`, its stdout pipe closed -- and the checkout's exit removes the directory (A-2/R-2;
        mutation: moving the registration below that same close leaves `_reap` unreached, so the guard is neither
        reaped nor orphaned). Domain: a wrapped `popen` that records the real guard, a `socketpair` whose guard end
        closes for real and then raises one saved `ValueError` after a successful spawn, and a leased checkout.
        Oracle: the identical exception object, exactly one `_reap` call with the recorded guard, that guard's
        `returncode` set, `ORPHANS` empty, `Popen.stdout` closed, and the empty scratch root."""
        error = ValueError("injected post-spawn cleanup fault")
        spawned, reaped = [], []
        real_popen, real_reap, real_pair = subprocess.Popen, checks._reap, socket.socketpair

        def popen(*arguments, **options):
            process = real_popen(*arguments, **options)
            spawned.append(process)  # record the real guard, then hand it back unchanged
            return process

        def reap(supervisor, key=None):
            reaped.append(supervisor.process)  # `_reap` must receive exactly the guard the spawn returned
            return real_reap(supervisor, key)

        class Rude:
            """The parent's own lifeline end: it closes for real, then raises once (`_shut` swallows only OSError)."""

            def __init__(self, end):
                self.end, self.fired = end, False

            def fileno(self):
                return self.end.fileno()

            def close(self):
                self.end.close()
                if not self.fired:
                    self.fired = True
                    raise error

        def pair():
            lifeline, guard_end = real_pair()
            return lifeline, Rude(guard_end)

        with patch.object(socket, "socketpair", pair), patch.object(checks, "_reap", reap):
            with self.assertRaises(ValueError) as caught:
                with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                    checks.run_check(self.check("ok", "print('x')"), found, export.environment(), popen=popen)
        self.assertIs(caught.exception, error, "a later fault replaced the post-spawn exception")
        self.assertEqual(len(spawned), 1, "the guard was never spawned")
        self.assertEqual(reaped, spawned, "`_reap` did not receive the guard the spawn returned")
        self.assertIsNotNone(spawned[0].returncode, "the guard was not reaped within `REAP`")
        self.assertEqual(checks.ORPHANS, [])
        self.assertTrue(spawned[0].stdout.closed, "the guard's stdout pipe was left open")
        self.assertEqual(self.entries(), [], "the checkout survived a confirmed stop")

    def test_a_cleanup_oserror_never_replaces_the_original_exception(self):
        """Class: an `OSError` from the removal never escapes `checkout`'s cleanup and never replaces the caller's own
        exception: the lock and the directory are left for the recovery, the fd still closes and the original
        `ValueError` is the object re-raised (A-X 2; mutation q). Domain: a live checkout whose `_remove` walk raises
        `OSError(EIO)` during the exit, with an original `ValueError` in flight. Oracle: the original object, the
        unregistered lease and the pair left in place."""
        original = ValueError("the caller's own failure")
        walked = []

        def refusing(*arguments, **options):
            walked.append(True)
            raise OSError(errno.EIO, "injected walk failure")

        with patch.object(os, "walk", refusing):
            with self.assertRaises(ValueError) as caught:
                with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                    name = Path(found).name
                    raise original
        self.assertIs(caught.exception, original, "the removal OSError replaced the original exception")
        self.assertTrue(walked, "the removal walk was never reached")
        self.assertEqual(checks.LEASES, {}, "the failed removal left the lease registered")
        self.assertEqual(sorted(self.entries()), sorted([name, name + ".lock"]))
        self.forget(self.work / name)

    def test_a_cleanup_oserror_on_the_lifeline_copy_never_replaces_the_original(self):
        """Class: the close of the parent's own lifeline end is an OSError-safe cleanup step too (R-X: a cleanup
        `OSError` is swallowed and never replaces the original), so the original exception is still the object
        re-raised (A-X 2). Domain: an injected `popen` raising a particular `ValueError` together with a
        guard-side socket that really closes and then raises `OSError(EIO)`; the open-descriptor count sampled around
        the call. Oracle: the identical object, the empty orphan list and the unchanged count."""
        error = ValueError("injected spawn failure")
        real_pair = socket.socketpair

        class Rude:
            """The guard's own end of the lifeline: it closes the socket, then refuses; the parent must swallow it."""

            def __init__(self, end):
                self.end = end

            def fileno(self):
                return self.end.fileno()

            def close(self):
                self.end.close()
                raise OSError(errno.EIO, "injected close failure")

        def popen(*arguments, **options):
            raise error

        def pair():
            lifeline, guard_end = real_pair()
            return lifeline, Rude(guard_end)

        before = len(os.listdir("/dev/fd"))
        with patch.object(socket, "socketpair", pair):
            with self.assertRaises(ValueError) as caught:
                checks.run_check(self.check("boom", "print('x')"), self.project, export.environment(), popen=popen)
        self.assertIs(caught.exception, error, "the cleanup OSError replaced the original exception")
        self.assertEqual((checks.ORPHANS, len(os.listdir("/dev/fd"))), ([], before))


class RemovalOrderTests(Fixture):
    """A-K: a lease is removed directory → lock pathname → lock fd, under the still-held lock, by every holder."""

    def test_the_checkout_exit_removes_the_directory_then_the_lock_then_the_fd(self):
        """Class: `checkout`'s exit removes the directory, then the lock pathname, then closes the lock fd, in that
        order (A-K; mutation z3: a lock fd closed before the unlink fails here). Domain: a leased checkout, spied on
        `_remove`, `os.unlink` and the close of the registered *owning handle* (a spy on `os.close` alone would miss
        `file.close()`, and no raw close is added to production for the spy: R-D). Oracle: the recorded order, the
        closed descriptor and the empty root."""
        order, lock_path, fd = [], [None], [None]
        real_remove, real_unlink, real_close = checks._remove, os.unlink, checks._Lock.close

        def remove(*arguments, **options):
            order.append("remove")
            return real_remove(*arguments, **options)

        def unlink(*arguments, **options):
            if arguments and str(arguments[0]) == lock_path[0]:
                order.append("unlink")
            return real_unlink(*arguments, **options)

        def close(owner):
            order.append("close")
            return real_close(owner)

        with patch.object(checks, "_remove", remove), patch.object(os, "unlink", unlink), \
                patch.object(checks._Lock, "close", close):
            with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                key = str(Path(found).resolve())
                lock_path[0] = key + ".lock"
                fd[0] = checks.LEASES[key].fileno()
        self.assertEqual(order, ["remove", "unlink", "close"])
        with self.assertRaises(OSError):
            os.fstat(fd[0])  # the owning handle really closed its descriptor, last
        self.assertEqual(self.entries(), [])

    def test_the_guard_releases_a_lease_in_the_same_order(self):
        """Class: the guard's R-2 release removes the directory, then the lock pathname, then closes the transferred
        lock fd, in that order (A-K, in the guard child; the guard is stdlib-only, so its spies are installed by a
        wrapper run in its place). Domain: the guard run alone against a manual lease, the peer closed to trigger R-2.
        Oracle: the wrapper's log and the empty root."""
        self.work.mkdir()
        directory = self.work / (checks.PREFIX + "manual")
        directory.mkdir()
        (directory / "file.txt").write_text("x")
        lock = str(directory) + ".lock"
        holder = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(holder, fcntl.LOCK_EX)
        self.addCleanup(lambda: os.close(holder))
        order_file = self.base / "order.txt"
        wrapper = self.base / "guard_wrapper.py"
        wrapper.write_text(ORDER_HOOK % (GUARD_DIR, str(order_file), lock))
        lifeline, peer = socket.socketpair()
        guard = self.spawn([sys.executable, "-I", str(wrapper), "--lifeline", str(lifeline.fileno()),
                            "--lease", str(directory), "--lock-fd", str(holder), "--",
                            sys.executable, "-c", "import time; time.sleep(30)"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, pass_fds=(lifeline.fileno(), holder))
        lifeline.close()
        self.assertTrue(self.until(order_file.exists), "the wrapper never started")
        peer.close()  # zplan gone: the guard spawns its check, then the lost lifeline is R-2 (R-2/R-K)
        self.assertTrue(self.until(lambda: guard.poll() is not None), "the guard never exited")
        self.assertEqual(guard.returncode, 0)
        self.assertEqual(order_file.read_text().split(), ["remove", "unlink", "close"])
        self.assertEqual(self.entries(), [])

    def test_a_failed_removal_keeps_the_sidecar_of_the_checkout_exit(self):
        """Class: when the directory removal fails, `checkout`'s exit removes nothing else -- the lock pathname stays
        for the later recovery -- and still closes the owning lock handle last (R-K: a failed removal leaves the rest
        to the recovery). Domain: an owned lease whose `rmtree` is injected to raise `OSError(EIO)` for that directory
        alone, with the removal, `os.unlink` and owning-handle close spies. Oracle: the recorded order (no unlink) and
        the pair left in the root."""
        target, order, lock_path = [None], [], [None]
        real_remove, real_unlink, real_close, real_rmtree = checks._remove, os.unlink, checks._Lock.close, shutil.rmtree

        def rmtree(path, *arguments, **options):
            if target[0] is not None and str(path) == target[0]:
                raise OSError(errno.EIO, "injected removal failure")
            return real_rmtree(path, *arguments, **options)

        def remove(*arguments, **options):
            order.append("remove")
            return real_remove(*arguments, **options)

        def unlink(*arguments, **options):
            if arguments and str(arguments[0]) == lock_path[0]:
                order.append("unlink")
            return real_unlink(*arguments, **options)

        def close(owner):
            order.append("close")
            return real_close(owner)

        with patch.object(shutil, "rmtree", rmtree), patch.object(checks, "_remove", remove), \
                patch.object(os, "unlink", unlink), patch.object(checks._Lock, "close", close):
            with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                name = Path(found).name
                target[0] = str(Path(found).resolve())
                lock_path[0] = target[0] + ".lock"
        self.assertEqual(order, ["remove", "close"], "a failed directory removal unlinked the sidecar (R-K)")
        self.assertEqual(checks.LEASES, {}, "the failed removal left the lease registered")
        self.assertEqual(sorted(self.entries()), sorted([name, name + ".lock"]))
        self.forget(self.work / name)

    def test_a_failed_removal_keeps_the_sidecar_in_the_guard(self):
        """Class: the guard's R-2 release keeps the lock pathname when the directory removal fails and still closes
        the transferred fd last (R-K, in the guard child). Domain: the guard run alone against a manual lease whose
        `rmtree` is injected to fail, the peer closed to trigger R-2. Oracle: the wrapper's log (no unlink) and the
        pair left in the root."""
        self.work.mkdir()
        directory = self.work / (checks.PREFIX + "manual-fail")
        directory.mkdir()
        (directory / "file.txt").write_text("x")
        lock = str(directory) + ".lock"
        holder = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(holder, fcntl.LOCK_EX)
        self.addCleanup(lambda: os.close(holder))
        order_file = self.base / "order.txt"
        wrapper = self.base / "guard_fail.py"
        wrapper.write_text(FAIL_HOOK % (GUARD_DIR, str(order_file), str(directory)))
        lifeline, peer = socket.socketpair()
        guard = self.spawn([sys.executable, "-I", str(wrapper), "--lifeline", str(lifeline.fileno()),
                            "--lease", str(directory), "--lock-fd", str(holder), "--",
                            sys.executable, "-c", "import time; time.sleep(30)"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, pass_fds=(lifeline.fileno(), holder))
        lifeline.close()
        self.assertTrue(self.until(order_file.exists), "the wrapper never started")
        peer.close()  # zplan gone: the guard spawns its check, then the lost lifeline is R-2 (R-2/R-K)
        self.assertTrue(self.until(lambda: guard.poll() is not None), "the guard never exited")
        self.assertEqual(guard.returncode, 0)
        self.assertEqual(order_file.read_text().split(), ["remove", "close"], "the guard unlinked a kept sidecar")
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), sorted([directory.name, directory.name + ".lock"]))
        self.forget(directory)

    def test_a_failed_removal_keeps_the_sidecar_of_an_abandoned_pair(self):
        """Class: an abandoned `_lease` pair whose directory removal fails keeps its lock pathname too, closes its
        owning handle last and re-raises the original registration failure (R-K/R-X). Domain: `_lease` with a
        registration that raises and an `rmtree` injected to fail for that directory, with the removal, unlink and
        owning-handle close spies. Oracle: the recorded order (no unlink) and the pair left in the root."""
        self.work.mkdir()
        stem = "ef" * 8
        directory = self.work / (checks.PREFIX + stem)
        lock = str(directory) + ".lock"
        order = []
        real_remove, real_unlink, real_close, real_rmtree = checks._remove, os.unlink, checks._Lock.close, shutil.rmtree

        def rmtree(path, *arguments, **options):
            if str(path) == str(directory):
                raise OSError(errno.EIO, "injected removal failure")
            return real_rmtree(path, *arguments, **options)

        def remove(*arguments, **options):
            order.append("remove")
            return real_remove(*arguments, **options)

        def unlink(*arguments, **options):
            if arguments and str(arguments[0]) == lock:
                order.append("unlink")
            return real_unlink(*arguments, **options)

        def close(owner):
            order.append("close")
            return real_close(owner)

        class Exploding(dict):
            def __setitem__(self, key, value):
                raise RuntimeError("injected registration failure")

        with patch("os.urandom", return_value=bytes.fromhex(stem)), patch.object(checks, "LEASES", Exploding()), \
                patch.object(checks, "_remove", remove), patch.object(os, "unlink", unlink), \
                patch.object(checks._Lock, "close", close), patch.object(shutil, "rmtree", rmtree):
            with self.assertRaises(RuntimeError):
                with checks.checkout(self.project, self.commit, self.tree, self.work):
                    self.fail("the lease was registered although registration was injected to fail")
        self.assertEqual(order, ["remove", "close"], "a failed directory removal unlinked the sidecar (R-K)")
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), sorted([directory.name, directory.name + ".lock"]))
        self.assertEqual(checks.LEASES, {}, "the failed pair was registered")
        self.forget(directory)

    def test_an_abandoned_lease_pair_is_removed_in_order(self):
        """Class: an acquisition that created a pair and then failed to register it removes the pair in the same
        order -- directory, lock pathname, fd -- and re-raises the original failure (A-K, an abandoned `_lease`
        pair). Domain: `_lease` with a registration that raises, its pair spied. Oracle: the recorded order."""
        self.work.mkdir()
        stem = "ab" * 8
        directory = self.work / (checks.PREFIX + stem)
        lock = str(directory) + ".lock"
        order = []
        real_remove, real_unlink, real_close = checks._remove, os.unlink, checks._Lock.close

        def remove(*arguments, **options):
            order.append("remove")
            return real_remove(*arguments, **options)

        def unlink(*arguments, **options):
            if arguments and str(arguments[0]) == lock:
                order.append("unlink")
            return real_unlink(*arguments, **options)

        def close(owner):
            order.append("close")
            return real_close(owner)

        class Exploding(dict):
            def __setitem__(self, key, value):
                raise RuntimeError("injected registration failure")

        with patch("os.urandom", return_value=bytes.fromhex(stem)), patch.object(checks, "LEASES", Exploding()), \
                patch.object(checks, "_remove", remove), patch.object(os, "unlink", unlink), \
                patch.object(checks._Lock, "close", close):
            with self.assertRaises(RuntimeError):
                with checks.checkout(self.project, self.commit, self.tree, self.work):
                    self.fail("the lease was registered although registration was injected to fail")
        self.assertEqual(order, ["remove", "unlink", "close"])
        self.assertEqual(self.entries(), [])

    def test_a_failed_exclusive_create_unlinks_nothing(self):
        """Class: an acquisition whose `O_EXCL` create fails closes only its own fd and unlinks nothing; the
        pre-existing entry is left exactly as it was (A-K/R-K; the a9107fc collision test's rule). Domain: a taken
        `checkout-*` stem whose sidecar lock is already published, `os.urandom` pinned to it. Oracle: no `unlink`
        observed and the witness intact."""
        self.work.mkdir()
        stem = "cd" * 8
        collided = self.work / (checks.PREFIX + stem)
        collided.mkdir()
        (collided / "keep.txt").write_text("keep\n")
        lock = str(collided) + ".lock"
        held = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(held, fcntl.LOCK_EX)
        self.addCleanup(lambda: os.close(held))
        unlinked = []
        real_unlink = os.unlink

        def unlink(*arguments, **options):
            unlinked.append(str(arguments[0]))
            return real_unlink(*arguments, **options)

        try:
            with patch("os.urandom", return_value=bytes.fromhex(stem)), patch.object(os, "unlink", unlink):
                with self.assertRaises(FileExistsError):
                    with checks.checkout(self.project, self.commit, self.tree, self.work):
                        self.fail("a lease was acquired under a taken lock name")
            self.assertEqual(unlinked, [], "a failed `O_EXCL` acquisition unlinked something")
            self.assertEqual((collided / "keep.txt").read_text(), "keep\n")
            self.assertTrue(os.path.exists(lock))
        finally:
            self.forget(collided)


class EnvironmentTests(Fixture):
    """A-E: the check sees exactly the environment handed to `run_check` (or the caller's own for `env=None`)."""

    def test_a_native_check_sees_every_name_of_the_given_environment(self):
        """Class: `env={"A": "1"}` with a native `/usr/bin/env` check → the output contains `A=1` (A-E/R-1: the
        guard adds none of the names it was given). Domain: the native program, one name. Oracle: the printed line."""
        found = checks.run_check(NATIVE_ENV, self.project, {"A": "1"})
        self.assertEqual(found["status"], 0)
        self.assertIn("A=1", found["tail"].split("\n"))

    def test_env_none_passes_the_controllers_own_environment(self):
        """Class: `env=None` hands the guard this process's environment, so a marker set here reaches the check
        (A-E/R-1). Domain: a native check, one marker in the controller's environment. Oracle: the printed line."""
        with patch.dict(os.environ, {"ZPLAN_MARKER": "present"}):
            found = checks.run_check(NATIVE_ENV, self.project, None)
        self.assertEqual(found["status"], 0)
        self.assertIn("ZPLAN_MARKER=present", found["tail"].split("\n"))

    def test_a_handed_over_environment_loses_at_most_the_consumed_name(self):
        """Class: the check sees the *whole* environment the call handed over -- every name of the `env` given to
        `run_check` (or every name of this process's environment for `env=None`) with its value -- except the names
        the guard's own interpreter consumes before `check_guard.py` runs (A-G, amended): the allowed removals are
        exactly {`__PYVENV_LAUNCHER__`} -- CPython clears it in every child it starts, on macOS and on Linux alike --
        while its own additions (`LC_CTYPE`, `__CF_USER_TEXT_ENCODING`) and its coercion of `LC_CTYPE` are allowed on
        the addition side. The class this guards is *any* input name lost or altered beyond those two exceptions, so
        the oracle compares the full input mapping, not just the planted marker. Interpretations recorded here (the
        worker's summary does not reach the reviewers): (1) A-G's "every name with its value" and R-1's plain `env=`
        cannot both hold through an interpreter that edits its environment, so A-G is read as "every name, additions
        allowed, removals limited to the one consumed name" and the mapping is handed over untouched (`env=`), never
        re-framed; (2) for `env=None` the caller's environment is made deterministic with
        `patch.dict(os.environ, planted, clear=True)` and the complete snapshot is the oracle, because the evidence
        tail is the R-4 scrubbed window: a non-isolated caller environment (this runner carries `*_API_KEY` values the
        scrubber rewrites to `live.HIDDEN`) could not be compared name-for-name, and a marker-only oracle would miss
        a lost name. Domain: an explicit mapping with three names (one consumable, two ordinary) and `env=None` over
        an isolated caller environment carrying the same three names. Oracle: `/usr/bin/env`'s output, parsed, loses
        no input name but `__PYVENV_LAUNCHER__`, keeps every retained input name's value (`LC_CTYPE` excepted) and
        carries the non-exempt markers `ZPLAN_ENV_MARK` and `ZPLAN_OTHER_INPUT`."""
        consumed = "__PYVENV_LAUNCHER__"  # the guard's interpreter clears this one before any guard code runs
        planted = {consumed: sys.executable, "ZPLAN_ENV_MARK": "here", "ZPLAN_OTHER_INPUT": "must-survive"}

        def shown(found):
            self.assertEqual(found["status"], 0)
            return dict(line.split("=", 1) for line in found["tail"].splitlines() if "=" in line)

        def checked(observed, source, mode):
            self.assertLessEqual(set(source) - set(observed), {consumed},
                                 "%s lost a name other than the consumed one" % mode)
            self.assertEqual({name: value for name, value in observed.items() if name in source and name != "LC_CTYPE"},
                             {name: source[name] for name in source if name in observed and name != "LC_CTYPE"},
                             "%s changed a retained name's value" % mode)
            self.assertIn("ZPLAN_ENV_MARK", observed, "%s lost the ordinary marker" % mode)

        checked(shown(checks.run_check(NATIVE_ENV, self.project, dict(planted))), planted, "an explicit mapping")
        with patch.dict(os.environ, planted, clear=True):
            inherited = dict(os.environ)  # the complete input mapping `env=None` hands over; every name counts
            checked(shown(checks.run_check(NATIVE_ENV, self.project, None)), inherited, "`env=None`")


HOLDER = """
import fcntl, os, pathlib, sys, time
fcntl.flock(int(sys.argv[1]), fcntl.LOCK_EX)
pathlib.Path(sys.argv[2]).write_text(str(os.getpid()))
time.sleep(30)
"""

OWNER = """
import pathlib, sys, time
from terminal_planner import checks
project, commit, tree, work, found, proceed, marker, resume = sys.argv[1:9]


def pause():
    checks.forget_after_remove = real  # one-shot: only the lease's own removal pauses
    pathlib.Path(marker).write_text("paused")
    end = time.monotonic() + 3  # every wait of this module is bounded at 3 s (Acceptance)
    while not pathlib.Path(resume).exists() and time.monotonic() < end:
        time.sleep(0.02)


real = checks.forget_after_remove
checks.forget_after_remove = pause
with checks.checkout(project, commit, tree, work) as leased:
    pathlib.Path(found).write_text(str(leased))
    end = time.monotonic() + 3  # every wait of this module is bounded at 3 s (Acceptance)
    while not pathlib.Path(proceed).exists() and time.monotonic() < end:
        time.sleep(0.02)
"""

PAUSE_HOOK = """
import pathlib, sys, time
sys.path.insert(0, %r)
import check_guard as guard
marker, resume = %r, %r


def pause():
    pathlib.Path(marker).write_text("paused")
    end = time.monotonic() + 3  # every wait of this module is bounded at 3 s (Acceptance)
    while not pathlib.Path(resume).exists() and time.monotonic() < end:
        time.sleep(0.02)


guard.release_after_remove = pause
guard.main(sys.argv[1:])
"""


class SweepTests(Fixture):
    """A-S/R-4/R-V/R-W: `sweep` reaps unheld `checkout-*` leftovers, reports a live holder busy, and never removes
    what it does not own; A-W's interleavings pin the two publication seams of this split."""

    def setUp(self):
        super().setUp()
        self._exited = set()

    def holder(self, path):
        """A `sys.executable` child holding `flock(LOCK_EX)` on the inherited `path` until it is stopped (A-S)."""
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
        marker = self.base / ("held-" + os.urandom(4).hex())
        child = self.spawn([sys.executable, "-c", HOLDER, str(fd), str(marker)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, pass_fds=(fd,))
        os.close(fd)  # the child's inherited copy is the only holder left
        self.addCleanup(self.stop, child)
        self.assertTrue(self.until(marker.exists), "the holder never took the lock")
        return child

    def stop(self, child):
        """Stop one fixture child: never raises, safe to call twice (the cleanup and the test share it)."""
        try:
            child.kill()
            child.wait(timeout=3)
        except OSError:
            pass

    def kill_group(self, pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass

    def listing(self, root):
        return sorted(path.name for path in Path(root).iterdir()) if Path(root).exists() else []

    def _exit_once(self, manager):
        """Exit a `checkout` context this test opened by hand, at most once (so the cleanup is idempotent)."""
        if id(manager) not in self._exited:
            self._exited.add(id(manager))
            manager.__exit__(None, None, None)

    def test_sweep_removes_unheld_leftovers_and_reports_a_held_lock_busy(self):
        """Class: a free or absent lock removes the entry and its lock, a held lock is one busy and goes once the
        holder exits, and a non-`checkout-*` name is untouched (A-S; mutation h: a `sweep` that ignores a held lock
        removes it anyway). Domain: a held leftover, a lockless leftover, an unheld leftover and an orphan lock.
        Oracle: the counts and `lexists` of every touched path."""
        self.work.mkdir()
        held, bare, lost, orphan = (self.work / name for name in
                                    ("checkout-held", "checkout-bare", "checkout-lost", "checkout-orphan"))
        held.mkdir()
        (held / "file.txt").write_text("x")
        holder = self.holder(self.work / "checkout-held.lock")
        bare.mkdir()
        (bare / "file.txt").write_text("y")
        lost.mkdir()
        (lost / "file.txt").write_text("z")
        (self.work / "checkout-lost.lock").write_text("")
        (self.work / "checkout-orphan.lock").write_text("")
        (self.work / "keep").mkdir()
        self.assertEqual(checks.sweep(self.work), {"removed": 3, "busy": 1})
        self.assertTrue(os.path.lexists(held), "the held entry was removed")
        self.assertTrue(os.path.lexists(str(held) + ".lock"), "the held lock was removed")
        for gone in (bare, lost, orphan, self.work / "checkout-lost.lock", self.work / "checkout-orphan.lock"):
            self.assertFalse(os.path.lexists(gone), "%s survived" % gone)
        self.assertEqual(self.entries(), ["checkout-held", "checkout-held.lock", "keep"])
        self.stop(holder)
        self.assertTrue(self.until(lambda: not self.holds(str(held) + ".lock")), "the lock stayed held")
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertEqual(self.entries(), ["keep"])
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})

    def test_sweep_answers_zeros_for_a_missing_and_an_empty_root(self):
        """Class: a missing root and an empty root both answer zeros and never raise (R-4/R-V). Domain: an absent
        directory and an existing empty one. Oracle: the counts."""
        self.assertEqual(checks.sweep(self.base / "absent"), {"removed": 0, "busy": 0})
        self.work.mkdir()
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})

    def test_a_live_checkout_is_busy_for_a_sweep_and_gone_after_it_exits(self):
        """Class: a live `checkout` holds its lease lock, so a sweep of its root is one busy and removes nothing;
        once the context exits the pair is already gone and the sweep returns zeros (A-S state: an entry held by a
        live checkout). Domain: a real checkout context, its own sweep. Oracle: the counts and `lexists`."""
        with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
            lock = str(Path(found).resolve()) + ".lock"
            self.assertTrue(self.holds(lock), "the live checkout does not hold its lease lock")
            self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
            self.assertTrue(os.path.isdir(found), "the live checkout's directory was removed")
            self.assertTrue(os.path.lexists(lock))
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})
        self.assertEqual(self.entries(), [])

    def test_sweep_answers_busy_for_a_root_it_cannot_list(self):
        """Class: a root that cannot be listed -- a regular file, or a directory this uid may not read -- is
        `{"removed": 0, "busy": 1}` and never raises; the mode-000 case is skipped where the uid lists it anyway
        (R-V). Domain: a regular file as the root and a mode-000 directory. Oracle: the counts."""
        regular = self.base / "rootfile"
        regular.write_text("x")
        self.assertEqual(checks.sweep(regular), {"removed": 0, "busy": 1})
        trapped = self.base / "trapped"
        trapped.mkdir()
        os.chmod(trapped, 0o000)
        try:
            try:
                os.listdir(trapped)
            except OSError:
                self.assertEqual(checks.sweep(trapped), {"removed": 0, "busy": 1})
            else:
                self.skipTest("this uid lists a mode-000 root, so the unreadable-root case cannot be shown")
        finally:
            os.chmod(trapped, 0o700)

    def test_sweep_counts_a_failed_removal_busy_and_removes_it_once_restored(self):
        """Class: an entry whose removal fails is one busy with its lock left with it, and a second sweep after the
        obstacle is gone removes it (R-V; mutation t: a failed removal counted as removed). Domain: a root made mode
        0500 so the entry cannot be unlinked (skipped for the root user). Oracle: the counts, `lexists` and the
        second sweep."""
        if os.geteuid() == 0:
            self.skipTest("the root user ignores the mode, so the failed-removal case cannot be shown")
        self.work.mkdir()
        entry = self.work / "checkout-locked"
        entry.mkdir()
        (entry / "file.txt").write_text("x")
        lock = self.work / "checkout-locked.lock"
        lock.write_text("")
        os.chmod(self.work, 0o500)
        try:
            self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
            self.assertTrue(os.path.lexists(entry), "the unremovable entry was reported gone")
            self.assertTrue(os.path.lexists(lock), "the lock of the busy entry was removed")
        finally:
            os.chmod(self.work, 0o700)
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertFalse(os.path.lexists(entry))
        self.assertFalse(os.path.lexists(lock))
        self.assertEqual(self.entries(), [])

    def test_sweep_never_counts_a_failed_removal_as_removed(self):
        """Class: when the entry survives its removal, `sweep` answers busy and removes nothing else -- the entry
        stays and its lock stays with it (R-V/R-K; mutations t and x: a removal counted removed without checking
        `lexists`, or a lock unlinked before the entry, would report removed while the entry is still there, and x
        would free the lock too). Domain: a `checkout-*` directory with a free lock whose `_remove` is injected to
        refuse, the real `unlink` untouched. Oracle: the counts and `lexists` of both."""
        self.work.mkdir()
        directory = self.work / "checkout-refused"
        directory.mkdir()
        lock = str(directory) + ".lock"
        (self.work / "checkout-refused.lock").write_text("")
        with patch.object(checks, "_remove", lambda *arguments, **options: False):
            self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        self.assertTrue(os.path.lexists(directory), "the refused entry was reported gone")
        self.assertTrue(os.path.lexists(lock), "the lock of a surviving entry was removed")
        self.forget(directory)

    def test_sweep_removes_the_entry_before_its_lock(self):
        """Class: a unit is removed entry-first and its lock pathname last, under the still-held lock (R-4/R-W;
        mutation x: a `sweep` that unlinked the lock first would free the lock of an entry whose removal then failed).
        Domain: a `checkout-*` directory with a free lock, spied on `_remove` and `os.unlink`. Oracle: the recorded
        order and the empty root."""
        self.work.mkdir()
        directory = self.work / "checkout-order"
        directory.mkdir()
        (directory / "file.txt").write_text("x")
        lock = str(directory) + ".lock"
        (self.work / "checkout-order.lock").write_text("")
        order = []
        real_remove, real_unlink = checks._remove, os.unlink

        def remove(*arguments, **options):
            order.append("remove")
            return real_remove(*arguments, **options)

        def unlink(path, *arguments, **options):
            if str(path) == lock:
                order.append("unlink")
            return real_unlink(path, *arguments, **options)

        with patch.object(checks, "_remove", remove), patch.object(os, "unlink", unlink):
            self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertEqual(order, ["remove", "unlink"], "the lock was removed before the entry")
        self.assertEqual(self.entries(), [])

    def test_sweep_unlinks_a_symlink_entry_without_reaching_its_target(self):
        """Class: a `checkout-*` symlink under the root is an entry of that root, never a window into its target:
        `sweep` unlinks the link and the target keeps its tree, its modes and its content (R-4 containment; mutation
        s: a removal that walked through the link would `chmod` the target's directory and file). Domain: a link to a
        project outside the root whose file is mode 0600, plus the link's sibling lock. Oracle: the target's modes
        and content, and the counts."""
        self.work.mkdir()
        outside = self.base / "outside"
        (outside / "nested").mkdir(parents=True)
        secret = outside / "nested" / "deep.txt"
        secret.write_text("x")
        os.chmod(secret, 0o600)
        os.chmod(outside, 0o755)
        link = self.work / "checkout-link"
        link.symlink_to(outside)
        (self.work / "checkout-link.lock").write_text("")
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertEqual(os.stat(secret).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(outside).st_mode & 0o777, 0o755)
        self.assertEqual(secret.read_text(), "x")
        self.assertFalse(os.path.lexists(link), "the link survived")
        self.assertFalse(os.path.lexists(str(link) + ".lock"))
        self.assertEqual(self.entries(), [])

    def test_sweep_removes_a_directory_named_like_a_sidecar_lock(self):
        """Class: an entry named `checkout-*.lock` that is a *directory* is a checkout without a valid lock, never
        the sidecar of a directory that is not there: its own `checkout-*.lock.lock` (absent, free or held) is its
        lock (R-4 row 3; mutation u: the suffix heuristic read the directory as a lock, tried to `flock` it and
        answered busy forever). Domain: three such directories. Oracle: the counts, the survivors and the held one
        once its holder exits."""
        self.work.mkdir()
        for name in ("checkout-lockless", "checkout-free", "checkout-held"):
            directory = self.work / (name + ".lock")
            directory.mkdir()
            (directory / "file.txt").write_text("x")
        (self.work / "checkout-free.lock.lock").write_text("")
        holder = self.holder(self.work / "checkout-held.lock.lock")
        self.assertEqual(checks.sweep(self.work), {"removed": 2, "busy": 1})
        self.assertEqual(self.entries(), ["checkout-held.lock", "checkout-held.lock.lock"])
        self.stop(holder)
        self.assertTrue(self.until(lambda: not self.holds(str(self.work / "checkout-held.lock.lock"))))
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertEqual(self.entries(), [])

    def test_sweep_removes_an_entry_and_a_lock_that_are_both_directories(self):
        """Class: `checkout-x` and `checkout-x.lock` both directories are two entries (the `.lock`-named one has no
        valid lock of its own): longest-first order clears `checkout-x.lock` before `checkout-x`'s lock is examined,
        so both go in one sweep (R-4). Domain: two directories and their contents. Oracle: the counts and the empty
        root."""
        self.work.mkdir()
        for name in ("checkout-x", "checkout-x.lock"):
            (self.work / name).mkdir()
            (self.work / name / "file.txt").write_text("x")
        self.assertEqual(checks.sweep(self.work), {"removed": 2, "busy": 0})
        self.assertFalse(os.path.lexists(self.work / "checkout-x"))
        self.assertFalse(os.path.lexists(self.work / "checkout-x.lock"))
        self.assertEqual(self.entries(), [])

    def test_sweep_never_keeps_a_dangling_lock_link_unaccounted(self):
        """Class: a `checkout-*.lock` symlink to a missing target is a leftover, never an absent lock: it is unlinked
        (never opened, never followed), so a sweep never answers removed while it stays (R-4/R-V; mutation v).
        Domain: a dangling lock link beside its entry and one alone. Oracle: the counts, the `lexists` of each link
        and a second sweep. Interpretation: an R-4 row-2 `.lock` link is an entry of its own, so the pair is two
        units."""
        self.work.mkdir()
        (self.work / "checkout-orphan").mkdir()
        (self.work / "checkout-orphan.lock").symlink_to(self.work / "missing-too")
        (self.work / "checkout-gone.lock").symlink_to(self.work / "missing")
        self.assertEqual(checks.sweep(self.work), {"removed": 3, "busy": 0})
        self.assertFalse(os.path.lexists(self.work / "checkout-orphan.lock"))
        self.assertFalse(os.path.lexists(self.work / "checkout-gone.lock"))
        self.assertFalse(os.path.lexists(self.work / "checkout-orphan"))
        self.assertEqual(self.entries(), [])
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})

    def test_sweep_never_blocks_on_a_fifo_lock_name(self):
        """Class: a fifo named `checkout-f.lock` is not a lease lock (R-4 row 2): `sweep` unlinks it and creates its
        own `checkout-f.lock.lock` instead, never opening the fifo, so a `sweep` with no writer returns (an `open` on
        the fifo would block forever). Domain: a fifo under a bounded worker thread. Oracle: the counts and a fresh
        `lexists`."""
        if not hasattr(os, "mkfifo"):
            self.skipTest("this platform has no fifo")
        self.work.mkdir()
        os.mkfifo(self.work / "checkout-f.lock")
        found = {}
        worker = threading.Thread(target=lambda: found.setdefault("value", checks.sweep(self.work)), daemon=True)
        worker.start()
        worker.join(3)
        self.assertFalse(worker.is_alive(), "sweep blocked on the fifo")
        self.assertEqual(found["value"], {"removed": 1, "busy": 0})
        self.assertFalse(os.path.lexists(self.work / "checkout-f.lock"))
        self.assertEqual(self.entries(), [])

    def test_sweep_leaves_non_prefixed_names_and_a_dashless_checkout_untouched(self):
        """Class: only names starting with `checkout-` are in the domain: a plain `checkout` without the dash, a
        `checkout`-prefixed name with the wrong shape and an unrelated name are all untouched (R-4). Domain: `keep`,
        `checkout`, `checkouts-1`. Oracle: the counts and the surviving names."""
        self.work.mkdir()
        for name in ("keep", "checkout", "checkouts-1"):
            (self.work / name).write_text("x")
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})
        self.assertEqual(self.entries(), ["checkout", "checkouts-1", "keep"])

    def test_sweep_removes_two_hundred_leftovers_in_one_call(self):
        """Class: a large batch of unheld leftovers is fully cleared by one `sweep` (R-4's only bound is the root's
        own memory). Domain: 200 `checkout-*` entries, half with a free lock and half lockless. Oracle: the counts and
        the empty root."""
        self.work.mkdir()
        for index in range(200):
            name = "checkout-%03d" % index
            (self.work / name).mkdir()
            (self.work / name / "file.txt").write_text("x")
            if index % 2:
                (self.work / (name + ".lock")).write_text("")
        self.assertEqual(checks.sweep(self.work), {"removed": 200, "busy": 0})
        self.assertEqual(self.entries(), [])

    def test_sweep_handles_each_entry_shape_with_each_lock_shape(self):
        """Class: every R-4 entry row with an absent, free, held, symlinked and directory-shaped lock (R-4; the held
        row is mutation h). Domain: an entry that is a directory, a regular file, a symlink or a fifo, each with the
        five lock shapes. Oracle: the counts and `lexists` of the entry, its lock and the link target.
        Interpretation: an R-4 `.lock`-named symlink or directory is an entry of its own, cleared longest-first, so
        the symlinked and directory-shaped rows clear two units (the entry plus the `.lock`-named one)."""
        self.work.mkdir()
        for shape in ("directory", "file", "symlink", "fifo"):
            for lock in ("absent", "free", "held", "symlinked", "directory"):
                with self.subTest(shape=shape, lock=lock):
                    self.assert_entry_lock_shape(shape, lock)

    def assert_entry_lock_shape(self, shape, lock):
        if shape == "fifo" and not hasattr(os, "mkfifo"):
            self.skipTest("this platform has no fifo")
        root = self.base / ("m-%s-%s" % (shape, lock))
        root.mkdir()
        name = "checkout-e"
        entry, lockpath = root / name, root / (name + ".lock")
        target = self.base / ("target-%s-%s" % (shape, lock))  # outside the root: only prefixed names are the domain
        target.write_text("keep\n")
        if shape == "directory":
            entry.mkdir()
            (entry / "inside.txt").write_text("x")
        elif shape == "file":
            entry.write_text("x")
        elif shape == "symlink":
            entry.symlink_to(target)
        else:
            os.mkfifo(entry)
        holder = None
        if lock == "free":
            lockpath.write_text("")
        elif lock == "held":
            holder = self.holder(lockpath)
        elif lock == "symlinked":
            lockpath.symlink_to(root / "missing")
        elif lock == "directory":
            lockpath.mkdir()
            (lockpath / "inside.txt").write_text("y")
        try:
            if lock == "held":
                self.assertEqual(checks.sweep(root), {"removed": 0, "busy": 1})
                self.assertTrue(os.path.lexists(entry), "the entry of a held lock was removed")
                self.assertTrue(os.path.lexists(lockpath))
                self.stop(holder)
                self.assertTrue(self.until(lambda: not self.holds(lockpath)), "the lock stayed held")
                self.assertEqual(checks.sweep(root), {"removed": 1, "busy": 0})
            elif lock in ("absent", "free"):
                self.assertEqual(checks.sweep(root), {"removed": 1, "busy": 0})
            else:  # a `.lock`-named symlink or directory is its own entry, so two units clear
                self.assertEqual(checks.sweep(root), {"removed": 2, "busy": 0})
            self.assertFalse(os.path.lexists(entry), "%s/%s: the entry survived" % (shape, lock))
            self.assertFalse(os.path.lexists(lockpath), "%s/%s: the lock survived" % (shape, lock))
            self.assertEqual(self.listing(root), [], "%s/%s: leftovers" % (shape, lock))
            if shape == "symlink":
                self.assertEqual(target.read_text(), "keep\n", "%s/%s: the link target changed" % (shape, lock))
        finally:
            if holder is not None:
                self.stop(holder)

    def test_a_project_at_or_under_the_root_is_refused_and_creates_nothing(self):
        """Class: `checkout` refuses a project that is the root itself or lies under it, with `ValueError`, and
        creates nothing under the root (R-P; mutation w: a project at `root/checkout-p` is a lockless entry by R-4,
        so an accepted checkout would let a later sweep delete a real project). Domain: `project == root` and
        `project == root/checkout-p`. Oracle: the raise and the untouched root."""
        for project in (self.work, self.work / "checkout-p"):
            with self.subTest(project=str(project)):
                with self.assertRaises(ValueError):
                    with checks.checkout(project, self.commit, self.tree, self.work):
                        self.fail("a project at or under the root was accepted")
        self.assertFalse(os.path.lexists(self.work), "something was created under the root")

    def test_a_publication_between_sweep_open_and_flock_is_never_removed(self):
        """Class: `sweep_after_open` fires after sweep opened the lock of a live checkout A at name N and before its
        `flock`; the hook exits A's context (A removes N and its lock) and enters a new checkout B that publishes the
        same N; sweep then reports N busy and removes nothing (R-W; mutation r: without the post-flock
        re-verification B's directory is removed). Domain: two checkouts of one name, no sleeps. Oracle: the counts,
        B's pair and a test-side `LOCK_NB` on B's lock. Interpretation: A is a real `checkout` context whose
        `__exit__` is run inside the hook (its generator is exited exactly once)."""
        self.work.mkdir()
        stem = bytes.fromhex("aa" * 8)
        name = checks.PREFIX + stem.hex()
        real_hook = checks.sweep_after_open
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        a = checks.checkout(self.project, self.commit, self.tree, self.work)
        self.addCleanup(self._exit_once, a)
        with patch("os.urandom", return_value=stem):
            found = a.__enter__()
        self.assertEqual(Path(found).name, name, "A was not leased under the pinned name")

        def after_open():
            checks.sweep_after_open = real_hook  # one-shot: only the first open interleaves
            self._exit_once(a)  # A removes N and N.lock, and closes its lock fd
            with patch("os.urandom", return_value=stem):
                stack.enter_context(checks.checkout(self.project, self.commit, self.tree, self.work))

        checks.sweep_after_open = after_open
        self.addCleanup(setattr, checks, "sweep_after_open", real_hook)
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        published = self.work / name
        self.assertTrue(os.path.isdir(published), "B's directory was removed")
        self.assertTrue(os.path.lexists(str(published) + ".lock"), "B's lock was removed")
        self.assertTrue(self.holds(str(published) + ".lock"), "B's lock is not held")
        stack.close()
        self.assertEqual(self.entries(), [])

    def test_a_sweep_between_lease_create_and_flock_leaves_a_locked_checkout(self):
        """Class: `lease_after_create` fires between `_lease`'s lock create and its `flock` and runs `sweep(root)`:
        the just-created orphan lock is seen (no directory yet) and counted busy or removed, never both; `_lease`
        then finds its lock no longer on disk and retries a fresh name, so the checkout still yields a directory
        whose own lock is on disk and held (R-W; mutation r2: without the publication check the lease ends with no
        lock on disk). Domain: one `checkout` with the seam replaced, no sleeps. Oracle: the checkout's own pair, the
        held lock and the sweep counts."""
        self.work.mkdir()
        seen = []
        real = checks.lease_after_create

        def hook():
            checks.lease_after_create = real  # one-shot: the retry after the loss must not sweep again
            seen.append(checks.sweep(self.work))

        checks.lease_after_create = hook
        self.addCleanup(setattr, checks, "lease_after_create", real)
        with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
            lock = str(Path(found).resolve()) + ".lock"
            self.assertTrue(os.path.isdir(found), "the lease published no directory")
            self.assertTrue(os.path.lexists(lock), "the lease published a checkout with no lock on disk")
            self.assertTrue(self.holds(lock), "the lease's lock is not held")
        self.assertEqual(len(seen), 1, "the seam fired %d times" % len(seen))
        self.assertEqual(seen[0]["removed"] + seen[0]["busy"], 1, "the orphan lock was counted twice")
        self.assertEqual(self.entries(), [])

    def test_an_old_owners_checkout_exit_pauses_for_sweep_and_a_new_acquisition(self):
        """Class: the old owner's `checkout` exit is paused by `checks.forget_after_remove` (after its directory
        removal, before its lock unlink); sweep reports N busy and a new acquisition of N fails its `O_EXCL` and
        retries another name; after the old owner finishes (unlink, then close) N is absent (R-K/A-W; depends on the
        unlink-before-close order, s1b1b1r mutation z3). Domain: the old owner in a child process, the sweep and the
        new acquisition in the test. Oracle: the sweep counts, the new owner's pair and the freed name."""
        self.work.mkdir()
        proceed, marker, resume, found_file = (self.base / n for n in ("proceed", "paused", "resume", "found"))
        owner = self.spawn([sys.executable, "-c", OWNER, self.project, self.commit, self.tree, str(self.work),
                            str(found_file), str(proceed), str(marker), str(resume)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        self.addCleanup(self.stop, owner)
        self.assertTrue(self.until(found_file.exists), "the old owner never leased")
        name = Path(found_file.read_text()).name
        lock = str(self.work / name) + ".lock"
        proceed.write_text("x")
        self.assertTrue(self.until(marker.exists), "the old owner never paused before its lock unlink")
        self.assertTrue(os.path.lexists(lock), "the old owner unlinked its lock before the pause")
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        real_urandom = os.urandom
        pinned = [bytes.fromhex(name[len(checks.PREFIX):])]
        with patch("os.urandom", side_effect=lambda size: pinned.pop(0) if pinned else real_urandom(size)):
            with checks.checkout(self.project, self.commit, self.tree, self.work) as found_b:
                fresh = Path(found_b)
                self.assertNotEqual(fresh.name, name, "the new acquisition took a name the old owner still holds")
                resume.write_text("x")
                self.assertTrue(self.until(lambda: not os.path.lexists(lock)),
                                "the old owner never unlinked its lock")
                self.assertEqual(owner.wait(timeout=3), 0)
                self.assertFalse(os.path.lexists(self.work / name), "the old owner's directory returned")
                self.assertFalse(os.path.lexists(lock), "the old owner's lock stayed")
                self.assertTrue(os.path.isdir(fresh), "the new owner's directory is gone")
                self.assertTrue(os.path.lexists(str(fresh) + ".lock"), "the new owner's lock is gone")
            self.assertEqual(self.entries(), [])

    def test_the_guards_release_pauses_for_sweep_and_a_new_acquisition(self):
        """Class: the guard's R-2 lease cleanup is paused by `check_guard.release_after_remove` (after its directory
        removal, before its lock unlink); sweep reports N busy and a new acquisition of N retries another name; after
        the guard resumes, N is absent (R-K/A-W; the same unlink-before-close dependency). Domain: the guard run alone
        against a manual lease, its peer closed to trigger R-2, the seam replaced in a wrapper. Oracle: busy while the
        guard holds, the new owner's pair and the freed name."""
        self.work.mkdir()
        name = checks.PREFIX + "ab" * 8
        directory = self.work / name
        directory.mkdir()
        (directory / "file.txt").write_text("x")
        lock = str(directory) + ".lock"
        opened = [os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)]
        fcntl.flock(opened[0], fcntl.LOCK_EX)

        def close_holder():
            if opened[0] is not None:
                os.close(opened[0])
                opened[0] = None
        self.addCleanup(close_holder)
        marker, resume = self.base / "gpaused", self.base / "gresume"
        wrapper = self.base / "guard_pause.py"
        wrapper.write_text(PAUSE_HOOK % (GUARD_DIR, str(marker), str(resume)))
        lifeline, peer = socket.socketpair()
        try:
            guard = self.spawn([sys.executable, "-I", str(wrapper), "--lifeline", str(lifeline.fileno()),
                                "--lease", str(directory), "--lock-fd", str(opened[0]), "--",
                                sys.executable, "-c", "import time; time.sleep(30)"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               pass_fds=(lifeline.fileno(), opened[0]))
        finally:
            lifeline.close()
            close_holder()  # the guard's inherited copy is the only holder now
        self.addCleanup(self.stop, guard)
        peer.close()  # the peer is gone: the guard's R-2 release runs
        self.assertTrue(self.until(marker.exists), "the guard never paused before its lock unlink")
        self.assertFalse(os.path.lexists(directory), "the guard removed no directory before the pause")
        self.assertTrue(os.path.lexists(lock), "the guard unlinked its lock before the pause")
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        real_urandom = os.urandom
        pinned = [bytes.fromhex("ab" * 8)]
        with patch("os.urandom", side_effect=lambda size: pinned.pop(0) if pinned else real_urandom(size)):
            with checks.checkout(self.project, self.commit, self.tree, self.work) as found_b:
                fresh = Path(found_b)
                self.assertNotEqual(fresh.name, name, "the new acquisition took a name the guard still holds")
                resume.write_text("x")
                self.assertEqual(guard.wait(timeout=3), 0)
                self.assertFalse(os.path.lexists(directory), "the guard's directory returned")
                self.assertFalse(os.path.lexists(lock), "the guard's lock stayed")
                self.assertTrue(os.path.lexists(str(fresh) + ".lock"))
            self.assertEqual(self.entries(), [])

    def test_a_hard_kill_of_zplan_leaves_nothing_for_a_sweep(self):
        """Class: after an s1b1b1r A-H/H-1 kill the guard removes the leased checkout, so no `checkout-*` entry
        exists and `sweep(root)` returns zeros (A-X; the guard's own R-2 cleanup, not a sweep, removed it). Domain: a
        controller that runs `qualify` with a running check, SIGKILLed. Oracle: the empty root and the sweep
        counts."""
        handshake = self.base / "handshake.txt"
        code = ("import os, pathlib, sys, time\n"
                "pathlib.Path(%r).write_text('%%d %%d' %% (os.getpid(), os.getppid()))\n"
                "time.sleep(30)\n") % (str(handshake),)
        controller = self.controller(QUALIFY, code, self.project, self.commit, self.tree, self.work)
        self.assertTrue(self.until(handshake.exists), "the handshake never appeared")
        group, guard = self.pids(handshake)
        controller.kill()
        self.assertEqual(controller.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(self.until(lambda: self.group_gone(group)), "group C %d still runs" % group)
        self.assertTrue(self.until(lambda: not self.alive(guard)), "the guard %d still runs" % guard)
        self.assertTrue(self.until(lambda: self.checkouts() == []), "a checkout entry survived")
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})

    def test_a_sweep_reports_each_unconfirmed_holds_lease_busy_then_removes_it(self):
        """Class: for each s1b1b1r A-C hold (1: the guard held in `after_spawn`; 2: `X 0` received, then the guard
        held in `after_report`) a sweep while the guard holds the transferred lease is one busy; the unconfirmed stop
        left the pair on disk and the guard exits without removing it (the queued `D` is a normal end, so R-2 never
        releases), so the next sweep removes the freed pair, a third returns zeros and no `checkout-*` entry remains
        (A-X). Domain: a leased checkout whose check outlives the stop, twice. Oracle: the sweep counts and the
        listing, the guard's exit observed by `waitid(WNOWAIT)` only."""
        cases = [("after_spawn", self.check("slow", "import time; time.sleep(30)", timeout_s=1)),
                 ("after_report", self.check("quick", "print('done')"))]
        for seam, check in cases:
            with self.subTest(seam=seam):
                hook = self.hook(seam)
                with patch.object(checks, "REAP", 0.5), patch.object(checks, "GUARD", hook):
                    with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
                        lock = str(Path(found).resolve()) + ".lock"
                        self.assertEqual(checks.run_check(check, found, export.environment())["status"], "timeout")
                        guard_process = checks.ORPHANS[0]
                        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
                        self.assertTrue(self.holds(lock), "the guard stopped holding the lease while it lived")
                self.assertTrue(self.until(lambda: self.exited(guard_process.pid)), "the guard never exited")
                self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
                self.assertEqual(self.checkouts(), [])
                self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})
                checks.run_check(self.check("ok", "print('done')"), self.project, export.environment())

    def test_a_lease_held_by_a_surviving_group_c_stays_busy_until_it_is_gone(self):
        """Class: group C inherits the lease lock (M-5), so a sweep while the guard is gone but group C still runs is
        one busy; after group C is killed the lock is free and the sweep removes the pair (A-S state: a leftover held
        by an orphan of group C after the guard exited). Domain: a manual lease, the guard SIGKILLed while the check
        sleeps. Oracle: the sweep counts, the held lock and the removal."""
        self.work.mkdir()
        directory = self.work / (checks.PREFIX + "gc")
        directory.mkdir()
        (directory / "file.txt").write_text("x")
        lock = str(directory) + ".lock"
        opened = [os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)]
        fcntl.flock(opened[0], fcntl.LOCK_EX)

        def close_holder():
            if opened[0] is not None:
                os.close(opened[0])
                opened[0] = None
        self.addCleanup(close_holder)
        handshake = self.base / "gc.pid"
        code = ("import os, pathlib, time\npathlib.Path(%r).write_text(str(os.getpid()))\ntime.sleep(30)\n"
                % (str(handshake),))
        lifeline, peer = socket.socketpair()
        try:
            guard = self.spawn([sys.executable, "-I", GUARD, "--lifeline", str(lifeline.fileno()),
                                "--lease", str(directory), "--lock-fd", str(opened[0]), "--",
                                sys.executable, "-c", code],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               pass_fds=(lifeline.fileno(), opened[0]))
        finally:
            lifeline.close()
            close_holder()
        self.addCleanup(self.stop, guard)
        self.assertTrue(self.until(handshake.exists), "the check never started")
        group = int(handshake.read_text())
        self.addCleanup(self.kill_group, group)
        guard.kill()
        self.assertEqual(guard.wait(timeout=3), -signal.SIGKILL)
        self.assertTrue(self.alive(group), "group C %d exited with the guard" % group)
        self.assertTrue(self.holds(lock), "group C did not keep the inherited lease lock")
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        os.killpg(group, signal.SIGKILL)
        self.assertTrue(self.until(lambda: not self.holds(lock)), "the lock stayed held after group C died")
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertEqual(self.entries(), [])
        peer.close()

    def test_a_lock_published_after_a_lockless_classification_is_busy(self):
        """Class: an entry classified lockless whose lock another actor publishes before the removal must not lose
        that lock -- the sidecar path is never unlinked without the owner's lock (R-W/R-4; the reviewer's live
        publication deletion). Domain: one lockless leftover `N`, whose `lstat` is answered from before an
        interleaving that clears it and enters a new checkout B under the same pinned name; no sleeps, no production
        helper in the oracle. Oracle: the counts, B's pair and a test-side `LOCK_NB` on B's lock.
        Interpretation: `sweep`'s classification is stale by construction (it reads, then acts), so a name that has a
        lock again at the moment of use is the case the publication rule must survive."""
        self.work.mkdir()
        stem = bytes.fromhex("ab" * 8)
        entry = self.work / (checks.PREFIX + stem.hex())
        entry.mkdir()
        lock = str(entry) + ".lock"
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        real, fired = os.lstat, [False]

        def lstat(path, *arguments, **options):
            if str(path) == lock and not fired[0]:
                fired[0] = True
                try:
                    real(path, *arguments, **options)  # the read the classification is about to trust: absent
                except OSError:
                    pass
                self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})  # the old leftover goes
                with patch("os.urandom", return_value=stem):
                    stack.enter_context(checks.checkout(self.project, self.commit, self.tree, self.work))
                self.assertTrue(self.holds(lock), "B did not publish a held lock under the old name")
                raise FileNotFoundError(errno.ENOENT, "stale read", str(path))
            return real(path, *arguments, **options)

        with patch("os.lstat", lstat):
            self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        self.assertTrue(os.path.isdir(entry), "sweep removed the newly published live checkout")
        self.assertTrue(os.path.lexists(lock), "sweep unlinked the newly published live lock")
        self.assertTrue(self.holds(lock), "the surviving lock is not the live one")
        stack.close()
        self.assertEqual(self.entries(), [])

    def test_a_busy_lock_named_entry_survives_its_bases_sweep(self):
        """Class: a `.lock`-named entry whose own lock is held is one busy, and processing its base afterwards must
        not clear it -- a busy name is not the base's to unlink (R-W/R-4; the reviewer's dangling `checkout-x.lock`
        held through `checkout-x.lock.lock`). Domain: `checkout-x` directory, a dangling `checkout-x.lock` link and a
        held `checkout-x.lock.lock`. Oracle: both counts, the `lexists` of every path and the empty root once the
        holder exits.
        Interpretation: an R-4 row-2 `.lock` link is an entry of its own, so the base's own unit is one busy while
        that entry cannot be removed."""
        self.work.mkdir()
        entry = self.work / "checkout-x"
        entry.mkdir()
        link = self.work / "checkout-x.lock"
        link.symlink_to(self.work / "missing")
        held = self.work / "checkout-x.lock.lock"
        holder = self.holder(held)
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 2})
        self.assertTrue(os.path.lexists(link), "a busy `.lock`-named entry was cleared by its base")
        self.assertTrue(os.path.lexists(held), "the held lock of a busy entry was removed")
        self.assertTrue(os.path.lexists(entry), "the base of a busy pair was removed")
        self.stop(holder)
        self.assertTrue(self.until(lambda: not self.holds(held)), "the holder never let the lock go")
        self.assertEqual(checks.sweep(self.work), {"removed": 2, "busy": 0})
        self.assertEqual(self.entries(), [])

    def test_a_classification_error_on_a_live_lock_is_busy(self):
        """Class: a `lstat` that fails with anything but "no such name" is an unknown type, never "not a lock": the
        unit is one busy and nothing of it is removed (R-V/R-W; the verifier's `EIO` on a live lock). Domain: a live
        checkout with one injected `EIO` on the `lstat` of its lock during classification. Oracle: the counts and the
        `lexists` of both live paths, with `os.lstat` itself the only injection point."""
        with checks.checkout(self.project, self.commit, self.tree, self.work) as found:
            lock = str(Path(found).resolve()) + ".lock"
            real, fired = os.lstat, [False]

            def lstat(path, *arguments, **options):
                if str(path) == lock and not fired[0]:
                    fired[0] = True
                    raise OSError(errno.EIO, "injected classification error")
                return real(path, *arguments, **options)

            with patch("os.lstat", lstat):
                self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
            self.assertTrue(os.path.lexists(found), "a live directory was removed after a classification error")
            self.assertTrue(os.path.lexists(lock), "a live lock was removed after a classification error")
            self.assertTrue(self.holds(lock), "the live lock was replaced after a classification error")
        self.assertEqual(self.entries(), [])

    def test_a_lockless_sweep_creates_its_own_lock_nonblocking(self):
        """Class: the lockless branch creates its own lock and takes it with `LOCK_EX | LOCK_NB`, never a blocking
        `LOCK_EX` that would wait for another cooperating sweeper holding the new lock (R-W). Domain: one lockless
        `checkout-*` entry with `fcntl.flock` spied. Oracle: the recorded operation, the counts and the empty root."""
        self.work.mkdir()
        (self.work / "checkout-nb").mkdir()
        operations, real = [], fcntl.flock

        def flock(descriptor, operation):
            operations.append(operation)
            return real(descriptor, operation)

        with patch("fcntl.flock", flock):
            self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertEqual(operations, [fcntl.LOCK_EX | fcntl.LOCK_NB])
        self.assertEqual(self.entries(), [])

    def test_a_failed_acquisition_never_unlinks_another_publishers_lock(self):
        """Class: an acquisition that fails after its own lock was unlinked closes only its own handle and unlinks
        nothing -- the live lock now at the path belongs to another publisher (R-W/R-K; `_lease`'s failure
        ownership). Domain: `_lease` under the `lease_after_create` seam with a pinned name, where the seam's sweep
        clears the orphan and a checkout publishes that same name, and `fcntl.flock` fails once for the unlinked
        inode. Oracle: the propagated failure and the publisher's intact, still-held pair.
        Interpretation: the seam is the only interleaving point this split exposes between the create and the flock,
        so the failure ownership of a half-published attempt is pinned there."""
        self.work.mkdir()
        stem = bytes.fromhex("cd" * 8)
        directory = self.work / (checks.PREFIX + stem.hex())
        lock = str(directory) + ".lock"
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        real_hook, real_flock = checks.lease_after_create, fcntl.flock

        def after_create():
            checks.lease_after_create = real_hook  # one-shot: only the attempt that fails pauses here
            self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})  # the orphan lock goes
            stack.enter_context(checks.checkout(self.project, self.commit, self.tree, self.work))  # it owns the name

        def flock(descriptor, operation):
            if os.fstat(descriptor).st_nlink == 0:
                raise OSError(errno.EIO, "injected flock failure")
            return real_flock(descriptor, operation)

        with patch.object(checks, "lease_after_create", after_create), patch("os.urandom", return_value=stem), \
                patch("fcntl.flock", flock):
            with self.assertRaises(OSError):
                with checks.checkout(self.project, self.commit, self.tree, self.work):
                    self.fail("the acquisition succeeded although its flock failed")
        self.assertTrue(os.path.isdir(directory), "a failed acquisition removed a publisher's directory")
        self.assertTrue(os.path.lexists(lock), "a failed acquisition unlinked a publisher's live lock")
        self.assertTrue(self.holds(lock), "a publisher's lock is not held any more")
        stack.close()
        self.assertEqual(self.entries(), [])

    def test_a_failure_before_its_flock_never_unlinks_the_lock(self):
        """Class: an acquisition that fails before it ever took its own `flock` closes only its own handle and never
        unlinks the pathname -- a name is a lock only for the holder of `flock` on the inode at it (R-W; the
        reviewers' pre-flock `EIO`). Domain: `_lease` under the `lease_after_create` seam with the name pinned, where
        the seam's cooperating actor opens and flocks the just-created lock before the acquisition's own `flock`
        fails with `EIO`. Oracle: the intact, still-held lock, the busy a sweep reports for it, and a checkout that
        publishes the same name once the actor lets go.
        Interpretation: identity (`fstat`/`lstat`) proves the pathname still names this attempt's inode, not that
        this attempt holds its flock, so a pre-flock failure may only close its own fd (recorded in `_lease`)."""
        self.work.mkdir()
        stem = bytes.fromhex("ef" * 8)
        directory = self.work / (checks.PREFIX + stem.hex())
        lock = str(directory) + ".lock"
        held, state = [], {"fail": False}
        real_hook, real_flock = checks.lease_after_create, fcntl.flock

        def close_holder():
            if held:
                os.close(held.pop())
        self.addCleanup(close_holder)

        def after_create():
            checks.lease_after_create = real_hook  # one-shot: only the acquisition that fails crosses this seam
            fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # a cooperating actor opened this lock and holds it (R-W)
            held.append(fd)
            state["fail"] = True  # ... so the acquisition's own `flock` fails without ever holding it

        def flock(descriptor, operation):
            if state["fail"]:
                state["fail"] = False  # one-shot: the acquisition's own attempt alone
                raise OSError(errno.EIO, "injected flock failure")
            return real_flock(descriptor, operation)

        with patch.object(checks, "lease_after_create", after_create), patch("os.urandom", return_value=stem), \
                patch("fcntl.flock", flock):
            with self.assertRaises(OSError):
                with checks.checkout(self.project, self.commit, self.tree, self.work):
                    self.fail("the acquisition succeeded although its flock failed")
        self.assertTrue(os.path.lexists(lock), "a pre-flock failure unlinked a lock another actor holds")
        self.assertTrue(self.holds(lock), "the lock is no longer held by the actor that took it")
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})  # a held lock is one busy (R-4)
        close_holder()  # the actor lets go: only now may a sweep clear the orphan lock
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        with patch("os.urandom", return_value=stem):
            with checks.checkout(self.project, self.commit, self.tree, self.work) as found:  # the same name again
                self.assertEqual(Path(found).name, directory.name)
                self.assertTrue(self.holds(lock), "the new owner's lock is not held")
                self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 0})
        self.assertEqual(self.entries(), [])

    def test_a_lock_a_sweep_did_not_create_is_never_adopted(self):
        """Class: sweep publishes its own lock with `O_EXCL` and a lost name is one busy -- the name is never adopted
        by reopening it (R-W: "`O_EXCL` failure when sweep creates a lock -> busy"). Domain: a lockless `checkout-*`
        entry whose lock a cooperating actor creates, unheld, while sweep classifies it; the classification's `lstat`
        answers from before that creation. Oracle: the counts, the entry and the foreign lock intact, and that lock
        still unheld after the call.
        Interpretation: the classification is a read taken before the act, so the `O_EXCL` create -- not that read --
        decides; a name another actor created is theirs to hold, unlink and clean up."""
        self.work.mkdir()
        entry = self.work / "checkout-race"
        entry.mkdir()
        lock = str(entry) + ".lock"
        real, fired = os.lstat, [False]

        def lstat(path, *arguments, **options):
            if str(path) == lock and not fired[0]:
                fired[0] = True
                try:
                    real(path, *arguments, **options)  # the read the classification is about to trust: absent
                except OSError:
                    pass
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600))
                raise FileNotFoundError(errno.ENOENT, "stale read", str(path))
            return real(path, *arguments, **options)

        with patch("os.lstat", lstat):
            self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        self.assertTrue(os.path.isdir(entry), "the entry of a lock sweep did not create was removed")
        self.assertTrue(os.path.lexists(lock), "the lock of another actor was removed")
        self.assertFalse(self.holds(lock), "the lock of another actor is held")
        self.assertEqual(self.entries(), ["checkout-race", "checkout-race.lock"])

    def test_a_held_lock_orphaned_by_its_bases_unit_is_busy(self):
        """Class: a `.lock` name left behind when a unit clears its base is an orphan lock of its own and is counted;
        held, it is one busy (R-4: a `.lock` regular file belongs to the entry named without `.lock` if that name
        exists, else it is an orphan lock). Domain: a `checkout-x` directory, a regular `checkout-x.lock`, and a
        `checkout-x.lock.lock` held by a child through an inherited descriptor. Oracle: the counts, the `lexists` of
        each path, and the empty root once the holder exits.
        Interpretation: the classification snapshot is taken before the removals, so the skip that treats
        `checkout-x.lock.lock` as the lock of the entry `checkout-x.lock` is revisited once that name is gone; every
        name is still counted once (recorded in `sweep`)."""
        self.work.mkdir()
        entry = self.work / "checkout-x"
        entry.mkdir()
        (self.work / "checkout-x.lock").write_text("")
        nested = self.work / "checkout-x.lock.lock"
        holder = self.holder(nested)
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 1})
        self.assertFalse(os.path.lexists(entry), "the unheld entry survived")
        self.assertFalse(os.path.lexists(str(entry) + ".lock"), "the free lock of the entry survived")
        self.assertTrue(os.path.lexists(nested), "the held lock of the orphaned name was removed")
        self.stop(holder)
        self.assertTrue(self.until(lambda: not self.holds(nested)), "the holder never let the lock go")
        self.assertEqual(checks.sweep(self.work), {"removed": 1, "busy": 0})
        self.assertEqual(self.entries(), [])

    def test_sweep_holds_every_opened_lock_in_an_owning_handle(self):
        """Class: every descriptor `sweep` opens is held by one owning `_Lock` file object, never a raw integer
        carried around (R-D; the reviewer's bare-integer finding). Domain: one sweep reaping a lockless entry, an
        entry with a free lock and an orphan lock (success), then a sweep whose only unit cannot be removed from a
        root the caller made read-only (error cleanup). All entries are regular files (R-4 row 4), so the only
        `os.open` calls in the domain are sweep's own locks. Oracle: the counts, every opened descriptor wrapped by
        `os.fdopen`, none closed through the raw `os.close`, and every one released afterwards.
        Interpretation: R-D's raw-integer exception ("an `int` closed in exactly one place right after the spawn
        that transferred it") never covers `_sweep_one`, which transfers no descriptor, so the owner must be an
        object and its `fileno` is only borrowed for the `flock` and the identity check (recorded in `_sweep_one`)."""
        self.work.mkdir()
        (self.work / "checkout-a").write_text("")  # a lockless entry: sweep publishes and owns its own lock
        (self.work / "checkout-b").write_text("")  # an entry with a free lock: sweep opens and owns that lock
        (self.work / "checkout-b.lock").write_text("")
        (self.work / "checkout-c.lock").write_text("")  # an orphan lock: sweep opens and owns it too

        def watch():
            opened, wrapped, closed = [], [], []
            real_open, real_fdopen, real_close = os.open, os.fdopen, os.close

            def opener(*arguments, **options):
                number = real_open(*arguments, **options)
                opened.append(number)
                return number

            def fdopener(descriptor, *arguments, **options):
                wrapped.append(descriptor)
                return real_fdopen(descriptor, *arguments, **options)

            def closer(descriptor, *arguments, **options):
                closed.append(descriptor)
                return real_close(descriptor, *arguments, **options)

            return opened, wrapped, closed, (patch("os.open", opener), patch("os.fdopen", fdopener),
                                             patch("os.close", closer))

        opened, wrapped, closed, patches = watch()
        with patches[0], patches[1], patches[2]:
            self.assertEqual(checks.sweep(self.work), {"removed": 3, "busy": 0})
        self.assertEqual(len(opened), 3, "sweep did not open one lock per unit")
        self.assertEqual(sorted(wrapped), sorted(opened), "a sweep descriptor is not wrapped by an owning object")
        self.assertEqual(closed, [], "sweep closed a descriptor through the raw os.close")
        for number in opened:  # the owners released every descriptor whatever the outcome
            with self.assertRaises(OSError):
                os.fstat(number)
        self.assertEqual(self.entries(), [])

        (self.work / "checkout-d").write_text("")  # a removal that fails still closes its owner (the error path)
        (self.work / "checkout-d.lock").write_text("")
        self.addCleanup(os.chmod, str(self.work), 0o700)
        os.chmod(str(self.work), 0o500)  # the unlink of the entry has nowhere to write its parent
        opened, wrapped, closed, patches = watch()
        with patches[0], patches[1], patches[2]:
            self.assertEqual(checks.sweep(self.work), {"removed": 0, "busy": 1})
        os.chmod(str(self.work), 0o700)
        self.assertEqual(len(opened), 1, "the failing unit did not open its one lock")
        self.assertEqual(wrapped, opened, "the failing unit's descriptor is not wrapped by an owning object")
        self.assertEqual(closed, [], "the failing unit closed its descriptor through the raw os.close")
        for number in opened:
            with self.assertRaises(OSError):
                os.fstat(number)
        self.assertTrue(os.path.lexists(str(self.work / "checkout-d")), "the failed removal still removed the entry")
        self.assertTrue(os.path.lexists(str(self.work / "checkout-d.lock")), "the failing unit lost its lock")
