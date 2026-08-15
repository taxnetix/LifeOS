#!/usr/bin/env bash
# Headless /heartbeat wrapper for scheduled runs.
#
# NOT INSTALLED BY THE BUILD. Turning this on means an agent writes to your
# financial records and spends tokens while you are not watching. That is your
# decision to make deliberately, once you trust the system.
# See docs/adr/0013-scheduling-template-not-installed.md
#
#   bash tools/scheduler/heartbeat.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VAULT="${LIFEOS_VAULT:-$REPO/vault}"
LOG="$VAULT/state/scheduler.log"
LOCK="$VAULT/state/heartbeat.lock"
TIMEOUT="${LIFEOS_HEARTBEAT_TIMEOUT:-900}"

export DYLD_FALLBACK_LIBRARY_PATH="${DYLD_FALLBACK_LIBRARY_PATH:-/opt/homebrew/lib}"

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG"; }

# Single-writer discipline assumes one loop at a time. An hourly job whose
# predecessor is still running would otherwise produce two concurrent heartbeats.
exec 9>"$LOCK"
if ! flock -n 9 2>/dev/null; then
  if command -v flock >/dev/null; then log "skipped: previous run still holding the lock"; exit 0; fi
  # macOS has no flock(1) by default; fall back to a pid file.
  if [[ -s "$LOCK" ]] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    log "skipped: previous run (pid $(cat "$LOCK")) still running"; exit 0
  fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

command -v claude >/dev/null || { log "ERROR: claude CLI not on PATH"; exit 1; }
[[ -f "$VAULT/profile/profile.yaml" ]] || { log "skipped: no vault — run /lifeos-init"; exit 0; }

log "starting heartbeat"
cd "$REPO"
if out="$(timeout "$TIMEOUT" claude -p /heartbeat 2>&1)"; then
  log "ok: $(echo "$out" | tail -3 | tr '\n' ' ')"
else
  rc=$?
  log "FAILED (rc=$rc): $(echo "$out" | tail -5 | tr '\n' ' ')"
  log "cursors were not advanced; the next SENSE will emit run.failed and retry"
  exit $rc
fi
