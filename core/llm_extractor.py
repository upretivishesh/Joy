import json
from openai import OpenAI


def extract_keywords_llm(
    jd_text: str, 
    api_key: str, 
    model: str = "gpt-4o-mini",
    max_keywords: int = 25
) -> list[str]:
    """
    High-quality LLM-based keyword extraction from Job Description.
    Returns clean list of technical skills/tools.
    """
    if not api_key or not jd_text or not jd_text.strip():
        return []

    try:
        client = OpenAI(api_key=api_key)

        prompt = f"""You are an expert technical recruiter.

Extract ONLY the most important **hard technical skills, tools, technologies, and domain-specific keywords** from this job description.

Rules:
- Return ONLY a clean JSON array of strings.
- Focus on must-have technical skills (ignore soft skills like communication, leadership, teamwork).
- Be specific (e.g. "React.js", "SAP MM", "Python", "Power BI", "Agrochem formulation").
- Do NOT include company names, locations, addresses, or generic words.
- Limit to the top {max_keywords} most relevant items.

Output format example:
["Python", "React", "Power BI", "SAP MM"]

Job Description:
{jd_text[:4500]}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a precise technical recruiter. Extract only hard skills and tools. Return valid JSON array only."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=500,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        keywords = json.loads(raw)

        if isinstance(keywords, list):
            cleaned = []
            for k in keywords:
                if isinstance(k, str):
                    k = k.strip().lower()
                    if len(k) > 2:
                        cleaned.append(k)
            return cleaned[:max_keywords]

        return []

    except Exception as e:
        print(f"[LLM Extractor Error] {e}")
        return []


def extract_candidate_name_llm(
    resume_text: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    contact_email: str = "",
) -> str:
    """
    LLM-based candidate name extraction.

    Regex/heuristic name extraction breaks constantly on real resumes:
    section headers ("Personal Details", "Bio Data"), other people
    mentioned in the doc (references, managers, "Father's Name"), place
    names that happen to look like a name, table headers pulled in by
    OCR, filename fallbacks, etc. An LLM reading the whole document in
    context handles all of these at once instead of chasing edge cases
    one blocklist word at a time.

    Returns "" (never a guess) if the model isn't confident — the caller
    is expected to fall back to the heuristic extractor in that case.
    """
    if not api_key or not resume_text or not resume_text.strip():
        return ""

    try:
        client = OpenAI(api_key=api_key)

        email_hint = (
            f'\nThe candidate\'s contact email on this resume is: {contact_email}\n'
            if contact_email else ""
        )

        prompt = f"""You are reviewing a resume/CV to identify whose document this is.

Return ONLY valid JSON: {{"name": "Full Name"}} or {{"name": ""}} if you cannot
confidently identify the candidate's own name.

Rules:
- This must be the name of the person this resume BELONGS TO — the job
  applicant/candidate themselves.
- Do NOT return a section heading like "Personal Details", "Bio Data",
  "Curriculum Vitae", "Career Objective" etc. Those are not names.
- Do NOT return the name of anyone else mentioned in the document —
  not a father's/mother's/spouse's name, not a reference, not a
  reporting manager, not a previous employer's name.
- Do NOT return a place, city, or company name.
- Do NOT return a filename or file extension like "12345.pdf".
- If several names appear, prefer the one that matches the contact
  email below, and the one presented as the resume owner (usually at
  the very top, near the contact details).
- If you are not reasonably confident, return {{"name": ""}} rather than guessing.
{email_hint}
Resume text:
{resume_text[:4000]}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract the resume owner's own name only. "
                        "Never a heading, relative, reference, or company. "
                        "Return valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=60,
            timeout=15,
        )

        raw = (response.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        name = str(data.get("name", "")).strip()
        if not name:
            return ""

        words = name.split()
        if not (2 <= len(words) <= 5):
            return ""
        if any(char.isdigit() for char in name):
            return ""

        return name

    except Exception as e:
        print(f"[LLM Name Extractor Error] {e}")
        return ""
