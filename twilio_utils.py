from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Say, Pause
import os


def get_twilio_client(account_sid: str, auth_token: str) -> Client:
    return Client(account_sid, auth_token)


def make_call(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    candidate_name: str,
    role_name: str,
    sender_name: str,
    company_name: str = "Seven Hiring",
    twiml_url: str = None
) -> tuple[bool, str]:
    """
    Initiate an outbound call to a candidate.
    Uses TwiML to play a spoken script.
    Returns (success: bool, message_or_call_sid: str)
    """
    try:
        client = get_twilio_client(account_sid, auth_token)

        if twiml_url:
            call = client.calls.create(
                to=to_number,
                from_=from_number,
                url=twiml_url
            )
        else:
            twiml = build_call_script_twiml(
                candidate_name=candidate_name,
                role_name=role_name,
                sender_name=sender_name,
                company_name=company_name
            )
            call = client.calls.create(
                to=to_number,
                from_=from_number,
                twiml=str(twiml)
            )

        return True, call.sid

    except Exception as e:
        err = str(e)
        if "authenticate" in err.lower() or "credentials" in err.lower():
            return False, "Twilio authentication failed. Check your Account SID and Auth Token."
        elif "not a valid phone number" in err.lower() or "21211" in err:
            return False, f"Invalid phone number: {to_number}. Use E.164 format e.g. +919876543210"
        elif "unverified" in err.lower() or "21606" in err:
            return False, "The destination number is unverified. With a trial account, verify the number in Twilio first."
        else:
            return False, f"Call failed: {err}"


def build_call_script_twiml(
    candidate_name: str,
    role_name: str,
    sender_name: str,
    company_name: str = "Seven Hiring"
) -> VoiceResponse:
    """
    Build a TwiML VoiceResponse that speaks a recruiter outreach script.
    """
    response = VoiceResponse()

    script_parts = [
        f"Hello, may I please speak with {candidate_name}?",
        f"Hi {candidate_name}, this is {sender_name} calling from {company_name}.",
        f"I'm reaching out regarding an exciting opportunity for the role of {role_name}.",
        "We came across your profile and felt you could be a strong match.",
        "I'd love to connect with you briefly to share more details and understand your interest.",
        "If you're open to exploring this, please feel free to call us back or check your email for more information.",
        f"Once again, this is {sender_name} from {company_name}.",
        "Thank you so much for your time, and have a wonderful day."
    ]

    for part in script_parts:
        response.say(part, voice="Polly.Aditi", language="en-IN")
        response.pause(length=1)

    return response


def send_sms(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    message: str
) -> tuple[bool, str]:
    """
    Send an SMS to a candidate.
    """
    try:
        client = get_twilio_client(account_sid, auth_token)
        msg = client.messages.create(
            to=to_number,
            from_=from_number,
            body=message
        )
        return True, msg.sid
    except Exception as e:
        return False, f"SMS failed: {str(e)}"


def format_phone_for_twilio(phone: str, default_country_code: str = "+91") -> str:
    """
    Convert a raw Indian phone number to E.164 format for Twilio.
    e.g. "9876543210" → "+919876543210"
         "+91 98765 43210" → "+919876543210"
    """
    digits = "".join(filter(str.isdigit, phone))

    if phone.startswith("+"):
        return "+" + digits

    if len(digits) == 10 and digits[0] in "6789":
        return default_country_code + digits

    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits

    return default_country_code + digits[-10:]


def get_call_status(account_sid: str, auth_token: str, call_sid: str) -> dict:
    """
    Get the status of an initiated call.
    Returns dict with status, duration, direction.
    """
    try:
        client = get_twilio_client(account_sid, auth_token)
        call = client.calls(call_sid).fetch()
        return {
            "status": call.status,
            "duration": call.duration,
            "direction": call.direction,
            "to": call.to,
            "from": call.from_
        }
    except Exception as e:
        return {"status": "unknown", "error": str(e)}
