"""Where messages go outside the app (phase 7E): the SMS and e-mail providers.

A provider is chosen with an environment variable (SMS_PROVIDER, EMAIL_PROVIDER), and its keys are
environment variables too, so no secret is ever stored in the database or shown on a screen. "log" writes
the message to the server log with the address masked, for trying the feature out. The real providers
refuse to work in demo mode: the demo's patients and numbers are invented, and a real person may own them.
"""

import hashlib
import hmac
import json
import logging
import smtplib
import ssl
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid

import httpx

from app.config import Settings, get_settings
from app.safety.privacy import mask_text

log = logging.getLogger(__name__)

SMS_PROVIDERS = ("none", "log", "twilio", "webhook")
EMAIL_PROVIDERS = ("none", "log", "smtp")
# The environment variables each provider needs.
NEEDS = {
    "twilio": ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"),
    "webhook": ("SMS_WEBHOOK_URL", "SMS_WEBHOOK_SECRET"),
    "smtp": ("SMTP_HOST", "SMTP_FROM"),
}


class DeliveryError(Exception):
    """A provider refused or could not be reached. The text names the cause, never the address."""


@dataclass
class Channel:
    channel: str  # "sms" or "email"
    provider: str
    ready: bool
    real: bool  # sends to real people (not "log")
    problem: str = ""
    missing: list[str] = field(default_factory=list)

    def view(self) -> dict:
        return {
            "provider": self.provider,
            "ready": self.ready,
            "real": self.real,
            "problem": self.problem,
            "missing": self.missing,
        }


def _env_value(settings: Settings, name: str) -> str:
    return str(getattr(settings, name.lower(), "") or "")


def channel_status(channel: str, settings: Settings | None = None) -> Channel:
    settings = settings or get_settings()
    provider = (settings.sms_provider if channel == "sms" else settings.email_provider).strip().lower()
    known = SMS_PROVIDERS if channel == "sms" else EMAIL_PROVIDERS
    if provider not in known:
        return Channel(channel, provider, False, False, problem="unknown_provider")
    if provider == "none":
        return Channel(channel, provider, False, False, problem="not_configured")
    if provider == "log":
        return Channel(channel, provider, True, False)
    missing = [name for name in NEEDS[provider] if not _env_value(settings, name)]
    if missing:
        return Channel(channel, provider, False, True, problem="missing_settings", missing=missing)
    if settings.demo_mode:
        return Channel(channel, provider, False, True, problem="demo_mode")
    return Channel(channel, provider, True, True)


def statuses(settings: Settings | None = None) -> dict[str, Channel]:
    return {name: channel_status(name, settings) for name in ("sms", "email")}


def _short(text: str, limit: int = 160) -> str:
    return mask_text(" ".join(str(text).split()))[:limit]


# --------------------------------------------------------------------------- senders
# Each takes the full address (+91XXXXXXXXXX or an e-mail address) and returns the provider's reference.


def _send_log(channel: str, to: str, subject: str, text: str) -> str:
    log.info("%s message to %s: %s", channel, mask_text(to), mask_text(text))
    return "log"


def _send_twilio(settings: Settings, to: str, text: str) -> str:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    try:
        response = httpx.post(
            url,
            data={"To": to, "From": settings.twilio_from, "Body": text},
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=settings.delivery_timeout_seconds,
        )
    except httpx.HTTPError as err:
        raise DeliveryError(f"Twilio could not be reached ({type(err).__name__}).") from None
    if response.status_code >= 300:
        try:
            body = response.json()
            detail = f"error {body.get('code')}: {body.get('message', '')}"
        except ValueError:
            detail = response.reason_phrase
        raise DeliveryError(_short(f"Twilio answered {response.status_code}, {detail}"))
    return str(response.json().get("sid", ""))[:80]


def _send_webhook(settings: Settings, to: str, text: str, reference: str) -> str:
    """POST {"channel", "to", "text", "reference"} to the hospital's gateway, signed with HMAC-SHA256 over
    "<timestamp>.<body>" in the X-CareFlow-Signature header, so the gateway can check it came from CareFlow."""
    body = json.dumps({"channel": "sms", "to": to, "text": text, "reference": reference}, ensure_ascii=False)
    stamp = str(int(time.time()))
    signature = hmac.new(settings.sms_webhook_secret.encode(), f"{stamp}.{body}".encode(), hashlib.sha256).hexdigest()
    try:
        response = httpx.post(
            settings.sms_webhook_url,
            content=body.encode(),
            headers={
                "Content-Type": "application/json",
                "X-CareFlow-Timestamp": stamp,
                "X-CareFlow-Signature": f"sha256={signature}",
            },
            timeout=settings.delivery_timeout_seconds,
        )
    except httpx.HTTPError as err:
        raise DeliveryError(f"The SMS gateway could not be reached ({type(err).__name__}).") from None
    if response.status_code >= 300:
        raise DeliveryError(f"The SMS gateway answered {response.status_code}.")
    try:
        return str(response.json().get("id", ""))[:80]
    except (ValueError, AttributeError):
        return ""


def _send_smtp(settings: Settings, to: str, subject: str, text: str) -> str:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = settings.smtp_from, to, subject
    message["Message-ID"] = make_msgid(domain=settings.smtp_from.rsplit("@", 1)[-1] or None)
    message.set_content(text)
    security = settings.smtp_security.strip().lower()
    timeout = settings.delivery_timeout_seconds
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout,
                                      context=ssl.create_default_context())  # fmt: skip
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
        with server:
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise DeliveryError("The mail server refused the user name or password.") from None
    except smtplib.SMTPRecipientsRefused:
        raise DeliveryError("The mail server refused the address.") from None
    except (smtplib.SMTPException, OSError) as err:
        raise DeliveryError(_short(f"The mail server could not take the message ({type(err).__name__}).")) from None
    return str(message["Message-ID"])[:80]


def send(channel: str, to: str, subject: str, text: str, reference: str = "", settings: Settings | None = None) -> str:
    """Send one message now. Raises DeliveryError; the caller checks the channel is ready first."""
    settings = settings or get_settings()
    status = channel_status(channel, settings)
    if not status.ready:
        raise DeliveryError(f"{channel.upper()} is not set up ({status.problem}).")
    if status.provider == "log":
        return _send_log(channel, to, subject, text)
    if status.provider == "twilio":
        return _send_twilio(settings, to, text)
    if status.provider == "webhook":
        return _send_webhook(settings, to, text, reference)
    return _send_smtp(settings, to, subject, text)
