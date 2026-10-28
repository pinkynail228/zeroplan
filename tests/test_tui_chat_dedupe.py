"""U-1 dedupe: an architect reply shows each draft body once, in the chat pane (u3b-chat-dedupe).

A reply that carries a draft is stored twice over: its fenced source text, and the draft records
`architect.parse_drafts` recognised in it. The pane now shows the body once: at each source span
`architect.draft_spans` finds, the opener, the body and the closing fence collapse into the record's labelled
draft line, the matched record is not appended again below the reply, and everything the parser did not record
stays the raw text it was stored as. `entries_of` counts the pane's `ENTRY_TEXT` bound over the transformed
payload — the narrative and the trimmed draft bodies, never the generated labels or the leading `…` — and a cut
section keeps its suffix and its label. The store, the transcript, the records and [c]/[t] are untouched.

Interpretations this change had to fix (the worker's own summary never reaches the reviewers, so they are recorded
here, next to the tests that cover them):

- The collapsed line is the trailing line's own spelling: `↳ <kind> draft: <text>` (`goal draft`, `answer draft`) (0.6.3 V2 dropped the
  `ответ N ·` name and the `арх ·` prefix, and with them `reply_names`). `entries_of` keeps the body structured on
  the entry (`ChatEntry.sections`), so the pane can set the line apart from its narrative. The label is generated,
  so the `ENTRY_TEXT` payload still counts only narrative and bodies.
- The pane matches an *eligible* span by content alone — `(kind, milestone or "", trimmed body)` — never by
  identity, `actionable` or the current snapshot, and it adds no rules of its own: eligibility is
  `architect.draft_body`, the very rule `parse_drafts` reads for its own body bound (empty means nothing;
  `MAX_DRAFT_TEXT` bounds the raw body). A span the parser's body rule rejects is ruled out *before* any record is
  consumed, so it can neither collapse nor take the record a later valid span owns — the reviewed collision, with
  the parser's own output as the fixture (EligibilityTests). A hand-written record the parser could never store
  for a span it would never have recorded (an unknown milestone) is outside the contract.
- The payload is counted over the line breaks, the narrative and the trimmed draft bodies, so the pane's bound is
  the same `ENTRY_TEXT` characters the entry shows as its own text. A matched section the cut drops whole is not
  appended again, and its `Draft` stays in `entry.drafts`, so [c]/[t] still act on a body that is out of view.

A-8 evidence: the base is f300ea5 (this change's parent) with only this test file added (scratch commit df4d5cb),
run as `devtools/mac-test.sh test_tui_chat_dedupe` (log: ~/zs-pause/merge-u3b-chat-dedupe/a8-base.log). Result:
26 tests, 24 fail and 2 pass (FAILED failures=120, errors=48 across subtests). The base keeps every fenced block raw
in `entry.text` and appends each record again below the reply, and its clip is `"…" + text[-ENTRY_TEXT:]`:

- `DedupeTests.test_a1_one_draft_is_shown_once_at_the_block_position` — the `entry_lines(entry)` assertion (now `entry_blocks`):
  `["арх: Начало\\n```zplan-goal\\nЦель\\n```\\nКонец", "арх · черновик цели: Цель"]` (the body twice).
- `DedupeTests.test_a1_five_drafts_each_collapse_at_their_own_position`, `test_a3_*` (both), `test_a4_*` (both
  paddings), `RestartTests.test_a6_the_store_rows_give_the_same_display` — the line-list assertion: the raw
  opener, body and fence stand where the collapsed line is expected.
- `RawSpanTests` (all six, including `test_a2_a_mismatched_milestone_never_takes_the_record`) — the `shown(...)`
  assertion: the M1 block stays raw with a trailing `арх · черновик ответа M1: X` line after the reply.
- `EligibilityTests.test_an_oversized_body_never_takes_the_valid_blocks_record` — the
  `entry.text.endswith("separator\\n" + label + "A")` assertion (`False is not true`): the base text ends with the
  valid block's raw closing fence. `test_a_raw_body_at_the_bound_keeps_both_blocks_collapsed` — the
  `entry.text.split` assertion: both blocks raw.
- `ClipTests` (all four) and `SourceNameTests` (all three) — the text/line assertions: the old clip cuts a raw
  block (the label and its `ответ N ·` name stand only on the trailing line).
- `ScanTests` (both) — the pane-line assertion: the raw block lines reach the scan.
- `GeneratorTests.test_a7_the_constructed_replies_render_like_the_oracle` — oracle text mismatches in cases with a
  block; cases without one stop with `AttributeError: 'ChatEntry' object has no attribute 'matched'` (48 subtests).
- Passing on the base, as the two compatibility controls must:
  `DedupeTests.test_a1_zero_drafts_is_the_compatibility_control` and
  `RestartTests.test_a6_an_old_format_row_is_unchanged`.

Size: this change is larger than the task's ~200-350-line guideline (the tests alone are ~380 lines): A-1..A-8
each ask for their own fixtures, the clip boundaries and a bounded generator with an independent oracle. No
acceptance criterion was dropped for brevity.
"""

