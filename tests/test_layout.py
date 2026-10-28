"""L-2..L-4 of the chat pane as unit rules: the conversation's text and the chat's own lines.

The header rows (`chat_head`, L-3) are gone with C1: the model and the counters ride the bar's tail and the thinking
row sits above the input, both checked in `tests/test_tui_chat_chrome.py`.

The conversation's own rows are not a hand-computed budget any more (i3-chat-inline): `#chat` is a scroll of one
widget per retained entry, so the rows the history takes are the widget's own layout and the old
`chat_scroll`/`chat_layout` arithmetic (its row budget, its marker and its below-the-minimum fallback) is gone with
the widget list. The text those widgets carry is still this module's business — `chat.entry_blocks` + L-2 is the
pipeline `MainScreen.chat_entry_lines` runs (`app.entry_rows`) — and the paging of the scroll itself is
checked through the real shell in `tests/test_tui_chat_scroll.py`."""

import re
import time
from types import SimpleNamespace
import unittest

from terminal_planner.tui import chat as chat_module
from tui_support import HAVE_TEXTUAL

# The reason the other TUI modules give when Textual is missing: without it the TUI test classes below are
# still declared (unittest discovery must see them) and skipped, never hidden.
TEXTUAL_REASON = "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is required"

# The oracle of L-2 for the regression check: the rule spelled out here, with regular expressions built from its
# closed classes and no production helper. It is checked against literal expectations below before it is trusted.
ORACLE_CSI = re.compile(r"(?:\x1b\[|\u009b)[0-?]*[ -/]*[@-~]")
ORACLE_OSC = re.compile(r"(?:\x1b\]|\u009d)(?:(?!\x07|\x1b\\|\u009c)[\s\S])*(?:\x07|\x1b\\|\u009c)")
ORACLE_STRING = re.compile(r"(?:\x1b[PX^_]|[\u0090\u0098\u009e\u009f])(?:(?!\x1b\\|\u009c)[\s\S])*(?:\x1b\\|\u009c)")
ORACLE_ESC = re.compile(r"\x1b[ -/]*[0-~]")
ORACLE_OSC_INTROS = ("\x1b]", "\u009d")
ORACLE_STRING_INTROS = ("\x1bP", "\x1bX", "\x1b^", "\x1b_", "\u0090", "\u0098", "\u009e", "\u009f")
ORACLE_ESC_SKIP = ("[", "]", "P", "X", "^", "_")


def escape_char(char):
    """L-2's escape for one remaining character: printable stays, LF and TAB get theirs, the rest a fixed-width
    lowercase escape of two, four or eight hex digits by code point."""
    if char.isprintable():
        return char
    if char == "\n":
        return "\\n"
    if char == "\t":
        return "\\t"
    code = ord(char)
    return "\\x%02x" % code if code <= 0xff else ("\\u%04x" % code if code <= 0xffff else "\\U%08x" % code)


def text_oracle(text):
    """The expected L-2 display form of `text`, written here from the rule and independent of production code."""
    out, index = [], 0
    while index < len(text):
        char, pair = text[index], text[index:index + 2]
        match = None
        if pair == "\x1b[" or char == "\u009b":
            match = ORACLE_CSI.match(text, index)
        elif pair in ORACLE_OSC_INTROS or char in ORACLE_OSC_INTROS:
            match = ORACLE_OSC.match(text, index)
        elif pair in ORACLE_STRING_INTROS or char in ORACLE_STRING_INTROS:
            match = ORACLE_STRING.match(text, index)
        elif char == "\x1b" and text[index + 1:index + 2] not in ORACLE_ESC_SKIP:
            match = ORACLE_ESC.match(text, index)
        if match is None:  # not a start, or a start that does not complete: the introducer stays a character
            out.append(escape_char(char))
            index += 1
        else:
            index = match.end()
    return "".join(out)


