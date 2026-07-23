#!/usr/bin/env bash
# Stop: backend QA gate — block finishing while basedpyright reports errors in backend/.
# No-op until basedpyright is installed. stop_hook_active guard prevents a loop.
set -euo pipefail

input=$(cat)
active=$(printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('stop_hook_active',False))" 2>/dev/null || echo False)
[ "$active" = "True" ] && exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
proj="$root/backend"
[ -d "$proj" ] || exit 0

bp="$proj/.venv/bin/basedpyright"
[ -x "$bp" ] || bp="basedpyright"
command -v "$bp" >/dev/null 2>&1 || exit 0

out=$("$bp" --project "$proj" 2>&1) || true
errs=$(printf '%s' "$out" | grep -oE '[0-9]+ error' | head -1 | grep -oE '^[0-9]+' || echo 0)

if [ "${errs:-0}" -gt 0 ]; then
  printf '%s\n' "$out" | tail -n 40 >&2
  echo "basedpyright reports ${errs} error(s) in backend/ — fix before finishing." >&2
  exit 2
fi
exit 0
