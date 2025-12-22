from typing import List, Tuple
from collections import Counter
import re

# ---------- BASIC UTILITIES ----------

STOP_WORDS = {
    "the", "and", "for", "with", "this", "that", "from", "have", "will", "are",
    "was", "were", "been", "has", "had", "can", "could", "would", "should",
    "may", "might", "must", "shall", "not", "all", "any", "your", "our",
    "their", "who", "what", "where", "when", "why", "how"
}

def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    """Simple frequency‑based keyword extraction from JD."""
    words = re.findall(r"\b[a-z]{3,}\b", jd_text.lower())
    words = [w for w in words if w not in STOP_WORDS]
    freq = Counter(words)
    return [w for w, _ in freq.most_common(top_n)]

def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    """Keyword overlap score (0–100)."""
    if not jd_keywords:
        return 0.0
    text = resume_text.lower()
    hits = sum(1 for kw in jd_keywords if kw in text)
    return round(100.0 * hits / len(jd_keywords), 1)

# ---------- ROLE & INDUSTRY DETECTION ----------

JOB_ROLE_KEYWORDS = {
    "sales": [
        "sales", "business development", "bdm", "account manager",
        "territory", "key account", "channel sales", "export sales",
        "client acquisition", "revenue"
    ],
    "hr": [
        "hr", "human resources", "recruiter", "talent acquisition",
        "recruitment", "people operations", "hr manager", "hrbp"
    ],
    "technology": [
        "software engineer", "developer", "programmer", "sde",
        "backend", "frontend", "full stack", "devops"
    ],
    "marketing": [
        "marketing", "digital marketing", "brand manager",
        "performance marketing", "seo", "content marketing"
    ],
    "operations": [
        "operations", "supply chain", "logistics", "warehouse",
        "procurement", "inventory"
    ],
    "finance": [
        "finance", "accountant", "financial analyst", "audit",
        "controller", "treasury"
    ],
    "data": [
        "data analyst", "data scientist", "business analyst",
        "analytics", "data engineer", "bi analyst"
    ],

    # R&D / Technical Team Lead
    "rnd_lead": [
        "r&d", "research and development", "research & development",
        "lab head", "laboratory head", "lab incharge", "lab in-charge",
        "rd manager", "r&d manager", "r and d manager",
        "team leader", "technical lead", "technical leader",
        "product development", "formulation development",
        "process development", "scale up", "scale-up",
        "new product development", "npd"
    ],
}

INDUSTRY_KEYWORDS = {
    "chemical": [
        "chemical", "chemicals", "pharmaceutical", "pharma", "api",
        "magnesium", "calcium", "potassium", "chloride"
    ],
    "jewelry": [
        "jewelry", "jewellery", "diamond", "gold", "silver", "gems"
    ],
    "technology": [
        "software", "it", "saas", "tech", "digital", "application"
    ],
    "manufacturing": [
        "manufacturing", "production", "factory", "industrial"
    ],
    "retail": [
        "retail", "ecommerce", "e-commerce", "store", "consumer goods"
    ],
    "finance": [
        "banking", "fintech", "insurance", "bfsi", "financial services"
    ],
    "healthcare": [
        "healthcare", "hospital", "medical", "clinical", "patient"
    ],
}

def get_role_from_jd(jd_text: str) -> str:
    jd = jd_text.lower()
    scores = {}
    for role, kws in JOB_ROLE_KEYWORDS.items():
        s = sum(jd.count(kw) for kw in kws)
        if s > 0:
            scores[role] = s

    if not scores:
        return "other"

    # Prefer R&D lead when there is decent R&D signal, even if HR words exist
    if "rnd_lead" in scores and scores["rnd_lead"] >= 3:
        return "rnd_lead"

    return max(scores, key=scores.get)

def get_industry_from_jd(jd_text: str) -> str:
    jd = jd_text.lower()
    scores = {}
    for ind, kws in INDUSTRY_KEYWORDS.items():
        s = sum(jd.count(kw) for kw in kws)
        if s > 0:
            scores[ind] = s
    return max(scores, key=scores.get) if scores else "other"

def check_role_match(resume_text: str, jd_role: str) -> Tuple[bool, float, str]:
    """Return (is_match, score 0–100, explanation)."""
    if jd_role not in JOB_ROLE_KEYWORDS:
        return True, 50.0, "JD role unclear"
    text = resume_text.lower()
    kws = JOB_ROLE_KEYWORDS[jd_role]
    matches = sum(1 for kw in kws if kw in text)
    if matches == 0:
        return False, 0.0, f"No {jd_role} signals"
    score = min(100.0, (matches / len(kws)) * 200.0)
    if score < 30:
        return False, score, f"Weak {jd_role} signals"
    return True, score, f"{jd_role} experience detected"

def check_industry_match(resume_text: str, jd_industry: str) -> Tuple[bool, float, str]:
    """Return (is_match, score 0–100, explanation)."""
    if jd_industry not in INDUSTRY_KEYWORDS:
        return True, 50.0, "JD industry unclear"
    text = resume_text.lower()
    kws = INDUSTRY_KEYWORDS[jd_industry]
    matches = sum(text.count(kw) for kw in kws)
    if matches == 0:
        return False, 0.0, f"No {jd_industry} domain signals"
    if matches >= 5:
        score = 100.0
    elif matches >= 3:
        score = 75.0
    else:
        score = 40.0
    if score < 30:
        return False, score, f"Weak {jd_industry} domain signals"
    return True, score, f"{jd_industry} domain experience"

# ---------- FINAL SCORING ----------

def calculate_weighted_score(
    role_match: bool,
    role_score: float,
    industry_match: bool,
    industry_score: float,
    keyword_score: float,
    semantic_score: float,
    experience_years: float,
) -> float:
    """Final score combining role, industry, keywords, semantic similarity and experience."""
    if not role_match and semantic_score < 25:
        return min(15.0, semantic_score * 0.2)

    if not industry_match and semantic_score < 30:
        return min(25.0, (role_score * 0.3 + semantic_score * 0.3))

    exp_score = min(100.0, (experience_years / 15.0) * 100.0)

    final = (
        role_score * 0.25 +
        industry_score * 0.20 +
        keyword_score * 0.20 +
        semantic_score * 0.25 +
        exp_score * 0.10
    )
    return round(final, 1)
