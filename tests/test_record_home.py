"""The recorded-home core (S2 slice s2a1, R-1..R-4): the binding shape (R-2), the pure resolver (R-3) and the two
binding producers that must keep exactly `BINDING_FIELDS` (R-3).

Base replay (A-B): `ShapeTests` is the base-replayable section — the module imports only pre-existing names, and the
candidate-only helpers (`terminal_planner.record_home`, `setup.legacy_codex_home`, `toolchain.valid_codex_home`) are
imported lazily inside the tests that use them, so replaying `ShapeTests` on the base fails at the 5-key assertions
(`valid_binding` returns False there) and never at import.

Interpretations recorded here (worker, s2a1):
- `valid_binding` keeps its historical TypeError for malformed native fields (`version=None`): R-2 only widens the
  accepted key set, so `ShapeTests` never asserts a ValueError on that helper; `record_home.binding_home` is the
  boundary that normalizes it to ValueError (R-3), and a named test pins that.
- "nonempty" for a recorded home is a nonempty str (`bool(value)`); only empty, relative, NUL-bearing, over-long and
  non-str values are judged — no requirement names whitespace-only values.
- The fixture binding is refused by `binding_home` because the shape check refuses it; there is no fixture special
  case and none is added.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner import toolchain
from terminal_planner.engine import NativeEngine
from terminal_planner.runs import NativeDriver


def native_binding(**extra):
    """A 4-key native binding, optionally with extra keys (`codex_home`, a malformed field)."""
    fields = {"executable": "/usr/local/bin/zeroshot", "state_root": "/var/lib/zeroshot",
              "sha256": "a" * 64, "version": "zeroshot 10.12.0"}
    fields.update(extra)
    return fields


class ShapeTests(unittest.TestCase):
    """A-1s: the shape of `toolchain.valid_binding` — the four identity keys alone (a pre-0.5 record) or the four
    plus a recorded `codex_home` (R-2). Any other key set is invalid."""

    def test_shape_accepts_the_four_keys_alone(self):
        self.assertTrue(toolchain.valid_binding(native_binding()))

    def test_shape_accepts_the_four_keys_plus_a_recorded_home(self):
        self.assertTrue(toolchain.valid_binding(native_binding(codex_home="/home/user/.codex")))

    def test_shape_accepts_a_4096_character_absolute_home(self):
        self.assertTrue(toolchain.valid_binding(native_binding(codex_home="/" + "a" * 4095)))

    def test_shape_rejects_a_4097_character_home(self):
        self.assertFalse(toolchain.valid_binding(native_binding(codex_home="/" + "a" * 4096)))

    def test_shape_rejects_an_empty_or_relative_home(self):
        for name, value in {"empty": "", "relative": "relative/.codex", "tilde": "~/.codex"}.items():
            with self.subTest(name):
                self.assertFalse(toolchain.valid_binding(native_binding(codex_home=value)))

    def test_shape_rejects_a_nul_bearing_home(self):
        self.assertFalse(toolchain.valid_binding(native_binding(codex_home="/home/user/.co\x00dex")))

    def test_shape_rejects_a_non_str_home(self):
        for name, value in {"none": None, "int": 1, "bytes": b"/home/user/.codex"}.items():
            with self.subTest(name):
                self.assertFalse(toolchain.valid_binding(native_binding(codex_home=value)))

    def test_shape_rejects_any_other_fifth_key(self):
        for name, extra in {"home": {"home": "/home/user/.codex"},
                            "two keys": {"codex_home": "/home/user/.codex", "more": 1}}.items():
            with self.subTest(name):
                self.assertFalse(toolchain.valid_binding(native_binding(**extra)))


class ResolverTests(unittest.TestCase):
    """A-R: `record_home` over a temp HOME and process `CODEX_HOME` (R-3/R-4): recorded home as is, legacy home for a
    pre-0.5 record, ValueError everywhere else. No network, provider, spawn or home creation."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="z")).resolve()  # short: state dirs hold socket paths
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("CODEX_HOME", None)

    def helpers(self):
        """The candidate-only helpers, imported lazily (see the module docstring)."""
        from terminal_planner import record_home, setup
        return record_home, setup

    def test_a_recorded_home_wins_over_the_process_env(self):
        record_home, _ = self.helpers()
        recorded = str(self.root / "recorded-home")
        os.environ["CODEX_HOME"] = str(self.root / "env-home")
        self.assertEqual(record_home.binding_home(native_binding(codex_home=recorded)), Path(recorded))

    def test_a_four_key_binding_uses_the_process_env_home(self):
        record_home, _ = self.helpers()
        os.environ["CODEX_HOME"] = str(self.root / "legacy-home")
        self.assertEqual(record_home.binding_home(native_binding()), (self.root / "legacy-home").resolve())

    def test_a_four_key_binding_without_codex_home_uses_home_dot_codex(self):
        record_home, _ = self.helpers()
        self.assertEqual(record_home.binding_home(native_binding()), (self.home / ".codex").resolve())
        self.assertFalse((self.home / ".codex").exists())  # resolving creates nothing

    def test_the_recorded_directory_is_returned_unchanged_and_nothing_is_created(self):
        record_home, _ = self.helpers()
        recorded = self.root / "missing-home"
        before = sorted(p.name for p in self.root.iterdir())
        self.assertEqual(record_home.effective_home(str(recorded)), recorded)
        self.assertFalse(recorded.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)

    def test_the_recorded_value_is_never_resolved(self):
        record_home, _ = self.helpers()
        target = self.root / "real-home"
        target.mkdir()
        link = self.root / "link-home"
        link.symlink_to(target)
        resolved = record_home.effective_home(str(link))
        self.assertEqual(resolved, link)
        self.assertNotEqual(str(resolved), str(resolved.resolve()))

    def test_an_invalid_recorded_value_raises_value_error(self):
        record_home, _ = self.helpers()
        for name, value in {"empty": "", "relative": "relative/.codex", "nul": "/a\x00b", "int": 7}.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    record_home.effective_home(value)

    def test_the_fixture_binding_raises_value_error(self):
        record_home, _ = self.helpers()
        with self.assertRaises(ValueError):
            record_home.binding_home({"fixture_id": "fixture-1"})

    def test_malformed_native_fields_raise_value_error_not_type_error(self):
        """Mutation killer: the shape check's own TypeError/AttributeError never escapes `binding_home`."""
        record_home, _ = self.helpers()
        for name, binding in {"non-dict": ["not", "a", "dict"],
                              "version none": native_binding(version=None),
                              "version none and home": native_binding(version=None, codex_home="/home/user/.codex"),
                              "key set without identity": {"executable": "/usr/local/bin/zeroshot",
                                                           "codex_home": "/home/user/.codex"}}.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    record_home.binding_home(binding)

    def test_changing_the_process_env_between_calls_changes_the_legacy_home(self):
        record_home, setup = self.helpers()
        first, second = self.root / "first-home", self.root / "second-home"
        os.environ["CODEX_HOME"] = str(first)
        self.assertEqual(setup.legacy_codex_home(), first.resolve())
        self.assertEqual(record_home.effective_home(None), first.resolve())
        os.environ["CODEX_HOME"] = str(second)
        self.assertEqual(setup.legacy_codex_home(), second.resolve())
        self.assertEqual(record_home.effective_home(None), second.resolve())
        os.environ.pop("CODEX_HOME")
        self.assertEqual(setup.legacy_codex_home(), (self.home / ".codex").resolve())
        self.assertNotEqual(setup.legacy_codex_home(), setup.private_codex_home())


