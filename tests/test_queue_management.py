"""Phase 6C queue management against the database: virtual queue (38), reassignment and transfers (42, 43,
53), coordination and balancing (44, 54), left without being seen (47), emergency interruption (49),
configurable priority rules (51) and clinician-authorized priority (52)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.analytics.utilization import utilization
from app.db.models import Appointment, Notification, Patient, PriorityRequest, QueueEntry, QueueEvent, QueueSession
from app.queue import engine, rules
from app.queue.coordination import department_board, virtual_queue_options
from app.tools import policy
from app.tools.booking import book_appointment
from app.tools.errors import ToolError
from app.tools.permissions import Actor
from tests.conftest import NOW, TODAY


def at_clock(hh: int, mm: int):
    return NOW.replace(hour=hh, minute=mm)


@pytest.fixture
def opd(world):
    """Monday: Dr. Pawar and Dr. Joshi (General Medicine, 10-minute slots) and Dr. Kulkarni (Cardiology)."""
    pawar, joshi = world.doctor("Dr. Suresh Pawar"), world.doctor("Dr. Kavita Joshi")
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    for d in (pawar, joshi, kulkarni):
        world.slots(d, TODAY)
    return pawar, joshi, kulkarni, world.other_patients(12)


def walk_ins(world, doctor, patients, start=(8, 40)):
    return [
        engine.register_walk_in(
            world.db, world.staff, doctor.id, patient_id=p, now=at_clock(*start) + timedelta(minutes=i)
        )
        for i, p in enumerate(patients)
    ]


def tokens_in_order(db, session_id: int) -> list[str]:
    entries = db.scalars(
        select(QueueEntry).where(QueueEntry.session_id == session_id, QueueEntry.status == "waiting")
    ).all()
    return [e.token for e in sorted(entries, key=lambda e: e.position)]


# --------------------------------------------------------------------------- feature 52


def test_desk_asks_and_the_doctor_authorizes_a_priority_change(world, opd):
    pawar, _, _, patients = opd
    db, staff, doctor = world.db, world.staff, world.doctor_account("Dr. Suresh Pawar")
    w = walk_ins(world, pawar, patients[:3])
    sid = w[0]["session_id"]
    asked = engine.request_priority(
        db, staff, w[2]["entry_id"], 2, "  chest   pain while waiting ", now=at_clock(8, 50)
    )
    assert asked["status"] == "pending" and asked["reason"] == "chest pain while waiting"
    assert tokens_in_order(db, sid) == ["W01", "W02", "W03"]  # nothing changes until the doctor decides
    assert [r["request_id"] for r in engine.pending_priority_requests(db, sid)] == [asked["request_id"]]
    with pytest.raises(ToolError) as dup:
        engine.request_priority(db, staff, w[2]["entry_id"], 3, "worse now", now=at_clock(8, 51))
    assert dup.value.code == "DUPLICATE"

    for actor in (staff, world.doctor_account("Dr. Kavita Joshi")):
        with pytest.raises(ToolError) as err:
            engine.decide_priority_request(db, actor, asked["request_id"], True, now=at_clock(8, 52))
        assert err.value.code == "FORBIDDEN"

    decided = engine.decide_priority_request(db, doctor, asked["request_id"], True, now=at_clock(8, 53))
    assert decided["status"] == "approved"
    assert tokens_in_order(db, sid) == ["W03", "W01", "W02"]
    assert engine.pending_priority_requests(db, sid) == []
    with pytest.raises(ToolError) as again:
        engine.decide_priority_request(db, doctor, asked["request_id"], False, now=at_clock(8, 54))
    assert again.value.code == "INVALID_STATE"


def test_declined_request_changes_nothing_and_requests_are_validated(world, opd):
    pawar, _, _, patients = opd
    db, staff = world.db, world.staff
    w = walk_ins(world, pawar, patients[:2])
    with pytest.raises(ToolError) as short:
        engine.request_priority(db, staff, w[1]["entry_id"], 2, "x", now=at_clock(8, 50))
    assert short.value.code == "VALIDATION_ERROR"
    with pytest.raises(ToolError) as same:
        engine.request_priority(db, staff, w[1]["entry_id"], 0, "already zero", now=at_clock(8, 50))
    assert same.value.code == "VALIDATION_ERROR"
    with pytest.raises(ToolError) as patient:
        engine.request_priority(db, world.asha, w[1]["entry_id"], 2, "let me in", now=at_clock(8, 50))
    assert patient.value.code == "FORBIDDEN"
    asked = engine.request_priority(db, staff, w[1]["entry_id"], 2, "elderly, unwell", now=at_clock(8, 50))
    engine.decide_priority_request(db, world.doctor_account("Dr. Suresh Pawar"), asked["request_id"], False,
                                   now=at_clock(8, 51))  # fmt: skip
    assert db.get(QueueEntry, w[1]["entry_id"]).priority == 0
    assert db.get(PriorityRequest, asked["request_id"]).status == "declined"


# --------------------------------------------------------------------------- features 42, 43, 53


def test_reassigning_a_booked_patient_keeps_check_in_time_and_appointment(world, opd):
    pawar, joshi, _, patients = opd
    db, staff = world.db, world.staff
    slots = world.slots(pawar, TODAY)
    appt = book_appointment(db, staff, patients[0], slots[0].id, confirmed=True, now=NOW - timedelta(days=1))
    b1 = engine.check_in(db, staff, appt["appointment_id"], now=at_clock(8, 45))
    joshi_walk = engine.register_walk_in(db, staff, joshi.id, patient_id=patients[1], now=at_clock(8, 50))

    moved = engine.transfer_entry(db, staff, b1["entry_id"], joshi.id, reason="balance", now=at_clock(8, 55))
    assert moved["token"] == "T01" and moved["same_department"] is True
    assert moved["checked_in_at"] == b1["checked_in_at"] and moved["appointment_id"] == appt["appointment_id"]
    assert db.get(QueueEntry, b1["entry_id"]).status == "transferred"
    # Checked in at 08:45, before Joshi's 08:50 walk-in, so the moved patient is called first.
    assert tokens_in_order(db, joshi_walk["session_id"]) == ["T01", "W01"]
    note = db.scalars(select(Notification).where(Notification.kind == "transfer")).one()
    assert note.patient_id == patients[0] and "T01" in note.message
    types = set(db.scalars(select(QueueEvent.type)))
    assert {"transfer_out", "transfer_in"} <= types

    joshi_doc = world.doctor_account("Dr. Kavita Joshi")
    called = engine.call_next(db, joshi_doc, moved["session_id"], now=at_clock(9, 0))
    engine.start_consultation(db, joshi_doc, called["entry_id"], now=at_clock(9, 1))
    engine.end_consultation(db, joshi_doc, called["entry_id"], now=at_clock(9, 9))
    assert db.get(Appointment, appt["appointment_id"]).status == "completed"


def test_doctor_forwards_their_patient_to_another_department(world, opd):
    pawar, _, kulkarni, patients = opd
    db, staff, doctor = world.db, world.staff, world.doctor_account("Dr. Suresh Pawar")
    w = walk_ins(world, pawar, patients[:2])
    called = engine.call_next(db, doctor, w[0]["session_id"], now=at_clock(9, 0))
    engine.start_consultation(db, doctor, called["entry_id"], now=at_clock(9, 1))
    with pytest.raises(ToolError) as desk:  # the desk does not take a patient out of the consulting room
        engine.transfer_entry(db, staff, called["entry_id"], kulkarni.id, now=at_clock(9, 5))
    assert desk.value.code == "INVALID_STATE"
    with pytest.raises(ToolError) as other:
        engine.transfer_entry(db, world.doctor_account("Dr. Kavita Joshi"), called["entry_id"], kulkarni.id,
                              now=at_clock(9, 5))  # fmt: skip
    assert other.value.code == "FORBIDDEN"
    forwarded = engine.transfer_entry(db, doctor, called["entry_id"], kulkarni.id, reason="ECG changes",
                                      now=at_clock(9, 8))  # fmt: skip
    assert forwarded["same_department"] is False and forwarded["to_doctor"] == "Dr. Anand Kulkarni"
    old = db.get(QueueEntry, called["entry_id"])
    assert old.status == "transferred" and old.consult_end == at_clock(9, 8)
    # Pawar's room is free again: the next patient can be called.
    assert engine.call_next(db, doctor, w[0]["session_id"], now=at_clock(9, 9))["token"] == "W02"


def test_moves_are_refused_when_they_make_no_sense(world, opd):
    pawar, joshi, _, patients = opd
    db, staff = world.db, world.staff
    w = walk_ins(world, pawar, patients[:1])
    with pytest.raises(ToolError) as same:
        engine.transfer_entry(db, staff, w[0]["entry_id"], pawar.id, now=at_clock(8, 50))
    assert same.value.code == "VALIDATION_ERROR"
    shaikh = world.doctor("Dr. Imran Shaikh")  # no OPD on Mondays
    with pytest.raises(ToolError) as no_opd:
        engine.transfer_entry(db, staff, w[0]["entry_id"], shaikh.id, now=at_clock(8, 50))
    assert no_opd.value.code == "VALIDATION_ERROR"
    engine.register_walk_in(db, staff, joshi.id, patient_id=patients[5], now=at_clock(8, 51))
    with pytest.raises(ToolError) as patient:
        engine.transfer_entry(db, world.asha, w[0]["entry_id"], joshi.id, now=at_clock(8, 52))
    assert patient.value.code == "FORBIDDEN"


def test_unavailable_doctor_can_hand_waiting_patients_to_colleagues(world, opd):
    pawar, joshi, _, patients = opd
    db, staff = world.db, world.staff
    slots = world.slots(pawar, TODAY)
    appts = [
        book_appointment(db, staff, patients[i], slots[k].id, confirmed=True, now=NOW - timedelta(days=1))
        for i, k in ((0, 0), (1, 12))
    ]
    b1 = engine.check_in(db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    w = walk_ins(world, pawar, patients[2:4], start=(8, 52))
    with pytest.raises(ToolError) as doctor_says:
        engine.record_doctor_event(db, world.doctor_account("Dr. Suresh Pawar"), b1["session_id"], "unavailable",
                                   now=at_clock(9, 5))  # fmt: skip
    assert doctor_says.value.code == "FORBIDDEN"

    result = engine.record_doctor_event(
        db, staff, b1["session_id"], "unavailable", reason="called away", reassign=True, now=at_clock(9, 5)
    )
    assert sorted(m["token"] for m in result["moved"]) == ["T01", "T02", "T03"]
    joshi_session = db.scalars(select(QueueSession).where(QueueSession.doctor_id == joshi.id)).one()
    assert {m["session_id"] for m in result["moved"]} == {joshi_session.id}
    # The checked-in booking carries on with Dr. Joshi; the 11:00 booking (not arrived) is displaced.
    assert db.get(Appointment, appts[0]["appointment_id"]).status == "booked"
    assert db.get(Appointment, appts[1]["appointment_id"]).status == "displaced"
    assert {a["patient_id"] for a in result["affected"]} == {patients[1]}
    assert db.get(QueueEntry, w[0]["entry_id"]).status == "transferred"


# --------------------------------------------------------------------------- feature 38


def test_patient_joins_the_queue_online_and_is_marked_arrived(world, opd):
    pawar, joshi, _, patients = opd
    db, staff, asha = world.db, world.staff, world.asha
    options = virtual_queue_options(db, at_clock(8, 0))
    gm = next(d for d in options["departments"] if d["department"] == "General Medicine")
    assert gm["opens"] == "08:00" and gm["closes"] == "13:30" and gm["window_open"]
    assert {d["doctor_name"] for d in gm["doctors"] if d["can_join"]} == {"Dr. Suresh Pawar", "Dr. Kavita Joshi"}

    joined = engine.join_virtual_queue(db, asha, pawar.id, asha.patient_id, now=at_clock(8, 5))
    assert joined["token"] == "V01" and joined["joined_remotely"] and joined["arrived_at"] is None
    with pytest.raises(ToolError) as twice:
        engine.join_virtual_queue(db, asha, joshi.id, asha.patient_id, now=at_clock(8, 6))
    assert twice.value.code == "ALREADY_CHECKED_IN"
    arrived = engine.mark_arrived(db, staff, joined["entry_id"], now=at_clock(8, 40))
    assert arrived["arrived_at"] is not None
    with pytest.raises(ToolError):
        engine.mark_arrived(db, staff, joined["entry_id"], now=at_clock(8, 41))


def test_virtual_queue_rules(world, opd, monkeypatch):
    pawar, _, _, patients = opd
    db, asha = world.db, world.asha
    with pytest.raises(ToolError) as early:
        engine.join_virtual_queue(db, asha, pawar.id, asha.patient_id, now=at_clock(7, 59))
    assert early.value.code == "POLICY_WINDOW"
    with pytest.raises(ToolError) as late:
        engine.join_virtual_queue(db, asha, pawar.id, asha.patient_id, now=at_clock(13, 31))
    assert late.value.code == "POLICY_WINDOW"
    with pytest.raises(ToolError) as other:
        engine.join_virtual_queue(db, asha, pawar.id, patients[0], now=at_clock(8, 30))
    assert other.value.code == "FORBIDDEN"
    with pytest.raises(ToolError) as staff:
        engine.join_virtual_queue(db, world.staff, pawar.id, asha.patient_id, now=at_clock(8, 30))
    assert staff.value.code == "FORBIDDEN"

    # A linked caregiver joins for the patient they look after.
    vinayak = world.patient("Vinayak Deshmukh").id
    rajan = world.user("rajan")
    assert engine.join_virtual_queue(db, rajan, pawar.id, vinayak, now=at_clock(8, 30))["token"] == "V01"

    monkeypatch.setattr(policy, "VIRTUAL_QUEUE_CAP", 1)
    with pytest.raises(ToolError) as full:
        engine.join_virtual_queue(db, asha, pawar.id, asha.patient_id, now=at_clock(8, 31))
    assert full.value.code == "QUEUE_FULL" and full.value.http_status == 409

    slots = world.slots(pawar, TODAY)
    book_appointment(db, asha, asha.patient_id, slots[20].id, confirmed=True, now=NOW - timedelta(days=1))
    monkeypatch.setattr(policy, "VIRTUAL_QUEUE_CAP", 10)
    with pytest.raises(ToolError) as booked:
        engine.join_virtual_queue(db, asha, pawar.id, asha.patient_id, now=at_clock(8, 32))
    assert booked.value.code == "INVALID_STATE" and "check in" in booked.value.message


# --------------------------------------------------------------------------- feature 47


def test_left_without_being_seen_is_counted_apart_from_no_shows(world, opd):
    pawar, _, _, patients = opd
    db, staff, asha = world.db, world.staff, world.asha
    doctor = world.doctor_account("Dr. Suresh Pawar")
    slots = world.slots(pawar, TODAY)
    appts = [
        book_appointment(db, staff, patients[i], slots[k].id, confirmed=True, now=NOW - timedelta(days=1))
        for i, k in ((0, 0), (1, 1), (2, 2))
    ]
    b1 = engine.check_in(db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    engine.check_in(db, staff, appts[1]["appointment_id"], now=at_clock(8, 55))
    mine = engine.join_virtual_queue(db, asha, pawar.id, asha.patient_id, now=at_clock(8, 56))
    sid = b1["session_id"]

    left = engine.mark_left(db, asha, mine["entry_id"], now=at_clock(9, 0))  # the patient leaves the queue
    assert left["status"] == "left"
    with pytest.raises(ToolError) as not_hers:
        engine.mark_left(db, asha, b1["entry_id"], now=at_clock(9, 0))
    assert not_hers.value.code == "FORBIDDEN"

    first = engine.call_next(db, doctor, sid, now=at_clock(9, 0))
    engine.mark_missed_turn(db, doctor, first["entry_id"], now=at_clock(9, 3))  # B01 never comes back
    second = engine.call_next(db, doctor, sid, now=at_clock(9, 4))
    engine.start_consultation(db, doctor, second["entry_id"], now=at_clock(9, 5))
    engine.end_consultation(db, doctor, second["entry_id"], now=at_clock(9, 12))

    closed = engine.close_session(db, staff, sid, now=at_clock(14, 0))
    assert closed["no_shows"] == 1 and closed["left_unseen"] == 1  # the 09:20 patient never arrived
    assert db.get(Appointment, appts[0]["appointment_id"]).status == "left"
    assert db.get(Appointment, appts[2]["appointment_id"]).status == "no_show"
    assert db.get(QueueEntry, first["entry_id"]).status == "left"

    stats = utilization(db, NOW + timedelta(days=1))
    row = next(r for r in stats["doctors"] if r["doctor_name"] == "Dr. Suresh Pawar")
    assert (row["attended"], row["no_shows"], row["left_unseen"]) == (1, 1, 1)
    assert row["attendance_rate"] == round(1 / 3, 3)
    assert stats["overall"]["abandonment_rate"] == round(2 / 3, 3)  # Asha and B01 of three arrivals


# --------------------------------------------------------------------------- feature 49


def test_emergency_interruption_keeps_places_and_tells_everyone_waiting(world, opd):
    pawar, joshi, _, patients = opd
    db = world.db
    doctor = world.doctor_account("Dr. Suresh Pawar")
    w = walk_ins(world, pawar, patients[:3])
    sid = w[0]["session_id"]
    before = tokens_in_order(db, sid)
    with pytest.raises(ToolError) as other:
        engine.record_doctor_event(db, world.doctor_account("Dr. Kavita Joshi"), sid, "emergency", minutes=20,
                                   now=at_clock(9, 0))  # fmt: skip
    assert other.value.code == "FORBIDDEN"
    engine.record_doctor_event(db, doctor, sid, "emergency", minutes=20, reason="cardiac arrest", now=at_clock(9, 0))
    assert tokens_in_order(db, sid) == before
    notes = db.scalars(select(Notification).where(Notification.kind == "delay")).all()
    assert {n.patient_id for n in notes} == set(patients[:3])
    assert all("emergency" in n.message and "20 minutes" in n.message for n in notes)
    with pytest.raises(ToolError) as busy:
        engine.call_next(db, doctor, sid, now=at_clock(9, 10))
    assert busy.value.code == "INVALID_STATE"
    engine.record_doctor_event(db, doctor, sid, "resume", now=at_clock(9, 15))
    assert engine.call_next(db, doctor, sid, now=at_clock(9, 16))["token"] == "W01"


# --------------------------------------------------------------------------- feature 51


def test_admin_priority_rules_reorder_open_queues(world, opd):
    pawar, _, _, patients = opd
    db, staff = world.db, world.staff
    admin = world.user("mehta")
    w = walk_ins(world, pawar, patients[:3])
    db.get(Patient, patients[2]).pregnant = True
    sid = w[0]["session_id"]
    assert tokens_in_order(db, sid) == ["W01", "W02", "W03"]
    with pytest.raises(ToolError) as desk:
        rules.set_priority_rules(db, staff, {"pregnant": 2}, now=at_clock(8, 50))
    assert desk.value.code == "FORBIDDEN"
    with pytest.raises(ToolError) as unknown:
        rules.set_priority_rules(db, admin, {"vip": 3}, now=at_clock(8, 50))
    assert unknown.value.code == "VALIDATION_ERROR"
    result = rules.set_priority_rules(db, admin, {"pregnant": 2, "senior": 1}, now=at_clock(8, 50))
    assert sid in result["reordered_sessions"]
    assert {r["category"]: r["weight"] for r in result["rules"]}["pregnant"] == 2
    assert tokens_in_order(db, sid) == ["W03", "W01", "W02"]
    assert db.get(QueueEntry, w[2]["entry_id"]).priority == 0  # the manual priority is untouched


def test_category_priority_waits_for_a_booked_patients_slot(world, opd):
    pawar, _, _, patients = opd
    db, staff = world.db, world.staff
    slots = world.slots(pawar, TODAY)
    late_slot = book_appointment(db, staff, patients[0], slots[12].id, confirmed=True, now=NOW - timedelta(days=1))
    db.get(Patient, patients[0]).pregnant = True
    rules.set_priority_rules(db, world.user("mehta"), {"pregnant": 2}, now=at_clock(8, 0))
    w = walk_ins(world, pawar, patients[1:3], start=(8, 30))
    b = engine.check_in(db, staff, late_slot["appointment_id"], now=at_clock(8, 45))
    # Her 11:00 slot is not due at 08:45, so she does not jump ahead of the walk-ins yet.
    assert tokens_in_order(db, w[0]["session_id"]) == ["W01", "W02", "B01"]
    engine.reorder_session(db, b["session_id"], at_clock(11, 0))
    assert tokens_in_order(db, w[0]["session_id"])[0] == "B01"


# --------------------------------------------------------------------------- features 44, 54


def test_coordination_board_and_balancing_suggestion(world, opd):
    pawar, joshi, _, patients = opd
    db = world.db
    walk_ins(world, pawar, patients[:6], start=(8, 30))
    board = department_board(db, at_clock(9, 0), pawar.department_id)
    (gm,) = board["departments"]
    rows = {r["doctor_name"]: r for r in gm["doctors"]}
    assert rows["Dr. Suresh Pawar"]["waiting"] == 6 and rows["Dr. Kavita Joshi"]["state"] == "not_started"
    assert rows["Dr. Suresh Pawar"]["predicted_finish"] > rows["Dr. Kavita Joshi"]["predicted_finish"]
    suggestions = gm["suggestions"]
    assert suggestions and all(s["from_doctor"] == "Dr. Suresh Pawar" for s in suggestions)
    assert suggestions[0]["token"] == "W06" and suggestions[0]["to_doctor"] == "Dr. Kavita Joshi"
    first = suggestions[0]
    engine.transfer_entry(db, world.staff, first["entry_id"], first["to_doctor_id"], now=at_clock(9, 0))
    after = department_board(db, at_clock(9, 0), pawar.department_id)["departments"][0]
    assert {r["doctor_name"]: r["waiting"] for r in after["doctors"]} == {
        "Dr. Kavita Joshi": 1,
        "Dr. Suresh Pawar": 5,
    }


def test_doctor_actor_carries_their_doctor(world):
    actor = world.doctor_account("Dr. Suresh Pawar")
    assert isinstance(actor, Actor) and actor.role == "doctor"
    assert actor.doctor_id == world.doctor("Dr. Suresh Pawar").id
