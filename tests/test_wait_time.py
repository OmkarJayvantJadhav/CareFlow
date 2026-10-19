"""Wait-time features and live predictions: FR-24, FR-25, TC-10, TC-11."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import Notification, QueueEntry, QueueSession, WaitPrediction
from app.ml.features import FEATURES, load_session_records, state_at
from app.ml.model import ARTIFACT_DIR, Estimate, FallbackModel, LightGbmModel, display_range, get_wait_model
from app.queue import engine
from app.queue.predictions import latest_estimate, predictions_disabled
from app.tools.booking import book_appointment
from tests.conftest import NOW, TODAY


def at_clock(hh: int, mm: int):
    return NOW.replace(hour=hh, minute=mm)


@pytest.fixture
def clinic(world):
    """Dr. Pawar (10-minute slots from 09:00): four bookings and two walk-ins checked in before 09:00."""
    doctor = world.doctor("Dr. Suresh Pawar")
    slots = world.slots(doctor, TODAY)
    patients = world.other_patients(8)
    appts = [
        book_appointment(world.db, world.staff, patients[i], slots[k].id, confirmed=True, now=NOW - timedelta(days=1))
        for i, k in enumerate((0, 2, 3, 6))
    ]
    staff = world.staff
    for i, appt in enumerate(appts[:3]):
        engine.check_in(world.db, staff, appt["appointment_id"], now=at_clock(8, 40 + i))
    walk_ins = [
        engine.register_walk_in(world.db, staff, doctor.id, patient_id=patients[5 + i], now=at_clock(8, 45 + i))
        for i in range(2)
    ]
    world.db.commit()
    session = world.db.scalars(select(QueueSession)).one()
    return world, doctor, session, appts, walk_ins


def predictions(db) -> int:
    return db.scalar(select(func.count()).select_from(WaitPrediction))


def test_rebuilt_state_matches_the_engine(clinic):
    world, _, session, _, _ = clinic
    rows = state_at(load_session_records(world.db, session.id), at_clock(8, 50))
    engine_order = [e.id for e in engine.ordered_waiting(world.db, session, at_clock(8, 50))]
    assert [r.entry_id for r in rows] == engine_order
    assert [r.position for r in rows] == [world.db.get(QueueEntry, i).position for i in engine_order]
    assert all(len(r.features) == len(FEATURES) for r in rows)


def test_state_at_uses_only_the_past(clinic):
    world, _, session, _, walk_ins = clinic
    records = load_session_records(world.db, session.id)
    early = state_at(records, at_clock(8, 41))  # before the walk-ins and the third booking arrived
    assert len(early) == 2 and walk_ins[0]["entry_id"] not in [r.entry_id for r in early]
    engine.call_next(world.db, world.staff, session.id, now=at_clock(9, 0))
    world.db.commit()
    records = load_session_records(world.db, session.id)
    assert len(state_at(records, at_clock(8, 59))) == 5  # the 09:00 call is in the future at 08:59
    assert len(state_at(records, at_clock(9, 0))) == 4


def test_tc11_every_queue_event_writes_a_prediction_for_every_waiting_patient(clinic):
    world, doctor, session, appts, _ = clinic
    db, staff = world.db, world.staff
    before = predictions(db)
    engine.record_doctor_event(db, staff, session.id, "delay", minutes=5, now=at_clock(8, 55))
    waiting = db.scalar(select(func.count()).select_from(QueueEntry).where(QueueEntry.status == "waiting"))
    assert predictions(db) - before == waiting == 5
    called = engine.call_next(db, staff, session.id, now=at_clock(9, 5))
    assert predictions(db) - before == 5 + 4
    engine.start_consultation(db, staff, called["entry_id"], now=at_clock(9, 6))
    assert predictions(db) - before == 5 + 4 + 4
    rows = db.scalars(select(WaitPrediction).order_by(WaitPrediction.id.desc()).limit(4)).all()
    assert all(r.low_min <= r.predicted_min <= r.high_min for r in rows)
    assert {r.model_version for r in rows} == {get_wait_model().version}


def test_tc10_break_keeps_positions_and_shifts_estimates(clinic):
    world, _, session, _, _ = clinic
    db, staff = world.db, world.staff
    called = engine.call_next(db, staff, session.id, now=at_clock(9, 0))
    engine.start_consultation(db, staff, called["entry_id"], now=at_clock(9, 1))
    t = at_clock(9, 5)
    before_rows = state_at(load_session_records(db, session.id), t)
    model = get_wait_model()
    before = {r.entry_id: e for r, e in zip(before_rows, model.predict(before_rows), strict=True)}
    positions = {r.entry_id: r.position for r in before_rows}

    engine.record_doctor_event(db, staff, session.id, "break", minutes=20, now=t)
    after_rows = state_at(load_session_records(db, session.id), t)
    after = {r.entry_id: e for r, e in zip(after_rows, model.predict(after_rows), strict=True)}
    assert {r.entry_id: r.position for r in after_rows} == positions
    assert all(r.start_offset == 20 for r in after_rows) and all(r.start_offset == 0 for r in before_rows)
    shifts = [after[i].predicted_min - before[i].predicted_min for i in before]
    # The known 20-minute unavailability is added exactly (start_offset above). The total moves by
    # up to that much: booked patients whose slot is after the break would have waited for their
    # slot anyway, so the break costs them less.
    assert all(10 <= s <= 21 for s in shifts), shifts
    stored = db.scalars(select(WaitPrediction).order_by(WaitPrediction.id.desc()).limit(len(after))).all()
    assert all(p.predicted_min >= 20 for p in stored)


def test_turn_near_notification_is_sent_once(clinic):
    world, _, session, _, _ = clinic
    db = world.db
    notes = db.scalars(select(Notification).where(Notification.message.contains("Your turn is near"))).all()
    assert notes  # the first patients in line are within three of the door
    count = len(notes)
    engine.record_doctor_event(db, world.staff, session.id, "delay", minutes=5, now=at_clock(8, 56))
    again = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.message.contains("Your turn is near"))
    )
    assert again == count


def test_latest_estimate_ages_between_events(clinic):
    world, _, session, _, walk_ins = clinic
    entry_id = walk_ins[1]["entry_id"]
    fresh = latest_estimate(world.db, entry_id, at_clock(8, 46))
    later = latest_estimate(world.db, entry_id, at_clock(8, 56))
    assert later["predicted_min"] == pytest.approx(max(0, fresh["predicted_min"] - 10), abs=0.11)
    assert later["display"].startswith(("about", "less than"))


def test_queue_status_includes_the_estimate_for_the_owner(clinic):
    world, _, session, appts, _ = clinic
    entry = world.db.scalars(select(QueueEntry).where(QueueEntry.appointment_id == appts[1]["appointment_id"])).one()
    patient_actor = world.staff  # staff can read any entry
    status = engine.get_queue_status(world.db, patient_actor, entry.id, now=at_clock(8, 50))
    assert status["estimate"]["low_min"] <= status["estimate"]["predicted_min"] <= status["estimate"]["high_min"]


def test_no_predictions_while_replaying_history(world):
    doctor = world.doctor("Dr. Suresh Pawar")
    with predictions_disabled():
        engine.register_walk_in(world.db, world.staff, doctor.id, patient_id=world.other_patients(1)[0], now=NOW)
    assert predictions(world.db) == 0


def test_display_range_is_rounded_and_never_a_single_number():
    assert display_range(Estimate(34.2, 23.0, 51.0)) == "about 35 min (20–55)"
    assert display_range(Estimate(2.0, 0.0, 4.0)) == "less than 5 min"
    assert display_range(Estimate(3.0, 1.0, 12.0)) == "about 5 min (0–15)"


def test_fallback_model_is_used_without_artifacts(tmp_path):
    model = get_wait_model(tmp_path)
    try:
        assert isinstance(model, FallbackModel)
    finally:
        get_wait_model(ARTIFACT_DIR)


def test_trained_artifacts_load():
    model = LightGbmModel(ARTIFACT_DIR)
    assert model.version.startswith("lgbm-v1-") and model.doctor_avg("Dr. Suresh Pawar")
