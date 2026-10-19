"""TC-03 (two simultaneous bookings for one slot; exactly one succeeds) and queue concurrency."""

import threading
from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import Appointment, QueueEntry
from app.queue import engine
from app.tools.booking import book_appointment
from app.tools.errors import ToolError
from tests.conftest import NOW, SATURDAY, TODAY


def race(factory, attempts):
    """Run each (actor, patient_id, slot_id) booking in its own session and thread at the same moment."""
    barrier = threading.Barrier(len(attempts))
    outcomes = [None] * len(attempts)

    def run(i, actor, patient_id, slot_id):
        db = factory()
        try:
            barrier.wait()
            book_appointment(db, actor, patient_id, slot_id, confirmed=True, now=NOW)
            db.commit()
            outcomes[i] = "ok"
        except ToolError as err:
            db.commit()  # the failure is audited; nothing else was written
            outcomes[i] = err.code
        finally:
            db.close()

    threads = [threading.Thread(target=run, args=(i, *a)) for i, a in enumerate(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return outcomes


def test_tc03_two_simultaneous_bookings_same_slot(world, factory):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    world.db.commit()
    p1, p2 = world.other_patients(2)
    outcomes = race(factory, [(world.staff, p1, slot.id), (world.staff, p2, slot.id)])
    assert sorted(outcomes) == ["SLOT_TAKEN", "ok"]
    check = factory()
    assert check.scalar(select(func.count()).select_from(Appointment).where(Appointment.slot_id == slot.id)) == 1
    check.close()


def test_ten_way_race_still_one_winner(world, factory):
    slot = world.slots(world.doctor("Dr. Suresh Pawar"), SATURDAY)[3]
    world.db.commit()
    patients = world.other_patients(10)
    outcomes = race(factory, [(world.staff, p, slot.id) for p in patients])
    assert outcomes.count("ok") == 1 and outcomes.count("SLOT_TAKEN") == 9


def test_simultaneous_duplicate_bookings_for_one_patient(world, factory):
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    world.db.commit()
    patient = world.other_patients(1)[0]
    outcomes = race(factory, [(world.staff, patient, slots[0].id), (world.staff, patient, slots[5].id)])
    assert sorted(outcomes) == ["DUPLICATE", "ok"]


def run_parallel(factory, calls):
    """Run callables db -> result at the same moment, each in its own session; return results or error codes."""
    barrier = threading.Barrier(len(calls))
    outcomes = [None] * len(calls)

    def run(i, fn):
        db = factory()
        try:
            barrier.wait()
            outcomes[i] = fn(db)
            db.commit()
        except ToolError as err:
            db.commit()
            outcomes[i] = err.code
        except Exception as err:  # noqa: BLE001 - surfaced by the assertions below
            db.rollback()
            outcomes[i] = repr(err)
        finally:
            db.close()

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return outcomes


def test_simultaneous_walk_ins_get_unique_tokens(world, factory):
    doctor = world.doctor("Dr. Suresh Pawar")
    staff = world.staff
    patients = world.other_patients(8)
    calls = [
        (lambda db, p=p: engine.register_walk_in(db, staff, doctor.id, patient_id=p, now=NOW)["token"])
        for p in patients
    ]
    tokens = run_parallel(factory, calls)
    assert sorted(tokens) == [f"W{i:02d}" for i in range(1, 9)]


def test_mixed_queue_actions_do_not_deadlock(world, factory):
    doctor = world.doctor("Dr. Suresh Pawar")
    staff = world.staff
    slots = world.slots(doctor, TODAY)
    patients = world.other_patients(6)
    appts = [
        book_appointment(world.db, staff, p, s.id, confirmed=True, now=NOW - timedelta(days=1))
        for p, s in zip(patients[:3], slots[4:7], strict=True)
    ]
    walk_ins = [engine.register_walk_in(world.db, staff, doctor.id, patient_id=p, now=NOW) for p in patients[3:]]
    world.db.commit()
    session_id = walk_ins[0]["session_id"]
    calls = [
        lambda db: engine.call_next(db, staff, session_id, now=NOW)["token"],
        lambda db: engine.set_priority(db, staff, walk_ins[2]["entry_id"], 2, now=NOW)["priority"],
        lambda db: engine.check_in(db, staff, appts[0]["appointment_id"], now=NOW)["token"],
        lambda db: engine.check_in(db, staff, appts[1]["appointment_id"], now=NOW)["token"],
        lambda db: engine.record_doctor_event(db, staff, session_id, "delay", minutes=5, now=NOW)["doctor_status"],
    ]
    outcomes = run_parallel(factory, calls)
    assert not any(isinstance(o, str) and o.startswith(("OperationalError", "DBAPIError")) for o in outcomes), outcomes
    check = factory()
    tokens = check.scalars(select(QueueEntry.token).where(QueueEntry.session_id == session_id)).all()
    assert len(tokens) == len(set(tokens)) == 5
    check.close()
