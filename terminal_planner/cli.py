"""Interactive terminal application, also usable through a line-oriented PTY or piped input.

The UI only renders engine/authority/runs state and sends explicit owner actions; every lifecycle decision
(readiness, export, merge, resume, revision) stays in Authority and MilestoneRuns."""

import argparse
import importlib
import io
import os
from pathlib import Path
import re
import select
import shlex
import sys
import time

from .authority import Authority, Blocked, discover
from .delivery import (ATTENTION, CHECK, DELIVERY, DIFF_LIMIT, EMPTY_ANSWER, NEW_ATTEMPT, OUTCOME,  # noqa: F401
                       PLAN_STATUS, RUN_FAMILY, RUN_STATUS, STATE_TEXT, Changed, Delivery, plain, plan_lines,
                       refusal, short)
from .engine import FixtureEngine, NativeEngine
from . import __version__, catalog, commands, planning as planning_module, process, setup, update
from .process import Profile, ProfileChanged
from .planning import (HEARTBEAT, OBSERVING, PLANNER_FAMILY, PLANNER_SLICE, Planning, elapsed, one_line, plural,  # noqa: F401
                       summary)
from .runs import FixtureDriver, MilestoneRuns, NativeDriver, run_state
from .setup import (INTERRUPTED, YES_ANSWERS, ROLE_DEFAULTS, EFFORTS, agent_home, default_roles, launch_home, check_installation, doctor,
                    install_tools, load_roles, login, logout, native_environment,
                    native_state_root, owned_home, readiness, save_roles, severity, tool_paths)

DETACH_HINT = "Detached; the run continues. Come back with: zplan"
PLAIN_CHAT = "The architect chat is full-screen only: run zplan in a terminal (without --plain)."
FIXTURE_DELAY = 1.0  # seconds per fixture driver step in the CLI, so a demo run can be watched and detached


def valid_fixture_id(value):
    """The `--fixture ID` rule, the same one Authority enforces: an explicit, nonempty id of letters, digits,
    `-` and `_`. Checked right after parsing, before setup or any other external I/O, so `--fixture ''` never
    reaches the wiring (R-1)."""
    return isinstance(value, str) and bool(value.strip()) and all(c.isalnum() or c in "_-" for c in value)


class Detached(Exception):
    """Owner pressed Ctrl-C while observing: leave the run alone and exit."""


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

    def pending(self):
        """A line typed while observing, without blocking; only on a terminal (piped input is never consumed)."""
        try:
            if not self.input.isatty():
                return None
            ready, _, _ = select.select([self.input], [], [], 0)
        except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
            return None
        return (self.input.readline() or None) if ready else None


def terminal_confirm(terminal):
    return lambda question: terminal.ask(question + " [y/N]").strip().lower() in YES_ANSWERS


NO_PROJECT_EXIT = "Exit: no project selected."


def choose_project(terminal, start):
    """The Git project at `start` (working directory or --project); asks only when it does not resolve. Empty input
    checks `start` again; Ctrl+D or Ctrl+C before a project ends the session with None (nothing was started)."""
    try:
        return discover(start)
    except Blocked:
        terminal.show("%s is not a Git project with a commit." % start)
    try:
        while True:
            selection = terminal.ask("Git project (path)")
            try:
                return discover(selection or start)
            except Blocked:
                terminal.show("The path does not point to a Git project with a commit. Give another path." if selection
                              else "%s is not a Git project with a commit." % start)
    except (EOFError, KeyboardInterrupt):
        terminal.show("\n" + NO_PROJECT_EXIT)
        return None


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


def render(terminal, authority, runs=()):
    """The plan record of the current revision (the plan part of [i], from the delivery service's text)."""
    for line in plan_lines(authority, authority.current, runs):
        terminal.show(line)