from pathlib import Path
import random
import tempfile
import unittest

from terminal_planner import architect
from terminal_planner.tui import chat as chat_module
from tui_support import HAVE_TEXTUAL

# The reason the other TUI modules give when Textual is missing: the scan test below is declared and skipped,
# never hidden (test_toolchain reads the module with neither Textual nor Rich importable at all).
TEXTUAL_REASON = "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"

if HAVE_TEXTUAL:  # `app` draws through Rich, so only the pane-scan test may reach for it
    from terminal_planner.tui import app as app_module

SNAPSHOT = {"project": "proj", "branch": "main", "revision": 2,
            "plan_state": {"status": "approved", "override": False},
            "milestones": [{"id": "M1", "state": "running", "token": {"milestone": "M1", "attempt": 1}},
                           {"id": "M2", "state": "ready", "token": None}]}
GOAL_LINE = "↳ goal draft: "
ANSWER_LINE = "↳ answer draft M1: "
ENTRY_TEXT = chat_module.ENTRY_TEXT


def goal_block(body):
    """One fenced goal block exactly as the protocol spells it (the opener, the body, the closer)."""
    return "```zplan-goal\n" + body + "\n```"


def answer_block(milestone, body):
    """One fenced answer block for `milestone`, exactly as the protocol spells it."""
    return "```zplan-answer " + milestone + "\n" + body + "\n```"


def draft(kind, text, milestone=""):
    """A stored draft record as `parse_drafts` writes it; the pane matches it by kind, milestone and text only."""
    return {"kind": kind, "text": text, "milestone": milestone or None, "identity": "no plan"}


def stored_render(text):
    """Today's rendering of a row no draft matches: the old `entries_of` clip, spelled out here so the
    compatibility controls never move with the code under test."""
    return text if len(text) <= ENTRY_TEXT else "…" + text[-ENTRY_TEXT:]


def entry_for(text, drafts=(), status="completed"):
    """The one pane entry a stored architect reply (with its success mark and records) yields."""
    return chat_module.entries_of([{"role": "architect", "text": text, "status": status,
                                    "drafts": list(drafts)}])[0]


def lines(entry):
    """The texts of the blocks the pane draws for one entry, in order (`chat.entry_blocks`)."""
    return [text for _kind, text in chat_module.entry_blocks(entry)]


def shown(text, drafts=()):
    """The pane blocks of one architect reply, as `body_rows` asks for them."""
    return lines(entry_for(text, drafts))


