"""Phase 6B: check-in (self, by receipt code), patient categories, late arrivals, duplicate detection
and reuse consent, custom registration fields, consent and caregiver access requests.
The clock is Monday 19 Oct 2026, 08:00 IST."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.api.routes import chat_limiter, login_failures, register_limiter
from app.db.models import Notification, Patient
from app.timeutil import to_ist
from app.tools.booking import book_appointment
from app.tools.receipts import reference_code
from app.tools.reminders import send_due_reminders
from tests.conftest import NOW, TODAY

NEW = {"name": "Meena Rao", "username": "meena", "password": "tulsi-garden-42", "birth_year": 1988,
       "phone": "9876543210", "language": "en"}  # fmt: skip


@pytest.fixture
def api(world, frozen_clock):
    for limiter in (chat_limiter, register_limiter, login_failures):
        limiter.reset()
    return TestClient(app)


def auth(client, role: str) -> dict:
    token = client.post("/api/v1/auth/demo-login", json={"role": role}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def book_today(world, index: int = 0):
    """Asha's booking with Dr. Pawar today; slot 0 starts at 09:00."""
    pawar = world.doctor("Dr. Suresh Pawar")
    slot = world.slots(pawar, TODAY)[index]
    result = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    return result, slot


# --------------------------------------------------------------------------- check-in (21, 24, 25, 27, 33)


def test_patients_see_when_they_can_check_in_online(api, world):
    result, slot = book_today(world)  # 09:00 today, the clock is 08:00
    headers = auth(api, "patient")
    mine = api.get(f"/api/v1/patients/{world.asha.patient_id}/appointments", headers=headers).json()
    appt = next(a for a in mine["upcoming"] if a["appointment_id"] == result["appointment_id"])
    assert appt["can_check_in"] is True and appt["token"] is None  # the window opened at 08:00
    entry = api.post(f"/api/v1/queue/entries/{result['appointment_id']}/check-in", headers=headers)
    assert entry.status_code == 201 and entry.json()["token"].startswith("B")
    mine = api.get(f"/api/v1/patients/{world.asha.patient_id}/appointments", headers=headers).json()
    appt = next(a for a in mine["upcoming"] if a["appointment_id"] == result["appointment_id"])
    assert appt["can_check_in"] is False and appt["token"] == entry.json()["token"]


def test_check_in_by_receipt_code_at_the_desk(api, world):
    result, _ = book_today(world, index=3)
    code = reference_code(result["appointment_id"])
    staff = auth(api, "staff")
    looked_up = api.get("/api/v1/staff/check-in/lookup", params={"code": code.lower()}, headers=staff).json()
    assert looked_up["first_name"] == "Asha" and looked_up["today"] and not looked_up["checked_in"]
    entry = api.post("/api/v1/staff/check-in/by-code", json={"code": code}, headers=staff)
    assert entry.status_code == 201
    again = api.post("/api/v1/staff/check-in/by-code", json={"code": code}, headers=staff)
    assert again.status_code == 409
    forged = code[:-1] + ("0" if code[-1] != "0" else "1")
    assert api.get("/api/v1/staff/check-in/lookup", params={"code": forged}, headers=staff).status_code == 404
    assert (
        api.get("/api/v1/staff/check-in/lookup", params={"code": code}, headers=auth(api, "patient")).status_code == 403
    )


def test_front_desk_sees_late_arrival_and_check_out(api, world, monkeypatch):
    result, slot = book_today(world)
    import app.api.admin_routes as admin_routes
    import app.api.registration_routes as registration_routes
    import app.timeutil as timeutil

    late = to_ist(slot.start_at) + timedelta(minutes=12)
    for module in (timeutil, admin_routes, registration_routes):
        monkeypatch.setattr(module, "now_ist", lambda: late)
    staff = auth(api, "staff")
    api.post("/api/v1/staff/check-in/by-code", json={"code": reference_code(result["appointment_id"])}, headers=staff)
    pawar = next(
        d
        for d in api.get("/api/v1/staff/today", headers=staff).json()["doctors"]
        if d["doctor_name"] == "Dr. Suresh Pawar"
    )
    booking = next(b for b in pawar["bookings"] if b["appointment_id"] == result["appointment_id"])
    assert (
        booking["late_minutes"] == 12
        and booking["checked_in_at"] == f"{late:%H:%M}"
        and booking["checked_out_at"] is None
    )


# --------------------------------------------------------------------------- categories (30)


