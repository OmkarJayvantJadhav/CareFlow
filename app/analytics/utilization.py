"""Appointment utilization and attendance (features 15 and 16) for the admin dashboard.

* Utilization: booked share of the bookable slots (free + booked; blocked slots are not offered) from
  today for the next ``days`` days, per department and doctor.
* Attendance: of the appointments that took place in the last 30 days, the share that were attended
  (completed) rather than missed (no-show); cancellations are counted separately.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Appointment, Department, Doctor, QueueEntry, Slot
from app.timeutil import at
from app.tools.calendar import consult_minutes

ATTENDANCE_DAYS = 30


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def utilization(db: Session, now: datetime, days: int = 7) -> dict:
    days = max(1, min(days, 30))
    today = now.date()
    lo, hi = at(today, time.min), at(today + timedelta(days=days), time.min)
    slot_counts = db.execute(
        select(Slot.doctor_id, Slot.status, func.count())
        .where(Slot.start_at >= lo, Slot.start_at < hi)
        .group_by(Slot.doctor_id, Slot.status)
    ).all()
    since = today - timedelta(days=ATTENDANCE_DAYS)
    outcome_counts = db.execute(
        select(Appointment.doctor_id, Appointment.status, func.count())
        .where(Appointment.appt_date >= since, Appointment.appt_date < today)
        .group_by(Appointment.doctor_id, Appointment.status)
    ).all()
    slots: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for doctor_id, status, n in slot_counts:
        slots[doctor_id][status] = n
    outcomes: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for doctor_id, status, n in outcome_counts:
        outcomes[doctor_id][status] = n

    doctors = list(db.scalars(select(Doctor).join(Department).order_by(Department.name, Doctor.name)))
    durations = consult_minutes(db, [d.id for d in doctors], now)
    rows, by_dept = [], defaultdict(lambda: defaultdict(int))
    for d in doctors:
        s, o = slots[d.id], outcomes[d.id]
        bookable = s["free"] + s["booked"]
        row = {
            "doctor_id": d.id,
            "doctor_name": d.name,
            "department": d.department.name,
            "booked": s["booked"],
            "free": s["free"],
            "blocked": s["blocked"],
            "utilization": _rate(s["booked"], bookable),
            "attended": o["completed"],
            "no_shows": o["no_show"],
            "cancelled": o["cancelled"],
            "attendance_rate": _rate(o["completed"], o["completed"] + o["no_show"]),
            "typical_consult_min": durations[d.id]["typical"],
        }
        rows.append(row)
        dept = by_dept[d.department.name]
        for key in ("booked", "free", "blocked", "attended", "no_shows", "cancelled"):
            dept[key] += row[key]
    departments = [
        {
            "department": name,
            **counts,
            "utilization": _rate(counts["booked"], counts["booked"] + counts["free"]),
            "attendance_rate": _rate(counts["attended"], counts["attended"] + counts["no_shows"]),
        }
        for name, counts in sorted(by_dept.items())
    ]
    # Late arrivals (feature 33): booked patients who checked in after their slot had started.
    arrivals = db.execute(
        select(func.count(), func.count(QueueEntry.late_minutes))
        .select_from(QueueEntry)
        .where(
            QueueEntry.kind == "booked",
            QueueEntry.checked_in_at >= at(since, time.min),
            QueueEntry.checked_in_at < at(today + timedelta(days=1), time.min),
        )
    ).one()
    total_booked = sum(r["booked"] for r in rows)
    total_free = sum(r["free"] for r in rows)
    attended = sum(r["attended"] for r in rows)
    no_shows = sum(r["no_shows"] for r in rows)
    return {
        "window": {"from": today.isoformat(), "days": days},
        "attendance_window_days": ATTENDANCE_DAYS,
        "overall": {
            "utilization": _rate(total_booked, total_booked + total_free),
            "attendance_rate": _rate(attended, attended + no_shows),
            "no_show_rate": _rate(no_shows, attended + no_shows),
            "late_arrival_rate": _rate(arrivals[1], arrivals[0]),
        },
        "departments": departments,
        "doctors": rows,
    }
