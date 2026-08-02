import pandas as pd
import streamlit as st

from core.ocr import read_uploaded_file
from core.parser import (
    detect_role_title,
    extract_jd_requirements_ai,
    extract_keywords,
    parse_min_experience,
    parse_required_education_level,
)
from core.scoring import score_resume, verdict_from_score
from core.history import load_history


def get_learning_adjustments(user_key: str, client_company: str = ""):
    candidate_memory = {}
    client_bias = 0.0
    try:
        hist = load_history(user_key)
    except Exception:
        return candidate_memory, client_bias

    if hist is None or hist.empty or "Feedback" not in hist.columns:
        return candidate_memory, client_bias

    hist = hist.copy()
    hist["Feedback"] = hist["Feedback"].fillna("Pending")

    if "Profile Key" in hist.columns:
        for _, row in hist.iterrows():
            profile_key = str(row.get("Profile Key", "")).strip()
            feedback = str(row.get("Feedback", "Pending")).strip()
            if profile_key and feedback != "Pending":
                candidate_memory[profile_key] = {
                    "feedback": feedback,
                    "role": row.get("Role", ""),
                    "client": row.get("Client", ""),
                }

    if client_company and "Client" in hist.columns:
        client_hist = hist[hist["Client"].astype(str).str.lower() == client_company.strip().lower()]
        good = int((client_hist["Feedback"] == "Good Hire").sum())
        bad = int((client_hist["Feedback"] == "Bad Hire").sum())
        total_decided = good + bad
        if total_decided >= 3:
            client_bias = round(((good - bad) / total_decided) * 10, 2)

    return candidate_memory, client_bias


def apply_candidate_memory(row: pd.Series, candidate_memory: dict) -> tuple[float, str]:
    profile_key = str(row.get("Profile Key", "")).strip()
    memory = candidate_memory.get(profile_key)
    if not memory:
        return 0.0, ""

    feedback = memory.get("feedback", "")
    memory_role = memory.get("role", "")
    if feedback == "Good Hire":
        return 12.0, f"Previously a Good Hire for {memory_role}."
    if feedback == "Bad Hire":
        return -15.0, f"Previously a Bad Hire for {memory_role}."
    if feedback == "Not Selected":
        return -4.0, f"Previously Not Selected for {memory_role}."
    return 0.0, ""


def required_education_from_jd(jd_requirements: dict) -> tuple[int, str]:
    required_edu_label = str((jd_requirements or {}).get("required_education", "") or "").strip()
    if not required_edu_label:
        return -1, ""
    try:
        level = parse_required_education_level(required_edu_label)
    except Exception:
        level = -1
    return level, required_edu_label


def run_screening(
    uploads,
    jd_text: str,
    role_input: str,
    extra_keywords: str = "",
    api_key: str | None = None,
    model: str | None = None,
    user_key: str | None = None,
    client_company: str = "",
    min_exp: float = 0,
    max_exp: float = 15,
    preferred_industries: list[str] | None = None,
):
    read_errors: list[str] = []
    preferred_industries = preferred_industries or []

    if not uploads:
        st.error("No resumes uploaded")
        return pd.DataFrame(), read_errors

    candidate_memory, client_bias = get_learning_adjustments(user_key or "", client_company)

    role = role_input.strip() if role_input and role_input.strip() else detect_role_title(jd_text, role_input, api_key, model)
    jd_req = extract_jd_requirements_ai(jd_text, api_key, model or "gpt-4o-mini") if api_key else {}
    jd_min_exp = parse_min_experience(jd_text)
    effective_min_exp = jd_min_exp if jd_min_exp > 0 else float(min_exp or 0)
    required_edu_level, required_edu_label = required_education_from_jd(jd_req)

    keywords = extract_keywords(
        jd_text,
        extra_keywords=extra_keywords or "",
        limit=30,
        jd_requirements=jd_req,
        client_profile={
            "preferred_industries": preferred_industries,
            "min_experience": min_exp,
            "max_experience": max_exp,
        },
    )

    results = []
    progress_bar = st.progress(0)
    total = len(uploads)

    for i, file in enumerate(uploads):
        try:
            text, read_error = read_uploaded_file(file.name, file.getvalue())
            if read_error:
                read_errors.append(f"{file.name}: {read_error}")
                progress_bar.progress((i + 1) / total)
                continue
            if not text.strip():
                read_errors.append(f"{file.name}: no readable text found")
                progress_bar.progress((i + 1) / total)
                continue

            row = score_resume(
                jd_text=jd_text,
                role=role,
                resume_text=text,
                filename=file.name,
                keywords=keywords,
                min_exp=effective_min_exp,
                api_key=api_key or "",
                model=model or "gpt-4o-mini",
                jd_requirements=jd_req,
                required_edu=required_edu_label,
                required_edu_level=required_edu_level,
                use_semantic=True,
                use_llm_keywords=bool(api_key),
                client_company=client_company,
                client_profile={
                    "preferred_industries": preferred_industries,
                    "min_experience": min_exp,
                    "max_experience": max_exp,
                },
            )
            row["Client"] = client_company
            row["Role"] = role

            memory_adj, memory_note = apply_candidate_memory(pd.Series(row), candidate_memory)
            total_adjustment = memory_adj + client_bias
            if total_adjustment:
                row["Final Score"] = max(0.0, min(100.0, round(float(row.get("Final Score", 0)) + total_adjustment, 1)))
                row["Verdict"] = verdict_from_score(row["Final Score"])
            row["Memory Adjustment"] = memory_adj
            row["Memory Note"] = memory_note
            if memory_note:
                row["Reason"] = f"{str(row.get('Reason', '')).strip()} {memory_note}".strip()

            results.append(row)
        except Exception as e:
            read_errors.append(f"{file.name}: {e}")
        progress_bar.progress((i + 1) / total)

    df = pd.DataFrame(results)
    if not df.empty and "Final Score" in df.columns:
        df = df.sort_values("Final Score", ascending=False).reset_index(drop=True)
    return df, read_errors
