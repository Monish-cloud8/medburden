"""Rule-based scoring. Every flag comes from a row in data/*.csv, and the row's source is carried with it.

Inputs: extracted items (MedItem) + normalized results (NormResult) + patient context.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from functools import lru_cache

from .config import DATA, ACB_HIGH

BEERS_T5 = ("2023 AGS Beers Criteria (J Am Geriatr Soc. 2023;71(7):2052-2081), Table 5, row 5: "
            "any combination of 3 or more CNS-active drugs")
DUP_SOURCE = "MedBurden rule: the same active ingredient (from RxNorm) appears in more than one product"
EXTENDED_RE = re.compile(r"\b(er|xr|xl|sr|cr|la|cd|extended|sustained|controlled)\b", re.I)


@lru_cache(maxsize=1)
def tables():
    def read(fn):
        with open(DATA / fn) as f:
            return list(csv.DictReader(f))
    acb = {r["ingredient"].lower(): r for r in read("acb_scale.csv")}
    beers = defaultdict(list)
    for r in read("beers_2023.csv"):
        beers[r["ingredient"].lower()].append(r)
    cns = {r["ingredient"].lower(): r for r in read("cns_classes.csv")}
    return acb, beers, cns


@lru_cache(maxsize=1)
def interaction_rules():
    """Beers 2023 Table 5 rows with member lists expanded ('*opioid' = class in cns_classes.csv, '*t7' = Table 7)."""
    _, beers, cns = tables()
    t7 = {ing for ing, rows in beers.items() if any("Table 7" in r["drug_class"] for r in rows)}
    p = DATA / "beers_2023_interactions.csv"
    if not p.exists():
        return []

    def expand(spec):
        out = set()
        for tok in spec.split():
            if tok == "*t7":
                out |= t7
            elif tok.startswith("*"):
                out |= {i for i, r in cns.items() if r["beers_cns_class"] == tok[1:]}
            else:
                out.add(tok)
        return out
    with open(p) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["object_set"], r["interacting_set"] = expand(r["object_members"]), expand(r["interacting_members"])
    return rows


def strength_mg(strength: str) -> float | None:
    """First number in the strength, converted to mg. None if unknown."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|µg|ug|g)\b", strength or "", re.I)
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2).lower()
    return v / 1000 if u in ("mcg", "µg", "ug") else v * 1000 if u == "g" else v


def _dose_rule_applies(rule: str, strength: str) -> tuple[bool, str]:
    """rule like 'gt:6:mg' = flag only if strength > 6 mg. Returns (flag?, note)."""
    if not rule:
        return True, ""
    op, val, _unit = rule.split(":")
    mg = strength_mg(strength)
    if mg is None:
        return True, f"Strength not given; Beers flags this only above {val} mg, so please check the dose."
    if op == "gt":
        return (mg > float(val)), ("" if mg > float(val) else f"{mg:g} mg is at or below the Beers limit of {val} mg.")
    return True, ""


