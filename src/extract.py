"""Turn a pasted list or a photo into structured medication items.

Order of preference:
  1. LLM (ANTHROPIC_API_KEY or OPENAI_API_KEY) for text or images
  2. No key: rule-based parser for text; for images, local OCR (tesseract) + parser if available
The LLM only extracts what is written. It never decides risk.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict, field

import requests

from .config import secret, anthropic_model, openai_model, openai_effort, LLM_TIMEOUT


@dataclass
class MedItem:
    name: str                 # drug name as written
    strength: str = ""
    dose: str = ""
    frequency: str = ""
    confidence: float = 0.5
    source: str = "parser"
    notes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ----------------------------------------------------------------- rule-based parser
STRENGTH_RE = re.compile(
    r"(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)*)\s*(mg|mcg|µg|ug|g|ml|mL|meq|mEq|units?|iu|IU|%)(?![a-z])", re.I)
COMBO_STRENGTH_RE = re.compile(r"\b(\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?)\b")
DOSE_RE = re.compile(r"\b(\d+(?:\.\d+)?|one|two|three|half|1/2)\s*(tabs?|tablets?|caps?|capsules?|caplets?|pills?|puffs?|"
                     r"drops?|patch(?:es)?|softgels?|gelcaps?|sprays?|teaspoons?|tsp)\b", re.I)
FREQ_PATTERNS = [
    r"once (?:a )?daily", r"twice (?:a )?daily", r"three times (?:a )?daily", r"four times (?:a )?daily",
    r"(?:once|twice|three times) a day", r"every \d+(?:\s*-\s*\d+)? ?(?:hours|hrs|h)\b", r"q\s?\d+h\b",
    r"every (?:morning|night|evening|day|other day)", r"in the (?:morning|evening)", r"at (?:bedtime|night)",
    r"before meals", r"with meals", r"\bnightly\b", r"\bdaily\b", r"\bweekly\b", r"\bqhs\b", r"\bqam\b", r"\bqd\b",
    r"\bbid\b", r"\btid\b", r"\bqid\b", r"\bprn\b", r"as needed(?: for [a-z ]+)?", r"a day",
]
FREQ_RE = re.compile("|".join(f"(?:{p})" for p in FREQ_PATTERNS), re.I)
HEADER_RE = re.compile(r"^(medications?|medicines?|med list|medication list|medicine list|current medications|meds|my meds|list|rx|"
                       r"patient|name|dob|date|allergies)\b[: ]*|^[a-z]+'s (meds|medicines|medications|pills)\b", re.I)
# Pharmacy-label lines that are not medicine names (pill-bottle photos)
LABEL_NOISE_RE = re.compile(r"\b(pharmacy|refills?|qty|quantity|rx\s*#|rx\s*no|ndc|prescriber|dr\.|md\b|filled|fill date|"
                            r"exp(ires|iration)?|discard|warning|caution|keep out|store at|mfg|manufacturer|phone|tel\b|"
                            r"street|avenue|ave\b|suite)\b|^\s*(dr|rx)\b|\(\d{3}\)", re.I)
INSTRUCTION_RE = re.compile(r"^\s*(take|apply|use|inhale|place|insert|chew|dissolve|instill)\b", re.I)
STOP_WORDS = {"take", "takes", "taking", "tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "by", "mouth",
              "po", "oral", "orally", "of", "for", "-", "–", ":", "the"}


def _clean_name(s: str) -> str:
    s = re.sub(r"^[\s\-\*•·\d]+[.)]\s*", "", s)          # "1. ", "2) "
    s = re.sub(r"^[\s\-\*•·]+", "", s)
    s = re.sub(r"[\(\)\[\],;:]+", " ", s)
    words = [w for w in s.split() if w.lower() not in STOP_WORDS]
    return " ".join(words).strip(" .-")


def parse_line(line: str) -> MedItem | None:
    raw = line.strip()
    if not raw or not re.search(r"[A-Za-z]{3,}", raw):
        return None
    if HEADER_RE.match(raw) and not STRENGTH_RE.search(raw):
        return None
    strength = ""
    m = STRENGTH_RE.search(raw)
    cut = len(raw)
    if m:
        strength = re.sub(r"\s+", " ", m.group(0)).strip()
        cut = m.start()
    else:
        m2 = COMBO_STRENGTH_RE.search(raw)     # e.g. "Norco 5/325"
        if m2:
            strength = m2.group(1).replace(" ", "")
            cut = m2.start()
    dose_m = DOSE_RE.search(raw)
    dose = dose_m.group(0) if dose_m else ""
    freqs = [f.group(0) for f in FREQ_RE.finditer(raw)]
    frequency = " ".join(dict.fromkeys(f.strip() for f in freqs))
    if dose_m and dose_m.start() < cut:
        cut = dose_m.start()
    f1 = FREQ_RE.search(raw)
    if f1 and f1.start() < cut:
        cut = f1.start()
    name = _clean_name(raw[:cut])
    if not re.search(r"[A-Za-z]{3,}", name):
        return None
    conf = 0.9 if strength else 0.7
    if len(name) < 4:
        conf = 0.4
    return MedItem(name=name, strength=strength, dose=dose, frequency=frequency, confidence=conf, source="parser")


def fix_ocr(line: str) -> str:
    """Common OCR confusions inside words: '!' or '|' for 'l', '0' between letters for 'o'."""
    line = re.sub(r"(?<=[A-Za-z])[!|](?=[\s,.]|$)", "l", line)
    line = re.sub(r"(?<=[A-Za-z])[!|](?=[A-Za-z])", "l", line)
    return re.sub(r"(?<=[A-Za-z])0(?=[A-Za-z])", "o", line)


def _plausible_name(name: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", name)
    if len(letters) < 4 or len(set(letters.lower())) < 3:
        return False
    return bool(re.search(r"[aeiouy]", letters, re.I))


def parse_text(text: str, ocr: bool = False) -> list[MedItem]:
    """One medicine per line. Pharmacy-label lines (pharmacy name, Rx #, refills...) are skipped, and a
    'TAKE 1 TABLET TWICE DAILY' line is attached to the medicine above it."""
    items = []
    lines = [fix_ocr(ln) if ocr else ln for ln in re.split(r"[\n;]+", text or "")]
    is_label = sum(bool(LABEL_NOISE_RE.search(ln)) for ln in lines) >= 2   # looks like a pharmacy label
    for line in lines:
        if not line.strip() or LABEL_NOISE_RE.search(line):
            continue
        if INSTRUCTION_RE.match(line):
            if items:
                d = DOSE_RE.search(line)
                fr = " ".join(dict.fromkeys(f.group(0).strip() for f in FREQ_RE.finditer(line)))
                items[-1].dose = items[-1].dose or (d.group(0) if d else "")
                items[-1].frequency = items[-1].frequency or fr
            continue
        it = parse_line(line)
        if it and is_label and not it.strength:
            continue          # on a label, the patient's name and other lines without a strength are not medicines
        if it and (_plausible_name(it.name) or it.strength):
            items.append(it)
    return items


# ----------------------------------------------------------------- OCR fallback
def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


OCR_INSTALL_HELP = ("Photo reading without an AI key needs the free Tesseract OCR program. Install it with "
                    "`brew install tesseract` (Mac) or `sudo apt install tesseract-ocr` (Linux). On Streamlit Cloud it is "
                    "installed from packages.txt. You can also type or paste the list instead.")


def ocr_status() -> dict:
    if not ocr_available():
        return {"ok": False, "message": "Tesseract not installed. " + OCR_INSTALL_HELP}
    try:
        v = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=10)
        ver = (v.stdout or v.stderr).splitlines()[0] if (v.stdout or v.stderr) else "tesseract"
        return {"ok": True, "message": f"{ver} installed"}
    except Exception as e:
        return {"ok": False, "message": f"Tesseract found but failed to run ({type(e).__name__}). " + OCR_INSTALL_HELP}


def ocr_image(image_bytes: bytes, timeout: float = 60) -> str:
    if not ocr_available():
        raise RuntimeError(OCR_INSTALL_HELP)
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(image_bytes)
        f.flush()
        r = subprocess.run(["tesseract", f.name, "stdout", "--psm", "6"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"OCR failed: {r.stderr.strip()[:200]}")
    return r.stdout


# ----------------------------------------------------------------- LLM extraction
EXTRACT_PROMPT = """You extract medication lists. Read the list or photo and return ONLY JSON:
{"medications": [{"name_as_written": str, "strength": str, "dose": str, "frequency": str, "confidence": number 0-1}]}
Rules:
- One entry per product line. Copy the drug or brand name exactly as written, including typos. Do not translate brand names into generics.
- Do not add drugs that are not written. Do not give medical advice or risk opinions.
- Leave a field as "" if it is not written. Lower the confidence if text is hard to read."""


def llm_provider() -> str | None:
    if secret("ANTHROPIC_API_KEY"):
        return "anthropic"
    if secret("OPENAI_API_KEY"):
        return "openai"
    return None


def _image_media_type(b: bytes) -> str:
    if b[:8].startswith(b"\x89PNG"):
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


class LLMError(RuntimeError):
    """An LLM call failed for a reason the user can fix (missing key, unknown model, bad key)."""


_STATUS_CACHE: dict = {}


def llm_status(check_model: bool = True) -> dict:
    """{"ok", "provider", "model", "message"}. Checks that the key works and the model exists (cached).
    Never raises."""
    prov = llm_provider()
    if not prov:
        return {"ok": False, "provider": None, "model": None,
                "message": "No AI key set (ANTHROPIC_API_KEY or OPENAI_API_KEY). Photo reading by AI, the AI summary "
                           "and the LLM-only baseline are off. Pasted text works without a key."}
    model = anthropic_model() if prov == "anthropic" else openai_model()
    key = (prov, model)
    if key in _STATUS_CACHE:
        return _STATUS_CACHE[key]
    res = {"ok": True, "provider": prov, "model": model, "message": f"{prov} · {model}"}
    if check_model:
        try:
            if prov == "anthropic":
                r = requests.get("https://api.anthropic.com/v1/models?limit=1000", timeout=15,
                                 headers={"x-api-key": secret("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})
            else:
                r = requests.get("https://api.openai.com/v1/models", timeout=15,
                                 headers={"Authorization": f"Bearer {secret('OPENAI_API_KEY')}"})
            if r.status_code in (401, 403):
                res = {**res, "ok": False, "message": f"The {prov} API key was rejected ({r.status_code}). Check the key."}
            elif r.ok:
                ids = {m.get("id") for m in r.json().get("data", [])}
                if ids and model not in ids:
                    env = "ANTHROPIC_MODEL" if prov == "anthropic" else "OPENAI_MODEL"
                    sample = ", ".join(sorted(i for i in ids if i)[:8])
                    res = {**res, "ok": False, "message": f"Model '{model}' is not available for this {prov} key. "
                                                          f"Set {env} to one of: {sample}..."}
            else:
                res = {**res, "message": res["message"] + f" (could not verify the model: HTTP {r.status_code})"}
        except Exception as e:
            res = {**res, "message": res["message"] + f" (could not verify the model: {type(e).__name__})"}
    _STATUS_CACHE[key] = res
    return res


def _raise_for(r, prov, model):
    if r.ok:
        return
    try:
        detail = r.json().get("error", {})
        detail = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    except Exception:
        detail = r.text[:200]
    if r.status_code in (401, 403):
        raise LLMError(f"The {prov} API key was rejected: {detail}")
    if r.status_code == 404 or "model" in detail.lower():
        raise LLMError(f"The {prov} model '{model}' was not found or is not allowed: {detail}")
    raise LLMError(f"{prov} API error {r.status_code}: {detail}")


def call_llm(system: str, user_text: str, image_bytes: bytes | None = None, max_tokens: int = 1500) -> str:
    """Single LLM call; returns the text reply. Raises LLMError / requests errors (callers fall back)."""
    prov = llm_provider()
    if prov == "anthropic":
        model = anthropic_model()
        content = []
        if image_bytes:
            content.append({"type": "image", "source": {"type": "base64", "media_type": _image_media_type(image_bytes),
                                                        "data": base64.b64encode(image_bytes).decode()}})
        content.append({"type": "text", "text": user_text})
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=LLM_TIMEOUT,
                          headers={"x-api-key": secret("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": model, "max_tokens": max_tokens,
                                "system": system, "messages": [{"role": "user", "content": content}]})
        _raise_for(r, prov, model)
        return "".join(b.get("text", "") for b in r.json().get("content", []))
    if prov == "openai":
        model = openai_model()
        content = [{"type": "text", "text": user_text}]
        if image_bytes:
            url = f"data:{_image_media_type(image_bytes)};base64,{base64.b64encode(image_bytes).decode()}"
            content.append({"type": "image_url", "image_url": {"url": url}})
        # Newer OpenAI models take max_completion_tokens and reject non-default temperature, so neither is forced.
        body = {"model": model, "max_completion_tokens": max(max_tokens, 4000),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        effort = openai_effort()
        if effort:
            body["reasoning_effort"] = effort   # "low" by default: this task is simple reading and rewording
        post = lambda b: requests.post("https://api.openai.com/v1/chat/completions", timeout=LLM_TIMEOUT,
                                       headers={"Authorization": f"Bearer {secret('OPENAI_API_KEY')}"}, json=b)
        r = post(body)
        if r.status_code == 400 and "reasoning_effort" in r.text and "reasoning_effort" in body:
            body.pop("reasoning_effort")        # this model does not accept the setting: retry without it
            r = post(body)
        _raise_for(r, prov, model)
        return r.json()["choices"][0]["message"]["content"] or ""
    raise LLMError("No LLM API key set.")


def parse_json_reply(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("LLM reply contained no JSON")
    return json.loads(m.group(0))


def llm_extract(text: str | None = None, image_bytes: bytes | None = None) -> list[MedItem]:
    user = "Extract the medications from this photo." if image_bytes else f"Extract the medications from this list:\n\n{text}"
    data = parse_json_reply(call_llm(EXTRACT_PROMPT, user, image_bytes))
    items = []
    for m in data.get("medications", []):
        name = str(m.get("name_as_written", "")).strip()
        if not name:
            continue
        try:
            conf = float(m.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        items.append(MedItem(name=name, strength=str(m.get("strength", "") or ""), dose=str(m.get("dose", "") or ""),
                             frequency=str(m.get("frequency", "") or ""), confidence=max(0.0, min(1.0, conf)), source="llm"))
    return items


# ----------------------------------------------------------------- top level
def extract(text: str | None = None, image_bytes: bytes | None = None, use_llm: bool = True) -> tuple[list[MedItem], str, list[str]]:
    """Returns (items, method, warnings). Never raises."""
    warnings = []
    if use_llm and llm_provider():
        st = llm_status()
        if not st["ok"]:
            warnings.append(f"AI reader not available: {st['message']} Used the basic reader instead.")
        else:
            try:
                items = llm_extract(text=text, image_bytes=image_bytes)
                return items, f"llm:{llm_provider()}", warnings
            except LLMError as e:
                warnings.append("The AI reader could not process this input (for example an unsupported or damaged image). Used the basic reader instead.")
            except Exception as e:
                warnings.append(f"The AI reader failed ({type(e).__name__}). Used the basic reader instead.")
    if image_bytes is not None:
        try:
            ocr = ocr_image(image_bytes)
            items = parse_text(ocr, ocr=True)
            for it in items:
                it.source, it.confidence = "ocr+parser", min(it.confidence, 0.6)
            warnings.append("Read the photo with basic offline OCR. Please check every line carefully.")
            return items, "ocr+parser", warnings
        except Exception as e:
            warnings.append(f"Could not read the photo: {e}")
            return [], "none", warnings
    return parse_text(text or ""), "parser", warnings
