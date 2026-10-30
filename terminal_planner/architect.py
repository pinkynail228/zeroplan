"""Architect adapter: an advisory, read-only Codex conversation per project, with no UI and no lifecycle actions.

One owner message is one `codex exec` / `codex exec resume` turn; the thread id, usage and transcript live in a private
store outside the checkout. This module never touches planning.json, Authority or MilestoneRuns.

Flag sources. The pinned Codex is toolchain.DEFAULT.codex (setup.tool_paths). Its CLI source and `--help` were not
available to this change (no upstream/ checkout in the worktree, executing Codex was not permitted, no network), so no
flag below is verified against the pinned Codex by this module's author. The flags are the ones the task prescribes,
which match the Codex `exec` CLI: `--json`, `-s/--sandbox`, `-C/--cd`, `-m/--model`, `-c/--config key=value`, stdin prompt via `-`, and the
`exec resume <id>` subcommand. `verify_cli` probes the real executable's `--help` for every long flag used and returns
the missing ones; a caller that gates on it fails closed. Order of flags after `resume <id>` is prescribed by the task
and must be confirmed by that gate.
"""

import errno
import fcntl
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

from . import project_read, record_home, setup, toolchain
from .authority import Blocked

MAX_LINE = 1 << 20           # one JSONL line
MAX_TEXT = 64 * 1024         # one message kept in the result
MAX_MESSAGES = 100           # messages kept per turn
MAX_EVENT_TEXT = 4000        # text handed to the UI callback per event
MAX_STDERR = 8 * 1024        # stderr tail
KILL_GRACE = 2.0             # seconds between SIGTERM and SIGKILL, and for orphans holding the pipe
MAX_CONTEXT_ITEM = 200
MAX_CONTEXT_SUMMARY = 4000
MAX_CONTEXT_MILESTONES = 50
MAX_DRAFT_TEXT = 4000        # characters of one draft body; a longer block stays ordinary text
MAX_DRAFTS = 5               # draft blocks taken from one reply; the blocks after it stay ordinary text

STATUSES = ("completed", "failed", "cancelled", "lost_session")
THREAD_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z_.:-]{0,127}\Z")
DRAFT_FENCE = "```"
DRAFT_GOAL = "```zplan-goal"
DRAFT_ANSWER = re.compile(r"```zplan-answer (\S+)\Z")
NO_PLAN = "no plan"          # the plan identity of a snapshot that names no revision
LOST = re.compile(r"no rollout found|no (?:saved )?(?:session|thread|conversation)\b"
                  r"|(?:thread|session|conversation)\b[^\n]{0,60}(?:not found|does not exist|no longer exists|missing)", re.I)
AUTH = re.compile(r"\b401\b|unauthori[sz]ed|not logged in|log in|login|authenticat|api key|credential|forbidden|\b403\b", re.I)

# The draft protocol as the architect is told it, in every prompt that can start a turn: the preamble of a first
# turn and the state update of a resumed one (a saved thread id means the architect has a history, not that it
# remembers the last prompt). `parse_drafts` is the one implementation of the format these lines describe.
DRAFT_RULES = (
    "Draft blocks (zplan shows each draft to the owner as a card with buttons; never ask the owner to copy or send",
    "a draft, and you never write proposal, approval or run state):",
    "- A proposed goal goes in one fenced block: a line that is exactly ```zplan-goal, then the goal text, then a",
    "  line that is exactly ```.",
    "- A proposed answer for a milestone goes in the same fence, opened with exactly ```zplan-answer <milestone id>.",
    "- A block holds its draft text only: at most 4000 characters, and an empty block means nothing. Anything else,",
    "  and any block inside another fenced block, is ordinary text.",
    "- At most 5 draft blocks in one reply; the blocks after them stay ordinary text.",
    "- A goal describes the product change only; merging into main is the owner's /merge step and never goal text.",
)

# The tools the architect may call, as every prompt that can start a turn states them (the preamble of a first turn
# and the update of a resumed one): the model only asks; the Controller decides what runs and what it must ask the
# owner to do. `architect_tools.TOOLS` is the machine-readable form of the same list.
TOOL_RULES = (
    "Tools (your only actions; the Controller decides what runs):",
    "- zplan_list_files, zplan_read_file and zplan_search read the project's git-tracked and untracked files",
    "  (credential files are refused). The one write is the project STATE file: zplan_state reads it and",
    "  zplan_state_update replaces it; no other file can be written.",
    "- zplan_status reports this session's requests (queued, running, done with a result), the current plan",
    "  revision (its status, gate verdict and the critic's findings) and the milestones (state, attempt, run id, token).",
    "- zplan_start {milestone, revision} asks to start a run; zplan_stop {milestone, run_id} asks to stop one.",
    "- zplan_approve_plan {revision} asks to approve the current plan revision. When the plan status is",
    "  review_exhausted never call it: say the check rejected the plan and point to the card on the main screen.",
    "- zplan_resume {milestone, token} asks to resume a recoverable attempt, named by its status row's token.",
    "- zplan_rebrief {milestone, token, note} asks for a new attempt with a note; the brief itself is unchanged.",
    "- zplan_edit_plan {revision, plan} asks to save an edited proposal (the full edited plan) as a new revision;",
    "  the Controller refuses when the revision is not current, the plan is invalid, or the edit changes nothing.",
    "  Use it only for an edit whose exact text the owner gave.",
    "- zplan_revise_plan {revision, feedback} asks the planner for a new revision from written feedback. After a",
    "  rejected check, read the findings in zplan_status (plan.findings) and call it naming them. A revision you",
    "  made that the check rejects again is the owner's to decide: the tool refuses.",
    "- zplan_merge {milestone, token} asks to merge the attempt named by its status row's token; a refusal naming",
    "  merge.critic_pending means the merge is not decided yet: call merge again with the same token.",
    "- zplan_propose_commit {paths, message} offers the owner to commit their own uncommitted files; it commits",
    "  nothing: the owner answers a card (the diff stat, your message), and only their «yes» commits those files.",
    "  You get the stat and a scrubbed diff back, never file content; credential files are refused.",
    "- The pinned Codex code tool calls a tool as `await tools.mcp__zplan__zplan_status({})`: the same",
    "  `mcp__zplan__` prefix for every zplan tool, the arguments as one object. Never list `ALL_TOOLS` to find a name.",
    "- The Controller applies its gates and the owner's autonomy policy to every action: it may refuse (a stale",
    "  revision, a missing profile) or answer that the owner must act with their own key. Start, resume and",
    "  re-brief follow the profile's autonomy level (at `manual` the owner acts); a plan approval is automatic only",
    "  at `auto`; a plan edit or revision is always allowed (it only proposes; its approval is gated). An approval",
    "  over a rejected critic, an override or a rejection, a push, tags, and deleting branches with unmerged work",
    "  stay the owner's (merged branches are cleaned up by the merge itself). Never claim an action happened until",
    "  zplan_status shows it done, and never claim that you did it yourself.",
    "- Call the tool. When the level leaves the action to the owner the call becomes a card for them (a start,",
    "  continue or new attempt, the plan, a merge): say in one line that the card is there; never ask for a yes in",
    "  the chat. Report it as requested, not done, until zplan_status shows it done.",
)

