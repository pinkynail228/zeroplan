"""The `zplan` command: the full-screen UI's entry, the subcommands, and the headless session core both share.

zplan is full-screen only (0.15): without a terminal it refuses and names `zplan status` and `zplan exec`. Every
lifecycle decision (readiness, export, merge, resume, revision) stays in Authority, MilestoneRuns and the services."""

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import sys
import time

from .authority import Authority, Blocked, discover
from .delivery import Delivery, refusal
from .engine import FixtureEngine, NativeEngine
from . import __version__, catalog, commands, process, setup, update
from .process import Profile
from .planning import Planning, summary
from .runs import FixtureDriver, MilestoneRuns, NativeDriver
from .setup import (INTERRUPTED, YES_ANSWERS, EFFORTS, agent_home, default_roles, launch_home, check_installation, doctor,
                    install_tools, load_roles, login, logout, native_environment,
                    native_state_root, owned_home, readiness, save_roles, tool_paths)

PLAIN_REFUSED = "zplan is full-screen only; run it in a terminal."
NO_TERMINAL = "zplan needs an interactive terminal; for scripts use zplan status or zplan exec."
TUI_BROKEN = "zplan's full-screen UI cannot start (%s): reinstall zplan."
FIXTURE_DELAY = 1.0  # seconds per fixture driver step in the CLI, so a demo run can be watched and detached


def valid_fixture_id(value):
    """The `--fixture ID` rule, the same one Authority enforces: an explicit, nonempty id of letters, digits,
    `-` and `_`. Checked right after parsing, before setup or any other external I/O, so `--fixture ''` never
    reaches the wiring (R-1)."""
    return isinstance(value, str) and bool(value.strip()) and all(c.isalnum() or c in "_-" for c in value)


def safe(value):
    # Never render model-supplied terminal control sequences (including OSC hyperlinks).
    return "".join(c if c == "\n" or (c >= " " and c != "\x7f" and not 0x80 <= ord(c) < 0xa0) else "?" for c in str(value))


class Terminal:
    def __init__(self, input_stream=sys.stdin, output_stream=sys.stdout):
        self.input = input_stream
        self.output = output_stream

    def show(self, value=""):
        print(safe(value), file=self.output, flush=True)

    def ask(self, label, default=None):
        self.output.write(safe(label) + (" [%s]" % safe(default) if default is not None else "") + ": ")
        self.output.flush()
        line = self.input.readline()
        if not line:
            raise EOFError
        value = line.strip() or default
        if value is None:
            return ""
        return value



def terminal_confirm(terminal):
    return lambda question: terminal.ask(question + " [y/N]").strip().lower() in YES_ANSWERS


def configure_roles(terminal, current=None):
    terminal.show("Runtime: Codex / OpenAI. Model and effort are set separately for each role.")
    roles = {}
    defaults = current or getattr(terminal, "role_preferences", {})
    for role, binding in default_roles().items():
        binding = defaults.get(role, binding)
        while True:
            model = terminal.ask(role + " model", binding["model"])
            selected = terminal.ask(role + " effort", binding["effort"])
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,255}", model) and selected in EFFORTS:
                roles[role] = {"model": model, "effort": selected}
                break
            terminal.show("A model ID and an effort are required: " + ", ".join(sorted(EFFORTS)))
    if hasattr(terminal, "role_preferences"):
        save_roles(roles)
        terminal.role_preferences = roles
    return roles


