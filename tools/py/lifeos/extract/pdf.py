"""PDF extraction via pdfplumber, falling back to OCR for scanned pages.

Bank statements, policy schedules and title deeds arrive as PDFs in two very
different forms: a real text layer, or a photograph of paper. Treating them
identically is how a smudged scan's guess ends up in a ledger looking exactly
as trustworthy as a printed figure.

So this module decides per PAGE, not per document — a scanned annexure stapled
to a digital policy schedule is common — and stamps the resulting confidence on
each block.
"""

from __future__ import annotations

from pathlib import Path

from . import Block, Extraction, Table

# A page with fewer than this many extracted characters is treated as an image
# of text rather than text. Deliberately low: a genuine near-blank page costs
# one wasted OCR pass, while a missed scan costs a wrong number in a ledger.
_TEXT_LAYER_MIN_CHARS = 40

_CONF_TEXT_LAYER = 0.99      # a real text layer is as good as it gets
_CONF_TABLE = 0.95           # ruled table: structure read from actual lines
_CONF_TABLE_INFERRED = 0.80  # borderless table: columns inferred from whitespace

# Borderless tables are the norm in bank statements — ruling lines are decorative
# and often absent. Falling back to text alignment is what makes a statement
# parseable at all; the lower confidence records that the structure is inferred.
_TEXT_TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "intersection_tolerance": 5,
}


def extract_pdf(path: Path, doc_hash: str, *, force_ocr: bool = False) -> Extraction:
    import pdfplumber

    out = Extraction(doc_hash=doc_hash, method="pdfplumber", pages=0)
    scanned_pages: list[int] = []

    try:
        with pdfplumber.open(path) as pdf:
            out.pages = len(pdf.pages)
            out.meta = {k: str(v) for k, v in (pdf.metadata or {}).items() if v}

            for n, page in enumerate(pdf.pages, 1):
                text = "" if force_ocr else (page.extract_text() or "")

                if len(text.strip()) < _TEXT_LAYER_MIN_CHARS:
                    scanned_pages.append(n)
                    continue

                for i, line in enumerate(_lines(text), 1):
                    out.blocks.append(
                        Block(locator=f"page={n};line={i}", text=line, confidence=_CONF_TEXT_LAYER)
                    )

                for t, (rows, strategy) in enumerate(_tables(page), 1):
                    out.tables.append(
                        Table(
                            locator=f"page={n};table={t}",
                            rows=rows,
                            # Text-aligned detection infers columns from whitespace
                            # rather than reading ruling lines, so it is a weaker
                            # claim and says so.
                            confidence=_CONF_TABLE if strategy == "lines" else _CONF_TABLE_INFERRED,
                        )
                    )
    except Exception as e:  # noqa: BLE001
        out.errors.append(f"pdfplumber failed: {type(e).__name__}: {e}")
        if not out.blocks:
            return out

    if scanned_pages:
        _ocr_pages(path, scanned_pages, out)

    if not out.blocks and not out.tables and not out.errors:
        out.errors.append("no text or tables found — the PDF may be empty or corrupt")

    return out


def _lines(text: str) -> list[str]:
    """One block per non-empty line.

    Line granularity, not paragraph: in a bank statement each line IS a
    transaction, and a locator that pointed at a whole page would make
    provenance useless — 'page=1' cannot answer 'where did this figure come
    from?'. Blank lines are dropped, so numbering stays stable regardless of
    vertical spacing.
    """
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def _tables(page) -> list[tuple[list[list[str]], str]]:
    """Extract tables, preferring ruled detection and falling back to text.

    Returns (rows, strategy) so the caller can set confidence honestly.
    """
    def clean(raw) -> list[list[str]]:
        rows = [[(c or "").strip() for c in row] for row in raw]
        return [r for r in rows if any(r)]

    found = [clean(t) for t in (page.extract_tables() or [])]
    found = [t for t in found if len(t) > 1]
    if found:
        return [(t, "lines") for t in found]

    try:
        inferred = [clean(t) for t in (page.extract_tables(_TEXT_TABLE_SETTINGS) or [])]
    except Exception:  # noqa: BLE001 — a failed fallback is not a failed extraction
        return []
    return [(t, "text") for t in inferred if _is_coherent(t)]


def _is_coherent(rows: list[list[str]]) -> bool:
    """Does a whitespace-inferred grid actually look like a table?

    Splitting on whitespace happily shreds 'Account holder' into 'Accou' and
    'nt holder' and returns it as two columns. That output is worse than no
    table: it is confidently wrong, and it would carry a confidence above the
    default write floor straight into a ledger.

    So an inferred table must earn its place — a stable column count across most
    rows. Anything ragged is dropped, and the line-level blocks (which are
    accurate) remain. Structured parsing of a specific bank's layout is a
    bank-specific adapter's job, not a generic heuristic's.
    """
    if len(rows) < 3:
        return False
    counts = [sum(1 for c in r if c) for r in rows]
    modal = max(set(counts), key=counts.count)
    if modal < 2:
        return False
    return counts.count(modal) / len(counts) >= 0.7


def _ocr_pages(path: Path, pages: list[int], out: Extraction) -> None:
    """OCR the pages that had no usable text layer.

    Degrades rather than fails: without pdftoppm or tesseract the pages become
    an explicit error the caller turns into a gap record, never a silent hole.
    """
    from .ocr import ocr_pdf_pages

    try:
        results = ocr_pdf_pages(path, pages)
    except Exception as e:  # noqa: BLE001
        out.errors.append(
            f"{len(pages)} page(s) have no text layer and OCR is unavailable "
            f"({type(e).__name__}: {e}); pages {pages} were not read"
        )
        return

    if results:
        out.ocr = True
        out.method = "pdfplumber+ocr:tesseract" if out.blocks else "ocr:tesseract"
        out.blocks.extend(results)

    missed = sorted(set(pages) - {int(b.locator.split(";")[0].split("=")[1]) for b in results})
    if missed:
        out.errors.append(f"OCR produced no text for page(s) {missed}")
