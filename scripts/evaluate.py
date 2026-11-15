"""Evaluate MedBurden on tests/eval_set and compare with an LLM-only baseline.

python scripts/evaluate.py                 # LLM extraction + LLM-only baseline if a key is set; RxNav if reachable
python scripts/evaluate.py --offline       # no RxNav calls (cache + local brand map / tables only)
python scripts/evaluate.py --no-llm        # rule-based parser / OCR for extraction
python scripts/evaluate.py --no-baseline   # skip the LLM-only baseline

Writes results/metrics.json, report.md, comparison.csv, comparison.png, unmatched.csv, beers_misses.csv
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import EVAL_DIR, RESULTS  # noqa: E402
from src.extract import extract, llm_provider, llm_status, call_llm, parse_json_reply, ocr_status  # noqa: E402
from src.normalize import RxNavClient, normalize_all, simplify  # noqa: E402
from src.score import score, beers_flag_set, tables  # noqa: E402

BASELINE_PROMPT = """You are helping a family caregiver of an older adult. Using only your own knowledge (no tools), read the
medication list or photo and return ONLY JSON:
{"items": [{"name_as_written": str, "ingredients": [generic active ingredient names, lowercase]}],
 "acb_total": int,
 "flags": [{"ingredient": "generic name, lowercase", "scope": "all|dementia|falls"}]}
