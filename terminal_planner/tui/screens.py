"""The full-screen forms that are not the main screen: the plan screen and Settings. The names they need from
`app.py` (`keys_bar`, `PLAIN_KEYS`, `LOG_LINES`, `LOG_PLACEHOLDER`, `PROGRESS_TITLE`) are imported inside
the methods that use them, because `app.py` imports this module."""

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, RichLog, Static

from .. import catalog
from .modals import NoteScreen, ProfileScreen
from .text import plain_value, wrapped


class ButtonScreen(Screen):
    """K1c2: a full-screen form that answers with a row of buttons, not letters: one `Button` per offered action
    (`sync_buttons`), Tab / ←→ move the focus, Enter presses the focused button, Esc goes back. A button's `name` is
    the action it runs (`action_<name>`); its label is the catalog entry `<bar>.<name>`."""
    bar = ""  # catalog screen of the buttons' labels and of the key bar
    row = ""  # id of the Horizontal that holds the buttons
    BINDINGS = [Binding("escape", "back", "Back"), Binding("left", "move(-1)", "Button", show=False),
                Binding("right", "move(1)", "Button", show=False)]
    shown = None  # the action names the row was last asked to show
    parked = False  # P1a: Esc closed a block and left the focus off the buttons: a rebuild must not take it back

    def sync_buttons(self, names, fresh=False):
        """Rebuild the row when the offered actions changed: the focus stays on the same action if it is still
        offered, else goes to the first button. `fresh` (P1a): the screen moved to another state (a plan that went from
        planning to proposed), so the focus goes to the first button whatever held it."""
        names = tuple(names)
        if names != self.shown:
            self.shown = names
            self.call_later(self.rebuild_buttons, names, fresh)

    async def rebuild_buttons(self, names, fresh=False):
        row = self.query_one("#" + self.row)
        focused = self.focused
        keep = focused.name if isinstance(focused, Button) and focused.parent is row and not fresh else None
        if fresh:
            self.parked = False
        await row.remove_children()
        buttons = [Button(catalog.label("%s.%s" % (self.bar, name)), id="%s-%s" % (self.row, name), name=name,
                          compact=True) for name in names]
        await row.mount(*buttons)
        target = next((b for b in buttons if b.name == keep), buttons[0] if buttons else None)
        if target is not None and (fresh or keep is not None
                                   or not (isinstance(self.focused, Button) or self.parked)):
            target.focus()

    def action_move(self, step):
        self.focus_next() if step > 0 else self.focus_previous()

    def on_key(self, event):
        """P1a: a `/` typed here is not dropped: the screen closes and the `/` opens the chat's palette."""
        if event.character == "/":
            event.stop()
            event.prevent_default()
            self.app.forward_to_chat("/", leave=True)

    def on_button_pressed(self, event):
        event.stop()
        getattr(self, "action_" + event.button.name)()


