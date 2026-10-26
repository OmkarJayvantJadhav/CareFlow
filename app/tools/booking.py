"""Deterministic booking rules (FR-07 – FR-16). The LLM never decides any of these."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import any_, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    Department,
    Doctor,
    Patient,
    Slot,
    WaitingList,
)
from app.timeutil import at, resolve_now, to_ist
from app.tools import policy
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.hospital import resolve_department
from app.tools.permissions import Actor, require_patient_access
from app.tools.serialize import appointment_dict, doctor_dict, slot_dict
from app.tools.timetable import current_doctor
from app.tools.vocab import normalize_language, parse_day

# --------------------------------------------------------------------------- reads


def search_doctors(
    db: Session,
    specialty: str | None = None,
    language: str | None = None,
    day: str | date | None = None,
    now: datetime | None = None,
) -> dict:
    """FR-07: doctors filtered by specialty, spoken language and OPD day."""
    now = resolve_now(now)
    query = select(Doctor).join(Department).where(current_doctor(now.date())).order_by(Department.name, Doctor.name)
    criteria: dict = {}
    if specialty:
        department = resolve_department(db, specialty)
        query = query.where(Department.name == department)
        criteria["department"] = department
    if language:
        lang = normalize_language(language)
        query = query.where(literal(lang) == any_(Doctor.languages))
        criteria["language"] = lang
    if day:
        weekday, next_date = parse_day(day, now)
        query = query.where(literal(weekday) == any_(Doctor.opd_days), current_doctor(next_date))
        criteria["date"] = next_date.isoformat()
    doctors = [doctor_dict(d) for d in db.scalars(query)]
    return {"criteria": criteria, "doctors": doctors}


def _slot_visible_to(slot: Slot, patient_id: int | None, now: datetime) -> bool:
    if slot.status != "free":
        return False
    if slot.start_at < now + policy.BOOKING_LEAD:
        return False
    held = slot.held_until is not None and slot.held_until > now
    return not held or slot.held_for_patient_id == patient_id


def check_availability(
    db: Session,
    doctor_id: int,
    day: str | date,
    patient_id: int | None = None,
    now: datetime | None = None,
) -> dict:
    """FR-08: free slots for a doctor on a date. Slots held for a waiting-list
    patient are shown only to that patient."""
    now = resolve_now(now)
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    target = parse_day(day, now)[1] if isinstance(day, str) else day
    result = {"doctor": doctor_dict(doctor), "date": target.isoformat(), "works_that_day": True, "slots": []}
    if not doctor.works_on(target):
        result["works_that_day"] = False
        return result
    if target < now.date() or target > (now + policy.BOOKING_HORIZON).date():
        result["outside_booking_window"] = True
        return result
    slots = db.scalars(
        select(Slot)
        .where(
            Slot.doctor_id == doctor_id,
            Slot.start_at >= at(target, time.min),
            Slot.start_at < at(target + timedelta(days=1), time.min),
        )
        .order_by(Slot.start_at)
    )
    result["slots"] = [slot_dict(s) for s in slots if _slot_visible_to(s, patient_id, now)]
    return result


def get_patient_appointments(db: Session, actor: Actor, patient_id: int, now: datetime | None = None) -> dict:
    """FR-16: appointment history (owner, linked caregiver or staff)."""
    now = resolve_now(now)
    require_patient_access(db, actor, patient_id)
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ToolError("NOT_FOUND", f"Patient {patient_id} does not exist.")
    rows = db.scalars(
        select(Appointment).join(Slot).where(Appointment.patient_id == patient_id).order_by(Slot.start_at.desc())
    )
    upcoming, past = [], []
    for a in rows:
        item = appointment_dict(a)
        is_active = a.status in ACTIVE_APPOINTMENT_STATUSES or a.status == "displaced"
        (upcoming if is_active and a.slot.start_at >= now else past).append(item)
    upcoming.reverse()
    return {"patient_id": patient_id, "patient_name": patient.name, "upcoming": upcoming, "past": past}


# --------------------------------------------------------------------------- helpers


def _require_confirmed(confirmed: bool) -> None:
    if confirmed is not True:
        raise ToolError(
            "CONFIRMATION_REQUIRED",
            "This change needs the patient's explicit confirmation. Ask them to confirm, then call again "
            "with confirmed=true.",
        )


def _lock_slots(db: Session, *slot_ids: int) -> dict[int, Slot]:
    """Lock slot rows in id order (avoids deadlocks) and re-read them from the database."""
    rows = db.scalars(
        select(Slot)
        .where(Slot.id.in_(slot_ids))
        .order_by(Slot.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {s.id: s for s in rows}


def _lock_appointment(db: Session, appointment_id: int) -> Appointment:
    appt = db.scalars(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if appt is None:
        raise ToolError("NOT_FOUND", f"Appointment {appointment_id} does not exist.")
    return appt


def _alternatives(db: Session, slot: Slot, patient_id: int, now: datetime, limit: int = 3) -> list[dict]:
    day = to_ist(slot.start_at).date()
    free = check_availability(db, slot.doctor_id, day, patient_id=patient_id, now=now)["slots"]
    return [s for s in free if s["slot_id"] != slot.id][:limit]


def _check_bookable(db: Session, slot: Slot, patient_id: int, now: datetime) -> None:
    if slot.start_at < now + policy.BOOKING_LEAD:
        raise ToolError("VALIDATION_ERROR", "That time has already passed or is too soon to book.")
    if slot.start_at > now + policy.BOOKING_HORIZON:
        raise ToolError("VALIDATION_ERROR", "Appointments can be booked at most 30 days ahead.")
    held_for_other = slot.held_until is not None and slot.held_until > now and slot.held_for_patient_id != patient_id
    if slot.status != "free" or held_for_other:
        raise ToolError(
            "SLOT_TAKEN",
            "Sorry, that slot is no longer available.",
            alternatives=_alternatives(db, slot, patient_id, now),
        )


def _check_duplicate(db: Session, patient_id: int, doctor_id: int, day: date, exclude_id: int | None = None) -> None:
    query = select(Appointment).where(
        Appointment.patient_id == patient_id,
        Appointment.doctor_id == doctor_id,
        Appointment.appt_date == day,
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
    )
    if exclude_id is not None:
        query = query.where(Appointment.id != exclude_id)
    existing = db.scalars(query).first()
    if existing is not None:
        raise ToolError(
            "DUPLICATE",
            "The patient already has an appointment with this doctor on that day.",
            existing=appointment_dict(existing),
        )


def _flush_or_conflict(db: Session) -> None:
    """The partial unique indexes are the last line of defence against races."""
    try:
        db.flush()
    except IntegrityError as err:
        name = getattr(getattr(err.orig, "diag", None), "constraint_name", "") or ""
        if "patient_doctor_day" in name:
            raise ToolError(
                "DUPLICATE", "The patient already has an appointment with this doctor on that day."
            ) from None
        if "active_slot" in name:
            raise ToolError("SLOT_TAKEN", "Sorry, that slot is no longer available.") from None
        raise


def _free_slot(db: Session, slot: Slot, now: datetime) -> None:
    """Release a slot and offer it to the waiting list first (FR-14). A slot the doctor's timetable no longer
    has (it changed, or the doctor has left) is retired instead, and the timetable's own slots take its place."""
    from app.tools.timetable import ensure_slots, on_timetable
    from app.tools.waiting_list import offer_freed_slot

    if slot.status == "booked":
        slot.status = "free"
    slot.held_for_patient_id = None
    slot.held_until = None
    db.flush()
    day = to_ist(slot.start_at).date()
    if slot.status == "free" and day > now.date() and not on_timetable(slot.doctor, slot):  # today runs as planned
        slot.status = "retired"
        db.flush()
        ensure_slots(db, day, day, [slot.doctor_id])
        return
    if slot.status == "free":
        offer_freed_slot(db, slot, now)