# R-5: the recorded home of a resumed thread is gone. The text names the home (tilde) and the reason, then the
# rollover the owner has: Ctrl+R ("new dialog") starts a new thread in the current home. Never a credential or a
# variable value: the reason is the kind of login that is missing, never what it held.
HOME_LOST = ("The recorded CODEX_HOME %s is unavailable (%s). Press Ctrl+R («new dialog») to start a new "
             "dialog in the current home.")
HOME_MISSING = "folder not found"
HOME_NO_FILE_AUTH = "no Codex login (auth.json)"
HOME_NO_ENV_AUTH = "login variable is not set"

CAUSE_CANCELLED = "The turn was cancelled by the owner."
CAUSE_LOST = "The architect session is lost (Codex did not find the saved dialog). Start a new dialog (reset)."
CAUSE_AUTH = "Codex rejected the authorization: run zplan login and repeat the message."
# Catalog family of a turn that did not complete; an authorization failure is a failed turn with CAUSE_AUTH.
FAMILIES = {"cancelled": "architect.cancelled", "lost_session": "architect.lost_session", "failed": "architect.failed"}


def family(result):
    """The terminal_planner.catalog error family of a TurnResult (None when it completed). Reserved for the
    architect chat screen; no caller shows these families yet."""
    return "architect.auth" if result.cause == CAUSE_AUTH else FAMILIES.get(result.status)

# Long names the adapter relies on, checked by verify_cli against the executable's own help text.
REQUIRED_HELP = {
    ("exec",): ("--json", "--sandbox", "--cd", "--model", "--config"),
    ("exec", "resume"): ("--json", "--model", "--config"),
    ("mcp", "list"): ("--json", "--config"),
}
# Codex merges `-c mcp_servers=...` into the owner's config and starts the plugins' servers and the apps server
# (`codex_apps`, absent from `codex mcp list`) too, so every turn turns plugins and apps off and disables each other
# configured server by name (see `foreign_servers`).
FEATURES_OFF = ("-c", "features.plugins=false", "-c", "features.apps=false")
OWN_SERVER = "zplan"
LIST_TIMEOUT = 10


def _toml_string(value):
    """A TOML basic string: backslash, quote and control characters escaped."""
    return '"' + "".join("\\" + ch if ch in '\\"' else "\\u%04x" % ord(ch) if ord(ch) < 0x20 or ord(ch) == 0x7F else ch
                         for ch in value) + '"'


def mcp_servers_config(project, disabled=(), controller=None):
    """`-c` value: zplan's own tools in a frozen interpreter, and `<name>={enabled=false}` for each server of the
    owner's config named in `disabled`. `controller` is the live Controller's socket path (the action tools reach
    it there); no path leaves the action tools answering `architect.controller_unavailable`."""
    if not Path(sys.executable).is_absolute():
        raise Blocked("The Python interpreter path is unknown; the architect MCP server cannot be frozen.",
                      family="architect.invalid_config")
    root = Path(__file__).resolve().parent.parent
    code = ("import sys; sys.path.insert(0, %s); from terminal_planner.architect_tools import main; "
            "sys.exit(main(sys.argv[1:]))" % json.dumps(str(root)))
    args = ["-I", "-c", code, "--project", project] + (["--controller", str(controller)] if controller else [])
    entries = ["%s={command=%s, args=[%s], default_tools_approval_mode=\"approve\"}" % (
        OWN_SERVER, _toml_string(sys.executable), ", ".join(_toml_string(a) for a in args))]
    entries += ["%s={enabled=false}" % _toml_string(name) for name in disabled if name != OWN_SERVER]
    return "mcp_servers={%s}" % ", ".join(entries)


def mcp_overrides(project, disabled=(), controller=None):
    """The `-c` pairs that decide which MCP servers a turn starts (the same for the turn and for its listings)."""
    return [*FEATURES_OFF, "-c", mcp_servers_config(project, disabled, controller)]


def build_argv(executable, project, model, effort, thread_id=None, disabled=(), controller=None):
    """Exact argv; the prompt always goes through stdin (`-`). Nothing here can widen the sandbox. `controller` is
    the live Controller's socket path, passed to zplan's own MCP server (`--controller`)."""
    executable, project, model, effort = str(executable), str(project), str(model), str(effort)
    for name, value in (("executable", executable), ("project", project), ("model", model), ("effort", effort)):
        if not value or "\0" in value:
            raise Blocked("Invalid architect parameter: %s." % name, family="architect.invalid_config")
    if model.startswith("-") or effort.startswith("-"):
        raise Blocked("Invalid architect model or effort.", family="architect.invalid_config")
    if thread_id is None:
        return [executable, "exec", "--json", "-s", "read-only", "-C", project, "-m", model,
                "-c", "model_reasoning_effort=" + effort, "-c", 'approval_policy="never"',
                *mcp_overrides(project, disabled, controller), "-"]
    if not isinstance(thread_id, str) or not THREAD_ID.match(thread_id):
        raise Blocked("Invalid architect thread id.", family="architect.invalid_config")
    return [executable, "exec", "resume", thread_id, "--json", "-m", model,
            "-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"',
            "-c", "model_reasoning_effort=" + effort, *mcp_overrides(project, disabled, controller), "-"]


