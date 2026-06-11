import json
import re

from .parser import extract_email, extract_experience, extract_name, extract_phone, extract_skills, profile_key


def keyword_match_score(resume_text: str, keywords: list[str]) -> tuple[int, list[str], list[str]]:
    if not keywords:
        return 50, [], []
    lower = (resume_text or "").lower()
    matched = [kw for kw in keywords if kw.lower() in lower]
    missing = [kw for kw in keywords if kw.lower() not in lower]
    score = round((len(matched) / len(keywords)) * 100)
    return int(score), matched, missing


def experience_score(candidate_years: float, required_years: float) -> int:
    if required_years <= 0:
        return 70 if candidate_years == 0 else 85
    if candidate_years >= required_years:
        return 100
    return int(max(0, min(100, (candidate_years / required_years) * 100)))


def contact_score(email: str, phone: str) -> int:
    score = 0
    if email:
        score += 65
    if phone:
        score += 35
    return score


def ai_score_resume(
    jd_text: str,
    resume_text: str,
    role: str,
    api_key: str,
    model: str,
) -> tuple[int | None, str]:
    if not api_key:
        return None, ""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = f"""
Score the resume against the role and job description.
Return JSON only:
{{"score": 0, "reason": ""}}

Role: {role}

Job description:
{jd_text[:2500]}

Resume:
{resume_text[:3500]}
"""
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict recruiter. Reward direct evidence, penalize missing must-haves, and stay concise.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=120,
            timeout=20,
        )
        raw = re.sub(r"```json|```", "", response.choices[0].message.content or "{}").strip()
        data = json.loads(raw)
        score = int(float(data.get("score", 0)))
        reason = str(data.get("reason", "")).strip()
        return max(0, min(100, score)), reason
    except Exception as exc:
        return None, f"AI scoring skipped: {exc}"


def make_reason(matched: list[str], missing: list[str], exp: float, min_exp: float) -> str:
    matched_text = ", ".join(matched[:5]) if matched else "few direct keyword matches"
    missing_text = ", ".join(missing[:4]) if missing else "no obvious must-have gaps"
    exp_text = f"{exp:g} yrs found vs {min_exp:g}+ yrs expected" if min_exp > 0 else (f"{exp:g} yrs found" if exp else "experience not clearly stated")
    return f"Matched {matched_text}. Missing/unclear: {missing_text}. {exp_text}."


def verdict_from_score(score: float) -> str:
    if score >= 82:
        return "Strong Fit"
    if score >= 68:
        return "Good Fit"
    if score >= 50:
        return "Review"
    return "Low Fit"


def score_resume(
    jd_text: str,
    role: str,
    resume_text: str,
    filename: str,
    keywords: list[str],
    min_exp: float,
    api_key: str,
    model: str,
) -> dict:
    name = extract_name(resume_text, filename)
    email = extract_email(resume_text)
    phone = extract_phone(resume_text)
    exp = extract_experience(resume_text)
    skills = extract_skills(resume_text)

    kw_score, matched, missing = keyword_match_score(resume_text, keywords)
    exp_score = experience_score(exp, min_exp)
    cnt_score = contact_score(email, phone)
    skill_score = min(100, len(skills) * 12)

    heuristic = (kw_score * 0.55) + (exp_score * 0.2) + (skill_score * 0.15) + (cnt_score * 0.1)
    ai_score = None
    ai_reason = ""
    if heuristic >= 65:
        ai_score, ai_reason = ai_score_resume(jd_text, resume_text, role, api_key, model)

    if ai_score is None:
        final_score = round(heuristic, 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp)
        ai_used = False
    else:
        final_score = round((heuristic * 0.45) + (ai_score * 0.55), 1)
        reason = ai_reason or make_reason(matched, missing, exp, min_exp)
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
