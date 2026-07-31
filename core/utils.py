import os
import re

import pandas as pd
import streamlit as st

from .constants import APP_NAME, DATA_DIR, DEFAULT_COMPANY, DEFAULT_QUESTIONS


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return value or os.getenv(name, default)


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


def reorder_columns(df: pd.DataFrame, priority: list[str]) -> pd.DataFrame:
    cols = list(df.columns)
    priority_present = [c for c in priority if c in cols]
    remaining = [c for c in cols if c not in priority_present]
    return df[priority_present + remaining]


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
    """
    Case-insensitive substring search across the ENTIRE candidate history,
    regardless of which role or client they were originally screened
    against — this is what powers the History tab's global search box.

    Matches whichever of these columns actually exist on the dataframe
    (schemas drift over time as fields get added), so a query like "priya",
    "9876", "SAP MM", or "atomgrid" all work without the caller needing to
    know which exact field the match lives in.
    """
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


def smart_multiselect(label, options, default, key, placeholder="", max_selections=None):
    """
    st.multiselect with accept_new_options=True (type straight into the
    dropdown to add something that isn't in the curated list — this is
    what actually fixes 'not many industries/languages to choose from')
    on Streamlit versions that support it; falls back to a companion
    'add custom' text input on older versions so an unpinned environment
    never hard-crashes on this call. Requires Streamlit >= 1.42 for the
    native path — `pip install -U streamlit` if the fallback keeps firing.
    """
    kwargs = dict(default=default, key=key, placeholder=placeholder)
    if max_selections:
        kwargs["max_selections"] = max_selections
    try:
        return st.multiselect(label, options=options, accept_new_options=True, **kwargs)
    except TypeError:
        selected = st.multiselect(label, options=options, **kwargs)
        custom = st.text_input(
            f"Add a custom {label.lower()} (press Enter)",
            key=f"{key}_custom",
            placeholder="Not in the list? Type it here.",
        )
        if custom.strip():
            selected = list(dict.fromkeys(selected + [custom.strip()]))
        return selected


