"""D1 public reference: help for every command, `?` per screen, the catalog's coverage in both directions
(finite sets derived from the code, never from message literals), the generated docs/REFERENCE.md tables, and the
`unknown_error` fallback. Fixture engine and driver only: no provider, no network, temporary HOME/XDG."""

import ast
import contextlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner import authority, catalog, cli, commands, runs
from terminal_planner.authority import Blocked
from terminal_planner.cli import Terminal, session
from terminal_planner.runs import FIXTURE_OUTCOMES, FixtureDriver
from test_setup import Steps
import test_tui
from test_ux import GOAL, Counting, UxTest
from tui_support import HAVE_TEXTUAL, screen_text

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "terminal_planner"
REFERENCE = ROOT / "docs" / "REFERENCE.md"
ESC = "\x1b"


# Code facts: parsed once, shared by the coverage tests. ---------------------------------------------------------

def sources(exclude=("catalog.py",)):
    return {path: ast.parse(path.read_text(encoding="utf-8")) for path in sorted(PACKAGE.rglob("*.py"))
            if path.name not in exclude}


def call_name(node):
    return node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)


def strings(tree):
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def literal(node):
    return node.value if isinstance(node, ast.Constant) else None


FAMILY_ROOTS = ("Blocked", "PersistenceError")


def class_families():
    """name -> effective class-level family (None when no class on its path sets one) for every class that
    transitively derives from a family root, with inherited defaults resolved."""
    classes = {}
    for tree in sources().values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                own = "<unset>"
                for item in node.body:
                    if isinstance(item, ast.Assign) and any(getattr(t, "id", None) == "family" for t in item.targets):
                        own = literal(item.value)
                bases = [b.id if isinstance(b, ast.Name) else getattr(b, "attr", None) for b in node.bases]
                classes[node.name] = (bases, own)

    def effective(name, seen=()):
        if name in FAMILY_ROOTS and classes.get(name, (0, "<unset>"))[1] == "<unset>":
            return True, None
        if name not in classes or name in seen:
            return False, None
        bases, own = classes[name]
        if own != "<unset>":
            return True, own
        for base in bases:
            derived, family = effective(base, seen + (name,))
            if derived:
                return True, family
        return False, None

    found = {}
    for name, (bases, own) in classes.items():
        derived, family = effective(name)
        if derived and (name in FAMILY_ROOTS or any(effective(b)[0] for b in bases)):
            found[name] = family
    return found


def readiness_ids():
    """The readiness item ids setup.py can yield: the first argument of every `item("<id>", ...)` call."""
    found = set()
    for path, tree in sources().items():
        if path.name != "setup.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node) == "item" and node.args and literal(node.args[0]):
                found.add(node.args[0].value)
    return found


def raise_sites():
    """(file, line, class, family literal | None | '<expr>') of every call of an exception class that carries a
    family, in the product code."""
    families = class_families()
    sites = []
    for path, tree in sources().items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or call_name(node) not in families:
                continue
            given = {k.arg: k.value for k in node.keywords}.get("family")
            sites.append((path.name, node.lineno, call_name(node),
                          None if given is None else (literal(given) or "<expr>")))
    return sites


def run_zplan(home, *argv, path=""):
    environment = {"PATH": path, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
                   "XDG_CONFIG_HOME": str(home / "config"), "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONUTF8": "1", "LANG": "C.UTF-8", "TERM": "xterm-256color"}
    return subprocess.run([sys.executable, "-m", "terminal_planner.cli", *argv], capture_output=True, text=True,
                          env=environment, cwd=str(home), timeout=60)


# A1: help ----------------------------------------------------------------------------------------------------

class HelpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()

    def test_top_help_names_every_command_with_its_purpose(self):
        for argv in (["--help"], ["-h"], ["help"]):
            with self.subTest(argv):
                result = run_zplan(self.home, *argv)
                self.assertEqual(result.returncode, 0, result.stderr)
                for item in commands.COMMANDS:
                    self.assertIn(item.purpose, result.stdout)
                    if item.name != commands.START:
                        self.assertRegex(result.stdout, r"(?m)^  %s\s" % item.name)
                self.assertNotIn(ESC, result.stdout)

    def test_every_command_has_usage_flags_and_one_to_three_examples_on_both_routes(self):
        for item in commands.COMMANDS:
            with self.subTest(item.name):
                self.assertTrue(1 <= len(item.examples) <= 3, item.examples)
                routes = [["help", item.name]]
                routes.append(["--help"] if item.name == commands.START else [item.name, "--help"])
                texts = []
                for argv in routes:
                    result = run_zplan(self.home, *argv)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    texts.append(result.stdout)
                if item.name != commands.START:
                    self.assertEqual(texts[0], texts[1])
                text = texts[0]
                self.assertIn(item.usage, text)
                self.assertIn("Examples:", text)
                for example in item.examples:
                    self.assertIn(example, text)
                for flag in commands.flags_of(item.name):
                    self.assertIn(commands.flag_text(flag), text)

    def test_default_start_help_covers_plain_project_and_fixture(self):
        text = run_zplan(self.home, "help", "start").stdout
        for flag in ("--plain", "--project", "--fixture"):
            self.assertIn(flag, text)
            self.assertTrue(any(flag in example for example in commands.command(commands.START).examples), flag)

    def test_help_needs_no_tools_login_project_or_model(self):
        # Empty PATH (no git, no node, no codex), a bare HOME and a working directory that is no Git project.
        for argv in (["help"], ["--help"], ["help", "setup"], ["doctor", "--help"], ["login", "--help"],
                     ["roles", "--help"], ["status", "--help"], ["help", "start"]):
            with self.subTest(argv):
                result = run_zplan(self.home, *argv, path="")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.strip())
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), [])  # help wrote nothing

    def test_unknown_topic_fails_with_the_list_of_commands(self):
        result = run_zplan(self.home, "help", "nosuch")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        for name in commands.NAMES:
            self.assertIn(name, result.stderr)

    def test_parser_and_help_metadata_are_the_same_set(self):
        parser = cli.build_parser()
        options = {name for action in parser._actions for name in action.option_strings}
        documented = {name for flag in commands.FLAGS for name in flag.names}
        self.assertEqual(options | {"-h", "--help"}, documented)
        positional = next(a for a in parser._actions if not a.option_strings)
        self.assertEqual(tuple(positional.choices), commands.NAMES)


# A1: `?` in the plain UI ----------------------------------------------------------------------------------------

def menu_keys(line):
    return set(re.findall(r"\[([^\]]+)\]", line))


class PlainHelpTests(UxTest):
    def blocks(self, output):
        """[(title, keys of the menu shown just before `?`, keys listed by the help)] for every `?` answer."""
        lines, found = output.splitlines(), []
        for index, line in enumerate(lines):
            if "Keys · " not in line:  # the prompt has no newline, so the help starts on its line
                continue
            line = line[line.index("Keys · "):]
            menu = next(l for l in reversed(lines[:index]) if re.match(r"\[\S+\] ", l))
            listed = set()
            for entry in lines[index + 1:]:
                if not entry.startswith("  ["):
                    break
                listed |= set(re.match(r"  \[([^\]]+)\]", entry).group(1).split(" / "))
            found.append((line[len("Keys · "):], menu_keys(menu), listed))
        return found

    def test_question_mark_lists_the_keys_of_the_screen_just_shown(self):
        output, _ = self.fixture("?", "p", GOAL, "", "?", "q", "q")
        blocks = self.blocks(output)
        self.assertEqual([title for title, _, _ in blocks],
                         [catalog.SCREENS["home"].title, catalog.SCREENS["goal"].title])
        for title, shown, listed in blocks:
            with self.subTest(title):
                self.assertTrue(shown)
                self.assertEqual(listed, shown)

    def test_every_end_screen_lists_exactly_the_keys_it_offers_and_each_key_is_wired(self):
        seen = {}
        original = cli.App.choose

        def choose(app, menu, keys):
            ids = getattr(menu, "ids", ())
            if ids:
                letters = {catalog.action(i).key for i in ids if len(catalog.action(i).key) == 1}
                seen.setdefault(catalog.action(ids[0]).screen, []).append((letters, set(keys)))
            return original(app, menu, keys)

        shutil_state = self.state
        with patch.object(cli.App, "choose", choose):
            for outcome in FIXTURE_OUTCOMES:
                with self.subTest(outcome):
                    output, _ = self.fixture("p", GOAL, "", "g", "a", "g", "y", "?", "o", "?", "q", "q", outcome=outcome)
                    blocks = self.blocks(output)
                    self.assertTrue(blocks, output[-600:])
                    title, shown, listed = blocks[-1]
                    self.assertEqual(listed, shown, title)
                    shutil.rmtree(shutil_state, ignore_errors=True)
        self.assertTrue({"home", "plan", "awaiting_merge", "needs_owner", "blocked", "failed_recoverable",
                         "failed"} <= set(seen), sorted(seen))
        for screen, entries in seen.items():
            for letters, accepted in entries:
                with self.subTest(screen):
                    # The menu offers a key exactly when a handler answers it (q is always "back").
                    self.assertEqual(letters - {"q"}, accepted - {"q"})


