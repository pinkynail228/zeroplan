"""C1 (0.6.3 V1): the chat pane shows the conversation; its chrome moves to the status area and the bar.

One smoke test per criterion and the invariants L-2/L-4 keep for the thinking row: C1-C3 through the real shell (one
test, at 80x24 and at 140x40), C2 and C5 as pure functions, C4 next to the commands (`tests/test_tui_commands.py`,
`test_p2a_...`).

Interpretations (the task leaves these open):
- The spinner `◐◓◑◒` steps once per second of the turn and shows `◑` at the 7th second (the task's example), so the
  frame is `SPIN[(seconds - 1) % 4]`: the first second shows the last frame, the clock never skips one.
- The bar's tail is `model/effort · N ток` joined to the rest with the bar's own ` · `, `chat.rot` after it; it is
  appended last and only when the whole of it fits beside the bar that is left, so a bar that cannot hold it is
  exactly the bar without it (the other fields are cut as they were).
- The chat's own lines (`chat_note`, `chat_outcome`, `chat_refusal`, and the line of a chat that is not ready) come
  after the activity row; a chat refusal is shown while its turn runs too (`chat_outcome` has no idle condition any
  more), which is where the old state row carried it.
- A run note keeps its own row after the activity row, also while a turn runs.
"""

import re
import unittest

from terminal_planner.tui import chat as chat_module
from test_tui_chat import ChatShell, HAVE_TEXTUAL, OPENING, TEXTUAL_REASON, chat_band

if HAVE_TEXTUAL:
    from terminal_planner.tui import app as app_module
    from terminal_planner.tui.activity import GAP, bar_text

KEYS = (("←→", "bar.key_tabs"), ("/", "bar.key_commands"), ("ctrl+q", "bar.key_quit"))
META = "gpt-6.1-sol/high · 15.6k tok"
THINKING = re.compile(r"[◐◓◑◒] The architect is thinking… \d:\d\d · читаю план")


def running(elapsed, live=""):
    return chat_module.ChatState(phase="ready", running=True, elapsed=elapsed, live=live)


