"""Queue engine against the database: FR-21 – FR-23, FR-27 (TC-12), US-11, US-12."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import Appointment, Notification, QueueEntry, QueueEvent, QueueSession, Slot
from app.queue import engine
from app.tools.booking import book_appointment, reschedule_appointment
from app.tools.errors import ToolError
from tests.conftest import NOW, TODAY


@pytest.fixture
def clinic(world):
    """Dr. Pawar (10-minute slots from 09:00) with three bookings today at 09:00, 09:30 and 10:00."""
    doctor = world.doctor("Dr. Suresh Pawar")
    slots = world.slots(doctor, TODAY)
    patients = world.other_patients(5)
    booked_at = NOW - timedelta(days=1)
    appts = [
        book_appointment(world.db, world.staff, patients[i], slots[k].id, confirmed=True, now=booked_at)
        for i, k in enumerate((0, 3, 6))
    ]
    return doctor, slots, patients, appts


def at_clock(hh: int, mm: int):
    return NOW.replace(hour=hh, minute=mm)


def test_us11_walk_in_gets_token_and_position(world, clinic):
    doctor, _, patients, appts = clinic
    staff = world.staff
    b1 = engine.check_in(world.db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    w1 = engine.register_walk_in(world.db, staff, doctor.id, patient_id=patients[3], now=at_clock(8, 52))
    assert b1["token"] == "B01" and w1["token"] == "W01"
    w2 = engine.register_walk_in(
        world.db,
        staff,
        doctor.id,
        name="Test Walkin",
        birth_year=1980,
        phone="+91 98765 43210",
        language="hi",
        now=at_clock(8, 55),
    )
    assert w2["token"] == "W02"
    session = world.db.get(QueueSession, b1["session_id"])
    positions = {e["token"]: e["position"] for e in engine.session_snapshot(world.db, session.id)["entries"]}
    # 09:00 B01 is due; then the walk-ins fill the gap before the 09:30 booking.
    assert positions == {"B01": 1, "W01": 2, "W02": 3}


def test_walk_in_phone_is_stored_masked(world, clinic):
    doctor = clinic[0]
    entry = engine.register_walk_in(
        world.db, world.staff, doctor.id, name="New Person", birth_year=1975, phone="9876543210", now=at_clock(9, 0)
    )
    patient = world.db.get(QueueEntry, entry["entry_id"]).patient
    assert patient.phone_masked == "+91 98XXXXXX10"


def test_check_in_rules(world, clinic):
    _, _, _, appts = clinic
    with pytest.raises(ToolError) as err:
        engine.check_in(world.db, world.staff, appts[0]["appointment_id"], now=NOW - timedelta(days=1))
    assert err.value.code == "VALIDATION_ERROR"
    engine.check_in(world.db, world.staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    with pytest.raises(ToolError) as err:
        engine.check_in(world.db, world.staff, appts[0]["appointment_id"], now=at_clock(8, 51))
    assert err.value.code == "ALREADY_CHECKED_IN"


def test_patient_can_check_in_self_but_not_others(world, clinic):
    doctor, slots, _, appts = clinic
    mine = book_appointment(world.db, world.asha, world.asha.patient_id, slots[9].id, confirmed=True, now=NOW)
    engine.check_in(world.db, world.asha, mine["appointment_id"], now=at_clock(9, 20))
    with pytest.raises(ToolError) as err:
        engine.check_in(world.db, world.asha, appts[0]["appointment_id"], now=at_clock(9, 20))
    assert err.value.code == "FORBIDDEN"


def test_full_consultation_flow_and_session_close(world, clinic):
    doctor, _, patients, appts = clinic
    staff, db = world.staff, world.db
    b1 = engine.check_in(db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    engine.check_in(db, staff, appts[1]["appointment_id"], now=at_clock(9, 20))
    session_id = b1["session_id"]

    called = engine.call_next(db, staff, session_id, now=at_clock(9, 0))
    assert called["token"] == "B01" and called["status"] == "called"
    with pytest.raises(ToolError):
        engine.call_next(db, staff, session_id, now=at_clock(9, 1))  # finish the current patient first
    engine.start_consultation(db, staff, called["entry_id"], now=at_clock(9, 1))
    done = engine.end_consultation(db, staff, called["entry_id"], now=at_clock(9, 9))
    assert done["status"] == "done"
    assert db.get(Appointment, appts[0]["appointment_id"]).status == "completed"

    second = engine.call_next(db, staff, session_id, now=at_clock(9, 30))
    engine.start_consultation(db, staff, second["entry_id"], now=at_clock(9, 31))
    engine.end_consultation(db, staff, second["entry_id"], now=at_clock(9, 40))
    assert engine.call_next(db, staff, session_id, now=at_clock(9, 41)) is None

    closed = engine.close_session(db, staff, session_id, now=at_clock(14, 0))
    assert closed["no_shows"] == 1  # the 10:00 patient never arrived
    assert db.get(Appointment, appts[2]["appointment_id"]).status == "no_show"


def test_missed_turn_and_return(world, clinic):
    doctor, _, patients, appts = clinic
    staff, db = world.staff, world.db
    b1 = engine.check_in(db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    w1 = engine.register_walk_in(db, staff, doctor.id, patient_id=patients[3], now=at_clock(8, 55))
    sid = b1["session_id"]
    engine.call_next(db, staff, sid, now=at_clock(9, 0))
    engine.mark_missed_turn(db, staff, b1["entry_id"], now=at_clock(9, 2))
    assert db.get(QueueEntry, b1["entry_id"]).position is None
    nxt = engine.call_next(db, staff, sid, now=at_clock(9, 2))
    assert nxt["entry_id"] == w1["entry_id"]
    engine.start_consultation(db, staff, nxt["entry_id"], now=at_clock(9, 3))
    back = engine.mark_returned(db, staff, b1["entry_id"], now=at_clock(9, 5))
    assert back["status"] == "waiting" and back["position"] == 1


def test_tc10_break_keeps_positions_and_blocks_calls(world, clinic):
    doctor, _, patients, appts = clinic
    staff, db = world.staff, world.db
    b1 = engine.check_in(db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    engine.register_walk_in(db, staff, doctor.id, patient_id=patients[3], now=at_clock(8, 55))
    sid = b1["session_id"]
    before = {e["token"]: e["position"] for e in engine.session_snapshot(db, sid)["entries"]}
    result = engine.record_doctor_event(db, staff, sid, "break", minutes=15, reason="tea", now=at_clock(9, 0))
    assert result["doctor_status"] == "on_break"
    after = {e["token"]: e["position"] for e in engine.session_snapshot(db, sid)["entries"]}
    assert before == after
    with pytest.raises(ToolError) as err:
        engine.call_next(db, staff, sid, now=at_clock(9, 10))
    assert err.value.code == "INVALID_STATE"
    called = engine.call_next(db, staff, sid, now=at_clock(9, 15))
    assert called["token"] == "B01"
    assert db.get(QueueSession, sid).doctor_status == "available"
    types = [e.type for e in db.scalars(select(QueueEvent).where(QueueEvent.session_id == sid).order_by(QueueEvent.id))]
    assert types[-3:] == ["break", "resume", "call"]


def test_event_validation(world, clinic):
    doctor = clinic[0]
    session = engine.get_or_create_session(world.db, doctor.id, TODAY)
    with pytest.raises(ToolError):
        engine.record_doctor_event(world.db, world.staff, session.id, "break", now=NOW)  # minutes missing
    with pytest.raises(ToolError):
        engine.record_doctor_event(world.db, world.staff, session.id, "party", minutes=5, now=NOW)


def test_walk_in_on_non_opd_day_is_rejected(world):
    doctor = world.doctor("Dr. Anand Kulkarni")  # not on Tuesdays
    with pytest.raises(ToolError) as err:
        engine.register_walk_in(
            world.db, world.staff, doctor.id, patient_id=world.other_patients(1)[0], now=NOW + timedelta(days=1)
        )
    assert err.value.code == "VALIDATION_ERROR"


def test_tc12_doctor_unavailable_closes_entries_and_notifies(world, clinic):
    doctor, slots, patients, appts = clinic
    staff, db = world.staff, world.db
    b1 = engine.check_in(db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    w1 = engine.register_walk_in(db, staff, doctor.id, patient_id=patients[3], now=at_clock(8, 55))
    sid = b1["session_id"]

    result = engine.record_doctor_event(db, staff, sid, "unavailable", reason="called away", now=at_clock(9, 5))
    db.commit()
    affected = {a["patient_id"] for a in result["affected"]}
    # Checked-in booked patient, walk-in, and the two booked patients who had not arrived yet.
    assert affected == {patients[0], patients[1], patients[2], patients[3]}
    assert db.get(QueueEntry, b1["entry_id"]).status == "closed"
    assert db.get(QueueEntry, w1["entry_id"]).status == "closed"
    for appt in appts:
        assert db.get(Appointment, appt["appointment_id"]).status == "displaced"
    notified = set(db.scalars(select(Notification.patient_id)))
    assert notified == affected
    statuses = db.scalars(select(Slot.status).where(Slot.id.in_([s.id for s in slots]))).all()
    assert set(statuses) == {"blocked"}
    session = db.get(QueueSession, sid)
    assert session.status == "closed" and session.doctor_status == "unavailable"
    with pytest.raises(ToolError):
        engine.register_walk_in(db, staff, doctor.id, patient_id=patients[4], now=at_clock(9, 10))


def test_displaced_patient_can_reschedule_inside_cutoff(world, clinic):
    doctor, _, patients, appts = clinic
    staff, db = world.staff, world.db
    engine.check_in(db, staff, appts[0]["appointment_id"], now=at_clock(8, 50))
    session = db.scalars(select(QueueSession)).one()
    engine.record_doctor_event(db, staff, session.id, "unavailable", now=at_clock(9, 5))
    # Same department, a colleague's slot later today: allowed although within 12 hours.
    colleague = world.doctor("Dr. Kavita Joshi")
    target = world.slots(colleague, TODAY)[-1]
    moved = reschedule_appointment(
        db, staff, appts[2]["appointment_id"], target.id, confirmed=True, now=at_clock(9, 10)
    )
    assert moved["doctor_id"] == colleague.id and moved["status"] == "rescheduled"
