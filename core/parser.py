import hashlib
import json
import re
from collections import Counter
from datetime import datetime

NLP = None

from .constants import (
    DATE_RANGE_REGEX,
    GENERIC_EMAIL_PREFIXES,
    MONTH_MAP,
    NAME_STOPWORDS,
    SKILL_ALIASES,
    STOP_WORDS,
)


# ---------------------------------------------------------------------------
# NOISE FILTER — words that appear in JDs but have zero resume-matching value
# ---------------------------------------------------------------------------
JD_NOISE_WORDS = {
    # Soft skills (judged on call, not on paper)
    "communication", "communications", "interpersonal", "teamwork", "leadership",
    "collaboration", "collaborative", "initiative", "proactive", "problem",
    "solving", "critical", "thinking", "adaptable", "adaptability",
    "multitask", "multitasking", "self", "motivated", "motivation", "driven",
    "passionate", "enthusiastic", "detail", "oriented", "hardworking",
    "dedicated", "innovative", "creative", "dynamic", "results", "focused",
    "organised", "organized", "punctual", "diligent", "energetic",
    # Generic JD verbs (every JD has these)
    "across", "within", "between", "through", "along", "around", "including",
    "regarding", "ensure", "ensuring", "maintain", "maintaining", "coordinate",
    "coordinating", "handle", "handling", "assist", "assisting", "perform",
    "performing", "responsible", "responsibilities", "provide", "providing",
    "support", "supporting", "develop", "developing", "implement",
    "implementing", "manage", "managing", "oversee", "overseeing", "monitor",
    "monitoring", "execute", "executing", "deliver", "delivering", "drive",
    "driving", "build", "building", "conduct", "conducting", "prepare",
    "preparing", "review", "reviewing", "analyse", "analyzing", "report",
    # Generic nouns used as filler
    "business", "organization", "organisation", "role", "position", "candidate",
    "applicant", "professional", "individual", "person", "employee", "join",
    "joining", "department", "division", "member", "company", "firm",
    "client", "clients", "internal", "external", "stakeholder", "stakeholders",
    "function", "functions", "activities", "activity", "process", "processes",
    "strategy", "strategic", "objective", "objectives", "goal", "goals",
    "target", "targets", "plan", "planning",
    # Quantity / descriptor words
    "years", "year", "months", "month", "minimum", "maximum", "least",
    "above", "below", "strong", "excellent", "good", "best", "ability",
    "knowledge", "understanding", "working", "experience", "expertise",
    "hands", "proficiency", "proficient", "skilled", "exposure",
    "proven", "demonstrated", "preferred", "required",
    # Indian JD boilerplate
    "ctc", "lpa", "salary", "package", "location", "immediate", "joiner",
    "notice", "period", "openings", "opening", "vacancy", "vacancies",
    "apply", "application", "deadline",

    # === FIX 1: Legal entity words + corporate boilerplate ===
    "private", "limited", "ltd", "pvt", "pvt.", "inc", "incorporated",
    "corp", "corporation", "llc", "llp", "technologies", "solutions",
    "services", "systems", "group", "holdings", "enterprises", "industries",
    "labs", "global", "international", "corporate",
    "dispatch", "atomgrid", "truuchem", "truchem", "obeya", "spruce", "embassy",
}


# ---------------------------------------------------------------------------
# NEW: Dynamic company name blocklist (multi-layered filtering)
# ---------------------------------------------------------------------------
def build_company_blocklist(jd_text: str) -> set[str]:
    """Dynamically extracts company names and corporate patterns from the JD itself."""
    if not jd_text or not jd_text.strip():
        return set()

    blocklist: set[str] = set()
    lower = jd_text.lower()

    # 1. Common corporate suffixes (always block when present in JD)
    corporate_suffixes = {
        "private", "limited", "ltd", "pvt", "inc", "incorporated",
        "corp", "corporation", "llc", "llp", "technologies", "solutions",
        "services", "systems", "group", "holdings", "enterprises",
        "industries", "labs", "global", "international", "corporate"
    }
    for word in corporate_suffixes:
        if word in lower:
            blocklist.add(word)

    # 2. Extract company name tokens using common Indian/global patterns
    patterns = [
        r'\b([A-Za-z][A-Za-z0-9&\'\-\. ]{2,50}?)\s+(?:technologies|solutions|services|systems|private limited|pvt\.?\s*ltd\.?|limited|ltd\.?)\b',
        r'\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s+(?:pvt|ltd|inc|corp|technologies|private)\b',
    ]
    for pat in patterns:
        for match in re.finditer(pat, jd_text, flags=re.IGNORECASE):
            phrase = match.group(1).strip()
            for word in re.findall(r'\b\w+\b', phrase):
                w = word.lower().strip('.,')
                if len(w) > 2:
                    blocklist.add(w)

    # 3. Hardcoded problematic tokens from this JD (safety net)
    problematic = {"dispatch", "atomgrid", "truuchem", "truchem", "obeya", "spruce", "embassy"}
    for p in problematic:
        if p in lower:
            blocklist.add(p)

    return blocklist