class App:
    """The headless session core over a locked authority: the planning and delivery services, the roles and the
    home lines. The full-screen UI's controller builds one per session; `zplan status` prints its home."""

    def __init__(self, terminal, authority, engine_factory, driver=None, worktrees=None, readiness=None,
                 install=None, login=None, driver_factory=None, clock=time.monotonic, profile=None):
        """`readiness` returns the setup.readiness() items (None: nothing to check); `install`/`login` are the
        [u]/[l] actions; `driver_factory` supplies the milestone driver once tools become ready; `profile` is the
        process.Profile whose accepted values the roles and guards come from (None: no profile enforcement)."""
        self.terminal = terminal
        self.authority = authority
        self.engine_factory = engine_factory
        self.controller = MilestoneRuns(authority, driver, worktrees)
        self.readiness, self.install, self.login = readiness, install, login
        self.driver_factory, self.clock = driver_factory, clock
        self.planning = Planning(authority, self.controller, engine_factory, readiness, driver_factory, terminal, clock)
        self.planning.profile = self.profile = authority.profile = profile
        self.delivery = Delivery(authority, self.controller, self.planning)
        revisions = authority.state["revisions"] if authority.state else []
        # Saved preferences, else the planning roles of the last revision, over the defaults for every role.
        self._roles = default_roles()
        self._roles.update(getattr(terminal, "role_preferences", None) or (revisions[-1]["roles"] if revisions else {}))

    @property
    def roles(self):
        """The role preferences of the next submission: the accepted profile as it is on disk right now (an edit made
        while the app is open applies to the next start), else the session's own copy."""
        live = self.profile.roles() if self.profile is not None else None
        return live if live is not None else self._roles

    @roles.setter
    def roles(self, value):
        self._roles = value

    def show(self, value=""):
        self.terminal.show(value)

    def plan(self):
        return self.delivery.plan()

    def home(self):
        """Print home: the project line, then the plan part (`home_body`)."""
        a = self.authority
        branch, clean = self.controller.workspace()
        self.show("")
        note = process.view(self.profile).note if self.profile is not None else ""
        self.show("zplan · %s (%s, %s)%s" % (a.project.name, branch or "HEAD detached",
                                             "clean" if clean else "has changes", " · " + note if note else ""))
        return self.home_body()

    def home_body(self):
        """The plan part of home (the TUI panel shows exactly these lines); returns the delivery service's home."""
        home = self.delivery.home()
        for line in home.lines:
            self.show(line)
        return home


def login_unfinished(code, retry, home=None):
    """The hint after a login that returned `code`, "" when the login already said why: Ctrl-C ("Login interrupted"), a
    home that is not zplan's (the "This is your Codex" line) or no terminal (the "needs your terminal" line)."""
    if code == INTERRUPTED or not owned_home(home or agent_home(os.environ)) or not setup.on_terminal():
        return ""
    return "Login not finished; retry %s. " % retry + catalog.LOGIN_DEVICE_CODE_OFF + catalog.tag("setup.login_failed")


def fixture_driver(authority):
    return FixtureDriver(authority.directory / "fixture-driver", delay=FIXTURE_DELAY)


class ReadOnlyAuthority(Authority):
    """The store as it is, for `zplan status` (G5): no session lock is taken, so it answers while the shell holds the
    project. Nothing is written: the overview's integration check (`MilestoneRuns.refresh`) still updates the records
    in memory, so a merge made by hand shows as merged, but `save` stores nothing; any other mutation is refused for
    want of the session lock."""

    def __enter__(self):
        self.state = None
        self._store_bytes = None
        self.feed_pending = False
        if self.path.exists():
            self.load_projection(self.path.read_bytes())
        return self

    def save(self):
        """Keep the in-memory state this one overview shows; the shell's store is not ours to write."""


def status(terminal, project, state_root, fixture_id=None, driver_factory=None, worktrees=None):
    """`zplan status`: the home screen once, no prompts, nothing dispatched. Read-only: no session lock, so it
    answers while the shell is open (G5)."""
    with ReadOnlyAuthority(state_root, project, fixture_id=fixture_id) as authority:
        driver = (driver_factory or (fixture_driver if fixture_id is not None else lambda _: None))(authority)
        if worktrees is None and fixture_id is not None:
            worktrees = authority.directory / "worktrees"
        # Read-only profile (no write, no prompt): only the header note of an undecided/postponed profile shows.
        App(terminal, authority, None, driver, worktrees,
            profile=Profile.peek(project, root=state_root, fixture_id=fixture_id)).home()


def tui_entry():
    """(run, start screen) of the full-screen UI: the Textual boundary. ImportError when Textual is missing or broken."""
    importlib.import_module(".tui.app", __package__)
    from .tui import run
    from .tui.start import choose
    return run, choose


def tui_wanted(args, environ=None, stdin=None, stdout=None):
    """Whether `zplan` itself can open: a real terminal on both ends and a usable TERM (not empty, unset or dumb)."""
    environ = os.environ if environ is None else environ
    if environ.get("TERM", "") in ("", "dumb"):
        return False
    try:
        return bool((stdin or sys.stdin).isatty() and (stdout or sys.stdout).isatty())
    except (AttributeError, ValueError):
        return False


