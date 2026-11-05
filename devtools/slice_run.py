#!/usr/bin/env python3
"""Unattended slice runner.

One worker per contract, in its own worktree, under checks the worker cannot
influence: the supervisor runs the acceptance check (red on base, green on the
result; the check lives in the worktree's `.slice/` and is never committed), applies
mechanical gates, then a blind reviewer. Passed slices land on
an integration branch; the architect moves them to `dev`. State is an append-only
ledger, so silence never looks like success: `wait` wakes the architect, `watchdog`
(launchd) covers a dead supervisor or a silent architect.

Commands: start | run | status | wait | ack | retry | skip | close | watchdog |
preflight | install-watchdog | uninstall-watchdog | notify
Rules: docs/DEVELOPMENT.md. Template: devtools/slice-contract.toml.
Ported from another (private) project's tools/slice_run.py at 23b74d4; project specifics live in run.toml
(`link`, `allow_read`, `worker_notes`, `base`), not here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import uuid

import ratchet

CLAUDE = "claude"
BASE_PATH = ":".join((str(pathlib.Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
WATCHDOG_LABEL = "com.zplan.slice-watchdog"
TOOLS = "Bash,Edit,Read,Write,Glob,Grep"
# USD per million tokens: input, output, cache read, cache write (1 h). Only used when a killed run has no result event.
PRICES = {"claude-opus-5-5": (4, 20, 0.2, 8), "claude-sonnet-5-5": (2, 10, 0.2, 4), "claude-haiku-5-5": (0.1, 0.5, 0.01, 0.2)}
RUN_DEFAULTS = {
    "base": "main", "worker_notes": "", "wake_after_passed": 3, "night_budget_usd": 150.0, "worker_model": "claude-sonnet-5-5", "review_model": "claude-opus-5-5",
    "worker_effort": "high", "review_effort": "high", "protected": [], "deny_read": [], "allow_read": [], "link": [],
    # lane_gate: the project's default test lane, run after every contract's own gates, so a pin in a module the
    # contract did not list fails the slice and not only the next full lane (2026-11-04, S1b).
    # `start` refuses a queue without one; "none: <reason>" opts out, for a project without a test lane.
    "lane_gate": "",
    # contract_review: a fresh reviewer reads the contract, its check and the code before any worker (2026-11-05: four
    # of five failed rounds that day were holes in the contract, found only by the diff reviewer after a worker round).
    "contract_review": True, "notify_cmd": "", "architect_session": "", "architect_cwd": "", "ack_timeout_s": 900, "stale_after_s": 180, "report_every_s": 10800,
    "min_battery_pct": 20, "limit_max_wait_s": 21600, "limit_default_wait_s": 1800, "tick_s": 1.0, "clock_gap_s": 60, "power_poll_s": 60,
}
SLICE_DEFAULTS = {
    "files": [], "check": "", "red_contains": "", "gates": [], "needs_owner": "", "depends": [], "max_diff_lines": 400, "worker_budget_usd": 10.0,
    "review": True, "review_budget_usd": 3.0, "idle_timeout_s": 660, "wall_timeout_s": 3600, "max_rounds": 2, "gate_timeout_s": 1200, "commit": "", "brief": "", "ratchet": {},
    # supersedes: earlier slices of this run whose behaviour this contract changes on purpose; their checks are not rerun.
    "supersedes": [],
}
WORKER_RULES = """You are a worker on one slice in an isolated working tree. Implement exactly the contract, nothing else.
Do not run git commit: the supervisor commits. Acceptance tests, frozen data and files outside the contract are locked; a denied write is final.
If the contract cannot be met without breaking a rule, do not work around it: stop and reply `BLOCKED: <reason>`.
Read narrowly, edit rather than rewrite, keep the diff small.
Run the check command and the unit tests of the code you touched before finishing. Do not run the whole suite: the supervisor runs the project gates.
Your report is not evidence: the supervisor reruns every check. End with at most 80 words: files changed and the check result."""
REVIEW_RULES = """You review one slice blind. You get the contract, its acceptance check and the diff, nothing else, and no tools. The supervisor has already run the check and the project tests: they pass.
Reject only for a violated requirement, non-goal or invariant on a realistic path. Name the failure scenario. No style preferences.
If you cannot tell from the diff, say so in a note and do not reject for it. Reply by the required schema."""
CONTRACT_REVIEW_RULES = """You review one slice contract before any worker starts. You get the contract and its acceptance check; your working directory is the repository at the slice's base, and you have read-only tools. A worker will implement the contract literally, then a blind reviewer will judge its diff against the contract's result. Find what would make a faithful implementation miss the result or fail that review:
1. Paths: every place the behaviour lives (entry points, callers, both tools of a pair, other modules applying the same rule). Search the code; a path the contract does not name is a finding.
2. Decisions: a decision that, followed literally, does not give the stated result on the result's own scenario (a retry, a second call, another caller, a restart).
3. The check: a scenario of the result the acceptance check does not exercise, so a wrong implementation would still pass it.
4. Pins: a test outside the contract's files that asserts what the change touches, so the default test lane would fail.
Reject only for a concrete finding with its scenario and file:line; otherwise accept, with notes. No style remarks. Reply by the required schema."""
CONTRACT_REVIEW_SCHEMA = {"type": "object", "required": ["verdict", "findings"], "properties": {
    "verdict": {"type": "string", "enum": ["accept", "reject"]},
    "findings": {"type": "array", "items": {"type": "object", "required": ["kind", "file", "scenario"], "properties": {
        "kind": {"type": "string", "enum": ["paths", "decision", "check", "pins"]}, "file": {"type": "string"},
        "line": {"type": "integer"}, "scenario": {"type": "string"}}}},
    "notes": {"type": "string"}}}
REVIEW_SCHEMA = {"type": "object", "required": ["verdict", "findings"], "properties": {
    "verdict": {"type": "string", "enum": ["accept", "reject"]},
    "findings": {"type": "array", "items": {"type": "object", "required": ["requirement", "file", "scenario"], "properties": {
        "requirement": {"type": "string"}, "file": {"type": "string"}, "line": {"type": "integer"}, "scenario": {"type": "string"}}}},
    "notes": {"type": "string"}}}


# A worker that keeps hitting these is missing something the brief should have given it.
REFUSED = re.compile(r"Operation not permitted|denied by your permission|has been denied|sandbox_violations|outside .*restricted|covered by a Read deny rule", re.I)


def now() -> float:
    return time.time()


def iso(ts: float | None = None) -> str:
    return dt.datetime.fromtimestamp(ts or now(), dt.timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    return True


def signature(output: str) -> str:
    """Stable identity of a failure: the failing test names, else the last line without digits."""
    names = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+)", output, re.M)))
    text = ",".join(names) if names else re.sub(r"\d+", "N", next((x for x in reversed(output.strip().splitlines()) if x.strip()), "no output"))[:160]
    return text[:200]


class Run:
    """A run directory: run.toml, contracts/<id>.toml, optional contracts/<id>/ acceptance files, ledger, heartbeat, logs."""

    def __init__(self, path: str | pathlib.Path):
        self.dir = pathlib.Path(path).resolve()
        self.cfg = {**RUN_DEFAULTS, **tomllib.loads((self.dir / "run.toml").read_text())}
        self.name = self.cfg["run"]
        self.repo = pathlib.Path(self.cfg["repo"]).resolve()
        self.ledger = self.dir / "ledger.jsonl"
        self.heartbeat = self.dir / "heartbeat.json"
        self.logs = self.dir / "logs"
        self.integration = f"slices/{self.name}"
        self.stage = "idle"
        self.slice = ""
        self.activity = ""
        self.gate_s = 0.0

    def event(self, kind: str, **fields) -> dict:
        row = {"ts": now(), "at": iso(), "event": kind, **fields}
        with open(self.ledger, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def events(self) -> list[dict]:
        if not self.ledger.exists():
            return []
        return [json.loads(x) for x in self.ledger.read_text().splitlines() if x.strip()]

    def beat(self, **extra) -> None:
        # One temporary file per writer: the supervisor beats from more than one thread, and a shared name let one
        # writer's rename remove the file the other was about to rename (2026-11-04, run a0s1b: FileNotFoundError).
        tmp = self.heartbeat.with_name("heartbeat.%d.%d.tmp" % (os.getpid(), threading.get_ident()))
        tmp.write_text(json.dumps({"pid": os.getpid(), "ts": now(), "slice": self.slice, "stage": self.stage, "activity": self.activity, **extra}))
        tmp.replace(self.heartbeat)

    def contract(self, sid: str) -> dict:
        path = self.dir / "contracts" / f"{sid}.toml"
        c = {**SLICE_DEFAULTS, **tomllib.loads(path.read_text())}
        c["id"] = sid
        c["text"] = path.read_text()
        c["acceptance_dir"] = self.dir / "contracts" / sid
        return c

    def git(self, *args, cwd=None, check=True, env=None) -> str:
        p = subprocess.run(["git", *args], cwd=cwd or self.repo, capture_output=True, text=True, errors="replace", env=env)
        if check and p.returncode:
            raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()[:300]}")
        return p.stdout.strip()

    def notify(self, text: str) -> None:
        notify(self.cfg.get("notify_cmd", ""), self.dir, f"{self.name}: {text}")


def notify(cmd: str, run_dir: pathlib.Path, text: str) -> None:
    """Neutral status only: slice ids and reasons, never client text or test output."""
    with open(run_dir / "notifications.log", "a") as f:
        f.write(f"{iso()} {text}\n")
    if not os.environ.get("SLICE_NO_OSA"):
        script = 'on run argv\ndisplay notification (item 1 of argv) with title "zplan slices"\nend run'
        subprocess.run(["osascript", "-e", script, text], capture_output=True, timeout=20, check=False)
    if cmd:
        try:
            subprocess.run(cmd, shell=True, input=text.encode(), capture_output=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            pass


def clean_env() -> dict:
    """Workers and gates get no provider keys, no session variables, nothing inherited by accident."""
    env = {"PATH": os.environ.get("SLICE_PATH_PREFIX", "") + BASE_PATH, "HOME": str(pathlib.Path.home()), "USER": os.environ.get("USER", ""),
           "LOGNAME": os.environ.get("LOGNAME", os.environ.get("USER", "")), "LANG": "en_US.UTF-8", "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
           "SHELL": "/bin/bash", "TERM": "dumb", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "DISABLE_AUTOUPDATER": "1",
           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "PYTHONDONTWRITEBYTECODE": "1",
           # Bytecode is read from an empty prefix, so a planted __pycache__ never stands in for the source.
           "PYTHONPYCACHEPREFIX": os.path.join(os.environ.get("TMPDIR", "/tmp"), "slice-no-pycache"),
           # git treats a denied ~/.gitconfig as fatal inside the sandbox; a worker needs no global git settings.
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "SLICE_GATE": "1"}
    for key in ("SLICE_FAKE_SCENARIO",):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def worker_settings(run: Run, c: dict, wt: pathlib.Path) -> dict:
    home = pathlib.Path.home()
    locked = list(run.cfg["protected"]) + [ACCEPTANCE]
    deny_write = [str(wt / p) for p in locked] + [str(wt / ".git"), str(run.repo / ".git")]
    # Absolute rules: on 2026-11-03 `Edit(./AGENTS.md)` from --settings did not bind a single file in a real worktree.
    root = "//" + str(wt).lstrip("/")
    deny_edit = [rule for p in [*locked, *run.cfg["link"]] for rule in (f"Edit({root}/{p})", f"Edit({root}/{p}/**)")]
    deny_read = [str(home)] + [str(pathlib.Path(p).expanduser()) for p in run.cfg["deny_read"]]
    allow_read = [str(wt), str(run.repo / ".git"), *[str((run.repo / link).resolve()) for link in run.cfg["link"] if link != ".local"], *[str(pathlib.Path(p).expanduser()) for p in run.cfg["allow_read"]]]
    read_rules = [f"Read({root}/.local/**)", "Read(//" + str((run.repo / ".local").resolve()).lstrip("/") + "/**)", "Read(**/.env)", "Read(**/.env.*)", "Read(**/*.pem)", "Read(**/*.key)"]
    return {"permissions": {"defaultMode": "dontAsk", "allow": TOOLS.split(","), "deny": deny_edit + read_rules},
            "sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False, "autoAllowBashIfSandboxed": True,
                        "filesystem": {"denyWrite": deny_write, "denyRead": deny_read, "allowRead": allow_read},
                        "network": {"allowedDomains": [], "allowLocalBinding": True}}}


def gate_policy(run: Run, c: dict, wt: pathlib.Path) -> str:
    """Seatbelt profile for checks: they execute worker-written code, so they get no network and cannot write outside the tree."""
    q = lambda p: json.dumps(str(p))
    home = pathlib.Path.home()
    locked = " ".join(f"(subpath {q(wt / p)})" for p in run.cfg["protected"] + [ACCEPTANCE])
    secrets = " ".join(f"(subpath {q(p)})" for p in (home / ".ssh", home / ".aws", home / ".config/gh", *[pathlib.Path(x).expanduser() for x in run.cfg["deny_read"]]))
    return "\n".join(("(version 1)", "(allow default)", '(deny network-outbound (remote ip "*:*"))', '(allow network-outbound (remote ip "localhost:*"))',
                      "(deny file-write*)", f'(allow file-write* (subpath {q(wt)}) (subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/dev"))',
                      f"(deny file-write* (subpath {q(run.repo / '.git')}) (subpath {q(wt / '.git')}) {locked})", f"(deny file-read* {secrets})"))


# Acceptance checks are the architect's oracle for one slice, not tests to keep (docs/designs/2026-11-04-w0-worker-
# contract.md 3.3): they are copied into this folder of the worktree, which ignores itself, and never reach a commit.
# A durable test is part of a change only when the brief asks the worker for one.
ACCEPTANCE = ".slice"


def install_acceptance(c: dict, wt: pathlib.Path) -> None:
    """Copies the contract's acceptance files into `.slice/` (mirroring their paths in the contract folder) and makes
    the folder ignore itself. Called before the red run and again before every green run, so a copy changed in the
    worktree never decides a result."""
    root = wt / ACCEPTANCE
    if root.is_symlink() or root.is_file():
        root.unlink()
    elif root.exists():
        shutil.rmtree(root)
    root.mkdir()
    (root / ".gitignore").write_text("*\n")
    for rel in acceptance_paths(c):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(c["acceptance_dir"] / rel, target)


def acceptance_paths(c: dict) -> list[str]:
    root = c["acceptance_dir"]
    if not root.is_dir():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


# An acceptance check runs without the current directory first on sys.path, so a module the worker plants in the tree
# (even an ignored one) cannot answer for the copy in `.slice/`; the check names its paths in PYTHONPATH.
CHECK_ENV = {"PYTHONSAFEPATH": "1"}


def acceptance_modules(c: dict) -> list[str]:
    return sorted({pathlib.PurePath(p).stem for p in acceptance_paths(c) if p.endswith(".py")})


def lane_problem(run: "Run") -> str:
    value = str(run.cfg["lane_gate"]).strip()
    if not value or (value.startswith("none") and not (value.startswith("none:") and value[5:].strip())):
        return 'run.toml: lane_gate must name the project\'s default test lane, or be "none: <reason>"'
    return ""


def lane(run: "Run") -> str:
    """The run's default test lane; "" when the run opted out ("none: <reason>")."""
    value = str(run.cfg["lane_gate"]).strip()
    return "" if value.startswith("none:") else value


