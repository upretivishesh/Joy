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
    text = re.sub(r"(?<=\w)\s*\.\s*(?=\w)", ".", text)
    return text


def extract_email(text: str) -> str:
    normalized = normalize_email_text(text)
    pattern = r"\b[A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@[A-Za-z0-9][A-Za-z0-9.\-]{1,250}\.[A-Za-z]{2,24}\b"
    candidates = []
    for match in re.finditer(pattern, normalized):
        email = match.group(0).strip(".,;:()[]{}<>").lower()
        local, domain = email.split("@", 1)
        if ".." in email or domain.startswith(".") or domain.endswith("."):
            continue
        if local in GENERIC_EMAIL_PREFIXES:
            penalty = 20
        else:
            penalty = 0
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
    value = re.sub(r"\b(?:email|e-mail|mail|mobile|phone|contact|tel|telephone|linkedin|github|portfolio|address|location)\b", " ", value, flags=re.I)
    value = re.sub(r"[^A-Za-z .'-]", " ", value)
    value = normalize_whitespace(value)
    return value.title().strip(" .'-") if value.isupper() else value.strip(" .'-")


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
    parts = [
        part for part in name.split()
        if part.lower() not in GENERIC_EMAIL_PREFIXES and len(part) > 1
    ]
    return " ".join(parts) if len(parts) >= 2 else ""


def name_score(clean: str, line_index: int, email_tokens: set[str]) -> int:
    lower = clean.lower()
    words = clean.split()
    if not 2 <= len(words) <= 5:
        return -100
    if any(char.isdigit() for char in clean):
        return -100
    if any(token in lower for token in NAME_STOPWORDS):
        return -100
    if len(clean) > 58:
        return -100
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", word) for word in words):
        return -100

    score = 95 - line_index * 3
    if len(words) in (2, 3):
        score += 24
    if all(word[:1].isupper() for word in words):
        score += 14
    if email_tokens:
        overlaps = sum(1 for word in words if word.lower() in email_tokens)
        score += overlaps * 24
        if overlaps >= 2:
            score += 20
    if line_index <= 3:
        score += 20
    if any(len(word) == 1 for word in words):
        score -= 18
    return score

def score_name_candidate(
    candidate: str,
    position: int,
    email_tokens: set[str],
) -> int:

    candidate = clean_name_candidate(candidate)

    if not candidate:
        return -999

    words = candidate.split()

    if not (2 <= len(words) <= 4):
        return -999

    if any(char.isdigit() for char in candidate):
        return -999

    lower = candidate.lower()

    score = 0

    # resumes usually start with the name
    score += max(0, 50 - position * 4)

    # ideal length
    if len(words) in (2, 3):
        score += 25

    # capitalization
    if all(word[0].isupper() for word in words):
        score += 20

    # email overlap
    overlaps = sum(
        word.lower() in email_tokens
        for word in words
    )

    score += overlaps * 25

    # blacklist
    if any(
        word in BAD_NAME_WORDS
        for word in lower.split()
    ):
        score -= 100

    # initials penalty
    if any(
        len(word) == 1
        for word in words
    ):
        score -= 10

    return score

def extract_name_ner(text: str) -> str:

    if NLP is None:
        return ""

    try:

        doc = NLP(text[:3000])

        for ent in doc.ents:

            if ent.label_ != "PERSON":
                continue

            candidate = clean_name_candidate(
                ent.text
            )

            words = candidate.split()

            if not (2 <= len(words) <= 4):
                continue

            if any(
                word.lower() in BAD_NAME_WORDS
                for word in words
            ):
                continue

            return candidate

    except Exception:
        return ""

    return ""

