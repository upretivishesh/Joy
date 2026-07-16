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

from .semantic import semantic_similarity_score
from .llm_extractor import extract_keywords_llm, extract_candidate_name_llm


# ---------------------------------------------------------------------------
# KEYWORD MATCHING (kept for explainability)
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
                    hit_count = sum(1 for w in kw_words if re.search(rf"\b{re.escape(w)}\b", lower))
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
# EXPERIENCE, EDUCATION, CONTACT, STRUCTURE SCORING (unchanged)
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
    if ratio >= 0.90: return 92
    if ratio >= 0.80: return 83
    if ratio >= 0.70: return 72
    if ratio >= 0.55: return 58
    if ratio >= 0.40: return 42
    return int(max(10, ratio * 80))


def education_score(resume_edu_level: int, required_edu: str, required_edu_level: int) -> tuple[int, str]:
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
    if email: score += 65
    if phone: score += 35
    return score


def section_presence_score(resume_text: str) -> int:
    lower = (resume_text or "").lower()
    sections = ["experience", "education", "skills", "objective", "summary",
                "projects", "certifications", "achievements"]
    found = sum(1 for s in sections if s in lower)
    return min(20, found * 4)


# ---------------------------------------------------------------------------
# AI SCORING (unchanged)
# ---------------------------------------------------------------------------
def ai_score_resume(jd_text: str, resume_text: str, role: str, api_key: str, model: str,
                    jd_requirements: dict | None = None, client_company: str = "") -> tuple[int | None, str, str]:
    if not api_key:
        return None, "", "N/A"
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

        client_context = (
            f"\nThe hiring client is: {client_company}. Weigh industry fit against "
            f"what this company actually does (infer its industry/sector from its "
            f"name and the JD if you're not directly familiar with it), not just "
            f"the JD's stated industry line.\n"
            if client_company.strip() else ""
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

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a strict recruiter. Be specific and objective, including about industry fit."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=260,
            timeout=20,
        )
        raw = re.sub(r"```json|```", "", response.choices[0].message.content or "{}").strip()
        data = json.loads(raw)
        score = int(float(data.get("score", 0)))
        reason = str(data.get("reason", "")).strip()
        industry_match = str(data.get("industry_match", "")).strip().title()
        if industry_match not in {"Yes", "Partial", "No"}:
            industry_match = "N/A"
        return max(0, min(100, score)), reason, industry_match
    except Exception as exc:
        return None, f"AI scoring skipped: {exc}", "N/A"


def make_reason(matched, missing, exp, min_exp, edu_reason=""):
    matched_text = ", ".join(matched[:5]) if matched else "few direct skill matches"
    missing_text = ", ".join(missing[:4]) if missing else "no obvious skill gaps"
    if min_exp > 0:
        exp_text = f"{exp:g} yrs found vs {min_exp:g}+ yrs expected" if exp > 0 else f"Experience not extracted; {min_exp:g}+ yrs expected"
    else:
        exp_text = f"{exp:g} yrs found" if exp else "Experience not clearly stated"

    parts = [f"Skills matched: {matched_text}.", f"Skills missing: {missing_text}.", exp_text + "."]
    if edu_reason:
        parts.append(edu_reason + ".")
    return " ".join(parts)


def verdict_from_score(score: float) -> str:
    if score >= 82: return "Strong Fit"
    if score >= 68: return "Good Fit"
    if score >= 50: return "Review"
    return "Low Fit"


# ---------------------------------------------------------------------------
# MAIN SCORING FUNCTION (Updated with Semantic + LLM Keywords)
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
) -> dict:

    # === 1. LLM Keyword Extraction (Best Quality) ===
    final_keywords = keywords or []
    if use_llm_keywords and api_key:
        llm_kws = extract_keywords_llm(jd_text, api_key, model)
        if llm_kws:
            final_keywords = llm_kws

    # === 2. Extract candidate data ===
    email = extract_email(resume_text)
    phone = extract_phone(resume_text)
    exp = extract_experience(resume_text)
    skills = extract_skills(resume_text)

    # Name: LLM first (reads the whole doc in context, so it doesn't get
    # fooled by section headers, a father's/reference's name, a place
    # name, or a stray filename the way pure regex scoring can). Falls
    # back to the heuristic extractor when there's no API key, the call
    # fails, or the model isn't confident enough to return a name.
    name = ""
    if api_key:
        name = extract_candidate_name_llm(resume_text, api_key, model, contact_email=email)
    if not name:
        name = extract_name(resume_text, filename)

    resume_edu_level, resume_edu_qual = extract_education_level(resume_text)
    edu_sc, edu_reason = education_score(resume_edu_level, required_edu, required_edu_level)

    # === 3. Sub-scores ===
    kw_score, matched, missing = keyword_match_score(resume_text, final_keywords)
    exp_sc = experience_score(exp, min_exp)
    cnt_score = contact_score(email, phone)
    skill_score = min(100, len(skills) * 10)
    structure_score = section_presence_score(resume_text)

    # === 4. NEW: Semantic Embedding Score ===
    semantic_sc = 50.0
    if use_semantic and api_key:
        semantic_sc = semantic_similarity_score(resume_text, jd_text, api_key)

    # === 5. Hybrid Weighted Score ===
    has_edu_requirement = required_edu_level != -1

    if has_edu_requirement:
        heuristic = (
            (kw_score * 0.27) +
            (exp_sc * 0.22) +
            (edu_sc * 0.15) +
            (semantic_sc * 0.22) +          # Semantic weight
            (skill_score * 0.09) +
            (cnt_score * 0.03) +
            (structure_score * 0.02)
        )
    else:
        heuristic = (
            (kw_score * 0.30) +
            (exp_sc * 0.25) +
            (semantic_sc * 0.25) +          # Semantic weight
            (skill_score * 0.12) +
            (cnt_score * 0.05) +
            (structure_score * 0.03)
        )

    # === 6. AI Scoring (every candidate gets a real AI read when a key is
    # present — not just ones that already scored well on cheap keyword
    # overlap. A candidate can be genuinely industry-relevant while using
    # different vocabulary than the JD, which is exactly the case a
    # keyword-only heuristic misses and Industry Match is meant to catch.)
    ai_score = None
    ai_reason = ""
    industry_match = "N/A"
    if api_key:
        ai_score, ai_reason, industry_match = ai_score_resume(
            jd_text, resume_text, role, api_key, model, jd_requirements, client_company
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
        "Matched Keywords": ", ".join(matched[:12]),
        "Missing Keywords": ", ".join(missing[:10]),
        "Skills": ", ".join(skills[:12]),
        "Reason": reason,
        "Source File": filename,
        "AI Used": ai_used,
        "Keywords Used": ", ".join(final_keywords[:15]),   # Shows what keywords were actually used
    }
