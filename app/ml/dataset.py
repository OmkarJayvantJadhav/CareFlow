"""Training data from replayed simulator days.

One row per (queue event, waiting patient): at every queue event the state is
rebuilt with ``state_at`` exactly as the live system would see it, and the label
is when that patient's consultation actually started.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Doctor, QueueEntry, QueueSession
from app.ml.features import FEATURES, load_session_records, state_at


@dataclass
class Dataset:
    x: np.ndarray
    residual: np.ndarray  # minutes from "doctor next free" to consultation start (model target)
    wait: np.ndarray  # actual minutes from the snapshot to consultation start
    offset: np.ndarray
    position: np.ndarray
    ahead: np.ndarray
    doctor_avg: np.ndarray
    walk_in: np.ndarray
    day: np.ndarray
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.wait)

    def subset(self, mask: np.ndarray) -> "Dataset":
        return Dataset(**{k: v[mask] for k, v in self.__dict__.items() if k != "meta"}, meta=self.meta)


def doctor_averages(db: Session, start: date, end: date) -> dict[str, float]:
    """Mean consultation minutes per doctor over [start, end] (the training days only)."""
    rows = db.execute(
        select(Doctor.name, QueueEntry.consult_start, QueueEntry.consult_end)
        .join(QueueSession, QueueSession.id == QueueEntry.session_id)
        .join(Doctor, Doctor.id == QueueSession.doctor_id)
        .where(QueueSession.date >= start, QueueSession.date <= end, QueueEntry.consult_end.is_not(None))
    ).all()
    totals: dict[str, list[float]] = {}
    for name, began, ended in rows:
        totals.setdefault(name, []).append((ended - began).total_seconds() / 60)
    return {name: round(float(np.mean(v)), 3) for name, v in totals.items()}


def build_dataset(db: Session, start: date, end: date, doctor_avg: dict[str, float]) -> Dataset:
    sessions = db.scalars(
        select(QueueSession.id)
        .where(QueueSession.date >= start, QueueSession.date <= end)
        .order_by(QueueSession.date, QueueSession.id)
    ).all()
    cols: dict[str, list] = {
        k: [] for k in ("x", "residual", "wait", "offset", "position", "ahead", "avg", "walk_in", "day")
    }
    for session_id in sessions:
        rec = load_session_records(db, session_id)
        started = {e.id: e.consult_start for e in rec.entries}
        avg = doctor_avg.get(rec.doctor_name)
        for t in sorted(set(rec.event_times)):
            for row in state_at(rec, t, avg):
                began = started.get(row.entry_id)
                if began is None or began < t:
                    continue  # never seen (doctor left, or left after missing a turn)
                wait = (began - t).total_seconds() / 60
                cols["x"].append(row.features)
                cols["residual"].append(max(0.0, wait - row.start_offset))
                cols["wait"].append(wait)
                cols["offset"].append(row.start_offset)
                cols["position"].append(row.position)
                cols["ahead"].append(row.ahead)
                cols["avg"].append(row.features[FEATURES.index("doctor_avg")])
                cols["walk_in"].append(row.features[FEATURES.index("walk_in")])
                cols["day"].append((rec.day - start).days)
    return Dataset(
        x=np.array(cols["x"], dtype=np.float64).reshape(-1, len(FEATURES)),
        residual=np.array(cols["residual"]),
        wait=np.array(cols["wait"]),
        offset=np.array(cols["offset"]),
        position=np.array(cols["position"]),
        ahead=np.array(cols["ahead"]),
        doctor_avg=np.array(cols["avg"]),
        walk_in=np.array(cols["walk_in"]),
        day=np.array(cols["day"]),
        meta={"start": start.isoformat(), "end": end.isoformat(), "sessions": len(sessions)},
    )


def split_days(end: date, days: int = 90, train: int = 60, val: int = 15) -> dict[str, tuple[date, date]]:
    """Calendar split of the ``days`` days before ``end``: train 1-60, validate 61-75, test 76-90."""
    first = end - timedelta(days=days)
    return {
        "train": (first, first + timedelta(days=train - 1)),
        "val": (first + timedelta(days=train), first + timedelta(days=train + val - 1)),
        "test": (first + timedelta(days=train + val), end - timedelta(days=1)),
    }
