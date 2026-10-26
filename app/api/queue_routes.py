"""Queue endpoints (docs §7) and the live WebSocket. Staff run the front desk, doctors run their own
queue; patients and linked caregivers can follow their own entry and join a queue online."""

import asyncio
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import verify_token
from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.db.models import Department, Doctor, QueueEntry, QueueSession
from app.db.session import session_factory
from app.queue import engine
from app.queue.broadcast import broadcaster, session_messages
from app.queue.coordination import department_board, virtual_queue_options
from app.queue.merge import effective_priority
from app.queue.predictions import latest_estimate
from app.timeutil import now_ist
from app.tools.errors import ToolError
from app.tools.permissions import can_manage_patient, require_queue_control, require_role
from app.tools.registration import categories
from app.tools.timetable import holds_opd

router = APIRouter(prefix="/api/v1/queue", tags=["queue"])
ws_router = APIRouter()


def _publish(db: Session, session_id: int) -> None:
    broadcaster.publish(session_id, session_messages(db, session_id, now_ist()))


def _write_and_publish(db: Session, fn, session_id_of) -> dict:
    result = run_and_commit(db, fn)
    ids = session_id_of(result)
    for session_id in ids if isinstance(ids, list | tuple | set) else [ids]:
        if session_id is not None:
            _publish(db, session_id)
    return result


# --------------------------------------------------------------------------- reads