def lane_green(run: "Run", tree: str) -> bool:
    return any(e["event"] == "lane_green" and e.get("tree") == tree for e in run.events())


def allowed(path: str, patterns: list[str]) -> bool:
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in patterns)


def is_locked(path: str, locked: list[str]) -> bool:
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in locked)


class Agent:
    """One headless Claude process: stream reader, idle and wall timers, process-group kill."""

    def __init__(self, run: Run, name: str, model: str, cmd: list[str], cwd: pathlib.Path, stdin_text: str | None, idle_s: float, wall_s: float):
        self.run, self.name, self.model, self.cwd, self.idle_s, self.wall_s = run, name, model, cwd, idle_s, wall_s
        self.cmd, self.stdin_text = cmd, stdin_text
        self.result, self.usage, self.peak, self.turns, self.limit_text = None, {"in": 0, "out": 0, "cr": 0, "cc": 0}, 0, 0, ""
        self.refused = 0
        self.seen, self.outcome, self.session = set(), "", ""
        self.last = now()
        run.logs.mkdir(exist_ok=True)
        self.log = run.logs / f"{name}.ndjson"

    def _read(self) -> None:
        with open(self.log, "ab") as out:
            for raw in self.proc.stdout:
                out.write(raw)
                out.flush()
                self.last = now()
                try:
                    self._parse(json.loads(raw))
                except (ValueError, KeyError, TypeError):
                    if b"limit" in raw and b"reset" in raw:
                        self.limit_text = raw.decode(errors="replace")[:300]

    def _parse(self, e: dict) -> None:
        kind = e.get("type")
        if kind == "system" and e.get("subtype") == "init":
            self.session = e.get("session_id", "")
        elif kind == "assistant":
            m = e.get("message") or {}
            if e.get("error") == "rate_limit" or (e.get("isApiErrorMessage") and "limit" in json.dumps(m)):
                self.limit_text = json.dumps(m.get("content"))[:300]
            mid, u = m.get("id"), m.get("usage")
            if mid and u and mid not in self.seen:
                self.seen.add(mid)
                self.turns += 1
                self.usage["in"] += u.get("input_tokens", 0)
                self.usage["out"] += u.get("output_tokens", 0)
                self.usage["cr"] += u.get("cache_read_input_tokens", 0)
                self.usage["cc"] += u.get("cache_creation_input_tokens", 0)
                self.peak = max(self.peak, u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0))
            for block in m.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    self.run.activity = f"{block.get('name')} {str(inp.get('file_path') or inp.get('command') or inp.get('pattern') or '')[:70]}"
        elif kind == "user":
            for block in (e.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and REFUSED.search(json.dumps(block.get("content"), ensure_ascii=False)):
                    self.refused += 1
        elif kind == "result":
            self.result = e
            u = e.get("usage") or {}
            if u:  # Per-message usage in the stream undercounts output; the result has the totals.
                self.usage = {"in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0), "cr": u.get("cache_read_input_tokens", 0), "cc": u.get("cache_creation_input_tokens", 0)}
            text = str(e.get("result") or "")
            if e.get("is_error") and re.search(r"limit", text, re.I) and re.search(r"reset", text, re.I):
                self.limit_text = text[:300]

    def cost(self) -> float:
        if self.result and self.result.get("total_cost_usd") is not None:
            return float(self.result["total_cost_usd"])
        p = PRICES.get(self.model, PRICES["claude-opus-5-5"])
        return round((self.usage["in"] * p[0] + self.usage["out"] * p[1] + self.usage["cr"] * p[2] + self.usage["cc"] * p[3]) / 1e6, 4)

    def execute(self) -> str:
        """Returns ok | error | hung | wall | killed | limit | power. A silent process is killed, never waited on."""
        self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, env=clean_env(), stdin=subprocess.PIPE if self.stdin_text is not None else subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        if self.stdin_text is not None:
            self.proc.stdin.write(self.stdin_text.encode())
            self.proc.stdin.close()
        self.run.event("agent_start", name=self.name, model=self.model, pid=self.proc.pid)
        reader = threading.Thread(target=self._read, daemon=True)
        reader.start()
        started = self.last = now()
        previous = started
        forced = ""
        try:
            forced = self._supervise(started, previous)
        finally:
            if self.proc.poll() is None:
                kill_group(self.proc)
        reader.join(timeout=5)
        code = self.proc.wait()
        if not reader.is_alive():
            self.proc.stdout.close()
        if forced:
            self.outcome = forced
        elif self.limit_text:
            self.outcome = "limit"
        elif code < 0 or (self.result is None and code != 0):
            self.outcome = "killed"
        elif self.result is None or self.result.get("is_error"):
            self.outcome = "error"
        else:
            self.outcome = "ok"
        self.run.event("agent_end", name=self.name, outcome=self.outcome, exit=code, subtype=(self.result or {}).get("subtype"), cost=self.cost(),
                       turns=self.turns, peak_ctx=self.peak, minutes=round((now() - started) / 60, 2), refused=self.refused, **self.usage)
        return self.outcome

    def _supervise(self, started: float, previous: float) -> str:
        forced = ""
        while self.proc.poll() is None:
            time.sleep(self.run.cfg["tick_s"])
            t = now()
            if t - previous > self.run.cfg["clock_gap_s"]:
                # The machine slept or the process was frozen: the gap is not the worker's silence.
                self.run.event("clock_gap", seconds=round(t - previous), name=self.name)
                self.run.notify(f"clock gap {round(t - previous)} s during {self.name}")
                self.last = t
                started += t - previous
            previous = t
            self.run.beat(agent_pid=self.proc.pid, idle=round(t - self.last), tokens=sum(self.usage.values()), peak=self.peak)
            if t - self.last > self.idle_s:
                forced = "hung"
            elif t - started > self.wall_s:
                forced = "wall"
            elif (why := battery_stop(self.run)):
                forced = "power"
                self.run.event("power_stop", detail=why)
            if forced:
                kill_group(self.proc)
                break
        return forced


def kill_group(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGCONT, signal.SIGTERM):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            return
    deadline = now() + 3
    while proc.poll() is None and now() < deadline:
        time.sleep(0.1)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def wait_for_power(run: Run, why: str) -> None:
    """A low battery pauses the slice until the Mac is on power (or charged above the floor) instead of failing it:
    an unattended night must not lose its queue to an unplugged charger. The heartbeat goes on while it waits."""
    run.event("power_wait", detail=why)
    run.notify(f"{why}: waiting for power")
    while why:
        run.stage = f"waiting for power ({why})"
        end = now() + run.cfg["power_poll_s"]
        while now() < end:
            time.sleep(min(run.cfg["tick_s"], max(0.01, end - now())))
            run.beat()
        run._battery_at = 0  # bypass the once-a-minute throttle: this loop sets its own pace
        why = battery_stop(run)
    run.event("power_back")


def battery_stop(run: Run) -> str:
    """Throttled to one pmset call a minute. Empty unless on battery below the floor."""
    t = now()
    if t - getattr(run, "_battery_at", 0) < 60:
        return ""
    run._battery_at = t
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"(\d+)%; discharging", out)
    if m and int(m.group(1)) < run.cfg["min_battery_pct"]:
        return f"battery {m.group(1)}%"
    return ""


def reset_wait(text: str, default: float, now_ts: float | None = None) -> float:
    """Seconds until a limit reset named like `resets 3:40pm (Europe/Moscow)`."""
    m = re.search(r"resets? (?:at )?(\d{1,2})(?::(\d{2}))?\s*([ap]m)", text, re.I)
    if not m:
        return default
    hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
    current = dt.datetime.fromtimestamp(now_ts or now()).astimezone()
    target = current.replace(hour=hour, minute=int(m.group(2) or 0), second=0, microsecond=0)
    if target <= current:
        target += dt.timedelta(days=1)
    return (target - current).total_seconds() + 120


def run_gate(run: Run, c: dict, wt: pathlib.Path, command: str, label: str, env: dict | None = None) -> tuple[int, str]:
    """Runs a check under the seatbelt profile; returns exit code and full output (kept in logs, never sent to a notification)."""
    run.stage, run.activity = label, command[:70]
    run.logs.mkdir(exist_ok=True)
    log = run.logs / f"{c['id']}.{label}.txt"
    # macOS forbids a nested seatbelt (sandbox_apply exits 71). A gate that is itself run inside a gate or a worker
    # sandbox (SLICE_GATE=1, set by clean_env) is already confined by the outer profile, so it runs without a new one.
    nested = os.environ.get("SLICE_GATE") == "1"
    cmd = ["/bin/bash", "-c", command] if nested else ["sandbox-exec", "-p", gate_policy(run, c, wt), "/bin/bash", "-c", command]
    began = now()
    try:
        with open(log, "wb") as out:
            proc = subprocess.Popen(cmd, cwd=wt, env={**clean_env(), **(env or {})}, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            deadline = now() + c["gate_timeout_s"]
            while proc.poll() is None:
                time.sleep(run.cfg["tick_s"])
                run.beat()
                if now() > deadline:
                    kill_group(proc)
                    return 124, f"gate timeout after {c['gate_timeout_s']} s: {command}"
        return proc.returncode, log.read_text(errors="replace")
    finally:
        run.gate_s += now() - began


def commit_prefix(run: Run, c: dict) -> str:
    m = re.match(r"\[[^\]]+\]", c.get("commit") or "")
    return m.group(0) if m else f"[{run.name} {c['id']}]"


def prepare(run: Run, c: dict) -> tuple[pathlib.Path, str]:
    sid = c["id"]
    wt = run.repo / ".worktrees" / f"slice-{run.name}-{sid}"
    branch = f"slice/{run.name}/{sid}"
    if wt.exists():
        run.git("worktree", "remove", "--force", str(wt))
    run.git("branch", "-D", branch, check=False)
    run.git("worktree", "add", "-q", "-b", branch, str(wt), run.integration)
    for link in run.cfg["link"]:
        if (run.repo / link).exists() and not (wt / link).exists():
            (wt / link).symlink_to(run.repo / link)
    install_acceptance(c, wt)
    return wt, branch


def contract_digest(c: dict) -> str:
    """Recorded at each start, so a contract changed between attempts shows in the ledger."""
    h = hashlib.sha256(c["text"].encode())
    for rel in acceptance_paths(c):
        h.update((c["acceptance_dir"] / rel).read_bytes())
    return h.hexdigest()[:12]


def worker_rules(run: Run) -> str:
    notes = run.cfg["worker_notes"].strip()
    return f"{WORKER_RULES}\n{notes}" if notes else WORKER_RULES


def worker_prompt(c: dict, note: str) -> str:
    extra = f"\n\nA previous attempt on this tree failed. Fix only this, keep what is already right:\n{note}" if note else ""
    return f"Contract {c['id']}: {c.get('title', '')}\nFiles you may change: {', '.join(c['files'])}\nCheck command: {c['check']}\n\n{c['brief']}{extra}"


def run_worker(run: Run, c: dict, wt: pathlib.Path, round_no: int, note: str, attempt: int) -> Agent:
    run.stage = f"worker r{round_no}"
    settings = worker_settings(run, c, wt)
    name = f"{c['id']}.r{round_no}.a{attempt}.worker"
    cmd = [CLAUDE, "-p", worker_prompt(c, note), "--model", run.cfg["worker_model"], "--effort", run.cfg["worker_effort"], "--output-format", "stream-json", "--verbose",
           "--restricted", "--strict-mcp-config", "--tools", TOOLS, "--permission-mode", "dontAsk", "--permission-prompts", "none", "--settings", json.dumps(settings),
           "--append-system-prompt", worker_rules(run), "--max-budget-usd", str(c["worker_budget_usd"]), "--session-id", str(uuid.uuid4())]
    agent = Agent(run, name, run.cfg["worker_model"], cmd, wt, None, c["idle_timeout_s"], c["wall_timeout_s"])
    agent.execute()
    return agent


def run_contract_review(run: Run, c: dict, wt: pathlib.Path) -> Agent:
    """The contract review before any worker: read-only tools on the base tree, the worker's read limits."""
    run.stage, run.activity = "contract review", ""
    acceptance = "\n\n".join(f"--- {rel}\n{(c['acceptance_dir'] / rel).read_text(errors='replace')}" for rel in acceptance_paths(c))
    prompt = f"{CONTRACT_REVIEW_RULES}\n\n<contract>\n{c['text']}\n</contract>\n\n<acceptance_check>\n{acceptance}\n</acceptance_check>"
    cmd = [CLAUDE, "-p", "--model", run.cfg["review_model"], "--effort", run.cfg["review_effort"], "--output-format", "stream-json", "--verbose", "--restricted", "--strict-mcp-config",
           "--tools", "Read,Grep,Glob", "--permission-mode", "dontAsk", "--permission-prompts", "none", "--settings", json.dumps(worker_settings(run, c, wt)),
           "--json-schema", json.dumps(CONTRACT_REVIEW_SCHEMA), "--max-budget-usd", str(c["review_budget_usd"]), "--no-session-persistence"]
    agent = Agent(run, f"{c['id']}.contract_review", run.cfg["review_model"], cmd, wt, prompt, c["idle_timeout_s"], c["wall_timeout_s"])
    agent.execute()
    return agent


def run_review(run: Run, c: dict, wt: pathlib.Path, diff: str, round_no: int) -> Agent:
    run.stage, run.activity = f"review r{round_no}", ""
    acceptance = "\n\n".join(f"--- {rel}\n{(c['acceptance_dir'] / rel).read_text(errors='replace')}" for rel in acceptance_paths(c))
    prompt = f"{REVIEW_RULES}\n\n<contract>\n{c['text']}\n</contract>\n\n<acceptance_check_part_of_the_contract>\n{acceptance}\n</acceptance_check_part_of_the_contract>\n\n<diff>\n{diff}\n</diff>"
    cmd = [CLAUDE, "-p", "--model", run.cfg["review_model"], "--effort", run.cfg["review_effort"], "--output-format", "stream-json", "--verbose", "--restricted", "--strict-mcp-config",
           "--tools", "", "--permission-mode", "dontAsk", "--permission-prompts", "none", "--json-schema", json.dumps(REVIEW_SCHEMA), "--max-budget-usd", str(c["review_budget_usd"]), "--no-session-persistence"]
    agent = Agent(run, f"{c['id']}.r{round_no}.review", run.cfg["review_model"], cmd, wt, prompt, c["idle_timeout_s"], c["wall_timeout_s"])
    agent.execute()
    return agent


def mechanical_gates(run: Run, c: dict, wt: pathlib.Path, base: str) -> tuple[str, str, str]:
    """Returns (failed gate or "", signature, detail). Paths and size first: cheap, and they do not execute worker code."""
    run.git("add", "-A", cwd=wt)
    names = [x for x in run.git("diff", "--cached", "--name-only", base, cwd=wt).splitlines() if x]
    if not names:
        return "no_change", "no_change", "The tree has no change against the base."
    locked = run.cfg["protected"] + [ACCEPTANCE]
    touched = [p for p in names if is_locked(p, locked)]
    if touched:
        return "locked_path", "locked:" + ",".join(touched), f"Locked paths changed: {', '.join(touched)}. Restore them."
    outside = [p for p in names if not allowed(p, c["files"])]
    if outside:
        return "outside_files", "outside:" + ",".join(outside), f"Files outside the contract changed: {', '.join(outside)}. Undo them."
    lines = sum(int(a) + int(d) for a, d, *_ in (row.split("\t") for row in run.git("diff", "--cached", "--numstat", base, cwd=wt).splitlines()) if a != "-")
    if lines > c["max_diff_lines"]:
        return "diff_too_big", "diff_too_big", f"The diff has {lines} changed lines; the contract allows {c['max_diff_lines']}."
    found = ratchet.compare(ratchet.sources_at(wt, base), ratchet.sources_in(wt), c["ratchet"])["problems"]
    if found:
        return "ratchet", signature("\n".join(found)), "The test ratchet refuses the change:\n" + "\n".join(found)
    tree = run.git("write-tree", cwd=wt)
    install_acceptance(c, wt)
    code, out = run_gate(run, c, wt, c["check"], "green", CHECK_ENV)
    if code:
        return "green", signature(out), f"Acceptance check failed (exit {code}):\n{out[-3000:]}"
    # The checks of the slices this run already passed run again: a later slice must not undo an earlier one.
    passed = replay(run)["pass"]
    for prior in [run.contract(sid) for sid in run.cfg["queue"] if sid in passed and sid not in c["supersedes"] and sid != c["id"]]:
        install_acceptance(prior, wt)
        code, out = run_gate(run, c, wt, prior["check"], f"check_{prior['id']}", CHECK_ENV)
        if code:
            return f"check:{prior['id']}", signature(out), (f"The acceptance check of the earlier slice {prior['id']} now fails (exit {code}): "
                                                           f"keep its behaviour.\n{out[-3000:]}")
    install_acceptance(c, wt)
    gates = c["gates"] + ([lane(run)] if lane(run) and lane(run) not in c["gates"] else [])
    for i, gate in enumerate(gates):
        code, out = run_gate(run, c, wt, gate, f"gate{i}")
        if code:
            note = ("\nIf a failing test lives in a module outside your files, do not change behaviour back to satisfy it: reply "
                    "`BLOCKED: <the test>`, so the architect fixes the contract." if gate == lane(run) else "")
            return f"gate:{gate}", signature(out), f"Project check `{gate}` failed (exit {code}):\n{out[-3000:]}{note}"
    run.git("add", "-A", cwd=wt)
    changed = [x for x in run.git("diff-index", "--cached", "--name-only", tree, cwd=wt).splitlines() if x]
    if changed:
        return "tree_changed", "tree_changed:" + ",".join(changed), f"Files changed while the checks ran: {', '.join(changed)}. A check must leave the tree as it found it."
    return "", "", ""


def run_slice(run: Run, sid: str) -> dict:
    """Returns {"result": "pass"|"fail", "reason", ...}. Never raises for worker failures."""
    c = run.contract(sid)
    run.slice, run.stage, run.activity = sid, "prepare", ""
    run.beat()
    started, spent = now(), 0.0
    run.gate_s = 0.0
    if (problem := lane_problem(run)):
        return {"result": "fail", "reason": "contract_invalid", "detail": problem}
    wt, branch = prepare(run, c)
    code, out = run_gate(run, c, wt, c["check"], "red", CHECK_ENV)
    lost = [m for m in acceptance_modules(c) if f"No module named '{m}'" in out]
    if lost:
        return {"result": "fail", "reason": "contract_invalid", "detail": f"The check cannot import its own module {lost[0]}: name .slice in its PYTHONPATH."}
    if code == 0:
        return {"result": "fail", "reason": "contract_invalid", "detail": "The check passes on the base: it proves nothing."}
    if c["red_contains"] and c["red_contains"] not in out:
        return {"result": "fail", "reason": "contract_invalid", "detail": f"The check fails on the base for another reason: {signature(out)}"}
    run.event("red_ok", slice=sid, exit=code, signature=signature(out))
    base = run.git("rev-parse", "HEAD", cwd=wt)
    base_tree = run.git("rev-parse", "HEAD^{tree}", cwd=wt)
    if lane(run) and not lane_green(run, base_tree):
        code, out = run_gate(run, c, wt, lane(run), "lane_base")
        if code:
            return {"result": "fail", "reason": "lane_red_on_base",
                    "detail": f"The default lane fails on the base before any work (exit {code}); fix the base or the lane first:\n{out[-2000:]}"}
        run.event("lane_green", tree=base_tree)
    if run.cfg["contract_review"]:
        review = run_contract_review(run, c, wt)
        spent += review.cost()
        data = (review.result or {}).get("structured_output") if review.outcome == "ok" else None
        if not isinstance(data, dict) or data.get("verdict") not in ("accept", "reject"):
            return {"result": "fail", "reason": "review_error", "detail": f"The contract reviewer ended as {review.outcome} without a verdict."}
        run.event("contract_review", slice=sid, verdict=data["verdict"], findings=data.get("findings", []),
                  notes=str(data.get("notes", ""))[:400], cost=review.cost())
        if data["verdict"] == "reject":
            return {"result": "fail", "reason": "contract_rejected", "detail": "A reviewer rejected the contract before any worker:\n"
                    + json.dumps(data.get("findings", []), ensure_ascii=False, indent=1)[:3000]}
    note, last_sig, attempt, round_no, totals = "", None, 0, 1, {"in": 0, "out": 0, "cr": 0, "cc": 0}
    peak = 0
    while round_no <= c["max_rounds"]:
        if (why := battery_stop(run)):
            wait_for_power(run, why)
        attempt += 1
        if budget_left(run) <= 0:
            return {"result": "fail", "reason": "budget_night", "detail": "Night budget spent."}
        agent = run_worker(run, c, wt, round_no, note, attempt)
        spent += agent.cost()
        peak = max(peak, agent.peak)
        for k in totals:
            totals[k] += agent.usage[k]
        outcome = agent.outcome
        if outcome == "limit":
            wait = reset_wait(agent.limit_text, run.cfg["limit_default_wait_s"])
            run.event("limit", slice=sid, wait_s=round(wait), text=agent.limit_text[:160])
            if wait > run.cfg["limit_max_wait_s"]:
                return {"result": "fail", "reason": "limit_too_long", "detail": agent.limit_text[:160]}
            run.notify(f"subscription limit, waiting {round(wait / 60)} min")
            pause(run, wait)
            continue
        if outcome == "power":  # the worker was stopped on a low battery: wait on the charger, the round is not spent
            wait_for_power(run, "battery below the floor during the worker")
            continue
        if outcome == "error" and (agent.result or {}).get("subtype") == "error_max_budget_usd":
            return {"result": "fail", "reason": "budget", "detail": f"Worker budget {c['worker_budget_usd']} USD spent."}
        text = str((agent.result or {}).get("result") or "")
        if outcome == "ok" and text.lstrip().startswith("BLOCKED"):
            return {"result": "fail", "reason": "blocked", "detail": text[:400]}
        if outcome == "ok":
            failed, sig, detail = mechanical_gates(run, c, wt, base)
        else:
            failed, sig, detail = f"worker_{outcome}", f"worker_{outcome}", f"The previous worker process ended as {outcome}; its work is still in the tree."
        if not failed:
            diff = run.git("diff", "--cached", "--unified=8", base, cwd=wt)
            if not c["review"]:
                return finish(run, c, wt, branch, base, spent, started, round_no, totals, peak)
            limit_waits = 0
            while True:
                review = run_review(run, c, wt, diff, round_no)
                spent += review.cost()
                if review.outcome == "power":
                    wait_for_power(run, "battery below the floor during the review")
                    continue
                if review.outcome != "limit" or limit_waits >= 3:
                    break
                limit_waits += 1
                wait = reset_wait(review.limit_text, run.cfg["limit_default_wait_s"])
                run.event("limit", slice=sid, wait_s=round(wait), text=review.limit_text[:160], stage="review")
                if wait > run.cfg["limit_max_wait_s"]:
                    return {"result": "fail", "reason": "limit_too_long", "detail": review.limit_text[:160]}
                run.notify(f"subscription limit in review, waiting {round(wait / 60)} min")
                pause(run, wait)
            data = (review.result or {}).get("structured_output") if review.outcome == "ok" else None
            if not isinstance(data, dict) or data.get("verdict") not in ("accept", "reject"):
                run.event("review_error", slice=sid, outcome=review.outcome)
                return {"result": "fail", "reason": "review_error", "detail": f"Reviewer ended as {review.outcome} without a verdict."}
            run.event("review", slice=sid, round=round_no, verdict=data["verdict"], findings=data.get("findings", []), notes=str(data.get("notes", ""))[:400], cost=review.cost())
            if data["verdict"] == "accept":
                return finish(run, c, wt, branch, base, spent, started, round_no, totals, peak)
            failed, sig = "review", "review:" + ",".join(sorted(f"{f.get('file')}:{f.get('requirement', '')[:24]}" for f in data.get("findings", [])))
            detail = "A blind reviewer rejected the diff:\n" + json.dumps(data.get("findings", []), ensure_ascii=False, indent=1)[:3000]
        run.event("round_failed", slice=sid, round=round_no, gate=failed, signature=sig[:200])
        if sig == last_sig:
            return {"result": "fail", "reason": "same_failure", "detail": sig[:200]}
        last_sig, note = sig, detail
        round_no += 1
    return {"result": "fail", "reason": "rounds_exhausted", "detail": str(last_sig)[:200]}


def finish(run: Run, c: dict, wt: pathlib.Path, branch: str, base: str, spent: float, started: float, round_no: int, totals: dict, peak: int) -> dict:
    sid = c["id"]
    numstat = run.git("diff", "--cached", "--numstat", base, cwd=wt)
    lines = sum(int(a) + int(d) for a, d, *_ in (row.split("\t") for row in numstat.splitlines()) if a != "-")
    is_test = lambda path: (lambda parts: "tests" in parts[:-1] or parts[-1].startswith("test_") or pathlib.PurePath(parts[-1]).stem.endswith("_test"))(pathlib.PurePath(path).parts)
    product, tests = [0, 0], [0, 0]
    for row in numstat.splitlines():
        a, d, path = row.split("\t", 2)
        if a != "-":
            part = tests if is_test(path) else product
            part[0], part[1] = part[0] + int(a), part[1] + int(d)
    text_pins = list(ratchet.compare(ratchet.sources_at(wt, base), ratchet.sources_in(wt))["text_pins"])
    title = c.get("commit") or f"{commit_prefix(run, c)} {c.get('title', sid)}"
    # --no-verify: the ratchet ran against the contract already; the commit-msg hook is for direct commits.
    run.git("commit", "-q", "--no-verify", "-m", title, "-m", f"Worker: {run.cfg['worker_model']}, round {round_no}. Checks rerun by devtools/slice_run.py.", cwd=wt)
    sha = run.git("rev-parse", "HEAD", cwd=wt)
    if lane(run):  # the lane passed on exactly this tree (mechanical_gates refuses a tree changed by the checks)
        run.event("lane_green", tree=run.git("rev-parse", "HEAD^{tree}", cwd=wt))
    head = run.git("rev-parse", run.integration)
    if subprocess.run(["git", "merge-base", "--is-ancestor", head, sha], cwd=run.repo).returncode:
        return {"result": "fail", "reason": "merge", "detail": "The integration branch moved under the slice."}
    run.git("update-ref", f"refs/heads/{run.integration}", sha, head)
    run.git("worktree", "remove", "--force", str(wt))
    run.git("branch", "-q", "-D", branch, check=False)
    return {"result": "pass", "sha": sha, "diff_lines": lines, "files": len(numstat.splitlines()), "cost": round(spent, 4), "minutes": round((now() - started) / 60, 2), "rounds": round_no, "peak_ctx": peak,
            "brief_chars": len(c["text"]), "lines_product": product, "lines_tests": tests, "text_pins": text_pins, "gate_s": round(run.gate_s, 2), **totals}


def pause(run: Run, seconds: float) -> None:
    run.stage = "waiting for limit reset"
    end = now() + seconds
    while now() < end:
        time.sleep(min(run.cfg["tick_s"], max(0.05, end - now())))
        run.beat(resume_in=round(end - now()))


def budget_left(run: Run) -> float:
    spent = sum(e.get("cost", 0) or 0 for e in run.events() if e["event"] in ("agent_end",))
    return run.cfg["night_budget_usd"] - spent


def replay(run: Run) -> dict:
    """Ledger to state. The ledger is the only truth about a run."""
    st = {"pass": [], "fail": {}, "deferred": {}, "started": {}, "wakes": [], "acked": 0, "closed": False, "alerts": {}, "ended": None, "pid": None, "slices": {}}
    for e in run.events():
        k = e["event"]
        s = e.get("slice")
        if k == "run_start":
            st["pid"], st["ended"] = e.get("pid"), None
        elif k == "run_end":
            st["ended"] = e
        elif k == "slice_start":
            st["started"][s] = st["started"].get(s, 0) + 1
            st["slices"].setdefault(s, {})["state"] = "running"
        elif k == "slice_pass":
            st["pass"].append(s)
            st["slices"].setdefault(s, {}).update(state="pass", **{x: e.get(x) for x in ("cost", "minutes", "rounds", "peak_ctx", "diff_lines", "sha", "lines_tests", "text_pins")})
        elif k == "slice_fail":
            st["fail"][s] = e.get("reason")
            st["slices"].setdefault(s, {}).update(state=f"fail: {e.get('reason')}")
        elif k == "slice_retry":
            st["fail"].pop(s, None)
            st["started"].pop(s, None)
            st["slices"].setdefault(s, {}).update(state="queued")
        elif k == "deferred":
            st["fail"].pop(s, None)
            st["deferred"][s] = e.get("why")
            st["slices"].setdefault(s, {}).update(state="deferred")
        elif k == "wake":
            st["wakes"].append(e)
        elif k == "ack":
            st["acked"] = e.get("seq", 0)
        elif k == "closed":
            st["closed"] = True
        elif k == "alert":
            st["alerts"][e.get("key")] = e["ts"]
    return st


def wake(run: Run, reason: str, **fields) -> None:
    st = replay(run)
    seq = len(st["wakes"]) + 1
    run.event("wake", seq=seq, reason=reason, **fields)
    run.notify(f"wake {seq}: {reason}")


def cmd_run(args) -> int:
    run = Run(args.dir)
    with open(run.dir / "lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another supervisor holds this run", file=sys.stderr)
            return 3
        return supervise(run)


def supervise(run: Run) -> int:
    if not run.git("rev-parse", "--verify", "-q", f"refs/heads/{run.integration}", check=False):
        run.git("branch", run.integration, run.cfg["base"])
    elif run.git("rev-list", "--count", f"{run.cfg['base']}..{run.integration}") == "0":
        # Nothing landed yet and the base moved (a harness fix before a retry): build on the current base.
        base, old = run.git("rev-parse", run.cfg["base"]), run.git("rev-parse", run.integration)
        if base != old:
            run.git("update-ref", f"refs/heads/{run.integration}", base, old)
            run.event("integration_moved", old=old, new=base)
    reap_orphans(run)
    run.event("run_start", pid=os.getpid(), integration=run.git("rev-parse", run.integration), lane_gate=str(run.cfg["lane_gate"]))
    run.beat()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _raise_interrupt)
    stop_beat = threading.Event()
    threading.Thread(target=_idle_beat, args=(run, stop_beat), daemon=True).start()
    st = replay(run)
    passed_at_wake = _passed_since_last_ack(run, st)
    code, reason = 0, "queue_done"
    try:
        for sid in run.cfg["queue"]:
            st = replay(run)
            if sid in st["pass"] or sid in st["deferred"]:
                continue
            if sid in st["fail"]:
                code, reason = 10, f"{sid}:{st['fail'][sid]}"
                break
            c = run.contract(sid)
            why = c["needs_owner"] or next((f"depends on {d}" for d in c["depends"] if d not in st["pass"]), "")
            if why:
                run.event("deferred", slice=sid, why=why)
                run.notify(f"{sid} deferred")
                continue
            if st["started"].get(sid, 0) >= 2:
                run.event("slice_fail", slice=sid, reason="restarts", detail="Started twice without an outcome.")
                code, reason = 10, f"{sid}:restarts"
                break
            run.event("slice_start", slice=sid, contract_sha=contract_digest(c))
            try:
                res = run_slice(run, sid)
            except Exception as exc:  # A supervisor bug must wake someone, not vanish.
                res = {"result": "fail", "reason": "supervisor_error", "detail": f"{type(exc).__name__}: {str(exc)[:300]}"}
            if res["result"] == "pass":
                run.event("slice_pass", slice=sid, **{k: v for k, v in res.items() if k != "result"})
                passed_at_wake += 1
                if passed_at_wake >= run.cfg["wake_after_passed"]:
                    code, reason = 0, f"passed {passed_at_wake}"
                    break
            else:
                run.event("slice_fail", slice=sid, **{k: v for k, v in res.items() if k != "result"})
                code, reason = 10, f"{sid}:{res['reason']}"
                break
    except KeyboardInterrupt:
        code, reason = 12, "supervisor stopped by a signal"
    finally:
        stop_beat.set()
    run.stage, run.slice, run.activity = "stopped", "", ""
    run.event("run_end", reason=reason, code=code)
    wake(run, reason, code=code)
    run.beat()
    return code


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def reap_orphans(run: Run) -> None:
    """A supervisor killed hard leaves its worker running on its own session and budget. Stop it before anything else."""
    ended = {e.get("name") for e in run.events() if e["event"] == "agent_end"}
    for e in run.events():
        if e["event"] == "agent_start" and e.get("name") not in ended and pid_alive(e.get("pid")):
            command = subprocess.run(["ps", "-o", "command=", "-p", str(e["pid"])], capture_output=True, text=True).stdout
            if CLAUDE in command:
                try:
                    os.killpg(e["pid"], signal.SIGKILL)
                except OSError:
                    continue
                run.event("orphan_killed", name=e.get("name"), pid=e["pid"])


def _passed_since_last_ack(run: Run, st: dict) -> int:
    ack_ts = 0
    for e in run.events():
        if e["event"] == "ack":
            ack_ts = e["ts"]
    return sum(1 for e in run.events() if e["event"] == "slice_pass" and e["ts"] > ack_ts)


def _idle_beat(run: Run, stop: threading.Event) -> None:
    while not stop.wait(15):
        run.beat()


CONTRACT_BYTES = 3072


def contract_problems(run: Run) -> list[str]:
    """What would make a queued contract fail for the architect's reason, not the worker's: the run names no lane
    gate; a contract does not parse, allows a file under a protected path (the lock wins and the worker is refused),
    is over the size rule, or has no `red_contains` naming a behaviour."""
    problems = [problem] if run.cfg["queue"] and (problem := lane_problem(run)) else []
    for sid in run.cfg["queue"]:
        try:
            c = run.contract(sid)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            problems.append(f"{sid}: contract unreadable: {exc}")
            continue
        locked = [f for f in c["files"] if is_locked(f.rstrip("/"), run.cfg["protected"])
                  or any(p.rstrip("/").startswith(f.rstrip("/") + "/") for p in run.cfg["protected"] if f.endswith("/"))]
        if locked:
            problems.append(f"{sid}: allowed files under a protected path: {', '.join(locked)}")
        if not str(c["red_contains"]).strip():
            problems.append(f"{sid}: red_contains is empty: name the behaviour the check fails on at the base")
        elif any(m in c["red_contains"] for m in acceptance_modules(c)):
            problems.append(f"{sid}: red_contains names the check's own module, which an import error also prints; name the behaviour")
        if len(c["text"].encode()) > CONTRACT_BYTES:
            problems.append(f"{sid}: contract is {len(c['text'].encode())} bytes, over {CONTRACT_BYTES}")
    return problems


MONITOR_BEAT = ".monitor.json"
MONITOR_STALE_S = 60


def monitor_problem(root: pathlib.Path) -> str:
    """Inside Herdr a run is reported only by the slice monitor: without its fresh heartbeat nobody would wake the
    architect, so the start is refused. Empty when the monitor is alive."""
    fix = "run `python3.13 devtools/slice_monitor.py up --tab` in the architect's pane"
    try:
        beat = json.loads((root / MONITOR_BEAT).read_text())
    except (OSError, ValueError):
        return f"no slice monitor watches {root}: {fix}"
    age = now() - float(beat.get("ts", 0))
    if age > MONITOR_STALE_S or not pid_alive(int(beat.get("pid") or 0)):
        return f"the slice monitor of {root} is not alive (last beat {round(age)} s ago): {fix}"
    return ""


def cmd_start(args) -> int:
    """Runs the supervisor in tmux: it outlives this shell and the architect's session, and a person can attach.
    A queued contract with a problem the architect must fix first refuses the start (nothing is launched), and so
    does a missing slice monitor inside Herdr (SLICE_NO_MONITOR=1 skips that check)."""
    run = Run(args.dir)
    problems = contract_problems(run)
    if os.environ.get("HERDR_ENV") == "1" and not os.environ.get("SLICE_NO_MONITOR"):
        problems += [p for p in (monitor_problem(run.dir.parent),) if p]
    if problems:
        print("not started:\n" + "\n".join("  " + p for p in problems), file=sys.stderr)
        return 2
    session = f"slices-{run.name}".replace(".", "-")
    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode == 0:
        hb = _read_heartbeat(run)
        if hb and pid_alive(hb.get("pid")) and now() - hb.get("ts", 0) < run.cfg["stale_after_s"]:
            print(f"already running: tmux attach -t {session}")
            return 0
        subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)
    me = shlex.quote(str(pathlib.Path(__file__).resolve()))
    py = shlex.quote(sys.executable)
    d = shlex.quote(str(run.dir))
    env = " ".join(f"{k}={shlex.quote(os.environ[k])}" for k in ("SLICE_NO_OSA", "SLICE_PATH_PREFIX", "SLICE_FAKE_SCENARIO") if k in os.environ)
    line = f"{env} exec caffeinate -i {py} {me} run {d} >> {d}/supervisor.log 2>&1"
    subprocess.run(["tmux", "new-session", "-d", "-s", session, "-n", "supervisor", "-x", "160", "-y", "40", line], check=True)
    subprocess.run(["tmux", "new-window", "-t", session, "-n", "status", f"{py} {me} status {d} --watch"], check=False)
    subprocess.run(["tmux", "select-window", "-t", f"{session}:status"], check=False)
    print(f"started: tmux attach -t {session}")
    return 0


