"""Patient records for staff and admins, and a patient's own data: export and erasure (phase 7C)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.api.passwords import verify_password
from app.db.models import AppUser
from app.tools import patients
from app.tools.errors import ToolError

router = APIRouter(prefix="/api/v1", tags=["patients"])


class PatientChange(BaseModel):
    name: str | None = Field(None, max_length=120)
    birth_year: int | None = None
    phone: str | None = Field(None, max_length=20)
    language: str | None = Field(None, max_length=2)
    pregnant: bool | None = None
    disability: bool | None = None
    answers: dict[str, str] | None = None
    email: str | None = Field(None, max_length=254)
    contact_by: Literal["sms", "email", "app"] | None = None


class Erasure(BaseModel):
    reason: str = Field("", max_length=200)


class OwnErasure(BaseModel):
    password: str = Field(min_length=1, max_length=128)


@router.get("/staff/patients")
def search(q: str = Query(..., max_length=60), auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return patients.search_patients(db, auth.actor, q)


@router.get("/staff/patients/{patient_id}")
def record(patient_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return patients.patient_record(db, auth.actor, patient_id)


@router.patch("/staff/patients/{patient_id}")
def update(patient_id: int, body: PatientChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    fields = body.model_dump(exclude_unset=True)
    return run_and_commit(db, lambda: patients.update_patient(db, auth.actor, patient_id, **fields))


@router.post("/staff/patients/{patient_id}/phone")
def reveal_phone(patient_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """The full number; each look is recorded in the audit log."""
    return run_and_commit(db, lambda: patients.reveal_phone(db, auth.actor, patient_id))


@router.post("/admin/patients/{patient_id}/erase")
def erase(patient_id: int, body: Erasure, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: patients.erase_patient(db, auth.actor, patient_id, body.reason))


@router.get("/me/export")
def export(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Everything CareFlow holds about the signed-in patient or caregiver."""
    if auth.actor.role not in ("patient", "caregiver"):
        raise ToolError("FORBIDDEN", "Only patients and caregivers have personal data to download here.")
    return patients.export_own_data(db, auth.actor)


@router.post("/me/erase")
def erase_own(body: OwnErasure, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """Delete one's own account and personal details, confirmed with the password. Signs out everywhere."""
    user = db.get(AppUser, auth.actor.user_id)
    if auth.actor.role not in ("patient", "caregiver"):
        raise ToolError("FORBIDDEN", "Staff accounts are switched off by an admin.")
    if user.password_hash is None:
        raise ToolError("FORBIDDEN", "Demo accounts cannot be deleted.")
    if not verify_password(body.password, user.password_hash):
        raise ToolError("INVALID_CREDENTIALS", "Your password is not right.")
    if auth.actor.role == "caregiver":
        return run_and_commit(db, lambda: patients.erase_caregiver_account(db, auth.actor))
    return run_and_commit(db, lambda: patients.erase_patient(db, auth.actor, auth.actor.patient_id, "own request"))