def _enabled_servers(executable, environment, cwd, overrides):
    """Names of the MCP servers `codex mcp list --json` reports enabled under `overrides`, in this env.

    Any failure to list (launch, exit code, timeout, JSON shape) refuses the turn: an unknown server set is not a
    sandbox the architect may start in."""
    def refuse(reason):
        return Blocked("Could not check the Codex MCP servers (%s); the architect turn was not started." % reason,
                       family="architect.foreign_tools")
    try:
        result = subprocess.run([str(executable), "mcp", "list", "--json", *overrides], capture_output=True,
                                text=True, timeout=LIST_TIMEOUT, env=dict(environment), cwd=str(cwd),
                                stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise refuse("timeout %g s" % LIST_TIMEOUT) from None
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise refuse(error.__class__.__name__) from error
    if result.returncode != 0:
        raise refuse("exit code %d" % result.returncode)
    try:
        listing = json.loads(result.stdout)
    except ValueError:
        raise refuse("the reply is not JSON") from None
    if not isinstance(listing, list) or not all(isinstance(item, dict) and isinstance(item.get("name"), str)
                                                for item in listing):
        raise refuse("unexpected reply shape")
    return [item["name"] for item in listing if item.get("enabled") is True]


def foreign_servers(executable, environment, project, controller=None):
    """The servers to disable for a turn, after proving that with them disabled only zplan's own is enabled.

    Raises Blocked (`architect.foreign_tools`) naming the servers that stay enabled, or zplan's own when missing."""
    project = str(project)
    disabled = sorted({name for name in _enabled_servers(executable, environment, project, list(FEATURES_OFF))
                       if name != OWN_SERVER})
    left = _enabled_servers(executable, environment, project, mcp_overrides(project, disabled, controller))
    if set(left) != {OWN_SERVER}:
        names = sorted(set(left) - {OWN_SERVER})
        raise Blocked("The architect has foreign Codex MCP servers enabled: %s; the turn was not started." % ", ".join(names)
                      if names else "The zplan MCP server is not visible to the architect's Codex; the turn was not started.",
                      family="architect.foreign_tools")
    return disabled


def verify_cli(executable, environment, timeout=30):
    """Return the required flags the executable's `--help` does not mention (empty list = all present)."""
    missing = []
    for command, flags in REQUIRED_HELP.items():
        try:
            result = subprocess.run([str(executable), *command, "--help"], capture_output=True, text=True,
                                    timeout=timeout, env=dict(environment), stdin=subprocess.DEVNULL)
            text = result.stdout + result.stderr
            ok = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            text, ok = "", False
        for flag in flags:
            if not ok or flag not in text:
                missing.append(" ".join(command) + " " + flag)
    return missing


# --- context -----------------------------------------------------------------------------------------------------

def _clip(value, limit=MAX_CONTEXT_ITEM):
    text = " ".join(str(value if value is not None else "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _state_section(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    lines = ["Project: " + (_clip(snapshot.get("project")) or "(unknown)"),
             "Branch: " + (_clip(snapshot.get("branch")) or "(unknown)")]
    uncommitted = snapshot.get("uncommitted")
    uncommitted = [_clip(path) for path in uncommitted] if isinstance(uncommitted, (list, tuple)) else []
    if uncommitted:  # the project tools show the last commit: these edits are the owner's and are not in what they read
        lines.append("Uncommitted (not in what zplan reads): " + project_read.shown_paths(uncommitted))
    summary = str(snapshot.get("plan_summary") or "").strip()
    lines.append("Plan summary: " + (summary[:MAX_CONTEXT_SUMMARY] if summary else "(no approved plan yet)"))
    milestones = snapshot.get("milestones")
    milestones = milestones if isinstance(milestones, (list, tuple)) else []
    lines.append("Milestones:" + ("" if milestones else " (none)"))
    for item in milestones[:MAX_CONTEXT_MILESTONES]:
        if isinstance(item, dict):
            title = _clip(item.get("title"))
            lines.append("- %s%s: %s" % (_clip(item.get("id")), " " + title if title else "", _clip(item.get("state")) or "unknown"))
        else:
            lines.append("- " + _clip(item))
    if len(milestones) > MAX_CONTEXT_MILESTONES:
        lines.append("- … %d more" % (len(milestones) - MAX_CONTEXT_MILESTONES))
    return "\n".join(lines)


PROJECT_METHOD = "zplan.architect.md"


def method(project=None):
    """The architect method: `<project>/zplan.architect.md` when it holds text, else the shipped one (preset
    zplan.default, the packaged text read through `importlib.resources`). Invalid UTF-8 bytes of the project file
    are replaced; a missing or unreadable file is the same as an empty one."""
    if project is not None:
        try:
            text = (Path(project) / PROJECT_METHOD).read_bytes().decode("utf-8", errors="replace").strip()
        except OSError:
            text = ""
        if text:
            return text
    data = resources.files("terminal_planner").joinpath("resources", "architect_method.md").read_bytes()
    return data.decode("utf-8").strip()


def build_preamble(snapshot, project=None):
    """First-turn instructions, the method (the project's own or the shipped one) and a read-only state snapshot
    supplied by the caller. Deterministic for the same files."""
    return "\n".join([
        "You are the zplan architect: you lead delivery for the project owner within the autonomy level the",
        "Controller enforces.",
        "Reply to the owner concisely, in the language of the owner's last message. A turn with no owner message",
        "(an event update, a session warm-up) is answered in English.",
        "Rules:",
        "- You may read the project files and ask the Controller to act; the one write you have is the project",
        "  STATE file through zplan_state_update. You cannot and must not modify other files, run state-changing",
        "  commands, or start other agents yourself.",
        "- When you propose a goal or an answer for a milestone, mark it clearly as a draft; the owner reviews it",
        "  and sends it through the normal planner -> verifier -> approval path.",
        "",
        method(project),
        "",
        "\n".join(TOOL_RULES),
        "",
        "\n".join(DRAFT_RULES),
        "",
        "Current state (read-only snapshot; it may be stale later in the conversation):",
        _state_section(snapshot),
        "",
        "Owner message follows.",
        "",
    ])


def build_update(snapshot):
    """Compact state refresh prepended to a resumed turn, draft protocol included.

    A resumed turn has no preamble, so the protocol of `DRAFT_RULES` is repeated here: a saved thread id means the
    architect has a history, not that it still has the format of its drafts."""
    return ("Updated state snapshot (read-only):\n" + _state_section(snapshot) + "\n\n"
            + "\n".join(TOOL_RULES) + "\n\n" + "\n".join(DRAFT_RULES) + "\n\nOwner message follows.\n\n")


# --- drafts ------------------------------------------------------------------------------------------------------

def _draft_opener(line):
    """(kind, milestone) of a draft opener line, or None: the line must be exactly one of the two forms."""
    if line == DRAFT_GOAL:
        return "goal", None
    found = DRAFT_ANSWER.match(line)
    return ("answer", found.group(1)) if found else None


def _skip_fence(lines, index):
    """The index after the fenced block opened at `index` (or the end of the text): its body, zplan-looking lines
    included, is quoted text and never a draft."""
    end = index + 1
    while end < len(lines) and lines[end] != DRAFT_FENCE:
        end += 1
    return end + 1


def draft_spans(text):
    """Every draft fence of `text`, in order, as `(start, end, kind, milestone, raw)`.

    `start` is the line index of the opener and `end` the line index just after the closing fence; `kind` and
    `milestone` are `_draft_opener`'s pair and `raw` is the body exactly as it stands between the fences
    (untrimmed, the size `MAX_DRAFT_TEXT` bounds). Only a well-formed closed fence opened by an exact opener line
    is yielded: a fence that is no opener — and everything inside it, a zplan-looking block included — is quoted
    text and skipped whole, and an unclosed opener ends the scan (the same rule `parse_drafts` states). The one
    iterator serves both the parser and the pane, so the two can never disagree about where a source span is."""
    lines = str(text or "").split("\n")
    index = 0
    while index < len(lines):
        opener = _draft_opener(lines[index])
        if opener is None:
            index = _skip_fence(lines, index) if lines[index].startswith(DRAFT_FENCE) else index + 1
            continue
        end = index + 1
        while end < len(lines) and lines[end] != DRAFT_FENCE:
            end += 1
        if end >= len(lines):  # an unclosed fence: it and the rest of the reply are not drafts either
            break
        yield (index, end + 1, opener[0], opener[1], "\n".join(lines[index + 1:end]))
        index = end + 1


def _milestone_tokens(snapshot):
    """{milestone id: its plain attempt token} for the milestones the snapshot names (a token may be None)."""
    items = snapshot.get("milestones") if isinstance(snapshot, dict) else None
    items = items if isinstance(items, (list, tuple)) else []
    return {item["id"]: item.get("token") for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), str)}


