from typing import List, Tuple
from collections import Counter
import re

STOP_WORDS = {
    "the","and","for","with","this","that","from","have","will","are",
    "was","were","been","has","had","can","could","would","should",
    "may","might","must","shall","not","all","any","your","our",
    "their","who","what","where","when","why","how"
}

# ---------- KEYWORDS ----------

def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    words = re.findall(r"\b[a-z]{3,}\b", jd_text.lower())
    words = [w for w in words if w not in STOP_WORDS]
    freq = Counter(words)
    return [w for w, _ in freq.most_common(top_n)]

def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    if not jd_keywords:
        return 0.0
    text = resume_text.lower()
    hits = sum(1 for kw in jd_keywords if kw in text)
    return round(100.0 * hits / len(jd_keywords), 1)

# ---------- ROLE & INDUSTRY ----------

JOB_ROLE_KEYWORDS = {
    "rnd_lead": [
        "r&d","research","development","lab","formulation",
        "process development","scale up","npd","technical lead"
    ],
    "sales": ["sales","business development","revenue"],
    "hr": ["hr","recruitment","talent acquisition"],
}

INDUSTRY_KEYWORDS = {
    "chemical": ["chemical","pharma","api"],
    "technology": ["software","it","saas"],
    "manufacturing": ["manufacturing","production"],
}

def get_role_from_jd(jd_text: str) -> str:
    jd = jd_text.lower()
    scores = {role: sum(jd.count(k) for k in kws) for role, kws in JOB_ROLE_KEYWORDS.items()}
    scores = {k: v for k, v in scores.items() if v > 0}
    return max(scores, key=scores.get) if scores else "other"

def get_industry_from_jd(jd_text: str) -> str:
    jd = jd_text.lower()
    scores = {ind: sum(jd.count(k) for k in kws) for ind, kws in INDUSTRY_KEYWORDS.items()}
    scores = {k: v for k, v in scores.items() if v > 0}
    return max(scores, key=scores.get) if scores else "other"

def check_role_match(resume_text: str, jd_role: str) -> Tuple[bool, float]:
    if jd_role not in JOB_ROLE_KEYWORDS:
        return True, 50.0
    text = resume_text.lower()
    kws = JOB_ROLE_KEYWORDS[jd_role]
    matches = sum(1 for kw in kws if kw in text)
    score = min(100, matches * 20)
    return matches > 0, score

def check_industry_match(resume_text: str, jd_industry: str) -> Tuple[bool, float]:
    if jd_industry not in INDUSTRY_KEYWORDS:
        return True, 50.0
    text = resume_text.lower()
    kws = INDUSTRY_KEYWORDS[jd_industry]
    matches = sum(text.count(kw) for kw in kws)
    score = min(100, matches * 25)
    return matches > 0, score

# ---------- NEW: REJECTION REASONS ----------

def generate_rejection_reason(role_match, industry_match, semantic, keyword):
    reasons = []
    if not role_match:
        reasons.append("No relevant role experience")
    if not industry_match:
        reasons.append("Different industry background")
    if semantic < 25:
        reasons.append("Low JD alignment")
    if keyword < 30:
        reasons.append("Missing key skills")
    return ", ".join(reasons) if reasons else "Good Fit"

# ---------- NEW: SUGGESTIONS ----------

def suggest_checks(row):
    suggestions = []

    if "60" in row["Notice Period"] or "90" in row["Notice Period"]:
        suggestions.append("Check notice buyout")

    if row["Red Flags"] != "None":
        suggestions.append("Review red flags")

    if row["Final Score"] > 70:
        suggestions.append("Strong candidate")

    return ", ".join(suggestions) if suggestions else "-"

# ---------- FINAL SCORE ----------

def calculate_weighted_score(role_score, industry_score, keyword_score, semantic_score, experience_years):
    exp_score = min(100.0, (experience_years / 15.0) * 100.0)

    final = (
        role_score * 0.25 +
        industry_score * 0.20 +
        keyword_score * 0.20 +
        semantic_score * 0.25 +
        exp_score * 0.10
    )
    return round(final, 1)
