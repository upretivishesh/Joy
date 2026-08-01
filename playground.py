import json
import re
import pandas as pd
import streamlit as st

from core.constants import APP_NAME, DATA_DIR, DEFAULT_COMPANY, DEFAULT_QUESTIONS
from core.client_profile import load_client_profile, save_client_profile, list_client_companies
from core.emailer import build_email_body, send_bulk_emails
from core.history import (
    clear_history,
    clear_role_history,
    load_history,
    load_jd_library,
    save_jd,
    delete_jd,
    confirm_delete_role_history,
    confirm_delete_all_history,
    confirm_delete_jd,
    update_feedback,
)
from core.ocr import read_uploaded_file
from core.parser import extract_role_from_jd
from core.screening import run_screening
from core.utils import (
    filter_history_by_search,
    format_experience_years,
    get_secret,
    init_state,
    inject_clear_icon_fix,
    inject_keepalive,
    inject_multiselect_chip_fix,
    inject_premium_persona_css,
    is_auth_configured,       # ← add (guards the crash below)
    is_user_allowed,          # ← add
    login_user_from_google,   # ← add
    logout_user,
    mask_email,
    order_columns_first,
    questions_from_text,
    render_css,
    reset_jd_library_form,
    reset_screening_session,
    show_results_summary,
)

st.set_page_config(page_title=f"{APP_NAME} AI Recruiter", page_icon="J", layout="wide")
render_css()
inject_premium_persona_css()
inject_multiselect_chip_fix()
inject_clear_icon_fix()
inject_keepalive()
init_state()

# ---------- Google OAuth + paid whitelist ----------
if not is_auth_configured():
    st.error(
        "Google Sign-In isn't configured yet. Add an [auth] section to "
        "secrets.toml (client_id, client_secret, redirect_uri, cookie_secret) "
        "to enable this."
    )
    st.stop()

if not st.user.is_logged_in:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Joy AI Recruiter</div>
            <h1 class="hero-title">Screen once. Ask once.</h1>
            <p class="hero-copy">
                Sign in with Google to continue. Only approved (paid) accounts can use the tool.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.button("Sign in with Google", type="primary", on_click=st.login, use_container_width=True)
    st.caption("We only request basic profile + email. No passwords are stored.")
    st.stop()

# At this point the user is authenticated with Google
google_email = (getattr(st.user, "email", None) or "").strip().lower()
google_name = getattr(st.user, "name", "") or ""

if not is_user_allowed(google_email):
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Joy AI Recruiter</div>
            <h1 class="hero-title">Access required</h1>
            <p class="hero-copy">
                This is a paid tool. Complete payment, then message the admin with the exact Google email you used to sign in so it can be whitelisted.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    payment_url = get_secret("PAYMENT_LINK", "")
    if payment_url:
        st.link_button("Pay now (Razorpay / Stripe)", payment_url, type="primary", use_container_width=True)
    else:
        st.warning("Payment link not configured yet. Contact the admin.")
    st.info(f"You are signed in as **{google_email}**. After payment, ask the admin to add this exact address to the whitelist.")
    if st.button("Sign out"):
        logout_user()
    st.stop()

# Whitelisted → finish setting session (App Password still needed for SMTP)
if not st.session_state.gmail_authenticated or st.session_state.sender_email != google_email:
    login_user_from_google(google_email, google_name, st.session_state.get("company_name", DEFAULT_COMPANY))

# One-time / optional App Password prompt (required only when you want to send emails)
if not st.session_state.sender_password:
    with st.expander("Gmail App Password required for sending emails", expanded=True):
        st.caption("Google blocks regular passwords for SMTP. Generate a 16-character App Password: Google Account → Security → 2-Step Verification → App Passwords.")
        app_pw = st.text_input("App Password for the signed-in Gmail", type="password", placeholder="xxxx xxxx xxxx xxxx")
        if st.button("Save App Password", type="primary"):
            clean_pw = re.sub(r"\s+", "", app_pw or "")
            if len(clean_pw) < 16:
                st.error("App Password must be at least 16 characters.")
            else:
                st.session_state.sender_password = clean_pw
                st.success("App Password saved for this session.")
                st.rerun()

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
    st.caption(f"Signed in as {mask_email(st.session_state.sender_email)}")
    if st.button("Sign out", use_container_width=True):
        logout_user()

    st.divider()

    ai_provider = get_secret("AI_PROVIDER", "openai").strip().lower()
    if ai_provider == "anthropic":
        ai_api_key = get_secret("ANTHROPIC_API_KEY")
        ai_model = get_secret("AI_MODEL", "claude-haiku-4-5-20251001")
        provider_label = "Claude"
    else:
        ai_api_key = get_secret("OPENAI_API_KEY")
        ai_model = get_secret("AI_MODEL") or get_secret("OPENAI_MODEL", "gpt-4o-mini")
        provider_label = "OpenAI"

    ai_status = f"{provider_label} scoring enabled ({ai_model})" if ai_api_key else "Heuristic scoring active"
    st.caption(ai_status)
    openai_api_key = ai_api_key
    openai_model = ai_model

    st.divider()
    user_key = st.session_state.sender_email or "local"
    if st.button("Clear current results", use_container_width=True):
        st.session_state.results_df = pd.DataFrame()
        st.session_state.email_results = []
        st.rerun()


st.markdown(
    """
    <section class="hero">
        <div class="eyebrow">Joy AI Recruiter</div>
        <h1 class="hero-title">Screen once. Ask once.</h1>
        <p class="hero-copy">
            Rank resumes against one role, then send a precise email that collects CTC,
            notice period, location, availability, and fit details before any call.
        </p>
    </section>
    """,
    unsafe_allow_html=True,
)

screen_tab, email_tab, history_tab, jd_tab = st.tabs(["Screen", "Email", "History", "JD Library"])
