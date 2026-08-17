# name_extractor.py (improved extract_name + helpers)

import re
from collections import Counter

try:
    import spacy
    NLP = spacy.load("en_core_web_sm")
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
    # Strip common titles / prefixes (Indian + Western)
    value = re.sub(
        r"^(Mr|Mrs|Ms|Miss|Dr|Shri|Smt|Er|Prof|Sri|Kumari|Late)\.?\s+",
        "",
        value,
        flags=re.I,
    )
    # Keep letters, spaces, dots, apostrophes, hyphens only
    value = re.sub(r"[^A-Za-z .'-]", " ", value)
    value = normalize_whitespace(value)
    # Title-case while preserving existing ALL-CAPS style lightly
    if value.isupper() and len(value) > 3:
        return value.title()
    return value.title() if value else ""


NOISE_HEADER_WORDS = {
    "resume", "cv", "curriculum", "vitae", "biodata", "bio", "data", "profile",
    "personal", "details", "information", "father", "mother", "spouse", "wife",
    "husband", "declaration", "address", "objective", "summary", "career",
    "contact", "email", "phone", "mobile", "linkedin", "github", "portfolio",
    "reference", "references", "permanent", "present", "correspondence",
    "dob", "date", "birth", "gender", "nationality", "marital", "status",
    "languages", "hobbies", "interests", "strengths", "weaknesses",
    "proactive", "safety", "mindset", "team", "player", "hardworking",
}

JOB_NOISE = {
    "manager", "engineer", "developer", "leader", "consultant", "analyst",
    "director", "officer", "executive", "specialist", "senior", "junior",
    "lead", "head", "associate", "trainee", "intern", "fresher", "software",
    "sales", "marketing", "hr", "finance", "accounts", "operations",
}


def score_name_candidate(
    candidate: str,
    position: int,
    email_tokens: set,
    email_local: str = "",
) -> int:
    candidate = clean_name_candidate(candidate)
    if not candidate:
        return -999

    words = candidate.split()
    if not (2 <= len(words) <= 5):
        return -999
    if any(char.isdigit() for char in candidate) or len(candidate) > 60:
        return -999

    lower_words = [w.lower() for w in words]

    # Reject pure noise / headers / job titles
    if any(w in NOISE_HEADER_WORDS for w in lower_words):
        return -999
    if any(w in JOB_NOISE for w in lower_words):
        return -999

    # Reject very short tokens that are usually initials only without real name
    if sum(1 for w in words if len(w) == 1) > 2:
        return -999

    score = 0

    # Position bonus (top of resume is almost always the name)
    if position == 0:
        score += 85
    elif position <= 2:
        score += 65
    elif position <= 5:
        score += 40
    elif position <= 12:
        score += 20

    # Length preference
    if len(words) == 2:
        score += 40
    elif len(words) == 3:
        score += 32
    elif len(words) == 4:
        score += 20

    # Case pattern
    is_title_case = all(
        w[0].isupper() and (len(w) == 1 or w[1:].islower() or w.isupper())
        for w in words
    )
    is_all_caps = candidate.isupper()
    if is_title_case or is_all_caps:
        score += 35

    # Strong email overlap signal
    overlaps = sum(1 for w in lower_words if w in email_tokens)
    score += overlaps * 55
    if overlaps >= 2:
        score += 40

    if overlaps == 0 and email_local:
        hits = sum(
            1 for w in words
            if len(w) >= 3 and w.lower() in email_local
        )
        score += hits * 30

    # Penalize lines that look like addresses or long phrases
    if len(candidate) > 40:
        score -= 25

    return score


def extract_name_ner(text: str) -> str:
    if NLP is None:
        return ""
    try:
        doc = NLP(text[:2500])
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                cleaned = clean_name_candidate(ent.text)
                if 2 <= len(cleaned.split()) <= 5:
                    return cleaned
    except Exception:
        pass
    return ""


def extract_email(text: str) -> str:
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.I)
    match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text
    )
    return match.group(0).lower() if match else ""


def extract_name_from_email(text: str) -> str:
    email = extract_email(text)
    if not email:
        return ""
    local = email.split("@")[0]
    local = re.sub(r"[_\-.]", " ", local)
    local = re.sub(r"\d+", " ", local)
    parts = [p.capitalize() for p in local.split() if len(p) > 1]
    return " ".join(parts[:3]) if len(parts) >= 2 else ""


def extract_name(text: str, filename: str = "") -> str:
    if not text:
        return "Unknown Candidate"

    text = normalize_whitespace(text)
    lines = [
        normalize_whitespace(line)
        for line in text.splitlines()
        if line.strip()
    ]

    email = extract_email(text)
    email_name = extract_name_from_email(text)
    email_tokens = {t.lower() for t in email_name.split()} if email_name else set()
    email_local = email.split("@", 1)[0].lower() if email else ""

    candidates = []

    # Explicit labels
    for pattern in [
        r"(?:full\s*name|candidate\s*name|applicant\s*name|name)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{3,65})",
        r"(?:i\s+am|myself)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    ]:
        for m in re.finditer(pattern, text, re.I | re.M):
            name = m.group(1).strip()
            score = score_name_candidate(name, 0, email_tokens, email_local) + 100
            candidates.append((score, name))

    # Title Case lines
    for m in re.finditer(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})$", text, re.M
    ):
        name = m.group(1).strip()
        score = score_name_candidate(name, 0, email_tokens, email_local) + 95
        candidates.append((score, name))

    # ALL CAPS (very common on Indian resumes)
    for m in re.finditer(
        r"^([A-Z]{2,}(?:\s+[A-Z]{2,}){1,4})$", text, re.M
    ):
        name = m.group(1).strip()
        score = score_name_candidate(name, 0, email_tokens, email_local) + 90
        candidates.append((score, name))

    # spaCy NER
    ner_name = extract_name_ner(text)
    if ner_name:
        candidates.append(
            (
                score_name_candidate(ner_name, 2, email_tokens, email_local) + 75,
                ner_name,
            )
        )

    # Top lines scan (most reliable signal)
    for i, line in enumerate(lines[:25]):
        # Skip obvious non-name lines early
        lower = line.lower()
        if any(w in lower for w in ("email", "phone", "mobile", "@", "http", "www")):
            continue
        score = score_name_candidate(line, i, email_tokens, email_local)
        if score > 30:
            candidates.append((score, line))

    # Email-derived fallback
    if email_name:
        candidates.append(
            (
                score_name_candidate(email_name, 4, email_tokens, email_local) + 50,
                email_name,
            )
        )

    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_name = candidates[0]
        if best_score >= 55:          # slightly higher confidence bar
            return clean_name_candidate(best_name)

    return "Unknown Candidate"
