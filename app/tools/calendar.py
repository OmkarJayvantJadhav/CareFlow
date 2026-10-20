"""Doctor calendars (feature 2): day-by-day slot counts, blocking single slots, leave days, and the
expected consultation length per doctor (feature 13). Staff and admins only."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Doctor, DoctorLeave, QueueEntry, Slot
from app.timeutil import at, resolve_now, to_ist
from app.tools import policy
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.notify import notify
from app.tools.permissions import Actor, require_role

MAX_CALENDAR_DAYS = 31
MAX_LEAVE_DAYS = 60
DURATION_HISTORY_DAYS = 60
MIN_VISITS_FOR_ESTIMATE = 5


def consult_minutes(db: Session, doctor_ids: list[int], now: datetime) -> dict[int, dict]:
    """Median and 80th-percentile consultation length from the last 60 days of finished visits.

    Doctors with fewer than five visits fall back to their slot length.
    """
    since = now - timedelta(days=DURATION_HISTORY_DAYS)
    minutes = func.extract("epoch", QueueEntry.consult_end - QueueEntry.consult_start) / 60
    rows = db.execute(
        select(
            Slot.doctor_id,
            func.count(),
            func.percentile_cont(0.5).within_group(minutes),
            func.percentile_cont(0.8).within_group(minutes),
        )
        .select_from(QueueEntry)
        .join(Appointment, Appointment.id == QueueEntry.appointment_id)
        .join(Slot, Slot.id == Appointment.slot_id)
        .where(
            Slot.doctor_id.in_(doctor_ids),
            QueueEntry.consult_end.is_not(None),
            QueueEntry.consult_start.is_not(None),
            QueueEntry.consult_start >= since,
        )
        .group_by(Slot.doctor_id)
    ).all()
    measured = {doctor_id: (n, median, p80) for doctor_id, n, median, p80 in rows}
    out = {}
    for doctor in db.scalars(select(Doctor).where(Doctor.id.in_(doctor_ids))):
        n, median, p80 = measured.get(doctor.id, (0, None, None))
        if n >= MIN_VISITS_FOR_ESTIMATE:
            out[doctor.id] = {"typical": round(median), "long": round(p80), "visits": n, "source": "history"}
        else:
            out[doctor.id] = {
                "typical": doctor.slot_minutes,
                "long": doctor.slot_minutes,
                "visits": n,
                "source": "slot",
            }
    return out


def leave_days(db: Session, start: date, end: date) -> set[tuple[int, date]]:
    """(doctor_id, day) pairs covered by leave between two dates; used when new slots are created."""
    out = set()
    for leave in db.scalars(select(DoctorLeave).where(DoctorLeave.end_date >= start, DoctorLeave.start_date <= end)):
        day = max(leave.start_date, start)
        while day <= min(leave.end_date, end):
            out.add((leave.doctor_id, day))
            day += timedelta(days=1)
    return out


def _leave_dict(leave: DoctorLeave) -> dict:
    return {
        "leave_id": leave.id,
        "doctor_id": leave.doctor_id,
        "start_date": leave.start_date.isoformat(),
        "end_date": leave.end_date.isoformat(),
        "reason": leave.reason,
    }


def doctor_calendar(
    db: Session, actor: Actor, doctor_id: int, start: date | None = None, days: int = 14, now: datetime | None = None
) -> dict:
    """Free, booked and blocked slots per day, with leave and the expected consultation length."""
    require_role(actor, "staff", "admin")
    now = resolve_now(now)
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    start = start or now.date()
    days = max(1, min(days, MAX_CALENDAR_DAYS))
    end = start + timedelta(days=days - 1)
    slots = list(
        db.scalars(
            select(Slot)
            .where(
                Slot.doctor_id == doctor_id,
                Slot.start_at >= at(start, time.min),
                Slot.start_at < at(end + timedelta(days=1), time.min),
            )
            .order_by(Slot.start_at)
        )
    )
    by_day: dict[date, list[Slot]] = defaultdict(list)
    for s in slots:
        by_day[to_ist(s.start_at).date()].append(s)
    # Every leave from the first day shown onwards, so upcoming leave is listed whichever week is open.
    leaves = list(
        db.scalars(
            select(DoctorLeave)
            .where(DoctorLeave.doctor_id == doctor_id, DoctorLeave.end_date >= start)
            .order_by(DoctorLeave.start_date)
        )
    )
    calendar = []
    for i in range(days):
        day = start + timedelta(days=i)
        day_slots = by_day.get(day, [])
        leave = next((lv for lv in leaves if lv.start_date <= day <= lv.end_date), None)
        calendar.append(
            {
                "date": day.isoformat(),
                "works": day.isoweekday() in doctor.opd_days,
                "leave": _leave_dict(leave) if leave else None,
                "free": sum(1 for s in day_slots if s.status == "free"),
                "booked": sum(1 for s in day_slots if s.status == "booked"),
                "blocked": sum(1 for s in day_slots if s.status == "blocked"),
                "slots": [
                    {
                        "slot_id": s.id,
                        "time": to_ist(s.start_at).strftime("%H:%M"),
                        "status": s.status,
                        "past": s.start_at <= now,
                    }
                    for s in day_slots
                ],
            }
        )
    return {
        "doctor_id": doctor.id,
        "doctor_name": doctor.name,
        "department": doctor.department.name,
        "slot_minutes": doctor.slot_minutes,
        "consultation_minutes": consult_minutes(db, [doctor.id], now)[doctor.id],
        "leaves": [_leave_dict(lv) for lv in leaves],
        "days": calendar,
    }


def _lock_slot(db: Session, slot_id: int) -> Slot:
    slot = db.scalars(
        select(Slot).where(Slot.id == slot_id).with_for_update().execution_options(populate_existing=True)
    ).first()
    if slot is None:
        raise ToolError("NOT_FOUND", f"Slot {slot_id} does not exist.")
    return slot


@write_tool("set_slot_blocked")
def set_slot_blocked(db: Session, actor: Actor, slot_id: int, blocked: bool, now: datetime | None = None) -> dict:
    """Block a free slot or reopen a blocked one. Booked slots are changed through the appointment."""
    require_role(actor, "staff", "admin")
    now = resolve_now(now)
    slot = _lock_slot(db, slot_id)
    if slot.start_at <= now:
        raise ToolError("VALIDATION_ERROR", "That slot is in the past.")
    if blocked:
        if slot.status == "booked":
            raise ToolError("INVALID_STATE", "That slot is booked; reschedule or cancel the appointment first.")
        slot.status = "blocked"
        slot.held_for_patient_id = None
        slot.held_until = None
    else:
        if slot.status != "blocked":
            raise ToolError("INVALID_STATE", "Only a blocked slot can be reopened.")
        day = to_ist(slot.start_at).date()
        on_leave = db.scalars(
            select(DoctorLeave.id).where(
                DoctorLeave.doctor_id == slot.doctor_id, DoctorLeave.start_date <= day, DoctorLeave.end_date >= day
            )
        ).first()
        if on_leave is not None:
            raise ToolError("INVALID_STATE", "The doctor is on leave that day; cancel the leave first.")
        slot.status = "free"
        db.flush()
        from app.tools.waiting_list import offer_freed_slot

        offer_freed_slot(db, slot, now)
    db.flush()
    return {"slot_id": slot.id, "status": slot.status}


@write_tool("add_doctor_leave")
def add_doctor_leave(
    db: Session,
    actor: Actor,
    doctor_id: int,
    start_date: date,
    end_date: date,
    reason: str = "",
    now: datetime | None = None,
) -> dict:
    """Leave from tomorrow onwards (today's absence is "unavailable today" on the queue). Free slots are
    blocked; booked patients are told and may rebook free of charge."""
    require_role(actor, "staff", "admin")
    now = resolve_now(now)
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise ToolError("NOT_FOUND", f"Doctor {doctor_id} does not exist.")
    if start_date <= now.date():
        raise ToolError("VALIDATION_ERROR", "Leave can start tomorrow at the earliest; use 'Unavailable today'.")
    if end_date < start_date:
        raise ToolError("VALIDATION_ERROR", "The last day of leave is before the first.")
    if (end_date - start_date).days + 1 > MAX_LEAVE_DAYS:
        raise ToolError("VALIDATION_ERROR", f"Leave can cover at most {MAX_LEAVE_DAYS} days at a time.")
    overlap = db.scalars(
        select(DoctorLeave.id).where(
            DoctorLeave.doctor_id == doctor_id, DoctorLeave.end_date >= start_date, DoctorLeave.start_date <= end_date
        )
    ).first()
    if overlap is not None:
        raise ToolError("DUPLICATE", "This leave overlaps leave already recorded for the doctor.")

    leave = DoctorLeave(
        doctor_id=doctor_id, start_date=start_date, end_date=end_date, reason=reason.strip()[:120],
        created_by=actor.user_id, created_at=now,
    )  # fmt: skip
    db.add(leave)
    lo, hi = at(start_date, time.min), at(end_date + timedelta(days=1), time.min)
    slots = list(
        db.scalars(
            select(Slot)
            .where(Slot.doctor_id == doctor_id, Slot.start_at >= lo, Slot.start_at < hi)
            .order_by(Slot.id)
            .with_for_update()
        )
    )
    for slot in slots:
        slot.status = "blocked"
        slot.held_for_patient_id = None
        slot.held_until = None
    affected = []
    for appt in db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.appt_date >= start_date,
            Appointment.appt_date <= end_date,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        )
    ):
        appt.status = "displaced"
        appt.updated_at = now
        notify(
            db,
            appt.patient_id,
            f"{doctor.name} is on leave on {appt.appt_date:%d %b}. We are sorry. Please choose a new time in "
            "CareFlow (My appointments → Reschedule); rescheduling is free of charge.",
            now,
            kind="unavailable",
            appointment_id=appt.id,
        )
        affected.append({"appointment_id": appt.id, "patient_id": appt.patient_id})
    db.flush()
    return {**_leave_dict(leave), "slots_blocked": len(slots), "affected": affected}


@write_tool("cancel_doctor_leave")
def cancel_doctor_leave(db: Session, actor: Actor, leave_id: int, now: datetime | None = None) -> dict:
    """Remove future leave and reopen its blocked slots. Patients already moved keep their new times;
    appointments still waiting to be rebooked stay so (they were told the doctor is away)."""
    require_role(actor, "staff", "admin")
    now = resolve_now(now)
    leave = db.get(DoctorLeave, leave_id)
    if leave is None:
        raise ToolError("NOT_FOUND", f"Leave {leave_id} does not exist.")
    if leave.end_date <= now.date():
        raise ToolError("INVALID_STATE", "This leave has already passed.")
    first = max(leave.start_date, now.date() + timedelta(days=1))
    lo, hi = at(first, time.min), at(leave.end_date + timedelta(days=1), time.min)
    reopened = 0
    held_by_displaced = select(Appointment.slot_id).where(Appointment.status == "displaced")
    for slot in db.scalars(
        select(Slot)
        .where(
            Slot.doctor_id == leave.doctor_id,
            Slot.start_at >= lo,
            Slot.start_at < hi,
            Slot.status == "blocked",
            Slot.start_at > now + policy.BOOKING_LEAD,
            Slot.id.not_in(held_by_displaced),
        )
        .with_for_update()
    ):
        slot.status = "free"
        reopened += 1
    result = {**_leave_dict(leave), "slots_reopened": reopened}
    db.delete(leave)
    db.flush()
    return result
