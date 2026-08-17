import re

from .parser import (
    extract_email,
    extract_education_level,
    extract_experience,
    extract_name,
    extract_phone,
    extract_skills,
    profile_key,
)
from .semantic import semantic_similarity_score
from .llm_extractor import extract_keywords_llm, extract_candidate_name_llm
from .india_industry_map import get_candidate_industry
from .ai_client import chat_json


# ---------------------------------------------------------------------------
# KEYWORD MATCHING
# ---------------------------------------------------------------------------
def keyword_match_score(resume_text: str, keywords: list[str]) -> tuple[int, list[str], list[str]]:
    if not keywords:
        return 60, [], []

    lower = (resume_text or "").lower()
    matched: list[str] = []
    missing: list[str] = []

    for kw in keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue

        if " " in kw_lower:
            if kw_lower in lower:
                matched.append(kw)
            else:
                kw_words = kw_lower.split()
                if all(re.search(rf"\b{re.escape(w)}\b", lower) for w in kw_words):
                    matched.append(kw)
                else:
                    hit_count = sum(
                        1 for w in kw_words if re.search(rf"\b{re.escape(w)}\b", lower)
                    )
                    if len(kw_words) > 1 and hit_count / len(kw_words) >= 0.6:
                        matched.append(kw)
                    else:
                        missing.append(kw)
        else:
            if re.search(rf"\b{re.escape(kw_lower)}\b", lower):
                matched.append(kw)
            else:
                missing.append(kw)

    score = round((len(matched) / len(keywords)) * 100) if keywords else 60
    return int(score), matched, missing


# ---------------------------------------------------------------------------
# EXPERIENCE, EDUCATION, CONTACT, STRUCTURE
# ---------------------------------------------------------------------------
def experience_score(candidate_years: float, required_years: float) -> int:
    if required_years <= 0:
        return 65 if candidate_years == 0 else min(100, 65 + int(candidate_years * 4))

    if candidate_years == 0:
        return 40

    if candidate_years >= required_years:
        bonus = min(10, int((candidate_years - required_years) * 2))
        return min(100, 100 + bonus)

    ratio = candidate_years / required_years
    if ratio >= 0.90:
        return 92
    if ratio >= 0.80:
        return 83
    if ratio >= 0.70:
        return 72
    if ratio >= 0.55:
        return 58
    if ratio >= 0.40:
        return 42
    return int(max(10, ratio * 80))


def education_score(
    resume_edu_level: int, required_edu: str, required_edu_level: int
) -> tuple[int, str]:
    if not required_edu or required_edu_level == -1:
        return 75, "No specific education requirement stated"
    if resume_edu_level == -1:
        return 35, f"Education not clearly identified on resume (requires {required_edu})"
    if resume_edu_level >= required_edu_level:
        return 100, "Meets or exceeds education requirement"

    gap = required_edu_level - resume_edu_level
    if gap == 1:
        return 52, f"One level below required education ({required_edu})"
    return 20, f"Significantly below required education ({required_edu})"


def contact_score(email: str, phone: str) -> int:
    score = 0
    if email:
        score += 65
    if phone:
        score += 35
    return score


def section_presence_score(resume_text: str) -> int:
    lower = (resume_text or "").lower()
    sections = [
        "experience",
        "education",
        "skills",
        "objective",
        "summary",
        "projects",
        "certifications",
        "achievements",
    ]
    found = sum(1 for s in sections if s in lower)
    return min(20, found * 4)


# ---------------------------------------------------------------------------
# INDUSTRY FIT HELPERS
# ---------------------------------------------------------------------------
def industry_fit_badge(industry_match: str) -> str:
    return {
        "Yes": "✅ Yes",
        "Partial": "⚠️ Partial",
        "No": "❌ No",
    }.get(industry_match, "— N/A")


