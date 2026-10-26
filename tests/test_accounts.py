"""Accounts people create themselves: registration, password sign-in, and demo reset keeping them."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.api.passwords import hash_password, verify_password
from app.api.routes import chat_limiter, login_failures, register_limiter
from app.db.models import AppUser, Patient
from tests.conftest import SATURDAY

NEW = {
    "name": "Meena  Rao",
    "username": "Meena.Rao",
    "password": "tulsi-garden-42",
    "birth_year": 1988,
    "phone": "+91 98765 43210",
    "language": "mr",
}


@pytest.fixture
def api(world):
    for limiter in (chat_limiter, register_limiter, login_failures):
        limiter.reset()
    return TestClient(app)


def test_passwords_are_salted_hashes():
    first, second = hash_password("tulsi-garden-42"), hash_password("tulsi-garden-42")
    assert first != second and first.startswith("scrypt$") and "tulsi" not in first
    assert verify_password("tulsi-garden-42", first) and not verify_password("tulsi-garden-43", first)
    assert not verify_password("anything", None) and not verify_password("anything", "not-a-hash")


def test_register_creates_patient_and_signs_in(api, world):
    response = api.post("/api/v1/auth/register", json=NEW)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "meena.rao" and body["user"]["role"] == "patient"
    assert body["user"]["display_name"] == "Meena Rao"
    me = api.get("/api/v1/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["patients"] == [{"patient_id": body["user"]["patient_id"], "name": "Meena Rao"}]
    user = world.db.scalars(select(AppUser).where(AppUser.username == "meena.rao")).one()
    patient = world.db.get(Patient, user.patient_id)
    assert user.self_registered and user.password_hash.startswith("scrypt$")
    assert patient.phone_masked == "+91 98XXXXXX10"  # stored masked only (NFR-08)
    assert (patient.birth_year, patient.preferred_language) == (1988, "mr")


def test_login_with_password(api):
    api.post("/api/v1/auth/register", json=NEW)
    ok = api.post("/api/v1/auth/login", json={"username": "MEENA.RAO", "password": NEW["password"]})
    assert ok.status_code == 200 and ok.json()["user"]["username"] == "meena.rao"
    wrong = api.post("/api/v1/auth/login", json={"username": "meena.rao", "password": "wrong-password"})
    unknown = api.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"] == unknown.json()["error"]  # does not reveal which accounts exist
    demo = api.post("/api/v1/auth/login", json={"username": "asha", "password": "anything"})
    assert demo.status_code == 401  # seeded demo accounts have no password


def test_repeated_failures_are_slowed_down(api):
    api.post("/api/v1/auth/register", json=NEW)
    for _ in range(10):
        api.post("/api/v1/auth/login", json={"username": "meena.rao", "password": "wrong-password"})
    blocked = api.post("/api/v1/auth/login", json={"username": "meena.rao", "password": NEW["password"]})
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


@pytest.mark.parametrize(
    "change, message",
    [
        ({"username": "ab"}, "username"),
        ({"username": "has space"}, "Usernames"),
        ({"password": "short"}, "password"),
        ({"password": "aaaaaaaa"}, "stronger password"),
        ({"phone": "12345"}, "mobile number"),
        ({"birth_year": 1850}, "Birth year"),
        ({"name": " "}, "name"),
    ],
)
def test_register_validates_input(api, change, message):
    response = api.post("/api/v1/auth/register", json={**NEW, **change})
    assert response.status_code == 400
    assert message.lower() in response.json()["error"]["message"].lower()


def test_usernames_are_unique(api):
    assert api.post("/api/v1/auth/register", json=NEW).status_code == 201
    again = api.post("/api/v1/auth/register", json={**NEW, "username": "meena.rao"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "USERNAME_TAKEN"
    taken = api.post("/api/v1/auth/register", json={**NEW, "username": "asha"})
    assert taken.json()["error"]["code"] == "USERNAME_TAKEN"


def test_registered_patient_can_book_and_see_it(api, world, frozen_clock):
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    world.slots(kulkarni, SATURDAY)
    world.db.commit()
    token = api.post("/api/v1/auth/register", json=NEW).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = api.get("/api/v1/me", headers=headers).json()
    slots = api.get(
        f"/api/v1/doctors/{kulkarni.id}/slots", params={"date": SATURDAY.isoformat()}, headers=headers
    ).json()["slots"]
    booked = api.post(
        "/api/v1/appointments",
        json={"patient_id": me["patient_id"], "slot_id": slots[0]["slot_id"], "confirmed": True},
        headers=headers,
    )
    assert booked.status_code in (200, 201)
    mine = api.get(f"/api/v1/patients/{me['patient_id']}/appointments", headers=headers).json()
    assert [a["slot_id"] for a in mine["upcoming"]] == [slots[0]["slot_id"]]


def test_demo_reset_keeps_own_accounts(api, world):
    api.post("/api/v1/auth/register", json=NEW)
    world.db.commit()
    admin = api.post("/api/v1/auth/demo-login", json={"role": "admin"}).json()["token"]
    reset = api.post("/api/v1/admin/reset", headers={"Authorization": f"Bearer {admin}"})
    assert reset.status_code == 200
    again = api.post("/api/v1/auth/login", json={"username": "meena.rao", "password": NEW["password"]})
    assert again.status_code == 200
    patient = world.db.get(Patient, again.json()["user"]["patient_id"])
    assert patient.name == "Meena Rao" and patient.phone_masked == "+91 98XXXXXX10"
