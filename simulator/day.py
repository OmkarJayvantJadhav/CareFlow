"""Replay a full synthetic OPD day through the real booking and queue functions.

Each doctor's session is a small discrete-event simulation: booked patients
arrive (some early, some late, some never), walk-ins arrive at random, the
doctor may start late, take a break, handle an emergency or become
unavailable, and patients occasionally miss their turn and come back. Every
action goes through the same audited service functions the API and the agent
use, with the simulated clock passed as ``now``.
"""

import heapq
import itertools
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ACTIVE_APPOINTMENT_STATUSES, Appointment, Doctor, QueueSession, Slot
from app.queue import engine
from app.timeutil import at
from app.tools.errors import ToolError
from simulator import hospital
from simulator.seed import book_as_simulator, ensure_slots, random_phone, simulated_patient_ids, system_actor


@dataclass
class SimParams:
    occupancy: tuple[float, float] = (0.50, 0.85)
    no_show_rate: float = 0.10
    late_rate: float = 0.08
    # Share of the doctor's time that walk-ins would fill, if every walk-in took one slot.
    walk_in_load: tuple[float, float] = (0.10, 0.35)
    new_walk_in_patient_rate: float = 0.15
    start_delay_mean_min: float = 6.0
    big_delay_rate: float = 0.10
    break_rate: float = 0.40
    emergency_rate: float = 0.12
    unavailable_rate: float = 0.015
    missed_turn_rate: float = 0.04
    return_after_miss_rate: float = 0.85
    priority_rate: float = 0.03
    consult_sigma: float = 0.35


@dataclass
class SessionStats:
    doctor: str
    booked: int = 0
    arrived: int = 0
    walk_ins: int = 0
    seen: int = 0
    missed_turns: int = 0
    events: list[str] = field(default_factory=list)
    unavailable: bool = False


def _minutes(value: float) -> timedelta:
    return timedelta(minutes=float(value))


