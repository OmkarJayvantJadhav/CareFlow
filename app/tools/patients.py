"""Patient records for staff, and a patient's own data (phase 7C).

Staff find a patient by name, phone number or record number, see the record and correct it; every change
is audited. The full phone number is shown only through an audited action. On request, an admin (or the
patient themself) erases a patient's personal details: the name, phone number, extra registration answers,
messages and sign-in go; the anonymous visit history stays for the hospital's statistics. A patient can also
download everything CareFlow holds about them.
"""

import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    ACTIVE_WAITLIST_STATUSES,
    LANGUAGES,
    Appointment,
    AppUser,
    CaregiverLink,
    CaregiverRequest,
    Conversation,
    HandoffTicket,
    Notification,
    Patient,
    PatientFieldValue,
    QueueEntry,
    QueueSession,
    RegistrationField,
    Slot,
    WaitingList,
)
from app.safety.pii import (
    decrypt_email,
    decrypt_phone,
    display_phone,
    normalize_mobile,
    phone_index,
    set_contact_by,
    set_email,
    set_phone,
)
from app.timeutil import iso, resolve_now, to_ist
from app.tools import registration
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.permissions import Actor, require_role

MAX_FOUND = 30
ERASED_NAME = "Erased patient"
LIVE_ENTRY_STATUSES = ("waiting", "called", "in_consultation", "missed")


def _patient(db: Session, patient_id: int, for_update: bool = False) -> Patient:
    query = select(Patient).where(Patient.id == patient_id)
    patient = db.scalars(query.with_for_update() if for_update else query).first()
    if patient is None:
        raise ToolError("NOT_FOUND", "There is no such patient.")
    return patient


def _live(patient: Patient) -> Patient:
    if patient.erased_at is not None:
        raise ToolError("INVALID_STATE", "This patient's details were erased on request.")
    return patient


def _summary(db: Session, p: Patient, year: int) -> dict:
    username = db.scalar(select(AppUser.username).where(AppUser.patient_id == p.id, AppUser.active))
    return {
        "patient_id": p.id,
        "name": p.name,
        "birth_year": p.birth_year,
        "phone_masked": p.phone_masked,
        "language": p.preferred_language,
        "categories": registration.categories(p, year),
        "username": username,
        "erased": p.erased_at is not None,
    }


def search_patients(db: Session, actor: Actor, q: str, now: datetime | None = None) -> dict:
    """By record number ("#123" or "123"), by phone number (exact), or by name (every word)."""
    now = resolve_now(now)
    require_role(actor, "staff", "admin")
    text = " ".join((q or "").split())
    if len(text) < 2:
        raise ToolError("VALIDATION_ERROR", "Type at least two letters or digits.")
    query = select(Patient).where(Patient.erased_at.is_(None))
    digits = re.sub(r"\D", "", text)
    if re.fullmatch(r"#?\d{1,7}", text):
        query = query.where(Patient.id == int(digits))
    elif len(digits) >= 10:
        try:
            wanted = normalize_mobile(text)
        except ToolError:
            return {"patients": [], "more": False}
        query = query.where(Patient.phone_hash == phone_index(wanted))
    else:
        for word in text.casefold().split():
            query = query.where(func.lower(Patient.name).contains(word, autoescape=True))
    found = list(db.scalars(query.order_by(Patient.name, Patient.id).limit(MAX_FOUND + 1)))
    return {"patients": [_summary(db, p, now.year) for p in found[:MAX_FOUND]], "more": len(found) > MAX_FOUND}


def _visits(db: Session, patient_id: int, now: datetime) -> tuple[list[dict], list[dict]]:
    upcoming, past = [], []
    for a in db.scalars(
        select(Appointment).where(Appointment.patient_id == patient_id).order_by(Appointment.appt_date.desc())
    ):
        start = to_ist(a.slot.start_at)
        row = {
            "appointment_id": a.id,
            "date": start.date().isoformat(),
            "time": start.strftime("%H:%M"),
            "doctor_name": a.doctor.name,
            "department": a.doctor.department.name,
            "status": a.status,
        }
        if a.status in ACTIVE_APPOINTMENT_STATUSES and start >= now:
            upcoming.append(row)
        elif len(past) < 10:
            past.append(row)
    upcoming.reverse()
    return upcoming, past