class ProducerTests(unittest.TestCase):
    """A-C: both binding producers keep exactly `BINDING_FIELDS` (R-3). A fifth key here would strand every record
    the writers still compare whole (`prepare`, `check_binding`, `binding_changed`) until s2a2 narrows them."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="z")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.binary = self.root / "zeroshot"
        self.binary.write_text("#!/bin/sh\nprintf '%s\\n'\n" % toolchain.current().zeroshot_version)
        self.binary.chmod(0o700)

    def engine(self, factory=NativeEngine):
        version = toolchain.current().zeroshot_version

        def call(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, version + "\n", "")

        return factory(self.binary, self.root / "state", call=call, sleep=lambda _: None, version=None)

    def authority(self):
        return type("Authority", (), {"fixture_id": None})()

    def test_binary_identity_keeps_exactly_the_binding_fields(self):
        identity = self.engine().binary_identity()
        self.assertEqual(set(identity), set(toolchain.BINDING_FIELDS))
        self.assertNotIn("codex_home", identity)

    def test_native_driver_binding_keeps_exactly_the_binding_fields(self):
        binding = self.engine(NativeDriver).binding(self.authority())
        self.assertEqual(set(binding), set(toolchain.BINDING_FIELDS))
        self.assertNotIn("codex_home", binding)


if __name__ == "__main__":
    unittest.main()
