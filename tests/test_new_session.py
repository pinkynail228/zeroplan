"""A8b: `/new` — a fresh architect session with a handoff turn and a warm-up turn, plus the rot signal.

One smoke test per acceptance criterion (C1 busy refusal and the command itself, C2 failed handoff, C3 warm-up, C4 rot
threshold) and the one invariant the feature can break (the plan and STATE stay on disk: the reset only forgets the
thread). Two tests drive the whole app (`/new` typed in the chat input; the bar's tail with the rot hint); the rest run
the chat without Textual against the scripted codex of tests/test_tui_chat.py.

Interpretations (the task leaves these open):
- The handoff and warm-up messages are stored under the `system` role (`chat.PROMPT_ROLE`, O4): the owner did not
  type them and the pane never shows that role; the architect's replies to them stay `architect` rows.
- O4: "the reset row is the first line, one short «новый диалог» line" — the stored reset row (`Новый диалог: …`) is
  that line; its text is not changed. Rows cut by the reset and the hidden prompts still count in `occurrence` and
  `ChatState.transcript` (the place among the store's role rows), so stamps and draft-card keys keep their meaning.
- O4: «nothing from before the reset» for the note and the live text: after the thread is forgotten the pane reloads
  and the note is the reset note alone; the handoff turn's streamed text is cleared.
- "the `chat_snapshot()` of that moment" is the snapshot taken when `/new` or Ctrl+R is pressed; the handoff turn and
  the warm-up turn both carry it, and the warm-up message holds it as JSON.
- The warm-up reads the STATE when it runs; an unreadable STATE counts as "(none)".
- The rot hint rides the bar's tail (C1 of 0.6.3 moved the header's fields there), after the model and the token
  count; a bar too narrow for the whole tail shows none of it.
- `chat.reset()` itself stays the bare "forget the thread" (tests/test_architect_home.py pins it); `new_session` is
  the path of `/new` and Ctrl+R.
"""

import time
import unittest

from terminal_planner import project_state
from terminal_planner.tui import chat as chat_module
from test_tui_chat import (ChatShell, Fixture, HAVE_TEXTUAL, OPENING, REPLY, TEXTUAL_REASON, THREAD)

NEW_THREAD = "0199aaaa-bbbb-cccc-dddd-eeeeffff0002"
NEW_REPLY = [{"type": "thread.started", "thread_id": NEW_THREAD}, {"type": "turn.started"},
             {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "Продолжаем."}},
             {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}]
STATE = "## Now\n\n## Next\nA8b\n\n## Open\n\n## Decisions\n"
SNAPSHOT = {"project": "demo", "branch": "main", "milestones": [{"id": "M7", "title": "t", "state": "running"}]}


