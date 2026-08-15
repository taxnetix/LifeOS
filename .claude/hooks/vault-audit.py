#!/usr/bin/env python3
"""PostToolUse audit — appends every vault mutation to state/audit.jsonl.

Append-only, many writers, which is safe precisely because it is append-only.
Paths are recorded vault-relative: an absolute path leaks the username and is
meaningless on another machine.

Never blocks and never raises. An audit failure must not break a run.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MUTATORS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def vault_root() -> Path:
    env = os.environ.get("LIFEOS_VAULT", "").strip()
    return Path(env).expanduser() if env else REPO / "vault"


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0

    tool = event.get("tool_name", "")
    if tool not in MUTATORS:
        return 0

    tin = event.get("tool_input", {}) or {}
    target = str(tin.get("file_path") or tin.get("notebook_path") or "")
    if not target:
        return 0

    root = vault_root()
    try:
        rel = Path(target).resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return 0  # outside the vault — the system repo is git-tracked instead

    try:
        size = Path(target).stat().st_size
    except OSError:
        size = 0

    rec = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "vault.write",
        "tool": tool,
        "path": str(rel),
        "bytes": size,
        "run_id": os.environ.get("LIFEOS_RUN_ID", "adhoc"),
    }
    try:
        out = root / "state" / "audit.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
