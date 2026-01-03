import streamlit as st
import pdfplumber
from docx import Document
import pandas as pd
import re
import warnings
from collections import Counter
import base64

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

warnings.filterwarnings("ignore")

from parser import (
    extract_jd_keywords,
    score_resume_against_jd,
    get_role_from_jd,
    get_industry_from_jd,
    check_role_match,
    check_industry_match,
    calculate_weighted_score,
)

# ---------- PAGE CONFIG ----------

st.set_page_config(page_title="Joy - Seven Hiring", layout="wide")

# ---------- USER DATABASE ----------

USERS = {
    "gaurika": {"password": "Gaurika@$7", "name": "Gaurika"},
    "vishesh": {"password": "Qwerty@0987", "name": "Vishesh"},
}

# ---------- LOGIN SYSTEM ----------

def check_login(username, password):
    if username in USERS and USERS[username]["password"] == password:
        return True, USERS[username]["name"]
    return False, None

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""

if not st.session_state.logged_in:
    st.markdown("""
    <style>
    .login-title {
        text-align: center;
        font-size: 3em;
        font-weight: bold;
        margin-top: 40px;
        margin-bottom: 60px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-title">Joy – Resume Screening Tool</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Please log in to continue")
        username = st.text_input("Username", key="username_input")
        password = st.text_input("Password", type="password", key="password_input")

        if st.button("Login", type="primary", use_container_width=True):
            ok, name = check_login(username.lower(), password)
            if ok:
                st.session_state.logged_in = True
                st.session_state.user_name = name
                st.rerun()
            else:
                st.error("Invalid username or password")
    st.stop()

# ---------- MAIN HEADER & LOGOUT ----------

with st.sidebar:
    st.markdown("### User Session")
    st.write(f"**Logged in as:** {st.session_state.user_name}")
    if st.button("🚪 Logout", type="secondary", use_container_width=True, key="logout_sidebar"):
        st.session_state.logged_in = False
        st.session_state.user_name = ""
        st.rerun()

st.title(f"Hi {st.session_state.user_name}!")
st.markdown("### Here to help you with the screening process")
st.markdown("---")
st.markdown(
    "Upload **one JD** (or paste text) and **multiple resumes**. "
    "Joy uses role, industry and semantic similarity to rank candidates."
)

# ---------- HELPERS ----------

def read_any_fp(uploaded_file):
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

def extract_name(text: str, filename: str) -> str:
    lines = text.split("\n")
    for line in lines[:5]:
        line = line.strip()
        if not line or len(line) < 3 or len(line) > 50:
            continue
        if re.search(r"resume|cv|curriculum|profile|email|phone|address", line, re.IGNORECASE):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.replace(".", "").isalpha() for w in words):
            return line.title()
    name_from_file = re.sub(r"[-_\[\]\d]", " ", filename.replace(".pdf", "").replace(".docx", ""))
    name_from_file = re.sub(r"\s+", " ", name_from_file).strip()
    if name_from_file and len(name_from_file) > 3:
        return name_from_file.title()
    return "-"

def extract_email(text: str) -> str:
    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    m = re.findall(pattern, text)
    return m[0].lower() if m else "-"

def extract_mobile(text: str) -> str:
    lines = text.splitlines()

    def _find(chunk: str) -> str:
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
                if len(num) == 10:
                    return num
        return ""

    for i, line in enumerate(lines):
        if re.search(r"contact|phone|mobile", line, re.IGNORECASE):
            window = "\n".join(lines[max(0, i - 1): i + 3])
            num = _find(window)
            if num:
                return num
    num = _find(text)
    return num if num else "-"

def extract_experience_years(text: str, filename: str = "") -> str:
    vals = []
    matches = re.findall(r"(\d+(?:\.\d+)?)\s+Years?", text, flags=re.IGNORECASE)
    for yrs in matches:
        try:
            v = float(yrs)
            if 0 < v < 50:
                vals.append(v)
        except:
            pass

    if filename:
        m = re.search(r"\[(\d+)y[_\-](\d+)m\]", filename)
        if m:
            try:
                y = int(m.group(1))
                mth = int(m.group(2))
                v = y + mth / 12
                if 0 < v < 50:
                    vals.append(v)
            except:
                pass

    total = max(vals) if vals else 0.0
    return f"{total:.1f} Years" if total > 0 else "-"

def extract_education(text: str) -> str:
    tl = text.lower()
    degrees = {
        "PhD": r"ph\.?d|doctor of philosophy",
        "Master's": r"master|m\.?tech|m\.?sc|mba|m\.?e|m\.?s\b",
        "Bachelor's": r"bachelor|b\.?tech|b\.?sc|b\.?e|b\.?a\b|bca",
        "Diploma": r"diploma|polytechnic",
    }
    for degree, pat in degrees.items():
        if re.search(pat, tl):
            return degree
    return "-"

def extract_notice_period(text: str) -> str:
    tl = text.lower()
    if re.search(r"immediate|immediately|can join immediately", tl):
        return "Immediate"
    m = re.search(r"(\d+)\s*(?:days?|weeks?|months?)\s*(?:notice|np)", tl)
    if m:
        num = int(m.group(1))
        unit = m.group(0).lower()
        if "week" in unit:
            return f"{num} weeks"
        if "month" in unit:
            return f"{num} months"
        return f"{num} days"
    if re.search(r"15\s*days|2\s*weeks", tl):
        return "15 days"
    if re.search(r"30\s*days|1\s*month", tl):
        return "30 days"
    if re.search(r"60\s*days|2\s*months", tl):
        return "60 days"
    if re.search(r"90\s*days|3\s*months", tl):
        return "90 days"
    return "-"

def extract_current_company(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"current|present|working at", line, re.IGNORECASE):
            for j in range(i, min(i + 3, len(lines))):
                m = re.search(r"(?:at|with)\s+([A-Z][A-Za-z0-9\s&,\.]+)", lines[j])
                if m:
                    return m.group(1).strip()[:50]
    return "-"

def detect_gaps(text: str) -> str:
    years = re.findall(r"\b(19|20)\d{2}\b", text)
    if len(years) < 2:
        return "Unable to detect"
    years = sorted([int(y) for y in years])
    gaps = []
    for i in range(len(years) - 1):
        diff = years[i+1] - years[i]
        if diff > 2:
            gaps.append(f"{diff}yr gap")
    return ", ".join(gaps) if gaps else "No major gaps"

def extract_top_skills(text: str, top_n: int = 5) -> str:
    pattern = r"\b(python|java|javascript|react|node|aws|azure|gcp|sql|docker|kubernetes|" \
              r"salesforce|sap|excel|powerbi|tableau|agile|scrum|leadership|management|" \
              r"marketing|sales|finance|hr|operations|analytics|machine learning|ai|" \
              r"data science|blockchain|devops|testing|qa|automation)\b"
    tl = text.lower()
    matches = re.findall(pattern, tl)
    if not matches:
        return "-"
    freq = Counter(matches)
    return ", ".join(s.title() for s, _ in freq.most_common(top_n))

def detect_red_flags(text: str, experience_str: str) -> str:
    flags = []
    if len(text) < 500:
        flags.append("Very short resume")
    company_mentions = len(re.findall(r"(?:pvt|ltd|inc|corp|limited)", text, re.IGNORECASE))
    if company_mentions > 6:
        flags.append("Frequent job changes")
    common_errors = ["experiance", "managment", "experties", "responsibilites"]
    if any(err in text.lower() for err in common_errors):
        flags.append("Spelling errors")
    if "@" not in text:
        flags.append("No email")
    if not re.search(r"\d{10}", text):
        flags.append("No phone")
    return ", ".join(flags) if flags else "None"

# ---------- SEMANTIC SIMILARITY ----------

def jd_resume_similarity(jd_text: str, resume_text: str) -> float:
    docs = [jd_text.lower(), resume_text.lower()]
    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=5000,
        ngram_range=(1, 2)
    )
    tfidf = vectorizer.fit_transform(docs)
    sim = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
    return round(sim * 100, 1)

# ---------- MAIN UI ----------

st.subheader("Job Description")

jd_input_method = st.radio(
    "Choose JD input method:",
    ["Upload file (PDF/DOCX/TXT)", "Paste text directly"],
    horizontal=True
)

jd_text = ""

if jd_input_method == "Upload file (PDF/DOCX/TXT)":
    jd_file = st.file_uploader("Upload JD file", type=["pdf", "docx", "txt"], key="jd_file")
    if jd_file:
        jd_text = read_any_fp(jd_file)
        st.success(f"JD loaded from {jd_file.name}")
else:
    jd_text_input = st.text_area(
        "Paste Job Description here:",
        height=250,
        placeholder="Paste your JD text here...",
        key="jd_text_area"
    )
    if jd_text_input.strip():
        jd_text = jd_text_input
        st.success(f"JD text received ({len(jd_text)} characters)")

st.subheader("Resumes")
resume_files = st.file_uploader(
    "Upload Resumes (PDF or DOCX)",
    type=["pdf", "docx"],
    accept_multiple_files=True,
    key="resume_files"
)

extra_kw = st.text_input("Extra keywords to highlight (comma-separated)")

if st.button("Screen Resumes", type="primary", key="screen_btn"):
    if not jd_text or not resume_files:
        st.error("Please provide both a JD and at least one resume.")
    else:
        with st.spinner("Analyzing JD and screening resumes..."):
            jd_role = get_role_from_jd(jd_text)
            jd_industry = get_industry_from_jd(jd_text)
            jd_keywords = extract_jd_keywords(jd_text)

            ROLE_LABELS = {
                "rnd_lead": "R&D Team Leader",
                "hr": "HR",
                "sales": "Sales",
                "technology": "Technology",
                "marketing": "Marketing",
                "operations": "Operations",
                "finance": "Finance",
                "data": "Data / Analytics",
                "other": "Other",
            }
            pretty_role = ROLE_LABELS.get(jd_role, jd_role.title())
            st.info(f"**JD Analysis:** Role = `{pretty_role}` | Industry = `{jd_industry.title()}`")

            extra_list = [w.strip().lower() for w in extra_kw.split(",") if w.strip()] if extra_kw.strip() else []

            if "resume_file_objects" not in st.session_state:
                st.session_state.resume_file_objects = {}

            rows = []
            for uf in resume_files:
                text = read_any_fp(uf)
                resume_name = uf.name

                uf.seek(0)
                st.session_state.resume_file_objects[resume_name] = uf.read()

                name = extract_name(text, resume_name)
                email = extract_email(text)
                mobile = extract_mobile(text)
                experience = extract_experience_years(text, filename=resume_name)
                education = extract_education(text)
                notice_period = extract_notice_period(text)
                current_company = extract_current_company(text)
                gaps = detect_gaps(text)
                top_skills = extract_top_skills(text)
                red_flags = detect_red_flags(text, experience)

                role_match, role_score, _ = check_role_match(text, jd_role)
                industry_match, industry_score, _ = check_industry_match(text, jd_industry)
                keyword_match = score_resume_against_jd(text, jd_keywords)
                semantic_match = jd_resume_similarity(jd_text, text)

                try:
                    exp_float = float(experience.replace(" Years", "").replace("-", "0"))
                except:
                    exp_float = 0.0

                # Relevance flag instead of dropping bad fits
                is_relevant = True
                if semantic_match < 15:
                    is_relevant = False
                if not role_match and semantic_match < 25:
                    is_relevant = False

                final_score = calculate_weighted_score(
                    role_match, role_score,
                    industry_match, industry_score,
                    keyword_match, semantic_match,
                    exp_float
                )

                extra_hits = []
                if extra_list:
                    tl = text.lower()
                    for w in extra_list:
                        if w in tl:
                            extra_hits.append(w)

                rows.append({
                    "Name": name,
                    "Email": email,
                    "Mobile": mobile,
                    "Experience": experience,
                    "Final Score": final_score,
                    "Semantic %": semantic_match,
                    "Keyword %": keyword_match,
                    "Role Match": "✓" if role_match else "✗",
                    "Role %": role_score,
                    "Industry Match": "✓" if industry_match else "✗",
                    "Industry %": industry_score,
                    "Relevant": "Yes" if is_relevant else "No",
                    "Education": education,
                    "Notice Period": notice_period,
                    "Current Company": current_company,
                    "Top Skills": top_skills,
                    "Employment Gaps": gaps,
                    "Red Flags": red_flags,
                    "Extra Keywords": ", ".join(extra_hits) if extra_hits else "-",
                    "Resume File": resume_name,
                })

        if not rows:
            st.warning("No resumes could be processed.")
        else:
            df = pd.DataFrame(rows)

            # Relevant first, then by score
            df["RelevantFlag"] = df["Relevant"].eq("Yes").astype(int)
            df = df.sort_values(
                by=["RelevantFlag", "Final Score"],
                ascending=[False, False]
            ).reset_index(drop=True)
            df.drop(columns=["RelevantFlag"], inplace=True)

            df.insert(0, "Rank", range(1, len(df) + 1))

            st.success(
                f"Screening complete! Uploaded {len(resume_files)} resumes, "
                f"showing {len(df)} (relevant first, then others)."
            )

            st.markdown("### Screening Results")
            st.dataframe(df, use_container_width=True, hide_index=True, height=400)

            st.markdown("### Download Individual Resumes")
            for idx, row in df.iterrows():
                filename = row["Resume File"]
                col1, col2, col3 = st.columns([2, 2, 6])
                with col1:
                    st.write(f"**{row['Name']}**")
                with col2:
                    st.write(f"Score: {row['Final Score']}")
                with col3:
                    if filename in st.session_state.resume_file_objects:
                        st.download_button(
                            label=f"📄 Download {filename}",
                            data=st.session_state.resume_file_objects[filename],
                            file_name=filename,
                            mime="application/pdf",
                            key=f"download_{idx}"
                        )

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📊 Download Full Report (CSV)",
                data=csv,
                file_name="joy_screening_report.csv",
                mime="text/csv",
            )

            st.markdown("### Screening Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Resumes", len(df))
            with col2:
                st.metric("Avg Score", f"{df['Final Score'].mean():.1f}")
            with col3:
                st.metric("Strong Matches (≥60)", len(df[df["Final Score"] >= 60]))
            with col4:
                perfect = len(df[(df["Role Match"] == "✓") & (df["Industry Match"] == "✓")])
                st.metric("Perfect Fit", perfect)
