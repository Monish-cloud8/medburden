"""Cross-check data/brand_map.csv against NIH RxNav (brand -> ingredients). Needs internet.
Writes results/brand_map_check.csv and prints any disagreement.   python scripts/check_brand_map.py"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.normalize import RxNavClient, canonical_ingredient  # noqa: E402

c = RxNavClient()
rows = list(csv.DictReader(open(ROOT / "data" / "brand_map.csv")))
out, bad = [], 0
for r in rows:
    if r["kind"] != "brand":
        continue
    rx = c.exact(r["name"])
    if c.reachable is False:
        print("RxNav not reachable: brand map check skipped.")
        sys.exit(0)
    if not rx:
        out.append({**r, "rxnav": "(no exact RxNorm match)", "agrees": "unknown"})
        continue
    props = c.properties(rx)
    ings = [{"name": props.get("name", "").lower()}] if props.get("tty") == "IN" else c.ingredients(rx)
    rxset = {canonical_ingredient(i["name"]) for i in ings}
    ok = rxset == set(r["ingredients"].split(";"))
    bad += not ok
    out.append({**r, "rxnav": ";".join(sorted(rxset)), "agrees": "yes" if ok else "NO"})
(ROOT / "results").mkdir(exist_ok=True)
with open(ROOT / "results" / "brand_map_check.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ["name"])
    w.writeheader()
    w.writerows(out)
print(f"Brand map vs RxNav: {sum(o['agrees'] == 'yes' for o in out)} agree, {bad} disagree, "
      f"{sum(o['agrees'] == 'unknown' for o in out)} not found by exact name. See results/brand_map_check.csv")
for o in out:
    if o["agrees"] == "NO":
        print(f"  {o['name']}: map={o['ingredients']}  rxnav={o['rxnav']}")
