import streamlit as st
import pandas as pd
import pdfplumber
from docx import Document
from datetime import datetime
from zoneinfo import ZoneInfo
import re, json, random

from resume_parser import (
    extract_name, extract_email, extract_phone, extract_experience,
    score_resume_against_jd, get_role_from_jd, get_industry_from_jd, suggest_checks
)
from gpt_utils import gpt_score_resume
from email_utils import send_bulk_screening_emails, SCREENING_QUESTIONS
from database import (
    save_to_db, load_history, clear_history, get_history_stats,
    log_login, save_chat_session, load_chat_sessions
)
from jd_generator import generate_jd, refine_jd

# ─────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Joy | AI Recruiter",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.html("""
<style>
  [data-testid="collapsedControl"],
  [data-testid="stToolbar"],
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  .stDeployButton,
  #MainMenu, footer, header {
    display: none !important;
    height: 0 !important;
    width: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
  }
  section[data-testid="stSidebar"] {
    transform: none !important;
    visibility: visible !important;
    display: block !important;
    left: 0 !important;
  }
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
    background-color: #0F0F0F;
    color: #ECECEC;
}
#MainMenu, footer, header { display: none !important; }

.block-container {
    padding: 2.5rem 2rem 4rem 2rem !important;
    max-width: 780px !important;
    margin: 0 auto !important;
}

