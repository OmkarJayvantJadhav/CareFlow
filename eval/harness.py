"""Drive real chat turns (``handle_chat``) and record what happened in them.

For every conversation it records each tool call the agent made (name,
arguments, ok, error code), every write that was actually executed (successful
audit rows), the replies, confirmation cards, emergency and handoff flags,
latency, tokens and cost (from the traces the chat layer writes anyway).
"""

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.agent.loop as loop_module
from app.agent import tracing
from app.agent.chat import handle_chat
from app.db.models import AppUser, AuditLog
from app.tools.errors import ToolError
from app.tools.permissions import Actor


@dataclass
class Turn:
    user: str
    reply: str
    language: str
    emergency: bool
    handoff: bool
    confirmation: dict | None
    actions: list[dict]
    citations: list[dict]
    latency_ms: float
    error: str | None = None
    conversation_id: str | None = None


@dataclass
class Conversation:
    turns: list[Turn] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    writes: list[dict] = field(default_factory=list)
    traces: list[dict] = field(default_factory=list)

    @property
    def replies(self) -> list[str]:
        return [t.reply for t in self.turns]

    @property
    def emergency(self) -> bool:
        return any(t.emergency for t in self.turns)

    def usage(self) -> dict:
        llm = [s for t in self.traces for s in t.get("spans", []) if s.get("kind") == "llm" and "prompt_tokens" in s]
        return {
            "llm_calls": len(llm),
            "prompt_tokens": sum(s["prompt_tokens"] for s in llm),
            "completion_tokens": sum(s["completion_tokens"] for s in llm),
            "cost_usd": round(sum(s.get("cost_usd", 0) for s in llm), 6),
            "llm_latency_ms": round(sum(s.get("latency_ms", 0) for s in llm), 1),
            "models": sorted({f"{s['provider']}:{s['model']}" for s in llm}),
        }


def actor_for(db: Session, username: str) -> Actor:
    return Actor.from_user(db.scalars(select(AppUser).where(AppUser.username == username)).one())


@contextmanager
def recording(conv: Conversation):
    """Record every tool call the agent makes and every trace the chat layer writes."""
    original_run_tool = loop_module.run_tool
    original_write = tracing.write_trace

    def run_tool(ctx, name, arguments, parse_error):
        result, ok = original_run_tool(ctx, name, arguments, parse_error)
        error = None if ok else (result.get("error") or {}).get("code")
        call = {"name": name, "arguments": arguments, "ok": ok, "error": error}
        if name == "search_knowledge" and ok:
            call["sources"] = result.get("sources", [])  # what the model saw, for faithfulness grading
        conv.tool_calls.append(call)
        return result, ok

    def write_trace(record):
        conv.traces.append(record)

    loop_module.run_tool = run_tool
    tracing.write_trace = write_trace
    try:
        yield
    finally:
        loop_module.run_tool = original_run_tool
        tracing.write_trace = original_write


def executed_writes(db: Session, after_id: int) -> list[dict]:
    rows = db.scalars(select(AuditLog).where(AuditLog.id > after_id).order_by(AuditLog.id)).all()
    return [{"tool": r.tool, "arguments": r.arguments, "result": r.result} for r in rows if r.result.get("ok", True)]


def last_audit_id(db: Session) -> int:
    return db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1)) or 0


def run_conversation(db: Session, actor: Actor, llm, now, next_message, max_turns: int = 8) -> Conversation:
    """``next_message(conv) -> str | None`` gives the user's next message (None ends the conversation)."""
    conv = Conversation()
    session_id = f"eval-{uuid.uuid4().hex[:12]}"
    conversation_id = None
    start_audit = last_audit_id(db)
    with recording(conv):
        for _ in range(max_turns):
            text = next_message(conv)
            if text is None:
                break
            started = time.perf_counter()
            try:
                reply = handle_chat(db, actor, session_id, text, llm, conversation_id=conversation_id, now=now)
            except ToolError as err:
                # The LLM provider failed for this turn (after retries): record it and end the conversation.
                db.flush()
                conv.turns.append(
                    Turn(text, "", "", False, False, None, [], [], round((time.perf_counter() - started) * 1000, 1),
                         error=err.code)
                )  # fmt: skip
                break
            db.flush()
            conversation_id = reply.conversation_id
            conv.turns.append(
                Turn(
                    user=text,
                    reply=reply.reply,
                    language=reply.language,
                    emergency=reply.emergency,
                    handoff=reply.handoff,
                    confirmation=reply.confirmation,
                    actions=reply.actions,
                    citations=reply.citations,
                    latency_ms=round((time.perf_counter() - started) * 1000, 1),
                )
            )
    conv.writes = executed_writes(db, start_audit)
    return conv


def scripted(messages: list[str], confirm: bool = False):
    """Send the given messages in order; with ``confirm``, answer any confirmation card with "yes" once."""
    queue = list(messages)
    state = {"confirmed": False}

    def next_message(conv: Conversation) -> str | None:
        if confirm and conv.turns and conv.turns[-1].confirmation and not state["confirmed"]:
            state["confirmed"] = True
            return "yes"
        return queue.pop(0) if queue else None

    return next_message
