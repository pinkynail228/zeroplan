"""The card half of the main screen (S1 of 0.5.2, the card split of `app.py`): `CardHost`, the methods of
`MainScreen` that show, close and route the decision cards and that read the data the merge, question and failure
cards need. A pure move: `class MainScreen(CardHost, Screen)` keeps every method under its own name.

Imports run one way (app -> card_host -> card_kinds); nothing here imports `app` at import time."""

from textual.app import SuspendNotSupported
from textual.containers import VerticalScroll

from ..authority import Blocked
from ..cli import summary
from . import cards, chat as chat_module, slash, strings
from .card_kinds import (CARD_ROUTES, CARD_SOURCES, EMPTY_ANSWER, FAILED_CARD_RETRY, FIX_KEY, MOVED,
                         NOT_STARTED_BELOW, QUESTION_CARD_CHROME, QUESTION_CARD_INSET, QUESTION_CHOICES,
                         QUESTION_LINES, STATUS_SHARE, DraftCardRequested, QuestionCard, QuestionNoteScreen,
                         card_clock, card_kind, draft_card_of, draft_reply_time, draft_tab_text,
                         failed_card_refusal, failed_plan_card_key, failed_plan_view, merge_same_attempt,
                         merge_stage, merge_tasks_counts, question_body, question_button_rows, question_card_key,
                         token_run_id)

CARD_REVEAL_TRIES = 4  # a just-mounted card is scrolled to once it has layout; up to this many retries


