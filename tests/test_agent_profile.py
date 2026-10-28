"""The packaged agent profile and its write lifecycle (0.5 item S2, slice s2b1: R-2..R-5; A-1..A-4; R-6 fixtures).
No production path imports `agent_profile` (R-1), so the unreached check is a source scan; literal home paths here
are under `/home/user/` and real file operations use `tempfile` directories through `XDG_DATA_HOME`.

Interpretations (worker, s2b1; updated by profile-memories): the packaged N is 2 (`memories = false` in `[features]`),
so `OLDER` is the previous packaged marker, version 1, which `ensure` now replaces by the version-change rule (A2). A
marker outside the closed grammar (e.g. `…: 0`) still classifies like "no marker" (case 4). "Undecodable bytes" is any
sequence that is not valid UTF-8 anywhere in the config, not only the marker area (R-2 names it as its own rejection),
so a valid marker with a corrupt tail is case 4 too — replaced, never "current" — while a valid hand edit that keeps
the current N stays "current". F1-F6 inject the OSError at the real calls R-3 names (`_make_home` for F1, `Path.open`
on the lock, `os.fsync` by order for the two temps, `os.replace` on the destination), never at a production helper, so
the same tests also kill a non-atomic publish or a missing cleanup.
"""

import contextlib
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from terminal_planner import agent_profile, setup
from terminal_planner.authority import Blocked

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "terminal_planner"
RESIDUAL = [".zplan-profile.lock", "config.toml", "config.toml.bak"]
OLDER = b"# zplan-agent-profile: 1\napproval_policy = \"on-request\"\n"
BAK = b"# stale backup\n"
NO_SPACE = OSError(28, "no space left on device")


def flatten(mapping, prefix=""):
    """The dotted key -> value map of a parsed TOML document (the comparison helper of A-1)."""
    flat = {}
    for key, value in mapping.items():
        flat.update(flatten(value, prefix + key + ".") if isinstance(value, dict) else {prefix + key: value})
    return flat


def listing(directory):
    return sorted(path.name for path in Path(directory).iterdir())


def seed_config(home, body, backup=None):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_bytes(body)
    if backup is not None:
        (home / "config.toml.bak").write_bytes(backup)


def link_config(home, target, body):
    target.write_bytes(body)
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").symlink_to(target)