class NewSessionTests(unittest.TestCase):
    def setUp(self):
        from test_terminal_planner import ProjectTest
        case = ProjectTest("run")
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.project, self.state, self.root = case.project, case.state, case.root
        self.fixture = Fixture(self.root, self.project)

    def chat(self, steps):
        self.fixture.script(steps)
        chat = chat_module.ArchitectChat(self.project, self.fixture.prepare(), binding=self.fixture.binding())
        self.addCleanup(chat.close)
        chat.start()
        self.wait(lambda: chat.state.phase != "preparing")
        self.assertEqual(chat.state.phase, "ready", chat.state.refusal)
        return chat

    @staticmethod
    def wait(condition, timeout=15.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not condition():
            time.sleep(0.01)
        return condition()

    def idle(self, chat):
        self.assertTrue(self.wait(lambda: not chat.busy), chat.state)
        time.sleep(0.05)

    def first_turn(self, chat):
        self.assertTrue(chat.send("начнём")[0])
        self.idle(chat)

    def roles(self):
        return [row["role"] for row in self.fixture.store().transcript()]

    def test_c2_c3_the_handoff_comes_first_then_the_reset_then_the_warm_up_in_a_new_thread(self):
        """C2/C3: three turns reach Codex in order — the owner's, the handoff (resumes the old thread, asks for
        `zplan_state_update`) and the warm-up (a new thread, holding the STATE and the snapshot); the thread id
        changes, the STATE file is untouched and the warm-up reply is in the chat like any reply."""
        project_state.write(self.project, STATE)
        chat = self.chat([{"lines": REPLY}, {"lines": REPLY}, {"lines": NEW_REPLY}])
        self.first_turn(chat)
        self.assertEqual(self.fixture.store().load()["thread_id"], THREAD)
        self.assertTrue(chat.new_session(SNAPSHOT)[0])
        self.idle(chat)
        calls = self.fixture.calls()
        self.assertEqual(len(calls), 3)
        self.assertIn("resume", calls[1]["argv"])
        self.assertIn(chat_module.HANDOFF_MESSAGE, calls[1]["stdin"])
        self.assertIn("zplan_state_update", chat_module.HANDOFF_MESSAGE)
        self.assertNotIn("resume", calls[2]["argv"])
        self.assertIn("A8b", calls[2]["stdin"])
        self.assertIn("M7", calls[2]["stdin"])
        self.assertEqual(self.roles()[2:], ["system", "architect", "reset", "system", "architect"])
        self.assertEqual(self.fixture.store().load()["thread_id"], NEW_THREAD)
        self.assertEqual(project_state.read(self.project), STATE)
        self.assertEqual(chat.state.entries[-1].text, "Продолжаем.")

    def test_c3_an_empty_state_reads_none(self):
        """C3: no STATE file -> the warm-up message says `(none)`."""
        chat = self.chat([{"lines": REPLY}])
        self.assertTrue(chat.new_session(SNAPSHOT)[0])
        self.idle(chat)
        self.assertIn("Project STATE:\n(none)", self.fixture.calls()[-1]["stdin"])

    def test_c2_a_failed_handoff_turn_does_not_block_the_reset_and_the_chat_notes_it(self):
        """C2: the handoff turn exits with an error and completes nothing: the thread id is forgotten anyway (the
        warm-up starts a new thread), nothing crashes, and the note says the handoff was not saved."""
        chat = self.chat([{"lines": REPLY}, {"lines": [], "exit": 1}, {"lines": NEW_REPLY}])
        self.first_turn(chat)
        self.assertTrue(chat.new_session(SNAPSHOT)[0])
        self.idle(chat)
        self.assertIn("reset", self.roles())
        self.assertEqual(self.fixture.store().load()["thread_id"], NEW_THREAD)
        self.assertNotIn("resume", self.fixture.calls()[-1]["argv"])
        self.assertIn(chat_module.HANDOFF_FAILED, chat.state.note)

    def test_c1_a_new_session_is_refused_while_a_turn_runs(self):
        """C1: with an owner turn running `new_session` answers today's busy line and resets nothing."""
        release = self.root / "release"
        chat = self.chat([{"lines": OPENING, "release": str(release), "release_timeout": 30}])
        self.assertTrue(chat.send("долго")[0])
        accepted, line = chat.new_session(SNAPSHOT)
        release.write_text("go")
        self.assertFalse(accepted)
        self.assertIn("The architect is answering: the new conversation starts after the turn.", line)
        self.idle(chat)
        self.assertNotIn("reset", self.roles())
        self.assertEqual(len(self.fixture.calls()), 1)

    def test_c4_the_rot_threshold_is_forty_turns_or_two_million_tokens(self):
        """C4: (40, 10) is long, (39, 10) is not; the token counter alone also trips it; no counters never do."""
        self.assertTrue(chat_module.session_long((40, 10)))
        self.assertFalse(chat_module.session_long((39, 10)))
        self.assertTrue(chat_module.session_long((1, 2_000_000)))
        self.assertFalse(chat_module.session_long((1, 1_999_999)))
        self.assertFalse(chat_module.session_long(None))

    def test_o4_c1_c4_the_pane_starts_at_the_last_reset_row_and_the_store_keeps_every_row(self):
        """O4 C1/C4: rows A, B, reset, C -> the pane shows reset, C (a start of the chat reads the same rows); with no
        reset row every row is shown, still capped at `history`; the store is untouched."""
        rows = [{"role": "owner", "text": "A"}, {"role": "architect", "text": "B"},
                {"role": "reset", "text": "Новый диалог: прежний thread id забыт."}, {"role": "owner", "text": "C"}]
        shown = chat_module.entries_of(rows)
        self.assertEqual([(entry.role, entry.occurrence) for entry in shown], [("reset", 2), ("owner", 3)])
        self.assertEqual(chat_module.transcript_size(rows), 4)
        self.assertEqual([entry.text for entry in chat_module.entries_of(rows[:2])], ["A", "B"])
        self.assertEqual(len(chat_module.entries_of(rows[:2] * 30, history=5)), 5)
        again = rows + [{"role": "reset", "text": "x"}]
        self.assertEqual([entry.role for entry in chat_module.entries_of(again)], ["reset"])
        store = self.fixture.store()
        for row in rows:
            store.append(row["role"], text=row["text"])
        chat = self.chat([])
        self.assertEqual([entry.text for entry in chat.state.entries][1:], ["C"])
        self.assertEqual(len(store.transcript()), 4)

    def test_o4_c2_old_stores_keep_the_prompts_as_events_rows_and_the_pane_hides_them(self):
        """O4 C2: an `events` row that begins with the handoff or the warm-up prompt is not shown; a real event row,
        a `system` row and the architect's replies are (the reply stays, the system row is no transcript role)."""
        warmup = chat_module.WARMUP_MESSAGE % ("STATE", "{}")
        rows = [{"role": "events", "text": chat_module.HANDOFF_MESSAGE}, {"role": "architect", "text": "сохранил"},
                {"role": "events", "text": warmup}, {"role": "architect", "text": "Мы тут"},
                {"role": "events", "text": "задача готова"}, {"role": "system", "text": warmup}]
        self.assertEqual([(entry.role, entry.text) for entry in chat_module.entries_of(rows)],
                         [("architect", "сохранил"), ("architect", "Мы тут"), ("events", "задача готова")])
        self.assertEqual([entry.occurrence for entry in chat_module.entries_of(rows)], [1, 3, 4])

    def test_o4_c3_after_new_nothing_from_before_the_reset_is_on_the_pane(self):
        """O4 C3: a chat with an owner turn, `/new` -> the pane holds the reset line and the warm-up reply only (no
        prompt, no earlier row), the handoff turn's streamed text is gone and the note is the reset note; the store
        keeps all seven rows. C5: the owner turn still counts (usage) and a following owner turn is shown after the
        reset."""
        project_state.write(self.project, STATE)
        chat = self.chat([{"lines": REPLY}, {"lines": REPLY}, {"lines": NEW_REPLY}, {"lines": NEW_REPLY}])
        self.first_turn(chat)
        self.assertTrue(chat.new_session(SNAPSHOT)[0])
        self.idle(chat)
        self.assertEqual([(entry.role, entry.text) for entry in chat.state.entries][1:], [("architect", "Продолжаем.")])
        self.assertEqual(chat.state.entries[0].role, "reset")
        self.assertEqual(len(chat.state.entries), 2)
        self.assertEqual(chat.state.live, "")
        self.assertIn("New conversation", chat.state.note)
        self.assertEqual(len(self.roles()), 7)
        self.assertEqual(chat.state.transcript, 5)
        self.assertEqual(chat.state.usage[0], 3)
        self.assertTrue(chat.send("дальше")[0])
        self.idle(chat)
        self.assertEqual([entry.role for entry in chat.state.entries], ["reset", "architect", "owner", "architect"])


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class NewSessionAppTests(ChatShell):
    def store_with(self, turns, tokens=10):
        store = self.fixture.store()
        store.save({"version": 1, "thread_id": None, "model": "gpt-6.1-sol", "created": "2026-01-01T00:00:00Z",
                    "turns": turns, "usage": {"input_tokens": tokens, "output_tokens": 0}})
        return store

    def head(self):
        from textual.widgets import Static
        return self.app.query_one("#keys", Static).render().plain

    async def test_c4_the_bar_shows_the_long_session_line_only_past_the_threshold(self):
        """C4: usage (40, 10) -> the bar's tail says the session is long and names /new; (39, 10) -> it does not."""
        for turns, shown in ((40, True), (39, False)):
            with self.subTest(turns=turns):
                async with self.shell(store=self.store_with(turns), size=(140, 40)) as pilot:
                    await self.loaded(pilot)
                    await self.chat_ready(pilot)
                    await self.until(pilot, lambda: self.app.chat.state.usage is not None)
                    await pilot.pause()
                    self.assertEqual("long session: /new" in self.head(), shown, self.head())

    async def test_c1_the_new_command_typed_in_the_chat_input_runs_the_session_path(self):
        """C1: `/new` typed in the input is not sent as a message; the handoff and the warm-up turns reach Codex and
        the reset row is in the transcript."""
        self.fixture.script([{"lines": REPLY}, {"lines": NEW_REPLY}])
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "/new")
            await self.until(pilot, lambda: self.app.chat.busy)
            await self.chat_done(pilot)
        roles = [row["role"] for row in self.fixture.store().transcript()]
        self.assertEqual(roles, ["system", "architect", "reset", "system", "architect"])
        self.assertIn(chat_module.HANDOFF_MESSAGE, self.fixture.calls()[0]["stdin"])


if __name__ == "__main__":
    unittest.main()
