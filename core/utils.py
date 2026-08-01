import os
import re
from typing import Optional

import pandas as pd
import streamlit as st

from .constants import APP_NAME, DATA_DIR, DEFAULT_COMPANY, DEFAULT_QUESTIONS


# ============================================================
# Secrets helper
# ============================================================
def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return value or os.getenv(name, default)


# ============================================================
# Basic helpers
# ============================================================
def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def name_from_email_address(email: str) -> str:
    local = (email or "").split("@")[0]
    local = re.sub(r"\+.*$", "", local)
    local = re.sub(r"[_\-.]+", " ", local)
    local = re.sub(r"[^A-Za-z]+", " ", local)
    parts = [part for part in local.split() if len(part) > 1 and not part.isdigit()]
    return " ".join(part.capitalize() for part in parts[:3])


def mask_email(email: str) -> str:
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    masked_local = local[:2] + "*" * min(5, max(len(local) - 2, 1))
    return f"{masked_local}@{domain}"


def order_columns_first(df: pd.DataFrame, first: list[str]) -> pd.DataFrame:
    cols = list(df.columns)
    first_present = [c for c in first if c in cols]
    remaining = [c for c in cols if c not in first_present]
    return df[first_present + remaining]


def format_experience_years(df: pd.DataFrame) -> pd.DataFrame:
    if "Experience" not in df.columns:
        return df
    df = df.copy()
    numeric = pd.to_numeric(df["Experience"], errors="coerce").fillna(0)
    df["Experience"] = numeric.apply(lambda v: f"{v:g} Years")
    return df


def format_industry_fit(df: pd.DataFrame) -> pd.DataFrame:
    if "Industry Match" not in df.columns:
        return df
    df = df.copy()
    badge = {"Yes": "✅ Yes", "Partial": "⚠️ Partial", "No": "❌ No", "N/A": "— N/A"}
    df["Industry Match"] = df["Industry Match"].astype(str).map(lambda v: badge.get(v, "— N/A"))
    return df


def filter_history_by_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    query = (query or "").strip()
    if not query or df.empty:
        return df

    search_cols = [
        c for c in [
            "Name", "Email", "Phone", "Skills", "Matched Keywords",
            "Role", "Candidate Industry", "Source File",
        ]
        if c in df.columns
    ]
    if not search_cols:
        return df.iloc[0:0]

    mask = pd.Series(False, index=df.index)
    for col in search_cols:
        mask = mask | df[col].astype(str).str.contains(query, case=False, na=False, regex=False)
    return df[mask]


