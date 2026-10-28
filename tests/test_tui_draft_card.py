"""I3a: the decision cards on the main screen — the shared card contract and the first card, «Составить план из
этого?», for the architect's goal draft (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md run i3a).

One acceptance criterion per test, and at most two whole-app tests (A6): A1+A2 drive the real shell once at 120x40
and once at 80x24 (`DraftCardTests`), A3+A4 drive it once more (`StaleDraftTests`); A5, the card contract
(`show_card`/`close_card`/`drop_card`, one card per key), the card key's own rule and every card-submission failure
path are unit level, with stand-in screens and no pilot (`CardContractTests`, `CardSubmissionTests`). The first
repair's third whole-app method (`CardRefusalTests`) is retired by the acceptance finding on A6 and its checks moved
to the unit-level `CardSubmissionTests`; the reply time, the `draft` state under a proposed or a failed plan and the
reply occurrence are the unit regressions.

Interpretations this run had to make (the worker's summary never reaches the reviewers, so they are recorded here):

- The card's `at` is the *reply's* own `HH:MM` (`draft_reply_time` reads the store row the reply came from, its
  `ts` in its own offset — no timezone conversion), not the clock read when the card is drawn; the sent receipt's
  `HH:MM` stays the clock read when the owner acts (the moment the plan started). `chat.ChatEntry` carries no
  timestamp and `chat.py` is outside this run's write-set, so the reply is found again in the transcript.
- An open goal draft comes *first* in `slash_state`'s precedence — ahead of a proposed plan, a failed planning run
  (`run_failed`/`proposal_invalid`), a question, a merge and even a running stage: the card is the decision the
  owner is looking at, and the palette must let the typed `/plan` reach it exactly as the card's button does. With
  no open draft every other fact keeps its precedence, a running stage included.
- A `/plan` that does not start the planner (a readiness refusal — `start_planning` answering `unsent` — a
  submission refused as `stale`, or a controller error) keeps the card open and writes no receipt; the refusal is
  said on the main screen's own status line, because `goal_message`/`goal_block` are drawn by no screen
  (K1b removed the goal form). The `stale` line is `PLAN_OUTDATED`, the same wording the
  plan screen's own watch shows.
- The card key carries the reply's own *occurrence* in the store's transcript (its place counted from the start of
  an append-only file, not a distance from the end of the retained window): two drafts of one reply and two
  *identical* replies each get their own card, while the same stored reply — across a refresh, a restart or a slide
  of the retained window — keeps its key, so a declined reply stays declined.
- The card slot holds one card *per key*: `show_card` mounts a new key beside the others and replaces its own,
  so an unrelated open card is kept (acceptance finding 2 — the slot used to take every other card off). Only a
  *closed* receipt has the stated newer-card expiry: a newer card or a new chat turn takes it off. A key, once shown
  or declined, is never shown again, and the card a refresh offers is decided by that key, never by the draft value
  (acceptance finding 1).
- A typed `/plan` with no open draft card is refused with `note.not_now` (the command's own state already decides
  most of it; the card path never opens the goal form and never pushes the plan screen over the chat).
- The start itself is `ZplanApp.start_goal`: the goal form's own paths are unchanged (its `unsent` and its `stale`
  still leave the form and show the plan screen); only the card path (`card_key` set) keeps its card and adds the
  main-screen line. The UI's stale refusal is only the first of the two checks (the worker re-checks the same
  provenance before it writes).
- A5 is checked at the dispatcher level (`MainScreen.run_command`) with a stand-in screen instead of a third
  whole-app walk, as A6 asks.
- The i3b merge (the plan-approval card) put a second card on the conversation beside the draft's: while a plan is
  proposed `CARD_SOURCES["plan"]` returns `plan:<version>`. The whole-app tests here name their draft card by its
  `draft:` key (`card()`), because the plan card lives beside it. (i3a's newer-card expiry for a *closed* receipt is
  gone with i3-chat-inline: the sent receipt stays in the history, so the whole-app A2 below reads it there;
  `CardSubmissionTests.test_a_started_card_submission_writes_the_receipt` still checks the receipt the real
  `start_goal` writes.)

i3-chat-inline (this run) made the conversation a `VerticalScroll` of one widget per history entry with the cards
mounted inline among them (`#cards` is gone). This run's additions here: `DraftCardTests`' 120x40 pass walks the joint
example's A1/A2 as well — after the draft's `/plan` the plan card mounts *below* the draft's sent receipt (A1), and
approving the plan turns it into its own receipt in place while the draft's receipt stays (A2) — and
`NarrowDraftCardTests` is the one added whole-app walk (A5 at 80x24: a card opening while the canvas is shown brings
«Разговор» back through `show_card`'s `show_chat`). Interpretations are in the changed method's and that class's
docstrings.

The repair (acceptance findings 1-3, code findings 1-2) adds: `NarrowDraftCardTests`' second walk is the joint
example at 80x24 — the size the changed joint test skipped — where both cards must be fully drawn with the view at
the conversation's end (the reveal retried until the card has layout, and `#chat > Card:last-child` dropped the
trailing margin row that spent a visible row); and `CappedWindowTests` is the capped history: a card's receipt in
the conversation, the window slid one entry, the appended reply mounting *below* the receipt (the reconciliation
follows the `ChatEntry`, not the renumbered display text). The role swap of a rewritten window is the unit-level
`RoleRewriteTests` of `tests/test_tui_chat_scroll.py`.

The second repair (the acceptance finding on A1 at 80x24) adds `NarrowDraftCardTests`'
`test_a1_two_open_cards_stay_fully_drawn`: the goal-draft card stays open while the planner is completed through the
app's existing planning path, so the conversation holds *two open cards* with buttons — the case the joint walks
above left uncovered by starting the plan from the card's own button (which closes the draft). The failed
reproduction had the draft card's title and body clipped above the view at 80x24, because the narrow pane cannot
hold two lab cards (fourteen rows with the drop between them) in the eleven rows the four head rows and the status
line leave. The repair's
layout change is `zplan.tcss`'s `MainScreen.narrow` card rules (the indent and the drop around a card go, and so
does its dim command line; the buttons, the text and the wide pane are untouched), and the interpretation is
recorded in that test's docstring.
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
    """The closed card's receipt as a pattern: `card.draft_sent` with a `HH:MM` time (A2's «✓ отправлен
    планировщику HH:MM»), read from the catalog so the check holds whatever language the runner's UI uses."""
    filled = strings.text("card.draft_sent", time="00:00")
    return re.escape(filled).replace("00:00", r"\d\d:\d\d")


