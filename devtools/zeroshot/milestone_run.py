#!/usr/bin/env python3.13
"""Dev runs through zplan's own milestone graph (task D1): `run.sh` with ZS_GRAPH=zplan.

    milestone_run.py documents TASK_FILE OUT_DIR --runtime RUNTIME_JSON [--worktree DIR] [--preamble FILE]

Turns a devtools/zeroshot task file into a one-milestone, one-task proposal and writes graph.json, runtime.json,
input.json and baseline.json from `runs.build_documents` (the product's own builder, with the preflight node first).
The task file: the first line is the title; the text up to the first header is the goal; headers at a line start are
`Why:`, `Reuse:`, `Write-set:`, `Acceptance criteria...:` (items `- Cn text ... Example: ...`), `Non-goals...:`,
`Conflict rule:` and `Risk:` (the first word) with `DoD:` after it. Roles come from RUNTIME_JSON's nodes: worker,
acceptance (reviewer, preflight) and code (steward). With --worktree it also writes what `MilestoneRuns.prepare`
(runs.py:903) leaves in the worktree before dispatch. Exit 2 and nothing written when the file or the runtime is
unusable.
"""

import argparse
import json
from pathlib import Path
import re
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from terminal_planner import milestone  # noqa: E402
from terminal_planner.authority import Blocked, atomic_state, git, normalize_origin_upstream  # noqa: E402
from terminal_planner.runs import bootstrap_manifest, build_documents, checker_command, validate_roles  # noqa: E402

HEADER = re.compile(r"^(Why|Reuse|Write-set|Acceptance criteria[^:\n]*|Non-goals[^:\n]*|Conflict rule|Risk):[ \t]*(.*)$")
SECTIONS = {"Why": "why", "Reuse": "reuse", "Write-set": "write_set", "Conflict rule": "conflict", "Risk": "risk"}
CRITERION = re.compile(r"(\S+)\s+(.*?)\s*Example:\s*(.*)", re.S)
NODES = {"worker": "worker", "acceptance": "reviewer", "code": "steward"}  # runtime node -> execution role
BINDING_KEYS = {"kind", "model", "effort"}
EXCLUDE = "/.zplan/"
CHECK = ".zplan/check.py"  # the frozen checker as a file: Claude agents refuse `python3.13 -I -c '<code; code>'`


class Refused(Exception):
    pass


def split(text):
    """The first line, the lines before the first header, and the header -> text of each section."""
    lines = text.strip().splitlines()
    sections, intro, current = {}, [], None
    for line in lines[1:] if lines else []:
        found = HEADER.match(line)
        if found:
            name = found.group(1)
            current = SECTIONS.get(name) or ("criteria" if name.startswith("Acceptance") else "non_goals")
            sections[current] = [found.group(2)]
        elif current is None:
            intro.append(line)
        elif current == "write_set" and not line.strip():
            current = "prose"  # a blank line ends the write-set: what follows is prose for the goal, never a file
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return (lines[0].strip() if lines else ""), intro, sections


def criteria(lines):
    items = []
    for line in lines:
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items and line.strip():
            items[-1] += " " + line.strip()
    result = []
    for item in items:
        found = CRITERION.fullmatch(item)
        if not found:
            raise Refused("acceptance criteria: %r has no `Cn text ... Example: ...` form" % item[:60])
        result.append({"id": found.group(1), "text": found.group(2), "example": found.group(3)})
    return result


def brief_task(text):
    """(title, task) of a task file; Refused names every missing field."""
    title, intro, sections = split(text)
    joined = {name: " ".join(line.strip() for line in lines if line.strip()) for name, lines in sections.items()}
    risk, _, dod = joined.get("risk", "").partition("DoD:")
    found = re.match(r"\w+", risk.strip())
    write_set = re.split(r"\.(?:\s|$)", re.sub(r"\([^)]*\)", "", joined.get("write_set", "")).strip(), maxsplit=1)[0]  # first sentence
    items = criteria(sections.get("criteria", []))
    non_goals = [g.strip().rstrip(".") for g in re.split(r";", joined.get("non_goals", "")) if g.strip().rstrip(".")]
    missing = [name for name, ok in (("title", title), ("write-set", write_set), ("acceptance criteria", items),
                                     ("non-goals", non_goals), ("risk", found), ("dod", dod.strip())) if not ok]
    if missing:
        raise Refused("missing field: " + ", ".join(missing))
    paths = [p.strip() for p in write_set.split(",") if p.strip()]
    prose = [p for p in paths if re.search(r"\s", p)]
    if prose:
        raise Refused("write-set: %r is not a file path" % prose[0][:60])
    goal = "\n".join([title] + intro + [""] + sections.get("prose", [])).strip()
    if joined.get("conflict"):
        goal += "\n\nConflict rule: " + joined["conflict"]
    brief = {"goal": goal, "why": joined.get("why") or title, "reuse": joined.get("reuse", ""),
             "write_set": paths, "criteria": items,
             "non_goals": non_goals, "risk": found.group(0).lower(), "dod": dod.strip()}
    checks = ["%s %s" % (c["id"], c["text"]) for c in items] + ["DoD: " + brief["dod"]]
    return title, {"id": "T1", "title": title, "checks": checks, "brief": brief}


