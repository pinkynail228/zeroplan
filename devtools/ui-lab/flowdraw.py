"""Scheme of a Zeroshot graph for the terminal, fitted to any pane.

Input is the public Zeroshot graph (upstream/protocol/openengine-cluster/v1/graph.schema.json: seq, step,
verifier, par, choice, loop, fail, succeed) and a per-node observation like the Zeroshot web UI uses
(upstream/ui/src/workflow-observation.ts: state idle|running|succeeded|failed|skipped|recorded, count,
detail), plus `timer` (m:ss on the running node, from zplan's live record).

Projection: sequences are invisible wiring; a choice shows its taken path (fail exits hidden, a branch
that only runs when the check did not pass is shown as "если нужно"); a loop is a bracket with its
round "2 из 4". Fitting: boxes when they fit, else one line per step, else a window around the
running step with both ends folded.
"""
from __future__ import annotations

from rich.text import Text

SPIN = "◐◓◑◒"
MARK = {"done": ("✓", "green"), "fail": ("✗", "red"), "error": ("!", "bold red"), "wait": ("◌", "dim"),
        "skip": ("–", "dim")}
WORD = {"run": "работает", "done": "готово", "fail": "отклонено", "error": "ошибка", "wait": "ждёт",
        "skip": "пропущено"}
LEGEND = [("◐", "yellow"), (" идёт  ", "dim"), ("✓", "green"), (" готово  ", "dim"),
          ("✗", "red"), (" отклонено  ", "dim"), ("◌", "dim"), (" ждёт  ", "dim"), ("↻", "dim"), (" повтор", "dim")]
STATE = {"running": "run", "succeeded": "done", "recorded": "done", "idle": "wait", "skipped": "skip"}

# Node and loop names -> the owner's words (GLOSSARY.md). Unknown names stay readable, never hidden.
NAMES = {"select_init": "выбор первой задачи", "select": "выбор задачи", "select_verify": "проверка выбора",
         "worker": "исполнитель", "acceptance_review": "ревью: приёмка", "code_review": "ревью: код",
         "steward_apply": "учёт результата", "steward_decide": "решение по задаче",
         "final_verify": "итоговая проверка", "repair": "доработка этапа", "scope_verify": "проверка объёма",
         "final_reverify": "повторная итоговая проверка", "planner": "планирование",
         "critic": "проверка плана", "plan_verifier": "проверка плана",
         "task_loop": "задачи по очереди", "review_loop": "раунды ревью", "repair_loop": "раунды доработки",
         "final_repair": "доработка после итоговой проверки"}
EXITS = ("fail", "succeed")


def title(name: str) -> str:
    name = name[6:] if name.startswith("empty_") else name
    return NAMES.get(name, name.replace("_", " "))


def clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


# ── projection: graph + observation -> items ─────────────────────────────
# item = ("stage", [node, ...]) | ("loop", {title, max, count, active, items}) | ("cond", {title, items})

def _state(node: dict, obs: dict) -> str:
    raw = obs.get(node.get("name"), {}).get("state", "idle")
    if raw == "failed":
        return "fail" if node["kind"] == "verifier" else "error"
    return STATE.get(raw, "wait")


def _leaf(node: dict, obs: dict, optional: bool) -> dict:
    o = obs.get(node.get("name"), {})
    state = _state(node, obs)
    word = o.get("detail") or ("если нужно" if optional and state == "wait" else WORD[state])
    return dict(title=o.get("title") or title(node["name"]), state=state, word=word, timer=o.get("timer", "") if state == "run" else "",
                color="cyan" if node["kind"] == "verifier" else "yellow")


def _touched(node, obs: dict) -> bool:
    if isinstance(node, dict):
        if obs.get(node.get("name"), {}).get("state", "idle") != "idle":
            return True
        return any(_touched(v, obs) for v in node.values() if isinstance(v, (dict, list)))
    if isinstance(node, list):
        return any(_touched(v, obs) for v in node)
    return False


