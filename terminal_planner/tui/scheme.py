"""Scheme of a Zeroshot graph for the terminal, fitted to any pane (U1 product port of `devtools/ui-lab/flowdraw.py`).

`render(graph_root, observation, width, height, tick=0, words=None, limits=None)` turns the public Zeroshot graph (upstream
`graph.schema.json`: seq, step, verifier, par, choice, loop, fail, succeed) plus a per-node observation
(`{"state": running|succeeded|failed|idle|skipped|recorded, "detail", "timer", "count", "title"}`, every key
optional) into a `rich.text.Text`: no line wider than `width` cells, no more than `height` lines. It is pure — no
I/O, no clock: only its arguments decide the result.

`limits` names the loop bounds that are facts of the attempt being drawn (`{"review_loop": 4}`): a loop in it is
drawn with that bound, a loop missing from it is drawn without any bound (the graph's own `maxIterations` is not a
fact of the attempt, so it is never drawn through `limits`); `None` keeps the graph's `maxIterations`, as every
caller before this keyword has it.

The same three fitting modes as the lab prototype, tried in order: framed boxes when they fit (`_full`), else one
line per step (`_tree`), else a window around the running step with both ends folded (`_window`). `project` folds
the graph into stages, loop groups and an optional "if needed" branch: sequences are invisible wiring; a choice
draws only the taken branch (the default before anything ran); a rejection-driven `loop` shows ↻ with its round.
`observation_from_flow` builds an observation from `terminal_planner.live.flow`'s plain facts.

Every visible word comes from the single `WORDS` table keyed by GLOSSARY ids (docs/ui-redesign/GLOSSARY.md:
`role.*`, `state.*`, `flow.*`); a `words` callable (id -> text) replaces the table, `None` uses the built-in
English one. A node name with no GLOSSARY id (a loop group, a scheme authored elsewhere) is shown as the name with
`_` replaced by a space, never hidden. `legend(words=None)` returns the legend (GLOSSARY `flow.legend`).

One GLOSSARY row carries placeholders and is filled from the facts at hand: `flow.loop_group` (a loop's round,
whose one row documents both the counted and the open form); `limits` is what decides which bounds it may name (a
classifier of what is a fact of the attempt, so the graph's own `maxIterations` is drawn only for callers that ask
for it). `flow.optional` is the `?`/`┆` branch header only (it names the branch); a step inside that branch that has
not run says `state.if_needed` alone, without the branch name. Only ids the GLOSSARY lists are ever requested, so a
glossary-derived `words` callable supplies every string."""

from __future__ import annotations

import os
import re
import shlex

from rich.cells import cell_len
from rich.text import Text

SPIN = "◐◓◑◒"
MARK = {"done": ("✓", "green"), "fail": ("✗", "red"), "error": ("!", "bold red"),
        "wait": ("◌", "dim"), "skip": ("–", "dim"), "unknown": ("?", "yellow")}
# Observation state -> the internal state key whose mark and word are drawn.
STATE = {"running": "run", "succeeded": "done", "recorded": "done", "idle": "wait", "skipped": "skip"}
# Internal state key -> the GLOSSARY id of the word that says it (state.*, EN column).
STATE_ID = {"run": "state.running", "done": "state.done", "fail": "state.rejected",
            "error": "state.error", "wait": "state.waiting", "skip": "state.skipped"}

