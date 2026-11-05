#!/usr/bin/env python3
"""The test ratchet (docs/designs/2026-11-03-test-system.md section 4.1). Stdlib only.

Compares tests/test_*.py between two trees. A change may not add sentence assertions, a test named after a brief
criterion or a test module, and may not drop an assertion, unless the contract's [ratchet] table declares it, each
entry as "<id, path or fnmatch pattern>: <reason>".

    ratchet.py BASE [HEAD] [--repo DIR] [--contract FILE]      no HEAD = the working tree; exit 1 on any problem"""
from __future__ import annotations

import argparse
import ast
import collections
import fnmatch
import pathlib
import re
import subprocess
import sys
import tomllib
import warnings

SENTENCE = re.compile(r"[A-Za-zА-Яа-яЁё]{2,}[,.:;!?)»\"']? +[A-Za-zА-Яа-яЁё(«\"']{2,}")
CRITERION = re.compile(r"^test_((?:[a-z]{1,3}\d+[a-z]?\d*_)+)")
NOT_CRITERIA = {"utf8", "md5", "sha1", "sha256", "x86", "x64", "ipv4", "ipv6", "b64", "py3", "http2"}
KINDS = ("new_modules", "text_pins", "removes")


def is_test_module(path: str) -> bool:
    parts = pathlib.PurePosixPath(path).parts
    return len(parts) == 2 and parts[0] == "tests" and parts[1].startswith("test_") and parts[1].endswith(".py")


def _is_sentence(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        scope = [node.test]
    else:
        scope = node.args[:2]
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and SENTENCE.search(n.value)
               for part in scope for n in ast.walk(part))


def _assertions(func: ast.AST) -> list[tuple[str, bool]]:
    found = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            found.append((ast.unparse(node), _is_sentence(node)))
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if name.startswith("assert") or name == "fail":
                found.append((ast.unparse(node), _is_sentence(node)))
    return found


def tests_of(path: str, source: str) -> dict[str, list[tuple[str, bool]]]:
    """{test id: [(assertion text, is a sentence assertion)]}. Raises SyntaxError on a module that does not parse."""
    with warnings.catch_warnings():  # a test module's invalid escape is not the ratchet's business
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(source)
    module = pathlib.PurePosixPath(path).stem
    out = {}
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef):
            for item in cls.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test"):
                    out[f"tests.{module}.{cls.name}.{item.name}"] = _assertions(item)
    return out


def _entries(allow: dict, kind: str, problems: list[str]) -> list[str]:
    """The patterns of the entries that carry a reason; one without a reason is itself a problem."""
    patterns = []
    for entry in allow.get(kind) or []:
        pattern, _, reason = str(entry).partition(":")
        if pattern.strip() and reason.strip():
            patterns.append(pattern.strip())
        else:
            problems.append(f"[ratchet] {kind} entry {str(entry)!r} has no reason: write \"<id or pattern>: <reason>\"")
    return patterns


def _matches(name: str, patterns: list[str]) -> bool:
    return any(name == p or fnmatch.fnmatchcase(name, p) for p in patterns)


def _collect(sources: dict[str, str]) -> tuple[dict, dict]:
    tests, broken = {}, {}
    for path, source in sorted(sources.items()):
        if not is_test_module(path):
            continue
        try:
            tests.update(tests_of(path, source))
        except (SyntaxError, ValueError) as exc:
            broken[path] = exc
    return tests, broken


