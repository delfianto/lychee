#!/usr/bin/env bash
# PreToolUse(Bash): git push policy.
#   - normal `git push`  -> auto-approved (no prompt)
#   - force-y pushes     -> require explicit approval (they rewrite remote history)
# Any non-push Bash command is deferred to the normal permission rules.
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || true)

# Not a `git push` → defer to normal permission handling.
printf '%s' "$cmd" | grep -qE '(^|[^[:alnum:]_])git[[:space:]]+push([^[:alnum:]_]|$)' || exit 0

# Force-y push → still ask.
if printf '%s' "$cmd" | grep -qE '(--force|--force-with-lease|--force-if-includes|(^|[[:space:]])-[[:alnum:]]*f([[:space:]]|$)|[[:space:]]\+[^[:space:]]+)'; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"Force push rewrites remote history — confirm."}}'
  exit 0
fi

# Normal push → auto-approve.
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Repo policy: normal git push is auto-approved."}}'
exit 0
