# Tool Calling (Function Calling)

## 30-second answer
Tool calling lets an LLM ask the application to run a function: we send the model a JSON Schema for each tool, the model replies with a tool name and JSON arguments, our code validates and runs it, and returns the result as a `tool` message. In CareFlow each tool has a **Pydantic argument model** that generates the schema *and* validates the arguments before anything runs. Read tools (search doctors, check availability, search knowledge) run directly; **write tools (book, reschedule, cancel, join waiting list, check in, join/leave queue) only create a confirmation card** after a rolled-back preview.

---

## Basics you must know

### The message flow (OpenAI-compatible format)
```json
// 1. We send
{"messages": [...], "tools": [{"type": "function", "function": {
   "name": "check_availability",
   "description": "...",
   "parameters": {"type": "object", "properties": {"doctor_id": {"type": "integer"}, "date": {"type": "string"}},
                  "required": ["doctor_id", "date"]}}}],
 "tool_choice": "auto"}

// 2. Model replies
{"role": "assistant", "tool_calls": [{"id": "call_1", "type": "function",
   "function": {"name": "check_availability", "arguments": "{\"doctor_id\": 7, \"date\": \"Saturday\"}"}}]}

// 3. We run it and append
{"role": "tool", "tool_call_id": "call_1", "content": "{\"slots\": [...]}"}

// 4. Model answers in text (or calls more tools)
```
Note: `arguments` is a **JSON string**, which may be invalid — always parse defensively.

### `tool_choice`
- `"auto"` — model decides (CareFlow uses this).
- `"none"` — no tools.
- `"required"` / a specific function — force a call (CareFlow's analytics agent effectively has one tool, `run_sql`).

### Good tool design
- Small, single-purpose tools with clear descriptions.
- Use ids returned by earlier tools (e.g. `slot_id` from `check_availability`) instead of free text.
- Return compact JSON — tool results cost tokens.
- Return errors as data (`{"error": {"code": ..., "message": ...}}`) so the model can recover.
- Never trust arguments: validate types, ranges, permissions.

---

## How I built it in CareFlow (`app/agent/tools.py`)

### 1. Pydantic models define arguments
```python
class Args(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

class CheckAvailabilityArgs(Args):
    doctor_id: int = Field(gt=0)
    date: str = Field(max_length=20, description="YYYY-MM-DD, a weekday name, 'today' or 'tomorrow'")

class BookArgs(Args):
    patient_id: int = Field(gt=0)
    slot_id: int = Field(gt=0)

class SearchKnowledgeArgs(Args):
    query: str = Field(min_length=2, max_length=300)
    collection: Literal["policies", "insurance", "departments", "doctors", "test_preparation", "facilities"] | None = None
```
`extra="ignore"` means an injected `"confirmed": true` argument is silently dropped.

### 2. Schema generated from the model, then simplified
`ToolSpec.schema()` calls `model_json_schema()` and `_simplify()` removes keys the LLM doesn't need (`title`, `default`, `minLength`, `maxLength`, …) and collapses `Optional[X]` (`anyOf: [X, null]`) into `X`. Validation limits stay enforced by Pydantic; the model only needs types, enums and descriptions — fewer tokens.

### 3. Each tool is a `ToolSpec`
```python
@dataclass
class ToolSpec:
    name: str
    description: str
    args: type[Args]
    kind: Literal["read", "write", "special"]
    run: Callable[[ToolContext, Any], dict]
    label: str   # "Checking available slots…" — shown in the UI while it runs
```

### 4. `run_tool` — the single gatekeeper
```python
def run_tool(ctx, name, arguments, parse_error):
    spec = TOOLS.get(name)
    if spec is None or name not in PATIENT_TOOLS:      → UNKNOWN_TOOL
    if parse_error:                                     → VALIDATION_ERROR (bad JSON)
    args = spec.args.model_validate(arguments or {})    → VALIDATION_ERROR (first 3 problems)
    if spec.kind == "write" and ctx.pending is not None:→ ONE_CHANGE_AT_A_TIME
    return spec.run(ctx, args), True                    # ToolError → {"error": ...}, False
```

### 5. Write tools → preview → card
`run_book` calls the real `booking.book_appointment(...)` inside `_preview()` (savepoint + rollback). On success it creates a card with a 5-minute expiry and returns `{"status": "awaiting_confirmation"}` to the model. The real write happens later in `execute_confirmed()`, called by the chat layer, never by the LLM.

### 6. Same business functions as the REST API
Tools call `app/tools/booking.py`, `waiting_list.py`, `app/queue/engine.py` — the very same functions the REST endpoints use. Rules (booking window 15 min–30 days, cancellation until 4 h before, one appointment per patient/doctor/day) are enforced once, in one place.

### 7. Provider quirks handled in `app/agent/llm.py`
- `parse_tool_calls` accepts arguments as a JSON string *or* a dict, catches `JSONDecodeError`, and generates an id if the provider omitted one.
- **Gemini 3 thought signatures:** Gemini returns an opaque signature with a function call that must be sent back. `prepare_messages()` keeps it for Gemini, strips it for other providers, and adds a documented "skip" placeholder for calls Gemini didn't make (e.g. the confirmed write).

### The tool list (patients/caregivers)
`search_knowledge`, `search_doctors`, `check_availability`, `get_patient_appointments`, `get_queue_status`, `predict_wait_time`, `list_queues_today`, `book_appointment`, `reschedule_appointment`, `cancel_appointment`, `join_waiting_list`, `check_in`, `join_virtual_queue`, `leave_queue`, `emergency_redirect`, `handoff_to_human`.

### Second agent: analytics (`app/analytics/agent.py`)
One tool, `run_sql`, for admins. The SQL it writes goes through a validator and a read-only transaction — see [SQL](../07-databases/sql.md).

---

## Interview questions

**Q: How does the model know which tools exist?**
We send JSON Schemas in the `tools` field of every request. In CareFlow they are generated from Pydantic models, and only the tools for the user's role are sent.

**Q: What if the model invents a tool or passes wrong types?**
`run_tool` returns `UNKNOWN_TOOL` or `VALIDATION_ERROR` as a tool result so the model can fix it; three invalid calls end the turn with a polite failure message.

**Q: How do you prevent the model from doing something dangerous with a tool?**
(1) Validation and permission checks inside every service function; (2) write tools only preview; (3) the confirmation flag is not part of the schema; (4) one pending change at a time; (5) cards expire after 5 minutes.

**Q: Parallel tool calls?**
A model can return several tool calls in one step; CareFlow runs up to 4 in order and appends each result with its `tool_call_id`.

**Q: Why return errors to the model instead of raising?**
So the model can recover (e.g. pick another slot after `SLOT_TAKEN`). Exceptions would end the turn for something the model could fix.
