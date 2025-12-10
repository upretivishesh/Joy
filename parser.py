from typing import List, Dict, Tuple
from collections import Counter
import re

# Industry-specific skill taxonomies
SKILL_SYNONYMS = {
    'python': ['python', 'py', 'django', 'flask', 'fastapi'],
    'javascript': ['javascript', 'js', 'node', 'nodejs', 'react', 'angular', 'vue'],
    'java': ['java', 'spring', 'springboot', 'hibernate'],
    'aws': ['aws', 'amazon web services', 'ec2', 's3', 'lambda'],
    'data analysis': ['data analysis', 'analytics', 'business intelligence', 'bi', 'powerbi', 'tableau'],
    'machine learning': ['machine learning', 'ml', 'deep learning', 'ai', 'artificial intelligence'],
    'project management': ['project management', 'pmp', 'agile', 'scrum', 'kanban'],
    'sales': ['sales', 'business development', 'account management', 'revenue'],
    'marketing': ['marketing', 'digital marketing', 'seo', 'sem', 'social media'],
    'finance': ['finance', 'accounting', 'financial analysis', 'cpa', 'cfa'],
}

# Common stop words to filter
STOP_WORDS = {
    'the', 'and', 'for', 'with', 'this', 'that', 'from', 'have', 'will', 
    'are', 'was', 'were', 'been', 'has', 'had', 'can', 'could', 'would', 
    'should', 'may', 'might', 'must', 'shall', 'but', 'not', 'all', 'any', 
    'your', 'our', 'their', 'who', 'what', 'where', 'when', 'why', 'how',
    'able', 'about', 'also', 'both', 'each', 'even', 'its', 'more', 'most',
    'only', 'such', 'than', 'them', 'then', 'these', 'those', 'very', 'well'
}

def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    """Extract keywords with context awareness and skill grouping."""
    jd_lower = jd_text.lower()
    keywords = []
    
    # Extract multi-word technical skills first (higher priority)
    multi_word_skills = [
        'machine learning', 'data science', 'project management', 'business development',
        'full stack', 'front end', 'back end', 'cloud computing', 'data analysis',
        'business intelligence', 'customer service', 'sales management', 'digital marketing',
        'financial analysis', 'human resources', 'supply chain', 'quality assurance'
    ]
    
    for skill in multi_word_skills:
        if skill in jd_lower:
            keywords.append(skill)
    
    # Extract single words
    words = re.findall(r'\b[a-z]{3,}\b', jd_lower)
    words = [w for w in words if w not in STOP_WORDS]
    
    # Weight words by context (skills section = higher weight)
    word_weights = {}
    
    # Find skills/requirements sections (higher weight)
    skills_section = re.search(r'(skills?|requirements?|qualifications?):(.{0,500})', jd_lower)
    if skills_section:
        skills_words = re.findall(r'\b[a-z]{3,}\b', skills_section.group(2))
        for word in skills_words:
            if word not in STOP_WORDS:
                word_weights[word] = word_weights.get(word, 0) + 3  # Triple weight
    
    # Count all words with base weight
    for word in words:
        word_weights[word] = word_weights.get(word, 0) + 1
    
    # Get top weighted words
    sorted_words = sorted(word_weights.items(), key=lambda x: x[1], reverse=True)
    keywords.extend([word for word, _ in sorted_words[:top_n - len(keywords)]])
    
    return keywords[:top_n]


def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    """Score with semantic matching and synonym recognition."""
    if not jd_keywords:
        return 0.0
    
    resume_lower = resume_text.lower()
    hits = 0
    
    for keyword in jd_keywords:
        # Direct match
        if keyword in resume_lower:
            hits += 1
            continue
        
        # Check synonyms
        for skill_group, synonyms in SKILL_SYNONYMS.items():
            if keyword in synonyms:
                # Check if any synonym exists in resume
                if any(syn in resume_lower for syn in synonyms):
                    hits += 1
                    break
    
    return round(100.0 * hits / len(jd_keywords), 1)


def get_industry_relevance_score(resume_text: str, jd_text: str) -> Tuple[float, str]:
    """
    Calculate industry relevance to filter out candidates from wrong industries.
    Returns (score, reasoning)
    """
    resume_lower = resume_text.lower()
    jd_lower = jd_text.lower()
    
    # Define industry indicators
    industries = {
        'technology': ['software', 'developer', 'programming', 'coding', 'engineer', 'tech', 'it', 'computer'],
        'healthcare': ['medical', 'hospital', 'healthcare', 'patient', 'clinical', 'nurse', 'doctor'],
        'finance': ['banking', 'financial', 'investment', 'trading', 'accounting', 'audit', 'cpa'],
        'sales': ['sales', 'revenue', 'quota', 'client acquisition', 'business development', 'crm'],
        'marketing': ['marketing', 'campaign', 'brand', 'advertising', 'content', 'seo', 'social media'],
        'operations': ['operations', 'logistics', 'supply chain', 'inventory', 'warehouse', 'procurement'],
        'hr': ['hr', 'human resources', 'recruitment', 'talent', 'hiring', 'onboarding', 'payroll'],
    }
    
    # Detect JD industry
    jd_industry_scores = {}
    for industry, keywords in industries.items():
        score = sum(1 for kw in keywords if kw in jd_lower)
        if score > 0:
            jd_industry_scores[industry] = score
    
    if not jd_industry_scores:
        return 100.0, "Industry neutral"  # Can't determine, give benefit of doubt
    
    primary_industry = max(jd_industry_scores, key=jd_industry_scores.get)
    
    # Check if resume matches primary industry
    resume_match_score = sum(1 for kw in industries[primary_industry] if kw in resume_lower)
    
    # Calculate relevance percentage
    max_possible = len(industries[primary_industry])
    relevance_pct = min(100, (resume_match_score / max(max_possible * 0.3, 1)) * 100)
    
    if relevance_pct < 30:
        reason = f"Low relevance to {primary_industry} industry"
    elif relevance_pct < 60:
        reason = f"Moderate relevance to {primary_industry}"
    else:
        reason = f"Strong {primary_industry} background"
    
    return round(relevance_pct, 1), reason
