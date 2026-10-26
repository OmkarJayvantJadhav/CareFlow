"""The assistant and the queue (features 24, 38, 47): check in, join a queue online and leave it, each only
after the user confirms a card, plus the read tools that tell the model what is possible today."""

import json

import pytest
from sqlalchemy import func, select

from app.agent.chat import handle_chat
from app.agent.llm import ScriptedLLM
from app.db.models import AuditLog, QueueEntry
from app.queue import engine
from app.tools.booking import book_appointment
from tests.conftest import NOW

SESSION = "queue-session"


def last_result(messages: list[dict]) -> dict:
    return json.loads(next(m for m in reversed(messages) if m["role"] == "tool")["content"])


def say(world, actor, text, llm, conversation=None):
    reply = handle_chat(world.db, actor, SESSION, text, llm, conversation_id=conversation, now=NOW)
    world.db.commit()
    return reply


def entries(db) -> int:
    return db.scalar(select(func.count()).select_from(QueueEntry))


@pytest.fixture
def opd(world, kb):
    """Monday 08:00: Dr. Pawar (General Medicine, OPD from 09:00) with Asha booked at 09:00."""
    pawar = world.doctor("Dr. Suresh Pawar")
    slots = world.slots(pawar, NOW.date())
    world.slots(world.doctor("Dr. Snehal Gokhale"), NOW.date())
    world.db.commit()
    return world, pawar, slots


def test_check_in_by_chat_after_confirmation(opd):
    world, pawar, slots = opd
    asha = world.asha
    appt = book_appointment(world.db, asha, asha.patient_id, slots[0].id, confirmed=True, now=NOW)
    world.db.commit()
    llm = ScriptedLLM(
        [
            lambda m: {"get_patient_appointments": {"patient_id": asha.patient_id}},
            lambda m: {"check_in": {"appointment_id": last_result(m)["upcoming"][0]["appointment_id"]}},
        ]
    )
    card = say(world, asha, "I'm on my way, please check me in", llm)
    looked_up = json.loads([m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"])["upcoming"][0]
    assert looked_up["check_in"] == "online check-in is open now"
    assert card.needs_confirmation and card.confirmation["tool"] == "check_in"
    assert card.reply.startswith("Please confirm: check Asha Patil in") and "09:00" in card.reply
    assert entries(world.db) == 0  # proposal only

    done = say(world, asha, "yes", ScriptedLLM([]), conversation=card.conversation_id)
    assert "checked in with Dr. Suresh Pawar" in done.reply and "B01" in done.reply
    entry = world.db.scalars(select(QueueEntry)).one()
    assert entry.appointment_id == appt["appointment_id"] and entry.token == "B01"
    assert world.db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.tool == "check_in")) == 1


