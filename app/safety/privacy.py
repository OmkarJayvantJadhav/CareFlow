"""Phone-number masking for logs, traces, audit rows and LLM context (NFR-08)."""

import logging
import re
from typing import Any

# Indian mobile numbers, optionally with +91 / 0 prefix and spaces or dashes between digits.
_PHONE_RE = re.compile(r"(?<![\dX])(?:\+?91[\s-]?|0)?([6-9](?:[\s-]?\d){9})(?!\d)")


def mask_phone_number(digits: str) -> str:
    """Format a 10-digit mobile number in the stored masked form: +91 98XXXXXX12."""
    d = re.sub(r"\D", "", digits)[-10:]
    if len(d) != 10:
        raise ValueError("expected a 10-digit mobile number")
    return f"+91 {d[:2]}XXXXXX{d[-2:]}"


_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+'-])[A-Za-z0-9._%+'-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")


def mask_text(text: str) -> str:
    """Replace every phone number and e-mail address in free text with its masked form."""
    text = _PHONE_RE.sub(lambda m: mask_phone_number(m.group(1)), text)
    return _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text) if "@" in text else text


# Values under these keys are never stored or logged (a temporary password returned once, for example).
_SECRET_KEY = re.compile(r"password|secret", re.I)


def mask_payload(value: Any) -> Any:
    """Recursively mask phone numbers inside JSON-like data, and drop secrets."""
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {k: "[redacted]" if _SECRET_KEY.search(str(k)) else mask_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_payload(v) for v in value]
    return value


def _mask_log_arg(value: Any) -> Any:
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, int) and not isinstance(value, bool):
        masked = mask_text(str(value))
        return value if masked == str(value) else masked
    return value


class MaskingFilter(logging.Filter):
    """Logging filter that masks phone numbers in the message template and its arguments.

    The arguments stay a tuple/dict so formatters that read them (e.g. uvicorn's
    access log) keep working.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_text(record.msg)
        if isinstance(record.args, dict):
            record.args = {k: _mask_log_arg(v) for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_mask_log_arg(a) for a in record.args)
        return True


_installed = False


def install_log_masking() -> None:
    """Mask every log record at creation time, so handlers added later are covered too."""
    global _installed
    if _installed:
        return
    base_factory = logging.getLogRecordFactory()

    def masked_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = base_factory(*args, **kwargs)
        MaskingFilter().filter(record)
        return record

    logging.setLogRecordFactory(masked_factory)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _installed = True
