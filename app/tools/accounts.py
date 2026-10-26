"""Account management by the hospital's administrators (phase 7A).

Admins create staff, doctor, admin and caregiver accounts, switch accounts off and on, change a name or
role, and reset forgotten passwords. A new or reset account gets a temporary password that is shown to
the admin once and must be replaced at its first sign-in. Patients still create their own accounts (or
are registered at the desk). Every change is audited; passwords never reach the audit log.
"""

import re
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.passwords import hash_password, temporary_password
from app.db.models import ROLES, AppUser, Doctor
from app.timeutil import iso, resolve_now
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.permissions import Actor, require_role

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")
STAFF_ROLES = ("staff", "doctor", "admin", "caregiver")  # roles an admin creates; patients sign up
MAX_LISTED = 200


def account_view(user: AppUser) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "doctor_id": user.doctor_id,
        "patient_id": user.patient_id,
        "active": user.active,
        "must_change_password": user.must_change_password,
        "has_password": user.password_hash is not None,
        "self_registered": user.self_registered,
        "created_at": iso(user.created_at),
        "last_login_at": iso(user.last_login_at),
    }


def list_accounts(db: Session, actor: Actor, role: str | None = None, q: str | None = None) -> dict:
    require_role(actor, "admin")
    query = select(AppUser).order_by(AppUser.role, AppUser.display_name)
    if role:
        if role not in ROLES:
            raise ToolError("VALIDATION_ERROR", f"Unknown role {role!r}.")
        query = query.where(AppUser.role == role)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(AppUser.username).like(like), func.lower(AppUser.display_name).like(like)))
    users = db.scalars(query.limit(MAX_LISTED + 1)).all()
    counts = dict(db.execute(select(AppUser.role, func.count()).group_by(AppUser.role)).all())
    return {
        "accounts": [account_view(u) for u in users[:MAX_LISTED]],
        "more": len(users) > MAX_LISTED,
        "counts": {r: counts.get(r, 0) for r in ROLES},
    }


def _clean_name(display_name: str) -> str:
    name = " ".join((display_name or "").split())
    if not 2 <= len(name) <= 120:
        raise ToolError("VALIDATION_ERROR", "Give a name of 2-120 characters.")
    return name


def _check_doctor(db: Session, doctor_id: int | None, except_user: int | None = None) -> None:
    if doctor_id is None or db.get(Doctor, doctor_id) is None:
        raise ToolError("VALIDATION_ERROR", "Choose the doctor this account belongs to.")
    taken = db.scalars(
        select(AppUser.id).where(AppUser.doctor_id == doctor_id, AppUser.active.is_(True), AppUser.id != except_user)
    ).first()
    if taken is not None:
        raise ToolError("DUPLICATE", "This doctor already has an active account.")


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AppUser).where(AppUser.role == "admin", AppUser.active.is_(True)))


@write_tool("create_account")
def create_account(
    db: Session,
    actor: Actor,
    username: str,
    display_name: str,
    role: str,
    doctor_id: int | None = None,
    now: datetime | None = None,
) -> dict:
    resolve_now(now)
    require_role(actor, "admin")
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ToolError(
            "VALIDATION_ERROR", "Usernames are 3–30 characters: lowercase letters, digits, dots, dashes or underscores."
        )
    if role not in STAFF_ROLES:
        raise ToolError("VALIDATION_ERROR", "Patients create their own accounts or are registered at the desk.")
    if db.scalars(select(AppUser.id).where(AppUser.username == username)).first() is not None:
        raise ToolError("USERNAME_TAKEN", "That username is taken; please choose another.")
    if role == "doctor":
        _check_doctor(db, doctor_id)
    password = temporary_password()
    user = AppUser(
        username=username,
        display_name=_clean_name(display_name),
        role=role,
        doctor_id=doctor_id if role == "doctor" else None,
        password_hash=hash_password(password),
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    return {"account": account_view(user), "temporary_password": password}


@write_tool("update_account")
def update_account(
    db: Session,
    actor: Actor,
    user_id: int,
    display_name: str | None = None,
    role: str | None = None,
    doctor_id: int | None = None,
    active: bool | None = None,
    now: datetime | None = None,
) -> dict:
    """Rename, change role (staff, doctor, admin, caregiver) or switch an account off and on."""
    resolve_now(now)
    require_role(actor, "admin")
    user = db.scalars(select(AppUser).where(AppUser.id == user_id).with_for_update()).first()
    if user is None:
        raise ToolError("NOT_FOUND", "There is no such account.")
    ends_sign_ins = False
    if display_name is not None:
        user.display_name = _clean_name(display_name)
    if role is not None and role != user.role:
        if user.id == actor.user_id:
            raise ToolError("FORBIDDEN", "You cannot change your own role.")
        if "patient" in (role, user.role):
            raise ToolError("VALIDATION_ERROR", "A patient account cannot become another kind of account.")
        if role not in STAFF_ROLES:
            raise ToolError("VALIDATION_ERROR", f"Unknown role {role!r}.")
        if user.role == "admin" and user.active and _active_admins(db) <= 1:
            raise ToolError("INVALID_STATE", "The hospital needs at least one active admin.")
        if role == "doctor":
            _check_doctor(db, doctor_id, except_user=user.id)
        user.role = role
        user.doctor_id = doctor_id if role == "doctor" else None
        ends_sign_ins = True
    elif role == "doctor" and doctor_id is not None and doctor_id != user.doctor_id:
        _check_doctor(db, doctor_id, except_user=user.id)
        user.doctor_id = doctor_id
        ends_sign_ins = True
    if active is not None and active != user.active:
        if user.id == actor.user_id:
            raise ToolError("FORBIDDEN", "You cannot switch off your own account.")
        if not active and user.role == "admin" and _active_admins(db) <= 1:
            raise ToolError("INVALID_STATE", "The hospital needs at least one active admin.")
        if active and user.role == "doctor":
            _check_doctor(db, user.doctor_id, except_user=user.id)
        user.active = active
        ends_sign_ins = ends_sign_ins or not active
    if ends_sign_ins:
        user.credentials_version += 1
    db.flush()
    return account_view(user)


@write_tool("reset_account_password")
def reset_password(db: Session, actor: Actor, user_id: int, now: datetime | None = None) -> dict:
    """A forgotten password: a new temporary one, shown once; earlier sign-ins end."""
    resolve_now(now)
    require_role(actor, "admin")
    user = db.scalars(select(AppUser).where(AppUser.id == user_id).with_for_update()).first()
    if user is None:
        raise ToolError("NOT_FOUND", "There is no such account.")
    if user.id == actor.user_id:
        raise ToolError("FORBIDDEN", "Change your own password from your account page.")
    password = temporary_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.credentials_version += 1
    db.flush()
    return {"account": account_view(user), "temporary_password": password}
