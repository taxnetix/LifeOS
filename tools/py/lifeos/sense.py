"""SENSE — deterministic change detection.

This is a SCRIPT, not an agent turn.  It compares state/cursors.json against the
filesystem and the SA fiscal calendar and prints a change report.  When nothing
has changed and no cadence is due it reports quiet:true, and the heartbeat agent
writes one journal line and stops — one turn, no delegation, no analysis.

That is what makes "run it hourly forever, and it costs almost nothing when
there's nothing to do" true rather than aspirational, and it is why detection is
exhaustive by enumeration rather than by judgment: adding a signal kind means
adding a detector and a test, not hoping a model notices.

See docs/adr/0003-deterministic-sense.md.

Usage:  python -m lifeos.sense [--json]
Exit:   0 always (a sense failure must not fail a heartbeat); errors go in the
        report under "errors" so the agent can see and report them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from . import atomic, calendar_za, clock, vault

# Files we never treat as an inbox document.
_INBOX_IGNORE = {".DS_Store", ".gitkeep", "README.md"}

# Default staleness thresholds in days when a ledger has no explicit cursor.
_DEFAULT_FRESHNESS = 90


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _age_seconds(ts: str | None, now: datetime) -> float | None:
    parsed = _parse(ts)
    return None if parsed is None else (now - parsed).total_seconds()


# ── detectors ────────────────────────────────────────────────────────────────
# Each returns a list of change dicts.  Each is independently testable.


def detect_inbox(cursors: dict, changes: list, errors: list) -> None:
    """New or unreadable files in inbox/, by hash against documents/index.jsonl."""
    inbox = vault.path("inbox")
    if not inbox.is_dir():
        return
    index_path = vault.path("documents", "index.jsonl")
    try:
        known = {r.get("doc_hash") for r in atomic.read_jsonl(index_path)}
    except ValueError as e:
        errors.append(f"documents/index.jsonl unreadable: {e}")
        known = set()

    for f in sorted(inbox.rglob("*")):
        if not f.is_file() or f.name in _INBOX_IGNORE or f.name.startswith("."):
            continue
        try:
            digest = _sha256(f)
        except OSError as e:
            changes.append({"kind": "inbox.unreadable", "path": vault.rel(f), "detail": str(e)})
            continue
        if digest not in known:
            changes.append(
                {
                    "kind": "inbox.new",
                    "path": vault.rel(f),
                    "sha256": digest,
                    "bytes": f.stat().st_size,
                    "suffix": f.suffix.lower(),
                }
            )


def detect_cadence(cursors: dict, now: datetime, due: list) -> None:
    """Elapsed cadence triggers.

    A quiet inbox is not an idle system: an elapsed cadence is a signal whether
    or not anything visibly moved.
    """
    cad = cursors.get("cadence", {})
    for name in calendar_za.CADENCES:
        last = cad.get(name)
        age = _age_seconds(last, now)
        window = calendar_za.CADENCE_SECONDS[name]
        if age is None:
            due.append({"cadence": name, "last": None, "overdue_by_s": None, "reason": "never run"})
        elif age >= window:
            due.append(
                {
                    "cadence": name,
                    "last": last,
                    "overdue_by_s": int(age - window),
                    "reason": "elapsed",
                }
            )


def detect_fiscal(today: date, changes: list) -> None:
    """SA fiscal anchors inside their lead window."""
    for a in calendar_za.due_anchors(today):
        changes.append({"kind": "obligation.due", "ref": f"calendar:{a['anchor']}", **a})


def detect_ledger_staleness(cursors: dict, now: datetime, changes: list) -> None:
    ledgers_dir = vault.path("ledgers")
    if not ledgers_dir.is_dir():
        return
    cursor_ledgers = cursors.get("ledgers", {})
    for f in sorted(ledgers_dir.glob("*.jsonl")):
        name = f.stem
        info = cursor_ledgers.get(name, {})
        threshold = int(info.get("freshness_days", _DEFAULT_FRESHNESS))
        age = _age_seconds(info.get("last_written"), now)
        if age is None:
            continue  # never written: absence is a gap, not staleness
        age_days = int(age // 86_400)
        if age_days > threshold:
            changes.append(
                {
                    "kind": "ledger.stale",
                    "ledger": name,
                    "age_days": age_days,
                    "threshold": threshold,
                }
            )


def detect_obligations(now: datetime, changes: list, errors: list) -> None:
    """Dated obligations from tax-deadlines.jsonl inside their lead time."""
    path = vault.path("ledgers", "tax-deadlines.jsonl")
    if not path.is_file():
        return
    today = now.date()
    try:
        for rec in atomic.read_jsonl(path):
            if rec.get("superseded_by") or rec.get("status") in {"submitted", "paid", "not_applicable"}:
                continue
            try:
                due_on = date.fromisoformat(rec["due_on"])
            except (KeyError, ValueError):
                continue
            days = (due_on - today).days
            if days <= int(rec.get("lead_days", 30)):
                changes.append(
                    {
                        "kind": "obligation.due",
                        "ref": rec.get("ref", rec.get("kind", "unknown")),
                        "due_on": rec["due_on"],
                        "days_until": days,
                        "overdue": days < 0,
                        "taxpayer": rec.get("taxpayer_ref"),
                    }
                )
    except ValueError as e:
        errors.append(f"tax-deadlines.jsonl unreadable: {e}")


def detect_rules(cursors: dict, today: date, changes: list) -> None:
    """Cached rulebooks past their refresh interval.

    A stale rule must be re-verified before it is relied on — every output that
    uses it states when it was last verified.
    """
    for name, info in cursors.get("rules", {}).items():
        verified = info.get("verified") or info.get("as_at")
        interval = str(info.get("refresh_interval", "P1Y"))
        if not verified:
            changes.append({"kind": "rule.expired", "rule": name, "reason": "never verified"})
            continue
        try:
            last = date.fromisoformat(verified)
        except ValueError:
            continue
        years = int(interval[1:-1]) if interval.endswith("Y") and interval[1:-1].isdigit() else 1
        days = int(interval[1:-1]) if interval.endswith("D") and interval[1:-1].isdigit() else years * 365
        age = (today - last).days
        if age > days:
            changes.append(
                {"kind": "rule.expired", "rule": name, "verified": verified, "age_days": age, "interval": interval}
            )


def detect_proposals(now: datetime, changes: list) -> None:
    """Unanswered artefacts in proposed/ — these are things waiting on the human."""
    root = vault.path("proposed")
    if not root.is_dir():
        return
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or f.name == "README.md":
            continue
        age_days = int((now.timestamp() - f.stat().st_mtime) // 86_400)
        kind = "proposal.pending"
        if f.parent.name == "issues":
            kind = "github.issue.needs_human"
        changes.append({"kind": kind, "path": vault.rel(f), "age_days": age_days})


def detect_agent_state(changes: list, errors: list) -> None:
    """Open questions and failed prior runs, from each agent's state file."""
    agents_dir = vault.path("state", "agents")
    if not agents_dir.is_dir():
        return
    for f in sorted(agents_dir.glob("*.json")):
        try:
            st = atomic.read_json(f, {}) or {}
        except json.JSONDecodeError as e:
            errors.append(f"{vault.rel(f)} unreadable: {e}")
            continue
        for q in st.get("pending_questions", []):
            changes.append(
                {
                    "kind": "question.open",
                    "agent": st.get("agent", f.stem),
                    "question": q.get("question", ""),
                    "asked_at": q.get("asked_at"),
                }
            )
        if st.get("health") == "blocked":
            changes.append({"kind": "gap.blocking", "agent": st.get("agent", f.stem)})


