"""The hand-written tool-calling loop.

    user message -> [LLM -> validated tool calls -> results]* -> reply

Limits: at most ``max_agent_steps`` LLM calls and 4 tool calls per step per
turn; three invalid tool calls in one turn count as a failed attempt. A write
tool only produces a confirmation card (see app/agent/tools.py), and once a
card exists the turn ends with a fixed, localised confirmation question.
"""

import logging
import re
from dataclasses import dataclass, field

from app.agent.budget import fit_to_budget
from app.agent.llm import LLM, LLMUnavailable
from app.agent.messages import message
from app.agent.tools import TOOLS, ToolContext, dumps, run_tool, tool_schemas
from app.config import get_settings
from app.safety.output_guard import mentions_medication

log = logging.getLogger(__name__)

MAX_CALLS_PER_STEP = 4
MAX_INVALID_CALLS = 3
# Internal ids never reach the user (the prompt asks for this; this makes it a rule): "(slot ID 1293)",
# "appointment_id: 45", "patient id 1".
_ID_WORD = r"(?:slot|appointment|patient|doctor|entry|waiting[_ ]?list)[_ ]?(?:id|ID|Id)"
_INTERNAL_ID = re.compile(rf"\s*\([^()]*\b{_ID_WORD}\b[^()]*\)|\b{_ID_WORD}\b\s*[:#=]?\s*\d+,?", re.I)


def strip_internal_ids(text: str) -> str:
    cleaned = _INTERNAL_ID.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).replace(" \n", "\n").strip()


# [1], and the full-width 【1】 some models write; both are shown as [1].
_CITATION = re.compile(r"[\[【]\s*(\d{1,2})\s*[\]】]")
CONFIRM_KEYS = {
    "book_appointment": "confirm_book",
    "reschedule_appointment": "confirm_reschedule",
    "cancel_appointment": "confirm_cancel",
    "join_waiting_list": "confirm_waiting_list",
}


@dataclass
class TurnResult:
    reply: str
    messages: list[dict]
    citations: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    pending: dict | None = None
    emergency: bool = False
    handoff_ticket_id: int | None = None
    failed: bool = False
    offer_handoff: bool = False


def _cited_refs(reply: str, ctx: ToolContext) -> list[int]:
    """The retrieved sources the reply actually cites with [n]."""
    refs = []
    for match in _CITATION.finditer(reply):
        n = int(match.group(1))
        if 1 <= n <= len(ctx.sources) and n not in refs:
            refs.append(n)
    return refs


def _citations(reply: str, ctx: ToolContext) -> list[dict]:
    """Sources the reply cites with [n]; at least one source whenever knowledge was used (FR-18)."""
    refs = _cited_refs(reply, ctx)
    if not refs and ctx.sources:
        refs = [1]
    return [{"ref": n, **ctx.sources[n - 1].citation()} for n in refs]


class Agent:
    def __init__(self, llm: LLM):
        self.llm = llm
        self.settings = get_settings()

    def run(self, ctx: ToolContext, system: str, history: list[dict], user_text: str) -> TurnResult:
        schemas = tool_schemas(ctx.actor.role)
        system_message = {"role": "system", "content": system}
        turn: list[dict] = [{"role": "user", "content": user_text}]
        actions: list[dict] = []
        invalid = 0

        for _step in range(self.settings.max_agent_steps):
            prompt = fit_to_budget(system_message, history, turn, schemas, self.settings.prompt_token_budget)
            try:
                response = self.llm.chat(prompt, schemas, self.settings.llm_max_output_tokens)
            except LLMUnavailable as err:
                ctx.trace.llm(None, error=str(err))
                raise
            ctx.trace.llm(response)

            if not response.tool_calls:
                return self._final(ctx, (response.text or "").strip(), turn, actions)

            calls = response.tool_calls[:MAX_CALLS_PER_STEP]
            assistant: dict = {"role": "assistant", "tool_calls": [c.as_message() for c in calls]}
            if response.text:
                assistant["content"] = response.text
            turn.append(assistant)
            for call in calls:
                result, ok = run_tool(ctx, call.name, call.arguments, call.parse_error)
                if not ok and result["error"]["code"] in ("UNKNOWN_TOOL", "VALIDATION_ERROR", "ONE_CHANGE_AT_A_TIME"):
                    invalid += 1
                spec = TOOLS.get(call.name)
                action = {"tool": call.name, "ok": ok, "label": spec.label if spec else call.name}
                if not ok:
                    action["error"] = result["error"]["code"]
                actions.append(action)
                ctx.trace.span("tool", name=call.name, arguments=call.arguments, ok=ok, error=action.get("error"))
                turn.append({"role": "tool", "tool_call_id": call.id, "content": dumps(result)})

            if ctx.emergency:
                reply = message("emergency", ctx.language)
                return TurnResult(
                    reply, turn + [{"role": "assistant", "content": reply}], actions=actions, emergency=True
                )
            if ctx.handoff_ticket_id is not None:
                reply = message("handoff", ctx.language, ticket_id=ctx.handoff_ticket_id)
                return TurnResult(
                    reply,
                    turn + [{"role": "assistant", "content": reply}],
                    actions=actions,
                    handoff_ticket_id=ctx.handoff_ticket_id,
                )
            if ctx.pending is not None:
                reply = message(CONFIRM_KEYS[ctx.pending["tool"]], ctx.language, **ctx.pending["summary"])
                return TurnResult(
                    reply, turn + [{"role": "assistant", "content": reply}], actions=actions, pending=ctx.pending
                )
            if invalid >= MAX_INVALID_CALLS:
                break

        reply = message("agent_failed", ctx.language)
        return TurnResult(reply, turn + [{"role": "assistant", "content": reply}], actions=actions, failed=True)

    def _final(self, ctx: ToolContext, text: str, turn: list[dict], actions: list[dict]) -> TurnResult:
        text = strip_internal_ids(_CITATION.sub(lambda m: f"[{m.group(1)}]", text))
        if not text:
            reply = message("agent_failed", ctx.language)
            return TurnResult(reply, turn + [{"role": "assistant", "content": reply}], actions=actions, failed=True)
        if mentions_medication(text):
            ctx.trace.span("output_guard", rule="medication")
            text = message("no_medicine_advice", ctx.language)
            return TurnResult(text, turn + [{"role": "assistant", "content": text}], actions=actions)
        other_tools = [a for a in actions if a["tool"] != "search_knowledge"]
        if ctx.knowledge_calls and not other_tools and not _cited_refs(text, ctx):
            # FR-18/FR-19: an answer from the hospital's documents must cite one of the retrieved
            # sources. Nothing relevant was found, or the reply cites none of it, so the model may
            # be answering from memory - say so instead.
            ctx.trace.span("grounding_guard", sources=ctx.knowledge_hits)
            text = message("no_source", ctx.language)
            return TurnResult(
                text, turn + [{"role": "assistant", "content": text}], actions=actions, offer_handoff=True
            )
        citations = _citations(text, ctx) if ctx.knowledge_hits else []
        return TurnResult(text, turn + [{"role": "assistant", "content": text}], citations=citations, actions=actions)
