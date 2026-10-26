"""Phase 7A: admins manage accounts; temporary passwords must be replaced; switched-off accounts and old
sign-ins stop working; caregivers sign up themselves; the first admin comes from the environment."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.prompts import system_prompt
from app.api.main import app
from app.config import get_settings
from app.db.models import AppUser, AuditLog
from app.manage import ensure_admin
from tests.conftest import NOW
from tests.test_api import headers, login


@pytest.fixture
def api(world, frozen_clock):
    return TestClient(app)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sign_in(api, username: str, password: str):
    return api.post("/api/v1/auth/login", json={"username": username, "password": password})


def create(api, admin, **body):
    return api.post("/api/v1/admin/accounts", json=body, headers=admin)


def change_password(api, token: str, old: str, new: str = "river-stone-42"):
    return api.post("/api/v1/me/password", json={"current_password": old, "new_password": new}, headers=bearer(token))


def test_admin_creates_a_staff_account_that_must_choose_its_own_password(api, world):
    admin = headers(login(api, "admin"))
    made = create(api, admin, username="nurse.kavya", display_name="Kavya Shetty", role="staff")
    assert made.status_code == 201
    temp = made.json()["temporary_password"]
    assert len(temp) == 12 and made.json()["account"]["must_change_password"] is True

    audit = world.db.scalars(select(AuditLog).where(AuditLog.tool == "create_account")).one()
    assert audit.result["data"]["temporary_password"] == "[redacted]" and temp not in str(audit.result)

    first = sign_in(api, "nurse.kavya", temp)
    assert first.status_code == 200 and first.json()["user"]["must_change_password"] is True
    token = first.json()["token"]
    blocked = api.get("/api/v1/staff/today", headers=bearer(token))
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 200
    assert change_password(api, token, temp, temp).status_code == 400  # must be a different password
    changed = change_password(api, token, temp)
    assert changed.status_code == 200
    assert api.get("/api/v1/staff/today", headers=bearer(changed.json()["token"])).status_code == 200
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 401  # the first sign-in has ended
    assert sign_in(api, "nurse.kavya", temp).status_code == 401


def test_only_admins_manage_accounts_and_patients_are_not_created_here(api):
    staff = headers(login(api, "staff"))
    assert api.get("/api/v1/admin/accounts", headers=staff).status_code == 403
    assert create(api, staff, username="x.y.z", display_name="X Y", role="staff").status_code == 403
    admin = headers(login(api, "admin"))
    assert create(api, admin, username="pat.one", display_name="Pat One", role="patient").status_code == 400
    assert create(api, admin, username="asha", display_name="Another Asha", role="staff").status_code == 409
    assert create(api, admin, username="No Spaces!", display_name="Bad Name", role="staff").status_code == 400
    listed = api.get("/api/v1/admin/accounts", params={"role": "doctor"}, headers=admin).json()
    assert listed["counts"]["doctor"] == 18 and {a["role"] for a in listed["accounts"]} == {"doctor"}


def test_doctor_accounts_belong_to_one_doctor(api, world):
    admin = headers(login(api, "admin"))
    joshi = world.doctor("Dr. Kavita Joshi")
    assert create(api, admin, username="kjoshi", display_name="Kavita Joshi", role="doctor").status_code == 400
    taken = create(api, admin, username="kjoshi", display_name="Kavita Joshi", role="doctor", doctor_id=joshi.id)
    assert taken.status_code == 409  # the seeded dr-joshi account is active
    seeded = world.db.scalars(select(AppUser).where(AppUser.username == "dr-joshi")).one()
    off = api.patch(f"/api/v1/admin/accounts/{seeded.id}", json={"active": False}, headers=admin)
    assert off.status_code == 200 and off.json()["active"] is False
    made = create(api, admin, username="kjoshi", display_name="Kavita Joshi", role="doctor", doctor_id=joshi.id)
    assert made.status_code == 201
    token = change_password(api, sign_in(api, "kjoshi", made.json()["temporary_password"]).json()["token"],
                            made.json()["temporary_password"]).json()["token"]  # fmt: skip
    today = api.get("/api/v1/queue/doctor/today", headers=bearer(token)).json()
    assert today["doctor_name"] == "Dr. Kavita Joshi"
    again = api.patch(f"/api/v1/admin/accounts/{seeded.id}", json={"active": True}, headers=admin)
    assert again.status_code == 409  # two active accounts for one doctor are not allowed


def test_switching_an_account_off_ends_its_sign_ins(api, world):
    admin = headers(login(api, "admin"))
    made = create(api, admin, username="desk.two", display_name="Desk Two", role="staff").json()
    token = change_password(api, sign_in(api, "desk.two", made["temporary_password"]).json()["token"],
                            made["temporary_password"]).json()["token"]  # fmt: skip
    user_id = made["account"]["user_id"]
    assert api.patch(f"/api/v1/admin/accounts/{user_id}", json={"active": False}, headers=admin).status_code == 200
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 401
    off = sign_in(api, "desk.two", "river-stone-42")
    assert off.status_code == 403 and off.json()["error"]["code"] == "ACCOUNT_DISABLED"
    assert sign_in(api, "desk.two", "wrong-password").json()["error"]["code"] == "INVALID_CREDENTIALS"
    api.patch(f"/api/v1/admin/accounts/{user_id}", json={"active": True}, headers=admin)
    assert sign_in(api, "desk.two", "river-stone-42").status_code == 200


def test_admins_cannot_lock_themselves_or_the_hospital_out(api, world):
    admin_view = login(api, "admin")
    admin = headers(admin_view)
    me = admin_view["_user"]["user_id"]
    own = api.patch(f"/api/v1/admin/accounts/{me}", json={"active": False}, headers=admin)
    assert own.status_code == 403
    assert api.patch(f"/api/v1/admin/accounts/{me}", json={"role": "staff"}, headers=admin).status_code == 403
    assert api.post(f"/api/v1/admin/accounts/{me}/reset-password", headers=admin).status_code == 403
    second = create(api, admin, username="admin.two", display_name="Second Admin", role="admin").json()
    token = change_password(api, sign_in(api, "admin.two", second["temporary_password"]).json()["token"],
                            second["temporary_password"]).json()["token"]  # fmt: skip
    # The second admin may switch the first one off; then the only active admin is the second one.
    assert api.patch(f"/api/v1/admin/accounts/{me}", json={"active": False}, headers=bearer(token)).status_code == 200
    demote = api.patch(f"/api/v1/admin/accounts/{second['account']['user_id']}", json={"role": "staff"},
                       headers=bearer(token))  # fmt: skip
    assert demote.status_code == 403  # own role; and it is the last active admin


def test_admin_resets_a_patients_forgotten_password(api, world):
    new = {"name": "Meena Rao", "username": "meena", "password": "tulsi-garden-42", "birth_year": 1988,
           "phone": "9876543210", "language": "en"}  # fmt: skip
    old_token = api.post("/api/v1/auth/register", json=new).json()["token"]
    admin = headers(login(api, "admin"))
    meena = world.db.scalars(select(AppUser).where(AppUser.username == "meena")).one()
    reset = api.post(f"/api/v1/admin/accounts/{meena.id}/reset-password", headers=admin)
    assert reset.status_code == 200
    temp = reset.json()["temporary_password"]
    assert api.get("/api/v1/me", headers=bearer(old_token)).status_code == 401
    assert sign_in(api, "meena", "tulsi-garden-42").status_code == 401
    assert sign_in(api, "meena", temp).json()["user"]["must_change_password"] is True
    turn = api.patch(f"/api/v1/admin/accounts/{meena.id}", json={"role": "staff"}, headers=admin)
    assert turn.status_code == 400  # a patient account stays a patient account


def test_caregivers_sign_up_themselves_and_ask_for_access(api, world):
    body = {"account_type": "caregiver", "name": "Sanjay Kale", "username": "sanjay.k", "password": "lotus-pond-88"}
    made = api.post("/api/v1/auth/register", json=body)
    assert made.status_code == 201
    user = made.json()["user"]
    assert user["role"] == "caregiver" and user["patient_id"] is None and user["patients"] == []
    ask = api.post(
        "/api/v1/caregiver/requests", json={"patient_username": "asha"}, headers=bearer(made.json()["token"])
    )
    assert ask.status_code == 201
    patient = {"name": "No Phone", "username": "no.phone", "password": "lotus-pond-88"}
    assert api.post("/api/v1/auth/register", json=patient).status_code == 400  # patients need birth year and phone


def test_first_admin_from_the_environment(world):
    db = world.db
    result = ensure_admin(db, "Head.Admin", "first-light-2026", "Head Administrator")
    assert "ready" in result
    user = db.scalars(select(AppUser).where(AppUser.username == "head.admin")).one()
    assert user.role == "admin" and user.must_change_password and user.password_hash
    assert "nothing changed" in ensure_admin(db, "other.admin", "first-light-2026", "Other")
    assert db.scalars(select(AuditLog).where(AuditLog.tool == "bootstrap_admin")).one().role == "system"


def test_first_admin_is_refused_for_a_non_admin_username(world):
    with pytest.raises(SystemExit):
        ensure_admin(world.db, "priya", "first-light-2026", "Not Priya")


def test_production_mode_hides_the_demo(api, monkeypatch):
    config = api.get("/api/v1/config").json()
    assert config["demo_mode"] is True and config["allow_registration"] is True
    assert config["hospital"]["name"]["en"] == "Indravani General Hospital"
    prompt = system_prompt("patient", "Asha", {1: "Asha Patil"}, "en", NOW)
    assert "fictional; demo" in prompt
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert api.get("/api/v1/config").json()["demo_mode"] is False
    assert api.post("/api/v1/auth/demo-login", json={"role": "patient"}).status_code == 403
    assert api.post("/api/v1/admin/reset", headers={"Authorization": "Bearer x"}).status_code == 401
    assert "fictional" not in system_prompt("patient", "Asha", {1: "Asha Patil"}, "en", NOW)
