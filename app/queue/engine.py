"""Live OPD queue (FR-21 – FR-23, FR-27, FR-28, features 36 – 55). Deterministic; every write is audited.

Every function takes an optional ``now`` so the simulator can replay a whole day.
Positions are recomputed after every queue event.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select
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
    PriorityRequest,
    PriorityRule,
    QueueEntry,
    QueueEvent,
    QueueSession,
    Slot,
)
from app.queue.merge import QueueItem, effective_priority, merge_order
from app.queue.predictions import latest_estimate, refresh_predictions
from app.safety.privacy import mask_payload, mask_phone_number
from app.timeutil import at, resolve_now, to_ist
from app.tools import policy
from app.tools.audit import write_tool
from app.tools.calendar import leave_days
from app.tools.errors import ToolError
from app.tools.notify import notify
from app.tools.permissions import (
    Actor,
    can_manage_patient,
    linked_patient_ids,
    require_own_doctor,
    require_patient_access,
    require_queue_control,
    require_role,
)
from app.tools.registration import categories
from app.tools.serialize import entry_dict
from app.tools.timetable import holds_opd

DOCTOR_EVENTS = ("break", "delay", "emergency", "resume", "unavailable")
MAX_PRIORITY = 3
# Patients still in the hospital's care: they cannot join another queue at the same time.
ACTIVE_ENTRY_STATUSES = ("waiting", "called", "in_consultation", "missed")


# --------------------------------------------------------------------------- sessions


def get_or_create_session(db: Session, doctor_id: int, day: date, merge_rule: str | None = None) -> QueueSession:
    _ensure_session(db, doctor_id, day, merge_rule)
    return _lock_session(db, doctor_id=doctor_id, day=day)


def _ensure_session(db: Session, doctor_id: int, day: date, merge_rule: str | None = None) -> int:
    """Create the doctor's session for the day if it does not exist yet (without locking it); return its id."""
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    if not holds_opd(db, doctor, day):
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
    return db.scalar(select(QueueSession.id).where(QueueSession.doctor_id == doctor_id, QueueSession.date == day))


def _lock_sessions(db: Session, session_ids: list[int]) -> dict[int, QueueSession]:
    """Lock several sessions in id order, so two moves in opposite directions cannot deadlock."""
    return {sid: _lock_session(db, session_id=sid) for sid in sorted(set(session_ids))}


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
    start = projection_start(session, now)
    weights = priority_weights(db)
    items = [
        QueueItem(
            entry_id=e.id,
            kind=e.kind,
            checked_in_at=e.checked_in_at,
            scheduled_at=e.scheduled_at,
            requeued_at=e.requeued_at,
            priority=effective_priority(e.priority, categories(e.patient, now.year), weights, category_due(e, start)),
            transferred=e.transferred_from_id is not None,
        )
        for e in waiting
    ]
    order = merge_order(items, session.merge_rule, start, session.doctor.slot_minutes)
    return [by_id[i] for i in order]


def priority_weights(db: Session) -> dict[str, int]:
    """Category weights set by the admin (feature 51); a category without a row has no priority."""
    rules = db.scalars(select(PriorityRule).execution_options(populate_existing=True))
    return {r.category: r.weight for r in rules}


def category_due(entry: QueueEntry, start: datetime) -> bool:
    """Category priority applies to a booked patient only once their slot time has come."""
    return entry.kind == "walk_in" or entry.transferred_from_id is not None or entry.scheduled_at <= start


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


def reorder_session(db: Session, session_id: int, now: datetime) -> None:
    """Recompute a session's order and estimates after the priority rules change."""
    _after_event(db, _lock_session(db, session_id=session_id), now)


# --------------------------------------------------------------------------- arrivals


def _in_queue(db: Session, session: QueueSession, patient_id: int) -> bool:
    return (
        db.scalars(
            select(QueueEntry.id).where(
                QueueEntry.session_id == session.id,
                QueueEntry.patient_id == patient_id,
                QueueEntry.status.in_(ACTIVE_ENTRY_STATUSES),
            )
        ).first()
        is not None
    )


