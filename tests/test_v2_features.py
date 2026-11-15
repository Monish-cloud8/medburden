"""Tests for v2: photo/OCR path, LLM model/key errors, Beers Table 5 rows and table numbering, comparison output."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.extract as ex  # noqa: E402
from src.extract import MedItem, extract, parse_text, ocr_status, llm_status, call_llm, LLMError  # noqa: E402
from src.normalize import NormResult, RxNavClient, normalize_all  # noqa: E402
from src.score import score, tables, interaction_rules  # noqa: E402

DEMO = ROOT / "demo"
needs_tesseract = pytest.mark.skipif(not ocr_status()["ok"], reason="tesseract not installed")


# ----------------------------------------------------------------- photo reading (OCR path)
@needs_tesseract
@pytest.mark.parametrize("img,expected", [
    ("med_list_photo.png", {"Tylenol PM": ["acetaminophen", "diphenhydramine"], "Meclizine": ["meclizine"],
                            "Lisinopril": ["lisinopril"], "Donepezil": ["donepezil"]}),
    ("pill_bottle_oxybutynin.png", {"OXYBUTYNIN CHLORIDE": ["oxybutynin"]}),
    ("pill_bottle_amitriptyline.png", {"AMITRIPTYLINE HCL": ["amitriptyline"]}),
])
def test_ocr_reads_demo_photos(monkeypatch, img, expected):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    items, method, _ = extract(image_bytes=(DEMO / img).read_bytes())
    assert method == "ocr+parser"
    assert [i.name for i in items] == list(expected)
    norms = normalize_all([i.name for i in items], RxNavClient(offline=True, cache_path=Path("/nonexistent/c.json")))
    assert [[x["name"] for x in n.ingredients] for n in norms] == list(expected.values())


@needs_tesseract
def test_pill_bottle_frequency_attached():
    items, _, _ = extract(image_bytes=(DEMO / "pill_bottle_oxybutynin.png").read_bytes(), use_llm=False)
    assert items[0].strength.lower() == "5 mg" and "twice daily" in items[0].frequency.lower()


def test_missing_tesseract_gives_friendly_message(monkeypatch):
    monkeypatch.setattr(ex.shutil, "which", lambda _: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    st = ocr_status()
    assert not st["ok"] and "brew install tesseract" in st["message"]
    items, method, warns = extract(image_bytes=b"\x89PNG fake")
    assert items == [] and method == "none" and "Tesseract" in warns[0]


def test_label_text_parsing_skips_pharmacy_lines():
    label = ("OAK STREET PHARMACY (555) 010-2233\nRx# 4419027 Fill date 10/02/2026\nJANE DOE\n"
             "OXYBUTYNIN CHLORIDE 5 MG TABLET\nTAKE 1 TABLET BY MOUTH TWICE DAILY\nQty 60 Refills 2 Dr. A. Patel")
    items = parse_text(label)
    assert [i.name for i in items] == ["OXYBUTYNIN CHLORIDE"] and "TWICE DAILY" in items[0].frequency


def test_normal_list_not_treated_as_label():
    assert [i.name for i in parse_text("Mom's medicines\nTylenol PM at bedtime\nAricept 10 mg")] == ["Tylenol PM", "Aricept"]


# ----------------------------------------------------------------- LLM key / model errors
class _R:
    def __init__(self, code, data):
        self.status_code, self._d, self.ok, self.text = code, data, code < 400, json.dumps(data)

    def json(self):
        return self._d


@pytest.fixture
def openai_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    ex._STATUS_CACHE.clear()
    yield
    ex._STATUS_CACHE.clear()


def test_no_key_status(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    st = llm_status()
    assert not st["ok"] and "No AI key" in st["message"]


def test_default_models_are_the_verified_ones(monkeypatch):
    from src import config
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert config.anthropic_model() == "claude-sonnet-5-5" and config.openai_model() == "gpt-6-luna"
    monkeypatch.setenv("OPENAI_MODEL", "my-model")
    assert config.openai_model() == "my-model"


def test_unknown_model_gives_clear_message(openai_key, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-does-not-exist")
    monkeypatch.setattr(ex.requests, "get", lambda *a, **k: _R(200, {"data": [{"id": "gpt-6-luna"}, {"id": "gpt-6.1-sol"}]}))
    st = llm_status()
    assert not st["ok"] and "gpt-does-not-exist" in st["message"] and "OPENAI_MODEL" in st["message"]


def test_bad_key_gives_clear_message(openai_key, monkeypatch):
    monkeypatch.setattr(ex.requests, "get", lambda *a, **k: _R(401, {"error": {"message": "bad key"}}))
    assert "rejected" in llm_status()["message"]


def test_extract_falls_back_when_model_missing(openai_key, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "nope")
    monkeypatch.setattr(ex.requests, "get", lambda *a, **k: _R(200, {"data": [{"id": "gpt-6-luna"}]}))
    items, method, warns = extract(text="Benadryl 25 mg at bedtime")
    assert method == "parser" and items[0].name == "Benadryl" and "not available" in warns[0]


def test_openai_request_shape_and_model_error(openai_key, monkeypatch):
    sent = {}

    def post(url, json=None, **k):
        sent.update(json)
        return _R(404, {"error": {"message": "The model `gpt-6-luna` does not exist"}})
    monkeypatch.setattr(ex.requests, "post", post)
    with pytest.raises(LLMError, match="model"):
        call_llm("sys", "hi")
    assert sent["model"] == "gpt-6-luna" and "max_completion_tokens" in sent and "temperature" not in sent


# ----------------------------------------------------------------- Beers numbering and Table 5
def _m(name, *ings):
    return NormResult(name, status="matched", matched_name=name, ingredients=[{"name": i, "rxcui": ""} for i in ings])


def test_beers_table_numbers_match_the_2023_article():
    _, beers, _ = tables()
    rows = [r for rs in beers.values() for r in rs]
    assert {r["beers_table"] for r in rows if r["applies_to"] == "all older adults"} == {"Table 2"}
    assert {r["beers_table"] for r in rows if r["applies_to"] != "all older adults"} == {"Table 3"}
    assert all(r["beers_row"] and r["source"].endswith(r["beers_table"]) for r in rows)


def test_all_12_table5_rows_present_and_cited():
    rows = interaction_rules()
    assert {r["rule_id"] for r in rows} == {f"T5-{i}" for i in range(1, 13)} - {"T5-5"}   # row 5 = 3+ CNS rule in code
    assert all("Table 5, row" in r["source"] for r in rows)


def test_anticholinergic_pair_flagged():
    rep = score([MedItem("Ditropan"), MedItem("Vesicare")], [_m("Ditropan", "oxybutynin"), _m("Vesicare", "solifenacin")])
    f = [x for x in rep["flags"] if x.get("rule_id") == "T5-4"]
    assert len(f) == 1 and f[0]["ingredient"] == "oxybutynin, solifenacin" and "row 4" in f[0]["source"]


def test_low_dose_doxepin_not_counted_as_anticholinergic():
    rep = score([MedItem("Doxepin", strength="3 mg"), MedItem("Ditropan")], [_m("Doxepin", "doxepin"), _m("Ditropan", "oxybutynin")])
    assert not [x for x in rep["flags"] if x.get("rule_id") == "T5-4"]


def test_warfarin_ssri_and_ras_rows():
    rep = score([MedItem("Coumadin"), MedItem("Zoloft"), MedItem("Lisinopril"), MedItem("Losartan")],
                [_m("Coumadin", "warfarin"), _m("Zoloft", "sertraline"), _m("Lisinopril", "lisinopril"), _m("Losartan", "losartan")])
    ids = {x.get("rule_id") for x in rep["flags"]}
    assert {"T5-12", "T5-1"} <= ids
    ras = next(x for x in rep["flags"] if x.get("rule_id") == "T5-1")
    assert "kidney" in ras["conditions"]


def test_comparison_csv_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sys.path.insert(0, str(ROOT / "scripts"))
    import evaluate
    ev = tmp_path / "eval"
    ev.mkdir()
    cases = json.loads((ROOT / "tests" / "eval_set" / "cases.json").read_text())["cases"]
    (ev / "cases.json").write_text(json.dumps({"cases": [c for c in cases if c["id"] in ("c01", "c09")]}))
    m = evaluate.run(offline=True, use_llm=True, baseline=True, out_dir=tmp_path / "r", eval_dir=ev,
                     client=RxNavClient(offline=True, cache_path=tmp_path / "c.json"), quiet=True)
    assert m["llm_only_baseline"] is None and "No AI key" in m["llm_only_baseline_skipped"]
    rows = list(csv.DictReader(open(tmp_path / "r" / "comparison.csv")))
    assert [r["metric"] for r in rows] == ["Ingredient match", "ACB total exact", "Beers precision", "Beers recall"]
    assert all(r["llm_only"] == "" and "not run" in r["note"] for r in rows)
    assert (tmp_path / "r" / "comparison.png").exists()


def test_baseline_runs_with_mocked_llm(tmp_path, openai_key, monkeypatch):
    """With a key, the LLM-only baseline runs on the same cases and lands in comparison.csv."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import evaluate
    monkeypatch.setattr(ex.requests, "get", lambda *a, **k: _R(200, {"data": [{"id": "gpt-6-luna"}]}))
    reply = {"items": [{"name_as_written": "Tylenol PM", "ingredients": ["acetaminophen", "diphenhydramine"]},
                       {"name_as_written": "Lisinopril", "ingredients": ["lisinopril"]},
                       {"name_as_written": "Atorvastatin", "ingredients": ["atorvastatin"]}],
             "acb_total": 3, "flags": [{"ingredient": "diphenhydramine", "scope": "all"}]}
    monkeypatch.setattr(evaluate, "call_llm", lambda *a, **k: json.dumps(reply))
    ev = tmp_path / "eval"
    ev.mkdir()
    cases = json.loads((ROOT / "tests" / "eval_set" / "cases.json").read_text())["cases"]
    (ev / "cases.json").write_text(json.dumps({"cases": [c for c in cases if c["id"] == "c01"]}))
    m = evaluate.run(offline=True, use_llm=False, baseline=True, out_dir=tmp_path / "r", eval_dir=ev,
                     client=RxNavClient(offline=True, cache_path=tmp_path / "c.json"), quiet=True)
    b = m["llm_only_baseline"]
    assert b["ingredient_match_rate"] == 1.0 and b["acb_exact_match_rate"] == 1.0
    assert b["beers_precision"] == 1.0 and b["beers_recall"] == 0.5          # missed diphenhydramine|dementia
    rows = {r["metric"]: r for r in csv.DictReader(open(tmp_path / "r" / "comparison.csv"))}
    assert float(rows["Beers recall"]["llm_only"]) == 0.5