class PlanScreen(ButtonScreen):
    """The current revision: its status, the planner progress, and the proposal with the owner's decisions.
    Opening it never submits or decides; every action is an explicit button."""
    bar = "tui_plan"
    row = "plan-buttons"
    BINDINGS = [Binding("up", "scroll('scroll_up')", "Scroll", show=False),
                Binding("down", "scroll('scroll_down')", "Scroll", show=False),
                Binding("pageup", "scroll('scroll_page_up')", "Scroll", show=False),
                Binding("pagedown", "scroll('scroll_page_down')", "Scroll", show=False)]
    ready = False
    row_state = None  # P1a: (version, kind, status) of the plan the button row was last built for
    from_main = False  # R-A: opened by the owner from the main screen; a plan screen that follows a goal form is not
    ACTION_IDS = {"start": "run", "retry": "run", "restart": "run", "renew": "renew", "login": "login",
                  "watch": "watch", "tail": "tail", "approve": "approve", "override": "override", "revise": "revise",
                  "reject": "reject",
                  "requirements": "info", "details": "info"}

    def compose(self):
        yield Static("", id="plan-title", markup=False)
        with VerticalScroll(id="plan-scroll", can_focus=False):
            yield Static("", id="plan-body", markup=False)
        yield Static("", id="plan-progress", markup=False)
        yield Horizontal(id="plan-buttons")
        yield Static("", id="plan-keys", markup=False)

    def on_mount(self):
        from .app import PROGRESS_TITLE  # function-level: app imports this module
        self.query_one("#plan-scroll").border_title = "Plan"
        self.query_one("#plan-progress").border_title = PROGRESS_TITLE
        self.ready = True
        self.render_state()
        self.app.request_check()  # a blocked message is re-checked against the project as it is now

    def on_resize(self, _):
        self.render_state()

    def view(self):
        snapshot = self.app.snapshot
        return snapshot.plan if snapshot is not None else None

    def offered(self):
        view = self.view()
        if view is None:
            return []
        # Only the plain actions this screen wires: a plan action with no TUI key yet (the planner stop of p1b)
        # is left to the plain screen until its own run binds it, never a KeyError here.
        names = [self.ACTION_IDS[a] for a in view.actions if a in self.ACTION_IDS]
        if "login" in names and self.app.controller.login is None:
            names.remove("login")
        if self.app.watching and "watch" in names:
            names.remove("watch")
        return list(dict.fromkeys(names))

    def render_state(self):
        from .app import command_hints, plan_tab_line  # function-level: app imports this module
        from .card_kinds import plan_auto_approves
        if not self.ready:
            return
        app, view = self.app, self.view()
        project = app.snapshot.project if app.snapshot else app.controller.name
        self.query_one("#plan-title", Static).update(Text("Plan%s · %s" % (
            " r%s" % view.version if view else "", project)))
        lines = [line for line in (view.lines if view else ("Loading…",))]
        while lines and not lines[0]:
            lines.pop(0)
        if app.snapshot is not None and app.snapshot.panel and view is not None and view.kind == "observing":
            lines += [""] + list(app.snapshot.panel)
        notes = list(app.plan_lines) + app.block_lines()
        lines += [""] + notes if notes else []
        auto = plan_auto_approves(app.snapshot)  # C3 H3: at `auto` this screen never asks for /approve either
        lines = [line for line in (plan_tab_line(line, auto) for line in lines) if line is not None]  # K1d: no letter key
        width = max(self.query_one("#plan-scroll").scrollable_content_region.width, 20)
        self.query_one("#plan-body", Static).update(Text("\n".join(wrapped(lines, width))))
        progress = self.query_one("#plan-progress", Static)
        shown = [command_hints(line) for line in list(app.progress)[-6:]]  # K1d: a failure line names steps, not letters
        progress.display = bool(shown or app.watching)
        progress.update(Text("\n".join(wrapped(shown or ["The planner is working…"], max(self.size.width - 4, 20)))))
        state = (view.version, view.kind, view.status) if view else None
        self.sync_buttons(self.offered(), fresh=state != self.row_state)
        self.row_state = state
        self.show_keys()

    def show_keys(self):
        from .app import keys_bar  # function-level: app imports this module
        width = max(self.size.width - 2, 10)
        shown = ["tui_plan.move", "tui_plan.press", "tui_plan.back"]
        self.query_one("#plan-keys", Static).update(
            Text(self.app.modal_bar(width) or keys_bar("tui_plan", width, shown)))

    def action_scroll(self, how):
        getattr(self.query_one("#plan-scroll"), how)()

    def on_descendant_focus(self, _):
        self.parked = False
        if self.ready:
            self.show_keys()

    def action_back(self):
        """Esc goes back one level: an open details/notes block first, then the screen. P1a: closing the block
        returns the focus to the plan itself, off the buttons, so the Enter that follows presses none of them (not
        «revise»); Tab or an arrow reaches the first button again."""
        if self.app.plan_lines:
            self.app.plan_lines = ()
            self.parked = True
            self.set_focus(None)
            self.app.changed()
        elif self.from_main:
            self.app.leave_to_input()
        else:
            self.app.pop_screen()

    def action_tail(self):
        if self.allowed("tail"):
            self.app.show_tail()

    def allowed(self, name):
        if name not in self.offered():
            return False
        return True

    def action_run(self):
        if self.allowed("run"):
            self.app.run_plan(self.view())

    def action_renew(self):
        if self.allowed("renew"):
            self.app.renew_plan()

    def action_login(self):
        if self.allowed("login"):
            self.app.start_login(self.view())

    def action_watch(self):
        if self.allowed("watch"):
            self.app.watch_planner()

    def action_approve(self):
        if self.allowed("approve"):
            version = self.view().version
            self.app.decide("approve", version)

    def action_override(self):
        if self.allowed("override"):
            version = self.view().version
            self.app.push_screen(
                NoteScreen("Approve plan r%s despite the check?" % version, answer=True,
                           label="Reason (one line, at most 500 characters); the plan check stays on record."),
                lambda text: self.app.override_note(version, text))

    def action_reject(self):
        if self.allowed("reject"):
            version = self.view().version
            self.app.confirm("Reject proposal r%s? Nothing will run; the proposal stays as it is."
                             % version, lambda: self.app.decide("reject", version))

    def action_revise(self):
        if self.allowed("revise"):
            self.app.push_screen(NoteScreen(), self.app.revision_note)

    def action_info(self):
        if self.allowed("info"):
            self.app.show_details()


