"""Admin analytics: SQL validator, read-only execution, analytics agent (FR-30, FR-31, TC-14, TC-15)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.agent.llm import ScriptedLLM
from app.analytics.agent import answer_question
from app.analytics.sql_guard import run_readonly, validate_sql
from app.api.deps import get_llm
from app.api.main import app
from app.api.routes import chat_limiter
from app.db.models import Appointment
from app.tools.booking import book_appointment
from app.tools.errors import ToolError
from tests.conftest import NOW, TODAY

SAFE = [
    "SELECT count(*) FROM appointments WHERE status = 'no_show'",
    "select department, count(*) from appointments group by department order by 2 desc",
    "WITH w AS (SELECT doctor, avg(wait_minutes) m FROM queue_entries GROUP BY doctor) SELECT * FROM w",
    "SELECT date_trunc('week', appt_date) AS week, count(*) FROM reporting.appointments GROUP BY 1",
    "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY wait_minutes) FROM queue_entries",
    "SELECT d.name, count(a.id) FROM doctors d LEFT JOIN appointments a ON a.doctor_id = d.id GROUP BY d.name",
]

UNSAFE = [
    "DELETE FROM appointments WHERE status = 'no_show'",  # TC-14
    "SELECT 1; DROP TABLE appointments",  # TC-15
    "SELECT count(*) FROM appointments; DELETE FROM appointments",  # TC-15
    "UPDATE appointments SET status = 'cancelled'",
    "INSERT INTO appointments (id) VALUES (1)",
    "DROP TABLE audit_log",
    "TRUNCATE queue_entries",
    "GRANT ALL ON appointments TO public",
    "SELECT * INTO copy_of_appointments FROM appointments",
    "SELECT * FROM appointments FOR UPDATE",
    "SELECT * FROM public.patient",
    "SELECT phone_masked FROM patient",
    "SELECT * FROM pg_shadow",
    "SELECT * FROM pg_catalog.pg_roles",
    "SELECT pg_sleep(10)",
    "SELECT current_setting('server_version')",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * FROM appointments a, generate_series(1, 100000000) g",
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT * FROM r",
    "COPY appointments TO PROGRAM 'rm -rf /'",
    "EXPLAIN ANALYZE DELETE FROM appointments",
    "SET ROLE careflow",
    "",
    "not sql at all ((",
]


@pytest.mark.parametrize("sql", SAFE)
def test_read_only_selects_over_reporting_views_pass(sql):
    assert validate_sql(sql)


@pytest.mark.parametrize("sql", UNSAFE)
def test_unsafe_sql_is_rejected_by_the_validator(sql):
    with pytest.raises(ToolError) as err:
        validate_sql(sql)
    assert err.value.code == "UNSAFE_QUERY"


@pytest.fixture
def booked(world):
    doctor = world.doctor("Dr. Suresh Pawar")
    slot = world.slots(doctor, TODAY)[3]
    book_appointment(world.db, world.staff, world.asha.patient_id, slot.id, confirmed=True, now=NOW)
    world.db.commit()
    return world


def test_queries_run_read_only_with_a_row_limit(booked):
    engine = booked.db.get_bind()
    result = run_readonly(engine, "SELECT doctor, status FROM appointments")
    assert result.columns == ["doctor", "status"] and result.rows == [["Dr. Suresh Pawar", "booked"]]
    many = run_readonly(engine, "SELECT id FROM slots", max_rows=5)
    assert len(many.rows) == 5 and many.truncated


def test_the_analytics_role_cannot_read_patient_columns(booked):
    with booked.db.get_bind().connect() as conn:
        conn.execute(text("SET ROLE careflow_analytics"))
        assert conn.execute(text("SELECT count(*) FROM reporting.appointments")).scalar() == 1
        with pytest.raises(Exception, match="permission denied"):
            conn.execute(text("SELECT name FROM public.patient"))
        conn.rollback()


def test_a_write_cannot_slip_through_even_without_the_validator(booked):
    """Defence in depth: the transaction itself is read-only."""
    with booked.db.get_bind().connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        with pytest.raises(Exception, match="read-only transaction"):
            conn.execute(text("DELETE FROM appointment"))
        conn.rollback()


def admin(world):
    return world.user("mehta")


def test_agent_answers_with_a_validated_query(booked):
    llm = ScriptedLLM(
        [
            lambda m: {"run_sql": {"sql": "SELECT count(*) AS n FROM appointments WHERE status = 'booked'"}},
            lambda m: "There is 1 booked appointment.",
        ]
    )
    out = answer_question(booked.db, admin(booked), "How many booked appointments are there?", llm, now=NOW)
    assert out.answer == "There is 1 booked appointment." and out.rows == [[1]] and "count" in out.sql.lower()
    assert '"rows": [[1]]' in llm.calls[1][-1]["content"]


def test_tc14_request_to_delete_rows_is_refused_before_the_llm(booked):
    llm = ScriptedLLM([])
    with pytest.raises(ToolError) as err:
        answer_question(booked.db, admin(booked), "Delete last week's no-shows", llm, now=NOW)
    assert err.value.code == "UNSAFE_QUERY" and llm.calls == []
    assert booked.db.scalar(select(func.count()).select_from(Appointment)) == 1


def test_unsafe_sql_written_by_the_llm_is_never_executed(booked):
    llm = ScriptedLLM([lambda m: {"run_sql": {"sql": "SELECT 1; DELETE FROM appointments"}}])
    with pytest.raises(ToolError) as err:
        answer_question(booked.db, admin(booked), "How many appointments are there?", llm, now=NOW)
    assert err.value.code == "UNSAFE_QUERY"
    assert booked.db.scalar(select(func.count()).select_from(Appointment)) == 1


def test_a_failing_query_is_returned_to_the_llm_to_fix(booked):
    llm = ScriptedLLM(
        [
            lambda m: {"run_sql": {"sql": "SELECT count(*) FROM appointments WHERE no_such_column = 1"}},
            lambda m: {"run_sql": {"sql": "SELECT count(*) FROM appointments"}},
            lambda m: "1 appointment.",
        ]
    )
    out = answer_question(booked.db, admin(booked), "How many appointments?", llm, now=NOW)
    assert out.rows == [[1]] and "query failed" in llm.calls[1][-1]["content"]


def test_only_admins_may_ask(booked):
    with pytest.raises(ToolError) as err:
        answer_question(booked.db, booked.staff, "How many appointments?", ScriptedLLM([]), now=NOW)
    assert err.value.code == "FORBIDDEN"


def test_analytics_endpoint(booked):
    chat_limiter.reset()
    client = TestClient(app)
    try:
        llm = ScriptedLLM([lambda m: {"run_sql": {"sql": "SELECT count(*) FROM appointments"}}, lambda m: "One."])
        app.dependency_overrides[get_llm] = lambda: llm
        token = client.post("/api/v1/auth/demo-login", json={"role": "admin"}).json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        ok = client.post("/api/v1/admin/analytics", json={"question": "How many appointments?"}, headers=auth)
        assert ok.status_code == 200 and ok.json()["rows"] == [[1]] and ok.json()["sql"]
        bad = client.post("/api/v1/admin/analytics", json={"question": "drop the audit log table"}, headers=auth)
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "UNSAFE_QUERY"
        patient = client.post("/api/v1/auth/demo-login", json={"role": "patient"}).json()["token"]
        denied = client.post(
            "/api/v1/admin/analytics",
            json={"question": "How many appointments?"},
            headers={"Authorization": f"Bearer {patient}"},
        )
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()
