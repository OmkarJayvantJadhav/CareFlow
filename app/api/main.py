"""FastAPI application. Phase 1 exposes only the health check; the rest of the
/api/v1 surface (docs §7) is added in later phases."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import HOSPITAL_NAME, get_settings
from app.db.session import get_engine
from app.safety.privacy import install_log_masking

DEMO_BANNER = "Demo with a fictional hospital. Not for medical use."

install_log_masking()
app = FastAPI(title="CareFlow API", version="0.1.0", description=f"{HOSPITAL_NAME} (fictional). {DEMO_BANNER}")


@app.get("/api/v1/health", tags=["platform"])
def health() -> JSONResponse:
    """Liveness and dependency status; 503 when the database is unreachable."""
    checks = {"database": "down", "pgvector": "missing"}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
            if conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first():
                checks["pgvector"] = "ok"
    except Exception:  # noqa: BLE001 - any failure means the dependency is down
        pass
    healthy = checks["database"] == "ok" and checks["pgvector"] == "ok"
    body = {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
        "demo_mode": get_settings().demo_mode,
        "banner": DEMO_BANNER,
    }
    return JSONResponse(body, status_code=200 if healthy else 503)
