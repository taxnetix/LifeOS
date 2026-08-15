"""OCR for scanned documents and images.

OCR output is a guess with a number attached. Tesseract reports per-word
confidence, and this module carries the *mean of the worst quartile* through to
the block — not the mean of everything, because a page that reads perfectly
except for the one column containing the amounts is exactly the failure this
system must not wave through.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from statistics import mean

from . import Block, Extraction

_DPI = 300
_MIN_WORD_CONF = 30      # below this tesseract is guessing at noise
_TIMEOUT = 120


def _require(binary: str) -> str:
    found = shutil.which(binary)
    if not found:
        raise RuntimeError(f"{binary} not installed")
    return found


def _confidence(data: dict) -> float:
    """Mean of the worst quartile of word confidences, scaled to 0–1.

    Using the overall mean would let a page of clean boilerplate hide a badly
    read table of figures. The worst quartile is what decides whether a human
    should look.
    """
    confs = [c for c in data.get("conf", []) if isinstance(c, (int, float)) and c >= 0]
    if not confs:
        return 0.0
    confs.sort()
    worst = confs[: max(1, len(confs) // 4)]
    return round(mean(worst) / 100.0, 3)


def _ocr_image_file(img: Path, locator: str) -> Block | None:
    import pytesseract
    from PIL import Image

    _require("tesseract")
    with Image.open(img) as im:
        if im.mode not in ("L", "RGB"):
            im = im.convert("RGB")
        data = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT)

    words = [
        w for w, c in zip(data.get("text", []), data.get("conf", []), strict=False)
        if w.strip() and isinstance(c, (int, float)) and c >= _MIN_WORD_CONF
    ]
    if not words:
        return None
    return Block(locator=locator, text=" ".join(words), confidence=_confidence(data))


def extract_image(path: Path, doc_hash: str) -> Extraction:
    out = Extraction(doc_hash=doc_hash, method="ocr:tesseract", pages=1, ocr=True)
    try:
        block = _ocr_image_file(path, "page=1;ocr=1")
    except Exception as e:  # noqa: BLE001
        out.errors.append(f"OCR unavailable: {type(e).__name__}: {e}")
        return out
    if block:
        out.blocks.append(block)
    else:
        out.errors.append("OCR found no legible text in this image")
    return out


def ocr_pdf_pages(path: Path, pages: list[int]) -> list[Block]:
    """Rasterise the named pages and OCR them. Raises if the toolchain is absent."""
    pdftoppm = _require("pdftoppm")
    _require("tesseract")

    blocks: list[Block] = []
    with tempfile.TemporaryDirectory() as tmp:
        for n in pages:
            prefix = Path(tmp) / f"page-{n}"
            subprocess.run(
                [pdftoppm, "-f", str(n), "-l", str(n), "-r", str(_DPI), "-png",
                 str(path), str(prefix)],
                check=True, capture_output=True, timeout=_TIMEOUT,
            )
            rendered = sorted(Path(tmp).glob(f"page-{n}*.png"))
            if not rendered:
                continue
            block = _ocr_image_file(rendered[0], f"page={n};ocr=1")
            if block:
                blocks.append(block)
    return blocks
