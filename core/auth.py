"""
core/auth.py — Google Sign-In (OIDC) front door + manual payment whitelist.

Replaces the old Gmail-App-Password login. That old flow did two jobs at
once: (1) prove who's using Joy, (2) hand over an SMTP credential to
actually send outreach emails. Google OAuth via st.login() only solves
job (1) — OIDC proves identity, it does not grant authority to act on the
user's behalf (Streamlit's own docs are explicit about this). So job (2)
is deliberately split out: email-sending credentials are now asked for
separately, inside the Email tab, only when someone actually tries to
send something — not as a precondition for using the rest of Joy.

Flow implemented here:
  1. Not signed in            -> Google Sign-In screen
  2. Signed in, not paid      -> paywall: payment link + "email me to get
                                  activated" instructions
  3. Signed in AND whitelisted -> caller proceeds to the real app

Whitelisting is manual by design (per spec): after a Razorpay/Stripe
payment notification, add a row to the `paid_users` Supabase table via
the Supabase dashboard's table editor — no redeploy needed. An
ADMIN_EMAILS secret is also supported as a zero-setup bootstrap fallback
(e.g. your own email), so you're never locked out of your own app if the
whitelist table is briefly unreachable or hasn't been created yet.

Supabase table:
    create table if not exists paid_users (
        email text primary key,
        whitelisted_at timestamptz default now(),
        note text
    );

secrets.toml additions:
    [auth]
    redirect_uri = "http://localhost:8501/oauth2callback"  # or your deployed URL + /oauth2callback
    cookie_secret = "a-long-random-string-you-generate-once"
    client_id = "xxx.apps.googleusercontent.com"
    client_secret = "xxx"
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

    ADMIN_EMAILS = "you@example.com,cofounder@example.com"
    PAYMENT_LINK_URL = "https://rzp.io/l/your-payment-link"
    SUPPORT_EMAIL = "you@example.com"
"""

from typing import Optional

import streamlit as st


def is_auth_configured() -> bool:
    """
    True only if the [auth] block actually exists in secrets. Checking
    this BEFORE touching st.user is what prevents the exact crash this
    was built to fix: st.user.is_logged_in raises AttributeError (not a
    graceful False) when [auth] isn't configured — confirmed against a
    live install, not assumed from docs.
    """
    try:
        return "auth" in st.secrets and bool(st.secrets["auth"].get("client_id"))
    except Exception:
        return False


def is_logged_in() -> bool:
    """Safe wrapper — never raises, even on an unconfigured or half-configured app."""
    if not is_auth_configured():
        return False
    try:
        return bool(st.user.is_logged_in)
    except AttributeError:
        return False


def get_user_email() -> Optional[str]:
    if not is_logged_in():
        return None
    try:
        email = getattr(st.user, "email", None)
        return email.strip().lower() if email else None
    except AttributeError:
        return None


def get_user_name() -> Optional[str]:
    if not is_logged_in():
        return None
    try:
        return getattr(st.user, "name", None)
    except AttributeError:
        return None


def _get_supabase_client():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL") or ""
        key = st.secrets.get("SUPABASE_KEY") or ""
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None


def _admin_emails() -> set[str]:
    try:
        raw = st.secrets.get("ADMIN_EMAILS", "") or ""
    except Exception:
        raw = ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_whitelisted(email: str) -> bool:
    """
    True if this email has paid access. Checks, in order:
      1. ADMIN_EMAILS secret (always-on bootstrap access — you, cofounders)
      2. The `paid_users` Supabase table (the actual manual-whitelist store)

    Fails closed: if Supabase is unreachable or the table doesn't exist
    yet, this returns False for non-admin emails rather than silently
    granting access — a broken whitelist check should never accidentally
    become an open door.
    """
    if not email:
        return False
    email = email.strip().lower()

    if email in _admin_emails():
        return True

    supabase = None
    try:
        supabase = _get_supabase_client()
    except Exception:
        pass
    if not supabase:
        return False

    try:
        response = (
            supabase.table("paid_users")
            .select("email")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return bool(response.data)
    except Exception:
        return False


def add_to_whitelist(email: str, note: str = "") -> bool:
    """
    Convenience function for whitelisting programmatically instead of
    using the Supabase table editor UI directly (either works — this
    exists for a future admin panel, or for one-off use from a Python
    shell). Not wired into the main app UI on purpose: the spec asked
    for manual whitelisting after payment notifications, and putting a
    self-service "add yourself" button in the app would defeat that.
    """
    supabase = _get_supabase_client()
    if not supabase or not email.strip():
        return False
    try:
        supabase.table("paid_users").upsert(
            {"email": email.strip().lower(), "note": note}
        ).execute()
        return True
    except Exception:
        return False


def _render_signin_screen() -> None:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Joy AI Recruiter</div>
            <h1 class="hero-title">Screen once. Ask once.</h1>
            <p class="hero-copy">
                Sign in with Google to continue.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Sign in with Google", type="primary", use_container_width=False):
        st.login()


def _render_paywall(email: str) -> None:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Joy AI Recruiter</div>
            <h1 class="hero-title">Almost there.</h1>
            <p class="hero-copy">
                Your Google account is verified — Joy just needs an active plan
                on this email before you can start screening.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.info(f"Signed in as **{email}**")

    payment_url = ""
    try:
        payment_url = st.secrets.get("PAYMENT_LINK_URL", "") or ""
    except Exception:
        pass

    support_email = ""
    try:
        support_email = st.secrets.get("SUPPORT_EMAIL", "") or ""
    except Exception:
        pass

    if payment_url:
        st.link_button("Get Access", payment_url, type="primary", use_container_width=False)
    else:
        st.warning("Payment link not configured yet — set PAYMENT_LINK_URL in secrets.")

    contact_line = (
        f"After payment, email **{support_email}** with the address above ({email}) "
        "and access will be activated shortly."
        if support_email
        else f"After payment, send your email address ({email}) to get access activated."
    )
    st.caption(contact_line)

    if st.button("Sign out", use_container_width=False):
        st.logout()


def require_paid_access() -> bool:
    """
    Call this once, near the top of app.py, in place of the old
    `if not st.session_state.gmail_authenticated: ... st.stop()` block.

    Returns True and does nothing further if the current user is signed
    in AND whitelisted — the caller should proceed to render the app.
    Otherwise renders the appropriate screen (sign-in or paywall) and
    returns False; the caller should st.stop() in that case.
    """
    if not is_auth_configured():
        st.error(
            "Google Sign-In isn't configured yet. Add an [auth] section to "
            "secrets.toml with your Google OAuth client_id/client_secret, "
            "redirect_uri, and cookie_secret to enable this."
        )
        return False

    if not is_logged_in():
        _render_signin_screen()
        return False

    email = get_user_email()
    if not email:
        st.error("Signed in, but Google didn't return an email address for this account.")
        if st.button("Sign out", use_container_width=False):
            st.logout()
        return False

    if not is_whitelisted(email):
        _render_paywall(email)
        return False

    return True
