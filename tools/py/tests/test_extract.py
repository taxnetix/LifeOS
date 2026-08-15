"""Extraction: provenance granularity, confidence honesty, graceful failure."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from lifeos import extract

FIXTURES = Path(__file__).resolve().parents[3] / "vault.example" / "inbox"
pytestmark = pytest.mark.skipif(not FIXTURES.is_dir(), reason="fixtures not generated")


def _fx(name: str) -> Path:
    p = FIXTURES / name
    if not p.is_file():
        pytest.skip(f"missing fixture {name}")
    return p


def test_unsupported_type_reports_rather_than_raising(tmp_path):
    """Silence is the one outcome that is never acceptable."""
    f = tmp_path / "thing.xyz"
    f.write_bytes(b"data")
    r = extract.extract(f)
    assert r.errors and not r.blocks
    assert "unsupported" in r.errors[0]


def test_hash_is_content_addressed_not_name_addressed(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("identical")
    b.write_text("identical")
    assert extract.sha256_file(a) == extract.sha256_file(b)


def test_pdf_blocks_are_line_level_so_a_row_is_locatable():
    """A locator of 'page=1' cannot answer 'where did this figure come from?'."""
    r = extract.extract(_fx("northbank-cheque-2026-07.pdf"))
    assert not r.errors
    assert len(r.blocks) > 10, "one block per page defeats provenance"
    netflix = [b for b in r.blocks if "NETFLIX" in b.text]
    assert len(netflix) == 1
    assert netflix[0].locator.startswith("page=1;line=")
    assert "199.00" in netflix[0].text


def test_pdf_locators_are_unique_and_stable_across_runs():
    f = _fx("northbank-cheque-2026-07.pdf")
    a, b = extract.extract(f), extract.extract(f)
    locs = [x.locator for x in a.blocks]
    assert len(locs) == len(set(locs)), "duplicate locators would collide record ids"
    assert locs == [x.locator for x in b.blocks]
    assert [x.text for x in a.blocks] == [x.text for x in b.blocks]


def test_text_layer_confidence_is_high():
    r = extract.extract(_fx("northbank-cheque-2026-07.pdf"))
    assert min(b.confidence for b in r.blocks) >= 0.95
    assert r.ocr is False


def test_ocr_confidence_is_lower_than_a_text_layer():
    """A scan and a text layer must not look equally trustworthy."""
    scan = extract.extract(_fx("deed-of-grave-scan.png"))
    digital = extract.extract(_fx("northbank-cheque-2026-07.pdf"))
    assert scan.ocr is True
    assert scan.blocks, "OCR produced nothing"
    assert max(b.confidence for b in scan.blocks) < min(b.confidence for b in digital.blocks)
    assert "FERNWOOD" in scan.text.upper() or "CEMETERY" in scan.text.upper()


def test_csv_delimiter_is_sniffed_not_assumed(tmp_path):
    """Guessing comma on a semicolon file yields one column that parses to nothing."""
    f = tmp_path / "semi.csv"
    with f.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Date", "Description", "Amount"])
        w.writerow(["2026-07-01", "TEST", "-100.00"])
    r = extract.extract(f)
    assert r.meta["delimiter"] == ";"
    assert r.tables[0].rows[0] == ["Date", "Description", "Amount"]


def test_csv_ragged_rows_are_flagged(tmp_path):
    f = tmp_path / "ragged.csv"
    f.write_text("a,b,c\n1,2,3\n4,5\n6,7,8\n9,10\n11,12\n")
    r = extract.extract(f)
    assert any("ragged" in e for e in r.errors)


def test_csv_survives_non_utf8_encoding(tmp_path):
    f = tmp_path / "cp1252.csv"
    f.write_bytes("Date,Description,Amount\n2026-07-01,CAFÉ MÔRE,-50.00\n".encode("cp1252"))
    r = extract.extract(f)
    assert not [e for e in r.errors if "decode" in e]
    assert "CAF" in r.text


def test_xlsx_locators_are_real_cell_references():
    r = extract.extract(_fx("meridian-holdings-jul-2026.xlsx"))
    assert not r.errors
    assert any(b.locator.startswith("sheet=Holdings;cell=A1") for b in r.blocks)
    assert r.pages == 2, "one 'page' per sheet"


def test_docx_paragraph_numbering_skips_blanks():
    r = extract.extract(_fx("will-a-sample-2023.docx"))
    assert not r.errors
    nums = [int(b.locator.split("para=")[1].split(";")[0]) for b in r.blocks]
    assert nums == list(range(1, len(nums) + 1)), "numbering must be dense and stable"
    assert "REVOKE" in r.text.upper()


def test_docx_table_is_extracted_with_high_confidence():
    r = extract.extract(_fx("will-a-sample-2023.docx"))
    assert r.tables and r.tables[0].confidence >= 0.95


def test_incoherent_inferred_tables_are_dropped():
    """A whitespace-shredded grid is confidently wrong, and would carry a
    confidence above the default write floor straight into a ledger."""
    r = extract.extract(_fx("northbank-cheque-2026-07.pdf"))
    for t in r.tables:
        counts = [sum(1 for c in row if c) for row in t.rows]
        modal = max(set(counts), key=counts.count)
        assert counts.count(modal) / len(counts) >= 0.7


def test_every_block_carries_a_locator_and_confidence():
    for name in ("northbank-cheque-2026-07.pdf", "will-a-sample-2023.docx",
                 "meridian-holdings-jul-2026.xlsx", "capital-card-jul-2026.csv"):
        r = extract.extract(_fx(name))
        for b in r.blocks:
            assert b.locator and "=" in b.locator, f"{name}: bad locator {b.locator!r}"
            assert 0.0 <= b.confidence <= 1.0
