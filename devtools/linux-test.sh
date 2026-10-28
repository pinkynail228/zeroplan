#!/bin/sh
# Run unittest on the Linux test host from a fresh copy of this checkout (tracked + untracked, not ignored).
# Usage: devtools/linux-test.sh [unittest args]   (default: discover -s tests)
#        devtools/linux-test.sh --py SCRIPT [args]   (run a Python script instead, e.g. devtools/driver_qual.py)
# ZPLAN_TEST_TIMEOUT (seconds, default 1800) bounds the remote command; a candidate qualification needs more.
# Evidence names the tree: the run prints HEAD and refuses a dirty checkout (tracked changes or untracked files);
# ZPLAN_TEST_DIRTY=1 allows an ad-hoc run, marked "dirty" in its header (not merge evidence).
# Old-release matrix sources (ZEROSHOT_V010_SOURCE, ...) are passed through only if set here.
set -eu
# Test host, resolved only at runtime (no built-in destination): ZPLAN_TEST_HOST
# when non-blank after trimming, else the first non-blank line of
# ~/.config/zplan-dev/test-host.  Neither source usable -> exit 2, no remote call.
# trim: strip whitespace from both ends of the whole value only, so an embedded
# newline or CR never reaches ssh as part of the destination while any inner
# character is preserved.
trim() {
  v=$1
  while :; do
    case $v in
      [[:space:]]*) v=${v#?} ;;
      *[[:space:]]) v=${v%?} ;;
      *) break ;;
    esac
  done
  printf '%s' "$v"
}
host=
if [ -n "${ZPLAN_TEST_HOST:-}" ]; then
  host=$(trim "$ZPLAN_TEST_HOST")
fi
if [ -z "$host" ]; then
  host_file=$HOME/.config/zplan-dev/test-host
  # A regular readable file only: a directory or an unreadable path is the same
  # single-line diagnostic below, never a shell read error next to it.
  if [ -f "$host_file" ] && [ -r "$host_file" ]; then
    line=
    while IFS= read -r line || [ -n "$line" ]; do
      line=$(trim "$line")
      if [ -n "$line" ]; then host=$line; break; fi
    done <"$host_file"
  fi
fi
if [ -z "$host" ]; then
  echo "linux-test: no test host: set ZPLAN_TEST_HOST or put the host in ~/.config/zplan-dev/test-host" >&2
  exit 2
fi
repo=$(git rev-parse --show-toplevel)
dirty=$(git -C "$repo" status --porcelain -- . ':!prototype' ':!reference' | wc -l | tr -d ' ')
if [ "$dirty" != 0 ] && [ "${ZPLAN_TEST_DIRTY:-}" != 1 ]; then
  echo "linux-test: $dirty uncommitted/untracked paths; commit first or set ZPLAN_TEST_DIRTY=1" >&2; exit 2
fi
echo "linux-test: tree $(git -C "$repo" rev-parse HEAD) $([ "$dirty" = 0 ] && echo clean || echo "dirty($dirty)") host $host"
dir=$(ssh "$host" 'mktemp -d ~/zplan-test-XXXXXX')
# TMPDIR lives outside the copied checkout: installed-app tests require paths outside it.
tmp=$(ssh "$host" 'mktemp -d ~/zplan-tmp-XXXXXX')
trap 'ssh "$host" "rm -rf $dir $tmp"' EXIT
cd "$repo"
git ls-files -co --exclude-standard -z -- . ':!prototype' ':!reference' |
  rsync -a --from0 --files-from=- . "$host:$dir/"
# Tool dir name of the default toolchain (toolchain.py), read here and used on the host.
tooldir=$(PYTHONPATH=. python3 -c 'from terminal_planner import toolchain; print(toolchain.current().tool_dir_name)')
mode='-m unittest'
if [ "${1:-}" = --py ]; then shift; mode=; fi
[ $# -gt 0 ] || set -- discover -s tests
q() { printf "'%s'" "$(printf %s "$1" | sed "s/'/'\\\\''/g")"; }
args=; for a in "$@"; do args="$args $(q "$a")"; done
pass=
for v in ZEROSHOT_C2A_SOURCE ZEROSHOT_C1B_SOURCE ZEROSHOT_V010_SOURCE ZEROSHOT_V011_SOURCE; do
  eval "val=\${$v:-}"; [ -z "$val" ] || pass="$pass $v=$(q "$val")"
done
# The copy is a git checkout again (index only): source-hygiene tests list files with git ls-files.
ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=8 "$host" "cd $dir && git init -q && git add -A && umask 022 && env TMPDIR=$tmp PYTHONPATH=.:tests$pass ZPLAN_TEST_WHEELHOUSE=\$HOME/zplan-wheelhouse \
  ZEROSHOT_TEST_BINARY=\$HOME/.local/share/planning-kit/tools/$tooldir/zeroshot \
  timeout ${ZPLAN_TEST_TIMEOUT:-1800} python3 $mode$args"
