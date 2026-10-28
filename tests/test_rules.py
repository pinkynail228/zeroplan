"""Rule files stay compact, undated and locked (devtools/zeroshot/ORCHESTRATOR.md, AGENTS.md)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "devtools"))
import rules_lock  # noqa: E402

BUDGETS = {
    "AGENTS.md": 1536,
    "devtools/zeroshot/ORCHESTRATOR.md": 10752,
    "devtools/zeroshot/preamble.md": 5120,
}
STATE_SECTIONS = ["## Production", "## Direction", "## Now", "## Next", "## Open"]
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


class RuleFiles(unittest.TestCase):
    def test_budgets(self):
        for rel, cap in BUDGETS.items():
            self.assertLessEqual(len((ROOT / rel).read_bytes()), cap, rel)
        self.assertLessEqual(len((ROOT / "STATE.md").read_bytes()), 6144, "STATE.md")

    def test_no_dates_or_history(self):
        for rel in BUDGETS:
            text = (ROOT / rel).read_text()
            self.assertIsNone(DATE.search(text), f"{rel}: dates belong in git, not in rules")
            self.assertNotRegex(text, r"(?i)owner \d", rel)

    def test_state_sections(self):
        headings = [line for line in (ROOT / "STATE.md").read_text().splitlines() if line.startswith("## ")]
        self.assertEqual(headings, STATE_SECTIONS)


class RulesLock(unittest.TestCase):
    def check(self, tool, unlocked=False, **data):
        return rules_lock.pre_verdict({"tool_name": tool, "tool_input": data}, str(ROOT), unlocked)

    def test_edits_blocked_until_unlock(self):
        for rel in rules_lock.LOCKED:
            self.assertIsNotNone(self.check("Edit", file_path=str(ROOT / rel)), rel)
            self.assertIsNotNone(self.check("Write", file_path=rel), rel)
            self.assertIsNone(self.check("Edit", unlocked=True, file_path=str(ROOT / rel)), rel)
        self.assertIsNone(self.check("Write", file_path=str(ROOT / "STATE.md")))
        self.assertIsNone(self.check("Bash", command="cp devtools/zeroshot/preamble.md /tmp/x"))

    def test_bash_change_restored_from_head(self):
        with tempfile.TemporaryDirectory() as repo:
            git = lambda *args: subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)
            git("init", "-q")
            (Path(repo) / "AGENTS.md").write_text("rules\n")
            (Path(repo) / "STATE.md").write_text("state\n")
            git("add", ".")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
            (Path(repo) / "AGENTS.md").write_text("edited by sed\n")
            (Path(repo) / "STATE.md").write_text("edited\n")
            self.assertEqual(rules_lock.restore_changed(repo), ["AGENTS.md"])
            self.assertEqual((Path(repo) / "AGENTS.md").read_text(), "rules\n")
            self.assertEqual((Path(repo) / "STATE.md").read_text(), "edited\n")

    def test_unlock_file_is_owners(self):
        self.assertIsNotNone(self.check("Bash", unlocked=True, command="touch ~/.config/zplan-dev/rules-unlock"))
        self.assertIsNotNone(self.check("Write", unlocked=True, file_path=rules_lock.UNLOCK))

    def test_hook_exit_code(self):
        event = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                 "tool_input": {"file_path": str(ROOT / "AGENTS.md")}, "cwd": str(ROOT)}
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, CLAUDE_PROJECT_DIR=str(ROOT))
            proc = subprocess.run([sys.executable, str(ROOT / "devtools/rules_lock.py")], input=json.dumps(event),
                                  capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("locked", proc.stderr)

    def test_hook_registered(self):
        settings = json.loads((ROOT / ".claude/settings.json").read_text())
        for event in ("PreToolUse", "PostToolUse"):
            commands = [h["command"] for group in settings["hooks"][event] for h in group["hooks"]]
            self.assertTrue(any("rules_lock.py" in c for c in commands), event)
        deny = json.loads((ROOT / "devtools/zeroshot/agent-settings.json").read_text())["permissions"]["deny"]
        for rel in BUDGETS:
            self.assertIn(f"Edit({rel})", deny)


if __name__ == "__main__":
    unittest.main()
