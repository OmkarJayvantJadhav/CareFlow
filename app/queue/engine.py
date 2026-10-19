"""Live OPD queue (FR-21 – FR-23, FR-27, FR-28). Deterministic; every write is audited.

Every function takes an optional ``now`` so the simulator can replay a whole day.
Positions are recomputed after every queue event.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    MERGE_RULES,
    WAITING_ENTRY_STATUSES,
    Appointment,
    Doctor,
    Patient,
    QueueEntry,
    QueueEvent,
    QueueSession,
    Slot,
)
from app.queue.merge import QueueItem, merge_order
from app.queue.predictions import latest_estimate, refresh_predictions
from app.safety.privacy import mask_payload, mask_phone_number
from app.timeutil import at, resolve_now, to_ist
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.notify import notify
from app.tools.permissions import Actor, can_manage_patient, linked_patient_ids, require_role
from app.tools.serialize import entry_dict

DOCTOR_EVENTS = ("break", "delay", "emergency", "resume", "unavailable")
MAX_PRIORITY = 3


# --------------------------------------------------------------------------- sessions


def get_or_create_session(db: Session, doctor_id: int, day: date, merge_rule: str | None = None) -> QueueSession:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    if day.isoweekday() not in doctor.opd_days:
        raise ToolError("VALIDATION_ERROR", f"{doctor.name} has no OPD on {day:%A}.")
    rule = merge_rule or get_settings().queue_merge_rule
    if rule not in MERGE_RULES:
        raise ToolError("VALIDATION_ERROR", f"Unknown merge rule '{rule}'.")
    db.execute(
        insert(QueueSession)
        .values(
            doctor_id=doctor_id, date=day, merge_rule=rule, status="open", doctor_status="available", delay_minutes=0
        )
        .on_conflict_do_nothing(constraint="uq_queue_session_doctor_date")
    )
    return _lock_session(db, doctor_id=doctor_id, day=day)


def _lock_session(
    db: Session, session_id: int | None = None, doctor_id: int | None = None, day: date | None = None
) -> QueueSession:
    query = select(QueueSession).with_for_update().execution_options(populate_existing=True)
    if session_id is not None:
        query = query.where(QueueSession.id == session_id)
    else:
        query = query.where(QueueSession.doctor_id == doctor_id, QueueSession.date == day)
    session = db.scalars(query).first()
    if session is None:
        raise ToolError("NOT_FOUND", "Queue session not found.")
    return session


def _require_open(session: QueueSession) -> None:
    if session.status != "open" or session.doctor_status == "unavailable":
        raise ToolError("INVALID_STATE", "This doctor's queue is closed for today.")


def _event(db: Session, session: QueueSession, type_: str, now: datetime, **payload) -> None:
    db.add(QueueEvent(session_id=session.id, type=type_, payload=mask_payload(payload), at=now))


def _lock_entry(db: Session, entry_id: int) -> tuple[QueueEntry, QueueSession]:
    """Lock the entry's session first, then the entry: every queue write takes
    locks in the order session -> entries, so concurrent staff actions cannot deadlock."""
    session_id = db.scalar(select(QueueEntry.session_id).where(QueueEntry.id == entry_id))
    if session_id is None:
        raise ToolError("NOT_FOUND", f"Queue entry {entry_id} does not exist.")
    session = _lock_session(db, session_id=session_id)
    entry = db.scalars(
        select(QueueEntry).where(QueueEntry.id == entry_id).with_for_update().execution_options(populate_existing=True)
    ).one()
    return entry, session


def _next_token(db: Session, session: QueueSession, prefix: str) -> str:
    count = db.scalar(
        select(func.count())
        .select_from(QueueEntry)
        .where(QueueEntry.session_id == session.id, QueueEntry.token.startswith(prefix))
    )
    return f"{prefix}{count + 1:02d}"


def _auto_resume(db: Session, session: QueueSession, now: datetime) -> None:
    """A break, delay or emergency ends on its own once busy_until has passed."""
    if session.doctor_status in ("on_break", "delayed") and session.busy_until and session.busy_until <= now:
        session.doctor_status = "available"
        session.busy_until = None
        session.delay_minutes = 0
        _event(db, session, "resume", now, auto=True)


def projection_start(session: QueueSession, now: datetime) -> datetime:
    """Where the merge rule's projection of the doctor's day starts: now, but not before OPD opens.

    Breaks, delays and emergencies are deliberately ignored here so that they never
    reorder the queue (TC-10); the wait estimates add the doctor's unavailability instead.
    """
    return max(now, at(session.date, session.doctor.department.opd_start))


def ordered_waiting(db: Session, session: QueueSession, now: datetime) -> list[QueueEntry]:
    """Waiting entries in the order the merge rule will call them."""
    waiting = list(
        db.scalars(select(QueueEntry).where(QueueEntry.session_id == session.id, QueueEntry.status == "waiting"))
    )
    by_id = {e.id: e for e in waiting}
    items = [
        QueueItem(
            entry_id=e.id,
            kind=e.kind,
            checked_in_at=e.checked_in_at,
            scheduled_at=e.scheduled_at,
            requeued_at=e.requeued_at,
            priority=e.priority,
        )
        for e in waiting
    ]
    order = merge_order(items, session.merge_rule, projection_start(session, now), session.doctor.slot_minutes)
    return [by_id[i] for i in order]


def recompute_positions(db: Session, session: QueueSession, now: datetime) -> list[QueueEntry]:
    db.flush()
    ordered = ordered_waiting(db, session, now)
    for position, entry in enumerate(ordered, start=1):
        entry.position = position
    for entry in db.scalars(
        select(QueueEntry).where(QueueEntry.session_id == session.id, QueueEntry.status != "waiting")
    ):
        entry.position = None
    db.flush()
    return ordered


def _after_event(db: Session, session: QueueSession, now: datetime) -> None:
    """FR-23/FR-25: positions and wait predictions are recomputed after every queue event."""
    recompute_positions(db, session, now)
    refresh_predictions(db, session, now)


# --------------------------------------------------------------------------- arrivals


def _in_queue(db: Session, session: QueueSession, patient_id: int) -> bool:
    return (
        db.scalars(
            select(QueueEntry.id).where(
                QueueEntry.session_id == session.id,
                QueueEntry.patient_id == patient_id,
                QueueEntry.status.in_((*WAITING_ENTRY_STATUSES, "in_consultation", "missed")),
            )
        ).first()
        is not None
    )


@write_tool("check_in")
def check_in(db: Session, actor: Actor, appointment_id: int, now: datetime | None = None) -> dict:
    """A booked patient arrives (staff at the desk, or the patient/caregiver themselves)."""
    now = resolve_now(now)
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise ToolError("NOT_FOUND", f"Appointment {appointment_id} does not exist.")
    if not can_manage_patient(db, actor, appt.patient_id):
        raise ToolError("FORBIDDEN", "You are not allowed to check in this patient.")
    if appt.appt_date != now.date():
        raise ToolError("VALIDATION_ERROR", "Check-in is only possible on the day of the appointment.")
    # Lock order: session, then appointment (the same order as doctor-unavailable handling).
    session = get_or_create_session(db, appt.doctor_id, appt.appt_date)
    appt = db.scalars(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    _require_open(session)
    if appt.status not in ACTIVE_APPOINTMENT_STATUSES:
        raise ToolError("INVALID_STATE", f"This appointment is {appt.status} and cannot be checked in.")
    if db.scalars(select(QueueEntry.id).where(QueueEntry.appointment_id == appt.id)).first() is not None:
        raise ToolError("ALREADY_CHECKED_IN", "This appointment is already checked in.")
    if _in_queue(db, session, appt.patient_id):
        raise ToolError("ALREADY_CHECKED_IN", "This patient is already in this doctor's queue.")
    entry = QueueEntry(
        session_id=session.id,
        appointment_id=appt.id,
        patient_id=appt.patient_id,
        token=_next_token(db, session, "B"),
        kind="booked",
        scheduled_at=appt.slot.start_at,
        checked_in_at=now,
        status="waiting",
        priority=0,
    )
    db.add(entry)
    db.flush()
    _event(db, session, "check_in", now, entry_id=entry.id, token=entry.token)
    _after_event(db, session, now)
    return entry_dict(entry)


@write_tool("register_walk_in")
def register_walk_in(
    db: Session,
    actor: Actor,
    doctor_id: int,
    patient_id: int | None = None,
    name: str | None = None,
    birth_year: int | None = None,
    phone: str | None = None,
    language: str = "en",
    now: datetime | None = None,
) -> dict:
    """FR-21: staff register a walk-in (an existing patient or a new record) and issue a token."""
    now = resolve_now(now)
    require_role(actor, "staff")
    session = get_or_create_session(db, doctor_id, now.date())
    _require_open(session)
    if patient_id is None:
        if not name or not birth_year or not phone:
            raise ToolError("VALIDATION_ERROR", "A new walk-in needs a name, birth year and phone number.")
        try:
            masked = mask_phone_number(phone)
        except ValueError:
            raise ToolError("VALIDATION_ERROR", "The phone number must be a 10-digit mobile number.") from None
        if not 1900 <= birth_year <= now.year:
            raise ToolError("VALIDATION_ERROR", "The birth year is not valid.")
        if language not in ("en", "hi", "mr"):
            raise ToolError("VALIDATION_ERROR", "Language must be en, hi or mr.")
        patient = Patient(synthetic_name=name, birth_year=birth_year, phone_masked=masked, preferred_language=language)
        db.add(patient)
        db.flush()
    else:
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise ToolError("NOT_FOUND", f"Patient {patient_id} does not exist.")
    if _in_queue(db, session, patient.id):
        raise ToolError("ALREADY_CHECKED_IN", "This patient is already in this doctor's queue.")
    entry = QueueEntry(
        session_id=session.id,
        patient_id=patient.id,
        token=_next_token(db, session, "W"),
        kind="walk_in",
        checked_in_at=now,
        status="waiting",
        priority=0,
    )
    db.add(entry)
    db.flush()
    _event(db, session, "walk_in", now, entry_id=entry.id, token=entry.token)
    _after_event(db, session, now)
    return entry_dict(entry)


# --------------------------------------------------------------------------- consultations


@write_tool("call_next")
def call_next(db: Session, actor: Actor, session_id: int, now: datetime | None = None) -> dict | None:
    """Call the next patient by the merge rule. Returns None when nobody is waiting."""
    now = resolve_now(now)
    require_role(actor, "staff")
    session = _lock_session(db, session_id=session_id)
    _require_open(session)
    _auto_resume(db, session, now)
    if session.busy_until and session.busy_until > now:
        raise ToolError("INVALID_STATE", f"The doctor is not available until {to_ist(session.busy_until):%H:%M}.")
    busy = db.scalars(
        select(QueueEntry.id).where(
            QueueEntry.session_id == session.id, QueueEntry.status.in_(("called", "in_consultation"))
        )
    ).first()
    if busy is not None:
        raise ToolError("INVALID_STATE", "Finish the current patient before calling the next one.")
    ordered = ordered_waiting(db, session, now)
    if not ordered:
        return None
    entry = ordered[0]
    entry.status = "called"
    entry.called_at = now
    if session.started_at is None:
        session.started_at = now
    _event(db, session, "call", now, entry_id=entry.id, token=entry.token)
    _after_event(db, session, now)
    return entry_dict(entry)


@write_tool("start_consultation")
def start_consultation(db: Session, actor: Actor, entry_id: int, now: datetime | None = None) -> dict:
    now = resolve_now(now)
    require_role(actor, "staff")
    entry, session = _lock_entry(db, entry_id)
    if entry.status != "called":
        raise ToolError("INVALID_STATE", "Only a called patient can start a consultation.")
    entry.status = "in_consultation"
    entry.consult_start = now
    _event(db, session, "consult_start", now, entry_id=entry.id)
    _after_event(db, session, now)
    return entry_dict(entry)


@write_tool("end_consultation")
def end_consultation(db: Session, actor: Actor, entry_id: int, now: datetime | None = None) -> dict:
    now = resolve_now(now)
    require_role(actor, "staff")
    entry, session = _lock_entry(db, entry_id)
    if entry.status != "in_consultation":
        raise ToolError("INVALID_STATE", "This patient is not in a consultation.")
    entry.status = "done"
    entry.consult_end = now
    if entry.appointment is not None:
        entry.appointment.status = "completed"
        entry.appointment.updated_at = now
    _event(db, session, "consult_end", now, entry_id=entry.id)
    _after_event(db, session, now)
    return entry_dict(entry)


@write_tool("mark_missed_turn")
def mark_missed_turn(db: Session, actor: Actor, entry_id: int, now: datetime | None = None) -> dict:
    """A called patient did not come in; they can return later (FR-23)."""
    now = resolve_now(now)
    require_role(actor, "staff")
    entry, session = _lock_entry(db, entry_id)
    if entry.status != "called":
        raise ToolError("INVALID_STATE", "Only a called patient can miss their turn.")
    entry.status = "missed"
    _event(db, session, "missed_turn", now, entry_id=entry.id)
    _after_event(db, session, now)
    return entry_dict(entry)


@write_tool("mark_returned")
def mark_returned(db: Session, actor: Actor, entry_id: int, now: datetime | None = None) -> dict:
    """A patient who missed their turn is back; they rejoin by return time."""
    now = resolve_now(now)
    require_role(actor, "staff")
    entry, session = _lock_entry(db, entry_id)
    _require_open(session)
    if entry.status != "missed":
        raise ToolError("INVALID_STATE", "Only a patient who missed their turn can return.")
    entry.status = "waiting"
    entry.requeued_at = now
    entry.called_at = None
    _event(db, session, "return", now, entry_id=entry.id)
    _after_event(db, session, now)
    return entry_dict(entry)


@write_tool("set_priority")
def set_priority(db: Session, actor: Actor, entry_id: int, priority: int, now: datetime | None = None) -> dict:
    """FR-28: staff only; the change is audited by the write_tool wrapper."""
    now = resolve_now(now)
    require_role(actor, "staff")
    if not 0 <= priority <= MAX_PRIORITY:
        raise ToolError("VALIDATION_ERROR", f"Priority must be between 0 and {MAX_PRIORITY}.")
    entry, session = _lock_entry(db, entry_id)
    _require_open(session)
    if entry.status != "waiting":
        raise ToolError("INVALID_STATE", "Priority can only be changed for a waiting patient.")
    previous = entry.priority
    entry.priority = priority
    _event(db, session, "priority", now, entry_id=entry.id, previous=previous, priority=priority)
    _after_event(db, session, now)
    return entry_dict(entry)


# --------------------------------------------------------------------------- doctor status


@write_tool("record_doctor_event")
def record_doctor_event(
    db: Session,
    actor: Actor,
    session_id: int,
    type: str,
    minutes: int | None = None,
    reason: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Break, delay, emergency interruption, resume or unavailability (FR-23, FR-27)."""
    now = resolve_now(now)
    require_role(actor, "staff")
    if type not in DOCTOR_EVENTS:
        raise ToolError("VALIDATION_ERROR", f"Event type must be one of {', '.join(DOCTOR_EVENTS)}.")
    session = _lock_session(db, session_id=session_id)
    _require_open(session)
    if type in ("break", "delay", "emergency"):
        if minutes is None or not 1 <= minutes <= 240:
            raise ToolError("VALIDATION_ERROR", "Give the expected length in minutes (1-240).")
        busy_until = now + timedelta(minutes=minutes)
        session.busy_until = max(busy_until, session.busy_until) if session.busy_until else busy_until
        session.doctor_status = "on_break" if type == "break" else "delayed"
        session.delay_minutes = minutes if type != "break" else 0
        _event(db, session, type, now, minutes=minutes, reason=reason)
    elif type == "resume":
        session.doctor_status = "available"
        session.busy_until = None
        session.delay_minutes = 0
        _event(db, session, "resume", now, reason=reason)
    else:
        _event(db, session, "unavailable", now, reason=reason)
        affected = _handle_unavailable(db, session, now)
        return {"session_id": session.id, "doctor_status": session.doctor_status, "affected": affected}
    _after_event(db, session, now)
    return {
        "session_id": session.id,
        "doctor_status": session.doctor_status,
        "busy_until": session.busy_until.isoformat() if session.busy_until else None,
    }