def _read_heartbeat(run: Run) -> dict | None:
    try:
        return json.loads(run.heartbeat.read_text())
    except (OSError, ValueError):
        return None


def numbers(s: dict) -> str:
    """The row's tail for a passed slice: test lines added/deleted and the sentence-assertion change."""
    if s.get("state") != "pass" or not s.get("lines_tests") or not s.get("text_pins"):
        return ""
    (a, d), (before, after) = s["lines_tests"], s["text_pins"]
    return f"  +{a}/-{d} pins {before}->{after}"


def render_status(run: Run) -> str:
    st, hb = replay(run), _read_heartbeat(run) or {}
    age = round(now() - hb.get("ts", 0)) if hb else None
    alive = pid_alive(hb.get("pid")) if hb else False
    spent = sum(e.get("cost", 0) or 0 for e in run.events() if e["event"] == "agent_end")
    open_wake = [w for w in st["wakes"] if w["seq"] > st["acked"]]
    head = f"run {run.name} | supervisor {'alive' if alive else 'DEAD or stopped'} pid {hb.get('pid')} heartbeat {age} s | spent ${spent:.2f} of ${run.cfg['night_budget_usd']:.0f}"
    lines = [head, f"passed {len(st['pass'])} failed {len(st['fail'])} deferred {len(st['deferred'])} of {len(run.cfg['queue'])} | unacknowledged wakes {len(open_wake)}"]
    lines.append(f"{'slice':<10}{'state':<34}{'rnd':>4}{'$':>8}{'min':>7}{'peak':>9}{'lines':>7}  tests")
    for sid in run.cfg["queue"]:
        s = st["slices"].get(sid, {})
        state = s.get("state", "queued")
        if hb.get("slice") == sid and alive:
            state = hb.get("stage", state)
        lines.append(f"{sid:<10}{state[:33]:<34}{str(s.get('rounds') or ''):>4}{str(s.get('cost') or ''):>8}{str(s.get('minutes') or ''):>7}{str(s.get('peak_ctx') or ''):>9}{str(s.get('diff_lines') or ''):>7}{numbers(s)}")
    if alive and hb.get("activity"):
        lines.append(f"now: {hb.get('activity')} | idle {hb.get('idle', 0)} s | tokens {hb.get('tokens', 0)} | peak {hb.get('peak', 0)}")
    for e in run.events()[-6:]:
        lines.append(f"  {e['at'][11:19]} {e['event']} {e.get('slice') or e.get('name') or ''} {e.get('reason') or e.get('outcome') or e.get('verdict') or ''}")
    return "\n".join(lines)


