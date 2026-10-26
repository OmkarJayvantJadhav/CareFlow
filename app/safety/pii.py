"""Patients' phone numbers (phase 7C): checked, encrypted at rest, and findable without being readable.

Three forms are stored: the masked form (+91 98XXXXXX12) for every screen, log and LLM context; the full
number encrypted with AES-GCM, readable only through an audited action; and a keyed hash of the digits, so
staff can find a patient by phone number exactly without the database holding it in the clear.
"""

import base64
import hashlib
import hmac
import logging
import os
import re
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings
from app.safety.privacy import mask_phone_number
from app.tools.errors import ToolError

log = logging.getLogger(__name__)
_AAD = b"careflow:patient-phone"
_PREFIX = "v1:"


def normalize_mobile(value: str | None) -> str:
    """A 10-digit Indian mobile number from what someone typed (+91, 0, spaces and dashes allowed)."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ToolError("VALIDATION_ERROR", "Enter a 10-digit Indian mobile number.")
    return digits


@lru_cache(maxsize=4)
def _keys(data_key: str, auth_secret: str) -> tuple[bytes, bytes]:
    if data_key:
        try:
            root = base64.b64decode(data_key, validate=True)
        except ValueError:
            root = b""
        if len(root) < 32:  # not base64 of 32+ bytes: a long random string works as well
            root = data_key.encode()
        if len(root) < 32:
            raise RuntimeError("DATA_KEY is too short; use python -m app.manage new-data-key.")
    else:
        root = auth_secret.encode()

    def derive(info: bytes) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"careflow-pii", info=info).derive(root)

    return derive(b"phone-encryption"), derive(b"phone-index")


def _current_keys() -> tuple[bytes, bytes]:
    settings = get_settings()
    return _keys(settings.data_key, settings.auth_secret)


def encrypt_phone(digits: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_current_keys()[0]).encrypt(nonce, digits.encode(), _AAD)
    return _PREFIX + base64.b64encode(nonce + sealed).decode()


def decrypt_phone(token: str | None) -> str | None:
    """The digits, or None when there is no number or the key has changed since it was stored."""
    if not token or not token.startswith(_PREFIX):
        return None
    raw = base64.b64decode(token[len(_PREFIX) :])
    try:
        return AESGCM(_current_keys()[0]).decrypt(raw[:12], raw[12:], _AAD).decode()
    except InvalidTag:
        log.warning("a stored phone number could not be decrypted; was DATA_KEY or AUTH_SECRET changed?")
        return None


def phone_index(digits: str) -> str:
    return hmac.new(_current_keys()[1], digits.encode(), hashlib.sha256).hexdigest()


def set_phone(patient, value: str) -> str:
    """Store a patient's number in all three forms; returns the digits."""
    digits = normalize_mobile(value)
    patient.phone_masked = mask_phone_number(digits)
    patient.phone_encrypted = encrypt_phone(digits)
    patient.phone_hash = phone_index(digits)
    return digits


def display_phone(digits: str) -> str:
    return f"+91 {digits[:5]} {digits[5:]}"