def test_categories_from_birth_year_and_staff(api, world):
    patients = world.db.scalars(select(Patient).order_by(Patient.id)).all()
    senior = next(p for p in patients if NOW.year - p.birth_year >= 60)
    staff = auth(api, "staff")
    body = api.patch(f"/api/v1/staff/patients/{senior.id}/categories", json={"pregnant": False, "disability": True},
                     headers=staff).json()  # fmt: skip
    assert body["categories"] == ["senior", "disability"]
    refused = api.patch(f"/api/v1/staff/patients/{senior.id}/categories", json={"pregnant": True, "disability": False},
                        headers=auth(api, "patient"))  # fmt: skip
    assert refused.status_code == 403


# --------------------------------------------------------------------------- duplicates and reuse consent (34, 48)


def test_duplicate_detection_and_reuse_consent(api, world):
    staff = auth(api, "staff")
    asha = world.db.get(Patient, world.asha.patient_id)
    by_name = api.post(
        "/api/v1/staff/patients/match", json={"name": "  asha   PATIL ", "birth_year": asha.birth_year}, headers=staff
    ).json()["matches"]
    assert by_name[0]["patient_id"] == asha.id and by_name[0]["reasons"] == ["same_name"] and by_name[0]["has_account"]
    other_year = api.post(
        "/api/v1/staff/patients/match", json={"name": "Asha Patil", "birth_year": asha.birth_year + 1}, headers=staff
    ).json()["matches"]
    assert asha.id not in {m["patient_id"] for m in other_year}
    # Asha withdraws consent to reuse her details: the desk can no longer register her by her record.
    patient = auth(api, "patient")
    state = api.put("/api/v1/me/consents/reuse_registration", json={"granted": False}, headers=patient).json()
    assert state["reuse_registration"] is False
    pawar = world.doctor("Dr. Suresh Pawar")
    refused = api.post("/api/v1/queue/walk-ins", json={"doctor_id": pawar.id, "patient_id": asha.id}, headers=staff)
    assert refused.status_code == 403 and "withdrawn consent" in refused.json()["error"]["message"]
    match = api.post("/api/v1/staff/patients/match", json={"name": "Asha Patil", "birth_year": asha.birth_year},
                     headers=staff).json()["matches"][0]  # fmt: skip
    assert match["reuse_allowed"] is False
    api.put("/api/v1/me/consents/reuse_registration", json={"granted": True}, headers=patient)
    ok = api.post("/api/v1/queue/walk-ins", json={"doctor_id": pawar.id, "patient_id": asha.id}, headers=staff)
    assert ok.status_code == 201
    history = api.get("/api/v1/me/consents", headers=patient).json()["history"]
    assert [h["granted"] for h in history[:2]] == [True, False]


# --------------------------------------------------------------------------- custom registration fields (26, 28)


def test_custom_fields_are_asked_and_checked(api, world):
    admin = auth(api, "admin")
    field = {"labels": {"en": "Blood group", "hi": "रक्त समूह", "mr": "रक्तगट"}, "kind": "choice",
             "options": ["A+", "B+", "O+", "AB+"], "required": True}  # fmt: skip
    created = api.post("/api/v1/admin/registration-fields", json=field, headers=admin)
    assert created.status_code == 201 and created.json()["key"] == "blood_group"
    bad = api.post("/api/v1/admin/registration-fields", json={**field, "options": ["only one"]}, headers=admin)
    assert bad.status_code == 400
    twice = api.post("/api/v1/admin/registration-fields", json={**field, "labels": {**field["labels"], "en": "blood  GROUP"}},
                     headers=admin)  # fmt: skip
    assert twice.status_code == 409
    assert api.post("/api/v1/admin/registration-fields", json=field, headers=auth(api, "staff")).status_code == 403
    public = api.get("/api/v1/registration-fields").json()["fields"]
    assert [f["key"] for f in public] == ["blood_group"]
    missing = api.post("/api/v1/auth/register", json=NEW)
    assert missing.status_code == 400 and "Blood group" in missing.json()["error"]["message"]
    wrong = api.post("/api/v1/auth/register", json={**NEW, "answers": {"blood_group": "Z"}})
    assert wrong.status_code == 400
    ok = api.post("/api/v1/auth/register", json={**NEW, "answers": {"blood_group": "O+"}})
    assert ok.status_code == 201
    mine = api.get("/api/v1/me/consents", headers={"Authorization": f"Bearer {ok.json()['token']}"}).json()
    assert mine["answers"] == {"blood_group": "O+"}
    # Switched off, the field is no longer asked; the answers already given are kept.
    off = api.patch(f"/api/v1/admin/registration-fields/{created.json()['field_id']}", json={**field, "active": False},
                    headers=admin)  # fmt: skip
    assert off.json()["active"] is False and api.get("/api/v1/registration-fields").json()["fields"] == []
    pawar = world.doctor("Dr. Suresh Pawar")
    walk_in = api.post(
        "/api/v1/queue/walk-ins",
        json={"doctor_id": pawar.id, "name": "Ramesh Kale", "birth_year": 1979, "phone": "9822012345"},
        headers=auth(api, "staff"),
    )
    assert walk_in.status_code == 201