def safe_filename_part(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", value or "user")
    return clean.strip("_")[:80] or "user"


def questions_from_text(text: str) -> list[str]:
    questions = []
    for line in (text or "").splitlines():
        clean = re.sub(r"^\s*[-*0-9.)]+\s*", "", line).strip()
        if clean:
            questions.append(clean)
    return questions or DEFAULT_QUESTIONS


def first_name(full_name: str) -> str:
    if not full_name or full_name == "Unknown Candidate":
        return "there"
    return str(full_name).split()[0].strip(",")


# ============================================================
# Session state
# ============================================================
def init_state() -> None:
    defaults = {
        "gmail_authenticated": False,
        "results_df": pd.DataFrame(),
        "last_role": "",
        "last_jd": "",
        "last_keywords": [],
        "last_client_company": "",
        "email_results": [],
        "questions_text": "\n".join(DEFAULT_QUESTIONS),
        "sender_email": "",
        "sender_password": "",
        "sender_name": "",
        "company_name": DEFAULT_COMPANY,
        "upload_session": 0,
        "selected_candidates": pd.DataFrame(),
        "selected_history": pd.DataFrame(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_jd_library_form() -> None:
    for key in ["jd_save_role", "jd_save_text", "jd_save_tags"]:
        st.session_state[key] = ""


def reset_screening_session() -> None:
    st.session_state.results_df = pd.DataFrame()
    st.session_state.email_results = []
    st.session_state.last_role = ""
    st.session_state.last_jd = ""
    st.session_state.last_keywords = []
    st.session_state.upload_session += 1

    st.session_state["_pending_jd_text"] = ""
    st.session_state["_pending_role_input"] = ""

    for key in ["typed_jd_text", "role_input", "extra_keywords", "client_company_input", "client_picker"]:
        if key in st.session_state:
            del st.session_state[key]

    for key in ["_persona_company_key", "_persona_profile"]:
        if key in st.session_state:
            del st.session_state[key]

    for key in ["email_subject", "edited_email_preview", "_email_fingerprint"]:
        if key in st.session_state:
            del st.session_state[key]

    for key in ["jd_save_role", "jd_save_text", "jd_save_tags"]:
        st.session_state[key] = ""


# ============================================================
# Authentication (Google OAuth + Manual Whitelist)
# ============================================================
def is_auth_configured() -> bool:
    """Return True only if all required Google OAuth secrets are present."""
    try:
        if "auth" not in st.secrets:
            return False
        auth = st.secrets["auth"]
        required = ["redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url"]
        return all(bool(auth.get(key)) for key in required)
    except Exception:
        return False


def is_user_allowed(email: str) -> bool:
    """
    Simple whitelist check.
    Looks at ADMIN_EMAILS and ALLOWED_EMAILS from secrets.
    """
    if not email:
        return False
    email = email.strip().lower()

    try:
        admin_raw = st.secrets.get("ADMIN_EMAILS", "") or ""
        allowed_raw = st.secrets.get("ALLOWED_EMAILS", "") or ""
    except Exception:
        admin_raw = ""
        allowed_raw = ""

    admins = {e.strip().lower() for e in admin_raw.split(",") if e.strip()}
    allowed = {e.strip().lower() for e in allowed_raw.split(",") if e.strip()}

    return email in admins or email in allowed


def login_user_from_google(email: str, name: str = "", company: str = "") -> None:
    """Called after successful Google login + whitelist check."""
    clean_email = (email or "").strip().lower()
    st.session_state.gmail_authenticated = True
    st.session_state.sender_email = clean_email
    st.session_state.sender_name = (name or "").strip() or name_from_email_address(clean_email)
    st.session_state.company_name = (company or "").strip() or DEFAULT_COMPANY
    if "sender_password" not in st.session_state:
        st.session_state.sender_password = ""


def login_user(email: str, app_password: str, sender_name: str, company_name: str) -> None:
    """Legacy function (kept for compatibility)."""
    clean_email = email.strip().lower()
    st.session_state.gmail_authenticated = True
    st.session_state.sender_email = clean_email
    st.session_state.sender_password = re.sub(r"\s+", "", app_password or "")
    st.session_state.sender_name = sender_name.strip() or name_from_email_address(clean_email)
    st.session_state.company_name = company_name.strip() or DEFAULT_COMPANY


def logout_user() -> None:
    """Fully sign out (clear session state + Google identity cookie)."""
    for key in ["gmail_authenticated", "sender_email", "sender_password", "sender_name", "company_name"]:
        st.session_state[key] = False if key == "gmail_authenticated" else ""
    st.session_state.email_results = []
    try:
        st.logout()
    except Exception:
        pass
    st.rerun()


# ============================================================
# CSS & UI helpers
# ============================================================
def render_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,650&display=swap');
        :root {
            --bg: #000000;
            --panel: #0d0f13;
            --panel-2: #151820;
            --ink: #f5f7fb;
            --muted: #8d96a6;
            --line: #222733;
            --accent: #54d6b6;
            --accent-2: #a5b4fc;
            --warn: #f6c267;
            --bad: #fb8b8b;
            --shadow: 0 18px 55px rgba(0, 0, 0, 0.55);
            --ease: cubic-bezier(0.16, 1, 0.3, 1);
        }
        html, body, [class*="css"], .stApp {
            font-family: 'Instrument Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: var(--ink);
        }
        .stApp {
            background:
                linear-gradient(180deg, rgba(0,0,0,0.98), rgba(0,0,0,1)),
                radial-gradient(circle at top left, rgba(84,214,182,0.08), transparent 30%),
                var(--bg);
        }
        .block-container {
            max-width: 1160px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3, .hero-title {
            font-family: 'Newsreader', Georgia, serif !important;
            letter-spacing: 0 !important;
            color: var(--ink);
        }
        h2, h3 { font-weight: 650 !important; }
        .hero {
            padding: 30px 0 20px;
            max-width: 860px;
        }
        .eyebrow {
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .hero-title {
            font-size: clamp(2.4rem, 6vw, 5rem);
            line-height: 0.95;
            font-weight: 650;
            margin: 0 0 14px;
        }
        .hero-copy {
            max-width: 680px;
            color: var(--muted);
            font-size: 1.02rem;
            line-height: 1.7;
            margin: 0;
        }
        [data-testid="stSidebar"] {
            background: #050506;
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] * { color: #eef2f7; }
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] .stCaptionContainer {
            color: #98a2b3 !important;
        }
        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 15px 16px;
            box-shadow: var(--shadow);
        }
        [data-testid="stMetricLabel"] p {
            color: var(--muted) !important;
            font-size: 0.78rem !important;
        }
        .joy-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 16px;
            box-shadow: var(--shadow);
        }
        .muted { color: var(--muted); }
        .small-label {
            color: var(--muted);
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.35rem;
        }
        [data-baseweb="tab-list"] {
            gap: 8px;
            border-bottom: 1px solid var(--line);
        }
        [data-baseweb="tab"] {
            font-weight: 650;
            color: var(--muted);
            padding-left: 4px;
            padding-right: 18px;
        }
        [aria-selected="true"] { color: var(--ink) !important; }
        textarea, input {
            border-radius: 10px !important;
            border-color: var(--line) !important;
            background: #0b0d11 !important;
            color: var(--ink) !important;
        }
        textarea:focus, input:focus {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 3px rgba(84,214,182,0.14) !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            background: #0b0d11;
            border: 1px dashed #303746;
            border-radius: 12px;
        }
        [data-testid="stFileUploaderDropzone"] * { color: var(--muted) !important; }
        .stButton button,
        .stDownloadButton button,
        [data-testid="stFormSubmitButton"] button {
            border-radius: 10px !important;
            font-weight: 700 !important;
        }
        .stButton button[kind="primary"],
        .stDownloadButton button[kind="primary"] {
            background: var(--ink) !important;
            border-color: var(--ink) !important;
            color: #000 !important;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: var(--shadow);
        }
        .stAlert { border-radius: 12px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_premium_persona_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stExpander"] textarea {
            min-height: 110px !important;
            line-height: 1.55 !important;
            padding: 12px 14px !important;
            resize: vertical !important;
        }
        [data-baseweb="tag"] {
            background: rgba(84, 214, 182, 0.14) !important;
            border: 1px solid rgba(84, 214, 182, 0.35) !important;
            border-radius: 8px !important;
            color: var(--ink) !important;
        }
        div[data-baseweb="select"] > div {
            border-radius: 10px !important;
            background: #0b0d11 !important;
            overflow: visible !important;
            padding-left: 10px !important;
            box-sizing: border-box !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_html(html_string: str, height: int = 1, width: int = 1) -> None:
    try:
        st.iframe(html_string, height=height, width=width)
    except AttributeError:
        import streamlit.components.v1 as components
        components.html(html_string, height=height, width=width)


def inject_multiselect_chip_fix() -> None:
    try:
        _inject_html(
            """
            <script>
            (function() {
                const doc = window.parent.document;
                function fixChipPadding() {
                    const controls = doc.querySelectorAll('div[data-baseweb="select"]');
                    controls.forEach((control) => {
                        const tag = control.querySelector('[data-baseweb="tag"]');
                        if (!tag || !tag.parentElement) return;
                        const row = tag.parentElement;
                        if (row.dataset.joyPadded !== "1") {
                            row.style.paddingLeft = "10px";
                            row.style.boxSizing = "border-box";
                            row.dataset.joyPadded = "1";
                        }
                    });
                }
                fixChipPadding();
                const observer = new MutationObserver(fixChipPadding);
                observer.observe(doc.body, { childList: true, subtree: true });
            })();
            </script>
            """,
        )
    except Exception:
        pass


def inject_clear_icon_fix() -> None:
    try:
        _inject_html(
            """
            <script>
            (function() {
                const doc = window.parent.document;
                function fixClearIcon() {
                    const controls = doc.querySelectorAll('div[data-baseweb="select"]');
                    controls.forEach((control) => {
                        const buttons = control.querySelectorAll('[role="button"]');
                        buttons.forEach((btn) => {
                            if (btn.dataset.joyCleared !== "1") {
                                btn.style.background = "transparent";
                                btn.style.borderRadius = "999px";
                                btn.dataset.joyCleared = "1";
                            }
                        });
                    });
                }
                fixClearIcon();
                const observer = new MutationObserver(fixClearIcon);
                observer.observe(doc.body, { childList: true, subtree: true });
            })();
            </script>
            """,
        )
    except Exception:
        pass


def inject_keepalive() -> None:
    try:
        _inject_html(
            """
            <script>
            const ping = () => {
              try {
                fetch(window.parent.location.href, {cache: "no-store", mode: "no-cors"});
              } catch (e) {}
            };
            setInterval(ping, 240000);
            </script>
            """,
        )
    except Exception:
        pass


def show_results_summary(df: pd.DataFrame) -> None:
    if df.empty:
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Screened", len(df))
    c2.metric("Strong Fit", int((df["Verdict"] == "Strong Fit").sum()) if "Verdict" in df.columns else 0)
    c3.metric("Good Fit", int((df["Verdict"] == "Good Fit").sum()) if "Verdict" in df.columns else 0)
    c4.metric("Average Score", round(float(df["Final Score"].mean()), 1) if "Final Score" in df.columns else 0)

    display_cols = [
        col for col in [
            "Send", "Name", "Email", "Phone", "Experience",
            "Final Score", "Verdict", "Industry Match", "Candidate Industry",
            "Matched Keywords", "Missing Keywords", "Source File",
        ]
        if col in df.columns
    ]

    display_df = df[display_cols].copy()
    if "Name" in display_df.columns:
        display_df["Name"] = display_df["Name"].astype(str).str.title()
    display_df = format_experience_years(display_df)
    display_df = format_industry_fit(display_df)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Download screening CSV",
        df.to_csv(index=False).encode("utf-8"),
        "joy_screening_results.csv",
        "text/csv",
        use_container_width=False,
    )
