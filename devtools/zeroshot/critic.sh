#!/bin/sh
# Critic call with a daily budget: devtools/zeroshot/critic.sh NAME [high|xhigh]
# Reads ~/zs-pause/critic/NAME.md, writes NAME.out; the 6th call of a day needs CRITIC_WHY=<reason>.
set -eu
[ $# -ge 1 ] || { echo "usage: critic.sh NAME [high|xhigh]" >&2; exit 2; }
name=$1
effort=${2:-high}
case $effort in high|xhigh) ;; *) echo "critic.sh: effort must be high or xhigh" >&2; exit 2 ;; esac
dir=${ZS_CRITIC_DIR:-$HOME/zs-pause/critic}
brief=$dir/$name.md
[ -f "$brief" ] || { echo "critic.sh: missing $brief" >&2; exit 2; }
log=$dir/calls.log
budget=${ZS_CRITIC_BUDGET:-5}
today=$(date +%Y-%m-%d)
used=$(grep -c "^$today " "$log" 2>/dev/null || true)
if [ "${used:-0}" -ge "$budget" ] && [ -z "${CRITIC_WHY:-}" ]; then
    echo "critic.sh: $used calls today (budget $budget); set CRITIC_WHY=<reason> to exceed" >&2
    exit 3
fi
printf '%s %s %s %s\n' "$today" "$name" "$effort" "${CRITIC_WHY:-}" >> "$log"
exec codex exec -m gpt-6.1-sol -c model_reasoning_effort="$effort" -s read-only -C . \
    --add-dir /tmp/zs-zplan -o "$dir/$name.out" - < "$brief"
