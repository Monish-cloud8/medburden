"""Write eval/verify_10.md: 10 eval cases with each drug's expected ACB score and Beers flags next to the source line,
so a person can check the answer key by hand.   python scripts/make_verify.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.score import tables  # noqa: E402

PICK = ["c01", "c03", "c05", "c09", "c12", "c14", "c16", "c18", "c24", "c25"]
SCOPE = {"all": "all older adults", "dementia": "dementia or cognitive impairment", "falls": "history of falls or fractures"}
ACB_PDF = "ACB scale 2012 update PDF (hii.iu.edu/resources/anticholinergic-cognitive-burden-scale.pdf)"


def acb_line(ing, acb):
    r = acb.get(ing)
    if not r:
        return "0 — not on the ACB scale"
    s = int(r["acb_score"])
    if s == 0:
        return f"0 — listed under 'reviewed but not added' "
    brands = f" ({r['brands_on_scale']})" if r["brands_on_scale"] else ""
    return f"**{s}** — score-{s} list: \"{r['name_on_scale']}{brands}\" "


def main():
    acb, beers, _ = tables()
    cases = {c["id"]: c for c in json.loads((ROOT / "tests/eval_set/cases.json").read_text())["cases"]}
    out = ["# Answer-key check: 10 eval cases", "",
           "For each drug: the expected ACB score and Beers flags, next to the line in the source they come from.",
           "Tick each box after checking it against the PDFs. Sources:",
           f"- ACB: {ACB_PDF}. Blocks: score 1, score 2, score 3, and 'reviewed but not added'.",
           "- Beers: 2023 AGS Beers Criteria, J Am Geriatr Soc 2023;71:2052-2081 (open access: pmc.ncbi.nlm.nih.gov/articles/PMC12478568).",
           "  Table 2 = drugs to avoid in older adults; Table 3 = drug-disease (dementia, falls); Table 7 = strong anticholinergics.",
           "- Labeling policy: a Beers flag is expected when the ingredient is listed in Table 2 (any patient), or in a Table 3 row",
           "  for a condition the patient has. Dose exemptions printed in Beers (doxepin <= 6 mg/day, digoxin <= 0.125 mg/day,",
           "  immediate-release nifedipine only) are applied. The ACB total sums unique ingredients.", ""]
    for cid in PICK:
        c = cases[cid]
        p, g = c["patient"], c["gold"]
        cond = ", ".join(k for k in ("dementia", "falls") if p[k]) or "none"
        out += [f"## {cid}: age {p['age']}, conditions: {cond}", "", "```", c["text"], "```", "",
                "| Drug (as written) | Ingredient | Expected ACB, source line | Expected Beers flag, source row | OK? |",
                "|---|---|---|---|---|"]
        for it in g["items"]:
            for ing in it["ingredients"] or ["(none: fictional)"]:
                flags = []
                for f in g["beers"]:
                    fi, sc = f.split("|")
                    if fi != ing:
                        continue
                    row = next((r for r in beers.get(ing, []) if r["applies_to"] == SCOPE[sc]), None)
                    flags.append(f"**{sc}** — {row['beers_table']}: {row['beers_row']}"
                                 + (f" (dose rule: {row['dose_rule']})" if row and row["dose_rule"] else "")
                                 if row else f"**{sc}** — NO TABLE ROW FOUND (check!)")
                exempt = [r for r in beers.get(ing, []) if r["dose_rule"] and not any(f.startswith(ing + "|") for f in g["beers"])]
                if exempt:
                    flags.append(f"none expected: {exempt[0]['beers_table']} {exempt[0]['beers_row']} applies only when "
                                 f"{exempt[0]['dose_rule'].replace('gt:', 'above ').replace(':mg', ' mg')}")
                acb_txt = acb_line(ing, acb) if not ing.startswith("(") else "n/a"
                out.append(f"| {it['name']} | {ing} | {acb_txt} | {'<br>'.join(flags) or '—'} | [ ] |")
        out += ["", f"**Expected ACB total: {g['acb_total']}** · Expected Beers flags: {', '.join(g['beers']) or 'none'}", ""]
    out += ["## Label change log", "",
            "No labels were changed in v2. Before v2, a script checked every label against the cited tables (scorer run on",
            "the gold ingredients); all 30 cases agreed. If you change a label, add a line here: case, old value,",
            "new value, why, and the source line.", ""]
    (ROOT / "eval").mkdir(exist_ok=True)
    (ROOT / "eval" / "verify_10.md").write_text("\n".join(out))
    print("wrote eval/verify_10.md")


if __name__ == "__main__":
    main()
