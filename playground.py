import streamlit as st
import pdfplumber
from docx import Document
import pandas as pd
import re
import warnings
from collections import Counter
import base64

warnings.filterwarnings("ignore")

from parser import (
    extract_jd_keywords,
    score_resume_against_jd,
    get_role_from_jd,
    get_industry_from_jd,
    check_role_match,
    check_industry_match,
    calculate_weighted_score,
)

# ---------- PAGE CONFIG ----------

st.set_page_config(page_title="Joy - Seven Hiring", layout="wide")

# ---------- USER DATABASE ----------

USERS = {
    "gaurika": {"password": "Gaurika@$7", "name": "Gaurika"},
    "yogita": {"password": "Yogita@$7", "name": "Yogita"},
    "vishesh": {"password": "Vishesh@$11", "name": "Vishesh"},
    "nilanjana": {"password": "Nilanjana@$7", "name": "Nilanjana"},
}

# ---------- LOGIN SYSTEM ----------

def check_login(username, password):
    """Verify user credentials."""
    if username in USERS and USERS[username]["password"] == password:
        return True, USERS[username]["name"]
    return False, None

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""

# Show login page if not logged in
if not st.session_state.logged_in:
    # Add custom CSS for login page
    st.markdown("""
    <style>
    .login-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        margin-top: 50px;
    }
    .login-title {
        text-align: center;
        font-size: 3em;
        font-weight: bold;
        margin-bottom: 80px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Centered title
    st.markdown('<div class="login-title">Joy – Resume Screening Tool</div>', unsafe_allow_html=True)
    
    # Login form centered
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### Please log in to continue")
        username = st.text_input("Username", key="username_input")
        password = st.text_input("Password", type="password", key="password_input")
        
        if st.button("Login", type="primary", use_container_width=True):
            is_valid, user_name = check_login(username.lower(), password)
            if is_valid:
                st.session_state.logged_in = True
                st.session_state.user_name = user_name
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    st.stop()


# ---------- FLOATING JOY BOT ----------

st.markdown("""
<style>
@keyframes float {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-10px); }
}

@keyframes blink {
    0%, 90%, 100% { opacity: 1; }
    95% { opacity: 0; }
}

.joy-bot {
    position: fixed;
    bottom: 40px;
    right: 40px;
    width: 90px;
    height: 90px;
    background: #ffffff;
    border-radius: 50%;
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    animation: float 3s ease-in-out infinite;
    cursor: pointer;
    z-index: 99999;
    border: 3px solid #e0e0e0;
    overflow: visible;
}

.joy-bot:hover {
    transform: scale(1.1);
    transition: transform 0.3s ease;
}

.joy-face {
    width: 100%;
    height: 100%;
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}

.joy-eyes {
    display: flex;
    gap: 18px;
    margin-bottom: 8px;
}

.joy-eye {
    width: 12px;
    height: 12px;
    background: #1a1a1a;
    border-radius: 50%;
    animation: blink 4s infinite;
}

.joy-mouth {
    width: 30px;
    height: 15px;
    border: 3px solid #1a1a1a;
    border-top: none;
    border-radius: 0 0 30px 30px;
    margin-top: 2px;
}

.joy-label {
    position: fixed;
    bottom: 140px;
    right: 30px;
    background: white;
    padding: 10px 18px;
    border-radius: 20px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    font-size: 13px;
    font-weight: 500;
    color: #333;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease;
    z-index: 99998;
    white-space: nowrap;
}

.joy-bot:hover ~ .joy-label {
    opacity: 1;
}

section[data-testid="stSidebar"] {
    z-index: 999 !important;
}

.main .block-container {
    z-index: 1 !important;
}
</style>

<div class="joy-bot" title="Joy - AI Resume Screener">
    <div class="joy-face">
        <div class="joy-eyes">
            <div class="joy-eye"></div>
            <div class="joy-eye"></div>
        </div>
        <div class="joy-mouth"></div>
    </div>