def clean_keywords(keywords: list[str], jd_text: str = "") -> list[str]:
    """Post-processor that nukes company names, proper nouns patterns, and boilerplate.
    Applied to BOTH AI path and heuristic path.
    """
    if not keywords:
        return []

    blocklist = JD_NOISE_WORDS.copy()
    if jd_text:
        blocklist.update(build_company_blocklist(jd_text))

    cleaned: list[str] = []
    seen: set[str] = set()

    for kw in keywords:
        if not isinstance(kw, str):
            continue
        k = kw.lower().strip()
        if not k or k in blocklist or len(k) < 3:
            continue

        # Extra aggressive pattern filter for company-style phrases
        if re.search(r'\b(private|limited|ltd|pvt|technologies|solutions|services|obeya|spruce|embassy|atomgrid|dispatch|truuchem|truchem)\b', k):
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
    """
    Use AI to extract structured hiring requirements from the JD.
    Returns dict with role, min_experience_years, core_skills,
    tools_technologies, required_education, preferred_education, industry.
    """
    if not api_key or not (jd_text or "").strip():
        return {}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
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
- core_skills must contain ONLY hard technical or domain-specific skills. NEVER include soft skills (communication, teamwork, leadership, interpersonal, problem-solving, adaptability, etc.)
- min_experience_years: extract the floor number only. "10+ years" -> 10, "5-8 years" -> 5, "minimum 3 years" -> 3
- Do NOT include the company name in any field
- Be specific: "agrochemical formulation" not just "chemical"; "SAP MM" not just "software"
- If education is not mentioned, use empty string for required_education

JD:
{jd_text[:3000]}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior technical recruiter. "
                        "Extract ONLY factual job requirements. "
                        "Never include soft skills in core_skills. "
                        "Return valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=700,
            timeout=25,
        )
        raw = re.sub(r"```json|```", "", response.choices[0].message.content or "{}").strip()
        data = json.loads(raw)
        # Sanitise min_experience_years
        try:
            data["min_experience_years"] = float(data.get("min_experience_years", 0) or 0)
        except (ValueError, TypeError):
            data["min_experience_years"] = 0.0
        return data
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# BETTER EXPERIENCE EXTRACTION
# ---------------------------------------------------------------------------
def extract_year_ranges_simple(text: str) -> float:
    """
    Fallback: extract experience from year-only date ranges like
    '2015 to 2020', '2015 - Present', '2010 – 2015'.
    """
    current_year = datetime.now().year
    pattern = (
        r"\b((?:19|20)\d{2})\s*(?:to|[-–])\s*"
        r"((?:19|20)\d{2}|present|current|till\s*date|now)\b"
    )
    ranges = []
    for match in re.finditer(pattern, text or "", flags=re.I):
        try:
            start = int(match.group(1))
            end_raw = match.group(2).strip().lower()
            if end_raw in ("present", "current", "now") or "till" in end_raw:
                end = current_year
            else:
                end = int(end_raw)
            if 1970 <= start <= current_year and start < end <= current_year + 1:
                ranges.append((start * 12, end * 12))
        except (ValueError, IndexError):
            continue

    if not ranges:
        return 0.0
    ranges.sort()
    merged: list[list[int]] = []
    for s, e in ranges:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    total_months = sum(e - s for s, e in merged)
    return round(total_months / 12, 1)


