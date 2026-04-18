import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(
    sender_email: str,
    sender_password: str,
    recipient_email: str,
    subject: str,
    body: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587
) -> tuple[bool, str]:
    """
    Send an email via SMTP.
    Returns (success: bool, message: str)
    Works with Gmail. For Gmail, use an App Password (not your main password).
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())

        return True, "Email sent successfully."

    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your email and App Password."
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"


def generate_email_template(candidate_name: str, sender_name: str, role_name: str = "", company_name: str = "Seven Hiring") -> str:
    """
    Fallback static email template (used when GPT is unavailable).
    """
    if not candidate_name or candidate_name.lower() in ["unknown", "-", "nan"]:
        candidate_name = "there"

    role_line = f" for the {role_name} role" if role_name else ""

    return f"""Hi {candidate_name},

Hope you're doing well.

We came across your profile and found it highly relevant{role_line} we are currently hiring for.

We would like to explore this further and understand your experience better.

The role details, compensation, and location can be discussed based on your interest.

Would you be open to a quick 15-minute call this week?

Best regards,
{sender_name}
{company_name}
"""