def cmd_status(args) -> int:
    run = Run(args.dir)
    while True:
        text = render_status(run)
        if not args.watch:
            print(text)
            return 0
        sys.stdout.write("\033[2J\033[H" + text + "\n")
        sys.stdout.flush()
        time.sleep(5)


def cmd_wait(args) -> int:
    """Blocks until the architect has something to do. Start it with Bash run_in_background: its exit is the wake."""
    run = Run(args.dir)
    while True:
        st = replay(run)
        pending = [w for w in st["wakes"] if w["seq"] > st["acked"]]
        if pending:
            print(render_status(run))
            print(f"WAKE {pending[-1]['seq']}: {pending[-1]['reason']}")
            return 0
        hb = _read_heartbeat(run)
        if st["pid"] and not st["ended"] and (not hb or now() - hb.get("ts", 0) > run.cfg["stale_after_s"]):
            print(render_status(run))
            print("WAKE: supervisor silent")
            return 11
        time.sleep(args.poll)


def cmd_ack(args) -> int:
    run = Run(args.dir)
    st = replay(run)
    seq = len(st["wakes"])
    run.event("ack", seq=seq)
    print(f"acknowledged wake {seq}")
    return 0


def cmd_close(args) -> int:
    Run(args.dir).event("closed")
    return 0


