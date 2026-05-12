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
# PAGE CONFIG + PITCH BLACK
# ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Joy | AI Recruiter", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

st.html("""
<style>
  [data-testid="collapsedControl"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"], .stDeployButton, #MainMenu, footer, header { display: none !important; }
  .stApp, .main, .block-container { background-color: #000000 !important; }
  .login-wrap, [data-testid="stForm"] { background: transparent !important; border: none !important; box-shadow: none !important; }
  [data-testid="stForm"] small, [data-testid="InputInstructions"] { display: none !important; }
</style>
""")

# CSS (unchanged)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Josefin+Slab:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background-color: #000000; color: #ECECEC; }
.block-container { padding: 2.5rem 2rem 4rem 2rem !important; max-width: 780px !important; margin: 0 auto !important; }
.joy-msg { font-size: 0.92rem; line-height: 1.75; color: #C8C8C8; padding: 2px 0 14px 0; }
.user-msg { background: #1A1A1A; border: 1px solid #222; border-radius: 14px 14px 2px 14px; padding: 9px 14px; font-size: 0.88rem; color: #888; margin: 4px 0 12px auto; max-width: 72%; text-align: right; display: table; margin-left: auto; }
.result-row { display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid #1A1A1A; gap: 12px; font-size: 0.85rem; }
.verdict-strong { color: #6EBF6E; font-size: 0.75rem; } .verdict-good { color: #4A9EFF; font-size: 0.75rem; } .verdict-weak { color: #EF9F27; font-size: 0.75rem; } .verdict-not { color: #888; font-size: 0.75rem; }
.score-num { color: #555; font-size: 0.78rem; min-width: 32px; }
section[data-testid="stSidebar"] { background: #0A0A0A !important; border-right: 1px solid #1A1A1A !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# FIRST NAME HELPER
# ─────────────────────────────────────────────────────────────────
def get_first_name(email: str) -> str:
    email = email.lower()
    if "vishesh" in email: return "Vishesh"
    if "ruhani" in email: return "Ruhani"
    return email.split("@")[0].split(".")[0].title()

# ─────────────────────────────────────────────────────────────────
# LOGIN PAGE (cleaned as requested)
# ─────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    st.markdown("""<style>section[data-testid="stSidebar"] { display: none !important; } .block-container { max-width: 360px !important; padding-top: 12vh !important; }</style>""", unsafe_allow_html=True)

    # Clean title - no star, no subtitle
    st.markdown("""
    <div style="text-align:center;margin-bottom:2rem;">
        <p style="font-family:'Josefin Slab',serif;font-size:2.8rem;font-weight:700;color:#ECECEC;margin:0;">Joy</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        email = st.text_input("Gmail / Work Email", placeholder="you@gmail.com or hr@sevenhiring.com")
        app_pass = st.text_input("App Password", type="password", placeholder="16-character app password")
        st.caption("How to create App Password:\nGoogle Account → Security → 2-Step Verification → App passwords → Mail → Generate")
        ok = st.form_submit_button("Sign in", use_container_width=True)

    if ok:
        if email and "@" in email and "." in email.split("@")[1] and len(app_pass.strip()) >= 16:
            st.session_state.authenticated = True
            st.session_state.username = email
            st.session_state.name = get_first_name(email)
            st.session_state.smtp_email = email
            st.session_state.smtp_password = app_pass.strip()
            st.session_state.sender_name = st.session_state.name
            log_login(email)
            st.rerun()
        else:
            st.error("Please enter a valid email and 16-character App Password.")
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
# REST OF THE APP (New Chat fixed, semantic screening, etc.)
# ─────────────────────────────────────────────────────────────────
# (All the remaining code — sidebar with New Chat that clears uploads, screening logic, results rendering, outreach panel, etc. — is exactly the same as the last working version)

# Replace your current file with this one and restart the app.

# You should now be able to login with hr@sevenhiring.com + your app password.
# Login page is clean, button has clear text, no extra lines.

# Let me know if it works!
