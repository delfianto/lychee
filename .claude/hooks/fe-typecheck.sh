#!/usr/bin/env bash
# Stop: frontend QA gate — block finishing while vue-tsc reports type errors in frontend/.
# No-op until deps are installed (frontend/node_modules/.bin/vue-tsc present).
set -euo pipefail

input=$(cat)
active=$(printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('stop_hook_active',False))" 2>/dev/null || echo False)
[ "$active" = "True" ] && exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
proj="$root/frontend"
tsc="$proj/node_modules/.bin/vue-tsc"
[ -x "$tsc" ] || exit 0

if ! out=$(cd "$proj" && "$tsc" --noEmit 2>&1); then
  printf '%s\n' "$out" | tail -n 40 >&2
  echo "vue-tsc reports type error(s) in frontend/ — fix before finishing." >&2
  exit 2
fi
exit 0