@router.get("/sessions")
def sessions(
    day: date | None = Query(None, alias="date"), auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    """Today's (or a given day's) doctor sessions, for the front desk and the dashboard."""
    require_role(auth.actor, "staff", "admin")
    day = day or now_ist().date()
    rows = db.execute(
        select(QueueSession, Doctor).join(Doctor, Doctor.id == QueueSession.doctor_id).where(QueueSession.date == day)
    ).all()
    out = []
    for s, d in sorted(rows, key=lambda r: r[1].name):
        waiting = db.scalars(
            select(QueueEntry.id).where(QueueEntry.session_id == s.id, QueueEntry.status == "waiting")
        ).all()
        out.append(
            {
                "session_id": s.id,
                "doctor_id": d.id,
                "doctor_name": d.name,
                "department": d.department.name,
                "status": s.status,
                "doctor_status": s.doctor_status,
                "merge_rule": s.merge_rule,
                "waiting": len(waiting),
            }
        )
    return {"date": day.isoformat(), "sessions": out}


def _detail(db: Session, session_id: int) -> dict:
    snapshot = engine.session_snapshot(db, session_id)
    now = now_ist()
    weights = engine.priority_weights(db)
    session = db.get(QueueSession, session_id)
    start = engine.projection_start(session, now)
    requests = {r["entry_id"]: r for r in engine.pending_priority_requests(db, session_id)}
    for entry in snapshot["entries"]:
        e = db.get(QueueEntry, entry["entry_id"])
        entry["patient_name"] = e.patient.synthetic_name
        entry["categories"] = categories(e.patient, now.year)  # feature 30
        entry["effective_priority"] = effective_priority(
            e.priority, entry["categories"], weights, engine.category_due(e, start)
        )
        entry["estimate"] = latest_estimate(db, e.id, now) if e.status == "waiting" else None
        entry["pending_request"] = requests.get(e.id)
    snapshot["doctor_name"] = session.doctor.name
    snapshot["department"] = session.doctor.department.name
    snapshot["doctor_status"] = session.doctor_status
    snapshot["delay_minutes"] = session.delay_minutes
    snapshot["busy_until"] = session.busy_until.isoformat() if session.busy_until else None
    snapshot["priority_requests"] = list(requests.values())
    return snapshot


@router.get("/sessions/{session_id}")
def session_detail(session_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Full queue with patient names: the front desk, or the doctor whose queue it is."""
    require_role(auth.actor, "staff", "doctor")
    session = db.get(QueueSession, session_id)
    if session is None:
        raise ToolError("NOT_FOUND", "Queue session not found.")
    require_queue_control(auth.actor, session.doctor_id)
    return _detail(db, session_id)


@router.get("/doctor/today")
def doctor_today(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """The signed-in doctor's own queue today, and where they can forward a patient (features 43, 52)."""
    require_role(auth.actor, "doctor")
    doctor = db.get(Doctor, auth.actor.doctor_id)
    day = now_ist().date()
    session = db.scalars(
        select(QueueSession).where(QueueSession.doctor_id == doctor.id, QueueSession.date == day)
    ).first()
    if session is None and holds_opd(db, doctor, day):
        session = run_and_commit(db, lambda: engine.get_or_create_session(db, doctor.id, day))
    others = [
        {"doctor_id": d.id, "name": d.name, "department": d.department.name}
        for d in db.scalars(select(Doctor).join(Department).order_by(Department.name, Doctor.name))
        if d.id != doctor.id and holds_opd(db, d, day)
    ]
    return {
        "doctor_id": doctor.id,
        "doctor_name": doctor.name,
        "department": doctor.department.name,
        "date": day.isoformat(),
        "session": _detail(db, session.id) if session else None,
        "forward_to": others,
    }


@router.get("/coordination")
def coordination(
    department_id: int | None = None, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    """Every doctor's queue per department side by side, with balancing suggestions (features 44, 54)."""
    require_role(auth.actor, "staff", "admin")
    return department_board(db, now_ist(), department_id)


@router.get("/virtual/options")
def virtual_options(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Doctors a patient can join online today, with queue lengths (feature 38)."""
    require_role(auth.actor, "patient", "caregiver")
    return virtual_queue_options(db, now_ist())


@router.get("/entries/{entry_id}/status")
def entry_status(entry_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Position, people ahead and the wait estimate with its range (polling fallback for the live page)."""
    return engine.get_queue_status(db, auth.actor, entry_id)


@router.get("/mine")
def my_entries(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Today's queue entries for the signed-in patient or the caregiver's linked patients."""
    return {"entries": engine.active_entries_for(db, auth.actor, now_ist())}


# --------------------------------------------------------------------------- front desk (staff)


class WalkInRequest(BaseModel):
    doctor_id: int
    patient_id: int | None = None
    name: str | None = Field(None, max_length=120)
    birth_year: int | None = None
    phone: str | None = Field(None, max_length=20)
    language: Literal["en", "hi", "mr"] = "en"
    answers: dict[str, str] | None = None


class EventRequest(BaseModel):
    type: Literal["break", "delay", "emergency", "resume", "unavailable"]
    minutes: int | None = None
    reason: str | None = Field(None, max_length=200)
    reassign: bool = False  # with "unavailable": move waiting patients to colleagues in the department


class PriorityRequest(BaseModel):
    priority: int


class PriorityAsk(BaseModel):
    priority: int
    reason: str = Field(max_length=200)


class Decision(BaseModel):
    approve: bool


class TransferRequest(BaseModel):
    doctor_id: int
    reason: str | None = Field(None, max_length=200)


class JoinRequest(BaseModel):
    doctor_id: int
    patient_id: int


@router.post("/walk-ins", status_code=201)
def walk_in(body: WalkInRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return _write_and_publish(
        db,
        lambda: engine.register_walk_in(
            db,
            auth.actor,
            body.doctor_id,
            body.patient_id,
            body.name,
            body.birth_year,
            body.phone,
            body.language,
            answers=body.answers,
        ),  # fmt: skip
        lambda r: r["session_id"],
    )


@router.post("/entries/{appointment_id}/check-in", status_code=201)
def check_in(appointment_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Check in a booked appointment; the queue entry is created here, so the id is the appointment's."""
    return _write_and_publish(db, lambda: engine.check_in(db, auth.actor, appointment_id), lambda r: r["session_id"])


@router.post("/sessions/{session_id}/call-next")
def call_next(session_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    called = _write_and_publish(db, lambda: engine.call_next(db, auth.actor, session_id), lambda r: session_id)
    return {"called": called}


@router.patch("/entries/{entry_id}/priority")
def priority(
    entry_id: int, body: PriorityRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    """The patient's doctor sets the priority directly (feature 52)."""
    return _write_and_publish(
        db, lambda: engine.set_priority(db, auth.actor, entry_id, body.priority), lambda r: r["session_id"]
    )


@router.post("/entries/{entry_id}/priority-requests", status_code=201)
def ask_priority(
    entry_id: int, body: PriorityAsk, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    """The front desk asks the doctor to change a patient's priority."""
    return _write_and_publish(
        db,
        lambda: engine.request_priority(db, auth.actor, entry_id, body.priority, body.reason),
        lambda r: r["session_id"],
    )


@router.post("/priority-requests/{request_id}")
def decide_priority(
    request_id: int, body: Decision, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return _write_and_publish(
        db,
        lambda: engine.decide_priority_request(db, auth.actor, request_id, body.approve),
        lambda r: r["session_id"],
    )


@router.post("/entries/{entry_id}/transfer")
def transfer(
    entry_id: int, body: TransferRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    """Move a patient to another doctor today (features 42, 43, 53)."""
    return _write_and_publish(
        db,
        lambda: engine.transfer_entry(db, auth.actor, entry_id, body.doctor_id, body.reason),
        lambda r: [r["from_session_id"], r["session_id"]],
    )


@router.post("/virtual/join", status_code=201)
def join_queue(body: JoinRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return _write_and_publish(
        db,
        lambda: engine.join_virtual_queue(db, auth.actor, body.doctor_id, body.patient_id),
        lambda r: r["session_id"],
    )


# Registered after the fixed paths above (transfer, priority-requests) so they are matched first.
@router.post("/entries/{entry_id}/{action}")
def entry_action(
    entry_id: int,
    action: Literal["start", "end", "missed", "return", "arrived", "left"],
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    fn = {
        "start": engine.start_consultation,
        "end": engine.end_consultation,
        "missed": engine.mark_missed_turn,
        "return": engine.mark_returned,
        "arrived": engine.mark_arrived,
        "left": engine.mark_left,
    }[action]
    return _write_and_publish(db, lambda: fn(db, auth.actor, entry_id), lambda r: r["session_id"])


@router.post("/sessions/{session_id}/events")
def doctor_event(
    session_id: int, body: EventRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return _write_and_publish(
        db,
        lambda: engine.record_doctor_event(
            db, auth.actor, session_id, body.type, body.minutes, body.reason, reassign=body.reassign
        ),
        lambda r: [session_id, *{m["session_id"] for m in r.get("moved", [])}],
    )


@router.post("/sessions/{session_id}/close")
def close(session_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return _write_and_publish(db, lambda: engine.close_session(db, auth.actor, session_id), lambda r: session_id)


# --------------------------------------------------------------------------- WebSocket


@ws_router.websocket("/ws/queue/{session_id}")
async def queue_socket(websocket: WebSocket, session_id: int, token: str = "") -> None:
    """Pushes queue.updated, prediction.updated and doctor.status for one doctor's session.

    Authenticate with ?token=<bearer token>. Patients may follow a session they are queued in, doctors
    their own; staff and admins may follow any session.
    """
    with session_factory()() as db:
        try:
            actor, _, _ = verify_token(db, token)
        except ToolError:
            await websocket.close(code=4401)
            return
        session = db.get(QueueSession, session_id)
        allowed = session is not None and (
            actor.role in ("staff", "admin")
            or (actor.role == "doctor" and actor.doctor_id == session.doctor_id)
            or any(
                can_manage_patient(db, actor, e.patient_id)
                for e in db.scalars(select(QueueEntry).where(QueueEntry.session_id == session_id))
            )
        )
        if not allowed:
            await websocket.close(code=4403)
            return
        initial = session_messages(db, session_id, now_ist())
    await websocket.accept()
    queue = broadcaster.subscribe(session_id)

    async def pump() -> None:
        while True:
            await websocket.send_json(await queue.get())

    async def listen() -> None:
        while True:  # clients send nothing; this only notices when they leave
            await websocket.receive_text()

    try:
        for message in initial:
            await websocket.send_json(message)
        tasks = [asyncio.create_task(pump()), asyncio.create_task(listen())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            if not isinstance(task.exception(), WebSocketDisconnect | None):
                raise task.exception()
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe(session_id, queue)
