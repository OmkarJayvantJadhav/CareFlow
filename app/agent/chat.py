"""One chat turn: safety gate, confirmation handling, the agent loop, persistence.

Order of checks for every patient message:

1. input validation;
2. emergency check (FR-02) - an emergency gets fixed guidance, any pending
   confirmation card is dropped and nothing is written (FR-03);
3. an explicit request for a person creates a handoff ticket (FR-06);
4. a pending confirmation card is confirmed, declined or dropped - a change
   is executed only here, after an explicit yes to that exact card (FR-09);
5. otherwise the agent loop runs; three failed turns in a row hand over to a person.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.confirm import is_affirmative, is_negative
from app.agent.llm import LLM, LLMUnavailable
from app.agent.loop import Agent, TurnResult
from app.agent.messages import message
from app.agent.prompts import PROMPT_VERSION, system_prompt
from app.agent.tools import ToolContext, dumps, execute_confirmed
from app.agent.tracing import Trace
from app.config import get_settings
from app.db.models import Appointment, AppUser, Conversation, Patient
from app.rag.text import normalize
from app.safety.emergency import check_emergency
from app.safety.language import detect_language
from app.timeutil import resolve_now, to_ist
from app.tools import policy
from app.tools.errors import ToolError
from app.tools.handoff import handoff_to_human
from app.tools.hospital import hospital_name, message_values
from app.tools.permissions import Actor, linked_patient_ids

FULL_TURNS = 2
TEXT_TURNS = 6
MAX_FAILED_ATTEMPTS = 3
SUMMARY_CHARS = 1200

_HANDOFF_REQUEST = re.compile(
    normalize(
        r"\b(talk|speak|chat) (to|with) (a |an |some )?(real )?(person|human|someone|agent|staff|receptionist|representative)\b"
        r"|\breal person\b|\bhuman agent\b|\bcustomer care\b|\bconnect me to (a |an )?(person|human|agent)"
        r"|(किसी )?(इंसान|व्यक्ति|आदमी) से बात|किसी से बात करनी|माणसाशी बोल|व्यक्तीशी बोल|कोणाशी तरी बोल"
        r"|insaan se baat|kisi se baat|manasashi bol"
    )
)


@dataclass
class ChatReply:
    conversation_id: str
    reply: str
    language: str
    citations: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    needs_confirmation: bool = False
    confirmation: dict | None = None
    handoff: bool = False
    ticket_id: int | None = None
    emergency: bool = False
    offer_handoff: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def session_message_count(db: Session, session_id: str) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Conversation.message_count), 0)).where(Conversation.session_id == session_id)
        )
    )


def actor_patients(db: Session, actor: Actor) -> dict[int, str]:
    if actor.role == "patient" and actor.patient_id:
        ids = [actor.patient_id]
    elif actor.role == "caregiver":
        ids = sorted(linked_patient_ids(db, actor))
    else:
        ids = []
    return {pid: db.get(Patient, pid).synthetic_name for pid in ids}


def displaced_notes(db: Session, patients: dict[int, str], now: datetime) -> list[str]:
    """FR-27: appointments the hospital cancelled because the doctor is unavailable are offered for rebooking."""
    if not patients:
        return []
    rows = db.scalars(
        select(Appointment).where(
            Appointment.patient_id.in_(list(patients)),
            Appointment.status == "displaced",
            Appointment.appt_date >= to_ist(now).date(),
        )
    ).all()
    return [
        f"Note: {patients[a.patient_id]}'s appointment {a.id} with {a.doctor.name} on {a.appt_date.isoformat()} was "
        "cancelled by the hospital because the doctor is unavailable. Tell the user and offer a new slot "
        "(same department; rescheduling is free and allowed now)."
        for a in rows
    ]


def _load_conversation(
    db: Session, actor: Actor, conversation_id: str | None, session_id: str, language: str
) -> Conversation:
    if conversation_id:
        conv = db.scalars(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if conv is None or conv.user_id != actor.user_id:
            raise ToolError("NOT_FOUND", "Conversation not found.")
        return conv
    conv = Conversation(
        id=uuid.uuid4().hex, user_id=actor.user_id, session_id=session_id, language=language, history=[], summary=""
    )
    db.add(conv)
    db.flush()
    return conv


def _history_messages(conv: Conversation) -> list[dict]:
    """Last turns in full, earlier ones as plain text; anything older lives in the summary."""
    turns = conv.history[-TEXT_TURNS:]
    out: list[dict] = []
    for i, turn in enumerate(turns):
        msgs = turn["messages"]
        if i >= len(turns) - FULL_TURNS:
            out.extend(msgs)
        else:
            out.extend([msgs[0], msgs[-1]])
    return out


def _summarise(turn: dict) -> str:
    user, reply = turn["messages"][0]["content"], turn["messages"][-1].get("content") or ""
    return f"User: {user[:120]} / Assistant: {reply[:120]}"


def _record_turn(conv: Conversation, messages: list[dict], now: datetime) -> None:
    history = list(conv.history) + [{"at": now.isoformat(), "messages": messages}]
    # Turns that leave the prompt window become one line of summary (docs §12).
    while len(history) > TEXT_TURNS:
        dropped = history.pop(0)
        conv.summary = (conv.summary + "\n" + _summarise(dropped)).strip()[-SUMMARY_CHARS:]
    conv.history = history
    conv.message_count += 1
    conv.updated_at = now


def _confirmation_card(pending: dict, now: datetime) -> dict:
    expires = datetime.fromisoformat(pending["expires_at"])
    return {
        "action_id": pending["action_id"],
        "tool": pending["tool"],
        "summary": pending["summary"],
        "expires_at": pending["expires_at"],
        # Relative, so a device whose clock is off still counts down correctly.
        "expires_in_seconds": max(0, int((expires - now).total_seconds())),
    }


def _alternatives_text(err: ToolError, lang: str) -> str:
    alternatives = err.details.get("alternatives") or []
    if not alternatives:
        return ""
    return message("alternatives", lang, times=", ".join(a["time"] for a in alternatives))


def _execute_card(
    db: Session, actor: Actor, conv: Conversation, pending: dict, lang: str, now: datetime
) -> tuple[str, dict, dict]:
    """Run a confirmed card. Returns (reply, action, tool result)."""
    tool = pending["tool"]
    try:
        result = execute_confirmed(db, actor, pending, now)
    except ToolError as err:
        result = {"error": err.to_dict()}
        if err.code == "SLOT_TAKEN":
            reply = message("slot_taken", lang, alternatives=_alternatives_text(err, lang))
        else:
            reply = message("action_failed", lang, reason=err.message)
        return reply, {"tool": tool, "ok": False, "error": err.code, "label": "Applying the change"}, result
    done_key = {
        "book_appointment": "done_book",
        "reschedule_appointment": "done_reschedule",
        "cancel_appointment": "done_cancel",
        "join_waiting_list": "done_waiting_list",
        "check_in": "done_check_in",
        "join_virtual_queue": "done_join_queue",
        "leave_queue": "done_leave_queue",
    }[tool]
    cancel_hours = int(policy.CANCEL_CUTOFF.total_seconds() // 3600)
    # The token is only known once the change is made.
    values = {**pending["summary"], "token": result.get("token", pending["summary"].get("token", ""))}
    reply = message(done_key, lang, cancel_hours=cancel_hours, **values)
    return reply, {"tool": tool, "ok": True, "label": "Applying the change"}, {"status": "done", **result}


def handle_chat(
    db: Session,
    actor: Actor,
    session_id: str,
    text: str,
    llm: LLM,
    conversation_id: str | None = None,
    confirm_action_id: str | None = None,
    language_hint: str | None = None,
    now: datetime | None = None,
) -> ChatReply:
    settings = get_settings()
    now = resolve_now(now)
    if actor.role not in ("patient", "caregiver"):
        raise ToolError("FORBIDDEN", "Chat is available to patients and caregivers.")
    text = (text or "").strip()
    if not text and not confirm_action_id:
        raise ToolError("VALIDATION_ERROR", "The message is empty.")
    if len(text) > settings.max_message_chars:
        raise ToolError("VALIDATION_ERROR", f"Messages can be at most {settings.max_message_chars} characters.")

    patients = actor_patients(db, actor)
    preferred = None
    if actor.patient_id:
        preferred = db.get(Patient, actor.patient_id).preferred_language
    hint = language_hint if language_hint in ("en", "hi", "mr") else preferred
    conv = _load_conversation(db, actor, conversation_id, session_id, hint or "en")
    short_reply = not text or is_affirmative(text) or is_negative(text)
    language = conv.language if (short_reply and conversation_id) else detect_language(text, hint or conv.language)
    conv.language = language
    user = db.get(AppUser, actor.user_id)
    trace = Trace(conv.id, actor.user_id, actor.role)
    user_message = {"role": "user", "content": text or "(confirmed with the button)"}

    def finish(reply: ChatReply, messages: list[dict], turn_type: str) -> ChatReply:
        _record_turn(conv, messages, now)
        db.flush()
        trace.finish(turn_type=turn_type, language=language, prompt_version=PROMPT_VERSION, emergency=reply.emergency,
                     actions=[a["tool"] for a in reply.actions], handoff=reply.handoff)  # fmt: skip
        return reply

    # 2. Emergency check, before any planning.
    if text:
        emergency = check_emergency(text)
        trace.span(
            "emergency_check", flagged=emergency.is_emergency, reason=emergency.reason, score=round(emergency.score, 3)
        )
        if emergency.is_emergency:
            conv.pending_action = None
            reply_text = message("emergency", language, **message_values(db, language))
            reply = ChatReply(conv.id, reply_text, language, emergency=True,
                              actions=[{"tool": "emergency_redirect", "ok": True, "label": "Showing emergency guidance"}])  # fmt: skip
            return finish(reply, [user_message, {"role": "assistant", "content": reply_text}], "emergency")

    # 3. Explicit request for a person.
    if text and _HANDOFF_REQUEST.search(normalize(text)):
        conv.pending_action = None
        ticket = handoff_to_human(db, actor, conv.id, "user_request", text[:200], now=now)
        conv.handoff_ticket_id = ticket["ticket_id"]
        reply_text = message("handoff", language, ticket_id=ticket["ticket_id"], **message_values(db, language))
        reply = ChatReply(conv.id, reply_text, language, handoff=True, ticket_id=ticket["ticket_id"],
                          actions=[{"tool": "handoff_to_human", "ok": True, "label": "Connecting you to a person"}])  # fmt: skip
        return finish(reply, [user_message, {"role": "assistant", "content": reply_text}], "handoff")

    # 4. A pending confirmation card.
    pending = conv.pending_action
    if confirm_action_id and (pending is None or confirm_action_id != pending["action_id"]):
        conv.pending_action = None
        reply_text = message("card_unknown", language)
        return finish(
            ChatReply(conv.id, reply_text, language),
            [user_message, {"role": "assistant", "content": reply_text}],
            "confirmation",
        )
    if pending is not None:
        if confirm_action_id or is_affirmative(text):
            conv.pending_action = None
            if now > datetime.fromisoformat(pending["expires_at"]):
                reply_text = message("card_expired", language)
                return finish(
                    ChatReply(conv.id, reply_text, language),
                    [user_message, {"role": "assistant", "content": reply_text}],
                    "confirmation",
                )
            reply_text, action, result = _execute_card(db, actor, conv, pending, language, now)
            trace.span(
                "tool",
                name=pending["tool"],
                arguments=pending["args"],
                ok=action["ok"],
                error=action.get("error"),
                confirmed=True,
            )
            call_id = f"confirmed_{pending['action_id'][:8]}"
            messages = [
                user_message,
                {"role": "assistant", "tool_calls": [{"id": call_id, "type": "function",
                    "function": {"name": pending["tool"], "arguments": json.dumps(pending["args"])}}]},
                {"role": "tool", "tool_call_id": call_id, "content": dumps(result)},
                {"role": "assistant", "content": reply_text},
            ]  # fmt: skip
            return finish(ChatReply(conv.id, reply_text, language, actions=[action]), messages, "confirmation")
        conv.pending_action = None
        if is_negative(text):
            reply_text = message("nothing_changed", language)
            return finish(
                ChatReply(conv.id, reply_text, language),
                [user_message, {"role": "assistant", "content": reply_text}],
                "confirmation",
            )

    # 5. The agent.
    ctx = ToolContext(db, actor, now, language, conv.id, trace, patients=patients)
    prompt = system_prompt(actor.role, user.display_name, patients, language, to_ist(now), hospital_name(db))
    for note in displaced_notes(db, patients, now):
        prompt += f"\n{note}"
    if conv.summary:
        prompt += f"\nEarlier in this conversation:\n{conv.summary}"
    try:
        result: TurnResult = Agent(llm).run(ctx, prompt, _history_messages(conv), text)
    except LLMUnavailable:
        trace.finish(turn_type="agent", language=language, error="llm_unavailable")
        raise ToolError(
            "LLM_UNAVAILABLE", "The assistant is temporarily unavailable. Please try again in a minute."
        ) from None

    reply = ChatReply(
        conv.id,
        result.reply,
        language,
        citations=result.citations,
        actions=result.actions,
        emergency=result.emergency,
        offer_handoff=result.offer_handoff,
    )
    if result.pending is not None:
        conv.pending_action = result.pending
        reply.needs_confirmation = True
        reply.confirmation = _confirmation_card(result.pending, now)
    if result.handoff_ticket_id is not None:
        conv.handoff_ticket_id = result.handoff_ticket_id
        reply.handoff, reply.ticket_id = True, result.handoff_ticket_id

    conv.failed_attempts = conv.failed_attempts + 1 if result.failed else 0
    messages = result.messages
    if conv.failed_attempts >= MAX_FAILED_ATTEMPTS:
        ticket = handoff_to_human(db, actor, conv.id, "repeated_failure", text[:200], now=now)
        conv.failed_attempts = 0
        conv.handoff_ticket_id = ticket["ticket_id"]
        reply.reply = message(
            "handoff_after_failures", language, ticket_id=ticket["ticket_id"], **message_values(db, language)
        )
        reply.handoff, reply.ticket_id = True, ticket["ticket_id"]
        reply.actions.append({"tool": "handoff_to_human", "ok": True, "label": "Connecting you to a person"})
        messages = messages[:-1] + [{"role": "assistant", "content": reply.reply}]
    return finish(reply, messages, "agent")
