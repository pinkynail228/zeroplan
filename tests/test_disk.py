"""0.5 S5a slice 2: the pure disk probe and thresholds of `terminal_planner.disk` (parent R-1 mechanics, R-2,
R-5; A-3, A-4, the threshold half of A-2). No production entry point is touched, so there is no base replay;
every case here fails on the base with an import error only because the module is new.

Both seams are always scripted fakes (`scripted_stat`/`scripted_usage`, or a local callable) so the machine's
real free space is never read and the real `os.stat` is never one of the two seam calls under test. A temporary
directory appears once, only for the no-create listing snapshot
(`test_a_deep_root_resolves_to_its_existing_ancestor_without_creating_anything`).

Interpretations recorded here, as the worker's summary never reaches a reviewer (each is also stated in the
docstring of the test that covers it):

* `Verdict.threshold` is the effective block size in GiB for the `low` and `ok` verdicts only; it is `None` for
  the `error` verdict (no free value was compared) and for the leading `invalid_config` verdict (no valid size is
  configured). The invalid_config verdict also carries no names and no path (`""`), and `free`/`threshold` are
  `None`.
* An error `Probe`'s `ancestor` stays `""` and its `device` is `None` when no `stat` ever succeeded for that root
  (a source-callable, `abspath` or `stat` failure); a `usage`-failure `Probe` keeps the first root's `path`,
  `ancestor` and `device`, with `free=None`.
* The `Probe`/`Verdict` output order is the first appearance of each device (or the position of each standalone
  error root) in the input root order; names inside one `Probe` keep input order.
"""

import os
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from terminal_planner import disk


GIB = 2 ** 30


def probed(free, name="root", device=1, error="", path=None):
    """A `Probe` with the identity fields filled: the classify/refusal cases only vary `free`/`error`."""
    path = path if path is not None else "/" + name
    return disk.Probe(names=(name,), path=path, ancestor=path, device=device, free=free, error=error)


def scripted_stat(devices, denied=()):
    """A `stat` over `{path: st_dev}`: `denied` paths raise `PermissionError`, everything else missing is
    `FileNotFoundError` (so the walk-up finds the nearest existing ancestor)."""
    def stat(path, *args, **kwargs):
        if path in denied:
            raise PermissionError(13, "Permission denied", path)
        if path in devices:
            return SimpleNamespace(st_dev=devices[path])
        raise FileNotFoundError(2, "No such file or directory", path)
    return stat


def nul_stat(path, *args, **kwargs):
    """A `stat` that mirrors the real one on an embedded NUL: `ValueError`, and `FileNotFoundError` otherwise."""
    if "\0" in path:
        raise ValueError("embedded null byte")
    raise FileNotFoundError(2, "No such file or directory", path)


def scripted_usage(free_by_path, failing=()):
    """A `usage` over `{path: free_bytes}` that records every call; `failing` paths raise `OSError`."""
    calls = []

    def usage(path):
        calls.append(path)
        if path in failing:
            raise OSError(5, "Input/output error", path)
        return SimpleNamespace(total=0, used=0, free=free_by_path[path])

    usage.calls = calls
    return usage


def _raise(error):
    raise error


