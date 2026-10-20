"""REST endpoints (docs §7). They call the same service functions as the agent tools."""

import re
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.chat import actor_patients, handle_chat, session_message_count
from app.agent.llm import LLM
from app.analytics.agent import answer_question
from app.api.auth import issue_token
from app.api.deps import Auth, SlidingWindowLimiter, client_key, get_auth, get_db, get_llm, run_and_commit
from app.api.passwords import DUMMY_HASH, hash_password, verify_password
from app.config import get_settings
from app.db.models import AppUser, Patient
from app.safety.privacy import mask_phone_number
from app.timeutil import iso, now_ist
from app.tools import booking, policy, waiting_list
from app.tools.errors import ToolError
from app.tools.permissions import Actor
from app.tools.receipts import reference_code

router = APIRouter(prefix="/api/v1")
DEMO_USERS_BY_ROLE = {"patient": "asha", "caregiver": "rajan", "staff": "priya", "admin": "mehta"}
chat_limiter = SlidingWindowLimiter(3600)
register_limiter = SlidingWindowLimiter(3600)
login_failures = SlidingWindowLimiter(900)
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")


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
    return _signed_in(db, user)


def _signed_in(db: Session, user: AppUser) -> dict:
    token, expires = issue_token(user)
    return {"token": token, "token_type": "bearer", "expires_at": iso(expires), "user": _user_view(db, user)}


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    birth_year: int
    phone: str = Field(max_length=20)
    language: Literal["en", "hi", "mr"] = "en"


class PasswordLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=128)


@router.post("/auth/register", tags=["auth"], status_code=201)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """Create a patient account (a patient record and its login) and sign in.

    The phone number is stored masked only (NFR-08), as for every patient.
    """
    settings = get_settings()
    if not settings.allow_registration:
        raise ToolError("FORBIDDEN", "New accounts cannot be created right now.")
    username = body.username.strip().lower()
    name = " ".join(body.name.split())
    if not USERNAME_RE.match(username):
        raise ToolError(
            "VALIDATION_ERROR",
            "Usernames are 3–30 characters: lowercase letters, digits, dots, dashes or underscores.",
        )
    if len(name) < 2:
        raise ToolError("VALIDATION_ERROR", "Please give your name.")
    this_year = now_ist().year
    if not 1900 <= body.birth_year <= this_year:
        raise ToolError("VALIDATION_ERROR", f"Birth year must be between 1900 and {this_year}.")
    digits = re.sub(r"\D", "", body.phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ToolError("VALIDATION_ERROR", "Enter a 10-digit Indian mobile number.")
    if body.password.strip() != body.password or len(set(body.password)) < 4:
        raise ToolError("VALIDATION_ERROR", "Choose a stronger password (at least 8 characters, not repetitive).")
    register_limiter.check(
        client_key(request), settings.max_registrations_per_ip_per_hour, "Too many new accounts; please try later."
    )
    if db.scalars(select(AppUser.id).where(AppUser.username == username)).first() is not None:
        raise ToolError("USERNAME_TAKEN", "That username is taken; please choose another.")
    patient = Patient(
        synthetic_name=name,
        birth_year=body.birth_year,
        phone_masked=mask_phone_number(digits),
        preferred_language=body.language,
    )
    db.add(patient)
    db.flush()
    user = AppUser(
        username=username,
        display_name=name,
        role="patient",
        patient_id=patient.id,
        password_hash=hash_password(body.password),
        self_registered=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:  # someone took the same username a moment ago
        db.rollback()
        raise ToolError("USERNAME_TAKEN", "That username is taken; please choose another.") from None
    result = _signed_in(db, user)
    db.commit()
    return result


@router.post("/auth/login", tags=["auth"])
def login(body: PasswordLoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """Sign in with a username and password. Repeated failures from one address are slowed down."""
    username = body.username.strip().lower()
    key = f"{client_key(request)}:{username}"
    limit = get_settings().max_failed_logins_per_15_min
    if login_failures.count(key) >= limit:
        login_failures.check(key, limit, "Too many failed sign-ins; please wait 15 minutes.")
    user = db.scalars(select(AppUser).where(AppUser.username == username)).first()
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or user.password_hash is None or not ok:
        login_failures.add(key)
        raise ToolError("INVALID_CREDENTIALS", "Wrong username or password.")
    return _signed_in(db, user)


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
    now = now_ist()
    result = booking.get_patient_appointments(db, auth.actor, patient_id, now=now)
    for appt in (*result["upcoming"], *result["past"]):
        appt["reference"] = reference_code(appt["appointment_id"])  # shown on the receipt (feature 20)
        # Whether the policy windows are still open, by the server's clock (the rules stay in the tools).
        left = datetime.fromisoformat(appt["start_at"]) - now
        displaced = appt["status"] == "displaced"
        active = appt["status"] in ("booked", "rescheduled") or displaced
        appt["can_reschedule"] = active and (displaced or left >= policy.RESCHEDULE_CUTOFF)
        appt["can_cancel"] = active and (displaced or left >= policy.CANCEL_CUTOFF)
    return result


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