# The one table of every visible word, keyed by GLOSSARY ids (docs/ui-redesign/GLOSSARY.md, EN column). A `words`
# callable overrides it; `{...}` values are templates the caller formats (the callable returns one string per id).
WORDS = {
    "role.preflight": "preflight",
    "role.select_init": "first task pick",
    "role.select": "task pick",
    "role.select_verify": "pick check",
    "role.worker": "worker",
    "role.review_accept": "acceptance review",
    "role.review_code": "code review",
    "role.steward_apply": "result record",
    "role.steward_decide": "task decision",
    "role.final_check": "final check",
    "role.repair": "stage fix-up",
    "role.scope_verify": "scope check",
    "role.final_reverify": "final re-check",
    "role.planner": "planning",
    "role.plan_check": "plan check",
    "role.plan_reader": "plan reader",
    "role.plan_reader_failed": "plan reader failed",
    "state.running": "running",
    "state.done": "done",
    "state.rejected": "rejected",
    "state.error": "error",
    "state.waiting": "waiting",
    "state.skipped": "skipped",
    "state.if_needed": "if needed",
    "flow.loop_group": "{name} · {n} of {max} / up to {max} times",
    "flow.optional": "if needed: {name}",
    "flow.task_loop": "tasks one by one",
    "flow.review_loop": "review rounds",
    "flow.repair_loop": "fix-up rounds",
    "flow.final_repair": "fix-up after the final check",
    "flow.fold_done": "✓ {n} stages behind ↑",
    "flow.fold_next": "◌ {n} ahead: {names} ↓",
}
# Node name (with `empty_` stripped) -> the GLOSSARY role id it is drawn as. A name absent here is shown as the
# name itself with `_` -> space (loops, unknown names from a scheme authored elsewhere).
NODE_IDS = {
    "preflight": "role.preflight", "select_init": "role.select_init", "select": "role.select",
    "select_verify": "role.select_verify",
    "worker": "role.worker", "acceptance_review": "role.review_accept", "code_review": "role.review_code",
    "steward_apply": "role.steward_apply", "steward_decide": "role.steward_decide",
    "final_verify": "role.final_check", "repair": "role.repair", "scope_verify": "role.scope_verify",
    "final_reverify": "role.final_reverify", "planner": "role.planner", "critic": "role.plan_check",
    "plan_verifier": "role.plan_check", "comprehension": "role.plan_reader",
    "comprehension_failed": "role.plan_reader_failed",
    "task_loop": "flow.task_loop", "review_loop": "flow.review_loop", "repair_loop": "flow.repair_loop",
    "final_repair": "flow.final_repair",
}
EXITS = ("fail", "succeed")


def _word(words, gid):
    """The word for a GLOSSARY id: the caller's callable, else the built-in English table."""
    return words(gid) if callable(words) else WORDS[gid]


def _one_line(text):
    """A display field (detail, title) as one physical line: line breaks become spaces.

    The observation contract allows an ordinary string, so a `detail` may carry embedded newlines. The layout counts
    one row per item (`_lines`) and `Canvas`/`_paint` would append those breaks after fitting, overflowing `height`;
    folding them into spaces keeps the field on its one logical row in every fitting mode."""
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _template(words, gid, **values):
    """A word that carries placeholders (`flow.loop_group`, the folds), formatted with the caller's values."""
    return _word(words, gid).format(**values)


def _loop_phrase(words, title, count, max_rounds):
    """The `flow.loop_group` phrase for a loop, honouring the GLOSSARY row's two documented forms.

    The GLOSSARY writes one row, "{name} · {n} of {max} / up to {max} times": the counted form mentions `{n}`, the open
    form does not, and the "{name} · " prefix is shared. Pick the form the observation allows (a count is known or
    not) and fill only that form's own `{name}`/`{n}`/`{max}` placeholders, so a glossary-derived `words` works.

    `max_rounds` None means the bound is not a fact of the attempt (`limits`): the counted form then keeps its count
    without the `{max}` clause ("{n} of {max}" -> "{n}") and a form whose only fact is the bound — the open one —
    collapses to the bare name, so no bound is ever drawn."""
    template = _word(words, "flow.loop_group")
    counted, _, open_form = template.partition(" / ")
    head, sep, tail = counted.rpartition(" · ")
    prefix, counted = (head + sep, tail) if sep else ("", counted)
    if max_rounds is None:
        if count is None:
            text, values = prefix, {"name": title}  # the name alone: the open form's only fact was the bound
        else:
            clause = counted.split("{max}")[0].rstrip(" ·/")
            tokens = clause.rsplit(" ", 1)
            counted = tokens[0].rstrip(" ·/") if len(tokens) == 2 and not tokens[1].startswith("{") else clause
            text, values = prefix + counted, {"name": title, "n": count}
    else:
        parts = [counted] + ([open_form] if open_form else [])
        chosen = next((p for p in parts if ("{n}" in p) == (count is not None)), parts[0])
        text, values = prefix + chosen, {"name": title, "n": count, "max": max_rounds}
    out = text.format(**{key: value for key, value in values.items() if "{%s}" % key in text})
    return out.rstrip(" ·") if max_rounds is None and count is None else out


