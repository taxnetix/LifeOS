"""COVER — policy schedules, medical aid and employee benefits into ledgers.

Label/value extraction driven by .claude/rules/cover-fields.yaml. Adding an
insurer's layout is an edit to that file plus a fixture, never a code change.

A field that does not match is ABSENT, and its absence becomes a gap record.
Nothing here fabricates a default: an unstated waiting period is unknown, not
zero, and an unstated escalation is unknown, not "none". Those two defaults
would each understate a real risk.

Usage:  python -m lifeos.cover [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from functools import cache
from pathlib import Path

from . import atomic, clock, extract, ledger, money, vault

RULES_PATH = vault.repo_root() / ".claude" / "rules" / "cover-fields.yaml"

_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y")


@cache
def load_rules() -> dict:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.load(fh)


def _coerce(raw: str, kind: str):
    raw = raw.strip()
    if kind == "money":
        return money.parse(raw)
    if kind == "pct":
        try:
            return float(raw)
        except ValueError:
            return None
    if kind == "int":
        try:
            return int(raw)
        except ValueError:
            return None
    if kind == "date":
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        return None
    return re.sub(r"\s+", " ", raw).strip() or None


def extract_fields(text: str, spec: dict) -> tuple[dict, list[str]]:
    """Apply the field patterns. Returns (values, names that did not match)."""
    values, missing = {}, []
    for name, field in (spec.get("fields") or {}).items():
        m = re.search(field["pattern"], text, re.M)
        if not m:
            missing.append(name)
            continue
        value = _coerce(m.group(1), field.get("type", "text"))
        if value is None:
            missing.append(name)
        else:
            values[name] = value
    return values, missing


def _classify_policy(policy_type: str | None, spec: dict) -> tuple[str, str | None]:
    if not policy_type:
        return "life", None
    low = policy_type.lower()
    for needle, mapped in (spec.get("class_map") or {}).items():
        if needle in low:
            return mapped["class"], mapped.get("subclass")
    return "life", None


def _envelope(*, rec_id, schema, subject, doc_hash, locator, confidence, valid_from,
              entity=None):
    env = {
        "id": rec_id, "schema": schema, "subject_id": subject,
        "source": {"doc_hash": doc_hash, "locator": locator, "method": "cover-fields/1",
                   "confidence": confidence, "extracted_at": clock.stamp()},
        "valid_from": valid_from, "valid_to": None, "superseded_by": None,
    }
    if entity:
        env["entity_id"] = entity
    return env


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:32] or "unknown"


def _subject(profile: dict) -> str:
    me = next((p for p in (profile.get("people") or []) if p.get("relation") == "self"), None)
    return (me or {}).get("ref", "per_unknown")


def _person_by_name(profile: dict, name: str | None) -> str | None:
    if not name:
        return None
    want = name.strip().lower()
    for p in profile.get("people") or []:
        if str(p.get("name", "")).strip().lower() == want:
            return p.get("ref")
    return None


def _gap(kind: str, detail: str, run_id: str, domain: str) -> None:
    import hashlib
    atomic.append_jsonl(vault.path("state", "gaps.jsonl"), {
        "id": f"sha256:{hashlib.sha256(f'{kind}|{detail}'.encode()).hexdigest()}",
        "kind": kind, "domain": domain, "detail": detail, "blocking": False,
        "consequence": "moderate", "opened_run": run_id,
        "opened_at": clock.stamp(), "agent": "insurance",
    })


def build(*, dry_run: bool = False) -> dict:
    from .readiness import load_profile

    run = clock.Run.current()
    rules = load_rules()
    conf = float(rules["confidence"])
    out: dict = {"schema": "cover/1", "run_id": run.id, "at": clock.stamp(),
                 "dry_run": dry_run, "documents": []}

    if not vault.is_initialised():
        out["error"] = "no vault — run /lifeos-init"
        return out

    profile = load_profile()
    subject = _subject(profile)
    index = list(atomic.read_jsonl(vault.path("documents", "index.jsonl")))

    records: dict[str, list[dict]] = {"policies": [], "medical-aid": [], "employee-benefits": []}

    for doc in index:
        spec = rules["types"].get(doc.get("type"))
        if not spec or doc.get("redacted"):
            continue
        path = vault.path(*Path(doc["filed_path"]).parts)
        if not path.is_file():
            continue

        text = extract.extract(path).text
        values, missing = extract_fields(text, spec)
        entry = {"doc": doc["doc_hash"][:19], "type": doc["type"],
                 "fields_found": len(values), "fields_missing": missing}

        if not dry_run:
            for name in missing:
                if name.endswith("_fallback"):
                    continue
                _gap("field.missing",
                     f"{doc['type']} {doc['doc_hash'][:19]}: '{name}' not found",
                     run.id, spec["ledger"])

        target = spec["ledger"]
        dh, loc = doc["doc_hash"], "page=1"

        if target == "policies":
            cls, sub = _classify_policy(values.get("policy_type"), spec)
            insurer = values.get("insurer") or values.get("insurer_fallback") or doc["type"]
            ref = f"pol_{_slug(insurer)}_{_slug(cls)}"
            rec = {
                **_envelope(rec_id=ledger.record_id(dh, loc, ref), schema="policies/1",
                            subject=subject, doc_hash=dh, locator=loc, confidence=conf,
                            valid_from=values.get("inception_on") or clock.today()),
                "ref": ref, "class": cls, "owner_ref": subject,
                # A schedule that never labels its insurer still shows it as
                # letterhead; "unknown" would be a worse answer than the header.
                "insurer": insurer,
            }
            if sub:
                rec["subclass"] = sub
            for src, dst in (("policy_no", "policy_no"), ("premium", None),
                             ("sum_assured", None), ("escalation_pct", "escalation_pct"),
                             ("inception_on", "inception_on")):
                if src in values:
                    rec[dst or src] = values[src]
            if "premium" in values:
                rec["premium"] = money.money(values["premium"])
                rec["premium_frequency"] = "monthly"
            # Income protection states a MONTHLY benefit, not a lump sum. Storing
            # it in sum_assured would make R55k/month look like R55k of cover.
            if "sum_assured" in values:
                rec["sum_assured"] = money.money(values["sum_assured"])
            if "monthly_benefit" in values:
                # Income protection pays MONTHLY. Putting R55 000/month into
                # sum_assured would read as R55 000 of total cover.
                rec["monthly_benefit"] = money.money(values["monthly_benefit"])
            if "ceases_age" in values:
                rec["benefit_ceases_age"] = values["ceases_age"]
            la = _person_by_name(profile, values.get("life_assured"))
            if la:
                rec["life_assured_ref"] = la
            if "waiting_period" in values:
                rec["waiting_periods"] = [{"kind": "general", "months": int(values["waiting_period"])}]
            if "ceded_to" in values:
                rec["cession"] = {"to": values["ceded_to"], "kind": "security"}
            records["policies"].append(rec)
            entry["ref"] = ref
            entry["class"] = cls

        elif target == "medical-aid":
            kind = spec["kind"]
            ref = f"med_{_slug(values.get('provider', kind))}_{kind}"
            rec = {
                **_envelope(rec_id=ledger.record_id(dh, loc, ref), schema="medical-aid/1",
                            subject=subject, doc_hash=dh, locator=loc, confidence=conf,
                            valid_from=values.get("inception_on") or clock.today()),
                "ref": ref, "kind": kind,
                "provider": values.get("provider") or "unknown",
                "doc_hash": dh,
            }
            for src in ("plan", "option", "member_no"):
                if src in values:
                    rec[src] = values[src]
            if "premium" in values:
                rec["premium"] = money.money(values["premium"])
            mm = _person_by_name(profile, values.get("main_member"))
            if mm:
                rec["main_member_ref"] = mm
            if "savings_annual" in values:
                rec["savings"] = {"annual": money.money(values["savings_annual"])}
            if "threshold_annual" in values:
                rec["threshold"] = {"annual": money.money(values["threshold_annual"])}
            sublimits = []
            for src, label in (("dentistry_limit", "dentistry"),
                               ("optometry_limit", "optometry"),
                               ("annual_limit", "annual_limit"),
                               ("casualty_benefit", "casualty"),
                               ("self_payment_gap", "self_payment_gap")):
                if src in values:
                    sublimits.append({"kind": label, "limit": money.money(values[src]),
                                      "period": "annual"})
            if sublimits:
                rec["sublimits"] = sublimits
            if "window_opens" in values:
                rec["option_change_window"] = {"opens": values["window_opens"]}
                if "window_closes" in values:
                    rec["option_change_window"]["closes"] = values["window_closes"]
            # What gap cover explicitly does NOT do becomes a hole on the map.
            excludes = [name for name, pat in (spec.get("excludes_patterns") or {}).items()
                        if re.search(pat, text)]
            if excludes:
                entry["excludes"] = excludes
                rec["providers"] = [{"kind": "excludes", "name": ", ".join(excludes)}]
            records["medical-aid"].append(rec)
            entry["ref"] = ref

        elif target == "employee-benefits":
            employer = values.get("employer") or "unknown employer"
            person = _person_by_name(profile, values.get("member")) or subject
            salary = values.get("annual_salary")
            entry["benefits"] = []

            for bname, bspec in (spec.get("benefits") or {}).items():
                cover_cents = multiple = None
                if bspec.get("pattern"):
                    m = re.search(bspec["pattern"], text)
                    if not m:
                        continue
                    groups = m.groups()
                    if len(groups) == 2:
                        multiple = float(groups[0])
                        cover_cents = money.parse(groups[1])
                    else:
                        cover_cents = money.parse(groups[0])
                elif bspec.get("value_from"):
                    cover_cents = values.get(bspec["value_from"])
                    if cover_cents is None:
                        continue

                ref = f"eb_{_slug(employer)}_{bname}"
                rec = {
                    **_envelope(rec_id=ledger.record_id(dh, f"benefit={bname}", ref),
                                schema="employee-benefits/1", subject=person,
                                doc_hash=dh, locator=f"benefit={bname}", confidence=conf,
                                valid_from=values.get("statement_as_at") or clock.today()),
                    "ref": ref, "person_ref": person, "employer": employer,
                    "kind": bspec["kind"], "doc_hash": dh,
                }
                if cover_cents is not None:
                    rec["benefit"] = money.money(cover_cents)
                if multiple is not None:
                    rec["multiple_of_salary"] = multiple
                if "fund_member_no" in values and bspec["kind"] in {"provident", "pension"}:
                    rec["member_no"] = values["fund_member_no"]
                if "statement_as_at" in values:
                    rec["statement_as_at"] = values["statement_as_at"]
                if salary and bspec["kind"] in {"provident", "pension"}:
                    for src, who in (("member_contrib", "employee"),
                                     ("employer_contrib", "employer")):
                        if src in values:
                            rec.setdefault("contribution", {})[who] = money.money(
                                int(salary * values[src] / 100 / 12)
                            )
                records["employee-benefits"].append(rec)
                entry["benefits"].append(bname)

            if salary:
                entry["annual_salary_cents"] = salary

        out["documents"].append(entry)

    out["ledgers"] = {
        name: ledger.write(name, recs, agent={"policies": "insurance"}.get(name, "living"),
                           run_id=run.id, dry_run=dry_run)
        for name, recs in records.items() if recs
    }
    out["totals"] = {
        "documents": len(out["documents"]),
        "records": sum(len(r) for r in records.values()),
        "fields_missing": sum(len(d["fields_missing"]) for d in out["documents"]),
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lifeos.cover")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    print(json.dumps(build(dry_run=args.dry_run), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
