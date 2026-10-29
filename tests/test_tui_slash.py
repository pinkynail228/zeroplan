"""U4 A1-A6: the `/` command registry (`terminal_planner.tui.slash`) — pure data and functions.

One test per acceptance criterion (A1 `COMMANDS`, A2 `parse`, A3 `available`, A4 `matches`, A5 `problem`); A6
("one test per criterion") is that very shape, so no sixth test is added. The module has no app, no I/O and no
engine call, and nothing imports it yet, so the tests read it directly and need neither Textual nor Rich.

Interpretations recorded here (worker; the module docstring repeats the contract):
- A1 names the four fields with `arg` last but does not type it; the argument rule is a small frozen
  `Arg(label, required, choices)` (`None` when the command takes no argument), which is what A5 needs to tell
  `/open`'s required path from `/language`'s optional en|ru|zh.
- The case rule ("Names match case-insensitively") is stated for `parse` only (A2); A4 names no case rule and the
  approved lab matches the prefix as typed (`c.startswith(word)`), so `matches` matches the prefix as typed too: a
  `/PL` resolves in `parse` but lists no command in the palette. The palette being stricter than `parse` is left
  as-is (a spec gap), never translated.
- A5 returns ids only, so the tests assert the four literals A5 names, never their texts.
- T2: `/language` is hidden while `strings.OFFERED` holds one language (the English-only release), so the registry
  tests of the parsing mechanics patch `OFFERED` to all three languages; `LanguageHiddenTests` pins the hiding."""

from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from terminal_planner.tui import strings
from terminal_planner.tui.slash import (Arg, Command, COMMANDS, Parsed, STATES, available, matches, parse,
                                        problem)

EVERYWHERE = frozenset(STATES)  # the eight states; every command named "all states" acts in all of them

# A1's table, spelled out: (name, description id, states it acts in, argument rule).
EXPECTED = (
    ("/plan", "cmd.plan", frozenset(("idle", "draft", "error")), Arg("goal")),
    ("/approve", "cmd.approve", frozenset(("plan_ready", "question", "error")), None),
    ("/decline", "cmd.decline", frozenset(("draft", "plan_ready", "question")), None),
    ("/run", "cmd.run", STATES, None),
    ("/merge", "cmd.merge", frozenset(("merge",)), None),
    ("/diff", "cmd.diff", frozenset(("merge", "idle")), None),
    ("/open", "cmd.open", frozenset(("idle", "draft", "plan_ready", "merge", "question", "error")),
     Arg("path", required=True)),
    ("/status", "cmd.status", EVERYWHERE, None),
    ("/stop", "cmd.stop", frozenset(("running", "planning")), None),
    ("/language", "cmd.language", EVERYWHERE, Arg("language", choices=("en", "ru", "zh"))),
    ("/setup", "cmd.setup", EVERYWHERE, None),
    ("/help", "cmd.help", EVERYWHERE, None),
    ("/new", "cmd.new", EVERYWHERE, None),
    ("/quit", "cmd.quit", EVERYWHERE, None),
    ("/view", "cmd.view", EVERYWHERE, None),
    ("/attempt", "cmd.attempt", EVERYWHERE, None),
    ("/answer", "cmd.answer", EVERYWHERE, None),
    ("/log", "cmd.log", EVERYWHERE, None),
    ("/details", "cmd.details", EVERYWHERE, None),
    ("/retry", "cmd.retry", EVERYWHERE, None),
    ("/scheme", "cmd.scheme", EVERYWHERE, None),
    ("/theme", "cmd.theme", EVERYWHERE, Arg("theme", choices=("auto", "dark", "light"))),
)

# A3's table, spelled out again (a name -> the states it acts in), so the check does not just read A1's tuple back.
ACTING = {
    "/plan": {"idle", "draft", "error"},
    "/approve": {"plan_ready", "question", "error"},
    "/decline": {"draft", "plan_ready", "question"},
    "/view": set(STATES),
    "/run": set(STATES),
    "/attempt": set(STATES),
    "/answer": set(STATES),
    "/merge": {"merge"},
    "/diff": {"merge", "idle"},
    "/open": {"idle", "draft", "plan_ready", "merge", "question", "error"},
    "/log": set(STATES),
    "/details": set(STATES),
    "/status": set(STATES),
    "/stop": {"running", "planning"},
    "/new": set(STATES),
    "/language": set(STATES),
    "/setup": set(STATES),
    "/help": set(STATES),
    "/quit": set(STATES),
    "/retry": set(STATES),
}


