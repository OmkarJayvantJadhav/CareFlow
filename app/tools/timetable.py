"""OPD slots from each doctor's timetable: created ahead of time, and rebuilt when an admin changes it (phase 7B).

A timetable is the department's OPD hours, the doctor's OPD weekdays, slot length and last day. Changing it
never cancels a booking: from tomorrow, free slots that are not on the new timetable are retired (kept for
history, never offered), the new slots are created around the bookings and blocked times that remain, and
the bookings that now fall outside the timetable are reported so staff can contact those patients. Today's
OPD runs as it was planned.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Doctor, Slot
from app.timeutil import at, to_ist

SLOT_DAYS_AHEAD = 21  # slots exist for today and the next 20 days; the 30-day booking window fills as days pass


def current_doctor(day: date) -> ColumnElement[bool]:
    """SQL: the doctor has not left by that day."""
    return or_(Doctor.last_day.is_(None), Doctor.last_day >= day)


def _overlaps(busy: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
    return any(s < end and start < e for s, e in busy)


def on_timetable(doctor: Doctor, slot: Slot) -> bool:
    """Whether a slot is one the doctor's current timetable would create."""
    start, end = to_ist(slot.start_at), to_ist(slot.end_at)
    if not doctor.works_on(start.date()):
        return False
    dept = doctor.department
    opens, closes = at(start.date(), dept.opd_start), at(start.date(), dept.opd_end)
    minutes = (start - opens).total_seconds() / 60
    return (
        opens <= start
        and end <= closes
        and minutes % doctor.slot_minutes == 0
        and end - start == timedelta(minutes=doctor.slot_minutes)
    )


def holds_opd(db: Session, doctor: Doctor, day: date) -> bool:
    """Whether the doctor sees patients that day: by the timetable, or by slots made before it changed
    (a change applies from tomorrow, so today runs as planned). Leave is separate."""
    if doctor.last_day is not None and day > doctor.last_day:
        return False
    if day.isoweekday() in doctor.opd_days:
        return True
    return (
        db.scalar(
            select(Slot.id)
            .where(
                Slot.doctor_id == doctor.id,
                Slot.start_at >= at(day, time.min),
                Slot.start_at < at(day + timedelta(days=1), time.min),
                Slot.status != "retired",
            )
            .limit(1)
        )
        is not None
    )


def ensure_slots(db: Session, start: date, end: date, doctor_ids: list[int] | None = None) -> int:
    """Create every timetabled slot between two dates (inclusive) that does not exist yet.

    Existing slots are kept; a new slot is not created where it would overlap a kept one (a booking or a
    blocked time from an earlier timetable). A retired slot at exactly the right time is reused.
    """
    from app.tools.calendar import leave_days

    lo, hi = at(start, time.min), at(end + timedelta(days=1), time.min)
    query = select(Slot).where(Slot.start_at >= lo, Slot.start_at < hi)
    doctors_q = select(Doctor).order_by(Doctor.id)
    if doctor_ids is not None:
        query = query.where(Slot.doctor_id.in_(doctor_ids))
        doctors_q = doctors_q.where(Doctor.id.in_(doctor_ids))
    by_start: dict[tuple[int, datetime], Slot] = {}
    busy: dict[tuple[int, date], list[tuple[datetime, datetime]]] = defaultdict(list)
    for slot in db.scalars(query):
        by_start[(slot.doctor_id, slot.start_at)] = slot
        if slot.status != "retired":
            busy[(slot.doctor_id, to_ist(slot.start_at).date())].append((slot.start_at, slot.end_at))

    away = leave_days(db, start, end)  # slots created on a leave day start blocked
    created = 0
    for doctor in db.scalars(doctors_q):
        dept = doctor.department
        step = timedelta(minutes=doctor.slot_minutes)
        day = start
        while day <= end:
            if doctor.works_on(day):
                taken = busy[(doctor.id, day)]
                status = "blocked" if (doctor.id, day) in away else "free"
                t, close = at(day, dept.opd_start), at(day, dept.opd_end)
                while t + step <= close:
                    existing = by_start.get((doctor.id, t))
                    if existing is not None and existing.status != "retired":
                        pass  # already there
                    elif not _overlaps(taken, t, t + step):
                        if existing is None:
                            db.add(Slot(doctor_id=doctor.id, start_at=t, end_at=t + step, status=status))
                        else:
                            existing.end_at, existing.status = t + step, status
                        taken.append((t, t + step))
                        created += 1
                    t += step
            day += timedelta(days=1)
    db.flush()
    return created


def top_up_slots(db: Session, today: date, days_ahead: int = SLOT_DAYS_AHEAD) -> int:
    """Keep the next ``days_ahead`` days bookable on a long-running deployment (only missing slots are added)."""
    return ensure_slots(db, today, today + timedelta(days=days_ahead - 1))


def rebuild_slots(db: Session, doctor_ids: list[int], now: datetime) -> dict:
    """Apply changed timetables from tomorrow. Returns the slots retired and created, and the bookings
    that are kept although they are no longer on the timetable."""
    if not doctor_ids:
        return {"from": None, "retired": 0, "created": 0, "outside": []}
    first = now.date() + timedelta(days=1)
    retired = 0
    for slot in db.scalars(
        select(Slot)
        .where(Slot.doctor_id.in_(doctor_ids), Slot.start_at >= at(first, time.min), Slot.status == "free")
        .with_for_update()
    ):
        if slot.held_until is not None and slot.held_until > now:
            continue  # offered to a waiting-list patient: the offer stands until it lapses
        slot.status = "retired"
        retired += 1
    db.flush()
    created = ensure_slots(db, first, now.date() + timedelta(days=SLOT_DAYS_AHEAD - 1), doctor_ids)
    return {
        "from": first.isoformat(),
        "retired": retired,
        "created": created,
        "outside": off_timetable(db, doctor_ids, first),
    }


def off_timetable(db: Session, doctor_ids: list[int], first: date) -> list[dict]:
    """Bookings from ``first`` on that the doctors' current timetables would not have."""
    out = []
    for appt in db.scalars(
        select(Appointment)
        .where(
            Appointment.doctor_id.in_(doctor_ids),
            Appointment.appt_date >= first,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        )
        .order_by(Appointment.appt_date, Appointment.id)
    ):
        if not on_timetable(appt.doctor, appt.slot):
            start = to_ist(appt.slot.start_at)
            out.append(
                {
                    "appointment_id": appt.id,
                    "doctor_name": appt.doctor.name,
                    "patient_name": appt.patient.synthetic_name,
                    "date": start.date().isoformat(),
                    "time": start.strftime("%H:%M"),
                }
            )
    return out