class CardHost:
    def on_card_chosen(self, event):
        """A card button was pressed (i3a): the button's command line runs through the same dispatcher as a typed
        `/` line, carrying the card's own key (`card.spec.key`), so the action knows which card it decides.

        The line is read by `slash`, the registry the typed path reads too (the buttons are built from the same
        command names); the dispatcher then gets the resolved command for a name `slash` knows, and the name as
        typed when it does not: the card-only commands (`/retry`, `/details`) are deliberately outside `slash`
        (they are never typable), and `run_command` refuses a name no action knows (`note.not_now`) exactly like a
        typed line — so a card never injects a command the app does not act on. A line that is no command line at
        all is ignored."""
        parsed = slash.parse(event.command)
        if parsed is None:
            return
        self.run_command(parsed.command.name if parsed.command is not None else parsed.name,
                         parsed.argument, event.card.spec.key)

    def show_card(self, spec, after=None):
        """Show one decision card inline in the conversation: mount `spec` in `#chat` after the newest entry at the
        moment it is shown, and replace the card that carries the same key *in its own place*.

        A card of another key is *mounted beside* this one: unrelated open cards are decisions still waiting for the
        owner and are left where they are (acceptance finding 2), and now every card — open or closed — keeps its
        place in the history as its own row block, so two cards can no longer clip each other and a closed receipt
        no longer leaves when the next card shows. The card of the same key is replaced by the new one, which is
        what `close_card` does; the card is built from `spec` and its key is remembered in `card_widgets`/
        `card_specs`, so `close_card`/`drop_card` name exactly this card; the key joins `cards_seen` and is never
        shown again after it has left.

        Only a card that was *not* in the history yet is scrolled into view (`reveal_card`); one that replaces its
        own key in place leaves the viewport where the owner had it — a live render that refreshes an existing card
        (`render_card_sources` re-reading a source whose `card_clock()` crossed a minute) is an update, not a new
        entry, and R-4 keeps the position.

        `after` is the widget a *new* card mounts right behind instead of the end of `#chat` (the goal-draft card:
        right after the reply that carries it, so a card another event mounted first stays below it); a widget that
        is no longer a child of `#chat` is ignored and the card mounts at the end."""
        scroll = self.query_one("#chat", VerticalScroll)
        # i3d: the owner-question spec is shown through `QuestionCard`, a `cards.Card` whose own action area wraps
        # its buttons (the full «send the answer draft» beside the three quick answers needs more cells than
        # the 120x40 half-width card holds); every other kind keeps the shared one-row layout of `cards.Card`.
        card = QuestionCard(spec) if card_kind(spec.key) == "question" else cards.Card(spec)
        old = self.card_widgets.get(spec.key)
        if old is not None and spec.buttons:
            card.choice = min(old.choice, len(spec.buttons) - 1)  # D2: a refreshed card keeps the owner's selection
        self.card_specs[spec.key] = spec  # D2: kept before the slot fires, so the slot's sync sees the new spec
        self.card_widgets[spec.key] = card
        self.cards_seen.add(spec.key)
        if old is not None:
            # The same key is replaced in place, never drawn twice: the new card is mounted right after the old one
            # and the old one taken off (the removal is pruned asynchronously, so both would otherwise be in the
            # DOM at once). A closed receipt therefore keeps its slot for good. The replacement changes the card's
            # own rows only, never the conversation around it, so the view is left exactly where the owner had it —
            # a live update while scrolled keeps the position (R-4), and a source whose spec changed only in its
            # own `HH:MM` (`card_clock` crossed the minute) must not pull the conversation back to it.
            scroll.mount(card, after=old)
            scroll.remove_children([old])
        else:
            if after is not None and after in scroll.children:
                scroll.mount(card, after=after)
            else:
                scroll.mount(card)
            # A card that was not there before is a new block in the history: bring it into view (`reveal_card`).
            self.call_after_refresh(lambda: self.reveal_card(card))
        if spec.done is None:
            self.show_chat()  # I7: an open card is a decision; in narrow mode the chat pane that holds it is shown

    def reveal_card(self, card, attempt=0):
        """Bring the card just mounted into view the way the scroll's own paging would: `#chat` aligns the card's own
        first row, which the clamp below turns into the conversation's end whenever the card fits the view.

        `scroll_to_widget(top=True)` asks for the card's top row at the viewport's top, but the scroll clamps the
        move to its own end: a card that fits cannot reach the top without overshooting (`card_top > max_scroll_y`
        exactly then), so a fitting card lands with the view at the conversation's end — R-4's rule, and A1's
        "the view is at the bottom" — while a card *taller* than the view keeps its own top: a small terminal, or
        the owner-question card still carrying its plain `QUESTION_LINES` fallback size because its source ran before
        the pane was laid out. Without that, such a card is scrolled out of sight above the view, its title included
        (the 60x20 needs_owner card of `test_tui_polish` reads the title). `scroll_chat_end` stays as it is: it is
        R-4's rule for a new *entry*, which is not a card.

        A card that is mounted but has no rows yet is asked for again over the next refreshes (`attempt`, bounded by
        `CARD_REVEAL_TRIES`): `scroll_to_widget` needs the card's laid-out region, and scrolling a zero-size widget
        is a no-op — the after-refresh callback can fire while the card's own compose and the pane's geometry are
        still settling, which would leave the view unmoved (acceptance A1: the plan card's buttons below the view at
        80x24)."""
        if self.closing:
            return
        if not card.region.height and attempt < CARD_REVEAL_TRIES:
            self.call_after_refresh(self.reveal_card, card, attempt + 1)
            return
        chat = self.query_one("#chat", VerticalScroll)
        if card.region.height <= chat.scrollable_content_region.height:
            chat.scroll_end(animate=False)  # deferred to the next refresh, when max_scroll_y counts the new card
        else:
            chat.scroll_to_widget(card, top=True, animate=False)

    def close_card(self, key, done_text):
        """Close the card `key`: the card stays where it was and shows only `done_text`, with no buttons.

        A closed card is no decision any more: it no longer holds the `draft` state (a typed `/plan` is refused as
        out of state then, and the palette offers the state's own commands). The receipt stays in the history where
        the card stood; its key stays in `cards_seen`, so it is never shown again."""
        spec = self.card_specs.get(key)
        if spec is None:
            return
        self.draft_cards.pop(key, None)
        self.show_card(cards.closed(spec, done_text))

    def drop_card(self, key):
        """Drop the card `key` — the owner said no: the card leaves the slot at once, and its key is remembered as
        seen so no later refresh of the same history brings it back."""
        self.cards_seen.add(key)
        self.unmount_card(key)

    def unmount_card(self, key):
        """Take one card off the conversation and forget it everywhere: its widget, its spec and, for an open draft
        card, the draft it stood for. The key's place in `cards_seen` is the caller's business (`drop_card` marks
        it; a card a newer one replaces has been shown already)."""
        card = self.card_widgets.pop(key, None)
        self.card_specs.pop(key, None)
        self.draft_cards.pop(key, None)
        if card is not None:
            self.query_one("#chat", VerticalScroll).remove_children([card])

    def keyed_card(self):
        """D2: the widget of the newest open card that has choices — the card the keys (↑↓ and Enter on the empty
        chat input) answer — or None."""
        for key in reversed(list(self.card_specs)):
            spec, card = self.card_specs[key], self.card_widgets.get(key)
            if spec.done is None and spec.buttons and card is not None:
                return card
        return None

    def sync_card_keys(self):
        """D2: mark the newest open card as the keyed one (its selected choice is drawn in reverse, every other card
        draws none) and set the input's placeholder: the card's keys while a card is open and the input is empty,
        `chat.placeholder` otherwise. Asked whenever a card comes or goes and the input changes."""
        if not self.ready or self.closing:
            return
        keyed = self.keyed_card()
        for card in self.card_widgets.values():
            card.set_keyed(card is keyed)
        field = self.query_one("#input")
        field.placeholder = strings.text("chat.placeholder_card" if keyed is not None and not field.value
                                         else "chat.placeholder")

    def newest_card_for(self, command):
        """The key of the newest open card whose kind routes the shared `command` (`CARD_ROUTES`), or None."""
        return next((key for key, spec in reversed(list(self.card_specs.items()))
                     if spec.done is None and (command, card_kind(key)) in CARD_ROUTES), None)

    def render_card_sources(self):
        """Show the cards `CARD_SOURCES` return for the current state and take off the open cards of a source's kind
        it no longer returns. A dropped or closed card is not brought back, and an unchanged card is not remounted."""
        for kind, source in CARD_SOURCES.items():
            wanted = {}
            for spec in source(self):
                wanted[spec.key] = spec
            for key in [k for k, spec in self.card_specs.items()
                        if card_kind(k) == kind and spec.done is None and k not in wanted]:
                self.unmount_card(key)
            for key, spec in wanted.items():
                shown = self.card_specs.get(key)
                if shown is None and key in self.cards_seen:
                    continue
                if shown is None or (shown.done is None and shown != spec):
                    self.show_card(spec)

    def draft_card_open(self):
        """i3a: whether the slot holds an open goal-draft card — the `draft` fact `screen_slash_state` reads. An open
        card the owner has not decided on keeps the state `draft`; a closed (done) card is not a decision any more,
        so it does not."""
        return bool(self.draft_cards)

    def open_draft_card(self):
        """`(key, draft)` of the open draft card of the slot — the newest card of that kind (an unrelated open card
        never takes a draft card off, so more than one may be open), or None when no draft card is open."""
        if not self.draft_cards:
            return None
        key = list(self.draft_cards)[-1]
        return key, self.draft_cards[key]

    def draft_card_ref(self, key):
        """The `(key, draft)` a card command names: the open draft card `key` (a button carries its own card's key),
        or — for a typed line, whose `key` is None — the open draft card of that kind. None when the key names no
        open draft card: a closed or dropped card, or a command typed with no draft card at all."""
        if key is None:
            return self.open_draft_card()
        draft = self.draft_cards.get(key)
        return None if draft is None else (key, draft)

    def plan_identity_now(self):
        """The plan identity the screen's own snapshot names, in the shape a goal draft carries it (i3a): "no plan",
        or `[revision, state]` with the revision and the state the snapshot already holds (`snapshot.plan_state`).

        This is the identity `chat.stale_reason` compares a draft against before the planner is called at all — the
        same check the controller repeats on the worker against the live plan, so a draft that went stale in between
        is refused there too."""
        snapshot = self.app.snapshot
        if snapshot is None or snapshot.version is None:
            return chat_module.NO_PLAN
        return [snapshot.version, snapshot.plan_state]

    def action_plan(self, argument, key):
        """`/plan` — the draft card's «yes» or the command typed in the chat.

        A goal typed after the command (`/plan <text>`, no card button) is the goal: it starts planning through
        `start_goal`, an open draft card or not. Otherwise the draft is the one the card names (a typed line names
        the open draft card): a draft whose plan moved on since the reply (`chat.stale_reason` against the identity
        this screen's snapshot names) is refused on the status line and the card stays; nothing is started then.
        Otherwise the draft's own identity travels with the goal and the planner starts through `start_goal`; on
        success the card becomes the sent receipt, on a failure the card stays. With no card and no text the unsent
        revision is sent (`send_unsent_plan`); a button of a card that is gone says `note.not_now`. Like a typed
        command, `/plan` ends the status note first (a refusal below sets its own)."""
        self.app.chat_note = ""
        if argument and key is None:
            self.app.goal_identity = None
            self.app.start_goal(argument)
            return
        ref = self.draft_card_ref(key)
        if ref is None:
            if key is None:
                self.app.send_unsent_plan()
            else:
                self.status_note(strings.text("note.not_now", name="/plan"))
            return
        card, draft = ref
        reason = chat_module.stale_reason(draft.identity, self.plan_identity_now())
        if reason:
            self.status_note("%s: %s" % (chat_module.OUTDATED, reason))
            return
        self.app.goal_identity = draft.identity
        self.app.start_goal(draft.text, card_key=card)

    def action_decline(self, argument, key):
        """`/decline` — the draft card's «no» or the command typed in the chat: the draft is not the plan.

        The card leaves the pane and its key is not shown again, however often the history is refreshed; nothing is
        written and no plan state changes (the draft itself stays in the transcript, copyable)."""
        ref = self.draft_card_ref(key)
        if ref is None:
            self.status_note(strings.text("note.not_now", name="/decline"))
            return
        self.drop_card(ref[0])

    def refresh_draft_card(self):
        """i3a: put the newest actionable goal draft of the retained history on screen as a draft card, once.

        The draft is `chat.newest_goal_draft` (the one choice of the newest draft) and its key is the stable key of the
        reply that carries it, with that reply's own occurrence in the transcript (`draft_card_of`); a key that was
        shown or declined is skipped, so a refresh, a poll or a restart of the screen never brings a card back for
        the same reply — while an identical reply stored later is its own occurrence and its own card. Showing the
        card also opens the «Goal draft» canvas tab beside «Plan» with the draft's whole text, as the approved look
        does (`canvas.draft_intro` + the text); the tab closes with esc like a file tab. Read from the chat state
        alone, never from what the pane happens to show.

        The decision is the *key*, never the draft value (acceptance finding 1 and code finding 1): a draft already
        open under a different key is a decision of its own, so a repeated identical reply whose key was never shown
        still gets its card. Only a key in `cards_seen` — shown or declined — is skipped; the key is built before
        that check, so every refresh reads the reply's own occurrence (a store read under an open card, the price of
        telling two equal drafts apart)."""
        self.retire_stale_draft_cards()
        chat = self.app.chat
        if chat is None:
            return
        found = draft_card_of(chat)
        if found is None:
            return
        key, draft = found
        if key in self.cards_seen:
            return
        # A draft the plan moved past (a plan built from it, a newer revision) is history, not a decision: no card on
        # mount or refresh. Undecided until the first snapshot names the plan, so the key stays unseen until then.
        if self.app.snapshot is None or chat_module.stale_reason(draft.identity, self.plan_identity_now()):
            return
        self.cards_seen.add(key)  # the key is decided now: a refresh before the message is handled posts nothing more
        self.draft_cards[key] = draft
        self.post_message(DraftCardRequested(key, draft, draft_reply_time(chat, draft)))

    def retire_stale_draft_cards(self):
        """RC4: close every open draft card whose draft the plan has moved past — a plan built from it and approved, a
        newer revision. The card is a decision about a draft that is history now, and an open card keeps the `draft`
        state, so `/run` would be refused while the panel says «Next: /run».

        Same check as the creation (`chat.stale_reason` against `plan_identity_now`), but only against a snapshot
        that names a plan: before the first snapshot, or while no plan exists, the identity has not moved (a refused
        `/plan` writes nothing), so the card stays. The card is unmounted, its key stays in `cards_seen` and its
        «Goal draft» canvas tab closes as esc closes it."""
        snapshot = self.app.snapshot
        if not self.draft_cards or snapshot is None or snapshot.version is None:
            return
        current = self.plan_identity_now()
        for key, draft in list(self.draft_cards.items()):
            if not chat_module.stale_reason(draft.identity, current):
                continue
            self.cards_seen.add(key)
            self.unmount_card(key)
            for tab_id in [tab for tab, opened in self.view_paths.items() if opened == key and tab in self.view_tabs]:
                self.close_view_tab(tab_id)

    def draft_reply_widget(self, draft):
        """The `#chat` entry widget of the newest reply that carries `draft` (the one `draft_card_of` keys the card
        on), or None when that entry is not mounted (yet) or this screen tracks no entries."""
        chat = self.app.chat
        widgets = self.chat_entry_widgets
        entries = getattr(self, "chat_entry_entries", ())
        if chat is None or len(entries) != len(widgets):
            return None
        return next((widgets[index] for index in range(len(entries) - 1, -1, -1) if draft in entries[index].drafts),
                    None)

    def on_draft_card_requested(self, event):
        """The `draft` state is already in place (`draft_cards`, set before the message was posted); this mounts the
        card and opens the «Goal draft» canvas tab beside «Plan», once — the slot replaces a card of the same
        key, and `cards_seen` keeps a key from being posted again. A card retired before this message was handled
        (`retire_stale_draft_cards`) is not mounted at all."""
        if event.key not in self.draft_cards:
            return
        # The tab first: in narrow mode opening it shows the canvas, and the card then brings the chat back.
        self.add_view_tab(strings.text("canvas.draft_tab"), draft_tab_text(event.draft), key=event.key)
        self.show_card(cards.draft_card(event.key, at=event.at), after=self.draft_reply_widget(event.draft))
        self.call_after_refresh(self.render_chat)

    # The failure cards (i3e2) ---------------------------------------------------------------------
    def failed_cards(self):
        """The failure cards' own per-screen state (i3e2), read and created lazily: `views` is the `EndView` of
        every stage key whose fetch returned (with the card's own `at`), `at` the `HH:MM` of every other card key,
        and `fetching` the stage keys already asked for, so a refresh never asks twice."""
        state = getattr(self, "_failed_cards", None)
        if state is None:
            state = self._failed_cards = {"views": {}, "at": {}, "fetching": set()}
        return state

    def failed_card_view(self, key, row):
        """The `EndView` of one failed stage's card, cached per key (i3e2).

        The card's text is the view's body and its buttons act on the view's own attempt, so the view is fetched
        once per key through `controller.open_run` — the end view `[o]` shows — off the event loop, and kept under
        the card's key. A key not fetched yet starts exactly one fetch and returns None (the card appears when the
        answer arrives and the screen repaints); a key whose fetch is in flight is never asked for again."""
        state = self.failed_cards()
        if key in state["views"]:
            return state["views"][key][0]
        if key not in state["fetching"]:
            state["fetching"].add(key)
            self.app.controller.open_run(row.id, self.app.deliver(
                lambda outcome, error: self.failed_card_fetched(key, outcome, error)))
        return None

    def failed_card_at(self, key):
        """The card's own `HH:MM` — its border subtitle — read once per key (i3e2): neither the end view nor the
        plan view carries a time of its own, and a refresh has to paint the same card again instead of remounting
        it every tick."""
        state = self.failed_cards()
        if key not in state["at"]:
            state["at"][key] = card_clock()
        return state["at"][key]

    def failed_card_fetched(self, key, outcome, error):
        """The worker's answer to one card's `open_run` (i3e2): the end view is cached under its key and the next
        render paints the card. A refusal — `error`, or an end view the export permit did not admit (the owner is
        quitting) — leaves the key unfetched, so a later refresh may ask again; nothing else is shown then."""
        self.failed_cards()["fetching"].discard(key)
        if error or outcome is None or outcome.kind != "end" or outcome.data is None:
            return
        self.failed_cards()["views"][key] = (outcome.data, self.failed_card_at(key))
        self.app.changed()

    def failed_card_ref(self, key):
        """What a failure card's key names on this screen (i3e2): `("stage", (end, at))` for a failed stage whose
        end view is already fetched, `("plan", view)` for a failed planning run, None when the key names no card
        here — an unfetched stage card has no view to act on yet, a closed one is no decision, and another
        screen's key is none of this screen's."""
        state = self.failed_cards()
        if key in state["views"]:
            return "stage", state["views"][key]
        snapshot = self.app.snapshot
        if key is not None and key == failed_plan_card_key(snapshot) and failed_plan_view(snapshot) is not None:
            return "plan", snapshot.plan
        return None

    def retry_failed_card(self, key):
        """`/retry` of a failure card (i3e2) — the card's «try again»: the retry the card's own view offers,
        run modal-less.

        A failed stage runs the first offered of `resume`, `new_attempt`, `check` (`FAILED_CARD_RETRY`): the very
        service call RunScreen makes for that action, without a form — a new attempt takes an empty note, exactly
        as the modal-less path asks — and the attempt it starts is observed exactly as the modal's own action
        observes it (`watch_run`), so a resumed attempt is followed by this screen too and not left `running`. A
        started attempt closes the card with the `card.error_retried` receipt; a refusal (an error, a readiness
        block, an attempt that moved) starts nothing, says so on the status line and leaves the card where it is,
        like every other card refusal. A failed planning run restarts planning (`retry_failed_plan`); a key with no
        card behind it, and a view offering none of the three actions, do nothing — no such card carries a retry
        button."""
        ref = self.failed_card_ref(key)
        if ref is None:
            self.status_note(strings.text("note.not_now", name="/retry"))
            return
        kind, data = ref
        if kind == "plan":
            self.retry_failed_plan(key)
            return
        end = data[0]
        name = next((name for name in FAILED_CARD_RETRY if name in end.names), None)
        if name is None:
            return

        def settled(outcome, error):
            if error:
                self.status_note("Not done: " + error)
            elif outcome.kind in ("attempt", "active"):
                # the same observation the modal's own action starts: the new attempt gets its own, empty buffer
                # and its own identity (C4), never the shown attempt's buffer or the finished attempt's run id
                line = "%s: %s." % (end.milestone, "new attempt started" if outcome.kind == "attempt"
                                    else "in progress")
                start = self.app.fresh_attempt if outcome.kind == "attempt" else self.app.attach_attempt
                start(end.milestone, token_run_id(outcome), line)
                self.close_card(key, strings.text("card.error_retried", time=card_clock()))
            else:
                self.status_note(failed_card_refusal(outcome))

        if name == "resume":
            self.app.controller.resume_run(end.token, self.app.deliver(settled))
        elif name == "new_attempt":
            self.app.controller.new_attempt(end.token, "", self.app.deliver(settled))
        else:
            self.app.controller.check_run(end.token, self.app.deliver(settled))

    def retry_failed_plan(self, key):
        """The planning half of a failure card's `/retry` (i3e2): the existing restart-planning path —
        `controller.restart_plan`, what [g] runs on the plan screen of a failed revision — sends a new revision of
        the same goal to the planner. A restart that started closes the card with the `card.error_retried` receipt;
        a readiness refusal or a revision that moved starts nothing, says so on the status line and keeps the
        card."""
        view = failed_plan_view(self.app.snapshot)
        if view is None:
            self.status_note(strings.text("note.not_now", name="/retry"))
            return

        def settled(outcome, error):
            if error:
                self.status_note("Not done: " + error)
                return
            self.app.plan_lines = ()  # the failed revision's own outcome lines are history once the planner runs
            self.app.after_submission(outcome)
            if outcome.kind == "ready":
                self.close_card(key, strings.text("card.error_retried", time=card_clock()))
            else:
                self.status_note(failed_card_refusal(outcome))
        self.app.controller.restart_plan(self.app.deliver(settled))

    def show_failed_card(self, key):
        """`/details` of a failure card (i3e2) — the card's «details»: what the card summarizes. A failed stage
        opens its end-of-run screen (the card's own cached end view, the same one `[o]` builds), a failed planning
        run opens the plan screen. A key with no card behind it is refused like any other card command."""
        ref = self.failed_card_ref(key)
        if ref is None:
            self.status_note(strings.text("note.not_now", name="/details"))
            return
        kind, data = ref
        if kind == "plan":
            self.app.action_open_plan()
            return
        self.app.show_end(data[0])

    # The merge card (i3c) --------------------------------------------------------------------------
    def merge_counts(self, key, milestone):
        """The `(done, total)` a merge card's own text carries, read from the attempt's EndView tasks line.

        The UI thread never reads an attempt itself and a card source must answer synchronously, so the counts are
        fetched *once per key* through `controller.open_run` (off the event loop, exactly as [o] reads the same
        view) and cached for the card's whole life. Until the answer arrives — and when the view carries no tasks
        line, or the read failed — the cached value stays None and the card is the bare one
        (`card.merge_text_bare`)."""
        if key not in self.merge_view:
            self.merge_view[key] = None  # pending, and this is the one read this key ever asks for
            self.app.controller.open_run(milestone, self.app.deliver(
                lambda outcome, error: self.merge_counts_arrived(key, outcome, error)))
        return self.merge_view[key]

    def merge_counts_arrived(self, key, outcome, error):
        """The counts read of one merge card: what the attempt's own EndView body says, or None (the card keeps the
        bare text). A key the slot no longer holds is left alone — the card it belonged to is gone."""
        if key not in self.merge_view:
            return
        counts = None
        if not error and outcome is not None and outcome.data is not None:
            counts = merge_tasks_counts(outcome.data)
        self.merge_view[key] = counts
        self.render_state()

    def merge_card_at(self, key):
        """The `HH:MM` a merge card's `at` carries: the clock read when the card was first drawn. A stage-done card
        has no stored stamp of its own (a goal draft carries its reply's), so this is the moment the decision
        appeared, read once per key so a refresh of a history that already holds the card never moves it."""
        at = self.merge_times.get(key)
        if at is None:
            at = self.merge_times[key] = card_clock()
        return at

    def merge_card_ref(self, key):
        """The `(key, milestone)` a `/merge` names: the open merge card `key` (a button carries its own card's key),
        or — for a typed line, whose key is None — the newest open merge card. None when nothing merge-like is open
        (a closed receipt is no decision, and a card of another kind never answers this command)."""
        if key is None:
            key = next((k for k, spec in reversed(list(self.card_specs.items()))
                        if spec.done is None and card_kind(k) == "merge"), None)
        if key is None or card_kind(key) != "merge" or key not in self.card_specs:
            return None
        return key, merge_stage(key)

    def action_merge(self, argument, key):
        """`/merge` — the merge card's «merge» or the command typed in the chat: merge the attempt the card names,
        with no modal in between (i3c).

        The card's key names its stage; the attempt is that row's token, read now, so a row that moved off
        `awaiting_merge` since the card was drawn starts nothing (the same re-check a modal makes with its own
        token). An accepted attempt whose export has not run yet (a cut export, a reopen: the row is `awaiting_merge`
        while `delivery` is still `none`/`exporting`) is exported by this very click — the owner's own arrival,
        exactly as [o] reads the view — and the merge then carries the token that export produced, so one click
        still suffices. The pending guard comes first: a second `/merge` while the first is in flight is refused on
        the status line, and a card already decided is no card at all. Typed with no merge card open the command
        keeps the run screen's own path (`[o]`'s end view holds merge and diff)."""
        ref = self.merge_card_ref(key)
        if ref is None:
            self.app.action_open_milestone()
            return
        card_key, milestone = ref
        if argument == "later":
            self.merge_later(card_key, milestone)
            return
        row = self.app.snapshot.row(milestone) if self.app.snapshot is not None else None
        if row is None or row.state != "awaiting_merge" or row.token is None:
            self.status_note(strings.text("note.not_now", name="/merge"))
            return
        if self.app.guard_pending():
            return
        self.app.begin_pending("merge", milestone)
        clicked = row.token  # the attempt this card names, carried through the export below
        if row.token.delivery == "awaiting_merge":
            self.merge_run(card_key, milestone, clicked)
        else:
            # The accepted attempt's export has not run (a cut export; a reopen): complete it first, exactly as [o]
            # reads the same view, and merge the token that view produces -- the unexported one the engine refuses.
            # The view is the *latest* attempt's, though: a click whose attempt changed under it is refused, never
            # merged (the export's own token must be the clicked attempt's, `merge_exported`).
            self.app.controller.open_run(milestone, self.app.deliver(
                lambda outcome, error: self.merge_exported(card_key, milestone, clicked, outcome, error)))

    def confirm_commit(self, key):
        """«yes» on the commit card (`/approve`): commit the proposal's files under the terminal suspend, as the login
        runs (hooks and signing may ask the owner), through `Controller.commit_files`. The card closes as a receipt
        of what happened: the commit, or the refusal with the fix; a terminal that cannot be suspended commits
        nothing and leaves the card open."""
        proposal_id = key.split(":", 1)[1]
        app = self.app
        try:
            with app.suspend():
                result = app.controller.commit_files(proposal_id)
        except SuspendNotSupported:
            self.status_note(strings.text("note.commit_no_suspend"))
            return
        except (Blocked, OSError, ValueError) as error:
            self.close_card(key, strings.text("card.commit_failed", time=card_clock(), reason=summary(error)))
        except KeyboardInterrupt:  # outside the commit itself (that one comes back as a Blocked); like the login's
            self.close_card(key, strings.text("card.commit_failed", time=card_clock(), reason="Commit interrupted."))
        else:
            self.close_card(key, strings.text("card.commit_done", time=card_clock(), lines="\n".join(result.lines())))
        app.request_refresh()
        app.changed()

    def decline_commit(self, key):
        """«no» on the commit card (`/decline`): nothing is run; the card closes as a receipt."""
        self.app.controller.decline_commit(key.split(":", 1)[1])
        self.close_card(key, strings.text("card.commit_declined", time=card_clock()))

    def merge_later(self, key, milestone):
        """«merge later» (`/merge later`): the owner decided not to merge now. The card closes as a receipt and the
        branch stays as it is; nothing is merged or written."""
        self.merge_overlap.pop(key, None)
        self.close_card(key, strings.text("card.merge_later_done", stage=milestone, time=card_clock()))

    def merge_exported(self, key, milestone, clicked, outcome, error):
        """The verdict of the export the card's first click owed (i3c): the view's counts are the ones the card was
        waiting for and land in its cache, and the merge goes on with the token that same view carries -- the
        exported attempt's, which the engine accepts.

        The export reads the *latest* attempt, so its view is trusted only when its token still names the click's own
        attempt (`merge_same_attempt`: revision, attempt and run). A view of another attempt -- a revision or a run
        that moved under the click -- is never merged: the changed state is the merge's own verdict on the status
        line and the card stays an open decision. A non-`end` outcome (the latest attempt still runs, no run at all,
        a refused export) is the same failure settlement, never unpacked as a view (`Token` has no `.token`)."""
        end = (outcome.data if error is None and outcome is not None and outcome.kind == "end"
               and outcome.data is not None else None)
        if end is None:
            self.merge_settled(key, milestone, None, error or "The result is not exported yet.")
            return
        if not merge_same_attempt(clicked, end.token):
            self.merge_settled(key, milestone, None, MOVED)
            return
        self.merge_view[key] = merge_tasks_counts(end)
        self.render_state()
        self.merge_run(key, milestone, end.token)

    def merge_run(self, key, milestone, token):
        """The card's merge itself, off the event loop; the engine's verdict comes back to `merge_settled`."""
        self.app.controller.merge(token, self.app.deliver(
            lambda outcome, error: self.merge_settled(key, milestone, outcome, error)))

    def action_merge_diff(self, argument, key):
        """`/diff` from a merge card's «see the changes»: select the card's own stage first, so the canvas and
        the selection agree on what was inspected, then the existing `open_diff_tab()`. The repaint the pane keys'
        own `action_select` asks for follows the assignment, so the panel shows the new selection at once (a command
        does not repaint by itself).

        An accepted attempt whose export has not run yet (`delivery` still `none`/`exporting`) is exported first --
        `runs.diff` needs the exported result -- exactly as the card's own «merge» does, and the view's counts land
        in the card's cache; the diff tab then opens on the exported attempt. A typed line (no card key) keeps its
        own meaning, the diff of the row selected in the panel, and exports nothing."""
        if key is not None and card_kind(key) == "merge":
            stage = merge_stage(key)
            self.app.selected = stage
            self.app.changed()
            row = self.app.snapshot.row(self.app.selected) if self.app.snapshot is not None else None
            if (row is not None and row.state == "awaiting_merge" and row.token is not None
                    and row.token.delivery != "awaiting_merge"):
                self.app.controller.open_run(row.id, self.app.deliver(
                    lambda outcome, error: self.merge_diff_exported(key, stage, outcome, error)))
                return
        self.open_diff_tab()

    def merge_diff_exported(self, key, stage, outcome, error):
        """The export «see the changes» owed: its view's counts reach the card and the row is refreshed to its
        exported state, then the existing diff tab opens (the exported attempt resolves the row's token without the
        exact check, so the stale delivery it still carries is no obstacle).

        The export runs off the event loop while the owner may move the panel's selection, so the card's own stage is
        carried through the callback and re-selected right before `open_diff_tab`: the tab is the diff of the stage
        the card named, never of whatever row happens to be selected when the export answers."""
        end = (outcome.data if error is None and outcome is not None and outcome.kind == "end"
               and outcome.data is not None else None)
        if end is not None:
            self.merge_view[key] = merge_tasks_counts(end)
            self.render_state()
        self.app.selected = stage
        self.app.changed()
        self.app.request_refresh()
        self.open_diff_tab()

    def merge_settled(self, key, milestone, outcome, error):
        """The verdict of the card's merge, with no modal to put it on (i3c): the pending line clears, the outcome
        goes on the status line and the card either becomes its receipt or stays an open decision.

        Success is the engine's own `integrated` verdict: its own line («Merged: M1 → main.») is published on the
        status line -- a refusal that preceded it is not left there -- and only then does the card close, as
        `card.merge_done` («✓ M1 merged into main HH:MM»). Every other verdict — a refusal, the merge's own conflict, a
        stale attempt — leaves the card where it was: a conflict moves the row out of `awaiting_merge`, so the
        source drops the card on the next render. The refresh that follows shows the row as it is now."""
        self.app.clear_pending()
        if error:
            self.status_note("Not done: " + error)
        elif outcome is not None and outcome.kind == "integrated":
            receipt = strings.text("card.merge_done", stage=milestone, time=card_clock())
            self.status_note(outcome.lines[0] if outcome.lines else receipt)
            self.close_card(key, receipt)
        else:
            lines = outcome.lines if outcome is not None else ()
            if outcome is not None and outcome.kind == "overlap":  # D4b: lines = the refusal, then the files in the way
                self.merge_overlap[key] = tuple(lines[1:])
                self.render_state()
            if lines:
                self.status_note(lines[0])
        self.app.request_refresh()

    # The owner-question card (i3d) ---------------------------------------------------------------

    def question_cache(self):
        """The per-screen i3d question material, built lazily: `ends` maps a card key to the `(EndView, at)` of the
        attempt its question was fetched for, `pending` holds the keys a fetch is in flight for, and `failed` the
        keys whose fetch did not build a question card. The cache belongs to the screen instance, so a refresh, a
        poll or a fresh screen starts from the store again; `pending`/`failed` keep the source from fetching one key
        twice or looping on a key it cannot build."""
        cache = getattr(self, "_question_cache", None)
        if cache is None:
            cache = self._question_cache = {"ends": {}, "pending": set(), "failed": set()}
        return cache

    def question_card_specs(self):
        """`CARD_SOURCES["question"]` (i3d): one `question_card` per `needs_owner` row whose end view is cached.

        The key is the row's own attempt of the current plan revision (`question:r<version>:<milestone>:<attempt>`),
        so a new revision or a new attempt is a new card, and the per-key cache is per revision. A row
        whose key has no end view yet starts one `controller.open_run` fetch — never inside a render, the fetch runs
        on the controller worker and delivers back through `app.deliver` — and the next render, with the end view
        cached, shows the card. A key that left the rows (the attempt moved on) drops its cache entries."""
        cache = self.question_cache()
        snapshot = self.app.snapshot
        current = {}
        for row in (snapshot.rows if snapshot is not None else ()):
            if row.state == "needs_owner" and row.token is not None:
                current[question_card_key(row.id, row.token.attempt, snapshot.version)] = row
        for gone in [k for k in cache["ends"] if k not in current]:
            cache["ends"].pop(gone, None)
        for gone in [k for k in cache["failed"] if k not in current]:
            cache["failed"].discard(gone)
        room = self.question_text_room()
        specs = []
        for key, row in current.items():
            entry = cache["ends"].get(key)
            if entry is not None:
                specs.append(self.question_card_spec(key, row, entry[0], entry[1], room))
            elif key not in cache["failed"] and key not in cache["pending"]:
                cache["pending"].add(key)
                self.app.controller.open_run(row.id, self.app.deliver(
                    lambda outcome, error, key=key: self.question_fetched(key, outcome, error)))
        return specs

    def question_text_room(self):
        """The rows and cells the question card's text may take, so the card's own actions are never clipped.

        The card, inline in the chat's scroll (`#chat`, the whole chat pane's width), shares its height budget (40%
        of the chat pane, the `#status` cap) with its title border, the gap over its buttons, the button row and its
        hint; the text gets what is left. The inner width is the card's own width minus its margin, border and
        padding. The sizes are read from the laid-out pane, so a resize (which re-renders the source) re-sizes the
        text and the card; a pane not laid out yet reports zeros, and the plain `QUESTION_LINES` cap with no
        wrapping is used then."""
        pane = self.query_one("#chat-pane")
        height, width = pane.size.height, pane.size.width
        if height <= 0 or width <= 0:
            return QUESTION_LINES, 0
        return max(int(height * STATUS_SHARE) - QUESTION_CARD_CHROME, 1), max(width - QUESTION_CARD_INSET, 1)

    def question_card_spec(self, key, row, end, at, room=None):
        """The `CardSpec` of one owner question: the title names the milestone, the text is the end view's own
        question body (`question_body`) sized to `room` — the rows and cells the card slot can show, so the
        question and the buttons below it stay visible at 80x24 and after a resize — and the buttons are the draft
        one — first, and only while an answer draft of that milestone exists — then «simplify», «split»,
        «skip» (the draft runs `/approve draft`, the three choices `/approve simplify`, `/approve split`,
        `/approve skip`).

        The draft button keeps its full `card.answer_draft` wording («send the answer draft`) at every size;
        the card wraps its buttons (`question_button_rows`), so at the 120x40 half-width chat pane the draft label
        and the three quick answers share two rows rather than a label being shortened or dropped (A3). Every
        button row past the first costs the text one row of the card's own chrome (which `question_text_room`
        budgets as one), so the card still fits the chat pane's own 40% (`STATUS_SHARE`) row budget. `room` None (a
        unit call with no laid-out pane) keeps the full label and the plain line cap."""
        buttons = []
        if self.answer_draft_of(end.milestone) is not None:
            buttons.append((strings.text("card.answer_draft"), "/approve draft"))
        buttons += [(strings.text("card.question_simplify"), "/approve simplify"),
                    (strings.text("card.question_split"), "/approve split"),
                    (strings.text("card.question_skip"), "/approve skip")]
        rows, width = room if room is not None else (QUESTION_LINES, 0)
        extra = max(len(question_button_rows(buttons, width)) - 1, 0)
        return cards.question_card(key, at, row.id, question_body(end, max(rows - extra, 1), width), buttons)

    def question_fetched(self, key, outcome, error):
        """The verdict of the off-event-loop end-view fetch: a `needs_owner` end is cached with the time the card is
        drawn (`card_clock`, read once, so the spec stays stable across renders); anything else — an error, another
        state, no end view — marks the key so the source does not fetch it in a loop. Wakes the screen either way,
        so the next render shows the card or leaves the key alone."""
        cache = self.question_cache()
        cache["pending"].discard(key)
        if (error is None and outcome is not None and outcome.kind == "end" and outcome.data is not None
                and outcome.data.state == "needs_owner"):
            cache["ends"][key] = (outcome.data, card_clock())
        else:
            cache["failed"].add(key)
        self.app.changed()

    def answer_draft_of(self, milestone):
        """The newest actionable answer draft of `milestone` in the chat history, or None — the source the card's
        own «send the answer draft» button appears from. The choice is the same `chat.newest_answer_draft` the
        `[t]` key reads, but scoped to the card's milestone instead of the selected row."""
        chat = self.app.chat
        if chat is None:
            return None
        return chat_module.newest_answer_draft(chat.state.entries, milestone)

    def question_end(self, key):
        """The `EndView` the *open* question card `key` stands for, or None: a closed or dropped card, or a key the
        card slot does not hold, is no decision any more, so a command naming it acts on nothing.

        The slot's own spec is the check (never the fetch cache alone): a card closed with `card.answer_sent` keeps
        its cache entry but is not an open card, so a late command against it is refused like a command with no card
        at all."""
        spec = self.card_specs.get(key)
        if spec is None or spec.done is not None:
            return None
        entry = self.question_cache()["ends"].get(key)
        return None if entry is None else entry[0]

    def approve_question(self, argument, key):
        """`/approve` for the owner-question card (i3d). A choice — the card's «simplify»/«split»/«skip»
        buttons, or `/approve simplify|split|skip` — answers the attempt with the choice's own catalog text and
        watches the new attempt; `draft` (the card's first button) sends the newest answer draft of the card's
        milestone through `controller.answer_draft`; a bare `/approve` sends that draft when there is one and opens
        the answer note otherwise; any other argument is refused. Every path that does not start an attempt keeps
        the card open and says why on the status line; a started attempt closes it with `card.answer_sent`."""
        end = self.question_end(key)
        if end is None:
            self.status_note(strings.text("note.not_now", name="/approve"))
        elif argument in QUESTION_CHOICES:
            self.answer_question(key, end, strings.text("card.question_" + argument))
        elif argument == "draft":
            self.send_question_draft(key, end)
        elif argument == "":
            if self.answer_draft_of(end.milestone) is not None:
                self.send_question_draft(key, end)
            else:
                self.open_question_note(key, end)
        else:
            self.status_note(strings.text("note.not_now", name="/approve"))

    def decline_question(self, argument, key):
        """`/decline` for the owner-question card (i3d): the owner answers in words instead of a quick choice, so it
        opens the card's own answer note (`NoteScreen(..., answer=True, enter=True)`); esc keeps the card, and a
        sent answer goes through `controller.answer`."""
        end = self.question_end(key)
        if end is None:
            self.status_note(strings.text("note.not_now", name="/decline"))
        else:
            self.open_question_note(key, end)

    def open_question_note(self, key, end):
        """The answer note of the owner-question card: its text is sent with `controller.answer` on the attempt's
        own token; esc (`None`) and an empty send keep the card open (the empty one says so on the status line)."""
        def sent(text):
            if text is None:
                return
            if not text:
                self.status_note(EMPTY_ANSWER)
                return
            self.answer_question(key, end, text)
        # `QuestionNoteScreen`: the frozen `NoteScreen(..., answer=True, enter=True)` hook with enter bound at
        # priority (see the class); the card's answer note submits on enter, esc keeps the card.
        self.app.push_screen(QuestionNoteScreen("Answer to the question %s" % end.milestone, answer=True, enter=True), sent)

    def answer_question(self, key, end, text):
        """Answer the attempt the card stands for: `controller.answer` with the card's own text, then `watch_run`
        the new attempt. The card closes with the sent receipt only once an attempt actually started; a refusal (a
        readiness block, a stale token, a controller error) keeps it open and shows the reason on the status line."""
        def answered(outcome, error):
            self.question_answered(key, end, outcome, error)
        self.app.controller.answer(end.token, text, self.app.deliver(answered))

    def send_question_draft(self, key, end):
        """Send the newest answer draft of the card's milestone through `controller.answer_draft` (the card's first
        button, or a bare `/approve`), then `watch_run` the new attempt. The draft's own identity, milestone and
        text travel, never a token of the view the screen shows; a refusal — `draft.stale` above all, when the
        attempt moved on since the draft was written — keeps the card open and shows the reason on the status
        line."""
        draft = self.answer_draft_of(end.milestone)
        if draft is None:
            self.status_note(strings.text("note.not_now", name="/approve"))
            return

        def answered(outcome, error):
            self.question_answered(key, end, outcome, error)
        self.app.controller.answer_draft(draft.identity, draft.milestone, draft.text, self.app.deliver(answered))

    def question_answered(self, key, end, outcome, error):
        """The verdict of one owner answer on the question card. A started attempt closes the card with
        `card.answer_sent` and is watched, exactly as the end-of-run screen's answer is; every other verdict keeps
        the card an open decision and says why on the status line — an error (the `draft.stale` refusal among them),
        a readiness block (the failing checks), or a token that went stale (`MOVED` and the service's reason)."""
        if error:
            self.status_note(error)
        elif outcome is not None and outcome.kind == "attempt":
            self.close_card(key, strings.text("card.answer_sent", time=card_clock()))
            self.app.fresh_attempt(end.milestone, token_run_id(outcome))  # its own buffer and identity (C4)
        elif outcome is not None and outcome.kind == "blocked":
            self.status_note("\n".join([NOT_STARTED_BELOW] + [
                "! " + FIX_KEY.sub("", summary(c.line)) for c in outcome.checks]))
        elif outcome is not None and outcome.kind == "stale":
            self.status_note("%s %s" % (MOVED, outcome.lines[0] if outcome.lines else ""))
        else:
            self.status_note("%s: %s" % (end.milestone, MOVED))