def help_request(argv):
    """(text, exit code) when argv asks for help (`help [command]`, or -h/--help anywhere), else None. Pure
    metadata: nothing else is read, so help works without tools, login, a Git project or a model."""
    values = {name for flag in commands.FLAGS if flag.metavar for name in flag.names}
    words, skip = [], False
    for word in argv:
        if skip:
            skip = False
        elif word in values:
            skip = True
        elif not word.startswith("-"):
            words.append(word)
    if words[:1] == ["help"]:
        topic = words[1] if len(words) > 1 else None
        text = commands.help_for(topic)
        return (text, 0) if text is not None else (commands.unknown_topic(topic), 2)
    if "-h" in argv or "--help" in argv:
        return commands.help_for(next((w for w in words if w in commands.NAMES), None)), 0
    return None


def build_parser():
    """The argument parser, derived from the same command and flag metadata as every help text."""
    parser = argparse.ArgumentParser(prog="zplan", description=commands.HEADER, add_help=False)
    parser.add_argument("command", nargs="?", choices=commands.NAMES, help="; ".join(
        "%s — %s" % (name, commands.command(name).purpose) for name in commands.NAMES))
    parser.add_argument("subcommand", nargs="?", choices=("init",), help="profile init")
    for flag in commands.FLAGS:
        if flag.names[-1] == "--help":
            continue  # answered by help_request before parsing
        if flag.names == ("--version",):
            parser.add_argument(*flag.names, action="version", version="zplan " + __version__, help=flag.purpose)
        elif flag.metavar is None:
            parser.add_argument(*flag.names, action="store_true", help=flag.purpose)
        else:
            parser.add_argument(*flag.names, metavar=flag.metavar, help=flag.purpose)
    return parser


def profile_command(terminal, args):
    """`zplan profile` prints the resolved profile (no lock, no prompt); `profile init` exports the effective profile
    to the project's file (never over an existing one) and commits it; from then on the file is the source.

    In a fixture session it records the snapshot in the fixture state and never writes the target's file (R-3); the
    file's own rule still applies (an existing file is refused), and an already accepted fixture profile is refused
    too, so `init` never silently re-decides one. A deferred (or undecided) fixture profile is accepted, exactly
    like a production `init` that writes the file over a "later"."""
    project = discover(args.project or os.getcwd())
    fixture = args.fixture is not None
    if args.subcommand == "init":
        with Authority(args.state_dir, project, fixture_id=args.fixture) as authority:
            profile = Profile.of(authority)
            status = profile.status()
            if status.present:
                raise Blocked("%s already exists: profile init does not overwrite it. Check the file and run zplan."
                              % process.PROFILE_FILE, family="action.refused")
            if fixture and status.state == "accepted":
                raise Blocked("The demo profile is already accepted: profile init does not overwrite it.", family="action.refused")
            status = profile.accept() if fixture else profile.export()
        if fixture:
            terminal.show("Demo profile accepted: it applies in the fixture state; %s is not created." % process.PROFILE_FILE)
        else:
            terminal.show("Created %s." % process.PROFILE_FILE if status.notice else
                          "Created %s, committed: %s." % (process.PROFILE_FILE, process.COMMIT_MESSAGE))
    else:
        status = Profile.peek(project, root=args.state_dir, fixture_id=args.fixture).status()
    for line in process.describe(status):
        terminal.show(line)
    return 1 if status.state in ("missing", "malformed") else 0


def roles_command(terminal, args):
    """`zplan roles`: with a project profile file the roles live there (shown, not edited); otherwise roles.json."""
    try:
        project = discover(args.project or os.getcwd())
    except Blocked:
        project = None
    peek = Profile.peek(project) if project is not None else None
    if peek is not None and os.path.lexists(peek.file):
        for line in process.describe(peek.status()):
            terminal.show(line)
        terminal.show("This project's roles live in %s: edit the file; roles.json was not changed." % process.PROFILE_FILE)
        return 0
    configure_roles(terminal)
    terminal.show("Role defaults were saved outside the project lifecycle state.")
    if peek is not None and peek.status().state == "later":
        terminal.show("This project's profile is postponed: its roles come from the snapshot and did not change. "
                      "To accept the profile: zplan profile init.")
    return 0


