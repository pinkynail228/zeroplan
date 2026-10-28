"""S5a slice 1 (s5a1): the readiness WARN contract, with no producer of warnings yet.

Severity lives on the readiness item (`setup.item`, `setup.severity`): "ok", "warn" or "block". A warning keeps
`ok=True`, so it never blocks a start, plan or resume; it is only shown — `zplan doctor` prints `WARN:` and still
exits 0, the plain start says each warning once with no menu, the readiness screen lists it, and the full-screen
Settings row marks it (yellow `! `) and keeps its whole escaped doctor line. Nothing here produces warnings: the
disk item and the 15 GiB threshold arrive in s5a2/s5a3, so these tests inject the item through the existing entry
points, exactly as the compatibility half of the parent acceptance demands (A-2w).

Interpretations (also noted where they bite):

- The public start path filters readiness by id (`planning.Planning.items("start")`, `NEEDS["start"]` minus
  `FIXTURE_SKIPS`), so a warn item must reuse an id that is already a start check to reach the screens here. This
  slice adds no producer and no `NEEDS` entry; s5a3 adds `disk` to `NEEDS`. The tests therefore mark the existing
  `clean` item as a warning — the id is only the filter key, the line and doctor text are the warning's.
- `readiness_screen` lists a warn line with the same `! ` prefix as a missing line (R-3: "lists warn lines too"),
  and the warning adds no key: the readiness menu is byte-identical with and without it.
- The TUI `Check.severity` is resolved in `controller.checks_of` from the item dict (`i.get("severity")` else the
  `ok`/`block` default, the same expression as `setup.severity`); the controller intentionally does not import
  `setup` (its module docstring), and the field is read only as data by the Settings screen.
- R-6 also edits docs/USER_FLOW.md; `R6DocSentenceTests` keeps the added sentence present and the file free of a
  glued Markdown block start (the acceptance review caught a wrapped line beginning with `0.`).
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal_planner import setup
from terminal_planner.authority import Authority as RealAuthority
from terminal_planner.planning import Planning
from test_docs import glued
from test_ux import UxTest
from test_tui import ShellTest

REPO = Path(__file__).resolve().parents[1]

WARN_DOCTOR = "Disk: 13 GiB free (threshold 15 GiB)"
WARN_LINE = "Low disk space: 13 GiB (threshold 15 GiB)"


def ok_item(name):
    return {"id": name, "ok": True, "doctor": name + " ok", "line": name, "detail": "", "key": None}


def warn_item(name="git"):  # an id every model action asks for, a fixture session included
    return {"id": name, "ok": True, "severity": "warn", "doctor": WARN_DOCTOR, "line": WARN_LINE,
            "detail": "", "key": None}


class SeverityContractTests(unittest.TestCase):
    """A-S: `item()`'s new `severity` and the `severity()` reader. Candidate-only (the base has neither)."""

    def test_item_defaults_the_missing_severity_from_ok(self):
        self.assertEqual(setup.item("x", True, "d", "l")["severity"], "ok")
        self.assertEqual(setup.item("x", False, "d", "l")["severity"], "block")

    def test_item_accepts_each_consistent_pair(self):
        self.assertEqual(setup.item("x", True, "d", "l", severity="ok")["severity"], "ok")
        self.assertEqual(setup.item("x", True, "d", "l", severity="warn")["severity"], "warn")
        self.assertEqual(setup.item("x", False, "d", "l", severity="block")["severity"], "block")

    def test_item_rejects_each_inconsistent_pair(self):
        for severity, ok in (("warn", False), ("ok", False), ("block", True)):
            with self.subTest(severity=severity, ok=ok), self.assertRaises(ValueError):
                setup.item("x", ok, "d", "l", severity=severity)

    def test_item_rejects_an_unknown_severity_word(self):
        for severity in ("WARN", "blocked", "warning", "", 1, False):
            with self.subTest(severity=severity), self.assertRaises(ValueError):
                setup.item("x", True, "d", "l", severity=severity)

    def test_severity_reads_a_dict_without_the_key(self):
        self.assertEqual(setup.severity({"ok": True}), "ok")
        self.assertEqual(setup.severity({"ok": False}), "block")
        self.assertEqual(setup.severity({"ok": True, "severity": "warn"}), "warn")
        self.assertEqual(setup.severity({"ok": False, "severity": "block"}), "block")
        self.assertEqual(setup.severity({"ok": True, "severity": ""}), "ok")  # a falsy value falls back


