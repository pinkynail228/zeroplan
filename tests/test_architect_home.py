"""Architect thread home (R-5, R-6): the session records the Codex home a thread started in, every later turn of that
thread acts in the recorded home, and a home that is gone is refused with `architect.home_lost` before anything is
written.

Deterministic: a scripted fake `codex` (never the real one), a `Popen` spy over the real launcher, temporary
HOME/XDG dirs and homes with a login fixture. `catalog.family` reads a refusal's family, never its wording.

Interpretations recorded here (the worker summary never reaches the reviewers):

- "a Popen spy records argv and env" is read as a spy that *wraps* the real `Popen` around the scripted fake: it
  records every launch and delegates, so "0 Popen calls" means no process was started at all, while a turn that
  must complete still has a process behind its pipes.
- The header's provider fallback "?" applies to a missing home directory as well as to an unreadable config and an
  unknown profile (R-5 names the three), so a lost recorded home never raises during preparation.
- `check_home` is the *module-level* `architect.check_home(home, environment, resumed)` -- the frozen interface
  `s2b2` calls -- while `Architect.next_home()` stays the method. A 4096-character home is an accepted shape
  (`toolchain.valid_codex_home`), so the predicate answers it with one of its own refusal families instead of
  letting the filesystem's ENAMETOOLONG escape.
- The `architect.home_lost` text names the home and the kind of login that is missing; it names no provider key
  either, so not even a variable name can leak into the pane (see
  `test_a5_a_lost_home_is_refused_before_anything_is_written`).
- A config.toml that *exists* but cannot be stat'ed or read (a permission error, a symlink loop, a component
  longer than NAME_MAX) is `readiness.codex_home` for both turn kinds and never the built-in OpenAI defaults:
  `setup.codex_provider` only catches read errors and `Path.exists()` swallows a permission error, so the read
  itself decides (`architect._config_text`). The header resolves through the same rule
  (`architect.home_provider`), so it shows "?" for such a home instead of "openai" (see
  `test_a_config_that_cannot_be_read_is_refused_for_both_turn_kinds` and
  `test_a5_the_header_falls_back_to_a_question_mark`).
- The required preparation scenario's "current B without one" means a genuinely logged-out current home: the
  fixture's `current` home carries a login for the other cases, so that test builds its own (`logged-out-current`)
  and asserts the precondition (see `test_a5_preparation_keeps_a_logged_in_recorded_home`).
"""

import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from terminal_planner import architect, catalog, process, setup, toolchain
from terminal_planner.architect import Architect, ArchitectStore
from terminal_planner.authority import Blocked
from terminal_planner.tui import chat as chat_module
from test_architect import FAKE, THREAD, completes

MODEL, EFFORT = "gpt-6.1-sol", "high"
# A literal home path for the shape cases (R-9: every literal home path in the tests lives under /home/user/).
LITERAL_HOME = "/home/user/a-home"
# The scripted fake codex, the thread id and `completes` come from the architect suite (one implementation of the
# same fixture); the tool check needs a `--help` text that mentions the exec flags.
HELP = "exec --json --sandbox --cd --model --config"


REAL_POPEN = subprocess.Popen   # captured before any patch: the spy delegates to the real launcher


