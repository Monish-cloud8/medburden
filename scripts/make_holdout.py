"""Builds tests/eval_set_holdout/cases.json (HELD-OUT set: brands NOT in data/brand_map.csv, messy input).

Gold labels come from the small hand-written knowledge table KB below (ACB score from the 2012 scale PDF; Beers flags from
the 2023 Beers tables). It is deliberately separate from data/*.csv so the check is not circular, but the same person
wrote both, so read the README caveat. Run:  python scripts/make_holdout.py
Every brand/generic used must be absent from data/brand_map.csv (checked below), so the offline brand map cannot help.
"""
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

# ingredient: (ACB score, Beers Table 2 'all', Table 3 'dementia', Table 3 'falls')
T, F = True, False
KB = {
 "oxybutynin": (3, F, T, T), "lorazepam": (0, T, T, T), "amitriptyline": (3, T, T, T), "hydroxyzine": (3, T, T, T),
 "donepezil": (0, F, F, F), "meclizine": (3, T, T, T), "trazodone": (1, F, F, F), "gabapentin": (0, F, F, T),
 "zolpidem": (0, T, T, T), "risperidone": (1, T, T, T), "fentanyl": (1, F, F, T), "tapentadol": (0, F, F, T),
 "sumatriptan": (0, F, F, F), "simvastatin": (0, F, F, F), "lisinopril": (0, F, F, F), "hydrochlorothiazide": (0, F, F, F), "paroxetine": (3, T, T, T), "escitalopram": (0, F, F, T),
 "chlorzoxazone": (0, T, F, F), "fluoxetine": (0, F, F, T), "doxazosin": (0, T, F, F), "milnacipran": (0, F, F, T), "pravastatin": (0, F, F, F),
 "dicyclomine": (3, T, T, T), "hyoscyamine": (3, T, T, T), "flavoxate": (3, F, T, T), "trihexyphenidyl": (3, T, T, T),
 "imipramine": (3, T, T, T), "desipramine": (3, T, T, T), "clomipramine": (3, T, T, T), "clozapine": (3, T, T, T),
 "chlorpromazine": (3, T, T, T), "perphenazine": (3, T, T, T), "prochlorperazine": (0, F, T, T), "orphenadrine": (3, T, T, T),
 "carbamazepine": (2, F, F, T), "oxcarbazepine": (2, F, F, T), "phenytoin": (0, F, F, T), "valproic acid": (0, F, F, T),
 "levetiracetam": (0, F, F, T), "lamotrigine": (0, F, F, T), "topiramate": (0, F, F, T), "clorazepate": (1, T, T, T),
 "chlordiazepoxide": (0, T, T, T), "estazolam": (0, T, T, T), "amiodarone": (0, T, F, F), "clonidine": (0, T, F, F),
 "prazosin": (0, T, F, F), "terazosin": (0, T, F, F), "guanfacine": (0, T, F, F), "digoxin": (1, F, F, F),
 "pioglitazone": (0, F, F, F), "sitagliptin": (0, F, F, F), "estradiol": (0, T, F, F), "conjugated estrogens": (0, T, F, F),
 "megestrol": (0, T, F, F), "desmopressin": (0, T, F, F), "ketorolac": (0, T, F, F), "diclofenac": (0, T, F, F),
 "naproxen": (0, T, F, F), "piroxicam": (0, T, F, F), "indomethacin": (0, T, F, F), "meperidine": (2, T, F, T),
 "tramadol": (0, F, F, T), "hydrocodone": (0, F, F, T), "oxycodone": (0, F, F, T), "morphine": (1, F, F, T),
 "hydromorphone": (0, F, F, T), "metoclopramide": (0, T, F, F), "lansoprazole": (0, T, F, F), "rabeprazole": (0, T, F, F),
 "sertraline": (0, F, F, T), "citalopram": (0, F, F, T), "fluoxetine": (0, F, F, T), "ziprasidone": (0, T, T, T),
 "lurasidone": (0, T, T, T), "paliperidone": (1, T, T, T), "aripiprazole": (1, T, T, T), "phenobarbital": (0, T, F, T),
 "butalbital": (0, T, F, F), "acetaminophen": (0, F, F, F), "diphenhydramine": (3, T, T, T), "carisoprodol": (0, T, F, F),
 "baclofen": (0, F, F, F), "montelukast": (0, F, F, F), "alendronate": (0, F, F, F), "tiotropium": (0, F, F, F),
 "ropinirole": (0, F, F, F), "pramipexole": (0, F, F, F), "warfarin": (1, T, F, F), "rivaroxaban": (0, T, F, F),
 "loperamide": (1, F, F, F), "colchicine": (1, F, F, F), "prednisone": (1, F, F, F), "hydralazine": (1, F, F, F),
 "nifedipine": (1, T, F, F), "metoprolol": (1, F, F, F), "furosemide": (1, F, F, F), "ramipril": (0, F, F, F),
 "valsartan": (0, F, F, F), "clopidogrel": (0, F, F, F), "gemfibrozil": (0, F, F, F), "ezetimibe": (0, F, F, F),
 "allopurinol": (0, F, F, F), "tizanidine": (0, F, F, F), "ropivacaine": (0, F, F, F), "ranolazine": (0, F, F, F),
 "buspirone": (0, F, F, F), "venlafaxine": (1, F, F, T), "lithium": (0, F, F, F), "sucralfate": (0, F, F, F),
}