class DoctorWarnTests(unittest.TestCase):
    """A-2w (doctor half): a warn item prints `WARN:` and does not fail doctor; a block item still does.

    R-8: `doctor` reads the process's own `private_codex_home()` for its profile line whenever `CODEX_HOME` is
    empty or unset, so the fixture pins that home — and an empty `CODEX_HOME` — inside a temporary root instead
    of letting the check (and the host's own data root) stand in for it. The readiness list itself is stubbed."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        environment = patch.dict(os.environ, {"HOME": str(root / "home"), "XDG_DATA_HOME": str(root / "data"),
                                              "XDG_CONFIG_HOME": str(root / "config"), "CODEX_HOME": ""})
        environment.start()
        self.addCleanup(environment.stop)

    def doctor(self, items):
        messages = []
        with patch.object(setup, "readiness", lambda *a, **k: [dict(i) for i in items]):
            code = setup.doctor(messages.append)
        return code, messages

    def test_a2w_a_warn_item_prints_warn_and_exits_zero(self):
        """A literal warn dict through the existing `setup.doctor`: on the base this prints `OK:` and fails here."""
        code, messages = self.doctor([warn_item()])
        self.assertIn("WARN: " + WARN_DOCTOR, messages)
        self.assertNotIn("OK: " + WARN_DOCTOR, messages)
        self.assertEqual(code, 0, messages)
        self.assertIn("Plan: ready.", messages)

    def test_a2w_a_block_item_still_blocks_next_to_a_warning(self):
        block = {"id": "disk", "ok": False, "severity": "block", "doctor": "Disk: 3 GiB free",
                 "line": "Low disk space", "detail": "Free up some space.", "key": "i"}
        code, messages = self.doctor([warn_item(), block])
        self.assertIn("WARN: " + WARN_DOCTOR, messages)
        self.assertIn("BLOCKED: " + block["doctor"], messages)
        self.assertEqual(code, 1, messages)
        self.assertNotIn("Plan: ready.", messages)


class PlainStartWarnTests(UxTest):
    """A-2w (plain half): the line start says each warning once and goes on, with no readiness menu."""

    def readiness(self):
        return lambda: [warn_item(), ok_item("identity"), ok_item("repo"), ok_item("branch")]

    def test_a2w_plain_start_shows_the_warning_and_proceeds_without_a_menu(self):
        """A literal warn dict through the existing session: on the base nothing is shown and this fails."""
        output, _ = self.fixture("q", "q", "q", readiness=self.readiness())
        self.assertIn("! " + WARN_LINE, output)
        self.assertNotIn("[g] check again", output)  # no readiness menu: the run was not blocked
        self.assertIn("zplan · " + self.project.name, output)  # ... and the home screen was reached

    def test_a2w_readiness_screen_lists_the_warning_without_adding_a_key(self):
        """The warning is listed while another check is missing; the menu line is unchanged (no key, no action)."""
        def ready():
            return [warn_item(), ok_item("identity"), ok_item("repo"),
                    {"id": "branch", "ok": False, "doctor": "branch", "line": "HEAD detached",
                     "detail": "git switch", "key": "i"}]
        without = lambda: [dict(i) for i in ready() if i["id"] != "git"]
        with_warn, _ = self.fixture("q", readiness=ready)
        without_warn, _ = self.fixture("q", readiness=without)
        self.assertIn("! " + WARN_LINE, with_warn)          # R-3: the readiness screen lists it too
        self.assertIn("! HEAD detached", with_warn)        # beside the missing check
        menu = lambda text: [line for line in text.splitlines() if "check again" in line]
        self.assertEqual(menu(with_warn), menu(without_warn))  # the warning added no key or action


class PlanningWarnTests(UxTest):
    """A-C: a warn item keeps `ok=True`, so the planning gate and every `all(i["ok"])` stay green (R-5)."""

    def test_ac_a_warn_item_leaves_planning_start_ready(self):
        names = ("socket", "tools", "codex", "codex_home", "auth", "roles",
                 "git", "identity", "repo", "branch", "origin", "clean")
        items = lambda: [setup.item(n, True, n, n, severity="warn" if n == "git" else None) for n in names]
        runs = type("Runs", (), {"engine": object()})()
        with RealAuthority(None, self.project) as authority:
            gate = Planning(authority, runs, lambda *_: None, readiness=items).gate(action="start")
        self.assertTrue(gate.ok, gate)


class R6DocSentenceTests(unittest.TestCase):
    """R-6 repair: the `WARN:` sentence this slice adds to docs/USER_FLOW.md is present and its paragraph
    introduces no glued Markdown block start.

    Class: a live-docs paragraph line that itself begins a Markdown block (the acceptance review caught the
    wrapped sentence starting a line with `0.`, which CommonMark would render as an ordered list inside the
    paragraph). Domain: docs/USER_FLOW.md, the file this slice edits. Oracle: the repository's own live-docs
    guard `test_docs.glued` (a regex over the file's own text, independent of any production helper) plus a
    whitespace-normalized substring check for the sentence's wording — so re-wrapping the sentence to another
    bad boundary, or dropping it, fails here.
    """

    def test_the_warn_sentence_is_present_and_user_flow_has_no_glued_block(self):
        text = (REPO / "docs" / "USER_FLOW.md").read_text(encoding="utf-8")
        self.assertIn("A `WARN:` line names a non-blocking issue and keeps the exit code 0.", " ".join(text.split()))
        self.assertEqual(glued(text), [])


class SettingsWarnTests(ShellTest):
    """A-2w (full-screen half): the warn row keeps the whole doctor line under a yellow `! ` marker (R-4)."""

    def marker_style(self, renderable, index):
        for span in renderable.spans:
            if span.start <= index < span.end:
                return str(span.style)
        return None

    async def test_a2w_settings_marks_a_warning_yellow_and_keeps_its_doctor_line(self):
        """A literal warn dict through the fixture controller: on the base the row is a `✓ ` and this fails."""
        readiness = lambda: [warn_item(), ok_item("identity"), ok_item("repo"), ok_item("branch")]
        async with self.shell(self.controller(readiness=readiness), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await pilot.pause(0.2)
            renderable = self.app.screen.query_one("#checks").content
        plain = renderable.plain
        self.assertIn("! " + WARN_DOCTOR, plain)      # the full escaped doctor line, as an ok row shows
        self.assertNotIn("✓ " + WARN_DOCTOR, plain)   # never rendered as ok
        self.assertNotIn(WARN_LINE, plain)            # and never the short block line
        marker = plain.index("! " + WARN_DOCTOR)
        self.assertEqual(self.marker_style(renderable, marker), "yellow")  # the warn marker, not the red block


if __name__ == "__main__":
    unittest.main()
