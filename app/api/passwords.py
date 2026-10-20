"""Password hashing with scrypt from the standard library (no extra dependency).

Stored form: ``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``, so the cost can be raised later
without breaking existing hashes.
"""

import base64
import hashlib
import hmac
import secrets

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
