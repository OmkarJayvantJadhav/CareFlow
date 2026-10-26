"""Phase 6A: doctor calendars and leave, smart slots, reminders, receipts, profile, notifications,
missed-appointment recovery and utilization. The clock is Monday 19 Oct 2026, 08:00 IST."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.api.routes import chat_limiter, login_failures, register_limiter
from app.db.models import Appointment, Notification, Slot
from app.queue import engine
from app.timeutil import to_ist
from app.tools.booking import book_appointment
from app.tools.calendar import add_doctor_leave, consult_minutes
from app.tools.receipts import appointment_from_code, reference_code
from app.tools.reminders import send_due_reminders
from simulator.seed import ensure_slots
from tests.conftest import NOW, SATURDAY, TODAY


@pytest.fixture
def api(world, frozen_clock):
    for limiter in (chat_limiter, register_limiter, login_failures):
        limiter.reset()
    return TestClient(app)


def auth(client, role: str) -> dict:
    token = client.post("/api/v1/auth/demo-login", json={"role": role}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def book(world, doctor_name: str, day: date, index: int = 0) -> Appointment:
    doctor = world.doctor(doctor_name)
    slot = world.slots(doctor, day)[index]
    result = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    return world.db.get(Appointment, result["appointment_id"])


# --------------------------------------------------------------------------- calendar and leave (2, 13)


def test_calendar_shows_each_day_for_staff_only(api, world):
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    world.slots(kulkarni, SATURDAY)
    book(world, "Dr. Anand Kulkarni", SATURDAY)
    body = api.get(
        f"/api/v1/staff/doctors/{kulkarni.id}/calendar", params={"start": TODAY.isoformat(), "days": 7},
        headers=auth(api, "staff"),
    ).json()  # fmt: skip
    saturday = next(d for d in body["days"] if d["date"] == SATURDAY.isoformat())
    assert saturday["works"] and saturday["booked"] == 1 and saturday["free"] == len(saturday["slots"]) - 1
    assert body["consultation_minutes"]["source"] == "slot"  # no visit history in this world
    patient = api.get(f"/api/v1/staff/doctors/{kulkarni.id}/calendar", headers=auth(api, "patient"))
    assert patient.status_code == 403


def test_block_and_reopen_a_slot(api, world):
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    free, taken = world.slots(kulkarni, SATURDAY)[:2]
    world.db.commit()
    book(world, "Dr. Anand Kulkarni", SATURDAY, index=1)
    staff = auth(api, "staff")
    assert api.post(f"/api/v1/staff/slots/{free.id}/block", headers=staff).json()["status"] == "blocked"
    refused = api.post(f"/api/v1/staff/slots/{taken.id}/block", headers=staff)
    assert refused.status_code == 409 and "booked" in refused.json()["error"]["message"]
    assert api.post(f"/api/v1/staff/slots/{free.id}/unblock", headers=staff).json()["status"] == "free"


def test_leave_blocks_slots_and_tells_booked_patients(api, world):
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    appt = book(world, "Dr. Anand Kulkarni", SATURDAY)
    staff = auth(api, "staff")
    today = api.post(
        f"/api/v1/staff/doctors/{kulkarni.id}/leave",
        json={"start_date": TODAY.isoformat(), "end_date": TODAY.isoformat()}, headers=staff,
    )  # fmt: skip
    assert today.status_code == 400  # today's absence is "Unavailable today" on the queue
    added = api.post(
        f"/api/v1/staff/doctors/{kulkarni.id}/leave",
        json={"start_date": SATURDAY.isoformat(), "end_date": SATURDAY.isoformat(), "reason": "Conference"},
        headers=staff,
    )
    assert added.status_code == 201
    body = added.json()
    assert body["affected"] == [{"appointment_id": appt.id, "patient_id": appt.patient_id}]
    world.db.expire_all()
    assert world.db.get(Appointment, appt.id).status == "displaced"
    statuses = {s.status for s in world.slots(kulkarni, SATURDAY)}
    assert statuses == {"blocked"}
    note = world.db.scalars(select(Notification).where(Notification.appointment_id == appt.id)).one()
    assert note.kind == "unavailable" and "on leave" in note.message
    overlap = api.post(
        f"/api/v1/staff/doctors/{kulkarni.id}/leave",
        json={"start_date": SATURDAY.isoformat(), "end_date": (SATURDAY + timedelta(days=7)).isoformat()},
        headers=staff,
    )
    assert overlap.status_code == 409
    # Cancelling the leave reopens the slots, except the one the displaced patient still holds.
    assert api.delete(f"/api/v1/staff/leave/{body['leave_id']}", headers=staff).json()["slots_reopened"] > 0
    world.db.expire_all()
    reopened = [s for s in world.slots(kulkarni, SATURDAY) if s.status == "free"]
    assert reopened and appt.slot_id not in {s.id for s in reopened}


def test_slots_created_later_on_a_leave_day_start_blocked(world):
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    far = SATURDAY + timedelta(days=21)  # beyond the slots created so far
    add_doctor_leave(world.db, world.staff, kulkarni.id, far, far, "Training", now=NOW)
    ensure_slots(world.db, far, far)
    statuses = {s.status for s in world.slots(kulkarni, far)}
    assert statuses == {"blocked"}


def test_consultation_length_comes_from_history_when_there_is_enough(world):
    pawar = world.doctor("Dr. Suresh Pawar")
    assert consult_minutes(world.db, [pawar.id], NOW)[pawar.id] == {
        "typical": pawar.slot_minutes, "long": pawar.slot_minutes, "visits": 0, "source": "slot",
    }  # fmt: skip


# --------------------------------------------------------------------------- smart slots (3, 14)


def test_recommendations_rank_and_explain(api, world):
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    for offset in range(8):
        ensure_slots(world.db, TODAY + timedelta(days=offset), TODAY + timedelta(days=offset))
    world.db.commit()
    asha = world.asha.patient_id
    body = api.get(
        "/api/v1/recommendations", params={"patient_id": asha, "specialty": "cardiology", "time_of_day": "afternoon"},
        headers=auth(api, "patient"),
    ).json()  # fmt: skip
    slots = body["slots"]
    assert slots, body
    assert all(s["department"] == "Cardiology" for s in slots)
    assert "earliest" in slots[0]["reasons"] or any("earliest" in s["reasons"] for s in slots)
    afternoon = [s for s in slots if "preferred_time" in s["reasons"]]
    assert afternoon and all(int(s["time"][:2]) >= 12 for s in afternoon)
    per_day = {}
    for s in slots:
        per_day[(s["doctor_id"], s["date"])] = per_day.get((s["doctor_id"], s["date"]), 0) + 1
    assert max(per_day.values()) <= 2
    # A day on which Asha already sees the doctor is not offered again (duplicate rule).
    book(world, "Dr. Anand Kulkarni", SATURDAY)
    again = api.get(
        "/api/v1/recommendations", params={"patient_id": asha, "doctor_id": kulkarni.id},
        headers=auth(api, "patient"),
    ).json()["slots"]  # fmt: skip
    assert SATURDAY.isoformat() not in {s["date"] for s in again}
    other = world.other_patients(1)[0]
    refused = api.get("/api/v1/recommendations", params={"patient_id": other, "specialty": "ent"},
                      headers=auth(api, "patient"))  # fmt: skip
    assert refused.status_code == 403


# --------------------------------------------------------------------------- reminders (7)


def test_reminders_are_sent_once_each(world):
    appt = book(world, "Dr. Anand Kulkarni", SATURDAY)
    start = to_ist(appt.slot.start_at)
    assert send_due_reminders(world.db, start - timedelta(days=2)) == 0  # too early
    assert send_due_reminders(world.db, start - timedelta(hours=20)) == 1
    assert send_due_reminders(world.db, start - timedelta(hours=19)) == 0  # already sent
    assert send_due_reminders(world.db, start - timedelta(hours=1)) == 1
    kinds = sorted(world.db.scalars(select(Notification.kind).where(Notification.appointment_id == appt.id)).all())
    assert kinds == ["reminder_day", "reminder_soon"]
    text = world.db.scalars(
        select(Notification.message).where(Notification.kind == "reminder_day", Notification.appointment_id == appt.id)
    ).one()
    assert reference_code(appt.id) in text and "Dr. Anand Kulkarni" in text


def test_booking_less_than_a_day_ahead_skips_the_day_before_reminder(world):
    pawar = world.doctor("Dr. Suresh Pawar")
    slot = world.slots(pawar, TODAY)[-1]
    book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    assert send_due_reminders(world.db, NOW + timedelta(minutes=5)) == 0
    assert send_due_reminders(world.db, to_ist(slot.start_at) - timedelta(hours=1)) == 1


# --------------------------------------------------------------------------- receipts (20)


def test_receipt_and_reference_code(api, world):
    appt = book(world, "Dr. Anand Kulkarni", SATURDAY)
    receipt = api.get(f"/api/v1/appointments/{appt.id}/receipt", headers=auth(api, "patient")).json()
    assert receipt["reference"] == reference_code(appt.id)
    assert appointment_from_code(receipt["reference"]) == appt.id
    tampered = receipt["reference"][:-1] + ("0" if receipt["reference"][-1] != "0" else "1")
    assert appointment_from_code(tampered) is None
    assert appointment_from_code("CF-000001-ZZZZZZ") is None
    assert receipt["patient_phone"].startswith("+91 ") and "X" in receipt["patient_phone"]
    assert (receipt["doctor_name"], receipt["date"]) == ("Dr. Anand Kulkarni", SATURDAY.isoformat())
    mine = api.get(f"/api/v1/patients/{appt.patient_id}/appointments", headers=auth(api, "patient")).json()
    assert mine["upcoming"][0]["reference"] == receipt["reference"]
    assert api.get(f"/api/v1/appointments/{appt.id}/receipt", headers=auth(api, "caregiver")).status_code == 403


# --------------------------------------------------------------------------- profile and notifications (29, 7)


def test_profile_can_be_edited_and_phone_stays_masked(api, world):
    headers = auth(api, "patient")
    before = api.get("/api/v1/me/profile", headers=headers).json()
    assert before["has_password"] is False
    updated = api.patch(
        "/api/v1/me/profile", json={"name": "Asha  P. Patil", "phone": "9123456789", "language": "hi"},
        headers=headers,
    ).json()  # fmt: skip
    assert (updated["name"], updated["phone_masked"], updated["language"]) == ("Asha P. Patil", "+91 91XXXXXX89", "hi")
    assert api.patch("/api/v1/me/profile", json={"phone": "123"}, headers=headers).status_code == 400
    assert api.get("/api/v1/me", headers=headers).json()["display_name"] == "Asha P. Patil"
    demo = api.post("/api/v1/me/password", json={"current_password": "x", "new_password": "longer-pass-1"},
                    headers=headers)  # fmt: skip
    assert demo.status_code == 403
    assert api.get("/api/v1/me/profile", headers=auth(api, "staff")).status_code == 403


def test_password_change_for_own_accounts(api):
    new = {"name": "Meena Rao", "username": "meena", "password": "tulsi-garden-42", "birth_year": 1988,
           "phone": "9876543210", "language": "en"}  # fmt: skip
    token = api.post("/api/v1/auth/register", json=new).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    wrong = api.post("/api/v1/me/password", json={"current_password": "nope", "new_password": "monsoon-tea-7"},
                     headers=headers)  # fmt: skip
    assert wrong.status_code == 401
    ok = api.post(
        "/api/v1/me/password", json={"current_password": "tulsi-garden-42", "new_password": "monsoon-tea-7"},
        headers=headers,
    )  # fmt: skip
    assert ok.json()["status"] == "changed"
    # The old sign-in ends with the password change; the new token from the response works.
    assert api.get("/api/v1/me", headers=headers).status_code == 401
    assert api.get("/api/v1/me", headers={"Authorization": f"Bearer {ok.json()['token']}"}).status_code == 200
    assert api.post("/api/v1/auth/login", json={"username": "meena", "password": "monsoon-tea-7"}).status_code == 200
    assert api.post("/api/v1/auth/login", json={"username": "meena", "password": "tulsi-garden-42"}).status_code == 401


def test_missed_appointment_gets_a_rebooking_offer_in_notifications(api, world):
    pawar = world.doctor("Dr. Suresh Pawar")
    slot = world.slots(pawar, TODAY)[-1]
    result = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    session = engine.get_or_create_session(world.db, pawar.id, TODAY)
    world.db.flush()
    closed = engine.close_session(world.db, world.staff, session.id, now=to_ist(slot.end_at) + timedelta(hours=1))
    world.db.commit()
    assert closed["no_shows"] == 1
    headers = auth(api, "patient")
    notes = api.get("/api/v1/me/notifications", headers=headers).json()
    rebook = [n for n in notes["notifications"] if n["kind"] == "rebook"]
    assert rebook and rebook[0]["appointment_id"] == result["appointment_id"] and notes["unread"] >= 1
    assert api.post("/api/v1/me/notifications/read", headers=headers).json()["marked_read"] >= 1
    assert api.get("/api/v1/me/notifications", headers=headers).json()["unread"] == 0
    assert api.get("/api/v1/me/notifications", headers=auth(api, "staff")).status_code == 403


# --------------------------------------------------------------------------- utilization (15, 16)


def test_utilization_for_admins(api, world):
    for offset in range(7):
        ensure_slots(world.db, TODAY + timedelta(days=offset), TODAY + timedelta(days=offset))
    world.db.commit()
    book(world, "Dr. Anand Kulkarni", SATURDAY)
    body = api.get("/api/v1/admin/utilization", params={"days": 7}, headers=auth(api, "admin")).json()
    cardiology = next(d for d in body["departments"] if d["department"] == "Cardiology")
    assert cardiology["booked"] == 1 and 0 < cardiology["utilization"] < 1
    total_slots = world.db.scalars(select(Slot.id)).all()
    assert sum(d["booked"] + d["free"] + d["blocked"] for d in body["doctors"]) <= len(total_slots)
    assert api.get("/api/v1/admin/utilization", headers=auth(api, "staff")).status_code == 403
