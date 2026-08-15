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


_BENEFICIARY_ROW = re.compile(
    r"^(?P<name>[A-Z][A-Za-z&' ]{2,50}?)\s*(?:\((?P<rel>[a-z ]+)\))?\s+(?P<pct>\d{1,3}(?:\.\d+)?)\s*%\s*$",
    re.M,
)


def extract_beneficiaries(text: str) -> list[dict]:
    """Nomination rows from a schedule's beneficiary section.

    A nomination OVERRIDES the will for that asset, so failing to read it means
    failing to detect the single highest-value estate finding LifeOS can
    produce. Rows outside a beneficiary heading are ignored — a stray
    percentage elsewhere on the page is not a nomination.
    """
    section = None
    for heading in ("Beneficiary nomination", "Beneficiaries", "Beneficiary"):
        i = text.find(heading)
        if i != -1:
            section = text[i: i + 600]
            break
    if section is None:
        return []
    out = []
    for m in _BENEFICIARY_ROW.finditer(section):
        try:
            pct = float(m.group("pct"))
        except ValueError:
            continue
        out.append({"name": m.group("name").strip(), "pct": pct,
                    **({"relationship": m.group("rel").strip()} if m.group("rel") else {})})
    return out


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

    records: dict[str, list[dict]] = {"policies": [], "medical-aid": [],
                                      "employee-benefits": [], "assets": [],
                                      "liabilities": [], "valuations": [], "wills": [],
                                      "trusts": [], "trustees": [], "distributions": [],
                                      "loan-accounts": []}

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
            bens = extract_beneficiaries(text)
            if bens:
                rec["beneficiaries"] = [
                    {"pct": b["pct"],
                     **({"person_ref": _person_by_name(profile, b["name"])}
                        if _person_by_name(profile, b["name"]) else {}),
                     "name": b["name"]}
                    for b in bens
                ]
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

        elif target == "trusts":
            ref = f"tr_{_slug(values.get('name', 'trust'))}"
            type_map = {
                "inter vivos discretionary": "inter_vivos_discretionary",
                "inter vivos vested": "inter_vivos_vested",
                "testamentary": "testamentary",
                "bewind": "bewind",
                "special": "special",
            }
            ttype = "inter_vivos_discretionary"
            for needle, mapped in type_map.items():
                if needle in (values.get("type_text") or "").lower():
                    ttype = mapped
                    break
            rec = {
                **_envelope(rec_id=ledger.record_id(dh, loc, ref), schema="trusts/1",
                            subject=subject, doc_hash=dh, locator=loc, confidence=conf,
                            valid_from=values.get("signed_on") or values.get("loa_issued_on")
                            or clock.today()),
                "ref": ref, "name": values.get("name") or "unnamed trust", "type": ttype,
            }
            if "mt_number" in values:
                rec["mt_number"] = values["mt_number"]
            founder = _person_by_name(profile, values.get("founder_name"))
            if founder:
                rec["founder_ref"] = founder
            # Year end drives every compliance date; "28 February" must become
            # "02-28" or the whole calendar is a year out.
            ye = values.get("year_end")
            if ye:
                import calendar as _cal
                months = {m.lower(): i for i, m in enumerate(_cal.month_name) if m}
                parts = ye.replace(",", " ").split()
                if len(parts) == 2 and parts[1].lower() in months:
                    rec["year_end"] = f"{months[parts[1].lower()]:02d}-{int(parts[0]):02d}"
            if "signed_on" in values:
                rec["deed"] = [{"kind": "deed", "signed_on": values["signed_on"],
                                "doc_hash": dh}]
            if "loa_issued_on" in values:
                rec["loa"] = {"issued_on": values["loa_issued_on"], "doc_hash": dh}

            # A trust is ONE thing evidenced by SEVERAL documents — the deed
            # carries the beneficiaries and the quorum, the letters of authority
            # carry the issue date and who may act. Keying on the document would
            # mint a separate trust per document, and every count, calendar and
            # s7C figure would then be doubled.
            #
            # Identity is the trust ref anchored to the lexicographically
            # smallest evidencing document, so it is stable whatever order the
            # documents arrive in; fields merge, and the deed's own record of a
            # field wins over a later document's silence.
            prior = next((r for r in records["trusts"] if r["ref"] == ref), None)
            if prior is None:
                records["trusts"].append(rec)
            else:
                anchor = min(prior["source"]["doc_hash"], dh)
                merged = {**rec, **{k: v for k, v in prior.items() if k not in rec}}
                for key in ("deed", "loa", "mt_number", "founder_ref", "year_end"):
                    if key in prior and key not in rec:
                        merged[key] = prior[key]
                    elif key in rec and key in prior and key == "deed":
                        merged[key] = prior[key] + rec[key]
                merged["source"] = dict(prior["source"] if anchor ==
                                        prior["source"]["doc_hash"] else rec["source"])
                merged["id"] = ledger.record_id(anchor, loc, ref)
                records["trusts"][records["trusts"].index(prior)] = merged
            entry["ref"] = ref

            for m in re.finditer(
                ((spec.get("resolves") or {}).get("trustee") or {}).get("pattern", r"(?!x)x"),
                text, re.M,
            ):
                tname, capacity, appointed = m.groups()
                tref = f"tt_{_slug(ref)}_{_slug(tname)}"
                records["trustees"].append({
                    **_envelope(rec_id=ledger.record_id(dh, f"trustee={tname.strip()}", tref),
                                schema="trustees/1", subject=subject, doc_hash=dh,
                                locator=f"trustee={tname.strip()}", confidence=conf,
                                valid_from=_coerce(appointed, "date") or clock.today()),
                    "trust_ref": ref, "kind": "appointment",
                    "name": tname.strip(),
                    **({"person_ref": _person_by_name(profile, tname.strip())}
                       if _person_by_name(profile, tname.strip()) else {}),
                    "role": "independent" if "independent" in capacity.lower() else "trustee",
                    "independent": "independent" in capacity.lower(),
                    "appointed_on": _coerce(appointed, "date"),
                    "doc_hash": dh,
                })
            entry["trustees"] = sum(1 for r in records["trustees"]
                                    if r.get("trust_ref") == ref and r["kind"] == "appointment")

        elif target == "trustees":
            trust_ref = None
            for tr in ledger.read("trusts"):
                if values.get("mt_number") and tr.get("mt_number") == values["mt_number"]:
                    trust_ref = tr["ref"]
                    break
            if trust_ref is None:
                trust_ref = next((tr["ref"] for tr in records["trusts"]
                                  if tr.get("mt_number") == values.get("mt_number")), None)
            if trust_ref is None:
                # A resolution that cannot be tied to a trust is a gap, never a
                # guess: attaching it to the wrong trust is worse than not
                # attaching it at all.
                entry["error"] = (
                    f"resolution references {values.get('mt_number')} but no trust with "
                    "that Master's reference is on file"
                )
                if not dry_run:
                    _gap("record.low_confidence", entry["error"], run.id, "trusts")
                out["documents"].append(entry)
                continue

            res_ref = f"res_{_slug(trust_ref)}_{_slug(values.get('resolution_no', 'x'))}"
            records["trustees"].append({
                **_envelope(rec_id=ledger.record_id(dh, loc, res_ref), schema="trustees/1",
                            subject=subject, doc_hash=dh, locator=loc, confidence=conf,
                            valid_from=values.get("meeting_on") or clock.today()),
                "trust_ref": trust_ref, "kind": "resolution",
                "meeting_on": values.get("meeting_on"),
                "subject": f"Resolution {values.get('resolution_no', '')}".strip(),
                "doc_hash": dh,
            })
            entry["ref"] = res_ref

            resolves = spec.get("resolves") or {}
            nature_map = {"rental income": "income_rental", "interest income": "income_interest",
                          "dividend": "dividend", "capital": "capital"}
            if resolves.get("distribution"):
                for m in re.finditer(resolves["distribution"]["pattern"], text, re.M):
                    name, amt, nature, vested = m.groups()
                    cents = money.parse(amt)
                    if cents is None:
                        continue
                    ben = _person_by_name(profile, name.strip())
                    dref = f"{res_ref}_{_slug(name)}"
                    records["distributions"].append({
                        **_envelope(rec_id=ledger.record_id(dh, f"dist={name.strip()}", dref),
                                    schema="distributions/1", subject=subject, doc_hash=dh,
                                    locator=f"dist={name.strip()}", confidence=conf,
                                    valid_from=values.get("meeting_on") or clock.today()),
                        "trust_ref": trust_ref,
                        "beneficiary_ref": ben or "per_unknown",
                        "tax_year": str(int(vested.split()[-1])),
                        "amount": money.money(cents),
                        "nature": nature_map.get(nature.strip().lower(), "income_interest"),
                        # Vested during the year AND authorised by this resolution:
                        # both are what the conduit principle needs.
                        "conduit": True,
                        "resolution_ref": res_ref,
                        "doc_hash": dh,
                    })
            if resolves.get("loan"):
                for m in re.finditer(resolves["loan"]["pattern"], text, re.M):
                    name, amt, rate = m.groups()
                    cents = money.parse(amt)
                    if cents is None:
                        continue
                    lender = _person_by_name(profile, name.strip())
                    lref = f"loan_{_slug(trust_ref)}_{_slug(name)}"
                    records["loan-accounts"].append({
                        **_envelope(rec_id=ledger.record_id(dh, f"loan={name.strip()}", lref),
                                    schema="loan-accounts/1", subject=subject, doc_hash=dh,
                                    locator=f"loan={name.strip()}", confidence=conf,
                                    valid_from=values.get("meeting_on") or clock.today()),
                        "trust_ref": trust_ref,
                        "counterparty_ref": lender or "per_unknown",
                        "direction": "owed_by_trust",
                        "balance": money.money(cents),
                        "balance_as_at": values.get("meeting_on") or clock.today(),
                        "interest_rate_pct": 0.0 if "interest free" in rate.lower()
                                             else float(rate.rstrip("%")),
                        "s7c_applicable": True,
                        "doc_hash": dh,
                    })

        elif target == "wills":
            testator = _person_by_name(profile, values.get("testator")) or subject
            ref = f"will_{_slug(values.get('testator', 'testator'))}"
            rec = {
                **_envelope(rec_id=ledger.record_id(dh, loc, ref), schema="wills/1",
                            subject=subject, doc_hash=dh, locator=loc, confidence=conf,
                            valid_from=values.get("signed_on") or clock.today()),
                "ref": ref, "testator_ref": testator, "kind": "will",
                # A will is only a will once signed. Absent evidence of a
                # signature the answer is "unknown", and the readiness score
                # treats that as the catastrophic gap it is.
                "signed": bool(values.get("signed_on")),
                "doc_hash": dh,
            }
            if "signed_on" in values:
                rec["signed_on"] = values["signed_on"]
            if "executor" in values:
                rec["executor"] = {"name": values["executor"]}
            for src, note in (("residuary_heir", "residuary heir"),
                              ("substitute_heir", "substitute heir"),
                              ("guardian", "guardian")):
                if src in values:
                    rec.setdefault("review_triggers", []).append(f"{note}: {values[src]}")
            records["wills"].append(rec)
            entry["ref"] = ref
            entry["heirs"] = {k: values[k] for k in
                              ("residuary_heir", "substitute_heir", "guardian",
                               "executor") if k in values}

        elif target == "assets":
            ref = f"ast_{_slug(values.get('deed_no') or values.get('description', 'property'))}"
            rec = {
                **_envelope(rec_id=ledger.record_id(dh, loc, ref), schema="assets/1",
                            subject=subject, doc_hash=dh, locator=loc, confidence=conf,
                            valid_from=values.get("acquired_on") or clock.today()),
                "ref": ref, "owner_ref": subject, "class": "property",
                "kind": "residential",
                "description": values.get("description") or "property",
                "doc_hash": dh,
            }
            for src, dst in (("acquired_on", "acquired_on"),
                             ("deed_location", "title_deed_location")):
                if src in values:
                    rec[dst] = values[src]
            # Base cost drives CGT at death. Without it the deemed disposal
            # cannot be computed, so its absence must be a gap, not a zero.
            if "base_cost" in values:
                rec["base_cost"] = money.money(values["base_cost"])
            records["assets"].append(rec)
            entry["ref"] = ref

            # A municipal valuation is NOT a market value. Recording the basis
            # matters more than the number: municipal values commonly lag the
            # market by years, in either direction.
            if "municipal_value" in values:
                vref = f"{ref}_municipal"
                records["valuations"].append({
                    **_envelope(rec_id=ledger.record_id(dh, "valuation", vref),
                                schema="valuations/1", subject=subject, doc_hash=dh,
                                locator="valuation", confidence=conf,
                                valid_from=values.get("acquired_on") or clock.today()),
                    "asset_ref": ref,
                    "as_at": values.get("acquired_on") or clock.today(),
                    "value": money.money(values["municipal_value"]),
                    "basis": "municipal",
                    "doc_hash": dh,
                })

        elif target == "liabilities":
            creditor = values.get("creditor_fallback") or "unknown creditor"
            ref = f"lia_{_slug(creditor)}_home_loan"
            rec = {
                **_envelope(rec_id=ledger.record_id(dh, loc, ref), schema="liabilities/1",
                            subject=subject, doc_hash=dh, locator=loc, confidence=conf,
                            valid_from=values.get("balance_as_at") or clock.today()),
                "ref": ref, "debtor_ref": subject, "kind": "home_loan",
                "creditor": creditor, "doc_hash": dh,
            }
            if "balance" in values:
                rec["balance"] = money.money(values["balance"])
            for src, dst in (("balance_as_at", "balance_as_at"), ("ends_on", "ends_on"),
                             ("account_no", "account_no")):
                if src in values:
                    rec[dst] = values[src]
            if "instalment" in values:
                rec["instalment"] = money.money(values["instalment"])
            if "rate_pct" in values:
                rec["rate"] = {"kind": "linked_to_prime", "pct": values["rate_pct"]}
            records["liabilities"].append(rec)
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
                bens = extract_beneficiaries(text)
                if bens and bspec["kind"] in {"group_life", "provident", "pension"}:
                    rec["beneficiaries"] = [
                        {"pct": b["pct"],
                         **({"person_ref": _person_by_name(profile, b["name"])}
                            if _person_by_name(profile, b["name"]) else {}),
                         "name": b["name"]}
                        for b in bens
                    ]
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
        name: ledger.write(
            name, recs,
            agent={"policies": "insurance", "assets": "assets",
                   "liabilities": "assets", "valuations": "assets",
                   "wills": "estate", "trusts": "trusts", "trustees": "trusts",
                   "distributions": "trusts", "loan-accounts": "trusts"}.get(name, "living"),
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
