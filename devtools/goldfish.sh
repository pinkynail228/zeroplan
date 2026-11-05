#!/bin/sh
# One Goldfish pass: fresh Opus sessions with no conversation, read-only tools, one persona each.
# Usage: devtools/goldfish.sh DOC OUTDIR [persona ...]   (default: comprehension design_critic zoom_out)
#        devtools/goldfish.sh --reply OUTDIR PERSONA FILE   answer that reviewer in its own session (FILE: the
#        architect's evidence for each disputed finding); the answer lands in OUTDIR/PERSONA.reply-N.md
# Personas: devtools/egm/agents/*.md. Reports: OUTDIR/<persona>.md, session ids OUTDIR/<persona>.session.
# Rules: docs/DEVELOPMENT.md (a reviewer is an extra opinion without context, not an authority).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
run() {  # run SYSTEM_PROMPT_FILE OUT ERR SESSION_ARGS... -- PROMPT
  persona_file=$1; out_file=$2; err_file=$3; shift 3
  claude -p "$@" --model "${GOLDFISH_MODEL:-claude-opus-5-5}" --effort high --restricted --strict-mcp-config \
    --tools "Read,Grep,Glob" --permission-mode dontAsk --max-budget-usd "${GOLDFISH_BUDGET_USD:-8}" \
    --append-system-prompt "$(cat "$persona_file")" > "$out_file" 2> "$err_file"
}
if [ "${1:-}" = "--reply" ]; then
  out=$2; persona=$3; file=$4
  session=$(cat "$out/$persona.session")
  n=1; while [ -e "$out/$persona.reply-$n.md" ]; do n=$((n + 1)); done
  run "$here/egm/agents/$persona.md" "$out/$persona.reply-$n.md" "$out/$persona.reply-$n.err" "$(cat "$file")
Answer each point: concede it, or keep your finding with the evidence (path:line) that the architect's reply misses." \
    --resume "$session"
  [ -s "$out/$persona.reply-$n.md" ] || { echo "goldfish: no answer, see $out/$persona.reply-$n.err" >&2; exit 1; }
  echo "goldfish: answer in $out/$persona.reply-$n.md"
  exit 0
fi
doc=$1; out=$2; shift 2
[ $# -gt 0 ] || set -- comprehension design_critic zoom_out
standard=$(cat "$here/egm/standards/feature-spec-standard.md")
mkdir -p "$out"
for persona in "$@"; do
  session=$(python3 -c 'import uuid; print(uuid.uuid4())')
  echo "$session" > "$out/$persona.session"
  run "$here/egm/agents/$persona.md" "$out/$persona.md" "$out/$persona.err" "Mode: REVIEW. Target document: $doc (whole file). Target Standard: $standard
Verify every claim the document makes against the repository; cite path:line for each finding that rests on evidence. Report in English." \
    --session-id "$session" &
done
wait
for persona in "$@"; do
  [ -s "$out/$persona.md" ] || { echo "goldfish: $persona produced no report, see $out/$persona.err" >&2; exit 1; }
done
echo "goldfish: reports in $out"
