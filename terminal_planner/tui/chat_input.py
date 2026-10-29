"""The chat input: a `TextArea` that still behaves as the one-line `Input` the screen was written against."""
from dataclasses import dataclass

from textual import events
from textual.actions import SkipAction
from textual.message import Message
from textual.widgets import TextArea


@dataclass
class Changed(Message, namespace="input"):
    """The text changed: the screen's `on_input_changed` handles it as it handled `Input.Changed`."""

    input: "ChatInput"
    value: str

    @property
    def control(self):
        return self.input


@dataclass
class Submitted(Message, namespace="input"):
    """Enter was pressed: the screen's `on_input_submitted` handles it as it handled `Input.Submitted`."""

    input: "ChatInput"
    value: str

    @property
    def control(self):
        return self.input


NEW_LINE_KEYS = ("ctrl+j", "alt+enter", "shift+enter")


class ChatInput(TextArea):
    """Several wrapped lines (Enter sends, ctrl+j / alt+enter / shift+enter add a line, a paste keeps its lines), no
    border and no line numbers. A text that starts with `/` is a command and stays one line: the new-line keys add
    nothing and a paste keeps its first line. It offers the `Input` members the screen uses: `value`,
    `cursor_position` (the offset in the whole text), `insert_text_at_cursor`, `placeholder`. Up on the first visual
    row and down on the last go to the screen's `pick`."""

    def __init__(self, *, placeholder="", id=None):
        super().__init__(placeholder=placeholder, id=id, soft_wrap=True, compact=True, highlight_cursor_line=False)

    @property
    def value(self):
        return self.text

    @value.setter
    def value(self, value):
        """Like `Input.value`: a change posts `Changed`, the cursor goes to the end."""
        if value != self.text:
            self.text = value
        self.cursor_position = len(value)

    @property
    def cursor_position(self):
        return self.document.get_index_from_location(self.cursor_location)

    @cursor_position.setter
    def cursor_position(self, position):
        self.move_cursor(self.document.get_location_from_index(max(0, min(position, len(self.text)))))

    def insert_text_at_cursor(self, text):
        self.replace(text, *self.selection, maintain_selection_offset=False)

    def on_text_area_changed(self, event):
        event.stop()
        self.post_message(Changed(self, self.text))

    async def _on_key(self, event):
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(Submitted(self, self.text))
        elif event.key in NEW_LINE_KEYS:
            event.stop()
            event.prevent_default()
            if not self.text.startswith("/"):
                self.insert_text_at_cursor("\n")

    async def _on_paste(self, event: events.Paste):
        event.stop()
        event.prevent_default()
        text = event.text.replace("\r\n", "\n").replace("\r", "\n")
        start = min(self.selection)
        if (self.text[:self.document.get_index_from_location(start)] + text).startswith("/"):
            text = text.split("\n")[0]  # the text would open a command: one line
        if text:
            self.insert_text_at_cursor(text)

    def visual_row(self):
        """The cursor's row in the wrapped text (0 is the first)."""
        return self.wrapped_document.location_to_offset(self.cursor_location).y

    def action_cursor_up(self, select=False):
        if self.visual_row() == 0:
            raise SkipAction()
        super().action_cursor_up(select)

    def action_cursor_down(self, select=False):
        if self.visual_row() >= self.wrapped_document.height - 1:
            raise SkipAction()
        super().action_cursor_down(select)