def draft_body(raw):
    """The trimmed body of one draft block, or None when the protocol's body rule rejects it.

    The rule is the one `DRAFT_RULES` states and `_draft_record` enforces: a body is its trimmed text, and an
    empty body means nothing; `MAX_DRAFT_TEXT` bounds the body as it stands between the fences, before the trim,
    so a space and 4000 characters is over the limit while 4000 characters with no padding are not. The parser
    and the pane's source-span match both read this one rule, so a span the parser would never have recorded can
    never take a record the pane holds: eligibility is settled before any record is consumed."""
    body = raw.strip()
    return body if body and len(raw) <= MAX_DRAFT_TEXT else None


def plan_identity(snapshot):
    """The plan identity of one turn's snapshot: "no plan", or the plain pair [revision, state].

    `state` is the plan state the controller snapshot names for that revision (`{status, override}`): the revision
    number alone cannot tell a submitted revision from a ready or approved one, and an owner override keeps the
    approved status while being a state of its own. None when the snapshot is missing or names no state for its
    revision: a draft then has no identity to carry, and is not actionable.

    The confirmed absence of a plan is `revision: None` (`NO_PLAN`). A snapshot that does not say which revision
    it is at all — no `revision` key, as the projection of a screen whose first refresh has not arrived yet —
    names no identity either: an unknown state is not the absence of a plan, and a draft of such a turn is not
    actionable."""
    if not isinstance(snapshot, dict) or "revision" not in snapshot:
        return None
    revision = snapshot["revision"]
    if revision is None:
        return NO_PLAN
    state = snapshot.get("plan_state")
    return [revision, state] if state is not None else None


def _draft_record(kind, milestone, raw, snapshot, tokens, count):
    """One recognised block as plain data, or None when it breaks a rule and stays ordinary text.

    `raw` is the body exactly as it stood between the fences; `draft_body` owns the body rule (see its docstring)
    and `count` the five-block budget of `MAX_DRAFTS`."""
    body = draft_body(raw)
    if count >= MAX_DRAFTS or body is None:
        return None
    if kind == "goal":
        return {"kind": "goal", "text": body, "milestone": None, "identity": plan_identity(snapshot)}
    if milestone not in tokens:  # the answer id must be a milestone of the turn's snapshot
        return None
    return {"kind": "answer", "text": body, "milestone": milestone, "identity": tokens[milestone]}


def parse_drafts(text, snapshot=None):
    """The draft blocks of one architect reply, as plain data.

    Called only with the final text of a successfully completed turn: streamed, cancelled and failed text is never
    parsed. Each record is `{"kind", "text", "milestone", "identity"}`; `identity` is `plan_identity(snapshot)` for
    a goal and the milestone's plain attempt token for an answer, None when the snapshot could name none (the
    caller then has no provenance and the draft is not actionable). A block that breaks one of the rules of
    `DRAFT_RULES` — an unknown milestone, an unclosed fence, an empty or oversized body, a zplan fence inside
    another fenced block, or one of the blocks past `MAX_DRAFTS` — is ordinary text and is not returned."""
    tokens = _milestone_tokens(snapshot)
    drafts = []
    for _start, _end, kind, milestone, raw in draft_spans(text):
        record = _draft_record(kind, milestone, raw, snapshot, tokens, len(drafts))
        if record is not None:
            drafts.append(record)
    return drafts

# --- store -------------------------------------------------------------------------------------------------------

def _stamp(clock):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))


def project_key(project):
    resolved = Path(project).expanduser().resolve()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", resolved.name).strip("-.")[:40] or "project"
    return slug + "-" + hashlib.sha256(str(resolved).encode()).hexdigest()[:12]


