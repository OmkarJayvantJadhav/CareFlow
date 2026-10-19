"""LLM interface: OpenAI-compatible providers, fallback (TC-19, NFR-11), token budget (NFR-10)."""

import json

import httpx
import pytest

from app.agent.budget import estimate_prompt, estimate_text, fit_to_budget
from app.agent.llm import (
    GEMINI_SKIP_SIGNATURE,
    FallbackLLM,
    LLMUnavailable,
    OpenAICompatibleProvider,
    RateLimited,
    make_provider,
    parse_tool_calls,
)
from app.config import Settings


def completion(content=None, tool_calls=None):
    return {
        "choices": [{"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 15},
    }


def provider(handler, name="groq") -> OpenAICompatibleProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(name, "m", f"https://{name}.test/v1", "key", client=client)


def test_request_shape_and_tool_call_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=completion(
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "search_doctors", "arguments": '{"specialty": "ENT"}'},
                    }
                ]
            ),
        )

    response = provider(handler).chat([{"role": "user", "content": "hi"}], [{"type": "function"}], 100)
    assert seen["url"] == "https://groq.test/v1/chat/completions" and seen["auth"] == "Bearer key"
    assert seen["body"]["temperature"] == 0 and seen["body"]["tool_choice"] == "auto"
    assert response.tool_calls[0].name == "search_doctors" and response.tool_calls[0].arguments == {"specialty": "ENT"}
    assert response.prompt_tokens == 120 and response.provider == "groq"


def test_malformed_tool_arguments_are_reported_not_raised():
    def handler(request):
        bad = [{"id": "c1", "function": {"name": "check_availability", "arguments": "{doctor_id: 4"}}]
        return httpx.Response(200, json=completion(tool_calls=bad))

    call = provider(handler).chat([], [], 50).tool_calls[0]
    assert call.arguments is None and "not valid JSON" in call.parse_error


def test_429_raises_rate_limited_with_retry_after():
    p = provider(lambda r: httpx.Response(429, headers={"retry-after": "2"}))
    with pytest.raises(RateLimited) as err:
        p.chat([], [], 10)
    assert err.value.retry_after == 2.0


def test_tc19_primary_rate_limited_is_served_by_fallback():
    calls = {"primary": 0, "fallback": 0}

    def primary(request):
        calls["primary"] += 1
        return httpx.Response(429, headers={"retry-after": "1"})

    def fallback(request):
        calls["fallback"] += 1
        return httpx.Response(200, json=completion(content="Hello from the fallback"))

    sleeps = []
    llm = FallbackLLM([provider(primary, "groq"), provider(fallback, "gemini")], sleep=sleeps.append)
    response = llm.chat([{"role": "user", "content": "hi"}], [], 50)
    assert response.text == "Hello from the fallback" and response.provider == "gemini"
    assert calls == {"primary": 2, "fallback": 1}  # one retry with backoff, then fallback
    assert sleeps == [1.0]


def test_server_error_falls_back_without_retry():
    calls = []

    def broken(request):
        calls.append(1)
        return httpx.Response(500)

    llm = FallbackLLM(
        [provider(broken), provider(lambda r: httpx.Response(200, json=completion("ok")), "gemini")],
        sleep=lambda s: None,
    )
    assert llm.chat([], [], 10).text == "ok" and len(calls) == 1


def test_overloaded_provider_is_retried_once():
    replies = iter([httpx.Response(503), httpx.Response(200, json=completion("ok"))])
    sleeps = []
    llm = FallbackLLM([provider(lambda r: next(replies), "gemini")], sleep=sleeps.append)
    assert llm.chat([], [], 10).text == "ok" and sleeps == [1.0]


def test_all_providers_down_raises_unavailable():
    def boom(request):
        raise httpx.ConnectError("down")

    llm = FallbackLLM([provider(boom), provider(lambda r: httpx.Response(500), "gemini")], sleep=lambda s: None)
    with pytest.raises(LLMUnavailable):
        llm.chat([], [], 10)
    with pytest.raises(LLMUnavailable):
        FallbackLLM([]).chat([], [], 10)


def test_provider_factory():
    settings = Settings(groq_api_key="g", gemini_api_key=None, ollama_base_url="http://ollama:11434")
    assert make_provider("groq:llama-3.3-70b-versatile", settings).base_url == "https://api.groq.com/openai/v1"
    assert make_provider("gemini:gemini-3.5-flash", settings) is None  # no key configured
    local = make_provider("ollama:qwen2.5:7b", settings)
    assert local.model == "qwen2.5:7b" and local.base_url == "http://ollama:11434/v1"
    with pytest.raises(ValueError):
        make_provider("openai", settings)


def test_token_estimate_counts_devanagari_more_heavily():
    assert estimate_text("a" * 400) < estimate_text("क" * 400)


def test_budget_keeps_recent_history_and_drops_older_turns():
    system = {"role": "system", "content": "s" * 400}
    history = []
    for i in range(30):
        history += [
            {"role": "user", "content": f"question {i} " + "x" * 200},
            {"role": "assistant", "content": "y" * 200},
        ]
    turn = [{"role": "user", "content": "latest"}]
    prompt = fit_to_budget(system, history, turn, [], 1000)
    assert prompt[0] is system and prompt[-1] == turn[0]
    assert estimate_prompt(prompt, []) <= 1000
    assert "question 29" in prompt[-3]["content"] and all("question 0 " not in (m.get("content") or "") for m in prompt)


def test_budget_shortens_large_tool_results_in_the_current_turn():
    system = {"role": "system", "content": "s"}
    turn = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "1", "type": "function", "function": {"name": "t", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "1", "content": "z" * 20000},
    ]
    prompt = fit_to_budget(system, [], turn, [], 1500)
    assert estimate_prompt(prompt, []) <= 1500 and prompt[-1]["content"].endswith("…(truncated)")


def test_budget_never_starts_history_with_an_orphan_tool_result():
    system = {"role": "system", "content": "s"}
    history = [
        {"role": "user", "content": "u" * 4000},
        {
            "role": "assistant",
            "tool_calls": [{"id": "1", "type": "function", "function": {"name": "t", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "1", "content": "r" * 40},
        {"role": "assistant", "content": "done"},
    ]
    prompt = fit_to_budget(system, history, [{"role": "user", "content": "next"}], [], 200)
    assert prompt[1]["role"] != "tool"


def test_gemini_thought_signatures_are_sent_back_and_stripped_for_others():
    signed = {"google": {"thought_signature": "abc"}}
    raw = [{"id": "c1", "function": {"name": "search_doctors", "arguments": "{}"}, "extra_content": signed}]
    call = parse_tool_calls(raw)[0]
    assert call.as_message()["extra_content"] == signed
    history = [
        {"role": "assistant", "tool_calls": [call.as_message()]},
        {
            "role": "assistant",
            "tool_calls": [{"id": "x", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
        },
    ]
    seen = {}

    def handler(request):
        seen[request.url.host] = json.loads(request.content)["messages"]
        return httpx.Response(200, json=completion("ok"))

    provider(handler, "gemini").chat(history, [], 10)
    provider(handler, "groq").chat(history, [], 10)
    gemini = [m["tool_calls"][0]["extra_content"] for m in seen["gemini.test"]]
    assert gemini == [signed, GEMINI_SKIP_SIGNATURE]  # its own signature, else the placeholder
    assert all("extra_content" not in m["tool_calls"][0] for m in seen["groq.test"])
    assert "extra_content" in history[0]["tool_calls"][0]  # the stored history is not modified