def node_title(name, words=None):
    """A node's visible title: its GLOSSARY role word when it has one, else the name with `_` -> space.

    A production node may carry an `empty_` prefix (`empty_final_verify`); the mapped variant is drawn with its
    role word. A name with no role mapping is never truncated: an unknown `empty_cache` stays `empty cache`, the
    whole name with `_` -> space."""
    gid = NODE_IDS.get(name) or NODE_IDS.get(name[len("empty_"):] if name.startswith("empty_") else name)
    return _word(words, gid) if gid else name.replace("_", " ")


def clip(text, width):
    """The text clipped to `width` terminal cells with a trailing ellipsis (used inside a box)."""
    if width <= 0:
        return ""
    return text if cell_len(text) <= width else _take(text, width - 1) + "…"


SHELLS = frozenset(("sh", "bash", "zsh", "dash", "ksh", "fish"))
PREFIXES = frozenset(("env", "exec", "command"))  # words a command line may open with before its program
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
LOCAL_PATH = re.compile(r"(?<!\S)/[^\s/]+/\S*")  # an absolute path of two or more parts, at a word start


def program_name(text, _inner=False):
    """R-B: a command as the TUI shows it — the program's name. A shell wrapper (`/bin/zsh -lc '…'`) is looked
    through to the command it runs, leading `NAME=value` words and `env` are skipped, and the path is dropped:
    `/bin/zsh -lc 'PATH="/Users/user/bin:$PATH" pytest -q'` -> `pytest`. A text that cannot be read as a command line
    (a cut-off quote) is split on blanks; when no program is found the wrapper's own name is shown. Display only:
    the stored command text is never changed."""
    text = str(text).strip()
    try:
        words = shlex.split(text)
    except ValueError:
        words = text.lstrip("'\"").split()
    first = os.path.basename(words[0]) if words else ""
    while words and (ASSIGNMENT.match(words[0]) or os.path.basename(words[0]) in PREFIXES):
        words = words[1:]
    if not words:
        return "" if _inner else first or text
    head = os.path.basename(words[0]) or words[0]
    if head in SHELLS and not _inner:
        for index, word in enumerate(words[1:-1], 1):
            if word.startswith("-") and not word.startswith("--") and "c" in word:
                return program_name(words[index + 1], _inner=True) or head
    return head


def without_local_path(line):
    """R-B: `line` with the first absolute local path and what follows it shown as the command's program name
    (`program_name`); a line with no such path is returned as it is."""
    found = LOCAL_PATH.search(line)
    return line if found is None else line[:found.start()] + program_name(line[found.start():])


# ── projection: graph + observation -> items ─────────────────────────────
# item = ("stage", [node, ...]) | ("loop", {title, max, count, active, items}) | ("cond", {title, items})

def _loop_bound(node, limits):
    """The bound to draw for the loop `node` (its projected item's `max`): the graph's `maxIterations` by default,
    the attempt's own bound for the loop names `limits` carries, and None (no bound drawn) for the rest."""
    if limits is None:
        return node.get("maxIterations")
    return limits.get(node.get("name", "?"))


# The loops that run a final check once more when it could not finish (`milestone_graph`, either prefix): drawn
# without a frame.
RETRY_LOOPS = ("final_verify_loop", "final_reverify_loop")


def _bare(name):
    """A node name without the `empty_` prefix of the no-open-task stage."""
    return name[len("empty_"):] if name.startswith("empty_") else name


def _state(node, obs):
    raw = (obs.get(node.get("name"), {}) or {}).get("state", "idle")
    if raw == "failed":
        return "fail" if node["kind"] == "verifier" else "error"
    return STATE.get(raw, "unknown")


def _leaf(node, obs, optional, words):
    o = obs.get(node.get("name"), {}) or {}
    state = _state(node, obs)
    fallback = ("unknown: " + str(o.get("state")) if state == "unknown" else
                _word(words, "state.if_needed") if optional and state == "wait"
                else _word(words, STATE_ID[state]))
    title = _one_line(o.get("title")) if o.get("title") else node_title(node["name"], words)
    if o.get("attempt") is not None:
        title += " · attempt %s" % o["attempt"]
    word = (_one_line(o.get("detail")) if o.get("detail") else
            _one_line(o.get("result")) if o.get("result") else fallback)
    timer = o.get("timer") or o.get("duration") or ""
    return dict(title=title, state=state, word=word, timer=timer,
                color="cyan" if node["kind"] == "verifier" else "yellow")


