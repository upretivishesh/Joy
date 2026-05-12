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
# CSS (unchanged - UI untouched)
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
# USERS + AUTH (unchanged)
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
    "chat": [],           
    "results_df": None, "role_detected": "", "industry_detected": "",
    "generated_jd": "", "jd_role": "",
    "uploads": [],        
    "_cookie_checked": False,
    "show_outreach": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────
# COOKIE RESTORE (unchanged)
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
# LOGIN (unchanged)
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
# HELPERS (unchanged)
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

LINES = [ ... ]  # (same list as before - omitted for brevity, keep your original LINES)

if "greeting" not in st.session_state:
    st.session_state.greeting = random.choice(LINES)

# ─────────────────────────────────────────────────────────────────
# NEW: Semantic Embedding + Fuzzy + Simple Vector Store
# ─────────────────────────────────────────────────────────────────
def get_openai_embedding(text: str):
    """Best semantic embedding using OpenAI (text-embedding-3-small)"""
    try:
        client = OpenAI()
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000]  # safe limit
        )
        return response.data[0].embedding
    except Exception:
        return None

def cosine_similarity(vec1, vec2):
    """Fast cosine similarity"""
    if vec1 is None or vec2 is None:
        return 0.0
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-8)

class SimpleVectorStore:
    """In-memory vector database for this session (scalable to FAISS/Pinecone later)"""
    def __init__(self):
        self.vectors = {}  # id -> (embedding, metadata)

    def add(self, doc_id: str, embedding: list, metadata: dict):
        self.vectors[doc_id] = (embedding, metadata)

    def search(self, query_embedding: list, top_k: int = 10):
        if not query_embedding or not self.vectors:
            return []
        scores = []
        for doc_id, (emb, meta) in self.vectors.items():
            sim = cosine_similarity(query_embedding, emb)
            scores.append((doc_id, sim, meta))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

# ─────────────────────────────────────────────────────────────────
# SIDEBAR (New Chat fixed - unchanged)
# ─────────────────────────────────────────────────────────────────
# ... (keep your exact sidebar code from previous version)

# ─────────────────────────────────────────────────────────────────
# PAGE ROUTER, HISTORY, SETTINGS (unchanged)
# ─────────────────────────────────────────────────────────────────
# ... (keep exactly as in previous full file)

# ── RENDER CHAT, OUTREACH PANEL (unchanged)
# ─────────────────────────────────────────────────────────────────
# ... (keep exactly as before)

# ── INPUT BAR (unchanged)
# ─────────────────────────────────────────────────────────────────

