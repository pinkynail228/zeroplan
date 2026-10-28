#!/bin/sh
# UI lab runner: restarts the prototype after each source edit (exit code 3).
# Stop with: tmux kill-session -t zplan-ui
cd "$(dirname "$0")" || exit 1
PY=../../build/ui-lab-venv/bin/python
while true; do
    "$PY" "${1:-welcome.py}"
    [ $? -eq 3 ] || sleep 1
done
