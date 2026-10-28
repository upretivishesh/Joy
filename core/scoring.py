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
def keyword_match_score(
    resume_text: str,
    keywords: list[str],
) -> tuple[int, list[str], list[str]]:
    if not keywords:
        return 60, [], []

    lower = (resume_text or "").lower()
    matched: list[str] = []
    missing: list[str] = []
    considered = 0

    for kw in keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue

        considered += 1

        if " " in kw_lower:
            if kw_lower in lower:
                matched.append(kw)
                continue

            kw_words = [word for word in kw_lower.split() if word]
            if not kw_words:
                considered -= 1
                continue

            # Every meaningful token must be present. A 60% hit was marking
            # "supply chain planning" as matched when only two generic words
            # appeared anywhere in the resume.
            if all(
                re.search(rf"\b{re.escape(word)}\b", lower) for word in kw_words
            ):
                matched.append(kw)
            else:
                missing.append(kw)
        else:
            if re.search(rf"\b{re.escape(kw_lower)}\b", lower):
                matched.append(kw)
            else:
                missing.append(kw)

    if considered == 0:
        return 60, [], []

    score = round((len(matched) / considered) * 100)
    return int(score), matched, missing


# ---------------------------------------------------------------------------
# EXPERIENCE, EDUCATION, CONTACT, STRUCTURE
# ---------------------------------------------------------------------------
def experience_score(candidate_years: float, required_years: float) -> int:
    if required_years <= 0:
        if candidate_years <= 0:
            return 70
        return min(100, 70 + int(candidate_years * 5))

    if candidate_years <= 0:
        return 45

    if candidate_years >= required_years:
        extra = candidate_years - required_years
        # 90 at the bar, 100 about 7 years above it.
        # The old `min(100, 100 + bonus)` made 8, 12, and 20 years identical.
        return int(min(100, 90 + min(10, extra * 1.5)))

    ratio = candidate_years / required_years
    # These stay below the at-bar score of 90. The previous 95 at 85% of
    # the requirement let a near-miss outrank someone who actually qualified.
    if ratio >= 0.85:
        return 80
    if ratio >= 0.70:
        return 70
    if ratio >= 0.55:
        return 58
    if ratio >= 0.40:
        return 46
    if ratio >= 0.25:
        return 34
    return int(max(18, ratio * 80))


def education_score(
    resume_edu_level: int,
    required_edu: str,
    required_edu_level: int,
) -> tuple[int, str]:
    if not required_edu or required_edu_level == -1:
        return 80, "No specific education requirement stated"
    if resume_edu_level == -1:
        return 45, f"Education not clearly identified (requires {required_edu})"
    if resume_edu_level >= required_edu_level:
        return 100, "Meets or exceeds education requirement"

    gap = required_edu_level - resume_edu_level
    if gap == 1:
        return 65, f"One level below required education ({required_edu})"
    return 35, f"Significantly below required education ({required_edu})"


def contact_score(email: str, phone: str) -> int:
    score = 0
    if email:
        score += 70
    if phone:
        score += 30
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
        "work history",
    ]
    found = sum(1 for section in sections if section in lower)
    return min(25, found * 4)


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
        token
        for token in _normalize_industry_label(value).split()
        if len(token) > 2 and token not in stop
    }


_INDUSTRY_ADJACENCY_PAIRS = [
    ({"api", "process", "chemistry"}, {"agrochemicals"}),
    ({"api", "process", "chemistry"}, {"pharmaceuticals"}),
    ({"api", "process", "chemistry"}, {"chemicals"}),
    ({"agrochemicals"}, {"pharmaceuticals"}),
    ({"agrochemicals"}, {"chemicals"}),
]