class PopenSpy:
    """Every launch of one test: its argv and env, in order. It records and delegates -- replacing the delegate
    would change behaviour -- so `calls == []` proves that no process was started at all."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "env": dict(kwargs.get("env") or {})})
        return REAL_POPEN(argv, **kwargs)


class HomeCase(unittest.TestCase):
    """A project, a scripted fake codex behind a recording Popen spy, and homes with a login each."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zs-arch-home-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        patcher = patch.dict(os.environ, {"HOME": str(self.root / "home"), "XDG_DATA_HOME": str(self.root / "data"),
                                          "XDG_CONFIG_HOME": str(self.root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.root / "proj"
        self.project.mkdir()
        # A real Git project with one commit: the production preparation resolves the process profile through it.
        for args in (("init", "-q", "-b", "main"), ("config", "user.name", "Fixture"),
                     ("config", "user.email", "fixture@example.invalid"), ("config", "commit.gpgsign", "false")):
            self.git(*args)
        (self.project / "source.txt").write_text("baseline\n")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "fixture")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.codex = self.bin / "codex"
        self.codex.write_text(FAKE % {"python": sys.executable})
        self.codex.chmod(0o755)
        self.script([{"lines": completes("Привет.")}])
        self.spy = PopenSpy()
        spy = patch.object(architect.subprocess, "Popen", self.spy)
        spy.start()
        self.addCleanup(spy.stop)
        self.recorded = self.home("recorded-home")   # A: the home a recorded thread started in
        self.current = self.home("current-home")     # B: the home the current env names

    # fixture ------------------------------------------------------------------

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.project), *args], stderr=subprocess.DEVNULL)

    def home(self, name, auth=True, config=None):
        home = self.root / name
        home.mkdir(parents=True, exist_ok=True)
        if auth:
            (home / "auth.json").write_text("{}\n")
        if config is not None:
            (home / "config.toml").write_text(config)
        return home

    def script(self, steps):
        (self.bin / "scenario.json").write_text(json.dumps({"steps": steps, "help": HELP}))

    def env(self, home):
        return {"PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(home)}

    def store(self):
        return ArchitectStore(self.project)

    def architect(self, home=None, env=None, **kwargs):
        return Architect(self.codex, env if env is not None else self.env(home or self.current),
                         self.project, MODEL, EFFORT, **kwargs)

    def session(self, **fields):
        """A stored thread record; a field whose value is None is removed instead (for the legacy session)."""
        session = {"version": 1, "thread_id": THREAD, "model": MODEL, "created": "2026-01-01T00:00:00Z",
                   "turns": 1, "usage": {}}
        session.update({key: value for key, value in fields.items() if value is not None})
        self.raw_session(json.dumps(session))
        return session

    def unreadable_homes(self):
        """Homes whose config.toml exists but no read yields its text: a symlink loop (ELOOP) and a directory in
        the file's place (IsADirectoryError). Both fail for any user, root included."""
        loop = self.home("loop-home")
        os.symlink("config.toml", loop / "config.toml")
        directory = self.home("dir-config-home")
        (directory / "config.toml").mkdir()
        return (("symlink loop", loop), ("config.toml is a directory", directory))

    def fresh_session(self):
        """A stored session with no thread: the next send starts a new thread in the env's home (R-5)."""
        self.raw_session(json.dumps({"version": 1, "thread_id": None, "model": MODEL,
                                     "created": "2026-01-01T00:00:00Z", "turns": 0, "usage": {}}))

    def raw_session(self, text):
        path = self.store().session_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def files(self):
        """The store's bytes without the lock file: what a refused operation must leave untouched."""
        directory = self.store().directory
        return {path.name: path.read_bytes() for path in directory.iterdir() if path.name != "lock"}

    def turn_calls(self):
        """The recorded launches of the scripted codex that are turns: the tool check's `--help` probe and the Git
        helpers the profile resolution runs are not turns."""
        return [call for call in self.spy.calls
                if call["argv"][0] == str(self.codex) and "--help" not in call["argv"]
                and call["argv"][1:3] != ["mcp", "list"]]

    def argv_of(self, call):
        """A recorded launch's codex argv without its executable: the flags the fake itself would see."""
        return call["argv"][1:]

    def refusal(self, call):
        with self.assertRaises(Blocked) as raised:
            call()
        return raised.exception

    def assert_corrupt(self, call):
        self.assertEqual(catalog.family(self.refusal(call)), "architect.session_corrupt")


class ThreadHomeTests(HomeCase):
    """A-5, the turn path: what a thread records, which home it acts in, and what a lost home refuses."""

    def test_a5_a_new_thread_records_the_home_it_started_in(self):
        result = self.architect().send("первое")
        self.assertEqual(result.status, "completed")
        call = self.turn_calls()[-1]
        self.assertEqual(self.argv_of(call)[:2], ["exec", "--json"])       # a first turn, not a resume
        self.assertEqual(call["env"]["CODEX_HOME"], str(self.current))
        session = self.store().load()
        self.assertEqual(session["thread_id"], THREAD)
        self.assertEqual(session.get("codex_home"), str(setup.codex_home(self.env(self.current))))

    def test_a5_a_continuation_acts_in_the_recorded_home_not_the_current_one(self):
        self.session(codex_home=str(self.recorded))
        arch = self.architect()                                       # the current env holds B
        result = arch.send("дальше")
        self.assertEqual(result.status, "completed")
        call = self.turn_calls()[-1]
        self.assertEqual(self.argv_of(call)[:3], ["exec", "resume", THREAD])
        self.assertEqual(call["env"]["CODEX_HOME"], str(self.recorded))   # A, not the current B
        session = self.store().load()
        self.assertEqual(session["thread_id"], THREAD)
        self.assertEqual(session.get("codex_home"), str(self.recorded))
        self.assertEqual(arch.next_home(), (self.recorded, True))

    def test_a5_a_continuation_is_checked_in_its_recorded_home_not_in_the_current_one(self):
        """Class: a continuation's turn readiness is judged in the home it will act in, and that home is the
        recorded one -- never the current env's.

        Domain checked: the two homes of one turn, each logged in and each logged out in turn (A the recorded home,
        B the current env's). Interpretations: the current env's login is irrelevant to a continuation (the turn
        process does not act there), while the recorded home's login is decisive; and the check is a *refusal*
        check, so a refused turn starts no second process."""
        self.session(codex_home=str(self.recorded))
        arch = self.architect(self.home("logged-out-current", auth=False))
        self.assertEqual(arch.send("дальше").status, "completed")
        self.assertEqual(self.turn_calls()[-1]["env"]["CODEX_HOME"], str(self.recorded))
        # the mirror: A without a login is refused although the current B has one
        self.session(codex_home=str(self.home("logged-out-recorded", auth=False)))
        error = self.refusal(lambda: self.architect(self.current).send("ещё"))
        self.assertEqual(catalog.family(error), "architect.home_lost")
        self.assertEqual(len(self.turn_calls()), 1)          # the refusal started no second process

    def test_a5_a_legacy_session_acts_in_the_legacy_process_home(self):
        self.session()                                                # no codex_home: a pre-0.5 record
        legacy, other = self.home("legacy-home"), self.home("other-home")
        with patch.dict(os.environ, {"CODEX_HOME": str(legacy)}):
            arch = self.architect(other)
            arch.send("дальше")
            self.assertEqual(self.turn_calls()[-1]["env"]["CODEX_HOME"], str(legacy))   # L, not the env's Z
            self.assertEqual(arch.next_home(), (setup.legacy_codex_home(), True))
            self.assertEqual(arch.next_home()[0], legacy)

    def test_a5_a_lost_home_is_refused_before_anything_is_written(self):
        """A missing directory, a missing `auth.json` and an unset or empty provider key each refuse the turn with
        `architect.home_lost`, no Popen and the session and transcript bytes untouched."""
        custom = self.home("custom-home", auth=False,
                           config='model_provider = "corp"\n\n[model_providers.corp]\nenv_key = "CORP_KEY"\n')
        cases = (
            ("missing directory", self.root / "gone-home", self.env(self.current)),
            ("missing auth.json", self.home("logged-out-home", auth=False), self.env(self.current)),
            ("unset key", custom, self.env(self.current)),
            ("empty key", custom, dict(self.env(self.current), CORP_KEY="")),
        )
        for label, home, env in cases:
            with self.subTest(label):
                self.spy.calls.clear()
                self.store().append("owner", text="прежнее")
                self.session(codex_home=str(home))
                before = self.files()
                error = self.refusal(lambda: self.architect(env=env).send("дальше"))
                self.assertEqual(catalog.family(error), "architect.home_lost")
                self.assertEqual(self.turn_calls(), [])
                self.assertEqual(self.files(), before)
                self.assertIn(setup.tilde(home), str(error))
                self.assertIn("Ctrl+R", str(error))                  # the rollover the remedy names
                self.assertNotIn("CORP_KEY", str(error))             # never the variable, let alone its value

    def test_a5_a_reset_forgets_the_home_and_the_next_turn_uses_the_current_one(self):
        self.session(codex_home=str(self.recorded))
        arch = self.architect()
        arch.reset()
        session = self.store().load()
        self.assertIsNone(session["thread_id"])
        self.assertNotIn("codex_home", session)                       # the previous thread's home is gone
        self.assertEqual(arch.next_home(), (self.current, False))   # a new thread in the current home
        arch.send("заново")
        call = self.turn_calls()[-1]
        self.assertEqual(self.argv_of(call)[:2], ["exec", "--json"])
        self.assertEqual(call["env"]["CODEX_HOME"], str(self.current))
        session = self.store().load()
        self.assertEqual(session["thread_id"], THREAD)
        self.assertEqual(session.get("codex_home"), str(self.current))

    def test_a5_a_malformed_recorded_home_is_a_corrupt_session(self):
        """Class: `load` validates the *presence* of `codex_home` separately from its value -- a present value must
        pass `toolchain.valid_codex_home` and must come with a thread, while the field's absence is a pre-0.5
        session.

        Domain checked: every R-2 shape violation (relative, empty, NUL, 4097 characters, a non-string value) plus
        an explicit JSON `null` (a present value the R-2 rule rejects), the pair (home, null thread), the largest
        accepted value (4096 characters, not corrupt) and the legacy session without the field. Interpretation: a
        present `codex_home: null` is a value of the wrong shape, not the absence of the field, so it is corrupt."""
        base = {"version": 1, "thread_id": THREAD, "model": MODEL, "created": "2026-01-01T00:00:00Z",
                "turns": 1, "usage": {}}
        cases = (("relative", "relative/home"), ("empty", ""), ("NUL", LITERAL_HOME + "\x00b"),
                 ("4097 characters", "/" + "a" * 4096), ("integer", 5), ("explicit null", None))
        for label, value in cases:
            with self.subTest(label):
                self.raw_session(json.dumps(dict(base, codex_home=value)))
                self.assert_corrupt(self.store().load)
                self.assert_corrupt(lambda: self.architect().send("x"))
                self.assertEqual(self.turn_calls(), [])
        # a home may only be recorded with a thread: a null thread with a home is corrupt too
        self.raw_session(json.dumps(dict(base, thread_id=None, codex_home=str(self.recorded))))
        self.assert_corrupt(self.store().load)
        # the largest accepted shape (4096 characters) is not corrupt
        accepted = "/home/user/" + "a" * (4096 - len("/home/user/"))
        self.assertEqual(len(accepted), 4096)
        self.assertTrue(toolchain.valid_codex_home(accepted))
        self.raw_session(json.dumps(dict(base, codex_home=accepted)))
        self.assertEqual(self.store().load()["codex_home"], accepted)
        # and a legacy session (no field at all) still loads
        self.session()
        self.assertIsNone(self.store().load().get("codex_home"))


class ReadOnlyHomeTests(HomeCase):
    """A-6: the argv stays read-only whatever the config says, and a selected profile refuses before any process."""

    def test_a6_a_danger_full_access_config_keeps_the_argv_read_only(self):
        home = self.home("danger-home", config='sandbox_mode = "danger-full-access"\n')
        arch = self.architect(home)
        self.assertEqual(arch.send("первое").status, "completed")
        first = self.argv_of(self.turn_calls()[0])
        self.assertEqual(first[:2], ["exec", "--json"])
        self.assertEqual(first[first.index("-s") + 1], "read-only")
        self.assertNotIn("danger-full-access", " ".join(first))
        self.assertEqual(arch.send("дальше").status, "completed")
        second = self.argv_of(self.turn_calls()[1])
        self.assertEqual(second[:3], ["exec", "resume", THREAD])
        self.assertIn('sandbox_mode="read-only"', second)
        self.assertNotIn("danger-full-access", " ".join(second))

    def test_a6_a_selected_profile_is_refused_before_any_process(self):
        """A non-empty top-level `profile` refuses with `architect.invalid_config`, not `readiness.codex_home`,
        for a new thread and for a continuation alike, with no Popen and the store bytes untouched."""
        home = self.home("profile-home", config='profile = "unknown"\n')   # no [profiles.unknown]
        self.store().append("owner", text="прежнее")
        before = self.files()
        error = self.refusal(lambda: self.architect(home).send("первое"))
        self.assertEqual(catalog.family(error), "architect.invalid_config")
        self.assertEqual(self.turn_calls(), [])
        self.assertEqual(self.files(), before)
        self.session(codex_home=str(home))
        before = self.files()
        error = self.refusal(lambda: self.architect().send("дальше"))
        self.assertEqual(catalog.family(error), "architect.invalid_config")
        self.assertEqual(self.turn_calls(), [])
        self.assertEqual(self.files(), before)

    def test_a6_an_unreadable_config_is_readiness_codex_home(self):
        home = self.home("broken-home", config='model_provider = "unterminated\n')
        self.store().append("owner", text="прежнее")
        before = self.files()
        error = self.refusal(lambda: self.architect(home).send("первое"))
        self.assertEqual(catalog.family(error), "readiness.codex_home")
        self.assertEqual(self.turn_calls(), [])
        self.assertEqual(self.files(), before)
        self.session(codex_home=str(home))
        error = self.refusal(lambda: self.architect().send("дальше"))
        self.assertEqual(catalog.family(error), "readiness.codex_home")
        self.assertEqual(self.turn_calls(), [])


class UnreadableConfigTests(HomeCase):
    """R-6/frozen `check_home`: a config.toml that exists but cannot be stat'ed or read is refused, for both turn
    kinds, instead of being answered with Codex's built-in defaults."""

    def test_a_config_that_cannot_be_read_is_refused_for_both_turn_kinds(self):
        """Class: a config.toml that a read cannot yield (the filesystem answers a stat/read error) is the
        `readiness.codex_home` refusal for a new thread and for a continuation alike -- never the built-in OpenAI
        defaults, and never a bare OSError after a save or a launch.

        Domain checked: the two read failures of an *existing* config.toml that do not depend on the user id (a
        symlink loop and a directory in the file's place), each on both turn kinds. Interpretation:
        `setup.codex_provider` only catches read errors, while `Path.exists()` swallows a permission error and
        answers "config absent", so the read itself decides here; the family is the one `codex_provider` uses for
        an unreadable config."""
        for label, home in self.unreadable_homes():
            for resumed in (False, True):
                with self.subTest(config=label, resumed=resumed):
                    self.spy.calls.clear()
                    self.store().append("owner", text="прежнее")
                    if resumed:
                        self.session(codex_home=str(home))
                    else:
                        self.fresh_session()
                    before = self.files()
                    error = self.refusal(lambda: self.architect(home).send("дальше"))
                    self.assertEqual(catalog.family(error), "readiness.codex_home")
                    self.assertEqual(self.turn_calls(), [])          # no process at all
                    self.assertEqual(self.files(), before)           # session and transcript byte-identical
                    self.assertEqual(chat_module.header_provider(home), "?")   # the header agrees with the turn


class PredicateTests(HomeCase):
    """The frozen interface itself: `check_home`, `_auth_present` and `next_home` with their exact contracts."""

    def test_the_frozen_interface_is_the_module_level_predicate(self):
        arch = self.architect()
        self.assertEqual(arch.next_home(), (self.current, False))
        self.assertIsNone(architect.check_home(self.current, self.env(self.current), False))
        self.assertIsNone(architect.check_home(self.recorded, self.env(self.current), True))
        self.assertTrue(architect._auth_present(self.recorded, "file", self.env(self.current)))
        self.assertFalse(architect._auth_present(self.recorded, ("env", "MISSING"), self.env(self.current)))
        self.assertTrue(architect._auth_present(self.recorded, None, {}))

    def test_check_home_never_answers_an_accepted_shape_home_with_an_oserror(self):
        """Class: the predicate's result for every home of an accepted shape (`toolchain.valid_codex_home`) is
        None or a `Blocked` of its own families, never a raw OSError.

        Domain checked: a 4096-character home (the longest accepted) whose single component makes the filesystem
        answer ENAMETOOLONG, for a resumed and a new turn. Interpretations: the filesystem failure is a refusal of
        the predicate's own families, never an OSError; a resumed turn's directory test answers
        `architect.home_lost`, while a new thread's config read answers `readiness.codex_home` (a config that
        cannot be read is refused, never replaced by the built-in defaults)."""
        huge = Path("/" + "a" * 4095)
        self.assertTrue(toolchain.valid_codex_home(str(huge)))
        for resumed, family in ((True, "architect.home_lost"), (False, "readiness.codex_home")):
            with self.subTest(resumed=resumed):
                error = self.refusal(lambda: architect.check_home(huge, {}, resumed))
                self.assertEqual(catalog.family(error), family)


class HeaderHomeTests(HomeCase):
    """A-5, the header half: the header shows the home the next turn uses, with the "?" fallback."""

    def test_a5_the_header_shows_the_home_of_the_next_turn(self):
        self.session(codex_home=str(self.recorded))
        arch = self.architect()
        header = chat_module.live_header(arch)
        self.assertEqual(header.home, setup.tilde(self.recorded))       # A, not the current B
        self.assertEqual(header.provider, "openai")
        arch.reset()
        self.assertEqual(chat_module.live_header(arch).home, setup.tilde(self.current))

    def test_a5_the_header_falls_back_to_a_question_mark(self):
        cases = (("missing directory", self.root / "gone-home"),
                 ("malformed config", self.home("broken-home", config='profile = "\n')),
                 ("unknown profile", self.home("profile-home", config='profile = "unknown"\n')),
                 *self.unreadable_homes())
        for label, home in cases:
            with self.subTest(label):
                header = chat_module.live_header(self.architect(home))
                self.assertEqual(header.home, setup.tilde(home))
                self.assertEqual(header.provider, "?")


class ChatHomeIntegrationTests(HomeCase):
    """A-5 through the production `default_prepare` and the real `ArchitectChat` (Ctrl+R included)."""

    def prepare(self, env):
        """`default_prepare` with only the toolchain boundary stubbed: the scripted codex is the installed one and
        `native_environment()` answers `env`."""
        config = self.root / "roles-config"
        config.mkdir(exist_ok=True)
        return (patch.object(process, "config_root", lambda: config),
                patch.object(setup, "check_installation", return_value=self.bin),
                patch.object(setup, "tool_paths", return_value=(None, self.codex)),
                patch.object(setup, "native_environment", return_value=env))

    def chat(self, env):
        instance = chat_module.ArchitectChat(self.project, lambda: chat_module.default_prepare(self.project),
                                            binding=lambda project=None: (MODEL, EFFORT))
        self.addCleanup(instance.close)
        instance.start()
        self.assertTrue(self.wait(lambda: instance.state.phase != "preparing"), instance.state)
        return instance

    @staticmethod
    def wait(condition, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return True
            time.sleep(0.005)
        return False

    def turn(self, chat, message):
        """One accepted message and the end of its turn; returns True when the turn could be sent."""
        accepted, _line = chat.send(message)
        if accepted:
            self.assertTrue(self.wait(lambda: not chat.busy), chat.state)
        return accepted

    def test_a5_preparation_keeps_a_logged_in_recorded_home(self):
        """Recorded A with a login and current B without one: preparation succeeds and the send continues in A.

        Class: preparation judges a continuation in the home it will act in -- the recorded one -- and never in the
        current env's. Domain checked: B is *genuinely* logged out (`auth.json` absent; the fixture's `current`
        home carries a login for the other cases, so this required case builds its own), so any check of the
        current home during preparation would refuse and reach neither the ready phase nor Ctrl+R. Interpretation:
        the required scenario's "current B without one" is about the login, so the assertion states the fixture
        precondition (B has no login, A has one) instead of trusting a name."""
        self.session(codex_home=str(self.recorded))
        current = self.home("logged-out-current", auth=False)           # B: no auth.json
        self.assertFalse((current / "auth.json").exists())
        self.assertTrue((self.recorded / "auth.json").is_file())
        env = self.env(current)
        with contextlib.ExitStack() as stack:
            for patcher in self.prepare(env):
                stack.enter_context(patcher)
            chat = self.chat(env)
            self.assertEqual(chat.state.phase, "ready", chat.state.refusal)
            self.assertEqual(chat.state.header_fields.home, setup.tilde(self.recorded))
            self.assertTrue(self.turn(chat, "дальше"))
        self.assertEqual(self.argv_of(self.turn_calls()[-1])[:3], ["exec", "resume", THREAD])
        self.assertEqual(self.turn_calls()[-1]["env"]["CODEX_HOME"], str(self.recorded))

    def test_a5_a_lost_recorded_home_never_blocks_preparation_and_ctrl_r_recovers(self):
        """Recorded A gone and current B logged out: preparation succeeds, the send is refused home_lost, Ctrl+R
        succeeds and the next send is refused readiness.auth for B -- both with no process at all."""
        self.session(codex_home=str(self.root / "gone-home"))
        current = self.home("logged-out-current", auth=False)            # B: a directory without a login
        env = self.env(current)
        with contextlib.ExitStack() as stack:
            for patcher in self.prepare(env):
                stack.enter_context(patcher)
            chat = self.chat(env)
            self.assertEqual(chat.state.phase, "ready", chat.state.refusal)
            self.assertTrue(self.turn(chat, "дальше"))
            self.assertIn("architect.home_lost", chat.state.note)
            self.assertEqual(self.turn_calls(), [])
            accepted, _line = chat.reset()                              # Ctrl+R: new dialog
            self.assertTrue(accepted)
            self.assertTrue(self.wait(lambda: not chat.busy), chat.state)
            self.assertIsNone(self.store().load()["thread_id"])
            self.assertEqual(chat.state.header_fields.home, setup.tilde(current))  # the current home after Ctrl+R
            self.assertTrue(self.turn(chat, "заново"))
            self.assertIn("readiness.auth", chat.state.note)
            self.assertEqual(self.turn_calls(), [])

    def test_a5_recovery_from_a_broken_recorded_home(self):
        """Recorded A whose config.toml cannot be read (and, separately, a missing A): preparation succeeds with
        the fallback header, the send is refused, Ctrl+R succeeds and the next send spawns in B, recording B."""
        broken = self.home("broken-home", config='model_provider = "unterminated\n')
        for label, home, family in (("unreadable config", broken, "readiness.codex_home"),
                                    ("missing directory", self.root / "gone-home", "architect.home_lost")):
            with self.subTest(label):
                self.spy.calls.clear()
                self.session(codex_home=str(home))
                env = self.env(self.current)                            # B has a login
                with contextlib.ExitStack() as stack:
                    for patcher in self.prepare(env):
                        stack.enter_context(patcher)
                    chat = self.chat(env)
                    self.assertEqual(chat.state.phase, "ready", chat.state.refusal)
                    self.assertEqual(chat.state.header_fields.home, setup.tilde(home))
                    self.assertEqual(chat.state.header_fields.provider, "?")
                    self.assertTrue(self.turn(chat, "дальше"))
                    self.assertIn(family, chat.state.note)
                    self.assertEqual(self.turn_calls(), [])
                    self.assertTrue(chat.reset()[0])
                    self.assertTrue(self.wait(lambda: not chat.busy), chat.state)
                    self.assertTrue(self.turn(chat, "заново"))
                call = self.turn_calls()[-1]
                self.assertEqual(self.argv_of(call)[:2], ["exec", "--json"])
                self.assertEqual(call["env"]["CODEX_HOME"], str(self.current))
                session = self.store().load()
                self.assertEqual(session["thread_id"], THREAD)
                self.assertEqual(session["codex_home"], str(self.current))

    def test_a5_the_control_a_new_thread_spawns_in_the_current_home(self):
        env = self.env(self.current)                                    # B with a login, no session
        with contextlib.ExitStack() as stack:
            for patcher in self.prepare(env):
                stack.enter_context(patcher)
            chat = self.chat(env)
            self.assertEqual(chat.state.phase, "ready", chat.state.refusal)
            self.assertEqual(chat.state.header_fields.home, setup.tilde(self.current))
            self.assertEqual(chat.state.header_fields.provider, "openai")
            self.assertTrue(self.turn(chat, "первое"))
        call = self.turn_calls()[-1]
        self.assertEqual(self.argv_of(call)[:2], ["exec", "--json"])
        self.assertEqual(call["env"]["CODEX_HOME"], str(self.current))
        self.assertEqual(self.store().load().get("codex_home"), str(self.current))


if __name__ == "__main__":
    unittest.main()
