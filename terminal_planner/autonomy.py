"""The architect's autonomy policy: what the Controller does by itself and what it asks the owner to do.

Data only. The level comes from the accepted process profile (`zplan.process.json`, section `autonomy`, key
`level`), read from the same live profile the delivery service enforces — never from a caller's value, so the
policy and the action can never disagree about which profile is in effect. `level_of` reads a profile status the
caller already resolved once, so the Controller decides on the very digest its preview was built on. `decide` is
the whole policy: the Controller consults it before an action runs. `AUTOMATIC` is the release gate the plan
named: with A4b and A7 merged (2026-10-25) automatic actions are on, so auto and supervised let the architect
start, resume and re-brief; the merge action follows the level and the candidate's risk tier."""

from .authority import Blocked

LEVELS = ("auto", "supervised", "manual")
ACTIONS = ("start", "stop", "approve", "resume", "rebrief", "edit", "merge")

# The release gate the plan named: automatic actions stay off until A4b and A7 are merged. Both are merged
# (2026-10-25), so it is True and auto and supervised let the architect start, resume and re-brief; manual asks.
AUTOMATIC = True


def decide(level, action, gate=None, tier=None):
    """What the Controller does with `action` at `level`: "allow" or "ask".

    stop is always allowed: it ends an attempt and merges nothing, so no autonomy level gates it. edit is allowed at
    every level: it only proposes a new revision, and the approval that lets it run stays gated, so a proposal is
    never an unreviewed action. start asks at every level while `AUTOMATIC` is off; with it on, auto and supervised
    allow and manual asks. resume and rebrief follow start (they open a new attempt, from an unchanged brief).
    approve asks at every level while `AUTOMATIC` is off; with it on only auto allows it, so supervised and manual
    plan approvals stay the owner's. merge follows the level and the candidate's risk `tier` (low, medium or high,
    from `process.risk_of`): auto allows it, supervised allows it below high and asks on high or on a tier it does
    not know, manual asks. The merge gate (`gate`, `gates.merge`) only decides whether checks and the critic run
    before the merge; it does not change who merges. An unknown level is manual and asks; an unknown action asks
    (fail closed)."""
    if action == "stop" or action == "edit":
        return "allow"
    if action == "merge":
        return "allow" if level == "auto" or (level == "supervised" and tier in ("low", "medium")) else "ask"
    if action in ("start", "resume", "rebrief"):
        if not AUTOMATIC:
            return "ask"
        return "allow" if level in ("auto", "supervised") else "ask"
    if action == "approve":
        if not AUTOMATIC:
            return "ask"
        return "allow" if level == "auto" else "ask"
    return "ask"


def merge_gate(status):
    """The merge gate of an already-resolved profile status: `gates.merge` ("required" / "off"), or None without a
    resolved configuration. The Controller reads it once with the policy's own status read, so the decision and the
    `expected` digest the merge is bound to come from the same profile."""
    resolved = getattr(status, "resolved", None)
    return resolved.config.get("gates", {}).get("merge") if resolved is not None else None


def level(profile):
    """The autonomy level of the accepted profile, "manual" when there is none or it cannot be read.

    `/1` carries no `autonomy` section and a profile that is not accepted has none to read, so both answer
    "manual"; a value outside `LEVELS` is manual too. Reads the profile only (`write=False`), and never raises: a
    status that cannot be read is still a session the owner must confirm by hand."""
    return level_of(status_of(profile))


def status_of(profile):
    """The accepted profile's status as the policy reads it: `profile.status(write=False)`, or None when there is no
    profile or it cannot be read (a `Blocked`, `OSError` or `ValueError` from a corrupt or deleted store). The
    Controller reads it once, so the digest it compares against the preview and the level it decides on are the same
    read; the owner-facing "unreadable is manual" rule is `level_of(None)`."""
    if profile is None:
        return None
    try:
        return profile.status(write=False)
    except (Blocked, OSError, ValueError):
        return None


def level_of(status):
    """The autonomy level of an already-resolved profile status (the Controller reads it once and keeps the same
    digest for the preview and the policy); None, an unresolved or an unknown value is "manual"."""
    resolved = getattr(status, "resolved", None)
    value = resolved.config.get("autonomy", {}).get("level") if resolved is not None else None
    return value if value in LEVELS else "manual"
