#!/bin/sh
# Run unittest on this Mac from the current checkout (the macOS half of the merge gate; Linux: devtools/linux-test.sh).
# Usage: devtools/mac-test.sh [unittest args]   (default: discover -s tests)
# Textual comes from the offline wheelhouse (tests/tui_support.py); without it the TUI tests skip silently,
# so the preflight refuses to start instead of reporting a misleading result. ZPLAN_MAC_PYTHON default python3.13.
# Evidence names the tree: the run prints HEAD and refuses a dirty checkout; ZPLAN_TEST_DIRTY=1 allows an ad-hoc run.
set -eu
py=${ZPLAN_MAC_PYTHON:-python3.13}
repo=$(git rev-parse --show-toplevel)
dirty=$(git -C "$repo" status --porcelain -- . ':!prototype' ':!reference' | wc -l | tr -d ' ')
if [ "$dirty" != 0 ] && [ "${ZPLAN_TEST_DIRTY:-}" != 1 ]; then
  echo "mac-test: $dirty uncommitted/untracked paths; commit first or set ZPLAN_TEST_DIRTY=1" >&2; exit 2
fi
wheels=${ZPLAN_TEST_WHEELHOUSE:-$HOME/.cache/zplan-wheelhouse}
ls "$wheels"/textual-*.whl >/dev/null 2>&1 || { echo "mac-test: no textual wheel in $wheels; set ZPLAN_TEST_WHEELHOUSE" >&2; exit 2; }
command -v "$py" >/dev/null || { echo "mac-test: $py not found; set ZPLAN_MAC_PYTHON" >&2; exit 2; }
echo "mac-test: tree $(git -C "$repo" rev-parse HEAD) $([ "$dirty" = 0 ] && echo clean || echo "dirty($dirty)") python $("$py" -V 2>&1)"
# A short TMPDIR: the long session TMPDIR breaks socket-path limits in test_toolchain.
tmp=$(mktemp -d /tmp/zs-mac-XXXXXX)
trap 'rm -rf "$tmp"' EXIT
[ $# -gt 0 ] || set -- discover -s tests
cd "$repo"
TMPDIR=$tmp ZPLAN_TEST_WHEELHOUSE=$wheels PYTHONPATH=.:tests \
  "$py" -m unittest "$@"
