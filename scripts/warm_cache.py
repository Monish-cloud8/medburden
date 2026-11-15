"""Look up every eval and demo drug name in RxNav once, so data/rxnav_cache.json ships with the app
(demos keep working if RxNav is slow or down). Safe to re-run.  python scripts/warm_cache.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extract import parse_text  # noqa: E402
from src.normalize import RxNavClient, normalize_all  # noqa: E402

texts = [c["text"] for c in json.loads((ROOT / "tests/eval_set/cases.json").read_text())["cases"]]
texts += [c["text"] for c in json.loads((ROOT / "data/demo_cases.json").read_text())["cases"]]
texts += [c["text"] for c in json.loads((ROOT / "tests/eval_set_holdout/cases.json").read_text())["cases"]]
names = sorted({i.name for t in texts for i in parse_text(t)})
c = RxNavClient()
res = normalize_all(names, c)
print(f"RxNav reachable: {c.reachable}. {sum(r.status == 'matched' for r in res)}/{len(res)} names matched. "
      f"Cache entries: {len(c.cache)}")