def shell(state):
    return type("Shell", (), {"chat": type("Chat", (), {"state": state})()})()


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ThinkingRowTests(unittest.TestCase):
    def test_c5_the_live_line_is_split_on_lf_escaped_per_line_and_one_row(self):
        """C5/L-2/L-4: `a TAB b ESC[31m c LF d` is the one row `a\\tbc d` (TAB escaped, the complete sequence out);
        a string sequence left open at the end of one line is not completed by the next line; a live line of one
        control character shows its escape; the row costs no line break, whatever the model streamed."""
        row = app_module.thinking_row(running(7.0, "a\tb\x1b[31mc\nd"))
        self.assertEqual(row, "◑ The architect is thinking… 0:07 · a\\tbc d")
        row = app_module.thinking_row(running(0.0, "left\x1b]secret\n\x07right"))
        self.assertTrue(row.endswith("· left\\x1b]secret \\x07right"), row)  # `secret` survives: no OSC completed
        self.assertEqual(app_module.thinking_row(running(61.0, "\t"))[-4:], "· \\t")
        self.assertEqual(app_module.thinking_row(running(61.0, "\x85"))[-6:], "· \\x85")
        self.assertEqual(app_module.thinking_row(running(61.0, "  A \n\n  B  ")), "◐ The architect is thinking… 1:01 · A B")
        self.assertEqual(app_module.thinking_row(running(5.0)), "◐ The architect is thinking… 0:05")  # no live line yet
        for live in ("x\ny", "\x1b]\n", "\r\n\t"):
            self.assertNotIn("\n", app_module.thinking_row(running(3.0, live)))

    def test_c3_the_spinner_steps_each_second_and_only_a_running_turn_has_a_row(self):
        frames = [app_module.thinking_row(running(float(second)))[0] for second in range(9)]
        self.assertEqual(len(set(frames[:4])), 4)
        self.assertEqual(frames[:4], frames[4:8])       # the four frames repeat
        self.assertEqual(frames[7], "◑")
        self.assertEqual(app_module.thinking_row(running(7.9))[0], "◑")  # steps by whole seconds
        self.assertEqual(app_module.chat_thinking(shell(running(7.0, "x"))).split()[0], "◑")
        for state in (chat_module.ChatState(phase="ready"), chat_module.ChatState(phase="blocked", running=True),
                      chat_module.ChatState(phase="preparing")):
            self.assertEqual(app_module.chat_thinking(shell(state)), "")
        self.assertIsNone(app_module.chat_state(shell(running(7.0))))   # a running turn is no "not ready" line
        self.assertEqual(app_module.chat_state(shell(chat_module.ChatState(phase="preparing"))),
                         chat_module.PREPARING)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class BarTailTests(unittest.TestCase):
    def bar(self, width, meta, project="demo", job=None):
        return bar_text(project, "main", job, "M1", 5, KEYS, width, meta=meta)

    def test_c2_the_tail_ends_the_bar_dim_and_goes_whole_before_any_other_field_is_cut(self):
        wide = self.bar(100, META)
        self.assertTrue(wide.plain.endswith(GAP + META), wide.plain)
        tail = wide.plain.index(META)
        self.assertTrue(all("dim" in str(span.style) for span in wide.spans if span.start >= tail))
        for project in ("demo", "a-very-long-project-name-" * 3):
            for job in (None, "running"):
                for width in range(20, 140):
                    with self.subTest(project=project[:8], job=job, width=width):
                        text = self.bar(width, META, project, job)
                        bare = self.bar(width, "", project, job)
                        self.assertLessEqual(text.cell_len, width)
                        # either the whole tail ends the bar, or the bar is exactly the one without a tail
                        self.assertTrue(text.plain.endswith(GAP + META) or text.plain == bare.plain, text.plain)
        self.assertEqual(self.bar(60, META).plain, self.bar(60, "").plain)   # no room: no tail, no half of one
        rot = META + GAP + "сессия длинная: /new"
        self.assertTrue(self.bar(140, rot).plain.endswith(rot))

    def test_c2_a_short_tail_never_stays_while_the_turn_tail_or_the_continue_hint_is_cut(self):
        """A short `model/effort` string must not outlive a higher-priority field: with a job and a turn together,
        and near the `bar.continue` threshold, the bar either holds every field and the tail or the bar without it."""
        short = "gpt-5/high · 3 ток"
        for job in ("waiting", "running", "planning"):
            for turn in (None, 7):
                for width in range(20, 160):
                    with self.subTest(job=job, turn=turn, width=width):
                        text = bar_text("demo", "main", job, "M1", 5, KEYS, width, turn=turn, meta=short)
                        bare = bar_text("demo", "main", job, "M1", 5, KEYS, width, turn=turn)
                        full = bar_text("demo", "main", job, "M1", 5, KEYS, 400, turn=turn)
                        whole = full.plain.replace(" · " + short, "")
                        self.assertLessEqual(text.cell_len, width)
                        if short in text.plain:
                            self.assertEqual(text.plain, whole + GAP + short)
                        else:
                            self.assertEqual(text.plain, bare.plain)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatChromeShellTests(ChatShell):
    HEADER = chat_module.ChatHeader(home="/srv/CODEX_HOME_marker", provider="openai", model="gpt-6.1-sol",
                                    effort="high")

    def seeded(self):
        store = self.fixture.store()
        store.save({"version": 1, "thread_id": None, "model": "gpt-6.1-sol", "created": "2026-01-01T00:00:00Z",
                    "turns": 3, "usage": {"input_tokens": 15600, "output_tokens": 0}})
        store.append("owner", text="привет")
        store.append("architect", text="Тут.")
        return store

    async def drive(self, size):
        """The invariant at one size: no header rows in the chat pane and the short conversation on the
        status area (C1); the bar's tail only where it fits whole (C2); the status area directly above the prompt
        box with the planner's newest line alone, wrapped in full, then the chat's own line wrapped in full, which a running turn's
        thinking row replaces (N1: one status line)."""
        note = ("Нужен вход в Codex на этом компьютере: выполните zplan login и повторите; сообщение сохранено и "
                "пишется заново не будет. [код: architect.login]")
        self.fixture.script([{"lines": OPENING + [{"type": "item.completed",
                                                   "item": {"id": "i1", "type": "agent_message",
                                                            "text": "читаю план"}}], "hang": 30}])
        store = self.seeded()
        header = self.HEADER
        async with self.shell(size=size, chat_prepare=lambda passed=None: (
                self.fixture.architect(store=store), header)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: self.app.chat.state.usage is not None
                             and len(self.app.chat.state.entries) == 2)
            await pilot.pause()
            app = self.app
            # C1
            band = chat_band(app)
            for word in ("provider", "CODEX_HOME", "turns"):
                self.assertNotIn(word, band)
            self.assertEqual(len(app.query("#chat-head")), 0)
            scroll, status = app.query_one("#chat"), app.query_one("#status")
            prompt = app.query_one("#prompt-box")
            messages = list(app.query("#chat .msg"))
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[-1].region.bottom, scroll.content_region.bottom)  # on the bottom ...
            self.assertEqual(status.region.y, scroll.region.bottom)                      # ... on the status
            self.assertLessEqual(status.region.bottom, prompt.region.y)                  # ... above the input
            # C2
            bar = app.query_one("#keys").render().plain
            if size[0] >= 140:
                self.assertTrue(bar.endswith(META), bar)
            else:
                self.assertNotIn("tok", bar)
            # C3: the planner's newest line alone
            app.progress = ["a", "b"]
            app.screen.render_state()
            await pilot.pause()
            self.assertEqual(status.content.plain, "b")
            long_line = "Планировщик: этап M2 разбирает требования, сверяет критерии и готовит черновик " * 3
            app.progress = [long_line]
            app.screen.render_state()
            await pilot.pause()
            rows = status.content.plain.split("\n")
            self.assertGreater(len(rows), 1)                              # a long line wraps ...
            self.assertEqual(" ".join(" ".join(rows).split()), long_line.strip())   # ... in full
            app.progress = []
            # C3: the chat's own line, wrapped in full; N1: a running turn is the one row, the note waits
            app.chat_note = note
            app.screen.render_state()
            await pilot.pause()
            rows = status.content.plain.split("\n")
            self.assertEqual(" ".join(" ".join(rows).split()), note)
            self.assertGreater(len(rows), 1)
            await self.say(pilot, "вопрос")
            await self.until(pilot, lambda: app.chat.state.live == "читаю план", 10.0)
            app.screen.render_state()
            await pilot.pause()
            rows = status.content.plain.split("\n")
            self.assertRegex(rows[0], THINKING)
            self.assertEqual(len(rows), 1)                                 # N1: one status line, the note waits
            self.assertLessEqual(status.region.bottom, prompt.region.y)
            self.assertEqual(status.region.y, scroll.region.bottom)
            self.assertEqual(app.query_one("#palette").display, False)

    async def test_c1_c2_c3_at_80x24(self):
        await self.drive((80, 24))

    async def test_c1_c2_c3_at_140x40(self):
        await self.drive((140, 40))


if __name__ == "__main__":
    unittest.main()