class ThresholdTests(unittest.TestCase):
    """A-4 first half: the override grammar and the exact value/None of `threshold`."""

    def test_unset_override_is_five(self):
        """R-2: no `ZPLAN_MIN_FREE_GB` means the 5 GiB default."""
        self.assertEqual(disk.threshold({}), 5)

    def test_a_valid_positive_ascii_integer_is_taken_exactly(self):
        """R-2/A-4: `5`, `0000000005`, `16`, `2000000000` convert to exactly those ints."""
        for raw, expected in (("5", 5), ("0000000005", 5), ("16", 16), ("2000000000", 2000000000)):
            with self.subTest(raw=raw):
                self.assertEqual(disk.threshold({"ZPLAN_MIN_FREE_GB": raw}), expected)

    def test_invalid_values_are_none(self):
        """R-2/A-4: every malformed override is None (invalid configuration), including `0`/`000`."""
        for raw in ("", " 5", "5 ", "+5", "-1", "0", "000", "1.5", "5.0", "1e3", "nan", "inf", "-inf",
                    "５", "٥", "five"):
            with self.subTest(raw=raw):
                self.assertIsNone(disk.threshold({"ZPLAN_MIN_FREE_GB": raw}))

    def test_a_leading_sign_or_space_is_rejected(self):
        """Interpretation/kill: only `[0-9]+` is accepted, so `int(raw)` on the whole string is wrong."""
        for raw in (" 5", "+5", "5 ", "-1"):
            self.assertIsNone(disk.threshold({"ZPLAN_MIN_FREE_GB": raw}))

    def test_non_ascii_digits_are_rejected(self):
        """Interpretation/kill: `str.isdigit` accepts Arabic-Indic and full-width digits, so it is not used."""
        for raw in ("٥", "５"):
            self.assertIsNone(disk.threshold({"ZPLAN_MIN_FREE_GB": raw}))

    def test_leading_zeros_are_allowed_and_converted(self):
        """R-2 round R2: leading zeros are allowed and stripped, not rejected."""
        self.assertEqual(disk.threshold({"ZPLAN_MIN_FREE_GB": "0000000005"}), 5)

    def test_a_5000_digit_value_is_that_exact_integer_without_overflow(self):
        """R-2: the chunked conversion never hits Python's int string-digit limit; 5000 digits stay exact."""
        digits = "9" * 5000
        expected = 0
        for character in digits:
            expected = expected * 10 + int(character)
        self.assertEqual(disk.threshold({"ZPLAN_MIN_FREE_GB": digits}), expected)

    def test_five_thousand_leading_zeros_then_five_is_five(self):
        """R-2: 5000 leading zeros are stripped before the (short) conversion, giving exactly 5."""
        self.assertEqual(disk.threshold({"ZPLAN_MIN_FREE_GB": "0" * 5000 + "5"}), 5)

    def test_the_conversion_never_calls_int_on_the_whole_digit_string(self):
        """Interpretation/R-2: the guard is the mechanism (chunked digits), not the host Python's limit. A spy on
        `builtins.int` proves no `int(str)` sees the whole digit string, which fails where the length is over the
        CPython limit — deterministically killing `_chunked_int = int(digits)` even on hosts (3.9) without it."""
        digits = "9" * 5000
        expected = 0
        for character in digits:
            expected = expected * 10 + int(character)
        seen = []
        real_int = int

        def spy(value=0, *args, **kwargs):
            if isinstance(value, str):
                seen.append(len(value))
            return real_int(value, *args, **kwargs)

        with mock.patch("builtins.int", spy):
            value = disk.threshold({"ZPLAN_MIN_FREE_GB": digits})
        self.assertEqual(value, expected)
        self.assertTrue(seen)
        self.assertLess(max(seen), 4300)

    def test_the_environment_defaults_to_os_environ_at_call_time(self):
        """R-2: with no argument `threshold` reads `os.environ` at call time, not a value frozen at import."""
        original = os.environ.get("ZPLAN_MIN_FREE_GB")
        os.environ["ZPLAN_MIN_FREE_GB"] = "7"
        try:
            self.assertEqual(disk.threshold(), 7)
        finally:
            if original is None:
                os.environ.pop("ZPLAN_MIN_FREE_GB", None)
            else:
                os.environ["ZPLAN_MIN_FREE_GB"] = original


