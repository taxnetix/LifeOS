"""Sync the GitHub issue mirror. Backs SENSE's github.* signals and /issues.

Files remain the source of truth: state/system/issues.jsonl is the local view,
and this refreshes it when the network is up.  When it is not — a flight, an
outage, an expired token — it degrades SILENTLY to the cache and sets
reachable:false.  GitHub can never fail a heartbeat.

Only SYSTEM work is mirrored. Personal data may never reach GitHub, and the
pii-guard hook enforces that on the `gh` call itself rather than trusting this
module.  See docs/adr/0017-github-for-system-work.md and docs/github.md.

Read-only by design: this module never creates, edits or closes an issue.
Filing goes through proposed/issues/ and /issues push, which is the human gate.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import atomic, clock, vault

MIRROR = ("state", "system", "issues.jsonl")
_TIMEOUT = 20

_FIELDS = "number,title,state,labels,milestone,assignees,url,createdAt,updatedAt"


def _gh(*args: str) -> tuple[bool, str]:
    """Run gh read-only. Never raises — unreachable is a normal condition."""
    try:
        p = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return False, "gh not installed"
    except subprocess.TimeoutExpired:
        return False, f"gh timed out after {_TIMEOUT}s"
    if p.returncode != 0:
        return False, (p.stderr or p.stdout).strip().splitlines()[0] if (p.stderr or p.stdout) else "gh failed"
    return True, p.stdout


def _normalise(raw: dict, synced_at: str) -> dict:
    return {
        "number": raw.get("number"),
        "title": raw.get("title", ""),
        "state": (raw.get("state") or "OPEN").lower(),
        "labels": sorted(lb["name"] for lb in raw.get("labels", []) if "name" in lb),
        "milestone": (raw.get("milestone") or {}).get("title"),
        "assignees": sorted(a["login"] for a in raw.get("assignees", []) if "login" in a),
        "url": raw.get("url", ""),
        "created_at": raw.get("createdAt"),
        "updated_at": raw.get("updatedAt"),
        "synced_at": synced_at,
        "local_only": False,
    }


def _local_drafts() -> list[dict]:
    """Unfiled drafts in proposed/issues/, so the backlog is complete offline."""
    out = []
    d = vault.path("proposed", "issues")
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        title = f.stem.replace("-", " ")
        labels: list[str] = []
        for line in f.read_text(encoding="utf-8").splitlines()[:20]:
            low = line.lower()
            if low.startswith("title:"):
                title = line.split(":", 1)[1].strip()
            elif low.startswith("labels:"):
                labels = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
        out.append(
            {
                "title": title,
                "state": "open",
                "labels": labels,
                "local_only": True,
                "draft_path": vault.rel(f),
            }
        )
    return out


def sync(*, offline: bool = False) -> dict:
    synced_at = clock.stamp()
    result: dict = {"schema": "gh-sync/1", "at": synced_at, "reachable": False, "mirrored": 0}

    drafts = _local_drafts()
    remote: list[dict] = []

    if not offline:
        ok, out = _gh(
            "issue", "list",
            "--state", "all",
            "--limit", "200",
            "--json", _FIELDS,
        )
        if ok:
            try:
                remote = [_normalise(r, synced_at) for r in json.loads(out)]
                result["reachable"] = True
            except json.JSONDecodeError as e:
                result["error"] = f"gh returned unparseable JSON: {e}"
        else:
            result["error"] = out
    else:
        result["error"] = "offline mode requested"

    if result["reachable"]:
        # Full replace: the remote is authoritative for filed issues, drafts are
        # ours.  The mirror is a cache, so rewriting it wholesale is correct.
        lines = remote + drafts
        path = vault.path(*MIRROR)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic.write_text(
            path,
            "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in lines),
        )
        result["mirrored"] = len(lines)
        result["open"] = sum(1 for r in lines if r["state"] == "open")
    else:
        # Degrade to cache. Report it; never fail.
        existing = list(atomic.read_jsonl(vault.path(*MIRROR)))
        result["mirrored"] = len(existing)
        result["open"] = sum(1 for r in existing if r.get("state") == "open")
        result["degraded_to_cache"] = True

    result["drafts_unfiled"] = len(drafts)

    # Record reachability in cursors so /status and the journal can report it.
    cpath = vault.path("state", "cursors.json")
    cursors = atomic.read_json(cpath, {}) or {}
    cursors.setdefault("schema", "cursors/1")
    cursors["github"] = {"last_synced": synced_at, "reachable": result["reachable"]}
    atomic.write_json(cpath, cursors)

    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.gh_sync")
    ap.add_argument("--offline", action="store_true", help="skip the network; report the cache")
    args = ap.parse_args(argv)
    if not vault.is_initialised():
        print(json.dumps({"error": "no vault — run /lifeos-init", "reachable": False}))
        return 0
    print(json.dumps(sync(offline=args.offline), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
