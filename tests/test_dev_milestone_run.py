"""D1: dev runs through zplan's milestone graph (devtools/zeroshot/milestone_run.py, run.sh with ZS_GRAPH=zplan).

Deterministic: scratch repository, fake `zeroshot` and `claude` on PATH, isolated agent homes; no engine, no network.
Interpretations: a task file without `Why:` takes its title as the why (the brief needs one); the steward role takes
the runtime's `code` node; `--no-environment` is not passed (the template run did not pass it); the shared
preamble.md joins the brief's `reuse` so every agent still sees the run rules; `.zplan/` joins the repository's
exclude file because the dev repository does not ignore it and the delivery runs `git add --all`; the pinned
engine is not on the test path, so `{"valid":true}` itself is checked by hand on the Linux host, here the fake engine
records the argv run.sh gives it."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "devtools" / "zeroshot"))

import milestone_run  # noqa: E402
from terminal_planner import milestone  # noqa: E402
from terminal_planner.authority import canonical, decode  # noqa: E402

TASK = """D1x — a small change (RELEASE plan step 1)
and its second title line.

Why: one reason.

Reuse: `helper()` of tools.py.

Write-set: tools/a.py (new), tools/b.py,
tests/test_a.py (new, tests only where they pin names, labels).

Acceptance criteria:
- C1 First. Example: input one -> output
  one.
- C2 Second. Example: input two -> output two.

Non-goals (reviewers must not require): the UI; the store.

Conflict rule: if a file is missing, answer `conflict:`.