class BoundaryTests(unittest.TestCase):
    """A-2t: block/warn/ok boundaries, equality not below, and the override bands."""

    def test_default_block_five_bounds(self):
        """A-2t: 5 GiB−1 block, 5 GiB warn, 15 GiB−1 warn, 15 GiB ok, 15 GiB+1 ok."""
        cases = ((5 * GIB - 1, "block", "low"), (5 * GIB, "warn", "low"), (15 * GIB - 1, "warn", "low"),
                 (15 * GIB, "ok", "ok"), (15 * GIB + 1, "ok", "ok"))
        for free, severity, kind in cases:
            with self.subTest(free=free):
                verdict = disk.classify([probed(free)], 5)[0]
                self.assertEqual((verdict.severity, verdict.kind), (severity, kind))

    def test_block_is_evaluated_before_warn(self):
        """R-3: block is tested first, so a value below both thresholds blocks (5 GiB−1 here)."""
        verdict = disk.classify([probed(5 * GIB - 1)], 5)[0]
        self.assertEqual((verdict.severity, verdict.kind), ("block", "low"))

    def test_equality_is_not_below_the_block_threshold(self):
        """R-3: equality is not "below", so free == block GiB is not a block."""
        self.assertEqual(disk.classify([probed(5 * GIB)], 5)[0].severity, "warn")

    def test_equality_is_not_below_the_warn_threshold(self):
        """R-3: equality is not "below", so free == 15 GiB is ok, not warn."""
        self.assertEqual(disk.classify([probed(15 * GIB)], 5)[0].severity, "ok")

    def test_override_below_fifteen(self):
        """A-2t: override 3 (below the 15 GiB warn band): 3 GiB−1 blocks and 3 GiB warns."""
        self.assertEqual(disk.classify([probed(3 * GIB - 1)], 3)[0].severity, "block")
        self.assertEqual(disk.classify([probed(3 * GIB)], 3)[0].severity, "warn")

    def test_override_above_fifteen_has_no_warn_band(self):
        """A-2t: override 20 (above 15) has no warn band: 20 GiB−1 blocks, 20 GiB and above are ok."""
        self.assertEqual(disk.classify([probed(20 * GIB - 1)], 20)[0].severity, "block")
        self.assertEqual(disk.classify([probed(20 * GIB)], 20)[0].severity, "ok")
        self.assertEqual(disk.classify([probed(20 * GIB + 1)], 20)[0].severity, "ok")


class InvalidConfigTests(unittest.TestCase):
    """A-4 second half: one leading `invalid_config` block, probes still classified against the default 5."""

    def test_every_invalid_override_leads_with_invalid_config(self):
        """A-4: each invalid override yields one leading `("block", "invalid_config")` with no path."""
        for raw in ("", " 5", "5 ", "+5", "-1", "0", "000", "1.5", "5.0", "1e3", "nan", "inf", "-inf",
                    "５", "٥", "five"):
            with self.subTest(raw=raw):
                verdicts = disk.classify([probed(1 * GIB)], disk.threshold({"ZPLAN_MIN_FREE_GB": raw}))
                self.assertEqual((verdicts[0].severity, verdicts[0].kind, verdicts[0].path),
                                 ("block", "invalid_config", ""))

    def test_invalid_config_keeps_the_probe_verdicts_against_the_default(self):
        """R-3: the probes are still classified against the default 5, so free space stays visible."""
        verdicts = disk.classify([probed(1 * GIB), probed(20 * GIB)], None)
        self.assertEqual([(v.severity, v.kind) for v in verdicts],
                         [("block", "invalid_config"), ("block", "low"), ("ok", "ok")])


class ClassifyTests(unittest.TestCase):
    """R-3: an error probe and the carried `threshold` field."""

    def test_an_error_probe_is_a_warn_of_kind_error_with_the_class_name(self):
        """R-3/R-5: an error probe is `("warn", "error")` and carries only the exception class name."""
        verdict = disk.classify([probed(None, error="PermissionError")], 5)[0]
        self.assertEqual((verdict.severity, verdict.kind, verdict.error), ("warn", "error", "PermissionError"))

    def test_an_error_verdict_carries_no_threshold(self):
        """Interpretation: an error verdict has no compared free value, so `threshold` is None (documented)."""
        self.assertIsNone(disk.classify([probed(None, error="ValueError")], 7)[0].threshold)

    def test_low_and_ok_verdicts_carry_the_effective_threshold(self):
        """Interpretation: only the compared (low/ok) verdicts name the effective block size in GiB."""
        self.assertEqual(disk.classify([probed(1 * GIB)], 7)[0].threshold, 7)
        self.assertEqual(disk.classify([probed(20 * GIB)], 7)[0].threshold, 7)


