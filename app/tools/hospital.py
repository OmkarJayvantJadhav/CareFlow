"""The hospital's own setup, edited by its admins (phase 7B): its details, departments, doctors and timetables.

Changes to a timetable apply from tomorrow and never cancel a booking (see ``app.tools.timetable``). A doctor
who leaves gets a last day: later bookings are moved off like leave (the patient is told and reschedules
free of charge). Departments and doctors can be removed only while nothing refers to them; afterwards they
stay for the records.
"""

import re
from datetime import date, datetime, time, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    ACTIVE_WAITLIST_STATUSES,
    LANGUAGES,
    Appointment,
    AppUser,
    Department,
    Doctor,
    DoctorLeave,
    HospitalProfile,
    QueueSession,
    Slot,
    WaitingList,
)
from app.timeutil import at, iso, resolve_now
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.notify import notify
from app.tools.permissions import Actor, require_role
from app.tools.timetable import SLOT_DAYS_AHEAD, ensure_slots, rebuild_slots
from app.tools.vocab import SPECIALTY_ALIASES

MAX_ALIASES = 20
PHONE_RE = re.compile(r"^[0-9+()\- ]{6,30}$")


# --------------------------------------------------------------------------- the hospital's details


def get_profile(db: Session) -> HospitalProfile | None:
    return db.get(HospitalProfile, 1)


def _by_language(values: dict | None) -> dict[str, str]:
    """English, Hindi and Marathi, each falling back to English."""
    values = values or {}
    english = values.get("en", "")
    return {lang: values.get(lang) or english for lang in LANGUAGES}


def hospital_name(db: Session, language: str = "en") -> str:
    """The hospital's name in a language; empty until an admin has entered it."""
    profile = get_profile(db)
    return _by_language(profile.name)[language] if profile else ""


def emergency_note(db: Session, language: str) -> str:
    """Where this hospital's emergency department is, in that language only (no other language is mixed in)."""
    profile = get_profile(db)
    return (profile.emergency_note or {}).get(language, "") if profile else ""


def reception_hours(db: Session) -> str:
    profile = get_profile(db)
    if profile is None:
        return ""
    return f"{profile.reception_opens:%H:%M}–{profile.reception_closes:%H:%M}"


def message_values(db: Session, language: str) -> dict[str, str]:
    """The hospital's own facts for the fixed messages: ``{note}`` (emergency directions) and ``{hours}``."""
    note = emergency_note(db, language)
    hours = reception_hours(db)
    return {"note": f" {note}" if note else "", "hours": (", " if language == "en" else " ") + hours if hours else ""}


def public_directory(db: Session, today: date) -> dict:
    """What a hospital's homepage shows anyone (D-134): reception hours, departments with their OPD hours,
    and the doctors who still hold OPD, with their languages and OPD days. No patient data."""
    departments = []
    for dept in db.scalars(select(Department).order_by(Department.name)):
        doctors = [
            {"name": d.name, "languages": list(d.languages), "opd_days": sorted(d.opd_days)}
            for d in sorted(dept.doctors, key=lambda d: d.name)
            if d.last_day is None or d.last_day >= today
        ]
        departments.append(
            {
                "name": dept.name,
                "floor": dept.floor,
                "opd_start": dept.opd_start.strftime("%H:%M"),
                "opd_end": dept.opd_end.strftime("%H:%M"),
                "doctors": doctors,
            }
        )
    return {"reception_hours": reception_hours(db), "departments": departments}


def public_profile(db: Session) -> dict | None:
    """What anyone may see: the name, address, phone and emergency directions."""
    profile = get_profile(db)
    if profile is None:
        return None
    return {
        "name": _by_language(profile.name),
        "address": profile.address,
        "phone": profile.phone,
        "emergency_note": {lang: (profile.emergency_note or {}).get(lang, "") for lang in LANGUAGES},
    }


def profile_view(profile: HospitalProfile | None) -> dict:
    if profile is None:
        return {
            "name": {lang: "" for lang in LANGUAGES},
            "address": "",
            "phone": "",
            "reception_opens": "08:00",
            "reception_closes": "20:00",
            "emergency_note": {lang: "" for lang in LANGUAGES},
            "updated_at": None,
        }
    return {
        "name": {lang: (profile.name or {}).get(lang, "") for lang in LANGUAGES},
        "address": profile.address,
        "phone": profile.phone,
        "reception_opens": f"{profile.reception_opens:%H:%M}",
        "reception_closes": f"{profile.reception_closes:%H:%M}",
        "emergency_note": {lang: (profile.emergency_note or {}).get(lang, "") for lang in LANGUAGES},
        "updated_at": iso(profile.updated_at) if profile.updated_at else None,
    }


