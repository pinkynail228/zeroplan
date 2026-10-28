#!/usr/bin/env python3
"""Fixture-only UX walkthrough of the full-screen zplan under a real PTY, rendered with pyte.

A development tool, not part of the unit suite. It drives the checkout (the repository root is taken from this
file's path, `python -m terminal_planner.cli` runs with PYTHONPATH set to it) or, with `--installed`, the package
installed in the `--python` interpreter, on a throw-away Git project with the deterministic fixture engine and
driver: no provider, no network, no Zeroshot. It writes the screen after every step to FRAMES_DIR and exits nonzero
on the first missed expectation or timeout.

    python devtools/ux_walkthrough.py FRAMES_DIR --python /path/to/interpreter/with/textual
    python devtools/ux_walkthrough.py FRAMES_DIR --python /path/to/installed/bin/python --installed

`--installed` is the release gate's candidate proof (docs/RELEASE_0.4.md, step 5): the child runs with `-I` (an
isolated interpreter) and no PYTHONPATH, and before the first frame a probe in the same interpreter proves that
`terminal_planner` and `terminal_planner.cli` really live in its own purelib/platlib — it refuses the checkout, a
symlink into it and an editable/.pth install of another tree, and writes the resolved paths to
FRAMES_DIR/installed.txt. Without `--installed` nothing changes: the child runs the checkout.

Every run first empties FRAMES_DIR of the previous run's outputs — numbered frames, installed.txt and INDEX.md —
so a reused directory never keeps a stale index (possibly a passing one) next to the new frame set; other files
there are left alone.

pyte must be importable by the interpreter that runs THIS script (a venv with `pip install pyte`); the interpreter
passed with --python is the one zplan itself runs under (it needs Textual). The walkthrough is the live proof of the
U5 items: the live run panel, the journal, the activity tail, pending feedback, "Next:", readiness, key bars,
wording."""

import argparse
import fcntl
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import terminal_planner  # noqa: E402
from terminal_planner import catalog  # noqa: E402

# The task's items 1-8 and the frames (by name, without the number) that show them.
ITEMS = (
    ("1 live panel: roles, time, last event, checked", ("m1-running", "m1-start-answered")),
    ("2 attempt journal; no stale «The planner finished» on the left", ("m1-running", "m1-journal")),
    ("3 the Zeroshot log tail on request", ("m1-activity-tail",)),
    ("4 immediate feedback (pending)", ("m1-pending", "m2-stopping")),
    ("5 the «Next:» line on the home screen", ("home-first-start", "home-ready", "m1-done-home",
                                            "home-after-merge", "m2-stopped", "m2-stopped-end")),
    ("6 readiness: the check name, a stale plan against a fixed tree",
     ("blocked-dirty-tree", "blocked-gone", "stale-baseline-stays")),
    ("7 key bar, focus, help", ("help-home", "start-confirm", "small-home", "small-plan", "small-help")),
    ("8 texts: wrap indent, confirmations, forms, [i], Esc",
     ("m1-running", "merge-confirm", "new-attempt-form", "small-attempt-form", "proposal", "proposal-info",
      "proposal-info-closed", "approve-confirm", "after-esc", "settings-empty-log")),
)

GOAL = "Add a README paragraph about installation"

# R-3: an end-of-run modal carries a "Next:" line of its own and closes with its own [esc] close; no other
# screen the walkthrough meets has both. Used to let the modal that opens over home be closed before home is read.
END_MODAL = ("Next:", "[esc] close")


class Missed(Exception):
    pass


class Refused(Exception):
    """Installed mode refused the interpreter: its zplan is not the package installed in it."""


# The installed-mode probe: the interpreter's own terminal_planner, its cli module and the library paths, or a
# refusal. It writes FRAMES_DIR (sys.argv[1]) /installed.txt only after the check passed, so a refusal leaves no frame.
PROBE = r'''\
import pathlib, sys, sysconfig

import terminal_planner
import terminal_planner.cli

libs = [pathlib.Path(p).resolve() for p in (sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"])]
files = [pathlib.Path(f).resolve() for f in (terminal_planner.__file__, terminal_planner.cli.__file__)]
outside = [str(f) for f in files if not any(f == l or l in f.parents for l in libs)]
if outside:
    sys.exit("not installed in this interpreter: " + ", ".join(outside))
frames = pathlib.Path(sys.argv[1])
(frames / "installed.txt").write_text(
    "terminal_planner.__file__ = %s\nterminal_planner.__version__ = %s\n" % (files[0], terminal_planner.__version__))
for key, value in (("file", files[0]), ("version", terminal_planner.__version__), ("cli_file", files[1]),
                   ("purelib", libs[0]), ("platlib", libs[1])):
    print("%s=%s" % (key, value))
'''


