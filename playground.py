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
from database import save_to_db, load_history, clear_history, get_history_stats
from joy_ai import get_greeting, joy_analyze_candidate
from jd_generator import generate_jd, refine_jd

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
    initial_sidebar_state="hidden"
)

# ─────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0F0F0F;
    color: #ECECEC;
}

/* Hide streamlit chrome completely */
#MainMenu, footer, header { display: none !important; visibility: hidden !important; }
.block-container { padding: 2rem 2rem 4rem 2rem; max-width: 900px; margin: 0 auto; }

/* Hide sidebar collapse toggle — every selector Streamlit has ever used */
[data-testid="collapsedControl"],
[data-testid="collapsedControl"] *,
[data-testid="baseButton-headerNoPadding"],
section[data-testid="stSidebarCollapsedControl"],
.st-emotion-cache-1dp5vir,
button[aria-label="Open sidebar"],
button[aria-label="Close sidebar"],
button[aria-expanded="false"][data-testid],
header button { display: none !important; width: 0 !important; height: 0 !important; overflow: hidden !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #161616;
    border-right: 1px solid #2A2A2A;
}
section[data-testid="stSidebar"] * { color: #ABABAB !important; font-size: 0.88rem; }
section[data-testid="stSidebar"] h3 { color: #ECECEC !important; font-size: 1rem !important; }

/* Buttons — primary */
.stButton > button {
    background: #1A1A1A;
    color: #ECECEC;
    border: 1px solid #2E2E2E;
    border-radius: 8px;
    padding: 0.5rem 1.2rem;
    font-size: 0.88rem;
    font-weight: 500;
    font-family: 'Inter', sans-serif;
    transition: all 0.15s ease;
    width: 100%;
}
.stButton > button:hover {
    background: #252525;
    border-color: #444;
    color: #fff;
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

/* Joy bubble */
.joy-bubble {
    background: #161616;
    border: 1px solid #2A2A2A;
    border-left: 3px solid #4A9EFF;
    border-radius: 0 10px 10px 10px;
    padding: 14px 18px;
    font-size: 0.9rem;
    line-height: 1.65;
    color: #DCDCDC;
    margin: 6px 0 18px 0;
}

/* User bubble */
.user-bubble {
    background: #1E1E1E;
    border: 1px solid #2E2E2E;
    border-radius: 10px 10px 0 10px;
    padding: 12px 16px;
    font-size: 0.9rem;
    color: #ECECEC;
    margin: 6px 0 6px auto;
    max-width: 80%;
    text-align: right;
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
    font-size: 2rem;
    font-weight: 300;
    color: #ECECEC;
    line-height: 1.3;
    margin-bottom: 4px;
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
# USERS
# ─────────────────────────────────────────────────────────────────
USERS = {
    "vishesh": {"password": "Qwerty@0987", "name": "Vishesh Upreti"},
    "ruhani":  {"password": "Ruhani@$67",  "name": "Ruhani Sukhija"}
}

def check_login(u, p):
    if u in USERS and USERS[u]["password"] == p:
        return True, USERS[u]["name"]
    return False, None

# ─────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────
defaults = {
    "logged_in": False, "user_name": "", "username_key": "",
    "page": "home",
    "results_df": None, "role_detected": "", "industry_detected": "",
    "smtp_email": "", "smtp_password": "",
    "twilio_sid": "", "twilio_token": "", "twilio_from": "",
    "chat_history": [], "call_log": [],
    "generated_jd": "", "jd_role": "",
    "email_draft": "", "call_script": "",
    "sender_name": ""
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

# ─────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown("### ✦ Joy")
        st.markdown('<p style="color:#555;font-size:0.85rem;margin-bottom:1.5rem">AI Recruiter — Seven Hiring</p>', unsafe_allow_html=True)
        u = st.text_input("Username", placeholder="Enter username")
        p = st.text_input("Password", type="password", placeholder="Enter password")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Sign in", use_container_width=True):
            ok, name = check_login(u.strip().lower(), p)
            if ok:
                st.session_state.logged_in    = True
                st.session_state.user_name    = name
                st.session_state.username_key = u.strip().lower()
                st.session_state.sender_name  = name
                st.rerun()
            else:
                st.error("Invalid credentials.")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────
# SIDEBAR — credentials only, no nav
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ✦ Joy")
    st.markdown(f"**{st.session_state.user_name}**")
    st.markdown("---")
    st.markdown("**Email (Gmail)**")
    st.session_state.smtp_email    = st.text_input("Gmail",        value=st.session_state.smtp_email,    placeholder="you@gmail.com",  label_visibility="collapsed")
    st.session_state.smtp_password = st.text_input("App Password", value=st.session_state.smtp_password, type="password",              label_visibility="collapsed", placeholder="Gmail App Password")
    st.caption("Use a Gmail App Password, not your main password.")
    st.markdown("**Calls (Twilio)**")
    st.session_state.twilio_sid   = st.text_input("Account SID",   value=st.session_state.twilio_sid,   type="password", label_visibility="collapsed", placeholder="Twilio Account SID")
    st.session_state.twilio_token = st.text_input("Auth Token",    value=st.session_state.twilio_token, type="password", label_visibility="collapsed", placeholder="Twilio Auth Token")
    st.session_state.twilio_from  = st.text_input("Twilio Number", value=st.session_state.twilio_from,                  label_visibility="collapsed", placeholder="+1XXXXXXXXXX")
    st.markdown("---")
    st.session_state.sender_name = st.text_input("Your name (emails/calls)", value=st.session_state.sender_name)
    st.markdown("---")
    if st.button("← Back to Home"):
        go("home")
    if st.button("Logout"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

# ─────────────────────────────────────────────────────────────────
# PAGE ROUTER
# ─────────────────────────────────────────────────────────────────
page = st.session_state.page

# ═════════════════════════════════════════════════════════════════
# HOME — Claude-style landing
# ═════════════════════════════════════════════════════════════════
if page == "home":

    now   = datetime.now(ZoneInfo("Asia/Kolkata"))
    hour  = now.hour
    greet = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")
    first = st.session_state.user_name.split()[0]

    st.markdown(f'<p class="greeting-title">{greet}, {first}.</p>', unsafe_allow_html=True)
    st.markdown('<p class="greeting-sub">What would you like to do today?</p>', unsafe_allow_html=True)

    # Show last Joy message if any
    if st.session_state.chat_history:
        last = next((t for t in reversed(st.session_state.chat_history) if t["role"] == "assistant"), None)
        if last:
            joy_bubble(last["content"])

    # ── ACTION CARDS ──
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown('<div class="card-btn">', unsafe_allow_html=True)
        if st.button("🔍\n\n**Screen Resumes**\n\nRank candidates against a JD", key="card_screen", use_container_width=True):
            go("screen")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="card-btn">', unsafe_allow_html=True)
        if st.button("✍️\n\n**Write a JD**\n\nGenerate a full job description", key="card_jd", use_container_width=True):
            go("jd")
        st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="card-btn">', unsafe_allow_html=True)
        if st.button("📬\n\n**Outreach**\n\nEmail & call shortlisted candidates", key="card_outreach", use_container_width=True):
            go("outreach")
        st.markdown('</div>', unsafe_allow_html=True)

    with c4:
        st.markdown('<div class="card-btn">', unsafe_allow_html=True)
        if st.button("🕓\n\n**History**\n\nPast screenings & candidates", key="card_history", use_container_width=True):
            go("history")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── ASK JOY ──
    section_label("Ask Joy anything")

    for turn in st.session_state.chat_history[-6:]:
        if turn["role"] == "assistant":
            joy_bubble(turn["content"])
        else:
            user_bubble(turn["content"])

    ci, cb = st.columns([6, 1])
    with ci:
        msg = st.text_input("Ask Joy", placeholder="Who were the top candidates last time? / Draft a JD for a QC Manager...", label_visibility="collapsed")
    with cb:
        if st.button("Send", use_container_width=True):
            if msg.strip():
                from joy_ai import route_intent
                st.session_state.chat_history.append({"role": "user", "content": msg.strip()})
                ctx = f"Last screening had {len(st.session_state.results_df)} candidates for {st.session_state.role_detected}." if st.session_state.results_df is not None else ""
                with st.spinner(""):
                    result = route_intent(msg.strip(), st.session_state.user_name, ctx)
                reply  = result.get("reply", "On it.")
                intent = result.get("intent", "chat")
                ad     = result.get("action_data", {})
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
                if intent == "write_jd" and ad.get("role"):
                    st.session_state.jd_role = ad["role"]
                st.rerun()

    # ── QUICK PROMPTS ──
    section_label("Suggested")
    q1, q2, q3 = st.columns(3)
    prompts = [
        ("Who was the top candidate from last screening?", "Top candidate"),
        ("Write a JD for Regional Sales Manager in Agrochemicals", "Write a JD"),
        ("What should I look for when hiring a QC Manager in pharma?", "Hiring tips"),
    ]
    for col, (prompt, label) in zip([q1, q2, q3], prompts):
        with col:
            if st.button(label, use_container_width=True, key=f"prompt_{label}"):
                from joy_ai import route_intent
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                with st.spinner(""):
                    result = route_intent(prompt, st.session_state.user_name)
                st.session_state.chat_history.append({"role": "assistant", "content": result.get("reply", "On it.")})
                st.rerun()


# ═════════════════════════════════════════════════════════════════
# SCREEN RESUMES
# ═════════════════════════════════════════════════════════════════
elif page == "screen":

    if st.button("← Home"):
        go("home")

    st.markdown("## Screen Resumes")
    st.markdown('<p style="color:#555;font-size:0.88rem;margin-bottom:1.5rem">Upload a JD and resumes. Joy ranks and scores every candidate.</p>', unsafe_allow_html=True)

    # ── JD INPUT ──
    section_label("Job Description")
    jd_text = st.text_area("Paste JD", height=160, placeholder="Paste the full job description here...", label_visibility="collapsed")
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
        save_to_db(df.copy(), role, industry, st.session_state.username_key)
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
                analysis = joy_analyze_candidate(top, st.session_state.user_name)
            joy_bubble(analysis)


# ═════════════════════════════════════════════════════════════════
# WRITE JD
# ═════════════════════════════════════════════════════════════════
elif page == "jd":

    if st.button("← Home"):
        go("home")

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

    if st.button("← Home"):
        go("home")

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
            sender = st.session_state.sender_name or st.session_state.user_name
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
                    sender = st.session_state.sender_name or st.session_state.user_name
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
                    sender = st.session_state.sender_name or st.session_state.user_name
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
                sender = st.session_state.sender_name or st.session_state.user_name
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

    if st.button("← Home"):
        go("home")

    st.markdown("## Screening History")
    st.markdown('<p style="color:#555;font-size:0.88rem;margin-bottom:1.5rem">All past screenings saved to your account.</p>', unsafe_allow_html=True)

    hist = load_history(st.session_state.username_key)

    if hist.empty:
        st.info("No history yet. Run your first screening to see results here.")
        if st.button("Screen Resumes →"):
            go("screen")
    else:
        s = get_history_stats(st.session_state.username_key)
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
                clear_history(st.session_state.username_key)
                st.success("History cleared.")
                st.rerun()
