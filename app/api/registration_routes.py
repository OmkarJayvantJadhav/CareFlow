"""Phase 6B endpoints: check-in by receipt code (front desk and kiosk), patient categories, duplicate
matching, custom registration fields, consent and caregiver access requests."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.api.queue_routes import _write_and_publish
from app.db.models import Appointment, QueueEntry
from app.queue import engine
from app.timeutil import now_ist, to_ist
from app.tools import registration
from app.tools.errors import ToolError
from app.tools.permissions import require_role
from app.tools.receipts import appointment_from_code

router = APIRouter(prefix="/api/v1")


# --------------------------------------------------------------------------- check-in by code (21, 27)


class CodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


def _appointment_for_code(db: Session, code: str) -> Appointment:
    appointment_id = appointment_from_code(code)
    appt = db.get(Appointment, appointment_id) if appointment_id else None
    if appt is None:
        raise ToolError("NOT_FOUND", "This code is not valid. Check it, or look the patient up by name.")
    return appt


@router.get("/staff/check-in/lookup", tags=["staff"])
def lookup_code(code: str, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """What a scanned or typed receipt code refers to, before checking the patient in."""
    require_role(auth.actor, "staff")
    appt = _appointment_for_code(db, code)
    now = now_ist()
    entry = db.scalars(select(QueueEntry).where(QueueEntry.appointment_id == appt.id)).first()
    start = to_ist(appt.slot.start_at)
    return {
        "appointment_id": appt.id,
        "patient_name": appt.patient.name,
        "first_name": appt.patient.name.split()[0],
        "categories": registration.categories(appt.patient, now.year),
        "doctor_name": appt.doctor.name,
        "department": appt.doctor.department.name,
        "floor": appt.doctor.department.floor,
        "date": start.date().isoformat(),
        "time": f"{start:%H:%M}",
        "status": appt.status,
        "today": appt.appt_date == now.date(),
        "token": entry.token if entry else None,
        "checked_in": entry is not None,
    }


@router.post("/staff/check-in/by-code", tags=["staff"], status_code=201)
def check_in_by_code(body: CodeRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    require_role(auth.actor, "staff")
    appt = _appointment_for_code(db, body.code)
    return _write_and_publish(db, lambda: engine.check_in(db, auth.actor, appt.id), lambda r: r["session_id"])


# --------------------------------------------------------------------------- categories and duplicates (30, 48)


class CategoryRequest(BaseModel):
    pregnant: bool
    disability: bool


class MatchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    birth_year: int
    phone: str | None = Field(None, max_length=20)


@router.patch("/staff/patients/{patient_id}/categories", tags=["staff"])
def set_categories(
    patient_id: int, body: CategoryRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db, lambda: registration.set_patient_categories(db, auth.actor, patient_id, body.pregnant, body.disability)
    )


@router.post("/staff/patients/match", tags=["staff"])
def match_patients(body: MatchRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return registration.find_duplicates(db, auth.actor, body.name, body.birth_year, body.phone)


# --------------------------------------------------------------------------- registration fields (26, 28)


class FieldRequest(BaseModel):
    labels: dict[str, str]
    kind: str = Field(max_length=10)
    options: list[str] = Field(default_factory=list, max_length=10)
    required: bool = False
    active: bool = True


@router.get("/registration-fields", tags=["registration"])
def active_fields(db: Session = Depends(get_db)) -> dict:
    """The extra questions on the sign-up and walk-in forms (public: the sign-up form needs them)."""
    return {"fields": registration.list_fields(db)}


@router.get("/admin/registration-fields", tags=["admin"])
def all_fields(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    require_role(auth.actor, "admin")
    return {"fields": registration.list_fields(db, include_inactive=True)}


@router.post("/admin/registration-fields", tags=["admin"], status_code=201)
def create_field(body: FieldRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: registration.create_registration_field(db, auth.actor, body.model_dump()))


@router.patch("/admin/registration-fields/{field_id}", tags=["admin"])
def update_field(
    field_id: int, body: FieldRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db, lambda: registration.update_registration_field(db, auth.actor, field_id, body.model_dump())
    )


# --------------------------------------------------------------------------- consent and caregivers (34, 35)


class ConsentRequest(BaseModel):
    granted: bool


class DecisionRequest(BaseModel):
    approve: bool


class AccessRequest(BaseModel):
    patient_username: str = Field(min_length=3, max_length=60)


@router.get("/me/consents", tags=["profile"])
def my_consents(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    require_role(auth.actor, "patient")
    pid = auth.actor.patient_id
    return {
        "consents": registration.consent_state(db, pid),
        "history": registration.consent_history(db, pid),
        "answers": registration.patient_answers(db, pid),
        **registration.patient_requests(db, pid),
    }


@router.put("/me/consents/{purpose}", tags=["profile"])
def set_consent(
    purpose: str, body: ConsentRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(db, lambda: registration.set_consent(db, auth.actor, purpose, body.granted))


@router.post("/me/caregiver-requests/{request_id}", tags=["profile"])
def decide_request(
    request_id: int, body: DecisionRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(db, lambda: registration.decide_caregiver_request(db, auth.actor, request_id, body.approve))


@router.delete("/me/caregivers/{caregiver_user_id}", tags=["profile"])
def revoke(caregiver_user_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: registration.revoke_caregiver(db, auth.actor, caregiver_user_id))


@router.post("/caregiver/requests", tags=["profile"], status_code=201)
def request_access(body: AccessRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: registration.request_caregiver_access(db, auth.actor, body.patient_username))


@router.get("/caregiver/requests", tags=["profile"])
def my_requests(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return {"requests": registration.caregiver_requests(db, auth.actor)}
