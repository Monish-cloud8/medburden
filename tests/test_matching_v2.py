"""Tests for the v2 matching changes: text normalization, brand map, spelling correction, RxNav IN+MIN, unmatched log."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.normalize import (RxNavClient, normalize, clean_keys, spelling_correction, local_dictionary,  # noqa: E402
                           levenshtein)
from test_medburden import FakeSession, FakeResp  # noqa: E402


@pytest.fixture
def offline(tmp_path):
    return RxNavClient(offline=True, cache_path=tmp_path / "c.json")


def test_clean_keys_strip_dose_frequency_release_salt():
    keys = clean_keys("Metoprolol Succinate ER 50 mg tablet once daily")
    assert "metoprolol succinate er" in keys and keys[0].startswith("metoprolol succinate er")
    assert keys[-1] == "metoprolol"
    assert "ditropan xl" in clean_keys("Ditropan XL 10 mg daily")       # brand suffix kept in an early key
    assert clean_keys("Diphenhydramine HCl 25mg at bedtime")[-1] == "diphenhydramine"
    assert clean_keys("Potassium chloride 20 mEq")[0] == "potassium chloride"   # salt kept in the first key


@pytest.mark.parametrize("written,ings", [
    ("Benadryl 25 mg", ["diphenhydramine"]), ("Tylenol PM", ["acetaminophen", "diphenhydramine"]),
    ("Advil PM", ["ibuprofen", "diphenhydramine"]), ("ZzzQuil", ["diphenhydramine"]), ("Unisom", ["doxylamine"]),
    ("Ditropan XL", ["oxybutynin"]), ("Detrol LA", ["tolterodine"]), ("Vesicare", ["solifenacin"]),
    ("Flexeril", ["cyclobenzaprine"]), ("Ambien", ["zolpidem"]), ("Xanax", ["alprazolam"]), ("Ativan", ["lorazepam"]),
    ("Valium", ["diazepam"]), ("Klonopin", ["clonazepam"]), ("Restoril", ["temazepam"]), ("Paxil", ["paroxetine"]),
    ("Elavil", ["amitriptyline"]), ("Seroquel", ["quetiapine"]), ("Risperdal", ["risperidone"]), ("Haldol", ["haloperidol"]),
    ("Zyprexa", ["olanzapine"]), ("Neurontin", ["gabapentin"]), ("Lyrica", ["pregabalin"]), ("Coumadin", ["warfarin"]),
    ("Glucotrol", ["glipizide"]), ("glyburide", ["glyburide"]), ("Phenergan", ["promethazine"]), ("Antivert", ["meclizine"]),
    ("Vistaril", ["hydroxyzine"]), ("Atarax", ["hydroxyzine"]), ("Aricept", ["donepezil"]), ("Namenda", ["memantine"]),
    ("Sinemet 25/100", ["carbidopa", "levodopa"]), ("Norco 5/325", ["hydrocodone", "acetaminophen"]),
    ("hydrocodone/acetaminophen", ["hydrocodone", "acetaminophen"]), ("K-Dur 20 mEq", ["potassium chloride"]),
])
def test_brand_map_offline(offline, written, ings):
    r = normalize(written, offline)
    assert r.status == "matched", (written, r.note)
    assert [i["name"] for i in r.ingredients] == ings


def test_brand_map_rows_have_sources():
    with open(ROOT / "data" / "brand_map.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 150 and all(r["source"] and r["ingredients"] for r in rows)
    assert len({r["name"] for r in rows}) == len(rows)       # no duplicate keys


@pytest.mark.parametrize("typo,fixed", [("Lisinoprill", "lisinopril"), ("Metforman", "metformin"),
                                        ("Omeprazol", "omeprazole"), ("Meclazine", "meclizine")])
def test_spelling_correction_is_shown(offline, typo, fixed):
    r = normalize(typo, offline)
    assert r.status == "matched" and r.ingredients[0]["name"] == fixed
    assert r.method == "local spelling correction" and "Spelling corrected" in r.note


@pytest.mark.parametrize("fake", ["Zorvatrex", "Blorpaxin", "Qwxyzzz"])
def test_fictional_names_never_corrected_into_real_drugs(offline, fake):
    assert spelling_correction(fake) is None
    assert normalize(fake, offline).status != "matched"


def test_levenshtein():
    assert levenshtein("meclazine", "meclizine") == 1 and levenshtein("abc", "abc") == 0


def test_rxnav_exact_beats_local_and_uses_in_min(tmp_path):
    s = FakeSession()
    c = RxNavClient(cache_path=tmp_path / "c.json", session=s)
    r = normalize("Tylenol PM", c)
    assert r.method == "rxnav exact" and r.rxcui == "220581"
    assert any("tty=IN+MIN" in k for k in c.cache)               # related ingredients requested as IN+MIN
    assert "Combination product" in r.note


def test_min_concepts_not_counted_as_ingredients(tmp_path):
    class MinSession(FakeSession):
        def get(self, url, timeout=None):
            if "related.json" in url:
                return FakeResp({"relatedGroup": {"conceptGroup": [
                    {"tty": "IN", "conceptProperties": [{"rxcui": "161", "name": "acetaminophen", "tty": "IN"},
                                                        {"rxcui": "3498", "name": "diphenhydramine", "tty": "IN"}]},
                    {"tty": "MIN", "conceptProperties": [{"rxcui": "1092189", "name": "acetaminophen / diphenhydramine",
                                                          "tty": "MIN"}]}]}})
            return super().get(url, timeout)
    c = RxNavClient(cache_path=tmp_path / "c.json", session=MinSession())
    r = normalize("Tylenol PM", c)
    assert [i["name"] for i in r.ingredients] == ["acetaminophen", "diphenhydramine"]


def test_cache_written_to_disk(tmp_path):
    c = RxNavClient(cache_path=tmp_path / "c.json", session=FakeSession())
    normalize("Advil", c)
    assert json.loads((tmp_path / "c.json").read_text())


def test_eval_writes_unmatched_and_misses(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import evaluate
    ev = tmp_path / "eval"
    ev.mkdir()
    cases = json.loads((ROOT / "tests" / "eval_set" / "cases.json").read_text())["cases"]
    (ev / "cases.json").write_text(json.dumps({"cases": [c for c in cases if c["id"] in ("c11", "c27", "c01")]}))
    out = tmp_path / "res"
    m = evaluate.run(offline=True, use_llm=False, baseline=False, out_dir=out, eval_dir=ev,
                     client=RxNavClient(offline=True, cache_path=tmp_path / "c.json"), quiet=True)
    rows = list(csv.DictReader(open(out / "unmatched.csv")))
    assert {r["written"] for r in rows} == {"Zorvatrex", "Blorpaxin"}
    assert all(r["expected"] == "yes" for r in rows)
    assert (out / "beers_misses.csv").exists() and (out / "comparison.csv").exists()
    assert m["medburden"]["rxnav_match_rate"] == 1.0