# ---------------------------------------------------------------------------
# (rest of the original helpers preserved below, with parse_min_experience
# and extract_keywords replaced)
# ---------------------------------------------------------------------------

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
    THROWAWAY_DOMAINS = {"example.com", "test.com", "email.com", "mail.com"}
    for match in re.finditer(pattern, normalized):
        email = match.group(0).strip(".,;:()[]{}<>").lower()
        local, domain = email.split("@", 1)
        if ".." in email or domain.startswith(".") or domain.endswith("."):
            continue
        if domain in THROWAWAY_DOMAINS:
            continue
        if len(local) < 3:
            continue
        if local.isdigit():
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


def clean_name_candidate(value: str) -> str:
    value = normalize_email_text(value)
    value = re.sub(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}\b", " ", value)
    value = re.sub(r"(?:\+91)?[6-9]\d{9}", " ", value)
    value = re.sub(r"https?://\S+|www\.\S+", " ", value, flags=re.I)
    value = re.sub(
        r"\b(?:email|e-mail|mail|mobile|phone|contact|tel|telephone|linkedin|github|portfolio|address|location)\b",
        " ", value, flags=re.I,
    )
    value = re.sub(r"[^A-Za-z .'-]", " ", value)
    value = normalize_whitespace(value)
    return value.title().strip(" .'-") if value.isupper() else value.strip(" .'-")


def filename_name_candidate(filename: str) -> str:
    if not filename:
        return ""
    stem = re.sub(r"\.(pdf|docx|doc|txt)$", "", filename, flags=re.I)
    stem = re.sub(
        r"(?i)\b(resume|cv|curriculum|vitae|profile|updated|final|latest|copy|new|old)\b",
        " ", stem,
    )
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
    parts = [
        part for part in name.split()
        if part.lower() not in GENERIC_EMAIL_PREFIXES and len(part) > 1
    ]
    return " ".join(parts) if len(parts) >= 2 else ""


BAD_NAME_WORDS = {
    "resume", "curriculum", "vitae", "cv", "summary", "profile",
    "professional", "experience", "education", "skills", "projects",
    "certifications", "languages", "achievements", "objective",
    "declaration", "contact", "mobile", "phone", "email", "linkedin",
    "github", "portfolio", "address", "location", "references",
    "hobbies", "interests", "activities", "awards", "publications",
    "manager", "engineer", "developer", "analyst", "consultant",
    "executive", "specialist", "director", "lead", "intern",
    "associate", "head", "officer", "coordinator", "assistant",
    "senior", "junior", "trainee", "architect", "designer",
    "recruiter", "hr", "sales", "marketing", "finance", "operations",
    "delhi", "mumbai", "bangalore", "bengaluru", "pune", "hyderabad",
    "chennai", "kolkata", "ahmedabad", "noida", "gurugram", "gurgaon",
    "india", "maharashtra", "karnataka", "gujarat", "rajasthan",
    "telangana", "tamilnadu", "kerala", "haryana", "uttar", "pradesh",
    "chandigarh", "jaipur", "lucknow", "bhopal", "indore", "nagpur",
    "surat", "vadodara", "coimbatore", "kochi", "vizag", "visakhapatnam",
    "street", "nagar", "colony", "sector", "plot", "flat", "floor",
    "road", "avenue", "lane", "block", "phase", "near", "opposite",
    "society", "apartment", "residency", "tower", "building", "cross",
    "present", "current", "till", "since", "from", "january", "february",
    "march", "april", "june", "july", "august", "september", "october",
    "november", "december",
    "dear", "regards", "sincerely", "thank", "please", "hereby",
}


