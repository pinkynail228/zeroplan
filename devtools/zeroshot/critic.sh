#!/bin/sh
# Critic call: devtools/zeroshot/critic.sh NAME
# Argument turn: devtools/zeroshot/critic.sh NAME --argue SESSION_ID
# Model gpt-6-astra at xhigh. Reads ~/zs-pause/critic/NAME.md (NAME-argue.md for --argue), writes NAME.out
# (NAME-argue.out). Both run read-only: `codex exec resume` has no -s and otherwise inherits the user's config (seen:
# danger-full-access on an argue turn). No daily cap: the triggers in ORCHESTRATOR.md (Critic) decide when to call;
# calls.log keeps the count.
set -eu
usage() { echo "usage: critic.sh NAME | critic.sh NAME --argue SESSION_ID" >&2; exit 2; }
[ $# -ge 1 ] || usage
name=$1 model=gpt-6-astra effort=xhigh
dir=${ZS_CRITIC_DIR:-$HOME/zs-pause/critic}
if [ "${2:-}" = --argue ]; then
    [ $# -eq 3 ] || usage
    session=$3 brief=$dir/$name-argue.md out=$dir/$name-argue.out
else
    [ $# -eq 1 ] || usage
    session= brief=$dir/$name.md out=$dir/$name.out
fi
[ -f "$brief" ] || { echo "critic.sh: missing $brief" >&2; exit 2; }
printf '%s %s %s %s\n' "$(date +%Y-%m-%d)" "$name" "$model/$effort" "${session:+argue}" >> "$dir/calls.log"
if [ -n "$session" ]; then
    exec codex exec resume -m "$model" -c model_reasoning_effort="$effort" -c sandbox_mode='"read-only"' \
        -o "$out" "$session" - < "$brief"
fi
exec codex exec -m "$model" -c model_reasoning_effort="$effort" -s read-only -C . \
    --add-dir /tmp/zs-zplan -o "$out" - < "$brief"
