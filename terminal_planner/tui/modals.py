"""The modal screens of the full-screen shell: the `Modal` base, help, confirm, bootstrap, finishing, the note and
text forms, the run end screen and its journal title. The key-bar helpers (`keys_bar`, `bar_width`), the help text and
the header rule stay in `app.py`: this module imports them inside the methods that use them, because `app.py` imports
this module."""

from rich.text import Text
from textual.actions import SkipAction
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static, TextArea

from .. import catalog, process
from ..authority import NATIVE_EFFORTS
from . import strings
from .text import wrapped


class Modal(ModalScreen):
    """A modal over another screen: while it is on top, the key bar of the screen below shows the modal's keys
    (`key_bar`), not the keys of a screen that cannot be reached."""
    bar = ""  # catalog screen of the modal's keys

    def key_bar(self, width):
        from .app import keys_bar  # function-level: app imports this module
        return keys_bar(self.bar, width) if self.bar else ""

    def on_mount(self):
        self.app.call_later(self.app.changed)

    def on_unmount(self):
        try:
            self.app.call_later(self.app.changed)
        except Exception:  # the app is going away
            pass

    def action_move(self, step):
        """K1c1: Tab / ←→ move the focus between a modal's buttons (no letter key answers a modal)."""
        self.focus_next() if step > 0 else self.focus_previous()


class HelpScreen(Modal):
    BINDINGS = [Binding("escape", "dismiss", "Close")]
    bar = "tui_help"

    def __init__(self, *screens):
        super().__init__()
        self.screens_shown = screens or ("tui_input", "tui_panel")

    def compose(self):
        from .app import help_text  # function-level: app imports this module
        with VerticalScroll(id="help"):  # long key lists scroll on a small terminal
            yield Static(Text(help_text(*self.screens_shown, "tui_help")), id="help-body", markup=False)


class ConfirmScreen(Modal):
    """One yes/no question before a decision that cannot be taken back, answered with two buttons: the focus starts
    on «no» (`default_yes` False), Tab / ←→ move it, Enter presses the focused button, Esc is «no». No letter
    answers."""
    bar = "tui_confirm"
    default_yes = False
    BINDINGS = [Binding("escape", "answer(False)", "No"), Binding("left", "move(-1)", "Button", show=False),
                Binding("right", "move(1)", "Button", show=False)]

    def __init__(self, question):
        super().__init__()
        self.question = question

    def compose(self):
        from .app import keys_bar  # function-level: app imports this module
        with Vertical(id="confirm"):
            yield Static(Text(self.question + "\n\n" + keys_bar("tui_confirm", 56)), id="confirm-question",
                         markup=False)
            with Horizontal(id="confirm-buttons"):
                yield Button(catalog.label("tui_confirm.yes"), id="confirm-yes", compact=True)
                yield Button(catalog.label("tui_confirm.no"), id="confirm-no", compact=True)

    def on_mount(self):
        super().on_mount()
        self.query_one("#confirm-yes" if self.default_yes else "#confirm-no", Button).focus()

    def on_button_pressed(self, event):
        event.stop()
        self.action_answer(event.button.id == "confirm-yes")

    def action_answer(self, yes):
        self.dismiss(yes)