def score_name_candidate(candidate: str, position: int, email_tokens: set[str]) -> int:
    candidate = clean_name_candidate(candidate)
    if not candidate:
        return -999
    if candidate.isupper():
        candidate = candidate.title()
    words = candidate.split()
    if not (2 <= len(words) <= 4):
        return -999
    if any(char.isdigit() for char in candidate):
        return -999
    if len(candidate) > 50:
        return -999
    lower = candidate.lower()
    if any(word in BAD_NAME_WORDS for word in lower.split()):
        return -999
    if re.search(r"[A-Za-z]+,\s*[A-Za-z]+", candidate):
        return -999
    if re.search(r"[|/:\\]", candidate):
        return -999
    if all(len(word) <= 2 for word in words):
        return -999
    single_chars = sum(1 for word in words if len(word) == 1)
    if single_chars > 1:
        return -999
    score = 0
    if position == 0:
        score += 60
    elif position <= 2:
        score += 45
    elif position <= 5:
        score += 30
    elif position <= 10:
        score += 15
    elif position <= 25:
        score += 5
    else:
        score -= 20
    if len(words) == 2:
        score += 30
    elif len(words) == 3:
        score += 25
    elif len(words) == 4:
        score += 10
    if all(word[0].isupper() and word[1:].islower() for word in words if len(word) > 1):
        score += 25
    elif all(word[0].isupper() for word in words):
        score += 15
    overlaps = sum(word.lower() in email_tokens for word in words)
    score += overlaps * 35
    if overlaps >= 2:
        score += 25
    avg_len = sum(len(w) for w in words) / len(words)
    if avg_len >= 4:
        score += 10
    elif avg_len < 3:
        score -= 20
    if single_chars == 1 and overlaps == 0:
        score -= 15
    return score


def extract_name_ner(text: str) -> str:
    if NLP is None:
        return ""
    try:
        doc = NLP(text[:3000])
        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            candidate = clean_name_candidate(ent.text)
            words = candidate.split()
            if not (2 <= len(words) <= 4):
                continue
            if any(word.lower() in BAD_NAME_WORDS for word in words):
                continue
            return candidate
    except Exception:
        return ""
    return ""


