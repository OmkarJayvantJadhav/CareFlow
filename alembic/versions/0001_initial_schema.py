"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-19 15:45:24.334965
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

APPEND_ONLY_TABLES = ("queue_event", "wait_prediction", "audit_log")

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "department",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("floor", sa.SmallInteger(), nullable=False),
        sa.Column("opd_start", sa.Time(), nullable=False),
        sa.Column("opd_end", sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "kb_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("last_verified", sa.Date(), nullable=False),
        sa.Column("source_path", sa.String(length=300), nullable=False),
        sa.CheckConstraint("language IN ('en', 'hi', 'mr')", name="ck_kb_document_language"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_path"),
    )
    op.create_index(op.f("ix_kb_document_collection"), "kb_document", ["collection"], unique=False)
    op.create_table(
        "patient",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("synthetic_name", sa.String(length=120), nullable=False),
        sa.Column("birth_year", sa.SmallInteger(), nullable=False),
        sa.Column("phone_masked", sa.String(length=20), nullable=False),
        sa.Column("preferred_language", sa.String(length=8), nullable=False),
        sa.CheckConstraint("phone_masked ~ '^\\+91 [0-9]{2}X{6}[0-9]{2}$'", name="ck_patient_phone_masked"),
        sa.CheckConstraint("preferred_language IN ('en', 'hi', 'mr')", name="ck_patient_language"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=60), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("role <> 'patient' OR patient_id IS NOT NULL", name="ck_app_user_patient_has_record"),
        sa.CheckConstraint("role IN ('patient', 'caregiver', 'staff', 'admin')", name="ck_app_user_role"),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "doctor",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("languages", sa.ARRAY(sa.String(length=8)), nullable=False),
        sa.Column("opd_days", sa.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("slot_minutes", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("slot_minutes BETWEEN 5 AND 60", name="ck_doctor_slot_minutes"),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_doctor_department_id"), "doctor", ["department_id"], unique=False)
    op.create_table(
        "kb_chunk",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(section, '') || ' ' || text)", persisted=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["kb_document.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kb_chunk_document_id"), "kb_chunk", ["document_id"], unique=False)
    op.create_index(
        "ix_kb_chunk_embedding",
        "kb_chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_kb_chunk_tsv", "kb_chunk", ["tsv"], unique=False, postgresql_using="gin")
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mocked", sa.Boolean(), nullable=False),
        sa.CheckConstraint("channel IN ('sms', 'whatsapp')", name="ck_notification_channel"),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_patient_id"), "notification", ["patient_id"], unique=False)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("tool", sa.String(length=60), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_user_id"), "audit_log", ["user_id"], unique=False)
    op.create_table(
        "caregiver_link",
        sa.Column("caregiver_user_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["caregiver_user_id"],
            ["app_user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
        ),
        sa.PrimaryKeyConstraint("caregiver_user_id", "patient_id"),
    )
    op.create_table(
        "handoff_ticket",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'closed')", name="ck_handoff_ticket_status"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "queue_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("merge_rule", sa.String(length=12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("doctor_status", sa.String(length=12), nullable=False),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("busy_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "doctor_status IN ('available', 'on_break', 'delayed', 'unavailable')",
            name="ck_queue_session_doctor_status",
        ),
        sa.CheckConstraint("merge_rule IN ('slot_order', 'alternate')", name="ck_queue_session_merge_rule"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_queue_session_status"),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctor.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "date", name="uq_queue_session_doctor_date"),
    )
    op.create_table(
        "slot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="free", nullable=False),
        sa.Column("held_for_patient_id", sa.Integer(), nullable=True),
        sa.Column("held_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('free', 'booked', 'blocked')", name="ck_slot_status"),
        sa.CheckConstraint("end_at > start_at", name="ck_slot_times"),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctor.id"],
        ),
        sa.ForeignKeyConstraint(
            ["held_for_patient_id"],
            ["patient.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "start_at", name="uq_slot_doctor_start"),
    )
    op.create_table(
        "appointment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("appt_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("source IN ('agent', 'staff', 'simulator')", name="ck_appointment_source"),
        sa.CheckConstraint(
            "status IN ('booked', 'rescheduled', 'cancelled', 'completed', 'no_show', 'displaced')",
            name="ck_appointment_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctor.id"],
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
        ),
        sa.ForeignKeyConstraint(
            ["slot_id"],
            ["slot.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appointment_patient", "appointment", ["patient_id"], unique=False)
    op.create_index(
        "uq_appointment_active_patient_doctor_day",
        "appointment",
        ["patient_id", "doctor_id", "appt_date"],
        unique=True,
        postgresql_where=sa.text("status IN ('booked', 'rescheduled')"),
    )
    op.create_index(
        "uq_appointment_active_slot",
        "appointment",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('booked', 'rescheduled')"),
    )
    op.create_table(
        "queue_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('check_in', 'walk_in', 'call', 'consult_start', 'consult_end', 'missed_turn', 'return', 'priority', 'break', 'resume', 'delay', 'emergency', 'unavailable', 'session_closed')",
            name="ck_queue_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["queue_session.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_queue_event_session", "queue_event", ["session_id", "at"], unique=False)
    op.create_table(
        "waiting_list",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("preferred_dates", sa.ARRAY(sa.Date()), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("offered_slot_id", sa.Integer(), nullable=True),
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'offered', 'fulfilled', 'cancelled')", name="ck_waiting_list_status"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctor.id"],
        ),
        sa.ForeignKeyConstraint(
            ["offered_slot_id"],
            ["slot.id"],
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_waiting_list_active",
        "waiting_list",
        ["patient_id", "doctor_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'offered')"),
    )
    op.create_table(
        "queue_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requeued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consult_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consult_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint("kind = 'walk_in' OR appointment_id IS NOT NULL", name="ck_queue_entry_booked_has_appt"),
        sa.CheckConstraint("kind IN ('booked', 'walk_in')", name="ck_queue_entry_kind"),
        sa.CheckConstraint(
            "status IN ('waiting', 'called', 'in_consultation', 'done', 'missed', 'closed')",
            name="ck_queue_entry_status",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["appointment.id"],
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["queue_session.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", name="uq_queue_entry_appointment"),
        sa.UniqueConstraint("session_id", "token", name="uq_queue_entry_token"),
    )
    op.create_index("ix_queue_entry_session", "queue_entry", ["session_id"], unique=False)
    op.create_table(
        "wait_prediction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("predicted_min", sa.Double(), nullable=False),
        sa.Column("low_min", sa.Double(), nullable=False),
        sa.Column("high_min", sa.Double(), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["queue_entry.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wait_prediction_entry", "wait_prediction", ["entry_id", "at"], unique=False)

    # Append-only tables: corrections are new rows (docs §6). TRUNCATE (demo reset) is allowed.
    op.execute(
        """
        CREATE FUNCTION careflow_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION careflow_append_only()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS careflow_append_only()")
    op.drop_index("ix_wait_prediction_entry", table_name="wait_prediction")
    op.drop_table("wait_prediction")
    op.drop_index("ix_queue_entry_session", table_name="queue_entry")
    op.drop_table("queue_entry")
    op.drop_index(
        "uq_waiting_list_active", table_name="waiting_list", postgresql_where=sa.text("status IN ('active', 'offered')")
    )
    op.drop_table("waiting_list")
    op.drop_index("ix_queue_event_session", table_name="queue_event")
    op.drop_table("queue_event")
    op.drop_index(
        "uq_appointment_active_slot",
        table_name="appointment",
        postgresql_where=sa.text("status IN ('booked', 'rescheduled')"),
    )
    op.drop_index(
        "uq_appointment_active_patient_doctor_day",
        table_name="appointment",
        postgresql_where=sa.text("status IN ('booked', 'rescheduled')"),
    )
    op.drop_index("ix_appointment_patient", table_name="appointment")
    op.drop_table("appointment")
    op.drop_table("slot")
    op.drop_table("queue_session")
    op.drop_table("handoff_ticket")
    op.drop_table("caregiver_link")
    op.drop_index(op.f("ix_audit_log_user_id"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_notification_patient_id"), table_name="notification")
    op.drop_table("notification")
    op.drop_index("ix_kb_chunk_tsv", table_name="kb_chunk", postgresql_using="gin")
    op.drop_index(
        "ix_kb_chunk_embedding",
        table_name="kb_chunk",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_kb_chunk_document_id"), table_name="kb_chunk")
    op.drop_table("kb_chunk")
    op.drop_index(op.f("ix_doctor_department_id"), table_name="doctor")
    op.drop_table("doctor")
    op.drop_table("app_user")
    op.drop_table("patient")
    op.drop_index(op.f("ix_kb_document_collection"), table_name="kb_document")
    op.drop_table("kb_document")
    op.drop_table("department")
