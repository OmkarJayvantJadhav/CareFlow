"""Mocked patient notifications (no real SMS/WhatsApp in v1)."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Notification
from app.safety.privacy import mask_text


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
    )
    db.add(note)
    db.flush()
    return note