def _accepts(guard) -> bool:
    """A guard that tests a check's verdict for `accepted`."""
    value = (guard or {}).get("value") or {}
    return value.get("field") == "verdict" and "accepted" in (guard or {}).get("labels", ())


def project(node: dict, obs: dict, optional: bool = False) -> list:
    kind = node.get("kind")
    if kind in ("step", "verifier"):
        return [("stage", [_leaf(node, obs, optional)])]
    if kind == "seq":
        return [item for child in node.get("children", []) for item in project(child, obs, optional)]
    if kind == "par":
        nodes = []
        for branch in node.get("children", node.get("branches", [])):
            branch = branch.get("node", branch)
            if branch["kind"] in ("step", "verifier"):
                nodes.append(_leaf(branch, obs, optional))
            else:  # a compound branch folds into one line named after it
                nodes.append(dict(title=title(branch.get("name", "?")), state="wait", word="несколько шагов",
                                  timer="", color="yellow"))
        return [("stage", nodes)]
    if kind == "loop":
        o = obs.get(node.get("name"), {})
        items = project(node["body"], obs, optional)
        return [("loop", dict(title=o.get("title") or title(node["name"]), max=node.get("maxIterations"), count=o.get("count"),
                              active=_touched(node["body"], obs), items=items))]
    if kind == "choice":
        raw = node.get("branches", [])
        branches = [b.get("node", b) for b in raw]
        paths = [b for b in branches if b["kind"] not in EXITS]
        other = node.get("otherwise")
        if other and other["kind"] not in EXITS:
            if not paths and any(b.get("node", {}).get("kind") == "succeed" and _accepts(b.get("when")) for b in raw):
                # The flow ends when a check accepts; the default path only runs when it did not.
                return [("cond", dict(title=title(other.get("name", "")), items=project(other, obs, True)))]
            paths.append(other)
        if not paths:
            return []
        taken = next((p for p in paths if _touched(p, obs)), paths[0])
        return project(taken, obs, optional)
    return []


# ── shared pieces ────────────────────────────────────────────────────────

def mark(node: dict, tick: int) -> tuple[str, str]:
    if node["state"] == "run":
        return SPIN[tick % 4], "bold " + node["color"]
    return MARK[node["state"]]


def frame(node: dict) -> str:
    if node["state"] == "run":
        return node["color"]
    return {"done": "green", "fail": "red", "error": "red"}.get(node["state"], "dim")


def _running(node: dict) -> bool:
    return node["state"] in ("run", "fail", "error")


def render(graph: dict, obs: dict, width: int, height: int, tick: int) -> Text:
    items = project(graph, obs)
    return (_full(items, width, height, tick) or _tree(items, width, height, tick, trunk=True)
            or _tree(items, width, height, tick, trunk=False) or _window(items, width, height, tick))


# ── boxes ────────────────────────────────────────────────────────────────

class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.w, self.h = width, height
        self.cells = [[(" ", "")] * width for _ in range(height)]

    def put(self, x: int, y: int, text: str, style: str = "") -> None:
        for i, ch in enumerate(text):
            if 0 <= x + i < self.w and 0 <= y < self.h:
                self.cells[y][x + i] = (ch, style)

    def box(self, x: int, y: int, w: int, lines: list, style: str, name: str, heavy: bool) -> None:
        tl, tr, bl, br, hz, vt = ("┏", "┓", "┗", "┛", "━", "┃") if heavy else ("╭", "╮", "╰", "╯", "─", "│")
        self.put(x, y, tl + hz * (w - 2) + tr, style)
        self.put(x + 2, y, f" {clip(name, w - 6)} ", "bold " + style)
        for i, segs in enumerate(lines, 1):
            self.put(x, y + i, vt + " " * (w - 2) + vt, style)
            cx = x + 2
            for text, st in segs:
                self.put(cx, y + i, text, st)
                cx += len(text)
        self.put(x, y + len(lines) + 1, bl + hz * (w - 2) + br, style)

    def text(self) -> Text:
        out = Text()
        for r, row in enumerate(self.cells):
            if r:
                out.append("\n")
            for ch, st in row:
                out.append(ch, st)
        return out


