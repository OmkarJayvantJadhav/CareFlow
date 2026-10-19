"""FastAPI application: /api/v1 REST endpoints, chat, health."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.agent.llm import build_llm
from app.api.routes import router
from app.config import HOSPITAL_NAME, get_settings
from app.db.models import KbChunk
from app.db.session import get_engine, session_factory
from app.safety.privacy import install_log_masking
from app.tools.errors import ToolError

DEMO_BANNER = "Demo with a fictional hospital. Not for medical use."

install_log_masking()
log = logging.getLogger("careflow.api")
app = FastAPI(title="CareFlow API", version="0.2.0", description=f"{HOSPITAL_NAME} (fictional). {DEMO_BANNER}")


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
        "banner": DEMO_BANNER,
    }
    return JSONResponse(body, status_code=200 if healthy else 503)


app.include_router(router)
