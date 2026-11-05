"""v3e: the blocking draft card is gone — a new goal draft is saved in Drafts with one line in the chat, and a bare
`/plan` sends the newest sendable draft. The shared card contract (`show_card`/`close_card`/`drop_card`, one card per
key) and the helpers other card modules import (`_Screen`, `_main_method`, `DraftShell`) live here since i3a.

Criteria -> tests: A1 (no card, the line once, also after a reopen) `DraftNoteTests`; A2 (the newest draft is sent with
its identity, a stale one is refused on the status line and starts nothing) `PlanCommandDispatchTests`; A3 (a sent or
stale draft never holds the `draft` state, so `/approve` is not in its way) `DraftNoteTests` and `StaleDraftTests`.
At most two whole-app walks drive the notes (`DraftNoteTests`, `StaleDraftTests`); the rest is unit level with
stand-in screens and no pilot.

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- «Once per key, also after a reopen» is the draft's stable key (`card_kinds.draft_key`: the reply and its place in the
  store's transcript) noted per screen: a refresh or a poll notes nothing twice; a reopen is a new screen, and a draft
  that is still sendable there (no plan has moved past it) gets its one line again, while a draft the plan moved past
  or that was sent is history and gets none.
- «The newest draft that was not sent and whose identity is still fresh» is the screen's `sendable_drafts`, newest
  first: a draft joins it when it is noted and leaves it when a `/plan` sent it (every older one goes with it, the plan
  they named moved) or the plan moved past it (`retire_stale_drafts`). The identity is checked once more right before
  sending (`chat.stale_reason`), and the controller repeats the check on the worker.
- «When sending is possible now» is the palette's own verdict on `/plan` in the screen's state (`plan_possible`): the
  second sentence is added only in the states where `/plan` acts (idle, draft, error).
- `start_goal(card_key=...)` keeps its parameter name (a test outside this write-set passes it): it is now the key of
  the draft sent. `draft_card_ref` keeps its name for the same reason (`test_tui_low_batch` stands it in).
- The line is a plain dim `Static` mounted in `#chat` right behind the reply that carries the draft; it is not a card
  (no `Card` widget, no receipt) and it is not repeated by a reload.
"""

import asyncio
import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# imported first for its side effect: the offline wheelhouse (ZPLAN_TEST_WHEELHOUSE) joins `sys.path` before the
# guarded imports below, so this module sees Textual and Rich there on a host that installs neither.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_text

from terminal_planner import architect as adapter
from terminal_planner.authority import Authority as RealAuthority
from terminal_planner.tui import strings

MISSING_REASON = "Rich и Textual недоступны: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"
# The app and the card widget need Rich (through Textual), so they alone are imported under the same guard the
# other TUI modules use: the module still loads (the classes declared below and skipped) where neither is
# importable, which `tests.test_toolchain` scans for. The chat contract, the controller and the shell are
# Textual-free, so importing them is unconditional — a broken wheelhouse then leaves only `ui`/`cards` unset, and
# every declared test class (the declared test count must not depend on the dependencies) still exists.
try:
    from rich.cells import cell_len  # noqa: F401
    from textual.widgets import Button, Static
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import card_kinds
    from terminal_planner.tui import cards
    from terminal_planner.tui import palette
    from terminal_planner.tui.controller import Snapshot
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    cell_len = ui = card_kinds = cards = palette = Snapshot = None

from terminal_planner.tui import chat as chat_module
from terminal_planner.tui.controller import Controller, Outcome, Row, checks_of
from test_tui_chat import ChatShell
from test_tui import Readiness, check
from test_tui_milestones import DIRTY

HAVE = HAVE_TEXTUAL and ui is not None and cards is not None

GOAL_DRAFT = "Экспорт отчётов в CSV: модель строки, экспорт, документация"
NO_PLAN = adapter.NO_PLAN  # "no plan": the plan identity of a snapshot that names no revision


def receipt_pattern():
    """A closed plan card's receipt as a pattern: `card.plan_done` with a `HH:MM` time («✓ утверждён HH:MM»), read
    from the catalog so the check holds whatever language the runner's UI uses. (Other card modules import it.)"""
    filled = strings.text("card.plan_done", time="00:00")
    return re.escape(filled).replace("00:00", r"\d\d:\d\d")


def plan_spec(key, at="21:03"):
    """A card spec for the contract tests (any kind would do: the slot does not read it)."""
    return cards.plan_card(key, at=at, stages="2 stages", tasks="3 tasks")