def score(items, norms, patient: dict | None = None) -> dict:
    """items: list of MedItem; norms: list of NormResult (same order).
    patient: {"age": int|None, "dementia": bool, "falls": bool}"""
    patient = patient or {}
    dementia, falls = bool(patient.get("dementia")), bool(patient.get("falls"))
    age = patient.get("age")
    acb_t, beers_t, cns_t = tables()

    rows, flags, unmatched, review = [], [], [], []
    ing_to_items = defaultdict(list)
    for idx, (it, nr) in enumerate(zip(items, norms)):
        if nr.status != "matched":
            (review if nr.status == "needs_review" else unmatched).append(
                {"item": idx, "drug": it.name, "status": nr.status, "suggestion": nr.matched_name, "note": nr.note})
            rows.append({"item": idx, "drug": it.name, "strength": it.strength, "frequency": it.frequency,
                         "ingredient": "—", "acb": None, "beers": [], "status": nr.status,
                         "reason": "Not scored: " + (nr.note or "no match"), "source": "RxNav (no confirmed match)"})
            continue
        written_extended = bool(EXTENDED_RE.search(it.name)) or bool(EXTENDED_RE.search(nr.matched_name or ""))
        ings = [i["name"] for i in nr.ingredients]
        for ing in dict.fromkeys(ings):
            ing_to_items[ing].append(idx)
            a = acb_t.get(ing)
            acb = int(a["acb_score"]) if a else 0
            beers_hits = []
            for b in beers_t.get(ing, []):
                scope = b["applies_to"]
                if scope.startswith("dementia") and not dementia:
                    continue
                if scope.startswith("history of falls") and not falls:
                    continue
                if ing == "nifedipine" and written_extended:
                    continue          # Beers applies to immediate-release nifedipine only
                if ing == "dipyridamole" and "aspirin" in ings:
                    continue          # Beers excludes extended-release dipyridamole + aspirin
                ok, note = _dose_rule_applies(b["dose_rule"], it.strength)
                if not ok:
                    continue
                beers_hits.append({"table": b["beers_table"], "applies_to": scope, "drug_class": b["drug_class"],
                                   "recommendation": b["recommendation"], "reason": b["reason_plain"],
                                   "conditions": " ".join(x for x in (b["conditions_note"], note) if x),
                                   "source": b["source"]})
            rows.append({
                "item": idx, "drug": it.name, "strength": it.strength, "frequency": it.frequency,
                "ingredient": ing, "rxcui": next((i["rxcui"] for i in nr.ingredients if i["name"] == ing), ""),
                "acb": acb, "acb_source": a["source"] if a else "Not on the ACB scale (counted as 0)",
                "beers": beers_hits, "status": "matched",
                "reason": "; ".join(dict.fromkeys(h["reason"] for h in beers_hits)),
                "source": "; ".join(dict.fromkeys(
                    ([f"ACB scale 2012 (score {acb})"] if a and acb > 0 else []) +
                    [h["source"].split(". J Am")[0].replace("2023 American Geriatrics Society Beers Criteria Update Expert Panel. ", "") +
                     " " + h["table"] for h in beers_hits])) or "—",
            })
            for h in beers_hits:
                flags.append({"type": "beers", "ingredient": ing, "drug": it.name, **h})

    # duplicates
    for ing, idxs in ing_to_items.items():
        if len(set(idxs)) >= 2:
            names = [items[i].name for i in dict.fromkeys(idxs)]
            flags.append({"type": "duplicate", "ingredient": ing, "drug": " and ".join(names),
                          "reason": f"{', '.join(names)} all contain {ing}. Taking them together can mean a double dose.",
                          "source": DUP_SOURCE})

    # CNS-active stacking (Beers 2023 Table 5)
    cns_present = {ing: cns_t[ing] for ing in ing_to_items if ing in cns_t}
    if len(cns_present) >= 3:
        flags.append({"type": "sedation_stack", "ingredient": ", ".join(sorted(cns_present)),
                      "drug": ", ".join(items[ing_to_items[i][0]].name for i in sorted(cns_present)),
                      "reason": (f"{len(cns_present)} medicines that act on the brain (antiepileptics, antidepressants, antipsychotics, "
                                 "benzodiazepines, Z-drugs, opioids or muscle relaxants). Beers advises avoiding 3 or more together "
                                 "because it raises the risk of falls and fractures."),
                      "source": BEERS_T5})
    # Beers Table 5 pair rows (opioid + benzodiazepine, anticholinergic + anticholinergic, warfarin + SSRI, ...)
    present = set(ing_to_items)
    low_dose_doxepin = {ing for ing in present if ing == "doxepin" and all(
        (strength_mg(items[k].strength) or 99) <= 6 for k in ing_to_items[ing])}
    for rule in interaction_rules():
        obj = sorted((present & rule["object_set"]) - (low_dose_doxepin if "*t7" in rule["object_members"] else set()))
        oth = sorted((present & rule["interacting_set"]) - (low_dose_doxepin if "*t7" in rule["interacting_members"] else set()))
        pairs = [(a, b) for a in obj for b in oth if a != b]
        if not pairs:
            continue
        ings = sorted({x for pr in pairs for x in pr})
        kind = "sedation_stack" if rule["rule_id"] in ("T5-2", "T5-3") else "interaction"
        flags.append({"type": kind, "rule_id": rule["rule_id"], "ingredient": ", ".join(ings),
                      "drug": " + ".join(dict.fromkeys(items[ing_to_items[x][0]].name for x in ings)),
                      "reason": rule["reason_plain"], "conditions": rule["recommendation"], "source": rule["source"]})

    acb_by_ing = {}
    for r in rows:
        if r["status"] == "matched":
            acb_by_ing[r["ingredient"]] = r["acb"]
    total = sum(acb_by_ing.values())
    level = "high" if total >= ACB_HIGH else "moderate" if total >= 1 else "low"
    return {
        "rows": rows, "flags": flags, "unmatched": unmatched, "needs_review": review,
        "acb_total": total, "acb_level": level,
        "acb_contributors": {k: v for k, v in acb_by_ing.items() if v > 0},
        "acb_incomplete": bool(unmatched or review),
        "patient": {"age": age, "dementia": dementia, "falls": falls},
        "age_note": ("The Beers Criteria are written for adults aged 65 and older." if age is not None and age < 65 else ""),
    }


def beers_flag_set(report: dict) -> set[tuple[str, str]]:
    """(ingredient, scope) pairs, scope in {all, dementia, falls}. Used by the evaluation."""
    m = {"all older adults": "all", "dementia or cognitive impairment": "dementia", "history of falls or fractures": "falls"}
    return {(f["ingredient"], m[f["applies_to"]]) for f in report["flags"] if f["type"] == "beers"}
