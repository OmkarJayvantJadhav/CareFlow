"""Schema/migration consistency and the health endpoint."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.api.main import app
from app.db.models import Base


def test_migrations_match_models(engine):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_schema_has_the_designed_tables_plus_later_phases_and_pgvector(engine):
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    later = {
        "conversation",
        "doctor_leave",
        "registration_field",
        "patient_field_value",
        "consent",
        "caregiver_request",
        "priority_rule",
        "priority_request",
    }
    assert len(tables) == 17 + len(later) and later <= tables
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar() == 1


def test_double_booking_indexes_exist(engine):
    indexes = {i["name"] for i in inspect(engine).get_indexes("appointment")}
    assert {"uq_appointment_active_slot", "uq_appointment_active_patient_doctor_day"} <= indexes


def test_health(engine, kb):
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    checks = body["checks"]
    assert checks["database"] == "ok" and checks["pgvector"] == "ok"
    assert checks["knowledge"]["chunks"] == kb["chunks"]
    assert checks["knowledge"]["embedding_models"] == [kb["embedder"]]
    # No LLM key is configured in tests, so chat is unavailable and the status says so.
    assert checks["llm_providers"] == "none configured" and body["status"] == "degraded"
    assert "Not for medical use" in body["banner"]
