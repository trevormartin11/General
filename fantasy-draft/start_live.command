#!/bin/bash
# Double-click (macOS) or run from a terminal: opens the draft co-pilot in this window.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
"$PY" draft.py live "$@"
echo
read -r -p "Co-pilot stopped. Press Enter to close."
