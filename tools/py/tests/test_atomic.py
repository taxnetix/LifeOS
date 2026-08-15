"""Atomic writes: determinism, append safety, and loud failure on corruption."""

from __future__ import annotations

import pytest

from lifeos import atomic


def test_write_json_is_byte_identical_for_equal_data(tmp_path):
    """The idempotency test asserts 'no diff', not 'no meaningful diff' — which
    only works if equal data always serialises identically."""
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    data = {"z": 1, "a": {"n": [3, 2, 1]}, "m": "x"}
    atomic.write_json(a, data)
    atomic.write_json(b, dict(reversed(list(data.items()))))
    assert a.read_bytes() == b.read_bytes()


def test_write_json_replaces_atomically_leaving_no_temp_files(tmp_path):
    target = tmp_path / "state.json"
    atomic.write_json(target, {"v": 1})
    atomic.write_json(target, {"v": 2})
    assert atomic.read_json(target) == {"v": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_read_json_returns_default_when_absent(tmp_path):
    assert atomic.read_json(tmp_path / "nope.json", {"d": True}) == {"d": True}


def test_append_jsonl_preserves_order_and_creates_parents(tmp_path):
    target = tmp_path / "deep" / "ledger.jsonl"
    for i in range(50):
        atomic.append_jsonl(target, {"i": i})
    records = list(atomic.read_jsonl(target))
    assert [r["i"] for r in records] == list(range(50))


def test_append_jsonl_handles_records_larger_than_one_write(tmp_path):
    """Large records take the temp-and-rename path; content must survive intact."""
    target = tmp_path / "big.jsonl"
    atomic.append_jsonl(target, {"small": 1})
    atomic.append_jsonl(target, {"blob": "x" * 20_000})
    atomic.append_jsonl(target, {"small": 2})
    records = list(atomic.read_jsonl(target))
    assert len(records) == 3
    assert len(records[1]["blob"]) == 20_000
    assert records[2] == {"small": 2}


def test_append_jsonl_never_emits_embedded_newlines(tmp_path):
    """A newline inside a record would silently split it into two on read."""
    target = tmp_path / "l.jsonl"
    atomic.append_jsonl(target, {"text": "line one\nline two\r\nthree"})
    assert len(target.read_text().strip().splitlines()) == 1
    assert list(atomic.read_jsonl(target))[0]["text"] == "line one\nline two\r\nthree"


def test_read_jsonl_skips_blank_lines(tmp_path):
    target = tmp_path / "l.jsonl"
    target.write_text('{"a":1}\n\n  \n{"a":2}\n')
    assert [r["a"] for r in atomic.read_jsonl(target)] == [1, 2]


def test_read_jsonl_raises_on_corruption_rather_than_skipping(tmp_path):
    """A corrupt ledger must fail loudly. Silently reading 9 of 10 records is
    how a wrong number reaches a report."""
    target = tmp_path / "l.jsonl"
    target.write_text('{"a":1}\nNOT JSON\n{"a":2}\n')
    with pytest.raises(ValueError, match="line 2|:2"):
        list(atomic.read_jsonl(target))


def test_read_jsonl_on_missing_file_yields_nothing(tmp_path):
    assert list(atomic.read_jsonl(tmp_path / "absent.jsonl")) == []


def test_unicode_survives_round_trip(tmp_path):
    target = tmp_path / "u.jsonl"
    atomic.append_jsonl(target, {"name": "Arné", "note": "Môre — R1 234,56"})
    assert list(atomic.read_jsonl(target))[0]["name"] == "Arné"