def _text(value: str | None, field: str, low: int, high: int) -> str:
    cleaned = " ".join((value or "").split())
    if cleaned and not low <= len(cleaned) <= high:
        raise ToolError("VALIDATION_ERROR", f"{field}: {low}–{high} characters.")
    return cleaned


@write_tool("update_hospital_profile")
def update_profile(
    db: Session,
    actor: Actor,
    name: dict[str, str],
    address: str,
    phone: str,
    reception_opens: time,
    reception_closes: time,
    emergency_note: dict[str, str],
    now: datetime | None = None,
) -> dict:
    now = resolve_now(now)
    require_role(actor, "admin")
    names = {lang: _text(name.get(lang), "Hospital name", 2, 120) for lang in LANGUAGES}
    if not names["en"]:
        raise ToolError("VALIDATION_ERROR", "Give the hospital's name in English.")
    notes = {lang: _text(emergency_note.get(lang), "Emergency directions", 10, 300) for lang in LANGUAGES}
    address = _text(address, "Address", 5, 200)
    phone = " ".join((phone or "").split())
    if phone and not PHONE_RE.match(phone):
        raise ToolError("VALIDATION_ERROR", "Give the reception phone number in digits (spaces, +, - allowed).")
    if reception_closes <= reception_opens:
        raise ToolError("VALIDATION_ERROR", "Reception must close after it opens.")
    profile = get_profile(db) or HospitalProfile(id=1)
    profile.name = {k: v for k, v in names.items() if v}
    profile.emergency_note = {k: v for k, v in notes.items() if v}
    profile.address, profile.phone = address, phone
    profile.reception_opens, profile.reception_closes = reception_opens, reception_closes
    profile.updated_at, profile.updated_by = now, actor.user_id
    db.add(profile)
    db.flush()
    return profile_view(profile)


# --------------------------------------------------------------------------- departments and search words


def _clean_aliases(aliases: list[str] | None) -> list[str]:
    out: list[str] = []
    for alias in aliases or []:
        word = " ".join(alias.split()).casefold()
        if not word:
            continue
        if not 2 <= len(word) <= 40:
            raise ToolError("VALIDATION_ERROR", "Each search word is 2–40 characters.")
        if word not in out:
            out.append(word)
    if len(out) > MAX_ALIASES:
        raise ToolError("VALIDATION_ERROR", f"At most {MAX_ALIASES} search words per department.")
    return out


def department_words(dept: Department) -> list[str]:
    """The department's name, its own search words, and common words for well-known specialties."""
    name = dept.name.casefold()
    words = [name, *(dept.aliases or [])]
    for known, aliases in SPECIALTY_ALIASES.items():
        if name == known.casefold() or name in aliases:
            words += [known.casefold(), *aliases]
    return list(dict.fromkeys(words))


def resolve_department(db: Session, value: str) -> str:
    """A department's name from what someone typed ("heart", "हृदय", "ENT"); exact words first."""
    key = value.strip().casefold()
    departments = list(db.scalars(select(Department).order_by(Department.id)))
    vocab = [(d.name, department_words(d)) for d in departments]
    for name, words in vocab:
        if key in words:
            return name
    for name, words in vocab:
        if any(re.search(rf"\b{re.escape(w)}\b", key) for w in words if w.isascii()):
            return name
        if any(w in key for w in words if not w.isascii()):
            return name
    raise ToolError("VALIDATION_ERROR", f"Unknown specialty '{value}'.", known=[d.name for d in departments])


def _check_hours(opd_start: time, opd_end: time, slot_minutes: list[int]) -> None:
    span = (datetime.combine(date.min, opd_end) - datetime.combine(date.min, opd_start)).total_seconds() / 60
    if span < 30:
        raise ToolError("VALIDATION_ERROR", "OPD must close at least 30 minutes after it opens.")
    if slot_minutes and span < max(slot_minutes):
        raise ToolError("VALIDATION_ERROR", "These OPD hours are shorter than a doctor's appointment length.")


def _unique_department_name(db: Session, name: str, except_id: int | None = None) -> str:
    name = " ".join((name or "").split())
    if not 2 <= len(name) <= 80:
        raise ToolError("VALIDATION_ERROR", "Give a department name of 2–80 characters.")
    query = select(Department.id).where(func.lower(Department.name) == name.lower())
    if except_id is not None:
        query = query.where(Department.id != except_id)
    if db.scalar(query) is not None:
        raise ToolError("DUPLICATE", "There is already a department with this name.")
    return name


