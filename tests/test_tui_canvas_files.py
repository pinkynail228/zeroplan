"""I5: a project file or a finished stage's diff opens as a closable read-only tab in the canvas.

Textual Pilot over the shared fixture store (`tests/test_tui_milestones.py`): a project file opens as one more
canvas tab after «Scheme» and «Plan», esc closes the shown one and returns to the tab that was active before it,
the arrows cycle every open tab, and nothing opens while any work runs. At most two whole-app tests (A5): A1+A4 in
one and A2+A3 in the other — the viewer's own logic is already covered by `tests/test_tui_viewer.py`.

Interpretations (recorded here; the worker's summary never reaches the reviewers):

- The change bullet names the `note.not_now` text for the work-running guard, while the catalog also carries
  `note.files_running` (the lab's file-specific line, `devtools/ui-lab/work.py`). The bullet's id is kept: both
  refusals show `strings.text("note.not_now", name=...)` with the command the guard protects (`/open`, `/diff`),
  the same id run i2 uses for a command that cannot act now. `note.files_running` is left unused.
- The token-less refusal of `open_diff_tab` (nothing finished selected) uses that same `note.not_now` text: the
  brief fixes no id for it and `/diff` has nothing to act on.
- "the tab that was active before" is the real previous tab — view or base — tracked per canvas tab and restored
  when that tab closes, with a fallback to the last base tab shown when the previous tab has already closed. This
  repairs the earlier base-only reading, which returned to the base tab and lost per-tab history.
- A5 caps the whole-app tests at two, so the regressions for the repaired defects live inside those two tests
  (the repeated-diff replacement, the binary-file refusal and the prior-tab return) instead of extra whole-app
  methods; the viewer's own binary refusal stays covered by `tests/test_tui_viewer.py`.
"""

import unittest

from terminal_planner.tui import strings
from test_tui_milestones import MilestoneShell
from tui_support import HAVE_TEXTUAL, screen_text

VIEW1 = "tab-view-1"  # the first file tab's id (the counter names them tab-view-N in order)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8")
class CanvasShell(MilestoneShell):
    """The milestone shell with a text/label reader and the planner double (A3's planner-active case)."""

    def setUp(self):
        super().setUp()
        from test_tui_planning import Planner
        self.planner = Planner()

    def controller(self, readiness=None, **kw):
        kw.setdefault("engine_factory", lambda name, terminal: self.planner)
        return super().controller(readiness, **kw)

    def main(self):
        """The main screen, whatever modal is on top."""
        return next(s for s in self.app.screen_stack if type(s).__name__ == "MainScreen")

    def tab(self):
        """The id of the canvas tab the right pane shows (`TabbedContent.active`)."""
        return self.main().query_one("#right").active

    def shown(self):
        """I7: the page the main screen shows — «Conversation» (`ui.TAB_CHAT`) while narrow mode shows the chat, else
        the active canvas tab (`self.tab()`); in wide mode both panes show, so it is always the canvas tab."""
        from terminal_planner.tui import app as ui
        screen = self.main()
        return ui.TAB_CHAT if screen.narrow and screen.chat_shown else self.tab()

    async def chat_status(self, pilot, text):
        """I7: the app's own status line (`status_note`'s `chat_note`) lives above the chat, which narrow mode
        hides while the canvas is shown; show the chat page — as the owner would — and wait for `text` there."""
        screen = self.main()
        if screen.narrow and not screen.chat_shown:
            screen.show_chat()
            await pilot.pause()
        await self.shows(pilot, text)

    def tabs(self):
        """Every canvas pane id, in the strip's order."""
        from textual.widgets import TabPane
        return [pane.id for pane in self.app.query(TabPane)]

    def file_tabs(self):
        """The open file tabs' ids, oldest first (the diff tab excluded)."""
        from terminal_planner.tui import app as ui
        return [tab for tab in self.main().view_tabs if tab != ui.TAB_DIFF]

    async def open_planner(self, pilot, timeout=8.0):
        """The app watching a stored observing revision (A3's planner case); the revision itself is written
        before the shell is opened (`plan_store`), while the store is still free."""
        await self.until(pilot, lambda: self.app.watching, timeout)

    def plan_store(self):
        """Store an observing revision with the planner kept busy (A3's planner case). Call it while no controller
        holds the store — before the shell that watches it."""
        from terminal_planner.authority import Authority
        from test_terminal_planner import ROLES
        from test_tui_planning import GOAL
        self.planner.running = True
        with Authority(self.state, self.project, fixture_id="test") as authority:
            authority.begin(GOAL, ROLES, "fixture")
            self.planner.receipt(authority)


