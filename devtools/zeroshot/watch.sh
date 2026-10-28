#!/bin/sh
# Orchestrator watchdog: block until a zplan run needs attention, then print the board and exit.
# Attention = an active run finished, or one has been silent for SILENT minutes (default 20), or a provider error
# showed up (403/429/502/timeout in its last message), or a reviewer reported `conflict:` (contradictory brief). Run it in the background; its exit is the notification.
# Usage: devtools/zeroshot/watch.sh [SILENT_MINUTES]
silent=${1:-20}
here=$(dirname "$0")
active() { python3 "$here/board.py" 2>/dev/null | grep -c "статус: идёт"; }
start=$(active)
while :; do
  out=$(python3 "$here/board.py" 2>/dev/null)
  now=$(printf '%s\n' "$out" | grep -c "статус: идёт")
  stale=$(printf '%s\n' "$out" | grep "статус: идёт" | sed -n 's/.*последняя активность \([0-9]*\) ч.*/999/p; s/.*последняя активность \([0-9]*\) мин.*/\1/p' |
    awk -v s="$silent" '$1>=s' | head -1)
  provider=$(printf '%s\n' "$out" | grep -i -E "403|429|502|503|Bad Gateway|timed out|No permission" | head -1)
  conflict=$(printf '%s\n' "$out" | grep -i -E "(rejected — (rejected: *)?|\(исполнитель\): )conflict:" | head -1)
  if [ "$now" -lt "$start" ] || [ -n "$stale" ] || [ -n "$provider" ] || [ -n "$conflict" ]; then
    echo "watch: active $start -> $now; silent>=${silent}m: ${stale:-no}; provider: ${provider:-no}; conflict: ${conflict:-no}"
    python3 "$here/board.py" --all 2>&1 | head -40 | cut -c1-300
    exit 0
  fi
  [ "$now" -gt "$start" ] && start=$now
  sleep 60
done
