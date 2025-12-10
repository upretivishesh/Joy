from typing import List, Dict, Tuple
from collections import Counter
import re

# Stop words
STOP_WORDS = {
    'the', 'and', 'for', 'with', 'this', 'that', 'from', 'have', 'will', 
    'are', 'was', 'were', 'been', 'has', 'had', 'can', 'could', 'would', 
    'should', 'may', 'might', 'must', 'shall', 'but', 'not', 'all', 'any', 
    'your', 'our', 'their', 'who', 'what', 'where', 'when', 'why', 'how'
}

# Job role categories and their keywords
JOB_ROLES = {
    'sales': ['sales', 'business development', 'account manager', 'sales manager', 
              'territory manager', 'key account', 'channel sales', 'inside sales',
              'outside sales', 'revenue', 'quota', 'client acquisition'],
    'hr': ['hr', 'human resources', 'recruiter', 'talent acquisition', 'hrbp',
           'hr manager', 'recruitment', 'people operations', 'employee relations'],
    'software': ['software engineer', 'developer', 'programmer', 'sde', 'full stack',
                 'frontend', 'backend', 'software developer', 'application developer'],
    'marketing': ['marketing', 'digital marketing', 'marketing manager', 'brand manager',
                  'content marketing', 'growth marketing', 'performance marketing'],
    'finance': ['finance', 'accountant', 'financial analyst', 'cfo', 'accounts manager',
                'financial controller', 'treasury', 'audit'],
    'operations': ['operations', 'operations manager', 'supply chain', 'logistics',
                   'warehouse', 'procurement', 'inventory'],
    'data': ['data analyst', 'data scientist', 'business analyst', 'data engineer',
             'analytics', 'bi analyst', 'ml engineer'],
}

# Industry keywords
INDUSTRIES = {
    'chemical': ['chemical', 'chemicals', 'pharmaceutical', 'pharma', 'api', 'formulation'],
    'technology': ['software', 'it', 'tech', 'saas', 'cloud', 'digital'],
    'manufacturing': ['manufacturing', 'production', 'industrial', 'assembly'],
    'healthcare': ['healthcare', 'medical', 'hospital', 'clinical', 'health'],
    'finance': ['banking', 'financial services', 'fintech', 'insurance'],
    'retail': ['retail', 'ecommerce', 'e-commerce', 'consumer goods'],
}


def extract_jd_role_and_industry(jd_text: str) -> Tuple[str, str]:
    """
    Extract the PRIMARY role and industry from JD.
    Returns (role_category, industry)
    """
    jd_lower = jd_text.lower()
    
    # Detect role
    role_scores = {}
    for role, keywords in JOB_ROLES.items():
        score = sum(jd_lower.count(kw) for kw in keywords)
        if score > 0:
            role_scores[role] = score
    
    primary_role = max(role_scores, key=role_scores.get) if role_scores else 'unknown'
    
    # Detect industry
    industry_scores = {}
    for industry, keywords in INDUSTRIES.items():
        score = sum(jd_lower.count(kw) for kw in keywords)
        if score > 0:
            industry_scores[industry] = score
    
    primary_industry = max(industry_scores, key=industry_scores.get) if industry_scores else 'unknown'
    
    return primary_role, primary_industry


def extract_resume_role(resume_text: str) -> str:
    """
    Extract candidate's PRIMARY role from resume (current/most recent title).
    """
    resume_lower = resume_text.lower()
    lines = resume_text.split('\n')
    
    # Look for current role indicators in first 30 lines
    for i, line in enumerate(lines[:30]):
        line_lower = line.lower()
        if any(indicator in line_lower for indicator in ['current', 'present', 'experience', 'working as']):
            # Check next 3 lines for job title
            for j in range(i, min(i+4, len(lines))):
                for role, keywords in JOB_ROLES.items():
                    if any(kw in lines[j].lower() for kw in keywords):
                        return role
    
    # Fallback: count all role mentions
    role_scores = {}
    for role, keywords in JOB_ROLES.items():
        score = sum(resume_lower.count(kw) for kw in keywords)
        if score > 0:
            role_scores[role] = score
    
    return max(role_scores, key=role_scores.get) if role_scores else 'unknown'