def _check_floor(floor: int) -> int:
    if not -3 <= floor <= 60:
        raise ToolError("VALIDATION_ERROR", "Floor: -3 to 60 (0 is the ground floor).")
    return floor


def doctor_view(doctor: Doctor, today: date, accounts: dict[int, str]) -> dict:
    return {
        "doctor_id": doctor.id,
        "name": doctor.name,
        "department_id": doctor.department_id,
        "languages": list(doctor.languages),
        "opd_days": sorted(doctor.opd_days),
        "slot_minutes": doctor.slot_minutes,
        "last_day": doctor.last_day.isoformat() if doctor.last_day else None,
        "current": doctor.is_current(today),
        "account": accounts.get(doctor.id),
    }


def department_view(dept: Department, today: date, accounts: dict[int, str]) -> dict:
    doctors = sorted(dept.doctors, key=lambda d: (not d.is_current(today), d.name))
    return {
        "department_id": dept.id,
        "name": dept.name,
        "floor": dept.floor,
        "opd_start": f"{dept.opd_start:%H:%M}",
        "opd_end": f"{dept.opd_end:%H:%M}",
        "aliases": list(dept.aliases or []),
        "doctors": [doctor_view(d, today, accounts) for d in doctors],
    }


def hospital_setup(db: Session, actor: Actor, now: datetime | None = None) -> dict:
    """Everything the setup page shows."""
    now = resolve_now(now)
    require_role(actor, "admin")
    accounts = dict(
        db.execute(
            select(AppUser.doctor_id, AppUser.username).where(AppUser.doctor_id.is_not(None), AppUser.active)
        ).all()
    )
    departments = db.scalars(select(Department).order_by(Department.name))
    return {
        "profile": profile_view(get_profile(db)),
        "departments": [department_view(d, now.date(), accounts) for d in departments],
    }


@write_tool("create_department")
def create_department(
    db: Session,
    actor: Actor,
    name: str,
    floor: int,
    opd_start: time,
    opd_end: time,
    aliases: list[str] | None = None,
    now: datetime | None = None,
) -> dict:
    now = resolve_now(now)
    require_role(actor, "admin")
    _check_hours(opd_start, opd_end, [])
    dept = Department(
        name=_unique_department_name(db, name),
        floor=_check_floor(floor),
        opd_start=opd_start,
        opd_end=opd_end,
        aliases=_clean_aliases(aliases),
    )
    db.add(dept)
    db.flush()
    db.refresh(dept)
    return department_view(dept, now.date(), {})


@write_tool("update_department")
def update_department(
    db: Session,
    actor: Actor,
    department_id: int,
    name: str | None = None,
    floor: int | None = None,
    opd_start: time | None = None,
    opd_end: time | None = None,
    aliases: list[str] | None = None,
    now: datetime | None = None,
) -> dict:
    """New OPD hours apply from tomorrow to every doctor in the department; bookings are kept."""
    now = resolve_now(now)
    require_role(actor, "admin")
    dept = db.scalars(select(Department).where(Department.id == department_id).with_for_update()).first()
    if dept is None:
        raise ToolError("NOT_FOUND", "There is no such department.")
    if name is not None:
        dept.name = _unique_department_name(db, name, except_id=dept.id)
    if floor is not None:
        dept.floor = _check_floor(floor)
    if aliases is not None:
        dept.aliases = _clean_aliases(aliases)
    start, end = opd_start or dept.opd_start, opd_end or dept.opd_end
    timetable = None
    if (start, end) != (dept.opd_start, dept.opd_end):
        current = [d for d in dept.doctors if d.is_current(now.date())]
        _check_hours(start, end, [d.slot_minutes for d in current])
        dept.opd_start, dept.opd_end = start, end
        db.flush()
        timetable = rebuild_slots(db, [d.id for d in current], now)
    db.flush()
    return {**department_view(dept, now.date(), {}), "timetable": timetable}


@write_tool("delete_department")
def delete_department(db: Session, actor: Actor, department_id: int, now: datetime | None = None) -> dict:
    resolve_now(now)
    require_role(actor, "admin")
    dept = db.get(Department, department_id)
    if dept is None:
        raise ToolError("NOT_FOUND", "There is no such department.")
    if dept.doctors:
        raise ToolError("INVALID_STATE", "Move or remove this department's doctors first.")
    name = dept.name
    db.delete(dept)
    db.flush()
    return {"department_id": department_id, "name": name, "deleted": True}


