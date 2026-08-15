"""System health — backs /status. Read-only.

Agent health, ledger staleness, queue depth, open gaps, stale rulebooks and
GitHub milestone progress in one JSON blob.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from . import atomic, clock, vault


def _age_days(ts: str | None, now: datetime) -> int | None:
    if not ts:
        return None
    try:
        then = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None
    return int((now - then).total_seconds() // 86_400)


def status() -> dict:
    now = clock.utc_now()
    out: dict = {
        "schema": "status/1",
        "at": clock.stamp(now),
        "vault": vault.rel(vault.vault_root()),
        "initialised": vault.is_initialised(),
    }
    if not out["initialised"]:
        out["note"] = "No vault. Run /lifeos-init."
        return out

    # Agents
    agents = []
    adir = vault.path("state", "agents")
    if adir.is_dir():
        for f in sorted(adir.glob("*.json")):
            st = atomic.read_json(f, {}) or {}
            last = (st.get("last_run") or {})
            agents.append(
                {
                    "agent": st.get("agent", f.stem),
                    "health": st.get("health", "never_run"),
                    "last_run": last.get("run_id"),
                    "outcome": last.get("outcome"),
                    "age_days": _age_days(last.get("started_at"), now),
                    "open_loops": len(st.get("open_loops", [])),
                    "pending_questions": len(st.get("pending_questions", [])),
                    "confidence": st.get("confidence"),
                }
            )
    out["agents"] = agents
    out["agents_unhealthy"] = [a["agent"] for a in agents if a["health"] not in {"healthy", "never_run"}]

    # Ledgers
    cursors = atomic.read_json(vault.path("state", "cursors.json"), {}) or {}
    ledgers = []
    ldir = vault.path("ledgers")
    if ldir.is_dir():
        for f in sorted(ldir.glob("*.jsonl")):
            info = cursors.get("ledgers", {}).get(f.stem, {})
            ledgers.append(
                {
                    "ledger": f.stem,
                    "records": info.get("records", sum(1 for _ in atomic.read_jsonl(f))),
                    "age_days": _age_days(info.get("last_written"), now),
                    "freshness_days": info.get("freshness_days", 90),
                }
            )
    out["ledgers"] = ledgers
    out["ledgers_stale"] = [
        x["ledger"] for x in ledgers
        if x["age_days"] is not None and x["age_days"] > x["freshness_days"]
    ]

    # Queue
    q = atomic.read_json(vault.path("state", "queue.json"), {}) or {}
    items = q.get("items", [])
    out["queue"] = {
        "depth": len(items),
        "queued": sum(1 for i in items if i.get("state") == "queued"),
        "in_progress": sum(1 for i in items if i.get("state") == "in_progress"),
        "failed": sum(1 for i in items if i.get("state") == "failed"),
        "parked": sum(1 for i in items if i.get("state") == "parked"),
    }

    # Gaps
    gaps = [g for g in atomic.read_jsonl(vault.path("state", "gaps.jsonl")) if not g.get("closed_at")]
    out["gaps"] = {
        "open": len(gaps),
        "blocking": sum(1 for g in gaps if g.get("blocking")),
        "by_consequence": {
            k: sum(1 for g in gaps if g.get("consequence") == k)
            for k in ("catastrophic", "severe", "moderate", "minor")
        },
    }

    # Rulebooks past their refresh interval
    out["rules_stale"] = [
        name for name, info in cursors.get("rules", {}).items()
        if (d := _age_days(info.get("verified") or info.get("as_at"), now)) is not None and d > 365
    ]

    # Proposals awaiting the human
    proposed = vault.path("proposed")
    pending = [
        vault.rel(f) for f in proposed.rglob("*")
        if f.is_file() and f.name != "README.md" and not f.name.startswith(".")
    ] if proposed.is_dir() else []
    out["awaiting_human"] = {"count": len(pending), "paths": pending[:20]}

    # GitHub mirror
    issues = list(atomic.read_jsonl(vault.path("state", "system", "issues.jsonl")))
    by_ms: dict[str, dict[str, int]] = {}
    for i in issues:
        ms = i.get("milestone") or "unassigned"
        b = by_ms.setdefault(ms, {"open": 0, "closed": 0})
        b["open" if i.get("state") == "open" else "closed"] += 1
    out["github"] = {
        "mirrored": len(issues),
        "open": sum(1 for i in issues if i.get("state") == "open"),
        "drafts_unfiled": sum(1 for i in issues if i.get("local_only")),
        "last_synced": cursors.get("github", {}).get("last_synced"),
        "reachable": cursors.get("github", {}).get("reachable"),
        "milestones": by_ms,
    }

    # Last runs
    runs = list(atomic.read_jsonl(vault.path("state", "run-log.jsonl")))
    out["runs"] = {
        "total": len(runs),
        "last": runs[-1] if runs else None,
        "quiet_ratio": round(sum(1 for r in runs if r.get("quiet")) / len(runs), 2) if runs else None,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="lifeos.status").parse_args(argv)
    print(json.dumps(status(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
