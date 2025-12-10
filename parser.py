from typing import List, Tuple
from collections import Counter
import re

STOP_WORDS = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'have', 'will', 'are', 'was', 'were', 'been', 'has', 'had'}

def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    """Basic keyword extraction."""
    words = re.findall(r'\b[a-z]{3,}\b', jd_text.lower())
    words = [w for w in words if w not in STOP_WORDS]
    counter = Counter(words)
    return [w for w, _ in counter.most_common(top_n)]

def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    """Basic keyword match."""
    if not jd_keywords:
        return 0.0
    resume_lower = resume_text.lower()
    hits = sum(1 for kw in jd_keywords if kw in resume_lower)
    return round(100.0 * hits / len(jd_keywords), 1)

def get_role_from_jd(jd_text: str) -> str:
    """Detect primary role from JD."""
    jd_lower = jd_text.lower()
    
    # Check for specific role keywords
    if any(kw in jd_lower for kw in ['business development', 'sales', 'account manager', 'territory', 'revenue', 'export sales']):
        return 'sales'
    elif any(kw in jd_lower for kw in ['hr', 'human resource', 'recruiter', 'talent acquisition', 'recruitment']):
        return 'hr'
    elif any(kw in jd_lower for kw in ['software', 'developer', 'engineer', 'programmer', 'coding', 'backend', 'frontend']):
        return 'technology'
    elif any(kw in jd_lower for kw in ['marketing', 'brand', 'digital marketing', 'content', 'seo', 'social media']):
        return 'marketing'
    elif any(kw in jd_lower for kw in ['operations', 'logistics', 'supply chain', 'warehouse', 'procurement']):
        return 'operations'
    elif any(kw in jd_lower for kw in ['finance', 'accounting', 'audit', 'financial analyst', 'controller']):
        return 'finance'
    elif any(kw in jd_lower for kw in ['data analyst', 'data scientist', 'business analyst', 'analytics']):
        return 'data'
    
    return 'other'

def get_industry_from_jd(jd_text: str) -> str:
    """Detect industry from JD."""
    jd_lower = jd_text.lower()
    
    if any(kw in jd_lower for kw in ['chemical', 'chemicals', 'pharmaceutical', 'pharma', 'api', 'reagent', 'compound', 'magnesium', 'calcium', 'potassium']):
        return 'chemical'
    elif any(kw in jd_lower for kw in ['jewelry', 'jewellery', 'diamond', 'gold', 'gems', 'ornament', 'silver']):
        return 'jewelry'
    elif any(kw in jd_lower for kw in ['software', 'it', 'saas', 'tech', 'technology', 'digital']):
        return 'technology'
    elif any(kw in jd_lower for kw in ['manufacturing', 'production', 'factory', 'industrial']):
        return 'manufacturing'
    elif any(kw in jd_lower for kw in ['retail', 'ecommerce', 'e-commerce', 'consumer goods']):
        return 'retail'
    elif any(kw in jd_lower for kw in ['banking', 'finance', 'fintech', 'insurance', 'bfsi']):
        return 'finance'
    elif any(kw in jd_lower for kw in ['healthcare', 'hospital', 'medical', 'clinical']):
        return 'healthcare'
    
    return 'other'

def check_role_match(resume_text: str, jd_role: str) -> Tuple[bool, float, str]:
    """
    Check if resume matches the JD role.
    Returns (is_match, score, reason)
    """
    resume_lower = resume_text.lower()
    
    role_keywords = {
        'sales': ['sales', 'business development', 'account manager', 'revenue', 'territory manager', 
                  'key account', 'sales manager', 'business development manager', 'export sales', 'client acquisition'],
        'hr': ['hr', 'human resource', 'recruiter', 'talent acquisition', 'recruitment', 'hrbp', 'employee relations'],
        'technology': ['software engineer', 'developer', 'programmer', 'sde', 'tech lead', 'backend', 'frontend', 'full stack'],
        'marketing': ['marketing', 'brand manager', 'digital marketing', 'content marketing', 'seo', 'social media'],
        'operations': ['operations manager', 'supply chain', 'logistics', 'warehouse', 'procurement', 'inventory'],
        'finance': ['finance', 'accountant', 'financial analyst', 'audit', 'controller', 'treasury'],
        'data': ['data analyst', 'data scientist', 'business analyst', 'analytics', 'data engineer', 'bi analyst'],
    }
    
    if jd_role not in role_keywords:
        return True, 50.0, "Cannot determine role"
    
    # Count how many role keywords appear in resume
    required_keywords = role_keywords[jd_role]
    matches = sum(1 for kw in required_keywords if kw in resume_lower)
    
    if matches == 0:
        return False, 0.0, f"No {jd_role} experience found"
    
    # Calculate score
    score = min(100, (matches / len(required_keywords)) * 200)
    
    if score < 30:
        return False, score, f"Minimal {jd_role} keywords"
    
    return True, score, f"Found {jd_role} experience"

def check_industry_match(resume_text: str, jd_industry: str) -> Tuple[bool, float, str]:
    """
    Check if resume matches the JD industry.
    Returns (is_match, score, reason)
    """
    resume_lower = resume_text.lower()
    
    industry_keywords = {
        'chemical': ['chemical', 'chemicals', 'pharmaceutical', 'pharma', 'api', 'export', 'import', 
                     'magnesium', 'calcium', 'potassium', 'chloride', 'reagent', 'compound'],
        'jewelry': ['jewelry', 'jewellery', 'diamond', 'gold', 'silver', 'gems', 'ornament'],
        'technology': ['software', 'it', 'saas', 'tech', 'application', 'coding', 'digital'],
        'manufacturing': ['manufacturing', 'production', 'factory', 'assembly', 'industrial'],
        'retail': ['retail', 'ecommerce', 'e-commerce', 'consumer goods', 'store'],
        'finance': ['banking', 'fintech', 'insurance', 'bfsi', 'investment'],
        'healthcare': ['healthcare', 'hospital', 'medical', 'clinical', 'patient'],
    }
    
    if jd_industry not in industry_keywords:
        return True, 50.0, "Cannot determine industry"
    
    required_keywords = industry_keywords[jd_industry]
    matches = sum(resume_lower.count(kw) for kw in required_keywords)
    
    if matches == 0:
        return False, 0.0, f"No {jd_industry} industry experience"
    
    # Score based on frequency
    if matches >= 5:
        score = 100.0
    elif matches >= 3:
        score = 75.0
    elif matches >= 1:
        score = 40.0
    else:
        score = 0.0
    
    if score < 30:
        return False, score, f"Minimal {jd_industry} exposure"
    
    return True, score, f"Has {jd_industry} experience"

def calculate_weighted_score(
    role_match: bool,
    role_score: float,
    industry_match: bool,
    industry_score: float,
    keyword_score: float,
    experience_years: float
) -> float:
    """
    Calculate final weighted score.
    STRICT: If role or industry doesn't match, heavily penalize.
    """
    
    # HARD REJECTION: If role doesn't match, max score = 15
    if not role_match:
        return min(15.0, keyword_score * 0.3)
    
    # HARD REJECTION: If industry doesn't match, max score = 25
    if not industry_match:
        return min(25.0, (role_score * 0.3 + keyword_score * 0.2))
    
    # Normal weighted calculation if both match
    exp_score = min(100, (experience_years / 15) * 100)
    
    final = (
        role_score * 0.35 +
        industry_score * 0.30 +
        keyword_score * 0.25 +
        exp_score * 0.10
    )
    
    return round(final, 1)
