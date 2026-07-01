import pandas as pd
import streamlit as st

from core.constants import APP_NAME, DEFAULT_COMPANY
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
)
from core.ocr import read_uploaded_file
from core.parser import extract_role_from_jd
from core.screening import run_screening
from core.utils import (
    get_secret,
    init_state,
    inject_keepalive,
    login_user,
    logout_user,
    mask_email,
    questions_from_text,
    render_css,
    reset_jd_library_form,
    reset_screening_session,
    show_results_summary,
)

st.set_page_config(page_title=f"{APP_NAME} AI Recruiter", page_icon="J", layout="wide")
render_css()
inject_keepalive()
init_state()

if not st.session_state.gmail_authenticated:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Joy AI Recruiter</div>
            <h1 class="hero-title">Screen once. Ask once.</h1>
            <p class="hero-copy">
                Sign in with the Gmail account that should send candidate emails.
                Credentials stay in this Streamlit session and are never written to GitHub.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    with st.form("gmail_login"):
        login_email = st.text_input("Gmail address", placeholder="you@gmail.com")
        login_password = st.text_input("Gmail App Password", type="password", placeholder="16-character app password")
        login_name = st.text_input("Your name", placeholder="Auto-filled from email if left blank")
        login_company = st.text_input("Company", value=st.session_state.company_name or DEFAULT_COMPANY)
        submitted = st.form_submit_button("Start screening", type="primary", use_container_width=True)

    st.caption("Use a Gmail App Password from Google Account > Security > 2-Step Verification > App Passwords.")

    if submitted:
        if "@" not in login_email:
            st.error("Enter a valid Gmail address.")
        elif len(login_password.replace(" ", "").strip()) < 16:
            st.error("Enter your Gmail App Password.")
        else:
            login_user(login_email, login_password, login_name, login_company)
            st.rerun()

    st.stop()

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
    if st.button("Change Gmail login", use_container_width=True):
        logout_user()

    st.divider()
    openai_api_key = get_secret("OPENAI_API_KEY")
    openai_model = get_secret("OPENAI_MODEL", "gpt-4o-mini")
    ai_status = "AI scoring enabled" if openai_api_key else "Heuristic scoring active"
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

