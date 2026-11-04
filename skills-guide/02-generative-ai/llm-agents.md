# LLM Agents

## 30-second answer
An LLM agent is a loop where a language model decides what to do next — call a tool, read the result, call another tool, or answer — until the task is done. In CareFlow I **hand-wrote the agent loop** (no LangChain) so every rule lives in code: tool arguments are validated with Pydantic, the loop has a **step limit (6)**, at most **4 tool calls per step**, a **3,000-token prompt budget**, and three invalid calls end the turn. The LLM can only *propose* a booking: the change is **previewed inside a database savepoint that is rolled back**, shown as a confirmation card, and executed only after the user confirms. It passed 25/25 booking scenarios with a median turn of 0.91 s.

---

## Basics you must know

### What makes something an "agent"
| Plain chatbot | Agent |
|---|---|
| One prompt → one answer | Loop: think → act (tool) → observe → repeat |
| Only knows its training data | Gets fresh facts through tools (database, search) |
| Cannot change anything | Can take actions (book, cancel) — so it needs guardrails |

### The ReAct-style loop
```
user message
  → LLM (sees: system prompt, history, tool schemas)
     → returns either text (final answer) or tool calls
  → run tools, append results as "tool" messages
  → LLM again … until a final answer or a limit is hit
```

### Key design questions for any agent
1. **Which tools?** Keep them small and specific.
2. **Who enforces rules?** Code, not the prompt. Prompts can be ignored or jailbroken.
3. **Limits:** max steps, max tool calls, token budget, timeouts — otherwise loops can run forever and cost money.
4. **State:** what is stored between turns (conversation history, pending actions).
5. **Human in the loop** for anything irreversible.
6. **Observability:** trace every model call and tool call.
7. **Evaluation:** scripted scenarios, not "it looked fine".

### Frameworks vs hand-written
LangChain / LlamaIndex / LangGraph give ready abstractions. I wrote ~170 lines (`app/agent/loop.py`) instead because I needed precise control over confirmation, emergencies, citations and token budgets, and it makes every behaviour testable with a scripted fake LLM.

---

## How I built it in CareFlow

### Files
| File | Job |
|---|---|
| `app/agent/chat.py` | One chat turn: checks in a fixed order, then the agent loop, then persistence |
| `app/agent/loop.py` | The tool-calling loop and output checks |
| `app/agent/tools.py` | Tool definitions (Pydantic args → JSON schema), preview → confirmation card |
| `app/agent/llm.py` | One OpenAI-compatible client for Groq / Gemini / Ollama, with fallback |
| `app/agent/budget.py` | Token estimation and trimming history to a budget |
| `app/agent/prompts.py` | Short system prompt (`agent-v4`) |
| `app/agent/tracing.py` | JSON-lines trace of every LLM and tool call, masked, with cost estimate |

### Order of checks for every message (`app/agent/chat.py`)
1. Input validation (length, quotas: 20 messages per session, 60 per IP per hour).
2. **Emergency check** — before the LLM. An emergency gets fixed guidance (call 112 / 108), any pending card is dropped, nothing is written.
3. **"Talk to a person"** request (regex in 3 languages) → handoff ticket.
4. **Pending confirmation card** — "yes" executes it, "no" cancels, anything else drops it.
5. Otherwise run the **agent loop**. Three failed turns in a row → offer a human.

### The loop (`app/agent/loop.py`, simplified)
```python
for _step in range(settings.max_agent_steps):          # 6
    prompt = fit_to_budget(system, history, turn, schemas, settings.prompt_token_budget)  # 3000
    response = self.llm.chat(prompt, schemas, settings.llm_max_output_tokens)
    if not response.tool_calls:
        return self._final(ctx, response.text, turn, actions)    # output guards here
    for call in response.tool_calls[:MAX_CALLS_PER_STEP]:          # 4
        result, ok = run_tool(ctx, call.name, call.arguments, call.parse_error)
        if not ok and code in ("UNKNOWN_TOOL", "VALIDATION_ERROR", "ONE_CHANGE_AT_A_TIME"):
            invalid += 1
        turn.append({"role": "tool", "tool_call_id": call.id, "content": dumps(result)})
    if ctx.emergency:  return fixed emergency reply
    if ctx.handoff_ticket_id is not None: return handoff reply
    if ctx.pending is not None: return fixed, localised "please confirm" question
    if invalid >= MAX_INVALID_CALLS: break                         # 3
return "agent_failed" reply
```
Notice: once a confirmation card exists, **the turn ends with a fixed sentence written by my code**, not by the LLM — so the model can never say "Done, I booked it".

