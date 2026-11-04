# FastAPI

## 30-second answer
FastAPI is a modern Python web framework for building APIs, built on **Starlette** (ASGI web toolkit) and **Pydantic** (validation). You declare endpoints as Python functions with type hints; FastAPI validates requests, serialises responses, injects dependencies and generates **OpenAPI docs at `/docs`** automatically. Both my backends use it: **CareFlow** has ~100 REST endpoints across 11 routers plus a WebSocket, dependency-injected DB sessions and auth, custom error handlers and background jobs; **MedVision** is a small, hardened inference API (`/health`, `/ready`, `/meta`, `/predict`, `/explain`) with an app factory, model loading in `lifespan`, uploads kept in memory, rate limiting, request IDs and restricted CORS.

---

## Basics you must know

### ASGI, async and sync
- **ASGI** (Asynchronous Server Gateway Interface) servers like **Uvicorn** run FastAPI.
- `async def` endpoints run on the event loop — never call blocking code inside them.
- Plain `def` endpoints run in a **thread pool** automatically — good for blocking libraries (SQLAlchemy sync sessions, ONNX Runtime).
- `run_in_threadpool(fn, ...)` runs blocking code from inside an `async def`.

### Path, query, body
```python
@router.get("/doctors/{doctor_id}/slots")
def slots(doctor_id: int, date: date, db: Session = Depends(get_db)): ...
#        path param      query param   dependency
```
A Pydantic model parameter = JSON body; `UploadFile = File(...)` = multipart upload.

### Dependency injection — `Depends`
Reusable functions that provide things (DB session, current user, settings). Dependencies can depend on others, and `yield` dependencies run cleanup after the response.

### Routers
`APIRouter(prefix="/api/v1")` groups endpoints; `app.include_router(router)`.

### Responses
Return a dict / Pydantic model → JSON. `response_model=` validates and documents the output. `JSONResponse(..., status_code=...)`, `FileResponse`, `StaticFiles`.

### Errors
`raise HTTPException(status_code, detail)` or custom exceptions + `@app.exception_handler(MyError)`.

### Lifespan
```python
@asynccontextmanager
async def lifespan(app):
    # start-up: load model, start threads
    yield
    # shutdown: clean up
app = FastAPI(lifespan=lifespan)
```

### Middleware
Code around every request: CORS, logging, request IDs, rate limiting, compression.

### Testing
`TestClient(app)` (from Starlette, uses httpx) — call endpoints in pytest without a server.

---

## How I used it in CareFlow (`app/api/`)

### Structure
| File | What it serves |
|---|---|
| `main.py` | App, lifespan, error handlers, health, static UI, background threads |
| `routes.py` | Auth (demo login, register, login), chat, booking, analytics |
| `care_routes.py` | Appointments, recommendations, receipts, reminders |
| `queue_routes.py` | Queue control (check in, call next, start, end, missed) + **WebSocket `/ws/queue/{id}`** |
| `registration_routes.py`, `patients_routes.py`, `accounts_routes.py`, `setup_routes.py`, `documents_routes.py`, `library_routes.py`, `messaging_routes.py`, `admin_routes.py` | The rest of the roles' features |
| `deps.py` | `get_db`, `get_auth`, `get_llm`, `SlidingWindowLimiter`, `run_and_commit` |

### Dependencies (`app/api/deps.py`)
```python
def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.rollback()
        db.close()

def get_auth(request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Auth:
    # "Authorization: Bearer <token>" → verify signed token → Actor(role, patient_id, doctor_id)
```
Accounts that must change their password can only reach `/me` and `/me/password` until they do.

### One error format everywhere (`app/api/main.py`, `app/tools/errors.py`)
Business functions raise `ToolError("SLOT_TAKEN", "...")`. A single handler maps the code to an HTTP status (`VALIDATION_ERROR` 400, `UNAUTHORIZED` 401, `FORBIDDEN` 403, `NOT_FOUND` 404, `SLOT_TAKEN`/`DUPLICATE` 409, `POLICY_WINDOW`/`UNSAFE_QUERY` 422, `RATE_LIMITED` 429, `LLM_UNAVAILABLE` 503) and returns `{"error": {"code", "message"}}`. Request validation errors and unexpected exceptions get the same shape (no stack traces leak). The UI shows plain-language text per code.

