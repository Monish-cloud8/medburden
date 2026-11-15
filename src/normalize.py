"""Map each written drug name to RxNorm (RxCUI + active ingredients) using the free NIH RxNav API.

Lookup order (first success wins):
  1. RxNav exact name match (rxcui.json?search=2), on the cleaned name
  2. local brand / generic map (data/brand_map.csv) and the ingredient names in the cited tables
  3. RxNav approximateTerm, accepted only if the RxNorm name is close to what was written
  4. local spelling correction (<= 2 letters different from a known brand or ingredient), shown to the user
  5. otherwise needs_review (close but uncertain) or unmatched
  Ingredients come from RxNav related.json?tty=IN+MIN, so combination products are split into each ingredient.

Statuses:
  matched       confident match; ingredients are used for scoring
  needs_review  a close RxNav suggestion exists but the name differs; NOT scored until the user confirms
  unmatched     nothing found; NOT scored and clearly shown to the user
When RxNav cannot be reached, only exact ingredient names from the local tables can be matched
(method = "local"); everything else becomes unmatched with a note. Nothing is guessed silently.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import quote

import requests

from .config import RXNAV_BASE, RXNAV_CACHE, RXNAV_TIMEOUT, DATA

MATCH_SIM = 0.80        # name similarity needed to accept an approximate RxNav match without review
FORM_WORDS = {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules", "caplet", "caplets", "oral",
              "er", "xr", "xl", "sr", "cr", "la", "dr", "ec", "hcl", "extended", "release", "nasal", "spray", "cream",
              "ointment", "patch", "solution", "liquid", "gel", "drops", "inhaler", "chewable", "softgel", "softgels",
              "tartrate", "succinate", "sodium", "potassium", "hydrochloride", "extra", "strength", "maximum", "regular"}


@dataclass
class NormResult:
    input_name: str
    status: str = "unmatched"
    rxcui: str = ""
    matched_name: str = ""
    tty: str = ""
    ingredients: list = field(default_factory=list)     # [{"name": str, "rxcui": str}]
    method: str = ""
    similarity: float = 0.0
    note: str = ""

    def to_dict(self):
        return asdict(self)


# ----------------------------------------------------------------- helpers
def simplify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"\d+(\.\d+)?\s*(mg|mcg|ml|meq|iu|units?|%)?", " ", s)
    s = re.sub(r"[^a-z\s\-/+]", " ", s)
    return " ".join(w for w in s.split() if w not in FORM_WORDS)


def similarity(a: str, b: str) -> float:
    a, b = simplify(a), simplify(b)
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    at = a.replace("-", " ").split()
    bt = set(b.replace("-", " ").replace("/", " ").split())
    tok = sum(1 for t in at if t in bt or any(difflib.SequenceMatcher(None, t, x).ratio() >= 0.85 for x in bt)) / len(at)
    return max(ratio, tok)


def split_combo(name: str) -> list[str]:
    parts = re.split(r"\s*(?:/|\+|\band\b|\bwith\b|&)\s*", name, flags=re.I)
    return [p.strip() for p in parts if re.search(r"[a-zA-Z]{3,}", p or "")]


def canonical_ingredient(name: str, aliases: dict | None = None) -> str:
    s = name.lower().strip()
    s = re.sub(r"\s*\(usp\)|\s*,?\s*usp\b", "", s).strip()
    aliases = aliases if aliases is not None else load_aliases()
    return aliases.get(s, s)


_ALIASES = None


def load_aliases() -> dict:
    global _ALIASES
    if _ALIASES is None:
        import csv
        p = DATA / "ingredient_aliases.csv"
        _ALIASES = {}
        if p.exists():
            with open(p) as f:
                for r in csv.DictReader(f):
                    _ALIASES[r["alias"].strip().lower()] = r["ingredient"].strip().lower()
    return _ALIASES


# ----------------------------------------------------------------- RxNav client
class RxNavClient:
    def __init__(self, cache_path: Path = RXNAV_CACHE, timeout: float = RXNAV_TIMEOUT, offline: bool = False,
                 session=None):
        self.cache_path = Path(cache_path)
        self.timeout = timeout
        self.offline = offline
        self.session = session or requests.Session()
        self._lock = threading.Lock()
        self.reachable = None if not offline else False
        self.stats = {"cache_hits": 0, "requests": 0, "errors": 0}
        try:
            self.cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        except Exception:
            self.cache = {}

    def _save(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache, indent=0, sort_keys=True))
            tmp.replace(self.cache_path)
        except Exception:
            pass   # read-only filesystem (e.g. some hosts): cache stays in memory

    def get(self, path: str) -> dict | None:
        """GET RXNAV_BASE + path. Returns parsed JSON, or None if unavailable. Never raises."""
        if path in self.cache:
            self.stats["cache_hits"] += 1
            return self.cache[path]
        if self.offline or self.reachable is False:
            return None
        try:
            self.stats["requests"] += 1
            r = self.session.get(RXNAV_BASE + path, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            self.reachable = True
            with self._lock:
                self.cache[path] = data
                self._save()
            return data
        except Exception:
            self.stats["errors"] += 1
            if self.reachable is None:
                self.reachable = False       # first call failed: stop trying for this session
            return None

    # --- endpoints
    def exact(self, name):
        d = self.get(f"/rxcui.json?name={quote(name)}&search=2")
        ids = ((d or {}).get("idGroup") or {}).get("rxnormId") or []
        return ids[0] if ids else None

    def approximate(self, name, n=5):
        d = self.get(f"/approximateTerm.json?term={quote(name)}&maxEntries={n}&option=1")
        cands = ((d or {}).get("approximateGroup") or {}).get("candidate") or []
        rx = [c for c in cands if c.get("source", "RXNORM") == "RXNORM"] or cands
        return sorted(rx, key=lambda c: int(c.get("rank", 99)))

    def properties(self, rxcui):
        d = self.get(f"/rxcui/{rxcui}/properties.json")
        return (d or {}).get("properties") or {}

    def related(self, rxcui):
        """Active ingredients (tty=IN) and, for combination products, the multi-ingredient concept (tty=MIN)."""
        d = self.get(f"/rxcui/{rxcui}/related.json?tty=IN+MIN")
        ins, mins = [], []
        for g in ((d or {}).get("relatedGroup") or {}).get("conceptGroup") or []:
            for c in g.get("conceptProperties") or []:
                item = {"name": c["name"].lower(), "rxcui": c["rxcui"]}
                (mins if (c.get("tty") or g.get("tty")) == "MIN" else ins).append(item)
        return ins, mins

    def ingredients(self, rxcui):
        return self.related(rxcui)[0]


# ----------------------------------------------------------------- text normalization
UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)*\s*(?:mg|mcg|µg|ug|g|ml|meq|iu|units?|%)?(?![a-z])", re.I)
FREQ_WORDS = {"daily", "nightly", "weekly", "bedtime", "night", "morning", "evening", "prn", "bid", "tid", "qid", "qhs", "qd",
              "qam", "once", "twice", "times", "day", "every", "hours", "hrs", "needed", "as", "at", "in", "the", "a", "for",
              "take", "takes", "by", "mouth", "po", "with", "meals", "before", "after", "q4h", "q6h", "q8h", "q12h", "sleep",
              "pain", "itching", "nausea", "dizziness", "one", "two", "half", "puff", "puffs", "drop", "drops", "use", "apply"}
RELEASE_WORDS = {"er", "xr", "xl", "sr", "cr", "la", "dr", "ec", "cd", "xt", "odt", "extended", "release", "delayed",
                 "sustained", "controlled", "immediate", "ir"}
DOSE_FORM_WORDS = {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules", "caplet", "caplets", "oral",
                   "nasal", "spray", "cream", "ointment", "patch", "solution", "liquid", "gel", "inhaler", "chewable",
                   "softgel", "softgels", "gelcap", "gelcaps", "suspension", "syrup", "injection", "topical", "lotion",
                   "regular", "maximum", "strength", "extra"}
SALT_WORDS = {"hcl", "hydrochloride", "tartrate", "succinate", "sodium", "potassium", "besylate", "maleate", "citrate",
              "bitartrate", "mesylate", "fumarate", "sulfate", "phosphate", "acetate", "bromide", "chloride", "calcium",
              "magnesium", "hyclate", "monohydrate", "dihydrate", "er", "xl"}


def clean_keys(name: str) -> list[str]:
    """Lookup keys from most to least specific: [as written minus dose/frequency, minus release/dose form, minus salt]."""
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = UNIT_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9\s\-/&+]", " ", s)
    s = re.sub(r"\bq\s?\d+\s?h\b", " ", s)
    w1 = [w for w in s.split() if w not in FREQ_WORDS and not w.isdigit()]
    w2 = [w for w in w1 if w not in DOSE_FORM_WORDS]
    w3 = [w for w in w2 if w not in RELEASE_WORDS]
    w4 = [w for w in w3 if w not in SALT_WORDS]
    keys = []
    for ws in (w1, w2, w3, w4):
        k = " ".join(ws).strip(" -/")
        if k and k not in keys:
            keys.append(k)
    return keys


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ----------------------------------------------------------------- local dictionary (brand map + table ingredients)
_LOCAL = None


def local_dictionary() -> dict:
    """name -> {"ingredients": [...], "source": str, "note": str}. Brand map rows plus every ingredient in the tables."""
    global _LOCAL
    if _LOCAL is None:
        import csv
        d = {}
        for fn in ("acb_scale.csv", "beers_2023.csv", "cns_classes.csv"):
            with open(DATA / fn) as f:
                for r in csv.DictReader(f):
                    ing = r["ingredient"].strip().lower()
                    d.setdefault(ing, {"ingredients": [ing], "source": f"ingredient name in data/{fn}", "note": ""})
        # Brand names printed on the ACB scale itself (a cited source). Two printed brands are skipped because they do
        # not match the listed drug: 'Contin' (codeine) and 'Diuril' (chlorothiazide, not chlorthalidone).
        skip = {"contin", "diuril", "multiple brands", ""}
        with open(DATA / "acb_scale.csv") as f:
            for r in csv.DictReader(f):
                for b in (r.get("brands_on_scale") or "").split(";"):
                    b = b.strip().lower()
                    if b not in skip:
                        d.setdefault(b, {"ingredients": [r["ingredient"].strip().lower()],
                                         "source": "brand printed on the ACB scale 2012", "note": ""})
        for alias, ing in load_aliases().items():
            d.setdefault(alias, {"ingredients": [ing], "source": "data/ingredient_aliases.csv", "note": ""})
            d.setdefault(ing, {"ingredients": [ing], "source": "data/ingredient_aliases.csv", "note": ""})
        p = DATA / "brand_map.csv"
        if p.exists():
            with open(p) as f:
                for r in csv.DictReader(f):
                    d[r["name"].strip().lower()] = {
                        "ingredients": [canonical_ingredient(x) for x in r["ingredients"].split(";") if x.strip()],
                        "source": f"data/brand_map.csv ({r['source']})", "note": r.get("notes", "") or ""}
        _LOCAL = d
    return _LOCAL


def local_vocab() -> set[str]:
    return set(local_dictionary())


def local_lookup(name: str) -> tuple[str, dict] | None:
    """Exact lookup of any cleaned key (or each part of a written combination) in the local dictionary."""
    d = local_dictionary()
    for k in clean_keys(name):
        if k in d:
            return k, d[k]
    for k in clean_keys(name):
        parts = split_combo(k)
        if len(parts) > 1:
            hits = [local_lookup(p) for p in parts]
            if all(hits):
                return " + ".join(h[0] for h in hits), {
                    "ingredients": [i for h in hits for i in h[1]["ingredients"]],
                    "source": "; ".join(dict.fromkeys(h[1]["source"] for h in hits)), "note": ""}
    return None


def spelling_correction(name: str) -> tuple[str, str] | None:
    """Return (written_key, corrected_name) if exactly one dictionary name is within 1-2 letters. Short words need 1."""
    d = local_dictionary()
    for k in clean_keys(name)[::-1]:
        if len(k) < 5:
            continue
        limit = 1 if len(k) < 9 else 2      # 2-letter fixes only for long names: 'librium' must never become 'lithium'
        best = sorted((levenshtein(k, n), n) for n in d if abs(len(n) - len(k)) <= limit)
        best = [b for b in best if b[0] <= limit]
        if best and (len(best) == 1 or best[0][0] < best[1][0]):
            return k, best[0][1]
    return None


def _from_local(r: NormResult, key: str, entry: dict, method: str, note: str = "") -> NormResult:
    r.status, r.method, r.matched_name, r.similarity = "matched", method, key, 1.0
    r.ingredients = [{"name": i, "rxcui": ""} for i in dict.fromkeys(entry["ingredients"])]
    r.note = " ".join(x for x in (note, entry.get("note", ""), f"Source: {entry['source']}.") if x)
    return r


# ----------------------------------------------------------------- main entry
def _rxnav_resolve(r: NormResult, rxcui: str, method: str, sim: float, client: RxNavClient) -> NormResult:
    props = client.properties(rxcui)
    r.rxcui, r.tty, r.method, r.similarity = rxcui, props.get("tty", ""), method, round(sim, 3)
    r.matched_name = props.get("name") or r.matched_name
    if r.tty == "IN":
        ings, mins = [{"name": r.matched_name.lower(), "rxcui": rxcui}], []
    else:
        ings, mins = client.related(rxcui)
    r.ingredients = [{"name": canonical_ingredient(i["name"]), "rxcui": i["rxcui"]} for i in ings]
    if not r.ingredients:
        r.status, r.note = "needs_review", "RxNorm concept found, but RxNav returned no active ingredient."
        return r
    r.status = "matched"
    if len(r.ingredients) > 1:
        r.note = "Combination product: " + " + ".join(i["name"] for i in r.ingredients) + "."
    if r.tty == "BN" and len(mins) > 1:
        r.note = ("This brand name covers several products, so these are the ingredients across all of them. "
                  "Check the label for the exact product.")
    return r


def normalize(name: str, client: RxNavClient) -> NormResult:
    name = (name or "").strip()
    r = NormResult(input_name=name)
    if not re.search(r"[A-Za-z]{2,}", name):
        r.note = "Empty or unreadable name."
        return r
    keys = clean_keys(name)

    # 1. RxNav exact on each cleaned key
    for k in keys:
        rx = client.exact(k)
        if rx:
            out = _rxnav_resolve(r, rx, "rxnav exact", 1.0, client)
            if out.status == "matched":
                return out
            r = NormResult(input_name=name)
            break

    # 2. local brand map / table ingredient names
    hit = local_lookup(name)
    if hit:
        why = "RxNav was not reachable; " if client.reachable is False else ""
        return _from_local(r, hit[0], hit[1], "local brand map" if "brand_map" in hit[1]["source"] else "local table name",
                           f"{why}matched in the local drug list.".capitalize() if why else "")

    # 3. RxNav approximate, accepted only when the names are close
    cand = None
    cands = client.approximate(keys[-1] if keys else name)
    if cands:
        top = cands[0]
        props = client.properties(top["rxcui"])
        cand_name = props.get("name") or top.get("name", "")
        sim = max(similarity(k, cand_name) for k in keys) if keys else similarity(name, cand_name)
        cand = (top["rxcui"], cand_name, sim)
        # "close only": high text similarity AND at most 1 letter different from the written name or the candidate's
        # name (brand names look alike: Zolvarex ~ Zoladex), else it goes to "needs review" below.
        cn = simplify(cand_name)
        near = bool(keys) and any(levenshtein(k, cn) <= 1 or (k.split() and set(k.split()) <= set(cn.split()))
                                  for k in keys)
        if sim >= MATCH_SIM and near:
            out = _rxnav_resolve(NormResult(input_name=name, matched_name=cand_name), top["rxcui"], "rxnav approximate",
                                 sim, client)
            if out.status == "matched":
                return out

    # 4. local spelling correction (shown to the user)
    sc = spelling_correction(name)
    if sc:
        entry = local_dictionary()[sc[1]]
        return _from_local(r, sc[1], entry, "local spelling correction",
                           f"Spelling corrected: '{sc[0]}' read as '{sc[1]}'. Please check this is right.")

    # 5. uncertain RxNav suggestion -> needs review
    if cand:
        out = _rxnav_resolve(NormResult(input_name=name, matched_name=cand[1]), cand[0], "rxnav approximate", cand[2], client)
        out.status = "needs_review"
        out.note = f"Closest RxNorm name is '{out.matched_name}'. Please confirm this is the right drug."
        return out

    # 6. written combination: split and look up each part
    parts = split_combo(name)
    if len(parts) > 1:
        subs = [normalize(p, client) for p in parts]
        if all(s.status == "matched" for s in subs):
            r.status, r.method = "matched", "combination split"
            r.ingredients = [i for s in subs for i in s.ingredients]
            r.matched_name = " + ".join(s.matched_name for s in subs)
            r.similarity = min(s.similarity for s in subs)
            return r

    # 7. close local name -> needs review; otherwise unmatched
    close = difflib.get_close_matches(keys[-1] if keys else name.lower(), local_vocab(), n=1, cutoff=0.80)
    if close:
        e = local_dictionary()[close[0]]
        r.status, r.method, r.matched_name = "needs_review", "local close match", close[0]
        r.ingredients = [{"name": i, "rxcui": ""} for i in e["ingredients"]]
        r.note = f"Not sure. The closest known name is '{close[0]}'. Please confirm."
        return r
    r.note = ("No match in RxNorm or in the local drug list. Please check the spelling or ask the pharmacist."
              if client.reachable is not False else
              "RxNav was not reachable, and this name is not in the local drug list. It was NOT checked.")
    return r


def normalize_all(names: list[str], client: RxNavClient) -> list[NormResult]:
    out = []
    for n in names:
        try:
            out.append(normalize(n, client))
        except Exception as e:   # never crash the app
            out.append(NormResult(input_name=n, note=f"Lookup error: {type(e).__name__}"))
    return out