class BootstrapScreen(Modal):
    """The first-start choice of the project's process profile: the proposal and a button each for accept / later
    (no «later» when the profile is `present`); the focus starts on «accept». Nothing else dismisses it; ctrl+q
    quits without deciding."""
    bar = "tui_bootstrap"
    BINDINGS = [Binding("left", "move(-1)", "Button", show=False), Binding("right", "move(1)", "Button", show=False)]

    def __init__(self, view):
        super().__init__()
        self.view_lines = tuple(view.bootstrap)
        self.present = view.present
        self.form = None if view.present else getattr(view, "form", None)
        self.problem = ""
        self.deciding = False

    def compose(self):
        with Vertical(id="bootstrap"):
            with VerticalScroll(id="bootstrap-scroll"):
                yield Static(Text("\n".join(self.view_lines)), id="bootstrap-body", markup=False)
            with Horizontal(id="bootstrap-buttons"):
                yield Button(catalog.label("tui_bootstrap.accept"), id="bootstrap-accept", compact=True)
                if self.form is not None:
                    yield Button(catalog.label("tui_bootstrap.configure"), id="bootstrap-configure", compact=True)
                if not self.present:
                    yield Button(catalog.label("tui_bootstrap.later"), id="bootstrap-later", compact=True)
            yield Static("", id="bootstrap-keys", markup=False)

    def on_mount(self):
        super().on_mount()
        self.query_one("#bootstrap-accept", Button).focus()
        self.render_state()

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == "bootstrap-configure":
            self.action_configure()
        else:
            self.action_decide(event.button.id == "bootstrap-accept")

    def key_bar(self, width):
        from .app import keys_bar  # function-level: app imports this module
        offered = (["tui_bootstrap.accept"] + ([] if self.form is None else ["tui_bootstrap.configure"])
                   + ([] if self.present else ["tui_bootstrap.later"]) + ["tui_bootstrap.quit"])
        return keys_bar("tui_bootstrap", width, offered)

    def render_state(self):
        from .app import keys_bar, bar_width  # function-level: app imports this module
        if not self.is_attached or not self.query("#bootstrap-body"):  # a Resize before compose paints nothing
            return
        body = list(self.view_lines) + (["", "Not done: " + self.problem] if self.problem else [])
        self.query_one("#bootstrap-body", Static).update(Text("\n".join(body)))
        keys = self.query_one("#bootstrap-keys", Static)
        keys.update(Text(self.key_bar(bar_width(keys, max(self.size.width - 2, 10)))))

    def on_resize(self, _):
        self.render_state()

    def action_configure(self):
        """«configure»: the editor on the proposal; saving it accepts the profile with the owner's values, so this
        screen closes with it. Cancelling the editor leaves this choice open."""
        if self.deciding or self.form is None:
            return

        def submit(changes, done):
            self.app.controller.decide_profile(True, done, changes)

        def closed(saved):
            if saved:
                self.dismiss(None)
                self.app.request_refresh()
        self.app.push_screen(ProfileScreen(self.form, submit), closed)

    def action_decide(self, accept):
        if self.deciding or (not accept and self.present):
            return
        self.deciding = True

        def decided(outcome, error):
            self.deciding = False
            if error:
                self.problem = error
                self.render_state()
                return
            self.dismiss(None)
            self.app.request_refresh()
        self.app.controller.decide_profile(accept, self.app.deliver(decided))