# A1: `/help` in the full-screen shell ---------------------------------------------------------------------------

@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is required")
class TuiHelpTests(test_tui.ShellTest):
    async def test_help_lists_the_commands_of_the_main_screen(self):
        """K1a: the main screen has no `?`/F1/Ctrl+S — `/help` opens the key help of `tui_input` and `tui_panel`, whose
        keys are the `/` commands. (K1c2: Settings has no `?` either; its buttons are its keys.)"""
        async with self.shell(size=(140, 40)) as pilot:
            await self.loaded(pilot)
            await pilot.press("f1", "question_mark")  # no binding on the main screen
            await pilot.pause()
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")
            await self.command(pilot, "/help")
            text = screen_text(self.app)
            for screen in ("tui_input", "tui_panel"):
                self.assertIn(catalog.SCREENS[screen].title, text)
                for found in catalog.ACTIONS.values():
                    if found.screen == screen:
                        self.assertIn(found.hint, text, found.id)
            await pilot.press("escape")


# A2: coverage in both directions --------------------------------------------------------------------------------

class VocabularyTests(unittest.TestCase):
    def test_plan_statuses_are_the_catalog_and_each_is_used(self):
        self.assertEqual(set(catalog.PLAN_STATUS), set(authority.PLAN_STATUSES))
        # The tuple itself is one occurrence, so a second one in the code that sets the status is the use.
        counts = {}
        for path, tree in sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value in authority.PLAN_STATUSES:
                    counts[node.value] = counts.get(node.value, 0) + 1
        for status in authority.PLAN_STATUSES:
            self.assertGreater(counts.get(status, 0), 1, status)

    def test_run_vocabulary_is_the_catalog_and_the_cli_wording(self):
        self.assertEqual(set(catalog.RUN_STATUS), set(runs.STATUSES))
        self.assertEqual(set(catalog.OUTCOME), set(runs.OUTCOMES))
        self.assertEqual(set(catalog.DELIVERY), set(runs.DELIVERIES))
        self.assertEqual(set(catalog.MILESTONE_STATE), set(runs.MILESTONE_STATES))
        self.assertEqual(set(cli.RUN_STATUS), set(runs.STATUSES))
        self.assertEqual(set(cli.OUTCOME) - {None}, set(runs.OUTCOMES))
        self.assertEqual(set(cli.DELIVERY), set(runs.DELIVERIES))
        self.assertEqual(set(cli.STATE_TEXT) & set(runs.MILESTONE_STATES), set(cli.STATE_TEXT))

    def test_run_state_reaches_exactly_the_milestone_states_after_an_attempt(self):
        reached = set()
        for status in runs.STATUSES:
            for outcome in (None,) + tuple(runs.OUTCOMES):
                for recoverable in (False, True):
                    for delivery in runs.DELIVERIES:
                        reached.add(runs.run_state({"status": status, "outcome": outcome, "recoverable": recoverable,
                                                    "delivery": delivery}))
        self.assertEqual(reached, set(runs.MILESTONE_STATES) - {"waiting", "ready"})
        self.assertTrue({"waiting", "ready"} <= set(runs.MILESTONE_STATES))

    def test_planner_causes_are_catalog_families(self):
        from terminal_planner import engine
        causes = {name for name, _ in engine.CAUSES}
        self.assertEqual(set(cli.PLANNER_FAMILY) - {None}, causes)
        for family in cli.PLANNER_FAMILY.values():
            self.assertIn(family, catalog.ERRORS)
        for state, family in cli.RUN_FAMILY.items():
            self.assertIn(state, runs.MILESTONE_STATES)
            self.assertIn(family, catalog.ERRORS)

    def test_run_states_that_ask_the_owner_have_a_screen_and_every_end_screen_has_actions(self):
        for state in cli.ATTENTION:
            self.assertIn(state, catalog.SCREENS)
            self.assertIn(state, runs.MILESTONE_STATES)
            self.assertTrue([a for a in catalog.ACTIONS.values() if a.screen == state], state)


