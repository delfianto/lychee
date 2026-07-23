#!/usr/bin/env bash
# PostToolUse(Edit|Write): format/lint-fix edited *frontend* files, if a formatter is set up.
# Path-scoped to frontend/. Non-blocking; a no-op until eslint/prettier are configured.
set -euo pipefail

input=$(cat)
file=$(printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || true)

case "$file" in
  */frontend/*) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
bin="$root/frontend/node_modules/.bin"

if [ -x "$bin/eslint" ]; then
  ( cd "$root/frontend" && "$bin/eslint" --fix "$file" ) >/dev/null 2>&1 || true
fi
if [ -x "$bin/prettier" ]; then
  "$bin/prettier" --write "$file" >/dev/null 2>&1 || true
fi
exit 0
