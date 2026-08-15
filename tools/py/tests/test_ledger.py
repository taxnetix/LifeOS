"""Ledger identity, validation and the confidence gate.

These three behaviours together are what make a re-run safe:
  - the same document yields the same ids, so writes are no-ops
  - an invalid record never enters a ledger
  - an uncertain record never enters a ledger
"""

from __future__ import annotations

import importlib

import pytest

from lifeos import atomic


@pytest.fixture
def led(vault_dir, frozen_clock):
    from lifeos import ledger
    importlib.reload(ledger)
    return ledger


def _person(ref="per_test", *, conf=0.99, locator="page=1;row=1"):
    from lifeos import ledger
    rid = ledger.record_id("sha256:" + "a" * 64, locator, ref)
    return {
        "id": rid,
        "schema": "people/1",
        "subject_id": ref,
        "source": {
            "doc_hash": "sha256:" + "a" * 64,
            "locator": locator,
            "method": "parser:test/1",
            "confidence": conf,
            "extracted_at": "2026-08-15T09:00:00Z",
        },
        "valid_from": "2026-08-15",
        "valid_to": None,
        "superseded_by": None,
        "ref": ref,
        "full_name": "Test Person",
        "relation": "self",
    }


def test_record_id_is_deterministic_across_calls(led):
    a = led.record_id("sha256:" + "b" * 64, "page=3;row=17", "acc_1|2026-07-01|-12500")
    b = led.record_id("sha256:" + "b" * 64, "page=3;row=17", "acc_1|2026-07-01|-12500")
    assert a == b and a.startswith("sha256:")


def test_record_id_changes_when_any_component_changes(led):
    base = ("sha256:" + "b" * 64, "page=3", "key")
    assert led.record_id(*base) != led.record_id("sha256:" + "c" * 64, "page=3", "key")
    assert led.record_id(*base) != led.record_id(base[0], "page=4", "key")
    assert led.record_id(*base) != led.record_id(base[0], base[1], "other")


def test_reingesting_the_same_records_writes_nothing(led):
    """The mechanism that prevents redone work."""
    recs = [_person("per_a"), _person("per_b", locator="page=1;row=2")]
    first = led.write("people", recs, agent="identity")
    assert (first["written"], first["unchanged"]) == (2, 0)

    second = led.write("people", recs, agent="identity")
    assert (second["written"], second["unchanged"]) == (0, 2)
    assert sum(1 for _ in atomic.read_jsonl(led.ledger_path("people"))) == 2


def test_invalid_record_is_rejected_and_parked_not_written(led, vault_dir):
    bad = _person()
    del bad["full_name"]                       # required
    r = led.write("people", [bad], agent="identity")
    assert r["written"] == 0 and r["rejected"] == 1
    assert not led.ledger_path("people").exists()
    parked = list((vault_dir / "proposed" / "rejected").glob("people-*.jsonl"))
    assert parked, "a rejected record must land somewhere visible, never vanish"


def test_float_cents_is_rejected(led):
    """Money is integer minor units. A float must not reach a ledger."""
    from lifeos import ledger
    rec = {
        "id": ledger.record_id("human", "l", "k"),
        "schema": "valuations/1",
        "subject_id": "per_test",
        "source": {"doc_hash": "human", "locator": "l", "method": "human",
                   "confidence": 1.0, "extracted_at": "2026-08-15T09:00:00Z"},
        "valid_from": "2026-08-15", "valid_to": None, "superseded_by": None,
        "asset_ref": "ast_house", "as_at": "2026-08-15",
        "value": {"cents": 1234.56, "currency": "ZAR"},
        "basis": "market",
    }
    assert led.write("valuations", [rec], agent="assets")["rejected"] == 1


def test_missing_currency_is_rejected(led):
    from lifeos import ledger
    rec = {
        "id": ledger.record_id("human", "l", "k2"),
        "schema": "valuations/1",
        "subject_id": "per_test",
        "source": {"doc_hash": "human", "locator": "l", "method": "human",
                   "confidence": 1.0, "extracted_at": "2026-08-15T09:00:00Z"},
        "valid_from": "2026-08-15", "valid_to": None, "superseded_by": None,
        "asset_ref": "ast_house", "as_at": "2026-08-15",
        "value": {"cents": 100000},
        "basis": "market",
    }
    assert led.write("valuations", [rec], agent="assets")["rejected"] == 1


def test_low_confidence_record_is_parked_not_written(led, vault_dir):
    """An uncertain extraction becomes a question, never a silent number."""
    r = led.write("people", [_person(conf=0.10)], agent="identity")
    assert r["written"] == 0 and r["low_confidence"] == 1
    assert list((vault_dir / "proposed" / "low-confidence").glob("people-*.jsonl"))


def test_transactions_have_a_stricter_floor_than_the_default(led):
    assert led.confidence_floor("transactions") == 0.90
    assert led.confidence_floor("household") == led.CONFIDENCE_FLOOR["_default"]


def test_dry_run_writes_nothing(led):
    r = led.write("people", [_person()], agent="identity", dry_run=True)
    assert r["written"] == 1
    assert not led.ledger_path("people").exists()


def test_meta_is_stamped_on_write(led, frozen_clock):
    led.write("people", [_person()], agent="identity")
    rec = next(iter(atomic.read_jsonl(led.ledger_path("people"))))
    assert rec["_meta"]["agent"] == "identity"
    assert rec["_meta"]["run_id"] == "run_test_0001"
    assert rec["_meta"]["written_at"] == "2026-08-15T09:00:00Z"


def test_supersede_appends_a_tombstone_and_keeps_history(led):
    old = _person("per_a")
    led.write("people", [old], agent="identity")
    new = _person("per_a", locator="page=2;row=9")
    new["full_name"] = "Corrected Name"
    led.supersede("people", old["id"], new, agent="identity")

    all_records = list(atomic.read_jsonl(led.ledger_path("people")))
    assert len(all_records) == 3, "original + replacement + tombstone"
    live = list(led.read("people"))
    assert [r["full_name"] for r in live] == ["Test Person", "Corrected Name"]
    assert any(r.get("superseded_by") == new["id"] for r in all_records)


def test_unknown_ledger_raises_rather_than_writing_anywhere(led):
    with pytest.raises(KeyError, match="no schema for ledger"):
        led.validate("not-a-ledger", {})


def test_every_ledger_schema_loads(led):
    """Guards against a schema that exists but cannot compile — /audit and the
    write path both depend on every one of these resolving."""
    names = [p.stem.replace(".schema", "")
             for p in (led.SCHEMA_DIR / "ledgers").glob("*.json")]
    assert len(names) >= 30
    for n in names:
        if n == "documents-index":
            continue  # not envelope-based; validated by the librarian's own path
        assert led.validator_for(n) is not None
