"""Queue REST endpoints and the live WebSocket: FR-21 - FR-28, TC-13, TC-20, NFR-02."""

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.main import app
from app.db.models import QueueSession
from app.tools.booking import book_appointment
from tests.conftest import NOW, TODAY
from tests.test_api import headers, login


@pytest.fixture
def desk(world, kb, frozen_clock):
    """Monday 08:00 (frozen clock): Dr. Pawar's OPD with one booked patient (Asha) at 09:00."""
    doctor = world.doctor("Dr. Suresh Pawar")
    slots = world.slots(doctor, TODAY)
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    world.db.commit()
    client = TestClient(app)
    staff, patient = login(client, "staff"), login(client, "patient")
    yield client, doctor, appt, headers(staff), headers(patient)


def test_front_desk_flow_over_http(desk, world):
    client, doctor, appt, staff, patient = desk
    checked = client.post(f"/api/v1/queue/entries/{appt['appointment_id']}/check-in", headers=staff)
    assert checked.status_code == 201 and checked.json()["token"] == "B01"
    walk = client.post(
        "/api/v1/queue/walk-ins",
        json={"doctor_id": doctor.id, "name": "Ravi Kale", "birth_year": 1980, "phone": "9811122233"},
        headers=staff,
    )
    assert walk.status_code == 201 and walk.json()["token"] == "W01"
    session_id = walk.json()["session_id"]

    listing = client.get("/api/v1/queue/sessions", headers=staff).json()
    assert any(s["session_id"] == session_id and s["waiting"] == 2 for s in listing["sessions"])
    detail = client.get(f"/api/v1/queue/sessions/{session_id}", headers=staff).json()
    assert {e["patient_name"] for e in detail["entries"]} == {"Asha Patil", "Ravi Kale"}

    mine = client.get("/api/v1/queue/mine", headers=patient).json()["entries"]
    assert len(mine) == 1 and mine[0]["token"] == "B01" and mine[0]["estimate"]["display"]
    status = client.get(f"/api/v1/queue/entries/{mine[0]['entry_id']}/status", headers=patient)
    assert status.status_code == 200 and status.json()["ahead"] is not None

    called = client.post(f"/api/v1/queue/sessions/{session_id}/call-next", headers=staff).json()["called"]
    entry_id = called["entry_id"]
    for action in ("start", "end"):
        assert client.post(f"/api/v1/queue/entries/{entry_id}/{action}", headers=staff).status_code == 200


def test_patients_cannot_run_the_desk(desk):
    client, doctor, appt, staff, patient = desk
    walk = client.post(
        "/api/v1/queue/walk-ins",
        json={"doctor_id": doctor.id, "name": "X Y", "birth_year": 1990, "phone": "9811122233"},
        headers=staff,
    ).json()
    refused = client.patch(f"/api/v1/queue/entries/{walk['entry_id']}/priority", json={"priority": 3}, headers=patient)
    assert refused.status_code == 403  # TC-13 over HTTP
    assert (
        client.post(
            f"/api/v1/queue/sessions/{walk['session_id']}/events", json={"type": "unavailable"}, headers=patient
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/queue/entries/{walk['entry_id']}/status", headers=patient).status_code == 403
    assert client.get("/api/v1/queue/sessions", headers=patient).status_code == 403


def test_tc20_websocket_pushes_updates_within_two_seconds(desk):
    client, doctor, appt, staff, patient = desk
    first = client.post(f"/api/v1/queue/entries/{appt['appointment_id']}/check-in", headers=staff).json()
    session_id = first["session_id"]
    token = staff["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/queue/{session_id}?token={token}") as ws:
        initial = [ws.receive_json() for _ in range(3)]
        assert [m["event"] for m in initial] == ["queue.updated", "prediction.updated", "doctor.status"]
        started = time.perf_counter()
        client.post(
            "/api/v1/queue/walk-ins",
            json={"doctor_id": doctor.id, "name": "New Walkin", "birth_year": 1985, "phone": "9822233344"},
            headers=staff,
        )
        update = ws.receive_json()
        elapsed = time.perf_counter() - started
        assert update["event"] == "queue.updated" and {e["token"] for e in update["entries"]} == {"B01", "W01"}
        assert "patient_name" not in update["entries"][0]  # tokens only on the live channel
        prediction = ws.receive_json()
        assert prediction["event"] == "prediction.updated" and len(prediction["predictions"]) == 2
        assert all(p["low_min"] <= p["predicted_min"] <= p["high_min"] for p in prediction["predictions"])
        assert ws.receive_json()["event"] == "doctor.status"
        assert elapsed < 2.0  # NFR-02

        client.post(f"/api/v1/queue/sessions/{session_id}/events", json={"type": "break", "minutes": 15}, headers=staff)
        messages = [ws.receive_json() for _ in range(3)]
        status = next(m for m in messages if m["event"] == "doctor.status")
        assert status["status"] == "on_break"


def test_websocket_requires_a_valid_token_and_access(desk, world):
    client, doctor, appt, staff, patient = desk
    first = client.post(f"/api/v1/queue/entries/{appt['appointment_id']}/check-in", headers=staff).json()
    with pytest.raises(WebSocketDisconnect) as bad:
        with client.websocket_connect(f"/ws/queue/{first['session_id']}?token=nope") as ws:
            ws.receive_json()
    assert bad.value.code == 4401
    rajan = login(client, "caregiver")["Authorization"].split()[1]  # his father is not in this queue
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(f"/ws/queue/{first['session_id']}?token={rajan}") as ws:
            ws.receive_json()
    assert denied.value.code == 4403
    asha = patient["Authorization"].split()[1]  # she is in this queue
    with client.websocket_connect(f"/ws/queue/{first['session_id']}?token={asha}") as ws:
        assert ws.receive_json()["event"] == "queue.updated"


def test_doctor_unavailable_over_http_closes_the_queue(desk, world):
    client, doctor, appt, staff, patient = desk
    first = client.post(f"/api/v1/queue/entries/{appt['appointment_id']}/check-in", headers=staff).json()
    result = client.post(
        f"/api/v1/queue/sessions/{first['session_id']}/events",
        json={"type": "unavailable", "reason": "unwell"},
        headers=staff,
    )
    assert result.status_code == 200 and result.json()["affected"]
    world.db.expire_all()
    assert world.db.get(QueueSession, first["session_id"]).status == "closed"
