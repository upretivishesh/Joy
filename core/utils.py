import os
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .constants import DEFAULT_COMPANY, DEFAULT_QUESTIONS


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
    badge = {
        "Yes": "Match",
        "Partial": "Partial",
        "No": "No Match",
        "N/A": "—",
        "NA": "—",
        "nan": "—",
        "": "—",
    }
    df["Industry Match"] = df["Industry Match"].astype(str).map(lambda v: badge.get(v, "—"))
    return df


def filter_history_by_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    query = (query or "").strip()
    if not query or df.empty:
        return df

    search_cols = [
        c for c in [
            "Name",
            "Email",
            "Phone",
            "Skills",
            "Matched Keywords",
            "Role",
            "Candidate Industry",
            "Source File",
            "Profile Key",
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
    st.session_state["_clear_jd_form"] = True

def reset_screening_session() -> None:
    import pandas as pd
    import streamlit as st

    st.session_state["results_df"] = pd.DataFrame()
    st.session_state["email_results"] = []
    st.session_state["selected_candidates"] = pd.DataFrame()
    st.session_state["selected_history"] = pd.DataFrame()

    st.session_state["last_role"] = ""
    st.session_state["last_jd"] = ""
    st.session_state["last_keywords"] = []
    st.session_state["last_client_company"] = ""

    st.session_state["typed_jd_text"] = ""
    st.session_state["role_input"] = ""
    st.session_state["client_company_input"] = ""
    st.session_state["extra_keywords"] = ""

    st.session_state["_pending_jd_text"] = None
    st.session_state["_pending_role_input"] = None
    st.session_state["_history_loaded_role"] = None
    st.session_state["_history_loaded_jd"] = None

    st.session_state["_persona_company_key"] = None
    st.session_state["_persona_profile"] = {}
    st.session_state["_persona_save_status"] = None

    st.session_state.pop("client_picker", None)
    st.session_state.pop("email_editor", None)
    st.session_state.pop("edited_email_preview", None)
    st.session_state.pop("_email_fingerprint", None)

    st.session_state.pop("history_editor", None)
    st.session_state.pop("history_email_preview", None)
    st.session_state.pop("_history_fingerprint", None)
    st.session_state.pop("history_subject", None)
    st.session_state.pop("history_questions", None)
    st.session_state.pop("history_note", None)
    st.session_state.pop("history_confirm", None)
    
    st.session_state["upload_session"] = st.session_state.get("upload_session", 0) + 1
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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Newsreader:opsz,wght@6..72,500;6..72,650&display=swap');

        :root {
            --bg: #05060a;
            --panel: rgba(255,255,255,0.03);
            --panel-strong: #0d0f14;
            --line: rgba(255,255,255,0.08);
            --ink: #f2f4f7;
            --muted: #9aa1b2;
            --muted-2: #5c6377;
            --accent: #35e0c1;
            --accent-soft: rgba(53,224,193,0.14);
            --bad: #ff6b6b;
            --bad-soft: rgba(255,90,90,0.15);
            --radius: 14px;
            --radius-sm: 10px;
            --shadow: 0 8px 30px rgba(0,0,0,0.35);
        }

        html, body, [class*="css"], .stApp {
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: var(--ink);
        }

        .stApp {
            background: radial-gradient(circle at 15% 0%, #0d1420 0%, var(--bg) 55%);
        }

        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        hr { display: none !important; }

        h1, h2, h3 {
            font-family: 'Newsreader', Georgia, serif !important;
            font-weight: 650 !important;
            letter-spacing: -0.01em;
            color: var(--ink);
        }

        .hero {
            padding: 2.2rem 2.4rem;
            border-radius: var(--radius);
            background: linear-gradient(135deg, rgba(53,224,193,0.08), rgba(255,255,255,0.02));
            border: 1px solid var(--line);
            margin-bottom: 1.6rem;
        }
        .eyebrow {
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--accent);
            background: var(--accent-soft);
            padding: 4px 10px;
            border-radius: 6px;
            margin-bottom: 12px;
        }
        .hero-title {
            font-size: clamp(2rem, 5vw, 3rem);
            line-height: 1.05;
            margin: 0 0 10px 0;
        }
        .hero-copy {
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.6;
            max-width: 660px;
            margin: 0;
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0b0d14 0%, var(--bg) 100%);
            border-right: 1px solid var(--line);
        }
        section[data-testid="stSidebar"] h1 {
            font-family: 'Inter', sans-serif !important;
            font-size: 1.3rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--ink);
            margin-bottom: 2px;
        }
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] .stCaptionContainer {
            color: var(--muted) !important;
        }

        div[data-baseweb="tab-list"] {
            gap: 6px;
            border-bottom: 1px solid var(--line);
        }
        button[data-baseweb="tab"] {
            font-weight: 600;
            font-size: 0.92rem;
            color: var(--muted);
            padding: 10px 18px;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--accent) !important;
        }
        div[data-baseweb="tab-highlight"] {
            background-color: var(--accent) !important;
            height: 2.5px !important;
        }
        div[data-baseweb="tab-border"] { display: none; }

        .stButton > button, .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] button {
            border-radius: var(--radius-sm) !important;
            font-weight: 600 !important;
            border: 1px solid var(--line) !important;
            transition: all 0.15s ease;
        }
        .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
            background: var(--ink) !important;
            color: #05070c !important;
            border: none !important;
            box-shadow: 0 4px 14px rgba(255,255,255,0.10);
        }
        .stButton > button[kind="primary"]:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(255,255,255,0.18);
            background: #ffffff !important;
        }
        .stButton > button[kind="secondary"] {
            background: var(--panel) !important;
            color: var(--ink) !important;
        }
        .stButton > button[kind="secondary"]:hover {
            border-color: var(--accent) !important;
            color: var(--accent) !important;
        }

        textarea, input, div[data-baseweb="select"] > div {
            background: var(--panel) !important;
            border: 1px solid var(--line) !important;
            border-radius: var(--radius-sm) !important;
            color: var(--ink) !important;
        }
        textarea:focus, input:focus {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 1px var(--accent) !important;
        }
        [data-testid="stExpander"] textarea {
            min-height: 110px !important;
            line-height: 1.55 !important;
            padding: 12px 14px !important;
            resize: vertical !important;
        }
        [data-baseweb="tag"] {
            background: var(--accent-soft) !important;
            border: 1px solid rgba(53,224,193,0.35) !important;
            border-radius: 8px !important;
            color: var(--ink) !important;
        }

        div[data-testid="stTextInput"] > div {
            background: var(--panel) !important;
            border: 1px solid var(--line) !important;
            border-radius: var(--radius-sm) !important;
        }
        div[data-testid="stTextInput"] [data-baseweb="input"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }
        div[data-testid="stTextInput"] input {
            background: transparent !important;
            color: var(--ink) !important;
        }
        div[data-testid="stTextInput"] button {
            background: transparent !important;
            color: var(--muted) !important;
            border: none !important;
            box-shadow: none !important;
        }
        div[data-testid="stTextInput"] > div:focus-within {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 1px var(--accent) !important;
        }

        [data-testid="stFileUploaderDropzone"] {
            background: var(--panel);
            border: 1.5px dashed var(--line);
            border-radius: var(--radius);
        }
        [data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent); }
        [data-testid="stFileUploaderDropzone"] * { color: var(--muted) !important; }

        div[data-testid="stExpander"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius);
        }
        .joy-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: var(--radius);
            padding: 16px;
            box-shadow: var(--shadow);
        }

        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: var(--shadow);
        }
        [data-testid="stMetricValue"] { color: var(--ink) !important; font-weight: 800; }
        [data-testid="stMetricLabel"] p { color: var(--muted) !important; font-size: 0.78rem !important; }

        div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
            border-radius: var(--radius);
            border: 1px solid var(--line);
            overflow: hidden;
            box-shadow: var(--shadow);
        }

        div[data-testid="stAlert"] { border-radius: var(--radius-sm); border: 1px solid var(--line); }

        .timeline-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 10px;
        }
        .timeline-card .tc-role { font-weight: 700; color: var(--ink); font-size: 0.98rem; }
        .timeline-card .tc-meta { color: var(--muted); font-size: 0.82rem; margin-top: 2px; }
        .timeline-card .tc-badge {
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 2px 9px;
            border-radius: 6px;
            margin-top: 6px;
        }
        .badge-good { background: rgba(53,224,193,0.14); color: #35e0c1; }
        .badge-bad { background: rgba(255,90,90,0.15); color: #ff6b6b; }
        .badge-pending { background: rgba(255,255,255,0.06); color: #9aa1b2; }
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


def inject_clear_icon_fix() -> None:
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


def inject_keepalive() -> None:
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
            "Send",
            "Name",
            "Email",
            "Phone",
            "Experience",
            "Education",
            "Final Score",
            "Feedback",
            "Verdict",
            "Industry Match",
            "Candidate Industry",
            "Matched Keywords",
            "Missing Keywords",
            "Source File",
        ]
        if col in df.columns
    ]

    display_df = df[display_cols].copy()

    if "Feedback" not in display_df.columns:
        display_df["Feedback"] = "Pending"
    display_df["Feedback"] = (
        display_df["Feedback"]
        .fillna("Pending")
        .astype(str)
        .replace({"": "Pending", "nan": "Pending"})
    )

    if "Name" in display_df.columns:
        display_df["Name"] = display_df["Name"].astype(str).str.title()

    if "Candidate Industry" in display_df.columns:
        display_df["Candidate Industry"] = (
            display_df["Candidate Industry"]
            .fillna("")
            .astype(str)
            .replace({"": "Others / Not Detected", "nan": "Others / Not Detected"})
        )

    if "Industry Match" in display_df.columns:
        display_df["Industry Match"] = (
            display_df["Industry Match"]
            .fillna("NA")
            .astype(str)
            .replace({"NA": "N/A", "": "N/A", "nan": "N/A"})
        )

    display_df = format_experience_years(display_df)
    display_df = format_industry_fit(display_df)
    display_df = order_columns_first(
        display_df,
        [
            "Send",
            "Name",
            "Email",
            "Phone",
            "Experience",
            "Education",
            "Final Score",
            "Feedback",
            "Verdict",
        ],
    )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Download screening CSV",
        df.to_csv(index=False).encode("utf-8"),
        "joy_screening_results.csv",
        "text/csv",
        use_container_width=False,
    )
