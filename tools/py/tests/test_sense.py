"""SENSE — the cheap idle path, and each detector.

The two properties that matter most:
  1. quiet means genuinely quiet (cheap hourly running is affordable)
  2. two consecutive runs on unchanged input are identical (idempotency)
"""

from __future__ import annotations

import importlib
import json
from datetime import date

import pytest

from lifeos import atomic, calendar_za


@pytest.fixture
def sense_mod(vault_dir, frozen_clock):
    from lifeos import sense
    importlib.reload(sense)
    return sense


def _quiet_cursors(vault_dir, now="2026-08-15T08:59:00Z"):
    """Cursors with every cadence just run, so only real change shows up."""
    atomic.write_json(
        vault_dir / "state" / "cursors.json",
        {
            "schema": "cursors/1",
            "inbox": {},
            "cadence": {c: now for c in calendar_za.CADENCES},
            "ledgers": {},
            "rules": {},
            "github": {},
        },
    )


def test_uninitialised_vault_is_reported_not_crashed(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEOS_VAULT", str(tmp_path / "nothing"))
    from lifeos import sense, vault
    importlib.reload(vault)
    importlib.reload(sense)
    r = sense.sense()
    assert r["uninitialised"] is True and r["quiet"] is False


def test_fresh_vault_reports_every_cadence_as_never_run(sense_mod):
    """'Nothing obviously changed' must not mean 'nothing to do' — an elapsed
    cadence is a signal in its own right."""
    r = sense_mod.sense()
    assert {d["cadence"] for d in r["due"]} == set(calendar_za.CADENCES)
    assert all(d["reason"] == "never run" for d in r["due"])


def test_quiet_when_cadences_current_and_nothing_changed(vault_dir, sense_mod, monkeypatch):
    _quiet_cursors(vault_dir)
    # Freeze to a date outside every fiscal lead window.
    monkeypatch.setenv("LIFEOS_NOW", "2026-05-20T09:00:00Z")
    from lifeos import clock
    importlib.reload(clock)
    importlib.reload(sense_mod)
    r = sense_mod.sense()
    assert r["quiet"] is True, f"expected quiet, got {r['changes']} / {r['due']}"
    assert r["counts"] == {"changes": 0, "due": 0, "errors": 0}


def test_two_consecutive_runs_are_identical(vault_dir, sense_mod):
    """Idempotency, mechanically: same input, same report."""
    _quiet_cursors(vault_dir)
    a, b = sense_mod.sense(), sense_mod.sense()
    for r in (a, b):
        r.pop("run_id"), r.pop("now")
    assert a == b


def test_new_inbox_file_is_detected_with_its_hash(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    (vault_dir / "inbox" / "absa-jul-2026.pdf").write_bytes(b"%PDF-1.4 fake")
    r = sense_mod.sense()
    hits = [c for c in r["changes"] if c["kind"] == "inbox.new"]
    assert len(hits) == 1
    assert hits[0]["path"] == "$VAULT/inbox/absa-jul-2026.pdf"
    assert hits[0]["sha256"].startswith("sha256:")
    assert r["quiet"] is False


def test_already_filed_document_is_not_detected_again(vault_dir, sense_mod):
    """Re-processing a filed document must be a no-op — this is what stops the
    system redoing work it has already done."""
    _quiet_cursors(vault_dir)
    f = vault_dir / "inbox" / "stmt.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    digest = sense_mod._sha256(f)
    atomic.append_jsonl(
        vault_dir / "documents" / "index.jsonl",
        {"doc_hash": digest, "filed_path": "documents/2026/finance/x-stmt.pdf"},
    )
    r = sense_mod.sense()
    assert [c for c in r["changes"] if c["kind"] == "inbox.new"] == []


def test_inbox_ignores_readme_and_dotfiles(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    (vault_dir / "inbox" / ".DS_Store").write_bytes(b"junk")
    r = sense_mod.sense()
    assert [c for c in r["changes"] if c["kind"].startswith("inbox")] == []


def test_pending_proposal_surfaces_as_needing_the_human(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    (vault_dir / "proposed" / "cancel-gym.md").write_text("# Proposal")
    r = sense_mod.sense()
    assert any(c["kind"] == "proposal.pending" for c in r["changes"])


def test_issue_draft_surfaces_as_github_needs_human(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    (vault_dir / "proposed" / "issues" / "absa-layout.md").write_text("Title: x")
    r = sense_mod.sense()
    assert any(c["kind"] == "github.issue.needs_human" for c in r["changes"])


def test_overdue_obligation_is_flagged_as_overdue(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    atomic.append_jsonl(
        vault_dir / "ledgers" / "tax-deadlines.jsonl",
        {"ref": "irp6-1", "kind": "irp6_1", "due_on": "2026-08-01",
         "lead_days": 30, "status": "upcoming"},
    )
    r = sense_mod.sense()
    hit = next(c for c in r["changes"] if c.get("ref") == "irp6-1")
    assert hit["overdue"] is True and hit["days_until"] < 0


def test_submitted_obligation_is_not_flagged(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    atomic.append_jsonl(
        vault_dir / "ledgers" / "tax-deadlines.jsonl",
        {"ref": "done", "kind": "irp6_1", "due_on": "2026-08-20",
         "lead_days": 30, "status": "submitted"},
    )
    r = sense_mod.sense()
    assert not any(c.get("ref") == "done" for c in r["changes"])


def test_failed_prior_run_is_detected(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    atomic.append_jsonl(
        vault_dir / "state" / "run-log.jsonl",
        {"run_id": "run_x", "outcome": "failed", "error": "boom", "quiet": False},
    )
    r = sense_mod.sense()
    assert any(c["kind"] == "run.failed" for c in r["changes"])


def test_blocking_gap_is_detected_and_closed_gaps_are_not(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    gaps = vault_dir / "state" / "gaps.jsonl"
    atomic.append_jsonl(gaps, {"id": "sha256:a", "kind": "document.missing",
                               "detail": "no will", "blocking": True})
    atomic.append_jsonl(gaps, {"id": "sha256:b", "kind": "document.missing",
                               "detail": "resolved", "blocking": True,
                               "closed_at": "2026-08-01T00:00:00Z"})
    hits = [c for c in sense_mod.sense()["changes"] if c["kind"] == "gap.blocking"]
    assert len(hits) == 1 and hits[0]["gap_id"] == "sha256:a"


def test_open_question_surfaces(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    atomic.write_json(
        vault_dir / "state" / "agents" / "finance.json",
        {"schema": "agent-state/1", "agent": "finance", "health": "healthy",
         "pending_questions": [{"question": "Is JHB PROPS the Sandton rental?",
                                "asked_run": "r", "asked_at": "2026-08-14T00:00:00Z"}]},
    )
    r = sense_mod.sense()
    assert any(c["kind"] == "question.open" for c in r["changes"])


def test_stale_ledger_is_detected_but_never_written_one_is_not(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    (vault_dir / "ledgers" / "holdings.jsonl").write_text("")
    (vault_dir / "ledgers" / "policies.jsonl").write_text("")
    cur = atomic.read_json(vault_dir / "state" / "cursors.json")
    cur["ledgers"] = {"holdings": {"last_written": "2026-01-01T00:00:00Z", "freshness_days": 90}}
    atomic.write_json(vault_dir / "state" / "cursors.json", cur)
    kinds = [(c["kind"], c.get("ledger")) for c in sense_mod.sense()["changes"]]
    assert ("ledger.stale", "holdings") in kinds
    assert ("ledger.stale", "policies") not in kinds  # absence is a gap, not staleness


def test_expired_rulebook_is_detected(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    cur = atomic.read_json(vault_dir / "state" / "cursors.json")
    cur["rules"] = {"za/sars-tables": {"as_at": "2024-03-01", "verified": "2024-03-01",
                                       "refresh_interval": "P1Y"}}
    atomic.write_json(vault_dir / "state" / "cursors.json", cur)
    assert any(c["kind"] == "rule.expired" for c in sense_mod.sense()["changes"])


def test_corrupt_ledger_is_reported_not_swallowed(vault_dir, sense_mod):
    _quiet_cursors(vault_dir)
    (vault_dir / "ledgers" / "tax-deadlines.jsonl").write_text("{ broken\n")
    r = sense_mod.sense()
    assert r["errors"] and r["quiet"] is False


def test_sense_never_raises_and_always_exits_zero(vault_dir, sense_mod, capsys):
    assert sense_mod.main([]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "sense/1"


# ── fiscal calendar ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "d,expected",
    [(date(2026, 3, 1), 2027), (date(2027, 2, 28), 2027), (date(2026, 2, 28), 2026)],
)
def test_sa_tax_year_runs_march_to_february(d, expected):
    assert calendar_za.tax_year_of(d) == expected


def test_tax_year_end_handles_leap_years():
    assert calendar_za.tax_year_end(2028) == date(2028, 2, 29)
    assert calendar_za.tax_year_end(2026) == date(2026, 2, 28)


def test_irp6_period_1_appears_inside_its_lead_window():
    """31 August, 30-day lead: visible from 1 August, absent in June."""
    assert any(a["anchor"] == "irp6_1" for a in calendar_za.due_anchors(date(2026, 8, 15)))
    assert not any(a["anchor"] == "irp6_1" for a in calendar_za.due_anchors(date(2026, 6, 15)))


def test_due_anchors_sorted_most_urgent_first():
    anchors = calendar_za.due_anchors(date(2026, 8, 15))
    assert anchors == sorted(anchors, key=lambda a: a["days_until"])
