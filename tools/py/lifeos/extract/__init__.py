"""EXTRACT — documents to structured content, with provenance on every block.

The contract every extractor returns (see Extraction.to_dict):

    { "doc_hash", "method", "pages", "ocr", "text",
      "blocks": [ {"locator", "text", "confidence"} ],
      "tables": [ {"locator", "rows", "confidence"} ],
      "meta": {...},
      "errors": [...] }

`locator` is the exact position inside the original — "page=3;para=7",
"sheet=Summary;cell=B14", "row=17" — because the question that matters later is
never "which document said this?" but "where in it?".  Record identity is
derived from doc_hash + locator, so a locator that is not stable would break
idempotency.

`confidence` is per block, not per document: a clean text layer and a smudged
scan can live in the same PDF, and a record built from the second must not
inherit the credibility of the first.

See docs/adr/0014-provenance-and-confidence.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".csv": "tabular",
    ".tsv": "tabular",
    ".txt": "text",
    ".md": "text",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".heic": "image",
}


@dataclass
class Block:
    locator: str
    text: str
    confidence: float


@dataclass
class Table:
    locator: str
    rows: list[list[str]]
    confidence: float


@dataclass
class Extraction:
    doc_hash: str
    method: str
    pages: int = 1
    ocr: bool = False
    blocks: list[Block] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    def to_dict(self) -> dict:
        return {
            "schema": "extraction/1",
            "doc_hash": self.doc_hash,
            "method": self.method,
            "pages": self.pages,
            "ocr": self.ocr,
            "text": self.text,
            "blocks": [b.__dict__ for b in self.blocks],
            "tables": [t.__dict__ for t in self.tables],
            "meta": self.meta,
            "errors": self.errors,
        }


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def kind_of(p: Path) -> str | None:
    return SUPPORTED.get(p.suffix.lower())


def extract(path: Path, *, force_ocr: bool = False) -> Extraction:
    """Dispatch to the right extractor.

    An unsupported or unreadable file is NEVER silently skipped: it returns an
    Extraction carrying the error, so the caller can open a gap record. Silence
    is the one outcome that is never acceptable.
    """
    path = Path(path)
    doc_hash = sha256_file(path)
    kind = kind_of(path)

    if kind is None:
        return Extraction(
            doc_hash=doc_hash,
            method="none",
            errors=[f"unsupported file type '{path.suffix}' — no extractor"],
        )

    try:
        if kind == "pdf":
            from .pdf import extract_pdf
            return extract_pdf(path, doc_hash, force_ocr=force_ocr)
        if kind == "docx":
            from .docx_ import extract_docx
            return extract_docx(path, doc_hash)
        if kind == "xlsx":
            from .xlsx_ import extract_xlsx
            return extract_xlsx(path, doc_hash)
        if kind == "tabular":
            from .tabular import extract_tabular
            return extract_tabular(path, doc_hash)
        if kind == "text":
            from .text import extract_text
            return extract_text(path, doc_hash)
        if kind == "image":
            from .ocr import extract_image
            return extract_image(path, doc_hash)
    except Exception as e:  # noqa: BLE001 — an extractor failure is data, not a crash
        return Extraction(doc_hash=doc_hash, method=kind, errors=[f"{type(e).__name__}: {e}"])

    return Extraction(doc_hash=doc_hash, method="none", errors=["no extractor matched"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.extract")
    ap.add_argument("path")
    ap.add_argument("--force-ocr", action="store_true")
    ap.add_argument("--text-only", action="store_true", help="print plain text instead of JSON")
    args = ap.parse_args(argv)

    result = extract(Path(args.path), force_ocr=args.force_ocr)
    if args.text_only:
        print(result.text)
    else:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 1 if result.errors and not result.blocks else 0


if __name__ == "__main__":
    sys.exit(main())