def safe_filename_part(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", value or "user")
    return clean.strip("_")[:80] or "user"


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
    st.rerun()


def reset_jd_library_form() -> None:
    for key in ["jd_save_role", "jd_save_text", "jd_save_tags"]:
        st.session_state[key] = ""


def reset_screening_session() -> None:
    """Fully reset the screening session (used by the Screen tab's 'New' button)."""
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
    return str(full_name).split()[0].strip(",")


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
            letter-spacing: 0 !important;
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

        .stButton button,
        .stDownloadButton button,
        [data-testid="stFormSubmitButton"] button {
            transition: background-color 0.22s var(--ease), border-color 0.22s var(--ease),
                        color 0.22s var(--ease), box-shadow 0.22s var(--ease),
                        transform 0.15s var(--ease);
        }
        .stButton button:hover,
        .stDownloadButton button:hover,
        [data-testid="stFormSubmitButton"] button:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
        }
        .stButton button:active,
        .stDownloadButton button:active,
        [data-testid="stFormSubmitButton"] button:active {
            transform: translateY(0) scale(0.98);
            transition-duration: 0.08s;
        }

        [data-baseweb="tab"] {
            transition: color 0.25s var(--ease);
        }
        [data-baseweb="tab-highlight"] {
            transition: left 0.28s var(--ease), width 0.28s var(--ease) !important;
        }
        [data-baseweb="tab-border"] {
            transition: none !important;
        }

        textarea, input, [data-baseweb="select"] > div {
            transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease),
                        background-color 0.2s var(--ease);
        }

        [data-testid="stFileUploaderDropzone"] {
            transition: border-color 0.22s var(--ease), background-color 0.22s var(--ease);
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            border-color: var(--accent);
            background: #0d1015;
        }

        [data-testid="stMetric"], .joy-card {
            transition: transform 0.25s var(--ease), box-shadow 0.25s var(--ease),
                        border-color 0.25s var(--ease);
        }
        [data-testid="stMetric"]:hover, .joy-card:hover {
            transform: translateY(-2px);
            border-color: #2c3444;
        }

        [data-testid="stExpander"] {
            transition: border-color 0.2s var(--ease);
        }
        [data-testid="stExpander"] summary {
            transition: color 0.2s var(--ease);
        }

        [data-testid="stCheckbox"] label span:first-child {
            transition: background-color 0.18s var(--ease), border-color 0.18s var(--ease),
                        box-shadow 0.18s var(--ease);
        }

        [data-testid="stSidebar"] .stButton button {
            transition: background-color 0.2s var(--ease), color 0.2s var(--ease),
                        border-color 0.2s var(--ease);
        }

        [data-testid="stDialog"] > div {
            animation: joy-dialog-in 0.28s var(--ease);
        }
        @keyframes joy-dialog-in {
            from { opacity: 0; transform: scale(0.97) translateY(6px); }
            to   { opacity: 1; transform: scale(1) translateY(0); }
        }

        .stAlert {
            animation: joy-fade-in 0.3s var(--ease);
        }
        @keyframes joy-fade-in {
            from { opacity: 0; transform: translateY(-4px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: 0.001ms !important;
                transition-duration: 0.001ms !important;
            }
        }
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
            transition: background-color 0.18s var(--ease), border-color 0.18s var(--ease),
                        transform 0.15s var(--ease);
        }
        [data-baseweb="tag"]:hover {
            background: rgba(84, 214, 182, 0.22) !important;
            transform: translateY(-1px);
        }

        div[data-baseweb="select"] > div {
            border-radius: 10px !important;
            background: #0b0d11 !important;
            overflow: visible !important;
            padding-left: 10px !important;
            box-sizing: border-box !important;
        }
        div[data-baseweb="select"]:focus-within > div {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 3px rgba(84, 214, 182, 0.14) !important;
        }
        [data-baseweb="select"] [data-baseweb="tag"] {
            margin: 3px 4px 3px 0 !important;
        }
        div[data-baseweb="select"] input {
            position: relative !important;
        }
        [data-baseweb="select"] [data-baseweb="tag"]:first-child {
            margin-left: 2px !important;
        }

        div[data-baseweb="select"] svg {
            fill: var(--muted) !important;
            opacity: 0.7 !important;
            transition: opacity 0.18s var(--ease), fill 0.18s var(--ease);
        }
        div[data-baseweb="select"] svg:hover {
            fill: var(--ink) !important;
            opacity: 1 !important;
        }
        div[data-baseweb="select"] [role="button"] {
            background: transparent !important;
            border-radius: 999px !important;
        }

        [data-baseweb="popover"] {
            animation: joy-dropdown-in 0.16s var(--ease);
        }
        @keyframes joy-dropdown-in {
            from { opacity: 0; transform: translateY(-4px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        [data-baseweb="menu"] li {
            transition: background-color 0.12s var(--ease);
        }

        [data-testid="stExpander"] [data-testid="stNumberInput"] input {
            border-radius: 10px !important;
        }

        [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            transition: opacity 0.2s var(--ease);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_multiselect_chip_fix() -> None:
    try:
        import streamlit.components.v1 as components

        components.html(
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
                        if (control.style.overflow !== "visible") {
                            control.style.overflow = "visible";
                        }
                    });
                }

                fixChipPadding();
                const observer = new MutationObserver(fixChipPadding);
                observer.observe(doc.body, { childList: true, subtree: true });
            })();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def inject_clear_icon_fix() -> None:
    """
    JS-level fallback for the multiselect 'clear all' button — same
    runtime-discovery pattern as inject_multiselect_chip_fix(), since we
    can't rely on a fixed DOM depth from BaseWeb's internals. Belt-and-
    braces alongside the CSS rule in inject_premium_persona_css(); costs
    nothing if the CSS already holds, fixes it if it doesn't.
    """
    try:
        import streamlit.components.v1 as components

        components.html(
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
                        const svgs = control.querySelectorAll('svg');
                        svgs.forEach((svg) => {
                            svg.style.opacity = "0.7";
                        });
                    });
                }

                fixClearIcon();
                const observer = new MutationObserver(fixClearIcon);
                observer.observe(doc.body, { childList: true, subtree: true });
            })();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def inject_keepalive() -> None:
    try:
        import streamlit.components.v1 as components

        components.html(
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
            height=0,
            width=0,
        )
    except Exception:
        pass


def show_results_summary(df: pd.DataFrame) -> None:
    if df.empty:
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Screened", len(df))
    c2.metric("Strong Fit", int((df["Verdict"] == "Strong Fit").sum()))
    c3.metric("Good Fit", int((df["Verdict"] == "Good Fit").sum()))
    c4.metric("Average Score", round(float(df["Final Score"].mean()), 1))

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
