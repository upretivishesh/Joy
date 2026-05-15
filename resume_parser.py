import re

JD_FILENAME_INDICATORS = ["jd", "job description", "job desc", "jdd", "requirement", "requirements", "role description", "hiring for", "we are hiring"]

def is_likely_jd_by_filename(filename: str) -> bool:
    fname = filename.lower()
    return any(ind in fname for ind in JD_FILENAME_INDICATORS)

def jd_likelihood_score(text: str) -> float:
    if not text or len(text) < 80:
        return 0.0
    t = text.lower()[:3000]
    jd_signals = [
        "job description", "role overview", "key responsibilities", "what you will do",
        "requirements", "qualifications", "must have", "nice to have", "responsibilities",
        "we are looking for", "about the role", "who you are", "job summary",
        "experience required", "skills required", "reporting to", "location", "salary"
    ]
    resume_signals = [
        "work experience", "professional summary", "education", "projects",
        "certifications", "skills", "achievements", "objective"
    ]
    jd_score     = sum(t.count(sig) for sig in jd_signals) * 8
    resume_score = sum(t.count(sig) for sig in resume_signals) * 10
    if re.search(r'(?:position|role|title)[:\s-]{1,3}[a-zA-Z\s]+', t):
        jd_score += 25
    if re.search(r'(?:₹|\$|lpa|ctc|salary|package)', t):
        jd_score += 15
    return max(0, min(100, jd_score - resume_score))

def extract_name(text: str, filename: str = "") -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines and re.match(r'^[A-Z][a-zA-Z\s\.\-\']{3,60}$', lines[0]):
        return lines[0]
    match = re.search(r'([A-Z][a-zA-Z\s\.\-\']{4,50})', text)
    if match:
        return match.group(1).strip()
    if filename:
        clean = re.sub(r'\.(pdf|docx|doc|txt)$', '', filename)
        clean = re.sub(r'[^a-zA-Z\s]', ' ', clean).strip()
        if len(clean.split()) >= 2:
            return clean.title()
    return "Unknown Candidate"

def extract_email(text: str) -> str:
    match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    return match.group(0) if match else ""

def extract_phone(text: str) -> str:
    for pat in [r'\+?\d{1,4}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', r'(\+91)?[-.\s]?[6-9]\d{9}']:
        match = re.search(pat, text)
        if match:
            return match.group(0)
    return ""

def extract_experience(text: str) -> int:
    for pat in [
        r'(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of)?\s*experience',
        r'experience\s*[:\-]?\s*(\d{1,2})',
        r'(\d{1,2})\s*years?',
        r'(\d+)\s*\+?\s*years?'
    ]:
        match = re.search(pat, text, re.I)
        if match:
            try: return int(match.group(1))
            except: pass
    return 0

def extract_education(text: str) -> str:
    pat = r'(B\.?Tech|B\.?E|M\.?Tech|MBA|Master|Bachelor|Ph\.?D|Diploma|CA|CPA)[\w\s]*?(?:in|of)?\s*([A-Za-z\s&]+)'
    match = re.search(pat, text, re.I)
    return match.group(0).strip() if match else "Not specified"

def extract_skills(text: str) -> str:
    skills = ["Python","JavaScript","Java","SQL","AWS","Azure","GCP","React","Django","Flask",
              "Machine Learning","Data Analysis","Excel","Power BI","Tableau","Leadership",
              "Communication","Project Management","SAP","ERP","Salesforce"]
    found = [s for s in skills if s.lower() in text.lower()]
    return ", ".join(found) if found else "None detected"

def score_resume_against_jd(resume_text: str, jd_keywords: list) -> int:
    if not jd_keywords:
        return 40
    resume_lower = resume_text.lower()
    matches = sum(1 for kw in jd_keywords if kw.lower() in resume_lower)
    return min(100, int((matches / len(jd_keywords)) * 100))

def extract_keywords_from_jd(jd_text: str) -> list:
    if not jd_text:
        return []
    stop = {"the","and","for","with","this","that","are","will","must","have","good",
            "strong","experience","skills","years","role","job","description"}
    words = re.findall(r'\b[a-zA-Z]{4,}\b', jd_text.lower())
    keywords = [w for w in words if w not in stop]
    return list(dict.fromkeys(keywords))[:25]

def get_role_from_jd(jd_text: str) -> str:
    if not jd_text:
        return "General Role"
    pat = r'(?:hiring|for|position|role|title)[:\s-]{1,3}([A-Za-z\s]+?)(?:\s+at|\s+in|\s+with|\.|$)'
    m = re.search(pat, jd_text, re.I)
    return m.group(1).strip().title() if m else "Role"

def get_industry_from_jd(jd_text: str) -> str:
    industries = ["Software","Tech","Finance","Healthcare","Marketing","Sales","Education",
                  "Manufacturing","Retail","Consulting","IT","Data","AI","ML","Chemical","Production",
                  "Agrochemical","Pharma","FMCG"]
    t = jd_text.lower()
    for ind in industries:
        if ind.lower() in t:
            return ind
    return "General"

def suggest_checks(data: dict) -> str:
    checks = []
    if data.get("Experience", 0) < 3:
        checks.append("Verify experience")
    if data.get("Keyword Score", 0) < 45:
        checks.append("Limited skill match")
    if "Not specified" in str(data.get("Education", "")):
        checks.append("Education unclear")
    return ", ".join(checks) or "Strong profile"
