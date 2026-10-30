#!/bin/sh
# Run a local Zeroshot software-change review cycle on zplan in an isolated worktree.
# Usage: [ZS_ATTEMPT=2] devtools/zeroshot/run.sh NAME TASK_FILE [TASK_FILE...] [--validate-only]  (ZS_ATTEMPT: rerun after a failed run on the same worktree HEAD)
# Each TASK_FILE is plain text, one task of the milestone NAME, run in the given order (H1, docs/PLAN_0.9.md); the shared
# test-environment preamble is appended. The upstream template lane (ZS_GRAPH=template) takes one task file.
# ZS_RUNTIME=deepseek: DeepSeek worker through the shared Yandex adapter (~/.local/share/yandex-adapter/README.md,
# instance zplan, port ${ADAPTER_PORT:-8797}) and gpt-6.1-sol high reviewers on the default Codex lane (runtime-deepseek.json).
# Default on the Claude lane (since 2026-10-25, after T1, the first real graph run): the run goes through zplan's own
# milestone graph (preflight node first): milestone_run.py builds graph/runtime/input/baseline into $work.docs/ from
# TASK_FILE and the .zplan/ files into the worktree (D1). ZS_GRAPH=template = the upstream software-change template,
# the default for ZS_RUNTIME=deepseek (milestone_run.py refuses a runtime with lanes or session scopes).
# Parallel runs: one NAME per run (own worktree/branch); a second start of an active NAME is refused (lock dir
# /tmp/zs-zplan/NAME.lock). Each run gets its own TMPDIR (NAME.tmp). The native run can outlive this CLI
# (Ctrl-C/detach), so both stay until the orchestrator's cleanup after a terminal status (devtools/zeroshot/ORCHESTRATOR.md step 5).
set -eu
name=$1; shift
tasks=
while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do tasks="$tasks $1"; shift; done
[ -n "$tasks" ] || { echo "usage: run.sh NAME TASK_FILE [TASK_FILE...] [--validate-only]" >&2; exit 2; }
task=${tasks# }; task=${task%% *}
repo=$(git rev-parse --show-toplevel)
here=$repo/devtools/zeroshot
work=/tmp/zs-zplan/$name
command -v python3.13 >/dev/null 2>&1 || { echo "run: python3.13 is required for agent tests and scripts" >&2; exit 2; }
mkdir -p /tmp/zs-zplan
# Brief cap (ORCHESTRATOR.md step 1): 3 KB. The night of 2026-10-25 ran briefs of 3.5-6.9 KB, grown by design-critic
# passes; ZS_BRIEF_MAX overrides it for one run (record why in STATE).
for t in $tasks; do
  size=$(wc -c < "$t" | tr -d ' ')
  [ "$size" -le "${ZS_BRIEF_MAX:-3072}" ] || { echo "brief $t is $size bytes, cap ${ZS_BRIEF_MAX:-3072}: cut it or split the slice" >&2; exit 2; }
done
# Disk guard: reviewer scratch copies filled the disk once (STATE Open). Threshold ZS_MIN_FREE_GB (default 30).
free=$(df -Pk /tmp | awk 'NR==2 {print int($4/1048576)}')
[ "$free" -ge "${ZS_MIN_FREE_GB:-30}" ] || { echo "only ${free} GB free on /tmp; clean /tmp/zs-agent-* of finished runs" >&2; exit 2; }
stale=$(find -H /tmp -maxdepth 1 -name 'zs-agent-*' -mmin +1440 2>/dev/null | wc -l | tr -d ' ')
[ "$stale" = 0 ] || echo "note: $stale scratch dirs /tmp/zs-agent-* older than 24 h (check they belong to finished runs)" >&2
runtime=$here/runtime.json graph=${ZS_GRAPH:-zplan}
if [ "${ZS_RUNTIME:-}" = deepseek ]; then
  # Fallback lane only (ORCHESTRATOR.md step 1, owner 2026-10-24): the Claude lane is the default.
  [ -n "${ZS_WHY:-}" ] || { echo "ZS_RUNTIME=deepseek is the fallback lane: set ZS_WHY=<reason> (Claude limit, outage) and record it in STATE" >&2; exit 2; }
  runtime=$here/runtime-deepseek.json graph=${ZS_GRAPH:-template}
  port=${ADAPTER_PORT:-8797}
  python3 -c 'import sys,urllib.request; sys.exit(urllib.request.urlopen(sys.argv[1], timeout=2).read() != b"{\"adapter\":\"zplan-yandex\"}")' \
    "http://127.0.0.1:$port/zplan-adapter/health" 2>/dev/null \
    || { echo "Yandex adapter is not answering on 127.0.0.1:$port; run ~/.local/share/yandex-adapter/install.sh zplan $port" >&2; exit 2; }
  export GATEWAY_BASE_URL=http://127.0.0.1:$port/v1 GATEWAY_API_KEY=dummy
else
  # Claude agents (runtime.json) get the same hygiene as the Codex home (2026-10-24): a curated CLAUDE_CONFIG_DIR
  # with its own login; its settings.json disables the account-synced plugins, bundled skills and auto memory; no
  # hooks, MCP servers or global CLAUDE.md. Residue: claude.ai account-synced skills still list (names only).
  # Upstream Zeroshot passes CLAUDE_CONFIG_DIR and the environment through to local runs. ZS_CLAUDE_HOME overrides it.
  export CLAUDE_CONFIG_DIR=${ZS_CLAUDE_HOME:-$HOME/.local/share/zplan-dev/claude-home}
  export ENABLE_CLAUDEAI_MCP_SERVERS=false CLAUDE_CODE_DISABLE_BUNDLED_SKILLS=1 CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
  claude auth status 2>/dev/null | grep -q '"loggedIn": true' \
    || { echo "agent home $CLAUDE_CONFIG_DIR needs a login: CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR claude auth login" >&2; exit 2; }
  claude plugin list --json 2>/dev/null > "$CLAUDE_CONFIG_DIR/.plugins-check.json"
  python3 -I - "$CLAUDE_CONFIG_DIR" <<'EOF' || exit 2
import json, os, sys
home = sys.argv[1]
def load(name):
    try:
        with open(os.path.join(home, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
settings, state = load("settings.json"), load(".claude.json")
bad = [p["id"] for p in load(".plugins-check.json") or [] if p.get("enabled")]
bad += [k for k in ("hooks", "mcpServers") if settings.get(k)]
bad += [".claude.json mcpServers"] if state.get("mcpServers") else []
bad += [d for d in ("agents", "commands", "CLAUDE.md") if os.path.exists(os.path.join(home, d))]
# Auto mode (owner 2026-10-25): a classifier, not a prompt, decides what the allow list misses (the allow list
# refused 154 of 4459 agent calls); agent-settings.json keeps the deny list. Only a user-level defaultMode
# turns it on: a project-level one is ignored, and the project's acceptEdits would override it.
bad += [] if (settings.get("permissions") or {}).get("defaultMode") == "auto" else ['settings.json permissions.defaultMode != "auto"']
if bad:
    sys.exit("agent home %s is not clean: %s" % (home, ", ".join(bad)))
EOF
fi
# Dogfood agent home (P2a, critic agent-env-scope 2026-10-18): Codex agents start from a curated CODEX_HOME (no account
# apps, plugins, MCP servers or hooks; its own login), not the owner's ~/.codex. ZS_CODEX_HOME overrides the location.
export CODEX_HOME=${ZS_CODEX_HOME:-$HOME/.local/share/zplan-dev/codex-home}
[ -f "$CODEX_HOME/config.toml" ] && [ -f "$CODEX_HOME/auth.json" ] \
  || { echo "agent home $CODEX_HOME needs config.toml and a login: CODEX_HOME=$CODEX_HOME codex login" >&2; exit 2; }
# Context hygiene (2026-10-21): rollouts showed ~14.5k chars of plugin/skill listings in every reviewer prompt.
# The home must switch them off like zplan's own profile (terminal_planner/resources/agent_profile.toml).
for want in 'plugins = false' 'multi_agent = false' 'include_instructions = false'; do
  grep -qx "$want" "$CODEX_HOME/config.toml" || { echo "agent home config.toml lacks '$want' (see agent_profile.toml)" >&2; exit 2; }
done
command -v zeroshot >/dev/null || { echo "zeroshot is not on PATH" >&2; exit 2; }
mkdir "$work.lock" 2>/dev/null || { echo "run $name is already active ($work.lock)" >&2; exit 2; }
# Until dispatch nothing native exists: release the lock on any exit before it (and after --validate-only).
trap 'rmdir "$work.lock" 2>/dev/null' EXIT
mkdir -p "$work.tmp"; export TMPDIR=$work.tmp
# A worktree left by an earlier run or --validate-only at an older HEAD would run the task without main's newer
# commits: only a rerun (ZS_ATTEMPT) reuses it.
if [ -d "$work" ] && [ -z "${ZS_ATTEMPT:-}" ] && [ "$(git -C "$work" rev-parse HEAD)" != "$(git -C "$repo" rev-parse HEAD)" ]; then
  echo "worktree $work is at an older HEAD: remove it (git worktree remove, git branch -D zs-$name) or rerun with ZS_ATTEMPT" >&2
  exit 2
fi
[ -d "$work" ] || git -C "$repo" worktree add -q -b "zs-$name" "$work" HEAD
mkdir -p "$work/.claude"
cp "$here/agent-settings.json" "$work/.claude/settings.local.json"
# The agent settings stay untracked even in a repo without an ignore rule for them (gates use git add -A).
exclude="$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir)/info/exclude"
mkdir -p "$(dirname "$exclude")"
grep -qxF /.claude/settings.local.json "$exclude" 2>/dev/null || echo /.claude/settings.local.json >> "$exclude"
# Pinned native tools are untracked; link them so admission tests see the same environment.
[ -e "$repo/.tools" ] && [ ! -e "$work/.tools" ] && ln -s "$repo/.tools" "$work/.tools"
if [ "$graph" = zplan ]; then
  # shellcheck disable=SC2086  # task file names carry no spaces (devtools/zeroshot/tasks/NAME.md)
  python3.13 "$here/milestone_run.py" documents $tasks "$work.docs" --runtime "$runtime" --worktree "$work" \
    --preamble "$here/preamble.md" --title "$name"
else
  [ "$task" = "${tasks# }" ] || { echo "the template lane takes one task file" >&2; exit 2; }
  python3 -c 'import json,sys; print(json.dumps({"task": open(sys.argv[1]).read().strip() + "\n\n" + open(sys.argv[2]).read()}))' \
    "$task" "$here/preamble.md" > "$work.input.json"
fi
cd "$work"
key="zplan-$name-$(git rev-parse --short HEAD)${ZS_ATTEMPT:+-$ZS_ATTEMPT}"
if [ "$graph" = zplan ]; then
  set -- --graph "$work.docs/graph.json" --input "$work.docs/input.json" --runtime-config "$work.docs/runtime.json" \
    --submission-key "$key" "$@"
else
  set -- --template software-change --input "$work.input.json" --runtime-config "$runtime" --submission-key "$key" "$@"
fi
for arg in "$@"; do
  if [ "$arg" = --validate-only ]; then
    zeroshot run --title "zplan $name" "$@"
    exit $?
  fi
done
trap - EXIT  # a submission may happen from here on: the lock stays until the orchestrator's cleanup
exec zeroshot run --title "zplan $name" "$@"
