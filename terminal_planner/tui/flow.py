"""Status wrapping and clipping helpers for the Now tab.

`wrap_status` wraps the app's planner/run status lines by terminal cells (the tab's `#live` never wraps while the
scheme is drawn); `clip` cuts a text to a number of cells with a visible `…`. The stage scheme itself is drawn by
`scheme.py`. No app, no I/O."""

from rich.cells import cell_len

ELLIPSIS = "…"


def wrap_status(lines, width):
    """Wrap the app's planner/run status lines by terminal cells for the drawn Now tab (F2/A4).

    While the drawing is shown `#live` carries `text-wrap: nowrap` (`zplan.tcss`) so a scheme row is never broken;
    that also means every appended line must already fit the pane in cells, or it is cut on the right. The app's own
    wrapper (`app.wrapped`) measures characters, so a line short in characters but wide in cells — wide glyphs like
    «汉» — stays one piece there and loses its tail; this wraps by cells instead, whole glyphs only. Each returned
    string is a plain line of at most `width` cells."""
    out = []
    for line in lines:
        out.extend(_wrap_cells(line, width))
    return out


def clip(text, room):
    """`text` cut to `room` terminal cells; a dropped tail ends with `…` so the cut is visible."""
    text = str(text)
    if room <= 0:
        return ""
    if cell_len(text) <= room:
        return text
    if room == 1:
        return ELLIPSIS
    piece, used = "", 0
    for char in text:
        width = cell_len(char)
        if used + width > room - 1:
            break
        piece += char
        used += width
    return piece + ELLIPSIS


def _cut_cells(text, room):
    """`text` split into the head that fits `room` terminal cells and the rest."""
    head, used = "", 0
    for index, char in enumerate(text):
        width = cell_len(char)
        if used + width > room:
            return text[:index], text[index:]
        head, used = head + char, used + width
    return text, ""


def _wrap_cells(text, room):
    """`text` wrapped to lines of at most `room` terminal cells: on spaces like `textwrap`, a word too wide for a
    line split by cells, so a wide glyph is never counted as one column (the same unit as the width bound A1
    uses)."""
    room = max(room, 1)
    lines, current = [], ""
    for word in str(text).split():
        candidate = word if not current else current + " " + word
        if cell_len(candidate) <= room:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        while cell_len(word) > room:
            head, word = _cut_cells(word, room)
            lines.append(head)
        current = word
    lines.append(current)
    return lines
