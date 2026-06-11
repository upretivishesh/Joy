# Joy AI Recruiter

Joy screens resumes against a JD, ranks candidates, stores screening history with the JD, detects duplicate profiles, and sends personalized candidate emails.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run playground.py
```

## Streamlit Cloud

Add this optional secret if you want AI-assisted role/scoring:

```toml
OPENAI_API_KEY = "your_key"
OPENAI_MODEL = "gpt-4o-mini"
```

Do not commit Gmail credentials. Users enter their own Gmail address and App Password in the app session.

## Structure

```text
playground.py
core/
data/
uploads/
requirements.txt
packages.txt
README.md
```
