# Gemini API

## 30-second answer
Gemini is Google's family of multimodal LLMs, available through the Gemini API (Google AI Studio keys) and Vertex AI. In CareFlow, Gemini is the **fallback LLM**: the primary is Groq, and if Groq is rate-limited, overloaded or down, the same request goes to **`gemini-3.5-flash-lite`**. I call Gemini through its **OpenAI-compatible endpoint**, so one client class serves Groq, Gemini and Ollama — switching providers is a configuration change (`LLM_FALLBACK=gemini:gemini-3.5-flash-lite`). I also had to handle Gemini 3's **thought signatures** for tool calls. Gemini Flash-Lite is also used as the **judge model** in the RAG answer evaluation.

---

## Basics you must know

### Ways to call Gemini
| Route | Endpoint | Notes |
|---|---|---|
| Native Gemini API | `generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` | Full features; `google-genai` SDK |
| **OpenAI-compatible** | `generativelanguage.googleapis.com/v1beta/openai/chat/completions` | Same request shape as OpenAI — what CareFlow uses |
| Vertex AI | Google Cloud | Enterprise, IAM, data residency |

### Model tiers (general idea)
- **Pro** — strongest reasoning, slower, pricier.
- **Flash** — fast and cheap, good default.
- **Flash-Lite** — cheapest/fastest, good for high-volume or fallback use.

### Concepts
- **Context window** — very large (up to ~1M tokens on many models).
- **Multimodal** — text, images, audio, video, PDFs.
- **Function calling** — JSON Schema tools, like OpenAI.
- **Structured output** — force JSON matching a schema.
- **Safety settings** — built-in content filters by category.
- **Thinking models** — internal reasoning; Gemini 3 returns a **thought signature** with function calls that must be sent back.
- **Rate limits** — requests per minute (RPM), tokens per minute (TPM), requests per day (RPD); errors as HTTP **429**, or **503** when overloaded.

---

## How I used it in CareFlow (`app/agent/llm.py`)

### One client for three providers
```python
if provider == "gemini":
    return OpenAICompatibleProvider(
        "gemini", model,
        "https://generativelanguage.googleapis.com/v1beta/openai",
        settings.gemini_api_key, timeout, client)
```
The request body is the standard chat-completions shape: `model`, `messages`, `temperature: 0`, `max_tokens`, `tools`, `tool_choice: "auto"`, sent with `Authorization: Bearer <key>` via `httpx`.

### Fallback chain — `FallbackLLM`
```python
for provider in self.providers:                # [Groq, Gemini]
    for attempt in range(2):
        try:
            return provider.chat(messages, tools, max_tokens)
        except RateLimited as err:             # 429 or 503
            if attempt == 0 and not err.daily:  # retry once, unless the DAILY quota is used up
                self._sleep(min(err.retry_after or 1.0, 4.0))
                continue
            break
        except LLMError:
            break                               # move to the next provider
raise LLMUnavailable(...)
```
- `_retry_after()` reads the `Retry-After` header or parses Gemini's `"retryDelay": "34s"` / Groq's "try again in 7m12s".
- `_DAILY_LIMIT` detects "per day" / `PerDay` / `(TPD)` / `(RPD)` messages — no point retrying a daily quota.
- Error messages keep only the provider's **error code**, never the message text (which can echo the conversation).

### Gemini 3 thought signatures
Gemini returns `extra_content: {"google": {"thought_signature": ...}}` with each function call, and the next request must include it. `prepare_messages()`:
- keeps it when sending to Gemini;
- strips it when sending to Groq or Ollama;
- adds Google's documented placeholder `skip_thought_signature_validator` for tool calls Gemini didn't create (e.g. a turn that started on Groq, or the confirmed write added by the chat layer).

### Cost tracking (`app/agent/tracing.py`)
Price table per model (USD per million input/output tokens) to estimate each turn's cost in the trace — e.g. `gemini:gemini-3.5-flash-lite: (0.30, 2.50)`.

### Evaluation
`python -m eval.run_rag --answers --llm groq:openai/gpt-oss-120b --judge gemini:gemini-3.5-flash-lite` — Gemini grades correctness and faithfulness (LLM-as-a-judge). Using a different model family as judge reduces self-preference bias.

### Configuration
```
LLM_PRIMARY=groq:openai/gpt-oss-120b
LLM_FALLBACK=gemini:gemini-3.5-flash-lite
GEMINI_API_KEY=...
```
If a key is missing, `make_provider` returns `None` and that provider is skipped; `/api/v1/health` reports `"degraded"` when no model key is set.

---

## Interview questions

**Q: Why use the OpenAI-compatible endpoint instead of the Gemini SDK?**
One HTTP client and one message format for Groq, Gemini and Ollama; switching provider is just config, and tests can use one fake. The trade-off is losing some Gemini-only features, which I didn't need.

**Q: How does your fallback work?**
Primary first; on 429/503 retry once after a short backoff (max 4 s) unless it's a daily quota, then try the fallback; if all fail raise `LLMUnavailable` and the chat shows a "busy, try again" message.

**Q: What problem did Gemini tool calling cause?**
Gemini 3 requires the thought signature from its function call to be returned in the next request; mixing providers in one conversation broke that, so `prepare_messages` adds, keeps or strips the signature per provider.

**Q: Why Flash-Lite as fallback?**
Cheapest and fastest Gemini tier with tool calling; a fallback is about availability, and the agent's rules are enforced in code, so a smaller model is acceptable.