def _normalize_industry_label(value: str) -> str:
    value = (value or "").lower().strip()
    value = value.replace("&", " and ")
    value = value.replace("/", " ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\b(fmcg sales|fmcg)\b", "fast moving consumer goods", value)
    value = re.sub(r"\b(d2c|dtc)\b", "direct to consumer", value)
    value = re.sub(
        r"\b(agro chemical|agro chemicals|crop protection|crop care|agri input|agri inputs)\b",
        "agrochemicals",
        value,
    )
    value = re.sub(r"\b(speciality)\b", "specialty", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _industry_tokens(value: str) -> set[str]:
    stop = {
        "and",
        "to",
        "the",
        "of",
        "general",
        "conventional",
        "business",
    }
    return {
        t for t in _normalize_industry_label(value).split() if len(t) > 2 and t not in stop
    }


# ---------------------------------------------------------------------------
# AI SCORING
# ---------------------------------------------------------------------------
def ai_score_resume(
    jd_text: str,
    resume_text: str,
    role: str,
    api_key: str,
    model: str,
    jd_requirements: dict | None = None,
    client_company: str = "",
) -> tuple[int | None, str, str, str]:
    if not api_key:
        return None, "", "N/A", ""

    try:
        requirements_context = ""
        if jd_requirements:
            requirements_context = f"""
Structured requirements extracted from JD:
- Min experience: {jd_requirements.get('min_experience_years', 'not stated')} years
- Core skills required: {', '.join(jd_requirements.get('core_skills') or [])}
- Tools/tech: {', '.join(jd_requirements.get('tools_technologies') or [])}
- Required education: {jd_requirements.get('required_education', 'not stated')}
- Industry: {jd_requirements.get('industry', 'not stated')}
"""

        client_context = (
            f"\nThe hiring client is: {client_company}. Weigh industry fit against "
            f"what this company actually does (infer its industry/sector from its "
            f"name and the JD if you're not directly familiar with it), not just "
            f"the JD's stated industry line.\n"
            if client_company.strip()
            else ""
        )

        prompt = f"""You are a strict senior recruiter evaluating a resume for a specific role.

Score from 0 to 100 based on how well the resume matches the job requirements.

Also judge the candidate's INDUSTRY fit: has this candidate actually worked
in the same or a closely adjacent industry to the one in the JD{" and/or the hiring client's own industry" if client_company.strip() else ""}?
- "Yes" — candidate's work history is in the same or a directly comparable industry.
- "Partial" — adjacent/transferable industry (e.g. FMCG vs D2C, general chemicals vs agrochemicals), not an exact match but relevant.
- "No" — candidate's background is in an unrelated industry with no meaningful overlap.

Return ONLY valid JSON:
{{"score": 0, "reason": "2-3 sentence specific reason", "industry_match": "Yes|Partial|No", "candidate_industry": "1-4 word label for the industry/sector this candidate has actually worked in"}}

Role: {role}
{requirements_context}{client_context}
Job Description:
{jd_text[:2000]}

Resume:
{resume_text[:3500]}"""

        data = chat_json(
            system="You are a strict recruiter. Be specific and objective, including about industry fit. Return valid JSON only.",
            user=prompt,
            api_key=api_key,
            model=model,
            max_tokens=260,
            temperature=0,
        )

        score = int(float(data.get("score", 0)))
        reason = str(data.get("reason", "")).strip()
        industry_match = str(data.get("industry_match", "")).strip().title()
        if industry_match not in {"Yes", "Partial", "No"}:
            industry_match = "N/A"
        candidate_industry = str(data.get("candidate_industry", "")).strip()

        return max(0, min(100, score)), reason, industry_match, candidate_industry

    except Exception as exc:
        return None, f"AI scoring skipped: {exc}", "N/A", ""


# ---------------------------------------------------------------------------
# REASON + VERDICT
# ---------------------------------------------------------------------------
def make_reason(matched, missing, exp, min_exp, edu_reason=""):
    matched_text = ", ".join(matched[:5]) if matched else "few direct skill matches"
    missing_text = ", ".join(missing[:4]) if missing else "no obvious skill gaps"

    if min_exp > 0:
        exp_text = (
            f"{exp:g} yrs found vs {min_exp:g}+ yrs expected"
            if exp > 0
            else f"Experience not extracted; {min_exp:g}+ yrs expected"
        )
    else:
        exp_text = f"{exp:g} yrs found" if exp else "Experience not clearly stated"

    parts = [
        f"Skills matched: {matched_text}.",
        f"Skills missing: {missing_text}.",
        exp_text + ".",
    ]
    if edu_reason:
        parts.append(edu_reason + ".")
    return " ".join(parts)


def verdict_from_score(score: float) -> str:
    if score >= 82:
        return "Strong Fit"
    if score >= 68:
        return "Good Fit"
    if score >= 50:
        return "Review"
    return "Low Fit"


# ---------------------------------------------------------------------------
# MAIN SCORING FUNCTION
# ---------------------------------------------------------------------------
def score_resume(
    jd_text: str,
    role: str,
    resume_text: str,
    filename: str,
    keywords: list[str] = None,
    min_exp: float = 0.0,
    api_key: str = "",
    model: str = "gpt-4o-mini",
    jd_requirements: dict | None = None,
    required_edu: str = "",
    required_edu_level: int = -1,
    use_semantic: bool = True,
    use_llm_keywords: bool = True,
    client_company: str = "",
    client_profile: dict | None = None,
    precomputed_semantic_score: float | None = None,
) -> dict:
    # 1. Keywords
    final_keywords = keywords or []
    if use_llm_keywords and api_key:
        llm_kws = extract_keywords_llm(jd_text, api_key, model)
        if llm_kws:
            final_keywords = llm_kws

    # 2. Candidate extraction
    email = extract_email(resume_text)
    phone = extract_phone(resume_text)
    exp = extract_experience(resume_text)
    skills = extract_skills(resume_text)

    name = ""
    if api_key:
        name = extract_candidate_name_llm(
            resume_text, api_key, model, contact_email=email
        )
    if not name:
        name = extract_name(resume_text, filename)

    resume_edu_level, resume_edu_qual = extract_education_level(resume_text)
    edu_sc, edu_reason = education_score(
        resume_edu_level, required_edu, required_edu_level
    )

    # 2b. Rule-based industry
    rule_based_industry = get_candidate_industry(resume_text, filename)

    # 3. Sub-scores
    kw_score, matched, missing = keyword_match_score(resume_text, final_keywords)
    exp_sc = experience_score(exp, min_exp)
    cnt_score = contact_score(email, phone)
    skill_score = min(100, len(skills) * 10)
    structure_score = section_presence_score(resume_text)

    # 4. Semantic score
    # If the caller already batch-embedded this resume against the JD
    # (see screening.py's run_screening, which embeds the whole batch in
    # one or two API calls instead of one call pair per resume), use that
    # value directly and skip the redundant single-pair API call here.
    # Falls back to the original per-resume call when no batch score was
    # supplied, so this function's behavior is unchanged for any other
    # caller that invokes score_resume() directly.
    if precomputed_semantic_score is not None:
        semantic_sc = precomputed_semantic_score
    else:
        semantic_sc = 50.0
        if use_semantic and api_key:
            semantic_sc = semantic_similarity_score(resume_text, jd_text, api_key)

    # 5. Heuristic score
    has_edu_requirement = required_edu_level != -1

    if has_edu_requirement:
        heuristic = (
            (kw_score * 0.27)
            + (exp_sc * 0.22)
            + (edu_sc * 0.15)
            + (semantic_sc * 0.22)
            + (skill_score * 0.09)
            + (cnt_score * 0.03)
            + (structure_score * 0.02)
        )
    else:
        heuristic = (
            (kw_score * 0.30)
            + (exp_sc * 0.25)
            + (semantic_sc * 0.25)
            + (skill_score * 0.12)
            + (cnt_score * 0.05)
            + (structure_score * 0.03)
        )

    # 6. AI score
    ai_score = None
    ai_reason = ""
    industry_match = "N/A"
    candidate_industry = ""

    if heuristic >= 50 and api_key:
        ai_score, ai_reason, industry_match, candidate_industry = ai_score_resume(
            jd_text=jd_text,
            resume_text=resume_text,
            role=role,
            api_key=api_key,
            model=model,
            jd_requirements=jd_requirements,
            client_company=client_company,
        )

    if ai_score is None:
        final_score = round(heuristic, 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp, edu_reason)
        ai_used = False
    else:
        ai_weight = 0.60 if heuristic >= 70 else 0.50
        final_score = round((heuristic * (1 - ai_weight)) + (ai_score * ai_weight), 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp, edu_reason)
        ai_used = True

    # 6b. Always backfill candidate industry if AI left it empty
    if not candidate_industry or candidate_industry.strip().lower() in {
        "",
        "n/a",
        "unknown",
        "not detected",
    }:
        candidate_industry = rule_based_industry

    # 6c. Fallback industry match from client persona
    if industry_match == "N/A" and client_profile:
        preferred = client_profile.get("preferred_industries") or []

        if preferred and rule_based_industry != "Others / Not Detected":
            rb_norm = _normalize_industry_label(rule_based_industry)
            rb_tokens = _industry_tokens(rule_based_industry)

            for pref in preferred:
                pref_norm = _normalize_industry_label(str(pref))
                pref_tokens = _industry_tokens(str(pref))
                overlap = rb_tokens & pref_tokens

                if rb_norm == pref_norm:
                    industry_match = "Yes"
                    break
                elif overlap:
                    industry_match = "Partial"
                    break

    # 7. Client persona adjustment
    band_note = ""
    if client_profile:
        boost = 0
        industries = client_profile.get("preferred_industries") or []

        if industries:
            if industry_match == "Yes":
                boost += 6
            elif industry_match == "Partial":
                boost += 2
            elif industry_match == "No":
                boost -= 6

        culture_notes = str(client_profile.get("culture_notes", "")).strip()
        if len(culture_notes) > 20:
            boost += 3

        min_band = float(client_profile.get("min_experience", 0) or 0)
        max_band = float(client_profile.get("max_experience", 0) or 0)
        if max_band > 0 and exp > 0 and not (min_band <= exp <= max_band):
            boost -= 4
            band_note = (
                f" Outside this client's usual {min_band:g}-{max_band:g} yr experience band."
            )

        if boost != 0:
            final_score = max(0.0, min(100.0, round(final_score + boost, 1)))
            reason = (reason + band_note).strip() if band_note else reason

    verdict = verdict_from_score(final_score)

    return {
        "Send": verdict in {"Strong Fit", "Good Fit"} and bool(email),
        "Duplicate": False,
        "Profile Key": profile_key(name, email, phone),
        "Name": name,
        "Email": email,
        "Phone": phone,
        "Experience": exp,
        "Education": resume_edu_qual or "Not detected",
        "Keyword Score": kw_score,
        "Semantic Score": round(semantic_sc, 1),
        "Final Score": final_score,
        "Verdict": verdict,
        "Industry Match": industry_match,
        "Candidate Industry": candidate_industry,
        "Matched Keywords": ", ".join(matched[:12]),
        "Missing Keywords": ", ".join(missing[:10]),
        "Skills": ", ".join(skills[:12]),
        "Reason": reason,
        "Source File": filename,
        "AI Used": ai_used,
        "Keywords Used": ", ".join(final_keywords[:15]),
    }
