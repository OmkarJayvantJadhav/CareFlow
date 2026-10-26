"""The evaluation machinery itself: write matching, the baseline mode, the scenario file."""

import json
from collections import Counter

from sqlalchemy import func, select

from app.agent.chat import handle_chat
from app.agent.llm import ScriptedLLM
from app.db.models import Appointment
from app.tools.booking import book_appointment
from eval.baseline import baseline_mode
from eval.run_agent import assign, describe, matches
from tests.conftest import NOW, SATURDAY
from tests.test_agent import booking_script

SPEC = {"tool": ["book_appointment"], "patient": "Asha Patil", "doctors": ["Dr. Anand Kulkarni"],
        "dates": [SATURDAY.isoformat()], "time_from": "09:00", "time_to": "10:00"}  # fmt: skip


def test_write_matching_checks_every_constraint():
    info = {"tool": "book_appointment", "patient": "Asha Patil", "doctor": "Dr. Anand Kulkarni",
            "date": SATURDAY.isoformat(), "time": "09:15"}  # fmt: skip
    assert matches(info, SPEC, {})
    assert not matches({**info, "time": "10:15"}, SPEC, {})
    assert not matches({**info, "doctor": "Dr. Meera Iyer"}, SPEC, {})
    assert not matches({**info, "tool": "reschedule_appointment"}, SPEC, {})
    unexpected, missing = assign([info, {**info, "time": "11:00"}], [SPEC], {})
    assert len(unexpected) == 1 and not missing
    unexpected, missing = assign([], [SPEC], {})
    assert not unexpected and missing == [SPEC]


def test_describe_reads_the_slot_of_a_booking(world):
    kulkarni = world.doctor("Dr. Anand Kulkarni")
    slot = world.slots(kulkarni, SATURDAY)[1]
    info = describe(world.db, "book_appointment", {"patient_id": world.asha.patient_id, "slot_id": slot.id})
    assert info == {"tool": "book_appointment", "appointment_id": None, "doctor": "Dr. Anand Kulkarni",
                    "date": SATURDAY.isoformat(), "time": "09:15", "patient": "Asha Patil"}  # fmt: skip
    appt = book_appointment(world.db, world.staff, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    cancel = describe(world.db, "cancel_appointment", {"appointment_id": appt["appointment_id"]})
    assert cancel["time"] == "09:15" and cancel["patient"] == "Asha Patil"


def test_baseline_mode_writes_without_a_confirmation_card(world, kb):
    world.slots(world.doctor("Dr. Anand Kulkarni"), SATURDAY)
    world.db.commit()
    llm = ScriptedLLM([*booking_script(world.asha.patient_id), lambda m: "Booked."])
    with baseline_mode():
        reply = handle_chat(world.db, world.asha, "s", "Book a Marathi cardiologist on Saturday", llm, now=NOW)
    assert reply.confirmation is None
    assert world.db.scalar(select(func.count()).select_from(Appointment)) == 1
    # Outside the context manager the safeguards are back: the same request only shows a card.
    world.db.rollback()
    llm = ScriptedLLM(booking_script(world.asha.patient_id))
    reply = handle_chat(world.db, world.asha, "s2", "Book a Marathi cardiologist on Saturday", llm, now=NOW)
    assert reply.confirmation is not None


def test_scenario_file_has_the_documented_families():
    rows = [json.loads(line) for line in open("eval/datasets/agent_scenarios.jsonl", encoding="utf-8")]
    assert len(rows) == 130 and len({r["id"] for r in rows}) == 130
    assert Counter(r["family"] for r in rows) == {
        "book": 25, "reschedule": 15, "cancel": 15, "waiting_list": 10, "caregiver": 10,
        "doctor_unavailable": 10, "queue": 10, "conflict": 15, "out_of_scope": 10, "queue_action": 10,
    }  # fmt: skip
    assert [r["family"] for r in rows[-10:]] == ["queue_action"] * 10  # appended: earlier ids keep their place


def test_rag_answer_records_the_sources_the_model_saw(world, kb):
    from eval.rag_answers import _parse, answer_one

    world.db.commit()
    llm = ScriptedLLM(
        [lambda m: {"search_knowledge": {"query": "lipid profile fasting"}}, lambda m: "Yes, fast for 10-12 hours [1]."]
    )
    out = answer_one({"id": "t1", "question": "Do I need to fast before a lipid profile?", "language": "en"}, llm)
    assert out["searched"] and out["reply"].endswith("[1].") and not out["grounding_guard"]
    assert out["sources"].startswith("[1] ") and "ipid" in out["sources"]
    assert _parse('Sure: {"correct": "yes", "faithful": "yes", "declined": "no"}')["correct"] == "yes"
    assert _parse("not json") == {}