def patient_record(db: Session, actor: Actor, patient_id: int, now: datetime | None = None) -> dict:
    now = resolve_now(now)
    require_role(actor, "staff", "admin")
    p = _patient(db, patient_id)
    upcoming, past = _visits(db, p.id, now)
    caregivers = db.execute(
        select(AppUser.display_name, AppUser.username)
        .join(CaregiverLink, CaregiverLink.caregiver_user_id == AppUser.id)
        .where(CaregiverLink.patient_id == p.id, CaregiverLink.verified)
    ).all()
    return {
        **_summary(db, p, now.year),
        "pregnant": p.pregnant,
        "disability": p.disability,
        "has_full_phone": p.phone_encrypted is not None,
        "email_masked": p.email_masked,
        "contact_by": p.contact_by,
        "erased_at": iso(p.erased_at) if p.erased_at else None,
        "answers": registration.patient_answers(db, p.id),
        "consent": registration.consent_state(db, p.id),
        "caregivers": [{"name": n, "username": u} for n, u in caregivers],
        "upcoming": upcoming,
        "past": past,
    }


@write_tool("update_patient")
def update_patient(
    db: Session,
    actor: Actor,
    patient_id: int,
    name: str | None = None,
    birth_year: int | None = None,
    phone: str | None = None,
    language: str | None = None,
    pregnant: bool | None = None,
    disability: bool | None = None,
    answers: dict | None = None,
    email: str | None = None,
    contact_by: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Correct a patient's details (the desk, with the patient). The patient's own account name follows."""
    now = resolve_now(now)
    require_role(actor, "staff", "admin")
    p = _live(_patient(db, patient_id, for_update=True))
    if name is not None:
        clean = " ".join(name.split())
        if not 2 <= len(clean) <= 120:
            raise ToolError("VALIDATION_ERROR", "Give the patient's name (2–120 characters).")
        p.name = clean
        for user in db.scalars(select(AppUser).where(AppUser.patient_id == p.id)):
            user.display_name = clean
    if birth_year is not None:
        if not 1900 <= birth_year <= now.year:
            raise ToolError("VALIDATION_ERROR", f"Birth year must be between 1900 and {now.year}.")
        p.birth_year = birth_year
    if phone is not None:
        set_phone(p, phone)
    if email is not None:
        set_email(p, email)
    if contact_by is not None:
        set_contact_by(p, contact_by)
    if language is not None:
        if language not in LANGUAGES:
            raise ToolError("VALIDATION_ERROR", "Language must be English, Hindi or Marathi.")
        p.preferred_language = language
    if pregnant is not None:
        p.pregnant = pregnant
    if disability is not None:
        p.disability = disability
    if answers is not None:
        cleaned = registration.clean_answers(db, answers)
        active = set(db.scalars(select(RegistrationField.id).where(RegistrationField.active)))
        for row in db.scalars(select(PatientFieldValue).where(PatientFieldValue.patient_id == p.id)):
            if row.field_id in active and row.field_id not in cleaned:
                db.delete(row)  # an optional answer cleared
        registration.save_answers(db, p.id, cleaned)
    db.flush()
    return patient_record(db, actor, p.id, now)


@write_tool("reveal_patient_phone")
def reveal_phone(db: Session, actor: Actor, patient_id: int, now: datetime | None = None) -> dict:
    """The full number, for calling the patient. Each look is audited (the audit row keeps it masked)."""
    resolve_now(now)
    require_role(actor, "staff", "admin")
    p = _live(_patient(db, patient_id))
    digits = decrypt_phone(p.phone_encrypted)
    if digits is None:
        raise ToolError(
            "NOT_FOUND",
            "Only the masked number is on file for this patient. Ask for their number and update the record.",
        )
    return {"patient_id": p.id, "phone": display_phone(digits)}


def _release_waiting_list(db: Session, patient_id: int, now: datetime) -> int:
    from app.tools.waiting_list import offer_freed_slot

    closed = 0
    for entry in db.scalars(
        select(WaitingList).where(
            WaitingList.patient_id == patient_id, WaitingList.status.in_(ACTIVE_WAITLIST_STATUSES)
        )
    ):
        entry.status = "cancelled"
        closed += 1
        held = db.get(Slot, entry.offered_slot_id) if entry.offered_slot_id else None
        if held is not None and held.held_for_patient_id == patient_id:
            held.held_for_patient_id, held.held_until = None, None
            db.flush()
            offer_freed_slot(db, held, now, exclude_patient_ids={patient_id})
    return closed


@write_tool("erase_patient")
def erase_patient(db: Session, actor: Actor, patient_id: int, reason: str = "", now: datetime | None = None) -> dict:
    """Erase a patient's personal details on their request: by an admin, or by the patient themself.

    Future appointments are cancelled (their slots are offered to the waiting list), waiting-list requests
    closed, caregiver access removed, messages, answers and the sign-in deleted, and the record kept only as
    "Erased patient" with the birth decade and language, so past visits still count in the statistics.
    """
    from app.tools.booking import _free_slot

    now = resolve_now(now)
    if not (actor.role == "admin" or (actor.role == "patient" and actor.patient_id == patient_id)):
        raise ToolError("FORBIDDEN", "Only an admin, or the patient themself, can erase a patient's details.")
    p = _live(_patient(db, patient_id, for_update=True))
    live = db.scalar(
        select(QueueEntry.id)
        .join(QueueSession)
        .where(
            QueueEntry.patient_id == p.id,
            QueueSession.date == now.date(),
            QueueEntry.status.in_(LIVE_ENTRY_STATUSES),
        )
        .limit(1)
    )
    if live is not None:
        raise ToolError(
            "INVALID_STATE", "This patient is in a queue today. Finish the visit or record that they left first."
        )

    cancelled = 0
    for appt in db.scalars(
        select(Appointment)
        .where(Appointment.patient_id == p.id, Appointment.status.in_((*ACTIVE_APPOINTMENT_STATUSES, "displaced")))
        .with_for_update()
    ):
        if to_ist(appt.slot.start_at) < now:
            continue
        appt.status, appt.updated_at = "cancelled", now
        _free_slot(db, appt.slot, now)
        cancelled += 1
    closed = _release_waiting_list(db, p.id, now)

    users = list(db.scalars(select(AppUser).where(AppUser.patient_id == p.id)))
    for model, column in (
        (CaregiverLink, CaregiverLink.patient_id),
        (CaregiverRequest, CaregiverRequest.patient_id),
        (PatientFieldValue, PatientFieldValue.patient_id),
        (Notification, Notification.patient_id),
    ):
        for row in db.scalars(select(model).where(column == p.id)):
            db.delete(row)
    user_ids = [u.id for u in users]
    if user_ids:
        for conv in db.scalars(select(Conversation).where(Conversation.user_id.in_(user_ids))):
            db.delete(conv)
        for ticket in db.scalars(select(HandoffTicket).where(HandoffTicket.user_id.in_(user_ids))):
            ticket.reason = "[erased on request]"
    db.flush()
    for user in users:  # the sign-in goes; the row stays because the audit log refers to it
        user.username = f"erased-{user.id}"
        user.display_name = ERASED_NAME
        user.password_hash = None
        user.active = False
        user.self_registered = False
        user.credentials_version += 1
    p.name = ERASED_NAME
    p.birth_year = p.birth_year - p.birth_year % 10  # keep only the decade, for age-group statistics
    p.phone_masked, p.phone_encrypted, p.phone_hash = "", None, None
    p.email_masked, p.email_encrypted, p.contact_by = "", None, "app"
    p.pregnant = p.disability = False
    p.erased_at = now
    db.flush()
    return {
        "patient_id": p.id,
        "erased": True,
        "appointments_cancelled": cancelled,
        "waiting_list_closed": closed,
        "reason": " ".join((reason or "").split())[:200],
    }


@write_tool("erase_own_account")
def erase_caregiver_account(db: Session, actor: Actor, now: datetime | None = None) -> dict:
    """A caregiver's own account: their access, requests, messages and sign-in go."""
    resolve_now(now)
    require_role(actor, "caregiver")
    user = db.get(AppUser, actor.user_id)
    for model, column in (
        (CaregiverLink, CaregiverLink.caregiver_user_id),
        (CaregiverRequest, CaregiverRequest.caregiver_user_id),
        (Conversation, Conversation.user_id),
    ):
        for row in db.scalars(select(model).where(column == user.id)):
            db.delete(row)
    for ticket in db.scalars(select(HandoffTicket).where(HandoffTicket.user_id == user.id)):
        ticket.reason = "[erased on request]"
    user.username, user.display_name, user.password_hash = f"erased-{user.id}", "Erased caregiver", None
    user.active, user.self_registered = False, False
    user.credentials_version += 1
    db.flush()
    return {"erased": True}


def export_own_data(db: Session, actor: Actor, now: datetime | None = None) -> dict:
    """Everything CareFlow holds about the signed-in patient (or caregiver), as data they can keep."""
    now = resolve_now(now)
    user = db.get(AppUser, actor.user_id)
    out: dict = {
        "exported_at": iso(now),
        "account": {
            "username": user.username,
            "name": user.display_name,
            "role": user.role,
            "created_at": iso(user.created_at) if user.created_at else None,
        },
    }
    conversations = db.scalars(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at)
    )
    out["conversations"] = [
        {
            "started": iso(c.created_at),
            "messages": [
                {"role": m.get("role"), "text": m.get("content")}
                for m in (c.history or [])
                if m.get("role") in ("user", "assistant") and m.get("content")
            ],
        }
        for c in conversations
    ]
    if user.role == "caregiver":
        out["caregiver_of"] = [
            name
            for (name,) in db.execute(
                select(Patient.name)
                .join(CaregiverLink, CaregiverLink.patient_id == Patient.id)
                .where(CaregiverLink.caregiver_user_id == user.id, CaregiverLink.verified)
            )
        ]
        return out
    require_role(actor, "patient")
    p = _patient(db, actor.patient_id)
    digits = decrypt_phone(p.phone_encrypted)
    all_visits = []
    for a in db.scalars(select(Appointment).where(Appointment.patient_id == p.id).order_by(Appointment.appt_date)):
        start = to_ist(a.slot.start_at)
        all_visits.append(
            {
                "date": start.date().isoformat(),
                "time": start.strftime("%H:%M"),
                "doctor": a.doctor.name,
                "department": a.doctor.department.name,
                "status": a.status,
            }  # fmt: skip
        )
    out["patient"] = {
        "name": p.name,
        "birth_year": p.birth_year,
        "phone": display_phone(digits) if digits else p.phone_masked,
        "email": decrypt_email(p.email_encrypted) or p.email_masked,
        "messages_by": p.contact_by,
        "language": p.preferred_language,
        "pregnant": p.pregnant,
        "disability": p.disability,
        "registration_answers": registration.patient_answers(db, p.id),
    }
    out["appointments"] = all_visits
    out["notifications"] = [
        {"at": iso(n.sent_at), "message": n.message, "sent_by": n.delivered_via if n.delivery == "sent" else None}
        for n in db.scalars(select(Notification).where(Notification.patient_id == p.id).order_by(Notification.sent_at))
    ]
    out["consent_history"] = registration.consent_history(db, p.id)
    out["caregivers"] = [
        name
        for (name,) in db.execute(
            select(AppUser.display_name)
            .join(CaregiverLink, CaregiverLink.caregiver_user_id == AppUser.id)
            .where(CaregiverLink.patient_id == p.id, CaregiverLink.verified)
        )
    ]
    out["queue_visits"] = [
        {"date": s.date.isoformat(), "token": e.token, "status": e.status}
        for e, s in db.execute(
            select(QueueEntry, QueueSession)
            .join(QueueSession, QueueSession.id == QueueEntry.session_id)
            .where(QueueEntry.patient_id == p.id)
            .order_by(QueueSession.date)
        )
    ]
    return out
