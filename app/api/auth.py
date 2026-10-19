"""Demo bearer tokens (docs §7): HMAC-signed, carrying user, role and a session id.

The role is read from the token and must match the user's record; it is never
taken from a request body.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AppUser
from app.timeutil import now_ist
from app.tools.errors import ToolError
from app.tools.permissions import Actor


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> str:
    return _b64(hmac.new(get_settings().auth_secret.encode(), payload, hashlib.sha256).digest())


def issue_token(user: AppUser, now: datetime | None = None) -> tuple[str, datetime]:
    now = now or now_ist()
    expires = now + timedelta(hours=get_settings().token_ttl_hours)
    payload = json.dumps(
        {"uid": user.id, "role": user.role, "sid": uuid.uuid4().hex, "exp": int(expires.timestamp())},
        separators=(",", ":"),
    ).encode()
    return f"{_b64(payload)}.{_sign(payload)}", expires


def verify_token(db: Session, token: str, now: datetime | None = None) -> tuple[Actor, str, datetime]:
    """Return (actor, session id, expiry) or raise UNAUTHORIZED."""
    try:
        body, signature = token.split(".", 1)
        payload = _unb64(body)
        if not hmac.compare_digest(signature, _sign(payload)):
            raise ValueError("bad signature")
        claims = json.loads(payload)
        expires = datetime.fromtimestamp(int(claims["exp"]), tz=(now or now_ist()).tzinfo)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ToolError("UNAUTHORIZED", "Please sign in again.") from None
    if expires <= (now or now_ist()):
        raise ToolError("UNAUTHORIZED", "Your session has expired; please sign in again.")
    user = db.get(AppUser, int(claims["uid"]))
    if user is None or user.role != claims.get("role"):
        raise ToolError("UNAUTHORIZED", "Please sign in again.")
    return Actor.from_user(user), str(claims["sid"]), expires