# If a 'New' / 'New screening' button just ran reset_screening_session(),
# this flag is set so we can force the UI back to the Screen tab — fixes
# the JD Library 'New screening' button silently resetting state while
# leaving the user stranded on JD Library with no visible change.

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
        st.markdown("<div style='height: 30px'></div>", unsafe_allow_html=True)
        new_search = st.button("New", key="new_search_btn", use_container_width=True)

    if new_search:
        reset_screening_session()
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

    with st.expander("Optional screening controls", expanded=False):
        role_input = st.text_input(
            "Role title override",
            placeholder="Leave blank. Joy will detect it from the JD.",
            key="role_input",
        )
        extra_keywords = st.text_input(
            "Must-have keywords",
            placeholder="HPLC, distributor management, SAP",
            key="extra_keywords",
        )

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
                    api_key=openai_api_key,
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

        st.session_state.selected_candidates = edited[edited["Send"] == True].copy()
        missing_email = st.session_state.selected_candidates[~st.session_state.selected_candidates["Email"].astype(str).str.contains("@", na=False)]

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

        if not st.session_state.selected_candidates.empty:

            with st.expander(
                f"Preview: {st.session_state.selected_candidates.iloc[0]['Name']}",
                expanded=True
            ):

                edited_preview_body = st.text_area(
                    "Edit email before sending",
                    value=preview_body,
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
                disabled=st.session_state.selected_candidates.empty or not confirm,
                use_container_width=True,
            )

        if not missing_email.empty:
            st.warning("Add valid email addresses before sending: " + ", ".join(missing_email["Name"].astype(str).tolist()))

        if send_clicked:
            if not st.session_state.sender_email or not st.session_state.sender_password:
                st.error("Your Gmail session expired. Sign in again to send emails.")

            elif not st.session_state.sender_name:
                st.error("Add sender name in the sidebar.")

            elif not missing_email.empty:
                st.error("Fix missing candidate email addresses first.")

            else:
                custom_email_body = st.session_state.get(
                "edited_email_preview",
                ""
                ).strip()

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

                    sent_count = sum(
                        1 for item in email_results if item["Success"]
                    )

                    st.success(
                        f"Sent {sent_count} of {len(email_results)} email(s)."
                    )
                    st.dataframe(
                        pd.DataFrame(email_results),
                        use_container_width=True,
                        hide_index=True,
                    )

                    

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
            roles = ["all"] + sorted(hist["Role"].dropna().unique().tolist())
            selected_role = st.selectbox("Role filter", roles)

            # ── Performance: User-controlled limit ─────────────────────────
            show_limit = st.slider(
                "Show last records",
                min_value=50,
                max_value=500,
                value=150,
                step=50,
                help="Reduce this number if the History tab feels slow with lots of data"
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

            # ── Delete Buttons with Confirmation Dialogs ───────────────────
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
                                if st.button("Yes, Delete", type="primary", use_container_width=True):
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

        # ── Data Display ───────────────────────────────────────────────────
        history_editable = shown.copy()

        # ensure Send column exists
        if "Send" not in history_editable.columns:
            history_editable.insert(0, "Send", False)

        # sanitize columns
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
            },
        )

        st.session_state.selected_history = history_edited[history_edited["Send"] == True].copy()

        # (rest of the email sending from history remains the same)
        if not st.session_state.selected_history.empty:
            st.divider()
            st.subheader("Send email from history")

            history_role = st.session_state.selected_history.iloc[0].get("Role", st.session_state.last_role or "the role")

            history_subject = st.text_input("Subject", value=f"Details required for {history_role} opportunity", key="history_subject")
            history_questions = st.text_area("Questions to collect", value=st.session_state.questions_text, height=180, key="history_questions")
            history_note = st.text_area("Extra note", placeholder="Optional context for candidates", height=100, key="history_note")

            parsed_questions = questions_from_text(history_questions)

            preview_body = build_email_body(
                st.session_state.selected_history.iloc[0],
                st.session_state.selected_history.iloc[0].get("Role", st.session_state.last_role),
                st.session_state.sender_name,
                st.session_state.company_name,
                parsed_questions,
                history_note,
                template_mode=True,
            )

            edited_history_body = st.text_area("Edit email before sending", value=preview_body, height=380, key="history_email_preview")
            history_confirm = st.checkbox("History recipient list reviewed", key="history_confirm")

            send_history = st.button(f"Send {len(st.session_state.selected_history)} email(s)", type="primary", disabled=not history_confirm, key="send_history_btn")

            if send_history:
                custom_body = st.session_state.get("history_email_preview", "").strip()
                with st.spinner("Sending emails from history..."):
                    history_results = send_bulk_emails(
                        selected_df=st.session_state.selected_history,
                        role=st.session_state.selected_history.iloc[0].get("Role", st.session_state.last_role),
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

with jd_tab:
    col1, col2 = st.columns([8.5, 1.5], vertical_alignment="center")

    with col1:
        st.subheader("JD Library")

    with col2:
        st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
        if st.button("New screening", key="jd_new_btn", use_container_width=True):
            reset_jd_library_form()    
            st.rerun()

    jd_lib = load_jd_library(user_key)

    # ── Save JD Form ─────────────────────────────────────────────────────────
    if "jd_save_role" not in st.session_state:
        st.session_state["jd_save_role"] = st.session_state.get("last_role", "")

    save_role = st.text_input(
        "Role title",
        placeholder="e.g. Assistant Manager Supply",
        key="jd_save_role",
    )

    if "jd_save_text" not in st.session_state:
        st.session_state["jd_save_text"] = st.session_state.get("last_jd", "")

    save_jd_text = st.text_area(
        "JD text",
        height=200,
        placeholder="Paste JD here or it auto-fills from your last screening.",
        key="jd_save_text",
    )

    save_tags = st.text_input(
        "Tags (optional)",
        placeholder="e.g. agrochemicals, bangalore, urgent",
        key="jd_save_tags",
    )

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

    # ── Saved JDs ────────────────────────────────────────────────────────────
    st.markdown("**Saved JDs**")

    if jd_lib.empty:
        st.info("No JDs saved yet. Run a screening or paste a JD above to save it.")
    else:
        search_query = st.text_input(
            "Search",
            placeholder="Filter by role or tags",
            key="jd_search",
        )

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

                with st.expander(f"{role_label}  ·  {saved_at[:10]}" + (f"  ·  {tags}" if tags and tags != "nan" else "")):
                    st.caption(jd_preview + ("..." if len(str(row.get("JD Text", ""))) > 180 else ""))

                    c1, c2 = st.columns([1, 1])
                    with c1:
                        if st.button("Load into screener", key=f"load_jd_{role_label}", use_container_width=True):
                            st.session_state["_pending_jd_text"] = str(row.get("JD Text", ""))
                            st.session_state["_pending_role_input"] = role_label
                            st.rerun()

                    with c2:
                        if st.button("Delete", key=f"delete_jd_{role_label}", use_container_width=True):
                            @st.dialog(f"Delete JD: '{role_label}'?")
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
