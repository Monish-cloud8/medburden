import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extract import MedItem, parse_text, extract          # noqa: E402
from src.normalize import RxNavClient, normalize, normalize_all, NormResult, split_combo  # noqa: E402
from src.score import score, beers_flag_set, strength_mg, tables  # noqa: E402
from src.report import questions, note_text, note_pdf, DISCLAIMER  # noqa: E402


# ----------------------------------------------------------------- fake RxNav (real response shapes)
class FakeResp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._d


CONCEPTS = {  # rxcui: (name, tty, ingredients)
    "220581": ("Tylenol PM", "BN", [("161", "acetaminophen"), ("3498", "diphenhydramine")]),
    "3498": ("diphenhydramine", "IN", []),
    "161": ("acetaminophen", "IN", []),
    "1191": ("aspirin", "IN", []),
    "5640": ("ibuprofen", "IN", []),
    "153008": ("Advil", "BN", [("5640", "ibuprofen")]),
    "29046": ("lisinopril", "IN", []),
    "999001": ("Zovirax", "BN", [("281", "acyclovir")]),
}
EXACT = {"tylenol pm": "220581", "diphenhydramine": "3498", "acetaminophen": "161", "aspirin": "1191",
         "advil": "153008", "lisinopril": "29046", "ibuprofen": "5640"}
APPROX = {"lisinoprill": "29046", "zorvatrex": "999001"}


class FakeSession:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def get(self, url, timeout=None):
        self.calls += 1
        if self.fail:
            raise TimeoutError("simulated timeout")
        from urllib.parse import urlparse, parse_qs, unquote
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path.replace("/REST", "")
        if path == "/rxcui.json":
            rx = EXACT.get(unquote(q["name"]).lower())
            return FakeResp({"idGroup": {"rxnormId": [rx]} if rx else {}})
        if path == "/approximateTerm.json":
            rx = APPROX.get(unquote(q["term"]).lower())
            c = [{"rxcui": rx, "rank": "1", "score": "9.1", "name": CONCEPTS[rx][0], "source": "RXNORM"}] if rx else []
            return FakeResp({"approximateGroup": {"candidate": c}})
        parts = path.split("/")
        rx = parts[2]
        name, tty, ings = CONCEPTS[rx]
        if path.endswith("properties.json"):
            return FakeResp({"properties": {"rxcui": rx, "name": name, "tty": tty}})
        if path.endswith("related.json"):
            return FakeResp({"relatedGroup": {"conceptGroup": [
                {"tty": "IN", "conceptProperties": [{"rxcui": r, "name": n, "tty": "IN"} for r, n in ings]}]}})
        return FakeResp({}, 404)


@pytest.fixture
def client(tmp_path):
    return RxNavClient(cache_path=tmp_path / "cache.json", session=FakeSession())


def items(*names):
    return [MedItem(name=n, strength=s) for n, s in names]


# ----------------------------------------------------------------- combo products
def test_combo_brand_split_into_ingredients(client):
    r = normalize("Tylenol PM", client)
    assert r.status == "matched" and r.tty == "BN"
    assert {i["name"] for i in r.ingredients} == {"acetaminophen", "diphenhydramine"}


def test_written_combo_split_offline():
    c = RxNavClient(offline=True, cache_path=Path("/nonexistent/x.json"))
    r = normalize("hydrocodone/acetaminophen", c)
    assert r.status == "matched" and [i["name"] for i in r.ingredients] == ["hydrocodone", "acetaminophen"]
    assert split_combo("oxycodone and acetaminophen") == ["oxycodone", "acetaminophen"]


def test_rxnav_cache_is_used(tmp_path):
    s = FakeSession()
    c = RxNavClient(cache_path=tmp_path / "c.json", session=s)
    normalize("Tylenol PM", c)
    n = s.calls
    c2 = RxNavClient(cache_path=tmp_path / "c.json", session=FakeSession(fail=True))
    assert normalize("Tylenol PM", c2).status == "matched"      # served from disk cache
    assert n > 0 and c2.stats["cache_hits"] > 0


# ----------------------------------------------------------------- unmatched handling
def test_typo_matched_by_approximate(client):
    r = normalize("Lisinoprill", client)
    assert r.status == "matched" and r.ingredients[0]["name"] == "lisinopril"