/* Joy text — plain, no box */
.joy-msg {
    font-size: 0.92rem;
    line-height: 1.75;
    color: #C8C8C8;
    padding: 2px 0 14px 0;
}
/* User bubble */
.user-msg {
    background: #1A1A1A;
    border: 1px solid #222;
    border-radius: 14px 14px 2px 14px;
    padding: 9px 14px;
    font-size: 0.88rem;
    color: #888;
    margin: 4px 0 12px auto;
    max-width: 72%;
    text-align: right;
    display: table;
    margin-left: auto;
}
/* Results table */
.result-row {
    display: flex;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid #1A1A1A;
    gap: 12px;
    font-size: 0.85rem;
}
.result-row:last-child { border-bottom: none; }
.verdict-strong { color: #6EBF6E; font-size: 0.75rem; }
.verdict-good   { color: #4A9EFF; font-size: 0.75rem; }
.verdict-weak   { color: #EF9F27; font-size: 0.75rem; }
.verdict-not    { color: #888;    font-size: 0.75rem; }
.score-num { color: #555; font-size: 0.78rem; min-width: 32px; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0A0A0A !important;
    border-right: 1px solid #1A1A1A !important;
    width: 210px !important;
    min-width: 210px !important;
}
section[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }
section[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    border-radius: 5px !important;
    color: #3A3A3A !important;
    font-family: 'Josefin Slab', serif !important;
    font-size: 0.76rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.07em !important;
    text-transform: uppercase !important;
    text-align: left !important;
    padding: 7px 14px !important;
    width: 100% !important;
    white-space: nowrap !important;
    justify-content: flex-start !important;
    box-shadow: none !important;
    min-height: 30px !important;
    height: 30px !important;
    line-height: 1 !important;
    margin: 0 !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #141414 !important;
    color: #ABABAB !important;
}
section[data-testid="stSidebar"] .stButton { margin: 0 !important; padding: 0 !important; }
section[data-testid="stSidebar"] label { display: none !important; }
section[data-testid="stSidebar"] hr { border-color: #1A1A1A !important; margin: 3px 0 !important; }

/* Chat history items */
.hist-btn button {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.68rem !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    color: #2A2A2A !important;
    padding: 3px 14px !important;
    height: 20px !important;
    min-height: 20px !important;
    font-weight: 400 !important;
}
.hist-btn button:hover { color: #666 !important; background: #111 !important; }

/* Input */
.stTextInput > div > div > input {
    background: #141414 !important;
    border: 1px solid #222 !important;
    border-radius: 10px !important;
    color: #ECECEC !important;
    font-size: 0.9rem !important;
    padding: 12px 16px !important;
}
.stTextInput > div > div > input:focus { border-color: #333 !important; box-shadow: none !important; }

/* File uploader — minimal button style */
[data-testid="stFileUploaderDropzone"] {
    background: #141414 !important;
    border: 1px dashed #222 !important;
    border-radius: 8px !important;
    padding: 8px 14px !important;
    min-height: unset !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #333 !important;
}
[data-testid="stFileUploaderDropzone"] > div {
    gap: 6px !important;
}
[data-testid="stFileUploaderDropzone"] p {
    font-size: 0.78rem !important;
    color: #444 !important;
    margin: 0 !important;
}
[data-testid="stFileUploaderDropzone"] small {
    font-size: 0.68rem !important;
    color: #2A2A2A !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: transparent !important;
    border: 1px solid #222 !important;
    border-radius: 6px !important;
    color: #444 !important;
    font-size: 0.75rem !important;
    padding: 3px 10px !important;
    min-height: unset !important;
    height: 26px !important;
}
[data-testid="stFileUploader"] { background: transparent !important; border: none !important; padding: 0 !important; }
[data-testid="stFileUploader"] > label { display: none !important; }

/* Hide form submit */
[data-testid="stForm"] [data-testid="stFormSubmitButton"] { display: none !important; }
[data-testid="InputInstructions"] { display: none !important; }

/* Checkbox */
.stCheckbox { margin: 0 !important; padding: 0 !important; }

/* JD box */
.jd-box {
    background: #111;
    border: 1px solid #1E1E1E;
    border-radius: 10px;
    padding: 16px;
    margin: 8px 0;
}
.jd-box pre {
    font-size: 0.76rem;
    color: #666;
    white-space: pre-wrap;
    line-height: 1.65;
    font-family: 'DM Sans', sans-serif;
    margin: 0;
    max-height: 240px;
    overflow-y: auto;
}
.section-label {
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #333;
    margin: 12px 0 4px;
}

/* Login */
.login-wrap {
    max-width: 360px;
    margin: 14vh auto 0;
}
[data-testid="stFormSubmitButton"] > button {
    background: #ECECEC !important;
    color: #0F0F0F !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    font-family: 'Josefin Slab', serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    font-size: 0.84rem !important;
    width: 100% !important;
    min-height: 42px !important;
    height: auto !important;
    line-height: 1.4 !important;
    white-space: nowrap !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
/* On login page, show the submit button */
.login-form [data-testid="stForm"] [data-testid="stFormSubmitButton"] {
    display: block !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# USERS + AUTH
# ─────────────────────────────────────────────────────────────────
USERS = {
    "vishesh": {"name": "Vishesh Upreti",  "password": "Qwerty@0987"},
    "ruhani":  {"name": "Ruhani Sukhija",  "password": "Ruhani@$67"},
}

def verify_password(u, p):
    return u in USERS and USERS[u]["password"] == p

try:
    from streamlit_cookies_controller import CookieController
    cookie_ctrl = CookieController()
    COOKIES_OK = True
except:
    cookie_ctrl = None
    COOKIES_OK = False

# ─────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────
defaults = {
    "authenticated": False, "username": "", "name": "",
    "smtp_email": "", "smtp_password": "", "sender_name": "",
    "chat": [],           # all messages: {role, content, type}
    "results_df": None, "role_detected": "", "industry_detected": "",
    "generated_jd": "", "jd_role": "",
    "uploads": [],        # currently attached files
    "_cookie_checked": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────
# COOKIE RESTORE
# ─────────────────────────────────────────────────────────────────
if not st.session_state._cookie_checked:
    st.session_state._cookie_checked = True
    if COOKIES_OK:
        try:
            saved = cookie_ctrl.get("joy_user")
            if saved and saved in USERS:
                st.session_state.authenticated = True
                st.session_state.username = saved
                st.session_state.name = USERS[saved]["name"]
                st.session_state.sender_name = USERS[saved]["name"]
        except: pass

def do_login(ukey):
    st.session_state.authenticated = True
    st.session_state.username = ukey
    st.session_state.name = USERS[ukey]["name"]
    st.session_state.sender_name = USERS[ukey]["name"]
    st.session_state.chat = []
    log_login(ukey)
    if COOKIES_OK:
        try: cookie_ctrl.set("joy_user", ukey, max_age=60*60*24*365)
        except: pass

def do_logout():
    if COOKIES_OK:
        try: cookie_ctrl.remove("joy_user")
        except: pass
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

# ─────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────
if not st.session_state.authenticated:
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] { display: none !important; }
    .block-container { max-width: 360px !important; padding-top: 12vh !important; }
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] { display: flex !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-bottom:2rem;">
        <p style="font-family:'Josefin Slab',serif;font-size:2.2rem;font-weight:700;color:#ECECEC;margin:0;letter-spacing:0.06em;">✦ Joy</p>
        <p style="color:#333;font-size:0.82rem;margin-top:6px;">AI Recruiter — Seven Hiring</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        u = st.text_input("Username", placeholder="Enter username")
        p = st.text_input("Password", type="password", placeholder="Enter password")
        ok = st.form_submit_button("Sign in", use_container_width=True)

    if ok:
        if verify_password(u.strip().lower(), p):
            do_login(u.strip().lower())
            st.rerun()
        else:
            st.error("Invalid credentials.")
    st.stop()

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

def joy(text, typ="text"):
    st.session_state.chat.append({"role": "assistant", "content": text, "type": typ})

def push_user(text):
    st.session_state.chat.append({"role": "user", "content": text, "type": "text"})

LINES = [
    "The right hire changes everything.",
    "Great talent doesn't find itself.",
    "Your next star hire is one screen away.",
    "Pipelines don't fill themselves.",
    "Let's find someone brilliant today.",
    "Good people are out there. Let's go get them.",
    "Every great team started with one great hire.",
    "Joy's ready when you are.",
    "The best recruiters don't just hire — they build legacies.",
    "Somewhere out there is your perfect candidate.",
    "Hiring is just matchmaking with better vocabulary.",
    "A bad hire costs more than a missed one.",
    "Behind every great company is a recruiter who didn't settle.",
    "Talent is everywhere. The trick is knowing where to look.",
    "Great hiring is 10% instinct and 90% Joy.",
    "You're not just filling roles. You're building futures.",
    "Résumés don't hire people. Recruiters do.",
    "Find the right person once. Stop hiring forever.",
    "Speed matters. The best candidates have three offers by Friday.",
    "Stop guessing. Start screening.",
    "Not all CVs are created equal. Joy knows the difference.",
    "Your competitors are also hiring today. Move faster.",
    "The best hire you ever made started with a great JD.",
    "Culture fit is real. So is Joy's scoring algorithm.",
]

if "greeting" not in st.session_state:
    st.session_state.greeting = random.choice(LINES)

# ─────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────
initials = "".join(w[0].upper() for w in st.session_state.name.split()[:2])

with st.sidebar:
    st.markdown("""
    <div style="padding:14px 14px 10px;border-bottom:1px solid #1A1A1A;
    font-family:'Josefin Slab',serif;font-size:0.88rem;font-weight:700;
    color:#ECECEC;letter-spacing:0.14em;">✦ JOY</div>
    """, unsafe_allow_html=True)

    if st.button("＋  New Chat", key="new_chat", use_container_width=True):
        if st.session_state.chat:
            preview = next((m["content"][:50] for m in st.session_state.chat if m["role"]=="user"), "Chat")
            save_chat_session(st.session_state.username, st.session_state.chat)
        st.session_state.chat = []
        st.session_state.greeting = random.choice(LINES)
        st.session_state.results_df = None
        st.session_state.generated_jd = ""
        st.session_state.uploads = []
        st.rerun()

    if st.button("◷  History",  key="nav_hist", use_container_width=True):
        st.session_state.page = "history"; st.rerun()
    if st.button("⚙  Settings", key="nav_set",  use_container_width=True):
        st.session_state.page = "settings"; st.rerun()

    past = load_chat_sessions(st.session_state.username)
    if past:
        st.markdown("""<div style="margin:6px 0 2px;padding:4px 14px 0;
        font-size:0.56rem;color:#222;text-transform:uppercase;
        letter-spacing:0.12em;border-top:1px solid #1A1A1A;">Recent</div>""",
        unsafe_allow_html=True)
        for i, s in enumerate(past[:8]):
            st.markdown('<div class="hist-btn">', unsafe_allow_html=True)
            if st.button(s.get("preview","Chat")[:32], key=f"h{i}", use_container_width=True):
                st.session_state.chat = s.get("messages", [])
                st.session_state.page = "main"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="padding:6px 14px;display:flex;align-items:center;gap:8px;">
        <div style="width:22px;height:22px;background:#1A1A1A;border:1px solid #222;
        border-radius:50%;display:flex;align-items:center;justify-content:center;
        font-size:0.55rem;font-weight:600;color:#555;flex-shrink:0;">{initials}</div>
        <div style="font-size:0.72rem;color:#444;white-space:nowrap;overflow:hidden;
        text-overflow:ellipsis;">{st.session_state.name}</div>
    </div>""", unsafe_allow_html=True)
    if st.button("⏻  Logout", key="logout", use_container_width=True):
        do_logout()

# ─────────────────────────────────────────────────────────────────
# PAGE ROUTER
# ─────────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "main"

page = st.session_state.get("page", "main")

# ─────────────────────────────────────────────────────────────────
# HISTORY PAGE
# ─────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# HISTORY PAGE
# ─────────────────────────────────────────────────────────────────
if page == "history":
    st.markdown("## History")
    hist = load_history(st.session_state.username)
    if hist.empty:
        st.info("No screening history yet.")
    else:
        s = get_history_stats(st.session_state.username)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Candidates", s["total"])
        c2.metric("Strong Fits", s["strong"])
        c3.metric("Roles Screened", len(s["roles"]))
        roles = ["All"] + list(hist["Role"].unique()) if "Role" in hist.columns else ["All"]
        rf = st.selectbox("Filter", roles, label_visibility="collapsed")
        show = hist if rf == "All" else hist[hist["Role"] == rf]
        st.dataframe(show, use_container_width=True, hide_index=True)
        col1, col2 = st.columns([1, 5])
        with col1:
            st.download_button("Download", show.to_csv(index=False).encode(), "joy_history.csv", "text/csv", use_container_width=True)
        with col2:
            if st.button("Clear History"):
                clear_history(st.session_state.username)
                st.rerun()

elif page == "settings":
    st.markdown("## Settings")
    st.markdown('<p class="section-label">Gmail — used to send outreach emails</p>', unsafe_allow_html=True)
    st.session_state.smtp_email    = st.text_input("Gmail", value=st.session_state.smtp_email, placeholder="you@gmail.com")
    st.session_state.smtp_password = st.text_input("App Password", value=st.session_state.smtp_password, type="password", placeholder="16-character app password")
    st.caption("Google Account → Security → 2-Step Verification → App Passwords → create one for Mail")
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<p class="section-label">Your Name</p>', unsafe_allow_html=True)
    st.session_state.sender_name = st.text_input("Name on emails", value=st.session_state.sender_name)
    st.markdown("---")
    st.markdown(f"Logged in as **{st.session_state.name}**")
    if st.button("Logout", key="settings_logout"):
        do_logout()

if page not in ("history", "settings"):
    st.session_state.page = "main"

# Greeting when no chat
if not st.session_state.chat:
    st.markdown(f"""
    <div style="text-align:center;padding:5vh 0 3vh;">
        <p style="font-family:'Josefin Slab',serif;font-size:2.5rem;font-weight:600;
        color:#ECECEC;line-height:1.2;margin:0;letter-spacing:0.01em;max-width:580px;
        margin-left:auto;margin-right:auto;">{st.session_state.greeting}</p>
    </div>
    """, unsafe_allow_html=True)

# ── RENDER CHAT ──
for i, msg in enumerate(st.session_state.chat):
    typ = msg.get("type", "text")
    content = msg["content"]

    if msg["role"] == "user":
        st.markdown(f'<div class="user-msg">{content}</div>', unsafe_allow_html=True)

    elif msg["role"] == "assistant":
        if typ == "text":
            st.markdown(f'<div class="joy-msg">✦ &nbsp;{content}</div>', unsafe_allow_html=True)

        elif typ == "results":
            # Inline results table
            df = pd.read_json(content)
            st.markdown(f'<div class="joy-msg">✦ &nbsp;Screened <strong>{len(df)}</strong> candidates for <strong>{st.session_state.role_detected}</strong>. Here\'s the ranking:</div>', unsafe_allow_html=True)

            for _, row in df.iterrows():
                verdict = row.get("Verdict","")
                vc = {"Strong Fit":"verdict-strong","Good Fit":"verdict-good","Weak Fit":"verdict-weak"}.get(verdict,"verdict-not")
                name  = row.get("Name","?")
                score = row.get("Final Score",0)
                exp   = row.get("Experience",0)
                email = row.get("Email","")
                reason = row.get("Reason","")
                st.markdown(f"""
                <div class="result-row">
                    <span style="color:#ECECEC;min-width:140px;font-weight:500;">{name}</span>
                    <span class="{vc}">{verdict}</span>
                    <span class="score-num">{score}</span>
                    <span style="color:#333;font-size:0.75rem;">{exp}y exp</span>
                    <span style="color:#2A2A2A;font-size:0.72rem;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{reason[:60]}</span>
                </div>""", unsafe_allow_html=True)

            # Download
            dl1, dl2 = st.columns([1, 5])
            with dl1:
                st.download_button("⬇ CSV", df.to_csv(index=False).encode(), "results.csv", "text/csv", key=f"dl_{i}")
            with dl2:
                if st.button("Send outreach emails →", key=f"outreach_{i}"):
                    st.session_state.show_outreach = True
                    st.rerun()

        elif typ == "jd":
            role_name = st.session_state.jd_role or "Role"
            st.markdown(f'<div class="joy-msg">✦ &nbsp;Done. Here\'s the JD for <strong>{role_name}</strong>:</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="jd-box"><pre>{content}</pre></div>', unsafe_allow_html=True)
            j1, j2, _ = st.columns([1, 1, 6])
            with j1:
                st.download_button("⬇", content.encode(), f"JD_{role_name}.txt", "text/plain", key=f"jd_dl_{i}", help="Download")
            with j2:
                if st.button("📋", key=f"jd_cp_{i}", help="Copy"):
                    st.toast("JD copied!")

        elif typ == "outreach":
            # Outreach results
            results = json.loads(content)
            sent   = [r for r in results if r["success"]]
            failed = [r for r in results if not r["success"]]
            if sent:
                names = ", ".join(r["name"] for r in sent)
                st.markdown(f'<div class="joy-msg">✦ &nbsp;Sent screening emails to <strong>{len(sent)}</strong> candidate{"s" if len(sent)!=1 else ""}: {names}</div>', unsafe_allow_html=True)
            for r in failed:
                st.markdown(f'<div class="joy-msg" style="color:#774040;">✗ {r["name"]}: {r["message"]}</div>', unsafe_allow_html=True)

# ── OUTREACH PANEL ──
if st.session_state.get("show_outreach") and st.session_state.results_df is not None:
    df   = st.session_state.results_df
    role = st.session_state.role_detected

    st.markdown("---")
    st.markdown('<p class="section-label">Select candidates to invite</p>', unsafe_allow_html=True)

    selected = []
    for _, row in df.iterrows():
        email_val = str(row.get("Email","")).strip()
        has_email = email_val and "@" in email_val and email_val not in ["-","nan","None"]
        verdict   = row.get("Verdict","")
        default   = verdict in ["Strong Fit","Good Fit"]

        c1, c2, c3, c4 = st.columns([0.4, 2.5, 1.8, 2.5])
        with c1:
            checked = st.checkbox("", key=f"sel_{row['Sr.No']}", value=default, label_visibility="collapsed")
        with c2:
            st.markdown(f"<p style='margin:5px 0;font-size:0.85rem;'>{row['Name']}</p>", unsafe_allow_html=True)
        with c3:
            color = {"Strong Fit":"#6EBF6E","Good Fit":"#4A9EFF","Weak Fit":"#EF9F27"}.get(verdict,"#555")
            st.markdown(f"<p style='margin:5px 0;font-size:0.75rem;color:{color};'>{verdict}</p>", unsafe_allow_html=True)
        with c4:
            if has_email:
                st.markdown(f"<p style='margin:5px 0;font-size:0.72rem;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{email_val}</p>", unsafe_allow_html=True)
            else:
                new_email = st.text_input("Email", placeholder="Enter email", key=f"em_{row['Sr.No']}", label_visibility="collapsed")
                if new_email.strip(): email_val = new_email.strip()

        if checked:
            selected.append({"name": row["Name"], "email": email_val})

    extra = st.text_input("Add a note to the email (optional)", placeholder="e.g. Budget ₹25-30L, Pune location, hybrid", label_visibility="visible")

    no_email = [c["name"] for c in selected if not c.get("email") or "@" not in str(c.get("email",""))]
    send_ok = len(selected) > 0 and len(no_email) == 0

    if no_email:
        st.warning(f"Missing email: {', '.join(no_email)}")

    col_send, col_cancel, _ = st.columns([2, 1, 5])
    with col_send:
        if st.button(f"Send to {len(selected)} →", disabled=not send_ok, use_container_width=True):
            if not st.session_state.smtp_email or not st.session_state.smtp_password:
                st.error("Add Gmail credentials in Settings.")
            else:
                with st.spinner(f"Sending {len(selected)} emails..."):
                    results = send_bulk_screening_emails(
                        sender_email=st.session_state.smtp_email,
                        sender_password=st.session_state.smtp_password,
                        candidates=selected,
                        role=role,
                        sender_name=st.session_state.sender_name or st.session_state.name,
                        extra_note=extra.strip()
                    )
                push_user(f"Send outreach to {len(selected)} candidates")
                st.session_state.chat.append({"role":"assistant","content":json.dumps(results),"type":"outreach"})
                st.session_state.show_outreach = False
                st.rerun()
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.session_state.show_outreach = False
            st.rerun()

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── INPUT BAR ──
uploaded_files = st.file_uploader(
    "Attach resumes",
    type=["pdf","docx","txt"],
    accept_multiple_files=True,
    label_visibility="collapsed"
)
if uploaded_files:
    st.session_state.uploads = list(uploaded_files)
    names = ", ".join(f.name for f in uploaded_files)
    st.markdown(f'<p style="font-size:0.72rem;color:#333;margin:2px 0 4px;">📄 {names}</p>', unsafe_allow_html=True)

with st.form(key="chat_form", clear_on_submit=True):
    msg = st.text_input(
        "Message",
        placeholder="Type role/keywords to screen, ask Joy anything, or write a JD for...",
        label_visibility="collapsed"
    )
    _ = st.form_submit_button("Send")

# ── PROCESS INPUT ──
if _ and (msg.strip() or st.session_state.uploads):
    user_msg  = msg.strip()
    files     = st.session_state.uploads
    msg_lower = user_msg.lower()

    # ── SCREENING — files uploaded ──
    if files:
        jd_text = user_msg or st.session_state.get("prefilled_jd","")

        if not jd_text:
            push_user(f"Uploaded: {', '.join(f.name for f in files)}")
            joy("Got the files. Tell me the role or paste the JD and I'll screen them right away.")
            st.session_state.uploads = []
            st.rerun()

        display = ", ".join(f.name for f in files[:3]) + (f" +{len(files)-3} more" if len(files)>3 else "")
        push_user(f"Screen: {display}" + (f" | {user_msg}" if user_msg else ""))

        with st.spinner(f"Screening {len(files)} resume(s)..."):
            role     = get_role_from_jd(jd_text) if jd_text else "General Role"
            industry = get_industry_from_jd(jd_text) if jd_text else "General"
            rows     = []
            for f in files:
                text  = read_file(f)[:2500]
                name  = extract_name(text)
                email = extract_email(text)
                phone = extract_phone(text)
                exp   = extract_experience(text)
                kw    = score_resume_against_jd(text, [])
                gs, verdict, reason = gpt_score_resume(jd_text, text)
                fs    = round((gs*0.65)+(kw*0.25)+(min(exp,10)*1.5), 2)
                rows.append({
                    "Name":name,"Email":email,"Phone":phone,
                    "Experience":exp,"Keyword Score":kw,
                    "GPT Score":gs,"Final Score":fs,
                    "Verdict":verdict,"Reason":reason,
                    "Suggestions":suggest_checks({"Experience":exp,"Keyword Score":kw,"Verdict":verdict})
                })

        df = pd.DataFrame(rows).sort_values("Final Score",ascending=False).reset_index(drop=True)
        df.insert(0,"Sr.No",range(1,len(df)+1))
        save_to_db(df.copy(), role, industry, st.session_state.username)
        st.session_state.results_df        = df
        st.session_state.role_detected     = role
        st.session_state.industry_detected = industry
        st.session_state.uploads           = []

        st.session_state.chat.append({"role":"assistant","content":df.to_json(),"type":"results"})
        st.rerun()

    elif user_msg:
        push_user(user_msg)

        jd_triggers       = ["jd","job description","write a jd","form a jd","create a jd","draft a jd","jd for","write jd"]
        cand_triggers     = ["top candidate","best candidate","who should","shortlist","strongest","highest score","recommend","who to hire","best fit","top pick"]
        outreach_triggers = ["email","outreach","reach out","send email","invite"]
        history_triggers  = ["history","past screening","previous"]
        settings_triggers = ["settings","gmail","configure","setup email"]

        is_jd       = any(t in msg_lower for t in jd_triggers)
        is_cand     = any(t in msg_lower for t in cand_triggers)
        is_outreach = any(t in msg_lower for t in outreach_triggers)
        is_history  = any(t in msg_lower for t in history_triggers)
        is_settings = any(t in msg_lower for t in settings_triggers)

        if is_jd:
            with st.spinner("Writing JD..."):
                from openai import OpenAI
                import re as _re
                client = OpenAI()
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role":"user","content":f"Extract role, industry, location, experience from: '{user_msg}'. JSON only: {{\"role\":\"\",\"industry\":\"\",\"location\":\"\",\"experience\":\"\"}}"}],
                    max_tokens=150
                )
                raw = _re.sub(r"```json|```","",res.choices[0].message.content).strip()
                try: params = json.loads(raw)
                except: params = {"role":user_msg,"industry":"","location":"","experience":""}
                jd = generate_jd(
                    role=params.get("role",user_msg), industry=params.get("industry",""),
                    location=params.get("location",""), experience_range=params.get("experience",""),
                    company_name="Our client"
                )
                st.session_state.generated_jd = jd
                st.session_state.jd_role = params.get("role","")
            st.session_state.chat.append({"role":"assistant","content":jd,"type":"jd"})

        elif is_outreach:
            if st.session_state.results_df is not None:
                joy("Sure — select the candidates you want to invite below.")
                st.session_state.show_outreach = True
            else:
                joy("Screen some resumes first — attach them above and tell me the role.")

        elif is_history:
            joy("Opening your screening history.")
            st.session_state.page = "history"

        elif is_settings:
            joy("Opening settings.")
            st.session_state.page = "settings"

        elif is_cand and st.session_state.results_df is not None:
            df  = st.session_state.results_df
            top = df.iloc[0]
            strong = len(df[df["Verdict"]=="Strong Fit"])
            good   = len(df[df["Verdict"]=="Good Fit"])
            joy(f"**{top['Name']}** is your top pick — {top['Final Score']} score, {top['Verdict']}. {top['Reason']} You have {strong} Strong and {good} Good fits in total.")

        elif is_cand:
            joy("No screening data yet. Attach resumes above and tell me the role.")

        else:
            # General GPT answer
            with st.spinner(""):
                from openai import OpenAI
                client = OpenAI()
                ctx = ""
                if st.session_state.results_df is not None:
                    df   = st.session_state.results_df
                    top3 = df.head(3)[["Name","Final Score","Verdict","Reason"]].to_dict("records")
                    ctx  = f"Last screening: {len(df)} candidates for {st.session_state.role_detected}. Top 3: {top3}"
                msgs = [{"role":"system","content":"You are Joy — sharp, witty AI recruitment assistant for Seven Hiring. Specific, actionable, max 3 sentences."}]
                if ctx: msgs.append({"role":"system","content":ctx})
                msgs.append({"role":"user","content":user_msg})
                res = client.chat.completions.create(model="gpt-4o-mini",messages=msgs,max_tokens=300,temperature=0.8)
                joy(res.choices[0].message.content.strip())

        st.rerun()

# ── CLEAR CHAT LINK ──
if st.session_state.chat:
    if st.button("🗑 Clear", key="clr"):
        save_chat_session(st.session_state.username, st.session_state.chat)
        st.session_state.chat = []
        st.session_state.greeting = random.choice(LINES)
        st.rerun()
