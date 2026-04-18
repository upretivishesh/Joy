from openai import OpenAI
import json
import re

client = OpenAI()

JOY_SYSTEM_PROMPT = """You are Joy — an AI recruitment assistant built for Seven Hiring. You are Jarvis-level sharp: witty, warm, intellectually curious, and devastatingly useful. You are not a chatbot. You are a colleague who happens to know everything about hiring.

Your personality:
- Confident but never arrogant
- Funny when appropriate — dry wit, not dad jokes
- You refer to yourself as Joy, never "I am an AI" or "as an assistant"
- You address the user by first name if you know it
- You are decisive: when asked for a recommendation, you give one
- You are honest: if something doesn't make sense, you say so with class

Your capabilities (what you can do for the recruiter):
1. Screen resumes against a JD — rank and score candidates
2. Send emails to shortlisted candidates
3. Make or initiate calls to candidates via Twilio
4. Write job descriptions from scratch
5. Answer questions about candidates, hiring, roles, industry
6. Remember context from the current session

When the user gives a voice command or text command, respond with a JSON object that tells the Streamlit app what to do:

{
  "intent": "screen" | "email" | "call" | "write_jd" | "chat" | "greeting",
  "reply": "<what Joy says out loud — conversational, witty, max 2 sentences>",
  "action_data": {}  // optional structured data for the action
}

For "chat" intent, just reply naturally. No action needed.
For "greeting", welcome the user warmly and tell them what you can do — but keep it punchy, not a wall of text.
For "screen", action_data can include: {"ready": true} to trigger the screen flow
For "email", action_data: {"candidate": "<name if mentioned>"}
For "call", action_data: {"candidate": "<name if mentioned>", "mode": "manual"|"auto"}
For "write_jd", action_data: {"role": "<role name>", "details": "<any extra context>"}

Respond ONLY with valid JSON. No markdown, no explanation outside the JSON.
"""

GREETINGS = [
    "I'm Joy. Think of me as your unfairly capable hiring co-pilot. I can screen resumes, write JDs, send emails, and call candidates — ideally all before your morning chai goes cold.",
    "Joy here. I've been waiting. Let's find you some brilliant people — or at least eliminate the obviously terrible ones.",
    "Good to have you. I'm Joy — part recruiter, part AI, entirely too good at my job. What are we hiring for?",
    "Joy at your service. I screen resumes faster than you can say 'cultural fit', write JDs that actually make sense, and I never ghost candidates. Unlike some recruiters. What do you need?"
]

import random

def get_greeting(user_name: str) -> dict:
    first = user_name.split()[0] if user_name else "there"
    base = random.choice(GREETINGS)
    return {
        "intent": "greeting",
        "reply": f"Hey {first}. {base}",
        "action_data": {}
    }


def route_intent(user_message: str, user_name: str = "", context: str = "") -> dict:
    """
    Takes a user voice/text command and returns an intent + reply + optional action data.
    """
    try:
        context_line = f"\nCurrent session context: {context}" if context else ""
        user_line = f"\nUser's name: {user_name}" if user_name else ""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JOY_SYSTEM_PROMPT + user_line + context_line},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0.8
        )

        raw = res.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)
        return data

    except Exception as e:
        return {
            "intent": "chat",
            "reply": "I heard you, but something went sideways on my end. Try again — I'm listening.",
            "action_data": {}
        }


def joy_chat(message: str, history: list, user_name: str = "") -> str:
    """
    General multi-turn conversation with Joy. Returns just the text reply.
    Used for follow-up questions, candidate analysis, advice, etc.
    """
    try:
        first = user_name.split()[0] if user_name else ""
        messages = [{"role": "system", "content": JOY_SYSTEM_PROMPT + (f"\nUser's name: {first}" if first else "")}]

        for turn in history[-6:]:
            messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({"role": "user", "content": message})

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=400,
            temperature=0.85
        )

        return res.choices[0].message.content.strip()

    except:
        return "My brain glitched for a second. Try me again."


def joy_analyze_candidate(candidate_row: dict, user_name: str = "") -> str:
    """
    Joy gives a sharp one-paragraph take on a specific candidate.
    """
    try:
        prompt = f"""Give a sharp, honest 2-sentence recruiter take on this candidate. Be direct. Be useful. A little wit is fine.

Candidate data:
Name: {candidate_row.get('Name', 'Unknown')}
Experience: {candidate_row.get('Experience', 0)} years
GPT Score: {candidate_row.get('GPT Score', 0)}/100
Final Score: {candidate_row.get('Final Score', 0)}
Verdict: {candidate_row.get('Verdict', '')}
Reason: {candidate_row.get('Reason', '')}
Suggestions: {candidate_row.get('Suggestions', '')}
"""
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are Joy, a sharp AI recruiter. Respond in plain text, 2 sentences max."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=120,
            temperature=0.8
        )
        return res.choices[0].message.content.strip()
    except:
        return "Couldn't analyse this one right now. The data's all there though — have a look."
