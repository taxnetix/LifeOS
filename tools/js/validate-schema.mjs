#!/usr/bin/env node
/**
 * Fast JSON Schema validation with ajv.
 *
 * Node owns this because it runs on the hook and pre-commit paths, where
 * interpreter startup latency is felt on every call.
 * See docs/adr/0011-python-primary-thin-node.md.
 *
 *   node tools/js/validate-schema.mjs <ledger> <file.jsonl>
 *   node tools/js/validate-schema.mjs --all          # every schema compiles
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const SCHEMA_DIR = join(REPO, "templates", "schemas");
const BASE = "https://lifeos.local/schemas";

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (entry.endsWith(".json")) out.push(full);
  }
  return out;
}

function buildAjv() {
  const ajv = new Ajv2020({ allErrors: true, strict: false, validateFormats: true });
  addFormats(ajv);
  for (const file of walk(SCHEMA_DIR)) {
    const doc = JSON.parse(readFileSync(file, "utf8"));
    if (doc.$id) ajv.addSchema(doc, doc.$id);
  }
  return ajv;
}

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

const args = process.argv.slice(2);

if (args[0] === "--all" || args.length === 0) {
  const ajv = buildAjv();
  const files = walk(SCHEMA_DIR);
  let compiled = 0;
  for (const file of files) {
    const doc = JSON.parse(readFileSync(file, "utf8"));
    if (!doc.$id) fail(`${file}: missing $id`);
    try {
      ajv.getSchema(doc.$id) ?? ajv.compile(doc);
      compiled += 1;
    } catch (e) {
      fail(`${file}: ${e.message}`);
    }
  }
  console.log(JSON.stringify({ schemas: files.length, compiled, ok: true }));
  process.exit(0);
}

const [ledger, target] = args;
if (!ledger || !target) fail("usage: validate-schema.mjs <ledger> <file.jsonl>  |  --all");

const ajv = buildAjv();
const id = `${BASE}/ledgers/${ledger}.schema.json`;
const validate = ajv.getSchema(id);
if (!validate) fail(`no schema for ledger '${ledger}' (expected ${id})`);

const text = readFileSync(target, "utf8");
const lines = text.split("\n").filter((l) => l.trim());
const problems = [];

lines.forEach((line, i) => {
  let record;
  try {
    record = JSON.parse(line);
  } catch (e) {
    problems.push({ line: i + 1, error: `not valid JSON: ${e.message}` });
    return;
  }
  if (record.schema?.endsWith("/tombstone")) return; // supersession markers
  if (!validate(record)) {
    for (const err of validate.errors ?? []) {
      problems.push({ line: i + 1, path: err.instancePath || "<root>", error: err.message });
    }
  }
});

console.log(JSON.stringify({ ledger, records: lines.length, problems: problems.length, detail: problems.slice(0, 25) }, null, 2));
process.exit(problems.length ? 1 : 0);
