"""S3a: whether the terminal is light, and the theme both apps mount with.

The choice is `ZPLAN_THEME` (dark, light, auto), else `ui.json` "theme", else auto; any other value reads as auto. Under
auto the terminal decides: `COLORFGBG` until the terminal answers an OSC 11 background query, the answer after. The
query is written by `Driver` (a `LinuxDriver`) and its reply is cut out of the input *before* Textual's parser sees it
(`remove_reply`), so a late reply never turns into key presses.
"""

from __future__ import annotations

from codecs import getincrementaldecoder
from collections import namedtuple
import os
import re
import selectors
import time

from textual import constants
from textual._parser import ParseError
from textual._xterm_parser import XTermParser
from textual.drivers.linux_driver import LinuxDriver

from . import strings

NAMES = ("dark", "light", "auto")
ENV = "ZPLAN_THEME"
QUERY = "\x1b]11;?\x1b\\"
REPLY = "\x1b]11;"
ENDS = ("\x07", "\x1b\\")
_COLOUR = re.compile(r"rgba?:([0-9a-f]{1,4})/([0-9a-f]{1,4})/([0-9a-f]{1,4})", re.IGNORECASE)
ALT_ENTER = "\x1b[13;3u"  # Option+Enter as Meta sends `ESC CR`, which the parser would read as Enter (a send)
TICK = 0.1  # the longest Textual's input loop waits for input

# `held`: input kept back (a strict prefix of REPLY, or a reply under way when `inside`); `since`: when it last grew.
State = namedtuple("State", "held since inside")
IDLE = State("", 0.0, False)


class Process:
    """What the process knows about the terminal, shared by every app and driver it runs."""

    def __init__(self):
        self.state = IDLE       # the input filter's state
        self.light = None       # the terminal's answer: True / False, None until it answers
        self.asked = False      # the query was written
        self.chosen = None      # a `/theme` choice made in this process: it wins over `ZPLAN_THEME`


process = Process()


def choice() -> str:
    """dark, light or auto: a `/theme` choice of this run, else `ZPLAN_THEME`, else the stored "theme", else auto."""
    value = process.chosen or os.environ.get(ENV, "").strip().lower() or strings.stored_theme() or "auto"
    return value if value in NAMES else "auto"


def theme_name() -> str:
    """`ansi-light` or `ansi-dark`: the choice, and under auto the terminal's answer, else `COLORFGBG`, else dark."""
    chosen = choice()
    if chosen == "auto":
        light = process.light
        if light is None:
            light = os.environ.get("COLORFGBG", "").split(";")[-1] in ("7", "15")
        chosen = "light" if light else "dark"
    return "ansi-" + chosen


def code_theme(name) -> str:
    """The Pygments theme for code under the app theme `name`: `ansi_light` under `ansi-light`, else `ansi_dark`."""
    return "ansi_light" if name == "ansi-light" else "ansi_dark"


def apply(app) -> None:
    """On the UI loop: a late answer changes the theme only under auto."""
    if choice() == "auto":
        app.theme = theme_name()


def choose(app, code) -> None:
    """`/theme CODE` (dark, light or auto): store the choice and apply it now. Auto reads the terminal's answer, else
    `COLORFGBG`, else dark. `ZPLAN_THEME` wins at start only: a choice made here stands over it, and over a late
    terminal answer."""
    strings.set_theme(code)
    process.chosen = code
    app.theme = theme_name()