def _fulfil_waiting_list(db: Session, patient_id: int, doctor_id: int, booked_slot_id: int, now: datetime) -> None:
    """Close the patient's waiting-list entry for this doctor; an offer for a
    different slot is released and passed on to the next waiting patient."""
    from app.tools.waiting_list import offer_freed_slot

    entries = list(
        db.scalars(
            select(WaitingList).where(
                WaitingList.patient_id == patient_id,
                WaitingList.doctor_id == doctor_id,
                WaitingList.status.in_(("active", "offered")),
            )
        )
    )
    for entry in entries:
        entry.status = "fulfilled"
        offered_id = entry.offered_slot_id
        if offered_id is None or offered_id == booked_slot_id:
            continue
        held = _lock_slots(db, offered_id).get(offered_id)
        if held is not None and held.held_for_patient_id == patient_id:
            held.held_for_patient_id = None
            held.held_until = None
            db.flush()
            offer_freed_slot(db, held, now, exclude_patient_ids={patient_id})
    db.flush()


def _clear_stale_offers(db: Session, slot: Slot, patient_id: int) -> None:
    """A lapsed hold lets anyone book the slot; the lapsed offer goes back to the list."""
    for entry in db.scalars(
        select(WaitingList).where(
            WaitingList.offered_slot_id == slot.id,
            WaitingList.status == "offered",
            WaitingList.patient_id != patient_id,
        )
    ):
        entry.status = "active"
        entry.offered_slot_id = None
        entry.offer_expires_at = None


def _source_for(actor: Actor, source: str | None) -> str:
    if source:
        return source
    return "staff" if actor.role == "staff" else "agent"


# --------------------------------------------------------------------------- writes