class SettingsScreen(ButtonScreen):
    bar = "tui_settings"
    row = "settings-buttons"
    BINDINGS = [Binding("up", "scroll('scroll_up')", "Scroll", show=False),
                Binding("down", "scroll('scroll_down')", "Scroll", show=False),
                Binding("pageup", "scroll('scroll_page_up')", "Scroll", show=False),
                Binding("pagedown", "scroll('scroll_page_down')", "Scroll", show=False)]
    ready = False
    placeholder = False

    def compose(self):
        from .app import LOG_LINES  # function-level: app imports this module
        yield Static("", id="settings-title", markup=False)
        with VerticalScroll(id="checks-pane", can_focus=False):
            yield Static("", id="checks", markup=False)
        yield RichLog(id="log", wrap=True, markup=False, max_lines=LOG_LINES)
        yield Static("", id="roles", markup=False)
        yield Horizontal(id="settings-buttons")
        yield Static("", id="settings-keys", markup=False)

    def on_mount(self):
        from .app import LOG_PLACEHOLDER  # function-level: app imports this module
        self.query_one("#checks-pane").border_title = "Readiness"
        self.query_one("#log").border_title = "Log"
        self.query_one("#roles").border_title = "Roles (model / effort)"
        self.query_one("#roles").display = False
        log = self.query_one("#log", RichLog)
        log.can_focus = False  # Tab and ←→ move between the buttons only
        self.placeholder = not self.app.log_lines
        for line in self.app.log_lines or (LOG_PLACEHOLDER,):
            self.write_line(log, line)
        self.ready = True
        self.render_state()

    def render_state(self):
        from .app import PLAIN_KEYS, button_hints, keys_bar  # function-level: app imports this module
        if not self.ready:
            return
        app = self.app
        project = app.snapshot.project if app.snapshot else app.controller.name
        self.query_one("#settings-title", Static).update(Text("Settings · " + project))
        rows = Text()
        if app.checks is None:
            rows.append("Checking…")
        for check in app.checks or ():
            if check.severity == "warn":
                # R-4: a warning keeps ok=True, so it is not a block: the same yellow `! ` marker everywhere and
                # the whole escaped doctor line, as an ok row shows, never the red block style or a fix key.
                rows.append("! ", style="yellow")
                rows.append(button_hints(plain_value(check.doctor)) + "\n")
            elif check.ok:
                rows.append("✓ ", style="green")
                # The pane scrolls, so the whole doctor line stays here, and L-3's full CODEX_HOME with it: it is
                # escaped as a header value is (L-2), never cleaned, so a legal path in a directory name keeps
                # every character — a newline or a tab included — and the full path stays readable, not a cut of it.
                rows.append(button_hints(plain_value(check.doctor)) + "\n")
            else:
                rows.append("! ", style="bold red")
                # L-3: a failed check keeps its whole text here too, never `summary`'s 256-character cut — a failed
                # configuration check carries the resolved CODEX_HOME in its detail (the error names the config
                # file it could not read) and the full path has to stay reachable in Settings. The text is escaped
                # as a header value is (L-2), so a legal control character of a directory name is shown, not lost.
                rows.append(button_hints(PLAIN_KEYS.sub("", plain_value(check.line))) + "\n")
                if check.detail:
                    rows.append("    " + button_hints(plain_value(check.detail)) + "\n", style="dim")
        if app.checking and app.checks is not None:
            rows.append("checking…", style="dim")
        profile = app.snapshot.profile if app.snapshot is not None else None
        if profile is not None:
            rows.append("\n\n" if rows.plain else "")
            rows.append("\n".join(profile.lines))
        rows.rstrip()
        self.query_one("#checks", Static).update(rows)
        roles = app.snapshot.roles if app.snapshot else ()
        self.query_one("#roles", Static).update(Text("\n".join("%-14s %s / %s" % r for r in roles) or "Roles are not loaded yet."))
        self.sync_buttons([name for name, available in (("setup", app.controller.install is not None),
                                                        ("login", app.controller.login is not None)) if available]
                          + ["recheck", "roles"] + (["profile"] if self.editable() else []))
        width = max(self.size.width - 2, 10)
        shown = ["tui_settings.move", "tui_settings.press", "tui_settings.back"]
        self.query_one("#settings-keys", Static).update(
            Text(self.app.modal_bar(width) or keys_bar("tui_settings", width, shown)))

    def on_resize(self, _):
        self.render_state()

    def editable(self):
        """«profile»: the accepted or postponed profile can be edited here; an undecided one is edited at the first
        start, a missing or broken one is repaired in its file."""
        profile = self.app.snapshot.profile if self.app.snapshot is not None else None
        return profile is not None and profile.state in ("accepted", "later") and profile.form is not None

    def write(self, line):
        log = self.query_one("#log", RichLog)
        if self.placeholder:
            self.placeholder = False
            log.clear()
        self.write_line(log, line)

    @staticmethod
    def write_line(log, line):
        from .app import button_hints  # function-level: app imports this module
        log.write(Text(button_hints(line)))

    def action_back(self):
        self.app.leave_to_input()

    def action_scroll(self, how):
        getattr(self.query_one("#checks-pane"), how)()

    def action_setup(self):
        self.app.start_setup()

    def action_login(self):
        self.app.start_login()

    def action_recheck(self):
        self.app.recheck()

    def action_profile(self):
        """«profile»: the profile editor on the values in effect; saving accepts a postponed profile and changes an
        accepted one in its file."""
        if not self.editable():
            return
        later = self.app.snapshot.profile.state == "later"

        def submit(changes, done):
            self.app.controller.decide_profile(True, done, changes) if later else \
                self.app.controller.edit_profile(changes, done)

        def closed(saved):
            if saved:
                self.app.request_refresh()
        self.app.push_screen(ProfileScreen(self.app.snapshot.profile.form, submit), closed)

    def action_roles(self):
        roles, log = self.query_one("#roles"), self.query_one("#log")
        roles.display = not roles.display
        log.display = not roles.display
