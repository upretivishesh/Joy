from typing import Dict, Tuple, Optional, List

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
from core.history import load_history, save_history
from core.semantic import semantic_similarity_scores_batch


POSITIVE_FEEDBACK = {"Interviewed", "Shortlisted", "Hired"}
NEGATIVE_FEEDBACK = {"Rejected", "Do Not Consider"}
DECIDED_FEEDBACK = POSITIVE_FEEDBACK | NEGATIVE_FEEDBACK


def _safe_str(value) -> str:
    return str(value or "").strip()


def get_learning_adjustments(
    user_key: str,
    client_company: str = "",
):
    candidate_memory = {}
    client_bias = 0.0
    learned_profile = {
        "preferred_industries": [],
        "good_fit_keywords": [],
        "min_experience_hint": None,
        "max_experience_hint": None,
    }

    try:
        history = load_history(user_key)
    except Exception:
        return candidate_memory, client_bias, learned_profile

    if history is None or history.empty:
        return candidate_memory, client_bias, learned_profile

    history = history.copy()

    if "Feedback" not in history.columns:
        history["Feedback"] = "Pending"

    history["Feedback"] = (
        history["Feedback"]
        .fillna("Pending")
        .astype(str)
        .str.strip()
    )

    if "Profile Key" in history.columns:
        for _, row in history.iterrows():
            profile_key_value = _safe_str(row.get("Profile Key", ""))
            feedback = _safe_str(row.get("Feedback", "Pending"))

            if profile_key_value and feedback != "Pending":
                candidate_memory[profile_key_value] = {
                    "feedback": feedback,
                    "role": _safe_str(row.get("Role", "")),
                    "client": _safe_str(row.get("Client", "")),
                    "verdict": _safe_str(row.get("Verdict", "")),
                    "industry": _safe_str(row.get("Candidate Industry", "")),
                    "experience": row.get("Experience", None),
                    "matched_keywords": _safe_str(row.get("Matched Keywords", "")),
                }

    if client_company and "Client" in history.columns:
        client_history = history[
            history["Client"].astype(str).str.lower()
            == client_company.strip().lower()
        ].copy()
    else:
        client_history = history.copy()

    if not client_history.empty:
        positive = int(client_history["Feedback"].isin(POSITIVE_FEEDBACK).sum())
        negative = int(client_history["Feedback"].isin(NEGATIVE_FEEDBACK).sum())
        total_decided = positive + negative

        # Small client-level bias only; it should not dominate fit.
        if total_decided >= 5:
            client_bias = round(
                ((positive - negative) / total_decided) * 2.0,
                2,
            )

        positive_history = client_history[
            client_history["Feedback"].isin(POSITIVE_FEEDBACK)
        ].copy()

        if not positive_history.empty:
            if "Candidate Industry" in positive_history.columns:
                industry_counts = (
                    positive_history["Candidate Industry"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace("", pd.NA)
                    .dropna()
                    .value_counts()
                )
                learned_profile["preferred_industries"] = (
                    industry_counts.head(5).index.tolist()
                )

            if "Experience" in positive_history.columns:
                experience_series = pd.to_numeric(
                    positive_history["Experience"],
                    errors="coerce",
                ).dropna()

                if not experience_series.empty:
                    learned_profile["min_experience_hint"] = round(
                        float(experience_series.quantile(0.25)),
                        1,
                    )
                    learned_profile["max_experience_hint"] = round(
                        float(experience_series.quantile(0.75)),
                        1,
                    )

            if "Matched Keywords" in positive_history.columns:
                keywords = []

                for text in positive_history["Matched Keywords"].fillna("").astype(str):
                    keywords.extend(
                        [
                            keyword.strip()
                            for keyword in text.split(",")
                            if keyword.strip()
                        ]
                    )

                if keywords:
                    learned_profile["good_fit_keywords"] = (
                        pd.Series(keywords).value_counts().head(10).index.tolist()
                    )

    return candidate_memory, client_bias, learned_profile


def apply_candidate_memory(
    row: pd.Series,
    candidate_memory: dict,
) -> Tuple[float, str, str]:
    profile_key_value = _safe_str(row.get("Profile Key", "")).strip()
    memory = candidate_memory.get(profile_key_value)

    if not memory:
        return 0.0, "", "New"

    feedback = memory.get("feedback", "")
    prior_role = memory.get("role", "")

    if feedback == "Hired":
        return 8.0, f"Previously hired ({prior_role}).", "Hired"

    if feedback == "Shortlisted":
        return 5.0, f"Previously shortlisted ({prior_role}).", "Shortlisted"

    if feedback == "Interviewed":
        return 3.0, f"Previously interviewed ({prior_role}).", "Interviewed"

    if feedback == "Rejected":
        return -3.0, f"Previously rejected ({prior_role}).", "Rejected"

    if feedback == "Do Not Consider":
        return -8.0, f"Previously marked do not consider ({prior_role}).", "Do Not Consider"

    return 0.0, "", feedback or "Seen Before"


def apply_learned_profile(
    row: dict,
    learned_profile: dict,
) -> Tuple[float, List[str]]:
    adjustment = 0.0
    notes = []

    candidate_industry = _safe_str(row.get("Candidate Industry", ""))
    learned_industries = learned_profile.get("preferred_industries", []) or []

    if candidate_industry and candidate_industry in learned_industries:
        adjustment += 2.0
        notes.append(
            f"Matches historically successful industry: {candidate_industry}"
        )

    candidate_experience = pd.to_numeric(
        pd.Series([row.get("Experience", None)]),
        errors="coerce",
    ).iloc[0]

    min_hint = learned_profile.get("min_experience_hint")
    max_hint = learned_profile.get("max_experience_hint")

    if (
        pd.notna(candidate_experience)
        and min_hint is not None
        and max_hint is not None
    ):
        if min_hint <= float(candidate_experience) <= max_hint:
            adjustment += 1.5
            notes.append(
                f"Experience aligns with prior successful range "
                f"({min_hint}-{max_hint} yrs)"
            )

    matched_keywords_text = _safe_str(row.get("Matched Keywords", ""))
    matched_keywords = {
        keyword.strip().lower()
        for keyword in matched_keywords_text.split(",")
        if keyword.strip()
    }

    good_fit_keywords = {
        keyword.strip().lower()
        for keyword in (learned_profile.get("good_fit_keywords", []) or [])
    }

    overlap = sorted(matched_keywords & good_fit_keywords)

    if overlap:
        bonus = min(2.5, 0.6 * len(overlap))
        adjustment += bonus
        notes.append("Shares winning keywords: " + ", ".join(overlap[:4]))

    return adjustment, notes


def _required_education_from_jd(
    jd_requirements: dict,
) -> Tuple[int, str]:
    required_edu_label = str(
        (jd_requirements or {}).get("required_education", "") or ""
    ).strip()

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
    api_key: str = "",
    model: str = "gpt-4o-mini",
    user_key: str = "",
    client_company: str = "",
    min_exp: float = 0,
    max_exp: float = 15,
    preferred_industries: Optional[List[str]] = None,
    save_results: bool = False,
):
    read_errors = []
    preferred_industries = preferred_industries or []

    if not uploads:
        st.error("No resumes uploaded")
        return pd.DataFrame(), read_errors

    candidate_memory, client_bias, learned_profile = get_learning_adjustments(
        user_key,
        client_company,
    )

    role = (
        role_input.strip()
        if role_input and role_input.strip()
        else detect_role_title(jd_text, role_input, api_key, model)
    )

    jd_requirements = (
        extract_jd_requirements_ai(jd_text, api_key, model or "gpt-4o-mini")
        if api_key
        else {}
    )

    jd_min_exp = parse_min_experience(jd_text)
    effective_min_exp = jd_min_exp if jd_min_exp > 0 else float(min_exp or 0)

    required_edu_level, required_edu_label = _required_education_from_jd(
        jd_requirements
    )

    keywords = extract_keywords(
        jd_text,
        extra_keywords=extra_keywords or "",
        limit=30,
        jd_requirements=jd_requirements,
    )

    merged_preferred_industries = list(
        dict.fromkeys(
            [
                *preferred_industries,
                *(learned_profile.get("preferred_industries", []) or []),
            ]
        )
    )

    client_profile = {
        "preferred_industries": merged_preferred_industries,
        "min_experience": min_exp,
        "max_experience": max_exp,
        "culture_notes": "",
        "language_preferences": [],
        "preferred_colleges": "",
    }

    progress_bar = st.progress(0)
    total = len(uploads)

    # PASS 1: read every uploaded file.
    file_entries = []

    for index, file in enumerate(uploads):
        try:
            text, read_error = read_uploaded_file(file.name, file.getvalue())

            if read_error:
                read_errors.append(f"{file.name}: {read_error}")
            elif not text.strip():
                read_errors.append(f"{file.name}: no readable text found")
            else:
                file_entries.append((file, text))
        except Exception as error:
            read_errors.append(f"{file.name}: {error}")

        progress_bar.progress((index + 1) / max(total, 1) * 0.4)

    # PASS 2: batch semantic scoring.
    semantic_scores: list[float | None] = [None] * len(file_entries)

    if api_key and file_entries:
        try:
            semantic_scores = semantic_similarity_scores_batch(
                resume_texts=[text for _, text in file_entries],
                jd_text=jd_text,
                api_key=api_key,
            )
        except Exception as error:
            st.warning(
                f"Batch semantic scoring failed; continuing without semantic scores: {error}"
            )
            semantic_scores = [None] * len(file_entries)

    # PASS 3: score every resume.
    results = []

    for index, (file, text) in enumerate(file_entries):
        try:
            row = score_resume(
                jd_text=jd_text,
                role=role,
                resume_text=text,
                filename=file.name,
                keywords=keywords,
                min_exp=effective_min_exp,
                api_key=api_key or "",
                model=model or "gpt-4o-mini",
                jd_requirements=jd_requirements,
                required_edu=required_edu_label,
                required_edu_level=required_edu_level,
                use_semantic=True,
                use_llm_keywords=bool(api_key),
                client_company=client_company,
                client_profile=client_profile,
                precomputed_semantic_score=semantic_scores[index],
            )

            row["Client"] = client_company
            row["Role"] = role

            memory_adjustment, memory_note, learning_status = apply_candidate_memory(
                pd.Series(row),
                candidate_memory,
            )

            learned_adjustment, learned_notes = apply_learned_profile(
                row,
                learned_profile,
            )

            # Fit Score is the core JD-fit ranking.
            fit_score = float(row["Final Score"])

            # Priority Score includes history and learned preferences.
            priority_score = (
                fit_score
                + memory_adjustment
                + learned_adjustment
                + client_bias
            )

            row["Fit Score"] = round(max(0.0, min(100.0, fit_score)), 1)
            row["Priority Score"] = round(
                max(0.0, min(100.0, priority_score)),
                1,
            )

            row["Memory Adjustment"] = round(memory_adjustment, 1)
            row["Learned Preference Adjustment"] = round(learned_adjustment, 1)
            row["Client Bias Adjustment"] = round(client_bias, 1)
            row["Learning Status"] = learning_status
            row["Memory Note"] = memory_note
            row["Learned Notes"] = " | ".join(learned_notes)

            notes = []

            if memory_note:
                notes.append(memory_note)

            notes.extend(learned_notes)

            if notes:
                row["Reason"] = (
                    str(row.get("Reason", "")) + " " + " ".join(notes)
                ).strip()

            results.append(row)

        except Exception as error:
            read_errors.append(f"{file.name}: {error}")

        if file_entries:
            progress_bar.progress(
                0.4 + (index + 1) / len(file_entries) * 0.6
            )

    progress_bar.progress(1.0)

    dataframe = pd.DataFrame(results)

    if not dataframe.empty and "Fit Score" in dataframe.columns:
        dataframe = (
            dataframe.sort_values(
                ["Fit Score", "Priority Score"],
                ascending=[False, False],
            )
            .reset_index(drop=True)
        )

    if save_results and not dataframe.empty:
        try:
            save_history(
                df=dataframe,
                role=role,
                user_key=user_key,
                jd_text=jd_text,
            )
        except Exception as error:
            st.error(f"Failed to save screening history: {error}")

    return dataframe, read_errors