def _private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def _write_atomic(path, text):
    descriptor, name = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


class ArchitectStore:
    """architect/<project key>/{session.json, transcript.jsonl, lock} under the data root; never in the project."""

    def __init__(self, project, root=None, clock=time.time):
        self.project = Path(project).expanduser().resolve()
        base = Path(root) if root is not None else setup.data_root() / "architect"
        self.directory = base / project_key(self.project)
        self.session_path = self.directory / "session.json"
        self.transcript_path = self.directory / "transcript.jsonl"
        self.lock_path = self.directory / "lock"
        self.clock = clock
        _private_directory(self.directory.parent)
        _private_directory(self.directory)

    def load(self):
        """The stored session, or None. A session without `codex_home` is a pre-0.5 session and loads unchanged;
        a present `codex_home` must satisfy R-2's shape rule and a session that records a home must record a thread,
        else the file is `architect.session_corrupt`."""
        try:
            text = self.session_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            value = json.loads(text)
            ok = False
            if isinstance(value, dict):
                thread = value["thread_id"]
                # R-5: the field is optional, but a present value -- an explicit null included -- must pass
                # valid_codex_home, and a session that carries a home must carry a thread.
                home_ok = ("codex_home" not in value
                           or (thread is not None and toolchain.valid_codex_home(value["codex_home"])))
                ok = ((thread is None or (isinstance(thread, str) and THREAD_ID.match(thread)))
                      and isinstance(value.get("turns"), int) and isinstance(value.get("usage"), dict)
                      and home_ok)
        except (ValueError, KeyError, TypeError):
            ok = False
        if not ok:
            raise Blocked("The architect session file is corrupted: %s. Delete it to start a new dialog." % self.session_path, family="architect.session_corrupt")
        return value

    def save(self, session):
        session = dict(session, updated=_stamp(self.clock))
        _write_atomic(self.session_path, json.dumps(session, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        return session

    def append(self, role, **fields):
        entry = {"ts": _stamp(self.clock), "role": role, **fields}
        line = (json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        descriptor = os.open(self.transcript_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, line)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return entry

    def transcript(self):
        entries = []
        try:
            with self.transcript_path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict):
                        entries.append(value)
        except FileNotFoundError:
            pass
        return entries


# --- turn --------------------------------------------------------------------------------------------------------

class TurnResult:
    def __init__(self):
        self.status = "failed"
        self.text = ""             # final answer (last completed agent message) when completed
        self.partial = ""          # last message text seen when the turn did not complete
        self.messages = []
        self.usage = {}
        self.cause = ""            # plain English cause for the owner
        self.detail = ""           # capped raw provider/process detail for diagnosis
        self.thread_id = None
        self.drafts = []           # the recognised draft blocks of the final reply, as plain data; [] otherwise
        self.exit_code = None
        self.stderr_tail = ""
        self.unknown_events = 0
        self.malformed_lines = 0
        self.events = 0

    def as_dict(self):
        return dict(vars(self))


def _cap(text, limit):
    text = text if isinstance(text, str) else ""
    return text if len(text) <= limit else text[:limit] + "…[truncated]"


def _ints(value):
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)} \
        if isinstance(value, dict) else {}


class _Turn:
    """Incremental JSONL state for one process."""

    def __init__(self, resumed, thread_id, persist, notify):
        self.resumed, self.thread_id, self.persist, self.notify = resumed, thread_id, persist, notify
        self.result = TurnResult()
        self.order, self.texts = [], {}
        self.completed = False
        self.failures = []       # provider-reported failure/error messages, in order

    def emit(self, **event):
        if "text" in event:
            event["text"] = _cap(event["text"], MAX_EVENT_TEXT)
        try:
            self.notify(event)
        except Exception:  # a UI callback must never break the turn
            pass

    def feed(self, raw):
        result = self.result
        try:
            event = json.loads(raw)
        except ValueError:
            event = None
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            result.malformed_lines += 1
            return
        result.events += 1
        kind = event["type"]
        if kind == "thread.started":
            thread = event.get("thread_id")
            if isinstance(thread, str) and THREAD_ID.match(thread):
                if self.thread_id is None:
                    self.thread_id = thread
                    self.persist(thread)
                self.emit(kind="thread", phase="started", thread_id=self.thread_id)
            else:
                result.malformed_lines += 1
        elif kind == "turn.started":
            self.emit(kind="turn", phase="started")
        elif kind in ("item.started", "item.updated", "item.completed"):
            self.item(kind.split(".", 1)[1], event.get("item"))
        elif kind == "turn.completed":
            self.completed = True
            usage = _ints(event.get("usage"))
            # Codex reports the thread's running total, not the turn's: the last report is the total.
            result.usage = usage
            self.emit(kind="usage", usage=usage)
        elif kind == "turn.failed":
            error = event.get("error")
            message = error.get("message") if isinstance(error, dict) else error
            self.failures.append(_cap(message if isinstance(message, str) else "turn.failed", 2000))
            self.emit(kind="failed", text=self.failures[-1])
        elif kind == "error":
            message = event.get("message")
            self.failures.append(_cap(message if isinstance(message, str) else "error", 2000))
            self.emit(kind="error", text=self.failures[-1])
        else:
            result.unknown_events += 1
            self.emit(kind="unknown", type=_cap(kind, 80))

    def item(self, phase, item):
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            self.result.malformed_lines += 1
            return
        item_type, ident = item["type"], item.get("id")
        text = item.get("text") if isinstance(item.get("text"), str) else ""
        if item_type == "agent_message":
            key = ident if isinstance(ident, str) else "#%d" % len(self.order)
            if key not in self.texts:
                self.order.append(key)
            self.texts[key] = (_cap(text, MAX_TEXT) if text else self.texts.get(key, ""), phase == "completed")
            self.emit(kind="message", phase=phase, id=ident, text=text)
        elif item_type == "reasoning":
            self.emit(kind="reasoning", phase=phase, id=ident, text=text)
        elif item_type == "command_execution":
            code = item.get("exit_code")
            self.emit(kind="command", phase=phase, id=ident, text=item.get("command") if isinstance(item.get("command"), str) else "",
                      status=item.get("status") if isinstance(item.get("status"), str) else None,
                      exit_code=code if isinstance(code, int) and not isinstance(code, bool) else None,
                      output=_cap(item.get("aggregated_output"), MAX_EVENT_TEXT))
        else:
            self.emit(kind="item", phase=phase, id=ident, item_type=_cap(item_type, 80), text=text)

    def finish(self):
        result = self.result
        done = [self.texts[k][0] for k in self.order if self.texts[k][1]]
        result.messages = done[-MAX_MESSAGES:]
        seen = [self.texts[k][0] for k in self.order if self.texts[k][0]]
        result.partial = seen[-1] if seen else ""
        result.thread_id = self.thread_id
        return done[-1] if done else ""