# Each case: (age, dementia, falls, [(line as written, name for the key, [ingredients] or None if it should stay unidentified)])
# Messy on purpose: abbreviations (bid/qhs), doses glued to names, typos, ER/XR, mixed case, brands not in brand_map.csv.
N = None
CASES = [
 (80, 1, 0, [("Bentyl 20mg qid", "Bentyl", ["dicyclomine"]), ("Actos 30 mg daily", "Actos", ["pioglitazone"]), ("Januvia 100mg", "Januvia", ["sitagliptin"])]),
 (78, 0, 1, [("Depakote ER 500 mg bid", "Depakote", ["valproic acid"]), ("Keppra 500mg twice a day", "Keppra", ["levetiracetam"]), ("Requip 1 mg hs", "Requip", ["ropinirole"])]),
 (83, 0, 0, [("Catapres 0.1 mg bid", "Catapres", ["clonidine"]), ("MINIPRESS 1mg qhs", "Minipress", ["prazosin"]), ("Procardia 10 mg tid", "Procardia", ["nifedipine"])]),
 (85, 1, 0, [("Tegretol XR 200 mg bid", "Tegretol", ["carbamazepine"]), ("Levsin 0.125mg prn", "Levsin", ["hyoscyamine"]), ("Urispas 100 mg tid", "Urispas", ["flavoxate"])]),
 (76, 0, 0, [("Megace 40 mg daily", "Megace", ["megestrol"]), ("Premarin 0.625mg daily", "Premarin", ["conjugated estrogens"]), ("DDAVP 0.2 mg at bedtime", "DDAVP", ["desmopressin"])]),
 (81, 0, 1, [("Demerol 50 mg q4h prn", "Demerol", ["meperidine"]), ("Toradol 10mg q6h", "Toradol", ["ketorolac"]), ("Singulair 10mg daily", "Singulair", ["montelukast"])]),
 (74, 0, 0, [("Fosamax 70 mg weekly", "Fosamax", ["alendronate"]), ("Spiriva 18 mcg inhaled daily", "Spiriva", ["tiotropium"]), ("Zetia 10mg", "Zetia", ["ezetimibe"])]),
 (79, 1, 0, [("Artane 2 mg three times daily", "Artane", ["trihexyphenidyl"]), ("Clozaril 25mg at night", "Clozaril", ["clozapine"]), ("Zyloprim 100 mg daily", "Zyloprim", ["allopurinol"])]),
 (77, 1, 1, [("Tofranil 25mg HS", "Tofranil", ["imipramine"]), ("Norpramin 50 mg daily", "Norpramin", ["desipramine"]), ("Prevacid 30 mg qd", "Prevacid", ["lansoprazole"])]),
 (84, 1, 0, [("Thorazine 25 mg twice daily", "Thorazine", ["chlorpromazine"]), ("Compazine 10mg prn nausea", "Compazine", ["prochlorperazine"]), ("Pexeva 10 mg daily", "Pexeva", ["paroxetine"])]),
 (82, 0, 1, [("Norflex ER 100mg bid", "Norflex", ["orphenadrine"]), ("Tranxene 7.5 mg hs", "Tranxene", ["clorazepate"]), ("Lioresal 10 mg tid", "Lioresal", ["baclofen"])]),
 (80, 1, 1, [("Librium 10mg tid prn", "Librium", ["chlordiazepoxide"]), ("Zyloprim 100mg", "Zyloprim", ["allopurinol"]), ("Colcrys 0.6 mg daily", "Colcrys", ["colchicine"])]),
 (85, 0, 0, [("Cordarone 200 mg daily", "Cordarone", ["amiodarone"]), ("Tenex 1mg qd", "Tenex", ["guanfacine"]), ("Altace 5 mg daily", "Altace", ["ramipril"])]),
 (78, 0, 1, [("Duragesic 25 mcg patch q72h", "Duragesic", ["fentanyl"]), ("Dilaudid 2mg q4h prn", "Dilaudid", ["hydromorphone"]), ("Zetia 10 mg", "Zetia", ["ezetimibe"])]),
 (81, 1, 0, [("Geodon 40 mg bid", "Geodon", ["ziprasidone"]), ("Latuda 20mg daily", "Latuda", ["lurasidone"]), ("Invega 3 mg qam", "Invega", ["paliperidone"])]),
 (79, 0, 0, [("Aciphex 20 mg daily", "Aciphex", ["rabeprazole"]), ("Metozolv 10mg ac", "Metozolv", ["metoclopramide"]), ("Diovan 80 mg daily", "Diovan", ["valsartan"])]),
 (83, 1, 1, [("Excedrin PM 2 caplets qhs", "Excedrin PM", ["acetaminophen", "diphenhydramine"]), ("Tegretol 100mg", "Tegretol", ["carbamazepine"]), ("Prozac Weekly 90 mg", "Prozac Weekly", ["fluoxetine"])]),
 (75, 0, 0, [("Fioricet 1 tab q6h prn", "Fioricet", ["acetaminophen", "butalbital"]), ("Naprosyn 500mg bid", "Naprosyn", ["naproxen"]), ("Feldene 20 mg daily", "Feldene", ["piroxicam"])]),
 (72, 0, 1, [("Lamictal 100 mg bid", "Lamictal", ["lamotrigine"]), ("Topamax 25mg hs", "Topamax", ["topiramate"]), ("BuSpar 10 mg tid", "BuSpar", ["buspirone"])]),
 (79, 1, 0, [("Dilantin 100mg tid", "Dilantin", ["phenytoin"]), ("Mirapex 0.25 mg hs", "Mirapex", ["pramipexole"]), ("Lopid 600 mg bid", "Lopid", ["gemfibrozil"])]),
 (82, 0, 0, [("doxazocin 2mg hs", "doxazocin", ["doxazosin"]), ("Tenex 1 mg qd", "Tenex", ["guanfacine"]), ("Lopid 600mg bid", "Lopid", ["gemfibrozil"])]),
 (77, 0, 1, [("Luminal 30 mg bid", "Luminal", ["phenobarbital"]), ("Parafon Forte 500mg tid", "Parafon Forte", ["chlorzoxazone"]), ("Zyloprim 300 mg", "Zyloprim", ["allopurinol"])]),
 (76, 0, 0, [("Estrace 1mg daily", "Estrace", ["estradiol"]), ("Indocin 25 mg tid", "Indocin", ["indomethacin"]), ("Altace 5mg daily", "Altace", ["ramipril"])]),
 (80, 0, 1, [("Voltaren 75mg bid", "Voltaren", ["diclofenac"]), ("Ultracet 1 tab q6h prn", "Ultracet", ["acetaminophen", "tramadol"]), ("Savella 50 mg bid", "Savella", ["milnacipran"])]),
 (83, 1, 1, [("Zolvarex 20 mg nightly", "Zolvarex", N), ("Nexaprine 5mg", "Nexaprine", N), ("Dilaudid 4 mg prn", "Dilaudid", ["hydromorphone"])]),
 (78, 1, 0, [("Imitrex 50 mg prn", "Imitrex", ["sumatriptan"]), ("Tizanidine 2mg tid", "Tizanidine", ["tizanidine"]), ("Carafate 1 g qid", "Carafate", ["sucralfate"])]),
 # typos in generic names
 (84, 1, 1, [("Diphenhydramin 25mg qhs", "Diphenhydramin", ["diphenhydramine"]), ("oxybutinin 5 mg bid", "oxybutinin", ["oxybutynin"]), ("lorazapam 0.5mg hs", "lorazapam", ["lorazepam"])]),
 (81, 1, 0, [("amitriptylin 25 mg hs", "amitriptylin", ["amitriptyline"]), ("hydroxyzin pamoate 25mg tid", "hydroxyzin", ["hydroxyzine"]), ("donepezyl 10 mg qd", "donepezyl", ["donepezil"])]),
 (79, 0, 1, [("trazadone 50mg hs", "trazadone", ["trazodone"]), ("gabapentine 300 mg tid", "gabapentine", ["gabapentin"]), ("tramadole 50 mg q6h", "tramadole", ["tramadol"])]),
 (77, 1, 1, [("meclizin 25mg tid prn", "meclizin", ["meclizine"]), ("zolpidum 5 mg hs", "zolpidum", ["zolpidem"]), ("rispiridone 0.5 mg bid", "rispiridone", ["risperidone"])]),
 (74, 0, 0, [("hydrocodone/apap 5/325 q6h prn", "hydrocodone/apap", ["acetaminophen", "hydrocodone"]), ("Zestoretic 10/12.5 daily", "Zestoretic", ["lisinopril", "hydrochlorothiazide"]), ("Pravachol 20mg", "Pravachol", ["pravastatin"])]),
]


