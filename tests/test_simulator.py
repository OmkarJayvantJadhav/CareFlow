"""Foundation gate: the simulator replays a full hospital day (and TC-17 demo reset)."""

import heapq
from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.db.models import OPERATIONAL_TABLES, Appointment, Patient, QueueSession
from app.tools.booking import book_appointment
from app.tools.permissions import Actor
from simulator.day import SimParams, replay_day
from simulator.seed import reset_demo, seed_all
from simulator.validate import validate_day
from tests.conftest import NOW, TODAY

REPLAY_DAY = date(2026, 10, 14)  # a Wednesday: 9 doctors in OPD


def snapshot(db) -> dict[str, str]:
    """A fingerprint of every operational table's full contents."""
    out = {}
    for table in OPERATIONAL_TABLES:
        out[table] = db.execute(
            text(f"SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {table} t")
        ).scalar_one()
    return out


@pytest.fixture
def seeded(factory):
    db = factory()
    seed_all(db, TODAY, seed=42, days_ahead=3)
    db.commit()
    yield db
    db.close()


def test_gate_replays_a_full_hospital_day(seeded):
    replay = replay_day(seeded, REPLAY_DAY, seed=42)
    assert len(replay["sessions"]) == 9
    report = validate_day(seeded, REPLAY_DAY)
    assert report["ok"], report["violations"]
    assert report["sessions"] == 9
    assert report["patients_seen"] > 80
    assert report["entries"]["walk_in"] > 0 and report["entries"]["booked"] > 0
    assert report["appointments"].get("no_show", 0) > 0
    assert 0 < report["wait_minutes"]["median"] < 90


def test_replay_is_idempotent_per_doctor(seeded):
    replay_day(seeded, REPLAY_DAY, seed=42)
    again = replay_day(seeded, REPLAY_DAY, seed=42)
    assert again["sessions"] == [] and again["skipped"] == 9


def test_replay_with_frequent_disruptions_stays_consistent(seeded):
    params = SimParams(unavailable_rate=0.5, emergency_rate=0.8, break_rate=1.0, missed_turn_rate=0.2, late_rate=0.3)
    replay_day(seeded, REPLAY_DAY, seed=7, params=params)
    report = validate_day(seeded, REPLAY_DAY)
    assert report["ok"], report["violations"]
    assert report["events"].get("unavailable", 0) > 0
    assert report["appointments"].get("displaced", 0) > 0
    assert report["notifications"] > 0


def test_replay_on_a_sunday_has_no_sessions(seeded):
    replay = replay_day(seeded, date(2026, 10, 18), seed=42)
    assert replay["sessions"] == []
    assert validate_day(seeded, date(2026, 10, 18))["ok"]


def test_seed_is_consistent(seeded):
    assert seeded.scalar(select(func.count()).select_from(Patient)) == 402
    statuses = set(seeded.scalars(select(Appointment.status)))
    assert statuses == {"booked", "completed"}
    assert seeded.scalar(select(func.count()).select_from(QueueSession)) == 0


def test_tc17_demo_reset_restores_seed_snapshot(seeded):
    before = snapshot(seeded)
    # A visitor makes changes: a booking, then a full day's replay.
    asha = seeded.execute(text("SELECT id, role, patient_id FROM app_user WHERE username = 'asha'")).one()
    free = seeded.execute(
        text("SELECT id FROM slot WHERE status = 'free' AND start_at > :t ORDER BY start_at LIMIT 1"), {"t": NOW}
    ).scalar_one()
    book_appointment(seeded, Actor(asha.id, asha.role, asha.patient_id), asha.patient_id, free, confirmed=True, now=NOW)
    replay_day(seeded, REPLAY_DAY, seed=42)
    seeded.commit()
    assert snapshot(seeded) != before

    reset_demo(seeded, TODAY, seed=42, days_ahead=3)
    seeded.commit()
    assert snapshot(seeded) == before


def test_doctor_leaving_between_call_and_consultation(seeded, monkeypatch):
    """Regression: the doctor becomes unavailable while a called patient walks in."""
    from datetime import timedelta

    import numpy as np

    from app.db.models import Doctor
    from app.queue import engine
    from simulator.day import SessionSimulator

    class LeavesAfterFirstCall(SessionSimulator):
        def plan(self):
            super().plan()
            self.pending = [p for p in self.pending if p[2] != "unavailable"]
            heapq.heapify(self.pending)

    real_call_next = engine.call_next
    sim_holder = {}

    def call_next(*args, **kwargs):
        called = real_call_next(*args, **kwargs)
        sim = sim_holder["sim"]
        if called and not sim.left_scheduled:
            sim.left_scheduled = True
            sim.schedule(kwargs["now"] + timedelta(seconds=30), "unavailable")
        return called

    monkeypatch.setattr(engine, "call_next", call_next)
    doctor = seeded.scalars(select(Doctor).where(Doctor.name == "Dr. Suresh Pawar")).one()
    sim = LeavesAfterFirstCall(seeded, doctor, REPLAY_DAY, np.random.default_rng(3), SimParams(missed_turn_rate=0.0))
    sim.left_scheduled = False
    sim_holder["sim"] = sim
    stats = sim.run()
    seeded.commit()
    assert sim.left_scheduled and stats.unavailable and stats.seen == 0