@unittest.skipUnless(HAVE, MISSING_REASON)
class CardContractTests(unittest.TestCase):
    """A5 and the card contract at unit level (A6): the one dispatcher both paths share, and show/close/drop on a
    stand-in screen whose only real part is the bookkeeping under test (no pilot, no project, no engine)."""

    def test_a5_open_and_diff_reach_the_canvas_tabs(self):
        """A5: `/open README.md` reaches `open_file_tab` with its argument and `/diff` reaches `open_diff_tab` —
        the old `/diff` -> `action_open_milestone` mapping is gone (the stand-in would count it)."""
        screen = _Tabs()
        self.assertTrue(ui.MainScreen.run_command(screen, "/open", "README.md", None))
        self.assertEqual(screen.opened, ["README.md"])
        self.assertTrue(ui.MainScreen.run_command(screen, "/diff", "", None))
        self.assertEqual((screen.diffs, screen.milestones), (1, 0))

    def test_the_conversation_mounts_replaces_in_place_keeps_open_and_drops_one_card_per_key(self):
        """The card contract (acceptance finding 2, i3-chat-inline): `show_card` mounts the card inline in the
        conversation (`#chat`) and a second `show_card` of the same key *replaces* it in its own place (the new
        widget mounted right after the old, the old one taken off), but a card of another key is mounted *beside* an
        existing card — the old slot took every other card off, an open decision included, which the shared contract
        does not allow. i3-chat-inline drops the newer-card expiry: a closed card's receipt *stays* in the history
        where the card stood, through a newer card and through a new chat turn alike. `drop_card` takes its own card
        off the conversation — its key remembered as seen, so it is never shown again — and leaves the rest alone."""
        screen = _Screen()
        first = plan_spec("k1", "21:03")
        screen.show_card(first)
        self.assertEqual(screen.box.mounted, [screen.card_widgets["k1"]])
        self.assertEqual(screen.card_specs["k1"], first)
        second = plan_spec("k1", "21:04")  # the same key, a new spec
        screen.show_card(second)
        self.assertEqual(screen.card_specs["k1"], second)
        self.assertEqual(screen.box.mounted[-1].spec, second)
        self.assertEqual(screen.box.after, [(screen.box.mounted[-1], screen.box.mounted[0])])  # replaced in place
        self.assertEqual(screen.box.removed, [screen.box.mounted[0]])  # the replaced card left the conversation
        other = plan_spec("k2", "21:05")
        screen.show_card(other)
        self.assertEqual(sorted(screen.card_specs), ["k1", "k2"])  # the open k1 was not taken off
        # the acceptance officer's own reproduction: a draft card, then an error card — both stay open, the draft
        # is not removed by the later card
        screen.show_card(cards.error_card("e1", at="21:05", task="M1", text="ошибка", buttons=()))
        self.assertEqual(sorted(screen.card_specs), ["e1", "k1", "k2"])
        self.assertIn(screen.card_widgets["k1"], screen.box.mounted)  # the draft card is still on the slot
        self.assertNotIn(screen.card_widgets["k1"], screen.box.removed)
        screen.drop_card("e1")
        self.assertEqual(sorted(screen.card_specs), ["k1", "k2"])
        kept = screen.card_widgets["k2"]
        screen.close_card("k1", "sent")  # k1 becomes a closed receipt, still in the conversation
        self.assertEqual(screen.card_specs["k1"].done, "sent")
        receipt = screen.card_widgets["k1"]
        third = plan_spec("k3", "21:06")
        screen.show_card(third)
        # i3-chat-inline: the closed receipt no longer expires — k1's receipt, k2 and k3 all stay
        self.assertEqual(sorted(screen.card_specs), ["k1", "k2", "k3"])
        self.assertIs(screen.card_widgets["k1"], receipt)
        self.assertNotIn(receipt, screen.box.removed)
        self.assertNotIn(kept, screen.box.removed)  # the open card's widget was never taken off
        screen.drop_card("k2")
        self.assertEqual(sorted(screen.card_specs), ["k1", "k3"])  # only the dropped card left the conversation
        self.assertIn("k2", screen.cards_seen)  # a dropped key is never shown again
        self.assertNotIn(screen.card_widgets["k3"], screen.box.removed)

    def test_close_card_leaves_the_receipt_and_no_buttons(self):
        """`close_card` replaces the card with `cards.closed(spec, done_text)`: the closed card composes only the
        receipt line (no buttons). i3-chat-inline: the receipt stays in the history (no `drop_closed_cards` any more)
        — it is the card's own place kept."""
        screen = _Screen()
        screen.show_card(plan_spec("k1"))
        self.assertEqual(len(list(screen.card_widgets["k1"].compose())), 3)  # text, buttons, hint
        receipt = strings.text("card.plan_done", time="21:05")
        screen.close_card("k1", receipt)
        closed = screen.card_widgets["k1"]
        self.assertEqual(closed.spec.done, receipt)
        self.assertEqual([type(widget).__name__ for widget in closed.compose()], ["Static"])  # no buttons
        self.assertIn("k1", screen.card_widgets)  # the receipt stays in the conversation
        self.assertNotIn(closed, screen.box.removed)

    def test_the_draft_key_is_stable_and_tells_two_drafts_of_one_plan_apart(self):
        """The key rule: two drafts of one reply under one plan share the plan identity, so the key is built from the
        reply and the draft's own text — two drafts get two keys — and the same stored draft keeps its key (that is
        what makes a draft noted once per key)."""
        entry = chat_module.ChatEntry("architect", "Вот два черновика.",
                                      drafts=(chat_module.Draft("goal", "Первый", "", NO_PLAN, True),
                                              chat_module.Draft("goal", "Второй", "", NO_PLAN, True)))
        first, second = entry.drafts
        key_a = card_kinds.draft_key(entry, first)
        key_b = card_kinds.draft_key(entry, second)
        self.assertNotEqual(key_a, key_b)
        self.assertNotEqual(key_a, repr(first.identity))  # never the identity alone
        self.assertEqual(key_a, card_kinds.draft_key(entry, first))  # stable across calls (a refresh, a restart)
        # the newest actionable draft of the reply is the one noted (a store that does not carry it: content alone)
        self.assertEqual(card_kinds.newest_draft_of(_Chat([], (entry,))), (key_b, second))

    def test_regression_two_identical_replies_are_two_drafts_and_a_slide_keeps_the_key(self):
        """Acceptance finding 1: the key hashed the reply's *content* alone, so a reply repeated identically under one
        plan identity (ask the architect to repeat the identical reply and draft) got the same key, and the second,
        still actionable draft was suppressed as already noted — nothing was saved and `/plan` found nothing to send.

        The key now carries the reply's own *occurrence* (`reply_occurrence`): its place counted from the start of
        the store's append-only transcript. Reproduction here: two identical stored replies key apart (the later one
        is its own card); the same stored reply keys the same across a refresh, a restart and a slide of the retained
        window (owner rows appended behind it move the window but not the reply's place); and `newest_draft_of` reads
        the reply's own entry and draft from `ChatState.entries` (the newest actionable draft wins).

        Interpretation: the provenance is a count from the start of the file, never a distance from the end of the
        retained window — the window slides (HISTORY) and a distance would move with it, re-keying a noted draft
        and noting it again. The *last* stored row matching the entry is the reply's own (the newest card is the
        newest actionable draft's reply). Without a readable store, or for a reply it does not carry, the content
        alone decides the key, exactly as before."""
        def reply(text=GOAL_DRAFT):
            return {"role": "architect", "status": "completed", "text": "Вот черновик.",
                    "drafts": [{"kind": "goal", "text": text, "milestone": None, "identity": NO_PLAN}]}
        asked = {"role": "owner", "text": "вопрос"}
        rows = [asked, reply()]
        key, draft = card_kinds.newest_draft_of(draft_chat(rows))
        self.assertEqual((draft.text, draft.identity), (GOAL_DRAFT, NO_PLAN))
        # the same stored reply keeps its key across a refresh and a restart of the shell
        self.assertEqual(card_kinds.newest_draft_of(draft_chat(rows))[0], key)
        # the architect repeats the identical reply and draft under the same plan identity: a new occurrence, a draft
        # of its own — the first reply's key is not reused
        twice = rows + [{"role": "owner", "text": "повтори"}, reply()]
        again, draft2 = card_kinds.newest_draft_of(draft_chat(twice))
        self.assertEqual((draft2.text, draft2.identity), (draft.text, draft.identity))
        self.assertNotEqual(again, key)
        # a slide of the retained window works on the same store: the original reply keeps its own key
        slid = rows + [{"role": "owner", "text": "дальше %d" % index} for index in range(5)]
        self.assertEqual(card_kinds.newest_draft_of(draft_chat(slid))[0], key)
        # a store that cannot be read (or a reply it does not carry) falls back to the content alone
        self.assertEqual(card_kinds.newest_draft_of(_Chat([], chat_module.entries_of(rows)))[0],
                         card_kinds.draft_key(chat_module.entries_of(rows)[1], draft))

    def test_regression_refresh_notes_a_repeated_identical_reply_once_each(self):
        """Acceptance finding 1 / code finding 1: `refresh_drafts` must decide by the reply-specific *key*, never by
        the draft value — the requirement is to note a draft whenever `newest_goal_draft` returns one whose key was
        never noted. Reproduction with the real method: note a reply, append an identical draft in a new reply,
        refresh — a note for the new key must appear (not zero); refreshing again notes nothing more; a draft sent
        by `/plan` (`draft_sent`) is not sendable any more and is never noted again.

        Interpretation: the same *key*, never the draft value, is what makes a draft "already noted" — two drafts
        under one plan share the value."""
        def reply():
            return {"role": "architect", "status": "completed", "text": "Вот черновик.",
                    "drafts": [{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": NO_PLAN}]}
        rows = [{"role": "owner", "text": "вопрос"}, reply()]
        first_key, _ = card_kinds.newest_draft_of(draft_chat(rows))
        screen = _DraftScreen(draft_chat(rows))
        screen.refresh_drafts()
        self.assertEqual([message.key for message in screen.posted], [first_key])  # the first reply's note
        self.assertEqual(list(screen.sendable_drafts), [first_key])
        screen.refresh_drafts()
        self.assertEqual([message.key for message in screen.posted], [first_key])  # the same key: nothing more
        # the architect repeats the identical reply and draft: a new occurrence, a key never noted — its own note
        screen.app.chat = draft_chat(rows + [{"role": "owner", "text": "повтори"}, reply()])
        second_key, second_draft = card_kinds.newest_draft_of(screen.app.chat)
        self.assertNotEqual(second_key, first_key)
        self.assertEqual(second_draft.text, GOAL_DRAFT)
        screen.refresh_drafts()
        self.assertEqual([message.key for message in screen.posted], [first_key, second_key])
        self.assertEqual(screen.newest_sendable_draft(), (second_key, second_draft))  # the newest is what /plan sends
        # a `/plan` sent the newest: none is sendable (the older one named the plan that moved), none comes back
        screen.draft_sent()
        screen.refresh_drafts()
        self.assertEqual((screen.sendable_drafts, [message.key for message in screen.posted]),
                         ({}, [first_key, second_key]))

    def test_regression_a_sendable_draft_makes_the_typed_plan_available_under_a_proposed_plan(self):
        """Acceptance finding 3: with a sendable draft the screen is in `draft` even while a plan is *proposed* (a
        draft made against that plan is current), so the palette submits the typed `/plan`. Pre-fix `slash_state`
        returned `plan_ready` for a `proposed` revision before it ever looked at `draft`, so
        `palette.submit("/plan", ...)` was a `Refused`.

        Interpretation: a sendable goal draft comes before `plan_ready` in the precedence (i3a); with none the same
        proposed screen keeps its `plan_ready`, which is what lets `/approve` act (A3)."""
        proposed = Snapshot("P", "main", True, 1, "proposed", (), ())
        self.assertEqual(ui.slash_state(proposed, draft=True), "draft")
        verdict = palette.submit("/plan", ui.slash_state(proposed, draft=True))
        self.assertIsInstance(verdict, palette.Submitted)
        self.assertEqual(verdict.command_name, "/plan")
        self.assertEqual(ui.slash_state(proposed), "plan_ready")  # unchanged without a sendable draft
        self.assertIsInstance(palette.submit("/plan", ui.slash_state(proposed)), palette.Refused)
        self.assertIsInstance(palette.submit("/approve", ui.slash_state(proposed)), palette.Submitted)  # A3

    def test_regression_a_sendable_draft_reaches_the_typed_plan_under_a_failed_plan(self):
        """Code-review finding 2: with a sendable, non-stale draft and a plan whose status is `run_failed` or
        `proposal_invalid` (or a `kind == "failed"` view), `slash_state(..., draft=True)` returned `error` because
        the failed-planning branch sat ahead of `draft`, and the palette refused the typed `/plan`.

        Interpretation: the sendable draft is what a typed `/plan` redoes, so `draft` is the screen's state under a
        failed plan; with none that fact keeps its own state (`error`). R-B (tests.test_tui_rb_fixes) moved the
        running stage, a question, a merge and an error line ahead of `draft`, so a live stage is `running` with or
        without the draft. The draft's staleness is still checked by `action_plan` and again on the worker, so this
        precedence only decides reachability."""
        from terminal_planner.planning import PlanView

        failed = Snapshot("P", "main", True, 1, "run_failed", (),
                          (),
                          plan=PlanView("failed", 1, "run_failed",
                                        ("", "План r1 · планирование остановилось"), ("retry", "revise")))
        for revision in (failed, Snapshot("P", "main", True, 1, "proposal_invalid", (), ())):
            state = ui.slash_state(revision, draft=True)
            self.assertEqual(state, "draft")
            verdict = palette.submit("/plan", state)
            self.assertIsInstance(verdict, palette.Submitted)
            self.assertEqual(verdict.command_name, "/plan")
            self.assertEqual(ui.slash_state(revision), "error")  # unchanged without a sendable draft
        running = Snapshot("P", "main", True, None, None, (), (),
                           rows=(Row(id="M1", title="M1", state="running", text="идёт"),))
        self.assertEqual(ui.slash_state(running, draft=True), "running")  # R-B: a live stage outranks the draft
        self.assertEqual(ui.slash_state(running), "running")


class _Slot:
    """The conversation stand-in (`#chat`): records the widgets mounted on it (and where — `after` names the card a
    replacement goes next to) and the ones taken off, so the contract's own bookkeeping is what the assertions read
    (no running app)."""

    def __init__(self):
        self.mounted, self.removed = [], []
        self.after = []  # (widget, the card it was mounted right after) for an in-place replacement

    def mount(self, widget, after=None):
        self.mounted.append(widget)
        if after is not None:
            self.after.append((widget, after))

    def remove_children(self, widgets):
        self.removed.extend(widgets)


class _Pad:
    """Only the app side the stand-in screen touches: the status note and the `changed` wake-up."""

    def __init__(self):
        self.chat_note, self.changes = "", 0

    def changed(self):
        self.changes += 1


class _Store:
    """The store side `reply_occurrence` reads: only a `transcript()` of the stored rows."""

    def __init__(self, rows):
        self._rows = rows

    def transcript(self):
        return [dict(row) for row in self._rows]


class _Chat:
    """A chat stand-in carrying a store of stored rows and, when the card key's own rule needs them, the retained
    window `chat.entries_of` builds from the same rows (`chat.state.entries`)."""

    def __init__(self, rows, entries=()):
        self.store = _Store(rows)
        self.state = chat_module.ChatState(entries=tuple(entries))


def draft_chat(rows):
    """A chat stand-in of `rows`: its store holds the rows and its retained window is `chat.entries_of(rows)`, the
    same derivation the shell's own `ChatState.entries` gets from the store."""
    return _Chat(rows, chat_module.entries_of(rows))


def _main_method(name):
    """The real `MainScreen` method `name`, copied onto the stand-in class so the method under test itself runs on
    the double. Without the app module (Textual/Rich missing) a stub stands in its place: the class, and with it
    every declared test, still exists (the count a `tests.test_toolchain` scan reads must not depend on the
    dependencies), and the skipped test never reaches the stub."""
    def missing(self, *args, **kwargs):  # pragma: no cover - reached only where the tests skip anyway
        raise AssertionError(MISSING_REASON)
    return missing if ui is None else getattr(ui.MainScreen, name)


class _Screen:
    """The MainScreen stand-in for the card contract: the real methods run on it (`show_card`, `close_card`,
    `drop_card`, `run_command`'s note path), and only the widgets they touch are doubled — the slot above and the
    app's note pad. No DOM, no project, no pilot."""

    show_card = _main_method("show_card")
    close_card = _main_method("close_card")
    drop_card = _main_method("drop_card")
    unmount_card = _main_method("unmount_card")
    status_note = _main_method("status_note")
    show_chat = _main_method("show_chat")  # a no-op here: the stand-in is wide
    newest_card_for = _main_method("newest_card_for")
    narrow = False

    def __init__(self):
        self.box, self.app = _Slot(), _Pad()
        self.card_widgets, self.card_specs, self.cards_seen = {}, {}, set()

    def query_one(self, selector, *args):
        if selector == "#chat":
            return self.box
        raise AssertionError(selector)

    def scroll_chat_end(self):
        """UI-only: the stand-in has no scroll to move."""

    def call_after_refresh(self, callback):
        """The card's own scroll-to-bottom request is UI work: the stand-in has no running app to schedule it on."""


class _DraftScreen(_Screen):
    """The card contract screen with a chat and a message sink: the real `refresh_drafts` runs on it, so the
    discovery of *which* draft is noted and sendable is exercised (the key compared, never the draft value), not the
    key rule alone. `posted` collects the `DraftSaved` messages the screen would hand to its own pump."""

    refresh_drafts = _main_method("refresh_drafts")
    plan_identity_now = _main_method("plan_identity_now")
    retire_stale_drafts = _main_method("retire_stale_drafts")
    draft_sendable = _main_method("draft_sendable")
    newest_sendable_draft = _main_method("newest_sendable_draft")
    draft_card_ref = _main_method("draft_card_ref")
    draft_sent = _main_method("draft_sent")

    def __init__(self, chat):
        super().__init__()
        self.app.chat = chat
        self.app.snapshot = SimpleNamespace(version=None, plan_state=None)  # loaded, and no plan: a "no plan" draft is current
        self.sendable_drafts, self.drafts_noted = {}, set()
        self.posted = []

    def post_message(self, message):
        self.posted.append(message)


class _Tabs:
    """The screen stand-in of A5: the canvas actions record their calls, and `action_open_milestone` counts what
    the old `/diff` mapping would have reached."""

    def __init__(self):
        self.opened, self.diffs, self.milestones, self.note = [], 0, 0, ""

    def open_file_tab(self, name):
        self.opened.append(name)

    def open_diff_tab(self):
        self.diffs += 1

    def action_open_milestone(self):
        self.milestones += 1

    def status_note(self, line):
        self.note = line


# The whole-app half: the notes (A1, A3) and the plan moving past a draft. ---------------------------------------


@unittest.skipUnless(HAVE, MISSING_REASON)
class DraftShell(ChatShell):
    """The chat shell with one architect reply carrying one actionable goal draft, written into the store before the
    shell opens (the note is made from the retained history, exactly as `[c]` reads it)."""

    def seed_goal_draft(self, text=GOAL_DRAFT, identity=NO_PLAN, status="completed"):
        """One owner question and one architect reply carrying one goal draft in the store."""
        store = self.fixture.store()
        store.append("owner", text="вопрос")
        store.append("architect", text="Вот черновик.", status=status,
                     drafts=[{"kind": "goal", "text": text, "milestone": None, "identity": identity}])
        return store

    def main(self):
        """The main screen, whatever modal (if any) is on top."""
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def notes(self):
        """The draft notes of the conversation: the one dim line a saved draft leaves in `#chat`."""
        return [widget for widget in self.main().query_one("#chat").children if widget.has_class("draft-note")]

    async def settled(self, pilot, timeout=8.0):
        """The chat is ready and the retained history carries the seeded actionable goal draft."""
        await self.loaded(pilot)
        await self.chat_ready(pilot)
        await self.until(pilot, lambda: chat_module.newest_goal_draft(self.app.chat.state.entries) is not None,
                         timeout)

    async def note_shown(self, pilot, timeout=8.0):
        """The draft's note, once it is mounted and the draft is sendable."""
        await self.until(pilot, lambda: self.main().draft_sendable() and self.notes(), timeout)
        await pilot.pause(0.3)
        return self.notes()

    def plan_card(self):
        """The conversation's *plan* card (`plan:<version>`), or None — which the fixture planner mounts once `/plan`
        has started it and it proposed."""
        return next((card for key, card in self.main().card_widgets.items() if key.startswith("plan:")), None)

    async def plan_card_shown(self, pilot, timeout=10.0):
        """The plan card, once the planner has proposed and the card is mounted and laid out."""
        await self.until(pilot, lambda: self.plan_card() is not None, timeout)
        await pilot.pause(0.3)
        return self.plan_card()

    async def send(self, pilot, line):
        """Put `line` in the chat input and press Enter."""
        field = self.query("#input")
        field.focus()
        field.value = line
        await pilot.press("enter")
        await pilot.pause(0.3)

    def counting_start(self, calls):
        """A `start_planning` spy: records `(goal, draft)` and still starts the planner, so a run that should not
        start is caught by the empty call list and a run that must start by the recorded one."""
        real = Controller.start_planning

        def spy(controller, goal, done, draft=None, card=False):
            calls.append((goal, draft))
            return real(controller, goal, done, draft=draft, card=card)
        return spy

    def draft_tab(self):
        """The permanent Drafts canvas tab: its label and the body it holds (v3d; no per-draft view tab opens)."""
        right = self.main().query_one("#right")
        body = right.get_pane(ui.TAB_DRAFTS).query_one(Static).content.plain
        return right.get_tab(ui.TAB_DRAFTS).label.plain, body


@unittest.skipUnless(HAVE, MISSING_REASON)
class DraftNoteTests(DraftShell):
    async def test_a1_a3_a_draft_is_saved_with_one_line_and_a_bare_plan_sends_it(self):
        """A1: a goal draft in the retained history leaves no card — only one dim line right behind its reply, and
        only once: a refresh adds none, and a reopen (a second shell on the same store, nothing sent yet) shows the
        line once again. The Drafts tab holds the draft's time and whole text and comes forward; `/plan` is offered in
        the line because the screen is in `draft`.

        A2/A3 on the reopened shell: a bare `/plan` calls `start_planning` once with the draft's text and its own
        identity, the draft stops being sendable (the state is no longer `draft`), the fixture planner proposes, and
        the typed `/approve` acts — a draft never stands in its way.

        The store is written once, before the first shell opens, and only the second pass starts anything."""
        store = self.seed_goal_draft()
        reply_at = ui.stamp_hm(store.transcript()[-1]["ts"])
        wanted = strings.text("chat.draft_saved") + " " + strings.text("chat.draft_send")
        for opening in ("first", "reopen"):
            with self.subTest(opening=opening):
                calls = []
                with patch.object(Controller, "start_planning", self.counting_start(calls)):
                    async with self.shell(size=(120, 40), store=store) as pilot:
                        await self.settled(pilot)
                        notes = await self.note_shown(pilot)
                        main = self.main()
                        self.assertEqual([note.content.plain for note in notes], [wanted])      # one line...
                        self.assertEqual(len(main.card_widgets), 0)                              # ...and no card
                        self.assertEqual(list(main.query(cards.Card)), [])
                        children = list(main.query_one("#chat").children)
                        reply = main.draft_reply_widget(main.sendable_drafts[next(iter(main.sendable_drafts))])
                        self.assertEqual(children.index(notes[0]), children.index(reply) + 1)  # right behind it
                        self.assertEqual(main.query_one("#right").active, ui.TAB_DRAFTS)         # Drafts came forward
                        self.assertEqual(self.draft_tab()[1], reply_at + "\n" + GOAL_DRAFT)
                        self.assertEqual(ui.screen_slash_state(self.app), "draft")
                        main.render_state()                                                      # a refresh adds none
                        await pilot.pause(0.3)
                        self.assertEqual(len(self.notes()), 1)
                        if opening == "first":
                            continue
                        await self.send(pilot, "/plan")
                        await self.until(pilot, lambda: calls and not main.draft_sendable())
                        self.assertEqual(calls, [(GOAL_DRAFT, NO_PLAN)])
                        plan = await self.plan_card_shown(pilot)
                        self.assertNotEqual(ui.screen_slash_state(self.app), "draft")            # A3
                        await self.send(pilot, "/approve")
                        await self.until(pilot, lambda: self.plan_card() is not None and self.plan_card().spec.done)
                        self.assertRegex(self.plan_card().spec.done, "^%s$" % receipt_pattern())
                        self.assertEqual(len(self.notes()), 1)                                   # the line stayed
                        self.assertEqual(calls, [(GOAL_DRAFT, NO_PLAN)])                         # and nothing re-sent


@unittest.skipUnless(HAVE, MISSING_REASON)
class StaleDraftTests(DraftShell):
    async def test_regression_a_draft_the_plan_moved_past_stops_being_sendable(self):
        """RC4 (0.6.0 smoke defect 4): the plan built from the draft was approved while the draft stayed the screen's
        state, so `/run` was refused while the panel said «Next: /run». A3: on the refresh after the plan appeared
        the draft is no longer sendable, `screen_slash_state` reads the plan's state, not `draft`, the Drafts tab keeps
        the draft, and a bare `/plan` starts nothing (it finds no draft and no unsent revision to send).

        Interpretation: «a snapshot that names a plan» is a snapshot with a revision (`snapshot.version`); the
        retirement runs on the screen's own refresh, so the test only waits for the snapshot and the refresh."""
        calls = []
        with patch.object(Controller, "start_planning", self.counting_start(calls)):
            async with self.shell(size=(120, 40), store=self.seed_goal_draft()) as pilot:
                await self.settled(pilot)
                await self.note_shown(pilot)
                main = self.main()
                self.assertEqual(main.view_tabs, [])                       # v3d: the draft opens no view tab
                self.assertEqual(ui.screen_slash_state(self.app), "draft")

                def propose(session):  # the plan appears while the draft is sendable: the draft is stale against it
                    self.begin(session.authority)
                    self.propose(session.authority)
                    session.authority.approve(1)
                await self.post_and_wait(pilot, propose)
                self.app.request_refresh()
                await self.until(pilot, lambda: self.app.snapshot.version is not None and not main.draft_sendable())
                await pilot.pause(0.3)
                self.assertNotEqual(ui.screen_slash_state(self.app), "draft")
                self.assertEqual(self.draft_tab()[1].count(GOAL_DRAFT), 1)  # the Drafts tab keeps the draft
                self.assertEqual(len(self.notes()), 1)                      # the line stays, once
                main.render_state()                                         # a later refresh notes nothing again
                await pilot.pause(0.3)
                self.assertEqual(len(self.notes()), 1)
                await self.send(pilot, "/plan")
                self.assertEqual(calls, [])                                 # nothing was started

    async def test_regression_a_refused_plan_writes_no_revision_and_the_retry_starts(self):
        """RC6 (0.6.0 smoke defect 3): the draft's own `/plan` met a dirty tree and `start_planning` saved an unsent
        revision before it looked at the gate, so the plan identity moved off «no plan» and the draft was
        «черновик устарел» for good. C1: the refusal names the checks, writes no revision and the draft stays
        sendable; C2: after the owner fixes readiness the same bare `/plan` starts the planner (one sent revision, no
        stale line); C3 (the goal form keeps saving an unsent revision) is pinned by
        `tests/test_tui_chat.py::GoalDraftTests` and not repeated here.

        Interpretation: the refusal is the readiness gate's `unsent` answer, so the plan identity is read through
        the authority file: absent after the refusal, one revision after the retry."""
        readiness = Readiness(check("git"), check("branch", False, DIRTY, key="d"))
        authority_path = RealAuthority(self.state, self.project, fixture_id="test").path
        async with self.shell(self.controller(readiness), size=(120, 40), store=self.seed_goal_draft()) as pilot:
            await self.settled(pilot)
            await self.note_shown(pilot)
            await self.send(pilot, "/plan")
            self.assertIn("отсоединён", screen_text(self.app))        # C1: the checks are named...
            self.assertFalse(authority_path.exists())                    # ...no revision, no run
            self.assertTrue(self.main().draft_sendable())                # ...and the draft is still sendable
            readiness.fix("branch")
            await self.send(pilot, "/plan")                              # C2: the retry
            await self.until(pilot, lambda: authority_path.exists())
            await self.until(pilot, lambda: not self.main().draft_sendable())
            self.assertNotIn(chat_module.OUTDATED, screen_text(self.app))
        revisions = json.loads(authority_path.read_text())["revisions"]
        self.assertEqual(len(revisions), 1)


@unittest.skipUnless(HAVE, MISSING_REASON)
class NarrowCardTests(DraftShell):
    async def test_a5_a_card_opening_in_narrow_mode_brings_the_chat_back(self):
        """A5 at 80x24: while the owner looks at the canvas (`show_canvas` — what the arrows do) a decision card opens
        in the conversation, and «Разговор» is the shown pane again — `show_card`'s own `show_chat` — so the
        decision the card holds is on screen.

        Interpretation: entering narrow mode alone already shows the chat (`layout_for`), so the check steps away to
        the canvas first and lets the card open *while the canvas is shown*; `show_card`'s contract — an open spec
        asks for the chat, a closed receipt does not — is what brings the pane back. (A draft is no card since v3e,
        so the card here is any open spec.)"""
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            main = self.main()
            self.assertTrue(main.narrow)
            main.show_canvas()  # the owner is on the canvas while the work goes on
            await pilot.pause()
            self.assertFalse(main.query_one("#chat-pane").display)
            self.assertFalse(main.chat_shown)
            main.show_card(plan_spec("note:open"))
            await pilot.pause(0.3)
            self.assertTrue(main.chat_shown)                            # A5: the card asked for the chat
            self.assertTrue(main.query_one("#chat-pane").display)
            self.assertFalse(main.query_one("#right-column").display)
            self.assertIs(main.card_widgets["note:open"].parent, main.query_one("#chat"))


def entry_texts(main):
    """The text of each rendered entry (`app.Shown`) of the screen, one string per entry."""
    return ["\n".join(text for _kind, text in shown.blocks) for shown in main.chat_entry_texts]


@unittest.skipUnless(HAVE, MISSING_REASON)
class CappedWindowTests(DraftShell):
    """The capped-window reconciliation (the repair's acceptance finding 2 and code finding 2): when the retained
    history slides, an entry that stayed can change its display text (its time line) while keeping its place. The
    reconciliation must follow the entries, not the text — otherwise it
    falls into the positional rewrite and the appended entry takes a slot *before* a card already inline."""

    async def test_a2_a_capped_slide_appends_the_new_entry_after_an_inline_receipt(self):
        """40 architect replies, the last carrying the goal draft: a card is shown and closed, so its receipt
        stands where the card was. One more reply is appended; the window drops its front entry and renumbers the
        kept replies (the renumbering that used to defeat the shift and rewrite the newest widget in the receipt's
        own place). The new reply must mount *below* the receipt, which keeps its identity and its slot."""
        store = self.fixture.store()
        for index in range(39):
            store.append("architect", text="архитектор ответ %d" % index, status="completed")
        store.append("architect", text="черновик цели", status="completed",
                     drafts=[{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": NO_PLAN}])
        async with self.shell(size=(120, 40), store=store) as pilot:
            await self.settled(pilot)
            await self.note_shown(pilot)
            main = self.main()
            main.show_card(plan_spec("receipt:1"))
            main.close_card("receipt:1", "✓ отправлен планировщику 21:05")
            await pilot.pause()
            receipt = main.card_widgets["receipt:1"]
            scroll = main.query_one("#chat")
            self.assertIn(receipt, list(scroll.children))            # the receipt stands in the conversation
            store.append("architect", text="ответ после квитанции", status="completed")
            self.app.chat.start()  # the window reloads and slides
            await self.until(pilot, lambda: any("после квитанции" in text
                                                for text in entry_texts(main)), 10.0)
            await pilot.pause()
            index = next(i for i, text in enumerate(entry_texts(main))
                         if "после квитанции" in text)
            appended = main.chat_entry_widgets[index]
            children = list(scroll.children)
            self.assertEqual(children[-1], appended)                 # the new reply is the newest entry...
            self.assertLess(children.index(receipt), children.index(appended))  # ...below the existing receipt
            self.assertIs(main.card_widgets["receipt:1"], receipt)  # and the receipt itself did not move


    async def test_a_reload_that_replaces_the_whole_window_mounts_the_new_entries_below_the_receipt(self):
        """A reload that pushes the *whole* capped window out at once (the acceptance finding): 40 architect replies,
        the last carrying the goal draft, a card shown and closed to a receipt; then 40 more distinct replies
        arrive before anything re-renders, so the new window and the old one overlap in nothing. Every retained
        entry is new, and every one of them belongs *below* the receipt — the receipt was mounted before they
        arrived, so rewriting the old rows in place would put the newest entry above it (chronology is kept, the
        receipt's own slot included)."""
        store = self.fixture.store()
        for index in range(39):
            store.append("architect", text="старый ответ %d" % index, status="completed")
        store.append("architect", text="черновик цели", status="completed",
                     drafts=[{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": NO_PLAN}])
        async with self.shell(size=(120, 40), store=store) as pilot:
            await self.settled(pilot)
            await self.note_shown(pilot)
            main = self.main()
            main.show_card(plan_spec("receipt:1"))
            main.close_card("receipt:1", "✓ отправлен планировщику 21:05")
            await pilot.pause()
            receipt = main.card_widgets["receipt:1"]
            scroll = main.query_one("#chat")
            for index in range(40):
                store.append("architect", text="новый ответ %d" % index, status="completed")
            self.app.chat.start()  # the reload replaces the whole window in one jump
            await self.until(pilot, lambda: any("новый ответ 39" in text
                                                for text in entry_texts(main)), 10.0)
            await pilot.pause()
            children = list(scroll.children)
            newest = main.chat_entry_widgets[-1]
            self.assertLess(children.index(receipt), children.index(newest))  # below the existing receipt
            self.assertEqual(children[-1], newest)                           # the newest entry is the last child
            self.assertIs(main.card_widgets["receipt:1"], receipt)         # the receipt itself did not move

    async def test_a_completed_send_at_the_cap_keeps_the_owner_line_below_the_receipt(self):
        """Code finding 1 (i3-chat-inline): the owner's optimistic line and the persisted one must reconcile as the
        same entry, or a completed send at the 40-entry cap falls into the positional rewrite and moves the owner's
        message *across* an existing receipt. 40 entries with the goal draft last; a card is closed to a receipt;
        the owner sends a question (its optimistic line mounts below the receipt) and the architect's reply
        completes, reloading the window from the store with the owner's *persisted* row. The owner line must stay
        below the receipt."""
        store = self.fixture.store()
        for index in range(39):
            store.append("architect", text="архитектор ответ %d" % index, status="completed")
        store.append("architect", text="черновик цели", status="completed",
                     drafts=[{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": NO_PLAN}])
        async with self.shell(size=(120, 40), store=store) as pilot:
            await self.settled(pilot)
            await self.note_shown(pilot)
            main = self.main()
            main.show_card(plan_spec("receipt:1"))
            main.close_card("receipt:1", "✓ отправлен планировщику 21:05")
            await pilot.pause()
            receipt = main.card_widgets["receipt:1"]
            scroll = main.query_one("#chat")
            await self.say(pilot, "вопрос после квитанции")
            await self.chat_done(pilot)
            await self.until(pilot, lambda: any("Привет" in text for text in entry_texts(main)), 10.0)
            await pilot.pause()
            index = next(i for i, text in enumerate(entry_texts(main))
                         if "вопрос после квитанции" in text)
            owner = main.chat_entry_widgets[index]
            children = list(scroll.children)
            self.assertLess(children.index(receipt), children.index(owner))  # the owner line stays below the receipt

    async def test_a_repeated_capped_window_keeps_the_receipt_above_the_appended_pair(self):
        """Code finding 2 (i3-chat-inline): a capped window of *repeated* entries. Twenty identical owner/architect
        pairs fill the window; a receipt stands inline after the last entry; one more identical pair is appended, so
        the store grows by two while the retained window — every display text included — is exactly what it was.
        Value equality alone cannot see that slide, so the newest entry widget used to stay above the receipt. The
        reconciliation follows the entries' own occurrence in the transcript: the front pair goes, the appended pair
        mounts at the end, below the receipt."""
        store = self.fixture.store()
        for _ in range(20):
            store.append("owner", text="повтор")
            store.append("architect", text="ответ", status="completed")
        async with self.shell(size=(120, 40), store=store) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: len(self.main().chat_entry_widgets) >= chat_module.HISTORY, 10.0)
            main = self.main()
            main.show_card(plan_spec("receipt:1"))
            await pilot.pause()
            main.close_card("receipt:1", "✓ утверждён 21:05")
            await pilot.pause()
            receipt = main.card_widgets["receipt:1"]
            scroll = main.query_one("#chat")
            self.assertIn(receipt, list(scroll.children))                      # the receipt stands in the conversation
            store.append("owner", text="повтор")
            store.append("architect", text="ответ", status="completed")
            self.app.chat.start()  # the reload slides the repeated window
            await self.until(pilot, lambda: self.app.chat.state.transcript > chat_module.HISTORY, 10.0)
            await pilot.pause(0.3)
            children = list(scroll.children)
            newest = main.chat_entry_widgets[-1]
            self.assertEqual(len(main.chat_entry_widgets), chat_module.HISTORY)  # the window is still capped
            self.assertLess(children.index(receipt), children.index(newest))     # the new entries are below it
            self.assertEqual(children[-1], newest)                              # and the newest entry is last


# The draft-submission failure paths (i3a repair: acceptance finding 1, code findings 1 and 3). ---------------

def _app_method(name):
    """The real `ZplanApp` method `name`, copied onto the stand-in app; without the app module a stub stands in its
    place, so the class and its declared tests still exist for the dependency-free declaration count."""
    def missing(self, *args, **kwargs):  # pragma: no cover - reached only where the tests skip anyway
        raise AssertionError(MISSING_REASON)
    return missing if ui is None else getattr(ui.ZplanApp, name)


class _DraftSendScreen(_Screen):
    """The screen double a draft submission runs against: the bookkeeping of `_Screen` plus the log of the sends it
    was told about (a submission that did not start the planner must report none)."""

    def __init__(self):
        super().__init__()
        self.sent = 0

    def draft_sent(self):
        self.sent += 1


class _Controller:
    """The controller side of `start_goal`: `start_planning` records the call and answers the prepared verdict at
    once, so the delivered handler runs synchronously as it would on the UI thread."""

    def __init__(self, outcome, error, calls):
        self.outcome, self.error, self.calls = outcome, error, calls

    def start_planning(self, goal, done, draft=None, card=False):
        self.calls.append((goal, draft))
        done(self.outcome, self.error)
        return None


class _GoalApp:
    """The app double of a draft submission: the real `ZplanApp.start_goal` and its own refusal/sent callbacks run
    on it, so each verdict is checked against the stand-in screen without a shell (A6 keeps the failure paths at
    unit level; the third whole-app method that covered them is retired)."""

    start_goal = _app_method("start_goal")
    note_card_refusal = _app_method("note_card_refusal")
    draft_sent = _app_method("draft_sent")

    def __init__(self, outcome, error=None):
        self.starting, self.goal_block = False, ()
        self.goal_message = ""
        self.goal_identity = NO_PLAN
        self.changes, self.checks, self.refreshes = 0, 0, 0
        self.after, self.calls = [], []
        self.screen = _DraftSendScreen()
        self.controller = _Controller(outcome, error, self.calls)

    def deliver(self, handler):
        return handler

    def changed(self):
        self.changes += 1

    def request_check(self):
        self.checks += 1

    def request_refresh(self):
        self.refreshes += 1

    def after_submission(self, outcome):
        self.after.append(outcome)

    def main_screen(self):
        return self.screen


class _PlanScreen(_Screen):
    """The screen double `/plan` is dispatched on: the real `action_plan` runs, the app records what it was asked."""

    action_plan = _main_method("action_plan")
    plan_identity_now = _main_method("plan_identity_now")
    newest_sendable_draft = _main_method("newest_sendable_draft")
    draft_card_ref = _main_method("draft_card_ref")

    def __init__(self, drafts=("k1",)):
        super().__init__()
        self.app.snapshot = SimpleNamespace(version=None, plan_state=None)  # no plan: the "no plan" draft is current
        self.sendable_drafts = {key: chat_module.Draft("goal", "%s %s" % (GOAL_DRAFT, key), "", NO_PLAN, True)
                                for key in drafts}
        self.started, self.unsent = [], []
        self.app.goal_identity = "untouched"
        self.app.start_goal = lambda goal, card_key=None: self.started.append((goal, card_key, self.app.goal_identity))
        self.app.send_unsent_plan = lambda: self.unsent.append(True)


@unittest.skipUnless(HAVE, MISSING_REASON)
class PlanCommandDispatchTests(unittest.TestCase):
    """K1b C3 and C2, v3e A2: what `/plan` acts on. Interpretation: a goal typed after the command (`argument`) wins
    over a sendable draft; a bare `/plan` sends the *newest* sendable draft with its own identity; one whose plan
    moved on is refused on the status line and starts nothing; a bare `/plan` with no draft goes to
    `send_unsent_plan`, while a `key` that names no draft only says `note.not_now`."""

    def test_typed_text_is_the_goal_even_beside_a_sendable_draft(self):
        screen = _PlanScreen()
        screen.action_plan("add slugify", None)
        self.assertEqual(screen.started, [("add slugify", None, None)])  # the text, no draft, no provenance
        self.assertEqual(sorted(screen.sendable_drafts), ["k1"])         # the draft is still sendable

    def test_a2_a_bare_plan_sends_the_newest_draft_with_its_identity(self):
        screen = _PlanScreen(drafts=("older", "newer"))
        screen.action_plan("", None)
        self.assertEqual(screen.started, [("%s newer" % GOAL_DRAFT, "newer", NO_PLAN)])
        self.assertEqual(screen.unsent, [])

    def test_a2_a_draft_the_plan_moved_past_is_refused_on_the_status_line_and_starts_nothing(self):
        screen = _PlanScreen()
        screen.app.snapshot = SimpleNamespace(version=1, plan_state={"status": "proposed", "override": None})
        screen.status_note = lambda line: setattr(screen.app, "chat_note", line)
        screen.action_plan("", None)
        self.assertEqual((screen.started, screen.unsent), ([], []))
        self.assertEqual(screen.app.chat_note, "%s: %s" % (chat_module.OUTDATED, "a plan appeared"))

    def test_a_bare_plan_with_no_draft_sends_the_unsent_plan_and_a_dead_key_does_not(self):
        screen = _PlanScreen(drafts=())
        screen.action_plan("", None)
        self.assertEqual((screen.started, screen.unsent), ([], [True]))
        screen.action_plan("", "k1")  # a key that names no sendable draft
        self.assertEqual((screen.started, screen.unsent), ([], [True]))
        self.assertEqual(screen.app.chat_note, strings.text("note.not_now", name="/plan"))


@unittest.skipUnless(HAVE, MISSING_REASON)
class CardSubmissionTests(unittest.TestCase):
    """The draft-submission failure paths at unit level (A6: the whole-app budget is two). The real
    `ZplanApp.start_goal` runs on `_GoalApp` with the controller answering one prepared verdict, so a submission
    that did not start the planner is checked against what it leaves behind and the line the owner reads."""

    def test_a_submission_that_does_not_start_keeps_the_draft_and_says_why(self):
        """Code-review finding 1: `start_goal` reported the draft as sent for *every* non-error, non-`unsent`
        verdict, so `Outcome("stale")` — `planning.submission` returns it when the target changed between preparation
        and submission and starts no planner — sent the draft away and started nothing. The stale verdict is now a
        refused submission like the others.

        The readiness refusal (`unsent`) and the controller error are the same two paths: they keep the draft
        sendable and say why on the main screen's own status line. Interpretation: the draft is sent only when the
        planner actually started, so `stale` and `unsent` are treated alike; the line for `stale` is `PLAN_OUTDATED`,
        the wording the plan screen's own watch already shows."""
        unsent = Outcome("unsent", checks_of([check("branch", False, DIRTY, key="d")]))
        stale = Outcome("stale")
        cases = ((None, "planner unavailable", "Not done: planner unavailable"),
                 (unsent, None, ui.NOT_STARTED_BELOW),
                 (stale, None, ui.PLAN_OUTDATED))
        for outcome, error, expected in cases:
            with self.subTest(kind=outcome.kind if outcome is not None else "error"):
                app = _GoalApp(outcome, error)
                app.start_goal(GOAL_DRAFT, card_key="k1")
                self.assertEqual(app.calls, [(GOAL_DRAFT, NO_PLAN)])  # the draft's own identity travelled
                self.assertEqual(app.screen.sent, 0)                  # the draft was not sent
                self.assertEqual(app.after, [])                       # nothing was submitted to the plan watch
                self.assertIn(expected, app.screen.app.chat_note)     # the refusal is on the main line
                self.assertFalse(app.starting)                        # another press is not swallowed
                if outcome is unsent:  # the readiness refusal names the failing check it lists
                    self.assertIn("отсоединён", app.screen.app.chat_note)

    def test_a_started_submission_sends_the_draft(self):
        """The other half of the same callback (no regression): a verdict that *did* start the planner sends the
        draft (it is not sendable any more), clears the draft's provenance and hands the verdict to the plan watch —
        so the stale branch did not swallow the success case. A goal typed as `/plan <text>` (no key) sends no draft."""
        app = _GoalApp(Outcome("ready"))
        app.start_goal(GOAL_DRAFT, card_key="k1")
        self.assertEqual(app.calls, [(GOAL_DRAFT, NO_PLAN)])
        self.assertNotEqual(app.after, [])
        self.assertIsNone(app.goal_identity)
        self.assertEqual(app.screen.sent, 1)
        typed = _GoalApp(Outcome("ready"))
        typed.start_goal("add slugify")
        self.assertEqual(typed.screen.sent, 0)