def detect_gaps(changes: list, errors: list) -> None:
    path = vault.path("state", "gaps.jsonl")
    if not path.is_file():
        return
    try:
        for rec in atomic.read_jsonl(path):
            if rec.get("closed_at"):
                continue
            if rec.get("blocking"):
                changes.append(
                    {
                        "kind": "gap.blocking",
                        "gap_id": rec.get("id"),
                        "detail": rec.get("detail", ""),
                        "domain": rec.get("domain"),
                    }
                )
    except ValueError as e:
        errors.append(f"gaps.jsonl unreadable: {e}")


def detect_failed_runs(changes: list, errors: list) -> None:
    """The last run, if it did not reach COMMIT.

    A run that dies leaves cursors unadvanced; this is how the work is retried
    rather than lost.
    """
    path = vault.path("state", "run-log.jsonl")
    if not path.is_file():
        return
    try:
        records = list(atomic.read_jsonl(path))
    except ValueError as e:
        errors.append(f"run-log.jsonl unreadable: {e}")
        return
    if records and records[-1].get("outcome") in {"failed", "partial"}:
        last = records[-1]
        changes.append(
            {
                "kind": "run.failed",
                "run_id": last.get("run_id"),
                "outcome": last.get("outcome"),
                "error": last.get("error"),
            }
        )