Risk: medium (dev tooling). DoD: `python3.13 devtools/fasttest.py
tests.test_a` exit 0; quote the `fasttest:` lines.
"""
GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="zs-dv-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.task = self.dir / "task.md"
        self.task.write_text(TASK)

    def documents(self, *extra, task=None):
        return subprocess.run([sys.executable, str(REPO / "devtools/zeroshot/milestone_run.py"), "documents",
                               str(task or self.task), str(self.dir / "docs"), "--runtime",
                               str(REPO / "devtools/zeroshot/runtime.json"), *extra], capture_output=True, text=True)


class MilestoneRunTests(Scratch):
    def test_c1_task_file_becomes_a_one_task_proposal(self):
        """C1: the documents are `build_documents` of the parsed brief; roles and harness come from runtime.json."""
        result = self.documents()
        self.assertEqual(result.returncode, 0, result.stderr)
        docs = {key: decode((self.dir / "docs" / (key + ".json")).read_text()) for key in ("graph", "runtime", "input", "baseline")}
        milestone.validate_baseline(docs["baseline"])
        (task,) = docs["baseline"]["tasks"]
        brief = task["brief"]
        self.assertEqual(task["title"], "D1x — a small change (RELEASE plan step 1)")
        self.assertEqual([c["id"] for c in brief["criteria"]], ["C1", "C2"])
        self.assertEqual(brief["criteria"][0]["example"], "input one -> output one.")
        self.assertEqual(brief["write_set"], ["tools/a.py", "tools/b.py", "tests/test_a.py"])
        self.assertEqual(brief["non_goals"], ["the UI", "the store"])
        self.assertEqual((brief["risk"], brief["why"]), ("medium", "one reason."))
        self.assertEqual(brief["dod"], "`python3.13 devtools/fasttest.py tests.test_a` exit 0; quote the `fasttest:` lines.")
        self.assertIn("Conflict rule: if a file is missing", brief["goal"])
        self.assertEqual(docs["input"]["baseline"], canonical(docs["baseline"]))
        self.assertIn("preflight", json.dumps(docs["graph"]))
        nodes = docs["runtime"]["nodes"]
        self.assertEqual((docs["runtime"]["harness"], nodes["worker"]["model"], nodes["preflight"]["model"], nodes["select"]["model"]),
                         ("claude", "claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5"))

    def test_c2_a_missing_field_is_named_and_nothing_is_written(self):
        """C2: a file without `Write-set:` (and without `Risk:`) exits 2 naming both; a DeepSeek-style node is refused."""
        self.task.write_text(TASK.replace("Write-set:", "Files:").split("Risk:")[0])
        result = self.documents()
        self.assertEqual(result.returncode, 2)
        self.assertIn("write-set", result.stderr)
        self.assertIn("risk", result.stderr)
        self.assertFalse((self.dir / "docs").exists())
        runtime = self.dir / "runtime.json"
        runtime.write_text(json.dumps({"nodes": {n: {"kind": "agent", "model": "m", "effort": "high", "lane": {}} for n in ("worker", "acceptance", "code")}}))
        self.task.write_text(TASK)
        result = subprocess.run([sys.executable, str(REPO / "devtools/zeroshot/milestone_run.py"), "documents", str(self.task),
                                 str(self.dir / "docs"), "--runtime", str(runtime)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("lane", result.stderr)
        self.assertFalse((self.dir / "docs").exists())

    def test_c1_write_set_ends_at_its_sentence_and_paragraph(self):
        """Regression: `Not ...` exclusions and a following paragraph are not write-set files; prose in the list is refused."""
        self.task.write_text(TASK.replace("(new, tests only where they pin names, labels).",
                                          "(new).\nNot tools/c.py, tools/d.py (lane X owns them).\n\nAPI: `f() -> int`, sorted; more."))
        result = self.documents()
        self.assertEqual(result.returncode, 0, result.stderr)
        brief = decode((self.dir / "docs" / "baseline.json").read_text())["tasks"][0]["brief"]
        self.assertEqual(brief["write_set"], ["tools/a.py", "tools/b.py", "tests/test_a.py"])
        self.assertIn("API: `f() -> int`, sorted; more.", brief["goal"])  # the paragraph reaches the worker
        self.task.write_text(TASK.replace("tests/test_a.py (new, tests only where they pin names, labels).", "tests/test_a.py and more"))
        shutil.rmtree(self.dir / "docs")
        result = self.documents()
        self.assertEqual(result.returncode, 2)
        self.assertIn("write-set", result.stderr)
        self.assertFalse((self.dir / "docs").exists())


class RunShTests(Scratch):
    def setUp(self):
        super().setUp()
        self.name = "dvt-" + self.dir.name[-8:]
        self.work = Path("/tmp/zs-zplan") / self.name
        for path in (self.work, Path(str(self.work) + ".docs"), Path(str(self.work) + ".tmp"),
                     Path(str(self.work) + ".input.json")):
            self.addCleanup(lambda p=path: shutil.rmtree(p, True) if p.is_dir() else p.unlink(missing_ok=True))
        self.repo = self.dir / "repo"
        for relative in ("run.sh", "milestone_run.py", "agent-settings.json", "runtime.json", "preamble.md"):
            (self.repo / "devtools/zeroshot").mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / "devtools/zeroshot" / relative, self.repo / "devtools/zeroshot" / relative)
        (self.repo / "terminal_planner").symlink_to(REPO / "terminal_planner")
        env = dict(os.environ, **GIT)
        for command in (["init", "-q", "-b", "main"], ["add", "devtools"], ["commit", "-q", "-m", "x"],
                        ["remote", "add", "origin", "https://example.invalid/r.git"]):
            subprocess.run(["git", *command], cwd=self.repo, env=env, check=True, capture_output=True)
        self.addCleanup(subprocess.run, ["git", "worktree", "prune"], cwd=self.repo, capture_output=True)
        bin_dir, self.log = self.dir / "bin", self.dir / "zeroshot.argv"
        bin_dir.mkdir()
        (bin_dir / "zeroshot").write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGV_LOG"\necho \'{"valid":true}\'\n')
        (bin_dir / "claude").write_text("#!/bin/sh\n[ \"$1\" = auth ] && echo '\"loggedIn\": true' || echo '[]'\n")
        for fake in bin_dir.iterdir():
            fake.chmod(0o755)
        codex = self.dir / "codex"
        codex.mkdir()
        (codex / "config.toml").write_text("plugins = false\nmulti_agent = false\ninclude_instructions = false\n")
        (codex / "auth.json").write_text("{}")
        (self.dir / "claude-home").mkdir()
        (self.dir / "claude-home/settings.json").write_text(json.dumps({"permissions": {"defaultMode": "auto"}}))  # run.sh refuses a home without auto mode
        self.env = dict(os.environ, **GIT, PATH="%s:%s" % (bin_dir, os.environ["PATH"]), ARGV_LOG=str(self.log),
                        ZS_MIN_FREE_GB="0", ZS_CODEX_HOME=str(codex), ZS_CLAUDE_HOME=str(self.dir / "claude-home"))
        self.env.pop("ZS_GRAPH", None)

    def run_sh(self, **env):
        return subprocess.run(["sh", str(self.repo / "devtools/zeroshot/run.sh"), self.name, str(self.task), "--validate-only"],
                              cwd=self.repo, env=dict(self.env, **env), capture_output=True, text=True)

    def argv(self):
        return self.log.read_text().splitlines()

    def test_c3_c4_graph_run_and_the_default_run(self):
        """C3/C4: the default run (ZS_GRAPH unset) starts `--graph/--input/--runtime-config` from `$work.docs/` with the
        same title, key and --validate-only, and leaves the lock released; ZS_GRAPH=template keeps the template run
        unchanged. The worktree
        holds `.zplan/baseline.json` and `milestone.json` that the frozen checker accepts, and stays clean."""
        result = self.run_sh()  # the default since 2026-10-25
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '{"valid":true}')
        docs = str(self.work) + ".docs"
        argv = self.argv()
        self.assertEqual(argv[:2], ["run", "--title"])
        self.assertEqual(argv[2], "zplan " + self.name)
        self.assertEqual(argv[3:9], ["--graph", docs + "/graph.json", "--input", docs + "/input.json",
                                     "--runtime-config", docs + "/runtime.json"])
        self.assertRegex(argv[10], r"^zplan-%s-[0-9a-f]+$" % self.name)
        self.assertEqual(argv[11:], ["--validate-only"])
        self.assertNotIn("--template", argv)
        self.assertFalse(Path(str(self.work) + ".lock").exists())
        baseline = decode((self.work / ".zplan/baseline.json").read_text())
        self.assertEqual(canonical(baseline), canonical(decode((Path(docs) / "baseline.json").read_text())))
        # The graph's checker is the file form a Claude agent may run (`Bash(python3.13:*)`), not a `-c` one-liner.
        frozen = "python3.13 -I %s/.zplan/check.py" % self.work.resolve()
        self.assertIn(frozen, (Path(docs) / "graph.json").read_text())
        self.assertNotIn(" -c ", (Path(docs) / "graph.json").read_text())
        # Every command a graph node must run exactly is admitted by the agents' allowlist: a refused one fails the
        # node outright (2026-10-25: select_init_invalid), unlike a worker's own command, which it can rephrase.
        allow = json.loads((REPO / "devtools/zeroshot/agent-settings.json").read_text())["permissions"]["allow"]
        prefixes = [rule[5:-3] for rule in allow if rule.startswith("Bash(") and rule.endswith(":*)")]
        graph = json.dumps(json.loads((Path(docs) / "graph.json").read_text()), ensure_ascii=False)
        prescribed = re.findall(r"Run exactly: (.*?)\\n", graph)  # prompts are JSON strings: a newline is `\\n`
        self.assertTrue(prescribed)
        for command in prescribed:
            self.assertTrue(any(command.startswith(p + " ") for p in prefixes), command)
        checker = subprocess.run(frozen + " check .zplan/milestone.json --baseline .zplan/baseline.json",
                                 shell=True, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(checker.returncode, 0, checker.stderr)
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.work, capture_output=True, text=True)
        self.assertEqual(status.stdout, "")
        self.run_sh(ZS_ATTEMPT="2", ZS_GRAPH="template")
        argv = self.argv()
        self.assertEqual(argv[3:5], ["--template", "software-change"])
        self.assertEqual(json.loads(Path(str(self.work) + ".input.json").read_text())["task"].startswith("D1x"), True)

    def test_a_worktree_at_an_older_head_is_reused_only_by_a_rerun(self):
        """A --validate-only leaves the worktree; after a new commit on main a plain launch refuses it (2026-10-25: a
        run started without the brief's committed resource), a rerun (ZS_ATTEMPT) keeps using it."""
        self.assertEqual(self.run_sh().returncode, 0)
        env = dict(os.environ, **GIT)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "y"], cwd=self.repo, env=env, check=True)
        self.log.unlink()
        result = self.run_sh()
        self.assertEqual(result.returncode, 2)
        self.assertIn("older HEAD", result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse(Path(str(self.work) + ".lock").exists())
        self.assertEqual(self.run_sh(ZS_ATTEMPT="2").returncode, 0)

    def test_c3_a_bad_task_file_stops_before_any_engine_call(self):
        """C2 through run.sh: the exit is 2, the engine is not called and the lock is released."""
        self.task.write_text(TASK.replace("Write-set:", "Files:"))
        result = self.run_sh(ZS_GRAPH="zplan")
        self.assertEqual(result.returncode, 2)
        self.assertIn("write-set", result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse(Path(str(self.work) + ".lock").exists())


if __name__ == "__main__":
    unittest.main()
