import html
import random
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

import pandas as pd

from .constants import DATA_DIR, DEFAULT_COMPANY


def safe_filename_part(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", value or "user")
    return clean.strip("_")[:80] or "user"


def first_name(full_name: str) -> str:
    if not full_name or full_name == "Unknown Candidate":
        return "there"
    return str(full_name).split()[0].strip(",")


def normalize_app_password(password: str) -> str:
    return re.sub(r"\s+", "", password or "")


def gmail_auth_error_message(sender_email: str, exc: smtplib.SMTPAuthenticationError) -> str:
    detail = ""
    try:
        raw = exc.smtp_error.decode("utf-8", errors="ignore")
        detail = f" Gmail said: {raw}" if raw else ""
    except Exception:
        detail = ""
    return (
        f"Gmail rejected login for {sender_email}. Use the exact Gmail/Workspace account "
        f"that created the App Password, confirm 2-Step Verification is enabled, and paste "
        f"a fresh 16-character App Password instead of your normal password.{detail}"
    )


def email_log_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"sent_emails_{safe_filename_part(user_key)}.xlsx"


def already_emailed(user_key: str, email: str, role: str) -> bool:
    path = email_log_path(user_key)
    if not path.exists() or not email:
        return False
    try:
        df = pd.read_excel(path)
        if "Email" not in df.columns or "Role" not in df.columns:
            return False
        same = df[
            (df["Email"].astype(str).str.lower().str.strip() == email.lower().strip())
            & (df["Role"].astype(str).str.lower().str.strip() == role.lower().strip())
        ]
        return not same.empty
    except Exception:
        return False


def build_email_body(
    candidate: pd.Series,
    role: str,
    sender_name: str,
    company_name: str,
    questions: list[str],
    extra_note: str,
) -> str:
    company = company_name or DEFAULT_COMPANY
    role_text = f"{role} opportunity" if role and "opportunity" not in role.lower() else role
    lines = [
        f"Hi {first_name},",
        "",
        f"I reviewed your profile for the {role_text} and it looks relevant for the first screening round.",
        "",
    ]
    if extra_note.strip():
        lines.extend([extra_note.strip(), ""])
    lines.extend(["To move ahead without a back-and-forth call, please reply with these details:", ""])
    for idx, question in enumerate(questions, start=1):
        lines.append(f"{idx}. {question}")
    lines.extend(
        [
            "",
            "Once I have this, I can confirm fit, share the next step, and avoid asking you the same basics again on call.",
            "",
            "Best regards,",
            sender_name or "Recruitment Team",
            company,
        ]
    )
    return "\n".join(lines)


def render_template_variables(text: str, candidate: pd.Series, role: str) -> str:
    variables = {
        "{first_name}": first_name(str(candidate.get("Name", ""))),
        "{full_name}": str(candidate.get("Name", "")),
        "{role}": role,
        "{email}": str(candidate.get("Email", "")),
        "{phone}": str(candidate.get("Phone", "")),
        "{experience}": str(candidate.get("Experience", "")),
        "{score}": str(candidate.get("Final Score", "")),
        "{verdict}": str(candidate.get("Verdict", "")),
    }
    rendered = text
    for key, value in variables.items():
        rendered = rendered.replace(key, value)
    return rendered


def append_email_log(sender_email: str, recipient_email: str, subject: str, role: str) -> None:
    entry = pd.DataFrame(
        [
            {
                "Email": recipient_email,
                "Subject": subject,
                "Role": role,
                "Sent At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    )
    path = email_log_path(sender_email)
    if path.exists():
        old = pd.read_excel(path)
        entry = pd.concat([old, entry], ignore_index=True)
    entry.to_excel(path, index=False)


def send_email(
    server,
    sender_email: str,
    sender_name: str,
    recipient_email: str,
    subject: str,
    body: str,
    role: str,
) -> tuple[bool, str]:
    try:
        msg = EmailMessage()
        msg["From"] = formataddr((sender_name or sender_email, sender_email))
        msg["To"] = recipient_email
        msg["Subject"] = subject

        safe_body = html.escape(body).replace("\n", "<br>")
        html_body = f"""
        <html>
        <body style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;">
        {safe_body}
        </body>
        </html>
        """
        msg.set_content(body)
        msg.add_alternative(html_body, subtype="html")

        time.sleep(random.uniform(1.0, 2.4))
        server.send_message(msg)
        append_email_log(sender_email, recipient_email, subject, role)
        return True, "Sent"
    except Exception as exc:
        return False, str(exc)


def send_bulk_emails(
    selected_df: pd.DataFrame,
    role: str,
    sender_email: str,
    sender_password: str,
    sender_name: str,
    company_name: str,
    subject: str,
    questions: list[str],
    extra_note: str,
    custom_body: str = "",
) -> list[dict]:
    results = []
    sender_email = str(sender_email or "").strip().lower()
    sender_password = normalize_app_password(sender_password)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_password)
    except smtplib.SMTPAuthenticationError as exc:
        return [{"Name": "", "Email": sender_email, "Success": False, "Message": gmail_auth_error_message(sender_email, exc)}]
    except Exception as exc:
        return [{"Name": "", "Email": "", "Success": False, "Message": str(exc)}]

    for _, candidate in selected_df.iterrows():
        name = str(candidate.get("Name", "Candidate"))
        recipient = str(candidate.get("Email", "")).strip()
        if already_emailed(sender_email, recipient, role):
            results.append({"Name": name, "Email": recipient, "Success": False, "Message": "Skipped duplicate candidate"})
            continue
        if "@" not in recipient:
            results.append({"Name": name, "Email": recipient, "Success": False, "Message": "Missing email"})
            continue

        if custom_body.strip():
            body = render_template_variables(custom_body, candidate, role)
        else:
            body = build_email_body(candidate, role, sender_name, company_name, questions, extra_note)

        personalized_subject = render_template_variables(subject, candidate, role)
        ok, message = send_email(server, sender_email, sender_name, recipient, personalized_subject, body, role)
        results.append({"Name": name, "Email": recipient, "Success": ok, "Message": message})

    server.quit()
    return results