class HomeTestCase(unittest.TestCase):
    """A temporary XDG_DATA_HOME per test; `isolated_home()` re-points it at a fresh private home."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.xdg = patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data")})
        self.xdg.start()
        self.addCleanup(self.xdg.stop)
        self.home = setup.private_codex_home()

    @contextlib.contextmanager
    def isolated_home(self):
        temp = tempfile.TemporaryDirectory()
        try:
            with patch.dict(os.environ, {"XDG_DATA_HOME": str(Path(temp.name) / "data")}):
                yield setup.private_codex_home()
        finally:
            temp.cleanup()


class ProfileTests(HomeTestCase):
    """A-1: the packaged file is the flattened `EXPECTED` map in both directions; the forbidden tables are absent."""

    def test_the_packaged_profile_is_the_expected_map_from_a_marker_line(self):
        data = agent_profile.packaged()
        first = data.split(b"\n", 1)[0]
        self.assertRegex(first, rb"^# zplan-agent-profile: [1-9][0-9]{0,8}$")
        self.assertEqual(agent_profile.version(data), int(first.rsplit(b" ", 1)[1]))
        parsed = setup.read_toml(data.decode("utf-8"))
        self.assertEqual(flatten(parsed), agent_profile.EXPECTED)
        self.assertEqual(agent_profile.EXPECTED, flatten(parsed))
        forbidden = {"mcp_servers", "projects", "profile", "profiles", "apps", "hooks", "plugins"}
        self.assertEqual(forbidden & set(parsed), set())

    def test_a_removed_key_or_a_changed_value_fails_the_comparison(self):
        text = agent_profile.packaged().decode("utf-8")
        for name, broken in {"removed": text.replace("goals = false\n", ""),
                             "changed": text.replace("apps = false", "apps = true")}.items():
            with self.subTest(name):
                self.assertNotEqual(flatten(setup.read_toml(broken)), agent_profile.EXPECTED)


class LifecycleTests(HomeTestCase):
    """A-2: written (0700 home), current (a valid same-N edit untouched), replaced (version 1, no marker, undecodable
    bytes, a corrupt tail, an old `.bak`) and the symlink rules."""

    def test_absent_writes_the_profile_and_a_same_n_edited_body_is_untouched(self):
        self.assertFalse(self.home.exists())
        self.assertEqual(agent_profile.ensure(self.home), "written")
        self.assertEqual((self.home / "config.toml").read_bytes(), agent_profile.packaged())
        mode, names = stat.S_IMODE(os.stat(self.home).st_mode), listing(self.home)
        self.assertEqual((mode, names), (0o700, [".zplan-profile.lock", "config.toml"]))
        edited = agent_profile.packaged() + b"# hand edit\n"
        (self.home / "config.toml").write_bytes(edited)
        self.assertEqual((agent_profile.ensure(self.home), (self.home / "config.toml").read_bytes(),
                          (self.home / "config.toml.bak").exists()), ("current", edited, False))

    def test_older_no_marker_undecodable_and_a_corrupt_tail_are_backed_up_and_replaced(self):
        cases = {"older": OLDER, "no marker": b"approval_policy = \"on-request\"\n",
                 "garbage": b"\x00\xff\x01 not toml \x80", "corrupt tail": agent_profile.packaged() + b"\xff\xfe\n"}
        for name, body in cases.items():
            with self.subTest(name), self.isolated_home() as home:
                seed_config(home, body, backup=BAK)
                state = agent_profile.ensure(home)
                self.assertEqual((state, (home / "config.toml").read_bytes(), (home / "config.toml.bak").read_bytes()),
                                 ("replaced", agent_profile.packaged(), body))

    def test_a_version_1_config_is_replaced_by_the_memories_off_profile(self):
        """A2/A3 (worker interpretations recorded here): the packaged marker moved 1 -> 2 because `features.memories`
        was turned off, so a version-1 `config.toml` is now "another N": `ensure` replaces it and keeps it as `.bak`,
        and the profile it writes carries `memories = false`. The version-1 body is the previous packaged marker; if
        the marker were reverted to 1 the same file would be "current" and this test would fail."""
        seed_config(self.home, OLDER, backup=BAK)
        self.assertEqual((agent_profile.ensure(self.home), (self.home / "config.toml.bak").read_bytes()),
                         ("replaced", OLDER))
        written = (self.home / "config.toml").read_bytes()
        self.assertIn(b"memories = false", written)
        self.assertEqual(written, agent_profile.packaged())
        self.assertEqual(flatten(setup.read_toml(written.decode("utf-8")))["features.memories"], False)
        self.assertEqual(agent_profile.ensure(self.home), "current")

    def test_a_second_ensure_changes_nothing_and_keeps_the_backup(self):
        seed_config(self.home, OLDER)
        self.assertEqual(agent_profile.ensure(self.home), "replaced")
        before = (agent_profile.packaged(), listing(self.home), OLDER)
        self.assertEqual(agent_profile.ensure(self.home), "current")
        self.assertEqual(((self.home / "config.toml").read_bytes(), listing(self.home),
                          (self.home / "config.toml.bak").read_bytes()), before)

    def test_a_symlinked_config_is_backed_up_as_a_link_and_replaced(self):
        target = self.root / "target.toml"
        link_config(self.home, target, b"# target\ncustom = true\n")
        self.assertEqual(agent_profile.ensure(self.home), "replaced")
        backup, config = self.home / "config.toml.bak", self.home / "config.toml"
        self.assertEqual((backup.is_symlink(), os.readlink(str(backup)) if backup.is_symlink() else None,
                          target.read_bytes(), config.is_symlink(), config.read_bytes()),
                         (True, str(target), b"# target\ncustom = true\n", False, agent_profile.packaged()))

    def test_a_symlink_to_the_current_version_is_still_replaced(self):
        target = self.root / "current.toml"
        link_config(self.home, target, agent_profile.packaged())
        self.assertEqual(agent_profile.ensure(self.home), "replaced")
        self.assertEqual((target.read_bytes(), (self.home / "config.toml.bak").is_symlink()),
                         (agent_profile.packaged(), True))

    def test_an_existing_backup_symlink_is_replaced_as_an_entry(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"untouched")
        seed_config(self.home, OLDER)
        (self.home / "config.toml.bak").symlink_to(sentinel)
        self.assertEqual(agent_profile.ensure(self.home), "replaced")
        backup = self.home / "config.toml.bak"
        self.assertEqual((backup.is_symlink(), backup.read_bytes(), sentinel.read_bytes()), (False, OLDER, b"untouched"))

    def test_a_non_file_entry_is_refused_without_a_write(self):
        self.home.mkdir(parents=True)
        (self.home / "config.toml").mkdir()
        with self.assertRaises(Blocked) as caught:
            agent_profile.ensure(self.home)
        self.assertEqual((caught.exception.family, listing(self.home)),
                         ("setup.agent_home", [".zplan-profile.lock", "config.toml"]))


class FaultTests(HomeTestCase):
    """A-2/F1-F6: each finite OSError point refuses with `setup.agent_home`, removes its own temp and leaves exactly
    the residual set R-3 lists; a retry then completes with `.bak` == the original config."""

    def fault(self, name):
        """The one OSError R-3 names for `name`, injected at the real call the module makes."""
        if name == "F1":
            return patch.object(agent_profile, "_make_home", side_effect=OSError(28, "mkdir failed"))
        real_open, real_fsync, real_replace = Path.open, os.fsync, os.replace
        seen = {"fsync": 0}

        def open_(self, *args, **kwargs):
            if self.name == ".zplan-profile.lock":
                raise OSError(13, "permission denied")
            return real_open(self, *args, **kwargs)

        def fsync(fd):
            seen["fsync"] += 1
            if seen["fsync"] == (1 if name == "F3" else 2):
                raise NO_SPACE
            return real_fsync(fd)

        def replace(source, destination):
            if Path(destination).name == {"F4": "config.toml.bak", "F6": "config.toml"}.get(name):
                raise NO_SPACE
            return real_replace(source, destination)

        if name == "F2":
            return patch.object(Path, "open", open_)
        which, hook = ("fsync", fsync) if name in ("F3", "F5") else ("replace", replace)
        return patch.object(agent_profile.os, which, side_effect=hook)

    def test_each_fault_point_refuses_and_leaves_exactly_its_residuals(self):
        cases = {"F1": {}, "F2": {"expected": ["config.toml"]},
                 "F3": {"backup": BAK, "expected": RESIDUAL}, "F4": {"backup": BAK, "expected": RESIDUAL},
                 "F5": {"expected": RESIDUAL}, "F6": {"expected": RESIDUAL}}
        for name, case in cases.items():
            with self.subTest(name), self.isolated_home() as home:
                if case:
                    seed_config(home, OLDER, case.get("backup"))
                with self.fault(name):
                    with self.assertRaises(Blocked) as caught:
                        agent_profile.ensure(home)
                self.assertEqual((caught.exception.family, str(home) in str(caught.exception)),
                                 ("setup.agent_home", True))
                if not case:
                    self.assertFalse(home.exists())  # F1: nothing created
                else:
                    kept = BAK if case.get("backup") is not None else (OLDER if name in ("F5", "F6") else None)
                    bak = (home / "config.toml.bak")
                    self.assertEqual((listing(home), (home / "config.toml").read_bytes(),
                                      bak.read_bytes() if kept is not None else None),
                                     (case["expected"], OLDER, kept))  # no temp file survives
                state = agent_profile.ensure(home)
                self.assertEqual((state, listing(home), (home / "config.toml").read_bytes()),
                                 ("written" if not case else "replaced",
                                  [".zplan-profile.lock", "config.toml"] if not case else RESIDUAL,
                                  agent_profile.packaged()))
                if case:
                    self.assertEqual((home / "config.toml.bak").read_bytes(), OLDER)

    def test_a_held_lock_is_the_busy_refusal_and_writes_nothing_else(self):
        seed_config(self.home, OLDER)
        entered, release = threading.Event(), threading.Event()
        real, results = agent_profile._apply, []

        def paused(home, data, current):
            entered.set()
            self.assertTrue(release.wait(10), "writer 1 was never released")
            return real(home, data, current)

        with patch.object(agent_profile, "_apply", side_effect=paused):
            thread = threading.Thread(target=lambda: results.append(agent_profile.ensure(self.home)))
            thread.start()
            self.assertTrue(entered.wait(10), "writer 1 never entered the critical section")
            with self.assertRaises(Blocked) as caught:
                agent_profile.ensure(self.home)
            self.assertEqual((caught.exception.family, listing(self.home)),
                             ("setup.agent_home", [".zplan-profile.lock", "config.toml"]))
            release.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual((results, agent_profile.ensure(self.home), (self.home / "config.toml").read_bytes(),
                          (self.home / "config.toml.bak").read_bytes(), listing(self.home)),
                         (["replaced"], "current", agent_profile.packaged(), OLDER, RESIDUAL))


class MarkerTests(unittest.TestCase):
    """R-2: the closed marker grammar and the undecodable-byte rejection, one documented result per shape."""

    CASES = (("1", b"# zplan-agent-profile: 1\n", 1), ("nine digits", b"# zplan-agent-profile: 123456789\n", 123456789),
             ("zero", b"# zplan-agent-profile: 0\n", None),
             ("leading zero", b"# zplan-agent-profile: 01\n", None), ("sign", b"# zplan-agent-profile: +1\n", None),
             ("space", b"# zplan-agent-profile:  1\n", None), ("crlf", b"# zplan-agent-profile: 1\r\n", None),
             ("bom", b"\xef\xbb\xbf# zplan-agent-profile: 1\n", None),
             ("ten digits", b"# zplan-agent-profile: 1000000000\n", None), ("missing lf", b"# zplan-agent-profile: 1", None),
             ("another prefix", b"# zplan-profile: 1\n", None), ("empty", b"", None), ("str", "# zplan-agent-profile: 1\n", None),
             ("undecodable marker", b"# zplan-agent-profile: \xff\n", None),
             ("undecodable tail", b"# zplan-agent-profile: 1\nx = \xff\n", None))

    def test_the_marker_grammar_and_the_encoding_rule_are_closed(self):
        for name, data, expected in self.CASES:
            with self.subTest(name):
                self.assertEqual(agent_profile.version(data), expected)
        packaged = agent_profile.packaged()  # the packaged file is decodable, so only a real corrupt tail is None
        self.assertEqual(agent_profile.version(packaged + b"\xff\xfe\n"), None)
        self.assertEqual(agent_profile.version(packaged), agent_profile.version(packaged + b"\n"))


class WrittenVersionTests(HomeTestCase):
    """R-4: an int, None for an absent or corrupt config, and never a write, a lock or a resolution."""

    def test_absent_corrupt_and_symlinked_configs_read_without_writing(self):
        self.assertIsNone(agent_profile.written_version(self.home))
        self.assertFalse(self.home.exists())
        seed_config(self.home, agent_profile.packaged() + b"\xff\xfe\n")
        before = listing(self.home)
        self.assertIsNone(agent_profile.written_version(self.home))  # a corrupt tail is not a version
        self.assertEqual(listing(self.home), before)
        agent_profile.ensure(self.home)
        self.assertEqual((agent_profile.written_version(self.home), (self.home / "config.toml").is_symlink()),
                         (agent_profile.version(agent_profile.packaged()), False))
        target = self.root / "elsewhere.toml"
        target.write_bytes(b"# zplan-agent-profile: 4\n")
        (self.home / "config.toml").unlink()
        (self.home / "config.toml").symlink_to(target)
        self.assertEqual((agent_profile.written_version(self.home), (self.home / "config.toml").is_symlink()), (4, True))


class ScopeTests(HomeTestCase):
    """A-3 and A-4 (R-1): only zplan's own home is written, and activation (s2b2) is the one production importer."""

    def test_a_foreign_home_is_refused_without_writing(self):
        for name, path in {"explicit": self.root / "user-home" / ".codex", "other": self.root / "other"}.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    agent_profile.ensure(path)
                self.assertFalse(path.exists())
        self.assertFalse(self.home.exists())
        self.assertEqual((agent_profile.ensure(self.home), (self.home / "config.toml").read_bytes()),
                         ("written", agent_profile.packaged()))  # the private home is the accepted control

    def test_only_setup_and_the_module_itself_mention_agent_profile(self):
        """R-1 after activation (s2b2): `setup.py` is the one production importer (login/launch and the doctor
        profile line); no other module names it, so the profile is written from one place only."""
        hits = sorted(path.name for path in PACKAGE.rglob("*.py")
                      if "agent_profile" in path.read_text(encoding="utf-8"))
        self.assertEqual(hits, ["agent_profile.py", "setup.py"])
