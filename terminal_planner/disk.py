"""Pure disk probe and thresholds behind the S5a guard (R-1, R-2, R-5 mechanics; which roots is s5a3).

Nothing here touches the real filesystem on its own: `probe` takes its `stat` and `usage` seams as arguments
(the only two calls it makes anywhere) and never creates, resolves or writes a path. The module raises no error
family of its own (the `disk.*` catalog entries arrive with the guard, s5a3), imports no product layer, and
prints and logs nothing — a caller wires the roots, the environment and the display.

The severity vocabulary (`ok`/`warn`/`block`, a warning keeps `ok=True`) is the one fixed by
`s5a1-warn-contract.md`; this module names severities but imports none of that slice's symbols.
"""

from dataclasses import dataclass
import os
import shutil

GIB = 2 ** 30
WARN_GIB = 15
DEFAULT_GIB = 5
MIN_FREE_ENV = "ZPLAN_MIN_FREE_GB"

_ASCII_DIGITS = frozenset("0123456789")


@dataclass(frozen=True)
class Probe:
    """One probed device: the roots that landed on it (input order), the first root's abspath and existing
    ancestor, its `st_dev`, the free bytes there, and the class name of any error (empty on success)."""

    names: tuple
    path: str
    ancestor: str
    device: object
    free: object
    error: str = ""


@dataclass(frozen=True)
class Verdict:
    """One classified device (or, first, the invalid configuration): severity `ok`/`warn`/`block`, the kind
    `ok`/`low`/`error`/`invalid_config`, and the probe's identity carried through for the caller's text.
    `threshold` is the effective block size in GiB for the compared (`low`/`ok`) verdicts and None otherwise
    (an `error` verdict compared no free value; an `invalid_config` verdict has no valid size)."""

    severity: str
    kind: str
    names: tuple
    path: str
    ancestor: str
    free: object
    threshold: object
    error: str


def threshold(environ=None):
    """The configured block size in GiB, or None for an invalid value. `environ` defaults to `os.environ` read
    at call time; an unset override is the 5 GiB default. A value counts only when it fully matches `[0-9]+`
    (ASCII digits): no sign, space, fraction, exponent, nan/inf or non-ASCII digit. Leading zeros are allowed and
    `int` string limits never apply — a 5000-digit value is valid."""
    raw = (os.environ if environ is None else environ).get(MIN_FREE_ENV)
    if raw is None:
        return DEFAULT_GIB
    if not raw or any(character not in _ASCII_DIGITS for character in raw):
        return None
    digits = raw.lstrip("0")
    if not digits:
        return None
    return _chunked_int(digits)


def _chunked_int(digits):
    """The exact integer for an ASCII digit string, accumulated in short chunks so Python's per-string `int`
    digit limit is never reached (the result stays an ordinary arbitrary-precision int)."""
    value = 0
    for start in range(0, len(digits), 9):
        chunk = digits[start:start + 9]
        value = value * 10 ** len(chunk) + int(chunk)
    return value


def probe(roots, stat=os.stat, usage=shutil.disk_usage):
    """Probe an ordered sequence of `(name, source)` roots and deduplicate by device.

    `source` is a path-like or a zero-argument callable returning one. Each root resolves to its nearest
    existing ancestor (the path itself, or the first parent whose `stat` succeeds; walking up only on
    `FileNotFoundError`/`NotADirectoryError`); its device is that `stat`'s `st_dev` and the free bytes are
    `usage(ancestor).free`, called once per device. Successful roots on one device become one `Probe` (names in
    input order, the first root's `path`/`ancestor`). `OSError` (incl. `PermissionError`), `RuntimeError` or
    `ValueError` from the source, `os.path.abspath`, `stat` or `usage` becomes that root's error `Probe` (or
    joins the device's, after a `usage` failure) carrying only the exception class name; the other roots are
    still probed. No path is created, resolved or written."""
    order = []
    device_index = {}
    for name, source in roots:
        try:
            value = source() if callable(source) else source
            path = os.path.abspath(os.fspath(value))
        except (OSError, RuntimeError, ValueError) as error:
            order.append({"names": [name], "path": "", "ancestor": "", "device": None, "free": None,
                          "error": type(error).__name__})
            continue
        try:
            ancestor, device = _existing_ancestor(path, stat)
        except (OSError, RuntimeError, ValueError) as error:
            order.append({"names": [name], "path": path, "ancestor": "", "device": None, "free": None,
                          "error": type(error).__name__})
            continue
        known = device_index.get(device)
        if known is not None:
            order[known]["names"].append(name)
            continue
        order.append({"names": [name], "path": path, "ancestor": ancestor, "device": device, "free": None,
                      "error": ""})
        device_index[device] = len(order) - 1
        try:
            order[-1]["free"] = usage(ancestor).free
        except (OSError, RuntimeError, ValueError) as error:
            order[-1]["error"] = type(error).__name__
    return tuple(Probe(names=tuple(entry["names"]), path=entry["path"], ancestor=entry["ancestor"],
                       device=entry["device"], free=entry["free"], error=entry["error"]) for entry in order)


def _existing_ancestor(path, stat):
    """(ancestor, device) for `path`: the path itself or the first parent `stat` accepts, walking up only while
    the path is missing. Any other `stat` failure leaves the caller to record it as that root's error."""
    candidate = path
    while True:
        try:
            return candidate, stat(candidate).st_dev
        except (FileNotFoundError, NotADirectoryError):
            parent = os.path.dirname(candidate)
            if parent == candidate:
                raise
            candidate = parent


def classify(probes, block_gib):
    """A tuple of frozen verdicts, invalid configuration first: with `block_gib` None one leading
    `("block", "invalid_config")` (no path) and the same probes classified against the 5 GiB default, so free
    space stays visible. Otherwise per probe: an error probe is `("warn", "error")`; block is tested first
    (`free < block_gib*GIB`), then warn (`free < WARN_GIB*GIB`), else `("ok", "ok")`. Equality to a threshold is
    not below it, so an override above 15 has no warn band. An error verdict carries `threshold=None` (no value
    was compared); the `low`/`ok` verdicts carry the effective block size."""
    verdicts = []
    if block_gib is None:
        verdicts.append(Verdict("block", "invalid_config", (), "", "", None, None, ""))
        block_gib = DEFAULT_GIB
    for item in probes:
        if item.error:
            verdicts.append(Verdict("warn", "error", item.names, item.path, item.ancestor, item.free, None,
                                    item.error))
        elif item.free < block_gib * GIB:
            verdicts.append(Verdict("block", "low", item.names, item.path, item.ancestor, item.free, block_gib,
                                    ""))
        elif item.free < WARN_GIB * GIB:
            verdicts.append(Verdict("warn", "low", item.names, item.path, item.ancestor, item.free, block_gib,
                                    ""))
        else:
            verdicts.append(Verdict("ok", "ok", item.names, item.path, item.ancestor, item.free, block_gib, ""))
    return tuple(verdicts)


def refusal(verdicts):
    """The first `block` verdict (an invalid_config verdict precedes every low one by `classify` order), or
    None. A root error never hides another device's block."""
    for verdict in verdicts:
        if verdict.severity == "block":
            return verdict
    return None