class ProfileScreen(Modal):
    """The editor of the process profile: autonomy, parallel runs, the merge gate and, per role, the model (an input,
    prefilled) and the effort (buttons). It starts on `form` (`process.Form`, the values in effect) and «save»
    hands only what the owner changed to `submit(changes, done)`; a refusal comes back as the reason, shown here
    while the editor stays open and nothing is written. «cancel» and Esc close it unchanged. The picked button of a
    group carries «● » (apart from the focus); the keys are the one hint line at the bottom (the modal's key bar).
    A value in the file outside the offered ones shows as a button of its own. Without a check the merge gate offers only «ask»,
    with the reason. Dismisses with True once saved, else False."""
    bar = "tui_profile"
    LEVELS = tuple(process.LEVEL_NAMES.items())
    RUNS = (1, 2, 3)
    MERGES = (("required", "automatic on green checks"), ("off", "ask"))
    NO_CHECKS = "There are no checks, so merging automatically on green checks is unavailable."
    EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")
    MARK = "● "
    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "save", "Save", show=False),
                Binding("space", "pick", "Select", show=False),
                Binding("left", "move(-1)", "Button", show=False), Binding("right", "move(1)", "Button", show=False)]
    DEFAULT_CSS = """
    ProfileScreen { align: center middle; }
    ProfileScreen #profile { width: 96%; height: 90%; border: round $accent; background: $surface; padding: 0 1; }
    ProfileScreen #profile-scroll { height: 1fr; }
    ProfileScreen .profile-head { height: 1; margin-top: 1; text-style: bold; }
    ProfileScreen .profile-row { height: 1; }
    ProfileScreen .profile-row Button { margin-right: 1; }
    ProfileScreen .profile-row Button.-chosen { text-style: bold; }
    ProfileScreen .profile-role { width: 12; }
    ProfileScreen .profile-model { width: 1fr; }
    ProfileScreen .profile-efforts { margin-left: 12; }
    ProfileScreen .profile-note { height: auto; color: $text-muted; }
    ProfileScreen #profile-problem { height: auto; color: $error; }
    ProfileScreen #profile-buttons { height: 1; margin-top: 1; }
    ProfileScreen #profile-buttons Button { margin-right: 2; }
    """

    def __init__(self, form, submit):
        super().__init__()
        self.form, self.submit = form, submit
        self.chosen = {"level": form.level, "max_runs": form.max_runs, "merge": form.merge}
        self.chosen.update(("effort." + role, effort) for role, _, effort in form.roles)
        self.problem = ""
        self.saving = False
        self.texts = {}  # button id -> its text without the mark

    def efforts(self):
        return [e for e in self.EFFORT_ORDER if e in NATIVE_EFFORTS] + sorted(NATIVE_EFFORTS - set(self.EFFORT_ORDER))

    def choices(self, group, options):
        """One row of buttons for `group`; the chosen one is marked (`-chosen`, «● »). A button's name is `group=value`."""
        with Horizontal(classes="profile-row"):
            for value, text in options:
                yield self.choice(group, value, text, "profile-%s-%s" % (group.replace(".", "-"), value))

    def choice(self, group, value, text, button_id):
        button = Button(text, id=button_id, name="%s=%s" % (group, value), compact=True)
        self.texts[button_id] = text
        self.mark(button, self.chosen[group] == value)
        return button

    def mark(self, button, chosen):
        button.label = (self.MARK if chosen else "") + self.texts[button.id]
        button.set_class(chosen, "-chosen")

    def compose(self):
        form = self.form
        with Vertical(id="profile"):
            with VerticalScroll(id="profile-scroll"):
                if form.level is not None:
                    yield Static("Autonomy", classes="profile-head", markup=False)
                    yield from self.choices("level", self.LEVELS)
                    yield Static("In parallel", classes="profile-head", markup=False)
                    runs = list(self.RUNS) + ([form.max_runs] if form.max_runs not in self.RUNS else [])
                    yield from self.choices("max_runs", [(n, str(n)) for n in runs])
                yield Static("Merge", classes="profile-head", markup=False)
                yield from self.choices("merge", [m for m in self.MERGES if form.checks or m[0] == "off"])
                if not form.checks:
                    yield Static(self.NO_CHECKS, classes="profile-note", markup=False)
                yield Static("Roles: model and effort", classes="profile-head", markup=False)
                for role, model, _ in form.roles:
                    with Horizontal(classes="profile-row"):
                        yield Static(role, classes="profile-role", markup=False)
                        yield Input(model, id="profile-model-" + role, classes="profile-model", compact=True)
                    with Horizontal(classes="profile-row profile-efforts"):
                        for effort in self.efforts():
                            yield self.choice("effort." + role, effort, effort, "profile-effort-%s-%s" % (role, effort))
            yield Static("", id="profile-problem", markup=False)
            with Horizontal(id="profile-buttons"):
                yield Button(catalog.label("tui_profile.save"), id="profile-save", compact=True)
                yield Button(catalog.label("tui_profile.cancel"), id="profile-cancel", compact=True)

    def on_mount(self):
        super().on_mount()
        first = self.query(".profile-row Button.-chosen")
        (first.first() if first else self.query_one("#profile-save", Button)).focus()
        self.render_state()

    def on_resize(self, _):
        self.render_state()

    def render_state(self):
        if not self.is_attached or not self.query("#profile-problem"):  # a Resize before compose paints nothing
            return
        self.query_one("#profile-problem", Static).update(Text("Not saved: " + self.problem if self.problem else ""))

    def on_button_pressed(self, event):
        event.stop()
        button = event.button
        if button.id == "profile-save":
            self.action_save()
        elif button.id == "profile-cancel":
            self.action_cancel()
        elif button.name:
            group, _, value = button.name.partition("=")
            self.chosen[group] = int(value) if group == "max_runs" else value
            for other in self.query(".profile-row Button"):
                if other.name and other.name.partition("=")[0] == group:
                    self.mark(other, other is button)

    def changes(self):
        """What the owner changed against `form`: {"level", "max_runs", "merge", "roles": {role: binding}}, only the
        parts that differ. A role is sent whole (model and effort) when either differs."""
        form, found = self.form, {}
        for key in ("level", "max_runs", "merge"):
            if self.chosen[key] != getattr(form, key):
                found[key] = self.chosen[key]
        roles = {}
        for role, model, effort in form.roles:
            now = {"model": self.query_one("#profile-model-" + role, Input).value.strip(),
                   "effort": self.chosen["effort." + role]}
            if now != {"model": model, "effort": effort}:
                roles[role] = now
        if roles:
            found["roles"] = roles
        return found

    def action_pick(self):
        """Space picks the focused button, as Enter does (Textual binds only Enter); in the model field it types."""
        if not isinstance(self.focused, Button):
            raise SkipAction
        self.focused.press()

    def action_save(self):
        if self.saving:
            return
        self.saving = True

        def saved(outcome, error):
            self.saving = False
            if error:
                self.problem = error
                self.render_state()
                return
            self.dismiss(True)
        self.submit(self.changes(), self.app.deliver(saved))

    def action_cancel(self):
        if not self.saving:
            self.dismiss(False)


