# Pydantic

## 30-second answer
Pydantic is a data-validation library: you declare a class with type hints (`class Book(BaseModel): slot_id: int = Field(gt=0)`), and it **parses, validates and converts** incoming data, raising clear errors when it's wrong. It can also export a **JSON Schema**. FastAPI uses it for request bodies and responses, and **pydantic-settings** reads configuration from environment variables. In CareFlow, Pydantic models do double duty for the LLM agent: they **generate the JSON Schemas of the tools** sent to the model *and* **validate the arguments** the model sends back before any tool runs. In MedVision, Pydantic v2 defines the API's response models and settings.

---

## Basics you must know

### Models and validation
```python
from pydantic import BaseModel, Field, ValidationError
from typing import Literal

class BookArgs(BaseModel):
    patient_id: int = Field(gt=0)
    slot_id: int = Field(gt=0)

BookArgs.model_validate({"patient_id": "7", "slot_id": 3})   # "7" coerced to 7 (lax mode)
BookArgs.model_validate({"patient_id": -1, "slot_id": 3})    # ValidationError
```

### Field constraints
`gt`, `ge`, `lt`, `le`, `min_length`, `max_length`, `pattern`, `default`, `default_factory`, `description`.

### Types
`int`, `float`, `str`, `bool`, `date`, `datetime`, `list[str]`, `dict[str, int]`, `Optional[X]` / `X | None`, `Literal["en", "hi", "mr"]`, enums, nested models.

### Model configuration (v2)
```python
model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)   # or extra="forbid"
```

### Useful methods (v2)
| v2 | Purpose |
|---|---|
| `Model.model_validate(data)` | Validate a dict/object |
| `obj.model_dump()` / `model_dump_json()` | Serialise |
| `Model.model_json_schema()` | JSON Schema |
| `@field_validator`, `@model_validator` | Custom validation |

(v1 names were `parse_obj`, `dict()`, `schema()`.)

### pydantic-settings
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEDVISION_", env_file=".env", extra="ignore")
    max_upload_mb: float = Field(default=8.0, gt=0, le=32)
```
Values come from environment variables (with prefix), then `.env`, then defaults — validated like any model.

### Why it's fast
Pydantic v2's core is written in **Rust** (`pydantic-core`).

---

## How I used it in CareFlow

### 1. Tool arguments for the LLM agent (`app/agent/tools.py`)
```python
class Args(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

class SearchKnowledgeArgs(Args):
    query: str = Field(min_length=2, max_length=300, description="What to look up, as a short search query")
    collection: Literal["policies", "insurance", "departments", "doctors", "test_preparation", "facilities"] | None = None
    language: Literal["en", "hi", "mr"] | None = None

class WaitingListArgs(Args):
    patient_id: int = Field(gt=0)
    doctor_id: int = Field(gt=0)
    dates: list[str] = Field(min_length=1, max_length=7, description="Preferred dates, YYYY-MM-DD")
```
- **Schema:** `ToolSpec.schema()` → `model_json_schema()` → `_simplify()` drops `title`, `default`, length limits and collapses `X | None` — the model sees only types, enums and descriptions (fewer tokens).
- **Validation:** `spec.args.model_validate(arguments)`; on `ValidationError`, the first 3 problems are sent back to the LLM as a `VALIDATION_ERROR` tool result so it can fix its call.
- **`extra="ignore"`** — an injected `"confirmed": true` argument is dropped, so the model cannot bypass confirmation.

### 2. Request bodies (`app/api/routes.py` and others)
```python
class LoginRequest(BaseModel):
    role: Literal["patient", "caregiver", "staff", "admin", "doctor"] | None = None
    username: str | None = Field(None, max_length=60)
```
Validation errors are converted by a custom handler into the app's standard `{"error": {"code": "VALIDATION_ERROR", ...}}` with HTTP 400.

### 3. Settings (`app/config.py`)
`class Settings(BaseSettings)` reads `DATABASE_URL`, `LLM_PRIMARY`, `GROQ_API_KEY`, `PROMPT_TOKEN_BUDGET`, `DEMO_MODE`, … with `@lru_cache` on `get_settings()` so it's built once.

## How I used it in MedVision AI

### Response models (`backend/app/schemas/prediction.py`)
```python
class PredictionResponse(BaseModel):
    status: Status = Field(description="ok, low_confidence or rejected")      # StrEnum
    predicted_class: str
    confidence: float = Field(ge=0, le=1)
    top_k: list[ClassProbability]
    risk_flag: RiskFlag
    malignant_probability: float = Field(ge=0, le=1)
    reasons: list[Reason]
    model_version: str
    calibrated: bool
    thresholds_fitted: bool
    summary: str
    disclaimer: str = DISCLAIMER
    latency_ms: float

class ExplanationResponse(PredictionResponse):         # inheritance adds the heatmap fields
    explained_class: str
    heatmap_png: str
    overlay_png: str
```
- `response_model=` makes FastAPI validate outgoing data — a bug producing confidence 1.3 would fail loudly.
- These models generate the **OpenAPI schema**, committed as `frontend/src/api/openapi.json`; frontend tests validate their fixtures against it (typed contract without TypeScript).
- The disclaimer is a default field, so **every** response carries it.

### Settings (`backend/app/core/settings.py`)
`MEDVISION_MODEL_DIR`, `MEDVISION_MAX_UPLOAD_MB` (0 < x ≤ 32), `MEDVISION_RATE_LIMIT_PER_MINUTE` (≥ 0), `MEDVISION_INFERENCE_THREADS`, `MEDVISION_ALLOWED_ORIGINS` (list) — invalid config fails at start-up.

---

## Interview questions

**Q: What does Pydantic do that dataclasses don't?**
Runtime validation and type coercion, constraints, nested parsing, JSON serialisation and JSON Schema generation. Dataclasses only generate `__init__` etc. with no validation.

**Q: How did you use Pydantic with an LLM?**
The same model generates the tool's JSON Schema for the LLM and validates the LLM's arguments before execution, so the schema and the validation can never drift apart.

**Q: `extra="ignore"` vs `extra="forbid"`?**
Ignore drops unknown fields silently; forbid raises an error. For LLM arguments I ignore extras — the model sometimes adds harmless fields — but a dangerous extra like `confirmed` has no effect.

**Q: v1 vs v2?**
v2 has a Rust core (much faster), renamed methods (`model_validate`, `model_dump`, `model_json_schema`), `ConfigDict` instead of `class Config`, and moved settings to `pydantic-settings`.

**Q: How do you validate configuration?**
pydantic-settings with typed fields and constraints; the service refuses to start with invalid values instead of failing later.
