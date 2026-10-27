"""Phase 7B: admins set up the hospital - its details, departments, doctors and timetables - and the rest of
the app follows: search, booking, the queue, the assistant's prompt and its fixed messages."""

from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.messages import message
from app.agent.prompts import system_prompt
from app.api.main import app
from app.db.models import Appointment, HospitalProfile, Notification, Slot, WaitingList
from app.queue import engine
from app.timeutil import at, to_ist
from app.tools import hospital
from app.tools.booking import (
    book_appointment,
    cancel_appointment,
    check_availability,
    reschedule_appointment,
    search_doctors,
)
from app.tools.errors import ToolError
from app.tools.timetable import ensure_slots
from app.tools.waiting_list import join_waiting_list
from tests.conftest import NOW, TODAY
from tests.test_api import headers, login

TUE, WED, SAT = TODAY + timedelta(days=1), TODAY + timedelta(days=2), TODAY + timedelta(days=5)
NEXT_WED = WED + timedelta(days=7)


@pytest.fixture
def api(world, frozen_clock):
    return TestClient(app)


def admin(world):
    return world.user("mehta")


def day_slots(world, doctor_id: int, day: date, statuses=("free", "booked", "blocked")) -> list[Slot]:
    return list(
        world.db.scalars(
            select(Slot)
            .where(
                Slot.doctor_id == doctor_id,
                Slot.start_at >= at(day, time.min),
                Slot.start_at < at(day + timedelta(days=1), time.min),
                Slot.status.in_(statuses),
            )
            .order_by(Slot.start_at)
        )
    )


def clock(slots: list[Slot]) -> list[str]:
    return [f"{to_ist(s.start_at):%H:%M}" for s in slots]


def no_overlaps(slots: list[Slot]) -> bool:
    ordered = sorted(slots, key=lambda s: s.start_at)
    return all(a.end_at <= b.start_at for a, b in zip(ordered, ordered[1:], strict=False))


def neurology(world):
    dept = hospital.create_department(
        world.db, admin(world), "Neurology", 5, time(10, 0), time(13, 0), ["Brain", "nerves", "मस्तिष्क"], now=NOW
    )
    doctor = hospital.create_doctor(
        world.db, admin(world), "Dr. Kiran Patkar", dept["department_id"], ["mr", "en"], [3, 6], 20, now=NOW
    )
    return dept, doctor


# --------------------------------------------------------------------------- the hospital's details


def test_admin_sets_the_hospitals_details_and_the_app_uses_them(api, world):
    body = {
        "name": {"en": "Sahyadri Care Hospital", "hi": "सह्याद्रि केयर हॉस्पिटल", "mr": ""},
        "address": "12 FC Road, Pune 411004",
        "phone": "+91 20 2555 0101",
        "reception_opens": "07:30",
        "reception_closes": "21:00",
        "emergency_note": {"en": "Our emergency department is at Gate 2 and is open 24 hours.", "hi": "", "mr": ""},
    }
    admin_h = headers(login(api, "admin"))
    assert api.put("/api/v1/admin/hospital/profile", json=body, headers=admin_h).status_code == 200
    public = api.get("/api/v1/config").json()["hospital"]
    assert public["name"] == {
        "en": "Sahyadri Care Hospital",
        "hi": "सह्याद्रि केयर हॉस्पिटल",
        "mr": "Sahyadri Care Hospital",
    }
    assert public["phone"] == "+91 20 2555 0101"

    world.db.expire_all()
    assert "assistant of Sahyadri Care Hospital" in system_prompt(
        "patient", "Asha", {}, "en", NOW, hospital.hospital_name(world.db)
    )
    english = message("emergency", "en", **hospital.message_values(world.db, "en"))
    assert "Gate 2" in english and "Omkar" not in english
    marathi = message("emergency", "mr", **hospital.message_values(world.db, "mr"))
    assert "Gate 2" not in marathi and "112" in marathi  # no English sentence inside a Marathi reply
    assert "07:30–21:00" in message("handoff", "hi", ticket_id=7, **hospital.message_values(world.db, "hi"))
    receipt_name = hospital.hospital_name(world.db)
    assert receipt_name == "Sahyadri Care Hospital"

    bad = {**body, "name": {"en": "", "hi": "कुछ", "mr": ""}}
    assert api.put("/api/v1/admin/hospital/profile", json=bad, headers=admin_h).status_code == 400
    late = {**body, "reception_opens": "21:00", "reception_closes": "07:30"}
    assert api.put("/api/v1/admin/hospital/profile", json=late, headers=admin_h).status_code == 400
    staff = headers(login(api, "staff"))
    assert api.put("/api/v1/admin/hospital/profile", json=body, headers=staff).status_code == 403
    assert api.get("/api/v1/admin/hospital", headers=staff).status_code == 403


