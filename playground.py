import re

import pandas as pd
import streamlit as st

from core.constants import APP_NAME, DEFAULT_COMPANY
from core.client_profile import load_client_profile, save_client_profile, list_client_companies
from core.emailer import build_email_body, send_bulk_emails
from core.history import (
    load_history,
    load_jd_library,
    save_jd,
    save_history,
    confirm_delete_role_history,
    confirm_delete_all_history,
    confirm_delete_jd,
    update_feedback,
    filter_history_by_search,
    search_candidates,
)
from core.ocr import read_uploaded_file
from core.parser import extract_role_from_jd, detect_role_title, extract_keywords, parse_min_experience
from core.screening import run_screening
from core.persona_options import INDUSTRY_OPTIONS, LANGUAGE_OPTIONS, merge_with_custom
from core.utils import (
    format_experience_years,
    get_secret,
    init_state,
    inject_elite_theme,
    inject_clear_icon_fix,
    inject_keepalive,
    inject_multiselect_chip_fix,
    is_auth_configured,
    is_user_allowed,
    login_user_from_google,
    logout_user,
    mask_email,
    order_columns_first,
    questions_from_text,
    reset_jd_library_form,
    reset_screening_session,
    show_results_summary,
)


st.set_page_config(page_title=f"{APP_NAME} AI Recruiter", page_icon="J", layout="wide")

inject_elite_theme()
inject_multiselect_chip_fix()
inject_clear_icon_fix()
inject_keepalive()
init_state()


if not is_auth_configured():
    st.error(
        "Google Sign-In is not configured yet. "
        "Add the [auth] section in secrets to enable login."
    )
    st.stop()

if not st.user.is_logged_in:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">JOY AI RECRUITER</div>
            <h1 class="hero-title">Screen once. Ask once.</h1>
            <p class="hero-copy">Sign in with Google to continue.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.button("Sign in with Google", type="primary", on_click=st.login, use_container_width=True)
    st.caption("We only request basic profile + email.")
    st.stop()


google_email = (getattr(st.user, "email", None) or "").strip().lower()
google_name = getattr(st.user, "name", "") or ""

if not is_user_allowed(google_email):
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">JOY AI RECRUITER</div>
            <h1 class="hero-title">Access required</h1>
            <p class="hero-copy">
                This is a paid tool.<br><br>
                Pay via UPI / Bank Transfer / any method and send your Google email to the admin.<br>
                Access will be enabled within a few minutes.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.info(f"You are signed in as **{google_email}**")
    st.write("After payment, just message this exact email to the admin.")
    if st.button("Sign out"):
        logout_user()
    st.stop()

if not st.session_state.gmail_authenticated or st.session_state.sender_email != google_email:
    login_user_from_google(
        google_email,
        google_name,
        st.session_state.get("company_name", DEFAULT_COMPANY),
    )

st.markdown(
    """
    <section class="hero">
        <div class="eyebrow">JOY AI RECRUITER</div>
        <h1 class="hero-title">Screen once. Ask once.</h1>
        <p class="hero-copy">
            Rank resumes against one role, then send a precise email that collects CTC,
            notice period, location, availability, and fit details before any call.
        </p>
    </section>
    """,
    unsafe_allow_html=True,
)

