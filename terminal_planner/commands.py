"""Command and flag metadata: the one source of `zplan --help`, `zplan help <command>`, `zplan <command> --help`,
the argument parser and the generated tables of docs/REFERENCE.md. Pure data and text rendering: it imports nothing
from the product, so every help path works without tools, login, a Git project or any model call."""

from collections import namedtuple

Command = namedtuple("Command", "name usage purpose detail meaning examples")
Flag = namedtuple("Flag", "names metavar purpose meaning commands")

START = "start"  # the default command: plain `zplan`

COMMANDS = (
    Command(START, "zplan [--plain] [--project PATH]",
            "open the plan and milestones of the current Git project",
            "Interactive mode: a full-screen interface on a terminal, otherwise (or with --plain, TERM=dumb) a "
            "line-oriented one. The project is the current directory or --project. Screen keys: ? (lists the current screen's keys).",
            "Opens the plan and milestones of the Git project in the working directory (full-screen on a terminal, "
            "line-oriented otherwise).",
            ("zplan --plain                  line-oriented mode without the full-screen interface",
             "zplan --project ~/work/app     open another project",
             "zplan --fixture demo --state-dir /tmp/zplan-demo   demo without a model in an isolated directory")),
    Command("status", "zplan status [--project PATH]",
            "show the home screen once, without prompts",
            "Prints the plan and the milestones' state and exits; starts and changes nothing. Suitable for scripts "
            "and outside checks.",
            "Prints the home screen once (no prompts, no escape codes, nothing dispatched).",
            ("zplan status                   plan and milestones of the current project",
             "zplan status --project ~/work/app",
             "zplan status --fixture demo --state-dir /tmp/zplan-demo")),
    Command("setup", "zplan setup",
            "install the pinned Zeroshot and Codex into zplan's data directory",
            "Downloads the Zeroshot bundle and verifies it against checksums, installs Codex from the pinned lockfile "
            "(Node.js >= 16 and npm are required). What is already installed is not replaced. No model is run.",
            "Installs the pinned Zeroshot bundle and Codex into zplan's data directory (checksums verified, no model call).",
            ("zplan setup                    install the tools",
             "zplan setup && zplan login     then log in to Codex")),
    Command("doctor", "zplan doctor [--project PATH]",
            "check readiness: tools, login, Git, project",
            "First the Toolchain line: the Zeroshot, Codex and restic versions of this release and the tools directory; then one line "
            "per check: OK, WARN or BLOCKED with the fix. Exit code 0 when nothing is BLOCKED. "
            "Outside a Git project only the tools are checked.",
            "Prints the Toolchain line (versions, tool directory), then one line per readiness check; exit status 0 "
            "only when everything is ready.",
            ("zplan doctor                   check the current project",
             "zplan doctor --project ~/work/app",
             "zplan doctor || zplan setup    install if something is missing")),
    Command("login", "zplan login",
            "log in to Codex (device auth) in zplan's own directory",
            "Runs the installed Codex login in the terminal; zplan neither reads nor stores credentials. "
            "If a login already exists, does nothing. Logs in only to zplan's own directory: in your CODEX_HOME it "
            "does not start Codex (log in there with codex login). Do not copy auth.json between directories.",
            "Runs the installed Codex device login in zplan's own Codex home (a login that is already there is kept); "
            "in a CODEX_HOME of yours it runs nothing; zplan never reads credentials.",
            ("zplan login                    log in to zplan's own directory",
             "CODEX_HOME=~/.codex zplan       work in your own Codex (log in there with codex login)")),
    Command("logout", "zplan logout",
            "log out of Codex in zplan's own directory",
            "Runs codex logout in zplan's own directory (revokes only its login). Not run in your "
            "CODEX_HOME, for a copied auth.json, or while a run is going or the architect is answering there.",
            "Runs codex logout in zplan's own Codex home only; refused in a CODEX_HOME of yours, for a copied "
            "auth.json and while a run or the architect is live there.",
            ("zplan logout                   log out, then zplan login",)),
    Command("update", "zplan update [--check]",
            "update zplan to the newest release",
            "Reads the repository's release tags (vX.Y.Z) and installs the newest with the same install.py as the first install: "
            "the new version sits beside the old one, the store is copied before the launcher is switched. --check only prints "
            "the current and the newest version and changes nothing. Close zplan before updating.",
            "Fetches the newest release tag and installs it (the old app and a store backup stay for rollback); "
            "--check only reports the versions.",
            ("zplan update                   update to the newest release",
             "zplan update --check           show the current and the newest version")),
    Command("roles", "zplan roles [--project PATH]",
            "choose the model and effort for each role",
            "Asks for the model and effort of planner, plan_verifier, worker, reviewer, steward; Enter keeps "
            "the value. Saved outside the project state and applies to the next planning and run. "
            "If the project has a zplan.process.json, the roles live there: the command shows them and changes nothing.",
            "Edits the model/effort binding of each role (saved outside any project's state); with a project "
            "zplan.process.json it only shows the roles, which live in that file.",
            ("zplan roles                    show and change the roles",)),
    Command("profile", "zplan profile [init] [--project PATH]",
            "show the project's process profile or create zplan.process.json",
            "Without an argument prints the effective profile: state, file path, short digest, roles with their sources, "
            "checks (gates), quality checks. Asks nothing and starts nothing. init writes the proposed "
            "profile to zplan.process.json without prompts; if the file already exists it refuses.",
            "Prints the resolved process profile with the source of each key; `init` writes the proposed "
            "zplan.process.json non-interactively and refuses when one exists.",
            ("zplan profile                  profile of the current project",
             "zplan profile init             write the proposed zplan.process.json",
             "zplan profile --project ~/work/app")),
)

