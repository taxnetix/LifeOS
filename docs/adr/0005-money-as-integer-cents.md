# ADR-0005 — Money is integer minor units, never a float

**Status** Accepted · Phase 0

## Context

LifeOS computes net worth, budget variance, tax liability, estate duty and liquidity shortfall. These figures inform real decisions and are compared against statements produced by banks and SARS, which are exact to the cent.

IEEE-754 binary floating point cannot represent most decimal fractions exactly. `0.1 + 0.2 != 0.3`. Summing a year of transactions as floats produces drift that is small, plausible, and therefore invisible — the worst possible failure mode for a system whose credibility rests on matching the bank's own arithmetic. JSON has no decimal type, so "just store a number" means storing a float.

## Decision

All monetary values are an object:

```json
{ "cents": -125000, "currency": "ZAR" }
```

- `cents` is a **signed integer** in the currency's minor unit. Negative is outflow.
- `currency` is **required**, ISO-4217. There is no default; an amount without a currency is a schema violation.
- Schema enforces `"type": "integer"` — a float in the `cents` field fails validation and is never written.
- Python uses `int` throughout and `decimal.Decimal` for any intermediate that needs fractional precision (interest, percentages, apportionment), rounding to integer cents at the boundary with an explicit, documented rounding mode.
- Percentages and rates are **not** money and are stored as decimal numbers with an explicit precision note.

**Cross-currency aggregation requires an explicit dated rate** from `ledgers/fx-rates.jsonl`. Any report mixing currencies names the rate and its date on the face of the output. There is no implicit conversion anywhere in the system.

## Consequences

- Arithmetic is exact. Totals reconcile to the cent against bank statements, which is the only standard that matters here.
- Every amount is self-describing; a bare number can never be mistaken for ZAR.
- Multi-currency correctness is forced rather than hoped for — you cannot accidentally add dollars to rands, because the code has nowhere to get a rate without asking for one.
- Verbosity: `{"cents": 1000, "currency": "ZAR"}` instead of `10.00`. Accepted; ledgers are read by tools far more often than by people, and reports render properly formatted amounts.
- Presentation formatting (thousands separators, `R` prefix, negative styling) lives in the visualiser, never in the ledger.

## Alternatives considered

**Decimal strings — `"1234.56"`** — exact and readable, but every consumer must parse before arithmetic, and nothing stops a malformed string. Integers cannot be malformed.

**Floats with rounding at display time** — the drift is already in the stored data by then. Rejected.

**A single implicit currency** — the user holds offshore assets and the brief requires currency exposure analysis. Rejected as wrong from day one.