def test_fictional_drug_not_silently_matched(client):
    r = normalize("Zorvatrex", client)          # RxNav suggests Zovirax: must NOT be accepted silently
    assert r.status == "needs_review" and "confirm" in r.note.lower()
    rep = score(items(("Zorvatrex", "20 mg")), [r])
    assert rep["acb_total"] == 0 and rep["needs_review"] and rep["acb_incomplete"]


def test_unknown_name_unmatched_and_not_scored(client):
    r = normalize("Qwxyzzz", client)
    assert r.status == "unmatched"
    rep = score(items(("Qwxyzzz", "")), [r])
    assert rep["unmatched"] and rep["rows"][0]["acb"] is None


def test_rxnav_timeout_falls_back_without_crashing(tmp_path):
    # Changed in v2: "Tylenol PM" is now in data/brand_map.csv, so the unknown-brand case uses a name that is not.
    c = RxNavClient(cache_path=tmp_path / "c.json", session=FakeSession(fail=True))
    res = normalize_all(["Qwertyzine PM", "diphenhydramine", ""], c)
    assert res[0].status == "unmatched" and "not reachable" in res[0].note
    assert res[1].status == "matched" and res[1].method.startswith("local")
    assert res[2].status == "unmatched"


# ----------------------------------------------------------------- scoring rules
def _m(name, *ings):
    return NormResult(name, status="matched", matched_name=name, ingredients=[{"name": i, "rxcui": ""} for i in ings])


def test_acb_total_and_levels():
    rep = score(items(("Tylenol PM", ""), ("Furosemide", "40 mg")),
                [_m("Tylenol PM", "acetaminophen", "diphenhydramine"), _m("Furosemide", "furosemide")])
    assert rep["acb_total"] == 4 and rep["acb_level"] == "high"
    assert score(items(("Lasix", "")), [_m("Lasix", "furosemide")])["acb_level"] == "moderate"
    assert score(items(("Lipitor", "")), [_m("Lipitor", "atorvastatin")])["acb_level"] == "low"


def test_beers_dementia_rows_only_when_dementia():
    it, nr = items(("Ditropan", "5 mg")), [_m("Ditropan", "oxybutynin")]
    assert beers_flag_set(score(it, nr, {"dementia": False})) == set()
    assert beers_flag_set(score(it, nr, {"dementia": True})) == {("oxybutynin", "dementia")}


def test_beers_falls_rows_use_classes():
    rep = score(items(("Zoloft", "50 mg")), [_m("Zoloft", "sertraline")], {"falls": True})
    assert beers_flag_set(rep) == {("sertraline", "falls")}


def test_dose_rules():
    assert strength_mg("125 mcg") == 0.125
    lo = score(items(("Doxepin", "3 mg")), [_m("Doxepin", "doxepin")])
    hi = score(items(("Doxepin", "25 mg")), [_m("Doxepin", "doxepin")])
    assert not beers_flag_set(lo) and ("doxepin", "all") in beers_flag_set(hi)
    assert not beers_flag_set(score(items(("Lanoxin", "125 mcg")), [_m("Lanoxin", "digoxin")]))
    assert beers_flag_set(score(items(("Digoxin", "0.25 mg")), [_m("Digoxin", "digoxin")]))
    unknown = score(items(("Digoxin", "")), [_m("Digoxin", "digoxin")])
    assert "check the dose" in unknown["flags"][0]["conditions"]


def test_nifedipine_er_not_flagged():
    assert not beers_flag_set(score(items(("Procardia XL", "30 mg")), [_m("Procardia XL", "nifedipine")]))
    assert beers_flag_set(score(items(("Nifedipine", "10 mg")), [_m("Nifedipine", "nifedipine")]))


def test_every_flag_has_a_source():
    rep = score(items(("Xanax", ""), ("Norco", ""), ("Neurontin", ""), ("Tylenol PM", ""), ("Tylenol", "")),
                [_m("Xanax", "alprazolam"), _m("Norco", "hydrocodone", "acetaminophen"), _m("Neurontin", "gabapentin"),
                 _m("Tylenol PM", "acetaminophen", "diphenhydramine"), _m("Tylenol", "acetaminophen")], {"falls": True})
    assert rep["flags"] and all(f.get("source") for f in rep["flags"])


