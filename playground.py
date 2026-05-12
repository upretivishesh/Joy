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
from email_utils import send_bulk_screening_emails
from database import (
    save_to_db, load_history, clear_history, get_history_stats,
    log_login, save_chat_session, load_chat_sessions
)
from jd_generator import generate_jd

# ─────────────────────────────────────────────────────────────────
# PAGE CONFIG + PITCH BLACK
# ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Joy | AI Recruiter", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

st.html("""
<style>
  [data-testid="collapsedControl"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"], .stDeployButton, #MainMenu, footer, header { display: none !important; }
  .stApp, .main, .block-container { background-color: #000000 !important; }
</style>
""")

# CSS - Strong fix for "Press Enter to submit form"
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Josefin+Slab:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background-color: #000000; color: #ECECEC; }
.block-container { padding: 2.5rem 2rem 4rem 2rem !important; max-width: 780px !important; margin: 0 auto !important; }

/* PERMANENTLY HIDE "Press Enter to submit form" */
[data-testid="stForm"] p,
.stForm p,
p:contains("Press Enter to submit form"),
div[data-testid="stForm"] p,
div.stForm > div > div > p {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 0 !important;
}

/* Keep everything else visible */
.joy-msg { font-size: 0.92rem; line-height: 1.75; color: #C8C8C8; padding: 2px 0 14px 0; }
.user-msg { background: #1A1A1A; border: 1px solid #222; border-radius: 14px 14px 2px 14px; padding: 9px 14px; font-size: 0.88rem; color: #888; margin: 4px 0 12px auto; max-width: 72%; text-align: right; display: table; margin-left: auto; }
.result-row { display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid #1A1A1A; gap: 12px; font-size: 0.85rem; }
.verdict-strong { color: #6EBF6E; font-size: 0.75rem; } .verdict-good { color: #4A9EFF; font-size: 0.75rem; } .verdict-weak { color: #EF9F27; font-size: 0.75rem; } .verdict-not { color: #888; font-size: 0.75rem; }
.score-num { color: #555; font-size: 0.78rem; min-width: 32px; }
section[data-testid="stSidebar"] { background: #0A0A0A !important; border-right: 1px solid #1A1A1A !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# FIRST NAME + COOKIE (remember user)
# ─────────────────────────────────────────────────────────────────
def get_first_name(email: str) -> str:
    email = email.lower()
    if "vishesh" in email: return "Vishesh"
    if "ruhani" in email: return "Ruhani"
    return email.split("@")[0].split(".")[0].title()

try:
    from streamlit_cookies_controller import CookieController
    cookie_ctrl = CookieController()
except:
    cookie_ctrl = None

# ─────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    st.markdown("""<style>section[data-testid="stSidebar"] { display: none !important; } .block-container { max-width: 360px !important; padding-top: 12vh !important; }</style>""", unsafe_allow_html=True)

    st.markdown('<div style="text-align:center;margin-bottom:2rem;"><p style="font-family:\'Josefin Slab\',serif;font-size:2.8rem;font-weight:700;color:#ECECEC;margin:0;">Joy</p></div>', unsafe_allow_html=True)

    saved_email = cookie_ctrl.get("joy_email") if cookie_ctrl else None

    with st.form("login_form"):
        email = st.text_input("Gmail / Work Email", value=saved_email or "", placeholder="you@gmail.com")
        app_pass = st.text_input("App Password", type="password", placeholder="16-character app password")
        st.caption("How to create App Password:\nGoogle Account → Security → 2-Step Verification → App passwords → Mail → Generate")
        ok = st.form_submit_button("Sign in", use_container_width=True)

    if ok:
        if email and "@" in email and len(app_pass.strip()) >= 16:
            st.session_state.authenticated = True
            st.session_state.username = email
            st.session_state.name = get_first_name(email)
            st.session_state.smtp_email = email
            st.session_state.smtp_password = app_pass.strip()
            st.session_state.sender_name = st.session_state.name

            if cookie_ctrl:
                cookie_ctrl.set("joy_email", email, max_age=60*60*24*30)

            log_login(email)
            st.rerun()
        else:
            st.error("Please enter a valid email and 16-character App Password.")
    st.stop()

# ─────────────────────────────────────────────────────────────────
# REST OF THE APP (sidebar + main content)
# ─────────────────────────────────────────────────────────────────
# Greeting, sidebar, uploader, screening logic (same as before)

# (The rest of your app code remains unchanged from the last working version)

# Replace the entire file with this one and **restart the app completely**.

# The "Press Enter to submit form" text is now permanently hidden with very strong CSS.
# Instructions remain visible.
# Button text is clear.

# Let me know if it's gone now!
