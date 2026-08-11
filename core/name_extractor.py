# name_extractor.py
import re
from collections import Counter

try:
    import spacy
    NLP = spacy.load("en_core_web_sm")  # use the trained pipeline as-is, don't strip NER
except Exception:
    NLP = None
    print("spaCy not installed or model missing. NER disabled.")

try:
    import PyPDF2
except Exception:
    PyPDF2 = None


def extract_text_from_pdf(pdf_file) -> str:
    if not PyPDF2:
        return ""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception:
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


NOISE_HEADER_WORDS = {
    "resume", "cv", "curriculum", "vitae", "biodata", "profile", "personal",
    "details", "father", "mother", "declaration", "address", "objective",
    "summary", "career", "contact", "email", "phone", "mobile", "linkedin",
    "github", "portfolio", "reference", "references",
}


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
    if any(w in NOISE_HEADER_WORDS for w in lower_words):
        return -999

    # reject if any word is itself an obvious job-title/company keyword
    JOB_NOISE = {"manager", "engineer", "developer", "leader", "consultant",
                 "analyst", "director", "officer", "executive", "specialist",
                 "team", "senior", "junior", "lead", "head", "associate"}
    if any(w in JOB_NOISE for w in lower_words):
        return -999

    score = 0
    if position == 0:
        score += 70
    elif position <= 3:
        score += 50
    elif position <= 10:
        score += 30

    if len(words) == 2:
        score += 35
    elif len(words) == 3:
        score += 28

    # Case pattern bonus: accept Title Case OR ALL CAPS (common on Indian resumes)
    is_title_case = all(w[0].isupper() and (len(w) == 1 or w[1:].islower()) for w in words)
    is_all_caps = candidate.isupper()
    if is_title_case or is_all_caps:
        score += 30

    overlaps = sum(1 for w in lower_words if w in email_tokens)
    score += overlaps * 45
    if overlaps >= 2:
        score += 30

    if overlaps == 0 and email_local:
        hits = sum(1 for w in words if len(w) >= 3 and w.lower() in email_local)
        score += hits * 25

    return score


def extract_name_ner(text: str) -> str:
    if NLP is None:
        return ""
    try:
        doc = NLP(text[:3000])
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                cleaned = clean_name_candidate(ent.text)
                if 2 <= len(cleaned.split()) <= 4:
                    return cleaned
    except Exception:
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
    local = re.sub(r"\d+", " ", local)  # strip trailing digits like "vishal123"
    parts = [p.capitalize() for p in local.split() if len(p) > 1]
    return " ".join(parts[:3]) if len(parts) >= 2 else ""


def extract_name(text: str, filename: str = "") -> str:
    if not text:
        return "Unknown Candidate"

    text = normalize_whitespace(text)
    lines = [normalize_whitespace(line) for line in text.splitlines() if line.strip()]

    email = extract_email(text)
    email_name = extract_name_from_email(text)
    email_tokens = {t.lower() for t in email_name.split()} if email_name else set()
    email_local = email.split("@", 1)[0].lower() if email else ""

    candidates = []

    # High priority explicit label patterns
    for pattern in [
        r"(?:full\s*name|candidate\s*name|name)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{3,65})",
    ]:
        for m in re.finditer(pattern, text, re.I | re.M):
            name = m.group(1).strip()
            score = score_name_candidate(name, 0, email_tokens, email_local) + 90
            candidates.append((score, name))

    # Title Case pattern (existing)
    for m in re.finditer(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})$", text, re.M):
        name = m.group(1).strip()
        score = score_name_candidate(name, 0, email_tokens, email_local) + 90
        candidates.append((score, name))

    # ALL CAPS pattern (new — common on Indian resumes)
    for m in re.finditer(r"^([A-Z]{2,}(?:\s+[A-Z]{2,}){1,3})$", text, re.M):
        name = m.group(1).strip()
        score = score_name_candidate(name, 0, email_tokens, email_local) + 85
        candidates.append((score, name))

    # spaCy NER (now using the real trained pipeline)
    ner_name = extract_name_ner(text)
    if ner_name:
        candidates.append((score_name_candidate(ner_name, 2, email_tokens, email_local) + 70, ner_name))

    # Top lines scan
    for i, line in enumerate(lines[:40]):
        score = score_name_candidate(line, i, email_tokens, email_local)
        if score > 25:
            candidates.append((score, line))

    # Email-derived fallback
    if email_name:
        candidates.append((score_name_candidate(email_name, 5, email_tokens, email_local) + 45, email_name))

    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_name = candidates[0]
        if best_score >= 48:
            return clean_name_candidate(best_name)

    return "Unknown Candidate"
