import os
from dotenv import load_dotenv
load_dotenv()
import streamlit as st
import pandas as pd
import pdfplumber
from docx import Document
from datetime import datetime
import json, re

from resume_parser import (
    extract_name, extract_email, extract_phone, extract_experience,
    score_resume_against_jd, get_role_from_jd, get_industry_from_jd,
    suggest_checks
)
from gpt_utils import gpt_score_resume, gpt_generate_email, gpt_generate_call_script
from email_utils import send_email
from database import save_to_db, load_history, clear_history, get_history_stats
from joy_ai import get_greeting, route_intent, joy_chat, joy_analyze_candidate
from jd_generator import generate_jd, refine_jd

try:
    from twilio_utils import make_call, format_phone_for_twilio, send_sms
    TWILIO_OK = True
except ImportError:
    TWILIO_OK = False

# ── CONFIG ──────────────────────────────────────────────────────
st.set_page_config(page_title="Joy | AI Recruiter", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Playfair+Display:wght@600&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;}
h1,h2,h3{font-family:'Playfair Display',serif;}
.main{background-color:#F8F7F4;}
.stButton>button{background:#1A1A2E;color:white;border-radius:6px;border:none;padding:.5rem 1.5rem;font-family:'DM Sans',sans-serif;font-weight:500;transition:background .2s;}
.stButton>button:hover{background:#16213E;}
section[data-testid="stSidebar"]{background-color:#1A1A2E;}
section[data-testid="stSidebar"] .stMarkdown,section[data-testid="stSidebar"] label,section[data-testid="stSidebar"] p{color:#CBD5E1!important;}
.joy-bubble{background:linear-gradient(135deg,#1A1A2E,#16213E);color:#E2E8F0;border-radius:16px 16px 16px 4px;padding:14px 18px;font-size:.95rem;line-height:1.6;margin:8px 0 16px;max-width:90%;border-left:3px solid #4F9FD4;}
.call-log{background:#F0FFF4;border:1px solid #86EFAC;border-radius:8px;padding:10px 14px;font-size:.85rem;color:#166534;margin:6px 0;}
</style>
""", unsafe_allow_html=True)

# ── VOICE JS ─────────────────────────────────────────────────────
VOICE_HTML = """
<div id="vstat" style="font-size:.8rem;color:#94A3B8;margin:4px 0 8px">Initialising voice...</div>
<script>
const WAKE = ["hey joy","ok joy","hi joy","joy"];
var recog=null,alive=false,awake=false,timer=null;
function initVoice(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){document.getElementById('vstat').textContent='Voice: use Chrome or Edge.';return;}
  recog=new SR();recog.continuous=true;recog.interimResults=true;recog.lang='en-IN';
  recog.onstart=()=>{alive=true;document.getElementById('vstat').innerHTML='<span style="color:#4ADE80">&#9679; Listening for Hey Joy...</span>';};
  recog.onresult=(e)=>{
    var t='';for(var i=e.resultIndex;i<e.results.length;i++)t+=e.results[i][0].transcript.toLowerCase();
    if(!awake&&WAKE.some(w=>t.includes(w))){
      awake=true;
      document.getElementById('vstat').innerHTML='<span style="color:#FACC15">&#9679; Joy is listening...</span>';
      chime();
      clearTimeout(timer);timer=setTimeout(()=>{awake=false;document.getElementById('vstat').innerHTML='<span style="color:#4ADE80">&#9679; Listening for Hey Joy...</span>';},6000);
    }
    if(awake&&e.results[e.results.length-1].isFinal){
      var cmd=t;WAKE.forEach(w=>{cmd=cmd.replace(w,'');});cmd=cmd.trim();
      if(cmd.length>2){
        awake=false;clearTimeout(timer);
        var inp=window.parent.document.querySelectorAll('[data-testid=stTextInput] input');
        var target=inp[inp.length-1];
        if(target){target.value=cmd;target.dispatchEvent(new Event('input',{bubbles:true}));}
        document.getElementById('vstat').innerHTML='<span style="color:#4ADE80">&#9679; Listening for Hey Joy...</span>';
      }
    }
  };
  recog.onerror=(e)=>{if(e.error!='no-speech')document.getElementById('vstat').textContent='Mic: '+e.error;};
  recog.onend=()=>{if(alive)recog.start();};
  recog.start();
}
function chime(){
  try{var a=new AudioContext(),o=a.createOscillator(),g=a.createGain();o.connect(g);g.connect(a.destination);
  o.type='sine';o.frequency.setValueAtTime(880,a.currentTime);o.frequency.exponentialRampToValueAtTime(1320,a.currentTime+.15);
  g.gain.setValueAtTime(.3,a.currentTime);g.gain.exponentialRampToValueAtTime(.001,a.currentTime+.4);
  o.start();o.stop(a.currentTime+.4);}catch(e){}
}
window.addEventListener('load',()=>setTimeout(initVoice,800));
</script>
"""

# ── USERS ────────────────────────────────────────────────────────
USERS = {
    "vishesh": {"password": "Qwerty@0987", "name": "Vishesh Upreti"},
    "ruhani":  {"password": "Ruhani@$67",  "name": "Ruhani Sukhija"}
}

def check_login(u, p):
    if u in USERS and USERS[u]["password"] == p:
        return True, USERS[u]["name"]
    return False, None

# ── SESSION STATE ────────────────────────────────────────────────
for k, v in {
    "logged_in": False, "user_name": "", "username_key": "",
    "results_df": None, "role_detected": "", "industry_detected": "",
    "smtp_email": "", "smtp_password": "",
    "twilio_sid": "", "twilio_token": "", "twilio_from": "",
    "joy_greeted": False, "chat_history": [],
    "call_log": [], "generated_jd": "", "jd_role": "",
    "email_draft": "", "call_script": ""
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── LOGIN ────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## ✦ Joy")
        st.markdown("##### AI Recruiter — Seven Hiring")
        st.markdown("<br>", unsafe_allow_html=True)
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            ok, name = check_login(u.strip().lower(), p)
            if ok:
                st.session_state.logged_in    = True
                st.session_state.user_name    = name
                st.session_state.username_key = u.strip().lower()
                st.rerun()
            else:
                st.error("Invalid credentials.")
    st.stop()

# ── SIDEBAR ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ✦ Joy")
    st.markdown(f"**{st.session_state.user_name}**")
    st.markdown("---")
    page = st.radio("Navigate", ["Joy Assistant", "Screen Resumes", "Write JD", "History", "Settings"])
    st.markdown("---")
    st.markdown("#### Email (Gmail)")
    st.session_state.smtp_email    = st.text_input("Gmail",        value=st.session_state.smtp_email,    placeholder="you@gmail.com")
    st.session_state.smtp_password = st.text_input("App Password", value=st.session_state.smtp_password, type="password")
    st.markdown("#### Calls (Twilio)")
    st.session_state.twilio_sid   = st.text_input("Account SID",    value=st.session_state.twilio_sid,   type="password")
    st.session_state.twilio_token = st.text_input("Auth Token",     value=st.session_state.twilio_token, type="password")
    st.session_state.twilio_from  = st.text_input("Twilio Number",  value=st.session_state.twilio_from,  placeholder="+1XXXXXXXXXX")
    st.markdown("---")
    if st.button("Logout"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

# ── HELPERS ──────────────────────────────────────────────────────
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

def play_tts(text):
    try:
        from openai import OpenAI
        c = OpenAI()
        r = c.audio.speech.create(model="tts-1", voice="nova", input=text[:400])
        st.audio(r.content, format="audio/mp3", autoplay=True)
    except: pass


# ════════════════════════════════════════════════════════════════
# PAGE: JOY ASSISTANT
# ════════════════════════════════════════════════════════════════
if page == "Joy Assistant":

    if not st.session_state.joy_greeted:
        g = get_greeting(st.session_state.user_name)
        st.session_state.joy_greeted = True
        st.session_state.chat_history.append({"role": "assistant", "content": g["reply"]})

    hr  = datetime.now().hour
    greet = "Good Morning" if hr < 12 else ("Good Afternoon" if hr < 18 else "Good Evening")
    st.title(f"{greet}, {st.session_state.user_name.split()[0]}.")
    st.caption('Say **"Hey Joy"** or type a command. Joy is always listening.')
    st.markdown("---")

    st.components.v1.html(VOICE_HTML, height=50)

    for turn in st.session_state.chat_history[-12:]:
        if turn["role"] == "assistant":
            joy_bubble(turn["content"])
        else:
            st.markdown(f"**You:** {turn['content']}")

    st.markdown("<br>", unsafe_allow_html=True)
    col_i, col_b = st.columns([5, 1])
    with col_i:
        command = st.text_input("Command", placeholder="Screen the resumes / Write a JD for QC Manager / Call Ankit Sharma...", label_visibility="collapsed")
    with col_b:
        go = st.button("Send", use_container_width=True)

    if go and command.strip():
        msg = command.strip()
        st.session_state.chat_history.append({"role": "user", "content": msg})
        ctx = f"Last screening: {len(st.session_state.results_df)} candidates for {st.session_state.role_detected}." if st.session_state.results_df is not None else ""

        with st.spinner("Joy is thinking..."):
            result = route_intent(msg, st.session_state.user_name, ctx)

        reply  = result.get("reply", "On it.")
        intent = result.get("intent", "chat")
        ad     = result.get("action_data", {})

        st.session_state.chat_history.append({"role": "assistant", "content": reply})

        if intent == "write_jd" and ad.get("role"):
            st.session_state.jd_role = ad["role"]

        play_tts(reply)
        st.rerun()

    st.markdown("---")
    st.caption("Quick actions")
    qcols = st.columns(4)
    qs = [
        "Screen the uploaded resumes",
        "Write a JD for Regional Sales Manager in Agrochemicals",
        "Who is the top candidate from last screening?",
        "Help me send outreach emails to shortlisted candidates"
    ]
    labels = ["Screen resumes", "Write a JD", "Top candidate", "Send emails"]
    for i, (lbl, q) in enumerate(zip(labels, qs)):
        with qcols[i]:
            if st.button(lbl, use_container_width=True, key=f"chip_{i}"):
                st.session_state.chat_history.append({"role": "user", "content": q})
                with st.spinner("Joy is thinking..."):
                    result = route_intent(q, st.session_state.user_name)
                reply = result.get("reply", "On it.")
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
                play_tts(reply)
                st.rerun()


# ════════════════════════════════════════════════════════════════
# PAGE: SCREEN RESUMES
# ════════════════════════════════════════════════════════════════
elif page == "Screen Resumes":
    st.title("Screen Resumes")
    st.caption("Upload a JD and resumes. Joy ranks every candidate.")
    st.markdown("---")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Job Description")
        jd_text = st.text_area("Paste JD", height=200, placeholder="Paste the job description here...")
        jd_file = st.file_uploader("Or upload JD", type=["pdf","docx","txt"])
        if jd_file:
            jd_text = read_file(jd_file)
            st.success(f"Loaded: {jd_file.name}")
    with c2:
        st.subheader("Settings")
        extra_kw      = st.text_input("Extra Keywords", placeholder="HPLC, CIPAC, SAP")
        persona       = st.text_input("Persona / Focus", placeholder="e.g. Field sales expert")
        sender_name   = st.text_input("Your Name", value=st.session_state.user_name)
        role_override = st.text_input("Role Override", placeholder="Leave blank to auto-detect")

    files = st.file_uploader("Upload Resumes", type=["pdf","docx"], accept_multiple_files=True)

    if st.button("Screen Resumes"):
        if not jd_text or not files:
            st.error("Need a JD and at least one resume.")
            st.stop()

        extra = [k.strip().lower() for k in extra_kw.split(",")] if extra_kw else []
        role     = role_override.strip() or get_role_from_jd(jd_text)
        industry = get_industry_from_jd(jd_text)
        rows = []
        prog = st.progress(0)
        stat = st.empty()

        for i, f in enumerate(files):
            stat.text(f"Screening {f.name} ({i+1}/{len(files)})...")
            txt = read_file(f)[:2000]
            name  = extract_name(txt);   email = extract_email(txt)
            phone = extract_phone(txt);  exp   = extract_experience(txt)
            kw    = score_resume_against_jd(txt, extra)
            gs, verdict, reason = gpt_score_resume(jd_text, txt, persona)
            fs = round((gs*0.65) + (kw*0.25) + (min(exp,10)*1.5), 2)
            rows.append({
                "Name": name, "Email": email, "Phone": phone,
                "Experience": exp, "Keyword Score": kw,
                "GPT Score": gs, "Final Score": fs,
                "Verdict": verdict, "Reason": reason,
                "Suggestions": suggest_checks({"Experience":exp,"Keyword Score":kw,"Verdict":verdict})
            })
            prog.progress((i+1)/len(files))

        stat.empty(); prog.empty()
        df = pd.DataFrame(rows).sort_values("Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Sr.No", range(1, len(df)+1))
        save_to_db(df.copy(), role, industry, st.session_state.username_key)
        st.session_state.results_df = df
        st.session_state.role_detected = role
        st.session_state.industry_detected = industry

    if st.session_state.results_df is not None:
        df   = st.session_state.results_df
        role = st.session_state.role_detected
        st.markdown("---")
        st.subheader(f"Results — {role}")

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Screened",  len(df))
        m2.metric("Strong",    len(df[df["Verdict"]=="Strong Fit"]))
        m3.metric("Good",      len(df[df["Verdict"]=="Good Fit"]))
        m4.metric("Avg Score", round(df["Final Score"].mean(),1))

        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", df.to_csv(index=False).encode(), "joy_results.csv", "text/csv")

        if len(df) > 0:
            top = df.iloc[0].to_dict()
            with st.expander(f"Joy's take on top candidate — {top['Name']}"):
                joy_bubble(joy_analyze_candidate(top, st.session_state.user_name))

        st.markdown("---")
        st.subheader("Email & Call Actions")
        selected = st.selectbox("Select Candidate", df["Name"].tolist())
        row = df[df["Name"] == selected].iloc[0]

        ec1, ec2 = st.columns(2)

        with ec1:
            st.markdown("#### Email")
            if st.button("Generate Email"):
                with st.spinner("Writing..."):
                    st.session_state.email_draft = gpt_generate_email(selected, role, sender_name)
            if st.session_state.email_draft:
                draft = st.text_area("Draft", value=st.session_state.email_draft, height=180)
                to    = st.text_input("To", value=row["Email"] if row["Email"] != "-" else "")
                subj  = st.text_input("Subject", value=f"Opportunity — {role}")
                if st.button("Send Email"):
                    if not st.session_state.smtp_email or not st.session_state.smtp_password:
                        st.warning("Add Gmail + App Password in sidebar.")
                    elif "@" not in to:
                        st.warning("Valid email needed.")
                    else:
                        ok, msg = send_email(st.session_state.smtp_email, st.session_state.smtp_password, to, subj, draft)
                        st.success(msg) if ok else st.error(msg)

        with ec2:
            st.markdown("#### Call & SMS")
            phone_val = row.get("Phone","")
            phone_val = "" if phone_val == "-" else phone_val
            to_num = st.text_input("Phone Number", value=phone_val, placeholder="+919876543210")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("Call Now", use_container_width=True):
                    if not (st.session_state.twilio_sid and st.session_state.twilio_token and st.session_state.twilio_from):
                        st.warning("Add Twilio credentials in sidebar.")
                    elif not to_num.strip():
                        st.warning("Enter phone number.")
                    else:
                        fmt = format_phone_for_twilio(to_num.strip())
                        with st.spinner(f"Calling {fmt}..."):
                            ok, res = make_call(
                                st.session_state.twilio_sid, st.session_state.twilio_token,
                                st.session_state.twilio_from, fmt,
                                selected, role, sender_name, "Seven Hiring"
                            )
                        if ok:
                            st.success(f"Call initiated! SID: {res[:20]}...")
                            st.session_state.call_log.append({"candidate":selected,"number":fmt,"sid":res,"time":datetime.now().strftime("%I:%M %p")})
                        else:
                            st.error(res)
            with cc2:
                if st.button("Send SMS", use_container_width=True):
                    if not (st.session_state.twilio_sid and st.session_state.twilio_token and st.session_state.twilio_from):
                        st.warning("Add Twilio credentials in sidebar.")
                    elif not to_num.strip():
                        st.warning("Enter phone number.")
                    else:
                        fmt = format_phone_for_twilio(to_num.strip())
                        sms = f"Hi {selected}, this is {sender_name} from Seven Hiring. We have an exciting {role} opportunity. Please check your email or call us back!"
                        ok, msg = send_sms(st.session_state.twilio_sid, st.session_state.twilio_token, st.session_state.twilio_from, fmt, sms)
                        st.success("SMS sent!") if ok else st.error(msg)

            if st.button("Preview Call Script"):
                with st.spinner("Writing..."):
                    st.session_state.call_script = gpt_generate_call_script(selected, role, sender_name)
            if st.session_state.call_script:
                st.text_area("Call Script", st.session_state.call_script, height=200)

        if st.session_state.call_log:
            st.markdown("---")
            st.subheader("Call Log")
            for log in reversed(st.session_state.call_log[-8:]):
                st.markdown(f'<div class="call-log">Called <strong>{log["candidate"]}</strong> at {log["number"]} — {log["time"]}</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# PAGE: WRITE JD
# ════════════════════════════════════════════════════════════════
elif page == "Write JD":
    st.title("Write a Job Description")
    st.caption("Tell Joy what you need. She'll write it.")
    st.markdown("---")

    c1, c2 = st.columns([1.2, 1])
    with c1:
        role      = st.text_input("Role Title",            value=st.session_state.jd_role, placeholder="e.g. Regional Sales Manager")
        industry  = st.text_input("Industry",              placeholder="Agrochemicals, Pharma, Technology...")
        location  = st.text_input("Location",              placeholder="Pune / Pan India / Remote")
        exp_range = st.text_input("Experience",            placeholder="5-10 years")
        skills    = st.text_input("Key Skills",            placeholder="HPLC, GC-MS, distributor management...")
        company   = st.text_input("Company Context",       placeholder="Mid-size agrochemical firm, 500Cr revenue")
        extra     = st.text_area("Extra Context", height=80, placeholder="Any other context for Joy...")
    with c2:
        st.markdown("#### What Joy writes")
        st.markdown("""
- Punchy role overview (no buzzwords)
- Specific key responsibilities
- Required vs preferred skills
- Honest compensation framing
- Company context that attracts the right people

Download the JD or use it directly for screening.
        """)

    if st.button("Write JD"):
        if not role.strip():
            st.error("Give Joy a role title at minimum.")
        else:
            with st.spinner("Joy is writing..."):
                st.session_state.generated_jd = generate_jd(
                    role=role, industry=industry, location=location,
                    experience_range=exp_range, key_skills=skills,
                    extra_context=extra, company_name=company or "Our client"
                )

    if st.session_state.generated_jd:
        st.markdown("---")
        edited = st.text_area("Edit if needed", value=st.session_state.generated_jd, height=500)
        dl1, dl2 = st.columns([1, 3])
        with dl1:
            st.download_button("Download JD", edited.encode(), f"JD_{role.replace(' ','_')}.txt", "text/plain")
        with dl2:
            fb = st.text_input("Changes needed?", placeholder="Make responsibilities more field-sales focused...")
            if st.button("Refine") and fb.strip():
                with st.spinner("Refining..."):
                    st.session_state.generated_jd = refine_jd(edited, fb)
                st.rerun()


# ════════════════════════════════════════════════════════════════
# PAGE: HISTORY
# ════════════════════════════════════════════════════════════════
elif page == "History":
    st.title("Screening History")
    st.markdown("---")
    hist = load_history(st.session_state.username_key)
    if hist.empty:
        st.info("No history yet.")
    else:
        s = get_history_stats(st.session_state.username_key)
        m1,m2,m3 = st.columns(3)
        m1.metric("Total",  s["total"])
        m2.metric("Strong", s["strong"])
        m3.metric("Roles",  len(s["roles"]))
        roles = ["All"] + list(hist["Role"].unique()) if "Role" in hist.columns else ["All"]
        rf    = st.selectbox("Filter by Role", roles)
        show  = hist if rf == "All" else hist[hist["Role"] == rf]
        st.dataframe(show, use_container_width=True, hide_index=True)
        col1, col2 = st.columns([1, 5])
        with col1:
            st.download_button("Download", show.to_csv(index=False).encode(), "joy_history.csv", "text/csv")
        with col2:
            if st.button("Clear History"):
                clear_history(st.session_state.username_key)
                st.success("Cleared.")
                st.rerun()


# ════════════════════════════════════════════════════════════════
# PAGE: SETTINGS
# ════════════════════════════════════════════════════════════════
elif page == "Settings":
    st.title("Settings")
    st.markdown("---")

    st.subheader("Voice — Joy")
    st.markdown("""
Joy listens continuously in the **Joy Assistant** tab.

- Say **"Hey Joy"** → hear a chime → speak your command
- You have 6 seconds after the wake word
- Joy replies in text + voice (OpenAI TTS, nova voice)
- Works in **Chrome** and **Edge**. Safari/Firefox: use text input.

Wake words: `Hey Joy` · `OK Joy` · `Hi Joy` · `Joy`
    """)

    st.subheader("Email (Gmail SMTP)")
    st.markdown("""
1. Enable 2-Step Verification on your Google Account
2. Go to Security → App Passwords → create one for Mail
3. Paste the 16-char password in the sidebar
    """)

    st.subheader("Twilio (Calls + SMS)")
    st.markdown("""
1. Sign up at [twilio.com](https://twilio.com) — trial is free
2. Get a phone number from the dashboard
3. Copy Account SID + Auth Token → paste in sidebar
4. Trial accounts can only call **verified** numbers — upgrade for full access
5. Indian numbers: Joy auto-converts to E.164 format (`+91XXXXXXXXXX`)
    """)

    st.subheader("About Joy v2.0")
    st.markdown("""
**Jarvis Update** — built for Seven Hiring.

Stack: Streamlit · OpenAI GPT-4o-mini · OpenAI TTS (nova) · Web Speech API · Twilio · Gmail SMTP
    """)
