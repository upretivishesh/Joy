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
    delete_jd,
    confirm_delete_role_history,
    confirm_delete_all_history,
    confirm_delete_jd,
    update_feedback,
)
from core.ocr import read_uploaded_file
from core.parser import extract_role_from_jd
from core.persona_options import INDUSTRY_OPTIONS, LANGUAGE_OPTIONS, merge_with_custom
from core.screening import run_screening
from core.utils import (
    filter_history_by_search,
    format_experience_years,
    format_industry_fit,
    get_secret,
    init_state,
    inject_clear_icon_fix,
    inject_keepalive,
    inject_multiselect_chip_fix,
    inject_premium_persona_css,
    is_auth_configured,
    is_user_allowed,
    login_user_from_google,
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

# ---------- Google OAuth + Manual Whitelist ----------
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
            <div class="eyebrow">Joy AI Recruiter</div>
            <h1 class="hero-title">Screen once. Ask once.</h1>
            <p class="hero-copy">
                Sign in with Google to continue.
            </p>
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
            <div class="eyebrow">Joy AI Recruiter</div>
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

if not st.session_state.sender_password:
    with st.expander("Gmail App Password required for sending emails", expanded=True):
        st.caption(
            "Google blocks regular passwords for SMTP. "
            "Generate a 16-character App Password: "
            "Google Account → Security → 2-Step Verification → App Passwords."
        )
        app_pw = st.text_input(
            "App Password for the signed-in Gmail",
            type="password",
            placeholder="xxxx xxxx xxxx xxxx",
        )
        if st.button("Save App Password", type="primary"):
            clean_pw = re.sub(r"\s+", "", app_pw or "")
            if len(clean_pw) < 16:
                st.error("App Password must be at least 16 characters.")
            else:
                st.session_state.sender_password = clean_pw
                st.success("App Password saved for this session.")
                st.rerun()

# ---------- Sidebar ----------
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

# ====================== SCREEN TAB ======================
with screen_tab:

    pending_jd = st.session_state.pop("_pending_jd_text", None)
    pending_role = st.session_state.pop("_pending_role_input", None)
    if pending_jd is not None:
        st.session_state["typed_jd_text"] = pending_jd
    if pending_role is not None:
        st.session_state["role_input"] = pending_role

    title_col, button_col = st.columns([7.5, 2.5], vertical_alignment="center")

    with title_col:
        st.subheader("Job")
    
    with button_col:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        
        b1, b2 = st.columns(2)
        with b1:
            new_search = st.button("New", key="new_search_btn", use_container_width=True)
        with b2:
            load_demo = st.button("Demo", key="load_demo_btn", use_container_width=True)
    
    if new_search:
        reset_screening_session()
        st.session_state["client_picker"] = "+ New client"
        st.rerun()
    
    if load_demo:
        sample_jd = """R&D Team Leader | Organic Chemistry
    
    Location: Bengaluru
    
    Key Responsibilities
    Lead and mentor a team of R&D scientists.
    Drive process development, optimization, validation, and scale-up.
    Develop cost-effective, commercially viable, and non-infringing manufacturing processes.
    Troubleshoot reaction pathways, process impurities, and purification methods.
    Support technology transfer from R&D to manufacturing.
    Interpret analytical data using NMR, HPLC, GC, Mass Spectrometry, etc.
    Conduct literature and patent searches using SciFinder/Reaxys.
    Prepare technical documentation, cost analysis, and risk assessments.
    Ensure compliance with lab safety, quality, and IP confidentiality.
    
    Requirements
    Ph.D. in Organic Chemistry with 3–5 years of industry experience, or M.Sc. in Chemistry with 12–15 years of industry experience.
    Strong experience in Agrochemical R&D or Process Development.
    Expertise in process optimization, scale-up, and technology transfer.
    Hands-on experience with analytical techniques and purification methods.
    Strong leadership, problem-solving, and project management skills."""
    
        st.session_state["typed_jd_text"] = sample_jd
        st.session_state["role_input"] = "R&D Team Leader | Organic Chemistry"
        st.session_state["client_company_input"] = "Atomgrid"
        st.session_state["client_picker"] = "Atomgrid"
        st.session_state["extra_keywords"] = "organic chemistry, process development, scale-up, NMR, HPLC, agrochemical, SciFinder"
        st.session_state["_demo_loaded"] = True
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
        uploaded_jd_text, jd_error = read_uploaded_file(
            jd_upload.name,
            jd_upload.getvalue(),
        )
        if jd_error:
            st.warning(f"JD upload: {jd_error}")
        if uploaded_jd_text.strip():
            jd_text = uploaded_jd_text
            st.caption(f"Using uploaded JD: {jd_upload.name}")

        # ---------- JD Preview Card (SAFE VERSION) ----------
        if jd_text and jd_text.strip():
            # Always get role safely from session_state
            current_role_input = st.session_state.get("role_input", "")
            
            detected_role = extract_role_from_jd(jd_text, current_role_input)
            
            preview_keywords = extract_keywords(jd_text, limit=10)
            
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div style="padding: 4px 0 2px 0;">
                        <span style="color:#42e8d0; font-weight:700; font-size:0.82rem; letter-spacing:0.06em;">DETECTED ROLE</span>
                        <h3 style="margin:6px 0 8px 0; color:#eef2ff; font-size:1.35rem;">{detected_role}</h3>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                
                if preview_keywords:
                    st.caption("Key requirements:  " + "  ·  ".join(preview_keywords[:8]))
                
                min_exp_detected = parse_min_experience(jd_text)
                if min_exp_detected > 0:
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

        NEW_CLIENT_LABEL = "+ New client"
        client_pick_options = [NEW_CLIENT_LABEL] + known_clients
        current_value = st.session_state.get("client_company_input", "").strip()
        try:
            default_index = (
                client_pick_options.index(current_value)
                if current_value in known_clients
                else 0
            )
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
            picked = NEW_CLIENT_LABEL

        if picked == NEW_CLIENT_LABEL:
            client_company_input = st.text_input(
                "Client name",
                placeholder="e.g. Atomgrid",
                key="client_company_input",
            )
        else:
            client_company_input = picked
            st.session_state["client_company_input"] = picked

        extra_keywords = st.text_input(
            "Must-have keywords",
            placeholder="HPLC, distributor management, SAP",
            key="extra_keywords",
        )

        persona_min_exp: float = 0.0
        persona_max_exp: float = 15.0
        persona_industries: list[str] = []

        if client_company_input.strip():
            company_key = client_company_input.strip().lower()

            if st.session_state.get("_persona_company_key") != company_key:
                st.session_state["_persona_profile"] = load_client_profile(
                    user_key, client_company_input
                )
                st.session_state["_persona_company_key"] = company_key

            profile = st.session_state["_persona_profile"]

            persona_min_exp = float(profile.get("min_experience", 0) or 0)
            persona_max_exp = float(profile.get("max_experience", 15) or 15)
            persona_industries = profile.get("preferred_industries", []) or []

            st.markdown("**Persona**")
            if profile.get("last_updated"):
                st.caption(
                    f"Joy remembers these preferences for this client · last updated {str(profile['last_updated'])[:10]}"
                )
            else:
                st.caption("Joy remembers these preferences for this client")

            col1, col2 = st.columns([1.1, 1])

            with col1:
                current_industries = profile.get("preferred_industries", []) or []
                industry_options = merge_with_custom(INDUSTRY_OPTIONS, current_industries)
                profile["preferred_industries"] = st.multiselect(
                    "Preferred industries",
                    options=industry_options,
                    default=current_industries,
                    key=f"persona_industries_{company_key}",
                    help="Pick one or more industries. Existing custom values are preserved.",
                )
                persona_industries = profile["preferred_industries"]
            
            with col2:
                current_languages = profile.get("language_preferences", []) or []
                language_options = merge_with_custom(LANGUAGE_OPTIONS, current_languages)
                profile["language_preferences"] = st.multiselect(
                    "Language preference",
                    options=language_options,
                    default=current_languages,
                    key=f"persona_languages_{company_key}",
                    help="Pick preferred spoken languages for the client.",
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
                persona_min_exp = float(profile["min_experience"])

            with exp_col2:
                profile["max_experience"] = st.number_input(
                    "Max experience (years)",
                    min_value=0,
                    max_value=40,
                    value=int(profile.get("max_experience", 15) or 15),
                    step=1,
                    key=f"persona_max_exp_{company_key}",
                )
                persona_max_exp = float(profile["max_experience"])

            st.caption(
                "Candidates outside this range take a small score penalty for this client."
            )

            profile["culture_notes"] = st.text_area(
                "Culture / soft-fit notes",
                value=profile.get("culture_notes", ""),
                placeholder="e.g. Strong ownership, comfortable with ambiguity, fast-paced environment...",
                height=130,
                key=f"persona_notes_{company_key}",
            )

            if st.button("Save Persona", type="secondary", use_container_width=True):
                saved_ok = save_client_profile(user_key, client_company_input, profile)
                st.session_state["_persona_save_status"] = (
                    "success" if saved_ok else "error"
                )

                if saved_ok:
                    st.session_state["_persona_profile"] = profile
                    clean_name = client_company_input.strip()
                    if clean_name and clean_name not in st.session_state["_known_clients"]:
                        st.session_state["_known_clients"].insert(0, clean_name)

                st.rerun()

            save_status = st.session_state.pop("_persona_save_status", None)
            if save_status == "success":
                st.success("Persona saved successfully!")
            elif save_status == "error":
                st.error("Failed to save persona.")

    detected_preview = (
        extract_role_from_jd(jd_text, role_input)
        if (jd_text.strip() or role_input.strip())
        else ""
    )
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
        run_clicked = st.button(
            "Screen resumes", type="primary", use_container_width=True
        )

    if run_clicked:
        if not uploads:
            st.error("Upload at least one resume.")
        elif not role_input.strip() and not jd_text.strip():
            st.error(
                "Upload or paste a JD, or add a role override in Optional screening controls."
            )
        else:
            with st.spinner("Screening resumes..."):
                results, read_errors = run_screening(
                    uploads,
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

            detected_role = role_input.strip()
            if results is not None and not results.empty and "Role" in results.columns:
                detected_role = str(results["Role"].iloc[0]) or detected_role

            if results is not None and not results.empty:
                df_ranked = results.copy()
                if "Final Score" in df_ranked.columns:
                    df_ranked = df_ranked.sort_values(
                        "Final Score", ascending=False
                    ).reset_index(drop=True)
                if "Rank" not in df_ranked.columns:
                    df_ranked.insert(0, "Rank", range(1, len(df_ranked) + 1))
                st.session_state.results_df = df_ranked
            else:
                st.session_state.results_df = pd.DataFrame()

            st.session_state.last_role = detected_role
            st.session_state.last_jd = jd_text
            st.session_state.last_keywords = []
            st.session_state.last_client_company = client_company_input

            try:
                from core.history import save_history

                if (
                    st.session_state.results_df is not None
                    and not st.session_state.results_df.empty
                ):
                    save_history(
                        st.session_state.results_df,
                        detected_role,
                        user_key,
                        jd_text,
                    )
            except Exception as _hist_err:
                st.warning(f"History save failed: {_hist_err}")

            st.success(f"Screened {len(results)} resume(s) for {detected_role}.")
            for error in read_errors:
                st.warning(error)

            if (
                ai_api_key
                and results is not None
                and not results.empty
                and "AI Used" in results.columns
                and not results["AI Used"].any()
            ):
                st.warning(
                    f"A {provider_label} key is set, but AI scoring failed for every resume in this batch "
                    "(Industry Match will show N/A). Check the key and model in your secrets."
                )

    if not st.session_state.results_df.empty:
        st.divider()
        st.subheader(f"Results: {st.session_state.last_role}")
        show_results_summary(st.session_state.results_df)


# ====================== EMAIL TAB ======================
with email_tab:
    st.subheader("Outreach")

    if st.session_state.results_df.empty:
        st.caption("Run a screening first.")
    else:
        editable = st.session_state.results_df.copy()

        if "Send" not in editable.columns:
            editable["Send"] = False
        editable["Send"] = editable["Send"].fillna(False).astype(bool)

        for col in ["Experience", "Final Score"]:
            if col in editable.columns:
                editable[col] = pd.to_numeric(editable[col], errors="coerce")

        if "Feedback" not in editable.columns:
            editable["Feedback"] = "Pending"
        editable["Feedback"] = editable["Feedback"].fillna("Pending").replace("", "Pending")

        editable = editable.drop(
            columns=[
                "Reason",
                "Duplicate",
                "Profile Key",
                "Keyword Score",
                "Semantic Score",
            ],
            errors="ignore",
        )

        editable = order_columns_first(
            editable,
            [
                "Rank",
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

        editable = format_experience_years(editable)
        editable = format_industry_fit(editable)

        edited = st.data_editor(
            editable,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=[
                "Rank",
                "Phone",
                "Experience",
                "Education",
                "Final Score",
                "Verdict",
                "Industry Match",
                "Candidate Industry",
                "Matched Keywords",
                "Missing Keywords",
                "Skills",
                "Source File",
                "AI Used",
                "Feedback",
            ],
            column_config={
                "Send": st.column_config.CheckboxColumn("Send"),
                "Email": st.column_config.TextColumn("Email"),
                "Feedback": st.column_config.TextColumn("Feedback"),
            },
            key="email_editor",
        )

        st.caption("Feedback shown here is read-only. Update and save feedback from the History tab.")

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
            st.session_state["email_subject"] = (
                f"Details required for {st.session_state.last_role} opportunity"
            )
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

            with st.expander(
                f"Preview: {st.session_state.selected_candidates.iloc[0]['Name']}",
                expanded=True,
            ):
                st.text_area(
                    "Edit email before sending",
                    height=380,
                    key="edited_email_preview",
                )
                st.caption("Use {first_name} anywhere for automatic personalization.")
                st.caption(
                    "Variables supported: "
                    "{first_name}, {full_name}, {role}, "
                    "{experience}, {score}, {verdict}"
                )

        c1, c2, c3 = st.columns([1.3, 1.5, 3])
        with c1:
            confirm = st.checkbox("Recipient list reviewed")
        with c2:
            send_clicked = st.button(
                f"Send {len(st.session_state.selected_candidates)} email(s)",
                type="primary",
                disabled=st.session_state.selected_candidates.empty
                or not confirm
                or not st.session_state.sender_password,
                use_container_width=True,
            )

        if not missing_email.empty:
            st.warning(
                "Add valid email addresses before sending: "
                + ", ".join(missing_email["Name"].astype(str).tolist())
            )

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
                    status.write(
                        f"Processed {len(st.session_state.selected_candidates)} email(s)"
                    )

                    st.session_state.email_results = email_results
                    sent_count = sum(1 for item in email_results if item["Success"])
                    st.success(f"Sent {sent_count} of {len(email_results)} email(s).")
                    st.dataframe(
                        pd.DataFrame(email_results),
                        use_container_width=True,
                        hide_index=True,
                    )
# ====================== HISTORY TAB ======================
with history_tab:
    st.subheader("History")
    hist = load_history(user_key)

    if hist.empty:
        st.info("No saved screenings yet.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Candidates", len(hist))
        c2.metric(
            "Strong Fit",
            int((hist["Verdict"] == "Strong Fit").sum())
            if "Verdict" in hist.columns
            else 0,
        )
        c3.metric("Roles", hist["Role"].nunique() if "Role" in hist.columns else 0)

        search_query = st.text_input(
            "Search all candidates",
            placeholder="Name, email, phone, skill, or role — searches your entire history at once",
            key="candidate_search",
        )

        selected_role = "all"
        if search_query.strip():
            shown = filter_history_by_search(hist, search_query)
            st.caption(f'{len(shown)} match(es) across all roles for "{search_query.strip()}"')
        elif "Role" in hist.columns:
            roles = ["all"] + sorted(hist["Role"].dropna().unique().tolist())
            selected_role = st.selectbox("Role filter", roles)

            show_limit = st.slider(
                "Show last records",
                min_value=50,
                max_value=500,
                value=150,
                step=50,
            )

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
                    if st.button(
                        f"Delete {selected_role} history",
                        use_container_width=True,
                        type="secondary",
                    ):
                        @st.dialog(f"Delete history for '{selected_role}'?")
                        def delete_role_dialog():
                            st.warning(
                                f"This will permanently delete **all screenings** for the role **{selected_role}**."
                            )
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
                if st.button(
                    "Delete all history",
                    use_container_width=True,
                    type="secondary",
                ):
                    @st.dialog("Delete ALL history?")
                    def delete_all_dialog():
                        st.error(
                            "**Warning:** This will permanently delete **all** screening history."
                        )
                        st.write("This action cannot be undone.")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Cancel", use_container_width=True):
                                st.rerun()
                        with col2:
                            if st.button(
                                "Yes, Delete Everything",
                                type="primary",
                                use_container_width=True,
                            ):
                                confirm_delete_all_history(user_key)

                    delete_all_dialog()
        else:
            shown = hist

        history_editable = shown.copy()

        if "Send" not in history_editable.columns:
            history_editable.insert(0, "Send", False)

        history_editable["Send"] = history_editable["Send"].fillna(False).astype(bool)

        for col in ["Experience", "Final Score"]:
            if col in history_editable.columns:
                history_editable[col] = pd.to_numeric(history_editable[col], errors="coerce")

        for col in history_editable.columns:
            if col not in ["Send", "Experience", "Final Score"]:
                history_editable[col] = history_editable[col].fillna("").astype(str)

        if "Name" in history_editable.columns:
            history_editable["Name"] = history_editable["Name"].str.title()

        history_editable = history_editable.loc[:, ~history_editable.columns.duplicated()]
        history_editable = history_editable.drop(
            columns=[
                "Reason",
                "JD",
                "Duplicate",
                "Keyword Score",
                "Semantic Score",
            ],
            errors="ignore",
        )

        history_editable = format_industry_fit(history_editable)

        history_editable = order_columns_first(
            history_editable,
            [
                "Rank",
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

        history_editable = format_experience_years(history_editable)

        if "Phone" in history_editable.columns:
            history_editable["Phone"] = (
                history_editable["Phone"]
                .fillna("")
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
            )

        if "Feedback" not in history_editable.columns:
            history_editable["Feedback"] = "Pending"
        history_editable["Feedback"] = (
            history_editable["Feedback"].fillna("Pending").replace("", "Pending")
        )

        st.caption("Update feedback in this table, then click 'Save feedback'.")

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
            changed = history_edited[
                history_edited["Feedback"] != history_editable["Feedback"]
            ]
            saved_count = 0
            for _, row in changed.iterrows():
                row_role = row.get("Role", selected_role if selected_role != "all" else "")
                if update_feedback(
                    user_key,
                    row.get("Profile Key", ""),
                    row_role,
                    row["Feedback"],
                ):
                    saved_count += 1
            if saved_count:
                st.success(f"Saved feedback for {saved_count} candidate(s).")
                st.rerun()
            else:
                st.info("No feedback changes to save.")

        st.session_state.selected_history = history_edited[
            history_edited["Send"] == True
        ].copy()

        if not st.session_state.selected_history.empty:
            st.divider()
            st.subheader("Send email from history")

            history_role = (
                selected_role
                if selected_role != "all"
                else st.session_state.selected_history.iloc[0].get(
                    "Role", st.session_state.last_role or "the role"
                )
            )

            history_fingerprint = (
                history_role,
                tuple(st.session_state.selected_history.index.tolist()),
            )
            if st.session_state.get("_history_fingerprint") != history_fingerprint:
                st.session_state["_history_fingerprint"] = history_fingerprint
                st.session_state["history_subject"] = (
                    f"Details required for {history_role} opportunity"
                )
                st.session_state.pop("history_email_preview", None)

            history_subject = st.text_input("Subject", key="history_subject")
            history_questions = st.text_area(
                "Questions to collect",
                value=st.session_state.questions_text,
                height=180,
                key="history_questions",
            )
            history_note = st.text_area(
                "Extra note",
                placeholder="Optional context for candidates",
                height=100,
                key="history_note",
            )

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

            st.text_area(
                "Edit email before sending",
                height=380,
                key="history_email_preview",
            )
            history_confirm = st.checkbox(
                "History recipient list reviewed",
                key="history_confirm",
            )

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
                st.dataframe(
                    pd.DataFrame(history_results),
                    use_container_width=True,
                    hide_index=True,
                )
                
# ====================== JD LIBRARY TAB ======================
# ====================== JD LIBRARY TAB ======================
with jd_tab:
    st.subheader("JD Library")

    if st.session_state.pop("_clear_jd_form", False):
        st.session_state["jd_save_role"] = ""
        st.session_state["jd_save_text"] = ""
        st.session_state["jd_save_tags"] = ""

    jd_df = load_jd_library(user_key)

    if jd_df.empty:
        st.info("No saved JDs yet.")
    else:
        jd_view = jd_df.copy()
        for col in jd_view.columns:
            jd_view[col] = jd_view[col].fillna("").astype(str)
        st.dataframe(jd_view, use_container_width=True, hide_index=True)

    with st.expander("Save current JD", expanded=False):
        default_role = st.session_state.get("last_role", "")
        default_jd = st.session_state.get("last_jd", "")

        if "jd_save_role" not in st.session_state:
            st.session_state["jd_save_role"] = default_role
        if "jd_save_text" not in st.session_state:
            st.session_state["jd_save_text"] = default_jd
        if "jd_save_tags" not in st.session_state:
            st.session_state["jd_save_tags"] = ""

        jd_save_role = st.text_input(
            "Role",
            key="jd_save_role",
        )
        jd_save_text = st.text_area(
            "JD Text",
            height=220,
            key="jd_save_text",
        )
        jd_save_tags = st.text_input(
            "Tags",
            placeholder="e.g. sales, agrochemical, west india",
            key="jd_save_tags",
        )

        save_jd_clicked = st.button("Save JD", type="primary")
        if save_jd_clicked:
            if not jd_save_role.strip() or not jd_save_text.strip():
                st.error("Role and JD text are required.")
            else:
                if save_jd(user_key, jd_save_role, jd_save_text, jd_save_tags):
                    st.success("JD saved.")
                    reset_jd_library_form()
                    st.rerun()
                else:
                    st.error("Could not save JD.")

    if not jd_df.empty:
        st.divider()
        st.subheader("Manage saved JDs")

        jd_options = [
            f"{row['Role']} · {str(row.get('Saved At', ''))[:19]}"
            for _, row in jd_df.iterrows()
        ]
        picked_label = st.selectbox("Saved JDs", jd_options, key="jd_picker")
        picked_index = jd_options.index(picked_label)
        picked_row = jd_df.iloc[picked_index]

        st.caption(
            f"Tags: {picked_row.get('Tags', '') or '—'}"
        )

        preview_jd = str(picked_row.get("JD Text", "") or "")
        st.text_area(
            "Saved JD preview",
            value=preview_jd,
            height=260,
            disabled=True,
        )

        action_col1, action_col2 = st.columns(2)

        with action_col1:
            if st.button("Load into Screen tab", use_container_width=True):
                st.session_state["_pending_jd_text"] = picked_row.get("JD Text", "")
                st.session_state["_pending_role_input"] = picked_row.get("Role", "")
                st.success("JD loaded into Screen tab.")
                st.rerun()

        with action_col2:
            if st.button("Delete JD", use_container_width=True, type="secondary"):
                role_label = str(picked_row.get("Role", "")).strip()

                @st.dialog(f"Delete JD for '{role_label}'?")
                def delete_jd_dialog():
                    st.warning(
                        f"This will permanently delete the saved JD for **{role_label}**."
                    )
                    st.write("This action cannot be undone.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Cancel", use_container_width=True):
                            st.rerun()
                    with col2:
                        if st.button("Yes, Delete JD", type="primary", use_container_width=True):
                            confirm_delete_jd(user_key, role_label)

                delete_jd_dialog()
