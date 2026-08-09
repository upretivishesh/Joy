import hashlib
import re
from collections import Counter
from datetime import datetime

from .constants import (
    DATE_RANGE_REGEX,
    GENERIC_EMAIL_PREFIXES,
    MONTH_MAP,
    NAME_STOPWORDS,
    SKILL_ALIASES,
    STOP_WORDS,
)
from .ai_client import chat_json


# ---------------------------------------------------------------------------
# REAL SPACY NER LOADING — this was the #1 accuracy killer.
# NLP was hardcoded to None, so extract_name_ner() never ran.
# ---------------------------------------------------------------------------
_NLP_CACHE = {}


def _load_nlp():
    """Lazily load spaCy's NER model once per process, with safe fallback."""
    if "model" in _NLP_CACHE:
        return _NLP_CACHE["model"]

    model = None
    try:
        import spacy
        try:
            model = spacy.load("en_core_web_sm")
        except OSError:
            try:
                model = spacy.load("en_core_web_sm", disable=["parser", "tagger"])
            except Exception:
                model = None
    except ImportError:
        model = None

    _NLP_CACHE["model"] = model
    return model


NLP = _load_nlp()


# ---------------------------------------------------------------------------
# NOISE FILTER — words that appear in JDs but have zero resume-matching value
# ---------------------------------------------------------------------------
JD_NOISE_WORDS = {
    "communication", "communications", "interpersonal", "teamwork", "leadership",
    "collaboration", "collaborative", "initiative", "proactive", "problem",
    "solving", "critical", "thinking", "adaptable", "adaptability",
    "multitask", "multitasking", "self", "motivated", "motivation", "driven",
    "passionate", "enthusiastic", "detail", "oriented", "hardworking",
    "dedicated", "innovative", "creative", "dynamic", "results", "focused",
    "organised", "organized", "punctual", "diligent", "energetic",
    "pioneering", "innovation", "market", "intelligence", "reliable",
    "operate", "sectors", "day-to-day", "share", "mission", "creating",
    "drive", "driving", "lead", "leading", "grow", "growth", "build", "building",
    "deliver", "delivering", "support", "supporting", "ensure", "ensuring",
    "daily", "basis", "track", "revolutionize", "new-age", "asset-light",
    "brand", "combines", "email", "quality", "sites", "standards",
    "confidentiality", "partners", "transfer", "capa", "agrochemicals",
    "across", "within", "between", "through", "along", "around", "including",
    "regarding", "maintain", "maintaining", "coordinate", "coordinating",
    "handle", "handling", "assist", "assisting", "perform", "performing",
    "responsible", "responsibilities", "provide", "providing", "develop",
    "developing", "implement", "implementing", "manage", "managing", "oversee",
    "overseeing", "monitor", "monitoring", "execute", "executing", "conduct",
    "conducting", "prepare", "preparing", "review", "reviewing", "analyse",
    "analyzing", "report", "business", "organization", "organisation", "role",
    "position", "candidate", "applicant", "professional", "individual", "person",
    "employee", "join", "joining", "department", "division", "member", "company",
    "firm", "client", "clients", "internal", "external", "stakeholder",
    "stakeholders", "function", "functions", "activities", "activity", "process",
    "processes", "strategy", "strategic", "objective", "objectives", "goal",
    "goals", "target", "targets", "plan", "planning", "years", "year", "months",
    "month", "minimum", "maximum", "least", "above", "below", "strong",
    "excellent", "good", "best", "ability", "knowledge", "understanding",
    "working", "experience", "expertise", "hands", "proficiency", "proficient",
    "skilled", "exposure", "proven", "demonstrated", "preferred", "required",
    "ctc", "lpa", "salary", "package", "location", "immediate", "joiner",
    "notice", "period", "openings", "opening", "vacancy", "vacancies", "apply",
    "application", "deadline", "bengaluru", "bangalore", "karnataka",
    "kadubeesanahalli", "layout", "kaverappa", "main", "square", "road",
    "sector", "phase", "block", "near", "opposite", "behind", "based",
    "onsite", "hybrid", "remote", "documentation", "contract", "contracts",
    "reports", "reporting", "relationships", "info", "information", "on-ground",
    "onground", "ground", "field", "visit", "visits", "private", "limited",
    "ltd", "pvt", "pvt.", "inc", "incorporated", "corp", "corporation", "llc",
    "llp", "technologies", "solutions", "services", "systems", "group",
    "holdings", "enterprises", "industries", "labs", "global", "international",
    "corporate", "industry", "travel", "related", "highly", "serve", "primary",
    "representative", "integrity", "atomgrid", "atomgrid.in", "work", "working",
    "duties", "task", "tasks", "responsibility",
}


