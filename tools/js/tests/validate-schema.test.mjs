import { describe, it, expect } from "vitest";
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const RUN = (args) =>
  execFileSync("node", ["tools/js/validate-schema.mjs", ...args], { encoding: "utf8" });

const envelope = (over = {}) => ({
  id: "sha256:" + "a".repeat(64),
  subject_id: "per_test",
  source: {
    doc_hash: "human",
    locator: "l",
    method: "human",
    confidence: 1,
    extracted_at: "2026-08-15T09:00:00Z",
  },
  valid_from: "2026-08-15",
  valid_to: null,
  superseded_by: null,
  _meta: { run_id: "r", agent: "test", written_at: "2026-08-15T09:00:00Z" },
  ...over,
});

const writeRecord = (ledger, record) => {
  const f = join(mkdtempSync(join(tmpdir(), "lifeos-")), `${ledger}.jsonl`);
  writeFileSync(f, JSON.stringify(record) + "\n");
  return f;
};

const validates = (ledger, record) => {
  try {
    return JSON.parse(RUN([ledger, writeRecord(ledger, record)])).problems === 0;
  } catch {
    return false;
  }
};

describe("schema set", () => {
  it("compiles every schema, so no $ref is left dangling", () => {
    const out = JSON.parse(RUN(["--all"]));
    expect(out.ok).toBe(true);
    expect(out.compiled).toBe(out.schemas);
    expect(out.schemas).toBeGreaterThanOrEqual(40);
  });
});

describe("money is integer cents", () => {
  const valuation = (value) =>
    envelope({
      schema: "valuations/1",
      asset_ref: "ast_house",
      as_at: "2026-08-15",
      value,
      basis: "market",
    });

  it("accepts integer cents with a currency", () => {
    expect(validates("valuations", valuation({ cents: 250000000, currency: "ZAR" }))).toBe(true);
  });

  it("rejects a float — this is the bug that silently corrupts a ledger", () => {
    expect(validates("valuations", valuation({ cents: 1234.56, currency: "ZAR" }))).toBe(false);
  });

  it("rejects a missing currency — there is no default", () => {
    expect(validates("valuations", valuation({ cents: 100000 }))).toBe(false);
  });

  it("rejects a bare number", () => {
    expect(validates("valuations", valuation(100000))).toBe(false);
  });
});

describe("envelope is enforced", () => {
  const base = {
    schema: "fx-rates/1",
    pair: "USDZAR",
    rate: 18.42,
    rate_date: "2026-08-15",
    rate_source: "sarb.co.za",
  };

  it("accepts a well-formed record", () => {
    expect(validates("fx-rates", envelope(base))).toBe(true);
  });

  it("rejects a record with no provenance", () => {
    const r = envelope(base);
    delete r.source;
    expect(validates("fx-rates", r)).toBe(false);
  });

  it("rejects a malformed id — identity must be a real hash", () => {
    expect(validates("fx-rates", envelope({ ...base, id: "12345" }))).toBe(false);
  });

  it("rejects unknown properties, catching typos before they reach a ledger", () => {
    expect(validates("fx-rates", envelope({ ...base, raat: 18.42 }))).toBe(false);
  });
});

describe("secrets can never be stored", () => {
  const digital = (pointer) =>
    envelope({
      schema: "digital-estate/1",
      ref: "de_1",
      subject_ref: "per_test",
      kind: "account",
      service: "FNB",
      credential_pointer: pointer,
    });

  it("accepts a pointer to where the credential lives", () => {
    expect(validates("digital-estate", digital("1Password/Personal/FNB Online"))).toBe(true);
  });

  it("rejects anything that looks like an actual secret", () => {
    for (const bad of ["my password is hunter2", "API_KEY=sk-abc", "seed phrase: alpha bravo"]) {
      expect(validates("digital-estate", digital(bad))).toBe(false);
    }
  });
});

describe("credential pointers stay usable", () => {
  const digital = (pointer) =>
    envelope({
      schema: "digital-estate/1",
      ref: "de_1",
      subject_ref: "per_test",
      kind: "account",
      service: "FNB",
      credential_pointer: pointer,
    });

  it("permits real-world manager paths containing the word 'password'", () => {
    for (const ok of [
      "1Password/Personal/FNB Online",
      "Bitwarden > Banking > Capitec",
      "Password Manager, Personal vault",
      "Master password held by the executor",
    ]) {
      expect(validates("digital-estate", digital(ok))).toBe(true);
    }
  });
});
