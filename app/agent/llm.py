"""The single LLM interface (NFR-11, NFR-16).

Groq, Gemini and Ollama all expose OpenAI-compatible chat-completions APIs with
tool calling, so one client class serves all three; switching providers is a
configuration change ("provider:model"). ``FallbackLLM`` retries a rate-limited
provider once with backoff and then moves to the next one.
"""

import json
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 4.0


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict | None
    raw_arguments: str = ""
    parse_error: str | None = None

    def as_message(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.raw_arguments or json.dumps(self.arguments or {})},
        }


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


class LLMError(Exception):
    pass


class RateLimited(LLMError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMUnavailable(LLMError):
    """Every configured provider failed."""


class LLM(Protocol):
    def chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse: ...


def parse_tool_calls(raw: Sequence[dict] | None) -> list[ToolCall]:
    calls = []
    for item in raw or []:
        fn = item.get("function") or {}
        args_text = fn.get("arguments") or ""
        arguments, error = None, None
        if isinstance(args_text, dict):
            arguments, args_text = args_text, json.dumps(args_text)
        else:
            try:
                arguments = json.loads(args_text) if args_text.strip() else {}
                if not isinstance(arguments, dict):
                    arguments, error = None, "arguments must be a JSON object"
            except json.JSONDecodeError as err:
                error = f"arguments are not valid JSON: {err.msg}"
        calls.append(
            ToolCall(
                id=item.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=fn.get("name", ""),
                arguments=arguments,
                raw_arguments=args_text,
                parse_error=error,
            )
        )
    return calls


class OpenAICompatibleProvider:
    def __init__(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"

    def chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        started = time.perf_counter()
        try:
            response = self._client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as err:
            raise LLMError(f"{self.name}: {type(err).__name__}") from None
        latency = (time.perf_counter() - started) * 1000
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            try:
                wait = float(retry_after) if retry_after else None
            except ValueError:
                wait = None
            raise RateLimited(f"{self.name}: rate limited", wait)
        if response.status_code >= 400:
            raise LLMError(f"{self.name}: HTTP {response.status_code}")
        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError(f"{self.name}: malformed response") from None
        usage = data.get("usage") or {}
        return LLMResponse(
            text=message.get("content"),
            tool_calls=parse_tool_calls(message.get("tool_calls")),
            provider=self.provider,
            model=self.model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=round(latency, 1),
        )


def make_provider(spec: str, settings: Settings, client: httpx.Client | None = None) -> OpenAICompatibleProvider | None:
    """Build a provider from "provider:model". Returns None when its API key is not configured."""
    provider, _, model = spec.partition(":")
    if not model:
        raise ValueError(f"LLM spec {spec!r} must look like provider:model")
    timeout = settings.llm_timeout_seconds
    if provider == "groq":
        if not settings.groq_api_key:
            return None
        return OpenAICompatibleProvider(
            "groq", model, "https://api.groq.com/openai/v1", settings.groq_api_key, timeout, client
        )
    if provider == "gemini":
        if not settings.gemini_api_key:
            return None
        return OpenAICompatibleProvider(
            "gemini",
            model,
            "https://generativelanguage.googleapis.com/v1beta/openai",
            settings.gemini_api_key,
            timeout,
            client,
        )
    if provider == "ollama":
        return OpenAICompatibleProvider(
            "ollama", model, f"{settings.ollama_base_url.rstrip('/')}/v1", None, timeout, client
        )
    raise ValueError(f"unknown LLM provider {provider!r}")


class FallbackLLM:
    """Primary first; on a 429 retry once after a short backoff, then fall back (docs §12)."""

    def __init__(self, providers: Sequence[LLM], sleep: Callable[[float], None] = time.sleep):
        self.providers = list(providers)
        self._sleep = sleep

    def chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse:
        errors = []
        for provider in self.providers:
            for attempt in range(2):
                try:
                    return provider.chat(messages, tools, max_tokens)
                except RateLimited as err:
                    errors.append(str(err))
                    if attempt == 0:
                        self._sleep(min(err.retry_after or 1.0, MAX_BACKOFF_SECONDS))
                        continue
                    break
                except LLMError as err:
                    errors.append(str(err))
                    break
            log.warning("LLM provider %s failed; trying the next one", getattr(provider, "name", provider))
        raise LLMUnavailable("; ".join(errors) or "no LLM provider is configured")


def build_llm(settings: Settings | None = None, client: httpx.Client | None = None) -> FallbackLLM:
    settings = settings or get_settings()
    providers = []
    for spec in (settings.llm_primary, settings.llm_fallback):
        provider = make_provider(spec, settings, client) if spec else None
        if provider is not None:
            providers.append(provider)
    return FallbackLLM(providers)


class ScriptedLLM:
    """Deterministic LLM for tests: each step is a function of the messages so far."""

    name = "scripted:test"

    def __init__(self, steps: Sequence[Callable[[list[dict]], LLMResponse | dict | str]]):
        self.steps = list(steps)
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse:
        self.calls.append([dict(m) for m in messages])
        if not self.steps:
            raise LLMError("scripted LLM has no more steps")
        out = self.steps.pop(0)(messages)
        if isinstance(out, LLMResponse):
            return out
        if isinstance(out, str):
            return LLMResponse(text=out, provider="scripted", model="test", prompt_tokens=100, completion_tokens=20)
        calls = [
            ToolCall(id=f"call_{i}", name=name, arguments=args, raw_arguments=json.dumps(args))
            for i, (name, args) in enumerate(out.items())
        ]
        return LLMResponse(
            text=None, tool_calls=calls, provider="scripted", model="test", prompt_tokens=100, completion_tokens=20
        )