class SessionSimulator:
    def __init__(self, db: Session, doctor: Doctor, day: date, rng: np.random.Generator, params: SimParams):
        self.db, self.doctor, self.day, self.rng, self.p = db, doctor, day, rng, params
        self.actor = system_actor(db)
        self.dept = doctor.department
        self.open_at = at(day, self.dept.opd_start)
        self.close_at = at(day, self.dept.opd_end)
        self.pending: list[tuple[datetime, int, str, dict]] = []
        self.seq = itertools.count()
        self.stats = SessionStats(doctor=doctor.name)
        self.session: QueueSession | None = None
        self.speed = float(rng.uniform(0.75, 1.15))
        self.taken: set[int] = set()
        self._pids: list[int] | None = None

    # ---------------------------------------------------------------- planning

    def schedule(self, when: datetime, kind: str, **data) -> None:
        heapq.heappush(self.pending, (when, next(self.seq), kind, data))

    def fill_bookings(self) -> None:
        """Top bookings up to the day's occupancy, as if patients had booked over the past days."""
        booking_time = at(self.day, time.min) - timedelta(days=1)
        target = float(self.rng.uniform(*self.p.occupancy))
        slots = self.db.scalars(
            select(Slot)
            .where(
                Slot.doctor_id == self.doctor.id,
                Slot.start_at >= at(self.day, time.min),
                Slot.start_at < at(self.day + timedelta(days=1), time.min),
            )
            .order_by(Slot.start_at)
        ).all()
        self.taken = set(
            self.db.scalars(
                select(Appointment.patient_id).where(
                    Appointment.doctor_id == self.doctor.id,
                    Appointment.appt_date == self.day,
                    Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
                )
            )
        )
        booked_share = sum(1 for s in slots if s.status == "booked") / max(len(slots), 1)
        if booked_share >= target:
            return
        fill_probability = (target - booked_share) / (1 - booked_share)
        for slot in slots:
            if slot.status != "free" or self.rng.random() > fill_probability:
                continue
            patient_id = int(self.rng.choice(self._patient_ids()))
            if patient_id in self.taken:
                continue
            try:
                book_as_simulator(self.db, patient_id, slot.id, booking_time)
            except ToolError:
                continue
            self.taken.add(patient_id)

    def plan(self) -> None:
        p, rng = self.p, self.rng
        appointments = self.db.scalars(
            select(Appointment)
            .join(Slot)
            .where(
                Appointment.doctor_id == self.doctor.id,
                Appointment.appt_date == self.day,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            )
            .order_by(Slot.start_at)
        ).all()
        self.stats.booked = len(appointments)
        for appt in appointments:
            if rng.random() < p.no_show_rate:
                continue
            start = appt.slot.start_at
            if rng.random() < p.late_rate:
                arrival = start + _minutes(rng.uniform(16, 45))
            else:
                arrival = start + _minutes(np.clip(rng.normal(-10, 8), -40, 12))
            self.schedule(max(arrival, self.open_at - timedelta(minutes=45)), "booked", appointment_id=appt.id)

        rate = float(rng.uniform(*p.walk_in_load)) * 60.0 / self.doctor.slot_minutes
        t, last = self.open_at - timedelta(minutes=15), self.close_at - timedelta(minutes=45)
        while True:
            t += _minutes(rng.exponential(60.0 / rate))
            if t > last:
                break
            self.schedule(t, "walk_in")

        delay = rng.exponential(p.start_delay_mean_min)
        if rng.random() < p.big_delay_rate:
            delay += rng.uniform(20, 45)
        self.start_delay = int(round(delay))
        self.break_at = self.open_at + _minutes(rng.uniform(100, 150)) if rng.random() < p.break_rate else None
        self.break_len = int(rng.integers(10, 21))
        span = (self.close_at - self.open_at).total_seconds() / 60
        self.emergency_at = (
            self.open_at + _minutes(rng.uniform(30, span - 30)) if rng.random() < p.emergency_rate else None
        )
        self.emergency_len = int(rng.integers(15, 36))
        if rng.random() < p.unavailable_rate:
            self.schedule(self.open_at + _minutes(rng.uniform(60, span - 60)), "unavailable")

    # ---------------------------------------------------------------- actions

    def _apply(self, when: datetime, kind: str, data: dict) -> None:
        db, actor = self.db, self.actor
        if self.stats.unavailable:
            return
        if kind == "booked":
            entry = engine.check_in(db, actor, data["appointment_id"], now=when)
            self._session(entry["session_id"])
            self.stats.arrived += 1
        elif kind == "walk_in":
            entry = self._walk_in(when)
            if entry and self.rng.random() < self.p.priority_rate:
                engine.set_priority(db, actor, entry["entry_id"], 1, now=when)
        elif kind == "return":
            engine.mark_returned(db, actor, data["entry_id"], now=when)
        elif kind == "unavailable":
            session = self._ensure_session()
            engine.record_doctor_event(db, actor, session.id, "unavailable", reason="called away", now=when)
            self.stats.events.append("unavailable")
            self.stats.unavailable = True

    def _walk_in(self, when: datetime) -> dict | None:
        rng = self.rng
        try:
            if rng.random() < self.p.new_walk_in_patient_rate:
                first = hospital.FIRST_NAMES[rng.integers(len(hospital.FIRST_NAMES))]
                last = hospital.LAST_NAMES[rng.integers(len(hospital.LAST_NAMES))]
                entry = engine.register_walk_in(
                    self.db, self.actor, self.doctor.id, name=f"{first} {last}",
                    birth_year=int(rng.integers(1940, 2024)), phone=random_phone(rng),
                    language=str(rng.choice(["mr", "hi", "en"])), now=when,
                )  # fmt: skip
            else:
                patient_id = int(rng.choice(self._patient_ids()))
                if patient_id in self.taken:
                    return None
                self.taken.add(patient_id)
                entry = engine.register_walk_in(self.db, self.actor, self.doctor.id, patient_id=patient_id, now=when)
        except ToolError as err:
            if err.code == "ALREADY_CHECKED_IN":
                return None
            raise
        self._session(entry["session_id"])
        self.stats.walk_ins += 1
        return entry

    def _patient_ids(self) -> list[int]:
        if self._pids is None:
            self._pids = simulated_patient_ids(self.db)
        return self._pids

    def _session(self, session_id: int) -> QueueSession:
        if self.session is None:
            self.session = self.db.get(QueueSession, session_id)
        return self.session

    def _ensure_session(self) -> QueueSession:
        if self.session is None:
            self.session = engine.get_or_create_session(self.db, self.doctor.id, self.day)
        return self.session

    def advance_to(self, until: datetime) -> None:
        while self.pending and self.pending[0][0] <= until:
            when, _, kind, data = heapq.heappop(self.pending)
            self._apply(when, kind, data)

    def consult_minutes(self) -> float:
        mean = self.doctor.slot_minutes * self.speed
        sigma = self.p.consult_sigma
        return max(3.0, float(self.rng.lognormal(np.log(mean) - sigma**2 / 2, sigma)))

    # ---------------------------------------------------------------- run

    def run(self) -> SessionStats:
        db, actor, rng = self.db, self.actor, self.rng
        self.fill_bookings()
        self.plan()
        session = self._ensure_session()
        if self.start_delay >= 15:
            self.advance_to(self.open_at)
            if not self.stats.unavailable:
                engine.record_doctor_event(
                    db,
                    actor,
                    session.id,
                    "delay",
                    minutes=self.start_delay,
                    reason="doctor running late",
                    now=self.open_at,
                )
                self.stats.events.append(f"delay {self.start_delay}m")
        clock = self.open_at + timedelta(minutes=self.start_delay)

        while True:
            self.advance_to(clock)
            if self.stats.unavailable:
                break
            if self.break_at and clock >= self.break_at:
                engine.record_doctor_event(
                    db, actor, session.id, "break", minutes=self.break_len, reason="tea break", now=clock
                )
                self.stats.events.append(f"break {self.break_len}m")
                self.break_at = None
                clock += timedelta(minutes=self.break_len)
                continue
            if self.emergency_at and clock >= self.emergency_at:
                engine.record_doctor_event(
                    db, actor, session.id, "emergency", minutes=self.emergency_len, reason="emergency case", now=clock
                )
                self.stats.events.append(f"emergency {self.emergency_len}m")
                self.emergency_at = None
                clock += timedelta(minutes=self.emergency_len)
                continue
            called = engine.call_next(db, actor, session.id, now=clock)
            if called is None:
                if all(kind == "unavailable" for _, _, kind, _ in self.pending):
                    break
                clock = max(clock, self.pending[0][0])
                continue
            if rng.random() < self.p.missed_turn_rate:
                clock += timedelta(minutes=2)
                self.advance_to(clock)
                if self.stats.unavailable:  # the called patient's entry was closed
                    break
                engine.mark_missed_turn(db, actor, called["entry_id"], now=clock)
                self.stats.missed_turns += 1
                if rng.random() < self.p.return_after_miss_rate:
                    self.schedule(clock + _minutes(rng.uniform(5, 25)), "return", entry_id=called["entry_id"])
                continue
            clock += timedelta(minutes=1)
            self.advance_to(clock)
            if self.stats.unavailable:  # the called patient's entry was closed
                break
            engine.start_consultation(db, actor, called["entry_id"], now=clock)
            clock += _minutes(self.consult_minutes())
            self.advance_to(clock)
            engine.end_consultation(db, actor, called["entry_id"], now=clock)
            self.stats.seen += 1

        if not self.stats.unavailable:
            engine.close_session(db, actor, session.id, now=clock + timedelta(minutes=1))
        self.pending.clear()
        return self.stats


def replay_day(db: Session, day: date, seed: int = 42, params: SimParams | None = None) -> dict:
    """Simulate every OPD session on ``day``. Doctors already replayed for that day are skipped."""
    params = params or SimParams()
    rng = np.random.default_rng([seed, day.toordinal()])
    ensure_slots(db, day, day)
    doctors = [d for d in db.scalars(select(Doctor).order_by(Doctor.id)) if day.isoweekday() in d.opd_days]
    done = set(db.scalars(select(QueueSession.doctor_id).where(QueueSession.date == day)))
    sessions = []
    for doctor in doctors:
        if doctor.id in done:
            continue
        stats = SessionSimulator(db, doctor, day, rng, params).run()
        db.commit()
        sessions.append(stats)
    return {"date": day.isoformat(), "sessions": [vars(s) for s in sessions], "skipped": len(done)}


def history_days(end: date, days: int) -> list[date]:
    return [end - timedelta(days=i) for i in range(days, 0, -1)]
