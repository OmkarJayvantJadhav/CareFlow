"""Staff and admin pages: front desk view (S6), dashboard (S8, FR-29, FR-32), demo reset (FR-34, TC-17)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.main import app
from app.api.routes import chat_limiter
from app.db.models import OPERATIONAL_TABLES, Appointment
from app.tools.booking import book_appointment
from tests.conftest import NOW, TODAY


@pytest.fixture
def api(world):
    chat_limiter.reset()
    return TestClient(app)


def auth(client, role: str) -> dict:
    token = client.post("/api/v1/auth/demo-login", json={"role": role}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_front_desk_lists_todays_doctors_and_bookings(api, world, frozen_clock):
    """Monday 19 Oct, 08:00: Dr. Pawar and Dr. Joshi are on duty; Dr. Shaikh (Tue/Thu/Sat) is not."""
    pawar = world.doctor("Dr. Suresh Pawar")
    slot = world.slots(pawar, TODAY)[-1]
    book_appointment(world.db, world.staff, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    body = api.get("/api/v1/staff/today", headers=auth(api, "staff")).json()
    names = [d["doctor_name"] for d in body["doctors"]]
    assert {"Dr. Suresh Pawar", "Dr. Kavita Joshi"} <= set(names) and "Dr. Imran Shaikh" not in names
    pawar_row = next(d for d in body["doctors"] if d["doctor_name"] == "Dr. Suresh Pawar")
    assert pawar_row["bookings"] == [
        {"appointment_id": pawar_row["bookings"][0]["appointment_id"], "time": "13:50", "patient_id": 1,
         "patient_name": "Asha Patil", "categories": [], "status": "booked", "entry_id": None, "token": None,
         "entry_status": None, "checked_in_at": None, "late_minutes": None, "checked_out_at": None}
    ]  # fmt: skip
    assert pawar_row["session_id"] is None and pawar_row["doctor_status"] == "available"
    opened = api.post(f"/api/v1/staff/doctors/{pawar.id}/session", headers=auth(api, "staff")).json()
    again = api.post(f"/api/v1/staff/doctors/{pawar.id}/session", headers=auth(api, "staff")).json()
    assert opened["session_id"] == again["session_id"]  # opening twice reuses today's session
    assert api.get("/api/v1/staff/today", headers=auth(api, "patient")).status_code == 403


def test_dashboard_shows_departments_and_the_latest_evaluation(api, world):
    body = api.get("/api/v1/admin/dashboard", headers=auth(api, "admin")).json()
    assert len(body["departments"]) == 8 and {"waiting", "no_shows_today", "average_delay_min"} <= set(
        body["departments"][0]
    )
    evaluation = body["evaluation"]
    assert evaluation["wait_time"]["model_mae"] < evaluation["wait_time"]["baseline_mae"]  # from ml_wait_time.json
    assert "operations" in body
    assert api.get("/api/v1/admin/dashboard", headers=auth(api, "staff")).status_code == 403


def _snapshot(db) -> dict:
    counts = {t: db.scalar(text(f"SELECT count(*) FROM {t}")) for t in OPERATIONAL_TABLES}
    counts["booked"] = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.status == "booked"))
    db.commit()  # end the read transaction: the reset's TRUNCATE needs every table lock
    return counts


def test_tc17_demo_reset_restores_the_seed(api, world):
    headers = auth(api, "admin")
    assert api.post("/api/v1/admin/reset", headers=headers).json()["status"] == "reset"
    world.db.expire_all()
    seeded = _snapshot(world.db)
    # Visitors change things...
    slot_id = world.db.scalar(text("SELECT id FROM slot WHERE status = 'free' ORDER BY start_at DESC LIMIT 1"))
    patient_id = world.db.scalar(text("SELECT patient_id FROM app_user WHERE username = 'asha'"))
    book_appointment(world.db, world.user("priya"), patient_id, slot_id, confirmed=True)
    world.db.commit()
    assert _snapshot(world.db) != seeded
    # ... and the reset puts every operational table back exactly.
    headers = auth(api, "admin")
    assert api.post("/api/v1/admin/reset", headers=headers).status_code == 200
    world.db.expire_all()
    assert _snapshot(world.db) == seeded
    patient = auth(api, "patient")
    assert api.post("/api/v1/admin/reset", headers=patient).status_code == 403


def test_long_running_demo_keeps_three_weeks_bookable(world):
    from datetime import timedelta

    from app.db.models import Slot
    from simulator.seed import SEED_DAYS_AHEAD, top_up_slots

    added = top_up_slots(world.db, TODAY)
    last_day = world.db.scalar(select(func.max(Slot.start_at)))
    assert added > 0 and last_day.date() >= TODAY + timedelta(days=SEED_DAYS_AHEAD - 2)
    assert top_up_slots(world.db, TODAY) == 0  # only missing slots are ever added
    assert top_up_slots(world.db, TODAY + timedelta(days=7)) > 0  # a week later, the next week is opened