- items: every medicine on the list with its active ingredient(s). If you do not recognise a name, give "ingredients": [].
- acb_total: the total Anticholinergic Cognitive Burden (ACB) scale score, summed over unique active ingredients.
- flags: every active ingredient the 2023 AGS Beers Criteria say to avoid in older adults (scope "all"), plus those to avoid
  in dementia or cognitive impairment (scope "dementia", only if the patient has dementia) and after falls or fractures
  (scope "falls", only if the patient has had falls)."""

SCOPE = {"all older adults": "all", "dementia or cognitive impairment": "dementia", "history of falls or fractures": "falls"}


def name_match(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or difflib.SequenceMatcher(None, simplify(a), simplify(b)).ratio() >= 0.85


def pair_items(gold_items, extracted_names, lenient=False):
    """Greedy one-to-one pairing of gold items to extracted names.
    lenient=True (used for the LLM-only baseline, which often repeats the whole line, doses included) also accepts a
    written line that contains the gold name, so the baseline is not marked wrong for formatting."""
    used, pairs = set(), {}
    for gi, g in enumerate(gold_items):
        for ei, e in enumerate(extracted_names):
            ok = name_match(g["name"], e) or (lenient and g["name"].lower().strip() in e.lower())
            if ei not in used and ok:
                pairs[gi] = ei
                used.add(ei)
                break
    return pairs


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    return p, r


def miss_reason(ing, scope, gold, items, norms, pairs) -> str:
    """Why MedBurden missed a gold Beers flag."""
    gi = next((i for i, g in enumerate(gold["items"]) if ing in g["ingredients"]), None)
    if gi is None:
        return "label references an ingredient not in any gold item"
    if gi not in pairs:
        return "not extracted from the list"
    nr = norms[pairs[gi]]
    if nr.status != "matched":
        return f"no match ({nr.status})"
    if ing not in {i["name"] for i in nr.ingredients}:
        return "matched to the wrong ingredients"
    _, beers, _ = tables()
    if not any(SCOPE[r["applies_to"]] == scope for r in beers.get(ing, [])):
        return "missing table row"
    return "row exists but condition or dose logic did not fire"


def run(offline=False, use_llm=True, baseline=True, out_dir=RESULTS, eval_dir=EVAL_DIR, client=None, quiet=False):
    t0 = time.time()
    log = (lambda *a: None) if quiet else print
    cases = json.loads((eval_dir / "cases.json").read_text())["cases"]
    client = client or RxNavClient(offline=offline)
    st = llm_status() if (use_llm or baseline) else {"ok": False, "message": "LLM disabled"}
    tot = dict(gold_items=0, extracted=0, ext_tp=0, real_items=0, rx_ok=0, rx_any=0, acb_exact=0,
               b_tp=0, b_fp=0, b_fn=0, unm_total=0, unm_flagged=0, unm_wrongly_matched=0, cases=0)
    bt = dict(n=0, errors=0, real_items=0, ing_ok=0, acb_exact=0, b_tp=0, b_fp=0, b_fn=0, unm_total=0, unm_flagged=0)
    methods, per_case, unmatched_rows, miss_rows = {}, [], [], []
    run_baseline = baseline and st["ok"]

    for c in cases:
        gold = c["gold"]
        img = (eval_dir / "images" / f"{c['id']}.png").read_bytes() if c["input"] == "image" else None
        items, method, warns = extract(text=None if img else c["text"], image_bytes=img, use_llm=use_llm and st["ok"])
        methods[method] = methods.get(method, 0) + 1
        norms = normalize_all([i.name for i in items], client)
        rep = score(items, norms, c["patient"])

        pairs = pair_items(gold["items"], [i.name for i in items])
        tot["cases"] += 1
        tot["gold_items"] += len(gold["items"])
        tot["extracted"] += len(items)
        tot["ext_tp"] += len(pairs)
        for gi, g in enumerate(gold["items"]):
            nr = norms[pairs[gi]] if gi in pairs else None
            expected = g["name"] in gold["expected_unmatched"]
            if nr is None or nr.status != "matched":
                unmatched_rows.append({"case": c["id"], "written": items[pairs[gi]].name if gi in pairs else f"(not extracted: {g['name']})",
                                       "status": nr.status if nr else "not extracted", "expected": "yes" if expected else "no",
                                       "gold_ingredients": ";".join(g["ingredients"]), "note": nr.note if nr else ""})
            if expected:
                tot["unm_total"] += 1
                if nr is None or nr.status != "matched":
                    tot["unm_flagged"] += 1
                else:
                    tot["unm_wrongly_matched"] += 1
                continue
            tot["real_items"] += 1
            if nr is not None and nr.status == "matched":
                tot["rx_any"] += 1
                if {i["name"] for i in nr.ingredients} == set(g["ingredients"]):
                    tot["rx_ok"] += 1
        tot["acb_exact"] += rep["acb_total"] == gold["acb_total"]
        pred = {f"{a}|{b}" for a, b in beers_flag_set(rep)}
        gs = set(gold["beers"])
        tot["b_tp"] += len(pred & gs)
        tot["b_fp"] += len(pred - gs)
        tot["b_fn"] += len(gs - pred)
        for f in sorted(gs - pred):
            ing, scope = f.split("|")
            miss_rows.append({"case": c["id"], "kind": "missed", "flag": f, "reason": miss_reason(ing, scope, gold, items, norms, pairs)})
        for f in sorted(pred - gs):
            miss_rows.append({"case": c["id"], "kind": "extra (false positive)", "flag": f, "reason": "flag not in answer key"})
        row = {"id": c["id"], "input": c["input"], "method": method, "extracted": [i.name for i in items],
               "statuses": [n.status for n in norms], "match_methods": [n.method for n in norms],
               "acb": rep["acb_total"], "acb_gold": gold["acb_total"],
               "beers_fp": sorted(pred - gs), "beers_fn": sorted(gs - pred), "warnings": warns}

        if run_baseline:
            bt["n"] += 1
            try:
                pt = c["patient"]
                user = (f"Patient: age {pt['age']}, dementia: {'yes' if pt['dementia'] else 'no'}, "
                        f"history of falls: {'yes' if pt['falls'] else 'no'}.\n")
                user += "Medication list: see the photo." if img else f"Medication list:\n{c['text']}"
                bj = parse_json_reply(call_llm(BASELINE_PROMPT, user, image_bytes=img, max_tokens=1500))
                bitems = bj.get("items", []) or []
                bpairs = pair_items(gold["items"], [str(b.get("name_as_written", "")) for b in bitems], lenient=True)
                for gi, g in enumerate(gold["items"]):
                    bings = {str(x).lower().strip() for x in bitems[bpairs[gi]].get("ingredients", [])} if gi in bpairs else set()
                    if g["name"] in gold["expected_unmatched"]:
                        bt["unm_total"] += 1
                        bt["unm_flagged"] += not bings
                    else:
                        bt["real_items"] += 1
                        bt["ing_ok"] += bings == set(g["ingredients"])
                bpred = {f"{str(f.get('ingredient', '')).lower().strip()}|{str(f.get('scope', '')).lower().strip()}"
                         for f in bj.get("flags", []) or []}
                try:
                    bacb = int(bj.get("acb_total", -1))
                except (TypeError, ValueError):
                    bacb = -1
                bt["acb_exact"] += bacb == gold["acb_total"]
                bt["b_tp"] += len(bpred & gs)
                bt["b_fp"] += len(bpred - gs)
                bt["b_fn"] += len(gs - bpred)
                row["baseline"] = {"acb": bacb, "fp": sorted(bpred - gs), "fn": sorted(gs - bpred)}
            except Exception as e:
                bt["errors"] += 1
                row["baseline_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        per_case.append(row)
        log(f"  {c['id']}: {method:12s} acb {rep['acb_total']} (gold {gold['acb_total']}) "
            f"beers fp={len(pred - gs)} fn={len(gs - pred)}" + (f" | baseline acb {row['baseline']['acb']}" if "baseline" in row else ""))

    bp, br = prf(tot["b_tp"], tot["b_fp"], tot["b_fn"])
    ep, er = prf(tot["ext_tp"], tot["extracted"] - tot["ext_tp"], tot["gold_items"] - tot["ext_tp"])
    m = {
        "setup": {
            "cases": tot["cases"], "image_cases": sum(c["input"] == "image" for c in cases),
            "extraction_methods": methods, "llm": st, "ocr": ocr_status(),
            "rxnav": "offline (forced)" if offline else ("reachable" if client.reachable else "NOT reachable (cache + local brand map only)"),
            "rxnav_stats": client.stats, "runtime_s": round(time.time() - t0, 1)},
        "medburden": {
            "extraction_precision": ep, "extraction_recall": er,
            "extraction_items": f"{tot['ext_tp']}/{tot['gold_items']} gold items found; {tot['extracted']} extracted",
            "rxnav_match_rate": tot["rx_ok"] / tot["real_items"] if tot["real_items"] else float("nan"),
            "rxnav_any_match_rate": tot["rx_any"] / tot["real_items"] if tot["real_items"] else float("nan"),
            "rxnav_items": f"{tot['rx_ok']}/{tot['real_items']} real drugs matched with exactly the right ingredients",
            "acb_exact_match_rate": tot["acb_exact"] / tot["cases"],
            "beers_precision": bp, "beers_recall": br,
            "beers_counts": {"tp": tot["b_tp"], "fp": tot["b_fp"], "fn": tot["b_fn"]},
            "unmatched_correctly_flagged": f"{tot['unm_flagged']}/{tot['unm_total']}",
            "fictional_drugs_wrongly_matched": tot["unm_wrongly_matched"]},
        "llm_only_baseline": None,
        "llm_only_baseline_skipped": None if run_baseline else (st["message"] if baseline else "skipped (--no-baseline)"),
        "per_case": per_case,
    }
    if run_baseline and bt["n"]:
        bbp, bbr = prf(bt["b_tp"], bt["b_fp"], bt["b_fn"])
        m["llm_only_baseline"] = {
            "provider": st["provider"], "model": st["model"], "cases": bt["n"], "errors": bt["errors"],
            "ingredient_match_rate": bt["ing_ok"] / bt["real_items"] if bt["real_items"] else float("nan"),
            "acb_exact_match_rate": bt["acb_exact"] / bt["n"], "beers_precision": bbp, "beers_recall": bbr,
            "beers_counts": {"tp": bt["b_tp"], "fp": bt["b_fp"], "fn": bt["b_fn"]},
            "unmatched_correctly_flagged": f"{bt['unm_flagged']}/{bt['unm_total']}"}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(m, indent=1, default=str))
    (out_dir / "report.md").write_text(report_md(m))
    _write_csv(out_dir / "unmatched.csv", ["case", "written", "status", "expected", "gold_ingredients", "note"], unmatched_rows)
    _write_csv(out_dir / "beers_misses.csv", ["case", "kind", "flag", "reason"], miss_rows)
    write_comparison(m, out_dir)
    if out_dir == RESULTS:
        update_readme(m)

    log("\nDrugs not matched:" if unmatched_rows else "\nAll drugs matched.")
    for u in unmatched_rows:
        log(f"  {u['case']}: {u['written']:28s} {u['status']:13s} expected unmatched: {u['expected']}")
    log("Beers misses / extras:" if miss_rows else "No Beers misses or extra flags.")
    for r in miss_rows:
        log(f"  {r['case']}: {r['kind']:22s} {r['flag']:28s} {r['reason']}")
    if not run_baseline:
        log(f"LLM-only baseline skipped: {m['llm_only_baseline_skipped']}")
    log(f"Wrote results to {out_dir}")
    return m


def _write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


COMPARE = [("Ingredient match", "rxnav_match_rate", "ingredient_match_rate"),
           ("ACB total exact", "acb_exact_match_rate", "acb_exact_match_rate"),
           ("Beers precision", "beers_precision", "beers_precision"),
           ("Beers recall", "beers_recall", "beers_recall")]


def write_comparison(m, out_dir):
    r, b = m["medburden"], m["llm_only_baseline"]
    rows = [{"metric": lab, "medburden": round(r[k1], 4),
             "llm_only": round(b[k2], 4) if b else "",
             "note": "" if b else f"LLM-only not run: {m['llm_only_baseline_skipped']}"} for lab, k1, k2 in COMPARE]
    _write_csv(out_dir / "comparison.csv", ["metric", "medburden", "llm_only", "note"], rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7.5, 3.6), dpi=150)
        x = range(len(rows))
        w = 0.38 if b else 0.55
        mb = [row["medburden"] * 100 for row in rows]
        ax.bar([i - (w / 2 if b else 0) for i in x], mb, w, label="MedBurden (rules + tables)", color="#2F6F8F")
        for i, v in zip(x, mb):
            ax.text(i - (w / 2 if b else 0), v + 1.5, f"{v:.0f}%", ha="center", fontsize=8)
        if b:
            lb = [row["llm_only"] * 100 for row in rows]
            ax.bar([i + w / 2 for i in x], lb, w, label=f"LLM only ({b['model']})", color="#C9A227")
            for i, v in zip(x, lb):
                ax.text(i + w / 2, v + 1.5, f"{v:.0f}%", ha="center", fontsize=8)
        ax.set_xticks(list(x), [row["metric"] for row in rows], fontsize=9)
        ax.set_ylim(0, 112)
        ax.set_ylabel("%")
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
        sub = "" if b else "\n(LLM-only baseline not run: no API key set)"
        ax.set_title(f"MedBurden vs LLM-only on {m['setup']['cases']} medication lists{sub}", fontsize=10)
        fig.tight_layout()
        fig.savefig(out_dir / "comparison.png")
        plt.close(fig)
    except Exception as e:  # chart is optional; csv is the source of truth
        print(f"(chart not written: {e})")


def update_readme(m):
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    rep = report_md(m)
    block = rep[rep.index("**Run conditions"): rep.index("## Cases with any error")].strip()
    t = readme.read_text()
    a, b = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    if a in t and b in t:
        readme.write_text(t[: t.index(a) + len(a)] + "\n" + block + "\n" + t[t.index(b):])


def _f(x):
    return "n/a" if x is None or x != x else f"{100 * x:.0f}%"


def report_md(m: dict) -> str:
    s, r, b = m["setup"], m["medburden"], m["llm_only_baseline"]
    brow = (f"| LLM only ({b['model']}, no tables) | n/a | {_f(b['ingredient_match_rate'])} | {_f(b['acb_exact_match_rate'])} | "
            f"{_f(b['beers_precision'])} | {_f(b['beers_recall'])} |") if b else \
        f"| LLM only (no tables) | not run: {m.get('llm_only_baseline_skipped')} | | | | |"
    fails = [c for c in m["per_case"] if c["acb"] != c["acb_gold"] or c["beers_fp"] or c["beers_fn"]]
    fail_lines = "\n".join(f"- {c['id']} ({c['input']}, {c['method']}): extracted {c['extracted']}, statuses {c['statuses']}; "
                           f"ACB {c['acb']} vs gold {c['acb_gold']}; missed {c['beers_fn']}; extra {c['beers_fp']}"
                           for c in fails) or "- none"
    llm = s["llm"]
    return f"""# MedBurden evaluation

