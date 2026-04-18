from openai import OpenAI

client = OpenAI()

JD_SYSTEM = """You are Joy, a world-class recruitment consultant at Seven Hiring with deep expertise across industries including Agrochemicals, Pharma, Technology, Sales, Finance, and FMCG.

When asked to write a Job Description, produce a clean, professional, compelling JD that:
- Is specific, not generic
- Avoids buzzword soup ("rockstar", "ninja", "passionate self-starter")
- Is honest about what the role actually involves
- Attracts the right people and naturally filters out the wrong ones
- Has a tone that's professional but human

Structure every JD as:
1. Role Overview (2-3 lines, punchy)
2. Key Responsibilities (5-8 bullet points)
3. Required Qualifications (must-haves)
4. Preferred Qualifications (nice-to-haves)
5. What We Offer (compensation, growth, culture — honest)
6. About the Company (2-3 lines max)

Do not include placeholder text like "[Company Name]". Use "Seven Hiring" or leave it as the client company context if provided.
"""


def generate_jd(
    role: str,
    industry: str = "",
    location: str = "India",
    experience_range: str = "3-8 years",
    key_skills: str = "",
    extra_context: str = "",
    company_name: str = "Our client"
) -> str:
    """
    Generate a complete job description using GPT.
    Returns the full JD as a string.
    """
    try:
        prompt_parts = [f"Write a detailed Job Description for the role of: {role}"]

        if industry:
            prompt_parts.append(f"Industry: {industry}")
        if location:
            prompt_parts.append(f"Location: {location}")
        if experience_range:
            prompt_parts.append(f"Experience required: {experience_range}")
        if key_skills:
            prompt_parts.append(f"Key skills/keywords to include: {key_skills}")
        if company_name:
            prompt_parts.append(f"Hiring company context: {company_name}")
        if extra_context:
            prompt_parts.append(f"Additional context: {extra_context}")

        prompt = "\n".join(prompt_parts)

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JD_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.75
        )

        return res.choices[0].message.content.strip()

    except Exception as e:
        return f"Joy couldn't write the JD right now. Error: {str(e)}"


def refine_jd(existing_jd: str, feedback: str) -> str:
    """
    Refine an existing JD based on recruiter feedback.
    """
    try:
        prompt = f"""Here is a job description:

{existing_jd}

The recruiter wants the following changes:
{feedback}

Rewrite the full JD incorporating this feedback. Keep the structure clean."""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JD_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )

        return res.choices[0].message.content.strip()

    except Exception as e:
        return f"Refinement failed: {str(e)}"


def extract_jd_keywords(jd_text: str) -> list[str]:
    """
    Pull key screening keywords from a JD for use in resume scoring.
    """
    try:
        prompt = f"""Extract the top 15 most important technical/skill keywords from this job description.
Return ONLY a JSON array of strings. No explanation.

JD:
{jd_text[:2000]}"""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )

        import json, re
        raw = re.sub(r"```json|```", "", res.choices[0].message.content).strip()
        return json.loads(raw)

    except:
        return []
