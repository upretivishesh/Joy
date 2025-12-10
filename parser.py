import spacy
from typing import List, Dict

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import en_core_web_sm
    nlp = en_core_web_sm.load()


def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    """Extract top_n lemmatized keywords from JD text."""
    doc = nlp(jd_text.lower())
    words = [
        tok.lemma_
        for tok in doc
        if tok.is_alpha and not tok.is_stop and len(tok.text) > 2
    ]
    
    # Count frequency
    freq: Dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    
    # Sort by frequency and return top N
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:top_n]]


def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    """Return % of JD keywords present in resume."""
    if not jd_keywords:
        return 0.0
    
    text_lower = resume_text.lower()
    hits = sum(1 for kw in jd_keywords if kw in text_lower)
    return round(100.0 * hits / len(jd_keywords), 1)