### Confirmation in code (the most important idea)
```python
def _preview(ctx, fn):
    savepoint = ctx.db.begin_nested()   # SAVEPOINT
    try:
        return fn()                     # the REAL booking function, with all its checks
    finally:
        savepoint.rollback()            # ROLLBACK TO SAVEPOINT — nothing is kept
```
If the preview succeeds, `_card()` stores a pending action (`action_id`, tool, args, summary, `expires_at = now + 5 min`). When the user confirms that exact card, `execute_confirmed()` runs the tool again with `confirmed=True`. The `confirmed` flag is **not in any schema the LLM sees**, so the model cannot skip confirmation.

Why preview with the real function? The card shows what will *really* happen — if the slot is taken or the patient already has a booking that day, the user sees the error before confirming.

### Output checks after the final answer (`_final`)
- `strip_internal_ids()` removes "slot ID 1293" style leaks with a regex.
- `mentions_medication()` → replace the reply with a fixed "no medical advice" message.
- **Grounding guard:** if the agent searched the knowledge base but the reply cites none of the retrieved sources (`[1]`, `[2]`…), the reply is replaced by "I couldn't find that" and a human is offered.

### Role-aware tools
`tool_schemas(role)` sends only patient tools to patients/caregivers — fewer tokens and fewer ways to misuse. Permissions are still re-checked inside every service function (`require_patient_access`).

### Token budget (`app/agent/budget.py`)
No tokenizer download: estimate ~4 characters per token for Latin text and ~2 for Devanagari (Hindi/Marathi split into more tokens). `fit_to_budget` always keeps the system prompt and current turn, shortens the longest tool results first, then adds as much recent history as fits, and never starts with an orphaned tool message.

### Tracing
Every turn writes a JSON line: trace id, spans for each LLM call (provider, model, tokens, latency) and tool call, estimated cost from a price table, with phone numbers masked. The last 200 traces are kept in memory for the admin dashboard.

### Results (README, `eval/results/`)
- Agent booking scenarios: **25/25 passed**, median turn **0.91 s** (`groq:openai/gpt-oss-120b`, prompt `agent-v2`).
- Queue actions by chat (check in, join online, leave): **19/20 runs**, 0 wrong actions, 0 false emergencies (prompt `agent-v4`).

---

## Interview questions

**Q: Why not just tell the model in the prompt "always ask before booking"?**
Prompts are suggestions; models can ignore them or be jailbroken. In CareFlow the confirmation is enforced by code: the write tools only produce a preview card, and the real write happens in the chat layer after an explicit "yes" to that exact card. The prompt only explains the flow.

**Q: How do you stop infinite loops and runaway cost?**
Max 6 LLM calls per turn, max 4 tool calls per step, 3 invalid calls end the turn, a 3,000-token prompt budget, a 1,024-token output cap, 30 s timeouts, and per-session / per-IP message quotas.

**Q: What happens if the LLM sends bad JSON arguments?**
`parse_tool_calls` records a `parse_error`; `run_tool` returns a `VALIDATION_ERROR` result to the model (not an exception), so it can correct itself. Pydantic validation errors are summarised (first 3 problems). Three invalid calls → the turn fails gracefully.

**Q: How do you test an agent deterministically?**
`ScriptedLLM` in `app/agent/llm.py` returns pre-written responses step by step, so tests check the loop, tools, confirmation and guards without calling a real model. Real-model runs are in the `eval/` suite.

**Q: Why hand-write instead of LangChain?**
Fewer abstractions, full control over confirmation, emergencies, citations and budgets, and every behaviour is a plain Python function I can unit-test. The loop is about 170 lines.

**Q: What would you improve?**
Run all 120 planned agent scenarios with repeats, compare prompts statistically, and move the WebSocket broadcaster to a shared message bus so the app can run on several processes.

---

## Key terms
Agent loop · ReAct · tool/function calling · human-in-the-loop · step limit · token budget · grounding · tracing/observability · scripted LLM for tests · savepoint preview.