def build_jd_blocklist(jd_text: str) -> set[str]:
    """Dynamically builds blocklist for company names + locations from the JD."""
    if not jd_text or not jd_text.strip():
        return set()

    blocklist: set[str] = set()
    lower = jd_text.lower()

    corporate = {
        "private", "limited", "ltd", "pvt", "inc", "incorporated",
        "corp", "corporation", "llc", "llp", "technologies", "solutions",
        "services", "systems", "group", "holdings", "enterprises",
        "industries", "labs", "global", "international", "corporate"
    }
    for word in corporate:
        if word in lower:
            blocklist.add(word)

    location_words = {
        "bengaluru", "bangalore", "karnataka", "kadubeesanahalli",
        "layout", "kaverappa", "main", "square", "road", "sector",
        "phase", "block", "near", "opposite", "behind", "location"
    }
    for word in location_words:
        if word in lower:
            blocklist.add(word)

    patterns = [
        r"\b([A-Za-z][A-Za-z0-9&'\-. ]{2,50}?)\s+(?:technologies|solutions|services|private limited|pvt\.?\s*ltd\.?|limited|ltd)\b",
        r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\s+(?:layout|square|main|road|sector)\b",
    ]
    for pat in patterns:
        for match in re.finditer(pat, jd_text, flags=re.IGNORECASE):
            for word in re.findall(r"\b\w+\b", match.group(0)):
                w = word.lower().strip(".,")
                if len(w) > 2:
                    blocklist.add(w)

    bad_tokens = {
        "dispatch", "atomgrid", "truuchem", "truchem", "obeya", "spruce", "embassy",
        "documentation", "contract", "reports", "relationships", "on-ground"
    }
    for token in bad_tokens:
        if token in lower:
            blocklist.add(token)

    return blocklist


def clean_keywords(keywords: list[str], jd_text: str = "") -> list[str]:
    if not keywords:
        return []

    blocklist = JD_NOISE_WORDS.copy()
    if jd_text:
        blocklist.update(build_jd_blocklist(jd_text))

    extra_generic = {
        "pioneering", "innovation", "market", "intelligence", "reliable",
        "operate", "sectors", "day-to-day", "share", "mission", "creating",
        "daily", "basis", "track", "revolutionize", "email", "quality",
        "sites", "standards", "confidentiality", "partners", "transfer"
    }

    cleaned = []
    seen = set()

    for kw in keywords:
        if not isinstance(kw, str):
            continue
        k = kw.lower().strip()

        if len(k) < 4:
            continue
        if k in blocklist or k in extra_generic:
            continue

        if k not in seen:
            seen.add(k)
            cleaned.append(kw)

    return cleaned


# ---------------------------------------------------------------------------
# EDUCATION LEVELS
# ---------------------------------------------------------------------------
EDUCATION_KEYWORDS = {
    "phd": 6, "ph.d": 6, "ph.d.": 6, "doctorate": 6, "doctoral": 6, "d.sc": 6,
    "mba": 5, "m.b.a": 5, "pgdm": 5, "pgdbm": 5, "executive mba": 5,
    "m.tech": 4, "mtech": 4, "m.e.": 4, "m.sc": 4, "msc": 4,
    "master": 4, "masters": 4, "post graduate": 4, "postgraduate": 4,
    "b.tech": 3, "btech": 3, "b.e.": 3, "b.e": 3, "b.sc": 3, "bsc": 3,
    "bachelor": 3, "bachelors": 3, "b.a": 3, "undergraduate": 3,
    "b.com": 3, "bcom": 3, "b.pharm": 3, "b.agri": 3, "b.agric": 3,
    "b.sc agri": 3, "bsc agri": 3,
    "diploma": 2, "polytechnic": 2, "iti": 2,
    "12th": 1, "hsc": 1, "intermediate": 1, "higher secondary": 1,
    "10th": 0, "ssc": 0, "matriculation": 0, "secondary school": 0,
}


