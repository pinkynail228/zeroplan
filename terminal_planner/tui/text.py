"""L-2/L-3 text helpers of the full-screen shell: terminal-cell fitting and eliding, the escaping scan that turns a
model-supplied value into display text, and the compact counter spellings. Pure string and width work: no widget, no
controller, no state. `app.py` imports every name here and re-exports it."""

import textwrap

from rich.cells import cell_len

ELLIPSIS = "…"                 # a middle- or end-elided value keeps it in place of what it drops
# L-2: the forms a scan removes whole, each a closed character class, tried in this order at every position: a CSI,
# then a string whose payload runs to its first ST (a BEL also ends an OSC), then any other escape. The dictionary
# holds the string introducers of both spellings, each mapped to its own OSC flag, and `C1_CSI` is the eight-bit CSI
# introducer (`CSI_INTRO` is the seven-bit one). The generic escape is tried only when the byte after the ESC opens
# none of the other forms.
CSI_INTRO = "\x1b["
C1_CSI = "\u009b"
STRING_INTRO = {"\x1b]": True, "\x1bP": False, "\x1bX": False, "\x1b^": False, "\x1b_": False,
                "\u009d": True, "\u0090": False, "\u0098": False, "\u009e": False, "\u009f": False}
GENERIC_ESC = ("[", "]", "P", "X", "^", "_")  # after these bytes only the two forms above may start


