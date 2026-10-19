"""TC-07 and US-05: waiting list, offer-first on a freed slot, offer expiry."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import Notification, Slot, WaitingList
from app.tools.booking import book_appointment, cancel_appointment, check_availability
from app.tools.errors import ToolError
from app.tools.waiting_list import expire_waitlist_offers, join_waiting_list
from tests.conftest import NOW, SATURDAY


@pytest.fixture
def full_day(world):
    """Dr. Kulkarni fully booked on Saturday by other patients."""
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    appts = [
        book_appointment(world.db, world.staff, p, s.id, confirmed=True, now=NOW)
        for p, s in zip(world.other_patients(len(slots)), slots, strict=True)
    ]
    return world.doctor("Dr. Anand Kulkarni"), slots, appts


def test_join_requires_confirmation(world, full_day):
    doctor, _, _ = full_day
    with pytest.raises(ToolError) as err:
        join_waiting_list(world.db, world.asha, world.asha.patient_id, doctor.id, [SATURDAY.isoformat()], now=NOW)
    assert err.value.code == "CONFIRMATION_REQUIRED"


def test_join_refused_when_slots_are_free(world):
    doctor = world.doctor("Dr. Anand Kulkarni")
    world.slots(doctor, SATURDAY)
    with pytest.raises(ToolError) as err:
        join_waiting_list(world.db, world.asha, world.asha.patient_id, doctor.id, [SATURDAY], confirmed=True, now=NOW)
    assert err.value.code == "SLOTS_AVAILABLE" and err.value.details["slots"]


def test_join_once_only(world, full_day):
    doctor, _, _ = full_day
    join_waiting_list(world.db, world.asha, world.asha.patient_id, doctor.id, [SATURDAY], confirmed=True, now=NOW)
    with pytest.raises(ToolError) as err:
        join_waiting_list(world.db, world.asha, world.asha.patient_id, doctor.id, [SATURDAY], confirmed=True, now=NOW)
    assert err.value.code == "ALREADY_ON_LIST"


def test_tc07_freed_slot_is_offered_to_waiting_patient_first(world, full_day):
    doctor, slots, appts = full_day
    asha = world.asha
    entry = join_waiting_list(world.db, asha, asha.patient_id, doctor.id, [SATURDAY], confirmed=True, now=NOW)
    later_patient = world.other_patients(len(slots) + 1)[-1]
    join_waiting_list(
        world.db, world.staff, later_patient, doctor.id, [SATURDAY], confirmed=True, now=NOW + timedelta(minutes=5)
    )

    cancel_appointment(
        world.db, world.staff, appts[3]["appointment_id"], confirmed=True, now=NOW + timedelta(minutes=10)
    )
    freed = world.db.get(Slot, slots[3].id)
    offered = world.db.get(WaitingList, entry["waiting_list_id"])
    assert offered.status == "offered" and offered.offered_slot_id == freed.id
    assert freed.held_for_patient_id == asha.patient_id
    note = world.db.scalars(select(Notification).where(Notification.patient_id == asha.patient_id)).one()
    assert "has opened" in note.message and note.mocked is True

    # Nobody else sees or can take the held slot ...
    assert freed.id not in [s["slot_id"] for s in check_availability(world.db, doctor.id, SATURDAY, now=NOW)["slots"]]
    with pytest.raises(ToolError) as err:
        book_appointment(
            world.db, world.staff, later_patient, freed.id, confirmed=True, now=NOW + timedelta(minutes=20)
        )
    assert err.value.code == "SLOT_TAKEN"

    # ... but the waiting patient does, and can book it.
    mine = check_availability(world.db, doctor.id, SATURDAY, patient_id=asha.patient_id, now=NOW)["slots"]
    assert [s["slot_id"] for s in mine] == [freed.id]
    book_appointment(world.db, asha, asha.patient_id, freed.id, confirmed=True, now=NOW + timedelta(minutes=30))
    assert world.db.get(WaitingList, entry["waiting_list_id"]).status == "fulfilled"
    assert freed.status == "booked" and freed.held_until is None


def test_lapsed_offer_passes_to_next_patient(world, full_day):
    doctor, slots, appts = full_day
    first = join_waiting_list(
        world.db, world.asha, world.asha.patient_id, doctor.id, [SATURDAY], confirmed=True, now=NOW
    )
    second_patient = world.other_patients(len(slots) + 1)[-1]
    second = join_waiting_list(
        world.db, world.staff, second_patient, doctor.id, [SATURDAY], confirmed=True, now=NOW + timedelta(minutes=1)
    )
    cancel_appointment(world.db, world.staff, appts[0]["appointment_id"], confirmed=True, now=NOW)

    assert expire_waitlist_offers(world.db, now=NOW + timedelta(hours=3)) == 1
    assert world.db.get(WaitingList, first["waiting_list_id"]).status == "active"
    nxt = world.db.get(WaitingList, second["waiting_list_id"])
    assert nxt.status == "offered" and nxt.offered_slot_id == slots[0].id
    assert world.db.get(Slot, slots[0].id).held_for_patient_id == second_patient


def test_booking_another_day_releases_held_offer_to_next_patient(world, full_day):
    doctor, slots, appts = full_day
    entry = join_waiting_list(
        world.db, world.asha, world.asha.patient_id, doctor.id, [SATURDAY], confirmed=True, now=NOW
    )
    second_patient = world.other_patients(len(slots) + 1)[-1]
    second = join_waiting_list(
        world.db, world.staff, second_patient, doctor.id, [SATURDAY], confirmed=True, now=NOW + timedelta(minutes=1)
    )
    cancel_appointment(world.db, world.staff, appts[0]["appointment_id"], confirmed=True, now=NOW)
    assert world.db.get(Slot, slots[0].id).held_for_patient_id == world.asha.patient_id

    # Asha books the same doctor on Monday instead; her Saturday hold passes to the next patient.
    monday = world.slots(doctor, SATURDAY + timedelta(days=2))[0]
    book_appointment(world.db, world.asha, world.asha.patient_id, monday.id, confirmed=True, now=NOW)
    assert world.db.get(WaitingList, entry["waiting_list_id"]).status == "fulfilled"
    assert world.db.get(Slot, slots[0].id).held_for_patient_id == second_patient
    assert world.db.get(WaitingList, second["waiting_list_id"]).status == "offered"


def test_lapsed_hold_lets_others_book_and_returns_offer_to_list(world, full_day):
    doctor, slots, appts = full_day
    entry = join_waiting_list(
        world.db, world.asha, world.asha.patient_id, doctor.id, [SATURDAY], confirmed=True, now=NOW
    )
    cancel_appointment(world.db, world.staff, appts[2]["appointment_id"], confirmed=True, now=NOW)
    other = world.other_patients(len(slots) + 1)[-1]
    # The 2-hour hold has lapsed and the expiry job has not run yet.
    book_appointment(world.db, world.staff, other, slots[2].id, confirmed=True, now=NOW + timedelta(hours=3))
    stale = world.db.get(WaitingList, entry["waiting_list_id"])
    assert stale.status == "active" and stale.offered_slot_id is None
