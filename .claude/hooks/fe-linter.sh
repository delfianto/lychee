#!/usr/bin/env bash
# PostToolUse(Edit|Write): format/lint-fix edited frontend files through local Vite+.
# Path-scoped to frontend/. Non-blocking; skips generated assets.
set -euo pipefail

input=$(cat)
file=$(printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || true)

case "$file" in
  */frontend/*) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0
case "$file" in
  */src/api/schema.d.ts|*/public/*|*/bun.lock) exit 0 ;;
esac

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
bin="$root/frontend/node_modules/.bin"

if [ -x "$bin/vp" ]; then
  ( cd "$root/frontend" && "$bin/vp" fmt "$file" ) >/dev/null 2>&1 || true
  case "$file" in
    *.ts|*.js|*.vue)
      ( cd "$root/frontend" && "$bin/vp" lint --fix "$file" ) >/dev/null 2>&1 || true
      ;;
  esac
fi
exit 0