# --------------------------------------------------------------------------- consent and caregivers (35)


def test_reminders_respect_consent(api, world):
    pawar = world.doctor("Dr. Suresh Pawar")
    slot = world.slots(pawar, TODAY + timedelta(days=1))[0]  # Tuesday 09:00
    result = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    api.put("/api/v1/me/consents/reminders", json={"granted": False}, headers=auth(api, "patient"))
    world.db.expire_all()
    assert send_due_reminders(world.db, to_ist(slot.start_at) - timedelta(hours=1)) == 0
    assert not world.db.scalars(
        select(Notification).where(Notification.appointment_id == result["appointment_id"])
    ).all()
    refused = api.put("/api/v1/me/consents/caregiver_access", json={"granted": True}, headers=auth(api, "patient"))
    assert refused.status_code == 400


def test_caregiver_requests_need_the_patients_approval(api, world):
    rajan = auth(api, "caregiver")  # Rajan, verified for his father Vinayak only
    asha_id = world.asha.patient_id
    assert api.get(f"/api/v1/patients/{asha_id}/appointments", headers=rajan).status_code == 403
    unknown = api.post("/api/v1/caregiver/requests", json={"patient_username": "nobody"}, headers=rajan)
    staff_account = api.post("/api/v1/caregiver/requests", json={"patient_username": "priya"}, headers=rajan)
    assert unknown.status_code == staff_account.status_code == 404
    asked = api.post("/api/v1/caregiver/requests", json={"patient_username": "asha"}, headers=rajan)
    assert asked.status_code == 201 and asked.json()["status"] == "pending"
    assert asked.json()["patient_name"] is None  # a username alone does not reveal who it is
    assert api.get("/api/v1/caregiver/requests", headers=rajan).json()["requests"][0]["patient_name"] is None
    assert api.post("/api/v1/caregiver/requests", json={"patient_username": "asha"}, headers=rajan).status_code == 409
    patient = auth(api, "patient")
    mine = api.get("/api/v1/me/consents", headers=patient).json()
    request_id = mine["requests"][0]["request_id"]
    assert mine["requests"][0]["status"] == "pending"
    note = api.get("/api/v1/me/notifications", headers=patient).json()["notifications"][0]
    assert "asks to manage your CareFlow appointments" in note["message"]
    approved = api.post(f"/api/v1/me/caregiver-requests/{request_id}", json={"approve": True}, headers=patient)
    assert approved.json()["status"] == "approved"
    assert api.get(f"/api/v1/patients/{asha_id}/appointments", headers=rajan).status_code == 200
    again = api.post(f"/api/v1/me/caregiver-requests/{request_id}", json={"approve": False}, headers=patient)
    assert again.status_code == 409
    caregivers = api.get("/api/v1/me/consents", headers=patient).json()["caregivers"]
    link = next(c for c in caregivers if c["name"].startswith("Rajan"))
    assert api.delete(f"/api/v1/me/caregivers/{link['caregiver_user_id']}", headers=patient).status_code == 200
    assert api.get(f"/api/v1/patients/{asha_id}/appointments", headers=rajan).status_code == 403
    assert api.get("/api/v1/me/consents", headers=patient).json()["consents"]["caregiver_access"] is False


def test_demo_reset_keeps_own_consents_and_answers(api, world):
    admin = auth(api, "admin")
    field = {"labels": {"en": "Diet", "hi": "आहार", "mr": "आहार"}, "kind": "text", "required": False}
    api.post("/api/v1/admin/registration-fields", json=field, headers=admin)
    token = api.post("/api/v1/auth/register", json={**NEW, "answers": {"diet": "Vegetarian"}}).json()["token"]
    api.put("/api/v1/me/consents/reminders", json={"granted": False}, headers={"Authorization": f"Bearer {token}"})
    world.db.commit()
    assert api.post("/api/v1/admin/reset", headers=auth(api, "admin")).status_code == 200
    login = api.post("/api/v1/auth/login", json={"username": "meena", "password": NEW["password"]}).json()
    mine = api.get("/api/v1/me/consents", headers={"Authorization": f"Bearer {login['token']}"}).json()
    assert mine["consents"]["reminders"] is False and mine["answers"] == {"diet": "Vegetarian"}
