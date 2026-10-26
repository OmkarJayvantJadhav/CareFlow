"""Roles enforced in code (NFR-07): TC-08, TC-13, US-10 and the permission table in docs §11."""

import pytest
from sqlalchemy import func, select

from app.db.models import Appointment, AuditLog, QueueEntry
from app.queue import engine
from app.tools.booking import book_appointment, cancel_appointment, get_patient_appointments
from app.tools.errors import ToolError
from tests.conftest import NOW, SATURDAY, TODAY


def test_us10_verified_caregiver_books_for_linked_patient(world):
    rajan = world.user("rajan")
    father = world.patient("Vinayak Deshmukh")
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    appt = book_appointment(world.db, rajan, father.id, slot.id, confirmed=True, now=NOW)
    assert appt["patient_id"] == father.id and appt["patient_name"] == "Vinayak Deshmukh"
    history = get_patient_appointments(world.db, rajan, father.id, now=NOW)
    assert len(history["upcoming"]) == 1


def test_tc08_unlinked_caregiver_cannot_view_or_change(world):
    sunil = world.user("sunil")  # link exists but was never verified
    father = world.patient("Vinayak Deshmukh")
    with pytest.raises(ToolError) as err:
        get_patient_appointments(world.db, sunil, father.id, now=NOW)
    assert err.value.code == "FORBIDDEN" and err.value.http_status == 403
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    with pytest.raises(ToolError):
        book_appointment(world.db, sunil, father.id, slot.id, confirmed=True, now=NOW)
    assert world.db.scalar(select(func.count()).select_from(Appointment)) == 0


def test_caregiver_cannot_reach_other_patients(world):
    rajan = world.user("rajan")
    stranger = world.other_patients(1)[0]
    with pytest.raises(ToolError) as err:
        get_patient_appointments(world.db, rajan, stranger, now=NOW)
    assert err.value.code == "FORBIDDEN"


def test_patient_cannot_book_or_cancel_for_someone_else(world):
    other = world.other_patients(1)[0]
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    with pytest.raises(ToolError):
        book_appointment(world.db, world.asha, other, slot.id, confirmed=True, now=NOW)
    theirs = book_appointment(world.db, world.staff, other, slot.id, confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        cancel_appointment(world.db, world.asha, theirs["appointment_id"], confirmed=True, now=NOW)
    assert err.value.code == "FORBIDDEN"
    assert world.db.get(Appointment, theirs["appointment_id"]).status == "booked"


def test_admin_cannot_book(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    with pytest.raises(ToolError) as err:
        book_appointment(world.db, world.user("mehta"), world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    assert err.value.code == "FORBIDDEN"


def _waiting_entry(world):
    doctor = world.doctor("Dr. Suresh Pawar")
    world.slots(doctor, TODAY)
    return engine.register_walk_in(world.db, world.staff, doctor.id, patient_id=world.other_patients(1)[0], now=NOW)


def test_tc13_patient_cannot_change_priority(world):
    entry = _waiting_entry(world)
    with pytest.raises(ToolError) as err:
        engine.set_priority(world.db, world.asha, entry["entry_id"], 3, now=NOW)
    assert err.value.code == "FORBIDDEN" and err.value.http_status == 403
    world.db.commit()
    assert world.db.get(QueueEntry, entry["entry_id"]).priority == 0
    refused = world.db.scalars(select(AuditLog).where(AuditLog.tool == "set_priority")).one()
    assert refused.result == {"ok": False, "error": "FORBIDDEN"} and refused.role == "patient"


def test_doctor_priority_change_is_audited(world):
    entry = _waiting_entry(world)
    engine.set_priority(world.db, world.doctor_account("Dr. Suresh Pawar"), entry["entry_id"], 2, now=NOW)
    world.db.commit()
    assert world.db.get(QueueEntry, entry["entry_id"]).priority == 2
    row = world.db.scalars(select(AuditLog).where(AuditLog.tool == "set_priority")).one()
    assert row.result["ok"] is True and row.arguments["priority"] == 2 and row.role == "doctor"


@pytest.mark.parametrize("who", ["staff", "other doctor"])
def test_priority_is_clinician_authorized(world, who):
    """Feature 52: neither the front desk nor another doctor sets a patient's priority directly."""
    entry = _waiting_entry(world)
    actor = world.staff if who == "staff" else world.doctor_account("Dr. Kavita Joshi")
    with pytest.raises(ToolError) as err:
        engine.set_priority(world.db, actor, entry["entry_id"], 2, now=NOW)
    assert err.value.code == "FORBIDDEN"


@pytest.mark.parametrize("username", ["asha", "rajan", "mehta"])
def test_only_staff_register_walk_ins(world, username):
    doctor = world.doctor("Dr. Suresh Pawar")
    with pytest.raises(ToolError) as err:
        engine.register_walk_in(
            world.db, world.user(username), doctor.id, patient_id=world.other_patients(1)[0], now=NOW
        )
    assert err.value.code == "FORBIDDEN"


@pytest.mark.parametrize("username", ["asha", "mehta"])
def test_only_staff_record_doctor_events(world, username):
    doctor = world.doctor("Dr. Suresh Pawar")
    session = engine.get_or_create_session(world.db, doctor.id, TODAY)
    with pytest.raises(ToolError) as err:
        engine.record_doctor_event(world.db, world.user(username), session.id, "unavailable", now=NOW)
    assert err.value.code == "FORBIDDEN"
    assert session.doctor_status == "available"