def extract_education_level(text: str) -> tuple[int, str]:
    """Returns (level_int, found_qualification_string). -1 if not found."""
    lower = (text or "").lower()
    best_level = -1
    best_qual = ""
    for qual, level in EDUCATION_KEYWORDS.items():
        if re.search(rf"\b{re.escape(qual)}\b", lower):
            if level > best_level:
                best_level = level
                best_qual = qual.upper()
    return best_level, best_qual


def parse_required_education_level(required_edu: str) -> int:
    """Parse the required education string from JD into a level int."""
    if not required_edu:
        return -1
    lower = required_edu.lower()
    best = -1
    for qual, level in EDUCATION_KEYWORDS.items():
        if qual in lower:
            best = max(best, level)
    return best


# ---------------------------------------------------------------------------
# AI-POWERED JD REQUIREMENTS EXTRACTION
# ---------------------------------------------------------------------------
def extract_jd_requirements_ai(jd_text: str, api_key: str, model: str) -> dict:
    if not api_key or not (jd_text or "").strip():
        return {}
    try:
        system = (
            "You are a senior technical recruiter. "
            "Extract ONLY factual job requirements. "
            "Never include soft skills in core_skills. "
            "Return valid JSON only."
        )
        prompt = f"""Extract hiring requirements from this job description. Return ONLY valid JSON with no markdown, no explanation, no code fences.

Output format:
{{
  "role": "exact job title from JD",
  "min_experience_years": 0,
  "core_skills": ["domain/technical skill 1", "domain/technical skill 2"],
  "tools_technologies": ["tool or software or certification"],
  "required_education": "minimum education qualification as a string, e.g. B.Tech in Mechanical Engineering",
  "preferred_education": "preferred additional qualification or empty string",
  "industry": "industry sector"
}}

Strict rules:
- core_skills must contain ONLY hard technical or domain-specific skills. NEVER include soft skills.
- min_experience_years: extract the floor number only.
- Do NOT include the company name in any field
- Be specific: "agrochemical formulation" not just "chemical"; "SAP MM" not just "software"
- If education is not mentioned, use empty string for required_education

JD:
{jd_text[:3000]}"""

        data = chat_json(system, prompt, api_key, model, max_tokens=700, temperature=0)
        try:
            data["min_experience_years"] = float(data.get("min_experience_years", 0) or 0)
        except (ValueError, TypeError):
            data["min_experience_years"] = 0.0
        return data
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# YEAR RANGE FALLBACK PARSER
# ---------------------------------------------------------------------------
def extract_year_ranges_simple(text: str) -> float:
    """Improved year range parser."""
    current_year = datetime.now().year
    patterns = [
        r"(\d{4})\s*[-–—to]+\s*(\d{4}|present|current|now|till date)",
        r"(\d{4})\s*[-–—]+\s*(present|current|now)",
        r"from\s+(\d{4})\s+to\s+(\d{4}|present)",
        r"(\d{4})\s*[-–—]\s*present",
    ]

    total_months = 0
    seen_years = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text or "", flags=re.I):
            try:
                start = int(match.group(1))
                end_str = match.group(2).lower() if len(match.groups()) > 1 else ""

                if end_str in ["present", "current", "now", "till date"]:
                    end = current_year
                else:
                    end = int(end_str)

                if 2005 <= start < end <= current_year + 1:
                    if start not in seen_years:
                        total_months += (end - start) * 12
                        seen_years.add(start)
            except Exception:
                continue

    return round(total_months / 12, 1) if total_months > 0 else 0.0


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def name_from_email_address(email: str) -> str:
    local = (email or "").split("@")[0]
    local = re.sub(r"\+.*$", "", local)
    local = re.sub(r"[_\-.]+", " ", local)
    local = re.sub(r"[^A-Za-z]+", " ", local)
    parts = [part for part in local.split() if len(part) > 1 and not part.isdigit()]
    return " ".join(part.capitalize() for part in parts[:3])


