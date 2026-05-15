import json
import os
import re
import smtplib
from collections import Counter
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from docx import Document
except Exception:
    Document = None


APP_NAME = "Joy"
DEFAULT_COMPANY = "Seven Hiring"
DATA_DIR = Path(".joy_data")

KNOWN_SKILLS = [
    "python", "java", "javascript", "typescript", "react", "node", "django",
    "flask", "fastapi", "sql", "postgresql", "mysql", "mongodb", "aws",
    "azure", "gcp", "docker", "kubernetes", "terraform", "linux", "git",
    "machine learning", "data analysis", "excel", "power bi", "tableau",
    "salesforce", "sap", "erp", "crm", "leadership", "communication",
    "project management", "agrochemical", "pharma", "fmcg", "sales",
    "distribution", "channel sales", "key account", "hplc", "gc-ms", "gmp",
    "qa", "qc", "production", "manufacturing", "finance", "accounting",
]

STOP_WORDS = {
    "about", "above", "after", "again", "against", "also", "among", "and",
    "any", "are", "based", "been", "being", "best", "between", "both",
    "business", "candidate", "candidates", "client", "company", "description",
    "detail", "details", "development", "each", "etc", "experience",
    "experienced", "for", "from", "good", "have", "hiring", "including",
    "india", "into", "job", "knowledge", "like", "looking", "management",
    "manager", "must", "need", "needs", "our", "over", "preferred", "profile",
    "required", "requirements", "responsibilities", "role", "should", "skill",
    "skills", "strong", "team", "that", "the", "their", "this", "through",
    "with", "work", "working", "years", "you", "your",
}

DEFAULT_QUESTIONS = [
    "Current CTC",
    "Expected CTC",
    "Notice period / earliest joining date",
    "Current location",
    "Preferred work location",
    "Total experience and relevant experience",
    "Reason for job change",
    "Current company and designation",
    "Any offer in hand",
    "Two suitable slots for a 15-minute discussion",
]


