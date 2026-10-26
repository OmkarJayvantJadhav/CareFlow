"""Messages by SMS and e-mail (phase 7E): the admin's switch, the kinds sent, a test message and retries."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.tools import messaging

router = APIRouter(prefix="/api/v1/admin/messaging", tags=["admin"])


class MessagingChange(BaseModel):
    enabled: bool
    kinds: list[str] = Field(default_factory=list, max_length=20)


class TestMessage(BaseModel):
    channel: Literal["sms", "email"]
    to: str = Field(min_length=1, max_length=254)


@router.get("")
def view(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return messaging.messaging_view(db, auth.actor)


@router.put("")
def update(body: MessagingChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: messaging.update_messaging(db, auth.actor, body.enabled, body.kinds))


@router.post("/test")
def test(body: TestMessage, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: messaging.send_test_message(db, auth.actor, body.channel, body.to))


@router.post("/retry")
def retry(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: messaging.retry_failed_messages(db, auth.actor))