def extract_name(
    text: str,
    filename: str = "",
) -> str:

    text = text or ""

    lines = [
        normalize_whitespace(line)
        for line in text.splitlines()
        if normalize_whitespace(line)
    ]

    email_name = extract_name_from_email(text)

    email_tokens = {
        token.lower()
        for token in email_name.split()
    }

    candidates = []

    # explicit labels
    patterns = [
        r"(?:name|candidate\s*name|applicant)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{3,60})",
        r"(?:i\s+am|my\s+name\s+is)\s+([A-Za-z][A-Za-z .'-]{3,60})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if match:

            name = match.group(1)

            candidates.append(
                (
                    score_name_candidate(
                        name,
                        0,
                        email_tokens,
                    ) + 50,
                    name,
                )
            )

    # SpaCy
    ner_name = extract_name_ner(text)

    if ner_name:

        candidates.append(
            (
                score_name_candidate(
                    ner_name,
                    1,
                    email_tokens,
                ) + 40,
                ner_name,
            )
        )

    # top resume section
    for idx, line in enumerate(lines[:25]):

        score = score_name_candidate(
            line,
            idx,
            email_tokens,
        )

        if score > 0:

            candidates.append(
                (
                    score,
                    line,
                )
            )

    # email fallback
    if email_name:

        candidates.append(
            (
                score_name_candidate(
                    email_name,
                    5,
                    email_tokens,
                ) + 10,
                email_name,
            )
        )

    # filename fallback
    file_name = filename_name_candidate(
        filename
    )

    if file_name:

        candidates.append(
            (
                score_name_candidate(
                    file_name,
                    10,
                    email_tokens,
                ),
                file_name,
            )
        )

    if candidates:

        candidates.sort(
            reverse=True,
            key=lambda x: x[0],
        )

        best_score, best_name = candidates[0]

        if best_score >= 50:

            return best_name

    return "Unknown Candidate"

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
    merged = []
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

BAD_NAME_WORDS = {
    "delhi", "mumbai", "bangalore", "bengaluru", "pune", "hyderabad",
"chennai", "kolkata", "ahmedabad", "noida", "gurugram", "gurgaon",
"india", "maharashtra", "karnataka", "gujarat", "rajasthan",
"street", "nagar", "colony", "sector", "plot", "flat", "floor",
"road", "avenue", "lane", "block", "phase", "near", "opposite",
    "resume",
    "curriculum",
    "vitae",
    "cv",
    "summary",
    "profile",
    "professional",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "languages",
    "achievements",
    "objective",
    "declaration",
    "contact",
    "mobile",
    "phone",
    "email",
    "linkedin",
    "github",
    "portfolio",
    "address",
    "location",
    "india",
    "manager",
    "engineer",
    "developer",
    "analyst",
    "consultant",
    "executive",
    "specialist",
    "director",
    "lead",
    "intern",
    "associate",
    "head",
}

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
    patterns = [
        r"(?:total\s+)?experience\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:total\s+)?experience",
        r"experience\s*[:\-]?\s*(\d{1,2})\s*(?:years?|yrs?)?\s*(?:and|,)?\s*(\d{1,2})\s*(?:months?|mos?)",
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
            except Exception:
                pass
    return round(best, 1)


def extract_experience(text: str) -> float:
    explicit = explicit_years_of_experience(text)
    section = extract_experience_section(text)
    ranges = parse_date_ranges(section or text)
    range_years = calculate_total_experience(ranges)
    if explicit and range_years:
        return round(max(explicit, range_years), 1)
    return explicit or range_years


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
    title_words = {"manager", "engineer", "developer", "analyst", "consultant", "executive", "specialist", "lead", "head", "director", "officer", "associate", "designer"}
    bad = {"about", "company", "overview", "responsibilities", "requirements", "benefits", "salary", "location", "experience", "skills", "apply", "contact", "email"}
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
                {"role": "user", "content": f"Return only JSON like {{\"title\":\"\"}}. JD:\n{jd_text[:3500]}"},
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


def parse_min_experience(jd_text: str) -> float:
    patterns = [
        r"(\d{1,2})\s*[-+]\s*\d{0,2}\s*(?:years?|yrs?)",
        r"minimum\s*(?:of)?\s*(\d{1,2})\s*(?:years?|yrs?)",
        r"at least\s*(\d{1,2})\s*(?:years?|yrs?)",
        r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of)?\s*experience",
    ]
    for pattern in patterns:
        match = re.search(pattern, jd_text or "", flags=re.I)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return 0.0
    return 0.0


def extract_keywords(text: str, extra_keywords: str = "", limit: int = 35) -> list[str]:
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