FLAGS = (
    Flag(("--plain",), None, "line-oriented mode without the full-screen interface (also when the output is not a terminal)",
         "Forces the line-oriented UI.", (START,)),
    Flag(("--project",), "PATH", "Git project (default: the current directory)",
         "Selects the Git project instead of the working directory.", (START, "status", "doctor", "roles", "profile")),
    Flag(("--state-dir",), "DIR", "fixture only: root of the isolated state",
         "Fixture state root; production overrides are rejected.", (START, "status", "profile")),
    Flag(("--fixture",), "ID", "isolated demo without a model; native runs are forbidden",
         "Runs against the deterministic fixture engine in an isolated authority.", (START, "status", "profile")),
    Flag(("--native-binary",), "PATH", "explicit isolated Zeroshot executable (development)",
         "Explicit Zeroshot executable instead of the pinned private tools.", (START, "status")),
    Flag(("--native-state-dir",), "DIR", "durable Zeroshot history; a short path for Unix sockets",
         "Durable native state root (short path: Unix socket limit).", (START, "status", "doctor")),
    Flag(("--check",), None, "only show the versions, change nothing (for update)",
         "Reports the installed and the newest release without changing anything.", ("update",)),
    Flag(("--version",), None, "show the version", "Prints the version.", ()),
    Flag(("-h", "--help"), None, "show help", "Prints help for the command.", ()),
)

TOP_FLAGS = ("--version", "--help")
NAMES = tuple(c.name for c in COMMANDS if c.name != START)
HEADER = "zplan — plan and milestones on top of Zeroshot."


def command(name):
    return next((c for c in COMMANDS if c.name == name), None)


def flags_of(name):
    """Flags that apply to the command (`start` for plain `zplan`); --help applies to every command."""
    return tuple(f for f in FLAGS if name in f.commands or f.names[-1] == "--help")


def flag_text(flag):
    names = ", ".join(flag.names)
    return names + (" " + flag.metavar if flag.metavar else "")


def top_help():
    """`zplan --help` / `zplan help`: every command with its one-line purpose, then the global flags."""
    lines = [HEADER, "", "Usage: zplan [command] [options]", "", "Commands:"]
    start = command(START)
    lines.append("  %-13s %s" % ("(no command)", start.purpose))
    for item in COMMANDS:
        if item.name != START:
            lines.append("  %-13s %s" % (item.name, item.purpose))
    lines.append("  %-13s %s" % ("help", "help: zplan help <command>"))
    lines += ["", "Start options (zplan [options]):"]
    for flag in flags_of(START):
        if flag.names[-1] != "--help":
            lines.append("  %-30s %s" % (flag_text(flag), flag.purpose))
    lines += ["", "Common options:"]
    for flag in FLAGS:
        if flag.names[-1] in TOP_FLAGS:
            lines.append("  %-30s %s" % (flag_text(flag), flag.purpose))
    lines += ["", "More: zplan help <command> or zplan <command> --help; reference: docs/REFERENCE.md.",
              "Keys: ? on any screen shows that screen's keys."]
    return "\n".join(lines)


def command_help(name):
    item = command(name)
    lines = [item.usage, "", item.purpose[0].upper() + item.purpose[1:] + ".", "", item.detail]
    shown = [f for f in flags_of(name)]
    if shown:
        lines += ["", "Options:"]
        for flag in shown:
            lines.append("  %-30s %s" % (flag_text(flag), flag.purpose))
    lines += ["", "Examples:"] + ["  " + example for example in item.examples]
    return "\n".join(lines)


def help_for(topic=None):
    """Text for `zplan help [topic]`; None when the topic is not a command."""
    if topic in (None, "", "help"):
        return top_help()
    return command_help(topic) if topic in NAMES or topic == START else None


def unknown_topic(topic):
    return "No help for “%s”. Commands: %s." % (topic, ", ".join(NAMES))
