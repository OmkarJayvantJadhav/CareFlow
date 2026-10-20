"""Tracing of every LLM call and tool call with latency, tokens and estimated cost (NFR-14).

Traces are written as JSON lines (one file per day) after masking phone numbers,
and the most recent ones are kept in memory for the admin dashboard.
"""

import json
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.safety.privacy import mask_payload
from app.timeutil import now_ist

# USD per million tokens at paid-tier list price, as published in Oct 2026; an estimate only
# (the demo itself runs on free tiers). Unknown models are counted as 0.
PRICES = {
    "groq:openai/gpt-oss-120b": (0.15, 0.60),
    "gemini:gemini-3.5-flash": (1.50, 9.00),
    "gemini:gemini-3.5-flash-lite": (0.30, 2.50),
}

_recent: deque[dict] = deque(maxlen=200)
_lock = threading.Lock()


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price_in, price_out = PRICES.get(f"{provider}:{model}", (0.0, 0.0))
    return round((prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000, 6)


class Trace:
    def __init__(self, conversation_id: str, user_id: int, role: str):
        self.data: dict[str, Any] = {
            "trace_id": uuid.uuid4().hex,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "started_at": now_ist().isoformat(),
            "spans": [],
        }
        self._t0 = time.perf_counter()

    def span(self, kind: str, **fields: Any) -> None:
        self.data["spans"].append({"kind": kind, **fields})

    def llm(self, response, error: str | None = None) -> None:
        if response is None:
            self.span("llm", error=error)
            return
        self.span(
            "llm",
            provider=response.provider,
            model=response.model,
            latency_ms=response.latency_ms,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=estimate_cost(
                response.provider, response.model, response.prompt_tokens, response.completion_tokens
            ),
            tool_calls=[c.name for c in response.tool_calls],
        )

    def finish(self, **fields: Any) -> dict:
        spans = self.data["spans"]
        llm_spans = [s for s in spans if s["kind"] == "llm" and "prompt_tokens" in s]
        self.data.update(fields)
        self.data["latency_ms"] = round((time.perf_counter() - self._t0) * 1000, 1)
        self.data["prompt_tokens"] = sum(s["prompt_tokens"] for s in llm_spans)
        self.data["completion_tokens"] = sum(s["completion_tokens"] for s in llm_spans)
        self.data["cost_usd"] = round(sum(s["cost_usd"] for s in llm_spans), 6)
        record = mask_payload(self.data)
        write_trace(record)
        return record


def write_trace(record: dict) -> None:
    with _lock:
        _recent.append(record)
        directory = Path(get_settings().trace_dir)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            day = datetime.fromisoformat(record["started_at"]).date().isoformat()
            with (directory / f"{day}.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass  # tracing must never break a request


def recent_traces(limit: int = 50) -> list[dict]:
    with _lock:
        return list(_recent)[-limit:]