if not st.session_state.sender_password:
    st.markdown(
        """
        <div class="joy-card" style="margin-bottom: 1.25rem;">
            <div style="font-weight:700; font-size:1.02rem; margin-bottom:0.45rem; color: var(--ink);">
                Gmail App Password required for sending emails
            </div>
            <div style="color: var(--muted); line-height: 1.6; margin-bottom: 0.9rem;">
                Google blocks regular passwords for SMTP.
                Generate a 16-character App Password after enabling 2-Step Verification.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("[Generate Google App Password](https://myaccount.google.com/apppasswords)")
    st.caption("This is saved only for this session and is cleared on refresh/restart.")
    app_pw = st.text_input(
        "App Password for the signed-in Gmail",
        type="password",
        placeholder="xxxx xxxx xxxx xxxx",
        key="gmail_app_password_input",
    )
    if st.button("Save App Password", type="primary"):
        clean_pw = re.sub(r"\s+", "", app_pw or "")
        if len(clean_pw) < 16:
            st.error("App Password must be at least 16 characters.")
        else:
            st.session_state.sender_password = clean_pw
            st.success("App Password saved for this session.")
            st.rerun()
else:
    st.success("App Password is already saved for this session.")

with st.sidebar:
    st.title("Joy")
    st.caption("AI Recruiter · Screen. Select. Send.")

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

    st.caption(f"Signed in as {mask_email(st.session_state.sender_email)}")
    if st.button("Sign out", use_container_width=True):
        logout_user()

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

    user_key = st.session_state.sender_email or "local"
    if st.button("Clear current results", use_container_width=True):
        st.session_state.results_df = pd.DataFrame()
        st.session_state.email_results = []
        st.rerun()

screen_tab, email_tab, history_tab, lookup_tab, jd_tab = st.tabs(
    ["Screen", "Email", "History", "Candidate Lookup", "JD Library"]
)

with screen_tab:
    pending_jd = st.session_state.pop("_pending_jd_text", None)
    pending_role = st.session_state.pop("_pending_role_input", None)
    if pending_jd is not None:
        st.session_state["typed_jd_text"] = pending_jd
    if pending_role is not None:
        st.session_state["role_input"] = pending_role

    title_col, button_col = st.columns([8.5, 1.5], vertical_alignment="center")
    with title_col:
        st.subheader("Job")
    with button_col:
        new_search = st.button("New", key="new_search_btn", use_container_width=True)

    if new_search:
        reset_screening_session()
        st.session_state["client_picker"] = "+ New client"
        st.rerun()

    jd_upload = st.file_uploader(
        "Upload JD",
        type=["pdf", "docx", "txt"],
        key=f"jd_upload_{st.session_state.upload_session}",
    )

    typed_jd_text = st.text_area(
        "Or paste JD",
        height=190,
        placeholder="Paste the job description or role requirements here. Joy will detect the title automatically.",
        key="typed_jd_text",
    )

    jd_text = typed_jd_text
    if jd_upload:
        uploaded_jd_text, jd_error = read_uploaded_file(jd_upload.name, jd_upload.getvalue())
        if jd_error:
            st.warning(f"JD upload: {jd_error}")
        if uploaded_jd_text.strip():
            jd_text = uploaded_jd_text
            st.caption(f"Using uploaded JD: {jd_upload.name}")

    # ---------- JD Preview Card ----------
    if jd_text and jd_text.strip():
        current_role_input = st.session_state.get("role_input", "")
        detected_role_preview = extract_role_from_jd(jd_text, current_role_input)
        preview_keywords = extract_keywords(jd_text, limit=10)

        with st.container(border=True):
            st.markdown(
                f"""
                <div style="padding: 4px 0 2px 0;">
                    <span style="color:#42e8d0; font-weight:700; font-size:0.82rem; letter-spacing:0.06em;">DETECTED ROLE</span>
                    <h3 style="margin:6px 0 8px 0; color:#eef2ff; font-size:1.35rem;">{detected_role_preview}</h3>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if preview_keywords:
                st.caption("Key requirements:  " + "  ·  ".join(preview_keywords[:8]))
            min_exp_detected = parse_min_experience(jd_text)
            if min_exp_detected and min_exp_detected > 0:
                st.caption(f"Minimum experience detected: **{min_exp_detected:g}+ years**")

    with st.expander("Optional screening controls + Persona", expanded=False):
        role_input = st.text_input(
            "Role title override",
            placeholder="Leave blank. Joy will detect it from the JD.",
            key="role_input",
        )

        if "_known_clients" not in st.session_state:
            st.session_state["_known_clients"] = list_client_companies(user_key)
        known_clients = st.session_state["_known_clients"]

        new_client_label = "+ New client"
        client_pick_options = [new_client_label] + known_clients
        current_value = st.session_state.get("client_company_input", "").strip()
        try:
            default_index = client_pick_options.index(current_value) if current_value in known_clients else 0
        except ValueError:
            default_index = 0

        if known_clients:
            picked = st.selectbox(
                "Client",
                options=client_pick_options,
                index=default_index,
                key="client_picker",
                help="Pick a client Joy already has a persona for, or add a new one.",
            )
        else:
            picked = new_client_label

        if picked == new_client_label:
            client_company_input = st.text_input("Client name", placeholder="e.g. Atomgrid", key="client_company_input")
        else:
            client_company_input = picked
            st.session_state["client_company_input"] = picked

        extra_keywords = st.text_input(
            "Must-have keywords",
            placeholder="HPLC, distributor management, SAP",
            key="extra_keywords",
        )

        persona_min_exp = 0
        persona_max_exp = 15
        persona_industries = []

        if client_company_input.strip():
            company_key = client_company_input.strip().lower()

            if st.session_state.get("_persona_company_key") != company_key:
                st.session_state["_persona_profile"] = load_client_profile(user_key, client_company_input)
                st.session_state["_persona_company_key"] = company_key
            profile = st.session_state["_persona_profile"]

            st.markdown("**Persona**")
            if profile.get("last_updated"):
                st.caption(f"Joy remembers these preferences for this client · last updated {str(profile['last_updated'])[:10]}")
            else:
                st.caption("Joy remembers these preferences for this client")

            industry_options = merge_with_custom(INDUSTRY_OPTIONS, profile.get("preferred_industries", []))
            language_options = merge_with_custom(LANGUAGE_OPTIONS, profile.get("language_preferences", []))

            col1, col2 = st.columns([1.1, 1])
            with col1:
                profile["preferred_industries"] = st.multiselect(
                    "Preferred industries",
                    options=industry_options,
                    default=profile.get("preferred_industries", []),
                    key=f"persona_industries_{company_key}",
                    help="Select likely-fit industries for this client. You can also add custom values.",
                    accept_new_options=True,
                )
            with col2:
                profile["language_preferences"] = st.multiselect(
                    "Language preference",
                    options=language_options,
                    default=profile.get("language_preferences", []),
                    key=f"persona_languages_{company_key}",
                    help="Select preferred spoken languages for this client.",
                    accept_new_options=True,
                )

            profile["preferred_colleges"] = st.text_area(
                "Preferred colleges / tiers",
                value=profile.get("preferred_colleges", ""),
                placeholder="e.g. IITs, NITs, Top B-schools, or specific colleges...",
                height=110,
                key=f"persona_colleges_{company_key}",
            )

            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                profile["min_experience"] = st.number_input(
                    "Min experience (years)",
                    min_value=0,
                    max_value=30,
                    value=int(profile.get("min_experience", 0) or 0),
                    step=1,
                    key=f"persona_min_exp_{company_key}",
                )
            with exp_col2:
                profile["max_experience"] = st.number_input(
                    "Max experience (years)",
                    min_value=0,
                    max_value=40,
                    value=int(profile.get("max_experience", 15) or 15),
                    step=1,
                    key=f"persona_max_exp_{company_key}",
                )
            st.caption("Candidates outside this range take a small score penalty for this client.")

            profile["culture_notes"] = st.text_area(
                "Culture / soft-fit notes",
                value=profile.get("culture_notes", ""),
                placeholder="e.g. Strong ownership, comfortable with ambiguity, fast-paced environment...",
                height=130,
                key=f"persona_notes_{company_key}",
            )

            if st.button("Save Persona", type="secondary", use_container_width=True):
                if save_client_profile(user_key, client_company_input, profile):
                    st.session_state["_persona_profile"] = profile
                    if client_company_input.strip() not in st.session_state["_known_clients"]:
                        st.session_state["_known_clients"].insert(0, client_company_input.strip())
                    st.success("Persona saved successfully!")
                else:
                    st.error("Failed to save persona.")

            persona_min_exp = profile.get("min_experience", 0) or 0
            persona_max_exp = profile.get("max_experience", 15) or 15
            persona_industries = profile.get("preferred_industries", [])
        else:
            client_company_input = ""

    detected_preview = extract_role_from_jd(jd_text, role_input) if (jd_text.strip() or role_input.strip()) else ""
    if detected_preview and detected_preview != "Open Role":
        st.caption(f"Detected role title: {detected_preview}")

    uploads = st.file_uploader(
        "Upload resumes",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key=f"resume_uploads_{st.session_state.upload_session}",
    )

    run_col, _ = st.columns([1, 4])
    with run_col:
        run_clicked = st.button("Screen resumes", type="primary", use_container_width=True)

    if run_clicked:
        if not uploads:
            st.error("Upload at least one resume.")
        elif not role_input.strip() and not jd_text.strip():
            st.error("Upload or paste a JD, or add a role override in Optional screening controls.")
        else:
            with st.spinner("Screening resumes..."):
                results, read_errors = run_screening(
                    uploads=uploads,
                    jd_text=jd_text,
                    role_input=role_input,
                    extra_keywords=extra_keywords,
                    api_key=ai_api_key,
                    model=ai_model,
                    user_key=user_key,
                    client_company=client_company_input,
                    min_exp=persona_min_exp,
                    max_exp=persona_max_exp,
                    preferred_industries=persona_industries,
                )

            if results is not None and not results.empty:
                results = results.reset_index(drop=True)
                if "Candidate Industry" in results.columns:
                    results["Candidate Industry"] = (
                        results["Candidate Industry"]
                        .fillna("")
                        .astype(str)
                        .replace({"": "Others / Not Detected", "nan": "Others / Not Detected"})
                    )
                if "Industry Match" in results.columns:
                    results["Industry Match"] = (
                        results["Industry Match"]
                        .fillna("NA")
                        .astype(str)
                        .replace({"": "NA", "nan": "NA"})
                    )
                if "Reason" in results.columns:
                    results["Reason"] = (
                        results["Reason"]
                        .fillna("")
                        .astype(str)
                        .replace({"nan": ""})
                    )
                if "Rank" not in results.columns:
                    results.insert(0, "Rank", range(1, len(results) + 1))
                if "Send" not in results.columns:
                    results.insert(1, "Send", False)

                detected_role = (
                    results["Role"].iloc[0]
                    if "Role" in results.columns and results["Role"].notna().any()
                    else (role_input.strip() or detect_role_title(jd_text) or "Open Role")
                )

                st.session_state.results_df = results
                st.session_state.last_role = detected_role
                st.session_state.last_jd = jd_text

                # Explicit history save (safe)
                try:
                    ok = save_history(results, detected_role, user_key, jd_text)
                    if not ok:
                        st.warning(
                            "Screening finished, but history was **not** saved. "
                            "Check logs / Supabase."
                        )
                except Exception as _hist_err:
                    st.warning(f"History save failed: {_hist_err}")
            else:
                st.session_state.results_df = pd.DataFrame()
                st.session_state.last_role = role_input.strip() or detect_role_title(jd_text) or "Open Role"
                st.session_state.last_jd = jd_text

            st.success(f"Screened {len(results) if results is not None else 0} resume(s) for {st.session_state.last_role}.")
            for error in read_errors:
                st.warning(error)

            if (
                ai_api_key and results is not None and not results.empty
                and "AI Used" in results.columns and not results["AI Used"].any()
            ):
                st.warning(
                    f"A {provider_label} key is set, but AI scoring failed for every resume in this batch "
                    "(Industry Match will show N/A). Check the key and model in your secrets."
                )

    if not st.session_state.results_df.empty:
        st.divider()
        st.subheader(f"Results: {st.session_state.last_role}")
        show_results_summary(st.session_state.results_df)

        # Quick ranked view (read-only)
        display_cols = [
            c for c in [
                "Rank", "Name", "Email", "Phone", "Experience",
                "Final Score", "Verdict", "Industry Match", "Matched Keywords"
            ] if c in st.session_state.results_df.columns
        ]
        if display_cols:
            preview_df = st.session_state.results_df[display_cols].copy()
            preview_df = format_experience_years(preview_df)
            st.dataframe(
                preview_df,
                use_container_width=True,
                hide_index=True,
                height=380,
            )
            st.caption("Go to the **Email** tab to select candidates and send outreach.")

with email_tab:
    st.subheader("Outreach")

    if st.session_state.results_df.empty:
        st.info("Run a screening first.")
    else:
        editable = st.session_state.results_df.copy()
        editable["Send"] = editable["Send"].astype(bool)
        editable = editable.drop(columns=["Reason", "Duplicate", "Profile Key"], errors="ignore")
        editable = order_columns_first(editable, ["Rank", "Send", "Name", "Email", "Phone", "Experience", "Verdict"])
        editable = format_experience_years(editable)

        edited = st.data_editor(
            editable,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=[
                "Rank", "Phone", "Experience", "Keyword Score", "Final Score",
                "Verdict", "Industry Match", "Candidate Industry", "Matched Keywords",
                "Missing Keywords", "Skills", "Source File", "AI Used",
            ],
            column_config={
                "Send": st.column_config.CheckboxColumn("Send"),
                "Email": st.column_config.TextColumn("Email"),
            },
            key="email_editor",
        )

        st.session_state.selected_candidates = edited[edited["Send"] == True].copy()
        missing_email = st.session_state.selected_candidates[
            ~st.session_state.selected_candidates["Email"].astype(str).str.contains("@", na=False)
        ]

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

        email_fingerprint = (
            st.session_state.last_role,
            tuple(st.session_state.selected_candidates.index.tolist()),
        )
        if st.session_state.get("_email_fingerprint") != email_fingerprint:
            st.session_state["_email_fingerprint"] = email_fingerprint
            st.session_state["email_subject"] = f"Details required for {st.session_state.last_role} opportunity"
            st.session_state.pop("edited_email_preview", None)

        subject = st.text_input("Subject", key="email_subject")
        questions = questions_from_text(st.session_state.questions_text)

        if not st.session_state.selected_candidates.empty:
            preview_body = build_email_body(
                st.session_state.selected_candidates.iloc[0],
                st.session_state.last_role,
                st.session_state.sender_name,
                st.session_state.company_name,
                questions,
                extra_note,
                template_mode=True,
            )
            if "edited_email_preview" not in st.session_state:
                st.session_state["edited_email_preview"] = preview_body

            with st.expander(f"Preview: {st.session_state.selected_candidates.iloc[0]['Name']}", expanded=True):
                st.text_area("Edit email before sending", height=380, key="edited_email_preview")
                st.caption("Use {first_name} anywhere for automatic personalization.")
                st.caption("Variables supported: {first_name}, {full_name}, {role}, {experience}, {score}, {verdict}")

        c1, c2, _ = st.columns([1.3, 1.5, 3])
        with c1:
            confirm = st.checkbox("Recipient list reviewed")
        with c2:
            send_clicked = st.button(
                f"Send {len(st.session_state.selected_candidates)} email(s)",
                type="primary",
                disabled=st.session_state.selected_candidates.empty or not confirm or not st.session_state.sender_password,
                use_container_width=True,
            )

        if not missing_email.empty:
            st.warning("Add valid email addresses before sending: " + ", ".join(missing_email["Name"].astype(str).tolist()))

        if not st.session_state.sender_password:
            st.error("App Password is required to send emails. Add it above.")

        if send_clicked:
            if not st.session_state.sender_email or not st.session_state.sender_password:
                st.error("App Password missing. Please add it first.")
            elif not st.session_state.sender_name:
                st.error("Add sender name in the sidebar.")
            elif not missing_email.empty:
                st.error("Fix missing candidate email addresses first.")
            else:
                custom_email_body = st.session_state.get("edited_email_preview", "").strip()
                with st.spinner("Sending emails..."):
                    progress = st.progress(0)
                    status = st.empty()
                    email_results = send_bulk_emails(
                        selected_df=st.session_state.selected_candidates,
                        role=st.session_state.last_role,
                        sender_email=st.session_state.sender_email,
                        sender_password=st.session_state.sender_password,
                        sender_name=st.session_state.sender_name,
                        company_name=st.session_state.company_name,
                        subject=subject,
                        questions=questions,
                        extra_note=extra_note,
                        custom_body=custom_email_body,
                    )
                    progress.progress(1.0)
                    status.write(f"Processed {len(st.session_state.selected_candidates)} email(s)")
                    st.session_state.email_results = email_results
                    sent_count = sum(1 for item in email_results if item["Success"])
                    st.success(f"Sent {sent_count} of {len(email_results)} email(s).")
                    st.dataframe(pd.DataFrame(email_results), use_container_width=True, hide_index=True)

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

        search_query = st.text_input(
            "Search all candidates",
            placeholder="Name, email, phone, skill, or role — searches your entire history at once",
            key="candidate_search",
        )

        selected_role = "all"
        if search_query.strip():
            shown = filter_history_by_search(hist, search_query)
            st.caption(f"{len(shown)} match(es) across all roles for \"{search_query.strip()}\"")
        elif "Role" in hist.columns:
            roles = ["all"] + sorted(hist["Role"].dropna().unique().tolist())
            selected_role = st.selectbox("Role filter", roles)

            show_limit = st.slider("Show last records", min_value=50, max_value=500, value=150, step=50)

            shown = hist if selected_role == "all" else hist[hist["Role"] == selected_role]
            shown = shown.tail(show_limit) if len(shown) > show_limit else shown

            if selected_role != "all" and "JD" in shown.columns:
                saved_jds = shown["JD"].dropna().astype(str)
                saved_jds = saved_jds[saved_jds.str.strip() != ""]
                if not saved_jds.empty:
                    latest_jd = saved_jds.iloc[-1]
                    already_loaded = (
                        st.session_state.get("_history_loaded_role") == selected_role
                        and st.session_state.get("_history_loaded_jd") == latest_jd
                    )
                    if not already_loaded:
                        st.session_state["_pending_jd_text"] = latest_jd
                        st.session_state["_pending_role_input"] = selected_role
                        st.session_state["_history_loaded_role"] = selected_role
                        st.session_state["_history_loaded_jd"] = latest_jd
                        st.rerun()

            delete_col1, delete_col2 = st.columns(2)
            with delete_col1:
                if selected_role != "all":
                    if st.button(f"Delete {selected_role} history", use_container_width=True, type="secondary"):
                        @st.dialog(f"Delete history for '{selected_role}'?")
                        def delete_role_dialog():
                            st.warning(f"This will permanently delete **all screenings** for the role **{selected_role}**.")
                            st.write("This action cannot be undone.")
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Cancel", use_container_width=True):
                                    st.rerun()
                            with col2:
                                if st.button("Yes", type="primary", use_container_width=True):
                                    confirm_delete_role_history(user_key, selected_role)
                        delete_role_dialog()
            with delete_col2:
                if st.button("Delete all history", use_container_width=True, type="secondary"):
                    @st.dialog("Delete ALL history?")
                    def delete_all_dialog():
                        st.error("**Warning:** This will permanently delete **all** screening history.")
                        st.write("This action cannot be undone.")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Cancel", use_container_width=True):
                                st.rerun()
                        with col2:
                            if st.button("Yes, Delete Everything", type="primary", use_container_width=True):
                                confirm_delete_all_history(user_key)
                    delete_all_dialog()
        else:
            shown = hist

        history_editable = shown.copy()
        if "Candidate Industry" in history_editable.columns:
            history_editable["Candidate Industry"] = (
                history_editable["Candidate Industry"]
                .fillna("")
                .astype(str)
                .replace({"": "Others / Not Detected", "nan": "Others / Not Detected"})
            )
        if "Industry Match" in history_editable.columns:
            history_editable["Industry Match"] = (
                history_editable["Industry Match"]
                .fillna("NA")
                .astype(str)
                .replace({"": "NA", "nan": "NA"})
            )
        if "Send" not in history_editable.columns:
            history_editable.insert(0, "Send", False)
        history_editable["Send"] = history_editable["Send"].fillna(False).astype(bool)

        for col in ["Experience", "Keyword Score", "Final Score"]:
            if col in history_editable.columns:
                history_editable[col] = pd.to_numeric(history_editable[col], errors="coerce")

        for col in history_editable.columns:
            if col not in ["Send", "Experience", "Keyword Score", "Final Score"]:
                history_editable[col] = history_editable[col].fillna("").astype(str)

        if "Name" in history_editable.columns:
            history_editable["Name"] = history_editable["Name"].str.title()

        history_editable = history_editable.loc[:, ~history_editable.columns.duplicated()]
        history_editable = history_editable.drop(columns=["Reason", "JD", "Duplicate"], errors="ignore")

        if selected_role != "all":
            history_editable = history_editable.drop(columns=["Role"], errors="ignore")

        history_editable = order_columns_first(history_editable, ["Rank", "Send", "Name", "Email", "Phone", "Experience", "Verdict", "Feedback"])
        history_editable = format_experience_years(history_editable)

        if "Feedback" not in history_editable.columns:
            history_editable["Feedback"] = "Pending"
        history_editable["Feedback"] = history_editable["Feedback"].replace("", "Pending")

        history_edited = st.data_editor(
            history_editable,
            height=500,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            key="history_editor",
            column_config={
                "Send": st.column_config.CheckboxColumn("Send"),
                "Email": st.column_config.TextColumn("Email"),
                "Profile Key": None,
                "Feedback": st.column_config.SelectboxColumn(
                    "Feedback",
                    options=[
                        "Pending",
                        "Interviewed",
                        "Shortlisted",
                        "Hired",
                        "Rejected",
                        "Do Not Consider",
                    ],
                ),
            },
        )

        if st.button("Save feedback", use_container_width=False):
            changed = history_edited[history_edited["Feedback"] != history_editable["Feedback"]]
            saved_count = 0
            for _, row in changed.iterrows():
                row_role = row.get("Role", selected_role if selected_role != "all" else "")
                if update_feedback(user_key, row.get("Profile Key", ""), row_role, row["Feedback"]):
                    saved_count += 1
            if saved_count:
                st.success(f"Saved feedback for {saved_count} candidate(s).")
            else:
                st.info("No feedback changes to save.")

        st.session_state.selected_history = history_edited[history_edited["Send"] == True].copy()

        if not st.session_state.selected_history.empty:
            st.divider()
            st.subheader("Send email from history")

            history_role = (
                selected_role if selected_role != "all"
                else st.session_state.selected_history.iloc[0].get("Role", st.session_state.last_role or "the role")
            )

            history_fingerprint = (history_role, tuple(st.session_state.selected_history.index.tolist()))
            if st.session_state.get("_history_fingerprint") != history_fingerprint:
                st.session_state["_history_fingerprint"] = history_fingerprint
                st.session_state["history_subject"] = f"Details required for {history_role} opportunity"
                st.session_state.pop("history_email_preview", None)

            history_subject = st.text_input("Subject", key="history_subject")
            history_questions = st.text_area("Questions to collect", value=st.session_state.questions_text, height=180, key="history_questions")
            history_note = st.text_area("Extra note", placeholder="Optional context for candidates", height=100, key="history_note")

            parsed_questions = questions_from_text(history_questions)

            preview_body = build_email_body(
                st.session_state.selected_history.iloc[0],
                history_role,
                st.session_state.sender_name,
                st.session_state.company_name,
                parsed_questions,
                history_note,
                template_mode=True,
            )

            if "history_email_preview" not in st.session_state:
                st.session_state["history_email_preview"] = preview_body

            st.text_area("Edit email before sending", height=380, key="history_email_preview")
            history_confirm = st.checkbox("History recipient list reviewed", key="history_confirm")

            send_history = st.button(
                f"Send {len(st.session_state.selected_history)} email(s)",
                type="primary",
                disabled=not history_confirm or not st.session_state.sender_password,
                key="send_history_btn",
            )

            if send_history:
                custom_body = st.session_state.get("history_email_preview", "").strip()
                with st.spinner("Sending emails from history..."):
                    history_results = send_bulk_emails(
                        selected_df=st.session_state.selected_history,
                        role=history_role,
                        sender_email=st.session_state.sender_email,
                        sender_password=st.session_state.sender_password,
                        sender_name=st.session_state.sender_name,
                        company_name=st.session_state.company_name,
                        subject=history_subject,
                        questions=parsed_questions,
                        extra_note=history_note,
                        custom_body=custom_body,
                    )
                sent_count = sum(1 for item in history_results if item["Success"])
                st.success(f"Sent {sent_count} of {len(history_results)} email(s).")
                st.dataframe(pd.DataFrame(history_results), use_container_width=True, hide_index=True)

with lookup_tab:
    st.subheader("Candidate Lookup")
    st.caption("Search any candidate ever screened — across every role and every client — and see their full timeline.")

    lookup_query = st.text_input(
        "Search by name, email, or phone",
        placeholder="e.g. Vishesh Sharma, vishesh@gmail.com, or 98765...",
        key="lookup_query",
    )

    if lookup_query.strip():
        matches = search_candidates(user_key)

        if matches.empty:
            st.info("No candidate found matching that search.")
        else:
            unique_people = matches.drop_duplicates(subset=["Profile Key"]) if "Profile Key" in matches.columns else matches
            st.caption(f"{len(unique_people)} unique candidate(s), {len(matches)} total screening record(s) found.")

            group_col = "Profile Key" if "Profile Key" in matches.columns else "Name"
            for _, group in matches.groupby(group_col, sort=False):
                display_name = str(group.iloc[0].get("Name", "Unknown Candidate")).title()
                display_email = str(group.iloc[0].get("Email", ""))
                display_phone = str(group.iloc[0].get("Phone", ""))

                with st.expander(f"{display_name} · {display_email or display_phone or 'No contact info'}", expanded=len(unique_people) == 1):
                    contact_c1, contact_c2, contact_c3 = st.columns(3)
                    contact_c1.metric("Screenings", len(group))
                    good_hires = int((group.get("Feedback", pd.Series(dtype=str)) == "Hired").sum())
                    bad_hires = int(
                        group.get("Feedback", pd.Series(dtype=str))
                        .isin(["Rejected", "Do Not Consider"])
                        .sum()
                    )
                    contact_c2.metric("Hired", good_hires)
                    contact_c3.metric("Rejected / DNC", bad_hires)

                    timeline = group.sort_values("Screened At", ascending=False) if "Screened At" in group.columns else group

                    for _, row in timeline.iterrows():
                        role = row.get("Role", "Unknown Role")
                        client = row.get("Client", "")
                        screened_at = str(row.get("Screened At", ""))[:16]
                        feedback = str(row.get("Feedback", "Pending") or "Pending")

                        badge_class = "badge-pending"
                        if feedback == "Hired":
                            badge_class = "badge-good"
                        elif feedback in ("Rejected", "Do Not Consider"):
                            badge_class = "badge-bad"

                        st.markdown(
                            f"""
                            <div class="timeline-card">
                                <div class="tc-role">{role}{f' · {client}' if client else ''}</div>
                                <div class="tc-meta">Screened {screened_at}</div>
                                <span class="tc-badge {badge_class}">{feedback}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
    else:
        st.info("Type a name, email, or phone number above to look up a candidate's full history.")

with jd_tab:
    col1, col2 = st.columns([8.5, 1.5], vertical_alignment="center")
    with col1:
        st.subheader("JD Library")
    with col2:
        if st.button("New screening", key="jd_new_btn", use_container_width=True):
            reset_jd_library_form()
            st.rerun()

    jd_lib = load_jd_library(user_key)

    if "jd_save_role" not in st.session_state:
        st.session_state["jd_save_role"] = st.session_state.get("last_role", "")

    save_role = st.text_input("Role title", placeholder="e.g. Assistant Manager Supply", key="jd_save_role")

    if "jd_save_text" not in st.session_state:
        st.session_state["jd_save_text"] = st.session_state.get("last_jd", "")

    save_jd_text = st.text_area(
        "JD text",
        height=200,
        placeholder="Paste JD here or it auto-fills from your last screening.",
        key="jd_save_text",
    )

    save_tags = st.text_input("Tags (optional)", placeholder="e.g. agrochemicals, bangalore, urgent", key="jd_save_tags")

    if st.button("Save to JD Library", type="primary", use_container_width=False):
        if not save_role.strip():
            st.error("Add a role title before saving.")
        elif not save_jd_text.strip():
            st.error("JD text is empty.")
        else:
            success = save_jd(user_key, save_role, save_jd_text, save_tags)
            if success:
                st.success(f"Saved: {save_role}")
                st.rerun()
            else:
                st.error("Could not save. Check role title and JD text.")

    st.divider()
    st.markdown("**Saved JDs**")

    if jd_lib.empty:
        st.info("No JDs saved yet. Run a screening or paste a JD above to save it.")
    else:
        search_query = st.text_input("Search", placeholder="Filter by role or tags", key="jd_search")
        display_df = jd_lib.copy()
        if search_query.strip():
            mask = (
                display_df["Role"].astype(str).str.lower().str.contains(search_query.lower(), na=False)
                | display_df.get("Tags", pd.Series(dtype=str)).astype(str).str.lower().str.contains(search_query.lower(), na=False)
            )
            display_df = display_df[mask]

        if display_df.empty:
            st.info("No JDs match that search.")
        else:
            for _, row in display_df.iterrows():
                role_label = str(row.get("Role", ""))
                saved_at = str(row.get("Saved At", ""))
                tags = str(row.get("Tags", ""))
                jd_preview = str(row.get("JD Text", ""))[:180].replace("\n", " ")

                title = f"{role_label} · {saved_at[:10]}"
                if tags and tags != "nan":
                    title += f" · {tags}"

                with st.expander(title):
                    st.caption(jd_preview + ("..." if len(str(row.get("JD Text", ""))) > 180 else ""))
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Load into screener", key=f"load_jd_{role_label}", use_container_width=True):
                            st.session_state["_pending_jd_text"] = str(row.get("JD Text", ""))
                            st.session_state["_pending_role_input"] = role_label
                            st.rerun()
                    with c2:
                        if st.button("Delete", key=f"delete_jd_{role_label}", use_container_width=True):
                            @st.dialog(f"Delete JD '{role_label}'?")
                            def delete_jd_dialog():
                                st.warning(f"This will permanently delete the saved JD **{role_label}** from your library.")
                                st.write("This action cannot be undone.")
                                col1, col2 = st.columns(2)
                                with col1:
                                    if st.button("Cancel", use_container_width=True):
                                        st.rerun()
                                with col2:
                                    if st.button("Yes, Delete JD", type="primary", use_container_width=True):
                                        confirm_delete_jd(user_key, role_label)
                            delete_jd_dialog()

        st.divider()
        st.caption(f"{len(jd_lib)} JD(s) saved in your library.")