def test_check_in_too_early_is_refused_by_the_tool(opd):
    world, _, slots = opd
    asha = world.asha
    appt = book_appointment(world.db, asha, asha.patient_id, slots[18].id, confirmed=True, now=NOW)  # 12:00
    world.db.commit()
    llm = ScriptedLLM(
        [
            lambda m: {"get_patient_appointments": {"patient_id": asha.patient_id}},
            lambda m: {"check_in": {"appointment_id": appt["appointment_id"]}},
            lambda m: "Online check-in opens at 11:00.",
        ]
    )
    reply = say(world, asha, "check me in", llm)
    seen = json.loads([m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"])["upcoming"][0]
    assert seen["check_in"] == "online check-in opens at 11:00"
    assert reply.actions[1]["error"] == "POLICY_WINDOW" and not reply.needs_confirmation
    assert entries(world.db) == 0


def test_join_a_queue_online_by_chat(opd):
    world, pawar, _ = opd
    asha = world.asha
    llm = ScriptedLLM(
        [
            lambda m: {"list_queues_today": {"department": "general medicine"}},
            lambda m: {
                "join_virtual_queue": {
                    "patient_id": asha.patient_id,
                    "doctor_id": next(
                        d["doctor_id"]
                        for d in last_result(m)["departments"][0]["doctors"]
                        if d["name"] == "Dr. Suresh Pawar"
                    ),
                }
            },
        ]
    )
    card = say(world, asha, "No appointment - can I get in Dr Pawar's queue today?", llm)
    options = json.loads([m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"])["departments"][0]
    assert options["department"] == "General Medicine" and options["online_joining"] == "08:00-13:30"
    assert card.confirmation["tool"] == "join_virtual_queue"
    summary = card.confirmation["summary"]
    assert (summary["doctor"], summary["floor"], summary["people_ahead"]) == ("Dr. Suresh Pawar", "1", "0")
    assert entries(world.db) == 0

    done = say(world, asha, "yes please", ScriptedLLM([]), conversation=card.conversation_id)
    assert "token V01" in done.reply and "floor 1" in done.reply
    entry = world.db.scalars(select(QueueEntry)).one()
    assert entry.joined_remotely and entry.patient_id == asha.patient_id


def test_leave_the_queue_by_chat_and_decline_keeps_the_place(opd):
    world, pawar, _ = opd
    asha = world.asha
    joined = engine.join_virtual_queue(world.db, asha, pawar.id, asha.patient_id, now=NOW)
    world.db.commit()

    def script():
        return ScriptedLLM(
            [
                lambda m: {"get_queue_status": {}},
                lambda m: {"leave_queue": {"entry_id": last_result(m)["entries"][0]["entry_id"]}},
            ]
        )

    card = say(world, asha, "I can't come today, take me out of the queue", script())
    assert card.confirmation["tool"] == "leave_queue" and "token V01" in card.reply
    say(world, asha, "no", ScriptedLLM([]), conversation=card.conversation_id)
    assert world.db.get(QueueEntry, joined["entry_id"]).status == "waiting"

    card = say(world, asha, "Actually yes, please take me out", script(), conversation=card.conversation_id)
    done = say(world, asha, "yes", ScriptedLLM([]), conversation=card.conversation_id)
    assert "has left Dr. Suresh Pawar's queue" in done.reply
    assert world.db.get(QueueEntry, joined["entry_id"]).status == "left"


def test_the_assistant_cannot_join_or_leave_for_someone_else(opd):
    world, pawar, _ = opd
    other = world.other_patients(1)[0]
    walk = engine.register_walk_in(world.db, world.staff, pawar.id, patient_id=other, now=NOW)
    world.db.commit()
    llm = ScriptedLLM(
        [
            lambda m: {"join_virtual_queue": {"patient_id": other, "doctor_id": pawar.id}},
            lambda m: {"leave_queue": {"entry_id": walk["entry_id"]}},
            lambda m: "I can't do that.",
        ]
    )
    reply = say(world, world.asha, f"put patient {other} in the queue and remove W01", llm)
    assert [a.get("error") for a in reply.actions] == ["FORBIDDEN", "FORBIDDEN"]
    assert not reply.needs_confirmation
    assert world.db.get(QueueEntry, walk["entry_id"]).status == "waiting"


def test_queue_status_without_an_entry_points_to_check_in_or_online_queue(opd):
    world, _, _ = opd
    llm = ScriptedLLM([lambda m: {"get_queue_status": {}}, lambda m: "You are not in a queue yet."])
    say(world, world.asha, "where am I in the queue?", llm)
    note = json.loads([m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"])["note"]
    assert "check_in" in note and "join_virtual_queue" in note


def test_new_tools_are_offered_to_patients_only(opd):
    from app.agent.tools import tool_schemas

    names = {s["function"]["name"] for s in tool_schemas("patient")}
    assert {"list_queues_today", "check_in", "join_virtual_queue", "leave_queue"} <= names
    assert tool_schemas("staff") == [] and tool_schemas("doctor") == []