def child_env(installed, base=None):
    """Environment of the zplan child: TERM and, unless installed, ROOT on PYTHONPATH (installed drops it)."""
    env = dict(os.environ if base is None else base)
    env["TERM"] = "xterm-256color"
    if installed:
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = str(ROOT)
    return env


def child_argv(python, tail, installed):
    """argv of the zplan child: an isolated interpreter (`-I`) in installed mode, the plain one otherwise."""
    return [str(python)] + (["-I"] if installed else []) + [str(part) for part in tail]


def child_command(python, cwd, tail, installed, base_env=None):
    """(argv, env, cwd) of the zplan child: the one builder the probe and every PTY launch come from."""
    return child_argv(python, tail, installed), child_env(installed, base_env), Path(cwd)


def zplan_command(python, project, state, installed, base_env=None):
    """The PTY launch: the fixture zplan on the throw-away project, in the checkout or in the installed package."""
    tail = ["-m", "terminal_planner.cli", "--project", str(project), "--state-dir", str(state), "--fixture", "smoke"]
    return child_command(python, project, tail, installed, base_env)


def probe_command(python, project, frames, base_env=None):
    """The probe child: the same interpreter, flags, env and cwd as the launched zplan, with a `-c` tail.

    The frame directory is resolved here: the child runs in the throw-away project, not in this script's cwd.
    """
    return child_command(python, project, ["-c", PROBE, str(Path(frames).resolve())], True, base_env)


def probe_installed(python, project, frames, base_env=None):
    """Prove that `python` runs its own installed terminal_planner, not the checkout; refuse it otherwise.

    Returns (version, file); a version different from the checkout's is a warning, not a failure: the candidate and
    the checkout must be the same commit, and equal versions do not prove it (the release receipt binds the wheel).
    """
    frames = Path(frames)
    (frames / "installed.txt").unlink(missing_ok=True)  # a refusal must leave the frame directory without a receipt
    argv, env, cwd = probe_command(python, project, frames, base_env)
    done = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise Refused("installed mode refused %s (exit %d): %s" % (python, done.returncode, done.stderr.strip()))
    values = dict(line.split("=", 1) for line in done.stdout.splitlines() if "=" in line)
    print(done.stdout.strip(), flush=True)
    if values.get("version") != terminal_planner.__version__:
        print("warning: installed terminal_planner %s differs from the checkout %s: the release candidate and the "
              "checkout must be the same commit" % (values.get("version"), terminal_planner.__version__), flush=True)
    return values.get("version"), values.get("file")


def known_item(key, label):
    """True when `label` is, whole, a label or short label of a catalog action that has `key`."""
    for a in catalog.ACTIONS.values():
        if key not in (a.key,) + tuple(a.alt):
            continue
        for text in (a.label, a.short, ""):
            if label == text or ("%s" in text and re.fullmatch(re.escape(text).replace("%s", ".+"), label)):
                return True
    return False


def bar_items(line):
    return [(m.group(1), (m.group(2) or "").strip())
            for m in re.finditer(r"\[([^\]]+)\](?: ([^\[]*?))?(?=\s{2,}\[|\s*$)", line)]


def clear_frames(frames):
    """Remove the previous run's outputs from FRAMES_DIR: numbered frames, the probe receipt and INDEX.md.

    The one place the run purges its own outputs, called by the `Walk` constructor before the probe and the
    first frame: a refused or crashed run writes no new INDEX.md, so a stale one must not survive next to an
    empty frame set. Files the walkthrough does not write are left alone.
    """
    frames = Path(frames)
    for old in list(frames.glob("[0-9][0-9]-*.txt")) + [frames / "installed.txt", frames / "INDEX.md"]:
        old.unlink(missing_ok=True)