class DedupeTests(unittest.TestCase):
    """A-1/A-3/A-4: every matched draft body shows once, as its labelled line at its block's position, in reply
    order, while the narrative around it keeps its own order."""

    def test_a1_one_draft_is_shown_once_at_the_block_position(self):
        """A-1 (1 draft): the fenced block collapses where it stood, nothing is appended below the reply."""
        entry = entry_for("Начало\n" + goal_block("Цель") + "\nКонец", [draft("goal", "Цель")])
        self.assertEqual(chat_module.entry_blocks(entry), [("text", "Начало"), ("draft", GOAL_LINE + "Цель"), ("text", "Конец")])
        self.assertEqual(entry.matched, (0,))
        self.assertNotIn("```", entry.text)

    def test_a1_five_drafts_each_collapse_at_their_own_position(self):
        """A-1 (5 drafts): the segments of each occurrence are checked, not a substring count."""
        text = ("Начало\n" + goal_block("A") + "\nсередина\n" + answer_block("M1", "B") + "\n" + goal_block("C")
                + "\n" + answer_block("M2", "D") + "\n" + goal_block("E") + "\nконец")
        entry = entry_for(text, [draft("goal", "A"), draft("answer", "B", "M1"), draft("goal", "C"),
                                 draft("answer", "D", "M2"), draft("goal", "E")])
        self.assertEqual(entry.text.split("\n"),
                         ["Начало", GOAL_LINE + "A", "середина", ANSWER_LINE + "B", GOAL_LINE + "C",
                          "↳ answer draft M2: D", GOAL_LINE + "E", "конец"])
        self.assertEqual(entry.matched, (0, 1, 2, 3, 4))
        self.assertEqual([kind for kind, _text in chat_module.entry_blocks(entry)].count("draft"), 5)  # each once

    def test_a1_zero_drafts_is_the_compatibility_control(self):
        """A-1 (0 drafts): a reply without a block, and one without metadata, render exactly as today."""
        self.assertEqual(shown("просто ответ"), ["просто ответ"])
        long = "х" * (ENTRY_TEXT + 500)
        self.assertEqual(shown(long), [stored_render(long)])   # today's clip, untouched

    def test_a3_identical_bodies_collapse_once_each_and_a_bare_occurrence_stays(self):
        """A-3: two identical recorded blocks collapse in order; the same text outside any fence stays narrative."""
        entry = entry_for(goal_block("Цель") + "\nЦель\n" + goal_block("Цель"),
                          [draft("goal", "Цель"), draft("goal", "Цель")])
        self.assertEqual(entry.text.split("\n"), [GOAL_LINE + "Цель", "Цель", GOAL_LINE + "Цель"])
        self.assertEqual(entry.matched, (0, 1))

    def test_a3_a_repeated_span_without_a_free_record_stays_raw(self):
        """A-3: a second, identical block is collapsed only when a second record is left for it."""
        entry = entry_for(goal_block("Цель") + "\n" + goal_block("Цель"), [draft("goal", "Цель")])
        self.assertEqual(entry.text.split("\n"), [GOAL_LINE + "Цель", "```zplan-goal", "Цель", "```"])
        self.assertEqual(entry.matched, (0,))

    def test_a4_whitespace_around_the_body_still_matches_and_collapses_trimmed(self):
        """A-4: the stored `Draft.text` is trimmed, the raw block is not; the two still pair up."""
        for raw in ("  Цель  ", " \nЦель\n "):
            with self.subTest(body=raw):
                entry = entry_for("до\n```zplan-goal\n" + raw + "\n```\nпосле", [draft("goal", "Цель")])
                self.assertEqual(entry.text.split("\n"), ["до", GOAL_LINE + "Цель", "после"])
                self.assertEqual(entry.matched, (0,))


