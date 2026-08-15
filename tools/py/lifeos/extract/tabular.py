"""CSV and TSV extraction.

Delimiter and encoding are sniffed rather than assumed: SA bank exports arrive
as comma, semicolon or tab separated, sometimes with a UTF-8 BOM, sometimes in
cp1252 with a stray Rand sign. Guessing wrong yields one giant column that
looks plausible and parses to nothing.
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import Block, Extraction, Table

_CONF = 0.99
_MAX_ROWS = 100_000
_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def _read_text(path: Path) -> tuple[str, str]:
    last: Exception | None = None
    for enc in _ENCODINGS:
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError as e:
            last = e
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"no encoding matched: {last}")


def _sniff(sample: str, suffix: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return "\t" if suffix == ".tsv" else ","


def extract_tabular(path: Path, doc_hash: str) -> Extraction:
    text, encoding = _read_text(path)
    delimiter = _sniff(text[:8192], path.suffix.lower())

    out = Extraction(
        doc_hash=doc_hash,
        method=f"csv[{ {',': 'comma', ';': 'semicolon', chr(9): 'tab', '|': 'pipe'}.get(delimiter, delimiter) }]",
        pages=1,
        meta={"encoding": encoding, "delimiter": delimiter},
    )

    rows: list[list[str]] = []
    for n, row in enumerate(csv.reader(text.splitlines(), delimiter=delimiter), 1):
        if n > _MAX_ROWS:
            out.errors.append(f"truncated at {_MAX_ROWS} rows")
            break
        cleaned = [c.strip() for c in row]
        if not any(cleaned):
            continue
        rows.append(cleaned)
        out.blocks.append(
            Block(locator=f"row={n}", text=delimiter.join(cleaned), confidence=_CONF)
        )

    if rows:
        out.tables.append(Table(locator="table=1", rows=rows, confidence=_CONF))
        widths = {len(r) for r in rows}
        if len(widths) > 1:
            out.errors.append(
                f"ragged rows: column counts {sorted(widths)} — the delimiter may be wrong, "
                "or the file may have a preamble before the header"
            )
    else:
        out.errors.append("file contains no rows")
    return out
