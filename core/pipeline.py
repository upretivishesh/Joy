import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from .history import mark_batch_duplicates, save_history
from .ocr import read_uploaded_file
from .parser import (
    detect_role_title,
    extract_jd_requirements_ai,
    extract_keywords,
    parse_min_experience,
    parse_min_experience_from_requirements,
    parse_required_education_level,
)
from .scoring import score_resume


def process_resume_worker(
    upload,
    jd_text: str,
    role: str,
    keywords: list[str],
    min_exp: float,
    api_key: str,
    model: str,
    jd_requirements: dict,
    required_edu: str,
    required_edu_level: int,
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
            "Education": "Not detected",
            "Keyword Score": 0,
            "Final Score": 0.0,
            "Verdict": "Low Fit",
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
        jd_requirements=jd_requirements,
        required_edu=required_edu,
        required_edu_level=required_edu_level,
    )


def run_screening(
    uploads,
    jd_text: str,
    role_input: str,
    extra_keywords: str,
    api_key: str,
    model: str,
    user_key: str,
) -> tuple[pd.DataFrame, list[str]]:
    errors = []

    # -----------------------------------------------------------------------
    # STEP 1: Parse role title
    # -----------------------------------------------------------------------
    role = detect_role_title(jd_text, role_input, api_key, model)

    # -----------------------------------------------------------------------
    # STEP 2: AI-powered structured JD requirements extraction
    #         This is the single biggest quality improvement — Joy now
    #         understands the JD instead of counting word frequencies.
    # -----------------------------------------------------------------------
    jd_requirements: dict = {}
    if api_key:
        with st.spinner("Analysing job description requirements..."):
            jd_requirements = extract_jd_requirements_ai(jd_text, api_key, model)

    # -----------------------------------------------------------------------
    # STEP 3: Derive screening parameters from structured requirements
    # -----------------------------------------------------------------------

    # Keywords — use AI-extracted skills, NOT word frequency
    keywords = extract_keywords(
        f"{role}\n{jd_text}",
        extra_keywords,
        limit=30,
        jd_requirements=jd_requirements or None,
    )

    # Min experience — prefer AI-parsed value, fallback to regex
    if jd_requirements and jd_requirements.get("min_experience_years"):
        min_exp = parse_min_experience_from_requirements(jd_requirements)
    else:
        min_exp = parse_min_experience(jd_text)

    # Education requirement
    required_edu: str = jd_requirements.get("required_education", "") if jd_requirements else ""
    required_edu_level: int = parse_required_education_level(required_edu)

    # Show what Joy understood about the JD (debug / transparency)
    if jd_requirements:
        with st.expander("Joy understood the JD as:", expanded=False):
            st.json({
                "Role": role,
                "Min Experience (years)": min_exp,
                "Core Skills": jd_requirements.get("core_skills", []),
                "Tools / Tech": jd_requirements.get("tools_technologies", []),
                "Required Education": required_edu or "Not specified",
                "Industry": jd_requirements.get("industry", "Not specified"),
            })

    # -----------------------------------------------------------------------
    # STEP 4: Screen resumes in parallel
    # -----------------------------------------------------------------------
    rows: list[dict] = []
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
                jd_requirements,
                required_edu,
                required_edu_level,
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

    # -----------------------------------------------------------------------
    # STEP 5: Deduplicate, sort, persist
    # -----------------------------------------------------------------------
    rows = mark_batch_duplicates(rows)
    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("Final Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Rank", range(1, len(df) + 1))

    st.session_state.last_role = role
    st.session_state.last_jd = jd_text
    st.session_state.last_keywords = keywords
    st.session_state.results_df = df

    save_history(df, role, user_key, jd_text)
    return df, errors