class RawSpanTests(unittest.TestCase):
    """A-2: the spans the parser leaves as text stay text beside the ones that collapse, and missing, mismatched
    and duplicate stored metadata are settled by content matching alone."""

    def test_a2_a_sixth_block_stays_raw_beside_five_collapsed_ones(self):
        text = "".join(goal_block("G%d" % index) + "\n" for index in range(6))
        drafts = architect.parse_drafts(text, SNAPSHOT)     # the real row: five records, the sixth is plain text
        entry = entry_for(text, drafts)
        self.assertEqual([item["text"] for item in drafts], ["G%d" % index for index in range(5)])
        self.assertEqual(entry.text.split("\n"),
                         [GOAL_LINE + "G%d" % index for index in range(5)]
                         + ["```zplan-goal", "G5", "```", ""])
        self.assertEqual(entry.matched, (0, 1, 2, 3, 4))

    def test_a2_an_unknown_milestone_and_an_empty_body_stay_raw(self):
        """The parser records neither, so only the valid block beside them collapses."""
        text = answer_block("M9", "не туда") + "\n```zplan-goal\n\n```\n" + goal_block("Цель")
        drafts = architect.parse_drafts(text, SNAPSHOT)
        self.assertEqual([item["text"] for item in drafts], ["Цель"])
        entry = entry_for(text, drafts)
        self.assertEqual(entry.text.split("\n"),
                         ["```zplan-answer M9", "не туда", "```", "```zplan-goal", "", "```",
                          GOAL_LINE + "Цель"])
        self.assertEqual(entry.matched, (0,))

    def test_a2_an_over_limit_body_stays_raw_beside_a_valid_block(self):
        """A body of 4001 characters is not recorded, so its block stays text — and is long enough to be clipped
        by the pane's own bound: only the tail of the reply is asserted here (A-5 owns the clip arithmetic)."""
        huge = "я" * 4001
        text = goal_block(huge) + "\n" + goal_block("Цель")
        drafts = architect.parse_drafts(text, SNAPSHOT)
        self.assertEqual([item["text"] for item in drafts], ["Цель"])
        entry = entry_for(text, drafts)
        self.assertTrue(entry.text.startswith("…"))
        self.assertIn("```", entry.text)                      # the over-limit block's closer is still plain text
        self.assertIn(GOAL_LINE + "Цель", entry.text)         # the valid block beside it collapsed
        self.assertNotIn("goal draft: " + huge[:10], entry.text)
        self.assertEqual(entry.matched, (0,))

    def test_a2_a_quoted_fence_and_an_unclosed_fence_stay_raw(self):
        """A zplan fence inside another block is never a source span, and an unclosed opener ends the scan; a
        record no span matches keeps today's trailing line."""
        text = ("Смотри:\n```python\n```zplan-goal\nсделать X\n```\n" + goal_block("Настоящий")
                + "\nконец\n```zplan-goal\nНе закрыто")
        entry = entry_for(text, [draft("goal", "сделать X"), draft("goal", "Настоящий")])
        self.assertEqual(entry.text.split("\n"),
                         ["Смотри:", "```python", "```zplan-goal", "сделать X", "```", GOAL_LINE + "Настоящий",
                          "конец", "```zplan-goal", "Не закрыто"])
        self.assertEqual(entry.matched, (1,))
        self.assertEqual(chat_module.entry_blocks(entry)[-1], ("draft", GOAL_LINE + "сделать X"))

    def test_a2_missing_mismatched_and_duplicate_metadata(self):
        """No record, a record no span matches, and two identical records for one span."""
        text = "Вот:\n" + goal_block("Написано")
        missing = entry_for(text)
        self.assertEqual(lines(missing), [text])
        mismatched = entry_for(text, [draft("goal", "Другое")])
        self.assertEqual(lines(mismatched), [text, GOAL_LINE + "Другое"])
        duplicate = entry_for(text, [draft("goal", "Написано"), draft("goal", "Написано")])
        self.assertEqual(lines(duplicate), ["Вот:", GOAL_LINE + "Написано", GOAL_LINE + "Написано"])
        self.assertEqual(duplicate.matched, (0,))

    def test_a2_a_mismatched_milestone_never_takes_the_record(self):
        """An unknown milestone's block and a known one with the same body, with the metadata the real parser
        stores: only the M1 record exists, so the M9 span stays raw, the M1 span collapses and nothing trails
        (a match that ignored the milestone would collapse the M9 span instead)."""
        text = answer_block("M9", "X") + "\n" + answer_block("M1", "X")
        drafts = architect.parse_drafts(text, SNAPSHOT)
        self.assertEqual([(item["kind"], item["milestone"], item["text"]) for item in drafts], [("answer", "M1", "X")])
        self.assertEqual(shown(text, drafts), ["```zplan-answer M9\nX\n```", ANSWER_LINE + "X"])


