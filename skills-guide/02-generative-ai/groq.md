# Groq

## 30-second answer
Groq is an AI inference company whose **LPU (Language Processing Unit)** chips run open-weight LLMs (Llama, gpt-oss, Qwen, …) with very high tokens-per-second and low latency, through an **OpenAI-compatible API** with a free tier. In CareFlow, Groq is the **primary LLM provider**, running **`openai/gpt-oss-120b`** for the chat agent and the analytics agent. Low latency matters for a chat agent that may call the model up to 6 times per turn — the 25 booking scenarios had a **median turn time of 0.91 s**.

---

## Basics you must know

### Groq vs model labs
Groq doesn't make the models; it **hosts open-weight models** on custom hardware. You choose a model id like `openai/gpt-oss-120b` or `llama-3.3-70b-versatile`.

### Why it's fast
- LPUs are designed for sequential token generation with deterministic, compiler-scheduled execution and lots of on-chip memory, so there's little waiting on external memory.
- Result: hundreds of tokens/second per request and low time-to-first-token.

### API
- Base URL: `https://api.groq.com/openai/v1`
- Endpoint: `POST /chat/completions` — same shape as OpenAI (messages, tools, tool_choice, temperature, max_tokens).
- Auth: `Authorization: Bearer $GROQ_API_KEY`.
- Supports tool calling, JSON mode, streaming.

### Limits (free tier)
Per-model limits on requests per minute/day and tokens per minute/day (RPM, RPD, TPM, TPD). A 429 response carries a message like "Rate limit reached … on tokens per day (TPD) … Please try again in 7m12.5s".

---

## How I used it in CareFlow

### Configuration (`app/config.py`)
```python
llm_primary: str = "groq:openai/gpt-oss-120b"
llm_fallback: str = "gemini:gemini-3.5-flash-lite"
llm_timeout_seconds: float = 30.0
llm_max_output_tokens: int = 1024   # reasoning models spend part of this before answering
```

### Client (`app/agent/llm.py`)
```python
if provider == "groq":
    return OpenAICompatibleProvider("groq", model, "https://api.groq.com/openai/v1",
                                    settings.groq_api_key, timeout, client)
```
The same `OpenAICompatibleProvider` class serves Groq, Gemini and Ollama.

### Handling Groq's rate limits
- 429/503 → `RateLimited` exception with `retry_after` parsed from the header or from "try again in 7m12.5s" (`_TRY_AGAIN` regex handles h/m/s).
- If the message mentions a **daily** limit (`(TPD)` / `(RPD)` / "per day"), don't retry — go straight to Gemini.
- Otherwise retry once after `min(retry_after, 4 s)`, then fall back.

### Keeping requests small (free-tier TPM limits)
- **Token budget** of 3,000 per prompt (`app/agent/budget.py`); estimate tokens without a tokenizer (~4 chars/token Latin, ~2 Devanagari).
- Send only the tools for the user's role, with simplified schemas.
- Compact JSON tool results (`separators=(",", ":")`), at most 12 slots and 700-character sources.
- Short system prompt (`agent-v4`).

### Results with Groq (`groq:openai/gpt-oss-120b`)
- Safety evaluation: 60/60 emergencies, 15/15 medical-advice bait, 15/15 permission attacks, 15/15 prompt injection, 10/10 unsafe analytics.
- 25/25 booking scenarios, median turn 0.91 s.
- Run logs: `eval/runs/agent/groq-openai-gpt-oss-120b.jsonl`.

### Cost estimate (trace price table)
`groq:openai/gpt-oss-120b: (0.15, 0.60)` USD per million input/output tokens — the demo itself runs on the free tier.

---

## Interview questions

**Q: Why Groq as the primary provider?**
Speed and a free tier. An agent turn can take several model calls, so per-call latency adds up; Groq kept the median turn under a second. Because the API is OpenAI-compatible, it costs nothing to switch.

**Q: What is gpt-oss-120b?**
OpenAI's open-weight mixture-of-experts reasoning model; being open-weight, providers like Groq can host it. It supports tool calling, which the agent needs.

**Q: What happens when Groq's daily quota runs out?**
The 429 message says "per day", so the client skips the retry and immediately falls back to Gemini Flash-Lite; if both fail, the user sees a friendly "busy" message.

**Q: What are the risks of depending on a hosted provider?**
Rate limits, outages, model deprecations and data leaving the system. Mitigations: fallback provider, local Ollama option, masking phone numbers in prompts, and rules enforced in code rather than relying on one model's behaviour.
