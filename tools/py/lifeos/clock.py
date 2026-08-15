"""A stable clock and run identity.

Every run stamps a `run_id` and both UTC and SAST timestamps.  Agents never call
datetime.now() directly — a single clock makes runs reproducible in tests and
keeps journal entries, audit lines and cursors mutually consistent.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

SAST = timezone(timedelta(hours=2), "SAST")


def utc_now() -> datetime:
    """Current UTC instant.

    $LIFEOS_NOW (RFC 3339) overrides it, so golden-file tests are deterministic.
    """
    override = os.environ.get("LIFEOS_NOW", "").strip()
    if override:
        return datetime.fromisoformat(override.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.now(UTC)


def stamp(dt: datetime | None = None) -> str:
    """RFC 3339 in UTC with a trailing Z — the only instant format we write."""
    dt = dt or utc_now()
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    """Today's calendar date in SAST. Local time is what a human means by 'today'."""
    return utc_now().astimezone(SAST).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class Run:
    """Identity of a single heartbeat or command run."""

    id: str
    started_at: str
    local: str

    @classmethod
    def new(cls) -> Run:
        now = utc_now()
        suffix = secrets.token_hex(2)
        return cls(
            id=f"run_{now.strftime('%Y%m%dT%H%MZ')}_{suffix}",
            started_at=stamp(now),
            local=now.astimezone(SAST).isoformat(timespec="seconds"),
        )

    @classmethod
    def current(cls) -> Run:
        """Reuse $LIFEOS_RUN_ID when a wrapper set one, so every tool invoked
        during one heartbeat stamps the same run."""
        existing = os.environ.get("LIFEOS_RUN_ID", "").strip()
        if existing:
            now = utc_now()
            return cls(id=existing, started_at=stamp(now), local=now.astimezone(SAST).isoformat(timespec="seconds"))
        return cls.new()
