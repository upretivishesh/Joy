import streamlit as st
import pandas as pd
import pdfplumber
from docx import Document
from datetime import datetime
from zoneinfo import ZoneInfo
import re

from resume_parser import (
    extract_name, extract_email, extract_phone, extract_experience,
    score_resume_against_jd, get_role_from_jd, get_industry_from_jd,
    suggest_checks
)
from gpt_utils import gpt_score_resume, gpt_generate_email, gpt_generate_call_script
from email_utils import send_email
from database import save_to_db, load_history, clear_history, get_history_stats, save_chat_history, load_chat_history, log_login
from joy_ai import joy_analyze_candidate
from jd_generator import generate_jd, refine_jd

# ─────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Joy | AI Recruiter", page_icon="✦", layout="wide")

# ─────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────
defaults = {
    "authenticated": True,
    "name": "Vishesh",
    "page": "home",
    "chat_history": [],
    "results_df": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────
# NAV CORE (FIXED)
# ─────────────────────────────────────────────────────────────────
def go(page):
    if st.session_state.page != page:
        st.session_state.page = page
        st.query_params["joy_nav"] = page
        st.rerun()

def handle_nav():
    nav = st.query_params.get("joy_nav", "")
    if nav and nav != st.session_state.page:
        st.session_state.page = nav
        st.rerun()

handle_nav()

def render_nav():
    cols = st.columns(4)
    pages = ["home", "screen", "outreach", "history"]

    for i, p in enumerate(pages):
        if cols[i].button(p.capitalize(), use_container_width=True):
            go(p)

render_nav()

page = st.session_state.page

# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────
def read_file(f):
    if f.name.endswith(".pdf"):
        with pdfplumber.open(f) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    elif f.name.endswith(".docx"):
        return "\n".join(p.text for p in Document(f).paragraphs)
    return ""

# ─────────────────────────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────────────────────────
if page == "home":

    first = st.session_state.name.split()[0]

    st.markdown(f"""
    <div style="text-align:center; padding: 4rem 0 2rem 0;">
        <h1 style="font-size:2.5rem;">Hey {first}</h1>
        <p style="color:#777;">Joy is ready. Let’s hire someone dangerous.</p>
    </div>
    """, unsafe_allow_html=True)

    _, center, _ = st.columns([1, 3, 1])
    with center:
        msg = st.text_input("Ask Joy", placeholder="Type something...")

    if msg:
        st.session_state.chat_history.append(msg)

        if "screen" in msg.lower():
            go("screen")
        elif "outreach" in msg.lower():
            go("outreach")
        else:
            st.write("Thinking...")
            st.write(msg)

# ─────────────────────────────────────────────────────────────────
# SCREEN
# ─────────────────────────────────────────────────────────────────
elif page == "screen":

    st.title("Screen Resumes")

    uploaded = st.file_uploader("Upload resumes", accept_multiple_files=True)

    if uploaded:
        st.success(f"{len(uploaded)} resumes uploaded")

        if st.button("Run Screening"):
            with st.spinner("Screening..."):
                st.session_state.results_df = pd.DataFrame([
                    {"Name": "Candidate A", "Score": 87},
                    {"Name": "Candidate B", "Score": 78},
                ])
            st.rerun()

    if st.session_state.results_df is not None:
        st.subheader("Results")
        st.dataframe(st.session_state.results_df)

        if st.button("Go to Outreach"):
            go("outreach")

# ─────────────────────────────────────────────────────────────────
# OUTREACH
# ─────────────────────────────────────────────────────────────────
elif page == "outreach":

    st.title("Outreach")

    if st.session_state.results_df is None:
        st.warning("No candidates yet.")
        if st.button("Go to Screen"):
            go("screen")
    else:
        for _, r in st.session_state.results_df.iterrows():
            st.write(f"Emailing {r['Name']}...")

# ─────────────────────────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────────────────────────
elif page == "history":

    st.title("History")

    if st.session_state.results_df is not None:
        st.dataframe(st.session_state.results_df)
    else:
        st.info("No history yet.")
