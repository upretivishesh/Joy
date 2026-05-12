import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import random

# ─────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Joy | AI Recruiter", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

st.html("""
<style>
  [data-testid="collapsedControl"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"], .stDeployButton, #MainMenu, footer, header { display: none !important; }
  .stApp, .main, .block-container { background-color: #000000 !important; }
</style>
""")

# CSS - Hide "Press Enter to submit form"
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Josefin+Slab:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background-color: #000000; color: #ECECEC; }
.block-container { padding: 2.5rem 2rem 4rem 2rem !important; max-width: 780px !important; margin: 0 auto !important; }
[data-testid="stForm"] p, [data-testid="InputInstructions"], .stForm p, p:contains("Press Enter to submit form") {
    display: none !important;
}
.greeting-text { font-size: 2.1rem !important; line-height: 1.2; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# LOGIN (clean)
# ─────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    st.markdown("""<style>section[data-testid="stSidebar"] { display: none !important; } .block-container { max-width: 360px !important; padding-top: 12vh !important; }</style>""", unsafe_allow_html=True)

    st.markdown('<div style="text-align:center;margin-bottom:2rem;"><p style="font-family:\'Josefin Slab\',serif;font-size:2.8rem;font-weight:700;color:#ECECEC;margin:0;">✦ Joy</p></div>', unsafe_allow_html=True)

    with st.form("login_form"):
        email = st.text_input("Gmail / Work Email", placeholder="you@gmail.com")
        app_pass = st.text_input("App Password", type="password", placeholder="16-character app password")
        st.caption("How to create App Password:\nGoogle Account → Security → 2-Step Verification → App passwords → Mail → Generate")
        ok = st.form_submit_button("Sign in", use_container_width=True)

    if ok:
        if email and "@" in email and len(app_pass.strip()) >= 16:
            st.session_state.authenticated = True
            st.session_state.username = email
            st.session_state.name = email.split("@")[0].split(".")[0].title()
            st.rerun()
        else:
            st.error("Please enter a valid email and 16-character App Password.")
    st.stop()

# ─────────────────────────────────────────────────────────────────
# GREETING (better rotation)
# ─────────────────────────────────────────────────────────────────
def get_greeting(name: str) -> str:
    hour = datetime.now(ZoneInfo("Asia/Kolkata")).hour
    if 5 <= hour < 12:
        options = ["Morning Recruit", "Rise & Hunt", "Talent Dawn", "Good Morning Hunt"]
    elif 12 <= hour < 17:
        options = ["Afternoon Wins", "Hiring Mode", "Star Search", "Peak Talent"]
    elif 17 <= hour < 22:
        options = ["Evening Magic", "Night Owls", "Great Hires", "Team Dreams"]
    else:
        options = ["Late Night Wins", "Dream Team", "Midnight Hunt", "Future Loading"]
    return f"{random.choice(options)}, {name}!"

if not st.session_state.get("chat"):
    st.markdown(f"""
    <div style="text-align:center;padding:5vh 0 3vh;">
        <p class="greeting-text" style="font-family:'Josefin Slab',serif;font-size:2.1rem;font-weight:600;color:#ECECEC;line-height:1.2;margin:0;letter-spacing:0.01em;">{get_greeting(st.session_state.name)}</p>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# SIDEBAR (this will now show)
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""<div style="padding:14px 14px 10px;border-bottom:1px solid #1A1A1A;font-family:'Josefin Slab',serif;font-size:0.88rem;font-weight:700;color:#ECECEC;letter-spacing:0.14em;">✦ JOY</div>""", unsafe_allow_html=True)

    if st.button("＋  New Chat", key="new_chat", use_container_width=True):
        st.session_state.chat = []
        st.rerun()

    if st.button("◷  History", key="nav_hist", use_container_width=True):
        st.session_state.page = "history"; st.rerun()
    if st.button("⚙  Settings", key="nav_set", use_container_width=True):
        st.session_state.page = "settings"; st.rerun()

    if st.button("⏻  Logout", key="logout", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ─────────────────────────────────────────────────────────────────
# MAIN INPUT (clean, no Upload/Send buttons)
# ─────────────────────────────────────────────────────────────────
msg = st.text_input("Type role/keywords to screen, ask Joy anything, or write a JD for...", label_visibility="collapsed")

if msg:
    st.session_state.chat.append({"role": "user", "content": msg})
    st.session_state.chat.append({"role": "assistant", "content": "Understood. How can I help with your hiring today?"})
    st.rerun()

# Render chat
for m in st.session_state.get("chat", []):
    if m["role"] == "user":
        st.markdown(f'<div class="user-msg">{m["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="joy-msg">✦ {m["content"]}</div>', unsafe_allow_html=True)