if HAVE_TEXTUAL:
    from rich.cells import cell_len

    from terminal_planner.tui import app as app_module


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatBodyTests(unittest.TestCase):
    """L-2/L-4 for the conversation: its text is read through the pipeline its widgets carry
    (`chat.entry_blocks` + L-2)."""

    def body(self, entries):
        """A history's display lines, through the very pipeline the entry widgets carry
        (`MainScreen.chat_entry_lines`): `chat.entry_blocks` renders each entry, L-2 escapes each line."""
        return [piece for _entry, _role, shown in app_module.entry_rows(entries)
                for _kind, text in shown.blocks for piece in text.split("\n")]

    def test_l4_a_history_of_unterminated_string_introducers_is_scanned_in_linear_time(self):
        """C-5: the L-2 scan is one left-to-right pass, not a terminator search restarted at every introducer.
        Thirty entries of nothing but `ESC ]` — 4 000 characters each, inside the store's own entry cap — put
        2 000 incomplete string starts in every line, and a search from each of them walked the rest of the
        line again: the whole corpus took a quarter of an hour in one pass, and that pass is what every render
        runs synchronously on the UI thread every time the entry widgets are built or updated (a Ctrl+Q arriving
        then could not be handled in its five seconds).
        It must now finish in the time a frame gets; the bound is generous — the fixed scan is milliseconds —
        and the corpus is deterministic. `missing_st`/`missing_osc` are what make it linear: a search that
        found no terminator records that none is left, and no later start of that kind searches again.

        The oracle is the L-2 rule itself: each `ESC ]` is an incomplete start, so its introducer is kept and
        the `]` is an ordinary character."""
        history = tuple(chat_module.ChatEntry("architect", "\x1b]" * 2000) for _ in range(30))
        start = time.monotonic()
        rows = self.body(history)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 5.0, "one pass over the retained history took %.3fs" % elapsed)
        self.assertEqual(app_module.state_row("\x1b]" * 3), "\\x1b]" * 3)
        self.assertTrue(all("\x1b" not in row for row in rows))  # nothing of the corpus reaches the terminal

    def test_l2_the_body_text_is_sanitized_before_it_is_escaped(self):
        """L-2: the history and the marked partial are split first, then the terminal sequence out and what is left escaped. A sequence therefore never shows
        up as `cli.safe`'s `?` (the scan removes it whole), and a C1 control is escaped, not kept."""
        escaped = "a\tb\x1b[31mRED\x1b[0m\x07"
        self.assertEqual(app_module.plain_lines(escaped + "\nlast"), ["a\\tbRED\\x07", "last"])
        self.assertEqual(app_module.plain_lines("a\x1b[2Jb"), ["ab"])
        self.assertEqual(app_module.plain_value("a\x85b"), "a\\x85b")
        # Every escape form goes whole, not just the seven-bit CSI: a string introducer (DCS, here with a
        # payload) with its terminator, an eight-bit C1 CSI, and the ESC forms that are one final byte (ESC 7
        # save-cursor) or an intermediate and a final byte (ESC (B charset select).
        for value, expected in (("left\x1b7right", "leftright"),
                                ("left\x9b31mright\x9b0m", "leftright"),
                                ("left\x1bPpayload\x1b\\right", "leftright"),
                                ("before\x1bP1;2|payload\x1b\\after", "beforeafter"),
                                ("left\x1b(Bright", "leftright"),
                                ("left\x9dpayload\x9cright", "leftright"),  # the eight-bit OSC form
                                ("left\x90dcs\x9cright", "leftright"),      # ... and the eight-bit DCS one
                                ("left\x9dkоманда\x9cright", "leftright"),
                                ("\x1b8\x1b7\x1b=text", "text")):
            with self.subTest(value=repr(value)):
                self.assertEqual(app_module.plain_value(value), expected)
        # The eight-bit string form is taken out whole, payload and introducer together — never left to the
        # C1 escape rule as `\x9d`/`\x9c` with its payload still readable between them.
        self.assertEqual(app_module.plain_value("left\x9dpayload\x9cright"), "leftright")
        entry = chat_module.ChatEntry("architect", escaped + "\nlast", "часть\x1b[2J")
        rows = self.body((entry,))
        self.assertIn("a\\tbRED\\x07", rows)
        self.assertIn("(interrupted): часть", rows)
        self.assertIn("last", rows)
        for text in ("до\x1bP1;2|x\x1b\\после", "до\x90payload\x9cпосле"):  # the seven- and the eight-bit string form
            self.assertIn("допосле", self.body((chat_module.ChatEntry("architect", text),)))
        for row in rows:
            self.assertNotIn("\x1b", row)
            self.assertNotIn("\x9c", row)
            self.assertLessEqual(cell_len(row), 80)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatOutcomeTests(unittest.TestCase):
    """u3b-chat C-4/C-6 with L-4: which of the chat's own lines the pane says above the body."""

    def shell(self, state):
        return SimpleNamespace(chat=SimpleNamespace(state=state) if state is not None else None)

    def test_a_refusal_the_history_does_not_carry_is_shown_while_the_chat_is_idle(self):
        """The refusals no store write follows — another window's lock (C-6), a closing chat, a rebind the
        profile refused — have no history line and no idle state row (L-4), so the pane shows the note."""
        locked = "Another zplan process is already talking to this project's architect. [code: architect.locked]"
        self.assertEqual(app_module.chat_outcome(self.shell(chat_module.ChatState(phase="ready", note=locked))),
                         locked)
        for state in (None,
                      chat_module.ChatState(phase="preparing", note=locked),
                      chat_module.ChatState(phase="blocked", note=locked),
                      chat_module.ChatState(phase="ready")):
            with self.subTest(state=state):
                self.assertEqual(app_module.chat_outcome(self.shell(state)), "")
        # a refusal is read for the turn it was refused for: it shows while a turn runs too (C3)
        self.assertEqual(app_module.chat_outcome(self.shell(chat_module.ChatState(
            phase="ready", running=True, note=locked))), locked)

    def test_a_result_the_history_carries_is_not_said_twice(self):
        """A failed turn's cause and a reset entry are history lines (L-4); the pane does not repeat them."""
        cause = "Codex exited with code 2 before the turn ended."
        self.assertEqual(app_module.chat_outcome(self.shell(chat_module.ChatState(
            phase="ready", note=cause, entries=(chat_module.ChatEntry("error", cause),)))), "")
        line = "New dialog: the previous thread id is forgotten."
        self.assertEqual(app_module.chat_outcome(self.shell(chat_module.ChatState(
            phase="ready", note=line, entries=(chat_module.ChatEntry("reset", line),)))), "")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class TextEncodingTests(unittest.TestCase):
    """G-6: L-2's scan through the production path (`app.plain_value`, the function `chat_header` and the
    history call) against `text_oracle`, the rule written out here with its own regular expressions.

    The corpus is finite and spelled out below: every C0 and every C1 code point alone and inside text; each
    introducer (the ESC and the C1 spelling of a CSI and of each string type, and any other escape) crossed
    with each terminator (ST as an ESC and a backslash, a C1 ST, a BEL for an OSC and for a non-OSC, and no
    terminator), over the payloads `""`, `abc`, the concatenated C0/C1 characters and `a ESC [ 31 m b ESC ] c`;
    every truncation point of every such token; a CSI with U+2603 before its final character; and every Python
    code point whose `isprintable()` is false, alone. Each form is also read next to a backslash, a wide and a
    non-BMP character, and next to itself; the literal table checks the oracle itself before it is trusted.

    Interpretations (G-5), each a decision the rule leaves open:

    - The introducer an incomplete form hands back is a single character: the ESC itself for the seven-bit CSI
      and string forms (the byte after it, `[`, `]`, `P`, `X`, `^` or `_`, is scanned again as an ordinary
      character) and the C1 character for the eight-bit ones. That is what `index += 1` does below and it is
      why `ESC [ 3 1` at the end of a value shows `\\x1b[31`, never `\\x1b` and a moved scan.
    - The three string spellings that name no OSC payload (DCS, SOS, PM, APC) are ended by an ST alone: a BEL
      inside them is payload, so `ESC P x BEL` without an ST is incomplete. The rule names the BEL terminator
      for `ESC ]`/U+009D alone.
    - An `ESC` that ends the value is a start that cannot complete (its generic form needs one final byte), so
      it is kept as `\\x1b`; `str.isprintable()` alone would have escaped it the same way, and the check keeps
      both readings.
    - The corpus uses U+009B/U+009D and the other C1 introducers in their U+0080..U+009F spelling, which is how
      the rule names them; a one-character `\\xNN` opcode spelling is not a separate form.

    G-8 mutations, demonstrated once each in a scratch copy (the checkout was copied without `.git`/`.tools`,
    the copy's `terminal_planner/tui/app.py` was edited and `PYTHONPATH=.:tests python3 -m unittest
    tests.test_layout.TextEncodingTests` was run there; the shared worktree was not reverted):

    - The f58d700 sanitizer (`TEXT_SEQ.sub` plus the `code < 32 or 0x7f <= code < 0xa0` escape, `plain_value`
      and `plain_lines` routed through it) as L-2: 22552 failures. The first reported case is the C0 singleton
      inside text, `\\x00nested` with an incomplete `ESC ]` after it: the old generic alternative matched that
      `ESC ]` and removed it, where the rule keeps `\\x1b]`; the incomplete CSI `a` + `ESC [ 3 1` fails too (the
      old regex matched `ESC [`, giving `a31`).
    - The generic escape tried before the string forms (so an `ESC ]`, `ESC P` or a C1 string introducer is
      consumed as an `ESC` plus one final byte) as L-2: 17859 failures. It fails again on `\\x00nested` + `ESC ]`
      and on the complete string forms `a` + `ESC ]` + `0;t` + BEL and `a` + `ESC P` + `1;2|xy` + `ESC \\`, whose
      payloads then print instead of going with their introducer.
    - Header fields reconstructed from a joined display string as L-3 (`header_values` re-joining the four named
      values with ` · ` and splitting them straight back out): `ChatHeaderFieldTests` in tests/test_tui_chat
      fails — twenty failures — first at its L-1 minimum (60x17) with ` · ` in all four fields: the rows come
      back as `['', '', '', 'ходов 1 · токенов 15']` where L-3's rows are `[' · / · ', 'provider  · ',
      'CODEX_HOME  · ', 'ходов 1 · токенов 15']`, every value that held the separator having been cut out of
      its own field.

    The failure counts are the ones the corpus below (229 tokens and every non-printable code point) reports
    on this checkout; they rise with the corpus, and the first reported case is the stable part.
    """

    C0 = "".join(chr(code) for code in range(0x00, 0x20))
    C1 = "".join(chr(code) for code in range(0x80, 0xa0))
    PAYLOADS = ("", "abc", C0 + C1, "a\x1b[31mb\x1b]c")
    TERMINATORS = ("\x1b\\", "\u009c", "\x07", "")
    STRING_INTROS = ("\x1b]", "\x1bP", "\x1bX", "\x1b^", "\x1b_",
                     "\u009d", "\u0090", "\u0098", "\u009e", "\u009f")
    CSI_INTROS = ("\x1b[", "\u009b")
    GENERIC_INTRO = "\x1b"  # any other escape: one final byte, and no payload of its own to run through
    ESC_TOKENS = ("\x1b7", "\x1b(B", "\x1b=", "\x1b ", "\x1b///0")
    CONTEXTS = ("\\", "\u754c", "\U00010348")  # a backslash, a wide and a non-BMP character
    LITERALS = (
        ("a\x1b[31mb", "ab"),                                  # a complete CSI goes whole
        ("a\x1b[31", "a\\x1b[31"),                             # an incomplete CSI keeps its ESC, `[31` prints
        ("a\x1b[31\u2603mb", "a\\x1b[31\u2603mb"),             # a CSI with U+2603 before its final byte
        ("a\x1bP1;2|xy\x1b\\b", "ab"),                         # a complete string form with its ST
        ("a\x1bPxy", "a\\x1bPxy"),                             # a string form with no terminator at all
        ("a\x1b]0;t\x07b", "ab"),                              # an OSC ended by a BEL
        ("a\u009d0;t\u009cb", "ab"),                           # ... and its eight-bit spelling
        ("a\x1bPx\x07b", "a\\x1bPx\\x07b"),                    # a BEL ends no non-OSC string: incomplete
        ("a\x1bPx\x1b[31m\x1b\\b", "ab"),                      # the payload runs through a nested ESC to its ST
        ("a\x1b7b", "ab"),                                     # any other escape: one final byte
        ("a\x1b(Bb", "ab"),                                    # ... an intermediate and a final byte
        ("a\x1b", "a\\x1b"),                                   # a lone trailing ESC is kept as a character
        ("x\x1by", "x"),                                       # ... its final byte is consumed with it
        ("a\n\tb", "a\\n\\tb"),                                # LF and TAB get their escapes
        ("a\x00\x85b", "a\\x00\\x85b"),                        # other unprintables get fixed-width escapes
        ("a\u2603b", "a\u2603b"),                              # a printable non-ASCII character stays
        ("a\\x1bb", "a\\x1bb"),                                # a literal backslash is shown as it is
    )

    def tokens(self):
        """Every generated complete, malformed and incomplete token of the corpus."""
        out = list(self.ESC_TOKENS)
        for intro in self.CSI_INTROS:
            out += [intro + body for body in ("", "m", "31m", "?25h", "1;2H", "0 q")]
            out.append(intro + "31\u2603m")  # malformed: no final byte where the snowman sits
            out.append(intro + "31")         # incomplete
        for intro in self.STRING_INTROS:
            out += [intro + payload + terminator for payload in self.PAYLOADS for terminator in self.TERMINATORS]
        # The finite corpus crosses every other introducer with the payloads and the terminators as well: the
        # CSI introducers and the generic ESC, whose form is one final byte and no payload — `\x1b[abc\x9c` is a
        # CSI with no final byte where the C1 ST sits, `\x1babc\x07` a generic ESC that swallowed `a` and left
        # `bc` and the BEL behind it, and `\u009b` + the concatenated C0/C1 payload + an ESC ST the eight-bit
        # CSI whose body runs into a terminator that is no part of it.
        for intro in list(self.CSI_INTROS) + [self.GENERIC_INTRO]:
            out += [intro + payload + terminator for payload in self.PAYLOADS for terminator in self.TERMINATORS]
        return out

    def test_the_oracle_matches_the_literal_expectations(self):
        """The oracle itself, before it is trusted: representative complete, malformed and incomplete cases."""
        for text, expected in self.LITERALS:
            with self.subTest(text=repr(text)):
                self.assertEqual(text_oracle(text), expected)
                self.assertEqual(app_module.plain_value(text), expected)

    def test_every_token_prefix_and_context_matches_the_oracle(self):
        """Every token, every truncation point of it, and each of them alone, in prefix/suffix context, next to
        a backslash, a wide character and a non-BMP character, and next to itself."""
        for token in self.tokens():
            for point in range(len(token) + 1):
                piece = token[:point]
                cases = [piece, "<<" + piece + ">>", piece + piece, "\t" + piece + "\u2603"]
                cases += [context + piece for context in self.CONTEXTS]
                cases += [piece + context for context in self.CONTEXTS]
                for case in cases:
                    with self.subTest(token=repr(token), point=point, case=repr(case)):
                        self.assertEqual(app_module.plain_value(case), text_oracle(case))
                        # the history's own entry point: the split on LF comes first, then the same scan
                        self.assertEqual(app_module.plain_lines(case),
                                         [text_oracle(part) for part in case.split("\n")])

    def test_every_c0_and_c1_code_point_alone_and_inside_text(self):
        """Every C0 and C1 code point as a singleton and inside text, in both spellings the rule can meet."""
        for code in list(range(0x00, 0x20)) + list(range(0x80, 0xa0)):
            char = chr(code)
            for case in (char, "x" + char + "y", "аб " + char, char + "nested\x1b]", char + "\u009dpayload"):
                with self.subTest(code=hex(code), case=repr(case)):
                    self.assertEqual(app_module.plain_value(case), text_oracle(case))

    def test_every_non_printable_code_point_as_a_singleton(self):
        """Every Python code point whose `isprintable()` is false, alone: its display form is exactly its
        escape, whether it is a C0/C1 control, a format character, a surrogate or an unassigned one."""
        wrong = [code for code in range(0x110000)
                 if not chr(code).isprintable() and app_module.plain_value(chr(code)) != escape_char(chr(code))]
        self.assertEqual(wrong, [])
