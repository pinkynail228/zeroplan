"""S1 (0.6.3 V3): an `events` entry is one-line steps in the chat pane, and a decided card is one dim row.

`StepTests` is the invariant test of the slice (C1-C4) at 80x24 and 140x40: a minimal Textual app mounts the real
`ChatMessage` widgets the pane builds (`app.entry_rows`) and a closed `cards.Card` in a `#chat` scroll under the real
`zplan.tcss`, and the screen is read row by row. `TableTests` is the unit side of C2 (every status and state has a
word and a tone), C3 and C5 (the entry text the architect's store and the pane share is untouched).

Worker interpretations (the reviewers do not see the worker summary):
- A step's detail is separated from its words by two spaces (`chat.STEP_GAP`), exactly as the criteria spell it;
  the idle count and the head line of `feed.summary` are dropped from the pane, never from `ChatEntry.text`.
- The tone of a status the criteria do not name: `ok` ✓ for finished/integrated/awaiting_merge/proposed, `run` ▶ for
  the in-flight ones (planning, observing, preparing, stopping, resume_pending, submission_unknown), `bad` ! for
  every halted or failed one (observation_blocked, detached, run_failed, proposal_invalid, review_exhausted,
  needs_owner), `idle` · for waiting, ready and unknown.
- A reviewer verdict passes when it is `approve` (the criterion's word) or `approved`/`accepted` (what the feed
  itself calls an accepted verdict); every other verdict label is a remark.
- A closed card keeps the mark its receipt text starts with (`✓`, or `↻` for a retried failure); a text without one
  gets `✓` (`cards.done_row`).
"""

import re
import unittest

# imported first for its side effect: the offline wheelhouse joins `sys.path`, and the language is pinned (`ru` falls back to English).
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_lines

from terminal_planner import feed
from terminal_planner.authority import PLAN_STATUSES
from terminal_planner.runs import MILESTONE_STATES, STATUSES
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui import strings

try:  # the module needs Textual; without it the classes are declared and skipped (tests.test_toolchain)
    from pathlib import Path
    from textual.app import App
    from textual.containers import VerticalScroll
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import cards
    _HAVE_UI = True
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    App = VerticalScroll = ui = cards = None
    _HAVE_UI = False

HAVE = HAVE_TEXTUAL and _HAVE_UI
REASON = "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with the textual wheels is needed"
_AppBase = App if App is not None else object
LONG = "нет теста для граничного случая " * 12  # a verdict text far wider than the pane


def event(**fields):
    return {"wake": True, "kind": "state", "milestone": "M1", "plan_revision": 1, "attempt": 1, **fields}


def summary_text():
    """A real `feed.summary` of a batch with every step shape, the way the pane gets it from the store."""
    batch = [{"wake": True, "kind": "plan", "plan_revision": 1, "previous": "proposed", "status": "approved"},
             event(previous="submitted", state="running"),
             event(attempt=2, previous="running", state="failed"),
             event(previous="x", state="y"),
             {"wake": True, "kind": "verdict", "milestone": "M1", "task": "T1", "round": 2, "role": "reviewer",
              "verdict": "approve", "text": "ok"},
             {"wake": True, "kind": "verdict", "milestone": "M1", "task": "T1", "round": 3, "role": "reviewer",
              "verdict": "reject", "text": LONG},
             {"wake": False}]
    return feed.summary(batch, 4, {"rows": []})