def _handle_unavailable(db: Session, session: QueueSession, now: datetime) -> list[dict]:
    """FR-27: close the queue, release today's remaining bookings for rebooking and notify everyone."""
    doctor = session.doctor
    session.doctor_status = "unavailable"
    session.status = "closed"
    session.closed_at = now
    affected: dict[int, dict] = {}

    for entry in db.scalars(
        select(QueueEntry).where(
            QueueEntry.session_id == session.id, QueueEntry.status.in_((*WAITING_ENTRY_STATUSES, "missed"))
        )
    ):
        entry.status = "closed"
        entry.position = None
        affected[entry.patient_id] = {
            "patient_id": entry.patient_id,
            "entry_id": entry.id,
            "appointment_id": entry.appointment_id,
        }

    day_start, day_end = at(session.date, time.min), at(session.date + timedelta(days=1), time.min)
    for appt in db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == doctor.id,
            Appointment.appt_date == session.date,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        )
    ):
        in_consult = db.scalars(
            select(QueueEntry.id).where(QueueEntry.appointment_id == appt.id, QueueEntry.status == "in_consultation")
        ).first()
        if in_consult is not None:
            continue
        appt.status = "displaced"
        appt.updated_at = now
        affected.setdefault(appt.patient_id, {"patient_id": appt.patient_id, "entry_id": None})
        affected[appt.patient_id]["appointment_id"] = appt.id

    for slot in db.scalars(
        select(Slot).where(
            Slot.doctor_id == doctor.id, Slot.start_at >= day_start, Slot.start_at < day_end, Slot.status != "blocked"
        )
    ):
        slot.status = "blocked"
        slot.held_for_patient_id = None
        slot.held_until = None

    for item in affected.values():
        item["notification_id"] = notify(
            db,
            item["patient_id"],
            f"{doctor.name} is unavailable today ({session.date:%d %b}). We are sorry for the inconvenience. "
            "Reply to CareFlow to choose a new slot; your rescheduling is free of charge.",
            now,
        ).id
    db.flush()
    return list(affected.values())


