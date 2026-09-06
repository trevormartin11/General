#!/bin/bash
# Double-click (macOS): runs an offline practice draft in this window. Enter = take the #1 pick.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
"$PY" draft.py mock "$@"
echo
read -r -p "Practice draft finished. Press Enter to close."