class Walk:
    def __init__(self, frames, python, deadline, installed=False):
        self.frames, self.python, self.deadline = Path(frames), python, time.monotonic() + deadline
        self.installed = installed
        self.frames.mkdir(parents=True, exist_ok=True)
        clear_frames(self.frames)
        self.index, self.term, self.base = [], None, Path(tempfile.mkdtemp(prefix="zplan-walk-"))
        self.project, self.state = self.base / "proj", self.base / "state"
        self.make_project()

    # Project -------------------------------------------------------------------------------------------

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.project), *args], check=True, capture_output=True)

    def make_project(self):
        self.project.mkdir()
        self.state.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.project / "README.md").write_text("hi\n")
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.git("remote", "add", "origin", "https://github.com/example/smoke.git")

    # Terminal ------------------------------------------------------------------------------------------

    def child(self):
        """(argv, env, cwd) of the zplan child: the one builder the installed-mode probe also uses."""
        return zplan_command(self.python, self.project, self.state, self.installed)

    def open(self, cols=120, rows=40):
        argv, env, cwd = self.child()
        self.cols, self.rows = cols, rows
        import pyte  # only the renderer needs it: importing this module must not require pyte
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.chdir(cwd)
            os.execvpe(argv[0], argv, env)
        self.alive, self.began = True, time.monotonic()

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ready, _, _ = select.select([self.fd], [], [], 0.03)
            if ready:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    self.alive = False
                    return
                if not data:
                    self.alive = False
                    return
                self.stream.feed(data)

    def text(self):
        return "\n".join(line.rstrip() for line in self.screen.display)

    def has(self, *needles):
        text = self.text()
        return all(n in text for n in needles)

    def expect(self, *needles, within=30, settle=0.4):
        """Wait until every needle is on the screen (a missed expectation ends the walkthrough)."""
        end = min(time.monotonic() + within, self.deadline)
        while time.monotonic() < end:
            self.pump(0.1)
            if self.has(*needles):
                self.pump(settle)
                return
            if not self.alive:
                break
        self.snap("MISSED", "expected %r" % (needles,))
        raise Missed("did not see %r\n%s" % (needles, self.text()))

    def expect_home(self, *needles, within=180):
        """Wait for a home line, tolerating the end-of-run modal that may open over home.

        A run that finishes while home is on top opens its own end-of-run modal over it (`MainScreen.show_end`),
        and home is then not rendered at all, so the line is unreachable until the modal is closed. Either order
        is allowed — the modal is the finished run's own result, not a wrong screen. The modal is captured as a
        frame and closed with its own [esc] close; the same expectation is then read again on home."""
        end = min(time.monotonic() + within, self.deadline)
        seen = False
        while time.monotonic() < end:
            self.pump(0.1)
            if self.has(*needles):
                self.pump(0.4)
                return
            if self.has(*END_MODAL) and not self.has(*needles):
                if not seen:
                    seen = True
                    self.snap("run-end-modal", "the finished run opened its modal over home (allowed order)")
                self.key(b"\x1b", 1.0)  # its own close key: home is behind it
                continue
            if not self.alive:
                break
        self.snap("MISSED", "expected %r" % (needles,))
        raise Missed("did not see %r\n%s" % (needles, self.text()))

    def expect_gone(self, needle, within=30):
        end = min(time.monotonic() + within, self.deadline)
        while time.monotonic() < end:
            self.pump(0.1)
            if not self.has(needle):
                return
        self.snap("MISSED", "still shown %r" % needle)
        raise Missed("still shown: %r\n%s" % (needle, self.text()))

    def absent(self, needle):
        if self.has(needle):
            self.snap("MISSED", "must not show %r" % needle)
            raise Missed("must not be shown: %r\n%s" % (needle, self.text()))

    def key(self, keys, pause=0.6):
        os.write(self.fd, keys.encode() if isinstance(keys, str) else keys)
        self.pump(pause)

    def snap(self, name, description):
        number = len(self.index) + 1
        name = "%02d-%s.txt" % (number, name)
        elapsed = time.monotonic() - self.began
        (self.frames / name).write_text("# %s | %dx%d | t+%.1fs\n%s\n" % (
            description, self.cols, self.rows, elapsed, self.text()))
        self.index.append((name, description))
        print("frame", name, flush=True)

    def bar_whole(self, where):
        """The key bar (last non-empty line) holds only whole catalog labels: no word is cut."""
        lines = [l for l in self.text().splitlines() if l.strip()]
        line = lines[-1]
        items = bar_items(line)
        bad = [(k, l) for k, l in items if not known_item(k, l)]
        if not items or bad:
            self.snap("MISSED", "key bar at %s" % where)
            raise Missed("key bar %s: %r (%r)" % (where, line, bad))

    def quit(self):
        """ctrl+q: the run keeps going, zplan leaves."""
        self.key(b"\x11", 1.5)
        for _ in range(40):
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                return
            self.pump(0.25)
        os.kill(self.pid, 9)
        os.waitpid(self.pid, 0)
        raise Missed("zplan did not exit on ctrl+q")

    def finish(self, ok, index=True):
        """Always remove the throw-away project; a refused installed run (`index=False`) writes no INDEX.md."""
        shutil.rmtree(self.base, ignore_errors=True)
        if not index:
            return
        with open(self.frames / "INDEX.md", "w") as handle:
            handle.write("# zplan TUI walkthrough (fixture engine and driver)\n\n")
            for name, description in self.index:
                handle.write("- `%s` — %s\n" % (name, description))
            handle.write("\n## By task item\n\n")
            for title, names in ITEMS:
                files = [n for n, _ in self.index if n.split("-", 1)[1].rsplit(".", 1)[0] in names]
                handle.write("- item %s: %s\n" % (title, ", ".join("`%s`" % f for f in files) or "no frames"))
            handle.write("\n%s\n" % ("OK" if ok else "FAILED"))

    # Journey -------------------------------------------------------------------------------------------

    def run(self):
        if self.installed:
            probe_installed(self.python, self.project, self.frames)
        self.open(120, 40)
        self.expect("Project process profile", "[l] later", within=30)  # the first-start profile choice
        self.snap("bootstrap-first-start", "first start: the process profile choice (accept / later)")
        self.bar_whole("bootstrap")
        self.key("l", 1.0)  # later: nothing is written to the project
        self.expect("proj ·", "profile not saved", within=30)
        self.pump(1.5)
        self.snap("home-first-start", "first start: home, no plan; the next step is named")
        self.expect("Next: [p] plan")
        self.key("?", 1)
        self.expect("Keys")
        self.snap("help-home", "[?] from home (the key bar of the help stays visible)")
        self.bar_whole("help")
        self.key(b"\x1b", 0.6)
        self.key(b"\x1b[11~", 0.1)  # F1 from the same place: the same help
        self.expect("Keys")
        self.key(b"\x1b", 0.6)
        self.key("s", 1.2)
        self.expect("The install log is empty so far")
        self.snap("settings-empty-log", "settings: the empty log says what to press")
        self.key(b"\x1b", 0.8)

        (self.project / "README.md").write_text("hi\ndirty\n")  # a dirty tree blocks the planner start
        self.key("p", 1.0)
        self.expect("New plan")
        self.key(GOAL.encode(), 0.8)
        self.key(b"\x07", 0.3)  # ctrl+g
        self.expect("Not started: fix what is marked above first.")
        self.snap("blocked-dirty-tree", "plan screen: start refused, the marked items are listed with the message")
        self.git("checkout", "README.md")  # fixed outside: the screen looks again by itself
        self.expect_gone("Not started", within=40)
        self.snap("blocked-gone", "the message went away by itself after the tree was fixed")
        self.expect("[n] new revision", within=20)  # the real stale baseline stays, with [n]
        self.snap("stale-baseline-stays", "a real stale baseline stays, with [n] new revision")
        self.key("n", 1.2)
        self.key("g", 0.3)  # the prepared revision goes to the planner
        self.expect("milestone", within=60)
        self.absent("The planner finished")
        self.snap("proposal", "proposal view: no repeated 'The planner finished'")
        self.key("i", 1.0)
        self.snap("proposal-info", "[i] opens the details")
        self.key("i", 1.0)
        self.snap("proposal-info-closed", "[i] again closes them")
        self.key("a", 1.0)
        self.expect("Approve plan")
        self.expect("Plan r")  # the confirmation does not cover the plan text
        self.snap("approve-confirm", "[a] confirmation leaves the plan text visible")
        self.key("y", 0.5)
        self.expect("approved", within=20)
        self.pump(1.0)
        self.snap("approved", "approved: the plan screen")
        self.key(b"\x1b", 1.0)  # one level: an open note first, then the screen
        if self.has("[esc] back"):
            self.snap("after-esc", "Esc from the approved plan screen closes the note, the screen stays")
            self.key(b"\x1b", 1.0)
        self.expect("Next: [g] start M1")
        self.snap("home-ready", "home with an approved plan: the next step is [g] start M1")
        self.bar_whole("home 120x40")

        self.key("g", 1.0)
        self.expect("Start M1")
        self.bar_whole("start confirmation 120x40")
        self.snap("start-confirm", "[g] start confirmation: its own key bar")
        self.key("y", 0.0)
        end = time.monotonic() + 3
        while time.monotonic() < end and not self.has("starting M1…"):
            self.pump(0.02)
        self.absent_or_snap_pending()
        self.expect("Working now:", "last event", "checked", within=60)
        self.snap("m1-running", "M1 running: active role, elapsed, last event age, heartbeat time")
        self.expect("running", "Run M1")
        self.absent("The planner finished")  # item 2: the planner's finish is not left over the run
        self.bar_whole("running 120x40")
        self.key("i", 1.2)
        self.expect("Journal M1 (attempt 1):")
        self.snap("m1-journal", "[i] details: the bounded journal of the attempt")
        self.key(b"\x1b", 0.8)
        self.key("e", 1.5)
        self.expect("fixture log")
        self.snap("m1-activity-tail", "[e] the activity tail of the Zeroshot log, on request")
        self.key(b"\x1b", 0.8)

        self.expect_home("Next: [o] open M1", within=180)
        self.snap("m1-done-home", "M1 finished: home names the next step, the named key works from home")
        self.key("o", 1.2)
        self.expect("[m] merge")
        self.snap("m1-done", "M1 end screen: the actions behind the next step")
        self.key("m", 1.2)
        self.expect("Merge the result of M1 into main?")
        self.absent("zplan/")
        self.snap("merge-confirm", "[m] merge confirmation names the result, not the branch")
        self.key("y", 0.5)
        self.expect("merged", within=60)
        self.key(b"\x1b", 1.2)
        self.expect_home("Next: [g] start M2")
        self.snap("home-after-merge", "home after the merge: [g] start M2")
        self.key("g", 1.0)
        self.expect("Start M2")
        self.key("y", 0.2)
        self.expect("Working now:", within=60)
        self.key("x", 1.0)
        self.expect("Stop")
        self.key("y", 0.0)
        end = time.monotonic() + 3
        while time.monotonic() < end and not (self.has("stopping M2…") or self.has("Stop requested")):
            self.pump(0.02)
        self.snap("m2-stopping", "stop confirmed: the pending line, no second stop")
        self.expect("stopped", "[n] new attempt", within=60)  # the end screen opens by itself
        self.snap("m2-stopped-end", "stopped: the end screen offers the new attempt")
        self.key(b"\x1b", 1.0)
        self.expect_home("Next: [g] new attempt M2", within=30)
        self.snap("m2-stopped", "stopped: home names the new attempt as the next step")
        self.key("g", 1.2)
        self.expect("New attempt M2")
        self.expect("This is a new run of the stage", "[ctrl+g] start attempt")
        self.snap("new-attempt-form", "new attempt: full explanation, labelled field, named confirm key")
        self.key(b"\x1b", 1.0)
        self.quit()

        self.open(80, 24)
        self.expect("proj ·", within=30)
        self.pump(1.5)
        self.snap("small-home", "80x24 home: a primary action is labelled, no word cut")
        self.bar_whole("home 80x24")
        self.key("p", 1.2)
        self.snap("small-plan", "80x24 plan screen")
        self.bar_whole("plan 80x24")
        self.key(b"\x1b", 0.8)
        self.key("g", 1.0)
        self.expect("New attempt M2", "[ctrl+g] start attempt")
        self.snap("small-attempt-form", "80x24 new attempt form: the confirm key is named")
        self.bar_whole("attempt form 80x24")
        self.key(b"\x1b", 0.8)
        self.key("?", 1.0)
        self.expect("Keys")
        self.bar_whole("help 80x24")
        self.snap("small-help", "80x24 help: its key bar is visible")
        self.key(b"\x1b", 0.6)
        self.quit()

    def absent_or_snap_pending(self):
        """The pending line is local and short-lived: keep the frame when the PTY caught it."""
        if self.has("starting M1…"):
            self.snap("m1-pending", "start confirmed: the local pending line until Zeroshot answers")
            return
        self.snap("m1-start-answered", "start confirmed: Zeroshot answered before the next frame")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("frames", help="directory for the frame files (outside the repository)")
    parser.add_argument("--python", default=sys.executable, help="interpreter that runs zplan (needs Textual)")
    parser.add_argument("--installed", action="store_true",
                        help="run the terminal_planner installed in --python, not the checkout")
    parser.add_argument("--timeout", type=float, default=900, help="overall deadline, seconds")
    args = parser.parse_args()
    walk = Walk(args.frames, args.python, args.timeout, args.installed)
    ok, refused = False, False
    try:
        walk.run()
        ok = True
    except Refused as error:
        refused = True
        print("REFUSED:", error, file=sys.stderr)
    except Missed as error:
        print("MISSED:", error, file=sys.stderr)
    finally:
        walk.finish(ok, index=not refused)  # a refused installed run leaves the frame directory empty
    if refused:
        print("walkthrough", "REFUSED", "frames:", args.frames)
        return 1
    print("walkthrough", "OK" if ok else "FAILED", "frames:", args.frames)
    print((Path(args.frames) / "INDEX.md").read_text().split("## By task item", 1)[-1].strip())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
