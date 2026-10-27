"""FastAPI application: /api/v1 REST endpoints, chat, health."""

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from app.agent.llm import build_llm
from app.api.accounts_routes import router as accounts_router
from app.api.admin_routes import router as admin_router
from app.api.care_routes import router as care_router
from app.api.documents_routes import router as documents_router
from app.api.library_routes import router as library_router
from app.api.messaging_routes import router as messaging_router
from app.api.patients_routes import router as patients_router
from app.api.queue_routes import router as queue_router
from app.api.queue_routes import ws_router
from app.api.registration_routes import router as registration_router
from app.api.routes import router
from app.api.setup_routes import router as setup_router
from app.config import get_settings
from app.db.models import KbChunk
from app.db.session import get_engine, session_factory
from app.rag.retriever import get_retriever
from app.safety.privacy import install_log_masking
from app.timeutil import now_ist
from app.tools.errors import ToolError

DEMO_BANNER = "Demo with a fictional hospital. Not for medical use."

install_log_masking()
log = logging.getLogger("careflow.api")


def _warm_up() -> None:
    """Load the retrieval models in the background so the first question does not wait for them."""
    try:
        with session_factory()() as db:
            get_retriever(db)
    except Exception:  # noqa: BLE001 - the first request will try again and report the error
        log.exception("retriever warm-up failed")


def _keep_slots_open(stop: threading.Event) -> None:
    """A deployment that runs for weeks keeps the next 21 days bookable (checked every 6 hours)."""
    from app.tools.timetable import top_up_slots

    while not stop.is_set():
        try:
            with session_factory()() as db:
                added = top_up_slots(db, now_ist().date())
                db.commit()
                if added:
                    log.info("added %d slots", added)
        except Exception:  # noqa: BLE001 - try again next time
            log.exception("slot top-up failed")
        stop.wait(6 * 3600)


def _close_past_days(stop: threading.Event) -> None:
    """Days that are over get their queues closed and no-shows recorded, if the desk did not (D-127).
    Checked at start-up and then every hour, so it happens soon after midnight."""
    from app.queue.engine import close_past_days

    while not stop.is_set():
        try:
            with session_factory()() as db:
                result = close_past_days(db, now_ist())
                db.commit()
                if any(result.values()):
                    log.info("closed past days: %s", result)
        except Exception:  # noqa: BLE001 - try again next time
            log.exception("closing past days failed")
        stop.wait(3600)


def _send_reminders(stop: threading.Event) -> None:
    """Appointment reminders (the day before and two hours before), checked every 10 minutes."""
    from app.tools.reminders import send_due_reminders

    while not stop.is_set():
        try:
            with session_factory()() as db:
                sent = send_due_reminders(db, now_ist())
                db.commit()
                if sent:
                    log.info("sent %d reminders", sent)
        except Exception:  # noqa: BLE001 - try again next time
            log.exception("reminders failed")
        stop.wait(600)


def _expire_waitlist_offers(stop: threading.Event) -> None:
    """Waiting-list offers whose hold lapsed go back to the list and the slot is offered to the next patient
    (D-08, D-136); checked every 5 minutes."""
    from app.tools.waiting_list import expire_waitlist_offers

    while not stop.is_set():
        try:
            with session_factory()() as db:
                lapsed = expire_waitlist_offers(db, now_ist())
                db.commit()
                if lapsed:
                    log.info("%d waiting-list offers lapsed", lapsed)
        except Exception:  # noqa: BLE001 - try again next time
            log.exception("expiring waiting-list offers failed")
        stop.wait(300)


def _deliver_messages(stop: threading.Event) -> None:
    """Messages by SMS and e-mail (phase 7E): the outbox is checked every 20 seconds."""
    from app.tools.messaging import deliver_due

    while not stop.is_set():
        try:
            with session_factory()() as db:
                counts = deliver_due(db)
                db.commit()
                if counts:
                    log.info("message delivery: %s", counts)
        except Exception:  # noqa: BLE001 - try again next time
            log.exception("message delivery failed")
        stop.wait(20)


