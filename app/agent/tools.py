"""Tools the agent can call (docs §7, agent tool contracts).

Each tool has a pydantic argument model (validated before anything runs), a
JSON schema for the LLM, and an executor that calls the same service functions
as the REST API. Results are compacted to keep prompts inside the token budget.

Write tools are never executed directly by the LLM: the agent runs a *preview*
(the real tool in a savepoint that is rolled back) and turns it into a
confirmation card. Only after the user confirms that exact card does the chat
layer execute it with ``confirmed=True``. ``confirmed`` is therefore not part
of any schema the LLM sees; an extra ``confirmed`` argument is ignored.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.agent.messages import display_date
from app.agent.tracing import Trace
from app.db.models import Appointment, Doctor, Patient
from app.queue import engine as queue_engine
from app.rag.retriever import get_retriever
from app.safety.injection import neutralize
from app.timeutil import to_ist
from app.tools import booking, handoff, policy, waiting_list
from app.tools.errors import ToolError
from app.tools.permissions import Actor
from app.tools.vocab import parse_day

CONFIRMATION_TTL = timedelta(minutes=5)
MAX_SLOTS_SHOWN = 12
MAX_SOURCE_CHARS = 700
WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class ToolContext:
    db: Session
    actor: Actor
    now: datetime
    language: str
    conversation_id: str
    trace: Trace
    patients: dict[int, str] = field(default_factory=dict)
    sources: list = field(default_factory=list)
    knowledge_calls: int = 0
    knowledge_hits: int = 0
    pending: dict | None = None
    emergency: bool = False
    handoff_ticket_id: int | None = None


class Args(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class SearchKnowledgeArgs(Args):
    query: str = Field(min_length=2, max_length=300, description="What to look up, as a short search query")
    collection: Literal["policies", "insurance", "departments", "doctors", "test_preparation", "facilities"] | None = (
        None
    )
    language: Literal["en", "hi", "mr"] | None = None


class SearchDoctorsArgs(Args):
    specialty: str | None = Field(None, max_length=60, description="Department or specialty, e.g. cardiology, ENT")
    language: str | None = Field(None, max_length=20, description="Language the doctor speaks: en, hi or mr")
    day: str | None = Field(None, max_length=20, description="Weekday name, 'today', 'tomorrow' or YYYY-MM-DD")


class CheckAvailabilityArgs(Args):
    doctor_id: int = Field(gt=0)
    date: str = Field(max_length=20, description="YYYY-MM-DD, a weekday name, 'today' or 'tomorrow'")


class BookArgs(Args):
    patient_id: int = Field(gt=0)
    slot_id: int = Field(gt=0)


class RescheduleArgs(Args):
    appointment_id: int = Field(gt=0)
    new_slot_id: int = Field(gt=0)


class CancelArgs(Args):
    appointment_id: int = Field(gt=0)


class WaitingListArgs(Args):
    patient_id: int = Field(gt=0)
    doctor_id: int = Field(gt=0)
    dates: list[str] = Field(min_length=1, max_length=7, description="Preferred dates, YYYY-MM-DD")


class PatientArgs(Args):
    patient_id: int = Field(gt=0)


class QueueStatusArgs(Args):
    entry_id: int | None = Field(None, gt=0, description="Leave out to list the user's queue entries for today")


class EntryArgs(Args):
    entry_id: int = Field(gt=0)


class EmergencyArgs(Args):
    language: Literal["en", "hi", "mr"] | None = None


class HandoffArgs(Args):
    reason: Literal["user_request", "out_of_scope", "other"] = "user_request"
    note: str = Field("", max_length=300)


@dataclass
class ToolSpec:
    name: str
    description: str
    args: type[Args]
    kind: Literal["read", "write", "special"]
    run: Callable[[ToolContext, Any], dict]
    label: str  # plain-words progress line for the UI ("Checking available slots…")

    def schema(self) -> dict:
        params = _simplify(self.args.model_json_schema())
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": params},
        }


# Validation keywords stay enforced by pydantic; the LLM only needs types, enums and descriptions.
_DROP_KEYS = {"title", "default", "exclusiveMinimum", "minLength", "maxLength", "minItems", "maxItems"}


def _simplify(node: Any) -> Any:
    if isinstance(node, dict):
        options = node.get("anyOf")
        if options and len(options) == 2 and {"type": "null"} in options:
            merged = {
                **next(o for o in options if o != {"type": "null"}),
                **{k: v for k, v in node.items() if k != "anyOf"},
            }
            return _simplify(merged)
        return {k: _simplify(v) for k, v in node.items() if k not in _DROP_KEYS}
    if isinstance(node, list):
        return [_simplify(v) for v in node]
    return node


# --------------------------------------------------------------------------- compact views


def _doctor_view(d: dict) -> dict:
    return {
        "doctor_id": d["doctor_id"],
        "name": d["name"],
        "department": d["department"],
        "languages": d["languages"],
        "opd_days": [WEEKDAY_ABBR[i - 1] for i in d["opd_days"]],
    }


def _appointment_view(a: dict) -> dict:
    return {k: a[k] for k in ("appointment_id", "patient_name", "doctor_name", "department", "date", "time", "status")}


def _resolve_date(value: str, now: datetime) -> date:
    return parse_day(value, now)[1]


# --------------------------------------------------------------------------- read tools


def run_search_knowledge(ctx: ToolContext, args: SearchKnowledgeArgs) -> dict:
    ctx.knowledge_calls += 1
    retriever = get_retriever(ctx.db)
    chunks = retriever.search(ctx.db, args.query, collection=args.collection, language=args.language or ctx.language)
    sources, flagged = [], 0
    for chunk in chunks:
        text, removed = neutralize(chunk.text)
        flagged += removed
        ctx.sources.append(chunk)
        sources.append(
            {"ref": len(ctx.sources), "title": chunk.title, "section": chunk.section, "text": text[:MAX_SOURCE_CHARS]}
        )
    if flagged:
        ctx.trace.span("injection_removed", chunks=flagged)
    if not sources:
        return {"sources": [], "note": "No relevant hospital document was found for this question."}
    ctx.knowledge_hits += 1
    return {"sources": sources, "instruction": "Answer only from these sources and cite them like [1]."}


def run_search_doctors(ctx: ToolContext, args: SearchDoctorsArgs) -> dict:
    result = booking.search_doctors(ctx.db, args.specialty, args.language, args.day, now=ctx.now)
    return {"criteria": result["criteria"], "doctors": [_doctor_view(d) for d in result["doctors"]]}


def run_check_availability(ctx: ToolContext, args: CheckAvailabilityArgs) -> dict:
    patient_id = next(iter(ctx.patients), None) if len(ctx.patients) == 1 else None
    result = booking.check_availability(
        ctx.db, args.doctor_id, _resolve_date(args.date, ctx.now), patient_id=patient_id, now=ctx.now
    )
    slots = result["slots"]
    out = {
        "doctor": result["doctor"]["name"],
        "doctor_id": args.doctor_id,
        "date": result["date"],
        "works_that_day": result["works_that_day"],
        "slots": [{"slot_id": s["slot_id"], "time": s["time"]} for s in slots[:MAX_SLOTS_SHOWN]],
    }
    if len(slots) > MAX_SLOTS_SHOWN:
        out["more_slots"] = len(slots) - MAX_SLOTS_SHOWN
    if result.get("outside_booking_window"):
        out["note"] = f"Bookings are possible only from today up to {policy.BOOKING_HORIZON.days} days ahead."
    elif result["works_that_day"] and not slots:
        out["note"] = "No free slot on this date; the patient can join the waiting list."
    return out


def run_get_patient_appointments(ctx: ToolContext, args: PatientArgs) -> dict:
    result = booking.get_patient_appointments(ctx.db, ctx.actor, args.patient_id, now=ctx.now)
    return {
        "patient": result["patient_name"],
        "upcoming": [_appointment_view(a) for a in result["upcoming"]],
        "past": [_appointment_view(a) for a in result["past"][:5]],
    }


def _queue_view(status: dict) -> dict:
    estimate = status.get("estimate") or {}
    return {
        "entry_id": status["entry_id"],
        "token": status["token"],
        "doctor": status["doctor_name"],
        "status": status["status"],
        "position": status["position"],
        "people_ahead": status["ahead"],
        "wait": estimate.get("display"),
        "doctor_status": status["doctor_status"],
    }


def run_get_queue_status(ctx: ToolContext, args: QueueStatusArgs) -> dict:
    if args.entry_id is not None:
        return _queue_view(queue_engine.get_queue_status(ctx.db, ctx.actor, args.entry_id, now=ctx.now))
    entries = queue_engine.active_entries_for(ctx.db, ctx.actor, ctx.now)
    if not entries:
        return {"entries": [], "note": "No one is checked in today; check in at the reception desk first."}
    return {"entries": [{**_queue_view(e), "patient": e["patient_name"]} for e in entries]}


def run_predict_wait_time(ctx: ToolContext, args: EntryArgs) -> dict:
    status = queue_engine.get_queue_status(ctx.db, ctx.actor, args.entry_id, now=ctx.now)
    estimate = status.get("estimate")
    if not estimate:
        return {
            "entry_id": args.entry_id,
            "status": status["status"],
            "note": "No estimate: the patient is not waiting.",
        }
    return {
        "entry_id": args.entry_id,
        "estimate_min": estimate["predicted_min"],
        "range_min": [estimate["low_min"], estimate["high_min"]],
        "say": estimate["display"],
        "doctor_status": status["doctor_status"],
    }


# --------------------------------------------------------------------------- write tools (preview -> card)


def _preview(ctx: ToolContext, fn: Callable[[], dict]) -> dict:
    """Run a write in a savepoint and roll it back: the exact checks, no changes."""
    savepoint = ctx.db.begin_nested()
    try:
        return fn()
    finally:
        savepoint.rollback()


def _card(ctx: ToolContext, tool: str, args: dict, summary: dict) -> dict:
    pending = {
        "action_id": uuid.uuid4().hex,
        "tool": tool,
        "args": args,
        "summary": summary,
        "language": ctx.language,
        "created_at": ctx.now.isoformat(),
        "expires_at": (ctx.now + CONFIRMATION_TTL).isoformat(),
    }
    ctx.pending = pending
    return {"status": "awaiting_confirmation", "summary": summary, "note": "A confirmation card is shown to the user."}


def _appointment_summary(a: dict, lang: str) -> dict:
    return {
        "patient": a["patient_name"],
        "doctor": a["doctor_name"],
        "department": a["department"],
        "date": display_date(date.fromisoformat(a["date"]), lang),
        "time": a["time"],
    }


def _current_appointment(db: Session, appointment_id: int) -> dict:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise ToolError("NOT_FOUND", f"Appointment {appointment_id} does not exist.")
    return {
        "patient_name": appt.patient.synthetic_name,
        "doctor_name": appt.doctor.name,
        "department": appt.doctor.department.name,
        "date": appt.appt_date.isoformat(),
        "time": to_ist(appt.slot.start_at).strftime("%H:%M"),
    }


def run_book(ctx: ToolContext, args: BookArgs) -> dict:
    preview = _preview(
        ctx,
        lambda: booking.book_appointment(ctx.db, ctx.actor, args.patient_id, args.slot_id, confirmed=True, now=ctx.now),
    )
    summary = _appointment_summary(preview, ctx.language)
    summary["cancellation_policy"] = policy.CANCEL_POLICY
    return _card(ctx, "book_appointment", args.model_dump(), summary)


def run_reschedule(ctx: ToolContext, args: RescheduleArgs) -> dict:
    preview = _preview(
        ctx,
        lambda: booking.reschedule_appointment(
            ctx.db, ctx.actor, args.appointment_id, args.new_slot_id, confirmed=True, now=ctx.now
        ),
    )
    old = _current_appointment(ctx.db, args.appointment_id)
    summary = _appointment_summary(preview, ctx.language)
    summary.update(
        old_doctor=old["doctor_name"],
        old_date=display_date(date.fromisoformat(old["date"]), ctx.language),
        old_time=old["time"],
    )
    return _card(ctx, "reschedule_appointment", args.model_dump(), summary)


def run_cancel(ctx: ToolContext, args: CancelArgs) -> dict:
    old = _current_appointment(ctx.db, args.appointment_id)
    _preview(
        ctx, lambda: booking.cancel_appointment(ctx.db, ctx.actor, args.appointment_id, confirmed=True, now=ctx.now)
    )
    summary = _appointment_summary(old, ctx.language)
    summary["cancellation_policy"] = policy.CANCEL_POLICY
    return _card(ctx, "cancel_appointment", args.model_dump(), summary)


def run_join_waiting_list(ctx: ToolContext, args: WaitingListArgs) -> dict:
    dates = [_resolve_date(d, ctx.now).isoformat() for d in args.dates]
    _preview(
        ctx,
        lambda: waiting_list.join_waiting_list(
            ctx.db, ctx.actor, args.patient_id, args.doctor_id, dates, confirmed=True, now=ctx.now
        ),
    )
    doctor = ctx.db.get(Doctor, args.doctor_id)
    patient = ctx.db.get(Patient, args.patient_id)
    summary = {
        "patient": patient.synthetic_name,
        "doctor": doctor.name,
        "department": doctor.department.name,
        "dates": ", ".join(display_date(date.fromisoformat(d), ctx.language) for d in dates),
    }
    return _card(ctx, "join_waiting_list", {**args.model_dump(), "dates": dates}, summary)


def execute_confirmed(db: Session, actor: Actor, pending: dict, now: datetime) -> dict:
    """Run the confirmed card's action for real (called by the chat layer, never by the LLM)."""
    tool, args = pending["tool"], pending["args"]
    if tool == "book_appointment":
        return booking.book_appointment(db, actor, args["patient_id"], args["slot_id"], confirmed=True, now=now)
    if tool == "reschedule_appointment":
        return booking.reschedule_appointment(
            db, actor, args["appointment_id"], args["new_slot_id"], confirmed=True, now=now
        )
    if tool == "cancel_appointment":
        before = _current_appointment(db, args["appointment_id"])
        return {**booking.cancel_appointment(db, actor, args["appointment_id"], confirmed=True, now=now), **before}
    if tool == "join_waiting_list":
        return waiting_list.join_waiting_list(
            db, actor, args["patient_id"], args["doctor_id"], args["dates"], confirmed=True, now=now
        )
    raise ToolError("VALIDATION_ERROR", f"Unknown action {tool}.")


