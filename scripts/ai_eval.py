"""Measure the AI layer on the held-out lists (needs an API key).

python scripts/ai_eval.py [--eval-dir tests/eval_set_holdout] [--out results/ai_layer.json]

1. Identify: for medicines that RxNav and the local list left unresolved, how often is the AI's suggested ingredient list
   exactly right, and how often does it suggest something for a made-up drug (a wrong suggestion)?
2. Write: for each list with findings, how many AI-written questions pass the verification check?
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai_layer import apply_ai_identification, write_questions, ai_available, check_rewrite  # noqa: E402
from src.config import RESULTS  # noqa: E402
from src.extract import MedItem  # noqa: E402
from src.normalize import RxNavClient, normalize_all  # noqa: E402
from src.report import questions  # noqa: E402
from src.score import score, tables  # noqa: E402


def main(eval_dir: Path, out: Path):
    if not ai_available():
        sys.exit("No working API key: the AI layer cannot be measured.")
    cases = json.loads((eval_dir / "cases.json").read_text())["cases"]
    client = RxNavClient(offline=True)       # cache + local list only, so the run is repeatable
    # Only names the lookups did not settle: status unmatched or needs_review (never confirmed without the user).
    ident = dict(real_unsettled=0, lookup_right=0, final_right=0, ai_changed_to_right=0, ai_changed_to_wrong=0, made_up_unsettled=0, ai_invented=0)
    wrote = dict(lists_with_questions=0, questions=0, ai_kept=0, fell_back=0)
    wrong_examples, fake_examples = [], []
    acb, beers, cns = tables()
    known = {k.lower() for k in (set(acb) | set(beers) | set(cns))}
    for c in cases:
        if c["input"] == "image":
            continue
        g = c["gold"]
        items = [MedItem(name=gi["name"]) for gi in g["items"]]
        norms = normalize_all([i.name for i in items], client)
        before = [(n.status, {i["name"] for i in n.ingredients}) for n in norms]
        apply_ai_identification(norms)
        for gi, n, (b_status, b_ings) in zip(g["items"], norms, before):
            if b_status == "matched":
                continue
            ai = n.method == "ai suggestion"
            if gi["name"] in g["expected_unmatched"]:
                ident["made_up_unsettled"] += 1
                if ai:
                    ident["ai_invented"] += 1
                    fake_examples.append({"name": gi["name"], "ai_said": [i["name"] for i in n.ingredients]})
                continue
            ident["real_unsettled"] += 1
            ident["lookup_right"] += b_ings == set(gi["ingredients"])
            final = {i["name"] for i in n.ingredients}
            ident["final_right"] += final == set(gi["ingredients"])
            if ai and final == set(gi["ingredients"]):
                ident["ai_changed_to_right"] += 1
            elif ai:
                ident["ai_changed_to_wrong"] += 1
                wrong_examples.append({"name": gi["name"], "ai_said": sorted(final), "gold": gi["ingredients"], "lookup_said": sorted(b_ings)})
        rep = score(items, normalize_all([i.name for i in items], client), c["patient"])
        facts = questions(rep, items, "My relative")
        if not facts:
            continue
        wrote["lists_with_questions"] += 1
        qs, by_ai = write_questions(facts, "My relative")
        for f, q in zip(facts, qs):
            wrote["questions"] += 1
            if q != f and check_rewrite(f, q, known):
                wrote["ai_kept"] += 1
            else:
                wrote["fell_back"] += 1
    res = {"cases_text_only": sum(c["input"] != "image" for c in cases), "identify": ident, "write": wrote,
           "wrong_suggestions": wrong_examples, "suggestions_for_made_up_drugs": fake_examples}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", default=str(ROOT / "tests" / "eval_set_holdout"))
    ap.add_argument("--out", default=str(RESULTS / "ai_layer.json"))
    a = ap.parse_args()
    main(Path(a.eval_dir), Path(a.out))
