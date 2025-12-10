from typing import List
from collections import Counter
import re

def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    """Extract top keywords using simple word frequency."""
    words = re.findall(r'\b[a-z]{3,}\b', jd_text.lower())
    
    stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'have', 
                  'will', 'are', 'was', 'were', 'been', 'has', 'had', 'can', 
                  'could', 'would', 'should', 'may', 'might', 'must', 'shall',
                  'but', 'not', 'all', 'any', 'your', 'our', 'their'}
    words = [w for w in words if w not in stop_words]
    
    counter = Counter(words)
    return [word for word, _ in counter.most_common(top_n)]

def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    """Return % of JD keywords present in resume."""
    if not jd_keywords:
        return 0.0
    
    text_lower = resume_text.lower()
    hits = sum(1 for kw in jd_keywords if kw in text_lower)
    return round(100.0 * hits / len(jd_keywords), 1)