class RefusalTests(unittest.TestCase):
    """R-4: the first block, invalid_config precedence, and error-versus-block independence."""

    def test_the_first_block_wins(self):
        """R-4: with two blocks `refusal` returns the first, not the last and not the lowest."""
        verdicts = disk.classify([probed(20 * GIB, name="a"), probed(1 * GIB, name="b"),
                                  probed(2 * GIB, name="c")], 5)
        self.assertEqual(disk.refusal(verdicts).names, ("b",))

    def test_invalid_config_precedes_a_low_block(self):
        """R-4/R-3: the invalid_config verdict is first, so it is the refusal even beside a low device."""
        verdicts = disk.classify([probed(1 * GIB)], None)
        self.assertEqual(disk.refusal(verdicts).kind, "invalid_config")

    def test_no_block_is_none(self):
        """R-4: with only ok/warn verdicts the refusal is None."""
        self.assertIsNone(disk.refusal(disk.classify([probed(20 * GIB)], 5)))

    def test_an_error_does_not_hide_another_devices_block(self):
        """Parent R-5 / A-3: a warn error root plus a low device still refuses on the low device."""
        roots = [("broken", lambda: _raise(PermissionError(13, "denied"))), ("low", "/low")]
        probes = disk.probe(roots, stat=scripted_stat({"/low": 2}), usage=scripted_usage({"/low": 1 * GIB}))
        verdicts = disk.classify(probes, 5)
        self.assertEqual(disk.refusal(verdicts).kind, "low")
        self.assertEqual([(v.severity, v.error) for v in verdicts if v.error], [("warn", "PermissionError")])


class ProbeTests(unittest.TestCase):
    """A-3: ancestors, device dedupe, the two seams, error roots, and no creation."""

    def test_a_deep_root_resolves_to_its_existing_ancestor_without_creating_anything(self):
        """A-3/R-1: a root three levels under its ancestor resolves to it, and the temp tree is unchanged."""
        with tempfile.TemporaryDirectory() as base:
            root = os.path.join(base, "a", "b", "c")
            before = sorted(os.listdir(base))
            usage = scripted_usage({base: 9 * GIB})
            probes = disk.probe([("deep", root)], stat=scripted_stat({base: 7}), usage=usage)
            self.assertEqual(len(probes), 1)
            self.assertEqual(probes[0].ancestor, base)
            self.assertEqual(probes[0].free, 9 * GIB)
            self.assertEqual(usage.calls, [base])
            self.assertFalse(os.path.exists(root))
            self.assertEqual(sorted(os.listdir(base)), before)

    def test_two_roots_on_one_device_share_one_probe_and_one_usage_call(self):
        """R-1/A-3: two roots on one `st_dev` form one Probe naming both, with one `usage` call."""
        stat = scripted_stat({"/data/a": 7, "/data/b": 7})
        usage = scripted_usage({"/data/a": 5 * GIB})
        probes = disk.probe([("a", "/data/a"), ("b", "/data/b")], stat=stat, usage=usage)
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].names, ("a", "b"))
        self.assertEqual(probes[0].path, "/data/a")
        self.assertEqual(usage.calls, ["/data/a"])

    def test_two_devices_give_two_probes(self):
        """R-1/A-3: two different devices give two Probes, each with its own `usage` call."""
        stat = scripted_stat({"/data/a": 7, "/data/b": 8})
        usage = scripted_usage({"/data/a": 5 * GIB, "/data/b": 6 * GIB})
        probes = disk.probe([("a", "/data/a"), ("b", "/data/b")], stat=stat, usage=usage)
        self.assertEqual([p.names for p in probes], [("a",), ("b",)])
        self.assertEqual(usage.calls, ["/data/a", "/data/b"])

    def test_device_dedupe_is_by_st_dev_not_by_ancestor_path(self):
        """R-1: dedupe keys on `st_dev`, so two distinct ancestor paths on one device still merge."""
        stat = scripted_stat({"/data/a": 7, "/other/b": 7})
        usage = scripted_usage({"/data/a": 5 * GIB})
        probes = disk.probe([("a", "/data/a"), ("b", "/other/b")], stat=stat, usage=usage)
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].names, ("a", "b"))

    def test_a_callable_source_is_called_for_its_path(self):
        """R-1: a callable source is invoked (root discovery may raise), and its returned path is used."""
        stat = scripted_stat({"/data/a": 7})
        usage = scripted_usage({"/data/a": 5 * GIB})
        probes = disk.probe([("a", lambda: "/data/a")], stat=stat, usage=usage)
        self.assertEqual(probes[0].path, "/data/a")

    def test_a_source_callable_error_is_an_error_probe_with_only_the_class_name(self):
        """R-5: a source-callable failure gives `names=(name,)`, empty path/ancestor, no device, the class."""
        probes = disk.probe([("bad", lambda: _raise(PermissionError("no")))],
                            stat=scripted_stat({}), usage=scripted_usage({}))
        self.assertEqual(probes, (disk.Probe(names=("bad",), path="", ancestor="", device=None, free=None,
                                             error="PermissionError"),))

    def test_a_stat_error_is_an_error_probe_after_the_path_is_computed(self):
        """R-5/R-1: a `stat` error keeps the computed abspath but no ancestor/device, with the class name."""
        stat = scripted_stat({}, denied=("/denied",))
        probes = disk.probe([("bad", "/denied")], stat=stat, usage=scripted_usage({}))
        self.assertEqual(probes, (disk.Probe(names=("bad",), path="/denied", ancestor="", device=None,
                                             free=None, error="PermissionError"),))

    def test_a_stat_error_does_not_stop_the_other_roots(self):
        """R-5/A-3: after one root's stat error the remaining roots are still probed."""
        stat = scripted_stat({"/low": 2}, denied=("/denied",))
        usage = scripted_usage({"/low": 1 * GIB})
        probes = disk.probe([("bad", "/denied"), ("low", "/low")], stat=stat, usage=usage)
        self.assertEqual([(p.names, p.error) for p in probes], [(("bad",), "PermissionError"), (("low",), "")])
        self.assertEqual(probes[1].free, 1 * GIB)

    def test_a_usage_error_makes_one_error_probe_that_later_roots_join(self):
        """R-1: a `usage` failure makes one error Probe; later roots on the device join it, `usage` called once."""
        stat = scripted_stat({"/data/a": 7, "/data/b": 7})
        usage = scripted_usage({}, failing=("/data/a",))
        probes = disk.probe([("a", "/data/a"), ("b", "/data/b")], stat=stat, usage=usage)
        self.assertEqual(probes, (disk.Probe(names=("a", "b"), path="/data/a", ancestor="/data/a", device=7,
                                             free=None, error="OSError"),))
        self.assertEqual(usage.calls, ["/data/a"])

    def test_a_stat_value_error_such_as_a_nul_path_is_an_error_probe(self):
        """R-5: a `ValueError` from `stat` (an embedded NUL) becomes that root's error Probe, not a crash."""
        probes = disk.probe([("nul", "/nonexistent\0root")], stat=nul_stat, usage=scripted_usage({}))
        self.assertEqual((probes[0].error, probes[0].ancestor, probes[0].free), ("ValueError", "", None))