class TableTests(unittest.TestCase):
    def test_c2_every_plan_status_and_run_state_has_a_word_and_a_tone(self):
        plans = set(PLAN_STATUSES) | set(feed.PLAN_WAKE)
        runs = set(STATUSES) | set(MILESTONE_STATES)
        self.assertEqual(plans - set(chat_module.PLAN_TONES), set())
        self.assertEqual(runs - set(chat_module.RUN_TONES), set())
        for status in plans:
            self.assertIn("step.plan." + status, strings.CATALOG)
        for state in runs:
            self.assertIn("step.run." + state, strings.CATALOG)
        self.assertEqual(chat_module.step_of("M1 attempt 2: running -> failed"),
                         ("bad", "M1 failed", "attempt 2"))
        self.assertEqual(chat_module.step_of("M1 attempt 1: x -> y"), ("idle", "M1: x -> y", ""))
        for done in ("finished", "integrated", "approved"):
            self.assertEqual(chat_module.RUN_TONES.get(done) or chat_module.PLAN_TONES[done], "ok")
        for failed in ("failed", "blocked", "stopped", "conflict"):
            self.assertEqual(chat_module.RUN_TONES[failed], "bad")
        self.assertEqual({chat_module.RUN_TONES[state] for state in ("running", "submitted")}, {"run"})

    def test_c3_c5_a_step_is_shown_and_the_entry_text_the_architect_shares_is_untouched(self):
        text = summary_text()
        entry = chat_module.entries_of([{"role": "events", "text": text}])[0]
        shown = [line for line in text.split("\n") if line not in chat_module.EVENT_HIDDEN
                 and not line.startswith(feed.STATUS_PREFIX)]
        self.assertEqual(entry.text, "\n".join(shown))  # C5: head, idle count and rest count stay in the text
        blocks = chat_module.entry_blocks(entry)
        kinds = [kind for kind, _ in blocks]
        self.assertEqual(kinds, ["step_ok", "step_run", "step_bad", "step_idle", "step_ok", "step_bad", "step_more"])
        self.assertEqual((blocks[0][1], blocks[-1][1]), ("Plan r1 approved", "… 4 more"))
        self.assertEqual(chat_module.step_of("M1 T1 round 2 reviewer: approve — ok"),
                         ("ok", "M1 check passed", "round 2 · ok"))
        self.assertEqual(chat_module.step_of("M1 T1 round 2 reviewer: reject — нет теста"),
                         ("bad", "M1 check remarks", "round 2 · нет теста"))


class ProducerConsumerTests(unittest.TestCase):
    """T2/U2 + U3: the pane reads what `feed.summary` really writes, and still reads the 0.7.x Russian rows.

    Interpretations (the reviewers do not see the worker summary):
    - U2's pair is tested with the producer's real output, line by line: every line of a `feed.summary` text
      (head, wake lines of the three kinds, idle count, rest count, status or the unavailable line, the closing
      instruction) is either one step of the table below or hidden from the pane; the rows of the text are never typed
      into the test by hand.
    - U3's 0.7.x row is the Russian text `feed.summary` wrote before 0.8.0, spelled out literally (the legacy forms
      are input, so this fixture is Russian on purpose): it must give the same steps as the English text.
    """

    STEPS = [("ok", "Plan r1 approved", ""), ("run", "M1 running", "attempt 1"), ("bad", "M1 failed", "attempt 2"),
             ("ok", "M1 check passed", "round 2 · ok"), ("more", "… 4 more", "")]

    def batch(self):
        return [{"wake": True, "kind": "plan", "plan_revision": 1, "previous": "proposed", "status": "approved"},
                event(previous="submitted", state="running"),
                event(attempt=2, previous="running", state="failed"),
                {"wake": True, "kind": "verdict", "milestone": "M1", "task": "T1", "round": 2, "role": "reviewer",
                 "verdict": "approve", "text": "ok"},
                {"wake": False}]

    def test_u2_every_line_feed_summary_writes_is_a_step_or_hidden(self):
        for status in ({"rows": []}, {}):  # a status line, then the line saying the status is unavailable
            with self.subTest(status=status):
                text = feed.summary(self.batch(), 4, status)
                entry = chat_module.entries_of([{"role": "events", "text": text}])[0]
                self.assertEqual([step for step in map(chat_module.step_of, entry.text.split("\n")) if step], self.STEPS)
                self.assertEqual([kind for kind, _ in chat_module.entry_blocks(entry)],
                                 ["step_ok", "step_run", "step_bad", "step_ok", "step_more"])
                for line in text.split("\n"):
                    hidden = line in chat_module.EVENT_HIDDEN or line.startswith(feed.STATUS_PREFIX)
                    if hidden:
                        self.assertNotIn(line, entry.text.split("\n"))
                    else:
                        self.assertIn(line, entry.text.split("\n"))
        self.assertTrue(text.split("\n")[-2] in chat_module.EVENT_HIDDEN)  # the unavailable line is hidden too
        self.assertIsNone(re.search("[\u0400-\u04ff]", text), text)

    def test_u3_a_0_7_x_events_row_is_hidden_and_parsed_as_before(self):
        legacy = "\n".join(["События с прошлого хода:", "план r1: proposed -> approved",
                            "M1 попытка 1: submitted -> running", "M1 попытка 2: running -> failed",
                            "M1 T1 раунд 2 reviewer: approve — ok",
                            "Промежуточных состояний без действия: 1.", "… и ещё 4 событий.",
                            'Статус: {"rows":[]}', "статус недоступен: вызови zplan_status",
                            "Оцени их по снимку и действуй по своим правилам; если решать нечего, ответь коротко."])
        entry = chat_module.entries_of([{"role": "events", "text": legacy}])[0]
        self.assertEqual([step for step in map(chat_module.step_of, entry.text.split("\n")) if step], self.STEPS)
        self.assertEqual(entry.text.split("\n")[0], "События с прошлого хода:")  # C5: the stored text is untouched
        for hidden in ('Статус: {"rows":[]}', "статус недоступен: вызови zplan_status",
                       "Оцени их по снимку и действуй по своим правилам; если решать нечего, ответь коротко."):
            self.assertNotIn(hidden, entry.text)
        self.assertEqual(len(chat_module.entry_blocks(entry)), 5)

    def test_u3_the_prompts_new_sends_are_recognised_in_both_forms(self):
        """U3 (`PROMPT_STARTS`): a 0.6.x `events` row holding the old Russian handoff or warm-up prompt, and one holding
        the English prompt `/new` sends now, are both prompt rows; an ordinary events row and an owner row are not."""
        warmup = chat_module.WARMUP_MESSAGE % ("STATE", "screen")
        legacy_warmup = chat_module.LEGACY_WARMUP_MESSAGE % ("STATE", "экран")
        for text in (chat_module.HANDOFF_MESSAGE, warmup, chat_module.LEGACY_HANDOFF_MESSAGE, legacy_warmup):
            with self.subTest(text[:20]):
                self.assertTrue(chat_module.is_prompt_row({"role": "events", "text": text}))
                self.assertFalse(chat_module.is_prompt_row({"role": "owner", "text": text}))
        self.assertFalse(chat_module.is_prompt_row({"role": "events", "text": feed.summary([], 0)}))