class EligibilityTests(unittest.TestCase):
    """R-1/R-2/A-2 (the reviewed collision): a span the parser's own body rule rejects can never take a record.

    An oversized block and a valid one whose trimmed bodies are equal, so content matching alone would spend the
    row's only record on the ineligible span and leave the valid span raw — and change the clip with it. The rule
    is `architect.draft_body`, the very one `parse_drafts` reads, and it is applied before any record is consumed.
    The fixtures are the parser's own output, never hand-written records: both draft kinds, both orders of the
    ineligible span, the 3999/4000/4001/4002 raw sizes, and space and tab padding."""

    def block(self, kind, raw, milestone=""):
        """One fenced block of `kind` around the raw body `raw`."""
        return ("```zplan-goal" if kind == "goal" else "```zplan-answer " + milestone) + "\n" + raw + "\n```"

    def label(self, kind):
        """The collapsed line's label for `kind`."""
        return GOAL_LINE if kind == "goal" else ANSWER_LINE

    def test_a_raw_body_at_the_bound_keeps_both_blocks_collapsed(self):
        """3999 and 4000 raw characters are inside `MAX_DRAFT_TEXT`: both blocks are recorded and both collapse,
        and the payload counts the trimmed bodies only, so nothing is clipped."""
        for kind, milestone in (("goal", ""), ("answer", "M1")):
            for pad in (" ", "\t"):
                for size in (3999, 4000):
                    with self.subTest(kind=kind, pad=pad, raw=size):
                        text = (self.block(kind, pad * (size - 1) + "A", milestone) + "\nseparator\n"
                                + self.block(kind, "A", milestone))
                        drafts = architect.parse_drafts(text, SNAPSHOT)
                        self.assertEqual([item["text"] for item in drafts], ["A", "A"])
                        entry = entry_for(text, drafts)
                        self.assertEqual(entry.text.split("\n"),
                                         [self.label(kind) + "A", "separator", self.label(kind) + "A"])
                        self.assertEqual(entry.matched, (0, 1))

    def test_an_oversized_body_never_takes_the_valid_blocks_record(self):
        """4001 and 4002 raw characters are outside `MAX_DRAFT_TEXT`: the parser records only the valid block, and
        the ineligible span leaves that record alone - before it (the discriminating order: content matching
        alone would spend the record on the ineligible span) and between two valid ones."""
        for kind, milestone in (("goal", ""), ("answer", "M1")):
            for pad in (" ", "\t"):
                for size in (4001, 4002):
                    huge = pad * (size - 1) + "A"
                    with self.subTest(kind=kind, pad=pad, raw=size, order="ineligible first"):
                        text = self.block(kind, huge, milestone) + "\nseparator\n" + self.block(kind, "A", milestone)
                        drafts = architect.parse_drafts(text, SNAPSHOT)
                        self.assertEqual([item["text"] for item in drafts], ["A"])
                        entry = entry_for(text, drafts)
                        self.assertTrue(entry.text.endswith("separator\n" + self.label(kind) + "A"),
                                        entry.text[-40:])
                        self.assertEqual(entry.matched, (0,))
                    with self.subTest(kind=kind, pad=pad, raw=size, order="ineligible between"):
                        text = (self.block(kind, "A", milestone) + "\nsep1\n" + self.block(kind, huge, milestone)
                                + "\nsep2\n" + self.block(kind, "A", milestone))
                        drafts = architect.parse_drafts(text, SNAPSHOT)
                        self.assertEqual([item["text"] for item in drafts], ["A", "A"])
                        entry = entry_for(text, drafts)
                        self.assertTrue(entry.text.endswith("sep2\n" + self.label(kind) + "A"), entry.text[-40:])
                        self.assertEqual(entry.matched, (0, 1))


class ClipTests(unittest.TestCase):
    """A-5: the bound counts the transformed payload, keeps a cut section's suffix and its whole label, never
    appends a wholly clipped matched draft again, and leaves the full records to [c]/[t]."""

    def test_a5_the_payload_boundary(self):
        """3999/4000 characters of payload are kept whole; 4001 loses its first payload character and says so."""
        for size, clipped in ((3999, False), (4000, False), (4001, True)):
            with self.subTest(payload=size):
                body, narrative = "Ц", "x" * (size - 2)
                entry = entry_for(narrative + "\n" + goal_block(body), [draft("goal", body)])
                expected = narrative + "\n" + GOAL_LINE + body
                self.assertEqual("\n".join(lines(entry)), "…" + expected[1:] if clipped else expected)

    def test_a5_a_maximum_body_keeps_its_label_and_its_tail(self):
        body = "Ц" * 4000
        entry = entry_for("x\n" + goal_block(body), [draft("goal", body)])
        self.assertEqual(entry.text, "…" + GOAL_LINE + body)   # the narrative and its break go, the label stays
        self.assertEqual(entry.matched, (0,))

    def test_a5_a_cut_within_a_narrative_and_within_a_body(self):
        """The cut falls inside a narrative segment, and inside a draft body of a following segment."""
        narrative = "x" * (ENTRY_TEXT + 1)
        entry = entry_for(narrative + "\n" + goal_block("Цель"), [draft("goal", "Цель")])
        self.assertEqual(entry.text, "…" + "x" * (ENTRY_TEXT - 5) + "\n" + GOAL_LINE + "Цель")
        body = "Ц" * 4000
        entry = entry_for(goal_block(body) + "\n" + goal_block("Цель"), [draft("goal", body), draft("goal", "Цель")])
        self.assertEqual(entry.text, "…" + GOAL_LINE + body[5:] + "\n" + GOAL_LINE + "Цель")

    def test_a5_a_wholly_clipped_draft_is_not_appended_again_and_keeps_its_choice(self):
        """Its line is gone from the pane, its record is not: [c] and [t] still act on the clipped draft."""
        goal = entry_for(goal_block("Цель") + "\n" + "n" * (ENTRY_TEXT + 100), [draft("goal", "Цель")])
        self.assertEqual(goal.text, "…" + "n" * ENTRY_TEXT)
        self.assertNotIn("draft", goal.text)
        self.assertEqual(lines(goal), [goal.text])   # nothing appended below
        self.assertEqual(chat_module.newest_goal_draft((goal,)).text, "Цель")
        answer = entry_for(answer_block("M1", "Ответ") + "\n" + "n" * (ENTRY_TEXT + 100),
                           [draft("answer", "Ответ", "M1")])
        self.assertNotIn("draft", answer.text)
        self.assertEqual(chat_module.newest_answer_draft((answer,), "M1").text, "Ответ")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ScanTests(unittest.TestCase):
    """A-5 (L-2) through the real renderer: a collapsed line is scanned like any other row."""

    def test_a5_a_collapsed_line_still_goes_through_the_pane_scan(self):
        body = "до\x1b[2Jпосле"
        entry = entry_for("Начало\n" + goal_block(body), [draft("goal", body)])
        self.assertEqual(app_module.body_rows((entry,)), ["Начало", GOAL_LINE + "допосле"])


