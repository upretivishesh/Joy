import spacy
import en_core_web_sm
from typing import List, Dict

# Load English model as a package (works well on Streamlit Cloud)
nlp = en_core_web_sm.load()


def extract_location(text: str) -> str:
    """
    Very rough location extractor: return first GPE (city/country) found.
    """
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "GPE":
            return ent.text
    return "-"


def extract_jd_keywords(jd_text: str, top_n: int = 30) -> List[str]:
    """
    Extract simple keyword list from JD:
    - lowercase tokens
    - no stopwords, no punctuation, no numbers
    """
    doc = nlp(jd_text)
    words = []
    for tok in doc:
        if not tok.is_alpha:
            continue
        if tok.is_stop:
            continue
        words.append(tok.lemma_.lower())

    # simple frequency count
    freq: Dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    # sort by frequency and return top_n
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:top_n]]


def score_resume_against_jd(resume_text: str, jd_keywords: List[str]) -> float:
    """
    Simple JD–resume match score: % of JD keywords present in resume text.
    """
    if not jd_keywords:
        return 0.0

    text_lower = resume_text.lower()
    hits = 0
    for kw in jd_keywords:
        if kw and kw in text_lower:
            hits += 1

    return round(100.0 * hits / len(jd_keywords), 1)