def _flatten(items: list, depth: int, stages: list, loops: list) -> None:
    for kind, value in items:
        if kind == "stage":
            stages.append(value)
            continue
        start = len(stages)
        _flatten(value["items"], depth + (kind == "loop"), stages, loops)
        if kind == "loop" and len(stages) > start:
            label = f"{value['count']}/{value['max']}" if value["count"] else f"≤{value['max']}"
            loops.append(dict(start=start, end=len(stages) - 1, depth=depth, active=value["active"], label=label))


def _full(items: list, width: int, height: int, tick: int):
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
            room = w - 7 - len(timer)
            line = [(m + " ", ms), (clip(node["word"], room).ljust(room), ""), (" " + timer, "dim")]
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


def _connect(c: Canvas, up: list, down: list, cx: int, y: int, active: bool, tick: int) -> int:
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

def _node_line(node: dict, tick: int) -> list:
    m, ms = mark(node, tick)
    segs = [(m + " ", ms), (node["title"], "bold" if node["state"] == "run" else ""), (" · " + node["word"], "dim")]
    if node["timer"]:
        segs.append(("  " + node["timer"], "dim"))
    return segs


def _lines(items: list, tick: int, trunk: bool, prefix: list) -> list:
    """Lines as (segments, is_step, is_running)."""
    out = []
    for i, (kind, value) in enumerate(items):
        if kind == "stage":
            live = any(_running(n) for n in value)
            if i and trunk:
                out.append((prefix + [("│", "yellow" if live else "dim")], False, False))
            for node in value:
                fork = [("├ ", "yellow" if live else "dim")] if len(value) > 1 else []
                out.append((prefix + fork + _node_line(node, tick), True, _running(node)))
        elif kind == "loop":
            style = "yellow" if value["active"] else "dim"
            rounds = f" · {value['count']} из {value['max']}" if value["count"] else f" · до {value['max']} раз"
            out.append((prefix + [("↻ ", style), (value["title"], "bold" if value["active"] else ""),
                                  (rounds, "dim")], False, False))
            out += _lines(value["items"], tick, trunk, prefix + [("│ ", style)])
        else:
            out.append((prefix + [("? ", "dim"), ("если нужно: " + value["title"], "dim")], False, False))
            out += _lines(value["items"], tick, trunk, prefix + [("┆ ", "dim")])
    return out


def _paint(lines: list, width: int) -> Text:
    longest = max(sum(len(t) for t, _ in segs) for segs in lines)
    pad = " " * max(0, (width - longest) // 2)
    out = Text(no_wrap=True, overflow="ellipsis")
    for i, segs in enumerate(lines):
        if i:
            out.append("\n")
        out.append(pad)
        for t, st in segs:
            out.append(t, st)
    return out


def _tree(items: list, width: int, height: int, tick: int, trunk: bool):
    lines = _lines(items, tick, trunk, [])
    return _paint([line[0] for line in lines], width) if lines and len(lines) <= height else None


def steps_word(n: int) -> str:
    form = "шаг" if n % 10 == 1 and n % 100 != 11 else "шага" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "шагов"
    return f"{n} {form}"


def _window(items: list, width: int, height: int, tick: int) -> Text:
    """The running step stays in view; the finished and the waiting ends fold into one line each."""
    lines = _lines(items, tick, False, [])
    focus = next((i for i, line in enumerate(lines) if line[2]), 0)
    room = max(1, height - 2)
    lo = max(0, min(focus - room // 3, len(lines) - room))
    hi = min(len(lines), lo + room)
    steps = lambda part: sum(1 for line in part if line[1])  # noqa: E731
    shown = []
    if lo:
        shown.append([("✓ ", "green"), (f"ещё {steps_word(steps(lines[:lo]))} выше", "dim"), ("  ↑", "dim")])
    shown += [line[0] for line in lines[lo:hi]]
    if hi < len(lines):
        shown.append([("◌ ", "dim"), (f"ещё {steps_word(steps(lines[hi:]))} ниже", "dim"), ("  ↓", "dim")])
    return _paint(shown, width)