def normalize_email_text(text: str) -> str:
    text = text or ""
    text = text.replace("\u200b", "")
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*\{at\}\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*\(\s*at\s*\)\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.I)
    text = re.sub(r"\s*\{dot\}\s*", ".", text, flags=re.I)
    text = re.sub(r"\s*\(\s*dot\s*\)\s*", ".", text, flags=re.I)
    text = re.sub(
        r"(?i)(?<=[A-Za-z0-9._%+\-])\s+at\s+(?=[A-Za-z0-9._%+\-]+\s+(?:dot|\.))",
        "@",
        text,
    )
    text = re.sub(r"(?i)(?<=[A-Za-z0-9._%+\-])\s+dot\s+(?=[A-Za-z]{2,24}\b)", ".", text)
    text = re.sub(r"(?i)(?<=[A-Za-z0-9._%+\-])\s+dot\s+(?=[A-Za-z0-9._%+\-]+\s+(?:dot|\.))", ".", text)
    text = re.sub(r"(?<=\w)\s*@\s*(?=\w)", "@", text)
    return text


def extract_email(text: str) -> str:
    normalized = normalize_email_text(text)
    pattern = r"\b[A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@[A-Za-z0-9][A-Za-z0-9.\-]{1,250}\.[A-Za-z]{2,24}\b"
    candidates = []
    throwaway_domains = {"example.com", "test.com", "email.com", "mail.com"}

    for match in re.finditer(pattern, normalized):
        email = match.group(0).strip(".,;:()[]{}<>").lower()
        local, domain = email.split("@", 1)
        if ".." in email or domain.startswith(".") or domain.endswith("."):
            continue
        if domain in throwaway_domains:
            continue
        if len(local) < 3 or local.isdigit():
            continue
        penalty = 20 if local in GENERIC_EMAIL_PREFIXES else 0
        score = 100 - match.start() / max(len(normalized), 1) * 20 - penalty
        candidates.append((score, email))

    if not candidates:
        return ""
    candidates.sort(reverse=True, key=lambda item: item[0])
    return candidates[0][1]


