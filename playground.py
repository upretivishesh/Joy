import streamlit as st
import pdfplumber
from docx import Document
import pandas as pd
import re

from parser import (
    extract_location,
    extract_jd_keywords,
    score_resume_against_jd,
)

# ---------- FILE READING ----------

def read_any_fp(uploaded_file):
    """Read text from PDF/DOCX/TXT-like uploads."""
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".pdf"):
        with pdfplumber.open(uploaded_file) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    elif name.endswith(".docx"):
        doc = Document(uploaded_file)
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        return uploaded_file.read().decode("utf-8", errors="ignore")


# ---------- MOBILE & EXPERIENCE HELPERS ----------

def extract_mobile(text: str) -> str:
    """
    Try multiple Indian-style phone patterns and prefer lines
    around 'Contact', 'Phone', 'Mobile' headings.
    """
    lines = text.splitlines()

    def _find_in_chunk(chunk: str) -> str:
        patterns = [
            r"(?:\+91[-\s]*)?\d{10}",
            r"(?:\+91[-\s]*)\d{3}[-\s]*\d{3}[-\s]*\d{4}",
        ]
        for pat in patterns:
            m = re.search(pat, chunk)
            if m:
                num = re.sub(r"\D", "", m.group(0))
                if len(num) > 10:
                    num = num[-10:]
                return num
        return ""

    # 1) Look near contact headings
    for i, line in enumerate(lines):
        if re.search(r"contact|phone|mobile", line, re.IGNORECASE):
            window = "\n".join(lines[max(0, i - 1): i + 3])
            num = _find_in_chunk(window)
            if num:
                return num

    # 2) Fallback: anywhere in the text
    num = _find_in_chunk(text)
    return num if num else "-"


def extract_experience_years(text: str, filename: str = "") -> str:
    """
    Rough total experience from:
    - phrases like '4.5 Years', '12 Years'
    - Naukri-style filename tags [8y_0m]
    """
    exp_vals = []

    # 1) From text phrases
    matches = re.findall(r"(\d+(?:\.\d+)?)\s+Years?", text, flags=re.IGNORECASE)
    for yrs in matches:
        try:
            val = float(yrs)
            if 0 < val < 50:
                exp_vals.append(val)
        except Exception:
            pass

    # 2) From filename tags like [8y_0m]
    if filename:
        m = re.search(r"\[(\d+)y[_\-](\d+)m\]", filename)
        if m:
            try:
                y = int(m.group(1))
                mth = int(m.group(2))
                val = y + mth / 12
                if 0 < val < 50:
                    exp_vals.append(val)
            except Exception:
                pass

    total = max(exp_vals) if exp_vals else 0.0
    return f"{total:.1f} Years" if total > 0 else "-"


def clean_location(loc: str) -> str:
    """Clean obviously wrong locations like 'LinkedIn'."""
    if not loc or loc == "-":
        return "-"
    bad = {"linkedin", "indeed", "naukri", "resume", "cv"}
    if loc.strip().lower() in bad:
        return "-"
    return loc.strip(" ,;.")


# ---------- STREAMLIT UI ----------

st.set_page_config(page_title="Joy - Seven Hiring", layout="wide")
st.title("Joy – Seven Hiring")

st.markdown(
    "Upload **one JD** and **multiple resumes**. Joy will show each resume file, "
    "current location, mobile number, total experience, JD match score, "
    "and extra keyword hits."
)

jd_file = st.file_uploader("Upload JD (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
resume_files = st.file_uploader(
    "Upload resumes (PDF or DOCX)", type=["pdf", "docx"], accept_multiple_files=True
)

extra_kw = st.text_input("Optional: extra keywords to search (comma‑separated)")


if st.button("Run NLP on resumes"):
    if not jd_file or not resume_files:
        st.error("Upload both a JD and at least one resume.")
    else:
        with st.spinner("Running NLP…"):
            jd_text = read_any_fp(jd_file)
            jd_keywords = extract_jd_keywords(jd_text)

            wanted = []
            if extra_kw.strip():
                wanted = [w.strip().lower() for w in extra_kw.split(",") if w.strip()]

            rows = []
            for uf in resume_files:
                text = read_any_fp(uf)
                resume_name = uf.name

                raw_loc = extract_location(text)
                loc = clean_location(raw_loc)

                mobile = extract_mobile(text)
                total_exp = extract_experience_years(text, filename=resume_name)

                score = score_resume_against_jd(text, jd_keywords)

                extra_hits = []
                if wanted:
                    low_text = text.lower()
                    for w in wanted:
                        if w in low_text:
                            extra_hits.append(w)

                rows.append(
                    {
                        "Resume file": resume_name,
                        "Current location": loc,
                        "Mobile Number": mobile,
                        "Total Experience": total_exp,
                        "JD match score": score,
                        "Extra keywords hit": ", ".join(extra_hits),
                    }
                )

        df = pd.DataFrame(rows)
        df = df.sort_values(by="JD match score", ascending=False).reset_index(drop=True)
        df.insert(0, "Sr No", range(1, len(df) + 1))

        st.success("Done.")
        st.dataframe(df, use_container_width=True, hide_index=True)
