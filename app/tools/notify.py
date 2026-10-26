"""Patient notifications: always shown in the app; also sent by SMS or e-mail when the hospital has turned
that on for their kind (phase 7E, app.tools.messaging). ``mocked`` stays true until one is really sent."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Notification
from app.safety.privacy import mask_text
from app.tools.messaging import should_send


def notify(
    db: Session,
    patient_id: int,
    message: str,
    now: datetime,
    channel: str = "sms",
    kind: str = "info",
    appointment_id: int | None = None,
) -> Notification:
    note = Notification(
        patient_id=patient_id,
        channel=channel,
        message=mask_text(message),
        sent_at=now,
        mocked=True,
        kind=kind,
        appointment_id=appointment_id,
        delivery="pending" if should_send(db, kind) else None,
    )
    db.add(note)
    db.flush()
    return note
