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
