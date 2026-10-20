"""registration and check-in: patient categories, late arrivals, custom registration fields, consent,
caregiver access requests

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-21 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("pregnant", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("patient", sa.Column("disability", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("queue_entry", sa.Column("late_minutes", sa.Integer(), nullable=True))

    op.create_table(
        "registration_field",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=40), nullable=False, unique=True),
        sa.Column("label_en", sa.String(length=80), nullable=False),
        sa.Column("label_hi", sa.String(length=80), nullable=False),
        sa.Column("label_mr", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('text', 'number', 'choice', 'yes_no')", name="ck_registration_field_kind"),
    )
    op.create_table(
        "patient_field_value",
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), primary_key=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("registration_field.id"), primary_key=True),
        sa.Column("value", sa.String(length=200), nullable=False),
    )
    op.create_table(
        "consent",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("by_user_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('reuse_registration', 'reminders', 'caregiver_access')", name="ck_consent_purpose"
        ),
    )
    op.create_index("ix_consent_patient_purpose", "consent", ["patient_id", "purpose", "at"])
    op.create_table(
        "caregiver_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("caregiver_user_id", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'declined')", name="ck_caregiver_request_status"),
    )
    op.create_index(
        "uq_caregiver_request_pending",
        "caregiver_request",
        ["caregiver_user_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_caregiver_request_pending", table_name="caregiver_request")
    op.drop_table("caregiver_request")
    op.drop_index("ix_consent_patient_purpose", table_name="consent")
    op.drop_table("consent")
    op.drop_table("patient_field_value")
    op.drop_table("registration_field")
    op.drop_column("queue_entry", "late_minutes")
    op.drop_column("patient", "disability")
    op.drop_column("patient", "pregnant")
