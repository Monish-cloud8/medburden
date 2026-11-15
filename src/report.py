"""Plain-English outputs: doctor questions, text/PDF note, optional LLM summary of the given flags."""
from __future__ import annotations

import io
import json
import re
from datetime import date

DISCLAIMER = ("This is a prototype and not medical advice. Always talk to a doctor or pharmacist before changing any medication. "
              "MedBurden checks medicines against published lists (ACB scale 2012, AGS Beers Criteria 2023) and can miss things.")


def _freq(f: str) -> str:
    return f" {f}" if f else ""


def questions(report: dict, items, who: str = "My relative") -> list[str]:
    who = who.strip() or "My relative"
    qs, done = [], set()
    by_item = {}
    for f in report["flags"]:
        if f["type"] == "beers":
            by_item.setdefault((f["drug"], f["ingredient"]), []).append(f)
    for (drug, ing), fl in by_item.items():
        it = next((i for i in items if i.name == drug), None)
        freq = _freq(it.frequency if it else "")
        contains = "" if drug.lower() == ing.lower() else f" It contains {ing}."
        scopes = {f["applies_to"] for f in fl}
        parts = []
        if "all older adults" in scopes:
            parts.append("the Beers Criteria say older adults should usually avoid")
        if "dementia or cognitive impairment" in scopes:
            parts.append("the Beers Criteria advise avoiding in people with dementia or memory problems")
        if "history of falls or fractures" in scopes:
            parts.append("the Beers Criteria advise avoiding after falls")
        reason = fl[0]["reason"].rstrip(".")
        cond = next((f["conditions"] for f in fl if f.get("conditions")), "")
        q = (f"{who} takes {drug}{freq}.{contains} This is a medicine that {' and '.join(dict.fromkeys(parts))}. "
             f"({reason}.) Is it still the right choice, or is there a safer option?")
        if cond:
            q += f" Note: {cond}"
        qs.append(q)
    for f in report["flags"]:
        if f["type"] == "duplicate" and f["ingredient"] not in done:
            done.add(f["ingredient"])
            qs.append(f"{f['drug']} both contain {f['ingredient']}. Is it safe to take them together, and what is the "
                      f"total daily amount?")
        elif f["type"] == "interaction":
            qs.append(f"{who} takes {f['drug']} together. {f['reason']} The Beers Criteria say: {f.get('conditions', '')} "
                      f"Is this combination still the best choice?")
        elif f["type"] == "sedation_stack":
            qs.append(f"{who} takes several medicines that act on the brain ({f['ingredient']}). {f['reason']} "
                      f"Could any of them be reduced or stopped safely?")
    if report["acb_level"] == "high":
        contrib = ", ".join(f"{k} ({v})" for k, v in report["acb_contributors"].items())
        qs.append(f"Together, these medicines add up to an anticholinergic burden score of {report['acb_total']} "
                  f"(3 or more is high): {contrib}. Higher scores are linked to confusion and memory problems. "
                  f"Could any of them be swapped for one with less anticholinergic effect?")
    for u in report["unmatched"] + report["needs_review"]:
        qs.append(f"We could not confidently identify \"{u['drug']}\". What is it, and what does it contain?")
    return qs


def note_text(report: dict, items, who: str = "My relative", qs: list | None = None) -> str:
    lines = [f"Questions for the doctor ({date.today():%d %b %Y})", ""]
    lines += [f"{i + 1}. {q}" for i, q in enumerate(qs or questions(report, items, who))] or ["No flags were found in the lists we check."]
    lines += ["", f"Total anticholinergic burden (ACB) score: {report['acb_total']} ({report['acb_level']})"
              + (" (incomplete: some medicines could not be identified)" if report["acb_incomplete"] else ""), "",
              "Medicines checked:"]
    lines += [f"- {it.name} {it.strength} {it.frequency}".rstrip() for it in items]
    lines += ["", "Sources: Anticholinergic Cognitive Burden Scale, 2012 update (Aging Brain Care); "
              "2023 AGS Beers Criteria (J Am Geriatr Soc 2023;71:2052-2081); RxNorm via NIH RxNav.", "", DISCLAIMER]
    return "\n".join(lines)


def note_pdf(report: dict, items, who: str = "My relative", qs: list | None = None) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
    from xml.sax.saxutils import escape

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
                            title="Questions for the doctor")
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=11, leading=15)
    small = ParagraphStyle("s", parent=body, fontSize=8.5, leading=11, textColor="#555555")
    story = [Paragraph("Questions for the doctor", ss["Title"]),
             Paragraph(f"Prepared {date.today():%d %B %Y} with MedBurden", small), Spacer(1, 10)]
    qs = qs or questions(report, items, who) or ["No flags were found in the lists we check."]
    story.append(ListFlowable([ListItem(Paragraph(escape(q), body), leftIndent=12) for q in qs], bulletType="1"))
    story += [Spacer(1, 10), Paragraph(f"<b>Total anticholinergic burden score:</b> {report['acb_total']} ({report['acb_level']})", body),
              Spacer(1, 6), Paragraph("<b>Medicines checked:</b> " + escape("; ".join(f"{i.name} {i.strength}".strip() for i in items)), body),
              Spacer(1, 14),
              Paragraph("Sources: Anticholinergic Cognitive Burden Scale, 2012 update (Aging Brain Care); 2023 AGS Beers "
                        "Criteria (J Am Geriatr Soc 2023;71:2052-2081); RxNorm via NIH RxNav.", small),
              Spacer(1, 6), Paragraph(escape(DISCLAIMER), small)]
    doc.build(story)
    return buf.getvalue()


# ----------------------------------------------------------------- optional LLM summary (flags in, words out)
SUMMARY_PROMPT = """You write a short, calm, plain-English summary (4-6 sentences) for a family caregiver.
Use ONLY the flags in the JSON you are given. Do not add drugs, side effects, doses or advice that are not in the JSON.
Do not tell them to stop or change any medicine; say to discuss it with the doctor or pharmacist."""


def llm_summary(report: dict) -> str | None:
    """Returns an LLM-written summary of the given flags, or None (no key, error, or failed safety check)."""
    from .extract import call_llm, llm_status
    from .score import tables
    if not report["flags"] or not llm_status()["ok"]:
        return None
    payload = {"acb_total": report["acb_total"], "acb_level": report["acb_level"],
               "flags": [{k: f.get(k) for k in ("type", "drug", "ingredient", "reason", "applies_to")} for f in report["flags"]]}
    try:
        text = call_llm(SUMMARY_PROMPT, json.dumps(payload), max_tokens=500).strip()
    except Exception:
        return None
    # Guard: reject the summary if it names any table drug that was not in the flags or the list.
    acb, beers, cns = tables()
    known = set(acb) | set(beers) | set(cns)
    allowed = {w.lower() for f in report["flags"] for w in re.findall(r"[a-z]+", f"{f.get('drug', '')} {f.get('ingredient', '')}".lower())}
    allowed |= {r["ingredient"] for r in report["rows"]}
    mentioned = {k for k in known if re.search(rf"\b{re.escape(k)}\b", text.lower())}
    if mentioned - allowed:
        return None
    return text
