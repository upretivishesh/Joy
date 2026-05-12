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

# CSS - Hide "Press Enter to submit form" and make input clean
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Josefin+Slab:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background-color: #000000; color: #ECECEC; }
.block-container { padding: 2.5rem 2rem 4rem 2rem !important; max-width: 780px !important; margin: 0 auto !important; }

/* Hide "Press Enter to submit form" permanently */
[data-testid="stForm"] p, [data-testid="InputInstructions"], .stForm p, p:contains("Press Enter to submit form") {
    display: none !important;
}

/* Smaller, clean greeting */
.greeting-text { font-size: 2.05rem !important; line-height: 1.25; letter-spacing: -0.02em; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# FIRST NAME + COOKIE
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

    st.markdown('<div style="text-align:center;margin-bottom:2rem;"><p style="font-family:\'Josefin Slab\',serif;font-size:2.8rem;font-weight:700;color:#ECECEC;margin:0;">✦ Joy</p></div>', unsafe_allow_html=True)

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
# SESSION STATE + HELPERS
# ─────────────────────────────────────────────────────────────────
for k in ["chat", "results_df", "role_detected", "industry_detected", "generated_jd", "jd_role", "uploads", "show_outreach", "page"]:
    if k not in st.session_state:
        st.session_state[k] = [] if k in ["chat", "uploads"] else None

def read_file(f):
    n = f.name.lower()
    if n.endswith(".pdf"):
        with pdfplumber.open(f) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    elif n.endswith(".docx"):
        return "\n".join(p.text for p in Document(f).paragraphs)
    elif n.endswith(".txt"):
        return f.read().decode("utf-8", errors="ignore")
    return ""

def joy(text, typ="text"):
    st.session_state.chat.append({"role": "assistant", "content": text, "type": typ})

def push_user(text):
    st.session_state.chat.append({"role": "user", "content": text, "type": "text"})

# ─────────────────────────────────────────────────────────────────
# OPTIMIZED COOL GREETING ROTATION (much better variety)
# ─────────────────────────────────────────────────────────────────
def get_greeting(name: str) -> str:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    hour = now.hour

    if 5 <= hour < 12:
        options = ["Morning Recruit", "Rise & Hunt", "Talent Dawn", "Good Morning Hunt", "Coffee & Wins", "Early Talent"]
    elif 12 <= hour < 17:
        options = ["Afternoon Wins", "Hiring Mode", "Star Search", "Let's Build", "Peak Talent", "Midday Hunt"]
    elif 17 <= hour < 22:
        options = ["Evening Magic", "Night Owls", "Great Hires", "Team Dreams", "Evening Hunt", "Dusk Talent"]
    else:
        options = ["Late Night Wins", "Dream Team", "Future Loading", "Midnight Hunt", "Night Build", "After Hours"]

    fun = random.choice(options)
    return f"{fun}, {name}!"

if not st.session_state.chat:
    st.markdown(f"""
    <div style="text-align:center;padding:5vh 0 3vh;">
        <p class="greeting-text" style="font-family:'Josefin Slab',serif;font-size:2.05rem;font-weight:600;color:#ECECEC;line-height:1.25;margin:0;letter-spacing:-0.02em;">{get_greeting(st.session_state.name)}</p>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""<div style="padding:14px 14px 10px;border-bottom:1px solid #1A1A1A;font-family:'Josefin Slab',serif;font-size:0.88rem;font-weight:700;color:#ECECEC;letter-spacing:0.14em;">✦ JOY</div>""", unsafe_allow_html=True)

    if st.button("＋  New Chat", key="new_chat", use_container_width=True):
        if st.session_state.chat:
            save_chat_session(st.session_state.username, st.session_state.chat)
        st.session_state.chat = []
        st.session_state.results_df = None
        st.session_state.role_detected = ""
        st.session_state.industry_detected = ""
        st.session_state.generated_jd = ""
        st.session_state.jd_role = ""
        st.session_state.uploads = []
        st.session_state.show_outreach = False
        st.session_state.page = "main"
        st.rerun()

    if st.button("◷  History", key="nav_hist", use_container_width=True):
        st.session_state.page = "history"; st.rerun()
    if st.button("⚙  Settings", key="nav_set", use_container_width=True):
        st.session_state.page = "settings"; st.rerun()

    if st.button("⏻  Logout", key="logout", use_container_width=True):
        if cookie_ctrl:
            cookie_ctrl.remove("joy_email")
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ─────────────────────────────────────────────────────────────────
# CLEAN CENTERED INPUT (Claude-style - no Upload / Send buttons)
# ─────────────────────────────────────────────────────────────────
msg = st.text_input(
    "Type role/keywords to screen, ask Joy anything, or write a JD for...",
    label_visibility="collapsed",
    placeholder="Type here and press Enter...",
    key="chat_input"
)

if msg and st.button("Send", use_container_width=True):
    # Full screening logic can be placed here (same as before)
    st.rerun()

# Render chat
for m in st.session_state.chat:
    if m["role"] == "user":
        st.markdown(f'<div class="user-msg">{m["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="joy-msg">✦ {m["content"]}</div>', unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
