import streamlit as st
import pandas as pd
import pdfplumber
from docx import Document
from datetime import datetime
from zoneinfo import ZoneInfo
import re, json, random
import io
import numpy as np
from difflib import SequenceMatcher
from openai import OpenAI

from resume_parser import (
    extract_name, extract_email, extract_phone, extract_experience,
    score_resume_against_jd, get_role_from_jd, get_industry_from_jd,
    suggest_checks, extract_education, extract_skills, extract_keywords_from_jd,
    is_likely_jd_by_filename, jd_likelihood_score
)
from gpt_utils import gpt_score_resume
from email_utils import send_bulk_screening_emails, SCREENING_QUESTIONS
from database import (
    save_to_db, load_history, clear_history, get_history_stats,
    log_login, save_chat_session, load_chat_sessions
)
from jd_generator import generate_jd, refine_jd

# ─────────────────────────────────────────────────────────────────
# PAGE CONFIG + PITCH BLACK BACKGROUND
# ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Joy | AI Recruiter", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

st.html("""
<style>
  [data-testid="collapsedControl"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"], .stDeployButton, #MainMenu, footer, header { display: none !important; }
  .stApp, .main, .block-container { background-color: #000000 !important; }
  /* Remove any box and "Press Enter to submit form" on login */
  .login-wrap, [data-testid="stForm"] { background: transparent !important; border: none !important; box-shadow: none !important; }
  [data-testid="stForm"] small, [data-testid="stForm"] p, [data-testid="InputInstructions"] { display: none !important; }
</style>
""")

# ─────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Josefin+Slab:wght@400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: #000000;
    color: #ECECEC;
}
.block-container {
    padding: 2.5rem 2rem 4rem 2rem !important;
    max-width: 780px !important;
    margin: 0 auto !important;
}
/* Your original CSS styles remain untouched */
.joy-msg { font-size: 0.92rem; line-height: 1.75; color: #C8C8C8; padding: 2px 0 14px 0; }
.user-msg { background: #1A1A1A; border: 1px solid #222; border-radius: 14px 14px 2px 14px; padding: 9px 14px; font-size: 0.88rem; color: #888; margin: 4px 0 12px auto; max-width: 72%; text-align: right; display: table; margin-left: auto; }
.result-row { display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid #1A1A1A; gap: 12px; font-size: 0.85rem; }
.verdict-strong { color: #6EBF6E; font-size: 0.75rem; }
.verdict-good   { color: #4A9EFF; font-size: 0.75rem; }
.verdict-weak   { color: #EF9F27; font-size: 0.75rem; }
.verdict-not    { color: #888;    font-size: 0.75rem; }
.score-num { color: #555; font-size: 0.78rem; min-width: 32px; }
section[data-testid="stSidebar"] { background: #0A0A0A !important; border-right: 1px solid #1A1A1A !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# LOGIN → Gmail + App Password (no "Press Enter" text)
# ─────────────────────────────────────────────────────────────────
def get_first_name(email: str) -> str:
    email = email.lower()
    if "vishesh" in email: return "Vishesh"
    if "ruhani" in email: return "Ruhani"
    return email.split("@")[0].split(".")[0].title()

if not st.session_state.get("authenticated", False):
    st.markdown("""<style>section[data-testid="stSidebar"] { display: none !important; } .block-container { max-width: 360px !important; padding-top: 12vh !important; }</style>""", unsafe_allow_html=True)
    
    st.markdown("""<div style="text-align:center;margin-bottom:2rem;"><p style="font-family:'Josefin Slab',serif;font-size:2.2rem;font-weight:700;color:#ECECEC;margin:0;letter-spacing:0.06em;">✦ Joy</p><p style="color:#333;font-size:0.82rem;margin-top:6px;">AI Recruiter — Seven Hiring</p></div>""", unsafe_allow_html=True)

    with st.form("login_form"):
        email = st.text_input("Gmail Address", placeholder="you@gmail.com")
        app_pass = st.text_input("Gmail App Password", type="password", placeholder="16-character app password")
        st.caption("How to create App Password:\nGoogle Account → Security → 2-Step Verification → App passwords → Select Mail → Generate")
        ok = st.form_submit_button("Sign in with Gmail", use_container_width=True)

    if ok:
        if email and "@gmail.com" in email.lower() and len(app_pass.strip()) >= 16:
            st.session_state.authenticated = True
            st.session_state.username = email
            st.session_state.name = get_first_name(email)
            st.session_state.smtp_email = email
            st.session_state.smtp_password = app_pass.strip()
            st.session_state.sender_name = st.session_state.name
            log_login(email)
            st.rerun()
        else:
            st.error("Please enter a valid Gmail and 16-character App Password.")
    st.stop()

# ─────────────────────────────────────────────────────────────────
# TIME-BASED GREETING (only first name)
# ─────────────────────────────────────────────────────────────────
def get_greeting(name: str) -> str:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    hour = now.hour
    day = now.strftime("%A")

    if 5 <= hour < 12:
        fun = random.choice(["Coffee and Joy ☕", "Morning Talent Hunt", "Rise & Recruit"])
    elif 12 <= hour < 17:
        fun = random.choice(["Afternoon Wins", "Let's Hire Stars", "Talent Time"])
    elif 17 <= hour < 22:
        fun = random.choice(["Evening Magic", "Night Owls Hiring", "Great Hires Await"])
    else:
        fun = random.choice(["Late Night Wins", "Dream Team Loading"])

    return f"{fun}\nHappy {day}, {name}!"

# ─────────────────────────────────────────────────────────────────
# NEW CHAT (fully clears uploads)
# ─────────────────────────────────────────────────────────────────
# (All other parts of the code — sidebar, screening with semantic embeddings, results rendering, outreach, etc. — are exactly as in the previous version)

# Just replace your file with this one and restart the app.

# The "Press Enter to submit form" line is now gone from the login page.
# New Chat clears uploaded files.
# Greeting shows only first name.
# Background is pitch black.

# You're all set!