def _in_any_queue_today(db: Session, patient_id: int, day: date) -> bool:
    return (
        db.scalars(
            select(QueueEntry.id)
            .join(QueueSession, QueueSession.id == QueueEntry.session_id)
            .where(
                QueueSession.date == day,
                QueueEntry.patient_id == patient_id,
                QueueEntry.status.in_(ACTIVE_ENTRY_STATUSES),
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
    if actor.role in ("patient", "caregiver"):
        # Self check-in (features 24, 25): from an hour before the slot until 15 minutes after it starts.
        opens, closes = (
            appt.slot.start_at - policy.SELF_CHECK_IN_OPENS,
            appt.slot.start_at + policy.SELF_CHECK_IN_CLOSES,
        )
        if now < opens:
            raise ToolError(
                "POLICY_WINDOW", f"Online check-in opens at {to_ist(opens):%H:%M}, an hour before your appointment."
            )
        if now > closes:
            raise ToolError(
                "POLICY_WINDOW", "Online check-in has closed for this appointment; please go to the reception desk."
            )
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
        late_minutes=max(0, int((now - appt.slot.start_at).total_seconds() // 60)) or None,
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
    answers: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """FR-21: staff register a walk-in (an existing patient or a new record) and issue a token.

    An existing record is reused only while the patient allows it (feature 34); a new record gets the
    answers to the hospital's extra registration questions (feature 28)."""
    from app.tools import registration

    now = resolve_now(now)
    require_role(actor, "staff")
    session = get_or_create_session(db, doctor_id, now.date())
    _require_open(session)
    if patient_id is None:
        clean = registration.clean_answers(db, answers)
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
        registration.save_answers(db, patient.id, clean)
    else:
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise ToolError("NOT_FOUND", f"Patient {patient_id} does not exist.")
        registration.require_reuse_consent(db, patient.id)
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
    require_role(actor, "staff", "doctor")
    session = _lock_session(db, session_id=session_id)
    require_queue_control(actor, session.doctor_id)
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
    require_role(actor, "staff", "doctor")
    entry, session = _lock_entry(db, entry_id)
    require_queue_control(actor, session.doctor_id)
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
    require_role(actor, "staff", "doctor")
    entry, session = _lock_entry(db, entry_id)
    require_queue_control(actor, session.doctor_id)
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
    require_role(actor, "staff", "doctor")
    entry, session = _lock_entry(db, entry_id)
    require_queue_control(actor, session.doctor_id)
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
    require_role(actor, "staff", "doctor")
    entry, session = _lock_entry(db, entry_id)
    require_queue_control(actor, session.doctor_id)
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
    """Clinician-authorized priority (FR-28, feature 52): only the patient's own doctor sets it directly;
    the front desk asks with request_priority. The change is audited by the write_tool wrapper."""
    now = resolve_now(now)
    require_role(actor, "doctor")
    _check_priority(priority)
    entry, session = _lock_entry(db, entry_id)
    require_own_doctor(actor, session.doctor_id)
    _require_open(session)
    _apply_priority(db, session, entry, priority, now)
    return entry_dict(entry)


def _check_priority(priority: int) -> None:
    if not 0 <= priority <= MAX_PRIORITY:
        raise ToolError("VALIDATION_ERROR", f"Priority must be between 0 and {MAX_PRIORITY}.")


def _apply_priority(
    db: Session, session: QueueSession, entry: QueueEntry, priority: int, now: datetime, **payload
) -> None:
    if entry.status != "waiting":
        raise ToolError("INVALID_STATE", "Priority can only be changed for a waiting patient.")
    previous = entry.priority
    entry.priority = priority
    _event(db, session, "priority", now, entry_id=entry.id, previous=previous, priority=priority, **payload)
    _after_event(db, session, now)


def _request_dict(r: PriorityRequest) -> dict:
    return {
        "request_id": r.id,
        "entry_id": r.entry_id,
        "token": r.entry.token,
        "current_priority": r.entry.priority,
        "priority": r.priority,
        "reason": r.reason,
        "status": r.status,
        "requested_at": r.requested_at.isoformat(),
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    }


@write_tool("request_priority")
def request_priority(
    db: Session, actor: Actor, entry_id: int, priority: int, reason: str, now: datetime | None = None
) -> dict:
    """The front desk asks the patient's doctor to change their priority (feature 52)."""
    now = resolve_now(now)
    require_role(actor, "staff")
    _check_priority(priority)
    reason = " ".join((reason or "").split())
    if not 3 <= len(reason) <= 200:
        raise ToolError("VALIDATION_ERROR", "Give the doctor a short reason (3-200 characters).")
    entry, session = _lock_entry(db, entry_id)
    _require_open(session)
    if entry.status != "waiting":
        raise ToolError("INVALID_STATE", "Priority can only be changed for a waiting patient.")
    if entry.priority == priority:
        raise ToolError("VALIDATION_ERROR", f"Token {entry.token} already has priority {priority}.")
    pending = db.scalars(
        select(PriorityRequest.id).where(PriorityRequest.entry_id == entry.id, PriorityRequest.status == "pending")
    ).first()
    if pending is not None:
        raise ToolError("DUPLICATE", "A request for this patient is already waiting for the doctor.")
    request = PriorityRequest(
        entry_id=entry.id,
        priority=priority,
        reason=reason,
        status="pending",
        requested_by=actor.user_id,
        requested_at=now,
    )
    db.add(request)
    db.flush()
    _event(db, session, "priority_request", now, entry_id=entry.id, request_id=request.id, priority=priority)
    return {**_request_dict(request), "session_id": session.id}


@write_tool("decide_priority_request")
def decide_priority_request(
    db: Session, actor: Actor, request_id: int, approve: bool, now: datetime | None = None
) -> dict:
    """The patient's doctor authorizes or declines the front desk's request (feature 52)."""
    now = resolve_now(now)
    require_role(actor, "doctor")
    request = db.get(PriorityRequest, request_id)
    if request is None:
        raise ToolError("NOT_FOUND", f"Priority request {request_id} does not exist.")
    entry, session = _lock_entry(db, request.entry_id)
    require_own_doctor(actor, session.doctor_id)
    db.refresh(request, with_for_update=True)
    if request.status != "pending":
        raise ToolError("INVALID_STATE", f"This request has already been {request.status}.")
    if approve:
        _require_open(session)
        _apply_priority(db, session, entry, request.priority, now, request_id=request.id)
    request.status = "approved" if approve else "declined"
    request.decided_by = actor.user_id
    request.decided_at = now
    db.flush()
    return {**_request_dict(request), "session_id": session.id}


def pending_priority_requests(db: Session, session_id: int) -> list[dict]:
    """Requests still waiting for the doctor, for patients who are still waiting."""
    rows = db.scalars(
        select(PriorityRequest)
        .join(QueueEntry, QueueEntry.id == PriorityRequest.entry_id)
        .where(
            QueueEntry.session_id == session_id,
            QueueEntry.status == "waiting",
            PriorityRequest.status == "pending",
        )
        .order_by(PriorityRequest.id)
    )
    return [_request_dict(r) for r in rows]


# --------------------------------------------------------------------------- moving patients


def _doctor_on_leave(db: Session, doctor_id: int, day: date) -> bool:
    return (doctor_id, day) in leave_days(db, day, day)


def _move_entry(
    db: Session, entry: QueueEntry, source: QueueSession, target: QueueSession, now: datetime, reason: str | None
) -> QueueEntry:
    """Close the entry here and continue it in the target doctor's queue under a new T-token.

    The patient keeps their check-in time (they do not go to the back of the line), their priority and
    their appointment; the old entry is kept as history."""
    if entry.status == "in_consultation":  # forwarded by the doctor after seeing the patient
        entry.consult_end = now
    entry.status = "transferred"
    entry.position = None
    db.flush()  # releases the appointment before the new entry takes it over
    moved = QueueEntry(
        session_id=target.id,
        appointment_id=entry.appointment_id,
        patient_id=entry.patient_id,
        token=_next_token(db, target, "T"),
        kind=entry.kind,
        scheduled_at=entry.scheduled_at,
        checked_in_at=entry.checked_in_at,
        status="waiting",
        priority=entry.priority,
        late_minutes=entry.late_minutes,
        joined_remotely=entry.joined_remotely,
        arrived_at=entry.arrived_at,
        transferred_from_id=entry.id,
    )
    db.add(moved)
    db.flush()
    doctor = target.doctor
    _event(db, source, "transfer_out", now, entry_id=entry.id, to_doctor_id=doctor.id, new_entry_id=moved.id,
           reason=reason)  # fmt: skip
    _event(db, target, "transfer_in", now, entry_id=moved.id, from_doctor_id=source.doctor_id, token=moved.token)
    notify(
        db,
        entry.patient_id,
        f"You have been moved to {doctor.name} ({doctor.department.name}, floor {doctor.department.floor}). "
        f"Your new token is {moved.token}; you keep your place by the time you checked in.",
        now,
        kind="transfer",
        appointment_id=entry.appointment_id,
    )
    return moved


@write_tool("transfer_entry")
def transfer_entry(
    db: Session, actor: Actor, entry_id: int, doctor_id: int, reason: str | None = None, now: datetime | None = None
) -> dict:
    """Move a patient to another doctor today: in the same department (reassignment, feature 42) or another
    one (transfer and forwarding, features 43 and 53). The front desk moves anyone who is waiting; the
    patient's doctor can also forward the patient they are seeing."""
    now = resolve_now(now)
    require_role(actor, "staff", "doctor")
    reason = " ".join(reason.split())[:200] if reason else None
    source_id = db.scalar(select(QueueEntry.session_id).where(QueueEntry.id == entry_id))
    if source_id is None:
        raise ToolError("NOT_FOUND", f"Queue entry {entry_id} does not exist.")
    source_doctor = db.scalar(select(QueueSession.doctor_id).where(QueueSession.id == source_id))
    require_queue_control(actor, source_doctor)
    if doctor_id == source_doctor:
        raise ToolError("VALIDATION_ERROR", "The patient is already in this doctor's queue.")
    if db.get(Doctor, doctor_id) is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    if _doctor_on_leave(db, doctor_id, now.date()):
        raise ToolError("INVALID_STATE", "That doctor is on leave today.")
    target_id = _ensure_session(db, doctor_id, now.date())
    sessions = _lock_sessions(db, [source_id, target_id])
    source, target = sessions[source_id], sessions[target_id]
    entry = db.scalars(
        select(QueueEntry).where(QueueEntry.id == entry_id).with_for_update().execution_options(populate_existing=True)
    ).one()
    if source.date != now.date():
        raise ToolError("INVALID_STATE", "Only today's patients can be moved.")
    _require_open(target)
    allowed = ("waiting", "called", "missed", "in_consultation") if actor.role == "doctor" else ("waiting", "missed")
    if entry.status not in allowed:
        raise ToolError("INVALID_STATE", f"A patient who is {entry.status.replace('_', ' ')} cannot be moved.")
    if _in_queue(db, target, entry.patient_id):
        raise ToolError("ALREADY_CHECKED_IN", "This patient is already in that doctor's queue.")
    moved = _move_entry(db, entry, source, target, now, reason)
    _after_event(db, source, now)
    _after_event(db, target, now)
    return {
        **entry_dict(moved),
        "from_session_id": source.id,
        "from_doctor": source.doctor.name,
        "to_doctor": target.doctor.name,
        "same_department": source.doctor.department_id == target.doctor.department_id,
    }


def _colleague_session_ids(db: Session, doctor_id: int, day: date) -> list[int]:
    """Open sessions today of the other doctors in the same department who are working (not on leave)."""
    doctor = db.get(Doctor, doctor_id)
    away = leave_days(db, day, day)
    ids = []
    for other in db.scalars(
        select(Doctor).where(Doctor.department_id == doctor.department_id, Doctor.id != doctor_id).order_by(Doctor.id)
    ):
        if holds_opd(db, other, day) and (other.id, day) not in away:
            session_id = _ensure_session(db, other.id, day)
            if db.scalar(select(QueueSession.status).where(QueueSession.id == session_id)) == "open":
                ids.append(session_id)
    return ids


# --------------------------------------------------------------------------- virtual queue, arrival, leaving


@write_tool("join_virtual_queue")
def join_virtual_queue(db: Session, actor: Actor, doctor_id: int, patient_id: int, now: datetime | None = None) -> dict:
    """A patient without a booking joins a doctor's queue today from their phone (feature 38)."""
    now = resolve_now(now)
    require_role(actor, "patient", "caregiver")
    require_patient_access(db, actor, patient_id)
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    day = now.date()
    if not holds_opd(db, doctor, day) or _doctor_on_leave(db, doctor_id, day):
        raise ToolError("INVALID_STATE", f"{doctor.name} has no OPD today.")
    dept = doctor.department
    opens = at(day, dept.opd_start) - policy.VIRTUAL_JOIN_OPENS
    closes = at(day, dept.opd_end) - policy.VIRTUAL_JOIN_CLOSES
    if not opens <= now <= closes:
        raise ToolError(
            "POLICY_WINDOW",
            f"The online queue for {dept.name} is open from {to_ist(opens):%H:%M} to {to_ist(closes):%H:%M}.",
        )
    booked_today = db.scalars(
        select(Appointment.id).where(
            Appointment.patient_id == patient_id,
            Appointment.doctor_id == doctor_id,
            Appointment.appt_date == day,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        )
    ).first()
    if booked_today is not None:
        raise ToolError("INVALID_STATE", f"You have an appointment with {doctor.name} today; check in for it instead.")
    if _in_any_queue_today(db, patient_id, day):
        raise ToolError("ALREADY_CHECKED_IN", "You are already in a queue today.")
    session = get_or_create_session(db, doctor_id, day)
    _require_open(session)
    remote_waiting = db.scalar(
        select(func.count())
        .select_from(QueueEntry)
        .where(
            QueueEntry.session_id == session.id,
            QueueEntry.joined_remotely.is_(True),
            QueueEntry.arrived_at.is_(None),
            QueueEntry.status.in_(WAITING_ENTRY_STATUSES),
        )
    )
    if remote_waiting >= policy.VIRTUAL_QUEUE_CAP:
        raise ToolError("QUEUE_FULL", f"The online queue for {doctor.name} is full; please come to the OPD desk.")
    entry = QueueEntry(
        session_id=session.id,
        patient_id=patient_id,
        token=_next_token(db, session, "V"),
        kind="walk_in",
        checked_in_at=now,
        status="waiting",
        priority=0,
        joined_remotely=True,
    )
    db.add(entry)
    db.flush()
    _event(db, session, "remote_join", now, entry_id=entry.id, token=entry.token)
    _after_event(db, session, now)
    return {**entry_dict(entry), "doctor_name": doctor.name, "department": dept.name, "floor": dept.floor}


@write_tool("mark_arrived")
def mark_arrived(db: Session, actor: Actor, entry_id: int, now: datetime | None = None) -> dict:
    """A patient who joined online has reached the OPD desk."""
    now = resolve_now(now)
    require_role(actor, "staff")
    entry, session = _lock_entry(db, entry_id)
    if not entry.joined_remotely or entry.arrived_at is not None:
        raise ToolError("INVALID_STATE", "This patient is already marked as here.")
    if entry.status not in ACTIVE_ENTRY_STATUSES:
        raise ToolError("INVALID_STATE", "This patient is no longer in the queue.")
    entry.arrived_at = now
    _event(db, session, "arrived", now, entry_id=entry.id)
    db.flush()
    return entry_dict(entry)


@write_tool("mark_left")
def mark_left(db: Session, actor: Actor, entry_id: int, now: datetime | None = None) -> dict:
    """Left without being seen (feature 47): the front desk records it, or the patient leaves the queue
    themselves. Counted separately from no-shows, who never arrived."""
    now = resolve_now(now)
    require_role(actor, "staff", "patient", "caregiver")
    entry, session = _lock_entry(db, entry_id)
    if actor.role != "staff" and not can_manage_patient(db, actor, entry.patient_id):
        raise ToolError("FORBIDDEN", "You are not allowed to change this queue entry.")
    if entry.status not in ("waiting", "called", "missed"):
        raise ToolError("INVALID_STATE", "Only a patient who is still waiting can leave the queue.")
    _leave(entry, now)
    _event(db, session, "left", now, entry_id=entry.id, by=actor.role)
    _after_event(db, session, now)
    return entry_dict(entry)


def _leave(entry: QueueEntry, now: datetime) -> None:
    entry.status = "left"
    entry.position = None
    if entry.appointment is not None:
        entry.appointment.status = "left"
        entry.appointment.updated_at = now


# --------------------------------------------------------------------------- doctor status


@write_tool("record_doctor_event")
def record_doctor_event(
    db: Session,
    actor: Actor,
    session_id: int,
    type: str,
    minutes: int | None = None,
    reason: str | None = None,
    reassign: bool = False,
    now: datetime | None = None,
) -> dict:
    """Break, delay, emergency interruption, resume or unavailability (FR-23, FR-27, features 49, 50).

    Doctors record their own breaks, delays and emergencies; only the front desk declares a doctor
    unavailable, optionally moving the waiting patients to colleagues in the department (feature 42)."""
    now = resolve_now(now)
    require_role(actor, "staff", "doctor")
    if type not in DOCTOR_EVENTS:
        raise ToolError("VALIDATION_ERROR", f"Event type must be one of {', '.join(DOCTOR_EVENTS)}.")
    if type == "unavailable" and actor.role != "staff":
        raise ToolError("FORBIDDEN", "The front desk marks a doctor unavailable for the day.")
    colleagues: list[int] = []
    if type == "unavailable" and reassign:
        row = db.execute(select(QueueSession.doctor_id, QueueSession.date).where(QueueSession.id == session_id)).first()
        if row is None:
            raise ToolError("NOT_FOUND", "Queue session not found.")
        colleagues = _colleague_session_ids(db, row.doctor_id, row.date)
        _lock_sessions(db, [session_id, *colleagues])
    session = _lock_session(db, session_id=session_id)
    require_queue_control(actor, session.doctor_id)
    _require_open(session)
    if type in ("break", "delay", "emergency"):
        if minutes is None or not 1 <= minutes <= 240:
            raise ToolError("VALIDATION_ERROR", "Give the expected length in minutes (1-240).")
        busy_until = now + timedelta(minutes=minutes)
        session.busy_until = max(busy_until, session.busy_until) if session.busy_until else busy_until
        session.doctor_status = "on_break" if type == "break" else "delayed"
        session.delay_minutes = minutes if type != "break" else 0
        notified = _notify_delay(db, session, type, minutes, now) if type != "break" else 0
        _event(db, session, type, now, minutes=minutes, reason=reason, notified=notified)
    elif type == "resume":
        session.doctor_status = "available"
        session.busy_until = None
        session.delay_minutes = 0
        _event(db, session, "resume", now, reason=reason)
    else:
        _event(db, session, "unavailable", now, reason=reason, reassign=reassign)
        targets = [_lock_session(db, session_id=sid) for sid in colleagues]
        affected, moved = _handle_unavailable(db, session, now, targets)
        for target in {m.session_id for m in moved}:
            _after_event(db, _lock_session(db, session_id=target), now)
        return {
            "session_id": session.id,
            "doctor_status": session.doctor_status,
            "affected": affected,
            "moved": [entry_dict(m) for m in moved],
        }
    _after_event(db, session, now)
    return {
        "session_id": session.id,
        "doctor_status": session.doctor_status,
        "busy_until": session.busy_until.isoformat() if session.busy_until else None,
    }


def _notify_delay(db: Session, session: QueueSession, type_: str, minutes: int, now: datetime) -> int:
    """Tell everyone waiting that the doctor is held up (feature 49); they keep their place."""
    doctor = session.doctor.name
    if type_ == "emergency":
        message = (f"{doctor} is attending to an emergency. Your consultation is delayed by about {minutes} "
                   "minutes; you keep your place in the queue.")  # fmt: skip
    else:
        message = f"{doctor} is running about {minutes} minutes late. You keep your place in the queue."
    waiting = db.scalars(
        select(QueueEntry).where(QueueEntry.session_id == session.id, QueueEntry.status.in_(WAITING_ENTRY_STATUSES))
    ).all()
    for entry in waiting:
        notify(db, entry.patient_id, message, now, kind="delay", appointment_id=entry.appointment_id)
    return len(waiting)


def _handle_unavailable(
    db: Session, session: QueueSession, now: datetime, targets: list[QueueSession]
) -> tuple[list[dict], list[QueueEntry]]:
    """FR-27: close the queue, release today's remaining bookings for rebooking and notify everyone.

    With ``targets`` (colleagues' open sessions), patients already waiting are moved to whichever colleague
    will be free soonest instead of being sent home (feature 42)."""
    doctor = session.doctor
    moved: list[QueueEntry] = []
    if targets:
        load = {t.id: _backlog_minutes(db, t, now) for t in targets}
        for entry in ordered_waiting(db, session, now) + list(
            db.scalars(select(QueueEntry).where(QueueEntry.session_id == session.id, QueueEntry.status == "called"))
        ):
            free = [t for t in targets if not _in_queue(db, t, entry.patient_id)]
            if not free:
                continue
            target = min(free, key=lambda t: (load[t.id], t.id))
            moved.append(_move_entry(db, entry, session, target, now, "doctor unavailable"))
            load[target.id] += target.doctor.slot_minutes
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
        # Keep appointments that are being seen here or carried on in a colleague's queue.
        carried_on = db.scalars(
            select(QueueEntry.id).where(
                QueueEntry.appointment_id == appt.id,
                or_(
                    QueueEntry.status == "in_consultation",
                    and_(QueueEntry.session_id != session.id, QueueEntry.status != "transferred"),
                ),
            )
        ).first()
        if carried_on is not None:
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
            kind="unavailable",
            appointment_id=item.get("appointment_id"),
        ).id
    db.flush()
    return list(affected.values()), moved


def _backlog_minutes(db: Session, session: QueueSession, now: datetime) -> float:
    """Minutes of work ahead of a doctor: their waiting patients plus any break or delay still running."""
    waiting = db.scalar(
        select(func.count())
        .select_from(QueueEntry)
        .where(QueueEntry.session_id == session.id, QueueEntry.status.in_(("waiting", "called", "in_consultation")))
    )
    busy = max(0.0, (session.busy_until - now).total_seconds() / 60) if session.busy_until else 0.0
    return waiting * session.doctor.slot_minutes + busy


@write_tool("close_session")
def close_session(db: Session, actor: Actor, session_id: int, now: datetime | None = None) -> dict:
    """End of OPD: booked patients who never arrived become no-shows; patients who missed their turn and
    never came back left without being seen. Both are offered a new appointment."""
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
    # Patients who missed their turn and never came back left without being seen (feature 47).
    left: list[Appointment] = []
    left_unseen = 0
    for entry in db.scalars(
        select(QueueEntry).where(QueueEntry.session_id == session.id, QueueEntry.status == "missed")
    ):
        _leave(entry, now)
        left_unseen += 1
        if entry.appointment is not None:
            left.append(entry.appointment)
    checked_in = select(QueueEntry.appointment_id).where(QueueEntry.appointment_id.is_not(None))
    no_shows: list[Appointment] = []
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
        no_shows.append(appt)
    # Missed-appointment recovery: everyone who missed their visit is offered a new one.
    for appt in no_shows + left:
        notify(
            db,
            appt.patient_id,
            f"We missed you at your appointment with {session.doctor.name} on {session.date:%d %b}. "
            "Book a new time in CareFlow: My appointments → Rebook.",
            now,
            kind="rebook",
            appointment_id=appt.id,
        )
    session.status = "closed"
    session.closed_at = now
    _event(db, session, "session_closed", now, no_shows=len(no_shows), left_unseen=left_unseen)
    db.flush()
    return {"session_id": session.id, "status": "closed", "no_shows": len(no_shows), "left_unseen": left_unseen}


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
        "department": session.doctor.department.name,
        "floor": session.doctor.department.floor,
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