class App:
    """One owner session over a locked authority: home screen and the screens it navigates to."""

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
        self.panel_clock = time.monotonic
        self.back = "back"  # readiness.back, or readiness.leave on the first screen: what [q] does there
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

    # Input -------------------------------------------------------------------

    def show(self, value=""):
        self.terminal.show(value)

    @staticmethod
    def offer(*ids):
        """(menu line, key set) of catalog actions: the one place a screen's keys are defined."""
        menu = catalog.menu(*ids)
        return menu, catalog.keys_of(*menu.ids)

    def explain(self, menu):
        """`?`: the keys of exactly the screen whose menu was shown, from the same catalog actions."""
        ids = getattr(menu, "ids", ())
        if ids:
            for line in catalog.help_lines(catalog.action(ids[0]).screen, ids):
                self.show(line)
        else:
            self.show("This screen's keys are listed in the menu above.")

    def choose(self, menu, keys):
        """A listed key (with an optional milestone id) or "" for Enter; q means back ("") wherever it is not
        listed itself; ? explains the keys. Anything else re-prompts with the menu."""
        while True:
            value = self.terminal.ask("Choice").strip()
            if not value:
                return "", None
            if value == "?":
                self.explain(menu)
                self.show(menu)
                continue
            key, _, rest = value.partition(" ")
            if key.lower() in keys:
                return key.lower(), rest.strip().upper() or None
            if key.lower() == "q" and not rest.strip():
                return "", None
            self.show("Unknown command \"%s\". Available (? for help):" % one_line(value, 40))
            self.show(menu)

    def confirm(self, question):
        return self.terminal.ask(question + " [y/N]").strip().lower() in YES_ANSWERS

    def text(self, label):
        self.show(label + " (several lines; an empty line ends):")
        lines = []
        while True:
            line = self.terminal.input.readline()
            if not line:
                raise EOFError
            if not line.strip():
                return "\n".join(lines).strip()
            lines.append(line.rstrip("\n"))

    # Home --------------------------------------------------------------------

    def plan(self):
        return self.delivery.plan()

    def title(self, milestone_id):
        return self.delivery.title(milestone_id)

    def home(self):
        """Render home; returns (menu, keys, focus). Refresh only detects integration (ancestry)."""
        a = self.authority
        branch, clean = self.controller.workspace()
        self.show("")
        note = process.view(self.profile).note if self.profile is not None else ""
        self.show("zplan · %s (%s, %s)%s" % (a.project.name, branch or "HEAD detached",
                                             "clean" if clean else "has changes", " · " + note if note else ""))
        return self.home_body()

    def home_body(self):
        """The plan part of home (the TUI panel shows exactly these lines); returns (menu, keys, home)."""
        home = self.delivery.home()
        for line in home.lines:
            self.show(line)
        menu, keys = self.offer(*home.ids)
        return menu, keys, home

    def run(self):
        menu = None
        items = self.planning.items("start")
        if not all(i["ok"] for i in items):
            # Shown only when something is missing; viewing plans and observing runs stay available.
            self.back = "leave"
            if self.ready(items, "start") == "q":
                return
        else:
            # R-3: nothing is missing, so no readiness screen; each warning is said once here and the run goes on.
            for line in dict.fromkeys(i["line"] for i in items if severity(i) == "warn"):
                self.show("! " + line)
        self.bootstrap()
        # Once per session, after the first screen: the architect chat is the full-screen shell's;
        # this line UI only says where it is. Not the first line, so the plain start stays the overview.
        self.show(PLAIN_CHAT)
        while True:
            try:
                menu, keys, home = self.home()
                self.show(menu)
                key, target = self.choose(menu, keys)
                if key == "q":
                    return
                if not key:
                    # Enter follows "Next" only when it is a view; starting or checking needs its letter.
                    key = self.delivery.next_view(home)
                if key:
                    self.dispatch(key, target, home)
            except Blocked as error:
                self.show("Not done: " + refusal(error))

    def bootstrap(self):
        """First start in a project whose process profile is undecided: one screen with the proposal and the
        choice (accept / later / leave undecided). Watching, stopping and exporting stay available either way."""
        if self.profile is None:
            return
        status = self.profile.status()
        if status.notice:
            self.show(status.notice)
        if status.state != "never":
            return
        self.show("")
        for line in process.bootstrap_lines(status):
            self.show(line)
        ids = ["bootstrap.accept"] + ([] if status.present else ["bootstrap.later"]) + ["bootstrap.leave"]
        menu, keys = self.offer(*ids)
        self.show(menu)
        key, _ = self.choose(menu, keys)
        if key == "a":
            done = self.profile.accept()
            if self.authority.fixture_id is not None and not status.present:
                # R-3: the demo keeps the snapshot in the fixture state; the project file is never created.
                self.show("Demo profile accepted: it applies in the fixture state; %s is not created." % process.PROFILE_FILE)
            else:
                self.show("Profile accepted: %s. %s" % (
                    process.PROFILE_FILE, "It was committed so the profile is shared." if not status.present
                    else "The file is unchanged."))
            if done.notice:
                self.show(done.notice)
        elif key == "l":
            self.profile.defer()
            self.show("Profile postponed: the values shown apply (%s)." % process.LATER_NOTE)
        else:
            self.show("Profile undecided: new plans and runs are unavailable until you accept it "
                      "(zplan or zplan profile init).")

    def dispatch(self, key, target, home):
        if key == "p":
            return self.plan_flow()
        if key == "r":
            return self.revise_plan()
        if key == "s":
            return self.settings()
        if key == "i":
            return self.details()
        if key == "e":
            return self.tail(target)
        pick = self.delivery.pick(key, target, home)
        if pick.kind == "message":
            self.show(pick.text)
        elif pick.kind == "start":
            return self.start(pick.row.id)
        elif pick.kind == "check":
            return self.check(self.delivery.latest(pick.row.id))
        elif pick.kind == "resume":
            return self.resume(self.delivery.latest(pick.row.id))
        elif pick.kind == "attempt":
            return self.follow(self.new_attempt(self.delivery.latest(pick.row.id)))
        else:
            return self.follow(self.delivery.latest(pick.row.id))

    def tail(self, target=None, r=None):
        """[e]: the last lines of the run's Zeroshot log, once, on request (bounded; never parsed)."""
        self.show("Reading the Zeroshot log…")
        if r is not None:
            title, lines = "Log %s · attempt %s" % (r["milestone"], r["attempt"]), self.delivery.tail(r)
        else:
            title, lines = self.delivery.activity(target)
        self.show(title + " (last lines):")
        for line in lines:
            self.show("  " + line)

    def resume(self, r):
        """[g] on a recoverable failure: readiness for a resume, then the same attempt continues."""
        if not self.gate("resume"):
            return
        self.show(self.delivery.pending_text("resume", r["milestone"]))
        return self.follow(self.delivery.resume(r))

    # Readiness ---------------------------------------------------------------

    def ready(self, items=None, need=None):
        """True when nothing is missing; otherwise the readiness screen until it passes, else the leaving key
        ("q" or "" for Enter). `need` names the model action whose checks apply (None: all, the home
        screen). Never commits, stashes or changes origin: [d] only shows the changes."""
        if self.readiness is None:
            return True
        items = self.planning.items(need) if items is None else items
        while True:
            missing = [i for i in items if not i["ok"]]
            if not missing:
                self.planning.attach_driver()
                return True
            menu, keys = self.readiness_screen(items)
            while True:
                key, _ = self.choose(menu, keys)
                if key == "d":
                    self.show("Uncommitted changes (git status --short):")
                    for line in self.controller.changes():
                        self.show("  " + line)
                    self.show("zplan does not change or commit them; [g] check again.")
                elif key == "i":
                    details = {}
                    for i in missing:
                        if i["detail"]:
                            details.setdefault(i["detail"], "readiness." + i["id"])
                    for line, code in details.items():
                        self.show("  " + line + catalog.tag(code))
                else:
                    break
                self.show(menu)
            if key in ("q", ""):
                return key
            action = {"u": self.install, "l": self.login}.get(key)
            if action is not None:
                self.attempt(action, key)
            items = self.planning.items(need)

    def readiness_screen(self, items):
        branch, _ = self.controller.workspace()
        self.show("")
        self.show("zplan · %s · %s" % (self.authority.project.name, branch or "HEAD detached"))
        for i in items:
            if i["id"] == "auth" and i["ok"]:
                self.show("✓ " + i["line"])
        # R-3: a warn line is listed here too (it keeps ok=True, so it is not "missing" and adds no key or action).
        for line in dict.fromkeys(i["line"] for i in items if not i["ok"] or severity(i) == "warn"):
            self.show("! " + line)
        actions = {"u": self.install, "l": self.login}
        wanted = {i["key"] for i in items if not i["ok"] and (i["key"] not in actions or actions[i["key"]] is not None)}
        wanted |= {"g", "i"}
        ids = [action_id for key, action_id in (("u", "readiness.install"), ("l", "readiness.login"),
                                                 ("d", "readiness.changes"), ("g", "readiness.recheck"),
                                                 ("i", "readiness.details")) if key in wanted]
        menu, keys = self.offer(*ids, "readiness." + self.back)
        self.show(menu)
        return menu, keys

    def gate(self, action="start"):
        """Readiness right before a model run: the checks `action` needs ("start" a new attempt, "resume")."""
        self.back = "back"
        if self.planning.gate(self.fixer(action), action).ok:
            return True
        self.show("Not started: fix what is marked above first.")
        return False

    def fixer(self, action):
        """The service's readiness callback for `action`: the readiness screen until the owner fixes it or leaves."""
        return lambda items: self.ready(items, action) is True

    def fix(self, items):
        """The planner submission's callback: the checks of the "plan" action."""
        return self.fixer("plan")(items)

    # Plan --------------------------------------------------------------------

    def roles_summary(self):
        self.show("Roles (model / effort):")
        for role in ROLE_DEFAULTS:
            binding = self.roles.get(role)
            if binding:
                self.show("  %-14s %s / %s" % (role, binding["model"], binding["effort"]))

    def plan_flow(self):
        if self.plan() is not None:
            return self.proposal_flow()
        self.planning.guard()  # an undecided or broken profile refuses before the goal is asked for
        goal = self.text("Goal")
        if not self.planning.valid_goal(goal):
            self.show(planning_module.GOAL_PROBLEM)
            return
        while True:
            self.roles_summary()
            menu, keys = self.offer("goal.start", "goal.settings", "goal.back")
            self.show(menu)
            key, _ = self.choose(menu, keys)
            if key == "s":
                self.settings()
                continue
            if key != "g":
                self.show("The goal was not saved; no plan was created.")
                return
            break
        try:
            ready = self.gate("plan")  # before the baseline: a fix made on the readiness screen belongs to this plan
        finally:
            # The goal is saved whatever the check says: a failed or interrupted check never loses it.
            self.planning.begin(goal, self.roles)
        if ready:
            self.submit()
        else:
            self.unsent()
        return self.proposal_flow()

    def unsent(self):
        self.show("Goal saved: plan r%s is not sent yet. To send it: [p] plan, then [g]." % self.authority.current["version"])

    def submit(self):
        """The only way to the planner: readiness right before it; a stale unsent revision is renewed first, an
        already sent one is never resent."""
        self.back = "back"
        self.outcome(self.planning.send(
            self.fix, lambda old, new: self.show(planning_module.renewed_line(old, new["version"]))))

    def outcome(self, result):
        """What a service verdict means on this screen: blocked keeps the goal and says so; stale is the plan
        screen's [n]; ready goes to the planner."""
        if result.kind == "blocked":
            self.show("Not started: fix what is marked above first.")
            if result.renewed or self.authority.current["status"] == "planning":
                self.unsent()
        elif result.kind == "ready":
            self.run_planner()

    def run_planner(self):
        """Submit once (if not yet sent) and observe in bounded slices: plain phases, a rare heartbeat."""
        watch = self.planning.watch(lambda line: self.show("  " + line))
        self.show("The planner is working; Ctrl-C leaves (planning continues; come back with [p] plan).")
        shown, phases = None, 0
        try:
            while watch.step() == "continue":
                shown = self.panel(None, shown, len(watch.shown) != phases)
                phases = len(watch.shown)
        except Blocked as error:
            self.show("Not done: " + refusal(error))

    def proposal_flow(self):
        """The plan screen. Viewing never submits: only [g], [n] or a written revision request reach the planner."""
        while True:
            menu, actions = self.plan_screen(self.authority.current)
            self.show(menu)
            key, _ = self.choose(menu, set(actions))
            if not key or key == "q":
                return
            if actions[key]():
                return

    PLAN_ACTIONS = {"start": "plan.start", "renew": "plan.renew", "watch": "plan.watch", "details": "plan.details",
                    "retry": "plan.retry", "revise": "plan.revise", "login": "plan.login", "restart": "plan.restart",
                    "approve": "plan.approve", "reject": "plan.reject", "requirements": "plan.requirements",
                    "tail": "plan.tail", "override": "plan.override", "stop": "plan.stop"}

    def plan_screen(self, current):
        view = self.planning.view()
        for line in view.lines:
            self.show(line)
        handlers = {"start": self.submit, "renew": self.renew, "watch": self.run_planner, "details": self.details,
                    "tail": self.tail,
                    "retry": self.restart, "revise": self.revise_current, "login": self.relogin,
                    "restart": self.restart, "approve": lambda: self.approve(current),
                    "reject": lambda: self.reject(current), "requirements": lambda: self.requirements(current),
                    "override": lambda: self.override(current), "stop": self.stop_planner}
        if view.kind == "unknown":
            handlers["details"] = lambda: self.unknown_details(current)
        entries = [(self.PLAN_ACTIONS[name], handlers[name]) for name in view.actions
                   if name != "login" or self.login is not None]
        return self.keys(*entries)

    @staticmethod
    def keys(*entries):
        """(menu, {key: action}) from (catalog action ID, action) pairs; [q] back closes every plan screen."""
        menu = catalog.menu(*[action_id for action_id, _ in entries], "plan.back")
        return menu, {catalog.action(action_id).key: action for action_id, action in entries}

    def unknown_details(self, current):
        """[i] for an unconfirmed submission: the record and how to see whether Zeroshot took it."""
        for line in self.delivery.plan_info():
            self.show(line)

    def attempt(self, action, key):
        """Run [u]/[l]; a failure is one plain line and the session stays on its screen (no errno or path)."""
        try:
            action()
        except Blocked as error:
            self.show("Not done: " + refusal(error))
        except (OSError, ValueError):
            self.show("Not done: the zplan tools are not installed; [u] install first." + catalog.tag("readiness.tools")
                      if key == "l" else
                      "Not done: the action could not be carried out; details: [i]." + catalog.tag(catalog.UNKNOWN))

    def relogin(self):
        """[l] after an authorization failure: the login of the home the run used (D6a/L4), not the process home."""
        self.attempt(lambda: self.login(home=self.planning.view().home, refresh=True), "l")

    def renew(self):
        """[n]: a new unsubmitted revision with the same goal, roles and request; the old one stays as it was."""
        new = self.planning.renew()
        self.show("Plan r%s prepared on the current project; same goal and settings. No model was run." % new["version"])

    def restart(self):
        """[g] after a failed planning: readiness first, then a new revision of the same goal goes to the planner."""
        self.back = "back"

        def announce(revision):
            self.show("Plan r%s prepared on the current project; same goal and settings. No model was run."
                      % revision["version"])
        self.outcome(self.planning.restart(self.fix, announce))

    def stop_planner(self):
        """[s]: force-stop the running planner once. A refusal keeps the revision as it was: the plan screen stays
        and offers [s] again."""
        try:
            self.show(self.planning.stop())
        except Blocked as error:
            self.show("Not done: " + refusal(error))
        return False

    def revise_current(self):
        feedback = self.text("What to change in the plan")
        if not feedback:
            self.show("Empty text: the plan is unchanged.")
            return
        self.back = "back"
        self.outcome(self.planning.revise(feedback, self.fix))

    def approve(self, current):
        self.planning.approve(current["version"])
        self.show("Plan r%s approved. Nothing was started; start with [g] on the home screen." % current["version"])
        return True

    def override(self, current):
        """[o]: approve a plan the critic rejected, with a typed reason; an empty reason cancels, a refusal stays here."""
        reason = self.text("Reason for approving the plan despite the check (one line, 10-500 characters)")
        if not reason:
            self.show("Empty text: the plan is unchanged.")
            return False
        try:
            self.planning.override(current["version"], reason)
        except Blocked as error:
            self.show("Not done: " + refusal(error))
            return False
        self.show("Plan r%s approved despite the check. Nothing was started; start with [g] on the home screen."
                  % current["version"])
        return True

    def reject(self, current):
        self.planning.reject(current["version"])
        self.show("Proposal r%s not approved; nothing was started." % current["version"])
        return True

    def requirements(self, current):
        """[i] requirements and checks: the full stored goal first, then the full plan — exactly the text the TUI's
        plan [i] shows, from the same delivery service (R-2: the plan [i] exposes the full goal in both UIs)."""
        for line in self.delivery.plan_info():
            self.show(line)

    def revise_plan(self):
        if self.plan() is None:
            self.show("There is no plan yet: [p] plan.")
            return
        feedback = self.text("What to change in the plan")
        if not feedback:
            self.show("Empty text: the plan is unchanged.")
            return
        self.back = "back"
        self.outcome(self.planning.revise(feedback, self.fix))
        return self.proposal_flow()

    # Settings and details ----------------------------------------------------

    def settings(self):
        self.roles_summary()
        if self.profile is not None:
            # Roles live in the project's profile (or its snapshot), not in roles.json: shown, never edited here.
            for line in process.describe(self.profile.status()):
                self.show(line)
            self.show("Roles and checks are edited in %s and apply to the next run." % process.PROFILE_FILE)
            return
        self.show("Enter keeps the current value.")
        self.roles = configure_roles(self.terminal, self.roles)
        self.show("Roles saved; they apply to the next planning and milestone run.")

    def details(self):
        """[i]: the outcome first, then the plan, then the marked diagnostic tail (the delivery service's text)."""
        for line in self.delivery.details():
            self.show(line)

    # Milestone screens -------------------------------------------------------

    def start(self, milestone_id):
        if not self.gate():
            return
        while True:
            preview = self.delivery.preview(milestone_id, self.roles)
            self.show("")
            for line in preview.lines:
                self.show(line)
            if not self.confirm(self.delivery.start_question(preview)):
                self.show("Not started.")
                return
            self.show(self.delivery.pending_text("start", milestone_id))
            try:
                r = self.delivery.start(preview, self.roles)
            except ProfileChanged as error:
                self.show("Not started: " + refusal(error))  # the preview is shown again with the new values
                continue
            return self.follow(r)

    def check(self, r):
        """Reconcile the active record with native: replay an unconfirmed submission, resend a lost force-stop."""
        self.show(self.delivery.check_line(r))
        self.delivery.reconcile()
        r = self.delivery.latest_only(r)
        return self.follow(r)

    def follow(self, r):
        """Observe while active, then the end screen; owner actions that create an attempt continue here."""
        while r is not None:
            if run_state(r) in ("running", "stopping"):
                r = self.observe(r)
                continue
            r = self.screen(r)

    def observe(self, r):
        self.show("")
        self.show("Watching %s · %s — Ctrl-C: detach (the run continues) · k + Enter: stop"
                  % (r["milestone"], self.title(r["milestone"])))
        now = self.delivery.now_line(r)
        if now:
            self.show(now)
        mark = None
        shown = None
        try:
            while r["status"] in {"submitted", "running", "stopping"}:
                step = self.delivery.step(r, mark)
                mark = step.mark
                for line in step.events:
                    self.show("  " + line)
                shown = self.panel(r, shown, bool(step.events))
                typed = self.terminal.pending()
                if typed is None:
                    continue
                if typed.strip() == "?":
                    for line in catalog.help_lines("observe"):
                        self.show(line)
                elif typed.strip().lower() == "e":
                    self.tail(r=r)
                elif typed.strip().lower() == "k" and r["status"] != "stopping":
                    if self.confirm(self.delivery.stop_question(r)):
                        self.show("  " + self.delivery.pending_text("stop", r["milestone"]))
                        self.delivery.stop(r)
                        self.show("  stop requested; waiting for Zeroshot to confirm.")
                else:
                    self.show("  While watching: k + Enter stops, e + Enter shows the log, Ctrl-C "
                              "detaches, ? is help.")
        except KeyboardInterrupt:
            raise Detached from None
        return r

    PANEL_EVERY = 30  # seconds between repeated live panels while nothing new happens

    def panel(self, r, shown, event):
        """Print the live panel (roles, elapsed, last event, heartbeat) when something new happened or every
        PANEL_EVERY seconds; `shown` is the clock reading of the last print."""
        now = self.panel_clock()  # its own clock: the planner heartbeat counts the session clock's readings
        if shown is not None and not event and now - shown < self.PANEL_EVERY:
            return shown
        lines = self.delivery.panel(r) if r is not None else self.delivery.planner_panel()
        for line in lines:
            self.show(line)
        return now

    def screen(self, r):
        """End screen of one attempt; returns the attempt to follow next, or None for home."""
        r = self.delivery.latest_only(r)
        if run_state(r) in ("running", "stopping"):
            return r
        end = self.delivery.end(r)
        self.show("")
        self.show(end.heading)
        self.show(end.status)
        for line in end.body:
            self.show(line)
        if not end.actions:
            return None
        handlers = {"merge": lambda: self.merge(end), "diff": lambda: self.show_diff(r), "later": lambda: None,
                    "accept": lambda: self.accept(r), "answer": lambda: self.answer(r), "leave": lambda: self.leave(r),
                    "plan": lambda: self.to_plan(r), "new_attempt": lambda: self.new_attempt(r),
                    "resume": lambda: self.delivery.resume(r) if self.gate("resume") else r, "check": lambda: self.check(r)}
        ids = [(a.id,) + a.args if a.args else a.id for a in end.actions] + ([end.back] if end.back else [])
        return self.menu(r, catalog.menu(*ids),
                         {catalog.action(a.id).key: handlers[a.name] for a in end.actions})

    def menu(self, r, menu, actions):
        self.show(menu)
        key, _ = self.choose(menu, set(actions))
        return actions[key]() if key else None

    def show_diff(self, r):
        self.show(self.delivery.diff_text(r))
        return r

    def merge(self, end):
        r = self.delivery.resolve(end.token)
        if not self.confirm(self.delivery.merge_question(r)):
            self.show("No merge was done.")
            return r
        self.show(self.delivery.pending_text("merge", r["milestone"]))
        # A7b2: the plain CLI has no event loop between slices, so it waits for the merge critic to finish.
        result = self.delivery.merge(r, slice=None)
        if result.line:
            self.show(result.line)
        return r if result.stay else None

    def new_attempt(self, r, label="Note for the new attempt (optional)"):
        if not self.gate():
            return r
        self.show(self.delivery.attempt_line(r))
        note = self.text(label)
        self.show(self.delivery.pending_text("attempt", r["milestone"]))
        return self.delivery.new_attempt(r, note)

    def to_plan(self, r):
        feedback = self.text("What to change in the plan")
        if not feedback:
            self.show("Empty text: the plan is unchanged.")
            return r
        self.delivery.to_plan(r, feedback)
        self.submit()
        self.proposal_flow()
        return None

    def answer(self, r):
        if not self.gate():
            return r
        self.show(self.delivery.attempt_line(r))
        text = self.text("Answer")
        if not text:
            self.show(EMPTY_ANSWER)
            return r
        return self.delivery.answer(r, text)

    def accept(self, r):
        if not self.gate():
            return r
        kind, value = self.delivery.accept(r)
        if kind == "attempt":
            self.show("Proposal accepted: " + self.delivery.attempt_line(r))
            return value
        self.show("The proposal changes the plan: revision r%s was created; it needs approval." % value["version"])
        self.submit()
        self.proposal_flow()
        return None

    def leave(self, r):
        self.show(self.delivery.leave_line(r))
        return None