def extract_phone(text: str) -> str:
    compact = re.sub(r"[\s().-]+", "", text or "")
    patterns = [
        r"(?:\+91)?[6-9]\d{9}",
        r"\+\d{10,15}",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            phone = match.group(0)
            if phone.startswith("+91") and len(phone) == 13:
                return phone
            if len(phone) == 10 and phone[0] in "6789":
                return phone
            if phone.startswith("+"):
                return phone
    return ""


# ---------------------------------------------------------------------------
# OCR / EXPORT ARTIFACT REPAIR
# ---------------------------------------------------------------------------
def repair_letter_spaced_text(line: str) -> str:
    """
    Detect lines like 'J O H N   D O E' and collapse to 'JOHN DOE'.
    """
    if not line or len(line) < 5:
        return line

    tokens = line.split(" ")
    single_letter_ratio = sum(1 for t in tokens if len(t) == 1 and t.isalpha()) / max(len(tokens), 1)

    if single_letter_ratio < 0.5:
        return line

    words = []
    current = []
    for tok in tokens:
        if tok == "":
            if current:
                words.append("".join(current))
                current = []
            continue
        if len(tok) == 1 and tok.isalpha():
            current.append(tok)
        else:
            if current:
                words.append("".join(current))
                current = []
            words.append(tok)
    if current:
        words.append("".join(current))

    return " ".join(w for w in words if w)


def clean_name_candidate(value: str) -> str:
    if not value:
        return ""
    value = repair_letter_spaced_text(value)
    value = normalize_email_text(value)
    value = re.sub(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}\b", " ", value)
    value = re.sub(r"(?:\+91)?[6-9]\d{9}", " ", value)
    value = re.sub(r"https?://\S+|www\.\S+", " ", value, flags=re.I)
    value = re.sub(r"^(id|name|candidate|applicant|full\s*name)\s*[:\-]?\s*", "", value, flags=re.I)
    value = re.sub(
        r"^(mr|mrs|ms|miss|mx|dr|shri|smt|er|eng|prof|capt|col|sir|madam)\.?\s+",
        "", value, flags=re.I,
    )
    value = re.sub(
        r"\b(?:email|e-mail|mail|mobile|phone|contact|tel|telephone|linkedin|github|portfolio|address|location|dob|date of birth)\b",
        " ", value, flags=re.I,
    )
    value = re.sub(r"[^A-Za-z .'-]", " ", value)
    value = normalize_whitespace(value)
    if not value:
        return ""
    # Preserve natural casing for mixed names, then title-case cleanly
    parts = []
    for p in value.split():
        if p.isupper() and len(p) > 1:
            parts.append(p.title())
        else:
            parts.append(p[0].upper() + p[1:] if p else p)
    return " ".join(parts).strip(" .'-")

def filename_name_candidate(filename: str) -> str:
    if not filename:
        return ""
    stem = re.sub(r"\.(pdf|docx|doc|txt)$", "", filename, flags=re.I)
    stem = re.sub(r"(?i)\b(resume|cv|curriculum|vitae|profile|updated|final|latest|copy|new|old)\b", " ", stem)
    stem = re.sub(r"[_\-.,()[\]{}]+", " ", stem)
    stem = re.sub(r"\d+", " ", stem)
    clean = clean_name_candidate(stem)
    words = clean.split()
    if 2 <= len(words) <= 5 and not any(word.lower() in NAME_STOPWORDS for word in words):
        return clean.title()
    return ""


def extract_name_from_email(text: str) -> str:
    email = extract_email(text)
    if not email:
        return ""
    local = email.split("@", 1)[0]
    if local in GENERIC_EMAIL_PREFIXES:
        return ""
    name = name_from_email_address(email)
    parts = [p for p in name.split() if p.lower() not in GENERIC_EMAIL_PREFIXES and len(p) > 1]
    # Allow single strong token now (used as last resort)
    return " ".join(parts) if parts else ""


COMMON_INDIAN_NAME_TOKENS = {
    "kumar", "kumari", "singh", "sharma", "verma", "gupta", "patel", "shah",
    "reddy", "rao", "nair", "menon", "iyer", "iyengar", "pillai", "das",
    "sen", "roy", "banerjee", "mukherjee", "chatterjee", "chakraborty",
    "bose", "ghosh", "yadav", "mishra", "pandey", "tiwari", "tripathi",
    "dubey", "chauhan", "rathore", "rana", "thakur", "bhatt", "joshi",
    "desai", "mehta", "shetty", "kulkarni", "deshpande", "patil", "jain",
    "agarwal", "aggarwal", "bansal", "goyal", "goel", "khan", "ahmed",
    "ali", "hussain", "sheikh", "syed", "ansari", "malik", "qureshi",
    "biswas", "sarkar", "dutta", "chowdhury", "chaudhary", "prasad",
    "raju", "naidu", "gowda", "hegde", "bhat", "acharya", "trivedi",
    "vishesh", "aarav", "rohan", "aditya", "vivaan", "arjun", "ishaan",
    "ananya", "priya", "neha", "pooja", "kavya", "sneha", "riya",
}


BAD_NAME_WORDS = {
    "resume", "curriculum", "vitae", "cv", "summary", "profile",
    "professional", "experience", "education", "skills", "projects",
    "certifications", "languages", "achievements", "objective",
    "declaration", "contact", "mobile", "phone", "email", "linkedin",
    "github", "portfolio", "address", "location", "references",
    "manager", "engineer", "developer", "analyst", "consultant",
    "executive", "specialist", "director", "lead", "intern",
    "associate", "head", "officer", "coordinator", "assistant",
    "senior", "junior", "trainee", "architect", "designer",
    "recruiter", "hr", "sales", "marketing", "finance", "operations",
    "delhi", "mumbai", "bangalore", "bengaluru", "pune", "hyderabad",
    "chennai", "kolkata", "ahmedabad", "noida", "gurugram", "gurgaon",
    "india",
}


def score_name_candidate(candidate: str, position: int, email_tokens: set[str], email_local: str = "") -> int:
    candidate = clean_name_candidate(candidate)
    if not candidate:
        return -999

    words = candidate.split()
    if not (1 <= len(words) <= 5):          # allow single first name + strong email signal
        return -999
    if any(c.isdigit() for c in candidate) or len(candidate) > 55:
        return -999
    if any(w.lower() in BAD_NAME_WORDS for w in words):
        return -999
    if any(w.lower() in NAME_STOPWORDS for w in words):
        return -999

    score = 0

    # Position bias (name almost always in first few lines)
    if position == 0:
        score += 75
    elif position <= 2:
        score += 55
    elif position <= 5:
        score += 35
    elif position <= 12:
        score += 15
    else:
        score -= 5

    # Length preference
    if len(words) == 2:
        score += 40
    elif len(words) == 3:
        score += 32
    elif len(words) == 4:
        score += 18
    elif len(words) == 1:
        score += 5   # only useful with strong email overlap

    # Title-case / proper-name look
    if all(w[0].isupper() for w in words if w):
        score += 25

    # Email overlap (very strong signal)
    lower_words = [w.lower() for w in words]
    overlaps = sum(1 for w in lower_words if w in email_tokens)
    score += overlaps * 50
    if overlaps >= 2:
        score += 40

    if overlaps == 0 and email_local:
        hits = sum(1 for w in words if len(w) >= 3 and w.lower() in email_local)
        score += hits * 28

    # Common Indian surname/first-name boost
    indian_hits = sum(1 for w in lower_words if w in COMMON_INDIAN_NAME_TOKENS)
    score += indian_hits * 12

    return score


def extract_name_ner(text: str) -> str:
    """Return the *best* PERSON entity, not the first one."""
    if NLP is None:
        return ""
    try:
        doc = NLP(text[:3500])
        best = ""
        best_score = -999
        email = extract_email(text)
        email_tokens = set()
        email_local = ""
        if email:
            email_name = name_from_email_address(email)
            email_tokens = {t.lower() for t in email_name.split()}
            email_local = email.split("@")[0].lower()

        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            candidate = clean_name_candidate(ent.text)
            words = candidate.split()
            if not (1 <= len(words) <= 4):
                continue
            if any(w.lower() in BAD_NAME_WORDS for w in words):
                continue
            # Prefer entities near the top of the document
            pos = text.find(ent.text)
            position_score = 0
            if pos < 200:
                position_score = 40
            elif pos < 600:
                position_score = 20
            score = score_name_candidate(candidate, 2, email_tokens, email_local) + position_score
            if score > best_score:
                best_score = score
                best = candidate
        return best if best_score >= 40 else ""
    except Exception:
        return ""

def extract_name(text: str, filename: str = "") -> str:
    text = text or ""
    lines = [
        normalize_whitespace(repair_letter_spaced_text(line))
        for line in text.splitlines()
        if normalize_whitespace(line)
    ]

    email_name = extract_name_from_email(text)
    email_tokens = {t.lower() for t in email_name.split()} if email_name else set()
    detected_email = extract_email(text)
    email_local = detected_email.split("@", 1)[0].lower() if detected_email else ""

    candidates = []

    # 1. Explicit labels (highest priority)
    patterns = [
        r"(?:full\s*name|candidate\s*name|applicant\s*name|employee\s*name|name)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{2,60})",
        r"(?:i\s+am|my\s+name\s+is)\s+([A-Za-z][A-Za-z .'-]{2,60})",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.I):
            candidates.append(
                (score_name_candidate(m.group(1), 0, email_tokens, email_local) + 90, m.group(1))
            )
            break

    # 2. spaCy NER (now picks best entity)
    ner_name = extract_name_ner(text)
    if ner_name:
        candidates.append(
            (score_name_candidate(ner_name, 1, email_tokens, email_local) + 60, ner_name)
        )

    # 3. Top lines – also strip trailing designation noise
    for idx, line in enumerate(lines[:50]):
        raw = line
        # Remove common trailing role/title after name
        cleaned_line = re.split(
            r"\s*[–—\-|•]\s*|\s{2,}|\s+(?:R&D|Scientist|Manager|Engineer|Lead|Head|Director|Executive)\b",
            raw, maxsplit=1, flags=re.I
        )[0]
        if cleaned_line.lower().rstrip(":") in BAD_NAME_WORDS or len(cleaned_line) > 55:
            continue
        score = score_name_candidate(cleaned_line, idx, email_tokens, email_local)
        if score > 25:
            candidates.append((score, cleaned_line))

    # 4. Email-derived
    if email_name:
        candidates.append(
            (score_name_candidate(email_name, 6, email_tokens, email_local) + 35, email_name)
        )

    # 5. Filename
    file_name = filename_name_candidate(filename)
    if file_name:
        candidates.append(
            (score_name_candidate(file_name, 10, email_tokens, email_local) + 20, file_name)
        )

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_name = candidates[0]
        cleaned = clean_name_candidate(best_name)
        if cleaned and best_score >= 48:
            return cleaned

    # Last resort – even a single strong token from email is better than Unknown
    if email_name:
        return clean_name_candidate(email_name)

    return "Unknown Candidate"


# ---------------------------------------------------------------------------
# EXPERIENCE EXTRACTION
# ---------------------------------------------------------------------------
def calculate_total_experience(ranges: list[tuple[int, int, int, int]]) -> float:
    intervals = []
    current_year = datetime.now().year

    for start_year, start_month, end_year, end_month in ranges:
        if start_year < 1975 or start_year > current_year:
            continue
        start = start_year * 12 + start_month
        end = end_year * 12 + end_month
        if end <= start:
            continue
        intervals.append((start, end))

    if not intervals:
        return 0.0

    intervals.sort()
    merged: list[list[int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    months = sum(end - start for start, end in merged)
    return round(months / 12, 1)


def parse_date_ranges(text: str) -> list[tuple[int, int, int, int]]:
    ranges = []
    current_year = datetime.now().year
    current_month = datetime.now().month

    for match in DATE_RANGE_REGEX.findall(text or ""):
        start_month, start_year, present, end_month, end_year = match
        start_year_num = int(start_year)
        start_month_num = MONTH_MAP.get((start_month or "").lower(), 1)

        if present:
            end_year_num = current_year
            end_month_num = current_month
        else:
            end_year_num = int(end_year)
            end_month_num = MONTH_MAP.get((end_month or "").lower(), 12)

        ranges.append((start_year_num, start_month_num, end_year_num, end_month_num))

    return ranges


def explicit_years_of_experience(text: str) -> float:
    patterns = [
        r"(?:total\s+)?experience\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:total\s+)?experience",
        r"(\d{1,2})\s*(?:years?|yrs?)?\s*(?:and|&|,)?\s*(\d{1,2})\s*(?:months?|mos?)\s*(?:of\s+)?experience",
        r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b",
        r"(?:over|more\s+than|above)\s+(\d{1,2})\s*(?:years?|yrs?)",
    ]
    best = 0.0
    for pattern in patterns:
        for match in re.finditer(pattern, text or "", flags=re.I):
            try:
                years = float(match.group(1))
                if len(match.groups()) >= 2 and match.group(2):
                    years += float(match.group(2)) / 12
                if 0 < years < 55:
                    best = max(best, years)
            except (ValueError, IndexError):
                pass
    return round(best, 1)


def extract_experience(text: str) -> float:
    if not text:
        return 0.0

    lower = text.lower()

    explicit = explicit_years_of_experience(lower)
    if explicit > 0:
        return explicit

    ranges = parse_date_ranges(lower)
    if ranges:
        return calculate_total_experience(ranges)

    year_only = extract_year_ranges_simple(lower)
    if year_only > 0:
        return year_only

    return 0.0


# ---------------------------------------------------------------------------
# KEYWORD EXTRACTION
# ---------------------------------------------------------------------------
def extract_keywords(
    text: str,
    extra_keywords: str = "",
    limit: int = 30,
    jd_requirements: dict | None = None,
) -> list[str]:
    text = text or ""
    lower = text.lower()
    configured = [kw.strip().lower() for kw in (extra_keywords or "").split(",") if kw.strip()]

    if jd_requirements:
        ai_keywords = []
        for skill in jd_requirements.get("core_skills") or []:
            if isinstance(skill, str) and skill.strip():
                ai_keywords.append(skill.lower().strip())
        for tool in jd_requirements.get("tools_technologies") or []:
            if isinstance(tool, str) and tool.strip():
                ai_keywords.append(tool.lower().strip())

        combined = configured + ai_keywords
        seen = set()
        result = []
        for kw in combined:
            if kw and kw not in seen:
                seen.add(kw)
                result.append(kw)
        return clean_keywords(result, text)[:limit]

    combined_stop = STOP_WORDS | JD_NOISE_WORDS

    skill_hits = []
    for canonical_skill, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias.lower())}\b", lower):
                skill_hits.append(canonical_skill)
                break

    words = re.findall(r"\b[a-zA-Z][a-zA-Z+#.-]{2,}\b", lower)
    words = [w.strip(".-") for w in words if w not in combined_stop and len(w) >= 4]
    common = [word for word, _ in Counter(words).most_common(limit)]

    keywords_list = []
    for item in configured + skill_hits + common:
        if item and item not in keywords_list and item not in combined_stop:
            keywords_list.append(item)

    return clean_keywords(keywords_list, text)[:limit]


def extract_skills(text: str) -> list[str]:
    lower = (text or "").lower()
    found = set()
    for canonical_skill, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias.lower())}\b", lower):
                found.add(canonical_skill)
                break
    return sorted(found)


