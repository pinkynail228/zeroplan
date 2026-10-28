#!/usr/bin/env python3
"""Permission refusals of Claude-lane run agents: `python3 devtools/zeroshot/denials.py SINCE_UTC_ISO`.
Reads the dev agent home transcripts (~/.local/share/zplan-dev/claude-home/projects) and prints the sessions, tool
calls and refused commands since SINCE, by first word: widen agent-settings.json from it (2026-10-25)."""
import json, glob, os, collections, re, sys
H = os.path.expanduser("~/.local/share/zplan-dev/claude-home/projects")
since = sys.argv[1]  # ISO, UTC
parts = collections.Counter(); calls = den = sess = hit = 0
for f in glob.glob(H + "/**/*.jsonl", recursive=True):
    ts = None; uses = {}; d0 = den
    for line in open(f, errors="replace"):
        try: r = json.loads(line)
        except Exception: continue
        ts = ts or r.get("timestamp")
        c_ = (r.get("message") or {}).get("content")
        if not isinstance(c_, list): continue
        for c in c_:
            if c.get("type") == "tool_use": uses[c["id"]] = c.get("input") or {}; calls += ts >= since if ts else 0
            elif c.get("type") == "tool_result" and c.get("is_error") and ts and ts >= since:
                t = c.get("content"); t = t if isinstance(t, str) else json.dumps(t)
                m = re.search(r"requires approval: (.*)", t) or (re.search(r"requires approval", t) and re.match(r"(.*)", uses.get(c.get("tool_use_id"), {}).get("command", "")))
                if m:
                    den += 1
                    word = re.split(r"\s+", m.group(1).strip())
                    parts[" ".join(word[:2]) if word[0] in ("git", "zeroshot", "sed", "sh") else word[0]] += 1
    if ts and ts >= since: sess += 1; hit += den > d0
print("since", since, "sessions", sess, "with a denial", hit, "calls", calls, "denials", den)
print(", ".join("%s %d" % kv for kv in parts.most_common(40)))
