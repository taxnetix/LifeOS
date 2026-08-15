#!/usr/bin/env python3
"""PreToolUse guard — blocks personal data leaving the machine, and blocks
mutation of immutable originals.

Instructing agents not to leak is not a control; it is a hope with good
intentions.  This is the control.  See docs/adr/0015-redaction-enforced-by-hook.md.

Egress is defined broadly and deliberately:
    WebFetch / WebSearch          obvious
    Bash: gh ...                  an issue body is publication
    Bash: curl/wget/nc/ssh/scp/rsync   direct network egress

The matcher is derived from LIVE profile data, not a static list — a static
regex set would miss the names that matter most, which are this person's own.

Blocking is the default on ambiguity: a borderline match blocks and explains,
because a rewritten query costs seconds and a leak cannot be undone.

Contract: reads a JSON event on stdin, writes a JSON decision on stdout, exit 0.
Never raises — a crashing guard must fail CLOSED, not open.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

EGRESS_TOOLS = {"WebFetch", "WebSearch"}
EGRESS_BASH = re.compile(r"\b(gh|curl|wget|nc|ncat|ssh|scp|rsync|http|httpie)\b")

# gh subcommands that only read. Everything else on gh is treated as publication.
GH_READONLY = re.compile(
    r"^\s*gh\s+(issue|pr|run|repo|api|search|release|workflow|label|auth)\s+"
    r"(list|view|status|checks|diff|download|ls)\b"
)

# Structural patterns — always checked, profile or no profile.
STRUCTURAL: list[tuple[str, re.Pattern]] = [
    ("sa_id_number", re.compile(r"\b\d{6}[0-5]\d{3}[01]\d{2}\b")),
    ("account_number", re.compile(r"\b\d{9,16}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("credential_like", re.compile(
        r"[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\s*[:=]|"
        r"[Aa][Pp][Ii][_-]?[Kk][Ee][Yy]\s*[:=]|"
        r"BEGIN [A-Z ]*PRIVATE KEY|"
        r"\bgh[pousr]_[A-Za-z0-9]{20,}"
    )),
]

# Words that are names in a profile but also ordinary English; never block alone.
_STOPWORDS = {
    "the", "and", "van", "der", "de", "du", "le", "la", "trust", "holdings",
    "group", "limited", "ltd", "pty", "inc", "cc", "family", "self", "main",
}


def vault_root() -> Path:
    env = os.environ.get("LIFEOS_VAULT", "").strip()
    return Path(env).expanduser() if env else REPO / "vault"


def profile_terms() -> list[tuple[str, str]]:
    """Proper names and identifiers from the live profile.

    Read as text, not parsed as YAML: this must work even when the profile is
    mid-edit and syntactically broken, because failing open is not an option.
    """
    terms: list[tuple[str, str]] = []
    p = vault_root() / "profile" / "profile.yaml"
    if not p.is_file():
        return terms
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return terms

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip("\"'")
        key = key.strip("- ").lower()
        if not value or value in {"[]", "{}", "true", "false"}:
            continue
        if any(k in key for k in ("name", "full_name", "legal_name", "trading_name")):
            for word in re.split(r"\s+", value):
                if len(word) > 3 and word.lower() not in _STOPWORDS:
                    terms.append(("profile_name", word))
        elif any(k in key for k in ("id_number", "tax_ref", "vat_no", "registration_no",
                                    "account_no", "policy_no", "member_no", "mt_number")):
            if len(value) > 4:
                terms.append(("account_number", value))
        elif "address" in key or key in {"line1", "street"}:
            if len(value) > 6:
                terms.append(("physical_address", value))
    return terms


def payload_of(tool: str, tin: dict) -> str:
    if tool in EGRESS_TOOLS:
        return " ".join(str(v) for v in tin.values())
    if tool == "Bash":
        return str(tin.get("command", ""))
    return ""


def scan(text: str) -> list[str]:
    """Return matched pattern CLASSES. Never the matched values — a redaction
    log containing the redacted values would be self-defeating."""
    hits: list[str] = []
    for name, rx in STRUCTURAL:
        if rx.search(text):
            hits.append(name)
    low = text.lower()
    for cls, term in profile_terms():
        if term.lower() in low:
            hits.append(cls)
    return sorted(set(hits))


def audit(event: str, **fields) -> None:
    try:
        path = vault_root() / "state" / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"at": _now(), "event": event, **fields}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    except Exception:
        pass  # auditing must never break the guard


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def check_document_write(tool: str, tin: dict) -> dict | None:
    """documents/ originals are immutable — never modified, never overwritten."""
    if tool not in {"Write", "Edit", "NotebookEdit", "MultiEdit"}:
        return None
    target = str(tin.get("file_path") or tin.get("notebook_path") or "")
    if not target:
        return None
    try:
        resolved = Path(target).resolve()
        docs = (vault_root() / "documents").resolve()
        resolved.relative_to(docs)
    except (ValueError, OSError):
        return None
    if Path(target).name in {"index.jsonl", "README.md"}:
        return None
    audit("vault.write", tool=tool, path="documents/<blocked>", blocked=True)
    return deny(
        "BLOCKED: $VAULT/documents/ holds immutable originals. Every figure in "
        "every report traces back to these files, so they are never modified, "
        "overwritten or deleted. Write a corrected record to the ledger instead "
        "(ledger.supersede), or file a new document through /ingest."
    )


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        print(json.dumps({}))
        return 0

    tool = event.get("tool_name", "")
    tin = event.get("tool_input", {}) or {}

    blocked = check_document_write(tool, tin)
    if blocked:
        print(json.dumps(blocked))
        return 0

    payload = payload_of(tool, tin)
    if not payload:
        print(json.dumps({}))
        return 0

    channel = tool
    if tool == "Bash":
        if not EGRESS_BASH.search(payload):
            print(json.dumps({}))
            return 0
        if GH_READONLY.match(payload):
            print(json.dumps({}))   # reads are free; nothing leaves
            return 0
        channel = "gh" if payload.lstrip().startswith("gh") else "other"

    hits = scan(payload)
    if hits:
        audit("egress.blocked", channel=channel, pattern_class=hits[0], all_classes=hits)
        print(json.dumps(deny(
            f"BLOCKED: this {channel} call matched personal-data patterns "
            f"({', '.join(hits)}). Nothing personal leaves this machine — "
            "public reference lookups only.\n\n"
            "Rewrite it generically. 'Discovery Classic Comprehensive 2026 benefits' "
            "answers what 'member 12345678 plan details' was reaching for.\n\n"
            "If this is a GitHub issue: an issue may describe a CLASS of problem "
            "('ABSA changed its statement column order'), never an INSTANCE of "
            "this person's data. Abstract it, then try again."
        )))
        return 0

    audit("egress.allowed", channel=channel)
    print(json.dumps({}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # fail CLOSED
        print(json.dumps(deny(f"pii-guard failed ({e}); denying by default.")))
        sys.exit(0)
