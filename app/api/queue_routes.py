"""Queue endpoints (docs §7) and the live WebSocket. Staff run the front desk; patients and
linked caregivers can read their own entry's status."""

import asyncio
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import verify_token
from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.db.models import Doctor, QueueEntry, QueueSession
from app.db.session import session_factory
from app.queue import engine
from app.queue.broadcast import broadcaster, session_messages
from app.queue.predictions import latest_estimate
from app.timeutil import now_ist
from app.tools.errors import ToolError
from app.tools.permissions import can_manage_patient, require_role
from app.tools.registration import categories

router = APIRouter(prefix="/api/v1/queue", tags=["queue"])
ws_router = APIRouter()


def _publish(db: Session, session_id: int) -> None:
    broadcaster.publish(session_id, session_messages(db, session_id, now_ist()))


def _write_and_publish(db: Session, fn, session_id_of) -> dict:
    result = run_and_commit(db, fn)
    session_id = session_id_of(result)
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


@router.get("/sessions/{session_id}")
def session_detail(session_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Full queue with patient names (staff only)."""
    require_role(auth.actor, "staff")
    snapshot = engine.session_snapshot(db, session_id)
    now = now_ist()
    for entry in snapshot["entries"]:
        e = db.get(QueueEntry, entry["entry_id"])
        entry["patient_name"] = e.patient.synthetic_name
        entry["categories"] = categories(e.patient, now.year)  # feature 30
        entry["estimate"] = latest_estimate(db, e.id, now) if e.status == "waiting" else None
    return snapshot


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


class PriorityRequest(BaseModel):
    priority: int


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


@router.post("/entries/{entry_id}/{action}")
def entry_action(
    entry_id: int,
    action: Literal["start", "end", "missed", "return"],
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    fn = {
        "start": engine.start_consultation,
        "end": engine.end_consultation,
        "missed": engine.mark_missed_turn,
        "return": engine.mark_returned,
    }[action]
    return _write_and_publish(db, lambda: fn(db, auth.actor, entry_id), lambda r: r["session_id"])


@router.patch("/entries/{entry_id}/priority")
def priority(
    entry_id: int, body: PriorityRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return _write_and_publish(
        db, lambda: engine.set_priority(db, auth.actor, entry_id, body.priority), lambda r: r["session_id"]
    )


@router.post("/sessions/{session_id}/events")
def doctor_event(
    session_id: int, body: EventRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return _write_and_publish(
        db,
        lambda: engine.record_doctor_event(db, auth.actor, session_id, body.type, body.minutes, body.reason),
        lambda r: session_id,
    )


@router.post("/sessions/{session_id}/close")
def close(session_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return _write_and_publish(db, lambda: engine.close_session(db, auth.actor, session_id), lambda r: session_id)


# --------------------------------------------------------------------------- WebSocket


@ws_router.websocket("/ws/queue/{session_id}")
async def queue_socket(websocket: WebSocket, session_id: int, token: str = "") -> None:
    """Pushes queue.updated, prediction.updated and doctor.status for one doctor's session.

    Authenticate with ?token=<bearer token>. Patients may follow a session they are queued in;
    staff and admins may follow any session.
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