@write_tool("close_session")
def close_session(db: Session, actor: Actor, session_id: int, now: datetime | None = None) -> dict:
    """End of OPD: booked patients who never arrived (or never came back) become no-shows."""
    now = resolve_now(now)
    require_role(actor, "staff")
    session = _lock_session(db, session_id=session_id)
    if session.status == "closed":
        raise ToolError("INVALID_STATE", "This session is already closed.")
    active = db.scalars(
        select(QueueEntry.id).where(
            QueueEntry.session_id == session.id, QueueEntry.status.in_((*WAITING_ENTRY_STATUSES, "in_consultation"))
        )
    ).first()
    if active is not None:
        raise ToolError("INVALID_STATE", "Patients are still waiting; the session cannot be closed yet.")
    no_shows = 0
    for entry in db.scalars(
        select(QueueEntry).where(QueueEntry.session_id == session.id, QueueEntry.status == "missed")
    ):
        entry.status = "closed"
        if entry.appointment is not None:
            entry.appointment.status = "no_show"
            entry.appointment.updated_at = now
            no_shows += 1
    checked_in = select(QueueEntry.appointment_id).where(QueueEntry.appointment_id.is_not(None))
    for appt in db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == session.doctor_id,
            Appointment.appt_date == session.date,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Appointment.id.not_in(checked_in),
        )
    ):
        appt.status = "no_show"
        appt.updated_at = now
        no_shows += 1
    session.status = "closed"
    session.closed_at = now
    _event(db, session, "session_closed", now, no_shows=no_shows)
    db.flush()
    return {"session_id": session.id, "status": "closed", "no_shows": no_shows}


