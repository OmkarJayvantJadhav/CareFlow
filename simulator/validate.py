"""Invariant checks for a replayed day: the Foundation phase gate."""

from collections import Counter
from datetime import date, time, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    Doctor,
    Notification,
    QueueEntry,
    QueueEvent,
    QueueSession,
)
from app.timeutil import at


def validate_day(db: Session, day: date) -> dict:
    violations: list[str] = []
    sessions = db.scalars(select(QueueSession).where(QueueSession.date == day).order_by(QueueSession.id)).all()
    working = [d for d in db.scalars(select(Doctor)) if day.isoweekday() in d.opd_days]
    if len(sessions) != len(working):
        violations.append(f"{len(working)} doctors work on {day} but {len(sessions)} sessions exist")

    waits: dict[str, list[float]] = {"booked": [], "walk_in": []}
    kinds, statuses, event_types = Counter(), Counter(), Counter()
    for session in sessions:
        if session.status != "closed":
            violations.append(f"session {session.id} is still open")
        entries = db.scalars(select(QueueEntry).where(QueueEntry.session_id == session.id)).all()
        consults = []
        for e in entries:
            kinds[e.kind] += 1
            statuses[e.status] += 1
            if e.status in ("waiting", "called", "in_consultation"):
                violations.append(f"entry {e.id} left in status {e.status}")
            if e.status == "done":
                if not (e.consult_start and e.consult_end and e.called_at):
                    violations.append(f"entry {e.id} is done without consultation times")
                    continue
                if not (e.checked_in_at <= e.called_at <= e.consult_start < e.consult_end):
                    violations.append(f"entry {e.id} has times out of order")
                if e.appointment is not None and e.appointment.status != "completed":
                    violations.append(f"entry {e.id} done but appointment is {e.appointment.status}")
                consults.append((e.consult_start, e.consult_end, e.id))
                waits[e.kind].append((e.consult_start - (e.requeued_at or e.checked_in_at)).total_seconds() / 60)
        consults.sort()
        for (_, e1, id1), (s2, _, id2) in zip(consults, consults[1:], strict=False):
            if s2 < e1:
                violations.append(f"consultations {id1} and {id2} overlap for one doctor")
        events = db.execute(
            select(QueueEvent.type, QueueEvent.at).where(QueueEvent.session_id == session.id).order_by(QueueEvent.id)
        ).all()
        for (_, t1), (_, t2) in zip(events, events[1:], strict=False):
            if t2 < t1:
                violations.append(f"session {session.id} has events out of time order")
                break
        event_types.update(t for t, _ in events)

    lingering = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.appt_date == day, Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES))
    )
    if lingering:
        violations.append(f"{lingering} appointments on {day} are still open after the day")
    double = db.execute(
        select(Appointment.slot_id)
        .where(Appointment.appt_date == day, Appointment.status.in_((*ACTIVE_APPOINTMENT_STATUSES, "completed")))
        .group_by(Appointment.slot_id)
        .having(func.count() > 1)
    ).all()
    if double:
        violations.append(f"{len(double)} slots have more than one appointment")

    appt_status = Counter(
        dict(
            db.execute(
                select(Appointment.status, func.count())
                .where(Appointment.appt_date == day)
                .group_by(Appointment.status)
            ).all()
        )
    )
    notifications = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.sent_at >= at(day, time.min), Notification.sent_at < at(day + timedelta(days=1), time.min))
    )
    return {
        "date": day.isoformat(),
        "sessions": len(sessions),
        "entries": dict(kinds),
        "entry_statuses": dict(statuses),
        "appointments": dict(appt_status),
        "events": dict(event_types),
        "patients_seen": statuses.get("done", 0),
        "wait_minutes": _summary(waits["booked"] + waits["walk_in"]),
        "wait_minutes_by_kind": {kind: _summary(values) for kind, values in waits.items()},
        "notifications": notifications,
        "violations": violations,
        "ok": not violations,
    }


def _summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p90": None, "max": None}
    w = np.array(values)
    return {
        "count": len(values),
        "mean": round(float(w.mean()), 1),
        "median": round(float(np.median(w)), 1),
        "p90": round(float(np.percentile(w, 90)), 1),
        "max": round(float(w.max()), 1),
    }