def login_unfinished(code, retry, home=None):
    """The hint after a login that returned `code`, "" when the login already said why: Ctrl-C ("Login interrupted"), a
    home that is not zplan's (the "This is your Codex" line) or no terminal (the "needs your terminal" line)."""
    if code == INTERRUPTED or not owned_home(home or agent_home(os.environ)) or not setup.on_terminal():
        return ""
    return "Login not finished; retry %s. " % retry + catalog.LOGIN_DEVICE_CODE_OFF + catalog.tag("setup.login_failed")


def fixture_driver(authority):
    return FixtureDriver(authority.directory / "fixture-driver", delay=FIXTURE_DELAY)


def session(terminal, project, state_root, engine_factory, fixture_id=None, driver_factory=None, worktrees=None,
            readiness=None, install=None, login=None, clock=time.monotonic, profile=False):
    with Authority(state_root, project, fixture_id=fixture_id) as authority:
        factory = driver_factory or (fixture_driver if fixture_id is not None else lambda _: None)
        driver = factory(authority)
        if worktrees is None and fixture_id is not None:
            worktrees = authority.directory / "worktrees"
        try:
            App(terminal, authority, engine_factory, driver, worktrees, readiness=readiness, install=install,
                login=login, driver_factory=factory, clock=clock,
                profile=Profile.of(authority) if profile else None).run()
        except Detached:
            terminal.show("\n" + DETACH_HINT)


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