class RestartTests(unittest.TestCase):
    """A-6: the store's own rows give the same display after a restart, and an old-format row is untouched."""

    def test_a6_the_store_rows_give_the_same_display(self):
        text = "Вот:\n" + goal_block("Цель") + "\nконец"
        with tempfile.TemporaryDirectory() as root:
            store = architect.ArchitectStore(Path(root), root=Path(root))
            store.append("owner", text="вопрос")
            store.append("architect", text=text, status="completed",
                         drafts=architect.parse_drafts(text, SNAPSHOT))
            first = chat_module.entries_of(store.transcript())
            again = chat_module.entries_of(architect.ArchitectStore(Path(root), root=Path(root)).transcript())
        self.assertEqual(lines(first[1]), ["Вот:", GOAL_LINE + "Цель", "конец"])
        self.assertEqual(lines(again[1]), lines(first[1]))

    def test_a6_an_old_format_row_is_unchanged(self):
        text = "Старый ответ:\n" + goal_block("Цель")
        with tempfile.TemporaryDirectory() as root:
            store = architect.ArchitectStore(Path(root), root=Path(root))
            store.append("architect", text=text)          # stored before drafts existed: no record, no mark
            entry = chat_module.entries_of(store.transcript())[0]
        self.assertEqual(entry.drafts, ())
        self.assertEqual(lines(entry), [text])


def fixture_text(parts):
    """The reply text of a generated case: each `("text", value)` is a narrative line, each block part is its
    opener, its raw body line and its closer."""
    lines = []
    for kind, value in parts:
        lines.extend([value] if kind == "text" else ["```zplan-goal", value, "```"])
    return "\n".join(lines)


def oracle(parts):
    """The expected pane text of one generated reply, from the construction alone.

    The payload and the rendering are built together from an origin map: a payload character is kept when its own
    index is in the kept tail, and a generated label when its section's payload is not wholly before the cut. The
    oracle never calls the production replacement or clipping helpers."""
    payload, atoms = "", []
    for index, (kind, value) in enumerate(parts):
        newline = "" if index == 0 else "\n"
        if kind == "text":
            body, label = value, ""
        elif kind == "goal":
            body, label = value.strip(), GOAL_LINE
        else:  # a block no record covers: its three lines are narrative
            body, label = "```zplan-goal\n" + value + "\n```", ""
        start = len(payload)
        payload += newline + body
        atoms.append(("run", newline, start))          # the section's line break, drawn before its label
        if label:
            atoms.append(("label", label, len(payload)))
        atoms.append(("run", body, start + len(newline)))
    if len(payload) <= ENTRY_TEXT:
        return "".join(value for _kind, value, _start in atoms)
    keep = len(payload) - ENTRY_TEXT
    kept = []
    for kind, value, start in atoms:
        if kind == "label":
            if start > keep:
                kept.append(value)
        elif start + len(value) > keep:
            kept.append(value[max(keep - start, 0):])
    return "…" + "".join(kept)