def cmd_retry(args) -> int:
    """Architect's decision after a failure: run the slice again, usually with an edited contract."""
    Run(args.dir).event("slice_retry", slice=args.slice, why=args.why)
    return 0


def cmd_skip(args) -> int:
    """Architect's decision after a failure: the queue moves on without this slice."""
    Run(args.dir).event("deferred", slice=args.slice, why=args.why)
    return 0


def alert_once(run: Run, st: dict, key: str, text: str, every: float | None = None) -> bool:
    seen = st["alerts"].get(key)
    if seen and (every is None or now() - seen < every):
        return False
    run.event("alert", key=key, text=text)
    run.notify(text)
    return True


def watch_run(run: Run, tick_gap: float | None) -> None:
    st = replay(run)
    if st["closed"] or not st["pid"]:
        return
    if tick_gap and tick_gap > 600:
        alert_once(run, st, f"slept:{int(now() // 600)}", f"the Mac was asleep or off for {round(tick_gap / 60)} min")
    hb = _read_heartbeat(run)
    age = now() - hb.get("ts", 0) if hb else 1e9
    alive = bool(hb) and pid_alive(hb.get("pid"))
    if not st["ended"]:
        if not alive:
            started = sum(1 for e in run.events() if e["event"] == "run_start")
            if alert_once(run, st, f"dead:{started}", "supervisor died, restarting") and started <= 3:
                cmd_start(argparse.Namespace(dir=str(run.dir)))
            elif started > 3:
                alert_once(run, st, "dead:final", "supervisor keeps dying, not restarting")
        elif age > run.cfg["stale_after_s"]:
            alert_once(run, st, f"stalled:{st['pid']}", f"supervisor frozen for {round(age)} s", every=1800)
    pending = [w for w in st["wakes"] if w["seq"] > st["acked"]]
    if pending and now() - pending[-1]["ts"] > run.cfg["ack_timeout_s"]:
        seq = pending[-1]["seq"]
        if alert_once(run, st, f"silent:{seq}", f"architect silent on wake {seq}: {pending[-1]['reason']}"):
            resume_architect(run, pending[-1])
    state = "paused, waiting for the architect" if st["ended"] else "running"
    alert_once(run, st, "report", f"{state}: passed {len(st['pass'])}, failed {len(st['fail'])}, deferred {len(st['deferred'])} of {len(run.cfg['queue'])}. Next report within {round(run.cfg['report_every_s'] / 3600, 1)} h; silence beyond that means the Mac or this channel is down",
               every=run.cfg["report_every_s"])


