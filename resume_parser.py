# resume_parser.py - Upgraded Smart Version for Joy AI Recruiter
import re

def extract_name(text: str) -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines and re.match(r'^[A-Z][a-zA-Z\s\.-]{3,50}$', lines[0]):
        return lines[0]
    match = re.search(r'([A-Z][a-zA-Z\s\.-]{4,40})(?:\n|$)', text)
    return match.group(1).strip() if match else "Unknown Candidate"

def extract_email(text: str) -> str:
    match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    return match.group(0) if match else ""

def extract_phone(text: str) -> str:
    patterns = [r'\+?\d{1,4}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', r'(\+91)?[-.\s]?[6-9]\d{9}']
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            return match.group(0)
    return ""

def extract_experience(text: str) -> int:
    patterns = [
        r'(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of)?\s*experience',
        r'experience\s*[:\-]?\s*(\d{1,2})',
        r'(\d{1,2})\s*years?',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.I)
        if match:
            try:
                return int(match.group(1))
            except:
                pass
    return 0

def extract_education(text: str) -> str:
    patterns = r'(B\.?Tech|B\.?E|M\.?Tech|MBA|Master|Bachelor|Ph\.?D|Diploma|CA|CPA)[\w\s]*?(?:in|of)?\s*([A-Za-z\s&]+)'
    match = re.search(patterns, text, re.I)
    return match.group(0).strip() if match else "Not specified"

def extract_skills(text: str) -> str:
    common_skills = ["Python", "JavaScript", "Java", "SQL", "AWS", "Azure", "GCP", "React", "Django", "Flask", "Machine Learning", "Data Analysis", "Excel", "Power BI", "Tableau", "Leadership", "Communication", "Project Management"]
    found = [skill for skill in common_skills if skill.lower() in text.lower()]
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
    stop_words = {"the", "and", "for", "with", "this", "that", "are", "will", "must", "have", "good", "strong", "experience", "skills", "years", "role", "job"}
    words = re.findall(r'\b[a-zA-Z]{4,}\b', jd_text.lower())
    keywords = [w for w in words if w not in stop_words]
    return list(dict.fromkeys(keywords))[:20]

def is_likely_jd(text: str) -> bool:
    if not text or len(text) < 100:
        return False
    text_l = text.lower()[:2500]
    jd_indicators = ["job description", "responsibilities", "requirements", "qualifications", "we are looking for", "role overview", "key responsibilities", "must have", "nice to have", "about the role", "who you are", "what you will do"]
    resume_indicators = ["professional summary", "work experience", "education", "projects", "certifications"]
    jd_score = sum(text_l.count(ind) for ind in jd_indicators)
    resume_score = sum(text_l.count(ind) for ind in resume_indicators)
    return jd_score >= 2 and jd_score > resume_score * 0.6

def get_role_from_jd(jd_text: str) -> str:
    if not jd_text:
        return "General Role"
    patterns = [r'(?:hiring|recruiting|for|position|role|title)\s*[:\-]?\s*([A-Za-z\s]+?)(?:\s+at|\s+in|\s+with|\.|$)', r'([A-Za-z\s]+?)\s*(?:Engineer|Developer|Manager|Analyst|Consultant|Specialist|Lead)']
    for pat in patterns:
        match = re.search(pat, jd_text, re.I)
        if match:
            return match.group(1).strip().title()
    return "Role"

def get_industry_from_jd(jd_text: str) -> str:
    industries = ["Software", "Tech", "Finance", "Healthcare", "Marketing", "Sales", "Education", "Manufacturing", "Retail", "Consulting", "IT", "Data", "AI", "ML"]
    text_l = jd_text.lower()
    for ind in industries:
        if ind.lower() in text_l:
            return ind
    return "General"

def suggest_checks(data: dict) -> str:
    checks = []
    if data.get("Experience", 0) < 2:
        checks.append("Verify experience claims")
    if data.get("Keyword Score", 0) < 50:
        checks.append("Limited skill match")
    if "Not specified" in str(data.get("Education", "")):
        checks.append("Education unclear")
    return ", ".join(checks) or "Strong profile"