def _touched(node, obs):
    if isinstance(node, dict):
        # A skipped branch is evidence that this path was *not* taken; only a running/finished/recorded node counts.
        if (obs.get(node.get("name"), {}) or {}).get("state", "idle") not in ("idle", "skipped"):
            return True
        return any(_touched(v, obs) for v in node.values() if isinstance(v, (dict, list)))
    if isinstance(node, list):
        return any(_touched(v, obs) for v in node)
    return False


def _choice_rank(node, obs):
    """Current execution wins; otherwise prefer the most recently observed path.

    Event order is local to the projection, not an invented engine iteration counter.
    Legacy observations without order keep their first-touched fallback.
    """
    if isinstance(node, list):
        return max((_choice_rank(child, obs) for child in node), default=(False, False, -1))
    if not isinstance(node, dict):
        return False, False, -1
    fact = obs.get(node.get("name"), {}) or {}
    touched = fact.get("state", "idle") not in ("idle", "skipped")
    own = (fact.get("state") == "running", touched, fact.get("order", -1) if touched else -1)
    return max([own] + [_choice_rank(child, obs) for child in node.values() if isinstance(child, (dict, list))])


def _decided(node, obs):
    """Whether engine facts settle any branch direction, including an explicitly skipped path."""
    if isinstance(node, dict):
        if (obs.get(node.get("name"), {}) or {}).get("state", "idle") != "idle":
            return True
        return any(_decided(value, obs) for value in node.values() if isinstance(value, (dict, list)))
    if isinstance(node, list):
        return any(_decided(value, obs) for value in node)
    return False


def _accepts(guard):
    """A guard that tests a check's verdict for `accepted`."""
    value = (guard or {}).get("value") or {}
    return value.get("field") == "verdict" and "accepted" in (guard or {}).get("labels", [])


def _skipped(items, words):
    """The projected nodes of an untaken branch, derived as skipped rather than hidden."""
    result = []
    for kind, value in items:
        if kind == "stage":
            result.append((kind, [dict(leaf, state="skip", word=_word(words, "state.skipped"), timer="")
                                  for leaf in value]))
        else:
            result.append((kind, dict(value, active=False, items=_skipped(value["items"], words))))
    return result


def project(node, obs, optional=None, words=None, limits=None):
    kind = node.get("kind")
    if kind in ("step", "verifier", *EXITS):
        return [("stage", [_leaf(node, obs, optional, words)])]
    if kind == "seq":
        return [item for child in node.get("children", []) for item in project(child, obs, optional, words, limits)]
    if kind == "par":
        branches = [branch.get("node", branch) for branch in node.get("children", node.get("branches", []))]
        if all(branch["kind"] in ("step", "verifier", *EXITS) for branch in branches):
            return [("stage", [_leaf(branch, obs, optional, words) for branch in branches])] if branches else []
        return [("parallel", {"items": [("branch", {"title": "branch %s" % (i + 1),
                                "items": project(branch, obs, optional, words, limits)})
                               for i, branch in enumerate(branches)]})]
    if kind == "loop":
        o = obs.get(node.get("name"), {}) or {}
        items = project(node["body"], obs, optional, words, limits)
        if _bare(node.get("name", "")) in RETRY_LOOPS:
            count = o.get("count")
            if count and count > 1:
                for item_kind, value in items:
                    for leaf in value if item_kind == "stage" else []:
                        leaf["title"] += " ↻%s/%s" % (count, node["maxIterations"])
            return items
        return [("loop", dict(title=_one_line(o.get("title")) if o.get("title") else node_title(node.get("name", "?"), words),
                              max=_loop_bound(node, limits), count=o.get("count"),
                              active=_touched(node["body"], obs), items=items))]
    if kind == "choice":
        paths = [branch.get("node", branch) for branch in node.get("branches", [])]
        if node.get("otherwise") is not None:
            paths.append(node["otherwise"])
        decided = any(_decided(path, obs) for path in paths)
        touched = [path for path in paths if _touched(path, obs)]
        taken = (max(touched, key=lambda path: _choice_rank(path, obs)) if touched else
                 next((path for path in paths if path.get("kind") not in EXITS), paths[0] if paths else None))
        items = []
        for path in paths:
            selected = path is taken
            if not selected and not decided:
                continue  # an unresolved future choice stays compact; decided branches name their untaken paths
            projected = project(path, obs, node_title(path.get("name", ""), words), words, limits) if selected else []
            items.append(("cond", dict(title=node_title(path.get("name", ""), words), items=projected,
                                       state="run" if selected else "skip", word=_word(words, "state.skipped"))))
        return items
    return []


