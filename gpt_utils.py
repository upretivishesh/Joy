from openai import OpenAI
import json
import re

client = OpenAI()

# SAFE PARSER
def safe_json_parse(text):
    try:
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except:
        return {}


# NAME EXTRACTION VIA GPT (was missing — caused crash in parser.py)
def gpt_extract_name(resume_text):
    try:
        prompt = f"""Extract only the candidate's full name from this resume text.
Return only the name as plain text. No explanation, no JSON.

Resume:
{resume_text[:1500]}
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        name = res.choices[0].message.content.strip()
        if name and len(name.split()) <= 4:
            return name
        return None
    except:
        return None


# PROFILE EXTRACTION
def gpt_extract_profile(resume_text):
    try:
        prompt = f"""Extract name, email, experience in JSON.

Return:
{{"name":"","email":"","experience":0}}

Resume:
{resume_text[:2000]}
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = res.choices[0].message.content
        data = safe_json_parse(raw)
        return (
            data.get("name", "Unknown"),
            data.get("email", "-"),
            float(data.get("experience", 0))
        )
    except:
        return "Unknown", "-", 0


# GPT SCORING
def gpt_score_resume(jd_text, resume_text, persona=None):
    try:
        persona_line = f"\nPersona/focus: {persona}" if persona else ""
        prompt = f"""Score this resume against the job description.{persona_line}

Return JSON only:
{{"score":0,"verdict":"","reason":""}}

score: 0-100
verdict: one of "Strong Fit", "Good Fit", "Weak Fit", "Not Relevant"
reason: 1-2 sentences

JD:
{jd_text[:1000]}

Resume:
{resume_text[:1000]}
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = res.choices[0].message.content
        data = safe_json_parse(raw)
        return (
            float(data.get("score", 0)),
            data.get("verdict", "Weak Fit"),
            data.get("reason", "")
        )
    except:
        return 0, "Weak Fit", "GPT failed"


# EMAIL GENERATION VIA GPT
def gpt_generate_email(candidate_name, role_name, sender_name, company_name="Seven Hiring"):
    try:
        prompt = f"""Write a short, warm, professional recruiter outreach email.

Candidate: {candidate_name}
Role: {role_name}
Sender: {sender_name}
Company: {company_name}

Keep it under 120 words. Natural tone. No fluff. End with a call to action to connect.
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content
    except:
        return f"""Hi {candidate_name},

Hope you're doing well.

We came across your profile and believe you could be a great fit for a role we're currently hiring for.

Would love to connect briefly and share more details.

Best regards,
{sender_name}
{company_name}
"""


# CALL SCRIPT GENERATION
def gpt_generate_call_script(candidate_name, role_name, sender_name, company_name="Seven Hiring"):
    try:
        prompt = f"""Write a short recruiter cold-call script for an initial outreach call.

Candidate: {candidate_name}
Role: {role_name}
Caller: {sender_name}
Company: {company_name}

Format as a natural spoken script under 150 words.
Include: greeting, purpose, quick pitch, ask for interest, next step.
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content
    except:
        return f"""Hi, may I speak with {candidate_name}?

Hi {candidate_name}, I'm {sender_name} calling from {company_name}.

I came across your profile and wanted to reach out about an exciting opportunity that matches your background.

We're currently hiring for a {role_name} role and I believe you could be a strong fit.

Do you have 2-3 minutes to hear a bit more?

[If yes] Great! [Pitch the role briefly]

Would you be open to a quick call this week to explore this further?

Thank you for your time!
"""