{s['cases']} made-up medication lists ({s['image_cases']} as photos). Labels written by hand; see tests/eval_set/cases.json and eval/verify_10.md.

**Run conditions:** extraction = {s['extraction_methods']}; RxNav = {s['rxnav']}; LLM = {llm['message']}; OCR = {s['ocr']['message'].rstrip('.')}.

| System | Drug extraction (precision / recall) | Ingredient match (exactly right) | ACB total exact | Beers precision | Beers recall |
|---|---|---|---|---|---|
| MedBurden (rules + tables) | {_f(r['extraction_precision'])} / {_f(r['extraction_recall'])} | {_f(r['rxnav_match_rate'])} ({r['rxnav_items']}) | {_f(r['acb_exact_match_rate'])} | {_f(r['beers_precision'])} | {_f(r['beers_recall'])} |
{brow}

- Fictional drug names correctly left unmatched: **{r['unmatched_correctly_flagged']}** (wrongly matched: {r['fictional_drugs_wrongly_matched']}).
- Beers counts (MedBurden): {r['beers_counts']}.
- Medicines that are unmatched or need review are never scored. MedBurden does not guess.

## Cases with any error
{fail_lines}

## Caveats
- The same team wrote the tables and the labels, so this measures whether the pipeline applies the cited rules correctly. It does not independently validate the tables. Spot-check the labels with eval/verify_10.md.
- 30 cases is small. Treat these as smoke-test numbers, not clinical accuracy.
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--eval-dir", default=str(EVAL_DIR))
    ap.add_argument("--out-dir", default=str(RESULTS))
    a = ap.parse_args()
    run(offline=a.offline, use_llm=not a.no_llm, baseline=not a.no_baseline,
        eval_dir=Path(a.eval_dir), out_dir=Path(a.out_dir))
