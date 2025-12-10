import re
import spacy

nlp = spacy.load("en_core_web_sm")

BAD_TOKENS = {"professional", "summary", "resume", "cv", "curriculum", "vitae", "profile"}


def _clean_name_candidate(s: str) -> str:
    """Normalize and validate a possible name string."""
    s = s.strip()
    # Keep only letters and spaces
    s = re.sub(r"[^A-Za-z\s]", " ", s)
    parts = [p for p in s.split() if p]
    if not (1 <= len(parts) <= 4):
        return ""
    if any(p.lower() in BAD_TOKENS for p in parts):
        return ""
    return " ".join(w.capitalize() for w in parts)


def extract_name(text: str) -> str:
    """
    Hybrid strategy:
    1) Look at first few lines for a clean-looking line.
    2) Then try spaCy PERSON entities.
    (Filename fallback is handled outside this function.)
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1) Top-line heuristic
    for l in lines[:8]:
        cand = _clean_name_candidate(l)
        if cand:
            return cand

    # 2) spaCy PERSON entities
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        cand = _clean_name_candidate(ent.text)
        if cand:
            return cand

    return "-"  # let caller fall back to filename


def extract_location(text: str) -> str:
    """Use first GPE/LOC entity as current location."""
    doc = nlp(text)
    locs = [ent.text.strip() for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
    return locs[0] if locs else "-"


def extract_jd_keywords(jd_text: str, top_n: int = 30) -> list[str]:
    """
    Basic JD keyword extractor: lemmatize, drop stopwords,
    return top-N most frequent lemmas.
    """
    doc = nlp(jd_text.lower())
    tokens = [t.lemma_ for t in doc if t.is_alpha and not t.is_stop]
    from collections import Counter

    counts = Counter(tokens)
    return [w for w, _ in counts.most_common(top_n)]


def score_resume_against_jd(resume_text: str, jd_keywords: list[str]) -> int:
    """
    Count how many JD lemmas appear in the resume lemmas.
    """
    doc = nlp(resume_text.lower())
    tokens = {t.lemma_ for t in doc if t.is_alpha}
    return sum(1 for kw in jd_keywords if kw in tokens)
