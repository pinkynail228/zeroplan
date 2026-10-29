#!/bin/sh
# Critic call: devtools/zeroshot/critic.sh NAME [high|xhigh]
# Argument turn: devtools/zeroshot/critic.sh NAME --argue SESSION_ID [high|xhigh]
# Reads ~/zs-pause/critic/NAME.md (NAME-argue.md for --argue), writes NAME.out (NAME-argue.out). Both run read-only:
# `codex exec resume` has no -s and otherwise inherits the user's config (seen: danger-full-access on an argue turn).
# No daily cap: the triggers in ORCHESTRATOR.md (Critic) decide when to call; calls.log keeps the count.
set -eu
usage() { echo "usage: critic.sh NAME [high|xhigh] | critic.sh NAME --argue SESSION_ID [high|xhigh]" >&2; exit 2; }
[ $# -ge 1 ] || usage
name=$1
dir=${ZS_CRITIC_DIR:-$HOME/zs-pause/critic}
if [ "${2:-}" = --argue ]; then
    [ $# -ge 3 ] || usage
    session=$3 effort=${4:-high} brief=$dir/$name-argue.md out=$dir/$name-argue.out
else
    session= effort=${2:-high} brief=$dir/$name.md out=$dir/$name.out
fi
case $effort in high|xhigh) ;; *) echo "critic.sh: effort must be high or xhigh" >&2; exit 2 ;; esac
[ -f "$brief" ] || { echo "critic.sh: missing $brief" >&2; exit 2; }
printf '%s %s %s %s\n' "$(date +%Y-%m-%d)" "$name" "$effort" "${session:+argue}" >> "$dir/calls.log"
if [ -n "$session" ]; then
    exec codex exec resume -m gpt-6.1-sol -c model_reasoning_effort="$effort" -c sandbox_mode='"read-only"' \
        -o "$out" "$session" - < "$brief"
fi
exec codex exec -m gpt-6.1-sol -c model_reasoning_effort="$effort" -s read-only -C . \
    --add-dir /tmp/zs-zplan -o "$out" - < "$brief"