def build():
    bm = {r["brand"].strip().lower() for r in csv.DictReader(open(ROOT / "data" / "brand_map.csv"))} if False else None
    rows = list(csv.reader(open(ROOT / "data" / "brand_map.csv")))
    in_map = {r[0].strip().lower() for r in rows[1:]}
    out, leaks, missing = [], [], set()
    for n, (age, dem, fall, lines) in enumerate(CASES, 1):
        items, acb, beers = [], 0, []
        for line, nm, ings in lines:
            if nm.lower() in in_map:
                leaks.append(nm)
            items.append({"name": nm, "ingredients": ings or []})
            for ing in ings or []:
                if ing not in KB:
                    missing.add(ing); continue
                a, t2, d, f = KB[ing]
                acb += a
                if t2: beers.append(f"{ing}|all")
                if d and dem: beers.append(f"{ing}|dementia")
                if f and fall: beers.append(f"{ing}|falls")
        out.append({"id": f"h{n:02d}", "input": "text", "patient": {"age": age, "dementia": bool(dem), "falls": bool(fall)},
                    "text": "\n".join(l for l, _, _ in lines),
                    "gold": {"items": items, "acb_total": acb, "beers": beers,
                             "expected_unmatched": [nm for _, nm, ings in lines if ings is None]}})
    assert not leaks, f"names already in brand_map.csv (not held-out): {leaks}"
    assert not missing, f"ingredients missing from KB: {missing}"
    about = ("HELD-OUT set: brands deliberately NOT in data/brand_map.csv, plus messy input (doses glued to names, bid/qhs, "
             "typos). Generated by scripts/make_holdout.py; gold labels come from its KB table, not from data/*.csv.")
    (ROOT / "tests" / "eval_set_holdout").mkdir(exist_ok=True)
    (ROOT / "tests" / "eval_set_holdout" / "cases.json").write_text(json.dumps({"_about": about, "cases": out}, indent=1))
    print(f"wrote {len(out)} held-out cases")


if __name__ == "__main__":
    build()