def extract_name(text: str, filename: str = "") -> str:
    text = text or ""
    lines = [
        normalize_whitespace(line)
        for line in text.splitlines()
        if normalize_whitespace(line)
    ]
    email_name = extract_name_from_email(text)
    email_tokens = {token.lower() for token in email_name.split()}
    candidates = []
    patterns = [
        r"(?:name|candidate\s*name|applicant)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{3,60})",
        r"(?:i\s+am|my\s+name\s+is)\s+([A-Za-z][A-Za-z .'-]{3,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            name = match.group(1)
            candidates.append((score_name_candidate(name, 0, email_tokens) + 50, name))
    ner_name = extract_name_ner(text)
    if ner_name:
        candidates.append((score_name_candidate(ner_name, 1, email_tokens) + 40, ner_name))
    for idx, line in enumerate(lines[:25]):
        score = score_name_candidate(line, idx, email_tokens)
        if score > 0:
            candidates.append((score, line))
    for idx in range(min(len(lines) - 1, 10)):
        for combo_size in [2, 3]:
            if idx + combo_size <= len(lines):
                combined = " ".join(lines[idx : idx + combo_size])
                score = score_name_candidate(combined, idx, email_tokens)
                if score > 0:
                    candidates.append((score, combined))
    if email_name:
        candidates.append((score_name_candidate(email_name, 5, email_tokens) + 10, email_name))
    file_name = filename_name_candidate(filename)
    if file_name:
        candidates.append((score_name_candidate(file_name, 10, email_tokens), file_name))
    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_name = candidates[0]
        if best_score >= 50:
            return best_name
    return "Unknown Candidate"


# ---------------------------------------------------------------------------
# EXPERIENCE EXTRACTION (improved)
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


EMPLOYMENT_HEADERS = [
    "experience", "work experience", "professional experience", "employment history",
    "career history", "work history", "professional background",
]

SECTION_BREAK_HEADERS = [
    "education", "skills", "projects", "certifications", "languages",
    "achievements", "summary", "objective", "personal details", "declaration",
]


def extract_experience_section(text: str) -> str:
    lines = (text or "").splitlines()
    collecting = False
    collected = []
    for line in lines:
        clean = line.strip()
        lower = clean.lower()
        if any(header in lower for header in EMPLOYMENT_HEADERS):
            collecting = True
            collected.append(clean)
            continue
        if collecting and any(lower.startswith(header) for header in SECTION_BREAK_HEADERS):
            break
        if collecting:
            collected.append(clean)
    return "\n".join(collected)


def explicit_years_of_experience(text: str) -> float:
    """
    Extract explicitly stated total experience from resume text.
    Covers: "10+ years", "X years Y months", "experience: 10 years", etc.
    """
    patterns = [
        # "Total experience: 10 years" / "10 years of experience"
        r"(?:total\s+)?experience\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:total\s+)?experience",
        # "X years and Y months" / "X years Y months"
        r"(\d{1,2})\s*(?:years?|yrs?)?\s*(?:and|&|,)?\s*(\d{1,2})\s*(?:months?|mos?)\s*(?:of\s+)?experience",
        # Standalone "10+ years" / "10 years" as a summary stat
        r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b",
        # "over 10 years" / "more than 10 years"
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
    """
    Three-pass experience extraction:
    1. Explicitly stated total ("10 years of experience")
    2. Parsed from date ranges with month names (via DATE_RANGE_REGEX)
    3. Parsed from year-only ranges ("2015 – Present")
    Returns the highest credible value.
    """
    explicit = explicit_years_of_experience(text)

    section = extract_experience_section(text)
    search_text = section or text

    ranges = parse_date_ranges(search_text)
    range_years = calculate_total_experience(ranges)

    # Fallback: year-only ranges (catches "2015 - Present" patterns)
    year_only = extract_year_ranges_simple(search_text)
    if not range_years and year_only:
        range_years = year_only
    elif year_only > range_years:
        # Take the larger of the two (both are real data points)
        range_years = max(range_years, year_only)

    if explicit and range_years:
        return round(max(explicit, range_years), 1)
    return explicit or range_years


# ---------------------------------------------------------------------------
# KEYWORD EXTRACTION (major overhaul)
# ---------------------------------------------------------------------------

def extract_keywords(
    text: str,
    extra_keywords: str = "",
    limit: int = 30,
    jd_requirements: dict | None = None,
) -> list[str]:
    """
    If jd_requirements (AI-parsed) is provided, use those structured skills
    as the authoritative keyword list.
    Fallback: SKILL_ALIASES hits + filtered word frequency.
    Now includes dynamic company name cleaning on both paths.
    """
    text = text or ""
    lower = text.lower()

    configured = [kw.strip().lower() for kw in (extra_keywords or "").split(",") if kw.strip()]

    # --- AI-structured path (preferred) ---
    if jd_requirements:
        ai_keywords: list[str] = []
        for skill in jd_requirements.get("core_skills") or []:
            if isinstance(skill, str) and skill.strip():
                ai_keywords.append(skill.lower().strip())
        for tool in jd_requirements.get("tools_technologies") or []:
            if isinstance(tool, str) and tool.strip():
                ai_keywords.append(tool.lower().strip())

        combined = configured + ai_keywords
        seen: set[str] = set()
        result: list[str] = []
        for kw in combined:
            if kw and kw not in seen:
                seen.add(kw)
                result.append(kw)

        # === FIX 2: Clean AI path ===
        result = clean_keywords(result, text)
        return result[:limit]

    # --- Fallback: heuristic path ---
    combined_stop = STOP_WORDS | JD_NOISE_WORDS

    # SKILL_ALIASES hits first
    skill_hits: list[str] = []
    for canonical_skill, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias.lower())}\b", lower):
                skill_hits.append(canonical_skill)
                break

    # Filtered word frequency
    words = re.findall(r"\b[a-zA-Z][a-zA-Z+#.-]{2,}\b", lower)
    words = [w.strip(".-") for w in words if w not in combined_stop and len(w) >= 4]
    common = [word for word, _ in Counter(words).most_common(limit)]

    keywords: list[str] = []
    for item in configured + skill_hits + common:
        if item and item not in keywords and item not in combined_stop:
            keywords.append(item)

    # === FIX 2: Clean heuristic path with dynamic company blocklist ===
    keywords = clean_keywords(keywords, text)
    return keywords[:limit]

# ---------------------------------------------------------------------------
# JD PARSING HELPERS
# ---------------------------------------------------------------------------

def parse_min_experience(jd_text: str) -> float:
    """
    Extract minimum required experience from JD text.
    Handles: "10+", "10-15 years", "minimum 10 years", "at least 10",
    "over 10 years", "10 years of experience", etc.
    """
    patterns = [
        r"(\d{1,2})\s*\+\s*(?:years?|yrs?)",                                   # 10+ years
        r"(\d{1,2})\s*[-–]\s*\d{1,2}\s*(?:years?|yrs?)",                      # 10-15 years
        r"(?:minimum|min\.?)\s*(?:of\s+)?(\d{1,2})\s*(?:years?|yrs?)",        # minimum 10 years
        r"at\s+least\s*(\d{1,2})\s*(?:years?|yrs?)",                           # at least 10 years
        r"(?:over|more\s+than)\s+(\d{1,2})\s*(?:years?|yrs?)",                # over 10 years
        r"(\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+)?experience",# 10 years of experience
        r"experience\s*[:\-]\s*(\d{1,2})\s*(?:years?|yrs?)?",                 # experience: 10
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


def extract_skills(text: str) -> list[str]:
    lower = (text or "").lower()
    found = set()
    for canonical_skill, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias.lower())}\b", lower):
                found.add(canonical_skill)
                break
    return sorted(found)


