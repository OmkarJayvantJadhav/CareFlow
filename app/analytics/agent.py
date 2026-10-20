"""Natural-language analytics for admins (FR-30), answered with read-only SQL (FR-31).

The LLM gets the reporting views' columns and one tool, ``run_sql``. Requests to
change data are refused in code before the LLM is called, and every query the
LLM writes goes through ``sql_guard`` - an unsafe query ends the turn with
UNSAFE_QUERY and is never executed.
"""

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent.llm import LLM, LLMUnavailable
from app.agent.tracing import Trace
from app.analytics.sql_guard import MAX_ROWS, SCHEMA, VIEWS, run_readonly
from app.config import get_settings
from app.db.models import APPOINTMENT_STATUSES, ENTRY_KINDS, ENTRY_STATUSES, WAITLIST_STATUSES
from app.rag.text import normalize
from app.timeutil import resolve_now, to_ist
from app.tools.errors import ToolError
from app.tools.permissions import Actor

MAX_STEPS = 4
PROMPT_VERSION = "analytics-v1"

# Requests to change or remove data, in English, Hindi and Marathi.
_WRITE_INTENT = re.compile(
    normalize(
        r"\b(delete|drop|truncate|insert|update|alter|grant|revoke|erase|wipe|purge|remove|overwrite)\b"
        r"|\bmark (all|every|each|the|them|these|those)\b.*\bas\b|\bset\b.*\bstatus\b.*\bto\b"
        r"|\b(add|create) (a |an )?(new |fake )?(appointment|patient|row|record|entry|table|user)s?\b"
        r"|हटा|मिटा|डिलीट|बदल दो|बदल दें|हटव|काढून टाक|डिलीट कर|बदलून टाक"
    )
)

TOOL = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": f"Run one read-only PostgreSQL SELECT over the reporting views (at most {MAX_ROWS} rows).",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single SELECT statement."}},
            "required": ["sql"],
        },
    },
}

_schema_lock = threading.Lock()
_schema_text: str | None = None


def schema_description(db: Session) -> str:
    global _schema_text
    with _schema_lock:
        if _schema_text is None:
            rows = db.execute(
                text(
                    "SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = :s ORDER BY table_name, ordinal_position"
                ),
                {"s": SCHEMA},
            ).all()
            tables: dict[str, list[str]] = {}
            for table, column, kind in rows:
                tables.setdefault(table, []).append(f"{column} {kind}")
            _schema_text = "\n".join(f"- {t}({', '.join(cols)})" for t, cols in tables.items() if t in VIEWS)
        return _schema_text


def system_prompt(schema: str, now: datetime) -> str:
    return f"""You answer questions from the OPD administrator of a fictional hospital using read-only SQL.
Current date and time (IST): {to_ist(now):%A %d %B %Y, %H:%M}.
Views (PostgreSQL; query them by name):
{schema}
Values: appointments.status in ({", ".join(APPOINTMENT_STATUSES)}); queue_entries.status in
({", ".join(ENTRY_STATUSES)}); queue_entries.kind in ({", ".join(ENTRY_KINDS)}); waiting_list.status in
({", ".join(WAITLIST_STATUSES)}). Dates are IST; doctors.opd_days are ISO weekdays (1 = Monday).
Rules:
- Use the run_sql tool with ONE SELECT statement. Never try to change data; you cannot.
- Do not list individual patients; answer with counts, rates and averages.
- After the result arrives, answer in one to three short sentences with the numbers. Do not invent numbers.
- If the question cannot be answered from these views, say so."""


@dataclass
class AnalyticsAnswer:
    answer: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "sql": self.sql,
            "columns": self.columns,
            "rows": json.loads(json.dumps(self.rows, default=str)),
            "row_count": len(self.rows),
            "truncated": self.truncated,
        }


def check_request(question: str) -> None:
    if _WRITE_INTENT.search(normalize(question)):
        raise ToolError("UNSAFE_QUERY", "Analytics can only read data; it cannot change, add or remove anything.")


def answer_question(db: Session, actor: Actor, question: str, llm: LLM, now: datetime | None = None) -> AnalyticsAnswer:
    if actor.role != "admin":
        raise ToolError("FORBIDDEN", "Analytics questions are available to admins only.")
    question = (question or "").strip()
    if not question:
        raise ToolError("VALIDATION_ERROR", "The question is empty.")
    if len(question) > get_settings().max_message_chars:
        raise ToolError("VALIDATION_ERROR", "The question is too long.")
    now = resolve_now(now)
    trace = Trace(f"analytics-{actor.user_id}", actor.user_id, actor.role)
    try:
        check_request(question)
    except ToolError as err:
        trace.span("sql_guard", stage="request", refused=True)
        trace.finish(turn_type="analytics", prompt_version=PROMPT_VERSION, refused=err.code)
        raise

    messages = [
        {"role": "system", "content": system_prompt(schema_description(db), now)},
        {"role": "user", "content": question},
    ]
    last: AnalyticsAnswer | None = None
    for _ in range(MAX_STEPS):
        try:
            response = llm.chat(messages, [TOOL], get_settings().llm_max_output_tokens)
        except LLMUnavailable as err:
            trace.llm(None, error=str(err))
            trace.finish(turn_type="analytics", prompt_version=PROMPT_VERSION)
            raise ToolError("LLM_UNAVAILABLE", "The assistant is temporarily unavailable.") from None
        trace.llm(response)
        if not response.tool_calls:
            answer = (response.text or "").strip() or "I could not answer that from the reporting data."
            trace.finish(turn_type="analytics", prompt_version=PROMPT_VERSION)
            if last is None:
                return AnalyticsAnswer(answer)
            last.answer = answer
            return last
        call = response.tool_calls[0]
        sql = (call.arguments or {}).get("sql", "") if call.name == "run_sql" else ""
        messages.append({"role": "assistant", "tool_calls": [call.as_message()]})
        try:
            result = run_readonly(db.get_bind(), sql)
        except ToolError as err:
            trace.span("sql_guard", stage="query", sql=sql[:500], error=err.code)
            if err.code == "UNSAFE_QUERY":
                trace.finish(turn_type="analytics", prompt_version=PROMPT_VERSION, refused=err.code)
                raise
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps({"error": err.message})})
            continue
        trace.span("sql", sql=result.sql[:500], rows=len(result.rows))
        last = AnalyticsAnswer("", result.sql, result.columns, result.rows, result.truncated)
        preview = json.dumps({"columns": result.columns, "rows": result.rows[:20]}, default=str)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": preview})
    trace.finish(turn_type="analytics", prompt_version=PROMPT_VERSION, failed=True)
    if last is not None:
        last.answer = "Here is the result of the query."
        return last
    raise ToolError("VALIDATION_ERROR", "I could not write a working query for that question. Try rephrasing it.")
