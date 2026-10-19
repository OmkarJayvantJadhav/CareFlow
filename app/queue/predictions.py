"""Live wait-time predictions (FR-24, FR-25).

After every queue event the queue is rebuilt with the same feature code used for
training, and a new ``wait_prediction`` row is appended for every waiting
patient. When at most three people are ahead, a (mocked) "your turn is near"
message is sent once.
"""

import contextvars
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Notification, QueueEntry, QueueSession, WaitPrediction
from app.ml.features import load_session_records, state_at
from app.ml.model import Estimate, display_range, get_wait_model
from app.timeutil import iso, to_ist
from app.tools.notify import notify

TURN_NEAR_AHEAD = 3
_enabled: contextvars.ContextVar[bool] = contextvars.ContextVar("predictions_enabled", default=True)


@contextmanager
def predictions_disabled():
    """Used when replaying history for training data: predictions are a live feature."""
    token = _enabled.set(False)
    try:
        yield
    finally:
        _enabled.reset(token)


def refresh_predictions(db: Session, session: QueueSession, now: datetime) -> list[dict]:
    if not _enabled.get() or session.status != "open":
        return []
    db.flush()
    model = get_wait_model()
    records = load_session_records(db, session.id)
    rows = state_at(records, now, model.doctor_avg(records.doctor_name))
    estimates = model.predict(rows)
    out = []
    for row, est in zip(rows, estimates, strict=True):
        db.add(
            WaitPrediction(
                entry_id=row.entry_id,
                predicted_min=est.predicted_min,
                low_min=est.low_min,
                high_min=est.high_min,
                model_version=model.version,
                at=now,
            )
        )
        if row.ahead <= TURN_NEAR_AHEAD:
            _turn_near(db, row.entry_id, records.doctor_name, now)
        out.append({"entry_id": row.entry_id, "position": row.position, "ahead": row.ahead, **_fields(est)})
    db.flush()
    return out


def _turn_near(db: Session, entry_id: int, doctor_name: str, now: datetime) -> None:
    entry = db.get(QueueEntry, entry_id)
    marker = f"token {entry.token}, {doctor_name}"
    day_start = to_ist(now).replace(hour=0, minute=0, second=0, microsecond=0)
    sent = db.scalars(
        select(Notification.id).where(
            Notification.patient_id == entry.patient_id,
            Notification.sent_at >= day_start,
            Notification.message.contains(marker),
        )
    ).first()
    if sent is None:
        notify(db, entry.patient_id, f"Your turn is near ({marker}). Please stay close to the consultation room.", now)


def _fields(est: Estimate) -> dict:
    return {
        "predicted_min": est.predicted_min,
        "low_min": est.low_min,
        "high_min": est.high_min,
        "display": display_range(est),
    }


def latest_estimate(db: Session, entry_id: int, now: datetime) -> dict | None:
    """The most recent prediction, aged by the minutes that have passed since it was made."""
    row = db.scalars(
        select(WaitPrediction).where(WaitPrediction.entry_id == entry_id).order_by(WaitPrediction.id.desc()).limit(1)
    ).first()
    if row is None:
        return None
    elapsed = max(0.0, (now - row.at).total_seconds() / 60)
    est = Estimate(
        round(max(0.0, row.predicted_min - elapsed), 1),
        round(max(0.0, row.low_min - elapsed), 1),
        round(max(0.0, row.high_min - elapsed), 1),
    )
    return {**_fields(est), "model_version": row.model_version, "predicted_at": iso(row.at)}
