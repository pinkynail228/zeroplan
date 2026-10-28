"""i3-chat-inline: the conversation as a scroll whose own PageUp/PageDown page it (release 0.5.2).

The chat pane is no longer one `Static` painting rows from a hand-computed layout: `#chat` is a `VerticalScroll`
holding one widget per retained history entry (`MainScreen.ChatMessage`), with the status area (`#status`)
below it and the decision cards mounted inline among the entries. The old offset
arithmetic (`chat_scroll`/`chat_layout`, `chat_offset`, `SCROLL_MARKER`, `chat_page`, the R-1/R-3/R-5 rules and
their pure classes) is gone with it and its tests are retired here; what stays is the behaviour the task keeps:

- R-2: the conversation's PageUp/PageDown are the screen's own priority bindings, guarded by `draft_keys_ready`
  (the plan pane's focus on `MainScreen`), and they page the `#chat` scroll itself.
- R-4: an accepted owner send, or a transcript that grew (the store's own entry count, `ChatState.transcript`),
  returns the view to the bottom; a live/stream update and a poll while the owner is scrolled up keep the position.

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- "the view is at the bottom" is the scroll's own end: `scroll_offset.y == max_scroll_y`, the `#chat` widget's
  numbers, never a row count the test computes. A view that has nothing to scroll is at its end too.
- "PageUp shows older entries" is read off the drawn screen (`screen_text`, the tui_support reading the other
  shell tests use): the pane is ~11 conversation rows at 120x24, so the oldest seeded entry is drawn only after
  the scroll moved. The entry texts are spelled out (`строка 0` … `строка 39`; 0.6.3 V2 has no
  author line), which is what the shared pipeline draws for the seeded one-row entries.
- The live line is drawn by `#status`, the Static below the scroll — the thinking row — so it
  stays visible while the conversation is scrolled up (the old tests asserted it "above" the marker; the marker is
  gone and the row moved out of the body).
- The append that a capped window cannot show (40 identical entries plus one more leaves the widget list exactly
  as it was) is still an append for R-4: `ChatState.transcript` carries it (`note_chat_transcript`), and the view
  returns to the bottom although no widget changed. `test_a4_a_capped_append_returns_the_view_to_the_bottom` is
  that case, the one the earlier scroll run's reviewer (F1) made the rule for.
- The pure `transcript_size` checks stay: they read `chat.py`, which this run does not touch, and they are the
  provenance the R-4 rule is built on.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401  (its import joins the offline wheelhouse to sys.path before the guarded imports)
from tui_support import HAVE_TEXTUAL, screen_text

from terminal_planner.architect import Architect
from terminal_planner.authority import Blocked
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui.controller import checks_of
from test_architect import MCP_LIST
from test_tui import check
from test_tui_chat import OPENING, PARTIAL, REPLY, ChatShell, Fixture, chat_band

TEXTUAL_REASON = "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"

if HAVE_TEXTUAL:
    from terminal_planner.tui import app as app_module
    from terminal_planner.tui import card_kinds, cards

# The scripted codex that can hold its stream open across explicit gates: a step emits its `lines`, waits for each
# `gates` file (a handshake the test creates), then emits that gate's lines. The turn's reader delivers each batch
# as its own stream event, so the live-update test scrolls between two updates with no timer deciding it.
STREAM_FAKE = r'''#!%(python)s
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
scenario = json.load(open(os.path.join(here, "scenario.json")))
if "--help" in sys.argv:
    print(scenario.get("help", "exec --json"))
    sys.exit(0)
''' + MCP_LIST + r'''calls = os.path.join(here, "calls.jsonl")
index = sum(1 for _ in open(calls)) if os.path.exists(calls) else 0
sys.stdin.read()
with open(calls, "a") as stream:
    stream.write(json.dumps({"argv": sys.argv[1:]}) + "\n")
step = scenario["steps"][min(index, len(scenario["steps"]) - 1)]

def emit(lines):
    for line in lines:
        sys.stdout.write((line if isinstance(line, str) else json.dumps(line)) + "\n")
        sys.stdout.flush()

emit(step.get("lines", []))
for gate in step.get("gates", []):
    end = time.time() + gate.get("timeout", 30)
    while not os.path.exists(gate["file"]) and time.time() < end:
        time.sleep(0.02)
    emit(gate.get("lines", []))
sys.exit(step.get("exit", 0))
'''


class StreamFixture(Fixture):
    """The chat fixture whose scripted codex waits on explicit gates (see `STREAM_FAKE`)."""

    def __init__(self, root, project):
        super().__init__(root, project)
        self.codex.write_text(STREAM_FAKE % {"python": sys.executable})
        self.codex.chmod(0o755)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class TranscriptProvenanceTests(unittest.TestCase):
    """R-4's append signal at its source: `transcript_size` counts the store's own entries, uncapped by `HISTORY`
    and unclipped by `ENTRY_TEXT`, so a reload that grew the transcript is visible whatever the retained window
    shows. This is the class of state the earlier scroll run got wrong (`appended_entries` compared the retained
    window, so 40 identical entries plus one more, 39 plus 2 and 40 plus 40 all read as unchanged)."""

    def test_the_count_is_uncapped_by_the_history_limit(self):
        rows = [{"role": "owner", "text": "строка %d" % index} for index in range(chat_module.HISTORY + 7)]
        self.assertEqual(chat_module.transcript_size(rows), chat_module.HISTORY + 7)
        window = chat_module.entries_of(rows)
        self.assertEqual(len(window), chat_module.HISTORY)          # the retained window is capped...
        self.assertGreater(chat_module.transcript_size(rows), len(window))
        self.assertEqual(chat_module.transcript_size(rows[:chat_module.HISTORY]), chat_module.HISTORY)

    def test_the_count_is_unclipped_by_the_entry_text_limit(self):
        rows = [{"role": "owner", "text": "д" * (chat_module.ENTRY_TEXT + 100)} for _ in range(3)]
        self.assertEqual(chat_module.transcript_size(rows), 3)
        window = chat_module.entries_of(rows)
        self.assertEqual(len(window[0].text), chat_module.ENTRY_TEXT + 1)   # "…" plus the clipped tail
        self.assertLess(len(window[0].text), len(rows[0]["text"]))

    def test_a_repeated_entry_and_a_reset_entry_both_count(self):
        full = [{"role": "owner", "text": "повтор"}] * chat_module.HISTORY
        self.assertEqual(chat_module.transcript_size(full + [{"role": "owner", "text": "повтор"}]),
                         chat_module.HISTORY + 1)
        self.assertEqual(chat_module.transcript_size(full + [{"role": "reset", "text": "Новый диалог"}]),
                         chat_module.HISTORY + 1)

    def test_a_row_the_pane_cannot_show_is_not_an_entry(self):
        rows = [{"role": "owner", "text": "a"}, {"role": "unknown", "text": "b"}, "не строка", {"text": "c"}]
        self.assertEqual(chat_module.transcript_size(rows), 1)


def entry_text(shown):
    """The text of one rendered entry (`app.Shown`): its blocks, one per line."""
    return "\n".join(text for _kind, text in shown.blocks)


class _RewriteScreen:
    """A stand-in `MainScreen` for one `sync_chat_history` call: no scroll, no tracked entries, so the
    reconciliation keys on the display texts and takes the positional rewrite. That is the path a role swap must
    survive (the acceptance finding of the repair: `remove_class("msg architect")` is not a class *name* and the
    reconciliation raised `textual.dom.BadIdentifier` instead of updating the widget)."""

    def __init__(self, entries):
        self.app = SimpleNamespace(chat=SimpleNamespace(state=chat_module.ChatState(entries=tuple(entries))))
        self.chat_entry_widgets = []
        self.chat_entry_texts = []

    def chat_entry_lines(self):
        return app_module.MainScreen.chat_entry_lines(self)

    def sync_chat_history(self):
        return app_module.MainScreen.sync_chat_history(self)

    def seed_widgets(self):
        """The widgets the previous render left: real `ChatMessage`s for the current window."""
        self.chat_entry_texts = [text for _role, text in self.chat_entry_lines()]
        self.chat_entry_widgets = [app_module.ChatMessage(text, role)
                                   for role, text in self.chat_entry_lines()]

    def query_one(self, selector, *args):
        return None  # no mount happens on this path: the windows have the same length


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class RoleRewriteTests(unittest.TestCase):
    """The role class on a rewritten window (the repair's code finding 3): a reconciliation that updates the
    widgets by position may meet a retained entry whose role changed — `remove_class`/`add_class` take single class
    names, so the role is swapped as `msg` plus the role itself, never as one space-joined name."""

    def test_a_role_change_is_swapped_by_name(self):
        """The acceptance reproduction at unit level: 38 architect replies, an owner question and an architect reply
        carrying a draft; the window is rewritten in place (no slide fits it, so the widgets are updated by position),
        which moves roles under several positions. The reconciliation must update the widgets (no `BadIdentifier`)
        with `msg` and the new role both in place. (Before 0.6.3 V2 the reply numbering made a one-entry slide look
        like a rewrite; the entries' display text no longer carries it, so the rewrite is built explicitly.)"""
        draft = chat_module.Draft("goal", "proposed goal", "", chat_module.NO_PLAN, True)
        old = [chat_module.ChatEntry("architect", "архитектор %d" % index) for index in range(38)]
        old += [chat_module.ChatEntry("owner", "вопрос"),
                chat_module.ChatEntry("architect", "ответ", drafts=(draft,))]
        new = [chat_module.ChatEntry("owner", "ещё вопрос")] + old[:-1]
        screen = _RewriteScreen(old)
        screen.seed_widgets()
        before = [widget.role for widget in screen.chat_entry_widgets]
        screen.app.chat.state = chat_module.ChatState(entries=tuple(new))
        screen.sync_chat_history()  # raises BadIdentifier before the fix
        for widget in screen.chat_entry_widgets:
            self.assertIn("msg", widget.classes)
            self.assertIn(widget.role, widget.classes)
        after = [widget.role for widget in screen.chat_entry_widgets]
        self.assertEqual(after, [role for role, _text in screen.chat_entry_lines()])
        self.assertNotEqual(before, after)  # the role really moved under a position here
        self.assertEqual(screen.chat_entry_texts, [text for _role, text in screen.chat_entry_lines()])


class ChatScroll(ChatShell):
    """The conversation's own scroll through the real shell: the helpers its paging and R-4 checks share. No tests
    of their own — `ChatScrollShellTests` holds those, and the repair regressions below reuse the same helpers."""

    def main(self):
        """The main screen, whatever modal (if any) is on top."""
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def scroll(self):
        return self.main().query_one("#chat")

    def offset(self):
        """Where the conversation is scrolled to: the `#chat` widget's own row offset, never a computed count."""
        return self.scroll().scroll_offset.y

    def at_bottom(self):
        """The view at the conversation's end (a view with nothing to scroll is at its end too)."""
        scroll = self.scroll()
        return scroll.scroll_offset.y == scroll.max_scroll_y

    def seed_history(self, count, text="строка"):
        store = self.fixture.store()
        for index in range(count):
            store.append("architect" if index % 2 else "owner", text="%s %d" % (text, index))
        return store

    async def start(self, pilot, count, timeout=10.0):
        """Load a chat whose store already holds `count` entries and wait for the widget list and the initial jump
        to the bottom: the conversation's own entries (the one widget per entry), never a row count."""
        await self.loaded(pilot)
        await self.chat_ready(pilot)
        await self.until(pilot, lambda: len(self.main().chat_entry_widgets) >= count, timeout)
        await self.until(pilot, self.at_bottom, timeout)
        await pilot.pause()

    async def focus_panel(self, pilot):
        """Give `#plan-pane` the focus the R-2 scroll keys require (this module's shells run wide, where both
        panes are shown)."""
        for _ in range(3):
            if app_module.draft_keys_ready(self.app):
                return
            await pilot.press("tab")
        self.assertTrue(app_module.draft_keys_ready(self.app))

    def arm_snapshots(self):
        """Wrap the app's own snapshot handler (`got_snapshot`, the one `request_refresh` hands the controller) and
        the request itself, so the poll check waits for the slice the UI has *applied* instead of an elapsed timer."""
        if getattr(self, "_snapshots_armed", False):
            return
        app = self.app
        original, ask = app.got_snapshot, app.request_refresh
        self.snapshots, self.polls = 0, 0

        def request_refresh():
            self.polls += 1
            ask()

        def got_snapshot(snapshot, error):
            original(snapshot, error)
            self.snapshots += 1

        app.request_refresh, app.got_snapshot = request_refresh, got_snapshot
        self._snapshots_armed = True

    async def poll(self, pilot, timeout=10.0):
        """A refresh asks for a fresh plan slice; wait until the request was issued and the UI applied the snapshot it
        delivered, then for a settled render — never a timer."""
        self.arm_snapshots()
        applied, asked = self.snapshots, self.polls
        self.app.request_refresh()
        await self.until(pilot, lambda: self.polls > asked and self.snapshots > applied, timeout)
        await pilot.pause()
        await pilot.pause()


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatScrollShellTests(ChatScroll):
    """The conversation's own scroll through the real shell: its paging, its guards and R-4's reset rules."""

    # A-3 ----------------------------------------------------------------------

    async def test_a3_the_pane_pages_through_the_entries_and_a_send_returns_to_the_bottom(self):
        """A3 at 120x24: the view starts at the conversation's end (the newest entry drawn, the oldest not);
        PageUp shows older entries and PageDown returns to the end; an accepted owner send returns the view to the
        end while a refused one leaves it where it was (R-4). The keys are the pane's own (R-2): they work with
        `#plan-pane` focused, and a blank send is refused before anything is appended.

        The turn is held open on an explicit gate, so the send's own jump is what the check reads: the reply's
        entry lands only after the check, and the send's append is the only entry that returned the view."""
        self.fixture = StreamFixture(self.root, self.project)
        final = str(self.root / "stream-final")
        self.fixture.script([{"lines": [], "gates": [{"file": final, "lines": REPLY}]}])
        self.seed_history(40)
        async with self.shell(size=(120, 24)) as pilot:
            await self.start(pilot, 40)
            await self.focus_panel(pilot)
            self.assertTrue(self.at_bottom())
            shown = chat_band(self.app)
            self.assertIn("строка 39", shown)           # today's view: the newest entry
            self.assertNotIn("строка 0", shown)                 # and not the oldest
            await pilot.press("pageup")                            # one page up: older entries, no longer the end
            await pilot.pause()
            above = self.offset()
            self.assertGreater(above, 0)
            self.assertLess(above, self.scroll().max_scroll_y)
            self.assertNotIn("строка 39", chat_band(self.app))
            for _ in range(40):
                await pilot.press("pageup")                        # the top is the limit, never past it
            await pilot.pause()
            self.assertEqual(self.offset(), 0)
            self.assertIn("строка 0", chat_band(self.app))      # the oldest retained entry is reachable
            await pilot.press("pageup")                            # at the top: a no-op
            await pilot.pause()
            self.assertEqual(self.offset(), 0)
            for _ in range(40):
                await pilot.press("pagedown")
            await pilot.pause()
            self.assertTrue(self.at_bottom())
            await pilot.press("pagedown")                          # at the end: a no-op
            await pilot.pause()
            self.assertTrue(self.at_bottom())
            self.assertIn("строка 39", chat_band(self.app))
            await pilot.press("pageup")
            await pilot.pause()
            above = self.offset()
            self.assertGreater(above, 0)
            before = list(self.app.chat.state.entries)
            await self.say(pilot, "   ")                           # refused: nothing sent, nothing appended
            await pilot.pause()
            self.assertEqual(list(self.app.chat.state.entries), before)
            self.assertEqual(self.offset(), above)                 # the scrolled view is untouched
            await self.say(pilot, "новый вопрос")                  # accepted: the send returns to the end
            await self.until(pilot, lambda: any("новый вопрос" in text
                                                for text in map(entry_text, self.main().chat_entry_texts)), 10.0)
            await self.until(pilot, self.at_bottom, 10.0)
            self.assertIn("новый вопрос", chat_band(self.app))
            Path(final).touch()                                    # let the held turn finish before the shell goes
            await self.chat_done(pilot)

    # R-4 ----------------------------------------------------------------------

    async def test_a4_a_live_update_and_a_poll_while_scrolled_keep_the_position(self):
        """R-4: a live/stream update and a poll never reload the transcript, so a scrolled view keeps its place
        (including across a *second* stream update delivered while scrolled); the reply's own entry, when the turn
        completes, returns the view to the end. The fixture holds the turn open on two explicit gates, so no timer
        decides the test, and the live line is the `#status` row below the scroll, visible at any position."""
        self.fixture = StreamFixture(self.root, self.project)
        second = OPENING + [{"type": "item.completed",
                             "item": {"id": "item_2", "type": "agent_message", "text": "Второе обновление"}}]
        first_gate = str(self.root / "stream-second")
        last_gate = str(self.root / "stream-final")
        self.fixture.script([{"lines": PARTIAL,
                              "gates": [{"file": first_gate, "lines": second},
                                        {"file": last_gate, "lines": REPLY}]}])
        self.seed_history(30)
        async with self.shell(size=(120, 24)) as pilot:
            await self.start(pilot, 30)
            await self.say(pilot, "вопрос")                        # accepted: the view returns to the end
            await self.until(pilot, lambda: self.app.chat.state.live == "Начало ответа", 10.0)
            await self.until(pilot, lambda: len(self.main().chat_entry_widgets) >= 31, 10.0)
            await self.until(pilot, self.at_bottom, 10.0)
            await self.focus_panel(pilot)
            await pilot.press("pageup")
            await pilot.pause()
            above = self.offset()
            self.assertGreater(above, 0)
            self.assertFalse(self.at_bottom())
            self.assertIn("Начало ответа", screen_text(self.app))   # the live row, below the scroll
            Path(first_gate).touch()                                # a second stream update while scrolled
            await self.until(pilot, lambda: self.app.chat.state.live == "Второе обновление", 10.0)
            await pilot.pause()
            self.assertEqual(self.offset(), above)                  # the live change kept the position
            await self.poll(pilot)                                  # a poll while scrolled: its slice is applied
            self.assertEqual(self.offset(), above)
            Path(last_gate).touch()                                 # release completion: the reply's entry lands
            await self.chat_done(pilot)
            await self.until(pilot, lambda: len(self.main().chat_entry_widgets) >= 32, 10.0)
            await self.until(pilot, self.at_bottom, 10.0)           # the new transcript entry returns to the end

    async def test_a4_a_capped_append_returns_the_view_to_the_bottom(self):
        """R-4: a reload that grew the store's transcript returns the view to the end even when the retained window
        cannot show the append. Forty identical entries plus one more leave the window — and so the widget list —
        exactly as it was, so only `ChatState.transcript` carries the append; the view is scrolled up first, and
        the reload is the real prepare path the app's own reload uses."""
        store = self.fixture.store()
        for _ in range(chat_module.HISTORY):
            store.append("owner", text="повтор")
        async with self.shell(size=(120, 24), store=store) as pilot:
            await self.start(pilot, chat_module.HISTORY)
            await self.focus_panel(pilot)
            await pilot.press("pageup")
            await pilot.pause()
            self.assertGreater(self.offset(), 0)
            store.append("owner", text="повтор")                    # the 41st entry: the window still holds 40
            self.app.chat.start()
            await self.until(pilot, self.at_bottom, 10.0)
            self.assertEqual(len(self.main().chat_entry_widgets), chat_module.HISTORY)  # no widget was added

    async def test_a4_a_transcript_entry_read_under_a_modal_jumps_to_the_bottom_when_it_closes(self):
        """R-4 (code finding 2): a reload that lands while a modal covers the conversation must still owe the jump
        to the bottom — the flag lives on the owning `MainScreen`, not on whatever screen is on top — and the jump
        happens once the modal is gone. 40 entries (so the capped window cannot grow and only the store's own count
        carries the append), the owner scrolled to the top, a `TextScreen` on top; one more stored entry reloads the
        chat while the modal is up; dismissing it leaves the view at the end."""
        store = self.seed_history(chat_module.HISTORY)
        async with self.shell(size=(120, 24), store=store) as pilot:
            await self.start(pilot, chat_module.HISTORY)
            await self.focus_panel(pilot)
            await pilot.press("pageup")
            await pilot.pause()
            self.assertGreater(self.offset(), 0)
            modal = app_module.TextScreen("Заголовок", ["строка"])
            self.app.push_screen(modal)
            await self.until(pilot, lambda: self.app.screen is modal, 10.0)
            await pilot.pause()
            store.append("owner", text="строка после модалки")   # the 41st entry: the capped window is unchanged
            self.app.chat.start()
            await self.until(pilot, lambda: self.app.chat.state.transcript > chat_module.HISTORY, 10.0)
            await pilot.pause()
            await pilot.press("escape")
            await self.until(pilot, lambda: self.app.screen is self.main(), 10.0)
            await self.until(pilot, self.at_bottom, 10.0)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class InlineCardRefreshTests(ChatScroll):
    """The inline cards keep the conversation around them where it is (the repair's code finding 1): a card that
    replaces its own key is a *replacement*, not a new entry, so it must not pull the viewport back to itself.

    Interpretation: the readiness card's own `HH:MM` comes from `card_clock()` (`ready_source`), so a mutable
    clock patched over `card_kinds.card_clock` is what "the minute crossed" means here; the card is the real
    `ready` source's, mounted through the screen's own `render_card_sources`, and the second render changes nothing
    but the clock — an otherwise unchanged spec that is still a *different* spec (`shown != spec`), which is exactly
    the replacement the finding names."""

    async def test_a_live_refresh_of_an_existing_card_keeps_the_scrolled_position(self):
        """The reproduction: 40 entries, the `ready:origin` card shown while the owner is at the end, the owner
        scrolled up; the clock crosses the minute and the same card is re-read. The card is replaced in place
        (`card_clock` is the only thing that changed) and the offset is exactly what it was (R-4: a live update while
        scrolled keeps the position). Without the fix the replacement's `reveal_card` sends the view back down."""
        store = self.seed_history(40)
        failing = checks_of([check("origin", False, line="Нет GitHub origin",
                                   detail="git remote add origin https://github.com/OWNER/REPO.git", key="i")])
        clock = ["21:00"]
        with patch.object(card_kinds, "card_clock", lambda: clock[0]):
            async with self.shell(size=(120, 24), store=store) as pilot:
                await self.start(pilot, 40)
                main = self.main()
                self.app.checks, self.app.goal_block = failing, failing  # a start blocked by the failing readiness
                main.render_state()  # a live render: its own `render_card_sources` shows the card
                await pilot.pause(0.3)
                await pilot.pause(0.3)
                card = main.card_widgets["ready:origin"]
                self.assertEqual(card.spec.at, "21:00")
                self.scroll().scroll_to(y=0, animate=False, immediate=True)  # the owner scrolls the conversation up
                await pilot.pause()
                self.assertEqual(self.offset(), 0)
                self.assertGreater(self.scroll().max_scroll_y, 0)  # the card really is below the view now
                clock[0] = "21:01"
                main.render_state()  # the same card, a minute later: an unchanged spec but for the clock
                await pilot.pause(0.3)
                await pilot.pause(0.3)
                replaced = main.card_widgets["ready:origin"]
                self.assertIsNot(replaced, card)                 # it really was replaced...
                self.assertEqual(replaced.spec.at, "21:01")
                self.assertEqual(self.offset(), 0)               # ...and the viewport did not move
                self.assertFalse(self.at_bottom())


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class OptimisticTailTests(ChatScroll):
    """An optimistic owner line that never persisted (the repair's code finding 2): a send the architect refused
    before it reserved the turn leaves the stored transcript untouched, so the reload takes the line away again —
    and the entries around it, and the inline cards beside them, must keep their place.

    Interpretation: the refusal is driven deterministically by making `Architect.begin` answer its own `Blocked`
    (the same class a busy architect raises), which is the reviewer's "refused before persistence" — the line is
    shown, the store never took it, and `chat._sync` reloads the unchanged transcript. A `cancel` racing the launch
    is the other reachable path and is not needed to show the reorder."""

    async def test_an_optimistic_line_that_vanishes_leaves_the_receipt_and_entries_in_place(self):
        """Two entries, the draft card shown and closed to a receipt at the conversation's end; the owner sends a
        question, its optimistic line mounts below the receipt, and the architect's refusal makes the reload drop it.
        The surviving entries keep their widgets and their slots, so the receipt stays the newest child — the
        history is not rewritten around it."""
        store = self.seed_history(2)
        async with self.shell(size=(120, 40), store=store) as pilot:
            await self.start(pilot, 2)
            main = self.main()
            main.show_card(cards.draft_card("draft:receipt", at="21:05"))
            await pilot.pause(0.3)
            main.close_card("draft:receipt", "✓ отправлен планировщику 21:05")
            await pilot.pause(0.3)
            receipt = main.card_widgets["draft:receipt"]
            scroll = main.query_one("#chat")
            surviving = list(main.chat_entry_widgets)
            self.assertEqual(list(scroll.children)[-1], receipt)  # the receipt is the newest child
            with patch.object(Architect, "begin", side_effect=Blocked("занято", family="architect.busy")):
                await self.say(pilot, "вопрос после квитанции")
                await self.chat_done(pilot)
            await self.until(pilot, lambda: len(main.chat_entry_widgets) == 2, 10.0)
            await pilot.pause(0.3)
            self.assertEqual(main.chat_entry_widgets, surviving)    # the two entries are the same widgets
            self.assertIs(main.card_widgets["draft:receipt"], receipt)
            self.assertEqual(list(scroll.children)[-1], receipt)    # the receipt did not move below them


if __name__ == "__main__":
    unittest.main()
