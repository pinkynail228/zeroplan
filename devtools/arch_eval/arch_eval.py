#!/usr/bin/env python3
"""Architect evaluation rig (roadmap A0 step 5): coded owner messages replayed on a fixture project with the real
model, through the real full-screen app, the path the owner uses. Stdlib only.

    arch_eval.py run REV OUT [--only id,...] [--repeat N] [--parallel 2]
    arch_eval.py score OUT [OUT ...]

`run` freezes REV with `git archive` under /tmp/a0r/code, then for every scenario of scenarios.toml (times --repeat)
builds the fixture under /tmp/a0r/p, an isolated zplan data and config home under /tmp/z/<n> (the installed tools are
linked, never copied), and drives `python -m terminal_planner.cli` in tmux (`-L a0r`). The model is the owner's: the
Codex home is $A0R_CODEX_HOME, default ~/.local/share/planning-kit/codex-home (zplan's own login; nothing reads it
here). At most --parallel apps run at once (default 2). Evidence lands in OUT/<case>/: the architect transcript and
operations, the Codex rollout of the thread, the last screen, and score.json.

`score` reads that evidence only; deterministic code decides every metric (no model judges):
- premature plan: a zplan_plan call in a turn whose message expects an answer;
- missed plan: a turn that expects a plan with neither a plan call nor a proposal (a goal draft, a mode request);
- turns to the first useful answer: a turn is useful when it calls no plan and its reply matches every oracle;
- format retries: refused zplan_plan or zplan_edit_plan calls of one turn (a format refusal names the format)."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import tomllib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
ROOT = pathlib.Path("/tmp/a0r")
HOMES = pathlib.Path("/tmp/z")  # short: the plan check's socket path must stay under 104 bytes
SERVER = ["tmux", "-L", "a0r"]
PYTHON = pathlib.Path.home() / ".local/share/planning-kit/app/0.10.0/bin/python3"
# $A0R_TOOLS: a tools root holding the frozen revision's default toolchain when the installed one does not (after a
# toolchain bump, e.g. ~/.cache/zplan-dev/data/planning-kit/tools from `setup.install_tools`); default the installed tools.
TOOLS = pathlib.Path(os.environ.get("A0R_TOOLS") or pathlib.Path.home() / ".local/share/planning-kit/tools")
CODEX_HOME = pathlib.Path(os.environ.get("A0R_CODEX_HOME") or pathlib.Path.home() / ".local/share/planning-kit/codex-home")
IDENTITY = ["-c", "user.name=Owner", "-c", "user.email=owner@example.invalid"]
TURN_LIMIT = 900        # seconds one architect turn may take
REVIEW_LIMIT = 480      # seconds the plan check's event turn may take before the next message
PLAN_TOOLS = ("zplan_plan", "zplan_edit_plan")
PROPOSAL_TOOLS = ("zplan_propose_mode", "zplan_request_mode")  # a later design's mode request, if it lands
FORMAT = re.compile(r"Invalid (proposal|argument)|request_invalid|plan format|schema", re.I)
OFFER = re.compile(r"(составл|напиш|сдела|подготов)\w*\s+план|план\w*\s*\?|shall I (write|draft|make) (a |the )?plan|"
                   r"want me to (write|draft|plan)|plan (it|this)\?", re.I)


def scenarios():
    return tomllib.loads((HERE / "scenarios.toml").read_text(encoding="utf-8"))["scenario"]


def sh(argv, **kw):
    return subprocess.run(argv, check=True, capture_output=True, text=True, **kw).stdout


def freeze(rev):
    sha = sh(["git", "-C", str(REPO), "rev-parse", "--short", rev]).strip()
    code = ROOT / "code" / sha
    if not code.exists():
        code.mkdir(parents=True)
        archive = subprocess.run(["git", "-C", str(REPO), "archive", sha], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(code)], input=archive, check=True)
    return sha, code


def fixture(variant, dest, level="supervised"):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(HERE / "fixture" / "shelf", dest)
    profile = dest / "zplan.process.json"
    document = json.loads(profile.read_text())
    document["autonomy"]["level"] = level
    profile.write_text(json.dumps(document, indent=2) + "\n")
    git = ["git", "-C", str(dest)]
    sh(git + ["init", "-q", "-b", "main"])
    if variant == "committed":
        sh(git + ["add", "-A"])
        sh(git + IDENTITY + ["commit", "-qm", "shelf"])
    else:
        sh(git + IDENTITY + ["commit", "-q", "--allow-empty", "-m", "Initial commit"])
    sh(git + ["remote", "add", "origin", "https://github.com/example/shelf.git"])


def screen(name):
    out = subprocess.run(SERVER + ["capture-pane", "-p", "-t", name], capture_output=True, text=True).stdout
    return "\n".join(line.rstrip() for line in out.splitlines())


def keys(name, *args):
    subprocess.run(SERVER + ["send-keys", "-t", name, *args], check=True)


def entries(store):
    path = store / "transcript.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def operations(store):
    path = store / "operations.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def store_of(home):
    found = sorted((home / "planning-kit" / "architect").glob("*/transcript.jsonl"))
    return found[0].parent if found else None


def replies_after(rows, owner_index):
    """The architect entries after the owner entry number `owner_index` (0-based), up to the next owner entry."""
    seen, out = -1, []
    for row in rows:
        if row.get("role") == "owner":
            seen += 1
            if seen > owner_index:
                break
        elif seen == owner_index:
            out.append(row)
    return out


def turn_tools(ops, turn_id):
    """{operation_id: (tool, terminal result text)} of the architect tools one turn called."""
    calls = {}
    for op in ops:
        if op.get("kind") == "architect_tool" and op.get("turn_id") == turn_id:
            if op.get("state") == "terminal":
                calls[op["operation_id"]] = (op.get("tool"), str(op.get("result")))
            else:
                calls.setdefault(op["operation_id"], (op.get("tool"), ""))
    return list(calls.values())


def plan_saved(ops, turn_id):
    return any(tool in PLAN_TOOLS and result and "refused" not in result and "failed" not in result
               for tool, result in turn_tools(ops, turn_id))


APPROVE = "zplan_approve_plan"


def judge(turn, owner, replies, ops):
    """One owner turn's facts and verdicts, from the stores alone. `expect`: "answer" (no plan wanted), "answer_plan"
    (an answer required, a plan welcome), "plan" (a saved revision required), "plan_or_approve" (a yes to a proposal:
    a saved revision, or the approval of the plan already drafted), "approve" / "no_approve" (a message sent while a
    plan waits: it must, or must not, approve it)."""
    tools = turn_tools(ops, owner.get("turn_id"))
    plans = [(tool, result) for tool, result in tools if tool in PLAN_TOOLS]
    refused = [result for _, result in plans if "refused" in result or "failed" in result]
    approved = any(tool == APPROVE and result and "refused" not in result and "failed" not in result
                   for tool, result in tools)
    text = "\n".join(str(row.get("text") or "") for row in replies if row.get("role") == "architect")
    drafts = [d for row in replies for d in (row.get("drafts") or []) if isinstance(d, dict)]
    card = any(d.get("kind") == "goal" for d in drafts) or any(tool in PROPOSAL_TOOLS for tool, _ in tools)
    oracle = turn.get("oracle", [])
    expect = turn["expect"]
    useful = bool(text) and all(re.search(p, text, re.I) for p in oracle)
    saved = len(plans) > len(refused)
    return {"text": turn["text"], "expect": expect, "followup": bool(turn.get("followup")),
            "plan_calls": len(plans), "plan_saved": saved, "approved": approved,
            "format_refusals": sum(1 for r in refused if FORMAT.search(r)), "refusals": len(refused),
            "proposal_card": card, "proposal_text": bool(OFFER.search(text)), "useful": useful,
            "premature": expect == "answer" and bool(plans),
            "missed": (expect == "plan" and not saved) or (expect == "plan_or_approve" and not saved and not approved),
            "wrong_approval": (expect == "no_approve" and approved) or (expect == "approve" and not approved),
            "status": [row.get("status") for row in replies if row.get("role") == "architect"],
            "tools": [tool for tool, _ in tools], "reply": text[:2000]}


def wait_for(predicate, limit, step=3.0):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    return None


def run_case(number, case, scenario, code, out, log):
    project, home = ROOT / "p" / case, HOMES / str(number)
    fixture(scenario["variant"], project, scenario.get("level", "supervised"))
    if home.exists():
        shutil.rmtree(home)
    (home / "planning-kit" / "native").mkdir(parents=True)
    (home / "planning-kit" / "tools").symlink_to(TOOLS)
    subprocess.run(SERVER + ["kill-session", "-t", case], capture_output=True)
    env = " ".join("%s=%s" % pair for pair in (("XDG_DATA_HOME", home), ("XDG_CONFIG_HOME", home / "config"),
                                                ("CODEX_HOME", CODEX_HOME), ("PYTHONPATH", code),
                                                ("TERM", "xterm-256color")))
    sh(SERVER + ["new-session", "-d", "-s", case, "-x", "140", "-y", "45",
                 "cd %s && env %s %s -m terminal_planner.cli; sleep 600" % (project, env, PYTHON)])
    started = time.monotonic()

    def ready():
        text = screen(case)
        if "Write to the architect" in text:
            return True
        if "Open this project" in text or "[enter] accept" in text:
            keys(case, "Enter")
        return False
    verdicts, owner_sent = [], 0
    try:
        if not wait_for(ready, 120, 2.0):
            raise RuntimeError("the app never showed the chat input")
        for turn in scenario["turns"]:
            if turn.get("followup") and (not verdicts or verdicts[-1]["useful"] or verdicts[-1]["expect"] != "answer"):
                continue
            keys(case, "-l", turn["text"])
            time.sleep(0.5)
            keys(case, "Enter")
            index = owner_sent
            owner_sent += 1

            def answered():
                store = store_of(home)
                if store is None:
                    return None
                rows = entries(store)
                done = [r for r in replies_after(rows, index) if r.get("role") == "architect" and r.get("status")]
                return store if done else None
            store = wait_for(answered, TURN_LIMIT)
            if store is None:
                verdicts.append({"text": turn["text"], "expect": turn["expect"], "timeout": True, "useful": False,
                                 "premature": False, "missed": turn["expect"] == "plan"})
                break
            owners = [r for r in entries(store) if r.get("role") == "owner"]
            if plan_saved(operations(store), owners[index].get("turn_id")):
                # The plan check answers with an event turn: the owner's next message comes after it, as in life,
                # and the case keeps its slot until then (at most 2 real model runs at once, the check included).
                wait_for(lambda: len([r for r in replies_after(entries(store), index)
                                      if r.get("role") == "architect"]) >= 2, REVIEW_LIMIT, 5.0)
            rows, ops = entries(store), operations(store)
            owners = [r for r in rows if r.get("role") == "owner"]
            verdicts.append(judge(turn, owners[index], replies_after(rows, index), ops))
        error = ""
    except Exception as failure:  # the case is recorded as broken, never as a pass
        error = "%s: %s" % (type(failure).__name__, failure)
    target = out / case
    target.mkdir(parents=True, exist_ok=True)
    (target / "screen.txt").write_text(screen(case), encoding="utf-8")
    subprocess.run(SERVER + ["kill-session", "-t", case], capture_output=True)
    store = store_of(home)
    thread = ""
    if store is not None:
        for name in ("transcript.jsonl", "operations.jsonl", "session.json"):
            if (store / name).exists():
                shutil.copy2(store / name, target / name)
        try:
            thread = json.loads((store / "session.json").read_text()).get("thread_id") or ""
        except (OSError, ValueError):
            thread = ""
    if thread:
        for rollout in (CODEX_HOME / "sessions").rglob("rollout-*%s.jsonl" % thread):
            shutil.copy2(rollout, target / "rollout.jsonl")
    record = {"case": case, "scenario": scenario["id"], "variant": scenario["variant"], "error": error,
              "seconds": round(time.monotonic() - started), "turns": verdicts}
    (target / "score.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    log("%s %s in %ds%s" % (case, "done" if not error else "BROKEN", record["seconds"], " " + error if error else ""))
    return record


def summary(records):
    """The metrics over the cases (counts, never percentages alone). G1 and G2 read first turns only: a follow-up is
    sent only after a failed turn, so it never changes a denominator."""
    t = {"answer_first": 0, "useful_first": 0, "noplan_first": 0, "unwanted": 0, "plan_turns": 0, "missed": 0,
         "format": 0, "plan_writing_turns": 0, "approval_turns": 0, "wrong_approval": 0, "broken": 0}
    lines = []
    for record in sorted(records, key=lambda r: r["case"]):
        t["broken"] += bool(record["error"])
        turns = record["turns"]
        first = turns[0] if turns else None
        if first is not None and first["expect"] in ("answer", "answer_plan"):
            t["answer_first"] += 1
            t["useful_first"] += bool(first.get("useful"))
            if first["expect"] == "answer":
                t["noplan_first"] += 1
                t["unwanted"] += bool(first.get("premature"))
        for turn in turns:
            if turn["expect"] in ("plan", "plan_or_approve"):
                t["plan_turns"] += 1
                t["missed"] += bool(turn.get("missed"))
            if turn["expect"] in ("approve", "no_approve"):
                t["approval_turns"] += 1
                t["wrong_approval"] += bool(turn.get("wrong_approval"))
            if turn.get("plan_calls"):
                t["plan_writing_turns"] += 1
                t["format"] += turn.get("format_refusals", 0)
        marks = " ".join(("U" if turn.get("premature") else "M" if turn.get("missed") else
                          "W" if turn.get("wrong_approval") else "") +
                         ("a" if turn.get("useful") else "") + ("p" if turn.get("plan_saved") else "") +
                         ("(%d)" % turn["format_refusals"] if turn.get("format_refusals") else "") or "-"
                         for turn in turns)
        lines.append("| %s | %s | %s | %s |" % (record["case"], record["variant"], marks, record["error"][:60]))
    head = ["Marks per turn: a answered (oracle), p plan saved, U unwanted plan, M missed plan, W wrong approval,"
            " (n) format refusals, - nothing.", "", "| case | variant | turns | error |", "|---|---|---|---|"]
    foot = ["", "- G1 answer first: %d of %d first turns that expect an answer" % (t["useful_first"], t["answer_first"]),
            "- G2 unwanted plan: %d of %d first turns where no plan is wanted" % (t["unwanted"], t["noplan_first"]),
            "- G3 missed plan: %d of %d plan turns" % (t["missed"], t["plan_turns"]),
            "- G4 format: %d refusals over %d plan-writing turns" % (t["format"], t["plan_writing_turns"]),
            "- wrong approvals: %d of %d turns sent while a plan waits" % (t["wrong_approval"], t["approval_turns"]),
            "- broken cases: %d" % t["broken"]]
    return "\n".join(head + lines + foot), t


def rescore(record, folder):
    """The record judged again from its saved stores with the current scenarios (an oracle may be corrected after a
    run); a case without stores, or a timed-out turn, keeps its recorded verdicts."""
    spec = {s["id"]: s for s in scenarios()}.get(record["scenario"])
    if spec is None or not (folder / "transcript.jsonl").exists():
        return record
    rows, ops = entries(folder), operations(folder)
    owners = [r for r in rows if r.get("role") == "owner"]
    by_text = {t["text"]: t for t in spec["turns"]}
    turns = []
    for index, old in enumerate(record["turns"]):
        turn = by_text.get(old["text"])
        if turn is None or old.get("timeout") or index >= len(owners):
            turns.append(old)
        else:
            turns.append(judge(turn, owners[index], replies_after(rows, index), ops))
    return dict(record, turns=turns)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("rev")
    run.add_argument("out")
    run.add_argument("--only", default="")
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--parallel", type=int, default=2)
    score = sub.add_parser("score")
    score.add_argument("outs", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "score":
        records = [rescore(json.loads(p.read_text()), p.parent)
                   for out in args.outs for p in sorted(pathlib.Path(out).glob("*/score.json"))]
        text = summary(records)[0]
        for out in args.outs:  # the re-judged summary is evidence too: written beside the run's own
            (pathlib.Path(out) / "summary-rescored.md").write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    if not PYTHON.exists() or not TOOLS.exists():
        sys.exit("the installed zplan app or tools are missing: %s, %s" % (PYTHON, TOOLS))
    if args.parallel > 2:
        sys.exit("at most 2 real runs at once")
    sha, code = freeze(args.rev)
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    chosen = [s for s in scenarios() if not args.only or s["id"] in args.only.split(",")]
    cases = [("%s-%s-%d" % (s["id"], sha, k + 1), s) for k in range(args.repeat) for s in chosen]
    logfile = out / "run.log"

    def log(text):
        line = "%s %s" % (time.strftime("%H:%M:%S"), text)
        with logfile.open("a") as stream:
            stream.write(line + "\n")
        print(line, flush=True)
    log("run %s on %s: %d cases, parallel %d" % (out.name, sha, len(cases), args.parallel))
    with concurrent.futures.ThreadPoolExecutor(args.parallel) as pool:
        records = list(pool.map(lambda n: run_case(n, cases[n][0], cases[n][1], code, out, log), range(len(cases))))
    text, _ = summary(records)
    (out / "summary.md").write_text("# %s on %s\n\n%s\n" % (out.name, sha, text), encoding="utf-8")
    log("summary in %s" % (out / "summary.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
