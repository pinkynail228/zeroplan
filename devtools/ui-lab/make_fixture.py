"""Write fixtures/{milestone,planner}-graph.json: zplan's real stage and planning graphs, structure only.

Run from the repo root with the project venv: .venv/bin/python devtools/ui-lab/make_fixture.py
Keeps the keys the scheme reads (kinds, names, nesting, loop bounds, branch guards); drops payload schemas.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from terminal_planner import engine, milestone  # noqa: E402

KEEP = ("kind", "name", "worker", "maxIterations", "join")
NEST = ("children", "body", "otherwise")


def strip(node):
    out = {k: node[k] for k in KEEP if k in node and not isinstance(node[k], dict)}
    for key in NEST:
        value = node.get(key)
        if isinstance(value, list):
            out[key] = [strip(c) for c in value]
        elif isinstance(value, dict) and "kind" in value:
            out[key] = strip(value)
    if "branches" in node:
        out["branches"] = [dict({"node": strip(b["node"])}, **({"when": b["when"]} if "when" in b else {}))
                           if "node" in b else strip(b) for b in node["branches"]]
    return out


if __name__ == "__main__":
    for name, graph in (("milestone", milestone.milestone_graph(3)), ("planner", engine.planner_graph_v2(3))):
        path = Path(__file__).with_name("fixtures") / f"{name}-graph.json"
        path.write_text(json.dumps(strip(graph["root"]), ensure_ascii=False, indent=1) + "\n")
        print(path, path.stat().st_size)
