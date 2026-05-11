import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


SCREENING_QUESTIONS = [
    "What is your current CTC? (in Lakhs per annum)",
    "What is your expected CTC? (in Lakhs per annum)",
    "What is your notice period?",
    "How many years of total work experience do you have?",
    "How many years of relevant experience do you have for this role?",
    "What is your current location?",
    "Are you open to relocating? If yes, which cities?",
    "What is your reason for looking for a change?",
]


def build_screening_email_html(candidate_name, role, sender_name, company="Seven Hiring", extra_note=""):
    if not candidate_name or str(candidate_name).lower() in ["unknown", "-", "nan"]:
        candidate_name = "there"

    questions_html = ""
    for i, q in enumerate(SCREENING_QUESTIONS):
        bg = "#FAFAFA" if i % 2 == 0 else "#FFFFFF"
        questions_html += f"""
        <tr style="background:{bg};">
            <td style="padding:12px 16px;font-size:13px;color:#333;border-bottom:1px solid #EEEEEE;">
                <strong>{i+1}.</strong> {q}
            </td>
        </tr>"""

    extra_block = f'<p style="margin:0 0 16px;font-size:14px;color:#555;line-height:1.7;">{extra_note}</p>' if extra_note else ""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F5F5F5;font-family:Helvetica Neue,Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F5F5F5;padding:40px 20px;">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,0.08);">

  <tr><td style="background:#111;padding:26px 36px;">
    <p style="margin:0;color:#fff;font-size:18px;font-weight:600;">Seven Hiring</p>
    <p style="margin:3px 0 0;color:#666;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;">Recruitment Partner</p>
  </td></tr>

  <tr><td style="padding:32px 36px 20px;">
    <p style="margin:0 0 16px;font-size:15px;color:#111;font-weight:500;">Hi {candidate_name},</p>
    <p style="margin:0 0 14px;font-size:14px;color:#444;line-height:1.75;">
      Hope you're doing well. We came across your profile and believe you could be a strong fit
      for a <strong>{role}</strong> opportunity we're currently working on with one of our clients.
    </p>
    {extra_block}
    <p style="margin:0 0 20px;font-size:14px;color:#444;line-height:1.75;">
      To understand your profile and check alignment, please <strong>reply to this email</strong>
      with answers to the questions below:
    </p>
  </td></tr>

  <tr><td style="padding:0 36px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #EEEEEE;border-radius:6px;overflow:hidden;">
      {questions_html}
    </table>
  </td></tr>

  <tr><td style="padding:24px 36px 32px;">
    <p style="margin:0 0 14px;font-size:14px;color:#444;line-height:1.75;">
      We'll review your responses and get back to you within <strong>2 business days</strong>.
    </p>
    <p style="margin:0 0 4px;font-size:14px;color:#111;font-weight:600;">{sender_name}</p>
    <p style="margin:0;font-size:12px;color:#999;">{company}</p>
  </td></tr>

  <tr><td style="padding:16px 36px 24px;border-top:1px solid #F0F0F0;">
    <p style="margin:0;font-size:11px;color:#BBB;line-height:1.6;">
      This message was sent by {company}. If this is not relevant to you, you may ignore this email.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def build_screening_email_plain(candidate_name, role, sender_name, company="Seven Hiring", extra_note=""):
    if not candidate_name or str(candidate_name).lower() in ["unknown", "-", "nan"]:
        candidate_name = "there"
    qs = "\n".join(f"{i+1}. {q}" for i, q in enumerate(SCREENING_QUESTIONS))
    note = f"\n{extra_note}\n" if extra_note else ""
    return f"""Hi {candidate_name},

Hope you're doing well. We came across your profile and believe you could be a strong fit for a {role} opportunity.
{note}
Please reply to this email with answers to the following:

{qs}

We'll review your responses and get back to you within 2 business days.

{sender_name}
{company}"""


def send_screening_email(
    sender_email, sender_password,
    recipient_email, candidate_name,
    role, sender_name,
    company="Seven Hiring", extra_note="",
    smtp_host="smtp.gmail.com", smtp_port=587
):
    if not recipient_email or "@" not in str(recipient_email):
        return False, f"Invalid email: {recipient_email}"
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]     = f"{sender_name} <{sender_email}>"
        msg["To"]       = recipient_email
        msg["Subject"]  = f"Opportunity | {role} — Seven Hiring"
        msg["Reply-To"] = sender_email

        msg.attach(MIMEText(build_screening_email_plain(candidate_name, role, sender_name, company, extra_note), "plain"))
        msg.attach(MIMEText(build_screening_email_html(candidate_name, role, sender_name, company, extra_note), "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True, f"✓ Sent to {recipient_email}"
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail auth failed. Check your App Password in Settings."
    except smtplib.SMTPRecipientsRefused:
        return False, f"Email rejected: {recipient_email}"
    except Exception as e:
        return False, f"Failed: {str(e)}"


def send_bulk_screening_emails(
    sender_email, sender_password,
    candidates, role, sender_name,
    company="Seven Hiring", extra_note=""
):
    """candidates: list of {"name": str, "email": str}"""
    results = []
    for c in candidates:
        ok, msg = send_screening_email(
            sender_email, sender_password,
            c.get("email",""), c.get("name","there"),
            role, sender_name, company, extra_note
        )
        results.append({"name": c.get("name"), "email": c.get("email"), "success": ok, "message": msg})
    return results


def send_email(sender_email, sender_password, recipient_email, subject, body,
               smtp_host="smtp.gmail.com", smtp_port=587):
    """Legacy single email send — kept for backwards compatibility."""
    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email; msg["To"] = recipient_email; msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(); server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent."
    except smtplib.SMTPAuthenticationError:
        return False, "Auth failed. Check App Password."
    except Exception as e:
        return False, str(e)