### `run_and_commit`
Commits after success **and** after a rule failure — a refused write was rolled back to its savepoint inside the tool, but its audit row must still be saved.

### Lifespan and background threads
At start-up: load booking rules, optionally warm up the retriever, start daemon threads: reminders (every 10 min), keep 21 days of slots open (6 h), close past days / record no-shows / refresh setup documents (1 h), lapsed waiting-list offers (5 min), SMS/e-mail outbox (20 s). Each uses `stop.wait(interval)` so shutdown is clean.

### Serving the React app
The built UI (`ui/dist`) is served by FastAPI from the same origin, so there is no CORS to configure and one container runs everything.

### Uvicorn
`uvicorn app.api.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"` (behind Render's proxy).

---

## How I used it in MedVision AI (`backend/app/`)

### App factory + lifespan (`main.py`)
```python
def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        _load_predictor(app, settings)   # ONNX session, checksums verified
        yield
    app = FastAPI(title="MedVision AI", lifespan=lifespan, ...)
```
Run with `uvicorn app.main:create_app --factory`. Tests create apps with custom settings. If the model fails to load, the app **still starts**: `/health` stays up and `/ready` returns **503** with the reason.

### Endpoints (`api/v1/routes.py`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Liveness |
| GET | `/api/v1/ready` | Model loaded and checksum-verified (503 otherwise) |
| GET | `/api/v1/meta` | Version, classes, thresholds, limits |
| POST | `/api/v1/predict` | Prediction (multipart field `file`) |
| POST | `/api/v1/explain` | Prediction + heatmap/overlay PNGs (base64) |

```python
PredictorDep = Annotated[Predictor, Depends(get_predictor)]
ImageFile = Annotated[UploadFile, File(description="JPEG, PNG or WebP image")]

async def read_upload(upload, settings):
    data = await upload.read(settings.max_upload_bytes + 1)   # never buffer more than the limit
    if len(data) > settings.max_upload_bytes: raise ImageTooLargeError(...)
```
Inference (CPU-bound) is called with `run_in_threadpool` so the event loop stays free.

### Hardening
- **Uploads never touch disk:** Starlette spools uploads > 1 MB to a temp file by default; MedVision raises `MultiPartParser.spool_max_size` above the upload limit.
- **Body-size check** from `Content-Length` before reading.
- **Middleware** (`core/middleware.py`): request ID (`X-Request-ID` echoed), sliding-window rate limit per client IP on `/api/` (429 with `Retry-After`), one structured JSON log line per request.
- **CORS** only for configured origins.
- **Error handlers** (`core/errors.py`): `{"error": {"code", "message"}}` with stable codes (`invalid_image` 400, `image_too_large` 413, `unsupported_image_type` 415, `validation_error` 422, `rate_limited` 429, `model_unavailable` 503, `internal_error` 500); unexpected errors are hidden.
- **OpenAPI snapshot test** fails if the committed `openapi.json` used by the frontend is stale.
- 98% backend test coverage.

---

## Interview questions

**Q: Why FastAPI over Flask or Django?**
Type-hint based validation and serialisation (Pydantic), automatic OpenAPI docs, async support, dependency injection, and high performance — with less boilerplate. Django is better for a full admin/ORM monolith; Flask needs extensions for validation and docs.

**Q: `def` vs `async def` endpoints?**
`async def` runs on the event loop — must not block. `def` runs in a thread pool. My CareFlow routes use sync SQLAlchemy, so they're `def`; the WebSocket is `async def`. MedVision's upload handler is async and pushes inference to a thread pool.

**Q: How does dependency injection work in FastAPI?**
Parameters with `Depends(fn)` are resolved per request; `fn` can have its own dependencies; `yield` dependencies clean up after the response (DB session close).

**Q: How did you structure errors?**
One exception type with a stable code and an HTTP mapping, one handler, one JSON shape — the frontend switches on `code`, never on message text.

**Q: How do you load an ML model once?**
In the `lifespan` start-up hook, store it on `app.state`, and provide it via a dependency; the session is reused across requests.

**Q: Readiness vs liveness?**
Liveness (`/health`): the process is alive. Readiness (`/ready`): it can serve traffic (model loaded). Orchestrators restart on failed liveness and stop routing on failed readiness.
