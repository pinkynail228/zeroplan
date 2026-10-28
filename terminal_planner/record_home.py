"""The Codex home a record acts in: the pure core shared by the engine wiring (s2a2) and the architect continuation
(s2a3). This slice adds the resolver only; no caller uses it yet (R-4).

A binding recorded from 0.5 on carries `codex_home` (R-2); a pre-0.5 record carries the four identity fields alone,
and then the home is the one the owner started zplan with — `setup.legacy_codex_home()`, read from `os.environ` at
call time (R-1), never from an env zplan has modified. Nothing here resolves, creates or checks the recorded path
(R-3): a missing recorded home is passed through as is and the engine's own error surfaces (R-4).
"""

from pathlib import Path

from . import setup, toolchain


def effective_home(recorded):
    """The home to use for a recorded `codex_home`: the recorded absolute path as is, or the legacy process home for
    a pre-0.5 record (`None`). Every other value is a ValueError: only `None` means "no recorded home"."""
    if recorded is None:
        return setup.legacy_codex_home()
    if not toolchain.valid_codex_home(recorded):
        raise ValueError("Invalid recorded codex_home: %r." % (recorded,))
    return Path(recorded)


def binding_home(binding):
    """The home a record frozen with `binding` starts in: its recorded `codex_home`, else the legacy process home.

    Every invalid binding — the fixture binding included — and every malformed native field (a non-dict, or e.g.
    `version=None`) is a ValueError, never the TypeError/AttributeError the shape check itself raises."""
    try:
        valid = toolchain.valid_binding(binding)
    except (TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Invalid native binding: %r." % (binding,))
    return effective_home(binding.get("codex_home"))