# --------------------------------------------------------------------------- doctors


def _clean_doctor(
    db: Session, name: str, languages: list[str], opd_days: list[int], slot_minutes: int, except_id: int | None
) -> tuple[str, list[str], list[int]]:
    name = " ".join((name or "").split())
    if not 3 <= len(name) <= 120:
        raise ToolError("VALIDATION_ERROR", "Give the doctor's name (3–120 characters).")
    query = select(Doctor.id).where(func.lower(Doctor.name) == name.lower())
    if except_id is not None:
        query = query.where(Doctor.id != except_id)
    if db.scalar(query) is not None:
        raise ToolError("DUPLICATE", "There is already a doctor with this name; add a middle name or initial.")
    langs = [lang for lang in LANGUAGES if lang in set(languages or [])]
    if not langs or len(set(languages)) != len(langs):
        raise ToolError("VALIDATION_ERROR", "Choose the languages the doctor speaks: English, Hindi or Marathi.")
    days = sorted(set(opd_days or []))
    if not days or any(d not in range(1, 8) for d in days):
        raise ToolError("VALIDATION_ERROR", "Choose at least one OPD day.")
    if not 5 <= slot_minutes <= 60:
        raise ToolError("VALIDATION_ERROR", "An appointment is 5–60 minutes long.")
    return name, langs, days


def _department(db: Session, department_id: int) -> Department:
    dept = db.get(Department, department_id)
    if dept is None:
        raise ToolError("VALIDATION_ERROR", "Choose the doctor's department.")
    return dept


def _horizon(now: datetime) -> tuple[date, date]:
    return now.date() + timedelta(days=1), now.date() + timedelta(days=SLOT_DAYS_AHEAD - 1)


@write_tool("create_doctor")
def create_doctor(
    db: Session,
    actor: Actor,
    name: str,
    department_id: int,
    languages: list[str],
    opd_days: list[int],
    slot_minutes: int,
    now: datetime | None = None,
) -> dict:
    """A new doctor's slots start tomorrow."""
    now = resolve_now(now)
    require_role(actor, "admin")
    name, langs, days = _clean_doctor(db, name, languages, opd_days, slot_minutes, None)
    dept = _department(db, department_id)
    _check_hours(dept.opd_start, dept.opd_end, [slot_minutes])
    doctor = Doctor(department_id=dept.id, name=name, languages=langs, opd_days=days, slot_minutes=slot_minutes)
    db.add(doctor)
    db.flush()
    db.refresh(doctor)
    first, last = _horizon(now)
    created = ensure_slots(db, first, last, [doctor.id])
    return {**doctor_view(doctor, now.date(), {}), "slots_created": created, "from": first.isoformat()}


@write_tool("update_doctor")
def update_doctor(
    db: Session,
    actor: Actor,
    doctor_id: int,
    name: str | None = None,
    department_id: int | None = None,
    languages: list[str] | None = None,
    opd_days: list[int] | None = None,
    slot_minutes: int | None = None,
    now: datetime | None = None,
) -> dict:
    """A changed department, OPD days or appointment length applies from tomorrow; bookings are kept."""
    now = resolve_now(now)
    require_role(actor, "admin")
    doctor = db.scalars(select(Doctor).where(Doctor.id == doctor_id).with_for_update()).first()
    if doctor is None:
        raise ToolError("NOT_FOUND", "There is no such doctor.")
    minutes = slot_minutes if slot_minutes is not None else doctor.slot_minutes
    name, langs, days = _clean_doctor(
        db,
        name if name is not None else doctor.name,
        languages if languages is not None else list(doctor.languages),
        opd_days if opd_days is not None else list(doctor.opd_days),
        minutes,
        doctor.id,
    )
    dept = _department(db, department_id) if department_id is not None else doctor.department
    _check_hours(dept.opd_start, dept.opd_end, [minutes])
    changed = (dept.id, days, minutes) != (doctor.department_id, sorted(doctor.opd_days), doctor.slot_minutes)
    doctor.name, doctor.languages = name, langs
    doctor.department_id, doctor.opd_days, doctor.slot_minutes = dept.id, days, minutes
    db.flush()
    db.refresh(doctor)
    timetable = rebuild_slots(db, [doctor.id], now) if changed and doctor.is_current(now.date()) else None
    return {**doctor_view(doctor, now.date(), {}), "timetable": timetable}


