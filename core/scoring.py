import json
import re

from .parser import (
    extract_email,
    extract_education_level,
    extract_experience,
    extract_name,
    extract_phone,
    extract_skills,
    parse_required_education_level,
    profile_key,
    EDUCATION_KEYWORDS,
)


# ---------------------------------------------------------------------------
# KEYWORD MATCHING — handles multi-word skills, phrase matching
# ---------------------------------------------------------------------------

def keyword_match_score(resume_text: str, keywords: list[str]) -> tuple[int, list[str], list[str]]:
    """
    Match keywords against resume. Handles multi-word skills (e.g. "plant operations")
    with phrase matching before falling back to individual word checks.
    """
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
            # Multi-word skill: try exact phrase first
            if kw_lower in lower:
                matched.append(kw)
            else:
                # Then check all individual words present (partial credit logic handled by caller)
                kw_words = kw_lower.split()
                if all(re.search(rf"\b{re.escape(w)}\b", lower) for w in kw_words):
                    matched.append(kw)
                else:
                    # At least 60% of words present = soft match (partial)
                    hit_count = sum(1 for w in kw_words if re.search(rf"\b{re.escape(w)}\b", lower))
                    if len(kw_words) > 1 and hit_count / len(kw_words) >= 0.6:
                        matched.append(kw)
                    else:
                        missing.append(kw)
        else:
            # Single word: exact word boundary match
            if re.search(rf"\b{re.escape(kw_lower)}\b", lower):
                matched.append(kw)
            else:
                missing.append(kw)

    score = round((len(matched) / len(keywords)) * 100) if keywords else 60
    return int(score), matched, missing


# ---------------------------------------------------------------------------
# EXPERIENCE SCORING
# ---------------------------------------------------------------------------

def experience_score(candidate_years: float, required_years: float) -> int:
    """
    Score candidate experience vs requirement.
    No longer hard-penalises 0 as 'missing' — 0 means parse failure, not no experience.
    """
    if required_years <= 0:
        # No requirement stated: neutral score
        return 70 if candidate_years == 0 else min(100, 70 + int(candidate_years * 3))

    if candidate_years == 0:
        # Parser couldn't extract experience — don't assume zero. Give neutral-negative.
        return 45  # was 30, which was too harsh; AI scoring will correct this

    if candidate_years >= required_years:
        bonus = min(10, int((candidate_years - required_years) * 2))
        return min(100, 100 + bonus)

    ratio = candidate_years / required_years
    if ratio >= 0.90:
        return 92   # essentially at requirement
    if ratio >= 0.80:
        return 83
    if ratio >= 0.70:
        return 72
    if ratio >= 0.55:
        return 58
    if ratio >= 0.40:
        return 42
    return int(max(10, ratio * 80))


# ---------------------------------------------------------------------------
# EDUCATION SCORING
# ---------------------------------------------------------------------------

def education_score(
    resume_edu_level: int,
    required_edu: str,
    required_edu_level: int,
) -> tuple[int, str]:
    """
    Score candidate education against JD requirement.
    Returns (score_0_to_100, reason_string).
    """
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


# ---------------------------------------------------------------------------
# CONTACT SCORE
# ---------------------------------------------------------------------------

def contact_score(email: str, phone: str) -> int:
    score = 0
    if email:
        score += 65
    if phone:
        score += 35
    return score


# ---------------------------------------------------------------------------
# STRUCTURE SCORE
# ---------------------------------------------------------------------------

