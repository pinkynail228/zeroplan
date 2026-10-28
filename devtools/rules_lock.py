#!/usr/bin/env python3
"""Claude Code hook: rule files change only while the owner's unlock file exists.

PreToolUse: blocks Edit/Write on a locked path, and any tool call that names the unlock file.
PostToolUse (Bash): a locked file that now differs from HEAD is restored from HEAD.
The owner unlocks with `touch ~/.config/zplan-dev/rules-unlock` and relocks with `rm`.
Exit 2 shows stderr to the model.
"""
import json
import os
import subprocess
import sys

LOCKED = (
    "AGENTS.md",
    "devtools/zeroshot/ORCHESTRATOR.md",
    "devtools/zeroshot/preamble.md",
    "devtools/rules_lock.py",
    ".claude/settings.json",
)
UNLOCK = os.path.expanduser("~/.config/zplan-dev/rules-unlock")
HINT = f"rule files are locked; the owner unlocks with `! touch {UNLOCK}`"


def pre_verdict(event, root, unlocked):
    """Reason to block a tool call, or None."""
    data = event.get("tool_input") or {}
    if event.get("tool_name") == "Bash":
        return "the unlock file is the owner's" if "rules-unlock" in data.get("command", "") else None
    target = data.get("file_path") or data.get("notebook_path")
    if not target:
        return None
    path = os.path.realpath(os.path.join(root, os.path.expanduser(target)))
    if path == os.path.realpath(UNLOCK):
        return "the unlock file is the owner's"
    if not unlocked and any(path == os.path.realpath(os.path.join(root, rel)) for rel in LOCKED):
        return HINT
    return None


def restore_changed(root):
    """Restore locked files that differ from HEAD; return their paths."""
    diff = subprocess.run(["git", "-C", root, "diff", "--name-only", "HEAD", "--", *LOCKED],
                          capture_output=True, text=True)
    changed = [line for line in diff.stdout.splitlines() if line]
    if changed:
        subprocess.run(["git", "-C", root, "checkout", "HEAD", "--", *changed], check=True)
    return changed


def main():
    event = json.load(sys.stdin)
    root = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    unlocked = os.path.exists(UNLOCK)
    if event.get("hook_event_name") == "PostToolUse":
        changed = [] if unlocked else restore_changed(root)
        reason = f"{HINT}; restored from HEAD: {', '.join(changed)}" if changed else None
    else:
        reason = pre_verdict(event, root, unlocked)
    if reason:
        print(f"rules_lock: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