def calculate_role_match_score(resume_text: str, jd_role: str) -> float:
    """
    Calculate how well the resume matches the JD role.
    Returns 0-100 score.
    """
    if jd_role == 'unknown':
        return 50.0  # Neutral if can't determine
    
    resume_role = extract_resume_role(resume_text)
    
    if resume_role == jd_role:
        return 100.0  # Perfect match
    
    # Check for role keywords in resume
    resume_lower = resume_text.lower()
    jd_role_keywords = JOB_ROLES.get(jd_role, [])
    
    matches = sum(1 for kw in jd_role_keywords if kw in resume_lower)
    total = len(jd_role_keywords)
    
    if total == 0:
        return 50.0
    
    score = (matches / total) * 100
    return round(min(score, 100.0), 1)


def calculate_industry_match_score(resume_text: str, jd_industry: str) -> float:
    """
    Calculate industry relevance score.
    Returns 0-100 score.
    """
    if jd_industry == 'unknown':
        return 50.0
    
    resume_lower = resume_text.lower()
    industry_keywords = INDUSTRIES.get(jd_industry, [])
    
    matches = sum(resume_lower.count(kw) for kw in industry_keywords)
    
    # Score based on mentions
    if matches >= 5:
        return 100.0
    elif matches >= 3:
        return 75.0
    elif matches >= 1:
        return 50.0
    else:
        return 0.0


def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    """Extract technical keywords from JD (skills, tools, qualifications)."""
    jd_lower = jd_text.lower()
    
    # Technical skills to look for
    technical_skills = [
        'python', 'java', 'javascript', 'react', 'angular', 'node', 'aws', 'azure',
        'sql', 'excel', 'powerbi', 'tableau', 'salesforce', 'sap', 'crm', 'erp',
        'project management', 'agile', 'scrum', 'leadership', 'negotiation',
        'b2b', 'b2c', 'market research', 'pricing', 'distribution', 'supply chain'
    ]
    
    found_skills = [skill for skill in technical_skills if skill in jd_lower]
    
    # Extract other keywords
    words = re.findall(r'\b[a-z]{4,}\b', jd_lower)
    words = [w for w in words if w not in STOP_WORDS]
    
    word_freq = Counter(words)
    top_words = [w for w, _ in word_freq.most_common(top_n - len(found_skills))]
    
    return found_skills + top_words


def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    """Calculate keyword match percentage."""
    if not jd_keywords:
        return 0.0
    
    resume_lower = resume_text.lower()
    hits = sum(1 for kw in jd_keywords if kw in resume_lower)
    
    return round(100.0 * hits / len(jd_keywords), 1)


def calculate_final_score(
    role_match: float,
    industry_match: float,
    keyword_match: float,
    experience_years: float
) -> float:
    """
    Calculate weighted final score with role/industry as PRIMARY factors.
    
    Weights:
    - Role Match: 40%
    - Industry Match: 25%
    - Keyword Match: 25%
    - Experience: 10%
    """
    # If role match is below 30%, heavily penalize
    if role_match < 30:
        return round(role_match * 0.3, 1)  # Max 9 points if wrong role
    
    # If industry match is below 30%, penalize
    if industry_match < 30:
        return round((role_match * 0.4 + industry_match * 0.3) * 0.6, 1)
    
    # Normal weighted calculation
    exp_score = min(100, (experience_years / 10) * 100)  # Cap at 10 years = 100
    
    final = (
        role_match * 0.40 +
        industry_match * 0.25 +
        keyword_match * 0.25 +
        exp_score * 0.10
    )
    
    return round(final, 1)