@unittest.skipUnless(HAVE, REASON)
class StepApp(_AppBase):
    """The pane's own widgets and stylesheet: the events entry as `ChatMessage`, then a closed card in its place."""

    CSS_PATH = str(Path(ui.__file__).with_name("zplan.tcss")) if ui is not None else None

    def __init__(self, entries, spec):
        super().__init__()
        self.entries, self.spec = entries, spec

    def compose(self):
        with VerticalScroll(id="chat"):
            for _, role, shown in ui.entry_rows(self.entries):
                yield ui.ChatMessage(shown, role)
            yield cards.Card(self.spec)


@unittest.skipUnless(HAVE, REASON)
class StepTests(unittest.IsolatedAsyncioTestCase):
    async def test_c1_c4_events_are_one_line_steps_and_a_closed_card_is_one_dim_row(self):
        entries = chat_module.entries_of([{"role": "events", "text": summary_text()}])
        receipt = strings.text("card.draft_sent", time="10:02")
        spec = cards.closed(cards.draft_card("d", "10:01"), receipt)
        for size in ((80, 24), (140, 40)):
            with self.subTest(size=size):
                app = StepApp(entries, spec)
                async with app.run_test(size=size) as pilot:
                    await pilot.pause()
                    lines = [line for line in screen_lines(app) if line.strip()]
                    # C1: no head line, no idle count, one row per step; the rest count is a dim `… N more`
                    self.assertEqual(lines[0], "✓ Plan r1 approved")
                    self.assertEqual(lines[1], "▶ M1 running  attempt 1")
                    self.assertEqual(lines[2], "! M1 failed  attempt 2")  # C2
                    self.assertEqual(lines[3], "· M1: x -> y")
                    self.assertEqual(lines[4], "✓ M1 check passed  round 2 · ok")  # C3
                    self.assertTrue(lines[5].startswith("! M1 check remarks  round 3 · нет теста"), lines[5])
                    self.assertTrue(lines[5].endswith("…") and len(lines[5]) <= size[0], lines[5])  # clipped
                    self.assertEqual(lines[6], "  … 4 more")
                    # C4: the closed card is one borderless row in its place, the receipt as the card has it
                    self.assertEqual(lines[7], receipt)
                    self.assertEqual(len(lines), 8, lines)
                    card = app.query_one(cards.Card)
                    self.assertEqual(card.region.height, 1)
                    self.assertNotIn("Goal draft", "".join(lines))
                    self.assertFalse(list(card.query("Button")))

    def test_the_step_row_glyph_colour_and_the_dim_detail(self):
        for kind, mark, style in (("step_ok", "✓", "green"), ("step_run", "▶", "cyan"), ("step_bad", "!", "red"),
                                  ("step_idle", "·", "dim")):
            row = ui.step_row(kind, "M1 слова" + chat_module.STEP_GAP + "деталь")
            self.assertEqual(row.plain, mark + " M1 слова  деталь")
            self.assertEqual(str(row.spans[0].style), style)
            self.assertEqual(str(row.spans[-1].style), "dim")
            self.assertEqual(row.plain[:2], mark + " ")  # the 2-cell gutter


if __name__ == "__main__":
    unittest.main()