def exec_command(args, text, engine_factory, driver_factory, readiness):
    """Thin send-only frontend; the service owns admission, replay and aggregate status."""
    from .application import ApplicationService, scrub
    from .architect import ArchitectStore, FixtureArchitect
    from .tui.controller import Controller  # existing no-screen controller; imports no Textual

    controller = None
    try:
        project = discover(args.project or os.getcwd())
        fixture = args.fixture is not None
        root = Path(args.state_dir) / "architect" / args.fixture if fixture else None
        store = ArchitectStore(project, root=root)
        architect = FixtureArchitect(store) if fixture else None
        controller = Controller.for_project(project, args.state_dir, fixture_id=args.fixture,
                                            engine_factory=engine_factory, driver_factory=driver_factory,
                                            readiness=None if fixture else readiness, profile=not fixture)
        service = ApplicationService(architect, store=store, controller=controller)
        controller.start()
        result = service.submit_message(args.operation_id, text)
        output = service.message_outcome(result)
        print(json.dumps(output, ensure_ascii=False))
        return output["exit_code"]
    except KeyboardInterrupt:
        print("Interrupted; inspect the durable operation before submitting another id.", file=sys.stderr)
        return 3
    except Exception as error:
        family = getattr(error, "family", None) or ("operation.store_invalid" if isinstance(error, (OSError, ValueError))
                                                  else catalog.UNKNOWN)
        print(scrub("%s: %s" % (family, error))[:2000], file=sys.stderr)
        return 1
    finally:
        if controller is not None:
            controller.stop()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    asked = help_request(argv)
    if asked is not None:
        text, code = asked
        if code == 0:
            Terminal().show(text)
        else:
            print(text, file=sys.stderr)
        return code
    parser = build_parser()
    args = parser.parse_args(argv)
    # R-1: the fixture id is checked right after parsing, before any filesystem access (native_state_root resolves
    # the production state path) or the wiring: an invalid id never reaches setup, attach_tools or a session.
    if args.fixture is not None and not valid_fixture_id(args.fixture):
        parser.error("the fixture ID must be non-empty and consist of letters, digits, \"-\" or \"_\"")
    goal_text = None
    if args.command == "exec":
        if not args.goal or not args.operation_id or not args.operation_id.strip() or len(args.operation_id) > 128:
            parser.error("exec requires --goal GOAL.md and --operation-id ID (1-128 characters)")
        if args.state_dir is not None and args.fixture is None:
            parser.error("--state-dir is fixture only")
        if args.fixture is not None and args.state_dir is None:
            parser.error("exec --fixture requires --state-dir DIR")
        if args.plain or args.check:
            parser.error("exec does not use --plain or --check")
        try:
            if not Path(args.goal).is_file():
                raise ValueError("not a regular goal file")
            with Path(args.goal).open("rb") as stream:
                data = stream.read((1 << 20) + 1)
            goal_text = data.decode("utf-8")
            if len(data) > 1 << 20 or not goal_text.strip() or "\0" in goal_text:
                raise ValueError("invalid goal")
        except (OSError, ValueError):
            parser.error("--goal must name a readable, nonempty UTF-8 text file of at most 1 MiB (no NUL)")
    elif args.goal is not None or args.operation_id is not None:
        parser.error("--goal and --operation-id apply only to exec")
    if args.native_state_dir is None:
        args.native_state_dir = str(native_state_root())
    if args.subcommand and args.command != "profile":
        parser.error("%s takes no argument %s" % (args.command or "zplan", args.subcommand))
    if args.command and args.command not in ("status", "profile", "exec") and args.fixture is not None:
        parser.error("setup/doctor/login/logout/update/roles do not use a fixture namespace")
    terminal = Terminal()
    environment = None
    explicit = bool(args.native_binary)  # a development binary; otherwise the pinned private tools
    fixture = args.fixture is not None  # the fixture mode is `--fixture ID` itself, never its truthiness (R-1)

    def attach_tools():
        """Use the pinned tools once they are installed and intact (checked again before every readiness list).

        R-1: the home is chosen independently of the executable. Even a `--native-binary` development launch hands
        the planner and the milestone driver an env whose `CODEX_HOME` is `setup.launch_home()`, so a fresh install
        never leaves it unset and falls back to Codex's own `~/.codex`. A `setup.agent_home` refusal (busy, OSError
        or a private home that resolves into the owner's own Codex home) is not "tools not installed": it reaches
        the owner instead of degrading (R-3c). Anything else keeps the old degrade-to-missing shape."""
        nonlocal environment
        if fixture:
            return
        if explicit:  # a development binary: no pinned tools, but the home is still zplan's own (R-1)
            environment = dict(os.environ, CODEX_HOME=str(launch_home()))
            return
        try:
            check_installation()
            environment = native_environment()
            args.native_binary = str(tool_paths()[0])
        except Blocked as error:
            if error.family == "setup.agent_home":
                raise
            environment, args.native_binary = None, None
        except (OSError, ValueError):
            environment, args.native_binary = None, None

    def factory(name, terminal):
        if name == "fixture":
            return FixtureEngine()
        binary = args.native_binary
        if not binary:
            raise Blocked("The zplan tools are not installed: [u] on the readiness screen or zplan setup.", family="readiness.tools")
        if not Path(binary).expanduser().is_absolute() or not os.access(Path(binary).expanduser(), os.X_OK):
            raise Blocked("An existing executable at an absolute path is required; the installed server binary is not used.", family="engine.unavailable")
        return NativeEngine(binary, args.native_state_dir, environment=environment)

    def drivers(authority):
        if authority.fixture_id is not None:
            return fixture_driver(authority)
        if not args.native_binary:
            return None  # status without installed tools: no live phase, nothing else needs the binary
        return NativeDriver(args.native_binary, args.native_state_dir, environment=environment)

    if args.command == "exec":
        def exec_readiness():
            attach_tools()
            return readiness(discover(args.project or os.getcwd()), args.native_state_dir, tools=not explicit)
        return exec_command(args, goal_text, factory, drivers, exec_readiness)

    try:
        if args.command == "setup":
            install_tools(terminal.show)
            return 0
        if args.command == "doctor":
            project = args.project
            if project is None:
                try:
                    discover(os.getcwd())
                    project = os.getcwd()
                except Blocked:
                    pass  # not a Git project: informational only, tools may be checked before cd
            return doctor(terminal.show, args.native_state_dir, project)
        if args.command == "login":
            code = login(terminal.show, confirm=terminal_confirm(terminal))
            hint = login_unfinished(code, "zplan login") if code else ""
            if hint:
                terminal.show(hint)
            return code
        if args.command == "logout":
            code = logout(terminal.show)
            if code:
                terminal.show("Exit not finished.")
            return code
        if args.command == "update":
            return update.run(check=args.check, show=terminal.show)
        if args.command == "status":
            if not fixture and not args.native_binary and (tool_paths()[0].parent / "installation.json").exists():
                try:
                    check_installation()
                    environment = native_environment(profile=False)  # R-3c: status reads records, writes nothing
                    args.native_binary = str(tool_paths()[0])
                except (Blocked, OSError):
                    pass  # status still renders the stored state
            status(terminal, discover(args.project or os.getcwd()), args.state_dir, args.fixture, drivers)
            return 0
        if args.command == "profile":
            return profile_command(terminal, args)
        if args.command is None:
            if args.plain:  # kept as a flag only to say why (0.15: the line UI is gone)
                print(PLAIN_REFUSED, file=sys.stderr)
                return 2
            if not tui_wanted(args):
                print(NO_TERMINAL, file=sys.stderr)
                return 2
        if not fixture:
            terminal.role_preferences = load_roles()
        if args.command == "roles":
            return roles_command(terminal, args)
        try:
            run_tui, start_screen = tui_entry()
        except ImportError as error:
            print(TUI_BROKEN % summary(error) + catalog.tag("tui.unavailable"), file=sys.stderr)
            return 1
        project = start_screen(args.project or os.getcwd(), origin=not fixture)
        if project is None:
            return 0  # the owner left before a project: nothing was started, nothing to say about a session

        def check():
            attach_tools()
            return readiness(project, args.native_state_dir, tools=not (fixture or explicit))

        def tui_login(**options):
            """The login under the TUI's suspend: what zplan itself says stays on screen until Enter."""
            said = []
            code = login(said.append, confirm=terminal_confirm(terminal), **options)
            for line in said:
                terminal.show(line)
            if said:
                terminal.ask("Enter returns to zplan")
            return code
        native = not fixture
        attach_tools()  # the milestone driver needs the binary from the start when tools are installed
        return run_tui(project, args.state_dir, fixture_id=args.fixture, driver_factory=drivers,
                       readiness=check, install=(lambda show: install_tools(show)) if native and not explicit else None,
                       login=tui_login if native else None, role_preferences=getattr(terminal, "role_preferences", None),
                       engine_factory=factory, profile=True)
    except (EOFError, KeyboardInterrupt):
        terminal.show("\nSession closed. The plan and the running milestones are saved; the run was not cancelled. Come back with: zplan")
        return 0
    except (Blocked, OSError, ValueError) as error:
        terminal.show("BLOCKED: " + refusal(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
