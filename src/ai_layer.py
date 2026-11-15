"""AI layer: an LLM does the reading-heavy work, fixed tables check the result.

1. identify: for medicine names RxNav and the local list could not resolve, the LLM suggests the active ingredient(s).
   The suggestion is only a suggestion: it goes to "needs review" and is scored only after the user confirms it.
2. write: the LLM rewrites the checked findings as personal, plain-English questions for the doctor.
   Every rewrite is verified (same count, same medicines and numbers, no new medicines, no "stop taking" advice).
   If a rewrite fails the check, the standard wording is used instead.

Without an API key both steps are skipped and the app still works.
"""
from __future__ import annotations

import json
import re

from .extract import call_llm, llm_status, parse_json_reply

IDENTIFY_PROMPT = """You help a family caregiver identify medicines. For each written name, give the generic active
ingredient(s) in lowercase. The name may be a brand name, a misspelling or an OCR error.
Rules:
- Only answer if you have clearly seen this exact name as a real marketed medicine (brand or generic) or it is an obvious
  misspelling of one. Names that merely look or sound like a drug, or that you cannot place, get an empty list. Never guess,
  never pick the nearest-sounding drug, and never invent a drug. A wrong answer is far worse than an empty one.
- Confidence is how sure you are that this exact name is that medicine (0.9 or more only if you are certain).
- Return ONLY JSON: {"results": [{"name": str, "ingredients": [str], "confidence": 0.0-1.0}]}"""

WRITE_PROMPT = """You write questions for a family caregiver to ask an older adult's doctor.
You get numbered FACTS that were already checked against published tables. Rewrite each fact as one clear, warm,
plain-English question the caregiver can read aloud, in the same order.
Rules:
- Return ONLY JSON: {"questions": [str, ...]} with exactly one question per fact, in order.
- Keep every medicine name and every number from the fact. Add no other medicine, dose, side effect or claim.
- Never tell the caregiver to stop, skip, change or reduce a medicine. Ask the doctor instead.
- Use short sentences and everyday words. No headings, no lists, no medical jargon without explaining it."""

STOP_LANGUAGE = re.compile(
    r"\b(you should (stop|discontinue|quit|skip)|stop taking|discontinue (the|this|these|it)|do not take|don't take|quit taking|"
    r"should be stopped|must be stopped|need to stop)\b", re.I)


def ai_available() -> bool:
    try:
        return bool(llm_status()["ok"])
    except Exception:
        return False


# ------------------------------------------------------------------ 1. identify
_ident_cache: dict[str, dict] = {}


def _ask_identify(names: list[str]) -> dict[str, dict]:
    data = parse_json_reply(call_llm(IDENTIFY_PROMPT, json.dumps({"names": names}), max_tokens=1500))
    out = {}
    for r in data.get("results", []):
        if not isinstance(r, dict):
            continue
        ings = sorted({str(i).strip().lower() for i in (r.get("ingredients") or []) if str(i).strip()})
        try:
            conf = float(r.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        out[str(r.get("name", "")).strip().lower()] = {"ingredients": ings, "confidence": max(0.0, min(1.0, conf))}
    return out


def suggest_ingredients(names: list[str]) -> dict[str, dict]:
    """name -> {"ingredients": [...], "confidence": float}. An empty list means the AI did not recognise the name.
    The AI is asked twice, with the names in a different order, and a suggestion is kept only if both answers agree.
    This cuts down on confident guesses for names that are not real medicines."""
    todo = [n for n in dict.fromkeys(n.strip() for n in names) if n and n not in _ident_cache]
    if todo and ai_available():
        try:
            first, second = _ask_identify(todo), _ask_identify(list(reversed(todo)))
            for n in todo:
                a, b = first.get(n.lower(), {}), second.get(n.lower(), {})
                if a and b and a["ingredients"] == b["ingredients"]:
                    _ident_cache[n] = {"ingredients": a["ingredients"], "confidence": min(a["confidence"], b["confidence"])}
                else:
                    _ident_cache[n] = {"ingredients": [], "confidence": 0.0}
        except Exception:
            pass
    return {n: _ident_cache[n] for n in names if n in _ident_cache}


def apply_ai_identification(norms, min_conf: float = 0.8) -> int:
    """Second opinion for names the lookups could not settle (unmatched, or only a weak "needs review" guess).
    The AI's ingredients become the suggestion, still "needs review": nothing is scored until the user confirms.
    Returns how many names got a new suggestion."""
    todo = [n for n in norms if n.status in ("unmatched", "needs_review") and re.search(r"[A-Za-z]{3,}", n.input_name)]
    if not todo:
        return 0
    sugg = suggest_ingredients([n.input_name for n in todo])
    count = 0
    for n in todo:
        s = sugg.get(n.input_name.strip())
        if not s or not s["ingredients"] or s["confidence"] < min_conf:
            continue
        old = ", ".join(i["name"] for i in n.ingredients)
        if n.status == "needs_review" and {i["name"] for i in n.ingredients} == set(s["ingredients"]):
            continue          # the AI agrees with the lookup: leave it for the user to confirm as before
        n.status, n.method = "needs_review", "ai suggestion"
        n.ingredients = [{"name": i, "rxcui": ""} for i in s["ingredients"]]
        n.matched_name = " + ".join(s["ingredients"])
        n.note = (f"The AI thinks this contains {n.matched_name}"
                  + (f" (the drug list guessed {old})" if old else "")
                  + ". This is a suggestion only. Confirm with the label or the pharmacist before relying on it.")
        count += 1
    return count


# ------------------------------------------------------------------ 2. write
def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s))


def check_rewrite(fact: str, text: str, known: set[str]) -> bool:
    """True only if the rewrite keeps the fact's medicines and numbers, adds no new medicine, and gives no stop advice."""
    if not text or STOP_LANGUAGE.search(text):
        return False
    low_f, low_t = fact.lower(), text.lower()
    has = lambda k, s: re.search(rf"\b{re.escape(k)}\b", s) is not None
    need = {k for k in known if has(k, low_f)}
    if any(not has(k, low_t) for k in need):
        return False
    if any(has(k, low_t) and k not in need for k in known):
        return False
    return _numbers(fact) <= _numbers(text)


_write_cache: dict[tuple, tuple[list[str], bool]] = {}


def write_questions(facts: list[str], who: str = "") -> tuple[list[str], bool]:
    """Returns (questions, written_by_ai). Falls back to the standard wording whenever the AI is unavailable or fails the check."""
    if not facts or not ai_available():
        return facts, False
    key = (tuple(facts), who)
    if key in _write_cache:
        return _write_cache[key]
    from .score import tables
    acb, beers, cns = tables()
    known = {k.lower() for k in (set(acb) | set(beers) | set(cns))}
    out = (facts, False)
    try:
        payload = {"person": who or "my relative", "facts": [f"{i + 1}. {f}" for i, f in enumerate(facts)]}
        data = parse_json_reply(call_llm(WRITE_PROMPT, json.dumps(payload), max_tokens=3000))
        qs = [str(q).strip() for q in data.get("questions", [])]
        if len(qs) == len(facts):
            # Each rewrite is checked on its own; a failing one keeps the standard wording.
            final, ok_any = [], False
            for f, q in zip(facts, qs):
                if check_rewrite(f, q, known):
                    final.append(q)
                    ok_any = True
                else:
                    final.append(f)
            out = (final, ok_any)
    except Exception:
        pass
    _write_cache[key] = out
    return out