def plan_receipt_pattern():
    """The plan card's closed receipt as a pattern: `card.plan_done` with a `HH:MM` time (i3-chat-inline A2's
    «✓ утверждён HH:MM»), read from the catalog like `receipt_pattern`."""
    filled = strings.text("card.plan_done", time="00:00")
    return re.escape(filled).replace("00:00", r"\d\d:\d\d")


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
        first = cards.draft_card("k1", at="21:03")
        screen.show_card(first)
        self.assertEqual(screen.box.mounted, [screen.card_widgets["k1"]])
        self.assertEqual(screen.card_specs["k1"], first)
        second = cards.draft_card("k1", at="21:04")  # the same key, a new spec
        screen.show_card(second)
        self.assertEqual(screen.card_specs["k1"], second)
        self.assertEqual(screen.box.mounted[-1].spec, second)
        self.assertEqual(screen.box.after, [(screen.box.mounted[-1], screen.box.mounted[0])])  # replaced in place
        self.assertEqual(screen.box.removed, [screen.box.mounted[0]])  # the replaced card left the conversation
        other = cards.draft_card("k2", at="21:05")
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
        third = cards.draft_card("k3", at="21:06")
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
        receipt line (no buttons), and the conversation holds no open draft card any more — the `draft` state is
        left, so a later `/plan` (typed, key None) finds nothing to act on. i3-chat-inline: the receipt stays in the
        history (no `drop_closed_cards` any more) — it is the card's own place kept."""
        screen = _Screen()
        screen.show_card(cards.draft_card("k1", at="21:03"))
        self.assertEqual(len(list(screen.card_widgets["k1"].compose())), 3)  # text, buttons, hint
        screen.draft_cards["k1"] = chat_module.Draft("goal", GOAL_DRAFT, "", NO_PLAN, True)
        self.assertTrue(screen.draft_card_open())
        receipt = strings.text("card.draft_sent", time="21:05")
        screen.close_card("k1", receipt)
        closed = screen.card_widgets["k1"]
        self.assertEqual(closed.spec.done, receipt)
        self.assertEqual([type(widget).__name__ for widget in closed.compose()], ["Static"])  # no buttons
        self.assertFalse(screen.draft_card_open())
        self.assertIsNone(screen.draft_card_ref(None))
        self.assertIn("k1", screen.card_widgets)  # the receipt stays in the conversation
        self.assertNotIn(closed, screen.box.removed)

    def test_the_card_key_is_stable_and_tells_two_drafts_of_one_plan_apart(self):
        """The key rule of A2/A4: two drafts of one reply under one plan share the plan identity, so the key is
        built from the reply and the draft's own text — two drafts get two keys — and the same stored draft keeps
        its key (that is what makes a card shown once per key and a declined key stay declined)."""
        entry = chat_module.ChatEntry("architect", "Вот два черновика.",
                                      drafts=(chat_module.Draft("goal", "Первый", "", NO_PLAN, True),
                                              chat_module.Draft("goal", "Второй", "", NO_PLAN, True)))
        first, second = entry.drafts
        key_a = ui.draft_card_key(entry, first)
        key_b = ui.draft_card_key(entry, second)
        self.assertNotEqual(key_a, key_b)
        self.assertNotEqual(key_a, repr(first.identity))  # never the identity alone
        self.assertEqual(key_a, ui.draft_card_key(entry, first))  # stable across calls (a refresh, a restart)
        # the newest actionable draft of the reply is the card (a store that does not carry it: content alone)
        self.assertEqual(ui.draft_card_of(_Chat([], (entry,))), (key_b, second))

    def test_regression_two_identical_replies_are_two_cards_and_a_slide_keeps_the_key(self):
        """Acceptance finding 1: the card key hashed the reply's *content* alone, so a reply repeated identically
        under one plan identity (the acceptance officer's reproduction: decline a draft, ask the architect to repeat
        the identical reply and draft) got the same key, and the second, still actionable draft was suppressed as
        already seen (`refresh_draft_card`'s `cards_seen`) — no card appeared and `/plan` found no open decision.

        The key now carries the reply's own *occurrence* (`reply_occurrence`): its place counted from the start of
        the store's append-only transcript. Reproduction here: two identical stored replies key apart (the later one
        is its own card); the same stored reply keys the same across a refresh, a restart and a slide of the retained
        window (owner rows appended behind it move the window but not the reply's place); and `draft_card_of` reads
        the reply's own entry and draft from `ChatState.entries` (the newest actionable draft wins).

        Interpretation: the provenance is a count from the start of the file, never a distance from the end of the
        retained window — the window slides (HISTORY) and a distance would move with it, re-keying a declined card
        and bringing it back. The *last* stored row matching the entry is the reply's own (the newest card is the
        newest actionable draft's reply). Without a readable store, or for a reply it does not carry, the content
        alone decides the key, exactly as before."""
        def reply(text=GOAL_DRAFT):
            return {"role": "architect", "status": "completed", "text": "Вот черновик.",
                    "drafts": [{"kind": "goal", "text": text, "milestone": None, "identity": NO_PLAN}]}
        asked = {"role": "owner", "text": "вопрос"}
        rows = [asked, reply()]
        key, draft = ui.draft_card_of(draft_chat(rows))
        self.assertEqual((draft.text, draft.identity), (GOAL_DRAFT, NO_PLAN))
        # the same stored reply keeps its key across a refresh and a restart of the shell
        self.assertEqual(ui.draft_card_of(draft_chat(rows))[0], key)
        # the architect repeats the identical reply and draft under the same plan identity: a new occurrence, a card
        # of its own — the declined first reply's key is not reused
        twice = rows + [{"role": "owner", "text": "повтори"}, reply()]
        again, draft2 = ui.draft_card_of(draft_chat(twice))
        self.assertEqual((draft2.text, draft2.identity), (draft.text, draft.identity))
        self.assertNotEqual(again, key)
        # a slide of the retained window works on the same store: the original reply keeps its own key
        slid = rows + [{"role": "owner", "text": "дальше %d" % index} for index in range(5)]
        self.assertEqual(ui.draft_card_of(draft_chat(slid))[0], key)
        # a store that cannot be read (or a reply it does not carry) falls back to the content alone
        self.assertEqual(ui.draft_card_of(_Chat([], chat_module.entries_of(rows)))[0],
                         ui.draft_card_key(chat_module.entries_of(rows)[1], draft))

    def test_regression_refresh_shows_a_card_for_a_repeated_identical_reply_and_keeps_it_declined(self):
        """Acceptance finding 1 / code finding 1: `refresh_draft_card` compared the *draft value* against the open
        card's draft before it looked at the reply-specific key, so a second architect reply carrying an identical
        draft was suppressed although its key had never been shown — the requirement is to show a card when
        `newest_goal_draft` returns a draft whose card key was never shown. Reproduction with the real method: show
        a reply, append an identical draft in a new reply, refresh — a request for the new key must appear (pre-fix
        zero requests, the first card and its time retained); decline the shown card and refresh — the declined key
        is in `cards_seen`, so the identical draft does not reappear (pre-fix it did, as one request for the
        already-present second reply). `tests/test_tui_draft_card.py`'s key rule alone missed this integration
        defect: it never ran `refresh_draft_card`.

        Interpretation: the same *key*, never the draft value, is what makes a card "already shown" — two drafts
        under one plan share the value (task: a key that is not `draft.identity` alone), and an open card of another
        key is an unrelated open decision, left where it is."""
        def reply():
            return {"role": "architect", "status": "completed", "text": "Вот черновик.",
                    "drafts": [{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": NO_PLAN}]}
        rows = [{"role": "owner", "text": "вопрос"}, reply()]
        first_key, _ = ui.draft_card_of(draft_chat(rows))
        screen = _DraftScreen(draft_chat(rows))
        screen.refresh_draft_card()
        self.assertEqual([message.key for message in screen.posted], [first_key])  # the first reply's card
        self.assertEqual(list(screen.draft_cards), [first_key])
        screen.refresh_draft_card()
        self.assertEqual([message.key for message in screen.posted], [first_key])  # the same key: nothing more
        # the architect repeats the identical reply and draft: a new occurrence, a key never shown — its own card
        screen.app.chat = draft_chat(rows + [{"role": "owner", "text": "повтори"}, reply()])
        second_key, second_draft = ui.draft_card_of(screen.app.chat)
        self.assertNotEqual(second_key, first_key)
        self.assertEqual(second_draft.text, GOAL_DRAFT)
        screen.refresh_draft_card()
        self.assertEqual([message.key for message in screen.posted], [first_key, second_key])
        self.assertEqual(list(screen.draft_cards), [first_key, second_key])  # both stay open decisions
        # /decline the repeated draft: its key is remembered as seen, so a refresh does not bring it back
        screen.drop_card(second_key)
        screen.refresh_draft_card()
        self.assertEqual([message.key for message in screen.posted], [first_key, second_key])
        self.assertNotIn(second_key, screen.draft_cards)
        self.assertIn(second_key, screen.cards_seen)
        self.assertEqual(list(screen.draft_cards), [first_key])

    def test_a2_the_card_carries_the_reply_time_not_the_display_clock(self):
        """Acceptance finding 4 (task: `show_card(draft_card(key, at=<reply time HH:MM>))`): the card's `at` is
        the reply's own time, carried from the stored transcript, not the clock read when the card is drawn.

        Reproduction on the candidate: a retained reply timestamped `2026-10-23T08:17:00+03:00` was stamped with
        the *current* clock (22:22) — opening retained history from an earlier time always showed the moment of
        opening. Interpretation: `chat.ChatEntry` carries no timestamp and `chat.py` is outside this run's
        write-set, so the reply is found again in the store's transcript (the same rows the pane's entry was built
        from) by the draft it carries, and its `ts` gives the time in its own offset. A row that names no time
        falls back to the clock the card is drawn at."""
        draft = chat_module.Draft("goal", GOAL_DRAFT, "", NO_PLAN, True)
        row = {"ts": "2026-10-23T08:17:00+03:00", "role": "architect", "status": "completed",
               "text": "Вот черновик.",
               "drafts": [{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": NO_PLAN}]}
        self.assertEqual(ui.stamp_hm(row["ts"]), "08:17")
        with patch.object(card_kinds, "card_clock", return_value="22:22"):  # the clock the card is drawn at now
            self.assertEqual(ui.draft_reply_time(_Chat([row]), draft), "08:17")  # the reply's time wins
            self.assertEqual(ui.draft_reply_time(_Chat([dict(row, ts="")]), draft), "22:22")  # no time: the clock
            self.assertEqual(ui.draft_reply_time(_Chat([]), draft), "22:22")  # no row at all: the clock

    def test_regression_an_open_draft_makes_the_typed_plan_available_under_a_proposed_plan(self):
        """Acceptance finding 3: with an open draft card the screen is in `draft` even while a plan is *proposed*,
        so the palette submits the typed `/plan` exactly as the card's button does (the button bypasses the
        palette's own validation). Pre-fix `slash_state` returned `plan_ready` for a `proposed` revision before it
        ever looked at `draft`, so `palette.submit("/plan", ...)` was a `Refused` and the typed line never reached
        the card although clicking did.

        Interpretation: the card is the decision the owner is looking at, so an open goal draft comes before
        `plan_ready` in the precedence (i3a); with no open draft the same proposed screen keeps its `plan_ready`."""
        proposed = Snapshot("P", "main", True, 1, "proposed", (), ())
        self.assertEqual(ui.slash_state(proposed, draft=True), "draft")
        verdict = palette.submit("/plan", ui.slash_state(proposed, draft=True))
        self.assertIsInstance(verdict, palette.Submitted)
        self.assertEqual(verdict.command_name, "/plan")
        self.assertEqual(ui.slash_state(proposed), "plan_ready")  # unchanged without an open draft
        self.assertIsInstance(palette.submit("/plan", ui.slash_state(proposed)), palette.Refused)

    def test_regression_an_open_draft_reaches_the_typed_plan_under_a_failed_plan(self):
        """Code-review finding 2: with an open, non-stale draft card and a plan whose status is `run_failed` or
        `proposal_invalid` (or a `kind == "failed"` view), `slash_state(..., draft=True)` returned `error` because
        the failed-planning branch sat ahead of `draft`. `/plan` is registered only for the `draft` state, so the
        palette refused the typed line before dispatch while the card's button reached `action_plan` and
        `start_goal` — the same button/typed-line divergence acceptance finding 3 fixed for a *proposed* plan.

        Interpretation: the open card is the decision on screen, so `draft` is the screen's state under a failed plan
        (the plan the card asks to redo); with no open draft that fact keeps its own state (`error`). R-B (tests.
        test_tui_rb_fixes) moved the running stage, a question, a merge and an error line ahead of `draft`, so a
        live stage is `running` with or without the card. The card's own staleness is still checked by `action_plan`
        and again on the worker, so this precedence only decides reachability."""
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
            self.assertEqual(ui.slash_state(revision), "error")  # unchanged without an open draft
        running = Snapshot("P", "main", True, None, None, (), (),
                           rows=(Row(id="M1", title="M1", state="running", text="идёт"),))
        self.assertEqual(ui.slash_state(running, draft=True), "running")  # R-B: a live stage outranks the card
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
    """The store side `draft_reply_time` reads: only a `transcript()` of the stored rows."""

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
    `drop_card`, `draft_card_open`, `draft_card_ref`, `run_command`'s note path), and only the widgets they touch
    are doubled — the slot above and the app's note pad. No DOM, no project, no pilot."""

    show_card = _main_method("show_card")
    close_card = _main_method("close_card")
    drop_card = _main_method("drop_card")
    unmount_card = _main_method("unmount_card")
    draft_card_open = _main_method("draft_card_open")
    open_draft_card = _main_method("open_draft_card")
    draft_card_ref = _main_method("draft_card_ref")
    status_note = _main_method("status_note")
    show_chat = _main_method("show_chat")  # a no-op here: the stand-in is wide
    newest_card_for = _main_method("newest_card_for")
    narrow = False

    def __init__(self):
        self.box, self.app = _Slot(), _Pad()
        self.card_widgets, self.card_specs, self.draft_cards, self.cards_seen = {}, {}, {}, set()

    def query_one(self, selector, *args):
        if selector == "#chat":
            return self.box
        raise AssertionError(selector)

    def scroll_chat_end(self):
        """UI-only: the stand-in has no scroll to move."""

    def call_after_refresh(self, callback):
        """The card's own scroll-to-bottom request is UI work: the stand-in has no running app to schedule it on."""


class _DraftScreen(_Screen):
    """The card contract screen with a chat and a message sink: the real `refresh_draft_card` runs on it, so the
    discovery of *which* draft gets a card is exercised (the key compared, never the draft value), not the key rule
    alone. `posted` collects the `DraftCardRequested` requests the screen would hand to its own pump."""

    refresh_draft_card = _main_method("refresh_draft_card")
    plan_identity_now = _main_method("plan_identity_now")
    retire_stale_draft_cards = _main_method("retire_stale_draft_cards")

    def __init__(self, chat):
        super().__init__()
        self.app.chat = chat
        self.app.snapshot = SimpleNamespace(version=None, plan_state=None)  # loaded, and no plan: a "no plan" draft is current
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


# The whole-app half: A1+A2 and A3+A4, one test each. ----------------------------------------------------------


@unittest.skipUnless(HAVE, MISSING_REASON)
class DraftCardShell(ChatShell):
    """The chat shell with one architect reply carrying one actionable goal draft, written into the store before the
    shell opens (the card is built from the retained history, exactly as `[c]` reads it)."""

    def seed_goal_draft(self, text=GOAL_DRAFT, identity=NO_PLAN, status="completed"):
        """One owner question and one architect reply carrying one goal draft in the store."""
        store = self.fixture.store()
        store.append("owner", text="вопрос")
        store.append("architect", text="Вот черновик.", status=status,
                     drafts=[{"kind": "goal", "text": text, "milestone": None, "identity": identity}])
        return store

    def append_plan_draft(self, store):
        """A newer architect reply whose goal draft carries the plan identity the last pass saw (`live_identity`), so
        a reload finds it current — a draft already stale against the plan never opens a card (R-A)."""
        store.append("owner", text="ещё")
        store.append("architect", text="Вот новый черновик.", status="completed",
                     drafts=[{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": self.live_identity}])

    def main(self):
        """The main screen, whatever modal (if any) is on top."""
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def card(self):
        """The card under test: the conversation's *draft* card, or None.

        The conversation holds one card per key (i3a) and i3b mounts the plan card of a proposed plan beside it too,
        so the newest child can be another decision (the fixture planner proposes as soon as `/plan` starts it).
        These tests are about the goal draft alone, so they name their card by its `draft:` key in
        `screen.card_widgets` instead of the conversation's last child.
        """
        return next((card for key, card in self.main().card_widgets.items()
                     if key.startswith("draft:")), None)

    async def settled(self, pilot, timeout=8.0):
        """The chat is ready and the retained history carries the seeded actionable goal draft."""
        await self.loaded(pilot)
        await self.chat_ready(pilot)
        await self.until(pilot, lambda: chat_module.newest_goal_draft(self.app.chat.state.entries) is not None,
                         timeout)

    async def card_shown(self, pilot, timeout=8.0):
        """The draft card of the slot, once it is mounted and laid out."""
        await self.until(pilot, lambda: self.main().draft_card_open(), timeout)
        await pilot.pause(0.3)
        return self.card()

    def plan_card(self):
        """The conversation's *plan* card (`plan:<version>`), or None — the joint example's second card, which the
        fixture planner mounts beside the draft's once `/plan` starts it."""
        return next((card for key, card in self.main().card_widgets.items() if key.startswith("plan:")), None)

    async def choose(self, pilot, command):
        """Press the button carrying the slash command `command` on the draft card."""
        await self.choose_on(self.card(), pilot, command)

    async def choose_on(self, card, pilot, command):
        """Press the button carrying the slash command `command` on `card`."""
        button = next(widget for widget in card.query(Button) if widget.command == command)
        await pilot.click(button)
        await pilot.pause(0.3)

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
        """The «Черновик цели» canvas tab: its label and the body it holds (the tab the draft card opens)."""
        right = self.main().query_one("#right")
        tab_id = self.main().view_tabs[0]
        body = right.get_pane(tab_id).query_one(Static).content.plain
        return right.get_tab(tab_id).label.plain, body

    def assert_joint_cards(self, card, size):
        """A1 (i3-chat-inline) in the joint example: the draft's sent receipt and the live plan card are both
        entries of the conversation's scroll, the plan card below the receipt, each of them fully drawn inside the
        chat pane — neither clipped above nor below — and the view at the conversation's own end. Returns the
        receipt so a caller can keep naming it."""
        main = self.main()
        plan = self.plan_card()
        receipt = main.card_widgets[card.spec.key]
        scroll, pane = main.query_one("#chat"), main.query_one("#chat-pane")
        self.assertIs(receipt.parent, scroll, size)
        self.assertIs(plan.parent, scroll, size)
        self.assertGreater(plan.region.y, receipt.region.y, size)                  # the plan card is below the draft
        self.assertEqual(scroll.scroll_offset.y, scroll.max_scroll_y, size)        # the view is at the bottom
        for entry in (receipt, plan):
            self.assertGreater(entry.region.height, 0, size)
            self.assertGreaterEqual(entry.region.y, scroll.content_region.y, size)    # not clipped above
            self.assertLessEqual(entry.region.bottom, pane.region.bottom, size)       # not clipped below
        return receipt

    def assert_card_under_the_chat(self, card, size):
        """A1 (i3-chat-inline): the card is mounted inline in the conversation's scroll (`#chat`), inside the chat
        pane, and both buttons and the title are drawn on screen (the view is at the bottom, where the card was
        mounted)."""
        main = self.main()
        scroll, pane = main.query_one("#chat"), main.query_one("#chat-pane")
        self.assertIs(card.parent, scroll, size)                # the card is an entry of the conversation
        self.assertGreater(card.region.height, 0, size)         # it took its own rows
        self.assertLessEqual(card.region.bottom, pane.region.bottom, size)  # inside the chat pane
        shown = screen_text(self.app)
        self.assertIn(strings.text("card.draft_title"), shown, size)
        for label in (strings.text("card.plan_yes"), strings.text("card.no")):
            self.assertIn(label, shown, size)


@unittest.skipUnless(HAVE, MISSING_REASON)
class DraftCardTests(DraftCardShell):
    async def test_a1_a2_the_draft_card_shows_and_plan_starts_from_it(self):
        """A1 at 120x40 and 80x24: with the fixture chat whose last architect reply carries an actionable goal
        draft, the card shows under the chat with its two buttons and the «Черновик цели» tab holds the intro and
        the whole draft text. A2: pressing «да» calls `start_planning` once with the draft text and its
        identity, the draft stops being an open decision, and a second `/plan` is refused because the state
        is no longer `draft` (the sent receipt the card becomes is the unit-level `CardSubmissionTests`, see the
        module docstring). A6's budget of two whole-app methods for A1-A4 holds: A1 walks both sizes here, A2
        walks the 120x40 one (the typed line's own success path resolves the open card through
        `draft_card_ref(None)`, pinned in `CardContractTests`), and A3+A4 are the other method.

        The store is written once, before the first shell opens, and only the 120x40 pass starts anything — so the
        80x24 pass sees the same fresh, unstale draft the 120x40 pass does (one fixture project is shared by both
        passes of a test method).

        i3-chat-inline adds the joint example to the 120x40 pass (A1/A2): after the draft's `/plan` the plan card
        mounts *below* the draft's sent receipt, and A1's "both cards" are that receipt and the live plan card —
        the owner starts the planner from the draft card, which is what closes the draft, so it is a receipt by the
        time the plan card appears (the lab draws the same «approve» state). Approving the plan then leaves both
        receipts in the history (A2): the draft's receipt staying is this run's change — i3a's newer-card expiry is
        gone."""
        store = self.seed_goal_draft()
        reply_at = ui.stamp_hm(store.transcript()[-1]["ts"])  # the reply's own time, what the card's `at` must be
        for size in ((80, 24), (120, 40)):
            with self.subTest(size=size):
                calls = []
                with patch.object(Controller, "start_planning", self.counting_start(calls)):
                    async with self.shell(size=size, store=store) as pilot:
                        await self.settled(pilot)
                        card = await self.card_shown(pilot)
                        self.assert_card_under_the_chat(card, size)
                        self.assertEqual(card.spec.at, reply_at, size)  # the reply's time, never the display clock
                        label, body = self.draft_tab()  # A1: the tab beside «План», the whole draft in it
                        self.assertEqual(label, strings.text("canvas.draft_tab"), size)
                        self.assertEqual(body, strings.text("canvas.draft_intro") + "\n\n" + GOAL_DRAFT, size)
                        if size == (80, 24):
                            continue  # A1 only at this size: the 120x40 pass below walks A2 on the same store
                        # A2: pressing «да» sends the draft to the planner with the draft's own identity
                        await self.choose(pilot, "/plan")
                        await self.until(pilot, lambda: calls and not self.main().draft_card_open())
                        self.assertEqual(calls, [(GOAL_DRAFT, NO_PLAN)], size)
                        self.assertNotEqual(ui.screen_slash_state(self.app), "draft", size)  # no decision is open
                        # i3-chat-inline A1 (the joint example): the fixture planner proposes right away, so the
                        # plan card mounts *below* the draft's sent receipt — both entries of the conversation's
                        # scroll, both fully drawn (the plan card with its own buttons), the view at the bottom.
                        plan = await self.plan_card_shown(pilot)
                        draft_receipt = self.main().card_widgets[card.spec.key]
                        scroll, pane = self.main().query_one("#chat"), self.main().query_one("#chat-pane")
                        self.assertIs(draft_receipt.parent, scroll, size)
                        self.assertIs(plan.parent, scroll, size)
                        self.assertGreater(plan.region.y, draft_receipt.region.y, size)
                        self.assertEqual(scroll.scroll_offset.y, scroll.max_scroll_y, size)
                        for entry in (draft_receipt, plan):
                            self.assertGreater(entry.region.height, 0, size)
                            self.assertGreaterEqual(entry.region.y, scroll.content_region.y, size)  # no clipping
                            self.assertLessEqual(entry.region.bottom, pane.region.bottom, size)
                        shown = screen_text(self.app)
                        self.assertRegex(shown, receipt_pattern())  # the draft's «✓ отправлен …» receipt is drawn
                        for label in (strings.text("card.approve_yes"), strings.text("card.revise")):
                            self.assertIn(label, shown, size)                      # the plan card's own buttons
                        # i3-chat-inline A2: approving the plan turns it into its own receipt *in place* (the same
                        # `plan:<version>` key, below the draft) while the draft's sent receipt stays
                        await self.choose_on(plan, pilot, "/approve")
                        await self.until(pilot, lambda: self.plan_card() is not None and self.plan_card().spec.done)
                        approved = self.plan_card()
                        self.assertRegex(approved.spec.done or "", "^%s$" % plan_receipt_pattern(), size)
                        self.assertIs(self.main().card_widgets[card.spec.key], draft_receipt, size)  # it stayed
                        self.assertGreater(approved.region.y, draft_receipt.region.y, size)
                        self.assertRegex(screen_text(self.app), plan_receipt_pattern())
                        self.assertRegex(screen_text(self.app), receipt_pattern())
                        # a second /plan starts nothing: the card is closed and the plan is approved, so a bare
                        # `/plan` has no unsent revision to send and says what to write (K1b)
                        await self.send(pilot, "/plan")
                        self.assertEqual(calls, [(GOAL_DRAFT, NO_PLAN)], size)
                        self.assertIn(strings.text("note.plan_needs_goal"), self.flat(), size)


@unittest.skipUnless(HAVE, MISSING_REASON)
class StaleDraftTests(DraftCardShell):
    async def test_a4_a_declined_card_stays_away(self):
        """A4: `/decline` takes the card off the pane, and the same draft does not bring it back on the next
        refresh. The typed line is the one path this test needs (the state is `draft`, the card is open)."""
        async with self.shell(size=(120, 40), store=self.seed_goal_draft()) as pilot:
            await self.settled(pilot)
            await self.card_shown(pilot)
            key = self.card().spec.key
            await self.send(pilot, "/decline")
            await self.until(pilot, lambda: self.card() is None)
            self.main().render_state()
            await pilot.pause(0.3)
            self.assertIsNone(self.card())
            self.assertIn(key, self.main().cards_seen)  # the declined key is remembered as seen

    async def test_regression_an_open_card_closes_once_the_plan_moved_past_it(self):
        """RC4 (0.6.0 smoke defect 4): the plan built from the draft was approved while the card stayed open, so the
        screen stayed in `draft` and `/run` was refused while the panel said «Дальше: /run». C1: on the refresh after
        the plan appeared the card is unmounted, its key stays in `cards_seen` and its «Черновик цели» tab is
        closed; C2: `screen_slash_state` then reads the plan's state, not `draft`; C3 (a card whose plan identity has
        not moved stays, as after a refused `/plan`) is the RC6 test below, which keeps the card open.

        Interpretation: «a snapshot that names a plan» is a snapshot with a revision (`snapshot.version`); the
        retirement runs on the screen's own refresh, so the test only waits for the snapshot and the refresh."""
        async with self.shell(size=(120, 40), store=self.seed_goal_draft()) as pilot:
            await self.settled(pilot)
            await self.card_shown(pilot)
            main = self.main()
            key = self.card().spec.key
            self.assertEqual(len(main.view_tabs), 1)                   # the «Черновик цели» tab is open
            self.assertEqual(ui.screen_slash_state(self.app), "draft")

            def propose(session):  # the plan appears while the card is open: the draft is stale against it
                self.begin(session.authority)
                self.propose(session.authority)
                session.authority.approve(1)
            await self.post_and_wait(pilot, propose)
            self.app.request_refresh()
            await self.until(pilot, lambda: self.app.snapshot.version is not None and self.card() is None)
            await pilot.pause(0.3)
            self.assertFalse(main.draft_card_open())
            self.assertIn(key, main.cards_seen)                        # never shown again
            self.assertEqual(main.view_tabs, [])                       # the draft tab closed with the card
            self.assertNotEqual(ui.screen_slash_state(self.app), "draft")
            main.render_state()                                        # a later refresh does not bring it back
            await pilot.pause(0.3)
            self.assertIsNone(self.card())


    async def test_regression_a_refused_card_plan_writes_no_revision_and_the_retry_starts(self):
        """RC6 (0.6.0 smoke defect 3): the card's own `/plan` met a dirty tree and `start_planning` saved an unsent
        revision before it looked at the gate, so the plan identity moved off «no plan» and the card's draft was
        «черновик устарел» for good. C1: the refusal names the checks, writes no revision and the card stays open;
        C2: after the owner fixes readiness the same card's `/plan` starts the planner (one sent revision, no
        stale line); C3 (the goal form keeps saving an unsent revision) is pinned by
        `tests/test_tui_chat.py::GoalDraftTests` and not repeated here.

        Interpretation: the refusal is the readiness gate's `unsent` answer, so the plan identity is read through
        the authority file: absent after the refusal, one revision after the retry."""
        readiness = Readiness(check("git"), check("branch", False, DIRTY, key="d"))
        authority_path = RealAuthority(self.state, self.project, fixture_id="test").path
        async with self.shell(self.controller(readiness), size=(120, 40), store=self.seed_goal_draft()) as pilot:
            await self.settled(pilot)
            await self.card_shown(pilot)
            await self.send(pilot, "/plan")
            self.assertIn("отсоединён", screen_text(self.app))        # C1: the checks are named...
            self.assertFalse(authority_path.exists())                    # ...no revision, no run
            self.assertIsNotNone(self.card())                            # ...and the card is still a decision
            readiness.fix("branch")
            await self.send(pilot, "/plan")                              # C2: the retry on the same card
            await self.until(pilot, lambda: authority_path.exists())
            await self.until(pilot, lambda: self.card() is not None and self.card().spec.done)
            self.assertNotIn(chat_module.OUTDATED, screen_text(self.app))
        revisions = json.loads(authority_path.read_text())["revisions"]
        self.assertEqual(len(revisions), 1)



@unittest.skipUnless(HAVE, MISSING_REASON)
class NarrowDraftCardTests(DraftCardShell):
    """i3-chat-inline's narrow-mode walks: A5 (a card opening brings the chat back), A1's joint example at the size
    the earlier joint test skipped, and A1 with *both* cards still open (the repair's acceptance finding)."""

    async def test_a5_a_card_opening_in_narrow_mode_brings_the_chat_back(self):
        """A5 at 80x24: while the owner looks at the canvas (`show_canvas` — what the arrows do) the architect's
        reply carrying the goal draft lands, the draft card opens in the conversation, and «Разговор» is the shown
        pane again — `show_card`'s own `show_chat` — so the decision the card holds is on screen.

        Interpretation: entering narrow mode alone already shows the chat (`layout_for`), so the check steps away to
        the canvas first and lets the card open *while the canvas is shown*; the reply that carries the draft is the
        store change the chat reloads (the same append the shell reads at load), and `show_card`'s contract — an open
        spec asks for the chat, a closed receipt does not — is what brings the pane back."""
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            main = self.main()
            self.assertTrue(main.narrow)
            main.show_canvas()  # the owner is on the canvas while the architect works
            await pilot.pause()
            self.assertFalse(main.query_one("#chat-pane").display)
            self.assertFalse(main.chat_shown)
            self.seed_goal_draft()      # the architect's reply with the goal draft reaches the stored transcript
            self.app.chat.start()       # the chat reloads it: the draft card opens
            await self.until(pilot, lambda: main.draft_card_open(), 10.0)
            await pilot.pause(0.3)
            self.assertTrue(main.chat_shown)                            # A5: the card asked for the chat
            self.assertTrue(main.query_one("#chat-pane").display)
            self.assertFalse(main.query_one("#right-column").display)
            self.assertIs(self.card().parent, main.query_one("#chat"))

    async def test_a1_the_joint_example_shows_both_cards_at_80x24(self):
        """A1 at 80x24 (the acceptance finding of the repair: the joint test walked the plan card only at 120x40):
        the draft card is shown, `/plan` starts the planner from its own button, and the plan card mounts below the
        draft's sent receipt with both cards fully drawn — the plan card's buttons on screen — and the view at the
        conversation's end. The reveal is the fix: the card is scrolled to once it has layout (a zero-size card was
        a no-op), and the newest card no longer carries a trailing margin row inside the scroll
        (`#chat > Card:last-child`), which was the row that pushed the receipt out of the view at 80x24."""
        calls = []
        with patch.object(Controller, "start_planning", self.counting_start(calls)):
            async with self.shell(size=(80, 24), store=self.seed_goal_draft()) as pilot:
                await self.settled(pilot)
                card = await self.card_shown(pilot)
                self.assert_card_under_the_chat(card, (80, 24))
                await self.choose(pilot, "/plan")
                self.assertEqual(calls, [(GOAL_DRAFT, NO_PLAN)])
                self.assertIsNotNone(await self.plan_card_shown(pilot))
                self.assert_joint_cards(card, (80, 24))
                shown = screen_text(self.app)
                self.assertRegex(shown, receipt_pattern())  # the draft's «✓ отправлен …» receipt
                for label in (strings.text("card.approve_yes"), strings.text("card.revise")):
                    self.assertIn(label, shown)                                # the plan card's own buttons

    async def test_a1_two_open_cards_stay_fully_drawn(self):
        """A1 at 80x24 and 120x40 with *two open cards* (the repair's acceptance finding): the goal-draft card is
        shown, planning is completed through the app's existing planning path while that draft card stays open —
        `begin`+`propose` on the controller's own authority, the state the goal form's submission leaves (its
        `start_goal` passes no card key, so no card is closed; the verifier's reproduction drives the same path) —
        and the plan card mounts below the draft card with both specs still `done=None`. Both cards must be fully
        drawn with their buttons inside the view, the plan card below the draft card, and the view at the
        conversation's end. The joint walks above start the plan *from the draft card's own button*, which turns
        the draft into a sent receipt, so neither covers this case.

        RC4: a draft card the plan moved past now retires, so both cards are open only for a draft made against the
        current plan: a first pass proposes the plan, a draft carrying that plan's identity is appended, and both
        sizes load the store with the two cards open. Interpretation: an
        80x24 narrow pane holds sixteen content rows and the four L-3/L-4 head rows plus the one status row leave
        eleven for the conversation, while two lab cards need fourteen of them (the draft's seven, the plan's six
        and the one-row drop the first carries between them), each carrying its dim command line as well. The narrow
        card is compact for that reason (`zplan.tcss`:
        `MainScreen.narrow #chat > Card` drops the indent and the drop around the card, so it sits flush like the
        history's own entries, and `MainScreen.narrow #chat .card-hint` leaves out the command line under the
        buttons — the commands those buttons stand for), so the draft's six rows and the plan's five fill the eleven
        exactly and both cards' buttons are in the view together; the wide pane keeps the lab card whole."""
        store = self.seed_goal_draft()
        async with self.shell(size=(80, 24), store=store) as pilot:  # the plan is proposed; the first draft retires
            await self.settled(pilot)
            await self.card_shown(pilot)

            def propose(session):
                self.begin(session.authority)
                self.propose(session.authority)
            await self.post_and_wait(pilot, propose)
            self.app.request_refresh()
            await self.plan_card_shown(pilot)
            self.live_identity = [self.app.snapshot.version, self.app.snapshot.plan_state]
        self.append_plan_draft(store)  # a draft made against the plan, which is current: its card stays open (RC4)
        for size in ((80, 24), (120, 40)):
            with self.subTest(size=size):
                async with self.shell(size=size, store=store) as pilot:
                    await self.settled(pilot)
                    draft = await self.card_shown(pilot)
                    plan = await self.plan_card_shown(pilot)
                    await pilot.pause(0.4)
                    self.live_identity = [self.app.snapshot.version, self.app.snapshot.plan_state]
                    main = self.main()
                    scroll, pane = main.query_one("#chat"), main.query_one("#chat-pane")
                    self.assertIsNone(draft.spec.done, size)   # both cards are open decisions ...
                    self.assertIsNone(plan.spec.done, size)
                    self.assertIs(main.card_widgets[draft.spec.key], draft, size)
                    self.assertIs(main.card_widgets[plan.spec.key], plan, size)
                    for entry in (draft, plan):
                        self.assertIs(entry.parent, scroll, size)              # entries of the conversation
                        self.assertGreater(entry.region.height, 0, size)
                        self.assertGreaterEqual(entry.region.y, scroll.content_region.y, size)    # not clipped above
                        self.assertLessEqual(entry.region.bottom, pane.region.bottom, size)       # nor below
                    self.assertGreater(plan.region.y, draft.region.y, size)    # the plan card below the draft card
                    self.assertEqual(scroll.scroll_offset.y, scroll.max_scroll_y, size)  # the view is at the end
                    shown = screen_text(self.app)
                    for label in (strings.text("card.plan_yes"), strings.text("card.no"),
                                  strings.text("card.approve_yes"), strings.text("card.revise")):
                        self.assertIn(label, shown, size)                      # both cards keep their buttons

    async def test_r1_the_draft_card_keeps_its_place_when_the_plan_card_mounts_first(self):
        """R1 / O1: on a reload with both cards open, the plan card (from `CARD_SOURCES`) may mount before the
        draft card (from `DraftCardRequested`); the goal-draft card still stands right after the reply that carries
        it, so `#chat` reads ..., reply, draft card, plan card. The first pass leaves a store with a goal reply and a
        proposed plan; the second pass holds the draft card's handler until `render_card_sources` has mounted
        the plan card. On the old `show_card` (every new card at the end of `#chat`) this fails on
        `assertLess(children.index(draft), children.index(plan))` (the plan card stood above the draft: 3 not less
        than 2).
        Interpretation: the reply's widget is the `#chat` entry widget of the newest entry carrying the draft
        (`draft_card_of`'s choice)."""
        store = self.seed_goal_draft()
        async with self.shell(size=(80, 24), store=store) as pilot:
            await self.settled(pilot)
            await self.card_shown(pilot)

            def propose(session):
                self.begin(session.authority)
                self.propose(session.authority)
            await self.post_and_wait(pilot, propose)
            self.app.request_refresh()
            await self.plan_card_shown(pilot)
            self.live_identity = [self.app.snapshot.version, self.app.snapshot.plan_state]
        self.append_plan_draft(store)  # the reload's draft is made against the plan, which is current (R-A)
        original = ui.MainScreen.on_draft_card_requested

        async def plan_first(screen, event):
            for _ in range(200):  # hold the draft card's handler until the plan card has mounted (bounded)
                screen.render_card_sources()
                if any(key.startswith("plan:") for key in screen.card_widgets):
                    break
                await asyncio.sleep(0.05)
            return original(screen, event)
        with patch.object(ui.MainScreen, "on_draft_card_requested", plan_first):
            async with self.shell(size=(120, 40), store=store) as pilot:
                await self.settled(pilot)
                draft = await self.card_shown(pilot)
                plan = await self.plan_card_shown(pilot)
                await pilot.pause(0.4)
                main = self.main()
                children = list(main.query_one("#chat").children)
                reply = main.draft_reply_widget(main.open_draft_card()[1])
                self.assertIsNotNone(reply)
                self.assertLess(children.index(draft), children.index(plan))
                self.assertEqual(children.index(draft), children.index(reply) + 1)
                self.assertGreater(plan.region.y, draft.region.y)


def entry_texts(main):
    """The text of each rendered entry (`app.Shown`) of the screen, one string per entry."""
    return ["\n".join(text for _kind, text in shown.blocks) for shown in main.chat_entry_texts]


@unittest.skipUnless(HAVE, MISSING_REASON)
class CappedWindowTests(DraftCardShell):
    """The capped-window reconciliation (the repair's acceptance finding 2 and code finding 2): when the retained
    history slides, an entry that stayed can change its display text (its time line) while keeping its place. The
    reconciliation must follow the entries, not the text — otherwise it
    falls into the positional rewrite and the appended entry takes a slot *before* a card already inline."""

    async def test_a2_a_capped_slide_appends_the_new_entry_after_an_inline_receipt(self):
        """40 architect replies, the last carrying the goal draft: its card is shown and closed, so its receipt
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
            card = await self.card_shown(pilot)
            main = self.main()
            main.close_card(card.spec.key, "✓ отправлен планировщику 21:05")
            await pilot.pause()
            receipt = main.card_widgets[card.spec.key]
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
            self.assertIs(main.card_widgets[card.spec.key], receipt)  # and the receipt itself did not move


    async def test_a_reload_that_replaces_the_whole_window_mounts_the_new_entries_below_the_receipt(self):
        """A reload that pushes the *whole* capped window out at once (the acceptance finding): 40 architect replies,
        the last carrying the goal draft, its card shown and closed to a receipt; then 40 more distinct replies
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
            card = await self.card_shown(pilot)
            main = self.main()
            main.close_card(card.spec.key, "✓ отправлен планировщику 21:05")
            await pilot.pause()
            receipt = main.card_widgets[card.spec.key]
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
            self.assertIs(main.card_widgets[card.spec.key], receipt)         # the receipt itself did not move

    async def test_a_completed_send_at_the_cap_keeps_the_owner_line_below_the_receipt(self):
        """Code finding 1 (i3-chat-inline): the owner's optimistic line and the persisted one must reconcile as the
        same entry, or a completed send at the 40-entry cap falls into the positional rewrite and moves the owner's
        message *across* an existing receipt. 40 entries with the goal draft last; its card is closed to a receipt;
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
            card = await self.card_shown(pilot)
            main = self.main()
            main.close_card(card.spec.key, "✓ отправлен планировщику 21:05")
            await pilot.pause()
            receipt = main.card_widgets[card.spec.key]
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
            main.show_card(cards.draft_card("draft:receipt", at="21:05"))
            await pilot.pause()
            main.close_card("draft:receipt", "✓ утверждён 21:05")
            await pilot.pause()
            receipt = main.card_widgets["draft:receipt"]
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


# The card-submission failure paths (i3a repair: acceptance finding 1, code findings 1 and 3). ---------------

def _app_method(name):
    """The real `ZplanApp` method `name`, copied onto the stand-in app; without the app module a stub stands in its
    place, so the class and its declared tests still exist for the dependency-free declaration count."""
    def missing(self, *args, **kwargs):  # pragma: no cover - reached only where the tests skip anyway
        raise AssertionError(MISSING_REASON)
    return missing if ui is None else getattr(ui.ZplanApp, name)


class _CardScreen(_Screen):
    """The screen double a card submission runs against: the card bookkeeping of `_Screen` plus the log of the
    receipts it was handed (a submission that did not start the planner must hand none)."""

    def __init__(self):
        super().__init__()
        self.closed = []

    def close_card(self, key, done_text):
        self.closed.append((key, done_text))


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
    """The app double of a card submission: the real `ZplanApp.start_goal` and its own refusal/receipt callbacks run
    on it, so each verdict is checked against the stand-in screen without a shell (A6 keeps the failure paths at
    unit level; the third whole-app method that covered them is retired)."""

    start_goal = _app_method("start_goal")
    note_card_refusal = _app_method("note_card_refusal")
    close_started_card = _app_method("close_started_card")

    def __init__(self, outcome, error=None):
        self.starting, self.goal_block = False, ()
        self.goal_message = ""
        self.goal_identity = NO_PLAN
        self.changes, self.checks, self.refreshes = 0, 0, 0
        self.after, self.calls = [], []
        self.screen = _CardScreen()
        self.screen.draft_cards["k1"] = chat_module.Draft("goal", GOAL_DRAFT, "", NO_PLAN, True)
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

    def __init__(self, with_card=True):
        super().__init__()
        self.app.snapshot = SimpleNamespace(version=None, plan_state=None)  # no plan: the "no plan" draft is current
        self.started, self.unsent = [], []
        self.app.goal_identity = "untouched"
        self.app.start_goal = lambda goal, card_key=None: self.started.append((goal, card_key, self.app.goal_identity))
        self.app.send_unsent_plan = lambda: self.unsent.append(True)
        if with_card:
            self.draft_cards["k1"] = chat_module.Draft("goal", GOAL_DRAFT, "", NO_PLAN, True)


@unittest.skipUnless(HAVE, MISSING_REASON)
class PlanCommandDispatchTests(unittest.TestCase):
    """K1b C3 and C2: what `/plan` acts on. Interpretation: a goal typed after the command (`argument`, no card
    button) wins over an open draft card; the card's button (a `key`) and a bare typed `/plan` with a card open act
    on the card's draft, with its own identity; a bare `/plan` with no card goes to `send_unsent_plan`, while the
    button of a card that is gone only says `note.not_now`."""

    def test_typed_text_is_the_goal_even_beside_an_open_card(self):
        screen = _PlanScreen()
        screen.action_plan("add slugify", None)
        self.assertEqual(screen.started, [("add slugify", None, None)])  # the text, no card, no draft provenance
        self.assertEqual(sorted(screen.draft_cards), ["k1"])             # the card is still an open decision

    def test_the_button_and_a_bare_typed_plan_send_the_card_s_goal(self):
        for key in ("k1", None):
            with self.subTest(key=key):
                screen = _PlanScreen()
                screen.action_plan("", key)
                self.assertEqual(screen.started, [(GOAL_DRAFT, "k1", NO_PLAN)])
                self.assertEqual(screen.unsent, [])

    def test_a_bare_plan_with_no_card_sends_the_unsent_plan_and_a_dead_button_does_not(self):
        screen = _PlanScreen(with_card=False)
        screen.action_plan("", None)
        self.assertEqual((screen.started, screen.unsent), ([], [True]))
        screen.action_plan("", "k1")  # the button of a card that is gone
        self.assertEqual((screen.started, screen.unsent), ([], [True]))
        self.assertEqual(screen.app.chat_note, strings.text("note.not_now", name="/plan"))


@unittest.skipUnless(HAVE, MISSING_REASON)
class CardSubmissionTests(unittest.TestCase):
    """The card-submission failure paths at unit level (A6: the whole-app budget is two). The real
    `ZplanApp.start_goal` runs on `_GoalApp` with the controller answering one prepared verdict, so a submission
    that did not start the planner is checked against the card it leaves behind and the line the owner reads."""

    def test_a_card_submission_that_does_not_start_keeps_the_card_and_says_why(self):
        """Code-review finding 1: `start_goal` closed the card with a sent receipt for *every* non-error, non-`unsent`
        verdict, so `Outcome("stale")` — `planning.submission` returns it when the target changed between preparation
        and submission and starts no planner — produced a sent receipt, no open card and no planner. The stale
        verdict is now a refused card submission like the others.

        The readiness refusal (`unsent`) and the controller error are the same two paths the first repair proved in
        the retired whole-app test (acceptance finding on A6): they keep the card, write no receipt and say why on
        the main screen's own status line. Interpretation: the receipt is written only when the planner actually
        started (`ready`/whatever the form path does), so the card path treats `stale` and `unsent` alike; the line
        for `stale` is `PLAN_OUTDATED`, the wording the plan screen's own watch already shows."""
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
                self.assertEqual(app.screen.closed, [])               # no receipt: the card stays a decision
                self.assertEqual(sorted(app.screen.draft_cards), ["k1"])
                self.assertEqual(app.after, [])                       # nothing was submitted to the plan watch
                self.assertIn(expected, app.screen.app.chat_note)     # the refusal is on the main line
                self.assertFalse(app.starting)                        # another press is not swallowed
                if outcome is unsent:  # the readiness refusal names the failing check it lists
                    self.assertIn("отсоединён", app.screen.app.chat_note)

    def test_a_started_card_submission_writes_the_receipt(self):
        """The other half of the same callback (no regression): a verdict that *did* start the planner closes the
        card with `card.draft_sent`, clears the draft's provenance and hands the verdict to the plan watch — so the
        stale branch did not swallow the success case."""
        app = _GoalApp(Outcome("ready"))
        app.start_goal(GOAL_DRAFT, card_key="k1")
        self.assertEqual(app.calls, [(GOAL_DRAFT, NO_PLAN)])
        self.assertNotEqual(app.after, [])
        self.assertIsNone(app.goal_identity)
        self.assertEqual(len(app.screen.closed), 1)
        self.assertEqual(app.screen.closed[0][0], "k1")
        self.assertRegex(app.screen.closed[0][1], "^%s$" % receipt_pattern())