class LanguageScreen(Modal):
    """i6: the language chooser. One row per language of `strings.OFFERED`, in its own order, each
    named by its `display_name`, the marked one reversed. ↑/↓ move the mark, enter — or a click on a row — picks
    the marked language and dismisses with its code; esc keeps the language in effect and dismisses with None,
    storing it when nothing was stored yet, so the first-run chooser is asked once. `preselect` starts the mark
    on a code (the default is the language in effect: the locale default on a first start). The modal shows no
    key bar (`bar` empty, the `Modal` default): the bar needs a catalog screen, and this chooser's keys are the
    arrows and enter."""
    BINDINGS = [Binding("up", "move(-1)", "Up", show=False), Binding("down", "move(1)", "Down", show=False),
                Binding("enter", "pick", "Select", show=False), Binding("escape", "keep", "Keep", show=False)]

    def __init__(self, preselect=None):
        super().__init__()
        self.codes = list(strings.OFFERED)
        self.index = self.codes.index(preselect) if preselect in self.codes else self.codes.index(strings.language())

    def compose(self):
        with Vertical(id="language") as pane:
            for code in self.codes:
                yield Static(strings.display_name(code), id="language-" + code, classes="language-row",
                             markup=False)
        pane.border_title = strings.text("note.language_prompt")

    def on_mount(self):
        super().on_mount()
        self.mark()  # after the rows are mounted: `compose` runs before they exist, `query_one` would miss them

    def mark(self):
        """Reverses exactly the marked row's own name (`zplan.tcss`), the others plain."""
        for code in self.codes:
            self.query_one("#language-" + code, Static).set_class(code == self.codes[self.index], "-selected")

    def action_move(self, delta):
        self.index = (self.index + delta) % len(self.codes)
        self.mark()

    def action_pick(self):
        """Enter (or a click): the marked language is the chooser's answer; the caller stores it."""
        self.dismiss(self.codes[self.index])

    def action_keep(self):
        """Esc: keep the language in effect, storing it when nothing was stored yet (`language()` is then the
        locale default), so the first-run chooser is asked once."""
        strings.set_language(strings.language())
        self.dismiss(None)

    def on_click(self, event):
        """The mouse path: a click on one language's own row marks and picks it. Any other click is left alone."""
        row = getattr(event, "widget", None)
        code = getattr(row, "id", "")
        if isinstance(code, str) and code.startswith("language-") and code[len("language-"):] in self.codes:
            self.index = self.codes.index(code[len("language-"):])
            self.mark()
            self.action_pick()


class FinishingScreen(ModalScreen):
    """Shown once the owner quits during a mutating job: the job is never cut, the app exits when it ends."""

    def compose(self):
        from .app import QUIT_WAITS  # function-level: app imports this module
        # i6: `QUIT_WAITS` holds a catalog id now, so the one line this modal shows follows the chosen language
        # (`strings.text`); the modal itself stays outside i6's scope, only the text the task lists moves.
        yield Static(Text(strings.text(QUIT_WAITS)), id="confirm", markup=False)


