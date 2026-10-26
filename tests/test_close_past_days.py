"""Days that are over are closed even when the desk did not close the queue (D-127)."""

from datetime import timedelta

from sqlalchemy import select

from app.db.models import Appointment, AuditLog, Notification, QueueEntry, QueueSession
from app.queue import engine
from app.tools.booking import book_appointment
from tests.conftest import NOW, TODAY


def at_clock(hh: int, mm: int):
    return NOW.replace(hour=hh, minute=mm)


def test_a_day_left_open_is_closed_the_next_day(world):
    db, staff = world.db, world.staff
    pawar, gokhale = world.doctor("Dr. Suresh Pawar"), world.doctor("Dr. Snehal Gokhale")
    p = world.other_patients(5)
    booked_at = NOW - timedelta(days=3)
    slots = world.slots(pawar, TODAY)
    seen, waiting, absent = (
        book_appointment(db, staff, p[i], slots[k].id, confirmed=True, now=booked_at)["appointment_id"]
        for i, k in ((0, 0), (1, 3), (2, 6))
    )
    other = world.slots(gokhale, TODAY)
    unopened = book_appointment(db, staff, p[3], other[2].id, confirmed=True, now=booked_at)["appointment_id"]
    tomorrow = world.slots(pawar, TODAY + timedelta(days=1))
    later = book_appointment(db, staff, p[4], tomorrow[1].id, confirmed=True, now=booked_at)["appointment_id"]

    first = engine.check_in(db, staff, seen, now=at_clock(8, 50))
    engine.check_in(db, staff, waiting, now=at_clock(9, 20))
    session_id = db.get(QueueEntry, first["entry_id"]).session_id
    engine.call_next(db, staff, session_id, now=at_clock(9, 0))
    engine.start_consultation(db, staff, first["entry_id"], now=at_clock(9, 1))
    # The desk goes home: one patient still in the room, one waiting, one never came; Dr. Gokhale's queue
    # was never opened.
    assert engine.close_past_days(db, now=at_clock(18, 0)) == {"sessions_closed": 0, "no_shows": 0, "left_unseen": 0}

    next_morning = NOW + timedelta(days=1, hours=-7)  # 01:00 the next day
    result = engine.close_past_days(db, now=next_morning)
    assert result == {"sessions_closed": 1, "no_shows": 2, "left_unseen": 1}
    status = {a: db.get(Appointment, a).status for a in (seen, waiting, absent, unopened, later)}
    assert status == {seen: "completed", waiting: "left", absent: "no_show", unopened: "no_show", later: "booked"}
    assert db.get(QueueSession, session_id).status == "closed"
    offered = set(db.scalars(select(Notification.appointment_id).where(Notification.kind == "rebook")))
    assert {waiting, absent, unopened} <= offered and seen not in offered
    assert db.scalars(select(AuditLog).where(AuditLog.tool == "close_past_days")).one().role == "system"

    # Nothing left to do: a second run changes nothing and records nothing.
    assert engine.close_past_days(db, now=next_morning + timedelta(hours=1)) == {
        "sessions_closed": 0, "no_shows": 0, "left_unseen": 0
    }  # fmt: skip
    assert len(db.scalars(select(AuditLog).where(AuditLog.tool == "close_past_days")).all()) == 1


def test_old_visits_are_recorded_without_messaging_the_patient(world):
    db, staff = world.db, world.staff
    pawar = world.doctor("Dr. Suresh Pawar")
    patient = world.other_patients(1)[0]
    slot = world.slots(pawar, TODAY)[4]
    appt = book_appointment(db, staff, patient, slot.id, confirmed=True, now=NOW - timedelta(days=1))
    engine.close_past_days(db, now=NOW + timedelta(days=5))
    assert db.get(Appointment, appt["appointment_id"]).status == "no_show"
    notes = db.scalars(
        select(Notification).where(Notification.appointment_id == appt["appointment_id"], Notification.kind == "rebook")
    ).all()
    assert notes == []  # five days later a "we missed you" message would only confuse
