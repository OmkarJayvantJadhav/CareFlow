"""Booking rules: TC-01, TC-02, TC-04, TC-05, TC-06 and US-01 – US-04, FR-07, FR-08, FR-16."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import Appointment, AuditLog, Slot
from app.tools.booking import (
    book_appointment,
    cancel_appointment,
    check_availability,
    get_patient_appointments,
    reschedule_appointment,
    search_doctors,
)
from app.tools.errors import ToolError
from tests.conftest import NOW, SATURDAY, TODAY


def appointment_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Appointment))


def test_search_marathi_cardiologist_on_saturday(world):
    result = search_doctors(world.db, specialty="cardiologist", language="Marathi", day="saturday", now=NOW)
    assert [d["name"] for d in result["doctors"]] == ["Dr. Anand Kulkarni"]
    assert result["criteria"] == {"department": "Cardiology", "language": "mr", "date": SATURDAY.isoformat()}


def test_search_language_filter_lists_only_matching_doctors(world):
    result = search_doctors(world.db, specialty="ENT", language="मराठी", now=NOW)
    assert result["doctors"] and all("mr" in d["languages"] for d in result["doctors"])


def test_search_rejects_unknown_specialty(world):
    with pytest.raises(ToolError) as err:
        search_doctors(world.db, specialty="astrology", now=NOW)
    assert err.value.code == "VALIDATION_ERROR"


def test_availability_lists_only_free_future_slots(world):
    doctor = world.doctor("Dr. Suresh Pawar")
    slots = world.slots(doctor, TODAY)
    late_now = slots[3].start_at - timedelta(minutes=5)
    book_appointment(world.db, world.asha, world.asha.patient_id, slots[5].id, confirmed=True, now=NOW)
    free = check_availability(world.db, doctor.id, TODAY, now=late_now)["slots"]
    ids = [s["slot_id"] for s in free]
    assert slots[3].id not in ids and slots[5].id not in ids
    assert slots[4].id in ids


def test_availability_on_non_opd_day(world):
    doctor = world.doctor("Dr. Anand Kulkarni")  # Mon, Wed, Sat
    result = check_availability(world.db, doctor.id, "2026-10-20", now=NOW)
    assert result["works_that_day"] is False and result["slots"] == []


def test_tc01_booking_without_confirmation_creates_nothing(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    with pytest.raises(ToolError) as err:
        book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, now=NOW)
    assert err.value.code == "CONFIRMATION_REQUIRED"
    world.db.commit()
    assert appointment_count(world.db) == 0
    assert world.db.get(Slot, slot.id).status == "free"


def test_us01_confirmed_booking_creates_exactly_one_appointment(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[2]
    result = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    assert appointment_count(world.db) == 1
    assert result["doctor_name"] == "Dr. Anand Kulkarni"
    assert result["date"] == SATURDAY.isoformat() and result["time"] == "09:30"
    assert result["source"] == "agent" and "cancellation_policy" in result
    assert world.db.get(Slot, slot.id).status == "booked"


def test_tc02_booking_a_taken_slot_offers_alternatives(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    other = world.other_patients(1)[0]
    book_appointment(world.db, world.staff, other, slot.id, confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    assert err.value.code == "SLOT_TAKEN" and err.value.http_status == 409
    assert len(err.value.details["alternatives"]) == 3
    world.db.commit()
    assert appointment_count(world.db) == 1
    owner = world.db.scalars(select(Appointment.patient_id).where(Appointment.slot_id == slot.id)).one()
    assert owner == other


def test_tc04_duplicate_same_patient_doctor_day(world):
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    book_appointment(world.db, world.asha, world.asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        book_appointment(world.db, world.asha, world.asha.patient_id, slots[1].id, confirmed=True, now=NOW)
    assert err.value.code == "DUPLICATE" and err.value.http_status == 409
    world.db.commit()
    assert appointment_count(world.db) == 1


def test_same_patient_can_see_two_doctors_same_day(world):
    a = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    b = world.slots(world.doctor("Dr. Rohit Malhotra"), SATURDAY)[4]
    book_appointment(world.db, world.asha, world.asha.patient_id, a.id, confirmed=True, now=NOW)
    book_appointment(world.db, world.asha, world.asha.patient_id, b.id, confirmed=True, now=NOW)
    assert appointment_count(world.db) == 2


def test_booking_in_the_past_or_beyond_horizon_is_rejected(world):
    doctor = world.doctor("Dr. Suresh Pawar")
    past = world.slots(doctor, TODAY)[0]
    with pytest.raises(ToolError) as err:
        book_appointment(world.db, world.asha, world.asha.patient_id, past.id, confirmed=True, now=past.start_at)
    assert err.value.code == "VALIDATION_ERROR"
    far = world.slots(doctor, TODAY + timedelta(days=35))[0]
    with pytest.raises(ToolError):
        book_appointment(world.db, world.asha, world.asha.patient_id, far.id, confirmed=True, now=NOW)


def test_us03_reschedule_outside_cutoff_moves_and_frees_old_slot(world):
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    moved = reschedule_appointment(world.db, world.asha, appt["appointment_id"], slots[4].id, confirmed=True, now=NOW)
    world.db.commit()
    assert moved["appointment_id"] == appt["appointment_id"]
    assert moved["slot_id"] == slots[4].id and moved["status"] == "rescheduled"
    assert world.db.get(Slot, slots[0].id).status == "free"
    assert world.db.get(Slot, slots[4].id).status == "booked"


def test_tc05_reschedule_inside_cutoff_keeps_original(world):
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    inside = slots[0].start_at - timedelta(hours=6)
    with pytest.raises(ToolError) as err:
        reschedule_appointment(world.db, world.asha, appt["appointment_id"], slots[4].id, confirmed=True, now=inside)
    assert err.value.code == "POLICY_WINDOW" and err.value.http_status == 422
    assert "12 hours" in err.value.details["policy"]
    world.db.commit()
    kept = world.db.get(Appointment, appt["appointment_id"])
    assert kept.slot_id == slots[0].id and kept.status == "booked"
    assert world.db.get(Slot, slots[4].id).status == "free"


def test_reschedule_to_other_department_is_rejected(world):
    a = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    b = world.slots(world.doctor("Dr. Rohit Malhotra"), SATURDAY)[0]
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, a.id, confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        reschedule_appointment(world.db, world.asha, appt["appointment_id"], b.id, confirmed=True, now=NOW)
    assert err.value.code == "VALIDATION_ERROR"


def test_reschedule_needs_confirmation(world):
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        reschedule_appointment(world.db, world.asha, appt["appointment_id"], slots[3].id, now=NOW)
    assert err.value.code == "CONFIRMATION_REQUIRED"


def test_tc06_cancel_within_policy_frees_slot_and_audits(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[1]
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    result = cancel_appointment(world.db, world.asha, appt["appointment_id"], confirmed=True, now=NOW)
    world.db.commit()
    assert result["status"] == "cancelled" and "4 hours" in result["policy_note"]
    assert world.db.get(Appointment, appt["appointment_id"]).status == "cancelled"
    assert world.db.get(Slot, slot.id).status == "free"
    audit = world.db.scalars(select(AuditLog).where(AuditLog.tool == "cancel_appointment")).one()
    assert audit.result["ok"] is True and audit.user_id == world.asha.user_id


def test_cancel_too_late_explains_policy_and_changes_nothing(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[1]
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        cancel_appointment(
            world.db, world.asha, appt["appointment_id"], confirmed=True, now=slot.start_at - timedelta(hours=2)
        )
    assert err.value.code == "POLICY_WINDOW"
    assert world.db.get(Appointment, appt["appointment_id"]).status == "booked"


def test_cancelled_slot_can_be_booked_again(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[1]
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    cancel_appointment(world.db, world.asha, appt["appointment_id"], confirmed=True, now=NOW)
    other = world.other_patients(1)[0]
    book_appointment(world.db, world.staff, other, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    assert world.db.get(Slot, slot.id).status == "booked"


def test_cancel_twice_is_rejected(world):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[1]
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    cancel_appointment(world.db, world.asha, appt["appointment_id"], confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        cancel_appointment(world.db, world.asha, appt["appointment_id"], confirmed=True, now=NOW)
    assert err.value.code == "INVALID_STATE"


def test_fr16_history_lists_upcoming_and_past(world):
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    book_appointment(world.db, world.asha, world.asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    history = get_patient_appointments(world.db, world.asha, world.asha.patient_id, now=NOW)
    assert [a["slot_id"] for a in history["upcoming"]] == [slots[0].id]
    later = get_patient_appointments(
        world.db, world.asha, world.asha.patient_id, now=slots[0].start_at + timedelta(days=1)
    )
    assert later["upcoming"] == [] and len(later["past"]) == 1