# ── shared pieces ────────────────────────────────────────────────────────

def mark(node, tick):
    if node["state"] == "run":
        return SPIN[tick % 4], "bold " + node["color"]
    return MARK[node["state"]]


def frame(node):
    if node["state"] == "run":
        return node["color"]
    return {"done": "green", "fail": "red", "error": "red"}.get(node["state"], "dim")


def _running(node):
    return node["state"] in ("run", "fail", "error")


def render(graph_root, observation, width, height, tick=0, words=None, limits=None):
    """The scheme of `graph_root` with `observation`, fitted into `width` x `height` cells (see the module docstring)."""
    obs = observation or {}
    items = project(graph_root, obs, words=words, limits=limits)
    if not items:
        return Text("")
    return (_full(items, width, height, tick) or _tree(items, width, height, tick, True, words)
            or _tree(items, width, height, tick, False, words) or _window(items, width, height, tick, words))


# ── boxes ────────────────────────────────────────────────────────────────

class Canvas:
    def __init__(self, width, height):
        self.w, self.h = width, height
        self.cells = [[(" ", "")] * width for _ in range(height)]

    def put(self, x, y, text, style=""):
        """Draw `text` at cell column `x`: a wide (CJK) character takes two cells, the second left blank."""
        if not 0 <= y < self.h:
            return
        row = self.cells[y]
        col = x
        for ch in text:
            size = cell_len(ch)
            if size and col >= 0 and col + size <= self.w:
                row[col] = (ch, style)
                for k in range(1, size):
                    row[col + k] = ("", style)
            col += size

    def box(self, x, y, w, lines, style, name, heavy):
        tl, tr, bl, br, hz, vt = ("┏", "┓", "┗", "┛", "━", "┃") if heavy else ("╭", "╮", "╰", "╯", "─", "│")
        self.put(x, y, tl + hz * (w - 2) + tr, style)
        self.put(x + 2, y, f" {clip(name, w - 6)} ", "bold " + style)
        for i, segs in enumerate(lines, 1):
            self.put(x, y + i, vt + " " * (w - 2) + vt, style)
            cx = x + 2
            for text, st in segs:
                self.put(cx, y + i, text, st)
                cx += cell_len(text)
        self.put(x, y + len(lines) + 1, bl + hz * (w - 2) + br, style)

    def text(self):
        out = Text()
        for r, row in enumerate(self.cells):
            if r:
                out.append("\n")
            for ch, st in row:
                out.append(ch, st)
        return out


def _flatten(items, depth, stages, loops):
    for kind, value in items:
        if kind == "stage":
            stages.append(value)
            continue
        if kind == "cond" and not value["items"]:
            stages.append([dict(title=value["title"], state="skip", word=value.get("word", "skipped"),
                                timer="", color="yellow")])
            continue
        start = len(stages)
        _flatten(value["items"], depth + (kind == "loop"), stages, loops)
        if kind == "loop" and len(stages) > start:
            # No bound (`limits`): a known count is drawn alone and an unknown one leaves the badge empty, so the
            # bound the graph carries but the attempt does not is never shown.
            if value["max"] is None:
                label = "" if value["count"] is None else f"{value['count']}"
            else:
                label = f"{value['count']}/{value['max']}" if value["count"] is not None else f"≤{value['max']}"
            loops.append(dict(start=start, end=len(stages) - 1, depth=depth, active=value["active"], label=label))