class PermissionAndLowTests(unittest.TestCase):
    """A-3 second half: a stat PermissionError (and separately a source error) plus another low device."""

    def test_a_stat_permission_error_plus_a_low_device_blocks_on_the_low_device(self):
        """A-3: a denied root is a warn error; the other device at 1 GiB is the low block refusal."""
        stat = scripted_stat({"/low": 2}, denied=("/denied",))
        usage = scripted_usage({"/low": 1 * GIB})
        verdicts = disk.classify(disk.probe([("denied", "/denied"), ("low", "/low")], stat=stat, usage=usage), 5)
        self.assertEqual((disk.refusal(verdicts).names, disk.refusal(verdicts).kind), (("low",), "low"))
        warn = [v for v in verdicts if v.error]
        self.assertEqual([(v.severity, v.error) for v in warn], [("warn", "PermissionError")])

    def test_a_source_permission_error_plus_a_low_device_blocks_on_the_low_device(self):
        """A-3: a source-callable PermissionError is a warn error; the low device still refuses."""
        stat = scripted_stat({"/low": 2})
        usage = scripted_usage({"/low": 1 * GIB})
        roots = [("bad", lambda: _raise(PermissionError("no"))), ("low", "/low")]
        verdicts = disk.classify(disk.probe(roots, stat=stat, usage=usage), 5)
        self.assertEqual(disk.refusal(verdicts).names, ("low",))
        self.assertEqual([(v.severity, v.error) for v in verdicts if v.error], [("warn", "PermissionError")])


if __name__ == "__main__":
    unittest.main()