class NoteScreen(Modal):
    """Free text for the plan revision, an answer or a new-attempt note: sent only by the send button after the
    field (Tab reaches it, Enter presses it); Escape closes it unchanged. `answer` selects the answer/note key bar instead of the plan-revision one; `bar`
    names another catalog screen (the new-attempt form names its confirm key), `label` the field.

    `text` prefills the field and `note` shows a short message above it: an answer draft opens the same form with
    the draft's text, and a refusal (or an empty send) is shown in it again with that text kept, so the draft stays
    editable and copyable after a failed send."""
    BINDINGS = [Binding("escape", "close", "Back", priority=True)]

    def __init__(self, title="What to change in the plan", answer=False, bar=None, label="", text="", note="", enter=False):
        super().__init__()
        self.enter = enter
        self.title_text, self.answer, self.label = title, answer, label
        self.text, self.note = text, note
        self.bar = bar or ("tui_answer" if answer else "tui_note")

    def compose(self):
        from .app import command_hints  # function-level: app imports this module
        with Vertical(id="note"):
            yield Static(self.title_text, id="note-title", markup=False)
            if self.label:
                yield Static(self.label, id="note-label", markup=False)
            if self.note:
                yield Static(command_hints(self.note), id="note-note", markup=False)  # K1d: a refusal names steps, not letters
            yield TextArea(self.text, id="note-text", show_line_numbers=False)
            yield Button(catalog.label(self.bar + ".send"), id="note-send", compact=True)
            yield Static("", id="note-keys", markup=False)

    def on_mount(self):
        self.query_one("#note-text").focus()
        self.show_keys()

    def on_resize(self, _):
        self.show_keys()

    def show_keys(self):
        """The bar of this form, cut to the width the bar widget really has (R-1)."""
        from .app import keys_bar, bar_width  # function-level: app imports this module
        keys = self.query_one("#note-keys", Static)
        keys.update(Text(keys_bar(self.bar, bar_width(keys, 70))))

    def action_send(self):
        self.dismiss(self.query_one("#note-text", TextArea).text.strip())

    def on_button_pressed(self, event):
        event.stop()
        self.action_send()

    def on_key(self, event):
        """`enter=True` (a card-origin note): enter sends; esc still cancels through the binding."""
        if self.enter and event.key == "enter":
            event.stop()
            event.prevent_default()
            self.action_send()

    def action_close(self):
        self.dismiss(None)


class TextScreen(Modal):
    """A scrollable read-only text: the exported result's diff or the details (outcome first, diagnostics last)."""
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, title, lines, diff=False):
        super().__init__()
        self.title_text, self.lines, self.diff = title, tuple(lines), diff
        self.bar = "tui_diff" if diff else "tui_details"

    def compose(self):
        with Vertical(id="text"):
            yield Static(self.title_text, id="text-title", markup=False)
            with VerticalScroll(id="text-scroll"):
                yield Static(Text("\n".join(self.lines)), id="text-body", markup=False)
            yield Static("", id="text-keys", markup=False)

    def on_mount(self):
        self.query_one("#text-scroll").focus()
        self.show_keys()

    def on_resize(self, _):
        self.show_keys()

    def show_keys(self):
        """The bar of this text screen, cut to the width the bar widget really has (R-1)."""
        from .app import keys_bar, bar_width  # function-level: app imports this module
        keys = self.query_one("#text-keys", Static)
        keys.update(Text(keys_bar(self.bar, bar_width(keys, 70))))


def journal_title(end):
    """The title of one attempt's stored-journal screen (the result modal's [i]); the same shape [e] uses."""
    return "%s %s · attempt %s" % (catalog.JOURNAL, end.milestone, end.attempt)


