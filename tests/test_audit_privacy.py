"""TC-16 (audit rows with masked arguments), TC-18 (no unmasked phone numbers), append-only tables."""

import logging
import re

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.models import AuditLog, Notification, Patient
from app.queue import engine
from app.safety.privacy import MaskingFilter, install_log_masking, mask_payload, mask_phone_number, mask_text
from app.tools.booking import book_appointment, cancel_appointment, reschedule_appointment
from app.tools.waiting_list import join_waiting_list
from tests.conftest import NOW, SATURDAY, TODAY

UNMASKED = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)|[6-9]\d{4}[\s-]\d{5}")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("call me on 9876543210", "call me on +91 98XXXXXX10"),
        ("+91 98765 43210 is mine", "+91 98XXXXXX10 is mine"),
        ("+91-9876543210", "+91 98XXXXXX10"),
        ("09876543210", "+91 98XXXXXX10"),
        ("919876543210", "+91 98XXXXXX10"),
        ("two: 9876543210, 7012345678", "two: +91 98XXXXXX10, +91 70XXXXXX78"),
    ],
)
def test_mask_text(raw, expected):
    assert mask_text(raw) == expected


def test_mask_leaves_other_numbers_alone():
    for value in ("slot 1234567890", "2026-10-19 09:30", "token B07", "+91 98XXXXXX10", "12345"):
        assert mask_text(value) == value


def test_mask_payload_is_recursive():
    data = {"phone": "9876543210", "nested": [{"note": "reach 8123456789"}], "n": 5}
    assert mask_payload(data) == {"phone": "+91 98XXXXXX10", "nested": [{"note": "reach +91 81XXXXXX89"}], "n": 5}


def test_mask_phone_number_rejects_bad_input():
    with pytest.raises(ValueError):
        mask_phone_number("12345")


def test_logging_filter_masks_messages():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "patient %s phoned from %s", ("A", "9876543210"), None)
    MaskingFilter().filter(record)
    assert record.getMessage() == "patient A phoned from +91 98XXXXXX10"
    template = logging.LogRecord("t", logging.INFO, __file__, 1, "call 9876543210 now", None, None)
    MaskingFilter().filter(template)
    assert template.getMessage() == "call +91 98XXXXXX10 now"


def test_logging_filter_keeps_args_for_access_log_formatters():
    """Uvicorn's access formatter unpacks record.args; masking must keep it a tuple."""
    from uvicorn.logging import AccessFormatter

    args = ("127.0.0.1:5000", "GET", "/api/v1/health?phone=9876543210", "1.1", 200)
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', args, None)
    MaskingFilter().filter(record)
    line = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False).format(record)
    assert line == '127.0.0.1:5000 - "GET /api/v1/health?phone=+91 98XXXXXX10 HTTP/1.1" 200 OK'


def test_database_refuses_unmasked_phone(world):
    world.db.add(Patient(synthetic_name="X", birth_year=1990, phone_masked="9876543210", preferred_language="en"))
    with pytest.raises(IntegrityError):
        world.db.flush()


def test_tc16_every_write_tool_writes_an_audit_row(world):
    db, staff, asha = world.db, world.staff, world.asha
    slots = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    appt = book_appointment(db, asha, asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    reschedule_appointment(db, asha, appt["appointment_id"], slots[2].id, confirmed=True, now=NOW)
    cancel_appointment(db, asha, appt["appointment_id"], confirmed=True, now=NOW)
    others = world.other_patients(len(slots) + 1)
    for p, s in zip(others, slots, strict=False):
        book_appointment(db, staff, p, s.id, confirmed=True, now=NOW)
    join_waiting_list(db, asha, asha.patient_id, slots[0].doctor_id, [SATURDAY], confirmed=True, now=NOW)
    pawar = world.doctor("Dr. Suresh Pawar")
    world.slots(pawar, TODAY)
    walk = engine.register_walk_in(db, staff, pawar.id, name="Ravi Test", birth_year=1970, phone="98765 43210", now=NOW)
    engine.set_priority(db, staff, walk["entry_id"], 1, now=NOW)
    engine.record_doctor_event(db, staff, walk["session_id"], "delay", minutes=10, now=NOW)
    db.commit()

    tools = set(db.scalars(select(AuditLog.tool)))
    assert {
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "join_waiting_list",
        "register_walk_in",
        "set_priority",
        "record_doctor_event",
    } <= tools
    walk_row = db.scalars(select(AuditLog).where(AuditLog.tool == "register_walk_in")).one()
    assert walk_row.arguments["phone"] == "+91 98XXXXXX10"
    assert walk_row.user_id == staff.user_id and walk_row.role == "staff"


def test_tc18_no_unmasked_phone_in_logs_or_stored_records(world, caplog):
    db, staff = world.db, world.staff
    pawar = world.doctor("Dr. Suresh Pawar")
    world.slots(pawar, TODAY)
    install_log_masking()
    logger = logging.getLogger("careflow.test")
    with caplog.at_level(logging.INFO):
        entry = engine.register_walk_in(db, staff, pawar.id, name="Meena", birth_year=1985, phone="9123456780", now=NOW)
        logger.info("registered walk-in %s with phone %s", entry["token"], "9123456780")
        engine.record_doctor_event(db, staff, entry["session_id"], "unavailable", reason="call 9123456780", now=NOW)
    db.commit()
    assert "9123456780" not in caplog.text and "+91 91XXXXXX80" in caplog.text
    dumps = [
        str(row)
        for table in ("audit_log", "notification", "patient", "queue_event")
        for row in db.execute(text(f"SELECT * FROM {table}")).all()
    ]
    assert dumps and not any(UNMASKED.search(d) for d in dumps)
    assert db.scalars(select(Notification)).first() is not None


@pytest.mark.parametrize("statement", ["UPDATE audit_log SET tool = 'x'", "DELETE FROM audit_log"])
def test_audit_log_is_append_only(world, statement):
    slot = world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)[0]
    book_appointment(world.db, world.asha, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        world.db.execute(text(statement))
        world.db.flush()
    world.db.rollback()


def test_queue_event_is_append_only(world):
    pawar = world.doctor("Dr. Suresh Pawar")
    engine.register_walk_in(world.db, world.staff, pawar.id, patient_id=world.other_patients(1)[0], now=NOW)
    world.db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        world.db.execute(text("UPDATE queue_event SET type = 'break'"))
    world.db.rollback()