# ---------------------------------------------------------------------------
# JD PARSING HELPERS
# ---------------------------------------------------------------------------
def parse_min_experience(jd_text: str) -> float:
    patterns = [
        r"(\d{1,2})\s*\+\s*(?:years?|yrs?)",
        r"(\d{1,2})\s*[-–]\s*\d{1,2}\s*(?:years?|yrs?)",
        r"(?:minimum|min\.?)\s*(?:of\s+)?(\d{1,2})\s*(?:years?|yrs?)",
        r"at\s+least\s*(\d{1,2})\s*(?:years?|yrs?)",
        r"(?:over|more\s+than)\s+(\d{1,2})\s*(?:years?|yrs?)",
        r"(\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+)?experience",
        r"experience\s*[:\-]\s*(\d{1,2})\s*(?:years?|yrs?)?",
    ]
    candidates = []
    for pattern in patterns:
        for match in re.finditer(pattern, jd_text or "", flags=re.I):
            try:
                val = float(match.group(1))
                if 0 < val < 40:
                    candidates.append(val)
            except (ValueError, IndexError):
                pass
    return min(candidates) if candidates else 0.0


def clean_role_title(value: str) -> str:
    value = normalize_whitespace(value)
    value = re.split(
        r"\b(location|experience|department|reports|reporting|salary|ctc|about|overview|responsibilities|qualification)\b",
        value,
        flags=re.I,
    )[0]
    value = re.sub(r"[^A-Za-z0-9 /&+.,'-]", " ", value)
    value = normalize_whitespace(value).strip(" -:.,")
    value = re.sub(r"^(for|as|a|an|the)\s+", "", value, flags=re.I)
    words = value.split()
    if len(words) > 8:
        value = " ".join(words[:8])
    return value.title() if value else ""