def section_presence_score(resume_text: str) -> int:
    lower = (resume_text or "").lower()
    sections = [
        "experience", "education", "skills", "objective", "summary",
        "projects", "certifications", "achievements",
    ]
    found = sum(1 for s in sections if s in lower)
    return min(20, found * 4)


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
) -> tuple[int | None, str]:
    """
    AI scoring with optional structured JD requirements for better context.
    """
    if not api_key:
        return None, ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

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

        prompt = f"""You are a strict senior recruiter evaluating a resume for a specific role.

Score from 0 to 100:
- 85-100: Exceptional match, directly relevant experience, meets all must-haves
- 70-84: Good match, most requirements met, minor gaps
- 50-69: Partial match, some relevant experience, notable gaps
- 0-49: Poor match, missing critical requirements

Penalise heavily for:
- Missing industry-specific experience clearly stated in JD
- Significant experience gap (more than 30% below required)
- No evidence of key technical skills mentioned in JD
- Education below stated minimum

Do NOT penalise for:
- Missing soft skills (communication, teamwork, leadership — these are on every JD)
- Generic buzzwords that aren't real skill requirements

Return JSON only, no markdown:
{{"score": 0, "reason": "2-3 sentence specific reason mentioning actual matched and missing elements"}}

Role: {role}
{requirements_context}
Job Description:
{jd_text[:2000]}

Resume:
{resume_text[:3500]}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict recruiter. Be specific. "
                        "Reward direct domain evidence. "
                        "Penalize missing must-haves. "
                        "Never penalize for missing soft skills."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=200,
            timeout=20,
        )
        raw = re.sub(r"```json|```", "", response.choices[0].message.content or "{}").strip()
        data = json.loads(raw)
        score = int(float(data.get("score", 0)))
        reason = str(data.get("reason", "")).strip()
        return max(0, min(100, score)), reason
    except Exception as exc:
        return None, f"AI scoring skipped: {exc}"


# ---------------------------------------------------------------------------
# REASON BUILDER
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
        if exp > 0:
            exp_text = f"{exp:g} yrs found vs {min_exp:g}+ yrs expected"
        else:
            exp_text = f"Experience not extracted from resume; {min_exp:g}+ yrs expected"
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


# ---------------------------------------------------------------------------
# VERDICT
# ---------------------------------------------------------------------------

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
    keywords: list[str],
    min_exp: float,
    api_key: str,
    model: str,
    jd_requirements: dict | None = None,
    required_edu: str = "",
    required_edu_level: int = -1,
) -> dict:
    """
    Score a single resume against a JD.

    New in this version:
    - Education scoring (edu_score) with 15% weight
    - Smarter experience scoring (no hard 30 for unknown)
    - Keyword matching with multi-word skill support
    - AI receives structured JD requirements for better context
    - Experience "0 parsed" no longer catastrophically tanks the score
    """

    # --- Extract candidate data ---
    name = extract_name(resume_text, filename)
    email = extract_email(resume_text)
    phone = extract_phone(resume_text)
    exp = extract_experience(resume_text)
    skills = extract_skills(resume_text)

    # --- Education ---
    resume_edu_level, resume_edu_qual = extract_education_level(resume_text)
    edu_sc, edu_reason = education_score(resume_edu_level, required_edu, required_edu_level)

    # --- Sub-scores ---
    kw_score, matched, missing = keyword_match_score(resume_text, keywords)
    exp_sc = experience_score(exp, min_exp)
    cnt_score = contact_score(email, phone)
    skill_score = min(100, len(skills) * 10)
    structure_score = section_presence_score(resume_text)

    # --- Weighted heuristic ---
    # Education now has explicit weight; keyword weight slightly reduced
    has_edu_requirement = required_edu_level != -1

    if has_edu_requirement:
        heuristic = (
            (kw_score * 0.35)
            + (exp_sc * 0.28)
            + (edu_sc * 0.17)
            + (skill_score * 0.12)
            + (cnt_score * 0.05)
            + (structure_score * 0.03)
        )
    else:
        heuristic = (
            (kw_score * 0.42)
            + (exp_sc * 0.30)
            + (skill_score * 0.15)
            + (cnt_score * 0.08)
            + (structure_score * 0.05)
        )

    ai_score = None
    ai_reason = ""

    # Call AI for borderline-and-above candidates (save tokens for clear rejects)
    if heuristic >= 50 and api_key:
        ai_score, ai_reason = ai_score_resume(
            jd_text, resume_text, role, api_key, model, jd_requirements
        )

    if ai_score is None:
        final_score = round(heuristic, 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp, edu_reason)
        ai_used = False
    else:
        # AI carries more weight when heuristic is confident about candidate quality
        ai_weight = 0.65 if heuristic >= 70 else 0.55
        final_score = round((heuristic * (1 - ai_weight)) + (ai_score * ai_weight), 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp, edu_reason)
        ai_used = True

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
        "Final Score": final_score,
        "Verdict": verdict,
        "Matched Keywords": ", ".join(matched[:12]),
        "Missing Keywords": ", ".join(missing[:10]),
        "Skills": ", ".join(skills[:12]),
        "Reason": reason,
        "Source File": filename,
        "AI Used": ai_used,
    }