def resume_architect(run: Run, wake_event: dict) -> None:
    """One headless attempt to continue the architect's session when its terminal is gone."""
    sid = run.cfg["architect_session"]
    if not sid:
        return
    prompt = (f"Supervisor wake {wake_event['seq']} for run {run.name}: {wake_event['reason']}. Your interactive session did not acknowledge it. "
              f"Read {run.dir}/ledger.jsonl, decide as DEVELOPMENT.md says, then run: {sys.executable} {pathlib.Path(__file__).resolve()} ack {run.dir}")
    cwd = run.cfg["architect_cwd"] or str(run.repo)
    run.logs.mkdir(exist_ok=True)
    with open(run.logs / f"architect-resume-{wake_event['seq']}.log", "ab") as log:
        proc = subprocess.Popen([CLAUDE, "-p", prompt, "--resume", sid, "--permission-mode", "auto", "--permission-prompts", "none", "--max-budget-usd", "20", "--output-format", "json"],
                                cwd=cwd, env=clean_env(), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    run.event("architect_resume", seq=wake_event["seq"], pid=proc.pid)


def cmd_watchdog(args) -> int:
    root = pathlib.Path(args.root).resolve()
    tick_file = root / ".watchdog-tick"
    previous = float(tick_file.read_text()) if tick_file.exists() else None
    tick_file.write_text(str(now()))
    gap = now() - previous if previous else None
    for path in sorted(root.glob("*/run.toml")):
        try:
            watch_run(Run(path.parent), gap)
        except Exception as exc:  # One broken run directory must not silence the others.
            notify("", path.parent, f"watchdog error: {type(exc).__name__}")
    return 0


def cmd_install_watchdog(args) -> int:
    root = pathlib.Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    plist = pathlib.Path.home() / "Library/LaunchAgents" / f"{WATCHDOG_LABEL}.plist"
    plist.write_bytes(plistlib.dumps({
        "Label": WATCHDOG_LABEL, "ProgramArguments": [sys.executable, str(pathlib.Path(__file__).resolve()), "watchdog", str(root)],
        "StartInterval": args.interval, "RunAtLoad": True, "StandardOutPath": str(root / "watchdog.log"), "StandardErrorPath": str(root / "watchdog.log"),
        "EnvironmentVariables": {"PATH": BASE_PATH}}))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{WATCHDOG_LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
    print(f"watchdog installed every {args.interval} s: {plist}")
    return 0


def cmd_uninstall_watchdog(args) -> int:
    plist = pathlib.Path.home() / "Library/LaunchAgents" / f"{WATCHDOG_LABEL}.plist"
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{WATCHDOG_LABEL}"], capture_output=True)
    plist.unlink(missing_ok=True)
    print("watchdog removed")
    return 0


def cmd_preflight(args) -> int:
    """Everything that would silently break an unattended night. Nonzero when something is wrong."""
    problems = []
    def line(ok, text):
        print(("OK   " if ok else "FAIL ") + text)
        if not ok:
            problems.append(text)
    batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout
    line("AC Power" in batt, "on AC power (lid must stay open)")
    free = shutil.disk_usage(pathlib.Path(args.dir)).free / 1e9
    line(free > 10, f"disk free {free:.0f} GB")
    for tool in ("tmux", "caffeinate", "sandbox-exec", CLAUDE):
        line(bool(shutil.which(tool, path=BASE_PATH)), f"{tool} on PATH")
    loaded = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{WATCHDOG_LABEL}"], capture_output=True).returncode == 0
    line(loaded, "watchdog loaded in launchd")
    run = Run(args.dir)
    line(bool(run.cfg["notify_cmd"]), "notification channel beyond this Mac is set (notify_cmd)")
    line(bool(run.cfg["architect_session"]), "architect session id is set for a headless resume")
    probe = subprocess.run([CLAUDE, "-p", "Reply ok", "--model", "claude-haiku-5-5", "--restricted", "--strict-mcp-config", "--tools", "", "--permission-mode", "dontAsk", "--permission-prompts", "none", "--json-schema", json.dumps(REVIEW_SCHEMA), "--output-format", "json", "--no-session-persistence"],
                           capture_output=True, text=True, env=clean_env(), stdin=subprocess.DEVNULL, cwd=run.dir, timeout=120)
    line(probe.returncode == 0 and '"is_error":false' in probe.stdout.replace(" ", ""), "claude answers with the login a worker will use")
    # A separate name: `line` appends to `problems`, so iterating over that list never ended (an unattended preflight
    # hung on the first contract problem).
    found = contract_problems(run)
    for problem in found:
        line(False, problem)
    line(not found, "contracts parse, stay within size, allow no protected file and name a red reason; the run names its lane")
    return 1 if problems else 0


def cmd_notify(args) -> int:
    run = Run(args.dir)
    run.notify(args.text)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("run", cmd_run), ("start", cmd_start), ("ack", cmd_ack), ("close", cmd_close), ("preflight", cmd_preflight)):
        p = sub.add_parser(name)
        p.add_argument("dir")
        p.set_defaults(fn=fn)
    for name, fn in (("retry", cmd_retry), ("skip", cmd_skip)):
        p = sub.add_parser(name)
        p.add_argument("dir")
        p.add_argument("slice")
        p.add_argument("why")
        p.set_defaults(fn=fn)
    p = sub.add_parser("status")
    p.add_argument("dir")
    p.add_argument("--watch", action="store_true")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("wait")
    p.add_argument("dir")
    p.add_argument("--poll", type=float, default=5)
    p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("watchdog")
    p.add_argument("root")
    p.set_defaults(fn=cmd_watchdog)
    p = sub.add_parser("install-watchdog")
    p.add_argument("root")
    p.add_argument("--interval", type=int, default=120)
    p.set_defaults(fn=cmd_install_watchdog)
    p = sub.add_parser("uninstall-watchdog")
    p.set_defaults(fn=cmd_uninstall_watchdog)
    p = sub.add_parser("notify")
    p.add_argument("dir")
    p.add_argument("text")
    p.set_defaults(fn=cmd_notify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
