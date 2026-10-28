#!/usr/bin/env python3
"""Qualify a candidate Zeroshot/Codex toolchain in a scratch root; the default toolchain is never changed.

    python3 devtools/toolchain-candidate.py --zeroshot 10.13.0 --sha256 <archive sha256 of this platform> \\
        --upstream ~/src/zeroshot [--codex 0.161.0 --codex-package DIR] [--archive FILE] [--keep-old-app]

Steps (each prints PASS/FAIL/WARN, the result line is PASS only when none failed):
  quiescence  the production store is read (read-only): unknown/active intents, recoverable failures, unexported
              results and unfinished approved plans block unless --keep-old-app (older app and tools stay in use).
  install     the candidate bundle into its own tool dir under a scratch data root (checksum + npm ci as setup does).
  contracts   static diff against the installed default: CLI help of the commands zplan calls, the graph identifiers
              (profile, policy, worker templates) zplan sends, and the upstream checkout's tag.
  installed   tests/test_install.py and the native admission tests against the candidate binary.
  driver      devtools/driver_qual.py scenarios against the candidate.

Every step runs with HOME, XDG_*, TMPDIR and the native state root inside one short scratch directory under /tmp;
nothing is written under ~/.local/share/planning-kit, the production state directories or the native state root of
the owner. Activation is a separate, manual change of terminal_planner/toolchain.py (docs/UPGRADE.md).
"""

import argparse
from contextlib import contextmanager
import dataclasses
import difflib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terminal_planner import setup, toolchain  # noqa: E402
from terminal_planner.authority import production_root  # noqa: E402

HERE = Path(__file__).resolve().parent
# Zeroshot commands zplan calls and the flags it passes (engine.py, runs.py NativeDriver.arguments).
COMMANDS = {"": [], "run": ["--title", "--graph", "--runtime-config", "--input", "--no-environment",
                            "--submission-key", "--detach", "--validate-only"],
            "watch": ["--after"], "status": [], "resume": [], "force-stop": [], "logs": [], "list": []}
ACTIVE_PLAN = frozenset({"submission_unknown", "observing", "observation_blocked", "detached"})
ACTIVE_RUN = frozenset({"preparing", "submission_unknown", "submitted", "running", "stopping", "resume_pending"})
INSTALLED_TESTS = ("tests.test_install", "tests.test_milestone")
SKIP_DIRS = {".git", "node_modules", "target", "dist", "__pycache__"}


class Report:
    def __init__(self):
        self.lines, self.failed = [], False

    def add(self, level, step, detail=""):
        line = "%s %s%s" % (level, step, (": " + detail) if detail else "")
        self.lines.append(line)
        self.failed = self.failed or level == "FAIL"
        print(line, flush=True)


# Quiescence (read-only) ---------------------------------------------------------------------------------------

def quiescence(root):
    """Reasons the older app must stay in use; reads each project's planning.json, creates and locks nothing."""
    blockers = []
    for path in sorted(Path(root).glob("*/planning.json")):
        name = path.parent.name[:12]
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            revisions, runs = state["revisions"], state.get("runs", [])
            assert isinstance(revisions, list) and isinstance(runs, list)
        except (OSError, ValueError, KeyError, AssertionError):
            blockers.append("%s: planning.json не читается — состояние неизвестно" % name)
            continue
        for r in revisions:
            if r.get("status") in ACTIVE_PLAN:
                blockers.append("%s: план r%s в статусе %s (unknown/active intent)" % (name, r.get("version"), r.get("status")))
        resumed = {r.get("predecessor") for r in runs}
        for r in runs:
            label = "%s: %s attempt %s" % (name, r.get("milestone"), r.get("attempt"))
            if r.get("status") in ACTIVE_RUN:
                blockers.append("%s в статусе %s (unknown/active intent)" % (label, r.get("status")))
            elif r.get("status") == "failed" and r.get("recoverable") and r.get("run_id") not in resumed:
                blockers.append("%s: recoverable failure ещё не resumed" % label)
            elif r.get("outcome") == "done" and r.get("delivery", "none") != "integrated":
                blockers.append("%s: результат не влит (delivery %s)" % (label, r.get("delivery", "none")))
        current = revisions[-1] if revisions else None
        if current and current.get("status") == "approved":
            done = {r.get("milestone") for r in runs if r.get("plan_revision") == current.get("version")
                    and r.get("outcome") == "done" and r.get("delivery") == "integrated"}
            open_ids = [m["id"] for m in (current.get("proposal") or {}).get("milestones", []) if m["id"] not in done]
            if open_ids:
                blockers.append("%s: утверждённый план r%s не завершён (%s)" % (name, current.get("version"), ", ".join(open_ids)))
    return blockers


# Scratch environment ------------------------------------------------------------------------------------------