class ErrorFamilyTests(unittest.TestCase):
    def test_every_raise_site_names_a_catalog_family(self):
        defaults = class_families()
        self.assertIn(authority.require.__defaults__[-1], catalog.ERRORS)  # require()'s own default
        for name, family in defaults.items():
            if family is not None:
                self.assertIn(family, catalog.ERRORS, name)
        sites = raise_sites()
        self.assertGreater(len(sites), 40, "the scan found no raise sites")
        for file, line, name, family in sites:
            where = "%s:%s %s" % (file, line, name)
            if family is None:
                self.assertIsNotNone(defaults[name], where + ": no family= and no class default")
            elif family != "<expr>":
                self.assertIn(family, catalog.ERRORS, where)
        # require(..., family=) is a raise site too.
        for path, tree in sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and call_name(node) == "require":
                    given = {k.arg: k.value for k in node.keywords}.get("family")
                    if given is not None and literal(given):
                        self.assertIn(given.value, catalog.ERRORS, "%s:%s require" % (path.name, node.lineno))

    def test_family_bearing_subclasses_keep_their_default(self):
        defaults = class_families()
        for name in ("Stale", "ObservationDetached", "SliceEnded", "Invalid", "PersistenceError"):
            self.assertIsNotNone(defaults.get(name), name)
        for name in ("Rejected", "Blocked"):
            self.assertIn(name, defaults)

    def test_pass_through_families_are_the_known_ones(self):
        expressions = [(f, n) for f, _, n, family in raise_sites() if family == "<expr>"]
        # controller.py: the bridge's own refusal, and the A6b2b feed port passing bridge.CLOSING,
        # bridge.TIMEOUT_FAMILY and catalog.UNKNOWN through (all catalog families).
        self.assertEqual(sorted(expressions), [("authority.py", "Blocked")] + [("controller.py", "Blocked")] * 4)
        from terminal_planner import bridge
        for family in (bridge.CLOSING, bridge.TIMEOUT_FAMILY, catalog.UNKNOWN):
            self.assertIn(family, catalog.ERRORS)

    def test_every_catalog_family_has_a_use_site(self):
        used, names = set(), set()
        for tree in sources().values():
            used |= strings(tree)
            names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        items = readiness_ids()
        for family in catalog.ERRORS:
            with self.subTest(family):
                if family == catalog.UNKNOWN:
                    self.assertIn("UNKNOWN", names)
                elif family.startswith("readiness."):
                    self.assertIn(family.split(".", 1)[1], items)  # shown as "readiness." + the failing item id
                else:
                    self.assertIn(family, used)
        # And the other way: every readiness item that can fail has its readiness.<id> family.
        self.assertEqual({"readiness." + i for i in items} - set(catalog.ERRORS), set())

    def test_every_readiness_check_id_is_the_doctor_and_screen_item(self):
        self.assertEqual(readiness_ids(), {"socket", "tools", "codex", "codex_home", "auth", "git", "identity",
                                           "roles", "repo", "branch", "origin", "clean"})

    def test_entries_are_complete_and_ids_unique(self):
        for kind, _, entries in catalog.KINDS:
            for key, entry in entries.items():
                with self.subTest("%s.%s" % (kind, key)):
                    self.assertEqual(entry.id, key)
                    for field in (entry.meaning, entry.cause, entry.remedy):
                        self.assertTrue(field.strip())
        self.assertEqual(catalog.family(Blocked("x")), catalog.UNKNOWN)
        self.assertEqual(catalog.family(Blocked("x", family="not.a.family")), catalog.UNKNOWN)
        self.assertEqual(catalog.family(Blocked("x", family="setup.busy")), "setup.busy")

    def test_the_architect_action_families_render_as_their_own_code(self):
        """A5t1 C5: the new action families are catalog entries, so `autonomy.ask` and the Controller errors never
        fall back to `unknown_error`."""
        for family in ("autonomy.ask", "architect.controller_unavailable", "architect.controller_timeout",
                       "architect.request_invalid"):
            with self.subTest(family):
                self.assertEqual(catalog.family(Blocked("x", family=family)), family)
                self.assertEqual(catalog.tag(family), " [code: %s]" % family)
                self.assertNotEqual(catalog.tag(family), catalog.tag("made.up"))

    def test_the_merge_critic_families_render_as_their_own_code(self):
        """A7b2 C5: the three merge-critic families are catalog entries and REFERENCE.md rows, so a pending,
        failed or blocked critic never falls back to `unknown_error`."""
        document = REFERENCE.read_text(encoding="utf-8")
        for family in ("merge.critic_pending", "merge.critic_failed", "milestone.critic_blocked"):
            with self.subTest(family):
                self.assertIn(family, catalog.ERRORS)
                self.assertIn("| `%s` |" % family, document)
                self.assertEqual(catalog.family(Blocked("x", family=family)), family)
                self.assertEqual(catalog.tag(family), " [code: %s]" % family)
                self.assertNotEqual(catalog.tag(family), catalog.tag("made.up"))


