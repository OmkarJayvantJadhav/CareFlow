"""Normalisation of free-text search arguments (English, Hindi, Marathi)."""

import re
from datetime import date, datetime, timedelta

from app.tools.errors import ToolError

LANGUAGE_ALIASES = {
    "en": "en", "english": "en", "अंग्रेज़ी": "en", "अंग्रेजी": "en", "इंग्रजी": "en",
    "hi": "hi", "hindi": "hi", "हिंदी": "hi", "हिन्दी": "hi",
    "mr": "mr", "marathi": "mr", "मराठी": "mr",
}  # fmt: skip

# Keys are department names; values are lower-case aliases.
SPECIALTY_ALIASES = {
    "General Medicine": ["general medicine", "general physician", "physician", "medicine", "gp", "fever",
                         "सामान्य चिकित्सा", "जनरल फिजिशियन", "सामान्य औषधोपचार"],
    "Cardiology": ["cardiology", "cardiologist", "cardiac", "heart", "हृदय", "हृदयरोग", "दिल", "कार्डियोलॉजी"],
    "ENT": ["ent", "ear", "nose", "throat", "otolaryngology", "कान", "नाक", "गला", "घसा", "ईएनटी"],
    "Orthopaedics": ["orthopaedics", "orthopedics", "orthopaedic", "orthopedic", "ortho", "bone", "joint",
                     "हड्डी", "हाड", "अस्थिरोग"],
    "Paediatrics": ["paediatrics", "pediatrics", "paediatrician", "pediatrician", "child", "children",
                    "बाल रोग", "बालरोग", "मुलांचे"],
    "Dermatology": ["dermatology", "dermatologist", "skin", "त्वचा", "त्वचारोग"],
    "Gynaecology": ["gynaecology", "gynecology", "gynaecologist", "gynecologist", "obstetrics",
                    "स्त्री रोग", "स्त्रीरोग"],
    "Ophthalmology": ["ophthalmology", "ophthalmologist", "eye", "eyes", "आंख", "आँख", "डोळे", "नेत्र"],
}  # fmt: skip

WEEKDAY_ALIASES = {
    1: ["monday", "mon", "सोमवार"],
    2: ["tuesday", "tue", "tues", "मंगलवार", "मंगळवार"],
    3: ["wednesday", "wed", "बुधवार"],
    4: ["thursday", "thu", "thurs", "गुरुवार", "गुरूवार"],
    5: ["friday", "fri", "शुक्रवार"],
    6: ["saturday", "sat", "शनिवार"],
    7: ["sunday", "sun", "रविवार"],
}


def normalize_language(value: str) -> str:
    key = value.strip().lower()
    if key not in LANGUAGE_ALIASES:
        raise ToolError("VALIDATION_ERROR", f"Unsupported language '{value}'. Use English, Hindi or Marathi.")
    return LANGUAGE_ALIASES[key]


def normalize_specialty(value: str) -> str:
    key = value.strip().lower()
    for department, aliases in SPECIALTY_ALIASES.items():
        if key == department.lower() or key in aliases:
            return department
    for department, aliases in SPECIALTY_ALIASES.items():
        if any(re.search(rf"\b{re.escape(a)}\b", key) for a in aliases if a.isascii()):
            return department
        if any(a in key for a in aliases if not a.isascii()):
            return department
    raise ToolError("VALIDATION_ERROR", f"Unknown specialty '{value}'.", known=list(SPECIALTY_ALIASES))


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ToolError("VALIDATION_ERROR", f"'{value}' is not a date in YYYY-MM-DD format.") from None


def parse_day(value: str | date, now: datetime) -> tuple[int, date]:
    """Return (ISO weekday, concrete date) for a weekday name, 'today'/'tomorrow' or an ISO date.

    A weekday name resolves to the next such day, today included.
    """
    if isinstance(value, date):
        return value.isoweekday(), value
    key = value.strip().lower()
    today = now.date()
    if key in ("today", "आज"):
        return today.isoweekday(), today
    if key in ("tomorrow", "उद्या"):
        d = today + timedelta(days=1)
        return d.isoweekday(), d
    for weekday, aliases in WEEKDAY_ALIASES.items():
        if key in aliases:
            return weekday, today + timedelta(days=(weekday - today.isoweekday()) % 7)
    d = parse_date(value)
    return d.isoweekday(), d