def _is_adjacent_industry(
    a_tokens: set[str],
    b_tokens: set[str],
) -> bool:
    for left, right in _INDUSTRY_ADJACENCY_PAIRS:
        if (left & a_tokens and right & b_tokens) or (
            left & b_tokens and right & a_tokens
        ):
            return True
    return False


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

        client_context = ""
        if client_company.strip():
            client_context = f"""
The hiring client is: {client_company}.
Weigh industry fit against what this company actually does.
Infer its industry/sector from its name and the JD if needed.
"""

        prompt = f"""You are a strict senior recruiter evaluating a resume for a specific role.

Score from 0 to 100 based on how well the resume matches the job requirements.

Also judge the candidate's INDUSTRY fit: has this candidate actually worked
in the same or a closely adjacent industry to the one in the JD{" and/or the hiring client's own industry" if client_company.strip() else ""}?
- "Yes" — candidate's work history is in the same or a directly comparable industry.
- "Partial" — adjacent or transferable industry, not an exact match but relevant.
- "No" — candidate's background is in an unrelated industry with no meaningful overlap.

Important:
- Pharmaceutical API process chemistry, including route scouting, process R&D,
  scale-up, technology transfer, impurity profiling, and multi-step synthesis,
  is a "Partial" match against agrochemical process-chemistry roles.
- Judge demonstrated responsibilities, achievements, domain exposure, and
  transferable skills, not only exact keyword matches.
- Do not reward a resume that repeats JD wording without the scope, tenure,
  or outcomes the role needs.
- Do not penalize a candidate for resume formatting or missing sections if the
  relevant experience is present.
- If a required education level is stated and the resume clearly falls short,
  reflect that in the score.

Return ONLY valid JSON:
{{"score": 0, "reason": "2-3 sentence specific reason", "industry_match": "Yes|Partial|No", "candidate_industry": "1-4 word label for the industry/sector this candidate has actually worked in"}}

Role: {role}
{requirements_context}{client_context}
Job Description:
{jd_text[:8000]}

Resume:
{resume_text[:14000]}"""

        data = chat_json(
            system=(
                "You are a strict recruiter. Be specific and objective, including "
                "about industry fit. Return valid JSON only."
            ),
            user=prompt,
            api_key=api_key,
            model=model,
            max_tokens=350,
            temperature=0,
        )

        score = int(float(data.get("score", 0)))
        reason = str(data.get("reason", "")).strip()
        industry_match = str(data.get("industry_match", "")).strip().title()
        if industry_match not in {"Yes", "Partial", "No"}:
            industry_match = "N/A"
        candidate_industry = str(data.get("candidate_industry", "")).strip()

        return (
            max(0, min(100, score)),
            reason,
            industry_match,
            candidate_industry,
        )

    except Exception as exc:
        return None, f"AI scoring skipped: {exc}", "N/A", ""


