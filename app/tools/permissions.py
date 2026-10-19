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

    @classmethod
    def from_user(cls, user: AppUser) -> "Actor":
        return cls(user_id=user.id, role=user.role, patient_id=user.patient_id)


def load_actor(db: Session, user_id: int) -> Actor:
    user = db.get(AppUser, user_id)
    if user is None:
        raise ToolError("FORBIDDEN", "Unknown user.")
    return Actor.from_user(user)


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
