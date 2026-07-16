import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from .history import mark_batch_duplicates, save_history
from .ocr import read_uploaded_file
from .parser import detect_role_title, extract_keywords, parse_min_experience
from .scoring import score_resume


def process_resume_worker(
    upload,
    jd_text,
    role,
    keywords,
    min_exp,
    api_key,
    model,
    client_company="",
):
    if not upload:
        return None

    text, error = read_uploaded_file(upload.name, upload.getvalue())
    if error or not text.strip():
        return {
            "Send": False,
            "Duplicate": False,
            "Profile Key": "",
            "Name": upload.name,
            "Email": "",
            "Phone": "",
            "Experience": 0.0,
            "Keyword Score": 0,
            "Final Score": 0.0,
            "Verdict": "Low Fit",
            "Industry Match": "N/A",
            "Matched Keywords": "",
            "Missing Keywords": ", ".join(keywords[:10]),
            "Skills": "",
            "Reason": error or "No readable text found.",
            "Source File": upload.name,
            "AI Used": False,
        }

    return score_resume(
        jd_text=jd_text,
        role=role,
        resume_text=text,
        filename=upload.name,
        keywords=keywords,
        min_exp=min_exp,
        api_key=api_key,
        model=model,
        client_company=client_company,
    )


def run_screening(
    uploads,
    jd_text: str,
    role_input: str,
    extra_keywords: str,
    api_key: str,
    model: str,
    user_key: str,
    client_company: str = "",
) -> tuple[pd.DataFrame, list[str]]:
    errors = []
    role = detect_role_title(jd_text, role_input, api_key, model)
    keywords = extract_keywords(f"{role}\n{jd_text}", extra_keywords)
    min_exp = parse_min_experience(jd_text)
    rows = []

    progress = st.progress(0)
    status = st.empty()
    max_workers = min(4, os.cpu_count() or 4, max(1, len(uploads)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_resume_worker,
                upload,
                jd_text,
                role,
                keywords,
                min_exp,
                api_key,
                model,
                client_company,
            ): upload
            for upload in uploads
        }
        completed = 0
        for future in as_completed(futures):
            upload = futures[future]
            try:
                result = future.result()
                if result is not None:
                    rows.append(result)
            except Exception as exc:
                errors.append(f"{upload.name}: {exc}")
            completed += 1
            status.write(f"Processed {completed}/{len(uploads)} resumes")
            progress.progress(completed / len(uploads))

    progress.empty()
    status.empty()

    rows = mark_batch_duplicates(rows)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Rank", range(1, len(df) + 1))

    st.session_state.last_role = role
    st.session_state.last_jd = jd_text
    st.session_state.last_keywords = keywords
    st.session_state.last_client_company = client_company
    st.session_state.results_df = df
    save_history(df, role, user_key, jd_text)
    return df, errors