</div>
<div class="joy-label">Hi, I am Joy. Just observing.</div>
""", unsafe_allow_html=True)

# ---------- FILE READING ----------

def read_any_fp(uploaded_file):
    """Read text from PDF/DOCX/TXT uploads."""
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".pdf"):
        with pdfplumber.open(uploaded_file) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    elif name.endswith(".docx"):
        doc = Document(uploaded_file)
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        return uploaded_file.read().decode("utf-8", errors="ignore")

# ---------- EXTRACTION FUNCTIONS ----------

def extract_name(text: str, filename: str) -> str:
    """Extract candidate name from resume."""
    lines = text.split("\n")
    
    for line in lines[:5]:
        line = line.strip()
        if not line or len(line) < 3 or len(line) > 50:
            continue
        if re.search(r"resume|cv|curriculum|profile|email|phone|address", line, re.IGNORECASE):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.replace(".", "").isalpha() for w in words):
            return line.title()
    
    name_from_file = re.sub(r"[-_\[\]\d]", " ", filename.replace(".pdf", "").replace(".docx", ""))
    name_from_file = re.sub(r"\s+", " ", name_from_file).strip()
    if name_from_file and len(name_from_file) > 3:
        return name_from_file.title()
    
    return "-"


def extract_email(text: str) -> str:
    """Extract email address from resume."""
    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    matches = re.findall(pattern, text)
    if matches:
        return matches[0].lower()
    return "-"


def extract_mobile(text: str) -> str:
    """Extract Indian mobile number."""
    lines = text.splitlines()

    def _find_in_chunk(chunk: str) -> str:
        patterns = [
            r"(?:\+91[-\s]*)?\d{10}",
            r"(?:\+91[-\s]*)\d{3}[-\s]*\d{3}[-\s]*\d{4}",
        ]
        for pat in patterns:
            m = re.search(pat, chunk)
            if m:
                num = re.sub(r"\D", "", m.group(0))
                if len(num) > 10:
                    num = num[-10:]
                if len(num) == 10:
                    return num
        return ""

    for i, line in enumerate(lines):
        if re.search(r"contact|phone|mobile", line, re.IGNORECASE):
            window = "\n".join(lines[max(0, i - 1): i + 3])
            num = _find_in_chunk(window)
            if num:
                return num

    num = _find_in_chunk(text)
    return num if num else "-"


def extract_experience_years(text: str, filename: str = "") -> str:
    """Extract total years of experience."""
    exp_vals = []

    matches = re.findall(r"(\d+(?:\.\d+)?)\s+Years?", text, flags=re.IGNORECASE)
    for yrs in matches:
        try:
            val = float(yrs)
            if 0 < val < 50:
                exp_vals.append(val)
        except:
            pass

    if filename:
        m = re.search(r"\[(\d+)y[_\-](\d+)m\]", filename)
        if m:
            try:
                y = int(m.group(1))
                mth = int(m.group(2))
                val = y + mth / 12
                if 0 < val < 50:
                    exp_vals.append(val)
            except:
                pass

    total = max(exp_vals) if exp_vals else 0.0
    return f"{total:.1f} Years" if total > 0 else "-"


def extract_education(text: str) -> str:
    """Extract highest education level."""
    text_lower = text.lower()
    
    degrees = {
        "PhD": r"ph\.?d|doctor of philosophy",
        "Master's": r"master|m\.?tech|m\.?sc|mba|m\.?e|m\.?s\b",
        "Bachelor's": r"bachelor|b\.?tech|b\.?sc|b\.?e|b\.?a\b|bca",
        "Diploma": r"diploma|polytechnic",
    }
    
    for degree, pattern in degrees.items():
        if re.search(pattern, text_lower):
            return degree
    
    return "-"


def extract_notice_period(text: str) -> str:
    """Extract notice period if mentioned."""
    text_lower = text.lower()
    
    if re.search(r"immediate|immediately|can join immediately", text_lower):
        return "Immediate"
    
    match = re.search(r"(\d+)\s*(?:days?|weeks?|months?)\s*(?:notice|np)", text_lower)
    if match:
        num = int(match.group(1))
        unit = match.group(0).lower()
        if "week" in unit:
            return f"{num} weeks"
        elif "month" in unit:
            return f"{num} months"
        else:
            return f"{num} days"
    
    if re.search(r"15\s*days|2\s*weeks", text_lower):
        return "15 days"
    if re.search(r"30\s*days|1\s*month", text_lower):
        return "30 days"
    if re.search(r"60\s*days|2\s*months", text_lower):
        return "60 days"
    if re.search(r"90\s*days|3\s*months", text_lower):
        return "90 days"
    
    return "-"


def extract_current_company(text: str) -> str:
    """Extract current company name."""
    lines = text.split("\n")
    
    for i, line in enumerate(lines):
        if re.search(r"current|present|working at", line, re.IGNORECASE):
            for j in range(i, min(i+3, len(lines))):
                company_match = re.search(r"(?:at|with)\s+([A-Z][A-Za-z0-9\s&,\.]+(?:Ltd|Inc|Corp|Pvt|Private|Limited)?)", lines[j])
                if company_match:
                    return company_match.group(1).strip()
    
    for i, line in enumerate(lines):
        if re.search(r"experience|work history|employment", line, re.IGNORECASE):
            for j in range(i+1, min(i+10, len(lines))):
                if re.match(r"[A-Z][A-Za-z0-9\s&,\.]+(?:Ltd|Inc|Corp|Pvt|Private|Limited)", lines[j].strip()):
                    return lines[j].strip()[:50]
    
    return "-"


def detect_gaps(text: str) -> str:
    """Detect employment gaps."""
    years = re.findall(r"\b(19|20)\d{2}\b", text)
    if len(years) < 2:
        return "Unable to detect"
    
    years = sorted([int(y) for y in years])
    gaps = []
    
    for i in range(len(years) - 1):
        diff = years[i+1] - years[i]
        if diff > 2:
            gaps.append(f"{diff}yr gap")
    
    return ", ".join(gaps) if gaps else "No major gaps"


def extract_top_skills(text: str, top_n: int = 5) -> str:
    """Extract top skills/keywords from resume."""
    skill_patterns = r"\b(python|java|javascript|react|node|aws|azure|gcp|sql|docker|kubernetes|" \
                    r"salesforce|sap|excel|powerbi|tableau|agile|scrum|leadership|management|" \
                    r"marketing|sales|finance|hr|operations|analytics|machine learning|ai|" \
                    r"data science|blockchain|devops|testing|qa|automation)\b"
    
    text_lower = text.lower()
    matches = re.findall(skill_patterns, text_lower)
    
    if not matches:
        return "-"
    
    skill_counts = Counter(matches)
    top_skills = [skill.title() for skill, _ in skill_counts.most_common(top_n)]
    
    return ", ".join(top_skills)


def detect_red_flags(text: str, experience_str: str) -> str:
    """Detect potential red flags in resume."""
    flags = []
    
    if len(text) < 500:
        flags.append("Very short resume")
    
    company_mentions = len(re.findall(r"(?:pvt|ltd|inc|corp|limited)", text, re.IGNORECASE))
    if company_mentions > 6:
        flags.append("Frequent job changes")
    
    common_errors = ["experiance", "managment", "experties", "responsibilites"]
    for error in common_errors:
        if error in text.lower():
            flags.append("Spelling errors")
            break
    
    has_email = re.search(r"@", text)
    has_phone = re.search(r"\d{10}", text)
    
    if not has_email:
        flags.append("No email")
    if not has_phone:
        flags.append("No phone")
    
    return ", ".join(flags) if flags else "None"


# ---------- STREAMLIT UI ----------

# ---------- MAIN PAGE HEADER ----------

# Add logout button in top-right corner
st.markdown("""
<style>
.logout-btn {
    position: fixed;
    top: 70px;
    right: 20px;
    z-index: 9999;
}
</style>
""", unsafe_allow_html=True)

# Create logout in sidebar to position it properly
with st.sidebar:
    st.markdown("### User Session")
    st.write(f"**Logged in as:** {st.session_state.user_name}")
    if st.button("🚪 Logout", type="secondary", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_name = ""
        st.rerun()

# Main title
st.title(f"Hi {st.session_state.user_name}! 👋")
st.markdown("### Here to help you with the screening process")

st.markdown("---")

st.markdown(
    "Upload **one JD** (or paste text) and **multiple resumes**. "
    "Joy will perform intelligent screening with role & industry matching."
)

# JD Input
st.subheader("Job Description")

jd_input_method = st.radio(
    "Choose JD input method:",
    ["Upload file (PDF/DOCX/TXT)", "Paste text directly"],
    horizontal=True
)

jd_text = ""

if jd_input_method == "Upload file (PDF/DOCX/TXT)":
    jd_file = st.file_uploader("Upload JD file", type=["pdf", "docx", "txt"], key="jd_file")
    if jd_file:
        jd_text = read_any_fp(jd_file)
        st.success(f"JD loaded from {jd_file.name}")
else:
    jd_text_input = st.text_area(
        "Paste Job Description here:",
        height=250,
        placeholder="Paste your JD text here...",
    )
    if jd_text_input.strip():
        jd_text = jd_text_input
        st.success(f"JD text received ({len(jd_text)} characters)")

# Resume uploads
st.subheader("Resumes")
resume_files = st.file_uploader(
    "Upload Resumes (PDF or DOCX)", 
    type=["pdf", "docx"], 
    accept_multiple_files=True,
    key="resume_files"
)

# Extra keywords
extra_kw = st.text_input("Extra keywords to highlight (comma-separated)")

if st.button("Screen Resumes", type="primary"):
    if not jd_text or not resume_files:
        st.error("Please provide both a JD (file or text) and at least one resume.")
    else:
        with st.spinner("Analyzing JD and screening resumes..."):
            # Detect JD role and industry
            jd_role = get_role_from_jd(jd_text)
            jd_industry = get_industry_from_jd(jd_text)
            jd_keywords = extract_jd_keywords(jd_text)
            
            st.info(f"**JD Analysis:** Role = `{jd_role.title()}` | Industry = `{jd_industry.title()}`")

            extra_list = []
            if extra_kw.strip():
                extra_list = [w.strip().lower() for w in extra_kw.split(",") if w.strip()]

            # Store uploaded files for download links
            if 'resume_file_objects' not in st.session_state:
                st.session_state.resume_file_objects = {}
            
            rows = []
            for uf in resume_files:
                text = read_any_fp(uf)
                resume_name = uf.name
                
                # Store file object
                uf.seek(0)
                st.session_state.resume_file_objects[resume_name] = uf.read()

                name = extract_name(text, resume_name)
                email = extract_email(text)
                mobile = extract_mobile(text)
                experience = extract_experience_years(text, filename=resume_name)
                education = extract_education(text)
                notice_period = extract_notice_period(text)
                current_company = extract_current_company(text)
                gaps = detect_gaps(text)
                top_skills = extract_top_skills(text)
                red_flags = detect_red_flags(text, experience)
                
                # NEW SCORING SYSTEM
                role_match, role_score, role_reason = check_role_match(text, jd_role)
                industry_match, industry_score, industry_reason = check_industry_match(text, jd_industry)
                keyword_match = score_resume_against_jd(text, jd_keywords)
                
                try:
                    exp_float = float(experience.replace(" Years", "").replace("-", "0"))
                except:
                    exp_float = 0.0
                
                final_score = calculate_weighted_score(
                    role_match, role_score,
                    industry_match, industry_score,
                    keyword_match, exp_float
                )
                
                extra_hits = []
                if extra_list:
                    low_text = text.lower()
                    for w in extra_list:
                        if w in low_text:
                            extra_hits.append(w)

                rows.append({
                    "Name": name,
                    "Email": email,
                    "Mobile": mobile,
                    "Experience": experience,
                    "Final Score": final_score,
                    "Role Match": "✓" if role_match else "✗",
                    "Role %": role_score,
                    "Industry Match": "✓" if industry_match else "✗",
                    "Industry %": industry_score,
                    "Keyword %": keyword_match,
                    "Education": education,
                    "Notice Period": notice_period,
                    "Current Company": current_company,
                    "Top Skills": top_skills,
                    "Employment Gaps": gaps,
                    "Red Flags": red_flags,
                    "Extra Keywords": ", ".join(extra_hits) if extra_hits else "-",
                    "Resume File": resume_name,
                })

        df = pd.DataFrame(rows)
        df = df.sort_values(by="Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Rank", range(1, len(df) + 1))

        st.success(f"Screening complete! Processed {len(df)} resumes.")
        
        # Display with clickable resume names
        st.markdown("### Screening Results")
        st.markdown("**Click on resume names below to download**")
        
        # Create download links column
        def make_download_link(filename):
            if filename in st.session_state.resume_file_objects:
                b64 = base64.b64encode(st.session_state.resume_file_objects[filename]).decode()
                return f'<a href="data:application/pdf;base64,{b64}" download="{filename}">{filename}</a>'
            return filename
        
        # Display table
        st.dataframe(df, use_container_width=True, hide_index=True, height=400)
        
        # Download links section
        st.markdown("### Download Individual Resumes")
        for idx, row in df.iterrows():
            filename = row['Resume File']
            col1, col2, col3 = st.columns([2, 2, 6])
            with col1:
                st.write(f"**{row['Name']}**")
            with col2:
                st.write(f"Score: {row['Final Score']}")
            with col3:
                if filename in st.session_state.resume_file_objects:
                    st.download_button(
                        label=f"📄 Download {filename}",
                        data=st.session_state.resume_file_objects[filename],
                        file_name=filename,
                        mime="application/pdf",
                        key=f"download_{idx}"
                    )
        
        # CSV export
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📊 Download Full Report (CSV)",
            data=csv,
            file_name="joy_screening_report.csv",
            mime="text/csv",
        )
        
        # Summary metrics
        st.markdown("### Screening Summary")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Resumes", len(df))
        with col2:
            avg_score = df["Final Score"].mean()
            st.metric("Avg Score", f"{avg_score:.1f}")
        with col3:
            high_match = len(df[df["Final Score"] >= 60])
            st.metric("Strong Matches (≥60)", high_match)
        with col4:
            role_industry_match = len(df[(df["Role Match"] == "✓") & (df["Industry Match"] == "✓")])
            st.metric("Perfect Fit", role_industry_match)