class SlashRegistryTests(unittest.TestCase):
    """A1-A5 of terminal_planner/tui/slash.py; A6 is the one-test-per-criterion shape of this class."""

    def setUp(self):
        offered = patch.object(strings, "OFFERED", ("en", "ru", "zh"))
        offered.start()
        self.addCleanup(offered.stop)

    def test_a1_commands_are_the_twenty_two_frozen_records_in_order(self):
        """A1: `COMMANDS` is a tuple of frozen `Command(name, description_id, states, arg)` records — the twenty-two
        commands, with the state sets given, in the order given."""
        self.assertIsInstance(COMMANDS, tuple)
        self.assertEqual(len(COMMANDS), 22)
        self.assertEqual([(c.name, c.description_id, c.states, c.arg) for c in COMMANDS], list(EXPECTED))
        self.assertEqual([c.name for c in COMMANDS],
                         ["/plan", "/approve", "/decline", "/run", "/merge", "/diff", "/open", "/status", "/stop",
                          "/language", "/setup", "/help", "/new", "/quit", "/view", "/attempt", "/answer", "/log",
                          "/details", "/retry", "/scheme", "/theme"])
        for command in COMMANDS:
            with self.subTest(command.name):
                self.assertIsInstance(command, Command)
                self.assertIsInstance(command.states, frozenset)
                self.assertTrue(command.states, "no command acts nowhere")
                self.assertTrue(command.states <= STATES, "a state outside STATES")
                self.assertTrue(command.description_id.startswith("cmd."))
                if command.arg is not None:
                    self.assertIsInstance(command.arg, Arg)
                with self.assertRaises(FrozenInstanceError):
                    command.name = "/changed"

    def test_a2_parse_resolves_names_case_insensitively_and_keeps_the_typed_name(self):
        """A2: None when the stripped line does not start with `/`, otherwise a `Parsed` with the resolved command
        (or None), the name as typed and the argument; a Cyrillic look-alike stays unknown (no translation)."""
        self.assertIsNone(parse("hello"))
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("   "))
        self.assertIsNone(parse("   plan   "))        # spaces stripped, still no leading slash
        self.assertIsNone(parse("plan /approve"))
        cases = (
            ("/plan", "/plan", "/plan", ""),
            ("  /plan  ", "/plan", "/plan", ""),           # leading and trailing spaces stripped
            ("/Plan", "/plan", "/Plan", ""),               # the name matches case-insensitively
            ("/APPROVE", "/approve", "/APPROVE", ""),
            ("/open AGENTS.md", "/open", "/open", "AGENTS.md"),
            ("/open  AGENTS.md", "/open", "/open", "AGENTS.md"),   # runs of spaces collapse
            ("/language ru", "/language", "/language", "ru"),
            ("/language", "/language", "/language", ""),
            ("/plan extra words here", "/plan", "/plan", "extra words here"),
            ("/nope x", None, "/nope", "x"),               # unknown name: command is None, the rest kept
            ("/", None, "/", ""),                          # a bare slash is an unknown command
            ("/план", None, "/план", ""),                  # Cyrillic is never translated
            ("/здфт", None, "/здфт", ""),                  # "plan" typed on a Russian layout
            ("/рlаn", None, "/рlаn", ""),                  # mixed Cyrillic look-alikes
        )
        for line, name, typed, argument in cases:
            with self.subTest(line):
                parsed = parse(line)
                self.assertIsInstance(parsed, Parsed)
                self.assertEqual(parsed.command, next((c for c in COMMANDS if c.name == name), None))
                self.assertEqual(parsed.name, typed)
                self.assertEqual(parsed.argument, argument)

    def test_a3_available_follows_the_state_table_and_rejects_unknown_states(self):
        """A3: `available` is exactly A3's table, and an unknown state raises `ValueError`."""
        by_name = {command.name: command for command in COMMANDS}
        for name, states in ACTING.items():
            for state in STATES:
                with self.subTest("%s / %s" % (name, state)):
                    self.assertEqual(available(by_name[name], state), state in states)
        for bad in ("", "empty", "approve", "IDLE", "plan-ready", "plan_ready ", None):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    available(by_name["/plan"], bad)

    def test_a4_matches_filters_by_prefix_and_puts_the_state_s_first(self):
        """A4: the name prefix filters in registry order; with a state the acting commands come first, the rest keep
        their order after them; a bare `/` lists all twenty-two."""
        self.assertEqual(matches("/"), list(COMMANDS))          # "/" alone lists all, in registry order
        self.assertEqual([c.name for c in matches("/pl")], ["/plan"])
        self.assertEqual([c.name for c in matches("/op")], ["/open"])
        self.assertEqual(matches("/zzz"), [])
        self.assertEqual([c.name for c in matches("/op AGENTS.md")], ["/open"])   # the first word of the prefix
        self.assertEqual([c.name for c in matches("/")], [c.name for c in COMMANDS])  # a fresh list, same order
        # with a state: the acting ones first, each group in registry order
        self.assertEqual([c.name for c in matches("/", state="merge")],
                         ["/run", "/merge", "/diff", "/open", "/status", "/language", "/setup", "/help", "/new",
                          "/quit", "/view", "/attempt", "/answer", "/log", "/details", "/retry",
                          "/scheme", "/theme", "/plan", "/approve", "/decline", "/stop"])
        self.assertEqual([c.name for c in matches("/", state="idle")],
                         ["/plan", "/run", "/diff", "/open", "/status", "/language", "/setup", "/help", "/new",
                          "/quit", "/view", "/attempt", "/answer", "/log", "/details", "/retry",
                          "/scheme", "/theme", "/approve", "/decline", "/merge", "/stop"])
        self.assertEqual([c.name for c in matches("/d", state="idle")], ["/diff", "/details", "/decline"])
        self.assertEqual([c.name for c in matches("/d", state="merge")], ["/diff", "/details", "/decline"])
        # the prefix is matched as typed (see the module docstring): a different case reaches no command
        self.assertEqual(matches("/PL"), [])
        with self.assertRaises(ValueError):
            matches("/", state="empty")

    def test_a5_problem_names_the_first_reason_a_line_cannot_act(self):
        """A5: None when the command can act, otherwise the first reason — unknown name, then a state it does not
        act in, then a missing required argument or a /language argument outside en|ru|zh."""

        def probe(line, state):
            return problem(parse(line), state)

        self.assertEqual(probe("/plan", "draft"), None)
        self.assertEqual(probe("/plan", "idle"), None)           # K1b: a goal can start from idle (`/plan <text>`)
        self.assertEqual(probe("/plan add slugify", "idle"), None)
        self.assertEqual(probe("/plan", "running"), "note.not_now")
        self.assertEqual(probe("/stop", "running"), None)
        self.assertEqual(probe("/stop", "planning"), None)
        self.assertEqual(probe("/stop", "idle"), "note.not_now")
        self.assertEqual(probe("/run", "idle"), None)
        self.assertEqual(probe("/run", "running"), None)        # i11: a running stage gets the busy note, not not_now
        for state in ("draft", "plan_ready", "merge", "question", "planning"):  # K1a: `g` acted in every state
            self.assertEqual(probe("/run", state), None, state)
        self.assertEqual(probe("/quit", "error"), None)
        self.assertEqual(probe("/nope", "draft"), "note.unknown_command")
        self.assertEqual(probe("/nope", "planning"), "note.unknown_command")   # unknown beats not_now
        self.assertEqual(probe("/open", "idle"), "note.needs_arg")
        self.assertEqual(probe("/open AGENTS.md", "idle"), None)
        self.assertEqual(probe("/open", "running"), "note.not_now")            # not_now beats needs_arg
        self.assertEqual(probe("/language", "idle"), None)                     # the argument is optional
        self.assertEqual(probe("/language ru", "idle"), None)
        self.assertEqual(probe("/language xx", "idle"), "note.bad_language")
        self.assertEqual(probe("/language EN", "idle"), "note.bad_language")


class LanguageHiddenTests(unittest.TestCase):
    """T2/U1: `/language` is hidden while one language is offered (an unknown command, not listed) and works again
    when several are offered."""

    def test_language_is_an_unknown_command_and_unlisted_with_one_offered_language(self):
        with patch.object(strings, "OFFERED", ("en",)):
            self.assertIsNone(parse("/language").command)
            self.assertEqual(problem(parse("/language ru"), "idle"), "note.unknown_command")
            self.assertNotIn("/language", [c.name for c in matches("/")])
            self.assertNotIn("/language", [c.name for c in matches("/", state="idle")])
            self.assertEqual(matches("/lang"), [])
        with patch.object(strings, "OFFERED", ("en", "ru", "zh")):
            self.assertEqual(parse("/language").command.name, "/language")
            self.assertIn("/language", [c.name for c in matches("/")])


if __name__ == "__main__":
    unittest.main()