def generated_cases(seed=20261018, count=120):
    """Bounded `(parts, drafts)` cases: a narrative line, a goal block with one record, or a block with none.

    The bodies and narratives around a bound-sized case exercise the clip; the block bodies of the two kinds are
    drawn from disjoint alphabets, so a record can never cover a block meant to stay raw. A goal block's raw body
    stays inside `MAX_DRAFT_TEXT` (padding is added only where it fits), so every record stands for a block the
    parser would really have stored — the eligibility rule the pane now applies before matching."""
    rng = random.Random(seed)
    for _ in range(count):
        parts, drafts = [], []
        for _ in range(rng.randint(1, 4)):
            roll = rng.random()
            if roll < 0.4:
                parts.append(("text", _line(rng, "н", (0, 1, 2, 3, 5, 3999, 4000, 4001))))
            elif roll < 0.55:
                parts.append(("raw", _line(rng, "0", (0, 1, 2, 3, 5, 3999, 4000, 4001))))
            else:
                raw = _line(rng, "ц", (1, 2, 3, 5, 3999, 4000), architect.MAX_DRAFT_TEXT)
                parts.append(("goal", raw))
                drafts.append({"kind": "goal", "text": raw.strip(), "milestone": None, "identity": "no plan"})
        yield parts, drafts


def _line(rng, char, sizes, limit=None):
    """One narrative line or block body: `char` repeated to a drawn size, sometimes with whitespace the stored
    `Draft.text` trims and the raw block keeps — never past `limit` raw characters, so a block body that stands for
    a stored record is one the parser's own bound accepts."""
    text = char * rng.choice(sizes)
    if text and rng.random() < 0.4:
        padded = ("%s " if rng.random() < 0.5 else " %s") % text
        if limit is None or len(padded) <= limit:
            text = padded
    return text


class DraftLabelTests(unittest.TestCase):
    """T2/U3: the app draws its own draft label, so a reply's own label line before the block is cut. The English
    label is cut, and so is the 0.7.x Russian one (`chat.LEGACY_DRAFT_KINDS`) a stored reply may still carry.

    Interpretation: the pane's own label is the `DRAFT_KINDS` word (`goal draft`), so the label line the architect
    writes is that word, with or without bold and colon; the Russian forms are input fixtures.
    """

    def test_u3_a_label_line_before_a_block_is_cut_in_english_and_in_a_0_7_x_reply(self):
        for label in ("Goal draft:", "**Goal draft:**", "goal draft", "Черновик цели:", "**Черновик цели:**",
                      "черновик цели"):
            with self.subTest(label=label):
                self.assertEqual(shown("Intro\n\n" + label + "\n\n" + goal_block("Цель"),
                                       [draft("goal", "Цель")]), ["Intro", GOAL_LINE + "Цель"])
        for label in ("Answer draft:", "Черновик ответа:"):
            with self.subTest(label=label):
                self.assertEqual(shown("Intro\n" + label + "\n" + answer_block("M1", "B"),
                                       [draft("answer", "B", "M1")]), ["Intro", ANSWER_LINE + "B"])
        self.assertEqual(shown("Draft below:\n" + goal_block("Цель"), [draft("goal", "Цель")]),
                         ["Draft below:", GOAL_LINE + "Цель"])  # any other line stays


class GeneratorTests(unittest.TestCase):
    """A-7: a bounded generator (fixed seed, 120 cases) over constructed replies, checked against the oracle
    above — the rule of A-1..A-5 applied from the fixture construction, never by the production helpers."""

    def test_a7_the_constructed_replies_render_like_the_oracle(self):
        for index, (parts, drafts) in enumerate(generated_cases()):
            with self.subTest(case=index, parts=[kind for kind, _ in parts]):
                entry = entry_for(fixture_text(parts), drafts)
                self.assertEqual(entry.text, oracle(parts))
                self.assertEqual(entry.matched, tuple(range(len(drafts))))
                self.assertEqual([kind for kind, _text in chat_module.entry_blocks(entry)].count("draft"),
                                 sum(1 for _head, label, _body in entry.sections if label))  # none appended below


if __name__ == "__main__":
    unittest.main()