# --------------------------------------------------------------------------- reads


def get_queue_status(db: Session, actor: Actor, entry_id: int, now: datetime | None = None) -> dict:
    """Position and people ahead for one entry (owner, linked caregiver or staff)."""
    now = resolve_now(now)
    entry = db.get(QueueEntry, entry_id)
    if entry is None:
        raise ToolError("NOT_FOUND", f"Queue entry {entry_id} does not exist.")
    if not can_manage_patient(db, actor, entry.patient_id):
        raise ToolError("FORBIDDEN", "You are not allowed to view this queue entry.")
    session = entry.session
    in_room = db.scalar(
        select(func.count())
        .select_from(QueueEntry)
        .where(QueueEntry.session_id == session.id, QueueEntry.status.in_(("called", "in_consultation")))
    )
    ahead = None
    if entry.status == "waiting" and entry.position is not None:
        ahead = entry.position - 1 + in_room
    return {
        **entry_dict(entry),
        "ahead": ahead,
        "estimate": latest_estimate(db, entry.id, now) if entry.status == "waiting" else None,
        "doctor_id": session.doctor_id,
        "doctor_name": session.doctor.name,
        "doctor_status": session.doctor_status,
        "delay_minutes": session.delay_minutes,
        "busy_until": session.busy_until.isoformat() if session.busy_until else None,
    }