def compare(base: dict[str, str], head: dict[str, str], allow: dict | None = None) -> dict:
    allow = allow or {}
    problems: list[str] = []
    new_modules = _entries(allow, "new_modules", problems)
    text_pins = _entries(allow, "text_pins", problems)
    removes = _entries(allow, "removes", problems)
    new_tests = _entries(allow, "new_tests", problems)
    before, _ = _collect(base)
    after, broken = _collect(head)
    for path, exc in broken.items():
        problems.append(f"{path}: the test module does not parse: {exc}")
        before_here = {i: a for i, a in before.items() if i.startswith(f"tests.{pathlib.PurePosixPath(path).stem}.")}
        after.update(before_here)
    for path in sorted(p for p in head if is_test_module(p) and p not in base):
        if not _matches(path, new_modules):
            problems.append(f"{path}: a new test module; declare it in [ratchet] new_modules with a reason")
    sentences = lambda tests: {i: sum(1 for _, s in a if s) for i, a in tests.items()}  # noqa: E731
    was, now = sentences(before), sentences(after)
    base_count, head_count = sum(was.values()), sum(now.values())
    if head_count - base_count > len(text_pins):
        grew = sorted(i for i, n in now.items() if n > was.get(i, 0))
        problems.append(f"sentence assertions grew from {base_count} to {head_count}, {len(text_pins)} declared in text_pins; grown in: {', '.join(grew)}")
    for test_id in sorted(set(after) - set(before)):
        # A durable test is part of a change only when its brief asks for one (docs/DEVELOPMENT.md 2.6).
        if not _matches(test_id, new_tests):
            problems.append(f"{test_id}: a new test; declare it in [ratchet] new_tests with the reason the brief asks for it")
        match = CRITERION.match(test_id.rsplit(".", 1)[1])
        if match and match.group(1).split("_")[0] not in NOT_CRITERIA:
            problems.append(f"{test_id}: a new test named after a brief criterion ({match.group(1).rstrip('_')}); name it for the behaviour")
    pool = collections.Counter()
    for test_id in set(after) - set(before):
        pool.update(text for text, _ in after[test_id])
    for test_id in sorted(before):
        if _matches(test_id, removes):
            continue
        if test_id in after:
            if len(after[test_id]) < len(before[test_id]):
                problems.append(f"{test_id}: {len(before[test_id])} assertions became {len(after[test_id])}; declare it in [ratchet] removes with a reason")
            continue
        lost = []
        for text, _ in before[test_id]:
            if pool[text] > 0:
                pool[text] -= 1
            else:
                lost.append(text)
        if lost:
            problems.append(f"{test_id}: deleted, and {len(lost)} of its assertions are in no new test (e.g. {lost[0][:80]}); declare it in [ratchet] removes with a reason")
    return {"problems": problems, "text_pins": (base_count, head_count)}


def sources_at(repo, rev: str) -> dict[str, str]:
    """The test modules of a revision. Raises CalledProcessError for a revision that does not exist."""
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, errors="replace", check=True).stdout  # noqa: E731
    names = [n for n in run("ls-tree", "-r", "--name-only", rev, "--", "tests/").splitlines() if is_test_module(n)]
    return {n: run("show", f"{rev}:{n}") for n in names}


def sources_staged(repo) -> dict[str, str]:
    """The test modules of the index: what a commit being made will contain."""
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, errors="replace", check=True).stdout  # noqa: E731
    return {n: run("show", f":{n}") for n in run("ls-files", "--", "tests/").splitlines() if is_test_module(n)}


TRAILERS = {"Ratchet-new-test": "new_tests", "Ratchet-new-module": "new_modules", "Ratchet-text-pin": "text_pins",
            "Ratchet-remove": "removes"}


def hook(message_file: str, repo=".") -> int:
    """The commit-msg hook (devtools/hooks/commit-msg): the ratchet on a direct commit, the index against HEAD. Its
    exceptions are trailers of the message, so they stay in the history: `Ratchet-new-test: <id>: <reason>` (also
    -new-module, -text-pin, -remove). The slice runner checks its own commits against their contracts and commits
    with --no-verify."""
    if subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repo, capture_output=True).returncode:
        return 0
    allow: dict = {}
    for line in pathlib.Path(message_file).read_text(errors="replace").splitlines():
        key, _, value = line.partition(":")
        if key.strip() in TRAILERS and value.strip():
            allow.setdefault(TRAILERS[key.strip()], []).append(value.strip())
    result = compare(sources_at(repo, "HEAD"), sources_staged(repo), allow)
    for problem in result["problems"]:
        print("ratchet: " + problem, file=sys.stderr)
    if result["problems"]:
        print("ratchet: the commit is refused; declare each exception as a trailer, e.g. "
              "'Ratchet-new-test: tests.test_x.T.test_y: <why the change needs it>'", file=sys.stderr)
    return 1 if result["problems"] else 0


def sources_in(root) -> dict[str, str]:
    root = pathlib.Path(root)
    return {f"tests/{p.name}": p.read_text(errors="replace") for p in sorted((root / "tests").glob("test_*.py")) if p.is_file()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check that a change does not grow test pins or drop assertions.")
    ap.add_argument("base", nargs="?")
    ap.add_argument("--hook", metavar="MESSAGE_FILE", help="run as the commit-msg hook (devtools/hooks/commit-msg)")
    ap.add_argument("head", nargs="?", help="a revision; default the working tree")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--contract", help="a slice contract whose [ratchet] table declares exceptions")
    args = ap.parse_args(argv)
    if args.hook:
        return hook(args.hook, args.repo)
    if not args.base:
        ap.error("base is required")
    allow = tomllib.loads(pathlib.Path(args.contract).read_text()).get("ratchet", {}) if args.contract else {}
    base = sources_at(args.repo, args.base)
    head = sources_at(args.repo, args.head) if args.head else sources_in(args.repo)
    result = compare(base, head, allow)
    for problem in result["problems"]:
        print(problem)
    print("sentence assertions: %d -> %d" % result["text_pins"])
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
