#!/usr/bin/env python3
"""Orchestrator board: who works on which zplan devtools run, round, reviewer verdicts, last agent message.

Devtools only (reads the local Zeroshot run stores read-only); the product never reads them. Interim view until the
S9 card flow (devtools/zeroshot/tasks/s9-roadmap.md) shows the same inside zplan.
Usage: python3 devtools/zeroshot/board.py [--hours 24] [--all]
"""
import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

RUNS = Path(os.environ.get("ZS_RUNS", "~/.local/state/zeroshot/runs")).expanduser()
ROLE = {"worker": "исполнитель", "acceptance": "ревьюер приёмки", "code": "ревьюер кода"}


def ago(ms, now):
    s = max(0, int(now - ms / 1000))
    return "%d ч %02d мин" % (s // 3600, s % 3600 // 60) if s >= 3600 else "%d мин" % (s // 60)


def one_line(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def board(db, now, show_all):
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    snap = json.loads(con.execute("select stored_json from v2_runs").fetchone()[0])["snapshot"]
    title = snap.get("title", "?")
    if not title.startswith("zplan "):
        return None
    terminal = snap.get("terminal") or snap.get("terminalResult") or {}
    finished = snap.get("phase") == "finished" or bool(terminal)
    if finished and not show_all:
        return None
    rnd, active, verdicts, first, last, said, tokens = 0, {}, {}, None, None, None, 0
    for (raw,) in con.execute("select event_json from v2_run_events order by sequence"):
        e = json.loads(raw)
        kind = e["kind"]
        if kind == "node_started":
            ref = e["reference"]
            rnd += ref["node"] == "worker"
            active[ref["execution"]] = ref["node"]
        elif kind == "node_completed":
            c = e["completion"]
            active.pop(c["reference"]["execution"], None)
            o = c["outcome"]
            if c["reference"]["node"] != "worker":
                verdict = (o.get("signals") or {}).get("verdict") or o.get("status")
                message = (o.get("diagnostic") or {}).get("message") or ""
                verdicts[c["reference"]["node"]] = (rnd, verdict, message)
        elif kind == "safe_log":
            first = first or e["timestamp"]
            last = e["timestamp"]
            if e.get("stream") == "output" and e["line"].strip() and not e["line"].lstrip().startswith('{"response"'):
                said = (e["line"], active.get(e["execution"], "?"))
        elif kind == "token_usage_observed":
            usage = e.get("usage") or {}
            tokens += (usage.get("inputTokens") or 0) + (usage.get("outputTokens") or 0)
    name = title[len("zplan "):]
    head = "%s  (%s)" % (name, snap["runId"])
    state = ("завершён: %s" % (terminal.get("reason") or terminal.get("status") or "?")) if finished else "идёт"
    lines = [head, "  статус: %s; раунд %d; идёт %s; последняя активность %s назад" % (
        state, rnd, ago(first, now) if first else "?", ago(last, now) if last else "?")]
    if active:
        lines.append("  сейчас работает: " + ", ".join(sorted({ROLE.get(n, n) for n in active.values()})))
    for node in ("acceptance", "code"):
        if node in verdicts:
            r, v, m = verdicts[node]
            lines.append("  %s, раунд %d: %s — %s" % (ROLE[node], r, v, one_line(m, 160)))
    if said:
        lines.append("  последнее сообщение (%s): %s" % (ROLE.get(said[1], said[1]), one_line(said[0], 160)))
    lines.append("  токены (вход+выход, наблюдённые): %.1f млн" % (tokens / 1e6))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--all", action="store_true", help="include finished runs")
    a = ap.parse_args()
    now = time.time()
    found = False
    for d in sorted(RUNS.iterdir(), reverse=True) if RUNS.is_dir() else []:
        db = d / "runs.sqlite3"
        if not db.is_file() or now - db.stat().st_mtime > a.hours * 3600:
            continue
        try:
            lines = board(db, now, a.all)
        except (sqlite3.Error, ValueError, KeyError, TypeError, AttributeError) as exc:
            lines = ["%s: не прочитан (%s)" % (d.name[:8], type(exc).__name__)]
        if lines:
            found = True
            print("\n".join(lines) + "\n")
    if not found:
        print("Нет идущих прогонов zplan за последние %g ч (--all покажет завершённые)." % a.hours)


if __name__ == "__main__":
    main()