def scratch_env(scratch):
    home = scratch / "home"
    values = {"HOME": str(home), "XDG_DATA_HOME": str(scratch / "data"), "XDG_CONFIG_HOME": str(scratch / "config"),
              "XDG_STATE_HOME": str(scratch / "state"), "TMPDIR": str(scratch / "tmp"), "CODEX_HOME": str(home / ".codex"),
              "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
              "ZEROSHOT_STATE_DIR": str(scratch / "zp/runs"), "ZEROSHOT_CONFIG_DIR": str(scratch / "zp/config")}
    for path in (home, scratch / "data", scratch / "config", scratch / "state", scratch / "tmp", scratch / "zp"):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    (home / ".gitconfig").write_text("[user]\n\tname = zplan qual\n\temail = zplan-qual@localhost\n")
    return values


@contextmanager
def isolated(values):
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def candidate_chain(args):
    default = toolchain.current()
    key = (platform.system(), platform.machine())
    if key not in default.releases:
        raise SystemExit("платформа %s/%s не поддерживается" % key)
    target = args.target or default.releases[key][0]
    chain = dataclasses.replace(
        default, zeroshot=args.zeroshot or default.zeroshot, codex=args.codex or default.codex,
        restic=args.restic or default.restic, runtime=args.runtime or default.runtime,
        url_template=args.url_template or default.url_template, releases={key: (target, args.sha256)},
        package_dir=str(Path(args.codex_package).expanduser().resolve()) if args.codex_package else None)
    if chain.tool_dir_name == default.tool_dir_name:
        raise SystemExit("кандидат совпадает с default toolchain (%s); укажите другие версии" % default.tool_dir_name)
    if chain.codex != default.codex and not chain.package_dir:
        raise SystemExit("Codex %s требует --codex-package DIR с package.json и package-lock.json" % chain.codex)
    return chain


# Static contract diff -----------------------------------------------------------------------------------------

def help_of(executable, argv, env):
    result = subprocess.run([str(executable), *argv, "--help"], capture_output=True, text=True, timeout=60, env=env,
                            stdin=subprocess.DEVNULL, cwd=env["TMPDIR"])
    return (result.stdout + result.stderr).strip()


def identifiers():
    """Upstream contract identifiers zplan's graphs and runtime send: graph profile, policy, built-in worker refs."""
    from terminal_planner import engine, milestone
    found = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("profile", "policy", "worker") and isinstance(item, str):
                    found.add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(engine.planner_graph())
    walk(milestone.milestone_graph(1))
    # zplan.* worker refs are zplan's own; bare node names are not identifiers.
    return sorted(i for i in found if "." in i and not i.startswith("zplan."))


def upstream_hits(path, wanted):
    """The subset of identifiers that occurs literally in the upstream checkout (text files, no vendored trees)."""
    hits = set()
    for directory, names, files in os.walk(path):
        names[:] = [n for n in names if n not in SKIP_DIRS]
        for name in files:
            full = Path(directory) / name
            try:
                if full.stat().st_size > 2 * 1024 * 1024:
                    continue
                text = full.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            hits.update(item for item in wanted if item in text)
        if hits == set(wanted):
            break
    return hits


def contracts(report, candidate_exe, default_exe, upstream, version, env):
    if not Path(default_exe).is_file():
        report.add("FAIL", "contracts", "текущий default не установлен (%s): сравнивать не с чем" % default_exe)
        return
    problems = False
    for command, flags in COMMANDS.items():
        argv = [command] if command else []
        label = "contracts help " + (command or "zeroshot")
        old, new = help_of(default_exe, argv, env), help_of(candidate_exe, argv, env)
        missing = [flag for flag in flags if flag not in new]
        if missing:
            problems = True
            report.add("FAIL", label, "у кандидата нет флагов: " + ", ".join(missing))
        elif old != new:
            diff = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), "default", "candidate", lineterm="", n=0)
                    if l[:1] in "+-" and not l.startswith(("+++", "---"))]
            report.add("WARN", label, "текст изменился (%s строк): %s" % (len(diff), " | ".join(d[:100] for d in diff[:6])))
    if upstream is None:
        report.add("FAIL", "contracts upstream", "нужен --upstream: checkout кандидата для schema/template contracts")
        return
    upstream = Path(upstream).expanduser()
    if not upstream.is_dir():
        report.add("FAIL", "contracts upstream", "нет каталога " + str(upstream))
        return
    tag = subprocess.run(["git", "-C", str(upstream), "describe", "--tags", "--exact-match"], capture_output=True, text=True)
    if tag.returncode == 0 and tag.stdout.strip() not in ("v" + version, version):
        problems = True
        report.add("FAIL", "contracts upstream tag", "checkout на %s, кандидат v%s" % (tag.stdout.strip(), version))
    elif tag.returncode:
        report.add("WARN", "contracts upstream tag", "checkout не на tag: убедитесь, что это v" + version)
    wanted = identifiers()
    for item in sorted(set(wanted) - upstream_hits(upstream, wanted)):
        problems = True
        report.add("FAIL", "contracts identifier", "%s не найден в upstream" % item)
    if not problems:
        report.add("PASS", "contracts", "%s identifiers, %s commands" % (len(wanted), len(COMMANDS)))