def _full(items, width, height, tick):
    # Flattening compound parallel branches would invent sequential edges. Use the
    # recursive fork/join drawing until a lane layout can preserve those same edges.
    def compound_parallel(items):
        return any(kind == "parallel" or (kind != "stage" and compound_parallel(value["items"]))
                   for kind, value in items)
    if compound_parallel(items):
        return None
    stages, loops = [], []
    _flatten(items, 0, stages, loops)
    if not stages:
        return None
    widest = max(len(s) for s in stages)
    gutter = 7 * (max((lp["depth"] for lp in loops), default=-1) + 1)
    w = min(30, (width - 2 * gutter - 2 * (widest - 1)) // widest)
    if w < 22:
        return None
    rows = lambda a, b: (len(a) > 1) + (len(b) > 1) + (len(a) == 1 and len(b) == 1) + 1  # noqa: E731
    total = 3 * len(stages) + sum(rows(a, b) for a, b in zip(stages, stages[1:]))
    if total > height:
        return None
    c = Canvas(width, total)
    cx = width // 2
    lefts, tops, y, prev = [], [], 0, []
    for i, stage in enumerate(stages):
        n = len(stage)
        x0 = cx - (n * w + 2 * (n - 1)) // 2
        centers = [x0 + k * (w + 2) + w // 2 for k in range(n)]
        if i:
            y = _connect(c, prev, centers, cx, y, any(_running(nd) for nd in stage), tick)
        tops.append(y)
        lefts.append(x0)
        for k, node in enumerate(stage):
            m, ms = mark(node, tick)
            timer = node["timer"]
            room = max(0, w - 7 - cell_len(timer))
            word = clip(node["word"], room)
            line = [(m + " ", ms), (word + " " * max(0, room - cell_len(word)), ""), (" " + timer, "dim")]
            c.box(x0 + k * (w + 2), y, w, [line], frame(node), node["title"], node["state"] == "run")
        y += 3
        prev = centers
    edge, deepest = min(lefts), max(lp["depth"] for lp in loops) if loops else 0
    for lp in sorted(loops, key=lambda item: item["depth"]):
        x = edge - 7 * (deepest - lp["depth"] + 1)
        rejected = any(nd["state"] == "fail" for s in stages[lp["start"]:lp["end"] + 1] for nd in s)
        style = "red" if rejected else "yellow" if lp["active"] else "dim"
        top, bottom = tops[lp["start"]] + 1, tops[lp["end"]] + 1
        c.put(x, top, "╭" + "─" * (lefts[lp["start"]] - x - 2) + "▶", style)
        for yy in range(top + 1, bottom):
            c.put(x, yy, "│", style)
        c.put(x, bottom, "╰" + "─" * (lefts[lp["end"]] - x - 2) + "╴", style)
        mid = (top + bottom) // 2
        c.put(x, mid, "↻", "bold " + style)
        c.put(x + 1, mid, lp["label"][:5], style)
    return c.text()


def _connect(c, up, down, cx, y, active, tick):
    style = "yellow" if active else "dim"
    if len(up) > 1:
        c.put(up[0], y, "╰" + "─" * (up[-1] - up[0] - 1) + "╯", style)
        for x in up[1:-1]:
            c.put(x, y, "┴", style)
        c.put(cx, y, "┼" if cx in up[1:-1] else "┬", style)
        y += 1
    if len(down) > 1:
        c.put(down[0], y, "╭" + "─" * (down[-1] - down[0] - 1) + "╮", style)
        for x in down[1:-1]:
            c.put(x, y, "┬", style)
        c.put(cx, y, "┼" if cx in down[1:-1] else "┴", style)
        if active:
            reach = max(1, (down[-1] - down[0]) // 2 - 1)
            c.put(cx - 1 - (tick // 2) % reach, y, "●", "bold yellow")
            c.put(cx + 1 + (tick // 2) % reach, y, "●", "bold yellow")
        y += 1
    if len(up) == 1 and len(down) == 1:
        c.put(cx, y, "●" if active and tick // 3 % 2 else "│", "bold yellow" if active else style)
        y += 1
    for x in down:
        c.put(x, y, "▼", style)
    return y + 1


# ── one line per step ────────────────────────────────────────────────────

def _node_line(node, tick):
    m, ms = mark(node, tick)
    segs = [(m + " ", ms), (node["title"], "bold" if node["state"] == "run" else "")]
    if node["word"]:
        segs.append((" · " + node["word"], "dim"))
    if node["timer"]:
        segs.append(("  " + node["timer"], "dim"))
    return segs


def _lines(items, tick, trunk, prefix, words):
    """Lines as (segments, is_step, is_running, title); `title` is the step's title, else None."""
    out = []
    for i, (kind, value) in enumerate(items):
        if kind == "stage":
            live = any(_running(n) for n in value)
            if i and trunk:
                out.append((prefix + [("│", "yellow" if live else "dim")], False, False, None))
            for node in value:
                fork = [("├ ", "yellow" if live else "dim")] if len(value) > 1 else []
                out.append((prefix + fork + _node_line(node, tick), True, _running(node), node["title"]))
        elif kind == "parallel":
            out.append((prefix + [("┬ parallel fork", "dim")], False, False, None))
            out += _lines(value["items"], tick, trunk, prefix + [("│ ", "dim")], words)
            out.append((prefix + [("┴ join", "dim")], False, False, None))
        elif kind == "branch":
            out.append((prefix + [("├ " + value["title"], "dim")], False, False, None))
            out += _lines(value["items"], tick, trunk, prefix + [("│   ", "dim")], words)
        elif kind == "loop":
            style = "yellow" if value["active"] else "dim"
            phrase = _loop_phrase(words, value["title"], value["count"], value["max"])
            out.append((prefix + [("↻ ", style), (phrase, "bold" if value["active"] else "dim")], False, False, None))
            out += _lines(value["items"], tick, trunk, prefix + [("│ ", style)], words)
        else:
            if value.get("state") == "skip":
                out.append((prefix + [("– ", "dim"), (value["title"] + " · " + _word(words, "state.skipped"), "dim")],
                            False, False, None))
            else:
                out.append((prefix + [("? ", "dim"),
                                      (_template(words, "flow.optional", name=value["title"]), "dim")], False, False, None))
            out += _lines(value["items"], tick, trunk, prefix + [("┆ ", "dim")], words)
    return out


def _take(text, room):
    """The longest prefix of `text` that fits in `room` terminal cells."""
    kept, used = [], 0
    for ch in text:
        size = cell_len(ch)
        if used + size > room:
            break
        kept.append(ch)
        used += size
    return "".join(kept)


def _fit(segs, width):
    """`segs` clipped to `width` cells, an ellipsis marking the cut, styles kept."""
    out, used = [], 0
    for text, style in segs:
        if used >= width:
            break
        room = width - used
        if cell_len(text) <= room:
            out.append((text, style))
            used += cell_len(text)
        else:
            out.append((_take(text, max(0, room - 1)) + "…", style))
            break
    return out


def _plain(segs):
    return "".join(text for text, _ in segs)


def _paint(lines, width):
    if not lines:
        return Text("")
    longest = max(cell_len(_plain(segs)) for segs in lines)
    pad = " " * max(0, (width - longest) // 2)
    out = Text(no_wrap=True, overflow="ellipsis")
    for i, segs in enumerate(lines):
        if i:
            out.append("\n")
        out.append(pad)
        room = width - len(pad)
        if cell_len(_plain(segs)) > room:
            segs = _fit(segs, room)
        for text, style in segs:
            out.append(text, style)
    return out


def _tree(items, width, height, tick, trunk, words):
    lines = _lines(items, tick, trunk, [], words)
    return _paint([line[0] for line in lines], width) if lines and len(lines) <= height else None


def _window(items, width, height, tick, words):
    """The running step stays in view; the finished and the waiting ends fold into one line each."""
    lines = _lines(items, tick, False, [], words)
    if not lines:
        return Text("")
    focus = next((i for i, line in enumerate(lines) if line[2]), 0)
    room = max(1, height - 2)
    lo = max(0, min(focus - room // 3, len(lines) - room))
    hi = min(len(lines), lo + room)
    steps = lambda part: sum(1 for line in part if line[1])  # noqa: E731
    shown = []
    if lo:
        shown.append([(_template(words, "flow.fold_done", n=steps(lines[:lo])), "dim")])
    shown += [line[0] for line in lines[lo:hi]]
    if hi < len(lines):
        names = ", ".join(line[3] for line in lines[hi:] if line[1])
        shown.append([(_template(words, "flow.fold_next", n=steps(lines[hi:]), names=names), "dim")])
    return _paint(shown[: max(1, height)], width)


# ── the legend and the live-flow observation ─────────────────────────────

def legend(words=None):
    """The scheme's legend (GLOSSARY `flow.legend`): a mark and the word for each shown state."""
    out = Text()
    for glyph, style, gid in (("◐", "yellow", "state.running"), ("✓", "green", "state.done"),
                              ("✗", "red", "state.rejected"), ("◌", "dim", "state.waiting")):
        out.append(glyph, style)
        out.append(" " + _word(words, gid) + "  ", "dim")
    return out


def observation_from_events(events, graph=None):
    """Latest observed fact per graph node, with attempt/duration/result evidence preserved.

    Events are engine facts, not UI completion flags. Later facts for the same node replace earlier scalar fields;
    unrelated fields survive so an attempt or result already observed is not forgotten by a state update.
    """
    names = set()

    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get("name"), str):
                names.add(value["name"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(graph)
    observation = {}
    for order, event in enumerate(events or ()):
        if not isinstance(event, dict) or not isinstance(event.get("node"), str):
            continue
        name = event["node"]
        if names and name not in names:
            matches = [candidate for candidate in names if name.endswith("/" + candidate)]
            if len(matches) == 1:
                name = matches[0]
        current = dict(observation.get(name, {}))
        current.update({key: value for key, value in event.items() if key != "node" and value is not None})
        current["order"] = order
        observation[name] = current
    return observation


WORKER_STATE = {"running": "running", "done": "succeeded", "waiting": "idle"}
REVIEW_STATE = {"running": "running", "accepted": "succeeded", "rejected": "failed", "conflict": "failed", "waiting": "idle"}


def observation_from_flow(flow, graph=None):
    """The scheme observation of one attempt from `terminal_planner.live.flow`'s facts (F1). `None` or `{}` -> `{}`.

    The worker's state, the two reviewers (a verdict maps accepted -> succeeded, rejected -> failed), a running
    final step as `final_verify`, a task-picking step as `select`, the review round as `review_loop.count`, the
    final check's attempt as `count` on the retry loop the check sits in, a run past preflight (a pick runs, a task
    is picked, or a worker, reviewer or final step has left waiting) as preflight succeeded, a later pick (a round or
    a task before it) as select_init succeeded too, a picked task (no pick running) as select_init and
    select_verify succeeded, and the echo of the running command as the worker's detail while the worker runs."""
    if not flow:
        return {}
    if "events" in flow:
        # An explicit execution projection is authoritative, even when empty (legacy
        # store or evicted timeline). Role/task/round summaries cannot prove a node
        # succeeded. Keep the old summary-only API below for explicit legacy callers.
        obs = observation_from_events(flow["events"], graph)
        final = flow.get("final") or {}
        if final.get("attempt") and final.get("check"):
            obs.setdefault(final["check"] + "_loop", {})["count"] = final["attempt"]
        if flow.get("round") is not None:
            obs.setdefault("review_loop", {})["count"] = flow["round"]
        if flow.get("command") and obs.get("worker", {}).get("state") == "running":
            obs["worker"]["detail"] = program_name(flow["command"])
        return obs
    obs = {}
    worker = WORKER_STATE.get((flow.get("worker") or {}).get("state"))
    if worker:
        obs["worker"] = {"state": worker}
    for reviewer in flow.get("reviewers") or []:
        name, state = reviewer.get("role"), REVIEW_STATE.get(reviewer.get("state"))
        if name and state:
            obs[name] = {"state": state}
    final = flow.get("final") or {}
    if final.get("state") == "running" and "events" not in flow:
        obs["final_verify"] = {"state": "running"}
    if final.get("attempt") and final.get("check"):
        obs.setdefault(final["check"] + "_loop", {})["count"] = final["attempt"]
    behind = flow.get("select") or flow.get("task") or any(
        obs.get(name, {}).get("state") not in (None, "idle") for name in ("worker", "acceptance_review", "code_review", "final_verify"))
    if behind:  # the run is past preflight
        obs["preflight"] = {"state": "succeeded"}
    if flow.get("select"):
        obs["select"] = {"state": "running"}
        if flow.get("round") is not None or flow.get("task"):  # a later pick: the first one is behind it
            obs["select_init"] = {"state": "succeeded"}
    elif flow.get("task"):  # a task is picked: the steps before the worker are behind it
        for name in ("select_init", "select_verify"):
            obs[name] = {"state": "succeeded"}
    if flow.get("round") is not None:
        obs.setdefault("review_loop", {})["count"] = flow["round"]
    if flow.get("command") and (flow.get("worker") or {}).get("state") == "running":
        obs.setdefault("worker", {})["detail"] = program_name(flow["command"])
    return obs
