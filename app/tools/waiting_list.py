"""Waiting list (FR-14): join when nothing is free; a freed slot is offered to the
earliest matching waiting patient first and held for them for a limited time."""

from datetime import date, datetime

from sqlalchemy import any_, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Doctor, Patient, Slot, WaitingList
from app.timeutil import resolve_now, to_ist
from app.tools import policy
from app.tools.audit import write_tool
from app.tools.booking import _require_confirmed, check_availability
from app.tools.errors import ToolError
from app.tools.notify import notify
from app.tools.permissions import Actor, require_patient_access
from app.tools.serialize import waiting_list_dict
from app.tools.vocab import parse_date


@write_tool("join_waiting_list")
def join_waiting_list(
    db: Session,
    actor: Actor,
    patient_id: int,
    doctor_id: int,
    dates: list[str | date],
    confirmed: bool = False,
    now: datetime | None = None,
) -> dict:
    now = resolve_now(now)
    require_patient_access(db, actor, patient_id)
    _require_confirmed(confirmed)
    if db.get(Patient, patient_id) is None:
        raise ToolError("NOT_FOUND", f"Patient {patient_id} does not exist.")
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    if not dates:
        raise ToolError("VALIDATION_ERROR", "Give at least one preferred date.")
    wanted = sorted({parse_date(d) for d in dates})
    horizon = (now + policy.BOOKING_HORIZON).date()
    if any(d < now.date() or d > horizon for d in wanted):
        raise ToolError("VALIDATION_ERROR", "Preferred dates must be between today and 30 days ahead.")
    working = [d for d in wanted if doctor.works_on(d)]
    if not working:
        raise ToolError("VALIDATION_ERROR", f"{doctor.name} has no OPD on the requested dates.")

    free = []
    for d in working:
        free += check_availability(db, doctor_id, d, patient_id=patient_id, now=now)["slots"]
    if free:
        raise ToolError(
            "SLOTS_AVAILABLE", "There are free slots on the requested dates; book one instead.", slots=free[:5]
        )
    existing = db.scalars(
        select(WaitingList).where(
            WaitingList.patient_id == patient_id,
            WaitingList.doctor_id == doctor_id,
            WaitingList.status.in_(("active", "offered")),
        )
    ).first()
    if existing is not None:
        raise ToolError(
            "ALREADY_ON_LIST",
            "The patient is already on this doctor's waiting list.",
            entry=waiting_list_dict(existing),
        )

    entry = WaitingList(
        patient_id=patient_id,
        doctor_id=doctor_id,
        preferred_dates=working,
        status="active",
        created_by=actor.user_id,
        created_at=now,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError:
        raise ToolError("ALREADY_ON_LIST", "The patient is already on this doctor's waiting list.") from None
    return waiting_list_dict(entry)


def _has_active_appointment(db: Session, patient_id: int, doctor_id: int, day: date) -> bool:
    return (
        db.scalars(
            select(Appointment.id).where(
                Appointment.patient_id == patient_id,
                Appointment.doctor_id == doctor_id,
                Appointment.appt_date == day,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            )
        ).first()
        is not None
    )


def offer_freed_slot(
    db: Session, slot: Slot, now: datetime, exclude_patient_ids: set[int] | None = None
) -> WaitingList | None:
    """Offer a newly free slot to the earliest matching waiting-list patient and hold it for them."""
    if slot.status != "free" or slot.start_at - now < policy.WAITLIST_MIN_LEAD:
        return None
    day = to_ist(slot.start_at).date()
    candidates = db.scalars(
        select(WaitingList)
        .where(
            WaitingList.doctor_id == slot.doctor_id,
            WaitingList.status == "active",
            literal(day) == any_(WaitingList.preferred_dates),
        )
        .order_by(WaitingList.created_at, WaitingList.id)
        .with_for_update(skip_locked=True)
    )
    for entry in candidates:
        if exclude_patient_ids and entry.patient_id in exclude_patient_ids:
            continue
        if _has_active_appointment(db, entry.patient_id, slot.doctor_id, day):
            continue
        expires = min(now + policy.WAITLIST_OFFER_HOLD, slot.start_at - policy.BOOKING_LEAD)
        entry.status = "offered"
        entry.offered_slot_id = slot.id
        entry.offer_expires_at = expires
        slot.held_for_patient_id = entry.patient_id
        slot.held_until = expires
        start = to_ist(slot.start_at)
        notify(
            db,
            entry.patient_id,
            f"A slot with {slot.doctor.name} on {start:%d %b} at {start:%H:%M} has opened. "
            f"It is held for you until {to_ist(expires):%H:%M}. Reply to CareFlow to book it.",
            now,
        )
        db.flush()
        return entry
    return None


def expire_waitlist_offers(db: Session, now: datetime | None = None) -> int:
    """Return lapsed offers to the list and pass each held slot to the next patient."""
    now = resolve_now(now)
    lapsed = list(
        db.scalars(
            select(WaitingList)
            .where(WaitingList.status == "offered", WaitingList.offer_expires_at <= now)
            .with_for_update(skip_locked=True)
        )
    )
    for entry in lapsed:
        slot = db.get(Slot, entry.offered_slot_id) if entry.offered_slot_id else None
        entry.status = "active"
        entry.offered_slot_id = None
        entry.offer_expires_at = None
        if slot is not None and slot.held_for_patient_id == entry.patient_id:
            slot.held_for_patient_id = None
            slot.held_until = None
            db.flush()
            offer_freed_slot(db, slot, now, exclude_patient_ids={entry.patient_id})
    db.flush()
    return len(lapsed)