class RunScreen(Modal):
    """The end of one attempt: the outcome and only the actions the delivery service allows for it, each a button
    (K1c3): Tab / ←→ move the focus, Enter presses the focused button, Esc closes, ↑↓ PgUp PgDn scroll the body; no
    letter or `?` does anything. The view is replaced (never acted on) when the attempt, run or revision moved
    underneath it.

    The recoverable failed end screen presents the delivery catalog's own offered actions (A1's «continue»,
    «new attempt», «plan», in that order) and its own back, the same IDs the line UI uses; every other end screen
    shows this modal's `tui_run` buttons. After the actions come «journal» when the attempt has a native run and
    «details»."""
    BINDINGS = [Binding("escape", "close", "Close"), Binding("left", "move(-1)", "Button", show=False),
                Binding("right", "move(1)", "Button", show=False),
                Binding("up", "scroll('scroll_up')", "Scroll", show=False),
                Binding("down", "scroll('scroll_down')", "Scroll", show=False),
                Binding("pageup", "scroll('scroll_page_up')", "Scroll", show=False),
                Binding("pagedown", "scroll('scroll_page_down')", "Scroll", show=False)]
    # The service action names (EndAction.name) of the offered owner actions -> the catalog action IDs of this modal.
    IDS = {"merge": "tui_run.merge", "diff": "tui_run.diff", "accept": "tui_run.accept", "answer": "tui_run.answer",
           "new_attempt": "tui_run.attempt", "plan": "tui_run.plan", "resume": "tui_run.resume",
           "check": "tui_run.check", "leave": "tui_run.leave"}
    # The one state whose end screen shows the delivery catalog's own action IDs (and back) instead of `tui_run`'s.
    DELIVERY_KEYS_STATE = "failed_recoverable"

    def __init__(self, end, note=""):
        super().__init__()
        self.end, self.note = end, note
        self.ready = False
        self.shown = None  # the (button name, catalog ID) pairs the row was last asked to show

    def compose(self):
        with Vertical(id="run"):
            yield Static("", id="run-title", markup=False)
            with VerticalScroll(id="run-scroll", can_focus=False):
                yield Static("", id="run-body", markup=False)
            yield Horizontal(id="run-buttons")
            yield Static("", id="run-keys", markup=False)

    def on_mount(self):
        super().on_mount()
        self.ready = True
        self.render_state()

    def on_resize(self, _):
        self.render_state()

    def set_end(self, end, note=""):
        self.end, self.note = end, note
        self.render_state()

    def offered(self):
        return [name for name in self.end.names if name in self.IDS]

    def buttons(self):
        """The row as (button name, catalog action ID), in order: the offered service actions (the recoverable
        failed end uses the delivery catalog's own IDs, so the two UIs name the same action the same way), the
        activity tail when it has one, that state's own delivery back, and the stored journal. A button's name is
        the service action it runs, or `tail`, `back` (close) and `details`."""
        if self.end.state == self.DELIVERY_KEYS_STATE:
            pairs = [(a.name, a.id) for a in self.end.actions]
        else:
            pairs = [(name, self.IDS[name]) for name in self.offered()]
        if self.tailable():
            pairs.append(("tail", "tui_run.tail"))
        if self.end.state == self.DELIVERY_KEYS_STATE:
            pairs.append(("back", self.end.back))
        return pairs + [("details", "tui_run.details")]

    def action_ids(self):
        """The catalog action IDs of the buttons, in row order."""
        return [action_id for _, action_id in self.buttons()]

    def tailable(self):
        """The activity tail is offered for an attempt that ran and has a native run (failed or still going)."""
        token = self.end.token
        return token is not None and token.run_id is not None and token.status in ("failed", "running", "stopping")

    def key_bar(self, width):
        from .app import keys_bar  # function-level: app imports this module
        return keys_bar("tui_run", width, ["tui_run.move", "tui_run.press", "tui_run.back"])

    def next_line(self):
        """`Next:` (R-3): the buttons of the offered actions by their labels, and the keys that work them."""
        labels = [catalog.label(i) for i in self.action_ids()]
        return "%s buttons %s. %s — select, %s — press, %s — close." % (
            catalog.NEXT, ", ".join("«%s»" % label for label in labels), *(
                catalog.action("tui_run." + n).key.capitalize() for n in ("move", "press", "back")))

    def journal(self):
        """The stored journal entries of exactly this attempt (never a native log read); the empty state line
        when the attempt carries none (R-3)."""
        return self.end.journal or (catalog.JOURNAL_EMPTY,)

    def render_state(self):
        from .app import bar_width, command_hints  # function-level: app imports this module
        if not self.ready:
            return
        end = self.end
        self.query_one("#run-title", Static).update(Text("%s · %s" % (end.milestone, end.title)))
        lines = [command_hints(line) for line in end.lines] + ["", catalog.JOURNAL + ":"] + list(self.journal()) \
            + ["", self.next_line()]
        if self.note:
            lines += ["", command_hints(self.note)]
        width = max(self.query_one("#run-scroll").scrollable_content_region.width, 20)
        body = "\n".join(wrapped(lines, width))
        keys = self.query_one("#run-keys", Static)
        keys.update(Text(self.key_bar(bar_width(keys, max(self.size.width * 9 // 10 - 4, 20)))))
        self.sync_buttons(self.buttons())
        self.fit_body(self.body_rows(Text(body), width))

    def sync_buttons(self, pairs):
        """Rebuild the row when the offered buttons changed: the focus stays on the same action if it is still
        offered, else goes to the first button."""
        pairs = tuple(pairs)
        if pairs != self.shown:
            self.shown = pairs
            self.call_later(self.rebuild_buttons, pairs)

    async def rebuild_buttons(self, pairs):
        row = self.query_one("#run-buttons")
        focused = self.focused
        keep = focused.name if isinstance(focused, Button) and focused.parent is row else None
        await row.remove_children()
        buttons = [Button(catalog.label(action_id), id="run-buttons-" + name, name=name, compact=True)
                   for name, action_id in pairs]
        await row.mount(*buttons)
        target = next((b for b in buttons if b.name == keep), buttons[0] if buttons else None)
        if target is not None and (keep is not None or not isinstance(self.focused, Button)):
            target.focus()

    def body_rows(self, body, width):
        """The physical rows `#run-body` really draws for `body` at `width` terminal cells (R-3/A-3): the widget's
        own measurement of its content, so terminal-cell wrapping (a wide glyph counts two) and embedded newlines
        are each the rows they draw, not the logical lines they came from."""
        widget = self.query_one("#run-body", Static)
        widget.update(body)
        widget.clear_cached_dimensions()  # the cached height belongs to the previous content
        return widget.get_content_height(self.size, self.size, width)

    def fit_body(self, content_rows):
        """Constrain the modal to the MainScreen body below the header on a supported terminal (R-3): its height
        is the wrapped content's physical rows plus title, buttons and keys and the border, capped at the available body
        height (the overflow scrolls). Below 80x24 the previous centred 90%x80% box is kept."""
        from .app import screen_header_rows  # function-level: app imports this module
        run = self.query_one("#run")
        wide = self.size.width >= 80 and self.size.height >= 24
        self.set_class(wide, "body-region")
        if wide:
            top = screen_header_rows(self.size.width, self.size.height)
            room = max(self.size.height - top, 3)
            run.styles.height = min(content_rows + 1 + 1 + 1 + 2, room)
            run.styles.margin = (top, 0, 0, 0)
        else:
            run.styles.height = "80%"
            run.styles.margin = 0

    def action_close(self):
        self.dismiss(None)

    def on_key(self, event):
        """P1a: the screen has no text field, so a printable key is not dropped: it is typed into the chat input
        (`forward_to_chat`) while this screen stays open and keeps the focus. Space and Enter stay the focused
        button's."""
        if event.is_printable and not event.character.isspace():
            event.stop()
            event.prevent_default()
            self.app.forward_to_chat(event.character)

    def action_scroll(self, how):
        getattr(self.query_one("#run-scroll"), how)()

    def on_button_pressed(self, event):
        event.stop()
        name = event.button.name
        if name == "back":
            self.action_close()
        elif name == "tail":
            self.action_tail()
        elif name == "details":
            self.action_journal()
        else:
            self.action_act(name)

    def action_act(self, name):
        """An owner action of the shown end, only while the delivery service still offers it."""
        if name in self.end.names:
            self.app.modal_action(self, name)

    def action_journal(self):
        """«details»: the stored journal entries of this attempt in the shared TextScreen, with or without a native log;
        closing it returns to this modal."""
        self.app.push_screen(TextScreen(journal_title(self.end), self.journal()))

    def action_tail(self):
        if self.tailable():
            self.app.tail_modal(self)
