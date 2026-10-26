"""Multi-doctor queue coordination (feature 44): every doctor's queue in a department side by side, when
each is expected to finish, and balancing suggestions (feature 54)."""

from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Department, Doctor, QueueSession
from app.queue.balance import DoctorLoad, Waiting, suggest_moves
from app.timeutil import at, iso, to_ist
from app.tools import policy
from app.tools.calendar import consult_minutes, leave_days


def _state(session: QueueSession | None, on_leave: bool) -> str:
    if on_leave:
        return "on_leave"
    if session is None:
        return "not_started"
    if session.status == "closed":
        return "unavailable" if session.doctor_status == "unavailable" else "closed"
    return session.doctor_status


def department_board(db: Session, now: datetime, department_id: int | None = None) -> dict:
    day = now.date()
    away = leave_days(db, day, day)
    query = select(Department).order_by(Department.name)
    if department_id is not None:
        query = query.where(Department.id == department_id)
    departments = list(db.scalars(query))
    doctors = [
        d
        for d in db.scalars(select(Doctor).where(Doctor.department_id.in_([x.id for x in departments])))
        if day.isoweekday() in d.opd_days
    ]
    typical = consult_minutes(db, [d.id for d in doctors], now) if doctors else {}
    sessions = {
        s.doctor_id: s
        for s in db.scalars(
            select(QueueSession).where(QueueSession.date == day, QueueSession.doctor_id.in_([d.id for d in doctors]))
        )
    }
    out = []
    for dept in departments:
        opens, closes = at(day, dept.opd_start), at(day, dept.opd_end)
        rows, loads = [], []
        for doctor in sorted((d for d in doctors if d.department_id == dept.id), key=lambda d: d.name):
            session = sessions.get(doctor.id)
            state = _state(session, (doctor.id, day) in away)
            minutes = float(typical[doctor.id]["typical"])
            entries = list(session.entries) if session else []
            waiting = sorted((e for e in entries if e.status == "waiting"), key=lambda e: e.position or 0)
            in_room = next((e for e in entries if e.status in ("called", "in_consultation")), None)
            free_in = max(0.0, (opens - now).total_seconds() / 60)
            if session and session.busy_until and session.busy_until > now:
                free_in = max(free_in, (session.busy_until - now).total_seconds() / 60)
            if in_room is not None:
                started = in_room.consult_start or now
                free_in += max(minutes - (now - started).total_seconds() / 60, 1.0)
            accepting = state not in ("on_leave", "unavailable", "closed")
            load = DoctorLoad(
                doctor.id,
                doctor.name,
                minutes,
                free_in,
                accepting,
                [Waiting(e.id, e.token, e.kind == "walk_in" or e.transferred_from_id is not None) for e in waiting],
            )
            loads.append(load)
            finish = now + timedelta(minutes=load.finish_in()) if accepting else None
            rows.append(
                {
                    "doctor_id": doctor.id,
                    "doctor_name": doctor.name,
                    "session_id": session.id if session else None,
                    "state": state,
                    "delay_minutes": session.delay_minutes if session else 0,
                    "busy_until": iso(session.busy_until) if session else None,
                    "waiting": len(waiting),
                    "remote_not_arrived": sum(1 for e in waiting if e.joined_remotely and e.arrived_at is None),
                    "in_room": in_room.token if in_room else None,
                    "consult_minutes": round(minutes),
                    "seen": sum(1 for e in entries if e.status == "done"),
                    "left_unseen": sum(1 for e in entries if e.status == "left"),
                    "predicted_finish": iso(finish),
                    "overtime": bool(finish and finish > closes),
                }
            )
        out.append(
            {
                "department_id": dept.id,
                "department": dept.name,
                "floor": dept.floor,
                "opd_start": dept.opd_start.strftime("%H:%M"),
                "opd_end": dept.opd_end.strftime("%H:%M"),
                "doctors": rows,
                "suggestions": [m.to_dict() for m in suggest_moves(loads)],
            }
        )
    return {"date": day.isoformat(), "at": iso(now), "departments": out}


def virtual_queue_options(db: Session, now: datetime) -> dict:
    """What a patient sees before joining a queue online (feature 38): who is working today, how long the
    queue is and whether online joining is open. No other patient's details are included."""
    board = department_board(db, now)
    out = []
    for dept in board["departments"]:
        if not dept["doctors"]:
            continue
        opens = at(now.date(), time.fromisoformat(dept["opd_start"])) - policy.VIRTUAL_JOIN_OPENS
        closes = at(now.date(), time.fromisoformat(dept["opd_end"])) - policy.VIRTUAL_JOIN_CLOSES
        window_open = opens <= now <= closes
        doctors = []
        for d in dept["doctors"]:
            working = d["state"] not in ("on_leave", "unavailable", "closed")
            full = d["remote_not_arrived"] >= policy.VIRTUAL_QUEUE_CAP
            finish = datetime.fromisoformat(d["predicted_finish"]) if d["predicted_finish"] else None
            doctors.append(
                {
                    "doctor_id": d["doctor_id"],
                    "doctor_name": d["doctor_name"],
                    "state": d["state"],
                    "waiting": d["waiting"],
                    "estimated_wait_min": round(max(0.0, (finish - now).total_seconds() / 60)) if finish else None,
                    "full": full,
                    "can_join": working and window_open and not full,
                }
            )
        out.append(
            {
                "department_id": dept["department_id"],
                "department": dept["department"],
                "floor": dept["floor"],
                "opens": to_ist(opens).strftime("%H:%M"),
                "closes": to_ist(closes).strftime("%H:%M"),
                "window_open": window_open,
                "doctors": doctors,
            }
        )
    return {"date": board["date"], "departments": out}