def test_without_details_the_app_names_no_hospital(world):
    world.db.delete(world.db.get(HospitalProfile, 1))
    world.db.flush()
    assert hospital.hospital_name(world.db) == "" and hospital.public_profile(world.db) is None
    assert "assistant of this hospital (" in system_prompt(
        "patient", "Asha", {}, "en", NOW, hospital.hospital_name(world.db)
    )
    reply = message("emergency", "en", **hospital.message_values(world.db, "en"))
    assert "immediately. Do not wait" in reply  # the general advice stays; no invented directions
    assert "during working hours. You can" in message(
        "handoff", "en", ticket_id=1, **hospital.message_values(world.db, "en")
    )


# --------------------------------------------------------------------------- departments


def test_departments_are_found_by_their_own_search_words(world):
    dept, _ = neurology(world)
    assert dept["aliases"] == ["brain", "nerves", "मस्तिष्क"]
    for typed in ("Neurology", "brain", "my nerves", "मस्तिष्क रोग"):
        assert search_doctors(world.db, specialty=typed, now=NOW)["criteria"]["department"] == "Neurology"
    assert search_doctors(world.db, specialty="heart", now=NOW)["criteria"]["department"] == "Cardiology"
    with pytest.raises(ToolError) as err:
        search_doctors(world.db, specialty="astrology", now=NOW)
    assert "Neurology" in err.value.details["known"]


def test_department_rules(world):
    a = admin(world)
    with pytest.raises(ToolError) as err:
        hospital.create_department(world.db, a, "cardiology", 3, time(9), time(13), now=NOW)
    assert err.value.code == "DUPLICATE"
    with pytest.raises(ToolError):
        hospital.create_department(world.db, a, "Night OPD", 1, time(13), time(9), now=NOW)
    dept, _ = neurology(world)
    with pytest.raises(ToolError) as err:  # Dr. Patkar's 20-minute appointments must fit
        hospital.update_department(
            world.db, a, dept["department_id"], opd_start=time(10), opd_end=time(10, 10), now=NOW
        )
    assert err.value.code == "VALIDATION_ERROR"
    with pytest.raises(ToolError) as err:
        hospital.delete_department(world.db, a, dept["department_id"], now=NOW)
    assert err.value.code == "INVALID_STATE"
    empty = hospital.create_department(world.db, a, "Psychiatry", 2, time(9), time(12), now=NOW)
    assert hospital.delete_department(world.db, a, empty["department_id"], now=NOW)["deleted"] is True
    with pytest.raises(ToolError):
        hospital.create_department(world.db, world.staff, "Dentistry", 1, time(9), time(12), now=NOW)


# --------------------------------------------------------------------------- doctors and timetables


def test_a_new_doctor_can_be_booked_from_tomorrow(world):
    _, doctor = neurology(world)
    assert doctor["slots_created"] > 0 and doctor["from"] == TUE.isoformat()
    assert clock(day_slots(world, doctor["doctor_id"], WED)) == [
        "10:00", "10:20", "10:40", "11:00", "11:20", "11:40", "12:00", "12:20", "12:40"
    ]  # fmt: skip
    found = search_doctors(world.db, specialty="brain", language="Marathi", day="Wednesday", now=NOW)["doctors"]
    assert [d["name"] for d in found] == ["Dr. Kiran Patkar"]
    free = check_availability(world.db, doctor["doctor_id"], WED, now=NOW)["slots"]
    booked = book_appointment(world.db, world.asha, world.asha.patient_id, free[0]["slot_id"], confirmed=True, now=NOW)
    assert booked["doctor_name"] == "Dr. Kiran Patkar"


