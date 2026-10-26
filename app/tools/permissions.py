"""Role and ownership checks, enforced inside every tool (NFR-07, docs §11).

The role always comes from the authenticated user record, never from the
conversation, so a prompt cannot grant itself permissions.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppUser, CaregiverLink
from app.tools.errors import ToolError


@dataclass(frozen=True)
class Actor:
    user_id: int
    role: str
    patient_id: int | None = None
    doctor_id: int | None = None

    @classmethod
    def from_user(cls, user: AppUser) -> "Actor":
        return cls(user_id=user.id, role=user.role, patient_id=user.patient_id, doctor_id=user.doctor_id)


def linked_patient_ids(db: Session, actor: Actor) -> set[int]:
    if actor.role != "caregiver":
        return set()
    rows = db.scalars(
        select(CaregiverLink.patient_id).where(
            CaregiverLink.caregiver_user_id == actor.user_id, CaregiverLink.verified.is_(True)
        )
    )
    return set(rows)


def can_manage_patient(db: Session, actor: Actor, patient_id: int) -> bool:
    """Book, reschedule, cancel, view history for a patient (docs §11 permission table)."""
    if actor.role == "staff":
        return True
    if actor.role == "patient":
        return actor.patient_id == patient_id
    if actor.role == "caregiver":
        return patient_id in linked_patient_ids(db, actor)
    return False  # admin: aggregates only


def require_patient_access(db: Session, actor: Actor, patient_id: int) -> None:
    if not can_manage_patient(db, actor, patient_id):
        raise ToolError("FORBIDDEN", "You are not allowed to view or change this patient's appointments.")


def require_role(actor: Actor, *roles: str) -> None:
    if actor.role not in roles:
        raise ToolError("FORBIDDEN", "Your account is not allowed to do this.")


def require_queue_control(actor: Actor, doctor_id: int) -> None:
    """Run a doctor's queue: the front desk for any doctor, a doctor only for their own patients."""
    if actor.role == "staff" or (actor.role == "doctor" and actor.doctor_id == doctor_id):
        return
    raise ToolError("FORBIDDEN", "Your account is not allowed to run this doctor's queue.")


def require_own_doctor(actor: Actor, doctor_id: int) -> None:
    """Clinical decisions (feature 52) are made by the patient's own doctor."""
    if actor.role != "doctor" or actor.doctor_id != doctor_id:
        raise ToolError("FORBIDDEN", "Only the patient's doctor can authorize this.")
