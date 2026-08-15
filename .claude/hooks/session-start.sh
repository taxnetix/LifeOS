#!/usr/bin/env bash
# SessionStart — load the digest so every session starts oriented.
#
# Cheap and read-only: profile, state, open loops, memory digest. Never mutates.
# Silent when there is no vault; /lifeos-init is the answer, and saying so once
# is enough.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VAULT="${LIFEOS_VAULT:-$REPO/vault}"

if [[ ! -f "$VAULT/profile/profile.yaml" ]]; then
  echo "LifeOS: no vault at \$VAULT. Run /lifeos-init to create one."
  exit 0
fi

echo "=== LifeOS session digest ==="
echo "vault: \$VAULT"

# Enabled domains
if command -v grep >/dev/null; then
  enabled="$(awk '/^domains:/{f=1;next} f&&/^[a-z]/{exit} f&&/: *true/{gsub(/[ :]/,"");sub(/true/,"");print}' \
    "$VAULT/profile/profile.yaml" 2>/dev/null | tr '\n' ' ')"
  [[ -n "${enabled// }" ]] && echo "domains enabled: $enabled" || echo "domains enabled: none yet"
fi

# Queue depth and anything waiting on the human
if [[ -f "$VAULT/state/queue.json" ]] && command -v jq >/dev/null; then
  depth="$(jq -r '.items | length' "$VAULT/state/queue.json" 2>/dev/null || echo 0)"
  echo "queue: ${depth} item(s)"
fi

pending="$(find "$VAULT/proposed" -type f ! -name 'README.md' ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' ')"
[[ "$pending" != "0" ]] && echo "AWAITING YOU: $pending item(s) in \$VAULT/proposed/"

open_gaps="$(grep -c '"closed_at"' "$VAULT/state/gaps.jsonl" 2>/dev/null || echo 0)"
total_gaps="$(wc -l < "$VAULT/state/gaps.jsonl" 2>/dev/null | tr -d ' ' || echo 0)"
[[ "$total_gaps" != "0" ]] && echo "gaps: $((total_gaps - open_gaps)) open"

# Last run
if [[ -f "$VAULT/state/run-log.jsonl" ]]; then
  last="$(tail -1 "$VAULT/state/run-log.jsonl" 2>/dev/null)"
  if command -v jq >/dev/null && [[ -n "$last" ]]; then
    echo "last run: $(echo "$last" | jq -r '"\(.run_id) \(.outcome)\(if .quiet then " (quiet)" else "" end)"' 2>/dev/null)"
  fi
fi

# Long-term memory digest — the durable facts, kept short on purpose
if compgen -G "$VAULT/memory/long/*.md" >/dev/null 2>&1; then
  echo "--- long-term memory ---"
  head -qn 3 "$VAULT"/memory/long/*.md 2>/dev/null | grep -v '^---$' | head -20
fi

echo "=== run /boot for a full orientation ==="
exit 0
