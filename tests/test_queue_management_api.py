"""Phase 6C endpoints over HTTP: the doctor role, priority requests, transfers, the virtual queue,
coordination and the admin's priority rules."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.main import app
from tests.conftest import TODAY
from tests.test_api import headers, login


@pytest.fixture
def opd(world, kb, frozen_clock):
    """Monday 08:00 (frozen clock): Dr. Pawar and Dr. Joshi in General Medicine, Dr. Kulkarni in Cardiology."""
    pawar, joshi = world.doctor("Dr. Suresh Pawar"), world.doctor("Dr. Kavita Joshi")
    for d in (pawar, joshi, world.doctor("Dr. Anand Kulkarni")):
        world.slots(d, TODAY)
    world.db.commit()
    client = TestClient(app)
    roles = {r: headers(login(client, r)) for r in ("staff", "patient", "admin", "doctor")}
    return client, pawar, joshi, roles


def walk_in(client, doctor_id: int, staff: dict, name: str = "Ravi Kale") -> dict:
    response = client.post(
        "/api/v1/queue/walk-ins",
        json={"doctor_id": doctor_id, "name": name, "birth_year": 1980, "phone": "9822233344"},
        headers=staff,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_demo_doctor_signs_in_to_their_own_queue(opd):
    client, pawar, joshi, roles = opd
    me = client.post("/api/v1/auth/demo-login", json={"role": "doctor"}).json()["user"]
    assert me["role"] == "doctor" and me["username"] == "dr-pawar" and me["doctor_id"] == pawar.id
    first = walk_in(client, pawar.id, roles["staff"])
    today = client.get("/api/v1/queue/doctor/today", headers=roles["doctor"]).json()
    assert today["doctor_name"] == "Dr. Suresh Pawar" and today["session"]["session_id"] == first["session_id"]
    assert today["session"]["entries"][0]["patient_name"] == "Ravi Kale"
    assert all(d["doctor_id"] != pawar.id for d in today["forward_to"])

    other = walk_in(client, joshi.id, roles["staff"], "Mina Rao")
    assert client.get(f"/api/v1/queue/sessions/{other['session_id']}", headers=roles["doctor"]).status_code == 403
    assert (
        client.post(f"/api/v1/queue/sessions/{other['session_id']}/call-next", headers=roles["doctor"]).status_code
        == 403
    )
    called = client.post(f"/api/v1/queue/sessions/{first['session_id']}/call-next", headers=roles["doctor"])
    assert called.status_code == 200 and called.json()["called"]["token"] == "W01"
    assert client.get("/api/v1/queue/doctor/today", headers=roles["patient"]).status_code == 403
    assert client.post("/api/v1/chat", json={"message": "hello"}, headers=roles["doctor"]).status_code == 403
    assert client.get("/api/v1/queue/doctor/today", headers=roles["staff"]).status_code == 403


def test_doctor_follows_only_their_own_queue_live(opd):
    client, pawar, joshi, roles = opd
    mine, theirs = walk_in(client, pawar.id, roles["staff"]), walk_in(client, joshi.id, roles["staff"], "Mina Rao")
    token = roles["doctor"]["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/queue/{mine['session_id']}?token={token}") as ws:
        assert ws.receive_json()["event"] == "queue.updated"
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(f"/ws/queue/{theirs['session_id']}?token={token}") as ws:
            ws.receive_json()
    assert denied.value.code == 4403


def test_priority_request_flow_over_http(opd):
    client, pawar, _, roles = opd
    entry = walk_in(client, pawar.id, roles["staff"])
    direct = client.patch(
        f"/api/v1/queue/entries/{entry['entry_id']}/priority", json={"priority": 2}, headers=roles["staff"]
    )
    assert direct.status_code == 403  # feature 52: the desk asks, the doctor decides
    asked = client.post(
        f"/api/v1/queue/entries/{entry['entry_id']}/priority-requests",
        json={"priority": 2, "reason": "fainted in the waiting area"},
        headers=roles["staff"],
    )
    assert asked.status_code == 201
    request_id = asked.json()["request_id"]
    detail = client.get(f"/api/v1/queue/sessions/{entry['session_id']}", headers=roles["staff"]).json()
    assert detail["entries"][0]["pending_request"]["request_id"] == request_id
    assert detail["priority_requests"][0]["reason"] == "fainted in the waiting area"
    assert (
        client.post(
            f"/api/v1/queue/priority-requests/{request_id}", json={"approve": True}, headers=roles["staff"]
        ).status_code
        == 403
    )
    approved = client.post(
        f"/api/v1/queue/priority-requests/{request_id}", json={"approve": True}, headers=roles["doctor"]
    )
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    detail = client.get(f"/api/v1/queue/sessions/{entry['session_id']}", headers=roles["doctor"]).json()
    assert detail["entries"][0]["priority"] == 2 and detail["entries"][0]["effective_priority"] == 2
    assert detail["priority_requests"] == []


def test_transfer_arrived_and_left_over_http(opd):
    client, pawar, joshi, roles = opd
    first = walk_in(client, pawar.id, roles["staff"])
    moved = client.post(
        f"/api/v1/queue/entries/{first['entry_id']}/transfer", json={"doctor_id": joshi.id}, headers=roles["staff"]
    )
    assert moved.status_code == 200 and moved.json()["token"] == "T01"
    gone = client.post(f"/api/v1/queue/entries/{moved.json()['entry_id']}/left", headers=roles["staff"])
    assert gone.status_code == 200 and gone.json()["status"] == "left"
    assert client.post(f"/api/v1/queue/entries/{first['entry_id']}/transfer", json={"doctor_id": joshi.id},
                       headers=roles["patient"]).status_code == 403  # fmt: skip


def test_virtual_queue_over_http(opd):
    client, pawar, _, roles = opd
    options = client.get("/api/v1/queue/virtual/options", headers=roles["patient"])
    assert options.status_code == 200
    gm = next(d for d in options.json()["departments"] if d["department"] == "General Medicine")
    assert any(d["doctor_id"] == pawar.id and d["can_join"] for d in gm["doctors"])
    assert client.get("/api/v1/queue/virtual/options", headers=roles["staff"]).status_code == 403
    me = client.get("/api/v1/me", headers=roles["patient"]).json()
    joined = client.post(
        "/api/v1/queue/virtual/join",
        json={"doctor_id": pawar.id, "patient_id": me["patient_id"]},
        headers=roles["patient"],
    )
    assert joined.status_code == 201 and joined.json()["token"] == "V01"
    mine = client.get("/api/v1/queue/mine", headers=roles["patient"]).json()["entries"]
    assert mine[0]["token"] == "V01" and mine[0]["joined_remotely"] is True
    arrived = client.post(f"/api/v1/queue/entries/{joined.json()['entry_id']}/arrived", headers=roles["staff"])
    assert arrived.status_code == 200 and arrived.json()["arrived_at"]
    left = client.post(f"/api/v1/queue/entries/{joined.json()['entry_id']}/left", headers=roles["patient"])
    assert left.status_code == 200 and left.json()["status"] == "left"


def test_coordination_and_priority_rules_over_http(opd):
    client, pawar, _, roles = opd
    for i in range(6):
        walk_in(client, pawar.id, roles["staff"], f"Patient {chr(65 + i)} Test")
    board = client.get(
        "/api/v1/queue/coordination", params={"department_id": pawar.department_id}, headers=roles["staff"]
    )
    assert board.status_code == 200
    (gm,) = board.json()["departments"]
    assert gm["suggestions"] and gm["suggestions"][0]["to_doctor"] == "Dr. Kavita Joshi"
    assert client.get("/api/v1/queue/coordination", headers=roles["admin"]).status_code == 200
    assert client.get("/api/v1/queue/coordination", headers=roles["patient"]).status_code == 403

    current = client.get("/api/v1/admin/priority-rules", headers=roles["admin"]).json()["rules"]
    assert {r["category"] for r in current} == {"senior", "child", "pregnant", "disability"}
    saved = client.put(
        "/api/v1/admin/priority-rules", json={"weights": {"senior": 1, "pregnant": 2}}, headers=roles["admin"]
    )
    assert saved.status_code == 200
    assert {r["category"]: r["weight"] for r in saved.json()["rules"]} == {
        "senior": 1,
        "child": 0,
        "pregnant": 2,
        "disability": 0,
    }
    bad = client.put("/api/v1/admin/priority-rules", json={"weights": {"senior": 5}}, headers=roles["admin"])
    assert bad.status_code == 400
    assert (
        client.put("/api/v1/admin/priority-rules", json={"weights": {"senior": 1}}, headers=roles["staff"]).status_code
        == 403
    )
    dashboard = client.get("/api/v1/admin/dashboard", headers=roles["admin"]).json()
    assert all("left_unseen_today" in d for d in dashboard["departments"])
