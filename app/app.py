"""MedBurden: spot medicines that can cause confusion, falls or memory problems, and prepare doctor questions.

Run: streamlit run app/app.py
"""
from __future__ import annotations

import csv
import html
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

st.set_page_config(page_title="MedBurden: medicine check for caregivers", page_icon="💊", layout="centered")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Figtree:wght@400;500;600;700&display=swap');
:root {
  --ink:#12313A; --ink-2:#44606A; --ink-3:#6F858D; --paper:#F2F6F6; --card:#FFFFFF; --line:#DCE5E7;
  --teal:#0E6B7D; --teal-dark:#0A5463; --teal-tint:#E3F2F4;
  --green:#23805A; --green-tint:#E5F4EC; --amber:#B7740F; --amber-tint:#FBF0D9; --red:#B93B27; --red-tint:#FBE9E5;
}
html, body, .stApp, [data-testid="stAppViewContainer"] {background:var(--paper); color:var(--ink);
  font-family:'Figtree', system-ui, sans-serif; font-size:17px;}
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {display:none !important;}
.block-container {max-width:760px; padding:0 1.1rem 4rem 1.1rem !important;}
h1, h2, h3, .mb-display {font-family:'Bricolage Grotesque', 'Figtree', sans-serif !important; color:var(--ink); letter-spacing:-0.02em;}
p, li, label, .stMarkdown {line-height:1.55;}

