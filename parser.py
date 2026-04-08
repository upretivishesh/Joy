from typing import List, Tuple
from collections import Counter
import re

# ---------- STOP WORDS ----------
STOP_WORDS = {
    "the","and","for","with","this","that","from","have","will","are",
    "was","were","been","has","had","can","could","would","should"
}

# ---------- KEYWORD EXTRACTION ----------
def extract_jd_keywords(jd_text: str, top_n: int = 25) -> List[str]:
    words = re.findall(r"\b[a-z]{3,}\b", jd_text.lower())
    words = [w for w in words if w not in STOP_WORDS]
    freq = Counter(words)
    return [w for w, _ in freq.most_common(top_n)]

def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    if not jd_keywords:
        return 0.0
    text = resume_text.lower()
    hits = sum(1 for kw in jd_keywords if kw in text)
    return round((hits / len(jd_keywords)) * 100, 1)

# ---------- ROLE ----------
ROLE_KEYWORDS = {
    "sales": ["sales", "business development", "revenue"],
    "hr": ["recruiter", "hr", "talent"],
    "technology": ["developer", "software", "engineer"],
    "marketing": ["marketing", "seo", "branding"],
    "rnd": ["r&d", "research", "formulation", "lab"]
}

def get_role_from_jd(jd_text: str) -> str:
    jd = jd_text.lower()
    scores = {}
    for role, kws in ROLE_KEYWORDS.items():
        scores[role] = sum(jd.count(k) for k in kws)
    return max(scores, key=scores.get)

# ---------- INDUSTRY ----------
INDUSTRY_KEYWORDS = {
    "chemical": ["chemical", "pharma"],
    "tech": ["software", "it"],
    "retail": ["retail", "store"],
}

def get_industry_from_jd(jd_text: str) -> str:
    jd = jd_text.lower()
    scores = {}
    for ind, kws in INDUSTRY_KEYWORDS.items():
        scores[ind] = sum(jd.count(k) for k in kws)
    return max(scores, key=scores.get)

# ---------- MATCH ----------
def check_role_match(text: str, role: str) -> Tuple[bool, float]:
    kws = ROLE_KEYWORDS.get(role, [])
    matches = sum(1 for k in kws if k in text.lower())
    score = min(100, matches * 30)
    return (matches > 0, score)

def check_industry_match(text: str, industry: str) -> Tuple[bool, float]:
    kws = INDUSTRY_KEYWORDS.get(industry, [])
    matches = sum(1 for k in kws if k in text.lower())
    score = min(100, matches * 30)
    return (matches > 0, score)

# ---------- FINAL SCORE ----------
def calculate_weighted_score(role, industry, keyword, semantic, exp):
    exp_score = min(100, exp * 10)

    return round(
        (role * 0.25) +
        (industry * 0.20) +
        (keyword * 0.20) +
        (semantic * 0.25) +
        (exp_score * 0.10),
        1
    )

# ---------- REJECTION ----------
def generate_rejection_reason(role_match, industry_match, semantic, keyword):
    if not role_match:
        return "Role mismatch"
    if not industry_match:
        return "Industry mismatch"
    if semantic < 20:
        return "Low relevance to JD"
    if keyword < 30:
        return "Missing key skills"
    return "Strong fit"

# ---------- SUGGESTIONS ----------
def suggest_checks(row):
    suggestions = []

    notice = str(row.get("Notice Period", "-"))

    if "60" in notice or "90" in notice:
        suggestions.append("Check notice period")

    if row.get("Red Flags") != "None":
        suggestions.append("Review red flags")

    if row.get("Experience", 0) < 2:
        suggestions.append("Low experience")

    return ", ".join(suggestions) if suggestions else "Good to proceed"