def tui_wanted(args, environ=None, stdin=None, stdout=None):
    """The full-screen UI only for an interactive owner: no subcommand, no --plain, a real terminal on both ends."""
    environ = os.environ if environ is None else environ
    if args.plain or args.command or environ.get("TERM", "") in ("", "dumb"):
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
    """`zplan profile` prints the resolved profile (no lock, no prompt); `profile init` writes the proposal.

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
            status = profile.accept()
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
    if args.native_state_dir is None:
        args.native_state_dir = str(native_state_root())
    if args.subcommand and args.command != "profile":
        parser.error("%s takes no argument %s" % (args.command or "zplan", args.subcommand))
    if args.command and args.command not in ("status", "profile") and args.fixture is not None:
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
        if not fixture:
            terminal.role_preferences = load_roles()
        if args.command == "roles":
            return roles_command(terminal, args)
        run_tui = start_screen = None
        if tui_wanted(args):
            try:
                importlib.import_module(".tui.app", __package__)  # Textual installed and importable?
                from .tui import run as run_tui
                from .tui.start import choose as start_screen
            except ImportError as error:
                terminal.show("Full-screen mode is unavailable (%s); continuing in line mode: zplan --plain." % summary(error)
                              + catalog.tag("tui.unavailable"))
        # The start screen needs the real terminals tui_wanted looks for; a patched check without them stays line-based.
        if start_screen is not None and sys.stdin.isatty() and sys.stdout.isatty():
            project = start_screen(args.project or os.getcwd())
        else:
            project = choose_project(terminal, args.project or os.getcwd())
        if project is None:
            return 0  # the owner left before a project: nothing was started, nothing to say about a session

        def check():
            attach_tools()
            return readiness(project, args.native_state_dir, tools=not (fixture or explicit))

        def sign_in(**options):
            code = login(terminal.show, confirm=terminal_confirm(terminal), **options)
            hint = login_unfinished(code, "[l] or zplan login", options.get("home")) if code else ""
            if hint:
                terminal.show(hint)

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
        if run_tui is not None:
            return run_tui(project, args.state_dir, fixture_id=args.fixture, driver_factory=drivers,
                           readiness=check, install=(lambda show: install_tools(show)) if native and not explicit else None,
                           login=tui_login if native else None, role_preferences=getattr(terminal, "role_preferences", None),
                           engine_factory=factory, profile=True)
        session(terminal, project, args.state_dir, factory, fixture_id=args.fixture, driver_factory=drivers,
                readiness=check, install=(lambda: install_tools(terminal.show)) if native and not explicit else None,
                login=sign_in if native else None, profile=True)
        return 0
    except (EOFError, KeyboardInterrupt):
        terminal.show("\nSession closed. The plan and the running milestones are saved; the run was not cancelled. Come back with: zplan")
        return 0
    except (Blocked, OSError, ValueError) as error:
        terminal.show("BLOCKED: " + refusal(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
