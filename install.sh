#!/bin/sh
# One-command install of zplan: fetch the newest release tag and install it, then run `zplan setup`.
#
#     curl -fsSL https://raw.githubusercontent.com/pinkynail228/zeroplan/main/install.sh | sh
#
# install.sh itself fetches and installs with only git and python3 (A2). The final `zplan setup` installs the pinned
# Codex through `npm ci` and therefore needs Node.js >= 16 with npm on PATH (docs/INSTALLATION.md). The one command
# is only complete when that setup succeeded: when Node.js/npm are missing setup reports its prerequisite and
# install.sh stops with a non-zero status, so it never reports a half-ready install that `zplan login` cannot use.
# The engine's setup needs Node.js, which A2's wording "needs only git and python3" cannot satisfy on its own; that
# prerequisite conflict is escalated to the owner rather than waived here (install Node.js and re-run install.sh or
# `zplan setup` to finish). Arguments go to the release's install.py (for example `sh install.sh --wheelhouse DIR`).
# ZPLAN_VERSION=X.Y.Z pins the release; ZPLAN_REPOSITORY overrides the repository (the same default as
# terminal_planner/update.py); ZEROSHOT_TOOLS may start with `~`, like install.py expands it.
set -eu

REPOSITORY="${ZPLAN_REPOSITORY:-https://github.com/pinkynail228/zeroplan.git}"

fail() {
    printf 'zplan: %s\n' "$1" >&2
    exit 1
}

command -v git >/dev/null 2>&1 || fail "git is required on PATH"
command -v python3 >/dev/null 2>&1 || fail "python3 is required on PATH (3.11 or newer)"

if [ -n "${ZPLAN_VERSION:-}" ]; then
    version="${ZPLAN_VERSION#v}"
else
    tags=$(git ls-remote --tags --refs "$REPOSITORY" 2>/dev/null \
        | sed -n 's#.*refs/tags/v\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)$#\1#p')
    [ -n "$tags" ] || fail "$REPOSITORY has no vX.Y.Z releases"
    version=$(printf '%s\n' "$tags" | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1)
fi

tmpdir="${TMPDIR:-/tmp}"
tmpdir="${tmpdir%/}"
work=$(mktemp -d "$tmpdir/zplan-install.XXXXXX") || fail "could not create a temporary directory in $tmpdir"
trap 'rm -rf "$work"' EXIT INT TERM
git clone --quiet --depth 1 --branch "v$version" "$REPOSITORY" "$work" || fail "could not fetch release v$version"
# A1: install.py is told that this script runs `zplan setup` right after, so its closing line never sends the
# owner to a `zplan setup` the one command already performs.
ZPLAN_SETUP_FOLLOWS=1 python3 "$work/install.py" "$@" || fail "install.py of release v$version failed"

if [ -n "${ZEROSHOT_TOOLS:-}" ]; then
    case "$ZEROSHOT_TOOLS" in
        "~") tools="$HOME" ;;
        "~/"*) tools="$HOME/${ZEROSHOT_TOOLS#\~/}" ;;
        *) tools="$ZEROSHOT_TOOLS" ;;
    esac
    launcher="$tools/bin/zplan"
else
    launcher="$HOME/.local/bin/zplan"
fi
# A2: the one command is complete only when `zplan setup` installed the pinned Codex; a setup failure is a failure of
# the install, never a success with a manual step left over (`zplan login` needs those tools).
if ! "$launcher" setup; then
    if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
        fail "zplan setup failed; retry $launcher setup"
    fi
    fail "zplan setup requires Node.js >= 16 and npm (they install the pinned Codex): zplan login does not work without them. Install Node.js and retry $launcher setup"
fi

# A2: setup succeeded, so the one command ends with a single line naming the next step. `zplan login` is that step
# (setup installed the pinned Codex); when the launcher directory is not on PATH the same line carries the export
# that puts it there.
bin_dir="${launcher%/*}"
case ":$PATH:" in
    *":$bin_dir:"*) printf 'zplan: next step: zplan login.\n' ;;
    *) printf 'zplan: export PATH="%s:$PATH"; next step: zplan login.\n' "$bin_dir" ;;
esac
