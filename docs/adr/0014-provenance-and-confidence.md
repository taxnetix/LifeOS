# ADR-0014 — Provenance and confidence on every extracted field

**Status** Accepted · Phase 0

## Context

The brief is unambiguous: every factual claim about the user's life must trace to a source document with hash and page; no invented numbers, ever; unknown is a valid, first-class answer. The system will nonetheless be extracting from scanned PDFs, OCR output and inconsistent bank layouts, where extraction is sometimes uncertain.

An extraction pipeline that returns only values gives the reader no way to distinguish a figure read cleanly from a printed table from one guessed off a smudged scan. Both look like numbers. In a system whose output informs tax and estate decisions, that flattening is the dangerous part.

## Decision

Every record carries a `source` block, and it is required by schema:

| Field | Meaning |
|---|---|
| `doc_hash` | SHA-256 of the filed original |
| `locator` | exact position — `page=3;row=17`, `sheet=Summary;cell=B14`, `para=12` |
| `method` | `parser:absa-cheque/2` · `pdfplumber` · `ocr:tesseract` · `llm-extract` · `human` · `inferred` |
| `confidence` | 0.0–1.0 |
| `extracted_at` | when extraction ran |

**Confidence gates the write.** Each ledger declares a floor. Below it, the record does not enter the ledger at all — it goes to `proposed/` with the extraction, the source excerpt and the reason, and waits for confirmation. A number the system is unsure of never becomes a number the system reports.

**`method` is not decoration.** `inferred` and `llm-extract` are rendered differently in every report, so a reader can always see which figures were read and which were derived or guessed.

**Absence is recorded.** A field that could not be extracted produces a record in `state/gaps.jsonl` — never `null` meaning "we didn't look", never `0` meaning "unknown", never a plausible placeholder.

## Consequences

- `/audit` can walk any figure in any dashboard back to a page of a real document, which is what makes definition-of-done #3 checkable rather than aspirational.
- The four-way distinction the brief requires — what documents say, arithmetic from them, suggestions, matters for a professional — is supported by data rather than by the model remembering to caveat.
- Low-confidence extraction becomes a conversation instead of a silent error, which is the behaviour that makes the system trustworthy on messy real-world scans.
- Provenance is inseparable from identity: the record ID is derived from `doc_hash` and `locator` ([ADR-0006](0006-deterministic-record-ids.md)), so a record without traceable origin cannot be constructed.
- The cost is verbosity — roughly five extra fields per record — and the discipline of threading provenance through every extractor. Both are non-negotiable given what the numbers are used for.
- Human-entered facts and inferences use `doc_hash: "human"` or `"inferred"` with a stable natural key, so they participate in the same model rather than being exceptions to it.

## Alternatives considered

**Provenance at document level only** — cheap, and useless for the actual question, which is always "where did *this number* come from?"

**Confidence without a gating floor** — records the uncertainty and then reports the figure anyway. The floor is what converts the metadata into a behaviour.

**Store extraction uncertainty in a side channel** — separates a fact from its reliability, and they inevitably drift apart. Rejected.
