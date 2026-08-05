import os
import re
from typing import Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*" * 3
    else:
        visible = local[:2]
        masked_local = visible + "*" * min(6, max(len(local) - 2, 3))
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
    df["Experience"] = numeric.apply(lambda v: f"{v:g} yrs")
    return df


def format_industry_fit(df: pd.DataFrame) -> pd.DataFrame:
    if "Industry Match" not in df.columns:
        return df
    df = df.copy()
    badge = {"Yes": "Match", "Partial": "Partial", "No": "No Match", "N/A": "—"}
    df["Industry Match"] = df["Industry Match"].astype(str).map(lambda v: badge.get(v, "—"))
    return df


def clean_phone_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )


def filter_history_by_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    query = (query or "").strip()
    if not query or df.empty:
        return df

    search_cols = [
        c for c in [
            "Name", "Email", "Phone", "Skills", "Matched Keywords",
            "Role", "Candidate Industry", "Source File", "Profile Key",
        ] if c in df.columns
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
    st.session_state["_clear_jd_form"] = True


def reset_screening_session() -> None:
    st.session_state.results_df = pd.DataFrame()
    st.session_state.email_results = []
    st.session_state.selected_candidates = pd.DataFrame()
    st.session_state.selected_history = pd.DataFrame()

    st.session_state.last_role = ""
    st.session_state.last_jd = ""
    st.session_state.last_keywords = []
    st.session_state.last_client_company = ""

    st.session_state["_pending_jd_text"] = None
    st.session_state["_pending_role_input"] = None
    st.session_state["_history_loaded_role"] = None
    st.session_state["_history_loaded_jd"] = None

    st.session_state["_persona_company_key"] = None
    st.session_state["_persona_profile"] = {}
    st.session_state["_persona_save_status"] = None

    st.session_state["typed_jd_text"] = ""
    st.session_state["role_input"] = ""
    st.session_state["extra_keywords"] = ""
    st.session_state["client_company_input"] = ""

    st.session_state.pop("client_picker", None)
    st.session_state.pop("email_subject", None)
    st.session_state.pop("edited_email_preview", None)
    st.session_state.pop("_email_fingerprint", None)

    st.session_state["jd_save_role"] = ""
    st.session_state["jd_save_text"] = ""
    st.session_state["jd_save_tags"] = ""

    st.session_state.upload_session = st.session_state.get("upload_session", 0) + 1


# ============================================================
# Authentication (Google OAuth + Manual Whitelist)
# ============================================================
def is_auth_configured() -> bool:
    try:
        if "auth" not in st.secrets:
            return False
        auth = st.secrets["auth"]
        required = ["redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url"]
        return all(bool(auth.get(key)) for key in required)
    except Exception:
        return False


def is_user_allowed(email: str) -> bool:
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
    clean_email = (email or "").strip().lower()
    st.session_state.gmail_authenticated = True
    st.session_state.sender_email = clean_email
    st.session_state.sender_name = (name or "").strip() or name_from_email_address(clean_email)
    st.session_state.company_name = (company or "").strip() or DEFAULT_COMPANY
    if "sender_password" not in st.session_state:
        st.session_state.sender_password = ""


def login_user(email: str, app_password: str, sender_name: str, company_name: str) -> None:
    clean_email = email.strip().lower()
    st.session_state.gmail_authenticated = True
    st.session_state.sender_email = clean_email
    st.session_state.sender_password = re.sub(r"\s+", "", app_password or "")
    st.session_state.sender_name = sender_name.strip() or name_from_email_address(clean_email)
    st.session_state.company_name = company_name.strip() or DEFAULT_COMPANY


def logout_user() -> None:
    for key in ["gmail_authenticated", "sender_email", "sender_password", "sender_name", "company_name"]:
        st.session_state[key] = False if key == "gmail_authenticated" else ""
    st.session_state.email_results = []
    try:
        st.logout()
    except Exception:
        pass
    st.rerun()


# ============================================================
# PREMIUM DESIGN SYSTEM
# ============================================================
def inject_elite_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg: #060b16;
                --panel: #111828;
                --panel-2: #0e1624;
                --line: rgba(95, 113, 145, 0.28);
                --line-soft: rgba(95, 113, 145, 0.16);
                --ink: #eef2ff;
                --muted: #9aa8c7;
                --accent: #42e8d0;
                --accent-soft: rgba(66, 232, 208, 0.14);
                --radius-md: 16px;
                --shadow: 0 16px 40px rgba(0, 0, 0, 0.34);
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(66, 232, 208, 0.08), transparent 28%),
                    radial-gradient(circle at top right, rgba(112, 92, 255, 0.09), transparent 30%),
                    linear-gradient(180deg, #060b16 0%, #040712 100%);
                color: var(--ink);
            }

            .block-container {
                padding-top: 2rem;
                padding-bottom: 2rem;
                max-width: 1380px;
            }

            h1, h2, h3, h4, h5, h6,
            p, span, label, div {
                color: var(--ink);
            }

            /* Hero / Joy AI Recruiter */
            .hero {
                position: relative;
                padding: 30px 34px;
                border-radius: 28px;
                background:
                    linear-gradient(135deg, rgba(19, 27, 44, 0.96), rgba(10, 17, 30, 0.94)),
                    linear-gradient(135deg, rgba(66, 232, 208, 0.08), rgba(112, 92, 255, 0.05));
                border: 1px solid rgba(95, 113, 145, 0.24);
                box-shadow: var(--shadow);
                overflow: hidden;
                margin-bottom: 1.2rem;
            }

            .eyebrow {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 7px 12px;
                border-radius: 999px;
                background: rgba(66, 232, 208, 0.1);
                color: var(--accent);
                font-size: 0.82rem;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                font-weight: 700;
                margin-bottom: 14px;
            }

            .hero-title {
                font-size: clamp(2.2rem, 3.6vw, 4rem);
                line-height: 1.04;
                font-weight: 800;
                margin: 0 0 12px 0;
                letter-spacing: -0.03em;
            }

            .hero-copy {
                max-width: 760px;
                color: var(--muted) !important;
                font-size: 1rem;
                line-height: 1.75;
                margin: 0;
            }

            /* Tabs: plain words + underline */
            div[data-baseweb="tab-list"] {
                gap: 28px !important;
                margin-top: 8px !important;
                margin-bottom: 14px !important;
                background: transparent !important;
                border-bottom: 1px solid rgba(95, 113, 145, 0.22) !important;
                box-shadow: none !important;
            }

            div[data-baseweb="tab-list"] > button {
                background: transparent !important;
                border: none !important;
                border-radius: 0 !important;
                color: #9aa8c7 !important;
                padding: 10px 2px !important;
                font-weight: 700 !important;
                box-shadow: none !important;
                position: relative !important;
                margin: 0 !important;
            }

            div[data-baseweb="tab-list"] > button[aria-selected="true"] {
                color: #eef2ff !important;
                background: transparent !important;
                box-shadow: none !important;
            }

            div[data-baseweb="tab-list"] > button::after {
                display: block !important;
                content: "";
                position: absolute;
                left: 0;
                right: 0;
                bottom: -14px;
                height: 3px;
                border-radius: 999px;
                background: transparent !important;
            }

            div[data-baseweb="tab-list"] > button[aria-selected="true"]::after {
                background: #ff5a52 !important;
            }

            div[data-baseweb="tab-panel"] {
                border-top: none !important;
            }

            /* Buttons: softer teal with darker text */
            .stButton > button {
                border-radius: 14px !important;
                border: 1px solid transparent !important;
                font-weight: 700 !important;
                padding: 0.72rem 1rem !important;
                box-shadow: none !important;
            }

           .stButton > button[kind="primary"] {
                background: linear-gradient(135deg, #4fd6c4, #67e3d4) !important;
                color: #08211f !important;
                border-color: rgba(66, 232, 208, 0.16) !important;
            }
            
            .stButton > button[kind="primary"]:hover {
                background: linear-gradient(135deg, #45ccb9, #5fdacb) !important;
                color: #041815 !important;
            }
            
            .stButton > button[kind="secondary"] {
                background: rgba(255, 255, 255, 0.04) !important;
                color: #dfe7f5 !important;
                border: 1px solid rgba(95, 113, 145, 0.28) !important;
            }
            /* Inputs (unchanged shape, just keep them clean) */
            div[data-baseweb="input"],
            div[data-baseweb="base-input"] {
                background: var(--panel) !important;
                border: 1px solid var(--line) !important;
                border-radius: var(--radius-md) !important;
                box-shadow: none !important;
                overflow: hidden !important;
            }

            div[data-baseweb="input"] > div {
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
            }

            div[data-baseweb="input"] input {
                background: transparent !important;
                border: none !important;
                outline: none !important;
                box-shadow: none !important;
                color: var(--ink) !important;
            }

            div[data-baseweb="input"]:focus-within {
                border-color: rgba(66, 232, 208, 0.7) !important;
                box-shadow: 0 0 0 1px rgba(66, 232, 208, 0.35) !important;
            }

            .stTextArea textarea {
                background: var(--panel) !important;
                color: var(--ink) !important;
                border: 1px solid var(--line) !important;
                border-radius: var(--radius-md) !important;
                box-shadow: none !important;
            }

            .stTextArea textarea:focus {
                border-color: rgba(66, 232, 208, 0.7) !important;
                box-shadow: 0 0 0 1px rgba(66, 232, 208, 0.35) !important;
            }

            .stTextInput label,
            .stTextArea label,
            .stSelectbox label,
            .stMultiSelect label,
            .stNumberInput label,
            .stFileUploader label {
                font-weight: 700 !important;
                color: var(--ink) !important;
            }

            .stCaption,
            [data-testid="stCaptionContainer"],
            [data-testid="stCaptionContainer"] * {
                color: var(--muted) !important;
            }

            [data-testid="stToolbar"] {
                visibility: hidden;
            }
            /* FORCE readable primary button text */
            button[kind="primary"],
            button[kind="primary"] span,
            .stButton > button,
            .stButton > button span {
                color: #041815 !important;
                -webkit-text-fill-color: #041815 !important;
                opacity: 1 !important;
            }
            
            button[kind="secondary"],
            button[kind="secondary"] span,
            .stButton > button[kind="secondary"],
            .stButton > button[kind="secondary"] span {
                color: #dbe7f3 !important;
                -webkit-text-fill-color: #dbe7f3 !important;
                opacity: 1 !important;
            }
            div[data-baseweb="input"],
            div[data-baseweb="base-input"],
            .stTextArea textarea {
                border: 1px solid rgba(66, 232, 208, 0.55) !important;
                box-shadow: none !important;
            }
            
            div[data-baseweb="input"]:focus-within,
            .stTextArea textarea:focus {
                border-color: rgba(66, 232, 208, 0.85) !important;
                box-shadow: 0 0 0 1px rgba(66, 232, 208, 0.25) !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    

def render_css() -> None:
    inject_elite_theme()


def inject_premium_persona_css() -> None:
    inject_elite_theme()


def _inject_html(html_string: str, height: int = 0, width: int = 0) -> None:
    try:
        components.html(html_string, height=height, width=width)
    except Exception:
        pass


def inject_multiselect_chip_fix() -> None:
    _inject_html(
        """
        <script>
        const applyChipFix = () => {
          const roots = window.parent.document.querySelectorAll('[data-baseweb="select"]');
          roots.forEach(root => {
            root.style.minHeight = "52px";
          });
        };
        applyChipFix();
        new MutationObserver(applyChipFix).observe(window.parent.document.body, {
          childList: true,
          subtree: true
        });
        /* FINAL OVERRIDE: button text color */
        .stButton > button[kind="primary"],
        .stButton > button[kind="primary"] span {
            color: #031716 !important;  /* much darker text */
        }
        
        .stButton > button[kind="secondary"],
        .stButton > button[kind="secondary"] span {
            color: #dfe7f5 !important;
        }
        </script>
        """,
        height=0,
        width=0,
    )


def inject_clear_icon_fix() -> None:
    _inject_html(
        """
        <script>
        const applyClearFix = () => {
          const buttons = window.parent.document.querySelectorAll('button[aria-label="Clear value"]');
          buttons.forEach(btn => {
            btn.style.border = "none";
            btn.style.boxShadow = "none";
            btn.style.background = "transparent";
          });
        };
        applyClearFix();
        new MutationObserver(applyClearFix).observe(window.parent.document.body, {
          childList: true,
          subtree: true
        });
        </script>
        """,
        height=0,
        width=0,
    )


def inject_keepalive() -> None:
    _inject_html(
        """
        <script>
        setInterval(() => {
          try {
            const parentDoc = window.parent.document;
            parentDoc.dispatchEvent(new MouseEvent("mousemove", {bubbles: true}));
            parentDoc.dispatchEvent(new KeyboardEvent("keydown", {bubbles: true, key: "Shift"}));
          } catch (e) {}
        }, 240000);
        </script>
        """,
        height=0,
        width=0,
    )


def show_results_summary(df: pd.DataFrame) -> None:
    if df is None or df.empty or "Final Score" not in df.columns:
        return

    work = df.copy()
    work["Final Score"] = pd.to_numeric(work["Final Score"], errors="coerce")
    work = work.dropna(subset=["Final Score"])

    if work.empty:
        return

    total = len(work)
    avg_score = round(float(work["Final Score"].mean()), 1)
    strong_fit = int((work["Final Score"] >= 75).sum())
    possible_fit = int(((work["Final Score"] >= 60) & (work["Final Score"] < 75)).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidates", total)
    c2.metric("Average score", avg_score)
    c3.metric("Strong fit", strong_fit)
    c4.metric("Possible fit", possible_fit)