def _load_policy() -> None:
    """The hospital's own booking and queue rules (phase 7D); the defaults if the database cannot be read."""
    from app.tools.policy_settings import load_policy

    try:
        with session_factory()() as db:
            load_policy(db)
    except Exception:  # noqa: BLE001 - serve with the default rules rather than not at all
        log.exception("could not load the policy settings; using the defaults")


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = threading.Event()
    _load_policy()
    if get_settings().warm_up_retriever:
        threading.Thread(target=_warm_up, name="retriever-warm-up", daemon=True).start()
        threading.Thread(target=_keep_slots_open, args=(stop,), name="slot-top-up", daemon=True).start()
        threading.Thread(target=_send_reminders, args=(stop,), name="reminders", daemon=True).start()
        threading.Thread(target=_close_past_days, args=(stop,), name="close-past-days", daemon=True).start()
        threading.Thread(target=_expire_waitlist_offers, args=(stop,), name="waitlist-offers", daemon=True).start()
    threading.Thread(target=_deliver_messages, args=(stop,), name="message-delivery", daemon=True).start()
    yield
    stop.set()


app = FastAPI(
    title="CareFlow API",
    version="0.2.0",
    description="OPD appointments, hospital information and live queues.",
    lifespan=lifespan,
)


@app.exception_handler(ToolError)
def tool_error_handler(request: Request, err: ToolError) -> JSONResponse:
    headers = {}
    if err.code == "RATE_LIMITED" and err.details.get("retry_after"):
        headers["Retry-After"] = str(err.details["retry_after"])
    return JSONResponse({"error": err.to_dict()}, status_code=err.http_status, headers=headers)


@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, err: RequestValidationError) -> JSONResponse:
    problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in err.errors()[:3])
    return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": problems}}, status_code=400)


@app.exception_handler(Exception)
def unexpected_error_handler(request: Request, err: Exception) -> JSONResponse:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        {"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong on our side. Please try again."}},
        status_code=500,
    )


@app.get("/api/v1/health", tags=["platform"])
def health() -> JSONResponse:
    """Liveness and dependency status; 503 when the database is unreachable."""
    checks: dict = {"database": "down", "pgvector": "missing"}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
            if conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first():
                checks["pgvector"] = "ok"
        with session_factory()() as db:
            count = db.scalar(select(func.count(KbChunk.id)))
            models = sorted(set(db.scalars(select(KbChunk.embedding_model).distinct())))
            checks["knowledge"] = {"chunks": count, "embedding_models": models}
    except Exception:  # noqa: BLE001 - any failure means the dependency is down
        pass
    providers = [p.name for p in build_llm().providers]
    checks["llm_providers"] = providers or "none configured"
    healthy = checks["database"] == "ok" and checks["pgvector"] == "ok"
    body = {
        "status": "ok" if healthy and providers else ("degraded" if healthy else "down"),
        "checks": checks,
        "demo_mode": get_settings().demo_mode,
        "banner": DEMO_BANNER if get_settings().demo_mode and get_settings().demo_notice else None,
    }
    return JSONResponse(body, status_code=200 if healthy else 503)


app.include_router(router)
app.include_router(admin_router)
app.include_router(accounts_router)
app.include_router(care_router)
app.include_router(library_router)
app.include_router(registration_router)
app.include_router(queue_router)
app.include_router(setup_router)
app.include_router(patients_router)
app.include_router(documents_router)
app.include_router(messaging_router)
app.include_router(ws_router)

# The built React app (ui/dist) is served from the same origin, so one container serves everything.
UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"
if (UI_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Static files from the build, and index.html for every client-side route."""
        if path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404)
        candidate = (UI_DIST / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(UI_DIST):
            return FileResponse(candidate)
        return FileResponse(UI_DIST / "index.html", headers={"Cache-Control": "no-cache"})
