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


def get_learning_adjustments(user_key: str, client_company: str = ""):
    candidate_memory = {}
    client_bias = 0.0
    learned_profile = {
        "preferred_industries": [],
        "good_fit_keywords": [],
        "min_experience_hint": None,
        "max_experience_hint": None,
    }

    try:
        hist = load_history(user_key)
    except Exception:
        return candidate_memory, client_bias, learned_profile

    if hist is None or hist.empty:
        return candidate_memory, client_bias, learned_profile

    hist = hist.copy()
    if "Feedback" not in hist.columns:
        hist["Feedback"] = "Pending"
    hist["Feedback"] = hist["Feedback"].fillna("Pending").astype(str).str.strip()

    if "Profile Key" in hist.columns:
        for _, row in hist.iterrows():
            pk = _safe_str(row.get("Profile Key", ""))
            fb = _safe_str(row.get("Feedback", "Pending"))
            if pk and fb != "Pending":
                candidate_memory[pk] = {
                    "feedback": fb,
                    "role": _safe_str(row.get("Role", "")),
                    "client": _safe_str(row.get("Client", "")),
                    "verdict": _safe_str(row.get("Verdict", "")),
                    "industry": _safe_str(row.get("Candidate Industry", "")),
                    "experience": row.get("Experience", None),
                    "matched_keywords": _safe_str(row.get("Matched Keywords", "")),
                }

    if client_company and "Client" in hist.columns:
        client_hist = hist[
            hist["Client"].astype(str).str.lower() == client_company.strip().lower()
        ].copy()
    else:
        client_hist = hist.copy()

    if not client_hist.empty:
        positive = int(client_hist["Feedback"].isin(POSITIVE_FEEDBACK).sum())
        negative = int(client_hist["Feedback"].isin(NEGATIVE_FEEDBACK).sum())
        total_decided = positive + negative

        # Milder client bias (was *6)
        if total_decided >= 3:
            client_bias = round(((positive - negative) / total_decided) * 4.5, 2)

        positive_hist = client_hist[client_hist["Feedback"].isin(POSITIVE_FEEDBACK)].copy()

        if not positive_hist.empty:
            if "Candidate Industry" in positive_hist.columns:
                industry_counts = (
                    positive_hist["Candidate Industry"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace("", pd.NA)
                    .dropna()
                    .value_counts()
                )
                learned_profile["preferred_industries"] = industry_counts.head(5).index.tolist()

            if "Experience" in positive_hist.columns:
                exp_series = pd.to_numeric(
                    positive_hist["Experience"], errors="coerce"
                ).dropna()
                if not exp_series.empty:
                    learned_profile["min_experience_hint"] = round(
                        float(exp_series.quantile(0.25)), 1
                    )
                    learned_profile["max_experience_hint"] = round(
                        float(exp_series.quantile(0.75)), 1
                    )

            if "Matched Keywords" in positive_hist.columns:
                keywords = []
                for text in positive_hist["Matched Keywords"].fillna("").astype(str):
                    keywords.extend([k.strip() for k in text.split(",") if k.strip()])
                if keywords:
                    learned_profile["good_fit_keywords"] = (
                        pd.Series(keywords).value_counts().head(10).index.tolist()
                    )

    return candidate_memory, client_bias, learned_profile


def apply_candidate_memory(
    row: pd.Series, candidate_memory: dict
) -> Tuple[float, str, str]:
    pk = _safe_str(row.get("Profile Key", "")).strip()
    memory = candidate_memory.get(pk)
    if not memory:
        return 0.0, "", "New"

    feedback = memory.get("feedback", "")
    prior_role = memory.get("role", "")

    # Softened negative penalties, kept healthy positive rewards
    if feedback == "Hired":
        return 16.0, f"Previously hired ({prior_role}).", "Hired"
    if feedback == "Shortlisted":
        return 9.0, f"Previously shortlisted ({prior_role}).", "Shortlisted"
    if feedback == "Interviewed":
        return 5.0, f"Previously interviewed ({prior_role}).", "Interviewed"
    if feedback == "Rejected":
        return -5.0, f"Previously rejected ({prior_role}).", "Rejected"
    if feedback == "Do Not Consider":
        return -12.0, f"Previously marked do not consider ({prior_role}).", "Do Not Consider"

    return 0.0, "", feedback or "Seen Before"


def apply_learned_profile(row: dict, learned_profile: dict) -> Tuple[float, List[str]]:
    adjustment = 0.0
    notes = []

    candidate_industry = _safe_str(row.get("Candidate Industry", ""))
    learned_industries = learned_profile.get("preferred_industries", []) or []
    if candidate_industry and candidate_industry in learned_industries:
        adjustment += 3.5
        notes.append(f"Matches historically successful industry: {candidate_industry}")

    candidate_exp = pd.to_numeric(
        pd.Series([row.get("Experience", None)]), errors="coerce"
    ).iloc[0]
    min_hint = learned_profile.get("min_experience_hint")
    max_hint = learned_profile.get("max_experience_hint")
    if pd.notna(candidate_exp) and min_hint is not None and max_hint is not None:
        if min_hint <= float(candidate_exp) <= max_hint:
            adjustment += 2.5
            notes.append(
                f"Experience aligns with prior successful range ({min_hint}-{max_hint} yrs)"
            )

    matched_keywords_text = _safe_str(row.get("Matched Keywords", ""))
    matched_keywords = {
        k.strip().lower() for k in matched_keywords_text.split(",") if k.strip()
    }
    good_fit_keywords = {
        k.strip().lower()
        for k in (learned_profile.get("good_fit_keywords", []) or [])
    }
    overlap = sorted(matched_keywords & good_fit_keywords)
    if overlap:
        bonus = min(4.5, 1.1 * len(overlap))
        adjustment += bonus
        notes.append("Shares winning keywords: " + ", ".join(overlap[:4]))

    return adjustment, notes


def _required_education_from_jd(jd_requirements: dict) -> Tuple[int, str]:
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
        user_key, client_company
    )

    role = (
        role_input.strip()
        if role_input and role_input.strip()
        else detect_role_title(jd_text, role_input, api_key, model)
    )

    jd_req = (
        extract_jd_requirements_ai(jd_text, api_key, model or "gpt-4o-mini")
        if api_key
        else {}
    )

    jd_min_exp = parse_min_experience(jd_text)
    effective_min_exp = jd_min_exp if jd_min_exp > 0 else float(min_exp or 0)

    required_edu_level, required_edu_label = _required_education_from_jd(jd_req)

    keywords = extract_keywords(
        jd_text,
        extra_keywords=extra_keywords or "",
        limit=30,
        jd_requirements=jd_req,
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

    # ---------- PASS 1: read every file ----------
    file_entries = []
    for i, file in enumerate(uploads):
        try:
            text, read_error = read_uploaded_file(file.name, file.getvalue())

            if read_error:
                read_errors.append(f"{file.name}: {read_error}")
            elif not text.strip():
                read_errors.append(f"{file.name}: no readable text found")
            else:
                file_entries.append((file, text))
        except Exception as e:
            read_errors.append(f"{file.name}: {e}")

        progress_bar.progress((i + 1) / max(total, 1) * 0.4)

    # ---------- Batch semantic scoring ----------
    # Neutral default raised to 55 to match the less-harsh score_resume
    semantic_scores = [55.0] * len(file_entries)
    if api_key and file_entries:
        try:
            semantic_scores = semantic_similarity_scores_batch(
                resume_texts=[text for _, text in file_entries],
                jd_text=jd_text,
                api_key=api_key,
            )
        except Exception as e:
            st.warning(f"Batch semantic scoring failed, using neutral scores: {e}")
            semantic_scores = [55.0] * len(file_entries)

    # ---------- PASS 2: score each resume ----------
    results = []
    for idx, (file, text) in enumerate(file_entries):
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
                jd_requirements=jd_req,
                required_edu=required_edu_label,
                required_edu_level=required_edu_level,
                use_semantic=True,
                use_llm_keywords=bool(api_key),
                client_company=client_company,
                client_profile=client_profile,
                precomputed_semantic_score=semantic_scores[idx] if api_key else None,
            )

            row["Client"] = client_company
            row["Role"] = role

            memory_adj, memory_note, learning_status = apply_candidate_memory(
                pd.Series(row), candidate_memory
            )
            learned_adj, learned_notes = apply_learned_profile(row, learned_profile)

            total_adjustment = memory_adj + learned_adj + client_bias

            if total_adjustment:
                row["Final Score"] = max(
                    0.0,
                    min(100.0, round(float(row["Final Score"]) + total_adjustment, 1)),
                )
                row["Verdict"] = verdict_from_score(float(row["Final Score"]))

            row["Memory Adjustment"] = round(memory_adj, 1)
            row["Learned Preference Adjustment"] = round(learned_adj, 1)
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

        except Exception as e:
            read_errors.append(f"{file.name}: {e}")

        if file_entries:
            progress_bar.progress(0.4 + (idx + 1) / len(file_entries) * 0.6)

    progress_bar.progress(1.0)

    df = pd.DataFrame(results)

    if not df.empty and "Final Score" in df.columns:
        df = df.sort_values("Final Score", ascending=False).reset_index(drop=True)

    if save_results and not df.empty:
        try:
            save_history(df=df, role=role, user_key=user_key, jd_text=jd_text)
        except Exception as e:
            st.error(f"Failed to save screening history: {e}")

    return df, read_errors