class CanvasFileTabTests(CanvasShell):
    async def test_a1_a4_a_file_opens_as_a_readable_tab_and_esc_or_the_arrows_manage_the_tabs(self):
        """A1+A4 at 120x40: `open_file_tab("README.md")` shows a third tab after «Scheme» and «Plan», titled with
        the file name and made active, holding the file's first lines with their numbers; a name outside the
        project and a missing one open no tab and show the viewer's own refusal on the status line. esc then closes
        the shown file tab and returns to the tab active before it, `←`/`→` cycle every open tab («Scheme» ->
        «Plan» -> the file tabs -> «Scheme»), and opening a fourth file closes the oldest.

        I7 at 80x24 (narrow): the canvas is hidden at start and `open_file_tab` brings it into view with the file
        tab; a refusal shows on the chat's own status line once the chat page is shown again; esc returns to
        «Plan»; and the cycle puts «Conversation» in front of the canvas tabs. The canvas-only management above stays
        the 120x40 (wide) case, where both panes are shown."""
        self.approve(running=False)
        (self.project / "README.md").write_text("# Title\nfirst line\nsecond line\n")
        for name in ("a.txt", "b.txt", "c.txt", "d.txt", "e.txt"):
            (self.project / name).write_text(name + "\n")
        from terminal_planner.tui import app as ui
        for size in ((120, 40), (80, 24)):
            with self.subTest(size=size):
                async with self.shell(size=size) as pilot:
                    await self.loaded(pilot)
                    main = self.main()
                    if size[0] < 100:
                        # I7: below 100 columns the screen is narrow — the chat alone at start. This subtest
                        # covers that layout: opening a file from the chat shows the canvas with the file tab, a
                        # refusal shows on the chat's own status line (the app's line lives above the chat, so the
                        # chat page is shown to read it), esc closes the file tab and returns to «Plan», and the
                        # arrows cycle «Conversation» in front of the canvas tabs. The full canvas-only management
                        # (the previous-tab return, a fourth file closing the oldest) runs at 120x40 below.
                        self.assertEqual(self.tab(), ui.TAB_PLAN)  # nothing runs: the canvas opens on «Plan»
                        main.open_file_tab("README.md")  # from the chat: the canvas appears with the file tab
                        await self.shows(pilot, "1 # Title")
                        self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                        self.assertEqual(self.tab(), VIEW1)
                        shown = screen_text(self.app)
                        self.assertIn("README.md", shown)
                        self.assertIn("1 # Title", shown)
                        self.assertIn("2 first line", shown)
                        # A1: both refusals open no tab; the viewer's own text lands on the status line.
                        main.open_file_tab("../x")
                        await self.chat_status(pilot, strings.text("note.view_outside", name="../x"))
                        self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                        self.assertIn(strings.text("note.view_outside", name="../x"), self.flat())
                        main.open_file_tab("missing-name")
                        await self.chat_status(pilot, strings.text("note.view_missing", name="missing-name"))
                        self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                        self.assertIn(strings.text("note.view_missing", name="missing-name"), self.flat())
                        # Regression (A1): a binary file is refused by the render, the same refusal path.
                        (self.project / "binary.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x01")
                        main.status_note("")
                        await pilot.pause()
                        main.open_file_tab("binary.png")
                        await self.chat_status(pilot, strings.text("note.view_binary", name="binary.png"))
                        self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                        self.assertIn(strings.text("note.view_binary", name="binary.png"), self.flat())
                        # A4: esc closes the shown file tab and returns to «Plan», the tab active before it.
                        await pilot.press("escape")
                        await pilot.pause()
                        self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN])
                        self.assertEqual(self.tab(), ui.TAB_PLAN)
                        # I7: the cycle puts «Conversation» in front of the canvas tabs (chat -> Scheme -> Plan -> …).
                        for key, expected in (("right", ui.TAB_LIVE), ("right", ui.TAB_PLAN),
                                              ("left", ui.TAB_LIVE), ("left", ui.TAB_CHAT)):
                            await pilot.press(key)
                            await pilot.pause()
                            self.assertEqual(self.shown(), expected, key)
                        continue
                    self.assertEqual(self.tab(), ui.TAB_PLAN)  # nothing runs: the canvas opens on «Plan»
                    # A1: the file is a third tab, active, with the first lines numbered.
                    main.open_file_tab("README.md")
                    await self.shows(pilot, "1 # Title")  # the pane's own render, once its tab is laid out
                    self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                    self.assertEqual(self.tab(), VIEW1)
                    shown = screen_text(self.app)
                    self.assertIn("README.md", shown)  # the tab title
                    self.assertIn("1 # Title", shown)
                    self.assertIn("2 first line", shown)
                    # A1: both refusals open no tab; the viewer's own text lands on the status line.
                    main.open_file_tab("../x")
                    await self.shows(pilot, strings.text("note.view_outside", name="../x"))
                    self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                    self.assertIn(strings.text("note.view_outside", name="../x"), self.flat())
                    main.open_file_tab("missing-name")
                    await self.shows(pilot, strings.text("note.view_missing", name="missing-name"))
                    self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                    self.assertIn(strings.text("note.view_missing", name="missing-name"), self.flat())
                    # Regression (A1): a binary project file is refused by the *render* (`viewer.file_view`
                    # raises `ViewError('note.view_binary')`), not by `resolve`; it must take the same refusal
                    # path — no tab, the catalog text on the status line, no leaked exception.
                    (self.project / "binary.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x01")
                    main.status_note("")
                    await pilot.pause()
                    main.open_file_tab("binary.png")
                    await self.shows(pilot, strings.text("note.view_binary", name="binary.png"))
                    self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, VIEW1])
                    self.assertIn(strings.text("note.view_binary", name="binary.png"), self.flat())
                    # A4: esc closes the shown file tab and returns to «Plan», the tab active before it.
                    await pilot.press("escape")
                    await pilot.pause()
                    self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN])
                    self.assertEqual(self.tab(), ui.TAB_PLAN)
                    # Regression (A4, base fallback): open a.txt, switch to «Scheme», then open b.txt from
                    # there; Esc returns to «Scheme» — the tab shown before b.txt — not to a.txt (the removal's
                    # neighbour) nor to «Plan». The actual previous tab is tracked, base or view.
                    main.open_file_tab("a.txt")
                    await pilot.pause()
                    self.assertEqual(self.tab(), "tab-view-2")
                    await pilot.press("right")  # view2 -> Scheme
                    await pilot.pause()
                    self.assertEqual(self.tab(), ui.TAB_LIVE)
                    main.open_file_tab("b.txt")
                    await pilot.pause()
                    self.assertEqual(self.tab(), "tab-view-3")
                    await pilot.press("escape")
                    await pilot.pause()
                    self.assertEqual(self.tab(), ui.TAB_LIVE)
                    self.assertEqual(self.file_tabs(), ["tab-view-2"])
                    # A4: the arrows cycle every open tab, the file tabs included.
                    main.open_file_tab("a.txt")  # already open: activates tab-view-2, no new tab
                    await pilot.pause()
                    main.open_file_tab("b.txt")  # b.txt closed above: a new tab, tab-view-4
                    await pilot.pause()
                    self.assertEqual(self.file_tabs(), ["tab-view-2", "tab-view-4"])
                    self.assertEqual(self.tab(), "tab-view-4")
                    for key, expected in (("right", ui.TAB_LIVE), ("right", ui.TAB_PLAN),
                                          ("right", "tab-view-2"), ("right", "tab-view-4"),
                                          ("left", "tab-view-2")):
                        await pilot.press(key)
                        await pilot.pause()
                        self.assertEqual(self.tab(), expected, key)
                    # Regression (A4): the return target is the tab shown just before the opened one, not the
                    # base tab. Open c.txt (tab-view-5) while a.txt (tab-view-2) is shown: Esc returns to a.txt
                    # — the real previous tab — not to b.txt (the removal's neighbour, the earlier behaviour).
                    main.open_file_tab("c.txt")
                    await pilot.pause()
                    self.assertEqual(self.tab(), "tab-view-5")
                    await pilot.press("escape")
                    await pilot.pause()
                    self.assertEqual(self.tab(), "tab-view-2")
                    self.assertEqual(self.file_tabs(), ["tab-view-2", "tab-view-4"])
                    # A4: a fourth file tab closes the oldest (tab-view-2, from a.txt).
                    main.open_file_tab("d.txt")  # tab-view-6
                    await pilot.pause()
                    self.assertEqual(self.file_tabs(), ["tab-view-2", "tab-view-4", "tab-view-6"])
                    main.open_file_tab("e.txt")  # tab-view-7: a fourth, closes tab-view-2
                    await pilot.pause()
                    self.assertEqual(self.file_tabs(), ["tab-view-4", "tab-view-6", "tab-view-7"])
                    self.assertNotIn("tab-view-2", self.tabs())
                    self.assertEqual(self.tab(), "tab-view-7")


