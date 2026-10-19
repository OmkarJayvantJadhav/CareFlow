"""Wait-time features, shared by training and live prediction.

``SessionRecords`` holds everything stored about one doctor's OPD session.
``state_at(records, t)`` rebuilds the queue as it was at time ``t`` using only
records with timestamps up to ``t`` - so the training set, built from finished
days, contains exactly what the live system would have known, and live
prediction simply calls the same function with ``t = now``.

The prediction target is split in two:

    wait = start_offset + residual

``start_offset`` is known for certain (the doctor is on a break, delayed, or
the OPD has not opened yet); the model learns only ``residual``, the time from
the moment the doctor is next free until the patient's consultation starts.
A break therefore moves every estimate by exactly its length (TC-10).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Appointment, Doctor, QueueEntry, QueueEvent, QueueSession, Slot
from app.queue.merge import QueueItem, merge_order
from app.timeutil import at as local_at

FEATURES = [
    "position",
    "ahead",
    "in_room",
    "walk_in",
    "late_or_returned",
    "priority",
    "minutes_waited",
    "slot_offset",
    "booked_ahead",
    "walk_ins_ahead",
    "upcoming_booked",
    "queue_length",
    "slot_minutes",
    "doctor_avg",
    "today_mean_consult",
    "today_done",
    "room_elapsed",
    "minutes_since_open",
    "hour",
    "weekday",
    "alternate_rule",
    "expected_naive",
]
NAN = float("nan")


@dataclass
class EntryRecord:
    id: int
    kind: str
    scheduled_at: datetime | None
    checked_in_at: datetime
    consult_start: datetime | None
    consult_end: datetime | None
    calls: list[datetime] = field(default_factory=list)
    misses: list[datetime] = field(default_factory=list)
    returns: list[datetime] = field(default_factory=list)
    priorities: list[tuple[datetime, int]] = field(default_factory=list)


@dataclass
class SessionRecords:
    session_id: int
    doctor_id: int
    doctor_name: str
    day: date
    merge_rule: str
    slot_minutes: int
    opd_start: datetime
    closed_at: datetime | None
    entries: list[EntryRecord]
    # (at, minutes) for break / delay / emergency, and resume times
    busy_events: list[tuple[datetime, int]]
    resumes: list[datetime]
    # Booked appointments for this doctor and day: (created_at, cancelled_at or None, slot start, appointment id)
    bookings: list[tuple[datetime, datetime | None, datetime, int]]
    entry_by_appointment: dict[int, int]
    event_times: list[datetime]


@dataclass
class WaitingRow:
    entry_id: int
    features: list[float]
    start_offset: float  # minutes from t until the doctor is next free
    position: int
    ahead: int  # people before this patient, including anyone in the room


def load_session_records(db: Session, session_id: int) -> SessionRecords:
    session = db.get(QueueSession, session_id)
    doctor = db.get(Doctor, session.doctor_id)
    rows = db.scalars(select(QueueEntry).where(QueueEntry.session_id == session_id).order_by(QueueEntry.id)).all()
    entries = {
        e.id: EntryRecord(e.id, e.kind, e.scheduled_at, e.checked_in_at, e.consult_start, e.consult_end) for e in rows
    }
    busy, resumes, times = [], [], []
    for ev in db.scalars(select(QueueEvent).where(QueueEvent.session_id == session_id).order_by(QueueEvent.id)):
        times.append(ev.at)
        entry = entries.get((ev.payload or {}).get("entry_id"))
        if ev.type in ("break", "delay", "emergency") and ev.payload.get("minutes"):
            busy.append((ev.at, int(ev.payload["minutes"])))
        elif ev.type == "resume":
            resumes.append(ev.at)
        elif entry is not None and ev.type == "call":
            entry.calls.append(ev.at)
        elif entry is not None and ev.type == "missed_turn":
            entry.misses.append(ev.at)
        elif entry is not None and ev.type == "return":
            entry.returns.append(ev.at)
        elif entry is not None and ev.type == "priority":
            entry.priorities.append((ev.at, int(ev.payload.get("priority", 0))))
    day_start = local_at(session.date, time.min)
    bookings = []
    for appt, slot in db.execute(
        select(Appointment, Slot)
        .join(Slot, Slot.id == Appointment.slot_id)
        .where(Appointment.doctor_id == session.doctor_id, Appointment.appt_date == session.date)
    ):
        cancelled = appt.updated_at if appt.status == "cancelled" else None
        bookings.append((appt.created_at or day_start, cancelled, slot.start_at, appt.id))
    return SessionRecords(
        session_id=session.id,
        doctor_id=doctor.id,
        doctor_name=doctor.name,
        day=session.date,
        merge_rule=session.merge_rule,
        slot_minutes=doctor.slot_minutes,
        opd_start=local_at(session.date, doctor.department.opd_start),
        closed_at=session.closed_at,
        entries=list(entries.values()),
        busy_events=busy,
        resumes=resumes,
        bookings=bookings,
        entry_by_appointment={e.appointment_id: e.id for e in rows if e.appointment_id},
        event_times=times,
    )


def _minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


def _busy_until(rec: SessionRecords, t: datetime) -> datetime | None:
    until = None
    events = sorted(
        [(a, "busy", m) for a, m in rec.busy_events if a <= t] + [(a, "resume", 0) for a in rec.resumes if a <= t]
    )
    for a, kind, minutes in events:
        if kind == "resume":
            until = None
        else:
            end = a + timedelta(minutes=minutes)
            until = max(until, end) if until else end
    return until


def _waiting_since(entry: EntryRecord, t: datetime) -> datetime | None:
    """When the entry (re)joined the queue if it is waiting at t, else None."""
    if entry.checked_in_at > t:
        return None
    start = entry.checked_in_at
    calls = sorted(c for c in entry.calls if c <= t)
    returns = sorted(r for r in entry.returns if r <= t)
    if not calls:
        return start
    last_call = calls[-1]
    later_returns = [r for r in returns if r > last_call]
    return later_returns[0] if later_returns else None


def _in_room(entry: EntryRecord, t: datetime) -> tuple[bool, datetime | None]:
    calls = [c for c in entry.calls if c <= t]
    if not calls:
        return False, None
    last_call = max(calls)
    if any(last_call < m <= t for m in entry.misses):
        return False, None
    if entry.consult_end is not None and entry.consult_end <= t:
        return False, None
    return True, entry.consult_start if entry.consult_start and entry.consult_start <= t else last_call


def _priority(entry: EntryRecord, t: datetime) -> int:
    changes = [p for a, p in sorted(entry.priorities) if a <= t]
    return changes[-1] if changes else 0


def state_at(rec: SessionRecords, t: datetime, doctor_avg: float | None = None) -> list[WaitingRow]:
    """Feature rows for every patient waiting at time t, in the order they will be called."""
    if rec.closed_at is not None and rec.closed_at <= t:
        return []
    avg = doctor_avg or float(rec.slot_minutes)
    busy_until = _busy_until(rec, t)
    start = max([t, rec.opd_start] + ([busy_until] if busy_until else []))

    waiting: dict[int, tuple[EntryRecord, datetime]] = {}
    room_elapsed, in_room = 0.0, 0
    done_durations = []
    for entry in rec.entries:
        since = _waiting_since(entry, t)
        if since is not None:
            waiting[entry.id] = (entry, since)
            continue
        busy, began = _in_room(entry, t)
        if busy:
            in_room = 1
            room_elapsed = _minutes(t - began) if began else 0.0
        if entry.consult_end is not None and entry.consult_end <= t and entry.consult_start is not None:
            done_durations.append(_minutes(entry.consult_end - entry.consult_start))
    if not waiting:
        return []

    items = [
        QueueItem(
            entry_id=e.id,
            kind=e.kind,
            checked_in_at=e.checked_in_at,
            scheduled_at=e.scheduled_at,
            requeued_at=since if since != e.checked_in_at else None,
            priority=_priority(e, t),
        )
        for e, since in waiting.values()
    ]
    by_id = {i.entry_id: i for i in items}
    # The same projection start as the engine: breaks and delays never reorder the queue.
    order = merge_order(items, rec.merge_rule, max(t, rec.opd_start), rec.slot_minutes)

    arrived = {appt for appt, entry_id in rec.entry_by_appointment.items() if _arrived(rec, entry_id, t)}
    not_arrived = [
        slot_start
        for created, cancelled, slot_start, appt_id in rec.bookings
        if created <= t and not (cancelled and cancelled <= t) and appt_id not in arrived
    ]
    today_mean = float(np.mean(done_durations)) if done_durations else NAN
    start_offset = _minutes(start - t)
    rows = []
    booked_seen = walk_seen = 0
    for index, entry_id in enumerate(order):
        item = by_id[entry_id]
        entry, since = waiting[entry_id]
        position = index + 1
        horizon = start + timedelta(minutes=position * rec.slot_minutes)
        upcoming = sum(1 for s in not_arrived if s < horizon and (item.scheduled_at is None or s < item.scheduled_at))
        ahead = index + in_room
        features = [
            position,
            ahead,
            in_room,
            1.0 if item.kind == "walk_in" else 0.0,
            0.0 if item.keeps_slot_order else (1.0 if item.kind == "booked" else 0.0),
            item.priority,
            _minutes(t - since),
            _minutes(item.scheduled_at - start) if item.keeps_slot_order else NAN,
            booked_seen,
            walk_seen,
            upcoming,
            len(order),
            rec.slot_minutes,
            avg,
            today_mean,
            len(done_durations),
            room_elapsed,
            _minutes(start - rec.opd_start),
            start.hour + start.minute / 60.0,
            rec.day.isoweekday(),
            1.0 if rec.merge_rule == "alternate" else 0.0,
            max(0.0, ahead * avg - room_elapsed),
        ]
        rows.append(WaitingRow(entry_id, features, start_offset, position, ahead))
        if item.keeps_slot_order:
            booked_seen += 1
        else:
            walk_seen += 1
    return rows


def _arrived(rec: SessionRecords, entry_id: int, t: datetime) -> bool:
    entry = next((e for e in rec.entries if e.id == entry_id), None)
    return entry is not None and entry.checked_in_at <= t