# ----------------------------------------------------------------- duplicates and sedation stacking
def test_duplicate_ingredient_detected():
    rep = score(items(("Tylenol PM", ""), ("Benadryl", "25 mg")),
                [_m("Tylenol PM", "acetaminophen", "diphenhydramine"), _m("Benadryl", "diphenhydramine")])
    d = [f for f in rep["flags"] if f["type"] == "duplicate"]
    assert len(d) == 1 and d[0]["ingredient"] == "diphenhydramine"
    assert rep["acb_total"] == 3        # duplicate ingredient counted once in the ACB total


def test_no_duplicate_for_different_ingredients():
    rep = score(items(("Ditropan", ""), ("Vesicare", "")), [_m("Ditropan", "oxybutynin"), _m("Vesicare", "solifenacin")])
    assert not [f for f in rep["flags"] if f["type"] == "duplicate"]


def test_sedation_stack_rules():
    rep = score(items(("Ambien", ""), ("Klonopin", ""), ("Tramadol", "")),
                [_m("Ambien", "zolpidem"), _m("Klonopin", "clonazepam"), _m("Tramadol", "tramadol")])
    stacks = [f for f in rep["flags"] if f["type"] == "sedation_stack"]
    assert any("3 medicines" in f["reason"] for f in stacks)
    assert any("opioid plus a benzodiazepine" in f["reason"] for f in stacks)
    two = score(items(("Zoloft", ""), ("Lipitor", "")), [_m("Zoloft", "sertraline"), _m("Lipitor", "atorvastatin")])
    assert not [f for f in two["flags"] if f["type"] == "sedation_stack"]


# ----------------------------------------------------------------- tables
def test_tables_cover_100_ingredients_and_cite_sources():
    acb, beers, cns = tables()
    assert len([k for k, v in acb.items() if int(v["acb_score"]) > 0]) >= 99 and len(acb) >= 100
    assert all(v["source"] for v in acb.values())
    assert all(r["source"] and r["reason_plain"] for rows in beers.values() for r in rows)
    assert int(acb["diphenhydramine"]["acb_score"]) == 3 and int(acb["carbamazepine"]["acb_score"]) == 2


# ----------------------------------------------------------------- extraction + report
def test_parser_fields():
    it = parse_text("1. Norco 5/325 every 6 hrs as needed\nMedication list\nLisinopril 10 mg once daily")
    assert [i.name for i in it] == ["Norco", "Lisinopril"]
    assert it[0].strength == "5/325" and "as needed" in it[0].frequency and it[1].strength == "10 mg"


def test_extract_without_key_uses_parser(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    got, method, _ = extract(text="Benadryl 25 mg at bedtime")
    assert method == "parser" and got[0].name == "Benadryl"


def test_doctor_note(client):
    its = [MedItem("Tylenol PM", frequency="nightly")]
    rep = score(its, [normalize("Tylenol PM", client)], {"dementia": True})
    qs = questions(rep, its, who="Mom")
    assert qs[0].startswith("Mom takes Tylenol PM nightly. It contains diphenhydramine")
    assert DISCLAIMER in note_text(rep, its, "Mom")
    assert note_pdf(rep, its, "Mom")[:4] == b"%PDF"


# ----------------------------------------------------------------- eval script
def test_eval_script_runs_offline(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import evaluate
    ev = tmp_path / "eval"
    ev.mkdir()
    cases = json.loads((ROOT / "tests" / "eval_set" / "cases.json").read_text())
    small = {"cases": [c for c in cases["cases"] if c["id"] in ("c02", "c05", "c11")]}
    (ev / "cases.json").write_text(json.dumps(small))
    m = evaluate.run(offline=True, use_llm=False, baseline=False, out_dir=tmp_path / "res", eval_dir=ev,
                     client=RxNavClient(offline=True, cache_path=tmp_path / "c.json"), quiet=True)
    r = m["medburden"]
    assert r["acb_exact_match_rate"] == 1.0 and r["beers_precision"] == 1.0 and r["beers_recall"] == 1.0
    assert r["unmatched_correctly_flagged"] == "1/1"
    assert (tmp_path / "res" / "report.md").exists()