# ── PROCESS INPUT ──
if _ and (msg.strip() or st.session_state.uploads):
    user_msg  = msg.strip()
    files     = st.session_state.uploads
    msg_lower = user_msg.lower()

    # ── SCREENING — files uploaded ──
    if files:
        jd_text = user_msg.strip() if user_msg else ""
        files_texts = [(f.name, read_file(f)[:3200]) for f in files]

        # ── BEST-IN-CLASS JD DETECTION (fuzzy + filename + content score) ──
        jd_candidate = None
        jd_embedding = None
        vector_store = SimpleVectorStore()

        # 1. Fuzzy + exact filename priority (extremely reliable)
        for fname, txt in files_texts:
            if is_likely_jd_by_filename(fname) or any(
                SequenceMatcher(None, fname.lower(), ind).ratio() > 0.75 
                for ind in ["jd", "job description", "job desc", "requirement", "role description"]
            ):
                jd_text = txt
                jd_candidate = fname
                joy(f"✅ **JD auto-detected by filename/fuzzy match**: **{fname}**")
                break

        # 2. Content-based scoring fallback
        if not jd_text:
            scored = [(fname, txt, jd_likelihood_score(txt)) for fname, txt in files_texts]
            scored.sort(key=lambda x: x[2], reverse=True)
            best = scored[0]
            if best[2] >= 40:
                jd_text = best[1]
                jd_candidate = best[0]
                joy(f"✅ **JD auto-detected by semantic content analysis**: **{jd_candidate}**")

        # Separate resumes
        if jd_candidate:
            resume_texts = [(n, t) for n, t in files_texts if n != jd_candidate]
        else:
            resume_texts = files_texts
            if resume_texts:
                joy("📄 No JD detected. All files treated as resumes.\nPaste JD manually for best accuracy.")

        if not resume_texts:
            joy("No resumes found.")
            st.session_state.uploads = []
            st.rerun()

        display = ", ".join([n for n, _ in resume_texts[:3]]) + (f" +{len(resume_texts)-3} more" if len(resume_texts)>3 else "")
        push_user(f"Screen: {display}" + (f" | JD: {jd_candidate}" if jd_candidate else ""))

        with st.spinner(f"Screening {len(resume_texts)} resumes with semantic embeddings..."):
            role     = get_role_from_jd(jd_text) if jd_text else "General Role"
            industry = get_industry_from_jd(jd_text) if jd_text else "General"
            keywords = extract_keywords_from_jd(jd_text) if jd_text else []

            # Compute JD embedding once (semantic foundation)
            if jd_text:
                jd_embedding = get_openai_embedding(jd_text)

            rows = []
            for fname, text in resume_texts:
                name  = extract_name(text, fname)
                email = extract_email(text)
                phone = extract_phone(text)
                exp   = extract_experience(text)
                edu   = extract_education(text)
                skills = extract_skills(text)
                kw    = score_resume_against_jd(text, keywords)

                # GPT score
                gs, verdict, reason = gpt_score_resume(jd_text, text)

                # NEW: Semantic embedding match
                resume_emb = get_openai_embedding(text) if jd_embedding else None
                semantic_score = cosine_similarity(jd_embedding, resume_emb) if jd_embedding and resume_emb else 0.0

                # Store in simple vector DB for future search/scalability
                vector_store.add(
                    doc_id=fname,
                    embedding=resume_emb,
                    metadata={"name": name, "score": semantic_score}
                )

                # Smarter final score (semantic + keyword + GPT + education)
                education_bonus = 12 if any(x in edu.lower() for x in ["b.tech", "m.tech", "b.e", "mba", "master", "bachelor", "phd"]) else 0
                fs = round(
                    (gs * 0.45) + 
                    (kw * 0.20) + 
                    (semantic_score * 25) + 
                    (min(exp, 18) * 1.1) + 
                    education_bonus, 
                    2
                )

                rows.append({
                    "Name": name,
                    "Email": email,
                    "Phone": phone,
                    "Experience": exp,
                    "Education": edu,
                    "Skills": skills,
                    "Keyword Score": kw,
                    "Semantic Score": round(semantic_score * 100, 1),
                    "GPT Score": gs,
                    "Final Score": fs,
                    "Verdict": verdict,
                    "Reason": reason,
                    "Suggestions": suggest_checks({"Experience": exp, "Keyword Score": kw, "Verdict": verdict, "Education": edu})
                })

        df = pd.DataFrame(rows).sort_values("Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Sr.No", range(1, len(df) + 1))

        save_to_db(df.copy(), role, industry, st.session_state.username)
        st.session_state.results_df        = df
        st.session_state.role_detected     = role
        st.session_state.industry_detected = industry
        st.session_state.uploads           = []

        st.session_state.chat.append({"role": "assistant", "content": df.to_json(orient="records"), "type": "results"})
        st.rerun()

    elif user_msg:
        # ... (rest of your original logic for JD generation, outreach, etc. - unchanged)
        # (keep the entire elif user_msg block exactly as in the previous full file)

# ── CLEAR CHAT LINK (unchanged)
# ─────────────────────────────────────────────────────────────────
if st.session_state.chat:
    if st.button("🗑 Clear", key="clr"):
        save_chat_session(st.session_state.username, st.session_state.chat)
        st.session_state.chat = []
        st.session_state.greeting = random.choice(LINES)
        st.rerun()
