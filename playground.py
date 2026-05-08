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
from database import save_to_db, load_history, clear_history, get_history_stats, save_chat_history, load_chat_history, log_login, load_login_log, save_chat_session, load_chat_sessions
from joy_ai import get_greeting, joy_analyze_candidate
from jd_generator import generate_jd, refine_jd

# ── CACHED HELPERS for speed ──
@st.cache_data(show_spinner=False, ttl=3600)
def cached_gpt_answer(system: str, user: str, ctx: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    msgs = [{"role": "system", "content": system}]
    if ctx:
        msgs.append({"role": "system", "content": ctx})
    msgs.append({"role": "user", "content": user})
    res = client.chat.completions.create(model="gpt-4o-mini", messages=msgs, max_tokens=300, temperature=0.8)
    return res.choices[0].message.content.strip()

@st.cache_data(show_spinner=False, ttl=600)
def cached_extract_params(user_msg: str) -> dict:
    from openai import OpenAI
    import json, re
    client = OpenAI()
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Extract: role title, industry, location, experience from this. Return JSON only: {{\"role\":\"\",\"industry\":\"\",\"location\":\"\",\"experience\":\"\"}}\n\nRequest: {user_msg}"}],
        max_tokens=150
    )
    raw = re.sub(r"```json|```", "", res.choices[0].message.content).strip()
    try:
        return json.loads(raw)
    except:
        return {"role": user_msg, "industry": "", "location": "", "experience": ""}

@st.cache_data(show_spinner=False, ttl=1800)
def cached_generate_jd(role, industry, location, experience, company) -> str:
    return generate_jd(role=role, industry=industry, location=location,
                       experience_range=experience, company_name=company)

# Greeting lines pool — used on home page and new chat
lines_pool = [
    "The right hire changes everything.",
    "Great talent doesn't find itself.",
    "Your next star hire is one screen away.",
    "Pipelines don't fill themselves.",
    "Let's find someone brilliant today.",
    "Good people are out there. Let's go find them.",
    "Every great team started with one great hire.",
    "Joy's ready when you are.",
    "The best recruiters don't just hire — they build legacies.",
    "Somewhere out there is your perfect candidate.",
    "Hiring is just matchmaking with better vocabulary.",
    "A bad hire costs more than a missed one. Choose wisely.",
    "Behind every great company is a recruiter who didn't settle.",
    "Talent is everywhere. The trick is knowing where to look.",
    "Great hiring is 10% instinct and 90% Joy.",
    "You're not just filling roles. You're building futures.",
    "The best interview question? Let Joy rank them first.",
    "Résumés don't hire people. Recruiters do.",
    "Find the right person once. Stop hiring forever.",
    "Culture fit is real. So is Joy's scoring algorithm.",
    "Speed matters. The best candidates have three offers by Friday.",
    "Not all CVs are created equal. Joy knows the difference.",
    "Your competitors are also hiring today. Move faster.",
    "The best hire you ever made started with a great JD.",
    "Stop guessing. Start screening.",
]

try:
    from twilio_utils import make_call, format_phone_for_twilio, send_sms
    TWILIO_OK = True
except ImportError:
    TWILIO_OK = False

# ─────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Joy | AI Recruiter",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject into <head> synchronously — this fires before Streamlit renders anything
# This is the only reliable way to kill the deploy button / sidebar toggle ghost box
st.html("""
<style>
  [data-testid="collapsedControl"],
  [data-testid="stToolbar"],
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  .stDeployButton,
  #MainMenu,
  footer,
  header {
    display: none !important;
    height: 0 !important;
    width: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
  }
</style>
""")

# ─────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Josefin+Slab:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0F0F0F;
    color: #ECECEC;
}

/* Hide streamlit chrome completely */
#MainMenu, footer, header { display: none !important; visibility: hidden !important; }

/* Main content area — centered in the space right of sidebar */
.block-container {
    padding: 3rem 2rem 4rem 2rem !important;
    max-width: 720px !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

/* Hide the chat form submit button visually — Enter still works */
[data-testid="stForm"] [data-testid="stFormSubmitButton"] { display: none !important; }

/* Hide "Press Enter to apply" tooltip on all inputs */
[data-testid="InputInstructions"] { display: none !important; }

/* Nav buttons — plain text style */
[data-testid="stButton"][class*="nav"] > button,
.stButton > button {
    background: transparent !important;
    color: #666 !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 0.3rem 0.5rem !important;
    font-family: 'Josefin Slab', serif !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    transition: color 0.15s ease !important;
    box-shadow: none !important;
    width: auto !important;
}
.stButton > button:hover {
    background: transparent !important;
    color: #ECECEC !important;
    border: none !important;
}

/* Non-nav action buttons — keep styled */
.action-button > div > button {
    background: #1A1A1A !important;
    color: #ECECEC !important;
    border: 1px solid #2E2E2E !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.88rem !important;
    text-transform: none !important;
    letter-spacing: normal !important;
    padding: 0.5rem 1.2rem !important;
}

/* Action cards — full button styled as card */
.card-btn > div > button {
    background: #161616 !important;
    border: 1px solid #2A2A2A !important;
    border-radius: 12px !important;
    padding: 18px 20px !important;
    height: 110px !important;
    width: 100% !important;
    text-align: left !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
    gap: 4px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    white-space: normal !important;
    line-height: 1.4 !important;
    font-size: 0.88rem !important;
    color: #ECECEC !important;
}
.card-btn > div > button:hover {
    border-color: #444 !important;
    background: #1C1C1C !important;
}

/* Joy response — plain text, no box */
.joy-bubble {
    background: transparent;
    border: none;
    padding: 2px 0 10px 0;
    font-size: 0.92rem;
    line-height: 1.7;
    color: #D0D0D0;
    margin: 0 0 4px 0;
}

/* User bubble */
.user-bubble {
    background: #181818;
    border: 1px solid #222;
    border-radius: 14px 14px 2px 14px;
    padding: 9px 14px;
    font-size: 0.88rem;
    color: #999;
    margin: 4px 0 10px auto;
    max-width: 75%;
    text-align: right;
    display: table;
    margin-left: auto;
}

/* Inputs */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #161616 !important;
    border: 1px solid #2E2E2E !important;
    border-radius: 8px !important;
    color: #ECECEC !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #444 !important;
    box-shadow: none !important;
}