def proposal(title, task):
    return {"requirements": [{"id": "R1", "text": title}],
            "milestones": [{"id": "M1", "title": title, "depends_on": [], "slices": [
                {"id": "S1", "title": title, "requirements": ["R1"], "tasks": [task]}]}]}


def roles(runtime):
    nodes = runtime.get("nodes") if isinstance(runtime, dict) else None
    result = {}
    for node, role in NODES.items():
        binding = nodes.get(node) if isinstance(nodes, dict) else None
        if not isinstance(binding, dict):
            raise Refused("runtime: node %s is missing" % node)
        if set(binding) - BINDING_KEYS:
            raise Refused("runtime: node %s has %s; only the model and effort of a node are used"
                          % (node, ", ".join(sorted(set(binding) - BINDING_KEYS))))
        result[role] = {k: binding.get(k) for k in ("model", "effort")}
    validate_roles(result)
    return result


def documents(args):
    try:
        runtime = json.loads(Path(args.runtime).read_text())
        title, task = brief_task(Path(args.task_file).read_text())
        if args.preamble:
            task["brief"]["reuse"] = (task["brief"]["reuse"] + "\n\n" + Path(args.preamble).read_text().strip()).strip()
        built = build_documents(proposal(title, task), "M1", 1, roles(runtime), checker(args.worktree))
        built["runtime"].update({k: runtime[k] for k in ("harness", "provider", "size") if k in runtime})
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True, mode=0o700)
        for key, value in built.items():
            atomic_state(out / (key + ".json"), value)
        if args.worktree:
            prepare(Path(args.worktree), built["baseline"])
    except (OSError, ValueError, Blocked) as error:
        raise Refused(str(error))


def checker(worktree):
    """The product's frozen checker (runs.py `checker_command`), as `python3.13 -I WORKTREE/.zplan/check.py` when a
    worktree is given: the 2026-10-25 first graph run failed at select_init because the Claude agent's permission
    check refused the `-c` one-liner ("This command requires approval"); `Bash(python3.13:*)` admits the file form."""
    if not worktree:
        return checker_command()
    return shlex.join(["python3.13", "-I", str(Path(worktree).resolve() / CHECK)])


def prepare(worktree, baseline):
    """What `MilestoneRuns.prepare` leaves in the worktree before dispatch: the branch pinned to `origin`
    (runs.py:923), `.zplan/baseline.json` and `.zplan/milestone.json` (runs.py:925-929, the first manifest as
    `bootstrap_manifest` builds it). The dev repository does not ignore `.zplan/` (the product excludes it from
    its export instead), so `git add --all` of the delivery would commit it: it joins the repository's exclude file."""
    normalize_origin_upstream(worktree)
    (worktree / ".zplan").mkdir(exist_ok=True)
    (worktree / CHECK).write_text(shlex.split(checker_command())[-1] + "\n")  # the -c code of the product checker
    for relative, value in ((milestone.BASELINE, baseline), (milestone.MANIFEST, bootstrap_manifest(baseline, None))):
        path = worktree / relative
        path.parent.mkdir(exist_ok=True)
        atomic_state(path, value)
    exclude = worktree / git(worktree, "rev-parse", "--git-path", "info/exclude").decode().strip()
    lines = exclude.read_text().splitlines() if exclude.is_file() else []
    if EXCLUDE not in lines:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("".join(line + "\n" for line in lines + [EXCLUDE]))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="milestone_run.py")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("documents")
    command.add_argument("task_file")
    command.add_argument("out_dir")
    command.add_argument("--runtime", required=True)
    command.add_argument("--worktree")
    command.add_argument("--preamble")
    args = parser.parse_args(argv)
    try:
        documents(args)
    except Refused as error:
        print("milestone_run: %s: %s" % (args.task_file, error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
