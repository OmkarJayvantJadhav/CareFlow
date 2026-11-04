# Python

## 30-second answer
Python is a high-level, dynamically typed, interpreted language with a huge ecosystem for web, data and AI. It is my main language: the whole CareFlow backend (FastAPI, SQLAlchemy, the LLM agent, RAG, LightGBM) and the whole MedVision pipeline (TensorFlow training, calibration, ONNX serving with FastAPI) are written in Python 3.11, with type hints checked by tools like mypy and linted with ruff.

---

## Basics you must know

### Data types
| Type | Mutable? | Example |
|---|---|---|
| `int`, `float`, `bool`, `str` | No | `42`, `3.14`, `True`, `"hi"` |
| `tuple` | No | `(1, 2)` — usable as a dict key |
| `list` | Yes | `[1, 2, 3]` |
| `dict` | Yes | `{"a": 1}` — insertion-ordered since 3.7 |
| `set` / `frozenset` | Yes / No | `{1, 2}` — O(1) membership test |

### Core features to explain
- **Functions are objects** — they can be passed around (CareFlow passes `lambda` functions into `_preview(ctx, fn)` to run a write inside a savepoint).
- **`*args` / `**kwargs`** — variable positional / keyword arguments.
- **Comprehensions** — `[x * 2 for x in items if x > 0]`, also dict/set comprehensions.
- **Generators / `yield`** — lazy sequences; FastAPI dependencies like `get_db()` use `yield` to give a DB session and then close it.
- **Decorators** — a function that wraps another. `@router.get(...)` in FastAPI, `@dataclass`, `@lru_cache`, and CareFlow's own `@write_tool("book_appointment")`.
- **Context managers (`with`)** — `__enter__`/`__exit__` or `@contextmanager`. CareFlow's `session_scope()` commits on success and rolls back on exception.
- **Exceptions** — `try / except / else / finally`; custom exception classes (`ToolError`, `LLMError`, `RateLimited`).
- **Classes & dataclasses** — `@dataclass(frozen=True)` gives `__init__`, `__eq__`, immutability for free.
- **Type hints** — `def f(x: int) -> str`, `list[int]`, `dict[str, float] | None`, `Protocol`, `Literal`.
- **`Protocol`** (structural typing) — CareFlow's `LLM`, `Embedder` and `Reranker` are Protocols, so any class with the right method works ("duck typing, but checked").

### Memory and performance
- Everything is an object; variables are references.
- **GIL (Global Interpreter Lock):** only one thread runs Python bytecode at a time. Threads still help for I/O-bound work (network, database); for CPU-bound work use processes or C-backed libraries (NumPy, ONNX Runtime, LightGBM release the GIL).
- **Mutable default argument trap:** `def f(x=[])` shares one list across calls — use `field(default_factory=list)` in dataclasses (CareFlow does this).

### Concurrency models
| Model | Use for | In my projects |
|---|---|---|
| `threading` | I/O-bound, blocking libraries | CareFlow background jobs (reminders every 10 min, slot top-up every 6 h) run as threads with `threading.Event` to stop |
| `asyncio` | Many concurrent network connections | CareFlow WebSocket endpoint (`async def`, `asyncio.Queue`, `asyncio.wait`) |
| `multiprocessing` | CPU-bound | Not needed |

---

## How I used it

### CareFlow (`app/`)
- **Package layout by responsibility:** `agent/`, `rag/`, `safety/`, `tools/`, `queue/`, `ml/`, `analytics/`, `db/`, `api/`.
- **Dataclasses everywhere:** `ToolCall`, `LLMResponse`, `TurnResult`, `RetrievedChunk`, `Estimate`.
- **Protocols for pluggable backends** (`app/agent/llm.py`):
  ```python
  class LLM(Protocol):
      def chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse: ...
  ```
  `FallbackLLM`, `OpenAICompatibleProvider` and the test-only `ScriptedLLM` all satisfy it.
- **Regex-heavy safety code:** emergency patterns in English/Hindi/Marathi (`app/safety/emergency.py`), prompt-injection filter (`app/safety/injection.py`), medicine/dose detector (`app/safety/output_guard.py`).
- **Thread-safe singletons:** the emergency classifier and the wait-time model are loaded once behind a `threading.Lock`.
- **Standard library crypto:** passwords hashed with `hashlib.scrypt` (`app/api/passwords.py`); phone lookup with `hmac` (`app/safety/pii.py`).
- **CLI modules:** `python -m simulator seed`, `python -m app.ml.train`, `python -m app.rag.ingest` (`argparse`).

### MedVision AI (`ml/` and `backend/`)
- Two Python packages, each with its own `pyproject.toml` and **uv** lockfile.
- **mypy in strict mode** and **ruff** for lint + format, enforced in CI.
- `from __future__ import annotations`, `NDArray[np.float32]` type hints, `StrEnum` for API enums (`Status`, `RiskFlag`, `Reason`).
- One CLI, `medvision-ml` (`ml/src/medvision_ml/cli.py`), runs every pipeline step: `split`, `check-leakage`, `train`, `evaluate`, `calibrate`, `fit-ood`, `export`.

---

## Interview questions

**Q: List vs tuple?**
A list is mutable, a tuple is immutable. Tuples are hashable (if their items are), so they can be dict keys. CareFlow uses `(doc_key, chunk_index, language)` tuples as dictionary keys to find translations of a chunk.

**Q: What is a decorator? Give an example you wrote.**
A function that takes a function and returns a new one, used for cross-cutting behaviour. FastAPI's `@router.post("/chat")` registers a route. In CareFlow `@write_tool(...)` marks service functions that change data.

**Q: What does `yield` do in a FastAPI dependency?**
Code before `yield` runs before the request; code after runs after the response. `get_db()` opens a SQLAlchemy session, yields it, then rolls back and closes it in `finally`.

**Q: What is the GIL and did it matter for you?**
It allows one thread to execute Python bytecode at a time. In my work, heavy computation runs inside C/C++ libraries (NumPy, ONNX Runtime, LightGBM) that release the GIL, and the rest is I/O (database, LLM HTTP calls), so threads and async were enough.

**Q: `is` vs `==`?**
`==` compares values, `is` compares identity (same object). Use `is` for `None`.

**Q: Shallow vs deep copy?**
A shallow copy copies the container but shares inner objects; a deep copy copies everything. In `fit_to_budget` I copy each message with `dict(m)` so that truncating a tool result does not change the caller's list.

**Q: How do you manage dependencies?**
CareFlow: `requirements.txt` + `requirements-dev.txt` with pip. MedVision: `pyproject.toml` + `uv.lock` with **uv** (`uv sync --locked`), so CI and Docker install the exact same versions.

---

## Cheat sheet
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt` / `uv sync --locked`
- `ruff check . && ruff format --check .` / `mypy` / `pytest`
- f-strings: `f"{value:.2f}"`, `f"{date:%Y-%m-%d}"`
- `enumerate`, `zip(..., strict=True)`, `sorted(key=...)`, `any`/`all`, `collections.defaultdict`, `deque(maxlen=200)` (CareFlow keeps the last 200 traces this way).