def _is_dir(path):
    """`Path(path).is_dir()` with a filesystem failure (a component longer than NAME_MAX, a permission error)
    answered as False: the home checks never let an OSError escape (a 4096-character home is an accepted shape,
    toolchain.valid_codex_home, so the predicate has to survive it)."""
    try:
        return Path(path).is_dir()
    except OSError:
        return False


def _auth_present(home, auth, environment):
    """Whether `home` holds the login the provider `auth` needs (R-4: presence only).

    The rule is one implementation, `setup.auth_served` (doctor, chat preparation and this turn check share it):
    "file" auth needs `home/auth.json` a file, a nonempty `CODEX_API_KEY`, or `OPENAI_API_KEY` when `CODEX_API_KEY`
    is absent; an ("env", NAME) provider needs a nonempty NAME in `environment`; a provider that needs no login
    (auth None) is always present. No value is read, copied or printed. This is the frozen seam s2a3 exposed."""
    return setup.auth_served(home, auth, environment)


def _config_text(home):
    """`home`'s config.toml as text, or None when the file is absent (Codex's own defaults).

    A file that cannot be stat'ed or read is refused here, with `codex_provider`'s own `readiness.codex_home`
    wording and family: `Path.exists()` swallows a permission error and would answer the built-in defaults, and an
    OSError must never escape `check_home` (R-6)."""
    path = Path(home) / "config.toml"
    try:
        return path.read_text()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise Blocked("Codex config %s is unreadable (%s); fix the file or remove it to restore the Codex defaults."
                      % (path, type(error).__name__), family="readiness.codex_home") from error


def _selected_profile(text):
    """The nonempty top-level `profile` of a parsed config.toml `text`, or None (R-6).

    An absent config.toml answers None (Codex's own defaults); so does a malformed one, whose refusal belongs to
    `home_provider` (`readiness.codex_home`). A file that cannot be read never reaches this helper: `_config_text`
    refuses it first."""
    if text is None:
        return None
    try:
        config = setup.read_toml(text)
    except ValueError:
        return None
    if not isinstance(config, dict):
        return None
    profile = config.get("profile")
    return profile if isinstance(profile, str) and profile else None


def home_provider(home, text=None):
    """`(provider, auth)` for a turn in `home`, with the config-read rule `check_home` uses (R-6): an unreadable
    config.toml is the `readiness.codex_home` refusal, never Codex's built-in defaults, and an OSError never
    escapes.

    `Path.exists()` swallows a permission error and would answer the defaults for a config that cannot be read, so
    the read itself decides: `text` is the caller's `_config_text(home)` when it already read the file. Both
    `check_home` and the header (`tui.chat.header_provider`) resolve the provider here, so the pane and the turn
    never disagree about a config that cannot be read."""
    if text is None:
        text = _config_text(home)
    try:
        return setup.codex_provider(home)
    except OSError as error:  # a stat `Path.exists()` refuses (a component longer than NAME_MAX): a refusal
        raise Blocked("Codex config %s is unreadable (%s); fix the file or remove it to restore the Codex defaults."
                      % (Path(home) / "config.toml", type(error).__name__), family="readiness.codex_home") from error


def check_home(home, environment, resumed):
    """The one predicate for "can a turn start in this home" (the frozen interface s2b2 builds on): None, or a
    `Blocked` whose family is `architect.home_lost` (a resumed turn), `readiness.auth` (a new thread),
    `readiness.codex_home` (an unreadable config, from `codex_provider`) or `architect.invalid_config` (a selected
    profile, R-6). It never raises anything else: a filesystem failure is one of those refusals, never an OSError.

    Order (fixed):
    - home is a directory (a resumed turn only) -> `architect.home_lost`;
    - config.toml parsed, a nonempty top-level `profile` -> `architect.invalid_config`, before `codex_provider`,
      which would otherwise answer `readiness.codex_home` for an unknown profile first;
    - `codex_provider(home)` -> its own `readiness.codex_home` when the config is unreadable;
    - `_auth_present`: absent -> `architect.home_lost` when resumed, `readiness.auth` for a new thread.

    A config.toml that exists but cannot be stat'ed or read (a permission error, a symlink loop, a component longer
    than NAME_MAX) is that same `readiness.codex_home`, for both turn kinds: it is a refusal before any save or
    launch, never the built-in defaults and never a bare OSError (R-6).

    Its `readiness.auth` texts are the ones `default_prepare` showed before, unchanged; the `home_lost` text names
    the home (tilde) and the Ctrl+R rollover and never a credential or a variable value."""
    home = Path(home)
    if resumed and not _is_dir(home):
        raise Blocked(HOME_LOST % (setup.tilde(home), HOME_MISSING), family="architect.home_lost")
    text = _config_text(home)          # a config that exists but cannot be read is refused here (R-6)
    profile = _selected_profile(text)
    if profile is not None:
        raise Blocked("Codex config %s selects profile %r; the architect does not run a profile — remove the profile "
                      "from the file." % (home / "config.toml", profile), family="architect.invalid_config")
    provider, auth = home_provider(home, text)
    if _auth_present(home, auth, environment):
        return None
    if resumed:
        raise Blocked(HOME_LOST % (setup.tilde(home), HOME_NO_FILE_AUTH if auth == "file" else HOME_NO_ENV_AUTH),
                      family="architect.home_lost")
    if auth == "file":
        raise Blocked("No Codex login in %s; run zplan login (zplan's own directory) or log in with codex login in your own CODEX_HOME."
                      % home, family="readiness.auth")
    raise Blocked("The variable %s is not set for provider %s; set it and run zplan again."
                  % (auth[1], provider), family="readiness.auth")


