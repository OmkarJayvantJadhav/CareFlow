from datetime import date, datetime, time

from app.config import HOSPITAL_TZ


def now_ist() -> datetime:
    return datetime.now(HOSPITAL_TZ)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetimes are not allowed")
    return dt.astimezone(HOSPITAL_TZ)


def at(day: date, t: time) -> datetime:
    """A hospital-local datetime for a date and wall-clock time."""
    return datetime.combine(day, t, tzinfo=HOSPITAL_TZ)


def iso(dt: datetime | None) -> str | None:
    return to_ist(dt).isoformat() if dt else None


def resolve_now(now: datetime | None) -> datetime:
    """Every service takes an optional clock so the simulator and tests can replay any moment."""
    return to_ist(now) if now else now_ist()
