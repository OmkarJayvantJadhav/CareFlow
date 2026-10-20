"""reporting views and a SELECT-only role for analytics (FR-30, FR-31)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20 09:10:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Views over the operational tables without patient names or phone numbers. Patients appear only
# as patient_ref (the internal id), birth year and preferred language.
VIEWS = {
    "departments": """
        SELECT id, name, floor, opd_start, opd_end FROM public.department""",
    "doctors": """
        SELECT d.id, d.name, d.department_id, dep.name AS department, d.languages, d.opd_days, d.slot_minutes
        FROM public.doctor d JOIN public.department dep ON dep.id = d.department_id""",
    "slots": """
        SELECT s.id, s.doctor_id, s.start_at, s.end_at, s.status FROM public.slot s""",
    "appointments": """
        SELECT a.id, a.patient_id AS patient_ref, p.birth_year AS patient_birth_year,
               p.preferred_language AS patient_language, a.doctor_id, d.name AS doctor, dep.name AS department,
               a.appt_date, s.start_at, a.status, a.source, a.created_at, a.updated_at
        FROM public.appointment a
        JOIN public.patient p ON p.id = a.patient_id
        JOIN public.slot s ON s.id = a.slot_id
        JOIN public.doctor d ON d.id = a.doctor_id
        JOIN public.department dep ON dep.id = d.department_id""",
    "waiting_list": """
        SELECT w.id, w.patient_id AS patient_ref, w.doctor_id, w.status, w.created_at FROM public.waiting_list w""",
    "queue_sessions": """
        SELECT q.id, q.doctor_id, d.name AS doctor, q.date, q.merge_rule, q.status, q.doctor_status,
               q.delay_minutes, q.started_at, q.closed_at
        FROM public.queue_session q JOIN public.doctor d ON d.id = q.doctor_id""",
    "queue_entries": """
        SELECT e.id, e.session_id, q.doctor_id, q.date, e.patient_id AS patient_ref, e.kind, e.priority, e.status,
               e.scheduled_at, e.checked_in_at, e.called_at, e.consult_start, e.consult_end,
               EXTRACT(EPOCH FROM (e.consult_start - e.checked_in_at)) / 60 AS wait_minutes,
               EXTRACT(EPOCH FROM (e.consult_end - e.consult_start)) / 60 AS consult_minutes
        FROM public.queue_entry e JOIN public.queue_session q ON q.id = e.session_id""",
    "queue_events": """
        SELECT id, session_id, type, at FROM public.queue_event""",
    "wait_predictions": """
        SELECT id, entry_id, predicted_min, low_min, high_min, model_version, at FROM public.wait_prediction""",
}

ROLE = "careflow_analytics"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS reporting")
    for name, body in VIEWS.items():
        op.execute(f"CREATE OR REPLACE VIEW reporting.{name} AS {body}")
    # A role that can only read the reporting views. Hosts that do not allow CREATE ROLE still get
    # the views; queries then rely on the read-only transaction and the SQL validator.
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN;
            END IF;
            GRANT USAGE ON SCHEMA reporting TO {ROLE};
            GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO {ROLE};
            EXECUTE format('GRANT {ROLE} TO %I', current_user);
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'could not create role {ROLE}; analytics uses read-only transactions only';
        END $$""")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS reporting CASCADE")
