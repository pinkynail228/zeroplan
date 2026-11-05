#!/usr/bin/env python3
"""Herdr monitor for slice runs: the architect hands work to the supervisor and keeps working.

The monitor watches every open run under a root (default .local/slices). When a supervisor wakes the
architect (pass batch, failure, queue end) or falls silent, it waits until the architect's Herdr agent is
idle, then prompts it once per wake with what to read and decide. It never decides anything itself.

    python3.13 devtools/slice_monitor.py up [--tab]    # name this pane's agent; monitor + status on the right (or a background tab)
    python3.13 devtools/slice_monitor.py watch --agent zplan-arch [--root .local/slices]

Delivery is recorded in each run's ledger as `architect_prompted`, so a restarted monitor does not repeat a
prompt. Rules: docs/DEVELOPMENT.md.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import slice_run as sr

HERE = pathlib.Path(__file__).resolve()
SETTLED = ("idle", "done")
NOTIFY_EVERY_S = 900
_notified: dict[str, float] = {}


def herdr(*args: str, timeout: float = 60) -> dict | None:
    """One Herdr CLI call; None when it fails (the reason goes to the monitor's own output)."""
    try:
        p = subprocess.run(["herdr", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"herdr {args[0]} {args[1] if len(args) > 1 else ''}: {type(exc).__name__}")
        return None
    if p.returncode:
        log(f"herdr {' '.join(args[:2])}: {(p.stderr or p.stdout).strip()[:200]}")
        return None
    try:
        return json.loads(p.stdout) if p.stdout.strip() else {}
    except ValueError:
        return {}


def log(text: str) -> None:
    # \r and erase-line first: the idle line written by cmd_watch is replaced, not left half-overwritten.
    print(f"\r\033[K{sr.iso()[11:19]} {text}", flush=True)


STAGES = {"prepare": "готовит ворктри", "red": "проверяет, что приёмочный тест красный на базе", "green": "запускает приёмочный тест",
          "waiting for limit reset": "ждёт сброса лимита подписки", "stopped": "остановлен"}


def stage_text(stage: str) -> str:
    if stage.startswith("worker r"):
        return f"воркер пишет код, раунд {stage[8:]}"
    if stage.startswith("review r"):
        return f"ревьюер проверяет дифф, раунд {stage[8:]}"
    if stage.startswith("gate"):
        return "тесты проекта"
    return STAGES.get(stage, stage)


def describe(run: sr.Run) -> list[str]:
    """One open run in plain words: what it does now, then one line per slice."""
    st, hb = sr.replay(run), sr._read_heartbeat(run) or {}
    alive = bool(hb) and sr.pid_alive(hb.get("pid")) and sr.now() - hb.get("ts", 0) < run.cfg["stale_after_s"]
    pending = [w for w in st["wakes"] if w["seq"] > st["acked"]]
    spent = sum(e.get("cost", 0) or 0 for e in run.events() if e["event"] == "agent_end")
    if pending:
        now = f"ждёт решения архитектора: {pending[-1]['reason']}"
    elif alive:
        now = f"{hb.get('slice') or ''} {stage_text(hb.get('stage', ''))}".strip()
        if hb.get("activity"):
            now += f" · {hb['activity']}"
    elif st["ended"]:
        now = "на паузе: архитектор уже решил, ждёт перезапуска"
    elif st["pid"]:
        now = "СУПЕРВИЗОР НЕ ОТВЕЧАЕТ: монитор уже позвал архитектора"
    else:
        now = "ещё не запускался"
    lines = [f"▶ {run.name}: {now}", f"  потрачено ${spent:.2f} (предохранитель ${run.cfg['night_budget_usd']:.0f})"]
    for sid in run.cfg["queue"]:
        s = st["slices"].get(sid, {})
        state = s.get("state", "в очереди")
        if state == "pass":
            state = f"✓ прошла: раунд {s.get('rounds')}, ${s.get('cost')}, {s.get('minutes')} мин, {s.get('diff_lines')} строк"
        elif state.startswith("fail"):
            state = f"✗ {state[6:]}"
        elif state == "running" and hb.get("slice") == sid and alive:
            state = "идёт"
        lines.append(f"  {sid}: {state}")
    return lines


def board_text(root: pathlib.Path) -> str:
    open_runs, closed = [], []
    for path in sorted(root.glob("*/run.toml")):
        try:
            run = sr.Run(path.parent)
            st = sr.replay(run)
        except Exception as exc:
            open_runs.append([f"▶ {path.parent.name}: не читается ({type(exc).__name__})"])
            continue
        if st["closed"]:
            closed.append(f"{run.name} ✓{len(st['pass'])}" + (f" ✗{len(st['fail'])}" if st["fail"] else ""))
        else:
            open_runs.append(describe(run))
    lines = [f"прогоны слайсов · {sr.iso()[11:19]}", ""]
    if open_runs:
        for block in open_runs:
            lines += block + [""]
    else:
        lines += ["активных прогонов нет: воркеры ничего не делают", ""]
    if closed:
        lines.append("закрытые: " + ", ".join(closed))
    return "\n".join(lines)


def cmd_board(args) -> int:
    """Redraws in place (cursor home, erase each line's tail and below): no full-screen clear, so no flicker."""
    root = pathlib.Path(args.root).resolve()
    sys.stdout.write("\033[?25l")
    try:
        while True:
            width = shutil.get_terminal_size((80, 24)).columns
            text = board_text(root)
            body = "\n".join(line[:width] + "\033[K" for line in text.splitlines())
            sys.stdout.write("\033[H" + body + "\033[J")
            sys.stdout.flush()
            if args.once:
                return 0
            time.sleep(args.every)
    finally:
        sys.stdout.write("\033[?25h\n")


def agent_status(agent: str) -> str:
    data = herdr("agent", "get", agent, timeout=15)
    if not data:
        return "missing"
    result = data.get("result") or {}
    found = result.get("agent") if isinstance(result.get("agent"), dict) else result
    return str(found.get("agent_status") or "unknown")


def notify_owner(title: str, body: str) -> None:
    """At most one Herdr notification per body every 15 minutes: a stuck wake must not flood the owner."""
    if sr.now() - _notified.get(body, 0) < NOTIFY_EVERY_S:
        return
    _notified[body] = sr.now()
    herdr("notification", "show", title, "--body", body[:200], "--sound", "request", timeout=15)


def deliver(run: sr.Run, agent: str, key: str, text: str) -> bool:
    """Prompt the architect once it is idle. False while it is busy, so the next tick tries again."""
    status = agent_status(agent)
    if status == "missing":
        notify_owner("zplan: architect gone", f"{run.name}: {key}; no Herdr agent named {agent}")
        return False
    if status == "blocked":
        notify_owner("zplan: architect waits for you", f"{run.name}: {key}; the architect pane shows a question")
        return False
    if status not in SETTLED:
        return False
    if herdr("agent", "prompt", agent, text, timeout=30) is None:
        return False
    run.event("architect_prompted", key=key, agent=agent)
    log(f"{run.name}: prompted {agent}: {key}")
    return True


def prompted(run: sr.Run) -> set[str]:
    return {e.get("key") for e in run.events() if e["event"] == "architect_prompted"}


def check_run(run: sr.Run, agent: str, stale_after: float) -> None:
    st = sr.replay(run)
    if st["closed"] or not st["pid"]:
        return
    done = prompted(run)
    status_cmd = f"python3.13 devtools/slice_run.py status {shlex.quote(str(run.dir))}"
    pending = [w for w in st["wakes"] if w["seq"] > st["acked"]]
    if pending:
        w = pending[-1]
        key = f"wake:{w['seq']}"
        if key not in done:
            deliver(run, agent, key, f"[slices {run.name}] WAKE {w['seq']}: {w['reason']}. Read `{status_cmd}` and the ledger, "
                    f"decide as docs/DEVELOPMENT.md says (integrate, retry, skip, next contracts), then `python3.13 devtools/slice_run.py ack {shlex.quote(str(run.dir))}`.")
        return
    if st["ended"]:
        return
    hb = sr._read_heartbeat(run)
    age = sr.now() - hb.get("ts", 0) if hb else 1e9
    if age > stale_after or (hb and not sr.pid_alive(hb.get("pid"))):
        key = f"silent:{st['pid']}"
        if key not in done:
            deliver(run, agent, key, f"[slices {run.name}] supervisor silent for {round(age)} s (pid {st['pid']}). "
                    f"Read `{status_cmd}`; restart with `python3.13 devtools/slice_run.py start {shlex.quote(str(run.dir))}` if it died.")


def beat(root: pathlib.Path, agent: str) -> None:
    """The monitor's own heartbeat (`slice_run.py start` refuses to start a run inside Herdr without a fresh one)."""
    try:
        tmp = root / ".monitor.tmp"
        tmp.write_text(json.dumps({"pid": os.getpid(), "ts": sr.now(), "agent": agent}))
        tmp.replace(root / sr.MONITOR_BEAT)
    except OSError as exc:
        log(f"heartbeat: {exc}")


def cmd_watch(args) -> int:
    root = pathlib.Path(args.root).resolve()
    log(f"watching {root} for agent {args.agent}, every {args.poll} s")
    while True:
        for path in sorted(root.glob("*/run.toml")):
            try:
                run = sr.Run(path.parent)
                check_run(run, args.agent, args.stale_after or run.cfg["stale_after_s"])
            except Exception as exc:  # One broken run directory must not silence the others.
                log(f"{path.parent.name}: {type(exc).__name__}: {str(exc)[:200]}")
        beat(root, args.agent)
        if args.once:
            return 0
        open_runs = sum(1 for p in root.glob("*/run.toml") if not sr.replay(sr.Run(p.parent))["closed"])
        idle = f"открытых прогонов: {open_runs}" if open_runs else "активных прогонов нет"
        sys.stdout.write(f"\r\033[K{sr.iso()[11:19]} слежу · {idle} · будить некого")
        sys.stdout.flush()
        time.sleep(args.poll)


def cmd_up(args) -> int:
    """Names the calling pane's agent and opens a monitor pane and a status pane: a right column (default) or,
    with --tab, a background tab `slices`. Focus stays in the calling pane either way."""
    if os.environ.get("HERDR_ENV") != "1" or not os.environ.get("HERDR_PANE_ID"):
        print("not inside a Herdr pane", file=sys.stderr)
        return 2
    me = os.environ["HERDR_PANE_ID"]
    if herdr("agent", "rename", me, args.agent) is None:
        return 1
    cwd = str(pathlib.Path.cwd())
    py = shlex.quote(sys.executable)
    root = shlex.quote(str(pathlib.Path(args.root).resolve()))
    if args.tab:
        made = herdr("tab", "create", "--workspace", os.environ.get("HERDR_WORKSPACE_ID", ""), "--label", "slices", "--cwd", cwd, "--no-focus")
        mon = made and made["result"]["root_pane"]["pane_id"]
    else:
        made = herdr("pane", "split", me, "--direction", "right", "--ratio", "0.7", "--cwd", cwd, "--no-focus")
        mon = made and made["result"]["pane"]["pane_id"]
    if not mon:
        return 1
    herdr("pane", "rename", mon, "slice monitor")
    # The pane id, not the name: it still resolves after the architect's agent restarts in the same pane.
    herdr("pane", "run", mon, f"{py} {shlex.quote(str(HERE))} watch --agent {me} --root {root}")
    status = herdr("pane", "split", mon, "--direction", "down", "--cwd", cwd, "--no-focus")
    if status:
        pane = status["result"]["pane"]["pane_id"]
        herdr("pane", "rename", pane, "slice status")
        herdr("pane", "run", pane, f"{py} {shlex.quote(str(HERE))} board --root {root}")
    print(json.dumps({"agent": args.agent, "monitor_pane": mon, "status_pane": (status or {}).get("result", {}).get("pane", {}).get("pane_id")}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("watch")
    p.add_argument("--agent", required=True)
    p.add_argument("--root", default=".local/slices")
    p.add_argument("--poll", type=float, default=10)
    p.add_argument("--stale-after", type=float, default=0)
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("board")
    p.add_argument("--root", default=".local/slices")
    p.add_argument("--every", type=float, default=2)
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_board)
    p = sub.add_parser("up")
    p.add_argument("--agent", default="zplan-arch")
    p.add_argument("--root", default=".local/slices")
    p.add_argument("--tab", action="store_true", help="a background tab instead of a right column")
    p.set_defaults(fn=cmd_up)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
