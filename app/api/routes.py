"""REST endpoints (docs §7). They call the same service functions as the agent tools."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.chat import actor_patients, handle_chat, session_message_count
from app.agent.llm import LLM
from app.analytics.agent import answer_question
from app.api.auth import issue_token
from app.api.deps import Auth, SlidingWindowLimiter, client_key, get_auth, get_db, get_llm, run_and_commit
from app.config import get_settings
from app.db.models import AppUser
from app.timeutil import iso, now_ist
from app.tools import booking, waiting_list
from app.tools.errors import ToolError
from app.tools.permissions import Actor

router = APIRouter(prefix="/api/v1")
DEMO_USERS_BY_ROLE = {"patient": "asha", "caregiver": "rajan", "staff": "priya", "admin": "mehta"}
chat_limiter = SlidingWindowLimiter(3600)


# --------------------------------------------------------------------------- auth


class LoginRequest(BaseModel):
    role: Literal["patient", "caregiver", "staff", "admin"] | None = None
    username: str | None = Field(None, max_length=60)


def _user_view(db: Session, user: AppUser) -> dict:
    patients = actor_patients(db, Actor.from_user(user))
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "patient_id": user.patient_id,
        "patients": [{"patient_id": pid, "name": name} for pid, name in patients.items()],
    }


@router.post("/auth/demo-login", tags=["auth"])
def demo_login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    """Get a token for one of the demo accounts (by role or username)."""
    if not get_settings().demo_mode:
        raise ToolError("FORBIDDEN", "Demo login is disabled.")
    username = body.username or DEMO_USERS_BY_ROLE.get(body.role or "")
    if not username or username == "sim-desk":
        raise ToolError("VALIDATION_ERROR", "Give a demo role or username.")
    user = db.scalars(select(AppUser).where(AppUser.username == username)).first()
    if user is None:
        raise ToolError("VALIDATION_ERROR", f"There is no demo account called {username!r}.")
    token, expires = issue_token(user)
    return {"token": token, "token_type": "bearer", "expires_at": iso(expires), "user": _user_view(db, user)}


@router.get("/me", tags=["auth"])
def me(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return _user_view(db, db.get(AppUser, auth.actor.user_id))


# --------------------------------------------------------------------------- chat


class ChatRequest(BaseModel):
    conversation_id: str | None = Field(None, max_length=64)
    message: str = Field("", max_length=4000)
    confirm_action_id: str | None = Field(None, max_length=64)
    language: Literal["en", "hi", "mr"] | None = None


@router.post("/chat", tags=["chat"])
def chat(
    body: ChatRequest,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
    llm: LLM = Depends(get_llm),
) -> dict:
    """Send a message; returns the reply, citations, actions taken and any confirmation card."""
    settings = get_settings()
    if session_message_count(db, auth.session_id) >= settings.max_messages_per_session:
        retry_after = max(1, int((auth.expires_at - now_ist()).total_seconds()))
        raise ToolError(
            "RATE_LIMITED",
            f"This demo session has reached its limit of {settings.max_messages_per_session} messages.",
            retry_after=retry_after,
        )
    chat_limiter.check(client_key(request), settings.max_messages_per_ip_per_hour)
    reply = run_and_commit(
        db,
        lambda: handle_chat(
            db,
            auth.actor,
            auth.session_id,
            body.message,
            llm,
            conversation_id=body.conversation_id,
            confirm_action_id=body.confirm_action_id,
            language_hint=body.language,
        ),
    )
    return reply.to_dict()


# --------------------------------------------------------------------------- doctors and slots


@router.get("/doctors", tags=["booking"])
def doctors(
    specialty: str | None = Query(None, max_length=60),
    language: str | None = Query(None, max_length=20),
    day: str | None = Query(None, max_length=20),
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    return booking.search_doctors(db, specialty, language, day)


@router.get("/doctors/{doctor_id}/slots", tags=["booking"])
def slots(
    doctor_id: int,
    date_: date = Query(..., alias="date"),
    patient_id: int | None = None,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    return booking.check_availability(db, doctor_id, date_, patient_id=patient_id or auth.actor.patient_id)


# --------------------------------------------------------------------------- appointments


class BookRequest(BaseModel):
    patient_id: int
    slot_id: int
    confirmed: bool = False


class RescheduleRequest(BaseModel):
    new_slot_id: int
    confirmed: bool = False


class WaitingListRequest(BaseModel):
    patient_id: int
    doctor_id: int
    dates: list[date] = Field(min_length=1, max_length=7)
    confirmed: bool = False


@router.post("/appointments", status_code=201, tags=["booking"])
def book(body: BookRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(
        db, lambda: booking.book_appointment(db, auth.actor, body.patient_id, body.slot_id, confirmed=body.confirmed)
    )


@router.patch("/appointments/{appointment_id}", tags=["booking"])
def reschedule(
    appointment_id: int, body: RescheduleRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db,
        lambda: booking.reschedule_appointment(
            db, auth.actor, appointment_id, body.new_slot_id, confirmed=body.confirmed
        ),
    )


@router.delete("/appointments/{appointment_id}", tags=["booking"])
def cancel(
    appointment_id: int, confirmed: bool = False, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(db, lambda: booking.cancel_appointment(db, auth.actor, appointment_id, confirmed=confirmed))


@router.get("/patients/{patient_id}/appointments", tags=["booking"])
def history(patient_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return booking.get_patient_appointments(db, auth.actor, patient_id)


@router.post("/waiting-list", status_code=201, tags=["booking"])
def join_list(body: WaitingListRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(
        db,
        lambda: waiting_list.join_waiting_list(
            db, auth.actor, body.patient_id, body.doctor_id, body.dates, confirmed=body.confirmed
        ),
    )


# --------------------------------------------------------------------------- admin analytics


class AnalyticsRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.post("/admin/analytics", tags=["admin"])
def analytics(
    body: AnalyticsRequest,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
    llm: LLM = Depends(get_llm),
) -> dict:
    """Answer an admin's question with one validated, read-only SELECT; 422 UNSAFE_QUERY otherwise."""
    if auth.actor.role != "admin":
        raise ToolError("FORBIDDEN", "Analytics questions are available to admins only.")
    chat_limiter.check(client_key(request), get_settings().max_messages_per_ip_per_hour)
    return answer_question(db, auth.actor, body.question, llm).to_dict()
