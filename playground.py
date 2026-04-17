import streamlit as st
import pandas as pd
import pdfplumber
from docx import Document
import io
from datetime import datetime
from zoneinfo import ZoneInfo

hour = datetime.now(ZoneInfo("Asia/Kolkata")).hour

from parser import (
    extract_name, extract_email, extract_phone, extract_experience,
    score_resume_against_jd, get_role_from_jd, get_industry_from_jd,
    suggest_checks
)
from gpt_utils import gpt_score_resume, gpt_generate_email, gpt_generate_call_script
from email_utils import send_email, generate_email_template
from database import save_to_db, load_history, clear_history, get_history_stats

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Joy | AI Recruitment Tool",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Playfair+Display:wght@600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

.main {
    background-color: #F8F7F4;
}

h1, h2, h3 {
    font-family: 'Playfair Display', serif;
}

.stButton > button {
    background-color: #1A1A2E;
    color: white;
    border-radius: 6px;
    border: none;
    padding: 0.5rem 1.5rem;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    transition: background 0.2s;
}

.stButton > button:hover {
    background-color: #16213E;
}

.verdict-strong { color: #16a34a; font-weight: 600; }
.verdict-good   { color: #2563eb; font-weight: 600; }
.verdict-weak   { color: #d97706; font-weight: 600; }
.verdict-not    { color: #dc2626; font-weight: 600; }

.score-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
}

.info-card {
    background: white;
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1rem;
    border: 1px solid #E5E5E5;
}

section[data-testid="stSidebar"] {
    background-color: #1A1A2E;
    color: white;
}

section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p {
    color: #CBD5E1 !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
USERS = {
    "vishesh": {"password": "Qwerty@0987", "name": "Vishesh Upreti"},
    "ruhani":  {"password": "Ruhani@$67",  "name": "Ruhani Sukhija"}
}

def check_login(username, password):
    if username in USERS and USERS[username]["password"] == password:
        return True, USERS[username]["name"]
    return False, None


# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
for key, default in {
    "logged_in": False,
    "user_name": "",
    "username_key": "",
    "results_df": None,
    "role_detected": "",
    "industry_detected": "",
    "smtp_email": "",
    "smtp_password": ""
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## ✦ Joy")
        st.markdown("##### AI Recruitment Tool by Seven Hiring")
        st.markdown("<br>", unsafe_allow_html=True)

        username  = st.text_input("Username")
        password  = st.text_input("Password", type="password")

        if st.button("Login", use_container_width=True):
            ok, name = check_login(username.strip().lower(), password)
            if ok:
                st.session_state.logged_in   = True
                st.session_state.user_name   = name
                st.session_state.username_key = username.strip().lower()
                st.rerun()
            else:
                st.error("Invalid credentials. Try again.")
    st.stop()


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### ✦ Joy")
    st.markdown(f"**{st.session_state.user_name}**")
    st.markdown("---")

    page = st.radio("Navigate", ["Screen Resumes", "History", "Settings"])

    st.markdown("---")
    st.markdown("#### Email Settings")
    smtp_email    = st.text_input("Your Gmail", value=st.session_state.smtp_email, placeholder="you@gmail.com")
    smtp_password = st.text_input("App Password", type="password", value=st.session_state.smtp_password, placeholder="Gmail App Password")

    if smtp_email:
        st.session_state.smtp_email = smtp_email
    if smtp_password:
        st.session_state.smtp_password = smtp_password

    st.caption("Use a Gmail App Password, not your main password.")

    st.markdown("---")
    if st.button("Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ─────────────────────────────────────────────
# HELPER: READ FILE
# ─────────────────────────────────────────────
def read_file(file):
    name = file.name.lower()
    if name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    elif name.endswith(".docx"):
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    elif name.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore")
    return ""


# ─────────────────────────────────────────────
# VERDICT COLOR
# ─────────────────────────────────────────────
def verdict_color(verdict):
    v = verdict.lower()
    if "strong" in v: return "verdict-strong"
    if "good"   in v: return "verdict-good"
    if "weak"   in v: return "verdict-weak"
    return "verdict-not"


# ─────────────────────────────────────────────
# PAGE: SCREEN RESUMES
# ─────────────────────────────────────────────
if page == "Screen Resumes":
    hour = datetime.now().hour
    greet = "Good Morning" if hour < 12 else ("Good Afternoon" if hour < 18 else "Good Evening")
    st.title(f"{greet}, {st.session_state.user_name.split()[0]}!")
    st.caption("AI-powered candidate screening by Seven Hiring")
    st.markdown("---")

    col_jd, col_cfg = st.columns([2, 1])

    with col_jd:
        st.subheader("Job Description")
        jd_text = st.text_area("Paste JD here", height=200, placeholder="Paste the full job description...")
        jd_file = st.file_uploader("Or upload JD (PDF / DOCX / TXT)", type=["pdf", "docx", "txt"])
        if jd_file:
            jd_text = read_file(jd_file)
            st.success(f"JD loaded from: {jd_file.name}")

    with col_cfg:
        st.subheader("Settings")
        extra_kw = st.text_input("Extra Keywords", placeholder="e.g. HPLC, GC-MS, CIPAC")
        persona  = st.text_input("Persona / Focus", placeholder="e.g. Analytical chemistry expert")
        sender_name   = st.text_input("Your Name (for emails)", value=st.session_state.user_name)
        role_override = st.text_input("Role Name Override", placeholder="Leave blank to auto-detect")

    st.subheader("Upload Resumes")
    files = st.file_uploader("Upload one or more resumes", type=["pdf", "docx"], accept_multiple_files=True)

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        screen_clicked = st.button("Screen Resumes", use_container_width=True)

    if screen_clicked:
        if not jd_text or not files:
            st.error("Please provide both a JD and at least one resume.")
            st.stop()

        extra_keywords = [k.strip().lower() for k in extra_kw.split(",")] if extra_kw else []
        role     = role_override.strip() if role_override.strip() else get_role_from_jd(jd_text)
        industry = get_industry_from_jd(jd_text)

        rows = []
        progress = st.progress(0)
        status   = st.empty()

        for i, file in enumerate(files):
            status.text(f"Screening {file.name} ({i+1}/{len(files)})...")
            text = read_file(file)[:2000]

            name     = extract_name(text)
            email    = extract_email(text)
            phone    = extract_phone(text)
            exp      = extract_experience(text)
            kw_score = score_resume_against_jd(text, extra_keywords)

            gpt_score, verdict, reason = gpt_score_resume(jd_text, text, persona)

            final_score = round(
                (gpt_score  * 0.65) +
                (kw_score   * 0.25) +
                (min(exp, 10) * 1.5),
                2
            )

            rows.append({
                "Name":          name,
                "Email":         email,
                "Phone":         phone,
                "Experience":    exp,
                "Keyword Score": kw_score,
                "GPT Score":     gpt_score,
                "Final Score":   final_score,
                "Verdict":       verdict,
                "Reason":        reason,
                "Suggestions":   suggest_checks({
                    "Experience": exp,
                    "Keyword Score": kw_score,
                    "Verdict": verdict
                })
            })
            progress.progress((i + 1) / len(files))

        status.empty()
        progress.empty()

        df = pd.DataFrame(rows).sort_values("Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Sr.No", range(1, len(df) + 1))

        # SAVE TO HISTORY (was missing before!)
        save_to_db(df.copy(), role, industry, st.session_state.username_key)

        st.session_state.results_df       = df
        st.session_state.role_detected    = role
        st.session_state.industry_detected = industry

    # ── RESULTS ──
    if st.session_state.results_df is not None:
        df   = st.session_state.results_df
        role = st.session_state.role_detected

        st.markdown("---")
        st.subheader(f"Results — {role}")

        # Quick stats
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Screened",  len(df))
        c2.metric("Strong Fit",      len(df[df["Verdict"] == "Strong Fit"]))
        c3.metric("Good Fit",        len(df[df["Verdict"] == "Good Fit"]))
        c4.metric("Avg Final Score", round(df["Final Score"].mean(), 1))

        st.markdown("<br>", unsafe_allow_html=True)

        # Results table
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Download
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download Results CSV", csv, "joy_results.csv", "text/csv")

        st.markdown("---")
        st.subheader("Email & Call Actions")
        st.caption("Select a candidate below to generate and send outreach.")

        candidate_names = df["Name"].tolist()
        selected_name = st.selectbox("Select Candidate", candidate_names)
        selected_row  = df[df["Name"] == selected_name].iloc[0]

        action_col1, action_col2 = st.columns(2)

        # ── EMAIL ──
        with action_col1:
            st.markdown("#### Email Outreach")

            if st.button("Generate Email"):
                with st.spinner("Writing email..."):
                    email_body = gpt_generate_email(
                        selected_name, role, sender_name,
                        company_name="Seven Hiring"
                    )
                    st.session_state["email_draft"] = email_body

            if "email_draft" in st.session_state:
                email_draft = st.text_area(
                    "Email Draft (edit before sending)",
                    value=st.session_state["email_draft"],
                    height=220,
                    key="email_edit"
                )
                recipient = st.text_input(
                    "Recipient Email",
                    value=selected_row["Email"] if selected_row["Email"] != "-" else ""
                )
                subject = st.text_input("Subject", value=f"Exciting Opportunity — {role}")

                if st.button("Send Email"):
                    if not st.session_state.smtp_email or not st.session_state.smtp_password:
                        st.warning("Add your Gmail and App Password in the sidebar first.")
                    elif not recipient or "@" not in recipient:
                        st.warning("Enter a valid recipient email.")
                    else:
                        with st.spinner("Sending..."):
                            ok, msg = send_email(
                                sender_email=st.session_state.smtp_email,
                                sender_password=st.session_state.smtp_password,
                                recipient_email=recipient,
                                subject=subject,
                                body=email_draft
                            )
                        if ok:
                            st.success(f"Email sent to {recipient}!")
                        else:
                            st.error(msg)

        # ── CALL SCRIPT ──
        with action_col2:
            st.markdown("#### Call Script")

            if st.button("Generate Call Script"):
                with st.spinner("Writing call script..."):
                    script = gpt_generate_call_script(
                        selected_name, role, sender_name,
                        company_name="Seven Hiring"
                    )
                    st.session_state["call_script"] = script

            if "call_script" in st.session_state:
                st.text_area(
                    "Call Script",
                    value=st.session_state["call_script"],
                    height=280,
                    key="call_script_display"
                )

                phone_no = selected_row.get("Phone", "-")
                if phone_no and phone_no != "-":
                    st.info(f"Phone: {phone_no}")
                else:
                    st.caption("No phone number found in resume.")


# ─────────────────────────────────────────────
# PAGE: HISTORY
# ─────────────────────────────────────────────
elif page == "History":
    st.title("Screening History")
    st.caption("All past screenings saved in your account.")
    st.markdown("---")

    hist_df = load_history(st.session_state.username_key)

    if hist_df.empty:
        st.info("No screening history yet. Run your first screening!")
    else:
        stats = get_history_stats(st.session_state.username_key)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Candidates",  stats["total"])
        c2.metric("Strong Fits",       stats["strong"])
        c3.metric("Roles Screened",    len(stats["roles"]))

        st.markdown("<br>", unsafe_allow_html=True)

        # Filter by role
        all_roles = ["All"] + list(hist_df["Role"].unique()) if "Role" in hist_df.columns else ["All"]
        role_filter = st.selectbox("Filter by Role", all_roles)

        display_df = hist_df if role_filter == "All" else hist_df[hist_df["Role"] == role_filter]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        col_dl, col_cl = st.columns([1, 5])
        with col_dl:
            csv = display_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download History", csv, "joy_history.csv", "text/csv")

        with col_cl:
            if st.button("Clear All History"):
                clear_history(st.session_state.username_key)
                st.success("History cleared.")
                st.rerun()


# ─────────────────────────────────────────────
# PAGE: SETTINGS
# ─────────────────────────────────────────────
elif page == "Settings":
    st.title("Settings")
    st.markdown("---")

    st.subheader("Account")
    st.write(f"**Logged in as:** {st.session_state.user_name}")

    st.subheader("Email (Gmail SMTP)")
    st.markdown("""
To send emails directly from Joy:
1. Enable 2-Step Verification on your Google account.
2. Go to **Google Account > Security > App Passwords**.
3. Create an App Password for "Mail".
4. Paste it in the sidebar password field.

Your credentials are used only to send emails and are not stored anywhere.
    """)

    st.subheader("About Joy")
    st.markdown("""
**Joy** is an AI recruitment tool built for Seven Hiring.
- Resume parsing (PDF & DOCX)
- GPT-powered scoring and fit analysis
- Email outreach (generate + send)
- Call script generation
- Screening history per user

Built with Streamlit + OpenAI GPT-4o-mini.
    """)
