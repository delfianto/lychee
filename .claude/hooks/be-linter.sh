#!/usr/bin/env bash
# PostToolUse(Edit|Write): auto-format + lint-fix edited *backend* Python files (ruff).
# Path-scoped to backend/ so it's inert for frontend edits. Non-blocking; no-op if
# ruff isn't available yet.
set -euo pipefail

input=$(cat)
file=$(printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || true)

case "$file" in
  */backend/*.py|backend/*.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
ruff="$root/backend/.venv/bin/ruff"
[ -x "$ruff" ] || ruff="ruff"
command -v "$ruff" >/dev/null 2>&1 || exit 0

"$ruff" format "$file" >/dev/null 2>&1 || true
"$ruff" check --fix "$file" >/dev/null 2>&1 || true
exit 0