class CanvasDiffTabTests(CanvasShell):
    async def test_a2_a3_the_diff_opens_for_a_finished_stage_only_and_never_while_work_runs(self):
        """A2 then A3: nothing finished selected means `open_diff_tab` opens no tab and says why; while a fixture
        stage runs both entry points open nothing and show the not-now text; once the stage is finished the diff
        opens as «Changes M1» with the fixture diff lines at 120x40; and with the planner active both entry
        points open nothing and show the not-now text too."""
        self.approve(running=False)
        (self.project / "README.md").write_text("# Title\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "readme")  # a start needs a clean checkout (the fixture driver refuses a dirty one)
        from terminal_planner.tui import app as ui
        self.driver.gate.clear()
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            main = self.main()
            # A2: nothing finished selected (no attempt at all) -> no tab, the status line says why.
            main.open_diff_tab()
            await self.shows(pilot, strings.text("note.not_now", name="/diff"))
            self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN])
            self.assertIn(strings.text("note.not_now", name="/diff"), self.flat())
            # A3: start the stage and hold its watch slice, so it really runs.
            await self.begin_run(pilot)
            await self.until(pilot, lambda: any(r.active for r in (self.app.snapshot.rows
                                                                   if self.app.snapshot else ())))
            before = self.tabs()
            main.status_note("")  # forget the note the A2 step left, so each wait below proves the new one
            await pilot.pause()
            main.open_file_tab("README.md")
            await self.shows(pilot, strings.text("note.not_now", name="/open"))
            self.assertEqual(self.tabs(), before)
            self.assertIn(strings.text("note.not_now", name="/open"), self.flat())
            main.status_note("")
            await pilot.pause()
            main.open_diff_tab()
            await self.shows(pilot, strings.text("note.not_now", name="/diff"))
            self.assertEqual(self.tabs(), before)
            self.assertIn(strings.text("note.not_now", name="/diff"), self.flat())
            # Let the stage finish, then open its end screen with [o] (i3c: an awaiting-merge end no longer pops
            # the run screen by itself — the stage-done card takes its place) and close it, so the canvas is the
            # active screen again.
            self.driver.gate.set()
            await self.open_merge_end(pilot)
            await pilot.press("escape")
            await pilot.pause()
            # A2: the finished stage's diff opens as one diff tab with the fixture diff lines.
            main = self.main()
            main.open_diff_tab()
            title = strings.text("canvas.diff_tab", stage="M1")  # the catalog title («Changes M1» in English)
            await self.shows(pilot, title)
            await self.shows(pilot, "+Fixture driver change for milestone M1")  # the diff pane's own render
            self.assertEqual(self.tab(), ui.TAB_DIFF)
            shown = screen_text(self.app)
            self.assertIn(title, shown)
            self.assertIn("+Fixture driver change for milestone M1", shown)
            # Regression (A2): a second successful diff replaces the one diff tab in place. Re-requesting it while
            # the pane is mounted must not reuse the id of a pane whose `remove_pane` has not completed
            # (`DuplicateIds`); the tab count stays two + one diff tab.
            main.open_diff_tab()
            await self.shows(pilot, "+Fixture driver change for milestone M1")
            await pilot.pause()
            self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, ui.TAB_DIFF])
            self.assertEqual(self.tab(), ui.TAB_DIFF)
            # Regression (A3): the controller answers asynchronously, so work may start while the request is in
            # flight; a delivered success must recheck activity and then keep the canvas — no tab opens and the
            # not-now text replaces the status line, while the already open diff tab stays.
            self.app.watching = True
            try:
                main.status_note("")
                await pilot.pause()
                main.diff_opened("M1", type("Outcome", (), {"kind": "diff", "lines": ["+late change"]})(), None)
                await self.shows(pilot, strings.text("note.not_now", name="/diff"))
                self.assertEqual(self.tabs(), [ui.TAB_LIVE, ui.TAB_PLAN, ui.TAB_DIFF])
                self.assertIn(strings.text("note.not_now", name="/diff"), self.flat())
                self.assertNotIn("+late change", screen_text(self.app))
            finally:
                self.app.watching = False
            await pilot.press("ctrl+q")  # release the store for the planner session below
        # A3: with the planner active the same two entry points open nothing and show the not-now text.
        self.plan_store()
        async with self.shell(size=(120, 40)) as pilot:
            await self.open_planner(pilot)
            main = self.main()
            before = self.tabs()
            main.open_file_tab("README.md")
            await self.shows(pilot, strings.text("note.not_now", name="/open"))
            self.assertEqual(self.tabs(), before)
            self.assertIn(strings.text("note.not_now", name="/open"), self.flat())
            main.open_diff_tab()
            await self.shows(pilot, strings.text("note.not_now", name="/diff"))
            self.assertEqual(self.tabs(), before)
            self.assertIn(strings.text("note.not_now", name="/diff"), self.flat())
            await pilot.press("ctrl+q")