@write_tool("book_appointment")
def book_appointment(
    db: Session,
    actor: Actor,
    patient_id: int,
    slot_id: int,
    confirmed: bool = False,
    now: datetime | None = None,
    source: str | None = None,
) -> dict:
    """FR-09 – FR-11: book only after confirmation, only a free slot, never a duplicate."""
    now = resolve_now(now)
    require_patient_access(db, actor, patient_id)
    _require_confirmed(confirmed)
    patient = db.get(Patient, patient_id)
    if patient is None or patient.erased_at is not None:
        raise ToolError("NOT_FOUND", f"Patient {patient_id} does not exist.")
    slot = _lock_slots(db, slot_id).get(slot_id)
    if slot is None:
        raise ToolError("NOT_FOUND", f"Slot {slot_id} does not exist.")
    _check_bookable(db, slot, patient_id, now)
    day = to_ist(slot.start_at).date()
    _check_duplicate(db, patient_id, slot.doctor_id, day)

    appt = Appointment(
        patient_id=patient_id,
        slot_id=slot.id,
        doctor_id=slot.doctor_id,
        appt_date=day,
        status="booked",
        source=_source_for(actor, source),
        created_by=actor.user_id,
        created_at=now,
    )
    # Before db.add: its query would autoflush the new row outside _flush_or_conflict.
    _clear_stale_offers(db, slot, patient_id)
    db.add(appt)
    slot.status = "booked"
    slot.held_for_patient_id = None
    slot.held_until = None
    _flush_or_conflict(db)
    _fulfil_waiting_list(db, patient_id, slot.doctor_id, slot.id, now)
    return {**appointment_dict(appt), "cancellation_policy": policy.CANCEL_POLICY}


@write_tool("reschedule_appointment")
def reschedule_appointment(
    db: Session,
    actor: Actor,
    appointment_id: int,
    new_slot_id: int,
    confirmed: bool = False,
    now: datetime | None = None,
) -> dict:
    """FR-12: move an appointment to another free slot in the same department,
    outside the rescheduling cut-off. Appointments displaced by a doctor's
    absence can always be moved."""
    now = resolve_now(now)
    appt = _lock_appointment(db, appointment_id)
    require_patient_access(db, actor, appt.patient_id)
    _require_confirmed(confirmed)
    if appt.status not in (*ACTIVE_APPOINTMENT_STATUSES, "displaced"):
        raise ToolError("INVALID_STATE", f"This appointment is {appt.status} and cannot be rescheduled.")
    if appt.slot_id == new_slot_id:
        raise ToolError("VALIDATION_ERROR", "The new slot is the same as the current one.")

    slots = _lock_slots(db, appt.slot_id, new_slot_id)
    old_slot, new_slot = slots[appt.slot_id], slots.get(new_slot_id)
    if new_slot is None:
        raise ToolError("NOT_FOUND", f"Slot {new_slot_id} does not exist.")
    if appt.status != "displaced" and old_slot.start_at - now < policy.RESCHEDULE_CUTOFF:
        raise ToolError("POLICY_WINDOW", policy.RESCHEDULE_POLICY, policy=policy.RESCHEDULE_POLICY)
    if new_slot.doctor.department_id != old_slot.doctor.department_id:
        raise ToolError("VALIDATION_ERROR", "An appointment can only be moved within the same department.")
    _check_bookable(db, new_slot, appt.patient_id, now)
    new_day = to_ist(new_slot.start_at).date()
    _check_duplicate(db, appt.patient_id, new_slot.doctor_id, new_day, exclude_id=appt.id)
    _clear_stale_offers(db, new_slot, appt.patient_id)

    appt.slot_id = new_slot.id
    appt.doctor_id = new_slot.doctor_id
    appt.appt_date = new_day
    appt.status = "rescheduled"
    appt.updated_at = now
    new_slot.status = "booked"
    new_slot.held_for_patient_id = None
    new_slot.held_until = None
    _flush_or_conflict(db)
    _fulfil_waiting_list(db, appt.patient_id, new_slot.doctor_id, new_slot.id, now)
    _free_slot(db, old_slot, now)
    db.refresh(appt)
    return {**appointment_dict(appt), "previous_slot_id": old_slot.id}


@write_tool("cancel_appointment")
def cancel_appointment(
    db: Session,
    actor: Actor,
    appointment_id: int,
    confirmed: bool = False,
    now: datetime | None = None,
) -> dict:
    """FR-13: cancel within the cancellation window; explain the policy otherwise."""
    now = resolve_now(now)
    appt = _lock_appointment(db, appointment_id)
    require_patient_access(db, actor, appt.patient_id)
    _require_confirmed(confirmed)
    if appt.status not in (*ACTIVE_APPOINTMENT_STATUSES, "displaced"):
        raise ToolError("INVALID_STATE", f"This appointment is {appt.status} and cannot be cancelled.")
    slot = _lock_slots(db, appt.slot_id)[appt.slot_id]
    if appt.status != "displaced" and slot.start_at - now < policy.CANCEL_CUTOFF:
        raise ToolError("POLICY_WINDOW", policy.CANCEL_POLICY, policy=policy.CANCEL_POLICY)
    appt.status = "cancelled"
    appt.updated_at = now
    db.flush()
    _free_slot(db, slot, now)
    return {"appointment_id": appt.id, "status": appt.status, "policy_note": policy.CANCEL_POLICY}
