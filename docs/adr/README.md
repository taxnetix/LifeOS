# Architecture Decision Records

One file per decision that would be expensive to reverse. Format: **Context · Decision · Consequences · Alternatives considered**.

An ADR is never edited to change its decision — it is superseded by a new one that links back. That is the same append-only discipline the ledgers use, applied to design.

| # | Decision | Status |
|---|---|---|
| [0001](0001-files-are-the-database.md) | Files are the database | Accepted |
| [0002](0002-fractal-definition-flat-runtime.md) | Fractal in definition, flat at runtime | Accepted |
| [0003](0003-deterministic-sense.md) | SENSE is a deterministic script, not an agent turn | Accepted |
| [0004](0004-tools-compute-skills-judge.md) | Tools compute, skills judge | Accepted |
| [0005](0005-money-as-integer-cents.md) | Money is integer minor units, never a float | Accepted |
| [0006](0006-deterministic-record-ids.md) | Deterministic record IDs give idempotency | Accepted |
| [0007](0007-single-writer-atomic-writes.md) | One writer per ledger; all writes atomic | Accepted |
| [0008](0008-vault-location-and-separation.md) | System and vault are separate; vault is `./vault/` | Accepted, with a flagged risk |
| [0009](0009-no-sqlite-read-model.md) | No SQLite read-model | Accepted |
| [0010](0010-lean-agent-tree.md) | Lean agent tree; depth is earned | Accepted |
| [0011](0011-python-primary-thin-node.md) | Python primary, thin Node | Accepted |
| [0012](0012-schema-versioning.md) | Schema versioning and migration | Accepted |
| [0013](0013-scheduling-template-not-installed.md) | Ship the scheduler, do not install it | Accepted |
| [0014](0014-provenance-and-confidence.md) | Provenance and confidence on every extracted field | Accepted |
| [0015](0015-redaction-enforced-by-hook.md) | Redaction is enforced by hook, not convention | Accepted |
| [0016](0016-jurisdiction-as-config-axis.md) | Jurisdiction is a config axis | Accepted |
| [0017](0017-github-for-system-work.md) | GitHub tracks the system, never your life | Accepted |
| [0018](0018-life-file-document.md) | The Life File is a tiered document, not a data dump | Accepted |