def session_snapshot(db: Session, session_id: int) -> dict:
    session = db.get(QueueSession, session_id)
    if session is None:
        raise ToolError("NOT_FOUND", "Queue session not found.")
    entries = sorted(
        db.scalars(select(QueueEntry).where(QueueEntry.session_id == session_id)),
        key=lambda e: (e.position is None, e.position or 0, e.id),
    )
    return {
        "session_id": session.id,
        "doctor_id": session.doctor_id,
        "date": session.date.isoformat(),
        "merge_rule": session.merge_rule,
        "status": session.status,
        "doctor_status": session.doctor_status,
        "entries": [entry_dict(e) for e in entries],
    }


def active_entries_for(db: Session, actor: Actor, now: datetime | None = None) -> list[dict]:
    """Today's open queue entries for a patient or a caregiver's linked patients."""
    now = resolve_now(now)
    if actor.role == "patient":
        patient_ids = [actor.patient_id]
    elif actor.role == "caregiver":
        patient_ids = sorted(linked_patient_ids(db, actor))
    else:
        return []
    entries = db.scalars(
        select(QueueEntry)
        .join(QueueSession, QueueSession.id == QueueEntry.session_id)
        .where(
            QueueSession.date == now.date(),
            QueueEntry.patient_id.in_(patient_ids),
            QueueEntry.status.in_(("waiting", "called", "in_consultation", "missed")),
        )
        .order_by(QueueEntry.id)
    ).all()
    return [{**get_queue_status(db, actor, e.id, now), "patient_name": e.patient.synthetic_name} for e in entries]