def extract_role_from_jd(jd_text: str, fallback: str = "") -> str:
    if fallback.strip():
        return clean_role_title(fallback)

    text = jd_text or ""
    lines = [normalize_whitespace(line) for line in text.splitlines() if normalize_whitespace(line)]
    patterns = [
        r"(?:job\s*)?title\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9 /&+.,'-]{2,90})",
        r"(?:role|position|designation)\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9 /&+.,'-]{2,90})",
        r"(?:we\s+are\s+)?hiring\s+(?:for\s+)?(?:a|an|the)?\s*([A-Za-z0-9][A-Za-z0-9 /&+.,'-]{2,90})",
        r"job description\s*(?:for|:|-)\s*([A-Za-z0-9][A-Za-z0-9 /&+.,'-]{2,90})",
        r"opening\s+(?:for|:|-)\s*([A-Za-z0-9][A-Za-z0-9 /&+.,'-]{2,90})",
    ]

    for line in lines[:35]:
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.I)
            if match:
                role = clean_role_title(match.group(1))
                if role:
                    return role

    return "Open Role"


def ai_extract_role_title(jd_text: str, api_key: str, model: str) -> str:
    if not api_key or not jd_text.strip():
        return ""
    try:
        data = chat_json(
            system="Extract the exact hiring role title from a job description. Return JSON only.",
            user=f'Return only JSON like {{"title": "..."}}. JD:\n{jd_text[:3500]}',
            api_key=api_key,
            model=model,
            max_tokens=80,
            temperature=0,
        )
        title = clean_role_title(str(data.get("title", "")).strip())
        return title if title and title != "Open Role" else ""
    except Exception:
        return ""


def detect_role_title(jd_text: str, fallback: str = "", api_key: str = None, model: str = None) -> str:
    if fallback.strip():
        return clean_role_title(fallback)
    if api_key and model:
        ai_title = ai_extract_role_title(jd_text, api_key, model)
        if ai_title:
            return ai_title
    return extract_role_from_jd(jd_text)


def extract_keywords_from_jd(text: str, extra_keywords: str = "", limit: int = 35) -> list[str]:
    return extract_keywords(text, extra_keywords, limit)


def parse_min_experience_from_requirements(jd_requirements: dict) -> float:
    try:
        val = float(jd_requirements.get("min_experience_years", 0) or 0)
        return val if 0 < val < 40 else 0.0
    except (ValueError, TypeError):
        return 0.0


def profile_key(name: str, email: str, phone: str) -> str:
    if email:
        raw = f"email:{email.lower().strip()}"
    elif phone:
        digits = re.sub(r"\D+", "", phone)
        raw = f"phone:{digits}"
    else:
        raw = f"name:{normalize_whitespace(name).lower()}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