def _luminance(reply):
    """The luminance (0..1) of `rgb:R/G/B` (1-4 hex digits a channel), None for anything else."""
    match = _COLOUR.fullmatch(reply)
    if not match:
        return None
    red, green, blue = (int(digits, 16) / (16 ** len(digits) - 1) for digits in match.groups())
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def remove_reply(state, chunk, now):
    """`(state, chunk, now) -> (state, output, light)`: `chunk` without an OSC 11 reply (`ESC ]11;` .. BEL or `ESC \\`).

    `light` is True / False when a reply ended in this chunk, else None. A strict prefix of `ESC ]11;` is held until
    the rest arrives or `constants.ESCAPE_DELAY` passes (then it goes on unchanged); a reply under way that stalls for
    that long is dropped. Everything else passes in order. Call it with an empty chunk to let a hold run out."""
    held, since, inside = state
    output, light = "", None
    if held and now - since >= constants.ESCAPE_DELAY:
        output = "" if inside else held
        held, inside = "", False
    data = held + chunk
    while data:
        if inside:
            ends = [(data.find(end, len(REPLY)), end) for end in ENDS if end in data[len(REPLY):]]
            if not ends:
                break
            at, end = min(ends)
            luminance = _luminance(data[len(REPLY):at])
            light = light if luminance is None else luminance > 0.5
            data, inside = data[at + len(end):], False
            continue
        at = data.find(REPLY)
        if at >= 0:
            output, data, inside = output + data[:at], data[at:], True
            continue
        keep = next((n for n in range(min(len(REPLY) - 1, len(data)), 0, -1) if REPLY.startswith(data[-n:])), 0)
        output, data = output + data[:len(data) - keep], data[len(data) - keep:]
        break
    if not data:
        return IDLE, output, light
    return State(data, now if chunk else since, inside), output, light


def hold_left(state, now):
    """Seconds until a hold in `state` runs out, None when nothing is held."""
    return max(0.001, state.since + constants.ESCAPE_DELAY - now) if state.held else None


class Fd:
    """The input the driver reads: a file descriptor."""

    def __init__(self, fileno):
        self.fileno = fileno
        self.selector = selectors.SelectSelector()
        self.selector.register(fileno, selectors.EVENT_READ)

    def ready(self, timeout):
        return bool(self.selector.select(timeout))

    def read(self):
        return os.read(self.fileno, 1024 * 4)

    def close(self):
        self.selector.close()


def read_input(source, stopped, deliver, found, debug=False, clock=time.monotonic):
    """Textual's `LinuxDriver.run_input_thread` with `remove_reply` before `parser.feed()`, and `ESC CR` (also when
    the two come in separate reads) turned into alt+enter.

    `source.ready(timeout)` / `source.read()` give bytes; `deliver(event)` gets each parsed event and `found(light)`
    each terminal answer. The shared filter state is `process.state`."""
    parser = XTermParser(debug)
    decode = getincrementaldecoder("utf-8")().decode

    def step(readable, final=False):
        text = ""
        if readable:
            text = decode(source.read(), final=final)
        now, before = clock(), process.state
        process.state, text, light = remove_reply(before, text, now)
        text = text.replace("\x1b\r", ALT_ENTER)
        if light is not None:
            found(light)
        if text:
            for event in parser.feed(text):
                deliver(event)
            if before.held and not before.inside and parser._timeout_time is not None:
                # a hold that ran out already waited the parser's ESCAPE_DELAY: a lone Escape is not late twice
                parser._timeout_time -= max(0.0, now - before.since)
        for event in parser.tick():
            deliver(event)

    try:
        while not stopped.is_set():
            left = hold_left(process.state, clock())
            step(source.ready(TICK if left is None else min(TICK, left)))
        step(source.ready(TICK), final=True)
    finally:
        source.close()
        try:
            for event in parser.feed(""):
                pass
        except (EOFError, ParseError):
            pass


class Driver(LinuxDriver):
    """`LinuxDriver` that asks the terminal its background once per process and keeps the reply out of the keys."""

    def start_application_mode(self):
        super().start_application_mode()
        if self._key_thread is not None and self.input_tty and not process.asked and "SSH_CONNECTION" not in os.environ:
            process.asked = True
            self.write(QUERY)
            self.flush()

    def run_input_thread(self):
        read_input(Fd(self.fileno), self.exit_event, self.process_message, self.found, self._debug)

    def found(self, light):
        """Input thread: remember the answer, apply it on the UI loop."""
        process.light = light
        self._loop.call_soon_threadsafe(apply, self._app)
