import streamlit as st
import pdfplumber
from docx import Document
import pandas as pd
import re
import warnings

warnings.filterwarnings("ignore")

# ---------- IMPORTS ----------
from parser import (
    extract_jd_keywords,
    score_resume_against_jd,
    get_role_from_jd,
    get_industry_from_jd,
    check_role_match,
    check_industry_match,
    calculate_weighted_score,
    generate_rejection_reason,
    suggest_checks
)

from database import save_to_db, load_history
from email_utils import generate_email

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------- CONFIG ----------
st.set_page_config(page_title="Joy - Seven Hiring", layout="wide")

# ---------- LOGIN ----------
USERS = {
    "vishesh": {"password": "Qwerty@0987", "name": "Vishesh"},
    "ruhani": {"password": "Ruhani@$67", "name": "Ruhani"},
    "amisha": {"password": "Amisha@$11", "name": "Amisha"}
}

def check_login(username, password):
    if username in USERS and USERS[username]["password"] == password:
        return True, USERS[username]["name"]
    return False, None

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""

if not st.session_state.logged_in:
    st.title("Joy – Resume Screening Tool")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        ok, name = check_login(username.lower(), password)
        if ok:
            st.session_state.logged_in = True
            st.session_state.user_name = name
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.stop()

# ---------- SIDEBAR ----------
with st.sidebar:
    st.write(f"Logged in as: {st.session_state.user_name}")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

st.title(f"Hi {st.session_state.user_name}")
st.markdown("---")

# ---------- HELPERS ----------

def read_file(file):
    name = file.name.lower()
    if name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    elif name.endswith(".docx"):
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        return file.read().decode(errors="ignore")

def extract_email(text):
    m = re.findall(r"\S+@\S+", text)
    return m[0] if m else "-"

def extract_mobile(text):
    m = re.findall(r"\d{10}", text)
    return m[0] if m else "-"

def extract_experience(text):
    m = re.findall(r"(\d+)\s+years", text.lower())
    return float(m[0]) if m else 0.0

def extract_notice_period(text):
    tl = text.lower()
    if "90" in tl:
        return "90 days"
    elif "60" in tl:
        return "60 days"
    elif "30" in tl:
        return "30 days"
    elif "15" in tl:
        return "15 days"
    return "-"

def detect_red_flags(text):
    if len(text) < 500:
        return "Short resume"
    if "@" not in text:
        return "No email"
    return "None"

def jd_similarity(jd, resume):
    jd = jd[:1500]
    resume = resume[:1500]

    docs = [jd.lower(), resume.lower()]
    tfidf = TfidfVectorizer(
        stop_words="english",
        max_features=2000
    ).fit_transform(docs)

    return round(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0] * 100, 1)

# ---------- TABS ----------
tab1, tab2 = st.tabs(["Screening", "History"])

# =========================
# 🔍 SCREENING TAB
# =========================
with tab1:

    st.subheader("Job Description")
    jd_text = st.text_area("Paste JD here")

    st.subheader("Upload Resumes")
    resumes = st.file_uploader("Upload resumes", type=["pdf", "docx"], accept_multiple_files=True)

    if st.button("Screen Resumes"):

        if not jd_text or not resumes:
            st.error("Upload JD and resumes")
            st.stop()

        rows = []

        jd_role = get_role_from_jd(jd_text)
        jd_industry = get_industry_from_jd(jd_text)
        jd_keywords = extract_jd_keywords(jd_text)

        with st.spinner("Processing resumes..."):

            for file in resumes:
                st.write(f"Processing: {file.name}")

                text = read_file(file)[:3000]

                email = extract_email(text)
                mobile = extract_mobile(text)
                exp = extract_experience(text)
                notice = extract_notice_period(text)
                red_flags = detect_red_flags(text)

                role_match, role_score = check_role_match(text, jd_role)
                ind_match, ind_score = check_industry_match(text, jd_industry)

                keyword_score = score_resume_against_jd(text, jd_keywords)
                semantic_score = jd_similarity(jd_text, text)

                final_score = calculate_weighted_score(
                    role_score, ind_score, keyword_score, semantic_score, exp
                )

                relevant = "Yes" if semantic_score > 20 else "No"

                row = {
                    "Name": file.name,
                    "Email": email,
                    "Mobile": mobile,
                    "Experience": exp,
                    "Notice Period": notice,
                    "Final Score": final_score,
                    "Relevant": relevant,
                    "Role Match": "✓" if role_match else "✗",
                    "Industry Match": "✓" if ind_match else "✗",
                    "Semantic %": semantic_score,
                    "Keyword %": keyword_score,
                    "Red Flags": red_flags,
                }

                # Rejection + Suggestions
                row["Rejection Reason"] = generate_rejection_reason(
                    role_match, ind_match, semantic_score, keyword_score
                )

                rows.append(row)

        df = pd.DataFrame(rows)
        df = df.sort_values(by="Final Score", ascending=False)

        # Suggestions (SAFE NOW)
        df["Suggestions"] = df.apply(suggest_checks, axis=1)

        # Save history
        save_to_db(df, jd_role, jd_industry)

        st.success("Screening Complete")
        st.dataframe(df, use_container_width=True)

        # ---------- EMAIL ----------
        st.subheader("Email Candidates")

        for i, row in df.iterrows():
            if st.button(f"Generate Email for {row['Name']}", key=f"email_{i}"):
                st.text_area(
                    f"Email to {row['Name']}",
                    generate_email(row["Name"]),
                    height=200
                )

# =========================
# 📂 HISTORY TAB
# =========================
with tab2:

    st.subheader("Candidate History")

    hist = load_history()

    if hist.empty:
        st.info("No previous data")
    else:
        st.dataframe(hist, use_container_width=True)