# --------------------------------------------------------------------------- special tools


def run_emergency(ctx: ToolContext, args: EmergencyArgs) -> dict:
    ctx.emergency = True
    ctx.pending = None
    return {"status": "emergency guidance shown to the user"}


def run_handoff(ctx: ToolContext, args: HandoffArgs) -> dict:
    ticket = handoff.handoff_to_human(ctx.db, ctx.actor, ctx.conversation_id, args.reason, args.note, now=ctx.now)
    ctx.handoff_ticket_id = ticket["ticket_id"]
    return ticket


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            "search_knowledge",
            "Search the hospital's approved documents (policies, insurance and schemes, departments, doctors, test "
            "preparation, facilities). Use for any policy or preparation question.",
            SearchKnowledgeArgs, "read", run_search_knowledge, "Looking this up in the hospital's documents",
        ),
        ToolSpec(
            "search_doctors",
            "Find doctors by specialty, spoken language and OPD day.",
            SearchDoctorsArgs, "read", run_search_doctors, "Finding doctors",
        ),
        ToolSpec(
            "check_availability",
            "List free appointment slots for a doctor on a date.",
            CheckAvailabilityArgs, "read", run_check_availability, "Checking available slots",
        ),
        ToolSpec(
            "get_patient_appointments",
            "Show a patient's upcoming and past appointments.",
            PatientArgs, "read", run_get_patient_appointments, "Looking up appointments",
        ),
        ToolSpec(
            "get_queue_status",
            "Today's queue position, people ahead and wait estimate for the user's checked-in patients.",
            QueueStatusArgs, "read", run_get_queue_status, "Checking the queue",
        ),
        ToolSpec(
            "predict_wait_time",
            "Wait estimate with a low-high range for one queue entry. Always give the range, not a single number.",
            EntryArgs, "read", run_predict_wait_time, "Estimating the wait",
        ),
        ToolSpec(
            "book_appointment",
            "Request booking a slot for a patient. The user is then asked to confirm a card; nothing is booked until they do.",
            BookArgs, "write", run_book, "Preparing the booking",
        ),
        ToolSpec(
            "reschedule_appointment",
            "Request moving an appointment to another free slot in the same department; the user confirms a card.",
            RescheduleArgs, "write", run_reschedule, "Preparing the change",
        ),
        ToolSpec(
            "cancel_appointment",
            "Request cancelling an appointment; the user confirms a card.",
            CancelArgs, "write", run_cancel, "Preparing the cancellation",
        ),
        ToolSpec(
            "join_waiting_list",
            "Request adding a patient to a doctor's waiting list when no slot is free on the wanted dates; the user confirms a card.",
            WaitingListArgs, "write", run_join_waiting_list, "Preparing the waiting-list request",
        ),
        ToolSpec(
            "emergency_redirect",
            "Show emergency guidance when the user describes a medical emergency. No booking happens after this.",
            EmergencyArgs, "special", run_emergency, "Showing emergency guidance",
        ),
        ToolSpec(
            "handoff_to_human",
            "Create a ticket so a staff member contacts the user: when they ask for a person, or the request is out of scope.",
            HandoffArgs, "special", run_handoff, "Connecting you to a person",
        ),
    ]
}  # fmt: skip