# ---------------------------------------------------------------------------
# REASON + VERDICT
# ---------------------------------------------------------------------------
def make_reason(
    matched: list[str],
    missing: list[str],
    exp: float,
    min_exp: float,
    edu_reason: str = "",
) -> str:
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
    if score >= 78:
        return "Strong Fit"
    if score >= 62:
        return "Good Fit"
    if score >= 45:
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
    final_keywords = keywords or []
    if use_llm_keywords and api_key:
        llm_keywords = extract_keywords_llm(jd_text, api_key, model)
        if llm_keywords:
            final_keywords = llm_keywords

    email = extract_email(resume_text)
    phone = extract_phone(resume_text)
    exp = extract_experience(resume_text)
    skills = extract_skills(resume_text)

    name = ""
    if api_key:
        name = extract_candidate_name_llm(
            resume_text,
            api_key,
            model,
            contact_email=email,
        )
    if not name:
        name = extract_name(resume_text, filename)

    resume_edu_level, resume_edu_qual = extract_education_level(resume_text)
    education_sc, education_reason = education_score(
        resume_edu_level,
        required_edu,
        required_edu_level,
    )

    rule_based_industry = get_candidate_industry(resume_text, filename)

    keyword_sc, matched, missing = keyword_match_score(
        resume_text,
        final_keywords,
    )
    experience_sc = experience_score(exp, min_exp)
    contact_sc = contact_score(email, phone)
    skill_sc = min(100, len(skills) * 12)
    structure_sc = section_presence_score(resume_text)

    semantic_sc: float | None = None
    if precomputed_semantic_score is not None:
        semantic_sc = float(precomputed_semantic_score)
    elif use_semantic and api_key:
        try:
            semantic_sc = semantic_similarity_score(
                resume_text,
                jd_text,
                api_key,
            )
        except Exception:
            semantic_sc = None

    has_edu_requirement = required_edu_level != -1

    # Evidence score. Used as the whole result only when AI is unavailable,
    # and as 25% of the result when AI returns a score.
    if semantic_sc is None:
        if has_edu_requirement:
            heuristic = (
                keyword_sc * 0.32
                + experience_sc * 0.30
                + education_sc * 0.15
                + skill_sc * 0.13
                + contact_sc * 0.06
                + structure_sc * 0.04
            )
        else:
            heuristic = (
                keyword_sc * 0.38
                + experience_sc * 0.34
                + skill_sc * 0.16
                + contact_sc * 0.07
                + structure_sc * 0.05
            )
    else:
        if has_edu_requirement:
            heuristic = (
                keyword_sc * 0.25
                + experience_sc * 0.24
                + education_sc * 0.10
                + semantic_sc * 0.25
                + skill_sc * 0.10
                + contact_sc * 0.04
                + structure_sc * 0.02
            )
        else:
            heuristic = (
                keyword_sc * 0.28
                + experience_sc * 0.26
                + semantic_sc * 0.26
                + skill_sc * 0.12
                + contact_sc * 0.05
                + structure_sc * 0.03
            )

    if email and phone:
        heuristic = max(heuristic, 30.0)
    else:
        heuristic = max(heuristic, 22.0)

    ai_score: int | None = None
    ai_reason = ""
    industry_match = "N/A"
    candidate_industry = ""

    if api_key:
        ai_score, ai_reason, industry_match, candidate_industry = ai_score_resume(
            jd_text=jd_text,
            resume_text=resume_text,
            role=role,
            api_key=api_key,
            model=model,
            jd_requirements=jd_requirements,
            client_company=client_company,
        )

    if ai_score is not None:
        # Do not add keyword or semantic again here. They are already inside
        # the heuristic. A second 15% + 15% pull made JD wording beat real fit.
        fit_score = (ai_score * 0.75) + (heuristic * 0.25)
        final_score = round(max(0.0, min(100.0, fit_score)), 1)
        reason = ai_reason or make_reason(
            matched,
            missing,
            exp,
            min_exp,
            education_reason,
        )
        ai_used = True
    else:
        final_score = round(max(0.0, min(100.0, heuristic)), 1)
        reason = ai_reason or make_reason(
            matched,
            missing,
            exp,
            min_exp,
            education_reason,
        )
        ai_used = False

    if not candidate_industry or candidate_industry.strip().lower() in {
        "",
        "n/a",
        "unknown",
        "not detected",
    }:
        candidate_industry = rule_based_industry

    if industry_match == "N/A" and client_profile:
        preferred = client_profile.get("preferred_industries") or []
        if preferred and rule_based_industry != "Others / Not Detected":
            rule_based_tokens = _industry_tokens(rule_based_industry)
            for preference in preferred:
                preference_tokens = _industry_tokens(str(preference))
                overlap = rule_based_tokens & preference_tokens
                if _normalize_industry_label(rule_based_industry) == _normalize_industry_label(str(preference)):
                    industry_match = "Yes"
                    break
                if overlap or _is_adjacent_industry(
                    rule_based_tokens,
                    preference_tokens,
                ):
                    industry_match = "Partial"
                    break

    persona_boost = 0.0
    band_note = ""
    if client_profile:
        industries = client_profile.get("preferred_industries") or []
        if industries:
            if industry_match == "Yes":
                persona_boost += 4
            elif industry_match == "Partial":
                persona_boost += 2
            elif industry_match == "No":
                persona_boost -= 3

        min_band = float(client_profile.get("min_experience", 0) or 0)
        max_band = float(client_profile.get("max_experience", 0) or 0)
        if max_band > 0 and exp > 0 and not (min_band <= exp <= max_band):
            persona_boost -= 2
            band_note = (
                f" Outside this client's usual {min_band:g}-{max_band:g} yr "
                "experience band."
            )

        if persona_boost != 0:
            final_score = max(
                0.0,
                min(100.0, round(final_score + persona_boost, 1)),
            )
            if band_note:
                reason = (reason + band_note).strip()

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
        "Keyword Score": keyword_sc,
        "Semantic Score": round(semantic_sc, 1) if semantic_sc is not None else "",
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
        "Heuristic Score": round(heuristic, 1),
        "AI Score": ai_score if ai_score is not None else "",
        "Persona Adjustment": round(persona_boost, 1),
    }