def detect_github(changes: list, errors: list) -> tuple[bool | None, int]:
    """Open system work from the local GitHub mirror.

    Reads the CACHE only — sense never touches the network.  Refreshing the
    mirror is gh_sync's job, and it degrades silently when offline so GitHub can
    never fail a heartbeat.  See docs/adr/0017-github-for-system-work.md.
    """
    path = vault.path("state", "system", "issues.jsonl")
    if not path.is_file():
        return None, 0
    try:
        records = list(atomic.read_jsonl(path))
    except ValueError as e:
        errors.append(f"issues.jsonl unreadable: {e}")
        return None, 0
    open_issues = [r for r in records if r.get("state") == "open" and not r.get("local_only")]
    for r in open_issues:
        labels = r.get("labels", [])
        kind = "github.issue.needs_human" if "needs:human" in labels else "github.issue.open"
        changes.append(
            {
                "kind": kind,
                "number": r.get("number"),
                "title": r.get("title", ""),
                "labels": labels,
                "url": r.get("url"),
            }
        )
    return True, len(open_issues)


# ── entry point ──────────────────────────────────────────────────────────────


def sense() -> dict:
    run = clock.Run.current()
    now = clock.utc_now()
    today = now.astimezone(clock.SAST).date()

    report: dict = {
        "schema": "sense/1",
        "run_id": run.id,
        "now": {"utc": clock.stamp(now), "local": run.local},
        "vault": vault.rel(vault.vault_root()),
        "changes": [],
        "due": [],
        "errors": [],
        "quiet": True,
    }

    if not vault.vault_root().is_dir():
        report["errors"].append("no vault — run /lifeos-init")
        report["quiet"] = False
        report["uninitialised"] = True
        return report

    if not vault.is_initialised():
        report["errors"].append("vault exists but has no profile/profile.yaml — run /lifeos-init")
        report["quiet"] = False
        report["uninitialised"] = True
        return report

    cursors = atomic.read_json(vault.path("state", "cursors.json"), {}) or {}
    changes, due, errors = report["changes"], report["due"], report["errors"]

    detect_inbox(cursors, changes, errors)
    detect_cadence(cursors, now, due)
    detect_fiscal(today, changes)
    detect_ledger_staleness(cursors, now, changes)
    detect_obligations(now, changes, errors)
    detect_rules(cursors, today, changes)
    detect_proposals(now, changes)
    detect_agent_state(changes, errors)
    detect_gaps(changes, errors)
    detect_failed_runs(changes, errors)
    reachable, open_count = detect_github(changes, errors)

    report["github"] = {"reachable": reachable, "open_issues": open_count}
    report["quiet"] = not (changes or due)
    report["counts"] = {"changes": len(changes), "due": len(due), "errors": len(errors)}
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.sense", description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="machine output (default)")
    ap.parse_args(argv)
    try:
        report = sense()
    except vault.VaultNotFound as e:
        report = {"schema": "sense/1", "quiet": False, "errors": [str(e)], "uninitialised": True}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