PATIENT_TOOLS = list(TOOLS)


def tool_schemas(role: str) -> list[dict]:
    """Only the tools relevant to the user's role are sent, which also saves tokens (docs §12)."""
    names = PATIENT_TOOLS if role in ("patient", "caregiver") else []
    return [TOOLS[n].schema() for n in names]


def run_tool(ctx: ToolContext, name: str, arguments: dict | None, parse_error: str | None) -> tuple[dict, bool]:
    """Validate and run one tool call. Returns (result for the LLM, ok)."""
    spec = TOOLS.get(name)
    if spec is None or name not in PATIENT_TOOLS:
        return {"error": {"code": "UNKNOWN_TOOL", "message": f"There is no tool called {name!r}."}}, False
    if parse_error:
        return {"error": {"code": "VALIDATION_ERROR", "message": parse_error}}, False
    try:
        args = spec.args.model_validate(arguments or {})
    except ValidationError as err:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()[:3])
        return {"error": {"code": "VALIDATION_ERROR", "message": problems}}, False
    if spec.kind == "write" and ctx.pending is not None:
        return {
            "error": {"code": "ONE_CHANGE_AT_A_TIME", "message": "Only one change can be confirmed at a time."}
        }, False
    try:
        return spec.run(ctx, args), True
    except ToolError as err:
        return {"error": err.to_dict()}, False


def dumps(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