@write_tool("set_doctor_last_day")
def set_last_day(db: Session, actor: Actor, doctor_id: int, last_day: date | None, now: datetime | None = None) -> dict:
    """The doctor holds OPD until ``last_day`` (None: they stay). Later bookings are moved off: each patient
    is told and can choose another doctor in the department free of charge, as with leave."""
    now = resolve_now(now)
    require_role(actor, "admin")
    doctor = db.scalars(select(Doctor).where(Doctor.id == doctor_id).with_for_update()).first()
    if doctor is None:
        raise ToolError("NOT_FOUND", "There is no such doctor.")
    first, last = _horizon(now)
    if last_day is None:
        doctor.last_day = None
        db.flush()
        created = ensure_slots(db, first, last, [doctor.id])
        return {**doctor_view(doctor, now.date(), {}), "slots_created": created, "moved": [], "waiting_list": 0}
    if last_day < now.date():
        raise ToolError("VALIDATION_ERROR", "The last day cannot be in the past.")
    doctor.last_day = last_day
    after = at(last_day + timedelta(days=1), time.min)
    retired = 0
    for slot in db.scalars(
        select(Slot).where(Slot.doctor_id == doctor.id, Slot.start_at >= after, Slot.status.in_(("free", "blocked")))
    ):
        slot.status, slot.held_for_patient_id, slot.held_until = "retired", None, None
        retired += 1
    moved = []
    for appt in db.scalars(
        select(Appointment)
        .where(
            Appointment.doctor_id == doctor.id,
            Appointment.appt_date > last_day,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        )
        .order_by(Appointment.appt_date, Appointment.id)
    ):
        appt.status, appt.updated_at = "displaced", now
        notify(
            db,
            appt.patient_id,
            f"{doctor.name} no longer holds OPD here after {last_day:%d %b}, so your visit on {appt.appt_date:%d %b} "
            f"cannot go ahead. We are sorry. Please choose another doctor in {doctor.department.name} in CareFlow "
            "(My appointments → Reschedule); rescheduling is free of charge.",
            now,
            kind="unavailable",
            appointment_id=appt.id,
        )
        moved.append({"appointment_id": appt.id, "date": appt.appt_date.isoformat()})
    closed = 0
    for entry in db.scalars(
        select(WaitingList).where(WaitingList.doctor_id == doctor.id, WaitingList.status.in_(ACTIVE_WAITLIST_STATUSES))
    ):
        if any(d <= last_day for d in entry.preferred_dates):
            if entry.status == "offered" and entry.offered_slot_id is not None:
                offered = db.get(Slot, entry.offered_slot_id)
                if offered is None or offered.status == "retired":
                    entry.status, entry.offered_slot_id, entry.offer_expires_at = "active", None, None
            continue
        entry.status = "cancelled"
        closed += 1
        notify(
            db,
            entry.patient_id,
            f"{doctor.name} no longer holds OPD here after {last_day:%d %b}, so your waiting-list request has been "
            f"closed. Please book another doctor in {doctor.department.name} in CareFlow.",
            now,
            kind="unavailable",
        )
    db.flush()
    return {**doctor_view(doctor, now.date(), {}), "slots_retired": retired, "moved": moved, "waiting_list": closed}


@write_tool("delete_doctor")
def delete_doctor(db: Session, actor: Actor, doctor_id: int, now: datetime | None = None) -> dict:
    """Only a doctor nobody has booked, queued for or linked an account to (an entry made by mistake)."""
    resolve_now(now)
    require_role(actor, "admin")
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", "There is no such doctor.")
    used = db.scalar(
        select(
            exists().where(Appointment.doctor_id == doctor_id)
            | exists().where(QueueSession.doctor_id == doctor_id)
            | exists().where(WaitingList.doctor_id == doctor_id)
            | exists().where(AppUser.doctor_id == doctor_id)
        )
    )
    if used:
        raise ToolError(
            "INVALID_STATE",
            "This doctor has appointments, queues or an account, so the records must stay. Set a last day instead.",
        )
    name = doctor.name
    try:
        with db.begin_nested():
            for model in (Slot, DoctorLeave):
                for row in db.scalars(select(model).where(model.doctor_id == doctor_id)):
                    db.delete(row)
            db.flush()
            db.delete(doctor)
            db.flush()
    except IntegrityError:
        raise ToolError(
            "INVALID_STATE", "This doctor is referred to by other records; set a last day instead."
        ) from None
    return {"doctor_id": doctor_id, "name": name, "deleted": True}