def hang(lines, width, indent=2):
    """Wrap logical lines to `width` columns; continuation lines hang under the text (leading space + `indent`).
    Returns (first piece, continuation pieces) per logical line."""
    out = []
    for line in lines:
        if len(line) <= width or width < 12:
            out.append((line, ()))
            continue
        lead = len(line) - len(line.lstrip())
        pieces = textwrap.wrap(line, width, subsequent_indent=" " * min(lead + indent, width // 2),
                               replace_whitespace=False, drop_whitespace=True, break_long_words=True,
                               break_on_hyphens=False) or [line]
        out.append((pieces[0], tuple(pieces[1:])))
    return out


def wrapped(lines, width, indent=2):
    """The wrapped text of logical lines, one string per displayed line."""
    return [piece for first, rest in hang(lines, width, indent) for piece in (first,) + rest]


def display_width(text):
    """How much room `text` takes on screen: terminal cells, not characters, so a wide glyph counts as two."""
    return cell_len(str(text))


def fit_cells(text, room, end=False):
    """The longest prefix (a suffix with `end`) of `text` that fits in `room` terminal cells, whole glyphs only."""
    if room <= 0:
        return ""
    if display_width(text) <= room:
        return text
    piece = ""
    for char in (reversed(text) if end else text):
        width = display_width(char)
        if width > room:
            break
        piece = char + piece if end else piece + char
        room -= width
    return piece


def elide_middle(text, room):
    """`text` shortened in the middle with `…` to `room` display columns: both ends stay, the middle goes.
    `room` is counted in terminal cells, so a path of wide glyphs is cut to the room the renderer gives it."""
    if display_width(text) <= room:
        return text
    if room <= 1:
        return ELLIPSIS
    inner = room - display_width(ELLIPSIS)
    head = fit_cells(text, (inner + 1) // 2)
    tail = fit_cells(text[len(head):], inner - display_width(head), end=True)
    return head + ELLIPSIS + tail


def elide_end(text, room):
    """L-3: `text` shortened at its end with `…` to `room` display cells: the start stays, the tail goes."""
    if display_width(text) <= room:
        return text
    return (fit_cells(text, room - 1) + ELLIPSIS) if room > 1 else (ELLIPSIS if room == 1 else "")


def csi_end(text, start):
    """L-2: where the CSI whose body starts at `start` ends, or None when it does not complete: parameter bytes
    (`0x30`–`0x3f`), then intermediate bytes (`0x20`–`0x2f`), then one final byte (`0x40`–`0x7e`)."""
    index = start
    while index < len(text) and 0x30 <= ord(text[index]) <= 0x3f:
        index += 1
    while index < len(text) and 0x20 <= ord(text[index]) <= 0x2f:
        index += 1
    return index + 1 if index < len(text) and 0x40 <= ord(text[index]) <= 0x7e else None


def string_end(text, start, osc):
    """L-2: where the string whose payload starts at `start` ends, or None when no terminator follows: the first
    ST (an ESC and a backslash, or a C1 ST `\u009c`), and for an OSC a BEL too."""
    index = start
    while index < len(text):
        char = text[index]
        if char == "\u009c" or (osc and char == "\x07"):
            return index + 1
        if char == "\x1b" and text[index + 1:index + 2] == "\\":
            return index + 2
        index += 1
    return None


def escape_end(text, start):
    """L-2: where any other escape whose body starts at `start` ends, or None when it does not complete:
    intermediate bytes, then one final byte (`0x30`–`0x7e`)."""
    index = start
    while index < len(text) and 0x20 <= ord(text[index]) <= 0x2f:
        index += 1
    return index + 1 if index < len(text) and 0x30 <= ord(text[index]) <= 0x7e else None


def shown(char):
    """L-2: one remaining character as it is shown — a printable one as itself, a line break and a tab as their
    escapes, every other one as a fixed-width lowercase escape (two, four or eight hex digits by its code point)."""
    if char.isprintable():
        return char
    if char == "\n":
        return "\\n"
    if char == "\t":
        return "\\t"
    code = ord(char)
    if code <= 0xff:
        return "\\x%02x" % code
    return ("\\u%04x" % code) if code <= 0xffff else ("\\U%08x" % code)


def plain_scan(text):
    """L-2: `text`'s display form. Scan left to right and at each position try, in this order, a CSI, a string, any
    other escape; a complete form is removed whole and a start that does not complete before the end hands its
    introducer to `shown` and the scan resumes at the next character, so an introducer is never re-read as the
    start of another form.

    A string that does not complete searched the whole rest of the value for a terminator and found none, so no
    later start of the same kind can find one there either: `missing_st` (and `missing_osc` for the forms a BEL
    may end) remembers where that search failed and is never run again from there. A value of nothing but `ESC ]`
    is one pass this way; searching from each of its introducers was a quarter of an hour of the UI thread for one
    millisecond of history."""
    out, index = [], 0
    beyond = len(text) + 1  # no terminator of this kind at or after this index: a search already proved it
    missing_st, missing_osc = beyond, beyond
    while index < len(text):
        char = text[index]
        pair = text[index:index + 2]
        if pair == CSI_INTRO:
            intro, end = "\x1b", csi_end(text, index + 2)
        elif char == C1_CSI:
            intro, end = char, csi_end(text, index + 1)
        elif pair in STRING_INTRO or char in STRING_INTRO:
            two = len(pair) == 2 and pair in STRING_INTRO
            key, intro = (pair, "\x1b") if two else (char, char)
            osc = STRING_INTRO[key]
            if index >= (missing_osc if osc else missing_st):
                end = None                      # a terminator of this kind is already known to be missing here
            else:
                end = string_end(text, index + len(key), osc)
                if end is None:                 # nothing to the end: no later start of this kind can find one
                    missing_st = index
                    if osc:
                        missing_osc = index
        elif char == "\x1b" and text[index + 1:index + 2] not in GENERIC_ESC:
            intro, end = "\x1b", escape_end(text, index + 1)
        else:
            out.append(shown(char))
            index += 1
            continue
        if end is None:
            out.append(shown(intro))
            index += 1
        else:
            index = end
    return "".join(out)


def plain_value(value):
    """L-2: one header value as one display row: the value is scanned whole, its terminal sequences removed and
    every remaining character shown — a line break and a tab as their escapes, another unprintable one as a
    fixed-width escape. A value never costs a row of its own and nothing of it reaches the terminal as a command.
    (`planning.clean` removes the control characters instead: that helper is another rule.)"""
    return plain_scan(str(value))


def plain_lines(value):
    """L-2: a body text as display rows: the split on the line break comes first — a break is never shown as one of
    the escapes — and each row then gets a header value's treatment. The model supplies this text, and `cli.safe`
    would turn a terminal sequence into its `?` before the scan can see it: the sequence goes first, so nothing of
    the text reaches the terminal as a command."""
    return [plain_scan(piece) for piece in str(value).split("\n")]


def wrap_cells(text, cols):
    """L-1: `text` as rows no wider than `cols` terminal cells. A word breaks at its end where that fits and is cut
    at the cell where it does not, so a row of wide glyphs is measured as the renderer measures it."""
    rows = []
    for piece in textwrap.wrap(text or "", max(cols, 1), replace_whitespace=False, drop_whitespace=True,
                               break_long_words=True, break_on_hyphens=False) or [""]:
        row, width = "", 0
        for char in piece:
            size = display_width(char)
            if width + size > cols:
                rows.append(row)
                row, width = "", 0
            row += char
            width += size
        rows.append(row)
    return rows


def decimal_text(value):
    """L-3: a nonnegative counter in decimal, spelled here rather than with `%d`: an interpreter caps `int`->`str`
    by default (4 300 digits) and L-3 bounds neither the counter nor the width, so `%d` would raise on a full row
    the rule still has to draw. Nine digits at a time is the same spelling `%d` would have written."""
    if value < 10:
        return chr(0x30 + value)
    chunks = []
    while value:
        value, rest = divmod(value, 1000000000)
        chunks.append(rest)
    return "%d%s" % (chunks.pop(), "".join("%09d" % chunk for chunk in reversed(chunks)))


def short_count(value):
    """L-3: a usage counter in the compact form: exact below a thousand, else floored to one decimal with k, M, G
    or T; from 10**15 on no counter fits the form, and `999T+` stands for every one of them."""
    value = max(int(value), 0)
    if value < 1000:
        return str(value)
    if value >= 10 ** 15:
        return "999T+"
    limit, suffix = next((limit, unit) for limit, unit in ((10 ** 12, "T"), (10 ** 9, "G"), (10 ** 6, "M"),
                                                           (10 ** 3, "k")) if value >= limit)
    return "%.1f%s" % (value // (limit // 10) / 10.0, suffix)
