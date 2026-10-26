"""Account management for admins (phase 7A) and the public settings the start page needs."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.config import get_settings
from app.tools import accounts, messaging, policy
from app.tools.hospital import public_profile

router = APIRouter(prefix="/api/v1")


@router.get("/config", tags=["auth"])
def public_config(db: Session = Depends(get_db)) -> dict:
    """What every page needs before sign-in: the hospital's name and emergency directions (null until an admin
    enters them), demo roles only in demo mode, and sign-up if it is allowed."""
    settings = get_settings()
    return {
        "demo_mode": settings.demo_mode,
        "allow_registration": settings.allow_registration,
        "hospital": public_profile(db),
        "policy": policy.current(),  # the rules in force, for texts that state them
        "messaging": messaging.available(db),  # the channels patients can choose: {"sms": bool, "email": bool}
    }


class NewAccount(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=2, max_length=120)
    role: str = Field(max_length=12)
    doctor_id: int | None = None


class AccountChange(BaseModel):
    display_name: str | None = Field(None, max_length=120)
    role: str | None = Field(None, max_length=12)
    doctor_id: int | None = None
    active: bool | None = None


@router.get("/admin/accounts", tags=["admin"])
def list_accounts(
    role: str | None = Query(None, max_length=12),
    q: str | None = Query(None, max_length=60),
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    return accounts.list_accounts(db, auth.actor, role, q)


@router.post("/admin/accounts", tags=["admin"], status_code=201)
def create_account(body: NewAccount, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    """The temporary password is in this response only; it is not stored in a readable form anywhere."""
    return run_and_commit(
        db,
        lambda: accounts.create_account(db, auth.actor, body.username, body.display_name, body.role, body.doctor_id),
    )


@router.patch("/admin/accounts/{user_id}", tags=["admin"])
def update_account(
    user_id: int, body: AccountChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db,
        lambda: accounts.update_account(
            db, auth.actor, user_id, body.display_name, body.role, body.doctor_id, body.active
        ),
    )


@router.post("/admin/accounts/{user_id}/reset-password", tags=["admin"])
def reset_password(user_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: accounts.reset_password(db, auth.actor, user_id))