def test_a_changed_timetable_keeps_bookings_and_fills_in_around_them(world):
    _, doctor = neurology(world)
    did = doctor["doctor_id"]
    second = check_availability(world.db, did, WED, now=NOW)["slots"][1]  # 10:20
    appt = book_appointment(world.db, world.asha, world.asha.patient_id, second["slot_id"], confirmed=True, now=NOW)

    changed = hospital.update_doctor(world.db, admin(world), did, slot_minutes=15, now=NOW)
    timetable = changed["timetable"]
    assert timetable["from"] == TUE.isoformat()
    assert [b["appointment_id"] for b in timetable["outside"]] == [appt["appointment_id"]]
    wed = day_slots(world, did, WED)
    assert no_overlaps(wed)
    assert clock(wed) == [
        "10:00",
        "10:20",
        "10:45",
        "11:00",
        "11:15",
        "11:30",
        "11:45",
        "12:00",
        "12:15",
        "12:30",
        "12:45",
    ]
    assert world.db.get(Appointment, appt["appointment_id"]).status == "booked"  # the patient keeps the visit

    # When that visit is cancelled, its old-length slot is retired and the 15-minute ones take its place.
    cancel_appointment(world.db, world.asha, appt["appointment_id"], confirmed=True, now=NOW)
    wed = day_slots(world, did, WED)
    assert no_overlaps(wed) and len(wed) == 12 and all(s.end_at - s.start_at == timedelta(minutes=15) for s in wed)


def test_new_opd_hours_apply_from_tomorrow_to_the_whole_department(world):
    dept, doctor = neurology(world)
    result = hospital.update_department(
        world.db, admin(world), dept["department_id"], opd_start=time(9), opd_end=time(11), now=NOW
    )
    assert result["timetable"]["created"] > 0
    assert clock(day_slots(world, doctor["doctor_id"], SAT)) == ["09:00", "09:20", "09:40", "10:00", "10:20", "10:40"]


def test_todays_opd_runs_as_planned_when_the_timetable_changes(world):
    pawar = world.doctor("Dr. Suresh Pawar")  # Monday to Saturday
    world.slots(pawar, TODAY)
    ensure_slots(world.db, TUE, TUE)
    hospital.update_doctor(world.db, admin(world), pawar.id, opd_days=[3, 4, 5], now=NOW)  # no Mon, Tue or Sat now
    assert engine.get_or_create_session(world.db, pawar.id, TODAY) is not None  # today's queue still opens
    assert day_slots(world, pawar.id, TODAY)  # and today's slots are untouched
    assert day_slots(world, pawar.id, TUE) == []
    assert check_availability(world.db, pawar.id, TUE, now=NOW)["works_that_day"] is False


def test_a_doctor_who_leaves_has_later_bookings_moved_off(world):
    kulkarni = world.doctor("Dr. Anand Kulkarni")  # Cardiology, Mon / Wed / Sat
    ensure_slots(world.db, TODAY, NEXT_WED)
    asha = world.asha.patient_id
    wed = check_availability(world.db, kulkarni.id, WED, now=NOW)["slots"][0]
    sat = check_availability(world.db, kulkarni.id, SAT, now=NOW)["slots"][0]
    keep = book_appointment(world.db, world.asha, asha, wed["slot_id"], confirmed=True, now=NOW)
    moved = book_appointment(world.db, world.asha, asha, sat["slot_id"], confirmed=True, now=NOW)
    other = world.other_patients(1)[0]
    for slot in day_slots(world, kulkarni.id, SAT, ("free",)):
        slot.status = "blocked"  # a full Saturday, so the waiting list is open
    join_waiting_list(world.db, world.staff, other, kulkarni.id, [SAT.isoformat()], confirmed=True, now=NOW)

    with pytest.raises(ToolError):
        hospital.set_last_day(world.db, admin(world), kulkarni.id, TODAY - timedelta(days=1), now=NOW)
    result = hospital.set_last_day(world.db, admin(world), kulkarni.id, WED, now=NOW)
    assert [m["appointment_id"] for m in result["moved"]] == [moved["appointment_id"]]
    assert result["waiting_list"] == 1 and result["current"] is True
    assert world.db.get(Appointment, keep["appointment_id"]).status == "booked"
    assert world.db.get(Appointment, moved["appointment_id"]).status == "displaced"
    told = world.db.scalars(select(Notification).where(Notification.patient_id == asha)).all()
    assert any("no longer holds OPD here" in n.message for n in told)
    assert world.db.scalars(select(WaitingList).where(WaitingList.patient_id == other)).one().status == "cancelled"
    assert day_slots(world, kulkarni.id, SAT, ("free", "blocked")) == []

    on_sat = search_doctors(world.db, specialty="cardiology", day="Saturday", now=NOW)["doctors"]
    assert "Dr. Anand Kulkarni" not in [d["name"] for d in on_sat]
    assert check_availability(world.db, kulkarni.id, SAT, now=NOW)["works_that_day"] is False
    # The patient moves to a colleague in the department, free of charge.
    iyer = world.doctor("Dr. Meera Iyer")  # Cardiology, Mon / Thu / Sat
    new_slot = check_availability(world.db, iyer.id, SAT, now=NOW)["slots"][0]
    rescheduled = reschedule_appointment(
        world.db, world.asha, moved["appointment_id"], new_slot["slot_id"], confirmed=True, now=NOW
    )
    assert rescheduled["doctor_name"] == "Dr. Meera Iyer"
    old = world.db.get(Slot, sat["slot_id"])
    assert old.status == "retired"  # never offered again

    back = hospital.set_last_day(world.db, admin(world), kulkarni.id, None, now=NOW)
    assert back["last_day"] is None and back["slots_created"] > 0
    assert check_availability(world.db, kulkarni.id, SAT, now=NOW)["slots"]


