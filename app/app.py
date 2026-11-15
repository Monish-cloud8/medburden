"""MedBurden: spot medicines that can cause confusion, falls or memory problems, and prepare doctor questions.

Run: streamlit run app/app.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extract import MedItem, extract, llm_status, ocr_status          # noqa: E402
from src.normalize import RxNavClient, normalize_all                       # noqa: E402
from src.score import score                                                # noqa: E402
from src.report import questions, note_text, note_pdf, llm_summary, DISCLAIMER  # noqa: E402

st.set_page_config(page_title="MedBurden", page_icon="💊", layout="wide")
st.markdown("""
<style>
 .block-container {max-width: 1100px; padding-top: 1.4rem;}
 .mb-disclaimer {background:#FFF4DC; border:2px solid #E9C46A; color:#5C4100; border-radius:12px;
                 padding:12px 16px; font-size:1rem; margin:6px 0 14px 0; line-height:1.4;}
 .mb-card {border-radius:12px; padding:12px 16px; margin:8px 0; border:1px solid #E3E8EB; background:#FAFBFC; line-height:1.45;}
 .mb-flag {border-left:6px solid #C2553D;} .mb-dup {border-left:6px solid #B7791F;}
 .mb-stack {border-left:6px solid #6B5BA8;} .mb-int {border-left:6px solid #2F6F8F;}
 .mb-src {color:#5F6B71; font-size:0.82rem; margin-top:4px;}
 .mb-meter-box {border-radius:16px; padding:16px 18px; margin:6px 0 10px 0; border:1px solid #E3E8EB;}
 .mb-score {font-size:2.6rem; font-weight:800; line-height:1;}
 .mb-level {font-size:1.25rem; font-weight:700; margin-left:10px;}
 .mb-meter {height:26px; border-radius:13px; position:relative; margin:14px 0 6px 0;
            background:linear-gradient(90deg,#3E9C6E 0%,#3E9C6E 16.6%,#E0A526 16.6%,#E0A526 50%,#C2553D 50%,#C2553D 100%);}
 .mb-pin {position:absolute; top:-8px; width:8px; height:42px; background:#1E2A30; border:2px solid #fff; border-radius:4px;}
 .mb-scale {display:flex; justify-content:space-between; font-size:0.8rem; color:#5F6B71;}
 @media (max-width: 640px) {
   .block-container {padding-left:0.7rem; padding-right:0.7rem;}
   .mb-score {font-size:2.1rem;} h1 {font-size:1.7rem !important;}
   .mb-card {padding:10px 12px;}
   div[data-testid="stHorizontalBlock"] {flex-wrap:wrap; gap:0.4rem;}
   div[data-testid="stHorizontalBlock"] > div {min-width:100% !important;}
 }
</style>""", unsafe_allow_html=True)


def wide(fn, *args, **kwargs):
    """Full-width element on both new Streamlit (width="stretch") and older versions (use_container_width)."""
    try:
        return fn(*args, width="stretch", **kwargs)
    except Exception as e:
        if "width" not in str(e) and not isinstance(e, TypeError):
            raise
        return fn(*args, use_container_width=True, **kwargs)


def disclaimer():
    st.markdown(f"<div class='mb-disclaimer'>⚠️ {DISCLAIMER}</div>",
                unsafe_allow_html=True)


@st.cache_resource
def rx_client():
    return RxNavClient()


@st.cache_data(ttl=600, show_spinner=False)
def cached_llm_status():
    return llm_status()


def run_pipeline(items, patient, accepted=None):
    norms = normalize_all([i.name for i in items], rx_client())
    for idx in (accepted or []):           # user confirmed a suggestion
        if idx < len(norms) and norms[idx].status == "needs_review" and norms[idx].ingredients:
            norms[idx].status = "matched"
            norms[idx].note = "Suggestion confirmed by the user."
    return norms, score(items, norms, patient)


# ----------------------------------------------------------------- shared results view
def meter(total, level, incomplete):
    pos = min(total, 6) / 6 * 100
    color = {"low": "#2E7D57", "moderate": "#A6740B", "high": "#B23A24"}[level]
    label = {"low": "Low", "moderate": "Moderate", "high": "High"}[level]
    bg = {"low": "#EEF7F1", "moderate": "#FDF6E3", "high": "#FBECE8"}[level]
    st.markdown(f"""<div class='mb-meter-box' style='background:{bg}'>
      <div>Anticholinergic burden score</div>
      <div><span class='mb-score' style='color:{color}'>{total}</span><span class='mb-level' style='color:{color}'>{label}</span></div>
      <div class='mb-meter'><div class='mb-pin' style='left:calc({pos}% - 4px)'></div></div>
      <div class='mb-scale'><span>0 low</span><span>1-2 moderate</span><span>3+ high</span><span>6+</span></div>
      <div class='mb-src'>Scores from the Anticholinergic Cognitive Burden Scale (2012 update). "3 or more = high" is a project
      threshold widely used in research.{' <b>Incomplete: some medicines could not be identified.</b>' if incomplete else ''}</div>
    </div>""", unsafe_allow_html=True)


def render_results(items, norms, rep, who, key):
    meter(rep["acb_total"], rep["acb_level"], rep["acb_incomplete"])
    if rep["age_note"]:
        st.info(rep["age_note"])

    st.subheader("What to ask about")
    flags = rep["flags"]
    if not flags:
        if len(items) > len(rep["needs_review"]) + len(rep["unmatched"]):
            st.success("No Beers Criteria, duplicate or combination flags among the identified medicines.")
        else:
            st.info("No medicines could be identified, so nothing was checked. This is not a sign that the list is safe.")
    style = {"beers": "mb-flag", "duplicate": "mb-dup", "sedation_stack": "mb-stack", "interaction": "mb-int"}
    for f in flags:
        title = {"beers": f"🚩 {f['drug']} → {f['ingredient']} · {f.get('applies_to', '')}",
                 "duplicate": f"🔁 Same ingredient twice: {f['ingredient']}",
                 "sedation_stack": f"😴 Sedating medicines together: {f['ingredient']}",
                 "interaction": f"⚠️ Combination to review: {f['drug']}"}.get(f["type"], f["type"])
        extra = f"<br><i>{f['conditions']}</i>" if f.get("conditions") else ""
        st.markdown(f"<div class='mb-card {style.get(f['type'], '')}'><b>{title}</b><br>{f['reason']}{extra}"
                    f"<div class='mb-src'>Source: {f['source']}</div></div>", unsafe_allow_html=True)

    st.subheader("Questions for your doctor")
    qs = questions(rep, items, who)
    if qs:
        for q in qs:
            st.markdown(f"- {q}")
    else:
        st.markdown("No questions were generated. You can still bring the full list to the next appointment.")
    c1, c2 = st.columns(2)
    pdf = _pdf(rep, items, who)
    if pdf:
        wide(c1.download_button, "⬇️ Download as PDF", pdf, "questions_for_doctor.pdf", mime="application/pdf", key=f"{key}_pdf")
    else:
        c1.caption("PDF not available here. Please use the text version.")
    wide(c2.download_button, "⬇️ Download as text", note_text(rep, items, who), "questions_for_doctor.txt", key=f"{key}_txt")
    if cached_llm_status()["ok"] and flags:
        if st.button("✍️ Write a short plain-English summary of these flags", key=f"{key}_sum"):
            with st.spinner("Writing..."):
                s = llm_summary(rep)
            if s:
                st.markdown(f"<div class='mb-card'>{s}<div class='mb-src'>Written by AI from the flags above only. "
                            "The flags themselves come from the cited tables.</div></div>", unsafe_allow_html=True)
            else:
                st.caption("Summary not available. The flags above are the full result.")

    with st.expander("How each medicine was identified", expanded=bool(rep["needs_review"] or rep["unmatched"])):
        badge = {"matched": "✅ matched", "needs_review": "❓ please confirm", "unmatched": "⛔ not identified"}
        wide(st.dataframe, pd.DataFrame([{
            "Written as": it.name, "Status": badge[nr.status], "Ingredient(s)": ", ".join(i["name"] for i in nr.ingredients),
            "How": nr.method, "Note": nr.note} for it, nr in zip(items, norms)]), hide_index=True)
    if rep["needs_review"] or rep["unmatched"]:
        st.warning("Medicines marked ❓ or ⛔ were **not** checked. Fix the spelling, confirm the suggestion, "
                   "or ask the pharmacist what they contain.")
    with st.expander("Full risk table"):
        wide(st.dataframe, pd.DataFrame([{
            "Drug": r["drug"], "Ingredient": r["ingredient"], "ACB": "—" if r["acb"] is None else str(r["acb"]),
            "Beers": "; ".join(f"{b['recommendation']} ({b['applies_to']})" for b in r["beers"]) or "—",
            "Reason": r["reason"] or "—", "Source": r["source"]} for r in rep["rows"]]),
            hide_index=True)


def _pdf(rep, items, who):
    try:
        return note_pdf(rep, items, who)
    except Exception:
        return None


def status_panel():
    ls, os_ = cached_llm_status(), ocr_status()
    with st.expander("⚙️ Status: AI reader, photo reading, drug lookup", expanded=not ls["ok"] and False):
        (st.success if ls["ok"] else st.info)(f"AI reader: {ls['message']}")
        (st.success if os_["ok"] else st.warning)(f"Offline photo reading: {os_['message']}")
        rx = rx_client().reachable
        st.write("Drug lookup (NIH RxNav): " + ("reachable" if rx else "not reached yet" if rx is None else
                                                 "not reachable. Using the saved cache and the local drug list."))


# ----------------------------------------------------------------- page
st.title("💊 MedBurden")
st.markdown("Spot medicines that can cause **confusion, falls or memory problems** in older adults, "
            "and get plain-English questions to take to the doctor.")
disclaimer()

tab_check, tab_demo, tab_acc, tab_about = st.tabs(["Check medications", "Demo cases", "Accuracy", "About"])

FEATURED = json.loads((ROOT / "data" / "demo_cases.json").read_text())["cases"][0]

with tab_check:
    status_panel()
    if "booted" not in st.session_state:   # preload the featured story so the burden meter is visible on first load
        st.session_state["booted"] = True
        _it, _m, _w = extract(text=FEATURED["text"], use_llm=False)
        st.session_state["items_df"] = pd.DataFrame([i.to_dict() for i in _it])
        st.session_state["extract_info"] = (_m, _w)
        st.session_state["check"] = (_it, FEATURED["patient"])
        st.caption("Showing a made-up example. Replace the list below with your own medicines.")
    c1, c2 = st.columns([3, 1])
    who = c1.text_input("Who is this for? (used in the doctor note)", "Mom")
    age = c2.number_input("Age", min_value=0, max_value=120, value=FEATURED["patient"]["age"])
    c3, c4 = st.columns(2)
    dementia = c3.checkbox("Dementia or memory problems", value=True)
    falls = c4.checkbox("Had a fall in the past year", value=FEATURED["patient"]["falls"])
    patient = {"age": int(age), "dementia": dementia, "falls": falls}

    mode = st.radio("How do you want to add the list?", ["Paste or type", "Upload a photo"], horizontal=True)
    text, img = None, None
    if mode == "Paste or type":
        text = st.text_area("One medicine per line", height=150,
                            value=FEATURED["text"])
    else:
        up = st.file_uploader("Photo of a medication list or pill bottle", type=["png", "jpg", "jpeg", "webp"])
        img = up.getvalue() if up else None
        if img:
            st.image(img, width=320)
        ls, os_ = cached_llm_status(), ocr_status()
        if not ls["ok"] and not os_["ok"]:
            st.warning("Photos can't be read right now: no AI key is set and Tesseract is not installed. "
                       "Please type or paste the list instead. " + os_["message"])
        elif not ls["ok"]:
            st.caption("No AI key, so photos are read with basic offline OCR. Clear, typed lists work best.")

    if st.button("Read the list", type="primary", disabled=not (text or img)):
        with st.spinner("Reading..."):
            got, method, warns = extract(text=text, image_bytes=img)
        st.session_state["items_df"] = pd.DataFrame([i.to_dict() for i in got] or
                                                    [{"name": "", "strength": "", "dose": "", "frequency": "", "confidence": 0.0}])
        st.session_state["extract_info"] = (method, warns)
        st.session_state.pop("check", None)

    if "items_df" in st.session_state:
        method, warns = st.session_state["extract_info"]
        for w in warns:
            st.warning(w)
        st.markdown(f"**Check the list and fix anything that's wrong** (read with `{method}`). "
                    "Tap a cell to edit it. You can add or delete rows.")
        edited = wide(st.data_editor, st.session_state["items_df"][["name", "strength", "dose", "frequency", "confidence"]],
                                num_rows="dynamic", key="editor",
                                column_config={"confidence": st.column_config.NumberColumn(format="%.1f", disabled=True)})
        if st.button("Check these medicines", type="primary"):
            items = [MedItem(name=str(r["name"]).strip(), strength=str(r.get("strength") or ""), dose=str(r.get("dose") or ""),
                             frequency=str(r.get("frequency") or ""), confidence=float(r.get("confidence") or 0))
                     for _, r in edited.iterrows() if str(r.get("name") or "").strip() and str(r["name"]) != "nan"]
            st.session_state["check"] = (items, patient)

    if "check" in st.session_state:
        items, patient_c = st.session_state["check"]
        with st.spinner("Looking up medicines..."):
            norms, _ = run_pipeline(items, patient_c)
        review = [i for i, n in enumerate(norms) if n.status == "needs_review" and n.ingredients]
        accepted = []
        if review:
            st.markdown("**Please confirm these suggestions** (only tick if you're sure):")
            for i in review:
                if st.checkbox(f"\"{items[i].name}\" is {norms[i].matched_name} "
                               f"({', '.join(x['name'] for x in norms[i].ingredients)})", key=f"acc_{i}"):
                    accepted.append(i)
        norms2, rep = run_pipeline(items, patient_c, accepted)
        st.divider()
        render_results(items, norms2, rep, who, "check")
    disclaimer()

with tab_demo:
    st.markdown("Made-up examples that run in one click. They work without an AI key.")
    demos = json.loads((ROOT / "data" / "demo_cases.json").read_text())["cases"]
    for i, d in enumerate(demos):
        with st.container(border=True):
            st.markdown(f"**{d['title']}**")
            st.code(d["text"], language=None)
            if wide(st.button, "Run this case", key=f"demo_{i}"):
                st.session_state["demo"] = ("text", i)
    st.markdown("**Sample photos.** These are read by the AI if a key is set, otherwise by offline OCR.")
    photos = sorted((ROOT / "demo").glob("*.png"))
    pcols = st.columns(len(photos) or 1)
    for j, (col, ph) in enumerate(zip(pcols, photos)):
        with col:
            wide(st.image, str(ph))
            if wide(st.button, "Read this photo", key=f"photo_{j}"):
                st.session_state["demo"] = ("photo", j)
    if "demo" in st.session_state:
        kind, i = st.session_state["demo"]
        st.divider()
        if kind == "text":
            d = demos[i]
            items, method, warns = extract(text=d["text"], use_llm=False)
            title, who_d, pat = d["title"], d["who"], d["patient"]
        else:
            items, method, warns = extract(image_bytes=photos[i].read_bytes())
            title, who_d, pat = f"Photo: {photos[i].stem.replace('_', ' ')}", "My relative", {"age": 80, "dementia": True, "falls": False}
            st.caption(f"Read with `{method}` · assumed: age 80, dementia")
        for w in warns:
            st.warning(w)
        st.markdown(f"### {title}")
        if items:
            norms, rep = run_pipeline(items, pat)
            render_results(items, norms, rep, who_d, f"demo_{kind}_{i}")
    disclaimer()

with tab_acc:
    p = ROOT / "results" / "metrics.json"
    if not p.exists():
        st.info("Run `bash run_all.sh` to produce the evaluation.")
    else:
        m = json.loads(p.read_text())
        s, r, b = m["setup"], m["medburden"], m["llm_only_baseline"]

        def pct(x):
            return "n/a" if x is None or x == "" or x != x else f"{100 * float(x):.0f}%"
        st.markdown(f"Tested on **{s['cases']} made-up medication lists** ({s['image_cases']} as photos) with "
                    "hand-written answers.")
        st.caption(f"Run conditions: extraction {s['extraction_methods']}; RxNav {s['rxnav']}.")
        cp = ROOT / "results" / "comparison.csv"
        if cp.exists():
            rows = list(csv.DictReader(open(cp)))
            df = pd.DataFrame([{"Metric": x["metric"], "MedBurden": pct(x["medburden"]),
                                "LLM only (no tables)": pct(x["llm_only"]) if x["llm_only"] else "not run"} for x in rows])
            wide(st.dataframe, df, hide_index=True)
            chart = pd.DataFrame({"MedBurden": [float(x["medburden"]) * 100 for x in rows]}, index=[x["metric"] for x in rows])
            if b:
                chart[f"LLM only ({b['model']})"] = [float(x["llm_only"]) * 100 for x in rows]
            try:
                st.bar_chart(chart, height=280, y_label="%", stack=False)
            except Exception:
                st.bar_chart(chart, height=280)
        if not b:
            st.info(f"The LLM-only comparison hasn't been run: {m.get('llm_only_baseline_skipped')}. "
                    "Set an API key and re-run `bash run_all.sh` to fill in this column.")
        st.markdown(f"- Fictional drug names correctly left unidentified: **{r['unmatched_correctly_flagged']}**\n"
                    f"- {r['rxnav_items']}\n"
                    f"- Beers flags: {r['beers_counts']['tp']} correct, {r['beers_counts']['fp']} wrong, "
                    f"{r['beers_counts']['fn']} missed")
        hp = ROOT / "results" / "holdout" / "metrics.json"
        if hp.exists():
            h = json.loads(hp.read_text())
            hr = h["medburden"]
            st.markdown("**Held-out check.** The local brand list was built to include the drugs above, so those numbers "
                        "are partly in-sample. We also tested 10 lists using brands we did **not** add:")
            wide(st.dataframe, pd.DataFrame([{"Set": f"Held-out ({h['setup']['rxnav']})",
                                        "Ingredient match": pct(hr["rxnav_match_rate"]),
                                        "ACB exact": pct(hr["acb_exact_match_rate"]),
                                        "Beers precision": pct(hr["beers_precision"]),
                                        "Beers recall": pct(hr["beers_recall"])}]), hide_index=True)
            st.caption("Unknown brands are shown as 'not identified' instead of being guessed, so misses lower recall but "
                       "never create wrong flags. With RxNav online, more of these brands are found.")
        st.markdown("**Caveats.** The same team wrote the tables and the answer key, so this tests whether the rules are "
                    "applied correctly. It is not an independent clinical validation, and 30 cases is a small test. "
                    "`eval/verify_10.md` lists 10 cases next to their source lines for a manual check.")
        with st.expander("Per-case details"):
            wide(st.dataframe, pd.DataFrame(m["per_case"]))
    disclaimer()

with tab_about:
    st.markdown("""
### The problem
Many older adults take medicines that make confusion, memory problems or falls more likely. Some are prescribed, and many
are bought over the counter: sleep aids like **Tylenol PM** or **Benadryl**, bladder pills, some antidepressants.
Caregivers often don't know which ones to ask about.

### How MedBurden works
1. **Read** the list you paste or photograph. An AI can help read it, but you check and fix the list before anything is scored.
2. **Identify** each medicine with the NIH **RxNav / RxNorm** service, plus a local list of common brands, splitting
   combination products into their ingredients. Names it can't identify are shown as *not identified* and never guessed.
   Spelling fixes are shown to you.
3. **Check** each ingredient against published tables using fixed rules. **No AI decides any flag.**
   - Anticholinergic Cognitive Burden (ACB) Scale, 2012 update (Aging Brain Care, Indiana University).
   - 2023 American Geriatrics Society Beers Criteria: Table 2 (avoid in older adults), Table 3 (dementia; falls),
     Table 5 (drug-drug combinations, all 12 rows), Table 7 (strong anticholinergics).
   - The same ingredient appearing in two products.
4. **Explain** the results in plain English and give you a printable list of questions for the doctor.

### Limitations
- The tables cover common medicines only. A drug that isn't listed is not proof that it's safe.
- Reading photos can fail. Always check the extracted list.
- US drug names only (RxNorm).
- The Beers Criteria have many exceptions (for example, the reason a medicine is prescribed). A flag means "worth asking
  about", not "wrong".
- **Not clinical advice.** Never stop or change a medicine without talking to a doctor or pharmacist.

### Sources
- Boustani M, Campbell N, et al. *Anticholinergic Cognitive Burden Scale, 2012 update.* Aging Brain Care.
- 2023 American Geriatrics Society Beers Criteria Update Expert Panel. *J Am Geriatr Soc.* 2023;71(7):2052-2081. doi:10.1111/jgs.18372
- WHO ATC/DDD Index, used for drug classes beyond the drugs printed in Beers.
- U.S. National Library of Medicine. RxNorm and RxNav APIs. Brand compositions: US product labeling (DailyMed).
""")
    disclaimer()
