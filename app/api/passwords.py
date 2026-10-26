"""Password hashing with scrypt from the standard library (no extra dependency).

Stored form: ``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``, so the cost can be raised later
without breaking existing hashes.
"""

import base64
import hashlib
import hmac
import secrets

from app.tools.errors import ToolError

N, R, P, DKLEN = 2**14, 8, 1, 32  # about 16 MB and a few tens of milliseconds per hash


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check; False for a missing or malformed hash."""
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Compared against when the username does not exist, so a wrong username takes as long as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def check_new_password(password: str, previous: str | None = None) -> None:
    """At least 8 characters, no spaces at the ends, not repetitive, and not the old one."""
    if len(password) < 8 or password.strip() != password or len(set(password)) < 4:
        raise ToolError("VALIDATION_ERROR", "Choose a stronger password (at least 8 characters, not repetitive).")
    if previous is not None and password == previous:
        raise ToolError("VALIDATION_ERROR", "Choose a password different from the current one.")


# No 0/O, 1/l/I: a temporary password is read out or copied by hand.
_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def temporary_password(length: int = 12) -> str:
    """A random password an admin hands over once; the account must replace it at its first sign-in."""
    while True:
        candidate = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
        if any(c.isdigit() for c in candidate) and len(set(candidate)) >= 4:
            return candidate
