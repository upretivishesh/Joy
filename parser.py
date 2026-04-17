import re


# ---------------- NAME EXTRACTION (rule-based) ----------------
def extract_name_rule(text):
    lines = text.split("\n")

    blacklist = [
        "resume", "cv", "profile", "summary", "objective",
        "location", "india", "board", "university", "college",
        "school", "experience", "email", "phone", "contact",
        "address", "linkedin", "github", "declaration"
    ]

    for line in lines[:15]:
        line = line.strip()

        if (
            len(line) < 3 or
            any(x in line.lower() for x in blacklist) or
            "@" in line or
            any(char.isdigit() for char in line) or
            "," in line or
            len(line) > 50
        ):
            continue

        words = line.split()

        if 2 <= len(words) <= 4:
            if all(w[0].isupper() for w in words if w.isalpha()):
                return line.title()

    return None


# ---------------- NAME EXTRACTION (with GPT fallback) ----------------
def extract_name(text):
    name = extract_name_rule(text)
    if name:
        return name

    try:
        from gpt_utils import gpt_extract_name  # safe import
        gpt_name = gpt_extract_name(text)

        if gpt_name:
            gpt_name = gpt_name.strip()
            bad_words = ["location", "india", "resume", "cv", "profile"]
            if any(x in gpt_name.lower() for x in bad_words):
                return "Unknown"
            if len(gpt_name.split()) <= 4:
                return gpt_name
    except Exception:
        pass

    return "Unknown"


# ---------------- EMAIL ----------------
def extract_email(text):
    matches = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return matches[0] if matches else "-"


# ---------------- PHONE ----------------
def extract_phone(text):
    matches = re.findall(r"(\+91[\s\-]?)?[6-9]\d{9}", text)
    return matches[0] if matches else "-"


# ---------------- EXPERIENCE ----------------
def extract_experience(text):
    text_lower = text.lower()

    patterns = [
        r"(\d+\.?\d*)\+?\s*years?\s*of\s*(work|professional|total)?\s*experience",
        r"(\d+\.?\d*)\+?\s*yrs",
        r"experience\s*[:\-]?\s*(\d+\.?\d*)\s*years?",
        r"(\d+\.?\d*)\+?\s*years?",
    ]

    values = []
    for pattern in patterns:
        for m in re.findall(pattern, text_lower):
            try:
                val = float(m[0] if isinstance(m, tuple) else m)
                if 0 < val < 40:  # sanity check
                    values.append(val)
            except:
                continue

    return max(values) if values else 0


# ---------------- KEYWORD SCORING ----------------
def score_resume_against_jd(resume_text, extra_keywords):
    text = resume_text.lower()

    jd_words = re.findall(r"\b[a-z]{4,}\b", text)
    jd_keywords = list(set(jd_words))[:30]

    keywords = jd_keywords + [k.lower() for k in extra_keywords]

    if not keywords:
        return 0

    matches = sum(1 for k in keywords if k in text)
    return round((matches / len(keywords)) * 100, 2)


# ---------------- ROLE DETECTION ----------------
def get_role_from_jd(jd_text):
    jd = jd_text.lower()
    roles = {
        "graphic designer": ["graphic designer", "visual designer"],
        "software engineer": ["software engineer", "developer", "sde"],
        "data analyst": ["data analyst", "business analyst"],
        "sales executive": ["sales executive", "sales rep", "bdm", "business development"],
        "hr executive": ["hr executive", "human resources"],
        "marketing manager": ["marketing manager", "digital marketing"],
        "qc manager": ["quality control", "qc manager", "quality assurance", "qa manager"],
        "r&d manager": ["r&d", "research and development"],
        "regional sales manager": ["regional sales manager", "rsm", "area sales manager"],
    }
    for label, keywords in roles.items():
        if any(k in jd for k in keywords):
            return label.title()
    return "General Role"


# ---------------- INDUSTRY DETECTION ----------------
def get_industry_from_jd(jd_text):
    jd = jd_text.lower()
    if any(x in jd for x in ["agrochemical", "pesticide", "herbicide", "insecticide", "crop protection"]):
        return "Agrochemicals"
    if any(x in jd for x in ["pharma", "pharmaceutical", "drug", "biotech"]):
        return "Pharma"
    if any(x in jd for x in ["design", "ui", "ux", "graphic"]):
        return "Design"
    if any(x in jd for x in ["software", "developer", "tech", "it", "saas"]):
        return "Technology"
    if any(x in jd for x in ["sales", "business development"]):
        return "Sales"
    if any(x in jd for x in ["finance", "accounting", "ca", "cfa"]):
        return "Finance"
    if any(x in jd for x in ["marketing", "seo", "social media"]):
        return "Marketing"
    return "General"


# ---------------- SUGGESTIONS ----------------
def suggest_checks(row):
    suggestions = []
    if row.get("Experience", 0) < 2:
        suggestions.append("Low experience")
    if row.get("Keyword Score", 0) < 20:
        suggestions.append("Weak keyword match")
    if row.get("Verdict", "") in ["Weak Fit", "Not Relevant"]:
        suggestions.append("Low GPT match")
    return ", ".join(suggestions) if suggestions else "Looks good"