def test_doctors_are_removed_only_while_nothing_refers_to_them(world):
    _, doctor = neurology(world)
    assert hospital.delete_doctor(world.db, admin(world), doctor["doctor_id"], now=NOW)["deleted"] is True
    assert world.db.scalars(select(Slot).where(Slot.doctor_id == doctor["doctor_id"])).first() is None
    with pytest.raises(ToolError) as err:  # has a doctor account
        hospital.delete_doctor(world.db, admin(world), world.doctor("Dr. Lakshmi Rao").id, now=NOW)
    assert err.value.code == "INVALID_STATE"
    with pytest.raises(ToolError) as err:
        hospital.create_doctor(world.db, admin(world), "dr. suresh pawar", 1, ["en"], [1], 10, now=NOW)
    assert err.value.code == "DUPLICATE"
    with pytest.raises(ToolError):
        hospital.create_doctor(world.db, admin(world), "Dr. New Name", 1, ["fr"], [1], 10, now=NOW)
    with pytest.raises(ToolError):
        hospital.create_doctor(world.db, admin(world), "Dr. New Name", 1, ["en"], [], 10, now=NOW)


def test_setup_page_through_the_api(api, world):
    admin_h = headers(login(api, "admin"))
    page = api.get("/api/v1/admin/hospital", headers=admin_h).json()
    assert page["profile"]["name"]["en"] == "Omkar General Hospital" and len(page["departments"]) == 8
    cardiology = next(d for d in page["departments"] if d["name"] == "Cardiology")
    assert {d["account"] for d in cardiology["doctors"]} == {"dr-kulkarni", "dr-siddiqui", "dr-iyer"}
    made = api.post(
        "/api/v1/admin/departments",
        json={"name": "Neurology", "floor": 5, "opd_start": "10:00", "opd_end": "13:00", "aliases": ["brain"]},
        headers=admin_h,
    )
    assert made.status_code == 201
    dept_id = made.json()["department_id"]
    doc = api.post(
        "/api/v1/admin/doctors",
        json={
            "name": "Dr. Kiran Patkar",
            "department_id": dept_id,
            "languages": ["en"],
            "opd_days": [3],
            "slot_minutes": 20,
        },
        headers=admin_h,
    )
    assert doc.status_code == 201
    doctor_id = doc.json()["doctor_id"]
    last = api.put(f"/api/v1/admin/doctors/{doctor_id}/last-day", json={"last_day": "2026-11-30"}, headers=admin_h)
    assert last.status_code == 200 and last.json()["last_day"] == "2026-11-30"
    renamed = api.patch(f"/api/v1/admin/departments/{dept_id}", json={"name": "Neurosciences"}, headers=admin_h)
    assert renamed.json()["name"] == "Neurosciences"
    assert api.delete(f"/api/v1/admin/doctors/{doctor_id}", headers=admin_h).status_code == 200
    assert api.delete(f"/api/v1/admin/departments/{dept_id}", headers=admin_h).status_code == 200


def test_demo_reset_keeps_caregivers_own_accounts(api, world):
    body = {"account_type": "caregiver", "name": "Sanjay Kale", "username": "sanjay.k", "password": "lotus-pond-88"}
    assert api.post("/api/v1/auth/register", json=body).status_code == 201
    world.db.commit()
    assert api.post("/api/v1/admin/reset", headers=headers(login(api, "admin"))).status_code == 200
    again = api.post("/api/v1/auth/login", json={"username": "sanjay.k", "password": "lotus-pond-88"})
    assert again.status_code == 200 and again.json()["user"]["role"] == "caregiver"