class ActionTests(unittest.TestCase):
    def test_every_screen_has_actions_or_is_a_bare_overlay(self):
        for screen in catalog.SCREENS:
            if screen not in ("home",):
                self.assertTrue([a for a in catalog.ACTIONS.values() if a.screen == screen], screen)
        for found in catalog.ACTIONS.values():
            self.assertIn(found.screen, catalog.SCREENS, found.id)
            self.assertEqual(found.id.split(".", 1)[0], found.screen)

    def test_menus_name_only_catalog_actions(self):
        ids = set()
        for tree in sources().values():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and call_name(node) in ("menu", "offer") and node.args:
                    for arg in node.args:
                        value = literal(arg) or (isinstance(arg, ast.Tuple) and literal(arg.elts[0]))
                        if value:
                            ids.add(value)
        # The shared delivery service names its menu actions as data (tables and lists); they are checked too.
        for path, tree in sources().items():
            if path.name == "delivery.py":
                for value in strings(tree):
                    head, _, tail = value.partition(".")
                    if tail and head in catalog.SCREENS and re.fullmatch(r"[a-z_]+", tail):
                        ids.add(value)
        self.assertGreater(len(ids), 25)
        self.assertEqual(ids - set(catalog.ACTIONS), set())

    def test_every_action_is_offered_somewhere(self):
        used, listed_screens = set(), set()
        for tree in sources().values():
            used |= strings(tree)
            for node in ast.walk(tree):  # screens whose whole key list is rendered from the catalog
                if isinstance(node, ast.Call) and call_name(node) in ("help_lines", "key_lines", "variants",
                                                                     "help_text", "HelpScreen", "keys_bar", "bar"):
                    listed_screens |= {literal(a) for a in node.args if literal(a)}
                if isinstance(node, ast.Call):  # `NoteScreen(..., bar="tui_attempt")`
                    listed_screens |= {literal(k.value) for k in node.keywords if k.arg == "bar" and literal(k.value)}
            for node in ast.walk(tree):  # `self.bar = "tui_diff" if diff else "tui_details"`: a modal's key bar
                if isinstance(node, ast.Assign) and any(getattr(t, "attr", getattr(t, "id", "")) == "bar"
                                                        for t in node.targets):
                    listed_screens |= {n.value for n in ast.walk(node.value)
                                       if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for found in catalog.ACTIONS.values():
            name = found.id.split(".", 1)[1]
            with self.subTest(found.id):
                offered = (found.id in used or found.screen in listed_screens
                           or (found.screen + "." in used and name in used))
                self.assertTrue(offered)

    def test_keys_of_a_screen_do_not_clash_unless_they_are_alternatives(self):
        # Two actions of one screen may share a key only when they are mutually exclusive variants of one menu.
        exclusive = {("home", "g"): {"home.check", "home.start", "home.resume", "home.attempt"},
                     ("readiness", "q"): {"readiness.back", "readiness.leave"},
                     ("plan", "g"): {"plan.start", "plan.restart", "plan.retry"},
                     ("plan", "i"): {"plan.details", "plan.requirements"},
                     # K1c3: the same for the run end screen, where every action button is one Enter
                     ("tui_run", "enter"): {"tui_run.%s" % n for n in (
                         "press", "merge", "diff", "accept", "answer", "attempt", "plan", "resume", "check", "tail",
                         "details", "leave")},
                     # K1c2: Enter presses the focused button, so every button of the plan screen and of Settings
                     # (and the `press` line of the bar) is one Enter, told apart by the focus.
                     ("tui_plan", "enter"): {"tui_plan.%s" % n for n in (
                         "press", "run", "renew", "login", "watch", "tail", "approve", "override", "revise",
                         "reject", "info")},
                     # RS2: the confirmation's Enter is `press`, or `start` where “yes” is the focused button
                     ("tui_confirm", "enter"): {"tui_confirm.press"},
                     ("tui_confirm_run", "enter"): {"tui_confirm_run.start"},
                     ("tui_settings", "enter"): {"tui_settings.%s" % n for n in (
                         "press", "setup", "login", "recheck", "roles")},
                     ("tui_panel", "/run"): {"tui_panel.run", "tui_panel.resume", "tui_panel.attempt",
                                          "tui_panel.check"}}
        taken = {}
        for found in catalog.ACTIONS.values():
            taken.setdefault((found.screen, found.key), set()).add(found.id)
        for slot, ids in taken.items():
            if len(ids) > 1:
                self.assertEqual(ids, exclusive.get(slot), slot)


# A3: generated tables ------------------------------------------------------------------------------------------


class AnswerDraftRefusalDocTests(unittest.TestCase):
    """The answer draft's refusals are catalog vocabulary, not only pane text.

    Class: every refusal the `[t]` answer-draft key can give is a catalog error family whose entry carries a cause
    and an owner remedy (the reference's "Error families" table), and the action's own row of the keys table names
    those families, so a pane code (`[code: draft.…]`) is explained by the document the owner reads. Domain checked:
    the four families the controller's open and send jobs raise for [t] — `draft.malformed`, `draft.active`,
    `draft.unavailable`, and the shared `draft.stale`. Interpretation: the task's "the answer-draft refusal
    reasons" is read as these families, since the pane shows them only as a code; the stale one stays shared with
    the goal draft, which its own entry now says.
    """

    REFUSALS = ("draft.malformed", "draft.active", "draft.unavailable", "draft.stale")

    def test_each_refusal_is_a_family_with_a_cause_and_an_owner_action(self):
        for family in self.REFUSALS:
            with self.subTest(family):
                self.assertIn(family, catalog.ERRORS)
                entry = catalog.ERRORS[family]
                self.assertTrue(entry.meaning.strip())
                self.assertTrue(entry.cause.strip())
                self.assertRegex(entry.remedy, r"\[[^\]]+\]")  # the remedy names the owner's own key

    def test_the_keys_table_names_them_for_the_action(self):
        meaning = catalog.action("tui_panel.answer_draft").meaning
        for family in self.REFUSALS:
            with self.subTest(family):
                self.assertIn(family, meaning)
                self.assertIn(family, catalog.generated("keys"))  # what docs/REFERENCE.md is generated from

    def test_each_refusal_remedy_names_the_fresh_draft_path(self):
        """Class: a refusal's remedy points at the way to a usable draft — asking the architect again — and never
        promises that the refused draft itself reopens.

        Domain checked: the remedies of the four `[t]` refusal families. Interpretation (P3): the refused draft is
        not reapplied by [t] — a draft of a still-running attempt is `draft.active` now and `draft.stale` once that
        same attempt ends, and a refused goal/answer draft only becomes usable through a new architect reply — so
        every remedy must name that fresh-draft path (the architect) and must not claim the draft itself opens.
        """
        for family in self.REFUSALS:
            with self.subTest(family):
                remedy = catalog.ERRORS[family].remedy.lower()
                self.assertIn("architect", remedy)  # the fresh draft comes from a new architect reply
                self.assertNotIn("then opens the draft", remedy)  # the refused draft itself is never reapplied


class LoginFailedRemedyTests(unittest.TestCase):
    """A2: the `setup.login_failed` remedy tells the owner the one extra step a turned-off device login needs,
    before sending them back to the same retry ([l] or `zplan login`)."""

    def test_login_failed_remedy_says_to_enable_device_login_then_retry(self):
        remedy = catalog.ERRORS["setup.login_failed"].remedy
        self.assertIn("device-code login is off", remedy)
        self.assertIn("ChatGPT account security settings", remedy)
        self.assertIn("[l]", remedy)
        self.assertIn("`zplan login`", remedy)
        self.assertIn("again", remedy)  # it still ends on the same retry it always named


class ReferenceDocumentTests(unittest.TestCase):
    def test_generated_blocks_equal_the_generator_output(self):
        document = REFERENCE.read_text(encoding="utf-8")
        for name, build in catalog.SECTIONS:
            with self.subTest(name):
                self.assertEqual(document.count(catalog.begin(name)), 1)
                self.assertEqual(document.count(catalog.end(name)), 1)
                head = document.split(catalog.begin(name), 1)[1].split(catalog.end(name), 1)[0]
                self.assertEqual(head.strip("\n"), build())
        self.assertEqual(catalog.render(document), document)

    def test_write_repairs_a_drifted_document_and_check_detects_it(self):
        document = REFERENCE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "REFERENCE.md"
            copy.write_text(document.replace("| `plan.stale` |", "| `plan.old` |"), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(catalog.main(["--check", str(copy)]), 1)
                self.assertEqual(catalog.main(["--write", str(copy)]), 0)
                self.assertEqual(copy.read_text(encoding="utf-8"), document)
                self.assertEqual(catalog.main(["--check", str(copy)]), 0)

    def test_the_limits_row_says_task_rounds_bounds_the_milestone_repair_rounds(self):
        """A2: docs/REFERENCE.md documents `limits.task_rounds` as the bound of a milestone's task review loop: one
        implementation pass plus `task_rounds` repairs, and the fixed 4 when the milestone has no frozen profile."""
        document = REFERENCE.read_text(encoding="utf-8")
        row = next(line for line in document.splitlines() if line.startswith("| `limits` |"))
        self.assertIn("`task_rounds` bounds the repair rounds", row)
        self.assertIn("one implementation pass plus `task_rounds` repairs", row)
        self.assertIn("a milestone built without a frozen profile keeps the fixed 4", row)

    def test_authored_sections_and_readme_link_exist(self):
        document = REFERENCE.read_text(encoding="utf-8")
        for heading in ("## How the pieces fit", "## Lifecycle", "## Commands and flags", "## Screens and keys",
                        "## Error families", "## Worked examples"):
            self.assertIn(heading, document)
        self.assertGreaterEqual(document.count("\n### "), 3)
        authored = document.split("<!-- BEGIN GENERATED", 1)[0] + document.rsplit("<!-- END GENERATED", 1)[1]
        for topic in ("CODEX_HOME", "merge --ff-only", "planning.json", "worktree",
                      "needs_owner.accept", "blocked.answer", "Safe to delete"):
            self.assertIn(topic, authored)
        self.assertIn("docs/REFERENCE.md", (ROOT / "README.md").read_text(encoding="utf-8"))
        # The lifecycle diagram names every plan status and milestone state, and only real ones with an underscore.
        diagram = document.split("## Lifecycle", 1)[1].split("```", 2)[1]
        known = set(catalog.PLAN_STATUS) | set(catalog.MILESTONE_STATE)
        words = set(re.findall(r"[a-z]+(?:_[a-z]+)*", diagram))
        self.assertEqual(known - words, set())
        self.assertEqual({w for w in words if "_" in w} - known, set())


# A4: the fallback ------------------------------------------------------------------------------------------------

class UnknownErrorJourneyTests(UxTest):
    def journey(self, install, *steps):
        # A fixture session needs no tools (readiness per action): the failing item is one it still asks for.
        item = test_tui.check("git", ok=False, line="zplan tools are not installed", key="u")
        output = io.StringIO()
        sent = []
        session(Terminal(Steps(*steps), output), self.project, self.state, lambda *_: Counting(sent), fixture_id="test",
                driver_factory=lambda _: FixtureDriver(self.root / "fixture-runs", delay=0),
                worktrees=self.root / "worktrees", readiness=lambda: [dict(item)], install=install)
        return output.getvalue()

    def test_a_failure_without_a_family_shows_unknown_error(self):
        def install():
            raise Blocked("Something went wrong in a place nobody classified.")
        output = self.journey(install, "u", "q")
        self.assertIn("Something went wrong", output)
        self.assertIn("[code: unknown_error]", output)

    def test_a_family_outside_the_catalog_is_also_unknown(self):
        def install():
            raise Blocked("Made-up code.", family="made.up")
        self.assertIn("[code: unknown_error]", self.journey(install, "u", "q"))

    def test_a_mapped_failure_shows_its_own_code_and_a_bug_shows_unknown(self):
        def busy():
            raise Blocked("Installation is already running.", family="setup.busy")
        output = self.journey(busy, "u", "q")
        self.assertIn("[code: setup.busy]", output)
        self.assertNotIn("unknown_error", output)

        def broken():
            raise OSError("boom")
        self.assertIn("[code: unknown_error]", self.journey(broken, "u", "q"))


if __name__ == "__main__":
    unittest.main()