def init_state() -> None:
    defaults = {
        "results_df": pd.DataFrame(),
        "last_role": "",
        "last_jd": "",
        "last_keywords": [],
        "email_results": [],
        "questions_text": "\n".join(DEFAULT_QUESTIONS),
        "sender_email": get_secret("GMAIL_ADDRESS"),
        "sender_password": get_secret("GMAIL_APP_PASSWORD"),
        "sender_name": "",
        "company_name": DEFAULT_COMPANY,
        "openai_api_key": get_secret("OPENAI_API_KEY"),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return value or os.getenv(name, default)


def normalize_whitespace(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_filename_part(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", value or "user")
    return clean.strip("_")[:80] or "user"


def history_path(user_key: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"history_{safe_filename_part(user_key)}.csv"


def read_uploaded_file(upload) -> tuple[str, str]:
    name = upload.name.lower()
    data = upload.getvalue()

    try:
        if name.endswith(".pdf"):
            if pdfplumber is None:
                return "", "pdfplumber is not installed."
            with pdfplumber.open(BytesIO(data)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return text.strip(), ""

        if name.endswith(".docx"):
            if Document is None:
                return "", "python-docx is not installed."
            doc = Document(BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text.strip(), ""

        if name.endswith(".txt"):
            return data.decode("utf-8", errors="ignore").strip(), ""

        return "", "Unsupported file type."
    except Exception as exc:
        return "", f"Could not read file: {exc}"


def extract_email(text: str) -> str:
    match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    return match.group(0) if match else ""


def extract_phone(text: str) -> str:
    patterns = [
        r"(?:\+91[-.\s]?)?[6-9]\d{9}",
        r"\+?\d{1,4}[-.\s]?\(?\d{2,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,6}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip()
    return ""


def extract_name(text: str, filename: str = "") -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bad_words = {"resume", "curriculum", "vitae", "profile", "email", "phone"}

    for line in lines[:8]:
        clean = re.sub(r"[^A-Za-z .'-]", " ", line)
        clean = normalize_whitespace(clean)
        if not clean:
            continue
        lower = clean.lower()
        words = clean.split()
        if 2 <= len(words) <= 4 and not any(word in lower for word in bad_words):
            if all(w[:1].isupper() for w in words if w):
                return clean

    if filename:
        stem = re.sub(r"\.(pdf|docx|doc|txt)$", "", filename, flags=re.I)
        stem = re.sub(r"[_\-.]+", " ", stem)
        stem = re.sub(r"resume|cv|profile", "", stem, flags=re.I)
        stem = normalize_whitespace(re.sub(r"[^A-Za-z ]", " ", stem))
        if len(stem.split()) >= 2:
            return stem.title()

    return "Unknown Candidate"


def extract_experience(text: str) -> float:
    patterns = [
        r"(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:total\s*)?experience",
        r"experience\s*[:\-]?\s*(\d{1,2}(?:\.\d)?)",
        r"(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return 0.0
    return 0.0


def extract_skills(text: str) -> list[str]:
    lower = text.lower()
    return sorted({skill for skill in KNOWN_SKILLS if skill in lower})


def extract_role_from_jd(jd_text: str, fallback: str = "") -> str:
    if fallback.strip():
        return fallback.strip()

    patterns = [
        r"(?:role|position|title|hiring for)\s*[:\-]\s*([A-Za-z][A-Za-z /&+-]{2,80})",
        r"job description\s*(?:for|:|-)\s*([A-Za-z][A-Za-z /&+-]{2,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, jd_text, flags=re.I)
        if match:
            role = normalize_whitespace(match.group(1))
            role = re.split(r"\b(location|experience|about|reports)\b", role, flags=re.I)[0]
            return role.strip(" -:").title()

    return "Open Role"


def parse_min_experience(jd_text: str) -> float:
    patterns = [
        r"(\d{1,2})\s*[-+]\s*\d{0,2}\s*(?:years?|yrs?)",
        r"minimum\s*(?:of)?\s*(\d{1,2})\s*(?:years?|yrs?)",
        r"at least\s*(\d{1,2})\s*(?:years?|yrs?)",
        r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of)?\s*experience",
    ]
    for pattern in patterns:
        match = re.search(pattern, jd_text, flags=re.I)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return 0.0
    return 0.0


def extract_keywords(text: str, extra_keywords: str = "", limit: int = 35) -> list[str]:
    text = text or ""
    configured = [kw.strip().lower() for kw in extra_keywords.split(",") if kw.strip()]
    skill_hits = [skill for skill in KNOWN_SKILLS if skill in text.lower()]

    words = re.findall(r"\b[a-zA-Z][a-zA-Z+#.-]{2,}\b", text.lower())
    words = [w.strip(".-") for w in words if w not in STOP_WORDS and len(w) >= 3]
    common = [word for word, _ in Counter(words).most_common(limit)]

    keywords = []
    for item in configured + skill_hits + common:
        if item and item not in keywords and item not in STOP_WORDS:
            keywords.append(item)
    return keywords[:limit]


def keyword_match_score(resume_text: str, keywords: list[str]) -> tuple[int, list[str], list[str]]:
    if not keywords:
        return 50, [], []

    lower = resume_text.lower()
    matched = [kw for kw in keywords if kw.lower() in lower]
    missing = [kw for kw in keywords if kw.lower() not in lower]
    score = round((len(matched) / len(keywords)) * 100)
    return int(score), matched, missing


def experience_score(candidate_years: float, required_years: float) -> int:
    if required_years <= 0:
        return 70 if candidate_years == 0 else 85
    if candidate_years >= required_years:
        return 100
    return int(max(0, min(100, (candidate_years / required_years) * 100)))


def contact_score(email: str, phone: str) -> int:
    score = 0
    if email:
        score += 60
    if phone:
        score += 40
    return score


def ai_score_resume(
    jd_text: str,
    resume_text: str,
    role: str,
    api_key: str,
    model: str,
) -> tuple[int | None, str]:
    if not api_key:
        return None, ""

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = f"""
Score the resume against the role and job description.
Return JSON only:
{{"score": 0, "reason": ""}}

Role: {role}

Job description:
{jd_text[:2500]}

Resume:
{resume_text[:3500]}
"""
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict recruiter. Reward direct evidence, penalize missing must-haves, and stay concise.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=220,
        )
        raw = response.choices[0].message.content or "{}"
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)
        score = int(float(data.get("score", 0)))
        reason = str(data.get("reason", "")).strip()
        return max(0, min(100, score)), reason
    except Exception as exc:
        return None, f"AI scoring skipped: {exc}"


def make_reason(matched: list[str], missing: list[str], exp: float, min_exp: float) -> str:
    matched_text = ", ".join(matched[:5]) if matched else "few direct keyword matches"
    missing_text = ", ".join(missing[:4]) if missing else "no obvious must-have gaps"
    if min_exp > 0:
        exp_text = f"{exp:g} yrs found vs {min_exp:g}+ yrs expected"
    else:
        exp_text = f"{exp:g} yrs found" if exp else "experience not clearly stated"
    return f"Matched {matched_text}. Missing/unclear: {missing_text}. {exp_text}."


def verdict_from_score(score: float) -> str:
    if score >= 82:
        return "Strong Fit"
    if score >= 68:
        return "Good Fit"
    if score >= 50:
        return "Review"
    return "Low Fit"


def score_resume(
    jd_text: str,
    role: str,
    resume_text: str,
    filename: str,
    keywords: list[str],
    min_exp: float,
    api_key: str,
    model: str,
) -> dict:
    name = extract_name(resume_text, filename)
    email = extract_email(resume_text)
    phone = extract_phone(resume_text)
    exp = extract_experience(resume_text)
    skills = extract_skills(resume_text)

    kw_score, matched, missing = keyword_match_score(resume_text, keywords)
    exp_score = experience_score(exp, min_exp)
    cnt_score = contact_score(email, phone)
    skill_score = min(100, len(skills) * 12)

    heuristic = (kw_score * 0.55) + (exp_score * 0.2) + (skill_score * 0.15) + (cnt_score * 0.1)
    ai_score, ai_reason = ai_score_resume(jd_text, resume_text, role, api_key, model)

    if ai_score is None:
        final_score = round(heuristic, 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp)
        ai_used = False
    else:
        final_score = round((heuristic * 0.45) + (ai_score * 0.55), 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp)
        ai_used = True

    return {
        "Send": verdict_from_score(final_score) in {"Strong Fit", "Good Fit"} and bool(email),
        "Name": name,
        "Email": email,
        "Phone": phone,
        "Experience": exp,
        "Keyword Score": kw_score,
        "Final Score": final_score,
        "Verdict": verdict_from_score(final_score),
        "Matched Keywords": ", ".join(matched[:12]),
        "Missing Keywords": ", ".join(missing[:10]),
        "Skills": ", ".join(skills[:12]),
        "Reason": reason,
        "Source File": filename,
        "AI Used": ai_used,
    }


def save_history(df: pd.DataFrame, role: str, user_key: str) -> None:
    if df.empty:
        return
    path = history_path(user_key)
    batch = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    to_save = df.copy()
    to_save["Role"] = role
    to_save["Screened At"] = batch

    if path.exists():
        old = pd.read_csv(path)
        to_save = pd.concat([old, to_save], ignore_index=True)
    to_save.to_csv(path, index=False)


def load_history(user_key: str) -> pd.DataFrame:
    path = history_path(user_key)
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def clear_history(user_key: str) -> None:
    path = history_path(user_key)
    if path.exists():
        path.unlink()


def questions_from_text(text: str) -> list[str]:
    questions = []
    for line in text.splitlines():
        clean = re.sub(r"^\s*[-*0-9.)]+\s*", "", line).strip()
        if clean:
            questions.append(clean)
    return questions or DEFAULT_QUESTIONS


def first_name(full_name: str) -> str:
    if not full_name or full_name == "Unknown Candidate":
        return "there"
    return full_name.split()[0].strip(",")


def build_email_body(
    candidate: pd.Series,
    role: str,
    sender_name: str,
    company_name: str,
    questions: list[str],
    extra_note: str,
) -> str:
    greeting = first_name(str(candidate.get("Name", "")))
    company = company_name or DEFAULT_COMPANY
    score = candidate.get("Final Score", "")
    verdict = candidate.get("Verdict", "")

    lines = [
        f"Hi {greeting},",
        "",
        f"I reviewed your profile for the {role} role and it looks relevant for the first screening round.",
        "",
    ]

    if extra_note.strip():
        lines.extend([extra_note.strip(), ""])

    lines.extend(
        [
            "To move ahead without a back-and-forth call, please reply with these details:",
            "",
        ]
    )

    for idx, question in enumerate(questions, start=1):
        lines.append(f"{idx}. {question}")

    lines.extend(
        [
            "",
            "Once I have this, I can confirm fit, share the next step, and avoid asking you the same basics again on call.",
            "",
            f"Internal note: screening result {verdict}, score {score}.",
            "",
            "Best regards,",
            sender_name or "Recruitment Team",
            company,
        ]
    )
    return "\n".join(lines)


def send_email(
    sender_email: str,
    sender_password: str,
    sender_name: str,
    recipient_email: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    try:
        msg = EmailMessage()
        msg["From"] = formataddr((sender_name or sender_email, sender_email))
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True, "Sent"
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail rejected the login. Use a Gmail App Password, not your normal password."
    except Exception as exc:
        return False, str(exc)


def send_bulk_emails(
    selected_df: pd.DataFrame,
    role: str,
    sender_email: str,
    sender_password: str,
    sender_name: str,
    company_name: str,
    subject: str,
    questions: list[str],
    extra_note: str,
) -> list[dict]:
    results = []
    for _, candidate in selected_df.iterrows():
        name = str(candidate.get("Name", "Candidate"))
        recipient = str(candidate.get("Email", "")).strip()
        if "@" not in recipient:
            results.append({"Name": name, "Email": recipient, "Success": False, "Message": "Missing email"})
            continue

        body = build_email_body(candidate, role, sender_name, company_name, questions, extra_note)
        ok, message = send_email(sender_email, sender_password, sender_name, recipient, subject, body)
        results.append({"Name": name, "Email": recipient, "Success": ok, "Message": message})
    return results


def render_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #0f1115;
            --panel: #161922;
            --panel-2: #1d2230;
            --text: #edf0f5;
            --muted: #9ca3af;
            --line: #2b3242;
            --accent: #63c7a3;
            --warn: #f5b85d;
            --bad: #ef7a7a;
        }
        .stApp { background: var(--bg); color: var(--text); }
        .block-container { max-width: 1180px; padding-top: 2rem; }
        h1, h2, h3 { letter-spacing: 0 !important; }
        [data-testid="stSidebar"] {
            background: #10131a;
            border-right: 1px solid var(--line);
        }
        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 14px 16px;
        }
        .joy-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
        }
        .muted { color: var(--muted); }
        .small-label {
            color: var(--muted);
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.35rem;
        }
        .success-pill, .warn-pill, .bad-pill {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 999px;
            font-size: 0.78rem;
            border: 1px solid var(--line);
        }
        .success-pill { color: var(--accent); }
        .warn-pill { color: var(--warn); }
        .bad-pill { color: var(--bad); }
        textarea, input { border-radius: 8px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_results_summary(df: pd.DataFrame) -> None:
    if df.empty:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Screened", len(df))
    c2.metric("Strong Fit", int((df["Verdict"] == "Strong Fit").sum()))
    c3.metric("Good Fit", int((df["Verdict"] == "Good Fit").sum()))
    c4.metric("Average Score", round(float(df["Final Score"].mean()), 1))

    display_cols = [
        "Send", "Name", "Email", "Phone", "Experience", "Final Score", "Verdict",
        "Matched Keywords", "Missing Keywords", "Reason", "Source File",
    ]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    st.download_button(
        "Download screening CSV",
        df.to_csv(index=False).encode("utf-8"),
        "joy_screening_results.csv",
        "text/csv",
        use_container_width=False,
    )


def run_screening(
    uploads,
    jd_text: str,
    role_input: str,
    extra_keywords: str,
    api_key: str,
    model: str,
    user_key: str,
) -> tuple[pd.DataFrame, list[str]]:
    errors = []
    role = extract_role_from_jd(jd_text, role_input)
    keywords = extract_keywords(f"{role}\n{jd_text}", extra_keywords)
    min_exp = parse_min_experience(jd_text)
    rows = []

    progress = st.progress(0)
    status = st.empty()

    for idx, upload in enumerate(uploads, start=1):
        status.write(f"Reading {upload.name} ({idx}/{len(uploads)})")
        text, error = read_uploaded_file(upload)
        if error:
            errors.append(f"{upload.name}: {error}")
        if not text.strip():
            rows.append(
                {
                    "Send": False,
                    "Name": upload.name,
                    "Email": "",
                    "Phone": "",
                    "Experience": 0.0,
                    "Keyword Score": 0,
                    "Final Score": 0.0,
                    "Verdict": "Low Fit",
                    "Matched Keywords": "",
                    "Missing Keywords": ", ".join(keywords[:10]),
                    "Skills": "",
                    "Reason": error or "No readable text found.",
                    "Source File": upload.name,
                    "AI Used": False,
                }
            )
        else:
            rows.append(
                score_resume(
                    jd_text=jd_text,
                    role=role,
                    resume_text=text,
                    filename=upload.name,
                    keywords=keywords,
                    min_exp=min_exp,
                    api_key=api_key,
                    model=model,
                )
            )
        progress.progress(idx / len(uploads))

    progress.empty()
    status.empty()

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Rank", range(1, len(df) + 1))

    st.session_state.last_role = role
    st.session_state.last_jd = jd_text
    st.session_state.last_keywords = keywords
    st.session_state.results_df = df
    save_history(df, role, user_key)
    return df, errors


st.set_page_config(page_title=f"{APP_NAME} AI Recruiter", page_icon="J", layout="wide")
render_css()
init_state()

with st.sidebar:
    st.title("Joy")
    st.caption("Screen. Select. Send.")

    st.session_state.sender_name = st.text_input(
        "Sender name",
        value=st.session_state.sender_name,
        placeholder="Your name",
    )
    st.session_state.company_name = st.text_input(
        "Company",
        value=st.session_state.company_name,
        placeholder=DEFAULT_COMPANY,
    )

    st.divider()
    st.session_state.sender_email = st.text_input(
        "Gmail address",
        value=st.session_state.sender_email,
        placeholder="you@gmail.com",
    )
    st.session_state.sender_password = st.text_input(
        "Gmail App Password",
        value=st.session_state.sender_password,
        type="password",
        placeholder="16-character app password",
    )
    st.caption("Gmail App Passwords are kept in this Streamlit session only.")

    st.divider()
    st.session_state.openai_api_key = st.text_input(
        "OpenAI API key (optional)",
        value=st.session_state.openai_api_key,
        type="password",
        placeholder="Fallback scoring works without it",
    )
    openai_model = st.text_input("OpenAI model", value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    st.divider()
    user_key = st.session_state.sender_email or "local"
    if st.button("Clear current results", use_container_width=True):
        st.session_state.results_df = pd.DataFrame()
        st.session_state.email_results = []
        st.rerun()


st.title("Joy AI Recruiter")
st.markdown(
    "<span class='muted'>Rank resumes against one role, then send one structured email that collects the details normally asked on a call.</span>",
    unsafe_allow_html=True,
)

screen_tab, email_tab, history_tab = st.tabs(["Screen", "Email", "History"])

with screen_tab:
    st.subheader("Role")
    role_col, keyword_col = st.columns([1.2, 1])
    with role_col:
        role_input = st.text_input("Role title", placeholder="Regional Sales Manager")
    with keyword_col:
        extra_keywords = st.text_input(
            "Must-have keywords",
            placeholder="HPLC, distributor management, SAP",
        )

    jd_text = st.text_area(
        "Job description",
        height=190,
        placeholder="Paste the JD or the role requirements here.",
    )

    uploads = st.file_uploader(
        "Upload resumes",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )

    run_col, _ = st.columns([1, 4])
    with run_col:
        run_clicked = st.button("Screen resumes", type="primary", use_container_width=True)

    if run_clicked:
        if not uploads:
            st.error("Upload at least one resume.")
        elif not role_input.strip() and not jd_text.strip():
            st.error("Add a role title or paste a JD.")
        else:
            with st.spinner("Screening resumes..."):
                results, read_errors = run_screening(
                    uploads=uploads,
                    jd_text=jd_text,
                    role_input=role_input,
                    extra_keywords=extra_keywords,
                    api_key=st.session_state.openai_api_key,
                    model=openai_model,
                    user_key=user_key,
                )
            st.success(f"Screened {len(results)} resume(s) for {st.session_state.last_role}.")
            for error in read_errors:
                st.warning(error)

    if not st.session_state.results_df.empty:
        st.divider()
        st.subheader(f"Results: {st.session_state.last_role}")
        show_results_summary(st.session_state.results_df)


with email_tab:
    st.subheader("Outreach")

    if st.session_state.results_df.empty:
        st.info("Run a screening first.")
    else:
        editable = st.session_state.results_df.copy()
        editable["Send"] = editable["Send"].astype(bool)

        edited = st.data_editor(
            editable,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=[
                "Rank", "Phone", "Experience", "Keyword Score", "Final Score",
                "Verdict", "Matched Keywords", "Missing Keywords", "Skills",
                "Reason", "Source File", "AI Used",
            ],
            column_config={
                "Send": st.column_config.CheckboxColumn("Send"),
                "Email": st.column_config.TextColumn("Email"),
            },
            key="email_editor",
        )

        selected = edited[edited["Send"] == True].copy()
        missing_email = selected[~selected["Email"].astype(str).str.contains("@", na=False)]

        st.session_state.questions_text = st.text_area(
            "Questions to collect",
            value=st.session_state.questions_text,
            height=180,
        )
        extra_note = st.text_area(
            "Extra note",
            placeholder="Example: This is a hybrid Pune role with a 25-30 LPA budget.",
            height=90,
        )

        subject = st.text_input(
            "Subject",
            value=f"Details required for {st.session_state.last_role} opportunity",
        )

        questions = questions_from_text(st.session_state.questions_text)
        if not selected.empty:
            preview_body = build_email_body(
                selected.iloc[0],
                st.session_state.last_role,
                st.session_state.sender_name,
                st.session_state.company_name,
                questions,
                extra_note,
            )
            with st.expander(f"Preview: {selected.iloc[0]['Name']}", expanded=False):
                st.code(preview_body, language="text")

        c1, c2, c3 = st.columns([1.3, 1.5, 3])
        with c1:
            confirm = st.checkbox("Recipient list reviewed")
        with c2:
            send_clicked = st.button(
                f"Send {len(selected)} email(s)",
                type="primary",
                disabled=selected.empty or not confirm,
                use_container_width=True,
            )

        if not missing_email.empty:
            st.warning("Add valid email addresses before sending: " + ", ".join(missing_email["Name"].astype(str).tolist()))

        if send_clicked:
            if not st.session_state.sender_email or not st.session_state.sender_password:
                st.error("Add Gmail address and Gmail App Password in the sidebar.")
            elif not st.session_state.sender_name:
                st.error("Add sender name in the sidebar.")
            elif not missing_email.empty:
                st.error("Fix missing candidate email addresses first.")
            else:
                with st.spinner("Sending emails..."):
                    st.session_state.email_results = send_bulk_emails(
                        selected_df=selected,
                        role=st.session_state.last_role,
                        sender_email=st.session_state.sender_email,
                        sender_password=st.session_state.sender_password,
                        sender_name=st.session_state.sender_name,
                        company_name=st.session_state.company_name,
                        subject=subject,
                        questions=questions,
                        extra_note=extra_note,
                    )
                sent_count = sum(1 for item in st.session_state.email_results if item["Success"])
                st.success(f"Sent {sent_count} of {len(st.session_state.email_results)} email(s).")

        if st.session_state.email_results:
            st.dataframe(pd.DataFrame(st.session_state.email_results), use_container_width=True, hide_index=True)


with history_tab:
    st.subheader("History")
    hist = load_history(user_key)

    if hist.empty:
        st.info("No saved screenings yet.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Candidates", len(hist))
        c2.metric("Strong Fit", int((hist["Verdict"] == "Strong Fit").sum()) if "Verdict" in hist.columns else 0)
        c3.metric("Roles", hist["Role"].nunique() if "Role" in hist.columns else 0)

        if "Role" in hist.columns:
            roles = ["All"] + sorted(hist["Role"].dropna().unique().tolist())
            selected_role = st.selectbox("Role filter", roles)
            shown = hist if selected_role == "All" else hist[hist["Role"] == selected_role]
        else:
            shown = hist

        st.dataframe(shown, use_container_width=True, hide_index=True)
        h1, h2, h3 = st.columns([1.2, 1.2, 4])
        with h1:
            st.download_button(
                "Download history",
                shown.to_csv(index=False).encode("utf-8"),
                "joy_history.csv",
                "text/csv",
                use_container_width=True,
            )
        with h2:
            confirm_clear = st.checkbox("Confirm clear")
            if st.button("Clear history", disabled=not confirm_clear, use_container_width=True):
                clear_history(user_key)
                st.rerun()
