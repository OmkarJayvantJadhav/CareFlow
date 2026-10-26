"""HTTP API (docs §7): auth, REST endpoints, chat end to end, rate limits, errors."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent.llm import ScriptedLLM
from app.api.deps import get_llm
from app.api.main import app
from app.api.routes import chat_limiter
from app.config import get_settings
from app.db.models import Appointment, AuditLog
from tests.conftest import SATURDAY


@pytest.fixture
def api(world, kb, frozen_clock):
    chat_limiter.reset()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def login(client, role="patient", username=None) -> dict:
    body = {"username": username} if username else {"role": role}
    response = client.post("/api/v1/auth/demo-login", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    return {"Authorization": f"Bearer {data['token']}", "_user": data["user"]}


def headers(auth: dict) -> dict:
    return {"Authorization": auth["Authorization"]}


def use_llm(steps):
    llm = ScriptedLLM(steps)
    app.dependency_overrides[get_llm] = lambda: llm
    return llm


def test_demo_login_returns_role_and_linked_patients(api):
    caregiver = login(api, "caregiver")
    assert caregiver["_user"]["role"] == "caregiver"
    assert [p["name"] for p in caregiver["_user"]["patients"]] == ["Vinayak Deshmukh"]
    me = api.get("/api/v1/me", headers=headers(caregiver)).json()
    assert me["username"] == "rajan"


def test_requests_without_a_valid_token_are_rejected(api):
    assert api.get("/api/v1/doctors").status_code == 401
    bad = api.get("/api/v1/doctors", headers={"Authorization": "Bearer abc.def"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "UNAUTHORIZED"


def test_tampered_token_role_is_rejected(api):
    import base64
    import json

    token = login(api)["Authorization"].split()[1]
    body, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims["role"] = "staff"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode() + "." + signature
    assert api.get("/api/v1/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_search_doctors_and_slots(api, world):
    auth = login(api)
    found = api.get(
        "/api/v1/doctors",
        params={"specialty": "cardiology", "language": "mr", "day": "saturday"},
        headers=headers(auth),
    )
    assert [d["name"] for d in found.json()["doctors"]] == ["Dr. Anand Kulkarni"]
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    world.slots(kulkarni, SATURDAY)
    world.db.commit()
    slots = api.get(
        f"/api/v1/doctors/{kulkarni.id}/slots", params={"date": SATURDAY.isoformat()}, headers=headers(auth)
    )
    assert slots.status_code == 200 and slots.json()["slots"]
    bad = api.get("/api/v1/doctors", params={"specialty": "astrology"}, headers=headers(auth))
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (
        api.get("/api/v1/doctors/9999/slots", params={"date": SATURDAY.isoformat()}, headers=headers(auth)).status_code
        == 404
    )


def test_rest_booking_lifecycle_and_error_codes(api, world):
    auth = login(api)
    pid = auth["_user"]["patient_id"]
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    world.db.commit()

    unconfirmed = api.post(
        "/api/v1/appointments", json={"patient_id": pid, "slot_id": slots[0].id}, headers=headers(auth)
    )
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    booked = api.post(
        "/api/v1/appointments",
        json={"patient_id": pid, "slot_id": slots[0].id, "confirmed": True},
        headers=headers(auth),
    )
    assert booked.status_code == 201
    appt_id = booked.json()["appointment_id"]
    dup = api.post(
        "/api/v1/appointments",
        json={"patient_id": pid, "slot_id": slots[1].id, "confirmed": True},
        headers=headers(auth),
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE"

    moved = api.patch(
        f"/api/v1/appointments/{appt_id}", json={"new_slot_id": slots[3].id, "confirmed": True}, headers=headers(auth)
    )
    assert moved.status_code == 200 and moved.json()["slot_id"] == slots[3].id
    history = api.get(f"/api/v1/patients/{pid}/appointments", headers=headers(auth)).json()
    assert [a["appointment_id"] for a in history["upcoming"]] == [appt_id]
    cancelled = api.delete(f"/api/v1/appointments/{appt_id}", params={"confirmed": "true"}, headers=headers(auth))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    # Refused attempts are audited too (the API commits after a rule failure).
    refused = world.db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.result["ok"].as_boolean().is_(False))
    )
    assert refused == 2


def test_permissions_hold_over_http(api, world):
    sunil = login(api, username="sunil")
    father = world.patient("Vinayak Deshmukh")
    response = api.get(f"/api/v1/patients/{father.id}/appointments", headers=headers(sunil))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
    staff = login(api, "staff")
    assert api.post("/api/v1/chat", json={"message": "hi"}, headers=headers(staff)).status_code == 403


def test_chat_booking_end_to_end_over_http(api, world):
    auth = login(api)
    pid = auth["_user"]["patient_id"]
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    slots = world.slots(kulkarni, SATURDAY)
    world.db.commit()
    use_llm(
        [
            lambda m: {"check_availability": {"doctor_id": kulkarni.id, "date": SATURDAY.isoformat()}},
            lambda m: {"book_appointment": {"patient_id": pid, "slot_id": slots[1].id}},
        ]
    )
    first = api.post("/api/v1/chat", json={"message": "Book Dr Kulkarni on Saturday at 09:15"}, headers=headers(auth))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["needs_confirmation"] and body["confirmation"]["summary"]["time"] == "09:15"
    assert body["actions"][0]["label"] == "Checking available slots"
    use_llm([])
    second = api.post(
        "/api/v1/chat",
        json={"conversation_id": body["conversation_id"], "confirm_action_id": body["confirmation"]["action_id"]},
        headers=headers(auth),
    )
    assert second.status_code == 200 and second.json()["actions"][0]["ok"]
    world.db.expire_all()
    assert world.db.scalars(select(Appointment)).one().slot_id == slots[1].id


def test_chat_returns_503_when_no_llm_is_available(api):
    auth = login(api)
    response = api.post("/api/v1/chat", json={"message": "Book an ENT doctor"}, headers=headers(auth))
    assert response.status_code == 503 and response.json()["error"]["code"] == "LLM_UNAVAILABLE"


def test_emergency_is_answered_even_without_an_llm(api):
    auth = login(api)
    response = api.post("/api/v1/chat", json={"message": "my father is unconscious"}, headers=headers(auth))
    assert response.status_code == 200 and response.json()["emergency"] is True


def test_session_message_cap_returns_429_with_retry_after(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_messages_per_session", 2)
    auth = login(api)
    use_llm([lambda m: "Hello!", lambda m: "Hello again!"])
    for _ in range(2):
        assert api.post("/api/v1/chat", json={"message": "hello"}, headers=headers(auth)).status_code == 200
    capped = api.post("/api/v1/chat", json={"message": "hello"}, headers=headers(auth))
    assert capped.status_code == 429 and int(capped.headers["Retry-After"]) > 0
    # A new session (a new login) starts again.
    use_llm([lambda m: "Hi"])
    assert api.post("/api/v1/chat", json={"message": "hello"}, headers=headers(login(api))).status_code == 200


def test_per_ip_rate_limit(api, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_messages_per_ip_per_hour", 1)
    auth = login(api)
    use_llm([lambda m: "Hello!"])
    assert api.post("/api/v1/chat", json={"message": "hello"}, headers=headers(auth)).status_code == 200
    limited = api.post("/api/v1/chat", json={"message": "hello"}, headers=headers(auth))
    assert limited.status_code == 429 and "Retry-After" in limited.headers


def test_chat_input_validation(api):
    auth = login(api)
    assert api.post("/api/v1/chat", json={"message": "   "}, headers=headers(auth)).status_code == 400
    too_long = api.post("/api/v1/chat", json={"message": "x" * 1500}, headers=headers(auth))
    assert too_long.status_code == 400 and too_long.json()["error"]["code"] == "VALIDATION_ERROR"
    other = api.post("/api/v1/chat", json={"message": "hi", "conversation_id": "nope"}, headers=headers(auth))
    assert other.status_code == 404


def test_conversations_are_private_to_their_user(api):
    asha = login(api)
    use_llm([lambda m: "Hello!"])
    conv = api.post("/api/v1/chat", json={"message": "hello"}, headers=headers(asha)).json()["conversation_id"]
    rajan = login(api, "caregiver")
    use_llm([lambda m: "Hi"])
    assert (
        api.post("/api/v1/chat", json={"message": "hello", "conversation_id": conv}, headers=headers(rajan)).status_code
        == 404
    )
