# Joy AI Recruiter

Joy is an AI-powered resume screening tool that ranks candidates against a Job Description (JD), learns from past hiring decisions, detects duplicate profiles, and can send personalized outreach emails.

It combines rule-based extraction, semantic similarity, keyword matching, and optional LLM scoring to produce fair, explainable rankings while remaining usable even without an API key.

## Key Features

- **Smart name extraction** – robust heuristic + optional LLM fallback that handles Indian-style resumes, ALL-CAPS names, titles, and noisy headers.
- **Balanced scoring** – experience, education, keywords, semantic similarity and industry fit with softened penalties so good (but not perfect) candidates are not over-penalized.
- **Learning from history** – remembers previous feedback (Hired / Shortlisted / Interviewed / Rejected) and adjusts future scores; also learns preferred industries and successful keyword patterns per client.
- **Batch semantic scoring** – embeds the whole resume batch + JD in 1–2 API calls instead of one call per resume (faster + cheaper).
- **Industry fit detection** – rule-based + LLM judgment of whether the candidate’s background matches the JD / client industry.
- **Duplicate profile detection** via stable Profile Key (name + email + phone).
- **Screening history** stored with the original JD for later review and learning.
- **Personalized candidate emails** (users supply their own Gmail + App Password).
- Works fully offline / without OpenAI key (falls back to heuristics).

## Run Locally

# Ubuntu / Debian
sudo apt-get install -y tesseract-ocr poppler-utils

OPENAI_API_KEY = "your_key"
OPENAI_MODEL = "gpt-4o-mini"   # or any compatible model

Do not commit Gmail credentials.
Users enter their own Gmail address and App Password inside the app session when they want to send emails.


playground.py                  # Main Streamlit UI
core/
├── ocr.py                     # PDF / image text extraction
├── parser.py                  # JD & resume field extraction
├── name_extractor.py          # Improved name extraction (heuristic + NER)
├── scoring.py                 # Balanced multi-signal scoring + verdicts
├── llm_extractor.py           # LLM keyword & name helpers
├── semantic.py                # Batch + single semantic similarity
├── history.py                 # Screening history load / save
├── india_industry_map.py      # Rule-based industry detection
└── ai_client.py               # Thin OpenAI / chat_json wrapper
data/                          # Screening history & learned profiles
uploads/                       # Temporary uploaded resumes
requirements.txt
packages.txt                   # System packages for Streamlit Cloud
README.md



Typical Workflow

Paste or upload a Job Description.
(Optional) set role title, min/max experience, preferred industries, extra keywords.
Upload one or many resumes (PDF / DOCX / images).
Click Screen.
Review ranked table, industry fit, matched/missing keywords, and reasons.
Mark feedback (Shortlisted / Interviewed / Hired / Rejected …) – this improves future runs.
Export results or send personalized emails.

Notes

Name extraction prefers the LLM when an API key is present; otherwise uses the improved heuristic (position, email overlap, noise rejection, Indian name patterns).
All LLM calls are temperature-0 and JSON-only for reliability.
History is stored per user key so multiple recruiters can keep separate learning profiles.
The tool never stores Gmail credentials.