/* Select box */
.stSelectbox > div > div {
    background: #161616 !important;
    border: 1px solid #2E2E2E !important;
    border-radius: 8px !important;
    color: #ECECEC !important;
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: #161616;
    border: 1px dashed #2E2E2E;
    border-radius: 10px;
    padding: 1rem;
}

/* Dataframe */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* Divider */
hr { border-color: #2A2A2A !important; margin: 1.5rem 0 !important; }

/* Metrics */
[data-testid="stMetric"] {
    background: #161616;
    border: 1px solid #2A2A2A;
    border-radius: 10px;
    padding: 14px 18px;
}
[data-testid="stMetricLabel"] { color: #888 !important; font-size: 0.8rem !important; }
[data-testid="stMetricValue"] { color: #ECECEC !important; font-size: 1.5rem !important; font-weight: 600 !important; }

/* Tab-style nav pills */
.nav-pill {
    display: inline-block;
    background: #1A1A1A;
    border: 1px solid #2E2E2E;
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 0.8rem;
    color: #888;
    margin: 0 4px 8px 0;
    cursor: pointer;
}
.nav-pill.active {
    background: #2A2A2A;
    color: #ECECEC;
    border-color: #444;
}

/* Call log */
.call-log {
    background: #0D1F0D;
    border: 1px solid #1A3A1A;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    color: #6EBF6E;
    margin: 5px 0;
}

/* Expander */
[data-testid="stExpander"] {
    background: #161616 !important;
    border: 1px solid #2A2A2A !important;
    border-radius: 10px !important;
}

/* Success / Error / Warning */
[data-testid="stAlert"] { border-radius: 8px !important; }

/* Section label */
.section-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #555;
    margin: 1.5rem 0 0.6rem 0;
}

/* Greeting headline */
.greeting-title {
    font-size: 2.6rem;
    font-weight: 600;
    color: #ECECEC;
    line-height: 1.2;
    margin-bottom: 4px;
    font-family: 'Josefin Slab', serif;
    letter-spacing: 0.01em;
}
.greeting-sub {
    font-size: 0.9rem;
    color: #555;
    margin-bottom: 2rem;
}

/* Login card */
.login-card {
    background: #161616;
    border: 1px solid #2A2A2A;
    border-radius: 14px;
    padding: 2.5rem 2rem;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# USERS — plain password check (bcrypt hashing on load was slow)
# ─────────────────────────────────────────────────────────────────
USERS = {
    "vishesh": {"name": "Vishesh Upreti",  "password": "Qwerty@0987"},
    "ruhani":  {"name": "Ruhani Sukhija",  "password": "Ruhani@$67"},
}

def verify_password(username, password):
    if username in USERS:
        return USERS[username]["password"] == password
    return False

# ─────────────────────────────────────────────────────────────────
# COOKIE MANAGER — persistent login
# ─────────────────────────────────────────────────────────────────
try:
    from streamlit_cookies_controller import CookieController
    cookie_ctrl = CookieController()
    COOKIES_OK = True
except Exception:
    cookie_ctrl = None
    COOKIES_OK = False

# ─────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────
defaults = {
    "authenticated": False,
    "username": "", "name": "",
    "page": "home",
    "results_df": None, "role_detected": "", "industry_detected": "",
    "smtp_email": "", "smtp_password": "",
    "twilio_sid": "", "twilio_token": "", "twilio_from": "",
    "chat_history": [], "call_log": [],
    "generated_jd": "", "jd_role": "",
    "email_draft": "", "call_script": "",
    "sender_name": "",
    "_history_loaded": False,
    "_cookie_checked": False
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────
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

def joy_bubble(text):
    st.markdown(f'<div class="joy-bubble">✦ {text}</div>', unsafe_allow_html=True)

def user_bubble(text):
    st.markdown(f'<div class="user-bubble">{text}</div>', unsafe_allow_html=True)

def section_label(text):
    st.markdown(f'<p class="section-label">{text}</p>', unsafe_allow_html=True)

def go(page):
    st.session_state.page = page
    st.rerun()

def persist_chat(history):
    try:
        save_chat_history(st.session_state.username, history)
    except Exception:
        pass

def do_login(ukey):
    """Set session state after successful login."""
    uname = USERS[ukey]["name"]
    st.session_state.authenticated = True
    st.session_state.username      = ukey
    st.session_state.name          = uname
    st.session_state.sender_name   = uname
    st.session_state.chat_history  = []   # always fresh chat on login
    st.session_state._history_loaded = True
    log_login(ukey)
    if COOKIES_OK:
        try:
            cookie_ctrl.set("joy_user", ukey, max_age=60*60*24*365)
        except Exception:
            pass

def do_logout():
    if COOKIES_OK:
        try:
            cookie_ctrl.remove("joy_user")
        except Exception:
            pass
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

# ─────────────────────────────────────────────────────────────────
# COOKIE RESTORE — check once per browser session
# ─────────────────────────────────────────────────────────────────
if not st.session_state._cookie_checked:
    st.session_state._cookie_checked = True
    if COOKIES_OK and not st.session_state.authenticated:
        try:
            saved = cookie_ctrl.get("joy_user")
            if saved and saved in USERS:
                do_login(saved)
                st.rerun()
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────
# LOGIN PAGE
# ─────────────────────────────────────────────────────────────────
if not st.session_state.authenticated:
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"]  { display: none !important; }
    .block-container {
        max-width: 400px !important;
        margin: 0 auto !important;
        padding-top: 12vh !important;
    }
    .stButton > button {
        background: #ECECEC !important;
        color: #0F0F0F !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.65rem 1rem !important;
        font-family: 'Josefin Slab', serif !important;
        font-weight: 600 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        font-size: 0.85rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center; margin-bottom:2.5rem;">
        <p style="font-family:'Josefin Slab',serif; font-size:2.4rem; font-weight:700;
                  color:#ECECEC; margin:0; letter-spacing:0.06em;">✦ Joy</p>
        <p style="color:#444; font-size:0.85rem; margin-top:8px; font-family:'Inter',sans-serif;">
            AI Recruiter — Seven Hiring
        </p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        u = st.text_input("Username", placeholder="Enter username")
        p = st.text_input("Password", type="password", placeholder="Enter password")
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        ukey = u.strip().lower()
        if ukey in USERS and verify_password(ukey, p):
            do_login(ukey)
            st.rerun()
        else:
            st.error("Invalid credentials.")
    st.stop()

# ── Load chat history if not yet loaded (cookie restore path) ──
if not st.session_state._history_loaded and st.session_state.username:
    st.session_state.chat_history    = []   # fresh chat, don't restore
    st.session_state._history_loaded = True

# ─────────────────────────────────────────────────────────────────
# SIDEBAR — Streamlit native (reliable buttons) + custom CSS overlay
# ─────────────────────────────────────────────────────────────────
def render_nav():
    uname    = st.session_state.name
    initials = "".join(w[0].upper() for w in uname.split()[:2]) if uname else "?"
    page     = st.session_state.page

    # Style the Streamlit sidebar to look like the custom one
    st.markdown("""
    <style>
    /* Sidebar base */
    section[data-testid="stSidebar"] {
        background: #111111 !important;
        border-right: 1px solid #1E1E1E !important;
        width: 220px !important;
        min-width: 220px !important;
    }
    /* Keep the toggle button visible so users can collapse sidebar */
    [data-testid="collapsedControl"] {
        background: #111111 !important;
        border-right: 1px solid #1E1E1E !important;
    }
    [data-testid="collapsedControl"] button {
        color: #333 !important;
    }
    [data-testid="collapsedControl"] button:hover {
        color: #666 !important;
        background: transparent !important;
    }
    button[data-testid="stBaseButton-headerNoPadding"] { display: none !important; }

    /* Sidebar inner */
    section[data-testid="stSidebar"] > div:first-child {
        padding: 0 !important;
    }

    /* Nav buttons */
    section[data-testid="stSidebar"] .stButton > button {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        color: #555 !important;
        font-family: 'Josefin Slab', serif !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        text-align: left !important;
        padding: 10px 16px !important;
        width: 200px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        justify-content: flex-start !important;
        box-shadow: none !important;
        transition: color 0.15s, background 0.15s !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #1A1A1A !important;
        color: #ECECEC !important;
    }
    /* Chat history items — tight spacing */
    section[data-testid="stSidebar"] .chat-history-item button {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.73rem !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        color: #3A3A3A !important;
        padding: 4px 16px !important;
        width: 200px !important;
        text-align: left !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 1.3 !important;
    }
    section[data-testid="stSidebar"] .chat-history-item button:hover {
        color: #ABABAB !important;
        background: #161616 !important;
    }
    /* Reduce gap between stButton elements in sidebar */
    section[data-testid="stSidebar"] .stButton {
        margin-bottom: 0 !important;
        margin-top: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div {
        gap: 0 !important;
    }
    /* Hide labels */
    section[data-testid="stSidebar"] label { display: none !important; }
    section[data-testid="stSidebar"] .stMarkdown p {
        color: #333 !important;
        font-size: 0.62rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
        padding: 6px 16px 2px !important;
        margin: 0 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
    }
    /* Dividers */
    section[data-testid="stSidebar"] hr {
        border-color: #1E1E1E !important;
        margin: 3px 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        # Logo
        st.markdown(f"""
        <div style="padding:18px 16px 14px;border-bottom:1px solid #1E1E1E;
                    font-family:'Josefin Slab',serif;font-size:1rem;font-weight:700;
                    color:#ECECEC;letter-spacing:0.1em;white-space:nowrap;">
            ✦ JOY
        </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Nav buttons
        if st.button("⌂  Home",     key="nav_home",     use_container_width=True): go("home")
        if st.button("⊞  Screen",   key="nav_screen",   use_container_width=True): go("screen")
        if st.button("✉  Outreach", key="nav_outreach", use_container_width=True): go("outreach")
        if st.button("◷  History",  key="nav_history",  use_container_width=True): go("history")

        st.markdown("---")

        # Past chat sessions
        past = load_chat_sessions(st.session_state.username)
        if past:
            st.markdown("Recent")
            for i, session in enumerate(past[:8]):
                label = session.get("preview", "Chat")[:28]
                st.markdown('<div class="chat-history-item">', unsafe_allow_html=True)
                if st.button(f"  {label}", key=f"past_{i}", use_container_width=True):
                    st.session_state.chat_history = session.get("messages", [])
                    go("home")
                st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("---")

        # Bottom — new chat + user
        if st.button("＋  New Chat", key="nav_new", use_container_width=True):
            import random
            # Save current chat before clearing
            if st.session_state.chat_history:
                save_chat_session(st.session_state.username, st.session_state.chat_history)
            st.session_state.chat_history = []
            if "greeting_line" in st.session_state:
                del st.session_state["greeting_line"]
            go("home")

        # User avatar + settings/logout
        st.markdown(f"""
        <div style="padding:12px 16px;border-top:1px solid #1E1E1E;margin-top:8px;
                    display:flex;align-items:center;gap:10px;white-space:nowrap;overflow:hidden;">
            <div style="width:28px;height:28px;background:#2A2A2A;border:1px solid #333;
                        border-radius:50%;display:flex;align-items:center;justify-content:center;
                        font-size:0.68rem;font-weight:600;color:#ECECEC;flex-shrink:0;">{initials}</div>
            <div>
                <div style="font-size:0.78rem;color:#ECECEC;font-family:'Inter',sans-serif;">{uname}</div>
                <div style="font-size:0.65rem;color:#444;font-family:'Inter',sans-serif;">Seven Hiring</div>
            </div>
        </div>""", unsafe_allow_html=True)

        if st.button("⚙  Settings", key="nav_settings", use_container_width=True): go("settings")
        if st.button("⏻  Logout",   key="nav_logout",   use_container_width=True): do_logout()

# ─────────────────────────────────────────────────────────────────
# PAGE ROUTER
# ─────────────────────────────────────────────────────────────────
page = st.session_state.page
render_nav()

# ═════════════════════════════════════════════════════════════════
# HOME — Claude-style landing
# ═════════════════════════════════════════════════════════════════
if page == "home":

    now  = datetime.now(ZoneInfo("Asia/Kolkata"))
    first = st.session_state.name.split()[0]

    import random
    if "greeting_line" not in st.session_state:
        st.session_state.greeting_line = random.choice(lines_pool)
    greeting_line = st.session_state.greeting_line

    # ── CENTERED GREETING ──
    # When no chat yet — vertically center the whole thing like Claude
    if not st.session_state.chat_history:
        st.markdown(f"""
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 55vh;
            text-align: center;
        ">
            <p style="
                font-size: 2.6rem;
                font-weight: 600;
                color: #ECECEC;
                font-family: 'Josefin Slab', serif;
                letter-spacing: 0.01em;
                line-height: 1.2;
                margin: 0 auto 3rem auto;
                max-width: 620px;
            ">{greeting_line}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="text-align:center; padding: 2.5rem 0 1.5rem 0;">
            <p style="font-size:1.6rem; font-weight:600; color:#ECECEC;
                      font-family:'Josefin Slab',serif; letter-spacing:0.01em;
                      line-height:1.2; margin:0 auto; max-width:580px;">
                {greeting_line}
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ── CHAT HISTORY — no duplicates, tight spacing ──
    for turn in st.session_state.chat_history[-14:]:
        if turn["role"] == "jd":
            continue
        if turn["role"] == "assistant":
            joy_bubble(turn["content"])
        elif turn["role"] == "user":
            user_bubble(turn["content"])

    # ── RENDER JD ABOVE SEARCH BAR ──
    for i, turn in enumerate(st.session_state.chat_history):
        if turn["role"] == "jd":
            jd_content = turn["content"]
            role_name  = st.session_state.get("jd_role", "Role")
            st.markdown(f"""
            <div style="background:#141414;border:1px solid #222;border-radius:10px;
                        padding:14px 16px;margin:8px 0 12px 0;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                    <span style="font-size:0.7rem;color:#444;font-family:'Inter',sans-serif;
                                 text-transform:uppercase;letter-spacing:0.08em;">
                        Generated JD — {role_name}
                    </span>
                </div>
                <pre style="font-size:0.78rem;color:#888;white-space:pre-wrap;
                             line-height:1.6;font-family:'Inter',sans-serif;margin:0;
                             max-height:200px;overflow-y:auto;">{jd_content[:1200]}{"..." if len(jd_content)>1200 else ""}</pre>
            </div>
            """, unsafe_allow_html=True)
            # Copy + Download + Use buttons
            jd_cols = st.columns([1, 1, 1, 3])
            with jd_cols[0]:
                if st.button("📋 Copy", key=f"copy_{i}", use_container_width=True):
                    st.session_state[f"copied_{i}"] = True
                    st.toast("Copied to clipboard!")
            with jd_cols[1]:
                st.download_button("⬇ Download", jd_content.encode(),
                                   f"JD_{role_name.replace(' ','_')}.txt",
                                   "text/plain", key=f"dl_{i}", use_container_width=True)
            with jd_cols[2]:
                if st.button("Use for Screening", key=f"use_{i}", use_container_width=True):
                    st.session_state["prefilled_jd"] = jd_content
                    st.session_state.page = "screen"
                    st.rerun()

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    # ── ASK JOY INPUT — full width, Enter submits ──
    with st.form(key="chat_form", clear_on_submit=True):
        msg = st.text_input(
            "Ask Joy",
            placeholder="Ask me anything — form a JD, who's the best candidate, screen resumes...",
            label_visibility="collapsed"
        )
        submitted = st.form_submit_button("↵", use_container_width=False)

        if submitted and msg.strip():
            user_msg = msg.strip()
            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            persist_chat(st.session_state.chat_history)

            msg_lower = user_msg.lower()

            # ── INTENT DETECTION — keyword-based, instant, reliable ──

            # JD Generation — most common use case
            jd_triggers = ["jd", "job description", "form a jd", "write a jd", "create a jd",
                           "draft a jd", "make a jd", "generate a jd", "jd for", "role for"]
            is_jd = any(t in msg_lower for t in jd_triggers)

            # Candidate questions — answer from real screening data
            cand_triggers = ["top candidate", "best candidate", "who should", "shortlist",
                             "strongest", "who scored", "highest score", "recommend",
                             "who to hire", "best fit", "top pick"]
            is_cand = any(t in msg_lower for t in cand_triggers)

            # Navigate to screen
            screen_triggers = ["screen", "screening", "upload resume", "rank candidates",
                               "score resume", "evaluate resume"]
            is_screen = any(t in msg_lower for t in screen_triggers)

            # Navigate to outreach
            outreach_triggers = ["email", "call", "outreach", "contact candidate", "reach out", "sms"]
            is_outreach = any(t in msg_lower for t in outreach_triggers)

            # ── EXECUTE ACTIONS ──

            if is_jd:
                with st.spinner("Writing JD..."):
                    params = cached_extract_params(user_msg)
                    jd = cached_generate_jd(
                        params.get("role", user_msg),
                        params.get("industry", ""),
                        params.get("location", ""),
                        params.get("experience", ""),
                        "Our client"
                    )
                    st.session_state.generated_jd = jd
                    st.session_state.jd_role = params.get("role", "")

                reply = f"Done. Here's the JD for **{params.get('role', 'the role')}**:"
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
                st.session_state.chat_history.append({"role": "jd", "content": jd})

            elif is_cand and st.session_state.results_df is not None:
                # Answer from real screening data
                df = st.session_state.results_df
                top = df.iloc[0]
                strong = df[df["Verdict"] == "Strong Fit"]
                good   = df[df["Verdict"] == "Good Fit"]

                from joy_ai import joy_analyze_candidate
                analysis = joy_analyze_candidate(top.to_dict(), st.session_state.name)

                reply = (
                    f"**Top pick: {top['Name']}** — Score {top['Final Score']}, {top['Verdict']}\n\n"
                    f"{analysis}\n\n"
                    f"**{len(strong)} Strong Fit** · **{len(good)} Good Fit** out of {len(df)} screened. "
                    f"Head to Outreach to contact them."
                )
                st.session_state.chat_history.append({"role": "assistant", "content": reply})

            elif is_cand and st.session_state.results_df is None:
                reply = "No screening data yet. Run a screening first — go to **Screen** in the nav."
                st.session_state.chat_history.append({"role": "assistant", "content": reply})

            elif is_screen:
                reply = "Going to Screen Resumes now."
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
                persist_chat(st.session_state.chat_history)
                go("screen")

            elif is_outreach:
                if st.session_state.results_df is None:
                    reply = "Run a screening first, then I can help you reach out to candidates."
                    st.session_state.chat_history.append({"role": "assistant", "content": reply})
                else:
                    reply = "Going to Outreach now."
                    st.session_state.chat_history.append({"role": "assistant", "content": reply})
                    persist_chat(st.session_state.chat_history)
                    go("outreach")

            else:
                ctx_parts = []
                if st.session_state.results_df is not None:
                    df = st.session_state.results_df
                    top3 = df.head(3)[["Name","Final Score","Verdict","Experience","Reason"]].to_dict("records")
                    ctx_parts.append(f"Last screening: {len(df)} candidates for {st.session_state.role_detected}. Top 3: {top3}")

                system = """You are Joy — a sharp, witty AI recruitment assistant for Seven Hiring.
Answer hiring questions with expertise and personality. Be specific, actionable, concise.
Max 3 sentences unless a list is genuinely useful. Never say you can't do something."""

                with st.spinner("Joy is thinking..."):
                    reply = cached_gpt_answer(system, user_msg, "\n".join(ctx_parts))
                st.session_state.chat_history.append({"role": "assistant", "content": reply})

            persist_chat(st.session_state.chat_history)
            st.rerun()



# ═════════════════════════════════════════════════════════════════
# SCREEN RESUMES
# ═════════════════════════════════════════════════════════════════
elif page == "screen":


    st.markdown("## Screen Resumes")
    st.markdown('<p style="color:#555;font-size:0.88rem;margin-bottom:1.5rem">Upload a JD and resumes. Joy ranks and scores every candidate.</p>', unsafe_allow_html=True)

    # ── JD INPUT ──
    section_label("Job Description")
    prefilled = st.session_state.pop("prefilled_jd", "") if "prefilled_jd" in st.session_state else ""
    jd_text = st.text_area("Paste JD", height=160,
                            value=prefilled,
                            placeholder="Paste the full job description here...",
                            label_visibility="collapsed")
    jd_file = st.file_uploader("Or upload JD (PDF / DOCX / TXT)", type=["pdf","docx","txt"])
    if jd_file:
        jd_text = read_file(jd_file)
        st.success(f"Loaded: {jd_file.name}")

    # ── OPTIONS ──
    section_label("Options")
    o1, o2 = st.columns(2)
    with o1:
        extra_kw      = st.text_input("Extra Keywords", placeholder="e.g. HPLC, CIPAC, SAP, GMP")
        role_override = st.text_input("Role Override", placeholder="Leave blank to auto-detect")
    with o2:
        persona = st.text_input("Screening Persona", placeholder="e.g. Experienced field sales manager")

    # ── RESUMES ──
    section_label("Resumes")
    files = st.file_uploader("Upload resumes (PDF or DOCX)", type=["pdf","docx"], accept_multiple_files=True, label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Run Screening", use_container_width=False):
        if not jd_text.strip() or not files:
            st.error("Please provide both a JD and at least one resume.")
            st.stop()

        extra    = [k.strip().lower() for k in extra_kw.split(",")] if extra_kw.strip() else []
        role     = role_override.strip() or get_role_from_jd(jd_text)
        industry = get_industry_from_jd(jd_text)
        rows     = []
        prog     = st.progress(0)
        stat     = st.empty()

        for i, f in enumerate(files):
            stat.text(f"Screening {f.name}  ({i+1} / {len(files)})")
            txt   = read_file(f)[:2000]
            name  = extract_name(txt)
            email = extract_email(txt)
            phone = extract_phone(txt)
            exp   = extract_experience(txt)
            kw    = score_resume_against_jd(txt, extra)
            gs, verdict, reason = gpt_score_resume(jd_text, txt, persona)
            fs = round((gs * 0.65) + (kw * 0.25) + (min(exp, 10) * 1.5), 2)
            rows.append({
                "Name": name, "Email": email, "Phone": phone,
                "Experience": exp, "Keyword Score": kw,
                "GPT Score": gs, "Final Score": fs,
                "Verdict": verdict, "Reason": reason,
                "Suggestions": suggest_checks({"Experience": exp, "Keyword Score": kw, "Verdict": verdict})
            })
            prog.progress((i + 1) / len(files))

        stat.empty(); prog.empty()
        df = pd.DataFrame(rows).sort_values("Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Sr.No", range(1, len(df) + 1))
        save_to_db(df.copy(), role, industry, st.session_state.username)
        st.session_state.results_df        = df
        st.session_state.role_detected     = role
        st.session_state.industry_detected = industry
        st.rerun()

    # ── RESULTS ──
    if st.session_state.results_df is not None:
        df   = st.session_state.results_df
        role = st.session_state.role_detected

        st.markdown("---")
        section_label(f"Results — {role}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Screened",   len(df))
        m2.metric("Strong Fit", len(df[df["Verdict"] == "Strong Fit"]))
        m3.metric("Good Fit",   len(df[df["Verdict"] == "Good Fit"]))
        m4.metric("Avg Score",  round(df["Final Score"].mean(), 1))

        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True)

        dl1, dl2 = st.columns([1, 5])
        with dl1:
            st.download_button("Download CSV", df.to_csv(index=False).encode(), "joy_results.csv", "text/csv")
        with dl2:
            if st.button("Go to Outreach →"):
                go("outreach")

        # Joy's take on top candidate
        if len(df) > 0:
            top = df.iloc[0].to_dict()
            st.markdown("<br>", unsafe_allow_html=True)
            section_label(f"Joy's take on {top['Name']}")
            with st.spinner(""):
                analysis = joy_analyze_candidate(top, st.session_state.name)
            joy_bubble(analysis)


# ═════════════════════════════════════════════════════════════════
# WRITE JD
# ═════════════════════════════════════════════════════════════════
elif page == "jd":


    st.markdown("## Write a Job Description")
    st.markdown('<p style="color:#555;font-size:0.88rem;margin-bottom:1.5rem">Tell Joy what you need. She\'ll write a clean, specific JD — no buzzword soup.</p>', unsafe_allow_html=True)

    section_label("Role Details")
    f1, f2 = st.columns(2)
    with f1:
        role      = st.text_input("Role Title *",      value=st.session_state.jd_role, placeholder="e.g. Regional Sales Manager")
        location  = st.text_input("Location",          placeholder="e.g. Pune / Pan India / Remote")
        skills    = st.text_input("Key Skills",        placeholder="e.g. HPLC, GC-MS, distributor mgmt")
    with f2:
        industry  = st.text_input("Industry",          placeholder="e.g. Agrochemicals, Pharma, Technology")
        exp_range = st.text_input("Experience",        placeholder="e.g. 5–10 years")
        company   = st.text_input("Company Context",   placeholder="e.g. Mid-size agrochemical firm, ₹500Cr revenue")

    section_label("Additional Context")
    extra = st.text_area("Anything else Joy should know", height=80, placeholder="Reporting structure, key challenges, team size, travel requirements...", label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Write JD", use_container_width=False):
        if not role.strip():
            st.error("Role title is required.")
        else:
            with st.spinner("Joy is writing..."):
                st.session_state.generated_jd = generate_jd(
                    role=role, industry=industry, location=location,
                    experience_range=exp_range, key_skills=skills,
                    extra_context=extra, company_name=company or "Our client"
                )
            st.session_state.jd_role = role
            st.rerun()

    if st.session_state.generated_jd:
        st.markdown("---")
        section_label("Generated JD — edit freely")
        edited = st.text_area("JD", value=st.session_state.generated_jd, height=480, label_visibility="collapsed")

        a1, a2, a3 = st.columns([1, 2, 2])
        with a1:
            st.download_button(
                "Download .txt",
                data=edited.encode(),
                file_name=f"JD_{role.replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        with a2:
            feedback = st.text_input("Feedback for refinement", placeholder="Make it more focused on field sales...", label_visibility="collapsed")
        with a3:
            if st.button("Refine JD", use_container_width=True):
                if feedback.strip():
                    with st.spinner("Refining..."):
                        st.session_state.generated_jd = refine_jd(edited, feedback)
                    st.rerun()
                else:
                    st.warning("Enter feedback first.")


# ═════════════════════════════════════════════════════════════════
# OUTREACH — Email & Calling
# ═════════════════════════════════════════════════════════════════
elif page == "outreach":


    st.markdown("## Outreach")
    st.markdown('<p style="color:#555;font-size:0.88rem;margin-bottom:1.5rem">Email and call shortlisted candidates directly from Joy.</p>', unsafe_allow_html=True)

    if st.session_state.results_df is None:
        st.info("No screening results yet. Run a screening first.")
        if st.button("Go to Screen Resumes"):
            go("screen")
        st.stop()

    df   = st.session_state.results_df
    role = st.session_state.role_detected

    section_label("Select Candidate")
    selected = st.selectbox("Candidate", df["Name"].tolist(), label_visibility="collapsed")
    row = df[df["Name"] == selected].iloc[0]

    # Candidate info strip
    info_cols = st.columns(4)
    info_cols[0].metric("Final Score", row["Final Score"])
    info_cols[1].metric("Verdict",     row["Verdict"])
    info_cols[2].metric("Experience",  f"{row['Experience']} yrs")
    info_cols[3].metric("GPT Score",   row["GPT Score"])

    st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📬 Email", "📞 Call & SMS"])

    # ── EMAIL TAB ──
    with tab1:
        section_label("Generate & Send Email")

        if st.button("Generate Email with AI", use_container_width=False):
            sender = st.session_state.sender_name or st.session_state.name
            with st.spinner("Writing..."):
                st.session_state.email_draft = gpt_generate_email(selected, role, sender)

        if st.session_state.email_draft:
            draft = st.text_area("Email Draft", value=st.session_state.email_draft, height=220, label_visibility="collapsed")
            e1, e2 = st.columns(2)
            with e1:
                to   = st.text_input("To", value=row["Email"] if row["Email"] != "-" else "", placeholder="candidate@email.com")
            with e2:
                subj = st.text_input("Subject", value=f"Exciting Opportunity — {role}")

            if st.button("Send Email", use_container_width=False):
                if not st.session_state.smtp_email or not st.session_state.smtp_password:
                    st.warning("Add your Gmail and App Password in the sidebar.")
                elif "@" not in to:
                    st.warning("Enter a valid email address.")
                else:
                    with st.spinner("Sending..."):
                        ok, msg = send_email(
                            st.session_state.smtp_email,
                            st.session_state.smtp_password,
                            to, subj, draft
                        )
                    st.success(msg) if ok else st.error(msg)

    # ── CALL & SMS TAB ──
    with tab2:
        section_label("Call or SMS")

        phone_val = str(row.get("Phone", ""))
        phone_val = "" if phone_val in ["-", "nan", "None"] else phone_val
        to_num = st.text_input("Phone Number", value=phone_val, placeholder="+919876543210 or 9876543210")

        cc1, cc2, cc3 = st.columns(3)

        with cc1:
            if st.button("Call Now", use_container_width=True):
                if not (st.session_state.twilio_sid and st.session_state.twilio_token and st.session_state.twilio_from):
                    st.warning("Add Twilio credentials in the sidebar.")
                elif not to_num.strip():
                    st.warning("Enter a phone number.")
                else:
                    fmt = format_phone_for_twilio(to_num.strip())
                    sender = st.session_state.sender_name or st.session_state.name
                    with st.spinner(f"Calling {fmt}..."):
                        ok, res = make_call(
                            st.session_state.twilio_sid,
                            st.session_state.twilio_token,
                            st.session_state.twilio_from,
                            fmt, selected, role, sender, "Seven Hiring"
                        )
                    if ok:
                        st.success(f"Call initiated!")
                        st.session_state.call_log.append({
                            "candidate": selected, "number": fmt,
                            "sid": res, "time": datetime.now().strftime("%I:%M %p")
                        })
                    else:
                        st.error(res)

        with cc2:
            if st.button("Send SMS", use_container_width=True):
                if not (st.session_state.twilio_sid and st.session_state.twilio_token and st.session_state.twilio_from):
                    st.warning("Add Twilio credentials in the sidebar.")
                elif not to_num.strip():
                    st.warning("Enter a phone number.")
                else:
                    fmt    = format_phone_for_twilio(to_num.strip())
                    sender = st.session_state.sender_name or st.session_state.name
                    sms    = f"Hi {selected}, this is {sender} from Seven Hiring. We have an exciting {role} opportunity for you. Please check your email or call us back!"
                    ok, msg = send_sms(
                        st.session_state.twilio_sid,
                        st.session_state.twilio_token,
                        st.session_state.twilio_from,
                        fmt, sms
                    )
                    st.success("SMS sent!") if ok else st.error(msg)

        with cc3:
            if st.button("Preview Call Script", use_container_width=True):
                sender = st.session_state.sender_name or st.session_state.name
                with st.spinner("Writing script..."):
                    st.session_state.call_script = gpt_generate_call_script(selected, role, sender)

        if st.session_state.call_script:
            st.markdown("<br>", unsafe_allow_html=True)
            section_label("Call Script")
            st.text_area("Script", st.session_state.call_script, height=220, label_visibility="collapsed")

        # Call log
        if st.session_state.call_log:
            st.markdown("<br>", unsafe_allow_html=True)
            section_label("Call Log")
            for log in reversed(st.session_state.call_log[-6:]):
                st.markdown(
                    f'<div class="call-log">Called <strong>{log["candidate"]}</strong> · {log["number"]} · {log["time"]}</div>',
                    unsafe_allow_html=True
                )


# ═════════════════════════════════════════════════════════════════
# HISTORY
# ═════════════════════════════════════════════════════════════════
elif page == "history":


    st.markdown("## Screening History")
    st.markdown('<p style="color:#555;font-size:0.88rem;margin-bottom:1.5rem">All past screenings saved to your account.</p>', unsafe_allow_html=True)

    hist = load_history(st.session_state.username)

    if hist.empty:
        st.info("No history yet. Run your first screening to see results here.")
        if st.button("Screen Resumes →"):
            go("screen")
    else:
        s = get_history_stats(st.session_state.username)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Candidates", s["total"])
        m2.metric("Strong Fits",      s["strong"])
        m3.metric("Roles Screened",   len(s["roles"]))

        st.markdown("<br>", unsafe_allow_html=True)
        section_label("Filter")
        roles = ["All"] + list(hist["Role"].unique()) if "Role" in hist.columns else ["All"]
        rf    = st.selectbox("Role", roles, label_visibility="collapsed")
        show  = hist if rf == "All" else hist[hist["Role"] == rf]

        st.dataframe(show, use_container_width=True, hide_index=True)

        h1, h2 = st.columns([1, 5])
        with h1:
            st.download_button("Download", show.to_csv(index=False).encode(), "joy_history.csv", "text/csv", use_container_width=True)
        with h2:
            if st.button("Clear All History", use_container_width=False):
                clear_history(st.session_state.username)
                st.success("History cleared.")
                st.rerun()


# ═════════════════════════════════════════════════════════════════
# SETTINGS
# ═════════════════════════════════════════════════════════════════
elif page == "settings":

    st.markdown("## Settings")
    st.markdown('<p style="color:#555;font-size:0.88rem;margin-bottom:1.5rem">Configure your email and calling credentials.</p>', unsafe_allow_html=True)

    s1, s2 = st.columns(2)

    with s1:
        section_label("Email — Gmail SMTP")
        st.session_state.smtp_email    = st.text_input("Gmail address", value=st.session_state.smtp_email, placeholder="you@gmail.com")
        st.session_state.smtp_password = st.text_input("Gmail App Password", value=st.session_state.smtp_password, type="password", placeholder="16-character app password")
        st.caption("Go to Google Account → Security → App Passwords to generate one.")

        section_label("Your Name")
        st.session_state.sender_name = st.text_input("Name shown in emails and calls", value=st.session_state.sender_name)

    with s2:
        section_label("Calling & SMS — Twilio")
        st.session_state.twilio_sid   = st.text_input("Account SID",   value=st.session_state.twilio_sid,   type="password", placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        st.session_state.twilio_token = st.text_input("Auth Token",    value=st.session_state.twilio_token, type="password", placeholder="Your Twilio auth token")
        st.session_state.twilio_from  = st.text_input("Twilio Number", value=st.session_state.twilio_from,                  placeholder="+1XXXXXXXXXX")
        st.caption("Find your SID and Auth Token at console.twilio.com")

    st.markdown("---")
    section_label("Account")
    st.markdown(f"Logged in as **{st.session_state.name}**")
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Logout", use_container_width=False):
        do_logout()