# Steps --------------------------------------------------------------------------------------------------------

def child_env(values, binary):
    env = dict(os.environ, **values)
    env.update(PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "tests")]), ZEROSHOT_TEST_BINARY=str(binary))
    env.pop("ZEROSHOT_V010_SOURCE", None)
    return env


def run_child(argv, env, timeout):
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    return result.returncode, (result.stdout + result.stderr)


def tail(text, count=12):
    return " | ".join(line.strip() for line in text.strip().splitlines()[-count:])[:1200]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zeroshot", required=True, help="candidate Zeroshot version, e.g. 10.13.0")
    parser.add_argument("--sha256", required=True, help="SHA256 of the candidate release archive for this platform")
    parser.add_argument("--codex", help="candidate Codex version (default: the default toolchain's)")
    parser.add_argument("--codex-package", help="directory with the candidate package.json and package-lock.json")
    parser.add_argument("--restic", help="candidate restic version (default: the default toolchain's)")
    parser.add_argument("--runtime", help="bundle layout tag (default: the default toolchain's)")
    parser.add_argument("--target", help="release target name of this platform (default: the default toolchain's)")
    parser.add_argument("--url-template", help="release URL with {version} and {target}")
    parser.add_argument("--archive", help="local release archive instead of the download (checksum still verified)")
    parser.add_argument("--upstream", help="checkout of the candidate's Zeroshot tag (contract diff)")
    parser.add_argument("--default-tools", help="installed default tool dir (default: this install's)")
    parser.add_argument("--keep-old-app", action="store_true", help="qualify although work is unfinished: the older app stays in use")
    parser.add_argument("--driver-scenario", action="append", default=[], help="driver_qual scenario (default: all)")
    parser.add_argument("--tests", nargs="*", default=list(INSTALLED_TESTS), help="installed test modules")
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    args = parser.parse_args(argv)
    report = Report()
    default = toolchain.current()
    chain = candidate_chain(args)
    production = [setup.data_root(), setup.config_root(), production_root(), setup.native_state_root()]
    default_exe = Path(args.default_tools).expanduser() / "zeroshot" if args.default_tools else setup.tool_paths(chain=default)[0]
    print("default toolchain: %s (%s)" % (default.tool_dir_name, "не меняется"))
    print("candidate: %s" % chain.tool_dir_name)

    blockers = quiescence(production_root())
    for line in blockers:
        report.add("WARN" if args.keep_old_app else "FAIL", "quiescence", line)
    if blockers and not args.keep_old_app:
        print("RESULT: BLOCKED — незавершённая работа; завершите её или передайте --keep-old-app (старый app остаётся)")
        return 1
    report.add("PASS", "quiescence", "старый app остаётся (--keep-old-app)" if blockers else "активной работы нет")

    scratch = Path(tempfile.mkdtemp(prefix="zt-", dir="/tmp")).resolve()
    try:
        if any(scratch == p or p in scratch.parents for p in production):
            raise SystemExit("scratch внутри production root: " + str(scratch))
        values = scratch_env(scratch)
        binary = None
        try:
            with isolated(values):
                setup.install_tools(lambda text: None, chain=chain, archive=args.archive)
                root = setup.tools_root(chain)
                setup.check_installation(chain)
            binary = root / "zeroshot"
            report.add("PASS", "install", str(root))
        except (Exception, SystemExit) as error:
            report.add("FAIL", "install", "%s: %s" % (type(error).__name__, str(error)[:400]))
        if binary is not None:
            try:
                contracts(report, binary, default_exe, args.upstream, chain.zeroshot, child_env(values, binary))
            except Exception as error:  # every failure is a step result, never a crash
                report.add("FAIL", "contracts", "%s: %s" % (type(error).__name__, str(error)[:300]))
            env = child_env(values, binary)
            for name, argv_ in (
                    ("installed", [sys.executable, "-m", "unittest", *args.tests]),
                    ("driver", [sys.executable, str(HERE / "driver_qual.py"), "--binary", str(binary),
                                "--zeroshot-version", chain.zeroshot, *args.driver_scenario])):
                try:
                    code, output = run_child(argv_, env, 3 * 3600)
                except (OSError, subprocess.TimeoutExpired) as error:
                    report.add("FAIL", name, type(error).__name__)
                    continue
                report.add("PASS" if code == 0 else "FAIL", name, "" if code == 0 else "exit %s: %s" % (code, tail(output)))
    finally:
        if args.keep:
            print("scratch kept: " + str(scratch))
        else:
            shutil.rmtree(scratch, ignore_errors=True)
    print("default toolchain unchanged: " + default.tool_dir_name)
    if report.failed:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS — кандидат %s прошёл квалификацию; активация: docs/UPGRADE.md" % chain.tool_dir_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
