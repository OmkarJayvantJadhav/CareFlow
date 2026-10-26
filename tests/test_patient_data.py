"""Phase 7C: real patient data - encrypted phone numbers, staff patient records, export and erasure."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.config import get_settings
from app.db.models import Appointment, AppUser, AuditLog, CaregiverLink, Notification, Patient, Slot, WaitingList
from app.queue import engine
from app.safety import pii
from app.tools import patients, registration
from app.tools.booking import book_appointment
from app.tools.errors import ToolError
from app.tools.notify import notify
from app.tools.waiting_list import join_waiting_list
from tests.conftest import NOW, TODAY
from tests.test_api import headers, login

SATURDAY = TODAY + timedelta(days=5)


@pytest.fixture
def api(world, frozen_clock):
    return TestClient(app)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(api, username="meena", phone="98220 12345", password="tulsi-garden-42"):
    body = {"name": "Meena Rao", "username": username, "password": password, "birth_year": 1988, "phone": phone,
            "language": "mr"}  # fmt: skip
    made = api.post("/api/v1/auth/register", json=body)
    assert made.status_code == 201, made.text
    return made.json()


# --------------------------------------------------------------------------- phone numbers


@pytest.mark.parametrize("typed", ["9822012345", "+91 98220 12345", "098220-12345", "91 9822012345"])
def test_mobile_numbers_are_read_the_way_people_type_them(typed):
    assert pii.normalize_mobile(typed) == "9822012345"


@pytest.mark.parametrize("typed", ["12345", "5822012345", "98220123456789", ""])
def test_impossible_mobile_numbers_are_refused(typed):
    with pytest.raises(ToolError):
        pii.normalize_mobile(typed)


def test_phone_numbers_are_encrypted_and_findable_but_not_readable(world, monkeypatch):
    patient = Patient(name="Test Person", birth_year=1990, preferred_language="en")
    digits = pii.set_phone(patient, "+91 98220 12345")
    assert patient.phone_masked == "+91 98XXXXXX45" and "9822012345" not in patient.phone_encrypted
    assert pii.decrypt_phone(patient.phone_encrypted) == digits
    assert pii.encrypt_phone(digits) != pii.encrypt_phone(digits)  # a fresh nonce every time
    assert patient.phone_hash == pii.phone_index("9822012345")
    monkeypatch.setattr(get_settings(), "data_key", "A" * 43 + "=")  # another 32-byte key
    assert pii.decrypt_phone(patient.phone_encrypted) is None  # unreadable without the key it was written with
    monkeypatch.setattr(get_settings(), "data_key", "c2hvcnQ=")
    with pytest.raises(RuntimeError):
        pii.encrypt_phone(digits)


def test_sign_up_and_profile_store_the_number_encrypted(api, world):
    made = register(api)
    meena = world.db.scalars(select(Patient).where(Patient.name == "Meena Rao")).one()
    assert pii.decrypt_phone(meena.phone_encrypted) == "9822012345"
    token = made["token"]
    assert api.patch("/api/v1/me/profile", json={"phone": "9890011122"}, headers=bearer(token)).status_code == 200
    world.db.refresh(meena)
    assert pii.decrypt_phone(meena.phone_encrypted) == "9890011122" and meena.phone_masked == "+91 98XXXXXX22"


# --------------------------------------------------------------------------- staff patient records


def test_staff_find_patients_by_name_number_or_record(api, world):
    register(api)
    staff = headers(login(api, "staff"))
    by_name = api.get("/api/v1/staff/patients", params={"q": "meena  RAO"}, headers=staff).json()["patients"]
    assert [p["name"] for p in by_name] == ["Meena Rao"] and by_name[0]["username"] == "meena"
    by_phone = api.get("/api/v1/staff/patients", params={"q": "+91 98220-12345"}, headers=staff).json()
    assert [p["name"] for p in by_phone["patients"]] == ["Meena Rao"]
    pid = by_name[0]["patient_id"]
    assert (
        api.get("/api/v1/staff/patients", params={"q": f"#{pid}"}, headers=staff).json()["patients"][0]["patient_id"]
        == pid
    )
    assert api.get("/api/v1/staff/patients", params={"q": "9999999999"}, headers=staff).json()["patients"] == []
    assert api.get("/api/v1/staff/patients", params={"q": "a"}, headers=staff).status_code == 400
    for role in ("patient", "doctor"):
        assert (
            api.get("/api/v1/staff/patients", params={"q": "meena"}, headers=headers(login(api, role))).status_code
            == 403
        )


@pytest.fixture
def allergies(world):
    """An extra registration question; registration questions are configuration and outlive a test."""
    admin = world.user("mehta")
    body = {"labels": {"en": "Allergies", "hi": "एलर्जी", "mr": "ॲलर्जी"}, "kind": "text"}
    field = registration.create_registration_field(world.db, admin, body, now=NOW)
    world.db.commit()
    yield field
    world.db.rollback()
    registration.update_registration_field(world.db, admin, field["field_id"], {**body, "active": False}, now=NOW)
    world.db.commit()


def test_staff_correct_a_record_and_every_change_is_audited(api, world, allergies):
    made = register(api)
    pid = made["user"]["patient_id"]
    staff = headers(login(api, "staff"))
    key = allergies["key"]
    change = {"name": "Meena S. Rao", "phone": "9765400011", "pregnant": True, "answers": {key: "Penicillin"}}
    updated = api.patch(f"/api/v1/staff/patients/{pid}", json=change, headers=staff)
    assert updated.status_code == 200, updated.text
    record = updated.json()
    assert record["name"] == "Meena S. Rao" and record["phone_masked"] == "+91 97XXXXXX11"
    assert record["answers"] == {key: "Penicillin"} and "pregnant" in record["categories"]
    assert api.get("/api/v1/me", headers=bearer(made["token"])).json()["display_name"] == "Meena S. Rao"
    cleared = api.patch(f"/api/v1/staff/patients/{pid}", json={"answers": {}}, headers=staff).json()
    assert cleared["answers"] == {}  # an optional answer can be cleared
    audit = world.db.scalars(select(AuditLog).where(AuditLog.tool == "update_patient")).all()
    assert len(audit) == 2 and "9765400011" not in str(audit[0].arguments)
    bad = api.patch(f"/api/v1/staff/patients/{pid}", json={"birth_year": 1850}, headers=staff)
    assert bad.status_code == 400
    assert api.patch(f"/api/v1/staff/patients/{pid}", json={"phone": "12345"}, headers=staff).status_code == 400


def test_the_full_number_is_shown_only_on_an_audited_request(api, world):
    pid = register(api)["user"]["patient_id"]
    staff = headers(login(api, "staff"))
    shown = api.post(f"/api/v1/staff/patients/{pid}/phone", headers=staff)
    assert shown.json()["phone"] == "+91 98220 12345"
    row = world.db.scalars(select(AuditLog).where(AuditLog.tool == "reveal_patient_phone")).one()
    assert row.role == "staff" and "12345" not in str(row.result)  # the look is recorded, the number is not
    patient = headers(login(api, "patient"))
    assert api.post(f"/api/v1/staff/patients/{pid}/phone", headers=patient).status_code == 403
    legacy = world.patient("Vinayak Deshmukh")
    legacy.phone_encrypted = None  # a record from before numbers were encrypted
    world.db.commit()
    missing = api.post(f"/api/v1/staff/patients/{legacy.id}/phone", headers=staff)
    assert missing.status_code == 404 and "masked number" in missing.json()["error"]["message"]


def test_duplicates_match_the_exact_number(world):
    a = world.db.scalars(select(Patient).where(Patient.name == "Asha Patil")).one()
    found = registration.find_duplicates(world.db, world.staff, "Someone Else", a.birth_year, "9822011234", now=NOW)
    assert [m["patient_id"] for m in found["matches"]] == [a.id] and found["matches"][0]["reasons"] == ["same_phone"]
    near = registration.find_duplicates(world.db, world.staff, "Someone Else", a.birth_year, "9822099934", now=NOW)
    assert near["matches"] == []  # same first and last digits used to count as the same number


# --------------------------------------------------------------------------- erasure and export


def _busy_patient(world):
    """Asha with a future booking, a waiting-list request, a caregiver, a message and a notification."""
    asha = world.asha
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    slots = world.slots(kulkarni, SATURDAY)
    appt = book_appointment(world.db, asha, asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    iyer = world.doctor("Dr. Meera Iyer")
    for s in world.slots(iyer, SATURDAY):
        s.status = "blocked"
    join_waiting_list(world.db, asha, asha.patient_id, iyer.id, [SATURDAY.isoformat()], confirmed=True, now=NOW)
    world.db.add(
        CaregiverLink(caregiver_user_id=world.user("rajan").user_id, patient_id=asha.patient_id, verified=True)
    )
    notify(world.db, asha.patient_id, "Your visit is on Saturday.", NOW)
    world.db.commit()
    return appt, slots[0].id


def test_an_admin_erases_a_patients_details_on_request(api, world):
    appt, slot_id = _busy_patient(world)
    pid = world.asha.patient_id
    staff = headers(login(api, "staff"))
    assert api.post(f"/api/v1/admin/patients/{pid}/erase", json={}, headers=staff).status_code == 403
    admin = headers(login(api, "admin"))
    done = api.post(f"/api/v1/admin/patients/{pid}/erase", json={"reason": "Written request, 28 Oct"}, headers=admin)
    assert done.status_code == 200, done.text
    assert done.json()["appointments_cancelled"] == 1 and done.json()["waiting_list_closed"] == 1

    world.db.expire_all()
    p = world.db.get(Patient, pid)
    assert (p.name, p.birth_year, p.phone_masked, p.phone_encrypted, p.phone_hash) == (
        "Erased patient",
        1990,
        "",
        None,
        None,
    )
    assert world.db.get(Appointment, appt["appointment_id"]).status == "cancelled"
    assert world.db.get(Slot, slot_id).status == "free"
    assert world.db.scalars(select(WaitingList).where(WaitingList.patient_id == pid)).one().status == "cancelled"
    assert world.db.scalars(select(Notification).where(Notification.patient_id == pid)).first() is None
    assert world.db.scalars(select(CaregiverLink).where(CaregiverLink.patient_id == pid)).first() is None
    user = world.db.scalars(select(AppUser).where(AppUser.patient_id == pid)).one()
    assert user.username.startswith("erased-") and not user.active and user.password_hash is None
    assert api.post("/api/v1/auth/demo-login", json={"username": "asha"}).status_code == 400
    assert api.get("/api/v1/staff/patients", params={"q": "asha patil"}, headers=staff).json()["patients"] == []
    again = api.post(f"/api/v1/admin/patients/{pid}/erase", json={}, headers=admin)
    assert again.status_code == 409
    with pytest.raises(ToolError):
        book_appointment(world.db, world.staff, pid, world.slots(world.doctor("Dr. Meera Iyer"), SATURDAY)[1].id,
                         confirmed=True, now=NOW)  # fmt: skip


def test_a_patient_in_todays_queue_is_not_erased_mid_visit(world):
    pawar = world.doctor("Dr. Suresh Pawar")
    world.slots(pawar, TODAY)
    entry = engine.register_walk_in(world.db, world.staff, pawar.id, name="Ravi Kale", birth_year=1980,
                                    phone="9822033344", now=NOW)  # fmt: skip
    with pytest.raises(ToolError) as err:
        patients.erase_patient(world.db, world.user("mehta"), entry["patient_id"], now=NOW)
    assert err.value.code == "INVALID_STATE"


def test_patients_download_their_data_and_delete_their_own_account(api, world):
    made = register(api)
    token = made["token"]
    data = api.get("/api/v1/me/export", headers=bearer(token)).json()
    assert data["patient"]["name"] == "Meena Rao" and data["patient"]["phone"] == "+91 98220 12345"
    assert {"appointments", "notifications", "consent_history", "conversations", "queue_visits"} <= set(data)
    assert api.get("/api/v1/me/export", headers=headers(login(api, "staff"))).status_code == 403

    wrong = api.post("/api/v1/me/erase", json={"password": "not-it"}, headers=bearer(token))
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 200  # still signed in
    gone = api.post("/api/v1/me/erase", json={"password": "tulsi-garden-42"}, headers=bearer(token))
    assert gone.status_code == 200 and gone.json()["erased"] is True
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 401
    assert api.post("/api/v1/auth/login", json={"username": "meena", "password": "tulsi-garden-42"}).status_code == 401
    register(api)  # the username is free again

    demo = login(api, "patient")
    refused = api.post("/api/v1/me/erase", json={"password": "x"}, headers=headers(demo))
    assert refused.status_code == 403


def test_caregivers_delete_their_own_account(api, world):
    body = {"account_type": "caregiver", "name": "Sanjay Kale", "username": "sanjay.k", "password": "lotus-pond-88"}
    token = api.post("/api/v1/auth/register", json=body).json()["token"]
    assert api.get("/api/v1/me/export", headers=bearer(token)).json()["account"]["role"] == "caregiver"
    assert api.post("/api/v1/me/erase", json={"password": "lotus-pond-88"}, headers=bearer(token)).status_code == 200
    assert api.post("/api/v1/auth/login", json={"username": "sanjay.k", "password": "lotus-pond-88"}).status_code == 401
