#!/usr/bin/env bash
# Install the git pre-commit guard. Run once per clone.
#
#     bash tools/scripts/install-hooks.sh
#
# This is the HARD control against vault leakage. .gitignore is advisory;
# this is not. See docs/adr/0008-vault-location-and-separation.md
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO/.claude/hooks/pre-commit"
DEST="$REPO/.git/hooks/pre-commit"

[[ -d "$REPO/.git" ]] || { echo "Not a git repo: $REPO" >&2; exit 1; }
[[ -f "$SRC" ]] || { echo "Missing $SRC" >&2; exit 1; }

if [[ -e "$DEST" && ! -L "$DEST" ]]; then
  cp "$DEST" "$DEST.backup.$(date +%s)"
  echo "Existing pre-commit backed up."
fi

ln -sf "../../.claude/hooks/pre-commit" "$DEST"
chmod +x "$SRC"
echo "Installed: .git/hooks/pre-commit -> .claude/hooks/pre-commit"
echo "Never bypass it with --no-verify."
