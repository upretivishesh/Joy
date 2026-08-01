# name_extractor.py
import re
import os
from collections import Counter

try:
    import spacy
    NLP = spacy.load("en_core_web_sm", disable=["parser", "ner"])  # We'll enable NER manually
    NLP.add_pipe("ner")  # Ensure NER is active
except:
    NLP = None
    print("spaCy not installed. NER disabled.")

try:
    import PyPDF2
except:
    PyPDF2 = None


def extract_text_from_pdf(pdf_file) -> str:
    """Extract text from uploaded PDF resume"""
    if not PyPDF2:
        return ""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except:
        return ""


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_name_candidate(value: str) -> str:
    if not value:
        return ""
    value = normalize_whitespace(value)
    value = re.sub(r"^(Mr|Mrs|Ms|Miss|Dr|Shri|Smt|Er|Prof)\.?\s+", "", value, flags=re.I)
    value = re.sub(r"[^A-Za-z .'-]", " ", value)
    value = normalize_whitespace(value)
    return value.title() if value else ""


def score_name_candidate(candidate: str, position: int, email_tokens: set, email_local: str = "") -> int:
    candidate = clean_name_candidate(candidate)
    if not candidate:
        return -999

    words = candidate.split()
    if not (2 <= len(words) <= 4):
        return -999
    if any(char.isdigit() for char in candidate) or len(candidate) > 55:
        return -999

    lower_words = [w.lower() for w in words]
    BAD_NAME_WORDS = {"resume", "cv", "profile", "personal", "details", "father", "mother", "declaration"}
    if any(w in BAD_NAME_WORDS for w in lower_words):
        return -999

    score = 0
    if position == 0: score += 70
    elif position <= 3: score += 50
    elif position <= 10: score += 30

    if len(words) == 2: score += 35
    elif len(words) == 3: score += 28

    if all(w[0].isupper() and (len(w) == 1 or w[1:].islower()) for w in words):
        score += 30

    overlaps = sum(1 for w in lower_words if w in email_tokens)
    score += overlaps * 45
    if overlaps >= 2: score += 30

    if overlaps == 0 and email_local:
        hits = sum(1 for w in words if len(w) >= 3 and w.lower() in email_local)
        score += hits * 25

    return score


def extract_name_ner(text: str) -> str:
    if NLP is None:
        return ""
    try:
        doc = NLP(text[:5000])
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                cleaned = clean_name_candidate(ent.text)
                if 2 <= len(cleaned.split()) <= 4:
                    return cleaned
    except:
        pass
    return ""


def extract_email(text: str) -> str:
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.I)
    match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    return match.group(0).lower() if match else ""


def extract_name_from_email(text: str) -> str:
    email = extract_email(text)
    if not email:
        return ""
    local = email.split("@")[0]
    local = re.sub(r"[_\-.]", " ", local)
    parts = [p.capitalize() for p in local.split() if len(p) > 1]
    return " ".join(parts[:3]) if len(parts) >= 2 else ""


def extract_name(text: str, filename: str = "") -> str:
    if not text:
        return "Unknown Candidate"

    text = normalize_whitespace(text)
    lines = [normalize_whitespace(line) for line in text.splitlines() if line.strip()]

    email_name = extract_name_from_email(text)
    email_tokens = {t.lower() for t in email_name.split()} if email_name else set()
    email_local = extract_email(text).split("@", 1)[0].lower() if extract_email(text) else ""

    candidates = []

    # High priority patterns
    for pattern in [
        r"(?:full\s*name|candidate\s*name|name)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{3,65})",
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})$"
    ]:
        for m in re.finditer(pattern, text, re.I | re.M):
            name = m.group(1).strip()
            score = score_name_candidate(name, 0, email_tokens, email_local) + 90
            candidates.append((score, name))

    # spaCy NER
    ner_name = extract_name_ner(text)
    if ner_name:
        candidates.append((score_name_candidate(ner_name, 2, email_tokens, email_local) + 70, ner_name))

    # Top lines
    for i, line in enumerate(lines[:40]):
        score = score_name_candidate(line, i, email_tokens, email_local)
        if score > 25:
            candidates.append((score, line))

    # Fallbacks
    if email_name:
        candidates.append((score_name_candidate(email_name, 5, email_tokens, email_local) + 45, email_name))

    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_name = candidates[0]
        if best_score >= 48:
            return clean_name_candidate(best_name)

    return "Unknown Candidate"