def clean_role_title(value: str) -> str:
    value = normalize_whitespace(value)
    value = re.split(
        r"\b(location|experience|department|reports|reporting|salary|ctc|about|overview|responsibilities|qualification)\b",
        value, flags=re.I,
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
    title_words = {
        "manager", "engineer", "developer", "analyst", "consultant",
        "executive", "specialist", "lead", "head", "director", "officer",
        "associate", "designer",
    }
    bad = {
        "about", "company", "overview", "responsibilities", "requirements",
        "benefits", "salary", "location", "experience", "skills", "apply",
        "contact", "email",
    }
    scored = []
    for idx, line in enumerate(lines[:15]):
        clean = clean_role_title(line)
        words = clean.split()
        lower = clean.lower()
        if 2 <= len(words) <= 7 and not any(word in lower for word in bad):
            score = 50 - idx * 2 + sum(18 for word in words if word.lower().strip(".,") in title_words)
            if score > 50:
                scored.append((score, clean))
    return sorted(scored, reverse=True)[0][1] if scored else "Open Role"


def ai_extract_role_title(jd_text: str, api_key: str, model: str) -> str:
    if not api_key or not jd_text.strip():
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Extract the exact hiring role title from a job description. Return JSON only."},
                {"role": "user", "content": f'Return only JSON like {{"title":""}}. JD:\n{jd_text[:3500]}'},
            ],
            temperature=0,
            max_tokens=80,
            timeout=12,
        )
        raw = re.sub(r"```json|```", "", response.choices[0].message.content or "").strip()
        title = clean_role_title(json.loads(raw).get("title", ""))
        return title if title and title != "Open Role" else ""
    except Exception:
        return ""


def detect_role_title(jd_text: str, fallback: str, api_key: str, model: str) -> str:
    if fallback.strip():
        return clean_role_title(fallback)
    return ai_extract_role_title(jd_text, api_key, model) or extract_role_from_jd(jd_text)


def extract_keywords_from_jd(text: str, extra_keywords: str = "", limit: int = 35) -> list[str]:
    """Alias kept for backward-compat. Prefer extract_keywords() with jd_requirements."""
    return extract_keywords(text, extra_keywords, limit)


def parse_min_experience_from_requirements(jd_requirements: dict) -> float:
    """Pull min_experience_years from AI-parsed requirements dict."""
    try:
        val = float(jd_requirements.get("min_experience_years", 0) or 0)
        return val if 0 < val < 40 else 0.0
    except (ValueError, TypeError):
        return 0.0


def extract_keywords_count(text: str, extra_keywords: str = "", limit: int = 35) -> list[str]:
    """Original keyword extraction kept as fallback — not used in main pipeline."""
    text = text or ""
    lower = text.lower()
    configured = [kw.strip().lower() for kw in extra_keywords.split(",") if kw.strip()]
    skill_hits = []
    for canonical_skill, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias.lower())}\b", lower):
                skill_hits.append(canonical_skill)
                break
    words = re.findall(r"\b[a-zA-Z][a-zA-Z+#.-]{2,}\b", lower)
    words = [w.strip(".-") for w in words if w not in STOP_WORDS and len(w) >= 3]
    common = [word for word, _ in Counter(words).most_common(limit)]
    keywords = []
    for item in configured + skill_hits + common:
        if item and item not in keywords and item not in STOP_WORDS:
            keywords.append(item)
    return keywords[:limit]


def profile_key(name: str, email: str, phone: str) -> str:
    if email:
        raw = f"email:{email.lower().strip()}"
    elif phone:
        digits = re.sub(r"\D+", "", phone)
        raw = f"phone:{digits}"
    else:
        raw = f"name:{normalize_whitespace(name).lower()}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