class Architect:
    def __init__(self, executable, environment, project, model, effort, *, store=None, on_event=None, clock=time.time,
                 controller=None):
        self.executable = str(executable)
        self.environment = dict(environment)
        self.project = Path(project).expanduser().resolve()
        if not self.project.is_dir():
            raise Blocked("Project not found: %s." % self.project, family="architect.project_missing")
        self.model, self.effort = str(model), str(effort)
        self.controller = str(controller) if controller else None  # the live Controller's socket, or None
        build_argv(self.executable, self.project, self.model, self.effort, controller=self.controller)  # validate early
        self.clock = clock
        self.store = store or ArchitectStore(self.project, clock=clock)
        self.on_event = on_event
        self._guard = threading.Lock()
        self._process = None
        self._cancel = False
        self._timer = None

    # state
    def session(self):
        return self.store.load()

    @property
    def thread_id(self):
        session = self.store.load()
        return session["thread_id"] if session else None

    @property
    def running(self):
        with self._guard:
            return self._process is not None

    def _fresh_session(self):
        return {"version": 1, "thread_id": None, "model": self.model, "created": _stamp(self.clock), "turns": 0, "usage": {}}

    def reset(self):
        """Forget the stored thread and its home; the next message starts a new thread in the current home. The
        transcript is kept (R-5).

        Takes the same per-project lock as a send, so two windows cannot reset and send the same project at once."""
        if self.running:
            raise Blocked("The architect is answering: cancel the turn first.", family="architect.busy")
        lock = None
        try:
            lock = self._lock()
            session = self.store.load() or self._fresh_session()
            session["thread_id"] = None
            session.pop("codex_home", None)
            self.store.save(session)
            self.store.append("reset", text="New dialog: the previous thread id is forgotten.")
        finally:
            if lock is not None:
                lock.close()

    # home (R-5, R-6)
    def next_home(self):
        """`(home, resumed)` for the next turn, without side effects: the recorded home of a continuation, the
        current home for a new thread (R-5).

        A session without `codex_home` is a pre-0.5 session: its old thread acts in `legacy_codex_home()`, the home
        of the process env the owner started zplan with, never in an env zplan has modified. Reads the session only;
        an empty store answers the current home. This is the frozen interface s2b2 builds on."""
        session = self.store.load()
        if not session or session["thread_id"] is None:
            return setup.codex_home(self.environment), False
        return record_home.effective_home(session.get("codex_home")), True

    # control
    def cancel(self):
        """Kill only the architect's own process group. Returns False when no turn is running."""
        with self._guard:
            process = self._process
            if process is None:
                return False
            self._cancel = True
            if process is False:  # reserved but not launched: _turn sees the cancel and never starts Codex
                return True
        self._signal(process, signal.SIGTERM)
        timer = threading.Timer(KILL_GRACE, self._signal, (process, signal.SIGKILL))
        timer.daemon = True
        timer.start()
        self._timer = timer
        return True

    @staticmethod
    def _signal(process, number):
        try:
            os.killpg(process.pid, number)  # start_new_session=True: pgid == pid
        except (ProcessLookupError, PermissionError):
            pass

    # turn
    def send(self, message, snapshot=None, on_event=None, role="owner"):
        """Reserve and run one turn: `begin` then `run` then `finish`. The chat calls the three directly, so its
        cancel cannot slip between the "is it cancelled?" check and the reservation. `role` names the transcript
        row the message is stored under: the owner's own turn is `"owner"`, an event-driven turn is `"events"`."""
        if not isinstance(message, str) or not message.strip():
            raise Blocked("Empty message to the architect.", family="architect.empty_message")
        self.begin()
        try:
            return self.run(message, snapshot, on_event, role)
        finally:
            self.finish()

    def begin(self):
        """Reserve the turn before anything runs; raises Blocked when one is already in flight. The caller takes
        the same lock its `cancel` uses while reserving, so a cancel that lands now is seen by `_turn` at once."""
        with self._guard:
            if self._process is not None or self._cancel:
                raise Blocked("The architect is already answering.", family="architect.busy")
            self._cancel = False
            self._process = False  # reserve; replaced by the Popen inside `_turn`

    def run(self, message, snapshot=None, on_event=None, role="owner"):
        """Run a reserved turn under the per-project lock (never without a preceding `begin`)."""
        lock = None
        try:
            lock = self._lock()
            return self._turn(message, snapshot, on_event, role)
        finally:
            if lock is not None:
                lock.close()

    def finish(self):
        """Drop the reservation; paired with every `begin`, whoever began the turn releases it."""
        with self._guard:
            self._process, self._cancel = None, False

    def _lock(self):
        descriptor = os.open(self.store.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        stream = os.fdopen(descriptor, "r+")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            if error.errno in (errno.EAGAIN, errno.EACCES):
                raise Blocked("Another zplan process is already talking to this project's architect.", family="architect.locked") from error
            raise
        return stream

    def _turn(self, message, snapshot, on_event, role="owner"):
        store = self.store
        session = store.load() or self._fresh_session()
        home, resumed = self.next_home()
        thread = session["thread_id"]
        # R-5: a continuation acts in its recorded home, so its own process env carries that home; a new thread
        # keeps the architect's env unchanged (it records it instead).
        environment = dict(self.environment, CODEX_HOME=str(home)) if resumed else dict(self.environment)
        # R-5/R-6: the turn home is judged before anything is written -- the session save and the transcript append
        # below -- and before the Popen, so a refusal leaves both files byte-identical and starts no process. The
        # auth verdict is judged on the owner's own env, before R-4b's child mapping, so a turn's verdict is the one
        # doctor and `default_prepare` gave (A-6/R-4): an env-key provider named `CODEX_API_KEY` cannot be refused
        # by readiness and then complete a resumed turn.
        check_home(home, environment, resumed)
        # R-4b: the child contract for the OPENAI_API_KEY route (the native engine's own mapping of upstream
        # `configure_openai_auth`); the Popen reads this env and never logs a value.
        environment = setup.child_auth_env(environment)
        # Only zplan's own MCP server may run in the architect's sandbox: proved with the owner's env before anything
        # is written, so a refusal leaves the store and the transcript byte-identical and starts no turn process.
        disabled = foreign_servers(self.executable, environment, self.project, self.controller)
        argv = build_argv(self.executable, self.project, self.model, self.effort, thread, disabled, self.controller)
        if resumed:
            # Every resumed turn is told the protocol, snapshot or not: `build_update` reads a missing snapshot as
            # an unknown state, and the draft instructions of a resumed turn must not depend on the caller having
            # one. A turn sent without a snapshot still gets the update, never the full preamble.
            prompt = build_update(snapshot) + message
        else:
            prompt = build_preamble(snapshot, self.project) + message
        session["model"] = self.model
        session["turns"] += 1
        session = store.save(session)
        store.append(role, text=message)

        def persist(new_thread):
            # R-5: the thread id and the home it starts in are written in the same save. The home is the current
            # one (`next_home()` of a new thread), not a later one the env may have moved on to.
            current = store.load() or session
            current["thread_id"] = new_thread
            current["codex_home"] = str(setup.codex_home(self.environment))
            store.save(current)

        def notify(event):
            for callback in (self.on_event, on_event):
                if callback is not None:
                    callback(event)

        turn = _Turn(resumed, thread, persist, notify)
        result = turn.result
        process = None
        cancelled_before_launch = False
        with self._guard:
            # The launch decision, the process and its publication are one critical section with `cancel`: a cancel
            # that returns True before this point never lets a Popen follow it, and one that lands while the process
            # exists signals the published process. `cancel` takes the same guard, so it cannot slip between the
            # "is it cancelled?" check and the reservation.
            if self._cancel:  # cancelled while the session was written: no Codex process is started at all
                cancelled_before_launch = True
            else:
                try:
                    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, cwd=str(self.project),
                                               env=environment, start_new_session=True, close_fds=True)
                except OSError as error:
                    result.cause = "Could not start Codex: %s." % (error.strerror or error.__class__.__name__)
                    result.detail = _cap(str(error), 500)
            if process is not None:
                self._process = process
        if cancelled_before_launch:
            return self._conclude(turn, None, snapshot=snapshot, early=True)
        if process is not None:
            self._pump(process, prompt.encode("utf-8"), turn)
        return self._conclude(turn, process, snapshot)

    def _pump(self, process, prompt, turn):
        tail = bytearray()

        def feed_stdin():
            try:
                process.stdin.write(prompt)
                process.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass

        def drain_stderr():
            try:
                while True:
                    chunk = process.stderr.read1(4096)
                    if not chunk:
                        break
                    tail.extend(chunk)
                    del tail[:-MAX_STDERR]
            except (OSError, ValueError):
                pass

        done = threading.Event()

        def watch():
            process.wait()
            if not done.wait(KILL_GRACE):  # an orphan keeps the pipe open: cut the whole group
                self._signal(process, signal.SIGKILL)

        helpers = [threading.Thread(target=target, daemon=True) for target in (feed_stdin, drain_stderr, watch)]
        for helper in helpers:
            helper.start()
        try:
            stream = process.stdout
            while True:
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE and not line.endswith(b"\n"):
                    turn.result.malformed_lines += 1
                    while True:  # drop the rest of an oversized line
                        rest = stream.readline(MAX_LINE)
                        if not rest or rest.endswith(b"\n"):
                            break
                    continue
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    turn.feed(text)
        finally:
            done.set()
            process.wait()
            self._signal(process, signal.SIGKILL)  # stragglers of the architect's group, never another group
            for helper in helpers:
                helper.join(KILL_GRACE * 2)
            for pipe in (process.stdout, process.stderr):
                try:
                    pipe.close()
                except OSError:
                    pass
        turn.result.stderr_tail = bytes(tail).decode("utf-8", errors="replace")
        turn.result.exit_code = process.returncode

    def _conclude(self, turn, process, snapshot=None, early=False):
        result, store = turn.result, self.store
        final = turn.finish()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        with self._guard:
            cancelled = self._cancel
        detail = " | ".join(turn.failures) or result.stderr_tail.strip()
        if process is None and not early:  # `early`: the cancel arrived before Popen, so nothing was launched
            result.status = "failed"
        elif cancelled:
            result.status, result.cause = "cancelled", CAUSE_CANCELLED
        elif turn.completed and result.exit_code == 0:
            result.status, result.text = "completed", final
        else:
            result.detail = _cap(detail, 1000)
            context = "\n".join(turn.failures) + "\n" + result.stderr_tail
            if turn.resumed and LOST.search(context):
                result.status, result.cause = "lost_session", CAUSE_LOST
            elif AUTH.search(context):
                result.status, result.cause = "failed", CAUSE_AUTH
            elif turn.failures:
                result.status, result.cause = "failed", "Codex reported a turn error: " + _cap(turn.failures[-1], 300)
            elif result.exit_code is not None and result.exit_code < 0:
                result.status, result.cause = "failed", "Codex was interrupted by signal %d before the turn ended." % -result.exit_code
            elif result.exit_code:
                result.status, result.cause = "failed", "Codex exited with code %d before the turn ended." % result.exit_code
            else:
                result.status, result.cause = "failed", "Codex exited without a turn result."
        if result.status == "completed":
            # Only here: a completed turn's final text. `snapshot` is the state the turn was sent with (the caller
            # froze it), so the drafts keep the identity of that state and never of a later one.
            result.drafts = parse_drafts(result.text, snapshot)
            session = store.load() or self._fresh_session()
            # `result.usage` is the thread total Codex last reported. A continuation's own usage is that total minus
            # the session total before the turn; a new thread (nothing resumed) counts from zero.
            before = session["usage"] if turn.resumed else {}
            own = {key: max(value - before.get(key, 0), 0) for key, value in result.usage.items()}
            session["usage"] = dict(result.usage)
            store.save(session)
            store.append("architect", text=result.text, usage=own, thread_id=result.thread_id,
                         status=result.status, drafts=list(result.drafts))
        else:
            store.append("error", status=result.status, text=result.cause, detail=result.detail,
                         partial=_cap(result.partial, MAX_TEXT), thread_id=result.thread_id)
        return result