/* top notice */
.mb-notice {background:var(--ink); color:#E8F1F3; font-size:0.86rem; padding:9px 14px; text-align:center; margin:0 -1.1rem 0 -1.1rem;}
.mb-notice b {color:#fff;}

/* hero */
.mb-hero {padding:34px 0 8px 0;}
.mb-brand {display:flex; align-items:center; gap:10px; font-family:'Bricolage Grotesque',sans-serif; font-weight:700; font-size:1.05rem; color:var(--teal);}
.mb-caps {display:inline-block; width:34px; height:16px; border-radius:9px; background:linear-gradient(90deg,var(--teal) 50%,#F3B440 50%); transform:rotate(-24deg);}
.mb-hero h1 {font-size:2.55rem; line-height:1.07; margin:14px 0 12px 0; font-weight:700;}
.mb-hero p {font-size:1.12rem; color:var(--ink-2); max-width:34em; margin:0;}
.mb-steps {display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:22px 0 6px 0;}
.mb-step {background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 14px; font-size:0.95rem; color:var(--ink-2);}
.mb-step b {display:block; color:var(--ink); font-size:1rem; margin-bottom:2px;}
.mb-step i {font-style:normal; display:inline-flex; width:22px; height:22px; border-radius:50%; background:var(--teal); color:#fff;
  font-size:0.8rem; font-weight:700; align-items:center; justify-content:center; margin-right:7px;}

/* section headings */
.mb-h {display:flex; align-items:center; gap:10px; margin:30px 0 6px 0;}
.mb-h .n {width:30px; height:30px; border-radius:50%; background:var(--teal); color:#fff; display:flex; align-items:center; justify-content:center;
  font-weight:700; font-size:0.95rem; flex:none;}
.mb-h h2 {font-size:1.5rem; margin:0; padding:0; font-weight:700;}
.mb-help {color:var(--ink-2); font-size:0.98rem; margin:0 0 12px 0;}

/* tabs */
[data-testid="stTabs"] [role="tablist"] {gap:4px; border-bottom:1px solid var(--line); margin-top:18px;}
[data-testid="stTabs"] button[role="tab"] {font-family:'Figtree',sans-serif; font-weight:600; font-size:1rem; padding:10px 16px; margin-right:6px; color:var(--ink-2); flex:none;}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {color:var(--teal);}

/* inputs */
label, [data-testid="stWidgetLabel"] p {font-weight:600 !important; color:var(--ink) !important; font-size:0.98rem !important;}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {background:var(--card) !important; border-radius:12px !important; border:1.5px solid var(--line) !important;}
[data-baseweb="textarea"] textarea, [data-baseweb="input"] input {font-size:1.05rem !important; font-family:'Figtree',sans-serif !important;}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {border-color:var(--teal) !important; box-shadow:0 0 0 3px var(--teal-tint) !important;}
[data-testid="stFileUploaderDropzone"] {background:var(--card); border:2px dashed #A9C3C9; border-radius:14px; padding:22px;}
[data-testid="stRadio"] [role="radiogroup"] {gap:8px;}

/* buttons */
.stButton > button, .stDownloadButton > button {border-radius:12px; font-family:'Figtree',sans-serif; font-weight:700; font-size:1.02rem;
  padding:0.62rem 1.1rem; border:1.5px solid var(--line); background:var(--card); color:var(--ink); transition:transform .08s, box-shadow .15s, background .15s;}
.stButton > button:hover, .stDownloadButton > button:hover {border-color:var(--teal); color:var(--teal); box-shadow:0 2px 10px rgba(14,107,125,.12);}
.stButton > button:active {transform:translateY(1px);}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {background:var(--teal); color:#fff; border-color:var(--teal); min-height:3.1rem; font-size:1.1rem;}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {background:var(--teal-dark); color:#fff; border-color:var(--teal-dark);}
button:focus-visible, [role="tab"]:focus-visible, input:focus-visible, textarea:focus-visible {outline:3px solid #F3B440 !important; outline-offset:2px;}

/* cards */
.mb-card {background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px 18px; margin:10px 0; line-height:1.5;}
.mb-card .t {font-weight:700; font-size:1.05rem; margin-bottom:3px;}
.mb-src {color:var(--ink-3); font-size:0.82rem; margin-top:6px;}
.mb-bar {border-left:6px solid var(--red);} .mb-bar.amber {border-left-color:var(--amber);} .mb-bar.blue {border-left-color:var(--teal);} .mb-bar.violet {border-left-color:#6B5BA8;}
.mb-empty {background:var(--teal-tint); border:1px dashed #9CC8D0; border-radius:16px; padding:18px; color:var(--ink-2); margin-top:18px;}

/* result label: the signature */
.mb-label {background:var(--card); border:1.5px solid var(--ink); border-radius:18px; margin:16px 0 8px 0; overflow:hidden; box-shadow:5px 5px 0 var(--ink);}
.mb-label-top {display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:10px 18px; background:var(--ink); color:#DDEBEE; font-size:0.85rem; letter-spacing:.04em; text-transform:uppercase; font-weight:600;}
.mb-label-body {padding:18px 18px 16px 18px;}
.mb-headline {font-family:'Bricolage Grotesque',sans-serif; font-size:1.75rem; line-height:1.15; font-weight:700; margin:0 0 6px 0;}
.mb-sub {color:var(--ink-2); margin:0 0 16px 0;}
.mb-scoreline {display:flex; align-items:baseline; gap:10px; margin-bottom:8px;}
.mb-score {font-family:'Bricolage Grotesque',sans-serif; font-size:3rem; font-weight:700; line-height:1;}
.mb-level {font-weight:700; font-size:1.1rem;}
.mb-scorelabel {color:var(--ink-2); font-size:0.92rem; margin-left:auto; text-align:right;}
.mb-caps-bar {display:grid; grid-template-columns:1fr 2fr 3fr; gap:4px; height:22px; position:relative;}
.mb-caps-bar span {display:block; background:#DCE5E7; height:100%;}
.mb-caps-bar span:nth-child(1) {border-radius:11px 0 0 11px;} .mb-caps-bar span:nth-child(3) {border-radius:0 11px 11px 0;}
.mb-caps-bar.low span:nth-child(1) {background:var(--green);} .mb-caps-bar.moderate span:nth-child(-n+2) {background:#E3A22B;} .mb-caps-bar.high span {background:var(--red);}
.mb-caps-bar.moderate span:nth-child(1) {background:#E3A22B;}
.mb-pin {position:absolute; top:-6px; width:6px; height:34px; background:var(--ink); border:2px solid #fff; border-radius:4px; transform:translateX(-3px);}
.mb-scale {display:grid; grid-template-columns:1fr 2fr 3fr; gap:4px; font-size:0.78rem; color:var(--ink-3); margin-top:5px;}

/* medicine list at a glance */
.mb-med {display:flex; align-items:center; justify-content:space-between; gap:10px; padding:11px 2px; border-bottom:1px solid var(--line);}
.mb-med:last-child {border-bottom:0;}
.mb-med b {display:block;} .mb-med small {color:var(--ink-3); font-size:0.85rem;}
.mb-pill {border-radius:999px; padding:4px 12px; font-size:0.84rem; font-weight:700; white-space:nowrap;}
.mb-pill.red {background:var(--red-tint); color:var(--red);} .mb-pill.amber {background:var(--amber-tint); color:var(--amber);}
.mb-pill.green {background:var(--green-tint); color:var(--green);} .mb-pill.grey {background:#E8EEEF; color:var(--ink-2);}

/* questions */
.mb-q {background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px 14px 52px; margin:9px 0; position:relative; line-height:1.5;}
.mb-q::before {content:"?"; position:absolute; left:14px; top:13px; width:26px; height:26px; border-radius:50%; background:var(--teal-tint); color:var(--teal);
  font-family:'Bricolage Grotesque',sans-serif; font-weight:700; display:flex; align-items:center; justify-content:center;}

.mb-disclaimer {background:var(--amber-tint); border:1.5px solid #E7C27A; color:#5C4100; border-radius:14px; padding:12px 16px; font-size:0.95rem; margin:22px 0 6px 0;}

[data-testid="stExpander"] {border:1px solid var(--line) !important; border-radius:14px !important; background:var(--card);}
[data-testid="stExpander"] summary {font-weight:600;}

@media (max-width:640px) {
  html, body, .stApp {font-size:16.5px;}
  .mb-hero {padding-top:24px;} .mb-hero h1 {font-size:2rem;}
  .mb-steps {grid-template-columns:1fr;}
  .mb-headline {font-size:1.45rem;} .mb-score {font-size:2.5rem;}
  .mb-label {box-shadow:3px 3px 0 var(--ink);}
  .mb-scorelabel {display:none;}
}
@media (prefers-reduced-motion: reduce) {* {transition:none !important; animation:none !important;}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def wide(fn, *args, **kwargs):
    """Full-width element on both new Streamlit (width="stretch") and older versions (use_container_width)."""
    try:
        return fn(*args, width="stretch", **kwargs)
    except Exception as e:
        if "width" not in str(e) and not isinstance(e, TypeError):
            raise
        return fn(*args, use_container_width=True, **kwargs)


def disclaimer():
    st.markdown(f"<div class='mb-disclaimer'><b>Please read.</b> {esc(DISCLAIMER)}</div>", unsafe_allow_html=True)


def section(n: int, title: str, help_text: str = ""):
    st.markdown(f"<div class='mb-h'><span class='n'>{n}</span><h2>{esc(title)}</h2></div>"
                + (f"<p class='mb-help'>{help_text}</p>" if help_text else ""), unsafe_allow_html=True)


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


def _pdf(rep, items, who):
    try:
        return note_pdf(rep, items, who)
    except Exception:
        return None


# ------------------------------------------------------------------ results
LEVEL_TEXT = {
    "low": ("Low", "var(--green)", "The medicines we could identify add up to a low score."),
    "moderate": ("Moderate", "var(--amber)", "Worth mentioning to the doctor."),
    "high": ("High", "var(--red)", "These medicines add up. Worth raising with the doctor."),
}


def label_card(rep, items, who):
    n_items = len(items)
    n_bad = len(rep["needs_review"]) + len(rep["unmatched"])
    identified = n_items - n_bad
    n_q = len(questions(rep, items, who)) - n_bad     # questions about risks, not about unidentified names
    n_q = max(n_q, 0)
    if identified == 0:
        head, sub = "We couldn't identify any of these medicines", "Check the spelling in the list above, or ask a pharmacist what each one contains."
    elif n_q:
        head = f"{n_q} thing{'s' if n_q != 1 else ''} to ask the doctor about"
        sub = "Not a reason to stop anything. Bring these questions to the next appointment."
    else:
        head, sub = "Nothing to flag in the medicines we could identify", "That is not a guarantee. Our lists do not cover every medicine."
    level, color, level_sub = LEVEL_TEXT[rep["acb_level"]]
    total = rep["acb_total"]
    pos = min(total, 6) / 6 * 100
    inc = " Some medicines could not be identified, so the real score may be higher." if rep["acb_incomplete"] else ""
    st.markdown(f"""
<div class='mb-label'>
  <div class='mb-label-top'><span>Results for {esc(who or 'your relative')}</span><span>{identified} of {n_items} medicines checked</span></div>
  <div class='mb-label-body'>
    <p class='mb-headline'>{esc(head)}</p>
    <p class='mb-sub'>{esc(sub)}</p>
    <div class='mb-scoreline'><span class='mb-score' style='color:{color}'>{total}</span><span class='mb-level' style='color:{color}'>{level}</span>
      <span class='mb-scorelabel'>Memory-effect score<br>(ACB scale, 2012)</span></div>
    <div class='mb-caps-bar {rep["acb_level"]}'><span></span><span></span><span></span><div class='mb-pin' style='left:{pos}%'></div></div>
    <div class='mb-scale'><span>0 Low</span><span>1 to 2 Moderate</span><span>3 or more High</span></div>
    <p class='mb-src'>{esc(level_sub)}{esc(inc)} Some medicines block a brain chemical called acetylcholine, and each one adds to the score.
    A total of 3 or more is a threshold many researchers use.</p>
  </div>
</div>""", unsafe_allow_html=True)


def glance(rep):
    pills = {"red": "Ask the doctor", "amber": "Mild effect", "green": "No flag", "grey": "Not identified"}
    rows = []
    for r in rep["rows"]:
        if r["status"] != "matched":
            kind = "grey"
        elif r["beers"] or (r["acb"] or 0) >= 3:
            kind = "red"
        elif (r["acb"] or 0) >= 1:
            kind = "amber"
        else:
            kind = "green"
        sub = r["ingredient"] if r["ingredient"] not in ("—", "") and r["ingredient"].lower() != r["drug"].lower() else ""
        sub = f"contains {sub}" if sub else (r.get("strength") or "")
        rows.append(f"<div class='mb-med'><div><b>{esc(r['drug'])}</b><small>{esc(sub)}</small></div>"
                    f"<span class='mb-pill {kind}'>{pills[kind]}</span></div>")
    st.markdown("<div class='mb-card' style='padding:6px 18px'>" + "".join(rows) + "</div>", unsafe_allow_html=True)


def render_results(items, norms, rep, who, key, show_label=True):
    if show_label:
        label_card(rep, items, who)
    if rep["age_note"]:
        st.info(rep["age_note"])

    st.markdown("<h3 style='margin:26px 0 4px 0'>Questions to ask the doctor</h3>"
                "<p class='mb-help'>Print these or save them on your phone. They are questions, not instructions.</p>",
                unsafe_allow_html=True)
    qs = questions(rep, items, who)
    if qs:
        st.markdown("".join(f"<div class='mb-q'>{esc(q)}</div>" for q in qs), unsafe_allow_html=True)
    else:
        st.markdown("<div class='mb-card'>No questions came up. You can still bring the full medicine list to the next appointment.</div>",
                    unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    pdf = _pdf(rep, items, who)
    if pdf:
        wide(c1.download_button, "Download as PDF", pdf, "questions_for_doctor.pdf", mime="application/pdf",
             key=f"{key}_pdf", type="primary")
    else:
        c1.caption("PDF is not available here. Use the text version.")
    wide(c2.download_button, "Download as text", note_text(rep, items, who), "questions_for_doctor.txt", key=f"{key}_txt")

    if rep["needs_review"] or rep["unmatched"]:
        names = ", ".join(f"\"{esc(u['drug'])}\"" for u in rep["needs_review"] + rep["unmatched"])
        st.markdown(f"<div class='mb-card mb-bar amber'><div class='t'>We could not check {names}</div>"
                    "Fix the spelling in the list above, tick the suggestion if you are sure it is right, "
                    "or ask the pharmacist what the medicine contains. Medicines we could not identify are not scored.</div>",
                    unsafe_allow_html=True)

    st.markdown("<h3 style='margin:26px 0 4px 0'>Your list at a glance</h3>", unsafe_allow_html=True)
    glance(rep)

    flags = rep["flags"]
    style = {"beers": "", "duplicate": "amber", "sedation_stack": "violet", "interaction": "blue"}
    with st.expander(f"Why each medicine was flagged ({len(flags)})", expanded=False):
        if not flags:
            st.write("Nothing was flagged.")
        for f in flags:
            title = {"beers": f"{f['drug']} ({f['ingredient']}): {f.get('applies_to', '')}",
                     "duplicate": f"Same ingredient twice: {f['ingredient']}",
                     "sedation_stack": f"Several sedating medicines together: {f['ingredient']}",
                     "interaction": f"Combination to review: {f['drug']}"}.get(f["type"], f["type"])
            extra = f"<br><i>{esc(f['conditions'])}</i>" if f.get("conditions") else ""
            st.markdown(f"<div class='mb-card mb-bar {style.get(f['type'], '')}'><div class='t'>{esc(title)}</div>{esc(f['reason'])}{extra}"
                        f"<div class='mb-src'>Source: {esc(f['source'])}</div></div>", unsafe_allow_html=True)

    if cached_llm_status()["ok"] and flags:
        if st.button("Write a short plain-English summary", key=f"{key}_sum"):
            with st.spinner("Writing..."):
                s = llm_summary(rep)
            if s:
                st.markdown(f"<div class='mb-card'>{esc(s)}<div class='mb-src'>Written by AI from the flags above only. "
                            "The flags themselves come from the cited tables.</div></div>", unsafe_allow_html=True)
            else:
                st.caption("A summary is not available right now. The questions above are the full result.")

    with st.expander("How each medicine was identified"):
        badge = {"matched": "Identified", "needs_review": "Please confirm", "unmatched": "Not identified"}
        wide(st.dataframe, pd.DataFrame([{
            "Written as": it.name, "Status": badge[nr.status], "Ingredient(s)": ", ".join(i["name"] for i in nr.ingredients),
            "How": nr.method, "Note": nr.note} for it, nr in zip(items, norms)]), hide_index=True)
    with st.expander("Full details for each ingredient"):
        wide(st.dataframe, pd.DataFrame([{
            "Medicine": r["drug"], "Ingredient": r["ingredient"], "ACB score": "-" if r["acb"] is None else str(r["acb"]),
            "Beers Criteria": "; ".join(f"{b['recommendation']} ({b['applies_to']})" for b in r["beers"]) or "-",
            "Reason": r["reason"] or "-", "Source": r["source"]} for r in rep["rows"]]), hide_index=True)


# ------------------------------------------------------------------ page
st.markdown(f"<div class='mb-notice'><b>Prototype, not medical advice.</b> "
            "Always talk to a doctor or pharmacist before changing any medication.</div>", unsafe_allow_html=True)
st.markdown("""
<div class='mb-hero'>
  <div class='mb-brand'><span class='mb-caps'></span>MedBurden</div>
  <h1>Check a medicine list for memory and fall risks</h1>
  <p>Some common medicines, like sleep aids and bladder pills, can worsen confusion and memory problems in older adults.
  Add the list of medicines and get plain-English questions to ask their doctor. No medical knowledge needed.</p>
  <div class='mb-steps'>
    <div class='mb-step'><b><i>1</i>Add the list</b>Type it or take a photo</div>
    <div class='mb-step'><b><i>2</i>Check it</b>We look each medicine up</div>
    <div class='mb-step'><b><i>3</i>Ask the doctor</b>Take the questions with you</div>
  </div>
</div>""", unsafe_allow_html=True)

DEMOS = json.loads((ROOT / "data" / "demo_cases.json").read_text())["cases"]
PHOTOS = sorted((ROOT / "demo").glob("*.png"))

for k, v in {"who": "", "age": 80, "dementia": True, "falls": False, "text": "", "ver": 0}.items():
    st.session_state.setdefault(k, v)


def load_example(i: int):
    d = DEMOS[i]
    st.session_state.update(text=d["text"], who=d["who"], age=int(d["patient"]["age"]),
                            dementia=bool(d["patient"]["dementia"]), falls=bool(d["patient"]["falls"]))
    for k in ("items_df", "extract_info"):
        st.session_state.pop(k, None)


tab_check, tab_acc, tab_about = st.tabs(["Check medicines", "How accurate is it?", "About"])

with tab_check:
    section(1, "Tell us about the person", "This changes which warnings apply. It is only used on this page and is not saved.")
    c1, c2 = st.columns([3, 1])
    who = c1.text_input("First name or how you refer to them", key="who", placeholder="For example: Mom")
    age = c2.number_input("Age", min_value=0, max_value=120, key="age")
    c3, c4 = st.columns(2)
    dementia = c3.checkbox("Has dementia or memory problems", key="dementia")
    falls = c4.checkbox("Has fallen in the past year", key="falls")
    patient = {"age": int(age), "dementia": dementia, "falls": falls}

    section(2, "Add the medicines", "Type or paste one medicine per line, or upload a photo of a medicine list or pill bottle.")
    mode = st.radio("How do you want to add them?", ["Type or paste", "Upload a photo"], horizontal=True, label_visibility="collapsed")
    text, img = None, None
    if mode == "Type or paste":
        text = st.text_area("Medicines, one per line", key="text", height=150,
                            placeholder="Tylenol PM at bedtime\nOxybutynin 5 mg once a day\nDonepezil 10 mg\nLisinopril 10 mg")
    else:
        up = st.file_uploader("Photo of a medicine list or pill bottle label", type=["png", "jpg", "jpeg", "webp"])
        img = up.getvalue() if up else None
        if not img and PHOTOS:
            pick = st.selectbox("No photo handy? Try a sample photo", ["None"] + [p.stem.replace("_", " ") for p in PHOTOS])
            if pick != "None":
                img = PHOTOS[[p.stem.replace("_", " ") for p in PHOTOS].index(pick)].read_bytes()
        if img:
            st.image(img, width=300)
        ls, os_ = cached_llm_status(), ocr_status()
        if not ls["ok"] and not os_["ok"]:
            st.warning("Photos can't be read on this computer right now. Please type the medicines instead.")
        elif not ls["ok"]:
            st.caption("Photos are read with basic text recognition here. Clear, well-lit, straight-on photos work best.")
        st.caption("Tip: take the photo in good light, with the label flat and every line in view.")

    go = st.button("Check these medicines", type="primary", disabled=not (text or img), use_container_width=True)
    if not (text or img):
        st.markdown("<div class='mb-empty'><b>Not sure what to enter?</b> Try an example. It fills in a made-up person and medicine list.</div>",
                    unsafe_allow_html=True)
        ex_cols = st.columns(2)
        for i, d in enumerate(DEMOS):
            short = d["title"].replace("Featured story: ", "")
            ex_cols[i % 2].button(short, key=f"ex_{i}", on_click=load_example, args=(i,))

    if go:
        with st.spinner("Reading the list..."):
            got, method, warns = extract(text=text, image_bytes=img)
        if not got:
            warns = list(warns) + ["No medicines could be read from this input. For a photo, try a sharper, well-lit, "
                                   "straight-on picture, or type the medicines in the box above."]
        st.session_state["ver"] += 1
        st.session_state["items_df"] = pd.DataFrame([i.to_dict() for i in got] or
                                                    [{"name": "", "strength": "", "dose": "", "frequency": "", "confidence": 0.0}])
        st.session_state["extract_info"] = (method, warns)

    if "items_df" in st.session_state:
        method, warns = st.session_state["extract_info"]
        section(3, "Check the list", "We read your input into the list below. Fix any mistakes. Tap a cell to edit, "
                "or use the empty row at the bottom to add a medicine. The results update as you edit.")
        for w in warns:
            st.warning(w)
        edited = wide(st.data_editor, st.session_state["items_df"][["name", "strength", "dose", "frequency"]],
                      num_rows="dynamic", key=f"editor_{st.session_state['ver']}",
                      column_config={"name": "Medicine", "strength": "Strength", "dose": "Dose", "frequency": "How often"})
        items = [MedItem(name=str(r["name"]).strip(), strength=str(r.get("strength") or ""), dose=str(r.get("dose") or ""),
                         frequency=str(r.get("frequency") or ""), confidence=1.0)
                 for _, r in edited.iterrows() if str(r.get("name") or "").strip() and str(r["name"]) not in ("nan", "None")]
        if not items:
            st.info("The list is empty. Add at least one medicine in the table to see results.")
        else:
            norms, _ = run_pipeline(items, patient)
            review = [i for i, n in enumerate(norms) if n.status == "needs_review" and n.ingredients]
            accepted = []
            if review:
                st.markdown("**We think we know these, but please confirm.** Only tick if you are sure:")
                for i in review:
                    if st.checkbox(f"\"{items[i].name}\" is {norms[i].matched_name} "
                                   f"({', '.join(x['name'] for x in norms[i].ingredients)})", key=f"acc_{st.session_state['ver']}_{i}"):
                        accepted.append(i)
            norms2, rep = run_pipeline(items, patient, accepted)
            section(4, "Your results")
            render_results(items, norms2, rep, who, "check")
    disclaimer()

with tab_acc:
    st.markdown("### How accurate is it?")
    st.write("We tested MedBurden on made-up medicine lists with answers written by hand. "
             "We also compared it with a general AI model given the same lists and no reference tables.")
    p = ROOT / "results" / "metrics.json"
    hp = ROOT / "results" / "holdout" / "metrics.json"

    def pct(x):
        return "n/a" if x is None or x == "" or x != x else f"{100 * float(x):.0f}%"

    if hp.exists():
        h = json.loads(hp.read_text())
        hr, hb, hs = h["medburden"], h.get("llm_only_baseline"), h["setup"]
        st.markdown(f"#### Fair test: {hs['cases']} new lists the tool was not built around")
        rows = [("Medicines recognised", hr["rxnav_match_rate"], hb and hb["ingredient_match_rate"]),
                ("Memory-effect score exactly right", hr["acb_exact_match_rate"], hb and hb["acb_exact_match_rate"]),
                ("Flags that were real (precision)", hr["beers_precision"], hb and hb["beers_precision"]),
                ("Real flags found (recall)", hr["beers_recall"], hb and hb["beers_recall"])]
        wide(st.dataframe, pd.DataFrame([{"What we measured": a, "MedBurden": pct(b),
                                          "AI model alone": pct(c) if c is not None else "not run"} for a, b, c in rows]), hide_index=True)
        st.caption("The AI model alone recognises more unusual brand names. MedBurden is more exact on the score and made no "
                   "wrong flags, but it misses medicines it will not guess at. The AI column changes from run to run.")
    if p.exists():
        m = json.loads(p.read_text())
        s, r, b = m["setup"], m["medburden"], m["llm_only_baseline"]
        st.markdown(f"#### Main test: {s['cases']} lists ({s['image_cases']} as photos)")
        st.caption("The tool was built around these lists, so treat this as a basic check, not a fair test.")
        cp = ROOT / "results" / "comparison.csv"
        if cp.exists():
            rows = list(csv.DictReader(open(cp)))
            wide(st.dataframe, pd.DataFrame([{"Metric": x["metric"], "MedBurden": pct(x["medburden"]),
                                              "AI model alone": pct(x["llm_only"]) if x["llm_only"] else "not run"} for x in rows]),
                 hide_index=True)
        if not b:
            st.info("The comparison with an AI model alone has not been run.")
        with st.expander("Per-list details"):
            wide(st.dataframe, pd.DataFrame(m["per_case"]))
    st.markdown("**Limits.** The same team wrote the reference tables and the answer key. 30 to 31 lists is a small test. "
                "This has not been tested on real patients or with doctors.")
    disclaimer()

with tab_about:
    st.markdown("""
### What this does
Many older adults take medicines that make confusion, memory problems or falls more likely. Some are prescribed, and many
are bought over the counter, like **Tylenol PM** or **Benadryl**, bladder pills and some antidepressants.
Family caregivers often do not know which ones to ask about. MedBurden turns published tables into a short list of
questions to take to the doctor.

### How it works
1. **Read.** You type or photograph the list. An AI can help read a photo. You check and fix the list before anything is scored.
2. **Identify.** Each medicine is looked up in the NIH **RxNav / RxNorm** service and a local list of brands. Combination
   products are split into their ingredients. Names it cannot identify are shown as not identified and never guessed.
3. **Check.** Each ingredient is checked against published tables using fixed rules. **No AI decides any flag.**
   - Anticholinergic Cognitive Burden (ACB) Scale, 2012 update (Aging Brain Care, Indiana University).
   - 2023 American Geriatrics Society Beers Criteria, Tables 2, 3, 5 and 7.
   - The same ingredient appearing in two products.
4. **Explain.** The results become plain-English questions you can print or save.

### Limits
- The tables cover common medicines only. A medicine that is not listed is not proof that it is safe.
- Reading photos can fail. Always check the list.
- US drug names only.
- The Beers Criteria have exceptions, such as the reason a medicine is prescribed. A flag means worth asking about, not wrong.
- **This is a prototype and not medical advice.** Always talk to a doctor or pharmacist before changing any medication.

### Sources
- Boustani M, Campbell N, et al. *Anticholinergic Cognitive Burden Scale, 2012 update.* Aging Brain Care.
- 2023 American Geriatrics Society Beers Criteria Update Expert Panel. *J Am Geriatr Soc.* 2023;71(7):2052-2081. doi:10.1111/jgs.18372
- WHO ATC/DDD Index, used for drug classes.
- U.S. National Library of Medicine. RxNorm and RxNav APIs. Brand compositions: US product labeling (DailyMed).
""")
    with st.expander("Technical status (AI reader, photo reading, drug lookup)"):
        ls, os_ = cached_llm_status(), ocr_status()
        (st.success if ls["ok"] else st.info)(f"AI reader: {ls['message']}")
        (st.success if os_["ok"] else st.warning)(f"Offline photo reading: {os_['message']}")
        rx = rx_client().reachable
        st.write("Drug lookup (NIH RxNav): " + ("reachable" if rx else "not reached yet" if rx is None else
                                                 "not reachable. Using the saved cache and the local drug list."))
    disclaimer()
