"""Phase 6A endpoints: patient profile and notifications, receipts, slot recommendations, doctor
calendars and leave, and appointment utilization."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.utilization import utilization
from app.api.auth import issue_token
from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.api.passwords import check_new_password, hash_password, verify_password
from app.db.models import AppUser, Department, Notification, Patient
from app.safety.pii import set_contact_by, set_email, set_phone
from app.timeutil import iso, now_ist
from app.tools import calendar, receipts, recommend
from app.tools.errors import ToolError
from app.tools.permissions import linked_patient_ids, require_role

router = APIRouter(prefix="/api/v1")


def _own_patient(db: Session, auth: Auth) -> tuple[AppUser, Patient]:
    require_role(auth.actor, "patient")
    user = db.get(AppUser, auth.actor.user_id)
    return user, db.get(Patient, user.patient_id)


def _profile(user: AppUser, patient: Patient) -> dict:
    return {
        "username": user.username,
        "name": patient.name,
        "birth_year": patient.birth_year,
        "phone_masked": patient.phone_masked,
        "language": patient.preferred_language,
        "email_masked": patient.email_masked,
        "contact_by": patient.contact_by,
        "has_password": user.password_hash is not None,
        "member_since": iso(user.created_at) if user.created_at else None,
    }


# --------------------------------------------------------------------------- profile (feature 29)


class ProfileUpdate(BaseModel):
    name: str | None = Field(None, max_length=80)
    birth_year: int | None = None
    phone: str | None = Field(None, max_length=20)
    language: Literal["en", "hi", "mr"] | None = None
    email: str | None = Field(None, max_length=254)  # "" removes it
    contact_by: Literal["sms", "email", "app"] | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/me/profile", tags=["profile"])
def get_profile(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return _profile(*_own_patient(db, auth))


@router.patch("/me/profile", tags=["profile"])
def update_profile(body: ProfileUpdate, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    user, patient = _own_patient(db, auth)
    if body.name is not None:
        name = " ".join(body.name.split())
        if len(name) < 2:
            raise ToolError("VALIDATION_ERROR", "Please give your name.")
        patient.name = name
        user.display_name = name
    if body.birth_year is not None:
        if not 1900 <= body.birth_year <= now_ist().year:
            raise ToolError("VALIDATION_ERROR", f"Birth year must be between 1900 and {now_ist().year}.")
        patient.birth_year = body.birth_year
    if body.phone is not None:
        set_phone(patient, body.phone)  # masked for display, encrypted at rest (D-111)
    if body.language is not None:
        patient.preferred_language = body.language
    if body.email is not None:
        set_email(patient, body.email)  # masked for display, encrypted at rest (phase 7E)
    if body.contact_by is not None:
        set_contact_by(patient, body.contact_by)
    db.commit()
    return _profile(user, patient)


@router.post("/me/password", tags=["profile"])
def change_password(body: PasswordChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    user = db.get(AppUser, auth.actor.user_id)
    if user.password_hash is None:
        raise ToolError("FORBIDDEN", "Demo accounts have no password to change.")
    if not verify_password(body.current_password, user.password_hash):
        raise ToolError("INVALID_CREDENTIALS", "Your current password is not right.")
    check_new_password(body.new_password, body.current_password)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.credentials_version += 1  # every other sign-in of this account ends
    db.commit()
    token, expires = issue_token(user)
    return {"status": "changed", "token": token, "expires_at": iso(expires)}


# --------------------------------------------------------------------------- notifications (features 7, 18)


def _patient_ids(db: Session, auth: Auth) -> list[int]:
    if auth.actor.role == "patient":
        return [auth.actor.patient_id]
    if auth.actor.role == "caregiver":
        return sorted(linked_patient_ids(db, auth.actor))
    raise ToolError("FORBIDDEN", "Only patients and caregivers have notifications.")


@router.get("/me/notifications", tags=["profile"])
def my_notifications(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    ids = _patient_ids(db, auth)
    rows = db.scalars(
        select(Notification)
        .where(Notification.patient_id.in_(ids))
        .order_by(Notification.sent_at.desc(), Notification.id.desc())
        .limit(50)
    ).all()
    return {
        "unread": sum(1 for n in rows if n.read_at is None),
        "notifications": [
            {
                "notification_id": n.id,
                "kind": n.kind,
                "message": n.message,
                "sent_at": iso(n.sent_at),
                "read": n.read_at is not None,
                "appointment_id": n.appointment_id,
                "channel": n.channel,
                # Phase 7E: "sent" with delivered_via sms/email, "pending", "failed", "skipped" or null (app only).
                "delivery": n.delivery,
                "delivered_via": n.delivered_via,
            }
            for n in rows
        ],
    }


@router.post("/me/notifications/read", tags=["profile"])
def mark_read(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    ids = _patient_ids(db, auth)
    now = now_ist()
    rows = db.scalars(select(Notification).where(Notification.patient_id.in_(ids), Notification.read_at.is_(None)))
    count = 0
    for n in rows:
        n.read_at = now
        count += 1
    db.commit()
    return {"marked_read": count}


# --------------------------------------------------------------------------- booking helpers (3, 14, 20)


@router.get("/departments", tags=["booking"])
def departments(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return {
        "departments": [
            {
                "department": d.name,
                "floor": d.floor,
                "opd_start": d.opd_start.strftime("%H:%M"),
                "opd_end": d.opd_end.strftime("%H:%M"),
            }  # fmt: skip
            for d in db.scalars(select(Department).order_by(Department.name))
        ]
    }


@router.get("/recommendations", tags=["booking"])
def recommendations(
    patient_id: int,
    specialty: str | None = Query(None, max_length=60),
    doctor_id: int | None = None,
    language: str | None = Query(None, max_length=20),
    date_from: date | None = None,
    date_to: date | None = None,
    time_of_day: Literal["any", "morning", "afternoon"] = "any",
    limit: int = Query(6, ge=1, le=20),
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    return recommend.recommend_slots(
        db, auth.actor, patient_id, specialty=specialty, doctor_id=doctor_id, language=language,
        date_from=date_from, date_to=date_to, time_of_day=time_of_day, limit=limit,
    )  # fmt: skip


@router.get("/appointments/{appointment_id}/receipt", tags=["booking"])
def appointment_receipt(appointment_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return receipts.receipt(db, auth.actor, appointment_id)


# --------------------------------------------------------------------------- doctor calendars (2, 13)


class LeaveRequest(BaseModel):
    start_date: date
    end_date: date
    reason: str = Field("", max_length=120)


@router.get("/staff/doctors/{doctor_id}/calendar", tags=["staff"])
def doctor_calendar(
    doctor_id: int,
    start: date | None = None,
    days: int = Query(14, ge=1, le=31),
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    return calendar.doctor_calendar(db, auth.actor, doctor_id, start=start, days=days)


@router.post("/staff/slots/{slot_id}/block", tags=["staff"])
def block_slot(slot_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: calendar.set_slot_blocked(db, auth.actor, slot_id, blocked=True))


@router.post("/staff/slots/{slot_id}/unblock", tags=["staff"])
def unblock_slot(slot_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: calendar.set_slot_blocked(db, auth.actor, slot_id, blocked=False))


@router.post("/staff/doctors/{doctor_id}/leave", tags=["staff"], status_code=201)
def add_leave(
    doctor_id: int, body: LeaveRequest, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db, lambda: calendar.add_doctor_leave(db, auth.actor, doctor_id, body.start_date, body.end_date, body.reason)
    )


@router.delete("/staff/leave/{leave_id}", tags=["staff"])
def cancel_leave(leave_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: calendar.cancel_doctor_leave(db, auth.actor, leave_id))


# --------------------------------------------------------------------------- utilization (15, 16)


@router.get("/admin/utilization", tags=["admin"])
def admin_utilization(
    days: int = Query(7, ge=1, le=30), auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    require_role(auth.actor, "admin")
    return utilization(db, now_ist(), days)
